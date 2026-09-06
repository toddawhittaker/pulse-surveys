# E4-03 — The aggregate read views

**ID:** E4-03
**Branch:** `e4/aggregate-read-views`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** identity-separated read paths in
`backend/app/views_sql/` — the §4/§4.1 heavy row itself. `privacy-authz`
fires. No suppression logic lives here (that is E4-04's ⚠ diff), but every
column these views expose is a column an instructor reads.

## Context

The report's numbers, computed at read time (breakdown decision 1): per
section and course week, for each stream, the rating distribution and the
trend mean; for the section-week, the workload mean and median, the response
rate, and the validity rate. All of it reads tables E2 shipped — `response`,
`answer`, `classification`, `enrollment`, `survey_window` — and none of it
needs anything E4 builds, so this starts on day one beside the schema
ticket.

The two streams are §3.2's fixed five questions read by role: Q1 ratings and
Q2 comments are the instructor stream, Q3 and Q4 the course stream, Q5 the
workload figure. The question set is versioned, so the mapping derives from
the question rows in force for the week, never from a hard-coded position —
E3-03's denominator rule, applied to reads.

Read first: SPEC §3.2, §3.3 (validity rate's definition lives there), §5.1,
§4.1; `backend/app/views_sql/section_enrollment_count_v001.sql` and
`teaching_instructor_v001.sql` (the shapes and naming conventions);
`backend/app/services/survey_read.py`'s header (how a read module states its
§4.1 predicate); the identity-column marker sweep in
`tests/integration/test_identity_column_marker.py` (not the
`tests/unit/test_lms_owned_column_marker.py` sweep, which is a different
guard).

## Scope

- The views, version-numbered in `backend/app/views_sql/`, keyed by section
  and course week, exposing no identity column: per-stream rating counts by
  value (the distribution), per-stream weekly mean (the trend point),
  workload mean and median as true numerics over the stored decimals (§3.2),
  response counts, enrolled counts, valid-response counts.
- Rates computed where the ADR says they are — in the view or in the
  consuming service — but defined once, consistently: response rate =
  responses ÷ enrolled that week; validity rate = valid responses ÷
  responses (§3.3).
- Grants for the runtime role on the new views, following the existing
  versioned-grants shape.
- A migration taking the second chain slot off `c4a8e51db9f3` (after E4-02,
  before E4-14; whichever merges later re-points).

## Acceptance criteria

1. Each view is proven identity-free: the identity-column marker sweep
   covers it, and a test asserts the view's column list against an expected
   set — a widened view is a red test, not a quiet diff.
2. The distribution counts every submitted rating exactly once, proven at a
   boundary: a five-response week where the counts sum to five, and a
   student with responses in two sections contributes to each section only
   its own.
3. The weekly mean is the mean of that week's submitted ratings — an absent
   response contributes nothing to the mean (it costs the response rate, not
   the average), and a test pins that against the alternative.
4. Workload mean and median are computed over the stored decimals, and the
   median of an even-count week is the conventional midpoint — asserted with
   values a float-representation accident cannot satisfy (the memory about
   "61.5"-shaped fixture values governs the choice of test data).
5. The enrolled denominator honors the enrollment window: a student enrolled
   for weeks 1–3 of a 6-week section is in week 2's denominator and not week
   5's, driven on both sides of the boundary.
6. The validity rate reads each response's current validity verdict, so an
   asynchronous reclassification changes it — asserted by adding a
   classification row, never editing one.
7. The stream mapping derives from the question set: a second question-set
   version with a different question order still maps ratings to the right
   stream, proven with a planted set.
8. `alembic upgrade`/`downgrade` both succeed; `alembic check` is clean.

## Decisions this ticket settles

- **The response-rate denominator's exact rule.** "Enrolled that week" needs
  a day: the recommendation is enrolled at the week's window close, the
  moment the report describes, with the enrollment window read the way
  §3.4's tiers read it. The ADR states the rule and its edge (a student who
  drops mid-window).
- **Where rates are computed** — in SQL or in the service reading it. The
  recommendation is the view exposes counts and the service divides, so the
  view stays a stable, testable contract and a division-by-zero rule lives
  in one reviewable place.
- **Whether the trend exposes a row for a zero-response week** — the chart
  needs the week to exist (a gap is information); the recommendation is the
  view yields the week with null mean and zero counts, and the ADR confirms
  or replaces it.

## Known traps

- **A wrong aggregate is invisible** — E3-03's warning transposed: a wrong
  mean renders as a plausible chart. Prefer asserting the forbidden state,
  and verify by mutation, not by reading (`docs/MISTAKES.md` entry 3):
  mutate the SQL in the migration, where mutations are live, to prove the
  tests can fail — and where a test could be satisfied by emptiness, assert
  non-emptiness first.
- **Every windowing rule asserted on both sides of its boundary** — the
  boundary-pair discipline the E3 formula tickets held to.
- **The dev clock crosses currencies** — ADR 0142's lesson: course-week
  derivation under a moved dev clock must not make these views' answers
  depend on the calendar date CI runs on. Tests pin their clock.
- **Views are created by migrations here** — a view edited only in
  `views_sql/` without its migration is drift `alembic check` may not see
  the way you expect; follow the existing v00N migration pattern exactly.

## Out of scope

- Small-N suppression, flags, comment text in any form — E4-04's ⚠ diff.
  These views expose numbers only.
- Comparison-set or university figures — E5 (the item-7 chokepoint is
  E4-07's).
- The API payload and its division into streams — E4-07.
- Storing any of it — decision 1.
