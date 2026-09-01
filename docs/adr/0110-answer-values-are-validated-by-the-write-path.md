# 0110 — An answer's value is validated by the write path, not by a constraint on `answer`

**Status:** Accepted
**Date:** 2026-09-01
**Tickets:** E2-05

## Context

SPEC §3.2 gives two of its five questions a Likert scale of 1 to 5 and the
workload question a "range 0-40, 0.5-hour steps". (The section writes both ranges
with an en dash; a hyphen is used throughout this record because the linter reads
the en dash as a confusable character.) E2-05 stores those ranges as data — a
minimum, a maximum and a step on each `question` row — because §3.2 says the set
is versioned precisely so a later feature can append questions without a schema
migration, and a range hard-coded anywhere would be a range that could not travel
with a new question.

That leaves an obvious question about the other table. `answer` holds exactly one
of three values: an integer `rating`, a `comment_text`, or a decimal
`workload_hours`. Nothing in E2-05 stops a `rating` of 9 or a `workload_hours` of
400 from being written.

A `CHECK` constraint cannot help, because a `CHECK` cannot read another table —
that is the same limitation
[ADR 0018](0018-cross-table-length-rules-are-enforced-by-a-composite-foreign-key.md)
opens with, and the reason a week's number is checked against a copy of its
term's length rather than against `term` itself. The bound an answer must satisfy
lives on the `question` row it points at, one join away.

E2-05 is a schema ticket. The write path that will submit a response is E2-08's,
and it does not exist yet, so this decision is about what the schema does in the
meantime and what E2-08 inherits.

## Decision

**`answer` carries no range check on any of its three value columns.** The only
constraint over them is `holds_exactly_one_value` — `num_nonnulls(rating,
comment_text, workload_hours) = 1` — which is about the shape of the row rather
than about the value in it. The three columns keep their types (`Integer`, `Text`,
`Numeric(4, 1)`) and nothing else.

**The bounds are enforced by E2-08's write path**, which reads the question a
submitted value answers and checks the value against that question's
`minimum_value`, `maximum_value` and `step`. That is one place, on the path every
submission takes, reading the one statement of the range that exists.

The ranges being data on `question` is what makes this the right split rather
than a concession. There is exactly one place a range is written down, so there
is nothing for a second copy to disagree with.

## Alternatives rejected

**A literal range check on `answer` — `rating BETWEEN 1 AND 5`, `workload_hours
BETWEEN 0 AND 40`.** The tempting one, and it loses on the same ground the
ranges-as-data decision stands on. It is a second statement of a rule that is
already stated on `question`, so the two can disagree: a v2 question set with a
1-to-7 scale, which §3.2 explicitly anticipates, would be refused by a constraint
nobody thought to move. It also has to name a *particular* question's range while
the column serves every question of every set. That is the shape
`docs/MISTAKES.md` warns about as a rule two constraints both have to satisfy —
green while they agree, and silently wrong the first time they do not.

**ADR 0018's composite-foreign-key mechanism, carrying the bounds onto `answer`.**
This one genuinely works, and it is the reason this record exists rather than a
comment in the model. Give `question` a `UNIQUE (id, minimum_value,
maximum_value, step)`, give `answer` three carried columns and a composite
foreign key `(question_id, minimum_value, maximum_value, step)` referencing them,
and a local `CHECK` can then compare `rating` against bounds sitting on its own
row — exactly what `week.term_length_weeks` does with its term's length. Rejected
on cost, and the cost is concrete:

- Three carried columns on the largest table in the schema. `answer` grows by
  five rows per response per student per week; `week` has eighteen rows per term.
  What ADR 0018 spends one integer on for a small table, this would spend three
  numerics on for the biggest one.
- The carried values are nullable for both comment questions, and a composite
  foreign key under `MATCH SIMPLE` is not checked at all when any key column is
  null — so the mechanism would be silently absent for exactly the rows where
  `comment_text` is set, and present only where it is not.
- The rule it buys is still only "the value is inside the bounds". The step is
  the harder half — 3.25 hours is inside 0 to 40 and is not a multiple of 0.5 —
  and a modulo over two numerics in a `CHECK` is not a comparison anybody should
  have to read at 11pm.
- `ON UPDATE CASCADE` would rewrite every answer row in the deployment when an
  admin edited a question's range, which is a schema migration wearing an
  `UPDATE`'s clothes.

The bounds are also not the only rule a submission has to satisfy: §3.2's
conditional requirement ("Required if Q1 ≤ 2") is about *other answers in the
same response*, which no per-row constraint of any kind can see. So E2-08 owns a
validation step whatever this record decides, and the choice is whether the
range half of it lives in two places or one.

**A trigger on `answer` that joins to `question`.** Rejected for the reason ADR
0018 rejected a trigger for the length rules, and the reasoning transfers
unchanged: a trigger reads the other row at the moment it fires and commits a
violating row when that row is edited concurrently. It would also put product
logic in PL/pgSQL, which nothing in this repository does.

**A `CHECK` naming a range wide enough for anything — `rating > 0`.** Refuses
almost nothing and reads as though somebody checked, which is worse than the
honest absence.

## Consequences

**A `rating` of 9 is storable by anything that is not E2-08.** A hand-written
`INSERT`, a repair script, a future backfill, a migration. That is the price, and
it is stated here so that whoever meets such a row knows it was foreseen rather
than missed. What contains it is that `pulse_app` is granted nothing on `answer`
by E2-05's migration at all, and E2-08 grants the privilege its own path needs
beside the code that justifies it — the same shape
[ADR 0055](0055-a-classification-row-names-its-task-and-no-comment.md) gives
`classification`.

**E2-08 owes a validation step and owes tests for it**, including the two edges a
constraint would have caught: a value outside its question's range, and a value
inside the range that is not a multiple of the step. Nothing in the schema will
be red if it forgets.

**`question.minimum_value`, `maximum_value` and `step` are the only statement of
the ranges in the system.** E2-08 validates against them and E2-10 renders the
slider from them, so a wrong value seeded into one of those columns is wrong
everywhere with nothing to disagree with it. That is why
`tests/integration/test_demo_seed_script.py` compares all three against SPEC
§3.2's own numbers rather than against anything the implementation can reach.

**A later ticket may still take the composite-key mechanism**, and this record is
the argument it would have to answer rather than a door closed. What would change
the balance is a measured incident: a bad row reaching a report through a path
that is not E2-08.
