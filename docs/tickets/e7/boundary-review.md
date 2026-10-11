# E7 boundary review

The SPEC §14.2 item 6 record for E7 (the response loop). It has four parts: the
reviews and where each finding went, the exit clause driven against the running
stack, the standing questions every epic boundary re-asks, and CI on the exit
commit.

The battery ran on the epic head 7b5f0c94, after E7-01 to E7-08 merged, against
`main` at c76b1724. Its findings became two fix tickets: E7-10 (#318, heavy)
for the backend, test and record findings, and E7-11 (#316, light) for the
accessibility findings. CI on the exit commit is filled in when the epic head
is final. The standing questions were answered by E7-09, below.

## The reviews

The full battery CLAUDE.md names for an epic boundary, each with a fresh
context, over the epic's cumulative diff against `main`.

| Review | Head reviewed | Result |
|---|---|---|
| `invariant-coverage` | 7b5f0c94 | 1 HIGH, 3 MED, 2 LOW |
| `adr-docs-completeness` | 7b5f0c94 | 2 MED, 3 LOW |
| `spec-conformance` | 7b5f0c94 | 1 MED, 4 LOW; every done-when of E7-01 to E7-08 met |
| `code-reviewer` | 7b5f0c94 | 1 MED, 1 LOW, 8 simplifications |
| `app-security` | 7b5f0c94 | 1 MED |
| `privacy-authz` | 7b5f0c94 | 1 MED, 1 LOW |
| `data-model` | 7b5f0c94 | 2 LOW |
| `prompt-eval` | 7b5f0c94 | 1 MED, 2 LOW |
| `a11y-copy` | 7b5f0c94 | 7 MED, 4 LOW |
| `lti-oidc` | 7b5f0c94 | Nothing found |
| `threat-model` | not run | SPEC §14.3 does not mark E7 ⚠ |
| `epic-exit` | | Runs on the final epic head; recorded below. |

## The findings, and where each went

**Fixed in E7-10 (#318), tests first:**

- HIGH (`invariant-coverage`): the on-behalf draft and check routes had no
  §4.1 test for their refusals. Only the instructor's door was covered. Tests
  now cover the on-behalf route past 96 hours, a scripted draft that lifts an
  excluded or still-flagged comment or a held stream's figures (refused, no
  row written), and an accepted control that lifts a published comment. The
  on-behalf gather and prompt carry no comment and no held count.
- MED (`invariant-coverage`): the instructor's read of a week's response was
  untested against a sibling's week, a missing week and an unpublished week.
  It now answers the report's own 404 for each, byte for byte, with no text or
  name.
- MED (`invariant-coverage`): the draft routes' taught-and-published test and
  the publish route's sibling-section test lacked the cases for a week that is
  not taught, does not exist or is unpublished. Added.
- MED (`invariant-coverage`): SPEC §4.1 item 1 was not checked on the rendered
  student results page. The benchmark-exclusion end-to-end spec now opens that
  page and runs the same canary check.
- LOWs (`invariant-coverage`): the student results page counted under the
  student survey surface for the confidentiality line. It is now its own
  governed surface, with the decision recorded that it owes no line. Two
  policy-switch tests gained the missing marker. The `privacy-authz` LOW on the
  same surface is closed by the same change.
- MED (`app-security`): the draft and check routes held a database connection,
  with a transaction open, for the whole 30 to 60 seconds of the model call, and
  nothing limited one person's requests. About fifteen at once could empty the
  connection pool and fail every request, including a student's submit. Every
  read now happens before the call and the transaction ends first, and one
  draft or check per person may be in flight; a second gets a 429 before any
  model call.
- MED (`prompt-eval`): the on-behalf draft used the prompt written in the
  instructor's first-person voice, which risked putting words in an instructor's
  mouth and promising actions only an instructor can take (SPEC §5.3). It now
  has its own prompt version (`response_draft.v3`) written as the named
  leadership role. Eval cases cover the on-behalf family, a null summary and an
  empty week, and the draft check has cases for no themes and a null summary,
  each with a breach.
- LOW (`prompt-eval`): the eval set's prompt versions were not tied to the
  versions the tasks use. Equality tests now pin them.
- MED (`privacy-authz`): the instructor's draft gather kept summaries written
  before the week's latest exclusion, so a paraphrase of an excluded comment
  could pass the run's refusal and reach published text. Every draft gather now
  uses the on-behalf summary filter, and ADR 0195 is corrected. A test excludes
  a comment after its summary was written and shows neither the summary nor its
  themes reach the prompt, while a summary generated after the decision is
  still used.
- MED (`code-reviewer`): the first person to publish on behalf of a course could
  not return to edit, because the on-behalf read answered 404 once the week was
  answered. That read now answers the first publisher with the response, the
  page seeds the composer from it, and everyone else still gets the 404.
- LOW (`code-reviewer`): a co-instructor was offered Edit and then met a 409.
  The week's view now says whether the reader can edit, and the composer shows
  Edit only then.
- Simplifications 6, 7 and 8 (`code-reviewer`): the 502 message defined twice is
  defined once; the stream-on-the-wire check lower-cases the token; comments
  that cited fix rounds, a stale `WeekEyebrow` comment and the SPEC §13 line are
  corrected.
- MED and three LOW (`adr-docs-completeness`): SPEC §8's `response_policy`
  bullet described a row per prefix, person and role. It now says one row per
  course, with the policy of record the latest row for the course when the
  report opens (ADR 0193). The SPEC §13 line for `response_loop.py` is
  corrected; the second `RESPONSE_TEXT_MAX` in `schemas/report.py` is replaced
  by an import, and ADR 0195's line about it is dropped; ADR 0195's "two
  structural refusals" now counts three.
- MED and LOWs (`spec-conformance`): the same SPEC §8 correction, plus a rule
  written into SPEC §5.3 and ADR 0193 that a course's policy carries over when
  its lead changes, with an inheritance test. The §13 lines for
  `api/leadership.py`, `api/instructor.py`, `copy/response_loop.py` and the
  `views_sql` files are drawn. The five attempt records filed under
  `docs/tickets/e0/.attempts/` moved to `docs/tickets/e7/.attempts/`. The unused
  `response_draft.v1` prompt and its pin row are deleted; it was never stored.
- LOW (`data-model`): `response_policy.prefix_id` looks redundant, since the
  course gives the prefix. ADR 0193 now says why it stays: it records the
  prefix the setter switched. The stale comment in `models/identity.py` is
  corrected.
- MED (`a11y-copy`, the re-check of #316): an advisory announcement that the
  new live region made audible was fixed.

**Fixed in E7-11 (#316, merged as 5f7779c9):** all seven MEDIUM and four LOW
accessibility findings. The replace-draft question is named and takes focus;
the status message is always rendered, so screen readers hear it; controls that
are busy are marked unavailable instead of disabled, so focus stays; a week
change moves focus to the heading; the identical "See your instructor's reply"
links name their course; the policy toggle's off state meets contrast; the
response card matches its prototype; failures of a draft or check no longer
mark the field invalid; "Use draft" became "Draft with AI"; the toggle has its
help text attached; and the owed-list copy no longer says "section-weeks".

**Not ours:** `CLAUDE.md` still names E6 as the active epic
(`adr-docs-completeness`, MED). Process pull request #305 changes it, and it
waits for the owner. `lti-oidc` found nothing.

**The carry-over rule.** The spec did not settle what happens to a course's
policy when its lead changes. E7-10 writes the rule into SPEC §5.3 and §8: the
old setting still holds the course for its new lead, and the overview shows the
new lead no setter until they set one. Resetting the course to its default was
rejected, because it would release held weeks without anyone deciding to.

**Carried to E8, each with an owner and a done-when in
`../e8/carried-from-e7.md`:** simplifications 1 to 5 from `code-reviewer`; the
unindexed `role_assignment.section_id` (`data-model`); the draft eval set not
typed through its output contract (`prompt-eval`); the on-behalf and unanswered
paths not driven on the stack (`spec-conformance`); and the unused `for_on_behalf`
keyword on `response_gather`. The exit carries listed in that file were already
there when the battery ran.

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
