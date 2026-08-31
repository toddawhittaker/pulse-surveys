# E2-06 — Survey windows derive from the calendar, and one is open at a time

**ID:** E2-06
**Branch:** `e2/window-scheduling`
**Depends on:** E2-04, E2-05
**Lane:** heavy
**Security-relevant:** window state decides what a student can submit to;
wrong scheduling is a correctness problem, not a leak, but the service sits
in `services/` and rides the heavy lane like everything there.

## Context

SPEC §3.1: windows open Friday 18:00 and close Sunday 23:59:59 in the
institution timezone; reports come after close. A section's active weeks
derive from its section code and the term calendar (§2.2, already computed
onto `section` by `apply_section_code`). Students see exactly one open survey
at a time per section; missed weeks cannot be back-filled.

The `survey_window` table exists and nothing fills it. This ticket is the one
writer: derivation of a section's windows from its calendar plus the
open/closed question, all through the E2-04 clock — that is what makes the
interactive time control actually show a Friday-evening student view.

§3.1 calls the rhythm "institution configuration". The configuration
*surface* is §6.3 and E11's. Here the default rhythm ships as named constants
in the scheduling service with the §3.1 citation; making them editable is
E11's, stated in the README's deliberately-not-done list.

Read first: SPEC §3.1, §2.2; ADR 0018 (including "Lengthening is the silent
direction" — the missing-weeks hazard this ticket must tolerate, not fix);
ADR 0020 (end date is the last day), ADR 0021; `backend/app/models/term.py`
(`SurveyWindow`, `Week`); `backend/app/services/section_codes.py`; E2-04's
clock service.

## Scope

- Window derivation: for a section, its windows follow from its weeks — one
  per active course week, opening the Friday 18:00 of that week and closing
  Sunday 23:59:59, institution timezone, stored as aware UTC instants
  (ADR 0019). Decide and record whether rows are materialized by the weekly
  job or written with the section and read thereafter; whichever wins, there
  is exactly one writer (ADR 0021's shape) and an ADR if the choice is
  contestable.
- The open-window question, answered by one function reading the E2-04
  clock: at most one window of a section is open at any instant, which the
  derivation itself guarantees (Friday–Sunday spans of consecutive weeks
  cannot overlap) — asserted, not assumed, across a term's worth of derived
  windows including the term-break weeks §2.2's calendar carries.
- Closed means closed: a window in the past never reopens, a missed week is
  not back-filled, and a section whose term has no week row for a course week
  (ADR 0018's lengthening gap) yields no window and a log line rather than a
  crash — the quiet-failure shape refused loudly.
- The weekly rhythm through the clock: with the dev override set to a Friday
  18:05, the seeded sections answer "open"; at Sunday 23:59:59 they still
  answer "open"; at Monday 00:00:01 they answer "closed" — the boundary pair
  both sides (MISTAKES entry 3).

## Acceptance criteria

1. Derived windows for the seeded Fall-2026 sections match §2.2's start
   letters and §3.1's rhythm — checked against hand-computed dates for at
   least one 6-, 12-, and 15-week section.
2. The one-open rule holds across a generated term (property test over the
   start-letter map, or the full seeded map — the generator must include the
   boundary instants, MISTAKES entry 15).
3. Open/closed flips with the dev clock against the running stack — the
   interactive check this epic was asked to support, scripted so it stays
   true.
4. No code outside the one writer writes `survey_window` (the E0-35 sweep
   pattern already used for section calendars extends or its absence is
   recorded in the ADR).

## Out of scope

- The submit path and what an open window permits — E2-08.
- Editing the rhythm, the term, or the start-letter map, and re-deriving
  anything after such an edit — E11 (ruled 2026-08-31).
- Report generation at window close — E4.
