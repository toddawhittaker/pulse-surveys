# E5-04 — The benchmark resolution service

**ID:** E5-04
**Branch:** `e5/benchmark-service`
**Depends on:** E5-01, E5-03
**Lane:** heavy
**Security-relevant:** the policy layer of §4.1 item 7. Everything this
module emits is a comparison figure; a defect here is a suppressed number
shown or a shown number wrong. `backend/app/services/` — heavy row.

## Context

`backend/app/services/benchmarks.py` — SPEC §13 names it: "comparison-set
resolution, length/level matching, min-N". This is the only module that
turns cohort numbers (E5-03's views) into comparison figures, and every
figure it emits is sealed by `comparison_after_suppression`
(`app.services.reporting`), under both configured minimums — breakdown
decision 2. Three resolutions live here:

- **Default set** (§5.1): the same Lead Faculty's courses
  (`lead_faculty_course_v001.sql` is the existing read), filtered to the
  hero section's length and level, minus the hero section itself
  (decision 5).
- **University line**: all same-length+level sections institution-wide,
  hero included (decision 5), same minimums (decision 2).
- **Named set** (E5-01's table): member courses' sections of the declared
  length, resolvable for E5-06's preview even though no report renders one
  yet (decision 4).

All three are past-referencing: week N across current and every retained
prior term (decision 6).

Read first: SPEC §5.1's comparison paragraph (whole), §4.1 items 6 and 7;
`app/services/reporting.py`'s chokepoint block (the sealing contract and
its docstrings — the module was written to be read by this ticket);
`backend/app/config.py`'s two `benchmark_min_*` fields and their comment;
E5-01's ADR; E5-03's view contracts.

## Scope

- The service: default-set, university and named-set resolution; week
  alignment across terms; both minimums applied to every figure — trend
  points, workload mean, workload median — with the respondent minimum
  counting distinct students.
- Every emitted figure constructed through `comparison_after_suppression`;
  nothing in this module builds a `ComparisonFigure` any other way.
- The ADR carrying decisions 2 (university line under the same minimums),
  5 (hero excluded from its own set, included in university) and 6 (no
  second horizon beyond retention), each with its rejected alternative.

## Acceptance criteria

1. A cohort on each side of **each** minimum: passes both → figure;
   fails sections only → suppressed; fails respondents only → suppressed.
   Three worlds, and the two failing ones differ from the passing one by
   exactly the count under test (the near-miss discipline).
2. The respondent minimum counts distinct students: a world where responses
   ≥ 15 but students < 15 suppresses (MISTAKES entry 50).
3. The default set excludes the hero section: a world where the set passes
   the minimums only if the hero is counted is suppressed.
4. Past-referencing reaches prior terms: a cohort thin in the current term
   passes when prior-term sections are counted — and the week alignment is
   course week N to week N, not calendar.
5. The university line and the comparison line resolve different
   populations from one world (lead's courses ⊂ university), asserted on a
   world where the two figures differ.
6. An empty or unresolvable named set yields a suppressed figure, never an
   error and never an absent member (E5-01's empty-set decision, asserted
   here).
7. A per-week trend series suppresses per week: a cohort passing in week 2
   and thin in week 3 yields a figure for 2 and a suppression for 3 —
   suppression is per figure, not per report.
8. Nothing in the module can emit an unsealed figure: the module's tests
   drive every public function and assert provenance via
   `refuse_an_unsealed_comparison`.

## Known traps

- **Do not touch the chokepoint.** `comparison_after_suppression` and its
  seal are E4's proven ground; this ticket is a caller. Widening the
  helper's signature "for convenience" re-opens what E4's invariant closed.
- **Two minimums, always** — the closed-set defeat (MISTAKES entry 53's
  class, decision 2's first half): every acceptance world plants both
  counts explicitly.
- **The dev clock crosses currencies** (ADR 0142) — term arithmetic under
  a moved clock; tests pin their clock.
- **Emptiness satisfies nothing**: every suppression assertion sits beside
  a passing control in the same world (MISTAKES entry 3).

## Out of scope

- The report schema and routes — E5-05.
- The leadership CRUD — E5-06.
- Term-axis rendering — E9 (this module serves E5-03's term-axis reads for
  E5-06's preview and E9's later use; decision 7).
