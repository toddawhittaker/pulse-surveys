# E5-10 — The report page joins the benchmark payload

**ID:** E5-10
**Branch:** `e5/report-benchmark-join`
**Depends on:** E5-05, E5-07, E5-08
**Lane:** light
**Security-relevant:** minimally; the page renders what the payload
carries, and the payload is where the guarantees live. A light diff
reaching any heavy path re-lanes, per the standing rule.

## Context

E4-11's pattern, replayed for benchmarks: the components (E5-07, E5-08)
built against the README's sketch, the schema (E5-05, E5-02) is now the
authority, and this ticket is the named reconciliation point (decision 8)
— fixtures move to the shipped shape, the page wires the real members
through, and the in-slice e2e grows the three-line assertion.

Read first: the README sketch **and** `backend/app/schemas/report.py` as
merged (where they disagree, the schema won — list every divergence in the
PR body, E4-11's precedent); E5-07 and E5-08's prop contracts;
`tests/e2e/` — the instructor-report specs E4 shipped and E4-22's
world-building rules (enrollments anchor to section starts, never the wall
clock).

## Scope

- InstructorMondayReport passes the payload's benchmark members to the
  overlay and stat components; the question-text and close-instant members
  (E5-02) are already rendering — this ticket must not regress them.
- Fixture reconciliation across the frontend test suite: one shape, the
  shipped one.
- The in-slice e2e: an instructor report in a seeded benchmark-bearing
  world shows three lines per panel and the workload comparison block; a
  suppressed world shows the stated treatments.

## Acceptance criteria

1. The page renders three lines per panel and the workload columns from a
   real (dev-stack) payload — driven, not mocked, in the e2e slice.
2. The suppressed world renders every stated treatment (series and
   columns), same e2e spec family, both directions per MISTAKES entry 3's
   pairing.
3. No fixture anywhere in `frontend/` still carries the sketch-era shape
   where it diverged — swept by grep for the divergent member names,
   listed in the PR.
4. Loading and error states unchanged from E4-11; an absent
   `workload_benchmark`/`benchmark` member (an older cached payload
   mid-deploy) renders E4's page, not a crash.
5. The student e2e specs still pass untouched — this PR touches no student
   surface (the assertion itself is E5-11's; this criterion is the
   don't-break-it floor).

## Known traps

- **The e2e world and the calendar** — E4-22's anchor discipline governs
  any new world rows; no pinned reading date may depend on the CI clock.
- **A reconciliation that edits the schema** — divergences resolve by
  moving fixtures to the schema; if the schema is what's wrong, that is an
  E5-05 defect to raise, not a page-side patch (the spec-vs-work rule in
  miniature).
- **Shared dev database** — the e2e drive follows the standing stack
  rules; `make docker-build` wipes the world (the recorded incident), so
  drive per the runbook.

## Out of scope

- New component behavior — E5-07/08.
- The student two-line proof — E5-11 (it cites this page's world).
- Named sets anywhere on this page — E9 (decision 4).
