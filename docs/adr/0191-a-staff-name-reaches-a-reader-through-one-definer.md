# 0191 — A staff name reaches a reader through one definer that checks the reader itself

**Status:** Accepted
**Date:** 2026-10-11
**Ticket:** [E7-01](../tickets/e7/E7-01-response-records-and-name-channel.md)

## Context

SPEC §5.3 posts an instructor's response "non-anonymously under the instructor's
name", and an on-behalf response "attributed honestly to the Lead Faculty". The
survey page should name the section's professor. Staff names live in
`person.identity_name`, and `pulse_app` holds no privilege on `person` by design
(SPEC §8's identity separation). The owner's ruling 4 for E7
(`../tickets/e7/README.md`) settles that the name travels through one narrow
database function. It does not say where the reader check sits, or what shape the
function takes. A launched student has a `user` row and no `person`
([ADR 0028](0028-a-student-holds-no-role-assignment.md)).

## Decision

**One `SECURITY DEFINER` function, `public.section_staff_names(p_section_id,
p_reader_user_id, p_reader_person_id) RETURNS TABLE (person_id, display_name)`**,
in [ADR 0043](0043-the-reveal-function-has-an-owner-of-its-own.md)'s pattern. Its
owner, `pulse_staff_name_definer`, is a NOLOGIN role that holds `SELECT` on exactly
the columns the body reads and nothing on `user_identity`. `pulse_app` may execute
it. The body is `backend/app/views_sql/section_staff_names_v001.sql`.

- **What it answers:** the section's live teaching instructors, and anyone who has
  published a response to the section, each once. The name is
  `person.identity_name`. No other column.
- **The author half is bounded when the row is written.** A response's author
  becomes a name this function answers, so a `BEFORE INSERT` trigger on
  `instructor_response` refuses a row unless the author holds the stated role
  for the section at that moment, by the same three rules as the staff checks
  below ([ADR 0192](0192-the-response-records-are-append-only-and-keyed-by-role.md),
  `response_loop_guard_v001.sql`). Without it, one forged insert followed by one
  call would hand any person's name, a student's included, to the application
  connection.
- **Every reader check sits inside the function, the staff checks included.**
  Exactly one reader key is non-null, or the answer is empty. The student check
  runs on the user key: a live enrollment in the section. The staff checks run on
  the person key: the section's `INSTRUCTOR` grant, or responsibility for its
  course (the course's Lead Faculty, or the department chair for a course with no
  lead). Every other reader gets the empty answer a section with no instructor
  gives.
- **These checks are SQL copies of three Python rules**: `survey_read`'s live
  enrollment (`enrollment_windows.live_on`), `authz.teaching_instructor_assigned`
  and `authz.lead_review_courses`. The copy is deliberate. The tests in
  `tests/integration/test_the_staff_name_channel_answers_no_other_reader.py` hold
  it to the rule over one world that holds every reader kind and every
  one-level-out non-reader.
- **"Today" is the database's UTC date.** The function has no clock parameter.
- **One Python door**: `app.services.response_loop.section_staff_names`, the only
  module under `backend/app/` that names the function. A unit test enforces it.
  The function trusts the reader key it is handed, so the door's job is to pass
  the session's own key and never one from a request.
- **The survey payload's section entry carries `instructors`**: the names the
  channel answers, kept to the section's teaching instructors
  (`authz.teaching_instructors_of`) and sorted. A response author who does not
  teach the section is not listed as its instructor.

## Alternatives rejected

- **A column grant on `person.identity_name`.** `person` holds students too, and a
  grant cannot filter rows, so every name in the institution would be one query
  away from the connection every screen runs on.
- **The staff checks in Python before the call, the student check alone in SQL.**
  The ticket allowed it. It would leave the function answering any member of staff
  for any section, so a second caller, or a bug in the first, would read names
  across the institution. With every check inside, the reader half of the answer
  does not depend on the caller's code, and the cost is one more copy of two
  Python rules, held to them by tests. Who the answer names is bounded by what
  the rows say: the teaching grants and the response authors (see Consequences).
- **One key, the reader's `person`.** A launched student has no `person`, so the
  student, the reader the channel exists for, could not be asked about.
- **A fourth parameter for the institution's date.** The settled signature has
  three. A caller-supplied date would also be one more value the function trusts.

## Consequences

- The function's day and the survey read's day can differ by the institution's
  offset from UTC near midnight, and under a moved development clock the function
  reads the real date. So at either end of an enrollment the check can disagree
  with the survey read for a few hours. The survey read asks only about sections
  it has already found live, so the function is the second check there and never
  the only one.
- A change to any of the three Python rules has to be made in
  `section_staff_names_v001.sql` too, as a new versioned file
  ([ADR 0041](0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md)).
- `test_identity_grants.py` now lists eleven functions `pulse_app` may execute,
  the first that returns a name, and eight definer owners (the eighth is the
  write guard's, ADR 0192).
- **Accepted residue: the instructor half trusts the teaching grants.** The
  names this function answers as instructors are whoever holds a section's
  `INSTRUCTOR` grant, and `public.record_teaching_instructor`, which `pulse_app`
  may execute for the roster sync, accepts any person key. So a caller who can
  run SQL as `pulse_app` can make a person a section's instructor and then read
  their name here. That caller can already grant teaching rights, which is the
  larger compromise, so this ticket does not close it; it is carried to the E7
  exit's hand-off.
- Staff names on leadership pages are E9's, and use this channel or argue for
  another.
