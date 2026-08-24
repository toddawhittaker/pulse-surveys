# 0018 — Cross-table length rules are enforced by a composite foreign key carrying the term's length

**Status:** Accepted
**Date:** 2026-08-14
**Tickets:** E0-06

## Context

Two rules in the academic calendar compare a row against *its own term*:

- a `week` row's `number` has to lie between 1 and the term's length (E0-06
  criterion 3, the range half);
- a `start_letter_map` row's `length_weeks` may not exceed the term's (criterion
  5).

[SPEC §2.2](../SPEC.md) makes term length institution configuration — 18 weeks
for fall and spring, 12 for summer — and gives course lengths their own set, 3
to 18. So both numbers are legal in general and only wrong against a particular
term: a 15-week letter is ordinary in an 18-week fall term and impossible in a
12-week summer one. A range check over §2.2's allowed lengths accepts every row
these rules exist to refuse.

A `CHECK` constraint cannot read another table. Postgres offers no cross-row
declarative constraint short of an assertion, which it does not implement. E0-06
names the shortlist — a trigger, a composite foreign key carrying the term's
length so the check becomes local, or something else — and leaves the choice to
the implementer, which is the test `CLAUDE.md` sets for a record.

## Decision

`week` and `start_letter_map` each carry a `term_length_weeks` column, and each
references its term through **one composite foreign key** rather than a plain
`term_id`:

```sql
CONSTRAINT uq_term_id_length_weeks UNIQUE (id, length_weeks)      -- on term
FOREIGN KEY (term_id, term_length_weeks) REFERENCES term (id, length_weeks)
    ON UPDATE CASCADE ON DELETE RESTRICT
CHECK (number >= 1 AND number <= term_length_weeks)               -- now local
```

The foreign key is what makes `term_length_weeks` mean "this row's term's
length" instead of "a number this row supplied", and the `CHECK` then compares
two columns of the same row, which the server enforces like any other. The extra
`UNIQUE (id, length_weeks)` on `term` exists only to give that key something to
reference; it is redundant against the primary key and dropping it drops both
rules.

`term_length_weeks` is not a column any write path sets on purpose.
`ON UPDATE CASCADE` rewrites it when the term's length changes, and the local
`CHECK` is re-evaluated on the cascaded row — so shortening a term below a week
that already exists is refused at the moment of the shortening.

Measured against the pinned Postgres (`postgres:17.10-bookworm`) before this was
written; the transcript is in `docs/tickets/e0/.attempts/E0-06.md`:

| Attempted | Outcome |
|---|---|
| week 12 in a 12-week term | accepted |
| week 13 in a 12-week term | refused, `ck_week_number_is_inside_the_term` |
| week 0 | refused, same constraint |
| week 13 claiming an 18-week term | refused, `fk_week_term_id_term_length_weeks_term` |
| lengthening the term 12 → 18 | accepted, and the copies cascade — which is not the whole of what it does; see "Lengthening is the silent direction" below |
| shortening 18 → 12 with a week 18 present | refused |
| deleting a term that still has weeks | refused, `ON DELETE RESTRICT` |

The fourth row is the one that matters: a row that *lies* about its term's
length is refused by the key, so the local check is not a weaker check.

## Alternatives rejected

**A `BEFORE INSERT OR UPDATE` trigger reading the term.** The obvious answer,
and the one that needs no extra column. Rejected on three counts, the first
measured rather than argued.

*It commits violating rows under concurrency.* Two transactions, both
individually valid, under `READ COMMITTED`, which is what the deployment runs: a
week 12 going in while its term is shortened to 6 weeks. The trigger reads the
term as of its own snapshot, and both transactions commit:

```
trigger
  insert:  committed
  shorten: committed
  left behind: a 6-week term holding weeks [12]
  VIOLATING ROWS: [12]

composite foreign key + local CHECK
  insert:  committed
  shorten: refused: new row for relation "week" violates check constraint
           "ck_week_number_is_inside_the_term"
  left behind: a 12-week term holding weeks [12]
  no violating rows
```

