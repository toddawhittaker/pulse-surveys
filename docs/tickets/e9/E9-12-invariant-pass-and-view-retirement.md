# E9-12 — The §4.1 pass over E9's reads, and the view retirement

**ID:** E9-12
**Branch:** `e9/invariant-pass-and-view-retirement`
**Depends on:** 05, 07, 09
**Lane:** heavy ⚠
**Why this lane:** it adds `invariant`-marked tests and a migration that drops
views and their grants. It carries ⚠ because its tests are written after the
code they test, so they pass on arrival; only the verifier's mutation battery
shows each one can fail.
**Size:** M
**Security-relevant:** this is the proof that E9's read paths keep §4.1. A
test here that cannot fail leaves a read path unguarded while it looks
covered.

## Context

E9-07 and E9-09 are light by path and add no `invariant`-marked test; E9-05
proves its own reads at the service level. This ticket writes the §4.1 tests
over every E9 read path through its route, as a leader meets it: the tree and
roll-up (07), the named-set series (05), the drill-down (09), and the
staff-name door (03, ruling 3). It also retires the four cohort views that
decision 10 leaves unread.

**Written after the code.** The test author writes each test from this
ticket and the spec without reading the implementation. Each test names the
mutation that must turn it red and a near miss that must leave it green, and
the verifier plants each one (MISTAKES entries 3 and 16).

Read first: SPEC §4, §4.1, §5.1, §5.5 and §5.6; ADRs 0041, 0166, 0179, 0199,
0201, 0203, 0205 and 0206; the existing invariant modules for the report and
the student path (the patterns); `scripts/ci/check_invariants.py`.

## Owns

- The `invariant`-marked tests below, in new modules.
- Migration **`e9e5b7d9f605`**, planned `down_revision = "e9d4a6c8e504"`
  (re-pointed to the head it finds): drops `benchmark_cohort_week`,
  `benchmark_cohort_rating_week`, `benchmark_cohort_term_axis` and
  `benchmark_cohort_rating_term_axis` and their grants to `pulse_app`; its
  downgrade recreates them from their versioned files.
- `tests/integration/test_identity_grants.py` and any catalog or grant
  inventory that lists the four views.
- SPEC §13, if it names the views or their grants file.
- ADR 0166: a line saying the cohort views were retired unread, and why.

## Reuse, do not rewrite

The existing invariant test patterns and fixtures; E9-01's forest generators;
`scripts/ci/check_invariants.py` unchanged.

## Done when

1. **§4.1 item 2, through every route.** On the seeded world and on one
   generated world, a Lead Faculty session's tree, roll-up, named-set series,
   attention cards and drill-down responses carry no id, label or name of a
   course mapped to another lead, or of its sections; a drill-down request for
   such a section answers the same 404 as a section that does not exist. Each
   has a present twin: the lead's own course appears. Marked `invariant`.
2. **No route resolves another person's scope.** Every leadership route,
   called with another person's id in a query string, path or body, answers
   from the session's own scope. Marked `invariant`.
3. **§4.1 item 3 up the chain (ruling 2).** No roll-up, tree, attention or
   named-set response carries a comment's text, a summary, a theme or a
   comment count. The drill-down of a section-week with a stream below the
   threshold carries no comment text for that stream and carries its small-N
   state, read this Monday and next across a release batch. Marked
   `invariant`.
4. **§4.1 item 4, ordering.** For two worlds that differ only in figures, every
   list in every roll-up response has the same order. Marked `invariant`.
5. **§4.1 item 7 for a leader.** The drill-down's comparison and university
   figures are suppressed when the remainder after the reader's known set
   (leadership purview and taught sections, §5.1) is non-empty and below a
   minimum, one respondent either side; the named-set series is suppressed
   below 3 sections or 10 respondents inside the purview. Marked
   `invariant`.
6. **Both hats, through the drill-down route.** A Math chair teaches Biology
   section T; the drill-down's university line U is suppressed when U less
   Math less T is non-empty and one respondent below a minimum, and shown at
   the minimum; the twin world, with the chair not teaching T and U less Math
   meeting both minimums, shows U. Marked `invariant`.
7. **The university line's two extra pieces, through the route.** With U
   less the known set meeting both minimums, U is suppressed when (i) a
   default comparison set of a purview section, less the known set, is
   non-empty and thin, or (ii) the university less the known set and less
   those sets is non-empty and thin. Each case has a shown twin, one
   respondent either side. Marked `invariant`.
8. **The staff-name door passes purview sections only (ruling 3).** A
   leadership page's call to the door never passes a section outside the
   reader's purview, asserted at the definer's boundary (the ids it received).
   Marked `invariant`.
9. **Every test above can fail.** The verifier plants, for each, the named
   mutation (for example: drop the lead clamp; read the purview by person;
   pass the whole section list to the door; sort attention by a figure; drop
   the reader from the seal; seal a leader without their taught sections;
   skip one of the university line's extra pieces; put a summary on the
   roll-up schema) and sees it red, and the named near miss green.
10. **The four cohort views are retired.** After the migration none exists and
   `pulse_app` holds no grant on any; nothing under `backend/app/` names them
   (search with a canary); downgrade and upgrade round-trip; the §4.1 view
   sweeps and catalog guards are green with the views gone. If E9-05, E9-07 or
   E9-09 recorded that one of them is read, that view is kept and the pull
   request says so.
11. **CI's isolated §4.1 pass collects every new module** (no skip, no empty
   collection).
12. **The records match.** ADR 0166 gains its line; the carried cohort-views
    entry is named closed in the pull request.

## Shares files with

- `tests/integration/test_identity_grants.py`: 02 and 03.
- Migration chain: every migration owner.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 16, 19, 20, 35, 51 and 53.

## Known traps

- **Entry 16.** Check each mutation landed before believing its red.
- **Entry 20.** A fixture that rebuilds what the mutation broke reads as a
  test that cannot fail.
- **Entry 51.** Item 3 up the chain is a property of the sequence of Mondays.

## Not in this ticket

- Any production code change beyond the migration. A defect a test finds goes
  back to its owning ticket's code in this pull request's fix round, or to a
  new ticket if the owner has merged.
