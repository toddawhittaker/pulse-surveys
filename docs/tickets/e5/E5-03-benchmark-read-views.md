# E5-03 — The benchmark read views

**ID:** E5-03
**Branch:** `e5/benchmark-read-views`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** identity-separated read paths in
`backend/app/views_sql/` — the §4/§4.1 heavy row itself. `privacy-authz`
fires. These views expose cohort aggregates; no threshold is applied here
(decision 1 and the decomposition note: views expose numbers, the service
applies policy), so every consumer must go through E5-04.

## Context

The cohort arithmetic under every benchmark figure, computed at read time
(decision 1): given length, level, term(s) and week, the per-stream rating
mean, the workload mean and median, the **distinct-respondent count** and
the **section count** — the two numbers the minimums compare against
(decision 2). Two axes, per decision 7: course-week alignment (week N of
every matching section, §5.1's past-referencing currency) and the term axis
per start cohort (§2.2, the shape E9's aggregate pages consume).

All of it reads tables that already exist — `response`, `answer`,
`section`, `course`, `survey_window`, `term` — so this starts day one
beside the schema ticket.

Read first: SPEC §2.2 (both axes, the start-letter cohorts), §5.1's
comparison paragraph, §4.1 items 1 and 7, §8;
`backend/app/views_sql/report_rating_distribution_v001.sql` and
`report_workload_v001.sql` (the E4 shapes these generalize);
`tests/integration/test_identity_column_marker.py`.

## Scope

- Version-numbered views in `backend/app/views_sql/`, keyed by length,
  level, term and week (course-week aligned), exposing per-stream rating
  means, workload mean and median, distinct-respondent counts and section
  counts — no identity column, no comment text, no per-section row that
  names a section (cohort rows only, except the per-section building block
  the service needs for set membership, which exposes section id and
  numbers, never a person).
- The term-axis variant: the same figures keyed by term week and start
  cohort (§2.2's one-line-per-cohort shape).
- Grants for the runtime role, versioned-grants shape.
- A migration taking the second chain slot off `e5a2b81c47d3` (after E5-01;
  whichever merges later re-points).

## Acceptance criteria

1. Each view is proven identity-free: the marker sweep covers it, and a
   test asserts each view's column list against an expected set.
2. The respondent count is a count of **distinct students**, proven by a
   planted student with two responses in cohort scope counting once
   (MISTAKES entry 50 — the unit is the criterion).
3. Cohort membership is exact on both length and level: a planted section
   differing only in level, and one differing only in length, are each
   outside the cohort — the §5.1 no-folding rule, both sides.
4. Week alignment is course-week: week 2 of a section started 9/7 aggregates
   with week 2 of one started 8/17, not with its calendar twin — asserted
   with two cohorts §2.2's Fall seed actually contains.
5. Prior-term rows aggregate beside current-term rows when the key spans
   terms — the past-referencing building block, proven with a planted
   prior-term section.
6. The term-axis view yields one row per start cohort per term week, and a
   cohort with no data yields no fabricated zeros.
7. No view applies any minimum: a one-section cohort has a row here (the
   suppression decision is E5-04's — asserted so the layering is a fact,
   not a hope).
8. `alembic upgrade`/`downgrade` both succeed; `alembic check` is clean.

## Known traps

- **A wrong aggregate is invisible** — mutate the SQL in the migration
  (model-side is inert) and watch each test fail; assert non-emptiness
  before any equality (MISTAKES entry 3).
- **Views are created by migrations here** — follow the v00N pattern
  exactly; a view edited only in `views_sql/` is drift.
- **The org-views SQL sweep reads non-docstring prose** (MISTAKES entry
  43) — mind policed relation names in any new string.
- **Boundary pairs** — every membership rule asserted on both sides.

## Out of scope

- Minimums, self-exclusion, default-set logic — E5-04.
- The named-set tables — E5-01 (these views do not read them; resolution
  composes the two).
- Any payload shape — E5-05.
