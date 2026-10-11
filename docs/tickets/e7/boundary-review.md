# E7 boundary review

The SPEC §14.2 item 6 record for E7 (the response loop). It has four parts: the
reviews and where each finding went, the exit clause driven against the running
stack, the standing questions every epic boundary re-asks, and CI on the exit
commit.

The battery runs on the epic head after E7-09 merges. The reviews' rows, the
findings and CI on the exit commit are filled in by the change that records
them. The standing questions were answered by E7-09, below.

## The reviews

The full battery CLAUDE.md names for an epic boundary, each with a fresh
context, over the epic's cumulative diff against `main`.

| Review | Head reviewed | Result |
|---|---|---|
| `invariant-coverage` | | |
| `adr-docs-completeness` | | |
| `spec-conformance` | | |
| `code-reviewer` | | |
| `app-security` | | |
| `privacy-authz` | | |
| `data-model` | | |
| `prompt-eval` | | |
| `a11y-copy` | | |
| `lti-oidc` | | |
| `threat-model` | | |
| `epic-exit` | | |

## The findings, and where each went

To be recorded with the reviews. Whatever is not fixed inside the epic is added
to `../e8/carried-from-e7.md` with an owner and a done-when, under the heading
that file keeps for this boundary.

## The exit clause, driven against the running stack

SPEC §14.3's E7 exit: "a required-mode section shows nothing to students until
a named human publishes."

Two pieces of E7-09 drive it:

- **`tests/e2e/exit-response-loop.spec.ts`**, over `MATH-140-E1FF`, with
  answers to course weeks 3 and 4 written by
  `scripts/seed_response_loop_exit_story.py`. The Lead Faculty member sets the
  course to required from the policy page a day before week 3's report opens.
  In week 3 the student reads the closed door, with no response card and no
  name. The instructor uses the AI draft, checks it, and publishes; the student
  reads the response under the instructor's name. The instructor edits it; the
  student reads the new text and no closed door. Week 4 has no response: the
  lead's owed list shows it at 48 hours with no on-behalf link, the student
  reads the closed door, and past 96 hours the lead publishes on behalf; the
  student reads the lead's name and role. The student, opening a leadership
  page, reads that it is not part of their role. The lead then sets the course
  back to encouraged before week 5's report opens. Every instant is read from
  the section's own window rows; no date is pinned.
- **`tests/integration/test_a_required_week_shows_students_nothing_until_a_named_person_publishes.py`**,
  the same story in the pytest world through the built application's routes,
  with `response_policy` and `instructor_response` read directly as the
  superuser rather than through any route's answer (`docs/MISTAKES.md` entry
  58).

**The section is not the work order's second section in the prefix.** The
drive's student has to be the mock platform's one launchable learner, and no
prefix holds two sections she is enrolled in, so the on-behalf half runs in
another week of the same section: "another section-week of the same prefix",
in the ticket's words. The chair seat is not driven: the chair reads a led
course's policy read-only, which `leadership-response.spec.ts` already drives.

The drive's first run is CI's: no stack built from the E7-09 branch was
available locally. Its result on the exit commit is recorded with CI below.

## The standing questions

### `PERSON_TABLES`, asked of `instructor_response` and `response_policy`

`PERSON_TABLES` is unchanged (`user`, `user_identity`, `person`), and the
answer is correct for both tables. Each names a `person` key
(`instructor_response.author_person_id`, `response_policy.set_by_person_id`),
the actor convention `moderation_state.decided_by_person_id` and
`audit_log.actor_person_id` already use. The identity behind a key sits on
`person` and `user_identity`, where `pulse_app` holds no `SELECT`; a staff
name reaches a reader only through the staff-name definer (ADR 0191), and
only for a reader of that section. Neither table reaches a student. Both sit
in `REACHED_TABLES_THAT_CARRY_NOTHING` in
`tests/integration/test_identity_column_marker.py` with pinned column tuples,
so either entry expires the first time its table grows a column; the module
passed (32 tests) on this branch. The owner stays E13.

### The session-read sweep, shown by planting

A session read from the request (`from app.services.session import
session_from_request`) was planted in E7's three route-serving modules, one at
a time: `backend/app/api/student.py` (the results route),
`backend/app/api/instructor.py` (the draft, check, publish and edit routes)
and `backend/app/api/leadership.py` (the policy, owed and on-behalf routes).
`tests/unit/test_only_the_dependency_module_reads_a_session_from_a_request.py`
went red on each (1 failed, 3 passed), naming the planted module; restored, it
is green (4 passed) and the tree clean. E7 added no route-serving package
outside `backend/app/`, so the sweep's two disclosed limits stand as disclosed
and are re-carried.

### The TypeScript 7 watch

Checked 2026-10-11: `typescript-eslint`'s latest is 8.71.1, and its peer range
is still `typescript >=4.8.4 <6.1.0`, so TypeScript 7 was not admitted during
E7. The root `package.json` pins TypeScript 6.0.3 and typescript-eslint 8.71.1.
Re-carried with the date.

### Every new E7 invariant-marked module is collected by the isolated pass

Twenty test modules added in E7 carry the `invariant` marker, and
`pytest -m invariant --collect-only` collects every one of them (882 tests in
all on the E7-09 branch). Each module and its collected count:

| Module | Collected |
|---|---|
| `test_a_draft_quoting_a_hidden_comment_is_refused.py` | 6 |
| `test_a_draft_stating_a_count_beside_a_held_stream_is_refused.py` | 19 |
| `test_a_held_streams_themes_carry_no_count.py` | 6 |
| `test_a_refused_results_read_names_nothing_of_the_section.py` | 8 |
| `test_a_response_and_a_policy_are_written_only_by_someone_who_holds_the_role.py` | 17 |
| `test_a_sibling_leads_policy_setting_reaches_nobody_else.py` | 2 |
| `test_no_refused_read_of_the_staff_name_channel_carries_a_name.py` | 2 |
| `test_on_behalf_carries_no_comment_text.py` | 2 |
| `test_on_behalf_refuses_a_section_the_reader_teaches_or_taught.py` | 15 |
| `test_on_behalf_refuses_a_sibling_course_identically_in_every_state.py` | 5 |
| `test_on_behalf_withholds_a_summary_written_before_the_weeks_latest_exclusion.py` | 7 |
| `test_the_draft_gather_sends_no_comment.py` | 3 |
| `test_the_draft_refusal_names_nothing_and_nothing_is_logged.py` | 5 |
| `test_the_leadership_gate_tells_another_role_from_an_ended_session.py` | 8 |
| `test_the_responses_owed_read_lists_only_the_readers_owed_weeks.py` | 5 |
| `test_the_staff_name_channel_answers_no_other_reader.py` | 13 |
| `test_the_staff_name_definer_answers_names_and_never_other_people.py` | 5 |
| `test_the_survey_payload_names_the_sections_instructors.py` | 1 |
| `test_only_the_response_loop_service_names_the_staff_name_definer.py` | 4 |
| `test_the_student_results_payload_carries_nothing_of_a_benchmark.py` | 17 |

## CI on the exit commit

To be recorded: the completed run, its id and its head SHA, on the exit commit
(`docs/MISTAKES.md` entry 42).