The key version blocks the second transaction on the referenced row's lock and
then refuses it through the cascade. The trigger version leaves a row no query
will ever complain about. Admins edit the calendar (§6.3), so shortening a term
is a thing that happens, not a hypothetical.

*It is procedural code with no drift gate.* A trigger lives as raw SQL in a
migration and is invisible to `alembic check`. Measured: a trigger created by
hand on `week`, in no migration and on no metadata, leaves `alembic check`
reporting "No new upgrade operations detected". So a trigger dropped by hand or
lost in a restore is a rule that silently stops existing, while the key and the
check are both on `Base.metadata` and removing either shows up as drift. That is E0-20's subject, and it argued against adding to the set of
things no gate watches.

*It is a second language in the schema.* A plpgsql function is the first one
here, and the one after it gets written by copying it.

**A `CHECK` calling an `IMMUTABLE`-declared function that reads `term`.**
Postgres accepts it and it is wrong: the function is not immutable, the check is
evaluated only for the row being written, and the lie about immutability is a
planner hazard. Refused on sight rather than measured.

**Storing no length on `term` and deriving it from the dates**, which would make
the comparison a date comparison. Not available: the ticket settles that the
length is stored, because §2.2 states term lengths as configuration and the spec
says neither whether `end_date` is inclusive nor what a span that is not a whole
number of weeks means.

**Nothing in the database, with the rule in `app/services/`.** SPEC §8 puts
containment and calendar rules in the server, and a rule in the application is
one a seed script, a migration and the admin console each get to forget.

## Consequences

**Two tables carry a denormalised copy of one number.** It is kept true by the
key rather than by discipline, and it costs four bytes a row on `week` (18 rows
a term) and on `start_letter_map` (a dozen or so). The cost that is worth
naming is comprehension: `week.term_length_weeks` looks like a column somebody
should maintain, and it is not. Both models say so where the column is
declared, and the module docstring says it again.

**Shortening a term fails at the shortening, naming a constraint on `week`.**
That is the correct behaviour — a 12-week term cannot hold a week 18 — but the
error names the child table, not the edit. When E11 ships the calendar editor,
it should catch this and say which weeks are in the way.

**Lengthening is the silent direction, and it leaves the term short of weeks.**
The two directions are not symmetric, and the asymmetry is the mechanism's:
shortening is refused because the cascade rewrites a row the CHECK then rejects,
and lengthening has nothing to reject, because the weeks that ought to exist do
not exist yet. Measured (PR #21's spec-conformance review found it; the
reproduction is in `docs/tickets/e0/.attempts/E0-06.md`, attempt 7): a 12-week
term with weeks 1–12 lengthened to 18 is accepted, the cascade sets
`term_length_weeks = 18` on all twelve rows, and the result is an 18-week term
holding twelve weeks with no error, no log line, and every surviving row looking
correct. Criterion 3's contiguity holds at creation and is broken by an ordinary
edit.

**E0-06 ships no reconciler, and `week_rows_for_term` cannot be one** — it always
emits 1..N, so a second call is refused by `uq_week_term_id_number`. Filling the
gap needs to see the existing rows, and deciding what shortening does to the
weeks past the new end (and to any `survey_window` keyed to one) is scheduling
and admin policy. That belongs to E2 and to E11's calendar editor (§6.3), which
is where a length is edited. This ADR is where the hazard is recorded so it
reaches them; the assertion that a term's weeks are 1..N *after* an edit belongs
to whichever of them closes it.

**Deleting a term requires deleting its weeks first** (`ON DELETE RESTRICT`,
matching every containment key in `app/models/org.py`). Deliberate: losing a term
would silently lose its weeks and every window keyed to them.

**A third such rule should use the same mechanism.** `survey_window` has one
available and does not take it: nothing yet stops a window pairing a section in
one term with a week in another. It would need `UNIQUE (id, term_id)` on both
`section` and `week` and a `term_id` on `survey_window`, which is a second index
on `section` for a table E2 has not started filling. Deferred to E2 with the
scheduling logic, when the rows exist to protect, and named here so the omission
is a decision rather than an oversight.
