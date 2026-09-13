# E4-22 — The student-survey e2e world stops depending on the wall calendar

**ID:** E4-22
**Branch:** `e4/e2e-clock-anchor`
**Depends on:** none (fixes existing test infrastructure)
**Lane:** light — the diff stays inside `tests/e2e/`; no product code, no
migration, no read path changes. `tests/e2e/` is not a heavy-lane row
(`.claude/heavy-lane-paths.md` names `tests/conftest.py` and `tests/fixtures/`,
not `tests/e2e/`).
**Security-relevant:** no. Test-support timing only.

## Context

Found on 2026-09-13 building E4-21: CI's Playwright job red on two specs,
`student-survey-confidentiality.spec.ts` and
`student-survey-heading-and-next-window.spec.ts`, both failing in world setup
with the learner at the no-access door. The cause is a calendar time-bomb, not
a regression — the epic tip ran green on the identical spec code on 2026-09-11.

The chain: enrollments are provisioned only by launch and roster sync
(`scripts/seed.py` creates none). The roster sync stamps
`enrollment.started_on` from the effective clock at sync time
(`backend/app/services/roster_sync.py` ~L437, `clock.today`). The
sync-triggering instructor launches in the specs' setup run at the **real**
CI clock, so `started_on` = the real date the run happens on. The student
read path shows only sections where `started_on <= today`
(`backend/app/services/survey_read.py:175`, `today` = the pretend clock).
Several specs pin their reading clock to a fixed past date —
`BOTH_WINDOWS_OPEN = "2026-09-11T19:00"`. While the real date was on or before
2026-09-11 the gate held; once the calendar passed it, `started_on` (now
2026-09-13) exceeds the pinned reading clock and the learner reads as
not-yet-enrolled everywhere.

This matches SPEC §3.4 read backwards: when the platform supplies no
enrollment dates — the mock supplies none — a student counts as enrolled from
the section's start date. The test world should therefore stamp `started_on`
at the section's start, not at whatever day CI happens to run.

## What this ticket builds

Anchor every sync-triggering instructor launch in e2e **setup** (the
`beforeAll` blocks and the `standTheLearnerIn` helper in
`tests/e2e/support/survey.ts`) to the launched section's own start date:
set the dev clock to that date before the launch, hold it there through the
enrollment/sync wait so the sync stamps `started_on` at the section start,
then let the spec advance the clock to its reading instant as it already does.

Section start dates come from `scripts/seed.py`'s `START_LETTER_MAP`, keyed by
the section code's start letter (`R` → 2026-09-07 for `BIOL-215-R3WW`, `E` →
2026-08-17 for `MATH-140-E1FF`, and so on). Derive the anchor from the code,
transcribed from that map with a comment naming it — never hardcode a date
that reads from nothing (`docs/MISTAKES.md` entry 19).

The result must be durable: no spec's learner enrollment may depend on the
real date the suite runs on.

## Acceptance criteria

- The full Playwright suite passes in CI, with today's real clock strictly
  after every pinned reading date in the affected specs (it is: today is past
  2026-09-11). One green CI run is the proof.
- No product code changes: the diff is confined to `tests/e2e/`.
- The anchor for each section is derived from its code against the seed's
  start-letter map, not written as a bare literal.
- Boundary check on the specs that still read at future dates (October,
  November): they stay green — anchoring `started_on` earlier never makes a
  later reading clock fail, since `started_on <= today` only relaxes.
- No test skipped, xfailed, or deleted; the §4.1 invariant suite untouched
  (it is not in this diff).

## Deliberately not built

- **No change to `roster_sync.py`'s stamping.** Making the sync itself date
  `started_on` at the section start when the platform supplies no dates is the
  arguably-correct product fix, but it is a §3.4 read-path/roster-sync
  decision, heavy-lane, and larger than unblocking CI. If it is wanted it is
  its own ticket; recorded here so the choice is visible, not forgotten.
- The student survey's eyebrow double-separator (already deferred in
  `deferred.md` by E4-21).

## ADR

None: this restores the world to what it was built to be (SPEC §3.4's
section-start enrollment) and makes no contestable construction choice. If the
anchor approach forces one, it gets its ADR in the PR.
