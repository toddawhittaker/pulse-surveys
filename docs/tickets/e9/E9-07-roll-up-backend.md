# E9-07 — The roll-up backend

**ID:** E9-07
**Branch:** `e9/roll-up-backend`
**Depends on:** 01, 03, 05
**Lane:** light
**Why this lane:** a new service, schema and routes. It reads the purview
through E9-01's `leadership_scope` and the staff names through E9-03's door,
calls the existing set functions through `services/benchmarks.py`, and
changes no heavy path. Its conditional migration is an index on
`instructor_response`, none of the four heavy kinds. It adds no
`invariant`-marked test; E9-12 writes those over its routes.
**Size:** L
**Security-relevant:** the tree and every aggregate a leader sees. A defect
here counts or labels sections outside the purview, shows a by-lead pivot to
a lead, carries a comment onto an aggregate page, or orders by a figure.

## Context

SPEC §5.5: one template for every leadership role, two panes, the term axis
with per-cohort lines and a cohort selector; hierarchy mode for everyone and
by-lead mode for chair and above; trees collapsed by default; roots and labels
per §2.1; attention cards by §5.6's exact predicates. Ruling 2: no comments on
roll-up pages.

- **The tree, in one payload.** The whole tree over the reader's leadership
  scope (E9-01), built once. Roots per §2.1: VP at colleges, dean at
  departments, chair at prefixes, lead at the prefixes of their led courses;
  the assistant dean's roots are the departments and prefixes their purview
  reaches. A union of several leadership assignments is several roots (§2's
  multi-root nav), from `ActorScope.grants`.
- **By-lead mode** is offered only when the reader holds a `CHAIR` or higher
  assignment (from `grants`, never from the purview's size). It groups the
  purview's courses by their mapped lead (`course_leads`), and unled courses
  under their chair.
- **Labels count held nodes only.** "N departments · N sections · Dean:
  {name}", "N prefixes · N sections · Chair: {name}", "N sections · Lead:
  {name}" (no lead name in the lead's own view), and a section row's code and
  teaching instructor. Every count is over the nodes the reader's purview
  holds, so a department reached through one cross-department led course
  counts that course's sections only. Names come through E9-03's door in one
  call per payload.
- **Series per node.** For each node, per start cohort in the viewed term,
  the instructor and course rating means and the workload mean and median on
  the term axis, through `benchmark_set_week` and `benchmark_set_rating_week`
  over the node's held sections, read once per distinct section set.
  Response rate and validity rate per node. A node's own figures are not a
  comparison set, so §4.1 item 7's minimums do not apply, and every section in
  it is one the reader can open (E9-09).
- **Attention cards (§5.6).** Instructor trend down two or more consecutive
  weeks; course trend down two or more; response rate under 40%; response
  required and delinquent 48 hours or more. Each card names its rule and
  stream and links to the section's report. Rule 4 calls
  `response_loop.is_owed`'s rule through a set-based owed read over the
  purview's sections (the carried entries), never a copy of the 48-hour rule.
  The empty state is "Nothing needs attention this week".
- **Ordering (decision 13).** Tree children, attention cards and every list
  sort by label or section code, never by a figure. A Hypothesis property
  shows the order is unchanged when every figure changes.
- **No comments.** No payload of this ticket carries a comment, a summary, a
  theme or a comment count.
- **Set-based response reads.** Policies and responses are read once per
  payload; `EXPLAIN` over a term-sized seed decides the index on
  `instructor_response (section_id, week_id, sequence)`.

Read first: SPEC §2.1, §2.2, §4.1 item 4, §5.5 and §5.6; ADRs 0166, 0179,
0191, 0194 and 0199; `services/benchmarks.py` (the set functions);
`services/response_loop.py` (`is_owed`, `_week_clocks`, `policy_overview`);
`services/reporting.py` (`_published_weeks`); `design/LeadershipRollup.dc.html`,
`design/Leadership Rollup - States.dc.html`, `HierarchyNav`, `AggregateHeader`,
`MetricBlock` and `AttentionList` mockups.

## Owns

- `backend/app/services/rollups.py` (new: SPEC §5.5 is a different reader
  from §5.1, and `reporting.py` is already over 2,600 lines; the set reads
  stay in `benchmarks.py`, so the benchmark-relation sweep is unchanged).
- `backend/app/schemas/rollup.py` (new), sentences added to
  `backend/app/copy/leadership_rollup.py` under the prefix E9-05 placed
  (README decision 15), and the routes in `backend/app/api/leadership.py`.
- `backend/app/services/response_loop.py`: the set-based owed read that
  `is_owed` and the attention list share.
- `backend/app/services/benchmarks.py`: a node-series read over a section set
  through the set functions, if no existing function fits.
- Migration **`e9f6c8e0a706`**, planned `down_revision = "e9a7c9e1b807"`,
  only if `EXPLAIN` asks for it.
- `scripts/seed.py`: roll-up data, if the seeded term is too thin to show
  per-cohort lines (additions only).
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated.
- SPEC §13: the new files.
- ADR **0205** (the one-payload tree, node series through the set functions,
  the set-based owed read, the ordering property).

## Reuse, do not rewrite

E9-01's `leadership_scope`, `ActorScope.grants` and `course_leads`; E9-03's
door; `response_loop.is_owed` and `_week_clocks`; the set functions;
`reporting._published_weeks`; `Purview`'s node sets.

## Done when

1. **Roots per role.** The seeded VP's roots are colleges, a dean's are
   departments, a chair's are prefixes, a lead's are the prefixes of their led
   courses; the assistant dean's are Math, Biology, and PSYC 110's prefix.
2. **Multi-root for a union.** A person with a `CHAIR` and a `LEAD_FACULTY`
   assignment in another department gets two roots, and the tree holds
   nothing from their instructor assignment (ruling 4).
3. **By-lead only for chair and above.** A lead's payload offers no by-lead
   mode and carries no grouping by lead; a chair's does. The gate is decided
   from the roles held: a lead whose purview is larger than a chair's still
   gets none.
4. **Labels count held nodes only.** For a department reached only through one
   cross-department led course, the row counts that course's sections and no
   other section of the department, beside a twin department wholly held
   whose count is its full size.
5. **Names, in one call.** The payload names the dean, chairs, leads and each
   section's instructor through E9-03's door in one call (a query-count
   test), and omits the lead's name in the lead's own view.
6. **Series per start cohort.** For a node holding two start cohorts, the
   payload carries one series per cohort on the term axis, each point at the
   term week of its course week, with the cohort's label ("U sections ·
   started 8/17").
7. **Attention follows §5.6 exactly.** One seeded section per rule makes one
   card naming its rule and stream; a section one week short of "two
   consecutive weeks" and one at exactly 40% make none. Rule 4's test fails if
   the owed read stops using `is_owed`'s rule (replace it with a copy and the
   test goes red). The empty state carries the calm sentence.
