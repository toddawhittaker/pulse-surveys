# E2-05 — The survey schema: questions, responses, answers, and the window's term rule

**ID:** E2-05
**Branch:** `e2/survey-schema`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** `response` is keyed to the student's identity — these
tables are the raw material of every §4 rule. Their identity-bearing columns
follow the marker conventions (ADR 0022) or the name-sweep review question
from the carried file applies to them.

## Context

E0's schema stopped at the calendar: `term`, `week`, `start_letter_map`, and
an empty `survey_window` exist (`backend/app/models/term.py`); `question_set`,
`question`, `response`, and `answer` do not exist anywhere. This ticket is the
schema slice and the seed, and nothing else — no window logic, no API.

ADR 0018's consequences name a rule deferred "to E2 with the scheduling
logic": nothing stops a `survey_window` pairing a section in one term with a
week in another. The mechanism is prescribed there — `UNIQUE (id, term_id)`
on `section` and on `week`, a `term_id` on `survey_window`, and the composite
foreign keys that make the agreement local.

Read first: SPEC §3.2 (the five questions, v1 fixed, versioned
`question_set`), §8 (`response` unique per student/section/week; workload
stored as a decimal; `answer` links versioned `question` rows;
`classification` is already built); ADR 0018 (the mechanism and why a trigger
was rejected), ADR 0019 (naive datetimes refused), ADR 0016 (UUID keys),
ADR 0022 (identity-column markers), ADR 0063/0064 (seed rules); the memory
that a late schema rule reaches every fixture — land constraints before the
fixtures that would violate them exist, which is exactly what building the
schema first buys.

## Scope

- `question_set` and `question`: versioned text, the v1 fixed set of five
  (§3.2 wording exactly — the Likert prompts, the conditional-required rule
  carried as data the form reads, the workload slider's range and step).
- `response`: one per (student, section, week), enforced by constraint; the
  student key is the same identity spelling `enrollment` uses; submission
  timestamps **with no server default** — E2-08 writes them through the
  E2-04 clock service, per that ticket's ADR — and whatever state the
  resubmission rule needs (E2-08 defines the writes, this ticket gives it
  columns to write).
- `answer`: linked to its versioned `question` row; workload as a decimal
  column, not a band.
- The ADR 0018 rule on `survey_window`: `term_id` plus the two composite
  foreign keys, so a cross-term window is refused by the server. The refusal
  is tested by attempting it (MISTAKES entry 3).
- Migration with a real downgrade; `alembic check` clean; the demo seed grows
  the v1 question set behind the development guard, idempotent by natural key
  (ADR 0064).
- The carried file's standing review question, answered in the PR body: the
  new tables' identity-bearing columns are named for the marker sweep, and
  the reached-table report classifies them.

## Acceptance criteria

1. The four tables exist with the constraints above; a second response for
   the same (student, section, week) is refused by the database.
2. A `survey_window` naming a week from another term is refused by the
   composite key — attempted in a test, both directions.
3. Seeded v1 question set matches §3.2's text verbatim; running the seed
   twice changes nothing.
4. `make ci` green, including migration drift and the §4.1 invariant pass
   (which must still collect — the suite's non-emptiness guard is the canary).
5. `response`'s submission timestamp columns declare **no server default** —
   asserted by a test that inspects the live table, not by review, because
   E2-08 writes them through the clock service and a `func.now()` default
   would silently win.

## Out of scope

- Window derivation and open/close semantics — E2-06.
- Any read or write path over these tables — E2-08 and E2-09.
- The future per-level question-append feature (§3.2 names it as the reason
  the set is versioned; nothing is built for it).
