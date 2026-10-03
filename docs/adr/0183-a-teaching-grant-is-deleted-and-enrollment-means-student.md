# 0183 — A teaching grant is deleted when the roster drops it, and enrollment means "student"

**Status:** Accepted
**Date:** 2026-10-03
**Ticket:** [E5.1-02](../tickets/e5.1/E5.1-02-roster-grants-and-respondents.md)

## Context

SPEC §2.1 puts teaching instructors and enrollments on the LMS's side. The roster
sync only ever added the `INSTRUCTOR` row in `role_assignment`, while the read
predicates in `app.services.authz` treat a grant as live while its row exists, so
an instructor the LMS removed went on reading the section. The sync also wrote an
enrollment for every roster member, and a launch with no assignment and a live
enrollment lands as a student, so staff and the platform's preview accounts were
counted as respondents and could submit. `role_assignment` has no validity dates;
SPEC §14.3 gives end-dating assignments to E9.

## Decision

1. **An ended grant is deleted, and recorded.** After a complete walk, every
   `INSTRUCTOR` grant on the section whose person the roster did not list as an
   active Instructor is ended through `public.end_teaching_instructor(assignment,
   call, day)`. It refuses (SQLSTATE 42501) anything but a section-scoped
   `INSTRUCTOR` row, and any cited `nrps_call` that is missing, of another section,
   or not 2xx (NULL included). It deletes the row and inserts an
   `ended_teaching_grant` row (assignment, person, section, role, day, call) in the
   same call, with no exception handler and no `ON CONFLICT`, so a failed record
   rolls the deletion back. A truncated walk ends nothing. A grant whose person has
   no LMS user is ended too: no roster can list them.
2. **A new owner role, `pulse_grant_end_definer`**, holding `SELECT, DELETE` on
   `role_assignment`, `SELECT (id, section_id, response_code)` on `nrps_call` and
   `INSERT` on `ended_teaching_grant`, and nothing else. `pulse_app` holds nothing
   on the new table and still no `DELETE` on `role_assignment`.
3. **One new reader in `authz.py`**, `teaching_instructor_grants`, answering
   `{assignment id: person id}`, because `assignment_scope` is read only there
   (E0-41) and the sync needs ids to end. No existing predicate changed.
4. **Enrollment means "student".** A member whose roles carry the Instructor URI
   or `…/lti/system/person#TestUser` (exact match) is written no enrollment, on any
   walk, and an open one is closed with `max(started_on, yesterday)`. Yesterday,
   because the live test is `ended_on >= today`, so a row closed with today still
   lets its holder land and submit today. Instructor plus Learner still teaches.

## Alternatives rejected

- **End-dating the grant** (a validity column and a filter in every predicate):
  that is E9's, and it would change every authz predicate in a ticket that must
  not touch them.
- **`GRANT DELETE ON role_assignment TO pulse_app`**: a grant cannot bound which
  role's row goes, so a `CARE` row would go as readily.
- **Widening `pulse_instructor_definer`**: one owner able to add and delete grants
  makes each door the other's blast radius (ADR 0043: one role per door).
- **Recording the ending in `audit_log`**: it holds identity reveals, needs an
  acting person, and is what E10's Care reader reads.
- **Closing a staff enrollment with today**, as a vanished student's is: it leaves
  the person a student for the rest of the day.

## Consequences

- One day of residue: an enrollment opened earlier the same day, while the member
  was listed as a learner, can only be closed with today
  (`CHECK (ended_on >= started_on)`), so it covers today. From tomorrow it covers
  nothing, and no later walk opens another.
- A grant planted by hand on a walked section is ended by the next complete walk.
  Sections without a roster address are never walked and keep theirs.
- The participation sweep's staff filter (`section_scoped_assignees`) stays, for
  the residue above.
