# E3-03 — The participation formula

**ID:** E3-03
**Branch:** `e3/participation-formula`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** the diff is arithmetic and reads no identity beyond
the enrollment it is scoring, but it sits in `backend/app/services/`, which
is a heavy-lane row, and it is the first reader of `response.is_valid` —
a field E2 wrote and nothing has read since.

## Context

SPEC §3.4's score, computed and nothing else: no AGS, no job, no network, no
posting. The whole ticket is one module, `backend/app/services/grading.py`
(the home SPEC §13 already names for it), that answers one question — for a
section and a student, what fraction of the items they could have completed
have they completed, and what does the per-week ledger say.

The formula changed at breakdown. **Ruled 2026-09-04:** the fraction is
completed items ÷ total items across the student's elapsed weeks, not valid
weeks ÷ elapsed weeks; and **ruled 2026-09-04:** the posted score carries a
comment holding one line per elapsed week, `Week 1: 4 of 5 items`. SPEC §3.3
and §3.4 are corrected in the breakdown's own pull request, so this ticket
builds from a spec that already says the right thing.

The ground this reads is all E2's and all present:

- `response` is unique per student, section and week, and carries `week_id`
  (`backend/app/models/survey.py:368`) and `term_id`
  (`backend/app/models/survey.py:376`). It does **not** carry
  `question_set_id`, which is why the denominator's derivation is a decision
  below rather than a lookup.
- `answer` rows exist only for questions a submission actually carried, and a
  revision that withdraws an answer deletes its row (ADR 0115). So the answer
  set is a faithful record of what was answered, and a blank optional comment
  is simply an absent row.
- `classification` (`backend/app/models/ai.py:100`) is append-only with
  `answer_id` (`backend/app/models/ai.py:142`), so a comment's governing
  verdict is the latest row, never the only row.
- `REFUSED_VERDICTS` (`backend/app/services/validity.py:102`) is the set that
  makes a comment not count.
- `Enrollment` (`backend/app/models/identity.py:288`) carries two date pairs —
  `started_on`/`ended_on`, which are Pulse's own first- and last-sighting
  record, and `lms_window_start`/`lms_window_end`, which are the platform's.
  §3.4's three late-add tiers are exactly a rule for choosing between them.

Read first: SPEC §3.1, §3.3, §3.4, §9.1, §2.2; ADR 0095 (two windows, no
status, and a member the sync refuses to date); ADR 0109 (the development
clock is an offset, not a freeze); ADR 0115; ADR 0052 (why the posted string
and not just the posted number is what matters); the E2-04 clock service.

## Scope

- For one section, per enrolled student: the elapsed course weeks under
  §3.4's three enrollment tiers, the completed-item numerator, the total-item
  denominator taken from the week's question set, the percentage, and the
  ledger string.
- A completed item is an `answer` row that counts. A rating or a workload
  answer counts by existing. A comment answer counts by existing *and* by its
  latest classification not being in `REFUSED_VERDICTS`. An absent answer,
  including a blank optional comment, is not completed.
- A missed week contributes zero completed items and its full denominator.
- The canonical percentage: one rounding rule, one formatting rule, one
  string, produced here and consumed unchanged by everything downstream.
- The ledger: one line per elapsed week, in course-week order.
- Hypothesis properties over adds, drops, missed weeks and partially answered
  weeks — the four §9.1 names once this breakdown's spec edit adds the fourth.

## Acceptance criteria

1. A student who answered every item of every elapsed week scores 100%, and a
   student who answered none scores 0% — both with the correct denominator,
   which is the part that can be wrong while both numbers look right.
2. A week answered four items of five produces four fifths of that week's
   contribution and a ledger line reading `Week N: 4 of 5 items`.
3. The three §3.4 tiers select the right first week: a platform-dated late
   add starts at the platform's date; an undated member starts at the
   section's start date; a member first seen in a roster sync later than the
   section's first sync starts at the week of that sync. Each tier is driven
   by its own case, and the boundary week is asserted on both sides
   (`docs/MISTAKES.md` entry 3).
4. Zero elapsed weeks produces no score at all — a distinguishable "nothing
   to post", not a zero. The caller cannot mistake the two.
5. A comment whose latest classification is `insufficient` or `nonsense` does
   not count its item, and a later classification row changes the answer —
   asserted by adding a row, not by editing one, because the table is
   append-only.
