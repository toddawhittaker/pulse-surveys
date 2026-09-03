# E2-14 — The §4.1 pass covers what E2 actually enforces

**ID:** E2-14
**Branch:** `e2/invariant-pass-coverage`
**Depends on:** E2-13 (the boundary review that found every item here)
**Lane:** heavy
**Security-relevant:** yes — every item widens the isolated §4.1 pass.

## Context

The E2 boundary review's invariant-coverage audit, verified adversarially
(the record is `docs/tickets/e2/boundary-review.md`), found that several of
the epic's live confidentiality enforcement points sit outside the isolated
invariant pass. Each claim below was proven by execution, not by reading.

## Scope

1. **The submit path's own-submission lookup gets an invariant test.**
   `_existing_response` (`backend/app/services/submissions.py:385`) is a
   second, independent copy of the `(user_id, section_id, week_id)` key.
   Deleting `Response.user_id == student_id` survives the whole isolated
   invariant pass (188 passed, measured) and is caught only incidentally, by
   an outage-floor test
   (`test_the_submit_path_follows_adr_0056s_taxonomy.py::test_a_provider_answering_503_floors_and_the_submission_is_stored`)
   that submits as a second student for unrelated reasons. The new test's
   subject: a second student submitting into a section-week a classmate has
   already answered writes its own `response` row, leaves the classmate's
   `answer` rows byte-identical, and returns neither the classmate's
   `response_id` nor their `first_submitted_at` — invariant-marked, with the
   classmate's stored values asserted present before the scan.
2. **The leadership purview union enters the pass.** `leadership_grant_covers`
   (`backend/app/services/authz.py:800`, ADR 0108) answering `True`
   unconditionally survives the isolated pass (measured); its only behavioural
   cover is one integration module
   (`test_a_staff_launch_binds_only_inside_the_launchers_purview.py`,
   `pytestmark` without `invariant`). Mark that module at module level, and
   add a direct invariant assertion over the union: a person holding a Lead
   Faculty assignment on one course answers `False` for a sibling lead's
   course and its section, at every grain, including with a second leadership
   assignment unioned in.
3. **The marker currency is made consistent.** Two live §4.1 denial tests hold
   `@pytest.mark.invariant` per test — the currency the denial-module sweep
   refuses — and escape the sweep only by filename:
   `test_the_submit_path_answers_the_validity_matrix.py:751` and
   `test_the_submit_paths_copy_is_externalised.py:456`. Both are collected
   today (this is consistency, not lost coverage). Move the markers to module
   level, or widen `DENIAL_NAME_SHAPES` to reach the two names — one
   direction, chosen and recorded.
4. **The dev clock control's exposure tests enter the pass.**
   `tests/unit/test_dev_clock_control_exposure.py` carries no invariant
   marker while both sibling exposure modules do, and it is the only thing
   asserting the clock-writing routes answer 404 outside development. One
   module-level marker, matching its neighbours.
5. **The item 1 inventory's blind spots get a sweep.** The route inventory
   keeps routes whose dependency graph contains `require_student`; a handler
   calling `app.services.session.session_from_request` directly is invisible
   to it, and `every_route` does not walk a `Mount`'s sub-routes — a live
   case, since `main.py:324` mounts the single-page application. Add an
   invariant-marked sweep asserting no module under `backend/app/api/` other
   than `app.api.deps` imports or calls `session_from_request`, with a
   planted offender and a near miss; match on the import binding, not the
   bare name (`app/api/auth.py:212` defines an unrelated `verified_session`).

## Acceptance criteria

1. Each item's named mutation, re-run against the finished branch, turns the
   isolated invariant pass red (items 1, 2, 5) or the sweep red (item 3's
   chosen direction, item 4's marker proven by `-m invariant` collection).
2. No existing test is weakened, skipped, or renamed to get there.
3. The boundary-review record's disposition lines for these findings are
   updated to point here when this merges.

## Out of scope

- The frontend string-literal sweep (carried to E4 with the copy inventory —
  see `docs/tickets/e3/carried-from-e2.md`).
- Anything in E2-15.
