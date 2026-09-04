# FIX-01 — attempts

## 2026-09-03 — confirming the red set before building

Ran the two must-be-green controls and the whole committed red set against
d51a658, tools by path with the localhost `DATABASE_URL` rewrite.

- `tests/integration/test_the_next_survey_window_is_the_first_one_after_now.py`
  — exit 1: **1 passed** (the seeding control) and **4 errors**, every one the
  `next_window_reader` fixture's `pytest.fail` naming
  `app.services.survey_windows.next_window_for_section` as absent. The named
  missing symbol the manifest predicted, not an incidental `AttributeError`.
- `tests/integration/test_the_student_read_answer_names_the_next_window.py`,
  `tests/unit/test_the_student_surveys_ruled_copy_is_in_the_governed_inventory.py`,
  `tests/integration/test_the_student_read_answer_names_the_course.py`,
  `tests/integration/test_the_course_label_names_nothing_outside_the_students_enrollment.py`
  — exit 1: **13 failed**, matching the manifest row for row (6 next-window
  wire, 1 copy inventory, 2 course label, 4 invariant-marked label tests).
- e2e control, `--grep "the seeded world holds the courses"` — exit 0, passed
  in 1.0s. The seeded world still holds the two courses, the term name and the
  two open windows the spec transcribes.

17 reds, split exactly as the manifest says. Nothing to dispute; building.

## 2026-09-03 — the backend half, first try, green

`next_window_for_section` beside `open_window_for_section`, sharing
`_reading_instant`; `EnrolledSection.next_window_opens_at` filled only when the
open-window read answered `None`; `StudentSurveyView.institution_timezone` from
the settings; `_course_label` given the section and the term.

Worked first time. The four next-window service tests, the six wire tests, the
two course-label tests, the four invariant-marked label tests and the refusal
pair — 25 tests — all green in one run.

One thing the tests did not name and mypy did: `app.api.student`'s
no-`user_id` branch builds `StudentSurveyView(sections=[])` directly, so a
required member on the view is a second construction site. It gets the same
`settings.institution_timezone`, and the handler's docstring says why an answer
about nobody still carries the deployment's zone.

## 2026-09-03 — the frontend half, first try, green

Copy: `student_survey.course_week_eyebrow` and `.term_week_eyebrow` replace the
two bare labels, `.section_closed_body_dated` joins `.section_closed_body`. The
E2-11 parser took all three in the file's literal style with no argument.

`WeekEyebrow` fills the two entries; `SectionSurvey` renders `course_label` as
the whole `h2` and chooses between the two closed sentences;
`institutionInstant` formats the instant with `formatToParts`. Threading the
zone from the read answer meant widening `Load`'s `sections` variant and two
component signatures — the boring route, no context and no module-level
variable.

All seven of the new e2e tests green on the first run after the image was
rebuilt, and the two changed existing spec files with them.

**The Compose stack serves the SPA out of the image, not out of a mount.**
`docker-compose.override.yml` mounts `./backend` only; the frontend is built
into the api image by `backend/Dockerfile`'s first stage. So a frontend change
needs `docker compose build api && docker compose up -d api` before any e2e run
— and **not** `make docker-build`, whose `trap … EXIT` runs `down -v` and takes
the seeded database with it.

## 2026-09-03 — the full suite found one failure, in a file with no SQL

`pytest tests/unit tests/integration -n 4`, 4m30s: **1 failed, 2670 passed**.
The failure was
`tests/unit/test_the_org_views_are_read_only_through_the_grant.py::test_no_module_outside_the_sanctioned_locations_runs_sql_naming_a_policed_relation`
reporting `{'backend/app/schemas/student.py': ['section']}`.

The cause was prose. The new `course_label` field description read "prefix,
number, section code, title, term name", and that sweep's pattern counts `,\s*`
as a position that introduces a relation — the comma-separated `FROM` list an
earlier security pass used to get past it. So "…, section code" read as SQL.

Reworded to "prefix, number, the section code, title and term name", with a
comment above the field saying why, and the sweep module alone re-run green in
0.26s. The guard was not touched: an exemption added so a sentence can keep its
comma is an exemption a real query can then sit behind.

Recorded as `docs/MISTAKES.md` entry 43, and entry 39's counter bumped 2→3 — the
record corrections were drafted while that suite ran and were deliberately held
back, which is what made this single offender unambiguous when it landed.

## 2026-09-03 — one item escalated: `docs/disputes/FIX-01-01.md`

`npx eslint . --max-warnings=0` — the root eslint step in
`.github/workflows/ci.yml`'s `lint-frontend` job — fails with exactly one error,
and it is in the committed spec file:

```
tests/e2e/student-survey-heading-and-next-window.spec.ts
  501:7  error  The value assigned to 'removed' is not used in subsequent statements  no-useless-assignment
```

`let removed = 0;` is a dead initializer; every read of `removed` comes after the
line that reassigns it, and the `finally` does not read it. No implementation
changes this — the rule is evaluated over the spec's own source. The repair is
one line inside `tests/**`, which the lane reserves to the test author, so the
objection is written and this one item stopped. Everything else is built and
green.

`tsc --noEmit` (root and workspace), `eslint` (frontend workspace) and
`vite build` all pass. The build failed once before `npm ci` was run — the local
`node_modules` was missing `@fontsource/*` entirely — which is an install gap
and not a defect in the change.
