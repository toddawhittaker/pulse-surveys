# 0183 — A teaching grant is deleted when the roster drops it, and enrollment means "student"

**Status:** Accepted
**Date:** 2026-10-03
**Ticket:** [E5.1-02](../tickets/e5.1/E5.1-02-roster-grants-and-respondents.md)
**Amended:** 2026-10-03 by [E5.1-11](../tickets/e5.1/E5.1-11-roster-roles-and-term-end.md); see the section at the end

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
   no LMS user is ended too: no roster can list them. (Amended by E5.1-11: no grant
   is written or ended once the section has ended, and a walk that read no member
   ends nothing.)
2. **A new owner role, `pulse_grant_end_definer`**, holding `SELECT, DELETE` on
   `role_assignment`, `SELECT (id, section_id, response_code)` on `nrps_call` and
   `INSERT` on `ended_teaching_grant`, and nothing else. `pulse_app` holds nothing
   on the new table and still no `DELETE` on `role_assignment`.
3. **One new reader in `authz.py`**, `teaching_instructor_grants`, answering
   `{assignment id: person id}`, because `assignment_scope` is read only there
   (E0-41) and the sync needs ids to end. No existing predicate changed.
4. **Enrollment means "student"** (as amended by E5.1-11). A member is a student
   only if the roster lists the Learner role, lists neither the Instructor role nor
   any Instructor sub-role (`…/membership/Instructor#…`), and does not list
   `…/lti/system/person#TestUser`. Anybody else is written no enrollment, on any
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
- A grant planted by hand on a walked section is ended by the next complete walk
  that read at least one member, up to the section's last day. Sections without a
  roster address are never walked and keep theirs.
- The participation sweep's staff filter (`section_scoped_assignees`) stays, for
  the residue above.

## Amended by E5.1-11 (2026-10-03)

The E5.1 epic-boundary reviews found decision 4 a deny-list and the grant-ending
pass unbounded in time and in what it trusts. Four changes.

- **Decision 4 is an allow-list.** The original rule made every member a student
  unless the roster listed the exact Instructor or TestUser role, so a teaching
  assistant listed only as `…/membership/Instructor#TeachingAssistant`, a Mentor,
  a ContentDeveloper or an Administrator got a student enrollment: they could
  submit, and they counted toward the five distinct commenters SPEC §4 requires
  before a stream's raw comments show. The rule is now the one stated in decision
  4 above. Who holds the teaching *grant* is unchanged: the exact Instructor role,
  not dropped. A member who stops being a student is closed by the same path as a
  teacher or a test user. *Rejected:* growing the deny-list by the roles the
  reviews named. It is a closed set guarding an open vocabulary, and the next
  role a platform sends (a sub-role, a custom role) is a student again.
  *Cost:* a platform that lists its students with no Learner role at all
  enrolls nobody. That fails visibly (an empty class) rather than quietly.
- **No grant is written or ended once the section has ended.** When the clock
  service's `today` is after `section.end_date` (the section's inclusive last
  day), the sync neither writes a teaching grant nor runs the grant-ending pass;
  on `end_date` itself it does both. One condition, computed once in `_ingest`,
  gates both. Writing and closing enrollments are unchanged. Platforms commonly end teacher enrollments when a
  course concludes, and the hourly walk visits a section for as long as it has a
  roster address, so without this the instructor lost her past reports and SPEC
  §5's seal changed what it treats as her sections. *Rejected:* ending grants
  after term as the platform says, which is what the original decision did.
  *Cost:* an instructor really removed after the term keeps the grant on that
  past section until E9's end-dating gives an admin a way to end it.
  **Writing is gated too**, because a grant written after the last day is one no
  later walk can end: a person first listed as Instructor on a past section
  would hold its reports for good. *Rejected:* gating only the ending pass,
  which the privacy and authorization review of this ticket found. *Cost:* an
  instructor the platform adds to a section after it ended, to grade late work
  for example, gets no grant from the sync and needs E9's admin surface.
- **A walk that read no member is incomplete.** A walk reported complete whose
  members, read and keyed by subject, number zero closes no enrollment and ends no
  grant; it is decided where `_ingest` reads `complete`, not in the page reader.
  *Rejected:* trusting an empty walk, which ended every grant and closed every
  enrollment on the section on one empty answer from the platform.
  *Cost:* a platform that truly empties a course leaves its rows open until a
  later walk lists somebody. That is rare and recoverable; the alternative is not.
- **What the roster timeout bounds.** `ROSTER_REQUEST_TIMEOUT` is a `requests`
  `(connect, read)` pair: it bounds the connect and each wait between bytes of the
  answer, not the whole request and not name resolution. A platform that trickles
  a byte every few seconds can hold a call longer. A total deadline belongs to the
  carried entry for rehoming the LTI transport (`docs/tickets/e5.1/README.md`),
  not here; the values are unchanged.
