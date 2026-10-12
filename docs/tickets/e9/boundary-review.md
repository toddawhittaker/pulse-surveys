# E9 boundary review

The SPEC §14.2 item 6 record for E9 (leadership hierarchy and roll-ups). It has
four parts: the reviews and where each finding went, the exit clause driven
against the running stack, the standing questions every epic boundary re-asks,
and CI on the exit commit.

The battery ran on 464f9773, the epic head after E9-12 (every build ticket
merged), against `main` at 40d3e24b. Its findings became three fix tickets:
E9-14 (#349), E9-15 (#347) and E9-16 (#348). E9-13 drove the exit clause and
answered the standing questions, below.

## The reviews

The full battery CLAUDE.md names for an epic boundary, each with a fresh
context, over the epic's cumulative diff against `main`. SPEC §14.3 marks E9 ⚠,
so `threat-model` ran.

| Review | Head reviewed | Result |
|---|---|---|
| `invariant-coverage` | 464f9773 | 2 HIGH, 2 MED, 2 LOW |
| `adr-docs-completeness` | 464f9773 | 1 HIGH, 4 MED, 3 LOW |
| `spec-conformance` | 464f9773 | 2 MED, 6 LOW |
| `code-reviewer` | 464f9773 | 3 LOW, 10 simplifications |
| `app-security` | 464f9773 | Nothing found |
| `privacy-authz` | 464f9773 | 2 LOW; agreed with every pull request's accepted residue |
| `data-model` | 464f9773 | 2 LOW; the full migration chain round-trips with an identical catalog |
| `prompt-eval` | 464f9773 | Nothing found |
| `a11y-copy` | 464f9773 | 3 MED, 2 LOW, and a note |
| `lti-oidc` | 464f9773 | 2 LOW |
| `threat-model` | 464f9773 | 1 MED, 1 LOW |
| `epic-exit` | | Runs on this ticket's head; its verdict goes under "CI on the exit commit" |

## The findings, and where each went

**Fixed in E9-14 (#349, merged as b288a711):**

- MED (`threat-model`): the wider roles' exclusion log served a row's reason
  and decision date where its excerpt was withheld, and with the drill-down's
  release batches that placed a held comment in its week. The log now blanks
  both for every reader but the decision's own decider, and puts undated rows
  after dated ones in no time order. SPEC §5.2 and ADRs 0190 and 0206 amended.
- MED (`spec-conformance`): a course could be mapped to a person with no Lead
  Faculty assignment, giving two meanings of "led" and comments that reached no
  queue. Mapping now needs a live LEAD_FACULTY holder, and that assignment's
  revoke is refused while its mappings remain (migration `e9b8c0d2e417`).
- LOW (`data-model`): admin-write audit rows carry their role and scope, and a
  linkage row carries no scope, by two checks.
- LOW (`privacy-authz`, `spec-conformance`, `code-reviewer`):
  `section_lead_name` takes a required scope, and the caller sweep covers it.
- HIGH, HIGH, MED, MED and LOW (`invariant-coverage`): invariant-marked tests
  for the wider roles' exclusion log, the admin read routes and definers
  against a lead and an instructor, by-lead mode never for a lead, the
  attention-order property, and the drill-down's context bar in the copy
  inventory.
- MED (`adr-docs-completeness`): `moderation.py`'s module docstring names both
  reaches; ADR 0174's action count and `AuditLog`'s docstring corrected.

**Fixed in E9-15 (#347, merged as 964585bd):**

- MED (`spec-conformance`): the roll-up drew one cohort line; it now draws
  every start cohort on one term axis, and the chips filter.
- MED (`a11y-copy`, owner's ruling): the shell sat above the student survey in
  the LMS frame; on student pages it now draws only when the person has another
  view. LOW (`code-reviewer`): a new tab with a cookie session gets the shell.
- MED (`a11y-copy`): admin refusals show beside the control that sent them.
- MED (`a11y-copy`, owner's ruling): the attention rule's display name is
  neutral; SPEC §5.6 defines the rule, not the text.
- LOW (`code-reviewer`, `adr-docs-completeness`): the leadership context calls
  provisioning's current-term rule instead of a copy.
- LOWs (`a11y-copy`): focus on tree presses, pending states on lazy routes,
  live regions mounted empty; the note: the shell's styles in their own sheet.
- LOWs (`code-reviewer`, `adr-docs-completeness`): route paths written once,
  stale router comments, `main.tsx` pointing at the layer-order file.

**Fixed in E9-16 (#348, merged as b79dfd9d):**

- HIGH (`adr-docs-completeness`): SPEC §8 named one channel for staff names;
  it now names every path, with ADR 0200's amendment and §13's comments.
- MEDs (`adr-docs-completeness`): ADR 0205 and `queries.py` name
  `admin_grant_nodes`; `identity.py`'s inventory and ADR 0094's pointer.
- LOWs (`lti-oidc`, `spec-conformance`): stale "until E9" text in SPEC §7.3,
  the moderation copy, ADRs 0183 and 0194; the mockup's roll-up nodes draw no
  comments or summary.
- LOW (`adr-docs-completeness`): ADR 0207 for the lazy routes and the
  cascade-layer file.
- Simplifications (`code-reviewer`): one published-weeks rule, dead code
  removed, `LEADERSHIP_ROLES` reused, one landings helper, a redundant query
  dropped, ticket citations replaced.
- Two items from E9-15's re-check: the duplicated cohort sentence, and butt
  caps on patterned strokes.

**Fixed in E9-13 (this ticket):** the two wording LOWs E9-16's own reviews
left (an import's audit row holds every name its diff shows; two comments named
a deleted function), and `lti-oidc`'s LOW that no cookieless drive ran the
switch and logout: `exit-assistant-dean.spec.ts` runs both inside the launch
frame. And \`adr-docs-completeness\`'s MED that some deferrals lived only in
pull request bodies: \`../e10/carried-from-e9.md\` now names every one.

**Recorded, nothing owed:** `spec-conformance`'s LOWs that E9-10's heavy code
was written before its tests (recorded in #343), that E9-09's done-when 4 test
was weak (E9-12 covers it), and that the generated series check was removed
(E9-12 replaced it with checks that have twins); `section_lead_name`'s default,
fixed by E9-14.

**Carried to E10**, each with an owner and a done-when in
`../e10/carried-from-e9.md`: `threat-model`'s and `privacy-authz`'s LOWs
(linking a login before a Care grant hides who holds Care; person creation and
edits are unaudited), the audit screen's scoping of `audit_log.detail`,
`data-model`'s redundant `uq_comparison_set_name`, `code-reviewer`'s AST
sweep-helper consolidation, \`invariant-coverage\`'s LOW that the marker gate
finds invariant modules by file name, and the residues E9-14 accepted.

## The exit clause, driven against the running stack

SPEC §14.3's E9 exit: "the assistant-dean worked example (§2.1) resolves
correctly from either door, and generated-graph properties prove sibling
isolation and transitive unions."

**The generated-graph half** is E9-01's and E9-05's: Hypothesis properties over
generated supervision forests (`test_the_purview_walk_holds_over_generated_forests.py`)
and generated named sets (`test_no_named_set_figure_reaches_a_reader_from_outside_the_purview.py`,
`test_no_sequence_of_named_set_reads_isolates_a_sibling_course.py`), each in the
isolated invariant pass.

**The worked example from either door** is this ticket's. The premise that the
mock provider already reached the assistant dean was false: its subject reached
a mock-world copy with no edges. `scripts/seed.py` now links the provider's
`mock-idp-user-assistant-dean` and a new mock-LMS subject,
`mock-lms-user-assistant-dean`, to the demo assistant dean (ADR 0208).

- **`tests/e2e/exit-assistant-dean.spec.ts`.** From a launch inside an LMS
  frame and from web login, the roll-up route's answer and the drawn tree give
  roots Biology, Mathematics and PSYC, PSYC holds PSYC 110 alone, the two
  answers are equal, and both sessions name one person. From the launch, the
  assistant dean switches to the student view and back and signs out, on the
  Bearer carrier alone, and every token the drive held is then refused 401.
- **`tests/e2e/exit-university-line-withheld.spec.ts`**, the entry carried from
  E5: a lead seated over BIOL 310 reads `BIOL-310-R7FF`'s week 6 with the
  comparison line drawn and the university line withheld, on the payload and on
  the page.
- **`tests/integration/test_the_worked_example_from_both_doors_on_the_seeded_institution.py`**
  resolves each door's subject with that door's own function and reads the tree
  through the roll-up on `pulse_app`'s connection, never the seeder's rows
  (`docs/MISTAKES.md` entry 58).

Every page each drive reaches is scanned with axe. No instant is a literal: the
clock is the demo term's last day, or an hour after a window's report opens,
both read from rows. CI run 38300480435 on 9531ff04 passed both drives.

**Green twice on one stack, shown by structure.** No stack built from this
branch was available locally. The assistant-dean drive adds no row (the
enrolment is the mock roster's own, and ended sessions stay ended). The
university-line drive moves BIOL 310's mapping to its reader and back, deletes
the seat it planted, and refuses to start if an earlier run left the mapping
moved; the benchmark world's seeders rewrite their rows in place.

## The standing questions

### `PERSON_TABLES`

`PERSON_TABLES` is unchanged (`user`, `user_identity`, `person`) and correct
for E9's tables. E9-02 and E9-06 add no table: they widen `audit_log` with
`subject_person_id`, `role`, `scope_node_id`, `parent_assignment_id` and
`detail`, recorded in `test_identity_column_marker.py`'s carries-nothing
inventory. `detail` holds staff names and person keys from an import's diff and
no student; no runtime role reads the table, and E10's audit screen must scope
it (carried). E9-04's `revoked_session` holds a token id and two instants and
no person. `test_identity_column_marker.py` passed (32 tests) on this branch.
The owner stays E13.

### The session-read sweep, shown by planting

A session read from the request was planted in `backend/app/api/admin.py`, the
route module E9 adds, and then in `backend/app/services/rollups.py`, one at a
time. `tests/unit/test_only_the_dependency_module_reads_a_session_from_a_request.py`
went red on each (1 failed, 3 passed), naming the planted module; restored, it
is green (4 passed) and the tree clean. The sweep's two disclosed limits stand
and are re-carried.

### The TypeScript 7 watch

Checked 2026-10-12: `typescript-eslint`'s latest is 8.71.2, and its peer range
is still `typescript >=4.8.4 <6.1.0`. The root `package.json` pins TypeScript
6.0.3 and typescript-eslint 8.71.1. Re-carried with the date.

### Every new E9 invariant-marked module is collected by the isolated pass

Thirty-seven test modules added in E9 carry the `invariant` marker, and
`pytest -m invariant --collect-only` collects every one of them: 176 of the 1155
tests the pass collects on this branch.

| Module | Collected |
|---|---|
| `test_a_lead_is_never_answered_a_by_lead_group.py` | 3 |
| `test_a_named_set_figure_meets_both_minimums_inside_the_purview.py` | 4 |
| `test_a_named_set_outside_the_purview_looks_like_a_thin_one.py` | 1 |
| `test_a_named_set_shows_a_lead_nothing_of_a_sibling_lead.py` | 2 |
| `test_a_student_is_named_the_lead_of_her_own_course_and_never_another.py` | 4 |
| `test_e9_a_leader_is_sealed_against_what_they_can_subtract.py` | 11 |
| `test_e9_a_lead_sees_nothing_of_a_sibling_course_on_the_seeded_institution.py` | 1 |
| `test_e9_no_comment_reaches_a_rollup_and_the_drill_down_keeps_its_hold.py` | 2 |
| `test_e9_rollup_lists_keep_their_order_when_only_figures_change.py` | 1 |
| `test_e9_routes_answer_from_the_sessions_own_scope.py` | 5 |
| `test_e9_routes_show_a_lead_nothing_of_a_sibling_leads_course.py` | 8 |
| `test_e9_the_staff_name_definer_receives_purview_sections_only.py` | 2 |
| `test_every_leadership_caller_of_the_staff_name_door_passes_a_scope.py` | 6 |
| `test_every_section_benchmarks_caller_names_the_reader.py` | 8 |
| `test_no_named_set_figure_reaches_a_reader_from_outside_the_purview.py` | 2 |
| `test_no_sequence_of_named_set_reads_isolates_a_sibling_course.py` | 1 |
| `test_nothing_under_the_application_names_a_retired_cohort_view.py` | 3 |
| `test_only_the_leadership_scope_dependency_calls_resolve_scope.py` | 23 |
| `test_the_admin_reads_refuse_a_lead_and_an_instructor.py` | 7 |
| `test_the_attention_card_order_never_follows_a_figure.py` | 2 |
| `test_the_benchmark_seal_counts_a_leadership_reader.py` | 8 |
| `test_the_benchmark_seal_covers_every_hat_one_person_wears.py` | 9 |
| `test_the_exclusion_log_blanks_a_row_another_holder_of_the_readers_role_decided.py` | 2 |
| `test_the_exclusion_log_names_no_week_for_a_decision_its_reader_did_not_make.py` | 6 |
| `test_the_exclusion_log_puts_undated_rows_after_dated_ones_in_no_time_order.py` | 1 |
| `test_the_four_cohort_views_are_retired.py` | 3 |
| `test_the_launch_binding_follows_the_full_purview.py` | 4 |
| `test_the_lead_clamp_and_the_leadership_only_union.py` | 4 |
| `test_the_leadership_scope_comes_only_from_the_session.py` | 2 |
| `test_the_lead_name_door_takes_a_scope_with_no_default.py` | 1 |
| `test_the_named_set_series_route_takes_its_scope_from_the_session.py` | 2 |
| `test_the_purview_walk_holds_over_generated_forests.py` | 5 |
| `test_the_purview_walk_is_transitive_and_batched_by_level.py` | 2 |
| `test_the_role_switch_follows_the_door_and_issues_one_role.py` | 4 |
| `test_the_set_based_staff_name_channel_keeps_each_readers_reach.py` | 15 |
| `test_the_wider_roles_log_stays_inside_their_purview_and_their_teaching.py` | 10 |
| `test_the_worked_example_resolves_on_the_seeded_graph.py` | 2 |

## CI on the exit commit

To be filled with `epic-exit`'s verdict and the CI run on the final head.
