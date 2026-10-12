# E9-16 — Boundary records and tidy-up

**ID:** E9-16
**Branch:** `e9/boundary-records-and-tidy-up`
**Depends on:** 01–12, 15
**Lane:** light
**Why this lane:** records (SPEC, ADRs, comments), a published-weeks refactor
in the reporting services, a mockup, and two frontend fixes. Edits that reach
heavy paths (`services/authz.py`, `services/identity.py`,
`services/session.py`, `api/deps.py`, `views_sql/queries.py`) are comments
only, except one pure refactor in `authz.py` with no test change; anything
more stops and re-lanes.
**Size:** M

## Context

The E9 epic-boundary review found records that no longer match the code: SPEC
§8 says a staff name reaches a reader through one channel, while the admin
console names people through its own reads, export and import audit row; ADR
0205 and the reader inventories miss the admin's unscoped grant-node reader;
`identity.py` counts four point lookups where there are five; several "until
E9" sentences are stale; the roll-up mockup still shows AI summaries and
comments on roll-up nodes, which SPEC §5.5 rules out; and the lazy routes and
the explicit cascade-layer file carry no ADR. The code review found the
published-weeks rule written three times, dead code, a duplicated role order,
a duplicated landing walk, a redundant instructor lookup and ticket numbers in
code comments. The re-check of the boundary UI fixes found a duplicated status
paragraph on the leadership page and patterned cohort strokes that do not read
apart.

Read first: SPEC §2.2, §5.5, §7.3, §8, §13; ADRs 0094, 0183, 0194, 0200, 0205.

## Done when

1. SPEC §8 states that, besides the staff-name function, an admin reads names
   through the admin-checked people-graph reads and their CSV export, and that
   an applied import's audit row holds names in `audit_log.detail`; ADR 0200
   carries the amendment, and SPEC §13's comment on
   `section_staff_names_v001.sql` no longer says "the one channel".
2. ADR 0205, its index row, `views_sql/queries.py`'s inventory and SPEC §13's
   comment on `org_node_label_v001.sql` name `admin_grant_nodes` as the
   admin-only, unscoped reader of `org_node_label`.
3. `services/identity.py`'s docstring counts five lookups, one of them a set,
   and ADR 0094 carries an amendment pointing at ADR 0205.
4. No stale "until E9" text remains in SPEC §7.3 (the launch binding is ADR
   0108 as amended by ADR 0199), `copy/leadership_moderation.py`, ADR 0183
   (end-dating was ruled out) or ADR 0194.
5. `design/LeadershipRollup.dc.html` shows no AI summary and no comment group
   on a roll-up node (SPEC §5.5).
6. ADR 0207 records the lazy routes and the explicit cascade-layer file, with
   raising the bundle budget and turning off CSS code splitting rejected.
7. One set-based `reporting.published_weeks_of` is the published-weeks rule for
   the instructor report, the roll-up's section figures and a node's series,
   with every existing test green; `benchmarks._sealed_by_its_own` is gone and
   `_Population`'s docstring is true; the roll-up names roles in
   `LEADERSHIP_ROLES` order; `resolve_landing` and `resolve_landings` share one
   role walk (a pure refactor, no test change); `survey_read._instructors`
   makes one instructor lookup; the E9 ticket citations in `session.py`,
   `benchmarks.py` and `deps.py` cite ADRs or SPEC instead.
8. The leadership page says "Choose one start cohort…" once (in its live
   status), and the vitest fails on two copies.
9. Patterned cohort strokes (cohorts 3 to 8) use butt line caps in the plot and
   the legend, so dashed and dotted lines read apart and the legend's dashed
   swatch shows its gaps.
