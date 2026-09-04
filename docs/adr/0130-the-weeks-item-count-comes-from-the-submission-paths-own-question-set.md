# 0130 — A week's item count comes from the submission path's own question set

## Context

SPEC §3.4's participation score, as ruled on 2026-09-04, is completed items over
total items across a student's elapsed weeks. The total for a week is "derived
from the `question_set` in force for it (§3.2) and is never a constant". The spec
stops there, and E3-03 has to say *which* set a past week's total is taken from.

Nothing in the schema answers it. `response` carries `week_id` and `term_id` and
no `question_set_id` (E2-05), so a week's response does not record the instrument
it was answered against. Exactly one set exists today — §3.2's v1 — which is the
condition under which every candidate rule gives the same answer and a wrong one
is green.

`app.services.submissions.current_questions` already answers a neighbouring
question for the submit path: which questions a student is served right now. It
takes the set at the highest `version`, and E2-08 recorded why that rule and not
another: the table has no `is_active` column because no ticket has yet specified
how a second set would be chosen.

## Decision

E3-03's denominator for every elapsed week is the number of questions
`current_questions` returns — the same call the submission path makes, not a
second reading of the same table.

One rule in one place. If the way a set is chosen ever changes, the ticket that
changes it changes what students are asked and what they are scored out of in the
same edit, because both go through that one function.

## Alternatives rejected

- **Resolve each week's set through its answered `question` rows.** The set a
  week's answers point at is recorded and needs no new column, which is what makes
  it attractive. It loses on two cases the formula is mostly about: two students
  who answered one week against different set versions would get different
  denominators for the same week, and a week nobody answered resolves to no set at
  all — and a missed week is precisely where the denominator has to be right,
  because it carries its full weight with a numerator of zero.
- **Record the set on the `survey_window` row at derivation time.** This is the
  faithful answer — it says what was in force when the window opened — and it is a
  schema change to a table E2-06 owns, with a backfill for every window already
  written. E3-03 does not own that table and a migration is out of its scope. It
  stays the right answer for the ticket that ships a second set version.
- **A constant of five.** §3.2 ships five questions and the arithmetic would be
  correct today. The table is versioned precisely so that it need not be five
  tomorrow, and a literal is wrong the first time a version changes with nothing
  failing to say so.

## Consequences

A second version of the question set **re-denominates weeks that have already
passed**. A week answered five items of five against v1 becomes five of three
against a v2 carrying three questions, and an already-posted score changes for a
reason no student did anything to cause. That is the price of having no per-week
record of the instrument, and it is stated here rather than discovered.

So the ticket that ships a second set version owes three things: the rule for
choosing between versions (which `current_questions` does not have — highest wins
is a placeholder, not a policy), the per-week record that makes a past week's
total stable, and E2-09's open read-back question, which asks what a student sees
when they re-open a response answered against an older set. None of those can be
deferred past that ticket, because the day a second row lands in `question_set` is
the day every past score moves.

Until then, the guarantee is narrow and testable: the denominator follows the set,
proved by planting a set of a different size and watching the total move
(`tests/integration/test_the_denominator_comes_from_the_weeks_question_set.py`),
with no integer literal five anywhere in the module.
