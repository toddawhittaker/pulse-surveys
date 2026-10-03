# E5-05 — The report serves three lines per panel

**ID:** E5-05
**Branch:** `e5/report-benchmark-lines`
**Depends on:** E5-02 (same files — merge first), E5-04
**Lane:** heavy
**Security-relevant:** `backend/app/api/` and the report schema — the wire
boundary §4.1 item 7 polices, now with real figures flowing. `privacy-authz`
and `spec-conformance` both read this diff.

## Context

E4 shipped the report with a `comparison` member only the chokepoint could
fill and nothing flowing through it. This ticket fills it: per stream, the
comparison-set and university trend series; for the section-week, the
workload comparison figures (§5.1: workload mean/median "against
comparison-set and university figures"). Every member comes from E5-04;
this route assembles, it never computes.

The payload sketch in this breakdown's README is the contract the frontend
built against; this schema is the authority the moment it merges
(decision 8), and E5-10 reconciles.

Read first: SPEC §5.1, §4.1 item 7; `backend/app/schemas/report.py`
(the sealed member and its validator — the pattern every new benchmark
member follows); E4-07's invariant test for item 7 (what this ticket
extends); the README sketch.

## Scope

- `schemas/report.py`: per-stream benchmark members (comparison and
  university series) and the workload-benchmark member, each typed so only
  chokepoint-produced values validate — the E4 seal pattern applied to
  every new member.
- `api/instructor.py`: the report route resolves the default set via
  E5-04 and fills the members; the E4 placeholder suppression ("no set
  exists") retires.
- §4.1 item 7's invariant grows from placeholder-era to data-era: figures
  planted on both sides of each minimum at the payload boundary, per-week.

## Acceptance criteria

1. A seeded world serves both panels' comparison and university series and
   the workload comparison figures through the route — the positive
   control.
2. Every benchmark member at every depth refuses an unsealed value:
   constructing the payload with a hand-built figure fails validation, per
   member (mutation-proven, not read-proven).
3. The item-7 invariant plants both sides of both minimums and asserts at
   the payload boundary: suppressed members carry reason and nothing else
   (no counts, no points — the README sketch's rule), passing members carry
   figures.
4. A suppressed week inside a passing series renders as that week's
   suppression, not as a dropped point (E5-04 criterion 7, asserted at the
   wire).
5. The E4-era "no comparison set exists" reason is gone from the live
   payload path, and the schema no longer admits it — a record sweep
   catches any prose still asserting the placeholder era (MISTAKES entry
   1).
6. Response shape changes are additive: every E4 member unchanged, proven
   by the existing report tests passing untouched.

## Known traps

- **This diff follows E5-02 into the same two files.** Rebase onto the
  epic branch after 02 merges; do not cherry-pick around it.
- **The route must not compute.** A mean assembled in `api/` is a figure
  born outside the chokepoint — the exact defect the seal exists to make
  loud. Assembly only.
- **The invariant's positive control** — a suppression asserted where no
  data could flow is emptiness wearing a green tick (MISTAKES entries 3
  and 9); every suppression case sits beside its passing twin.

## Out of scope

- Frontend rendering — E5-07/08/10.
- The student payload — untouched here; E5-11 asserts it.
- Named sets on the wire — nothing serves one (decision 4); E5-06's
  preview is the only named-set read.
