# E0-41 — Read paths the invariant suite never touches (Batch I)

**ID:** E0-41
**Branch:** `e0/invariant-coverage-gaps`
**Depends on:** E0-18, E0-26, E0-33 (all merged)

## The findings (epic-boundary invariant-coverage audit, 2026-08-22)

The isolated §4.1 pass (54 tests, 36 functions) covers only the read paths
someone thought to test. The subtraction of what-is-tested from what-exists:

- **The LTI launch door has zero invariant-marked tests.** The web door's
  landing pages have three; the launch door — the only door a student can
  enter through — has none. `tests/integration/test_lti_launch_door.py`
  carries no `invariant` marker anywhere, and
  `backend/app/services/landing.py`'s docstring names only the two web-door
  tests as holding its no-identifier rule.
- **`safety.reveal_identity` — the single application-code path to a
  student's name — has no invariant-marked test.** The suite drives the SQL
  functions directly; the service layer's tests
  (`tests/integration/test_care_service_reveal.py`) are marked `integration`
  only, so the `holds_care` pre-check and the record-commit ordering are
  skippable without the isolated pass noticing.
- **§4.1 item 3 has no invariant-marked test.** `raw_comments_permitted`'s
  fail-closed tests sit unmarked in
  `tests/unit/test_deferred_authz_seams_fail_closed.py`, and the resolved
  scope's `n_threshold` assertion sits unmarked in
  `tests/integration/test_a_resolved_scope_holds_care_beside_the_purview.py`.
  The records saying only items 1 and 7 are unasserted become true again when
  these are marked — that is part of the point of this ticket.
- **The three org views are readable unscoped and nothing asserts the reach.**
  `pulse_app` holds unfiltered SELECT on `lead_faculty_course`,
  `assignment_scope`, and `containment_path`; the only narrowing is the WHERE
  inside `services/authz.py`'s grant functions. No sweep asserts that no
  module outside `services/authz.py` runs SQL naming those views, and none
  asserts that nothing outside `services/authz.py` imports
  `app.views_sql.queries` (the code calls that one-import property a control;
  today it is a reviewer's grep).
- **Guards that exist but are skippable**: the deferred-union raise test
  (`transitive_purview`), the two log-surface tests (bound parameters and
  result rows outside development), the dev-console and docs-exposure 404
  tests. All correct, all unmarked, none run in the isolated pass.

## The decisions, settled

This is a coverage ticket: the new tests assert **current, correct** behavior,
so the expected color is green-with-mutation-proof, not red-first. Every test
docstring names the mutation it kills; the manifest predicts green and names
the mutation; the verifier's battery is what proves the tests would catch the
regression. A test that comes up red has found a real defect — stop and
report it, do not adjust the test.

1. New `tests/integration/test_the_launch_views_name_nobody.py`: the student
   page and the instructor page rendered by `POST /lti/launch` name nobody
   and carry no section, course, roster, or comparison identifier — asserted
   against the rendered body, mirroring the web-door trio (read those three
   tests first). Marked `invariant`. Boundary pairs: a positive control per
   page proving the assertion machinery sees the body it thinks it sees.
2. `safety.reveal_identity` service-layer pair, marked `invariant`: a person
   with no live CARE assignment gets `NotCareStaffError` and no name; a
   seeded Care person gets the name (the positive direction already exists in
   `test_care_service_reveal.py` — mark what is needed or add beside it).
3. Item 3 pair marked `invariant`: `raw_comments_permitted` raises rather
   than answering; a resolved scope's `n_threshold` is the configured value.
   Mark the existing tests rather than duplicating them.
4. New sweep, marked `invariant` (one new unit test file): no module outside
   `backend/app/services/authz.py` runs SQL naming `lead_faculty_course`,
   `assignment_scope`, or `containment_path`, and no module outside it
   imports `app.views_sql.queries`. Follow the existing sweep pattern in
   `tests/unit/test_no_service_module_names_an_identity_table_in_a_statement_it_runs`
   (find its file). The inventory of view names must come from the
   `views_sql` directory listing, not a hand-written list, so a new view
   cannot shrink the sweep.
5. Markers added (`pytest.mark.invariant`, keeping existing markers) to: the
   deferred-union raise test, the two log-surface guards, the dev-console
   404 test, the docs-exposure tests, and the deferred authz seam tests.
6. Implementer side: `landing.py`'s docstring updated to name all four
   landing surfaces its rule is held on; the `authz.py` comment calling the
   one-import property a control updated to point at the sweep that now
   mechanises it; and the two false attributions found by the docs audit in
   backend docstrings corrected — `authz.py` line ~3 attributes the
   thin-router rule to CLAUDE.md (it lives in SPEC §13 only) and
   `tokens.py` line ~9 cites a CLAUDE.md duplication rule that does not
   exist (attribute to what actually holds the rule, or drop the citation).

## Acceptance

- The isolated invariant pass grows from 54 collected; every addition
  collected and green; `scripts/ci/check_invariants.py` and
  `check_invariant_assertions.py` both pass.
- The verifier's mutation battery kills, at minimum: a launch landing page
  gaining a seeded person's name; a launch landing page gaining a section
  code; `reveal_identity` skipping the `holds_care` check; the seam returning
  a value instead of raising; a service module gaining a direct
  `lead_faculty_course` query; a module outside authz importing
  `queries`. Near-misses included per docstring.
- Full suite green.

## File ownership (parallel-build boundary — do not cross)

This ticket may touch: files under `tests/` EXCEPT
`tests/unit/test_compose_stack.py`, `tests/unit/test_env_example_resolves.py`,
`tests/unit/test_oidc_provider_configuration.py`,
`tests/unit/test_the_detect_probes_see_the_files_their_jobs_run.py`, and
`tests/unit/test_when_only_diff_does_not_run_the_expensive_gates.py` (sibling
tickets own those); plus docstring/comment-only edits in
`backend/app/services/landing.py`, `backend/app/services/authz.py`,
`backend/app/services/tokens.py`; plus this ticket file. No behavior change
in any `backend/` file. Never `pyproject.toml`, never CI files, never
`docs/` beyond this ticket file.