8. **Order never follows a figure.** A Hypothesis property: for random
   figures over a fixed tree, the order of every list in the payload is the
   same. The sort keys are labels and codes.
9. **No comment on any roll-up payload.** The roll-up schemas carry no
   comment, summary, theme or comment count; a schema sweep over
   `schemas/rollup.py` asserts it, with a canary member planted to show the
   sweep can see one.
10. **Set-based reads.** The payload for the seeded VP reads policies and
    responses a fixed number of times, whatever the number of sections
    (counted at two sizes). The `EXPLAIN` is recorded in ADR 0205, with the
    migration if it asks.
11. **Out-of-purview ids are refused like missing ones.** A route that takes
    a node id answers a node outside the purview exactly as a node that does
    not exist.
12. **Words.** Every string is in the copy registry under
    `leadership_rollup.`, with no change to the inventory test; aggregate language
    counts sections, never instructors, and says "needs attention", never
    "underperforming" (the copy inventory extends over the surface).
13. **The records match.** ADR 0205 is written and indexed; SPEC §13 draws
    the new files; the carried `is_owed` and set-based entries are named
    closed in the pull request.

## Shares files with

- `services/response_loop.py`: 03, 08 and 09.
- `services/benchmarks.py`: 05 and 09.
- `api/leadership.py`: 05 and 09.
- `openapi.json`, `wire.gen.ts`: 04 to 09.
- `scripts/seed.py`: 11 and 13.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 14, 19, 50, 51 and 58.

## Known traps

- **Entry 58.** A seeded world's claim ("the dean has two cohorts") is
  checked through this ticket's read, not the seeder's.
- **Entry 51.** Labels that count only held nodes must stay so across a
  mapping edit between two reads; the residue is ruling 6's, not a new one.
- **Calendar.** Pin the clock; the term axis depends on the seeded term's
  dates.

## Not in this ticket

- Named-set lines (05 serves them; 11 draws them).
- The drill-down (09).
- The screens (11).
- The `invariant`-marked tests over these routes (12).