6. The denominator is derived from the week's question set and a test proves
   it: a question set with a different number of questions produces a
   different denominator, with no constant `5` anywhere in the module.
7. The Hypothesis properties hold across generated enrollment shapes, and the
   generator provably includes the boundary cases its docstring names
   (`docs/MISTAKES.md` entry 15).
8. No network call, no AGS type, and no job import appears in the module.
9. Nothing in the tree still states the superseded formula as the current
   rule. Twelve files outside `docs/SPEC.md` and `docs/tickets/e3/` carried
   the phrase "valid weeks completed ÷ weeks elapsed" or a variant of it when
   this breakdown was written, across sixteen lines: `backend/app/models/`,
   `backend/app/views_sql/`, `backend/migrations/versions/`, `mock-lms/app/`
   and eight test modules. Each is re-read and either corrected or dated as
   history in this ticket's pull request, and the grep is re-run and reported
   rather than assumed clean.

## Decisions this ticket settles

- **How the week's question set is derived.** `response` carries no
  `question_set_id`, and today exactly one set exists, so any rule at all
  works and none of them is proven. The rule gets written down, not assumed:
  the candidates are the set the week's answered `question` rows resolve to,
  the set in force at the window's close, and a set recorded on the window.
  Whichever wins needs an ADR, because a versioned set with one version is
  the exact condition under which a wrong rule is green.
- **How tier 3 resolves "later than the section's first sync".**
  `enrollment.started_on` is Pulse's own first-sighting date (ADR 0095); the
  section's earliest `NrpsCall` row is the other candidate. They can disagree,
  and the disagreement is what the tier is about.
- **The rounding and formatting rule.** ADR 0052 rejected body deduplication
  partly because `61.5` and `61.50` are different bodies. One rule here, one
  string, stored by E3-02's `grade_sync` and re-sent verbatim by E3-04.
- **Whether a drop truncates the denominator or freezes the score.** §3.4
  says scores stop updating and the LMS owns the column; that is a rule about
  posting, and this module still has to answer what it computes for a dropped
  student. The recommendation is that it computes the same thing it always
  did and E3-06 stops posting — one behaviour in one place.

## Known traps

- **A posted score is not final when its week closes.** E2-08's asynchronous
  reclassification can flip a floored comment to `insufficient` weeks after
  the week closed, which lowers a numerator this module already answered. The
  module is pure and correct either way; the consequence is E3-06's, and it
  is the reason the recompute is a sweep rather than a one-shot. It is named
  here so the module's docstring says plainly that its answer is a function
  of the current classification state and not of the week.
- **There is no "unclassified" state.** A comment that fell to the fail-open
  floor already carries a verdict, written under `FLOOR_MODEL_ID` and
  `FLOOR_PROMPT_VERSION` (`backend/app/ai/tasks.py:117-118`). "Not yet
  classified" is not a case this module can see, and writing code for it
  would be writing code for a state that cannot occur.
- **The formula is the one part of this epic where a wrong answer is
  invisible.** A schema mistake fails a migration and a client mistake fails
  a call; a denominator mistake posts a plausible number into a real
  gradebook. Prefer asserting the forbidden state over the permitted one
  (`docs/MISTAKES.md` entry 2), and mutate the arithmetic to prove the tests
  can fail (entry 3).
- **The superseded formula is written into the tree in sixteen places, and
  none of them is code.** They are docstrings, SQL comments, a migration's
  prose and test module headers, all explaining *why* a rule exists by citing
  a formula this breakdown replaced. A grep for the identifier finds none of
  them; a grep for the fact finds all of them (`docs/MISTAKES.md` entry 1).
  Two more sit in `docs/disputes/`, which are dated records of an argument
  and are correct as history — the judgement of which class a hit belongs to
  is part of the work, and a merged migration's prose is the borderline case
  worth deciding out loud.
- **A property test whose generator excludes its own named case** is
  `docs/MISTAKES.md` entry 15, and the four cases §9.1 names — adds, drops,
  missed weeks, partially answered weeks — are exactly the ones a bounded
  strategy quietly drops.

## Out of scope

- Posting anything, creating a line item, or talking to a platform —
  E3-04, E3-05.
- The job that decides when to recompute — E3-06.
- Showing the number to a student or an instructor — E8 and E4; nothing in E3
  renders it.
