# 0201 — The staff-name channel answers a set of sections, with each name's role

**Status:** Accepted
**Date:** 2026-10-12
**Ticket:** [E9-03](../tickets/e9/E9-03-staff-names-for-a-set-of-sections.md)
**Supersedes in part:** [ADR 0191](0191-a-staff-name-reaches-a-reader-through-one-definer.md):
its one-section door, its rejection of a date parameter, and its UTC-date
consequence. Its definer, v001, stays as it was.

## Context

E9's tree labels name a section's dean, chair, lead and instructor (SPEC §2.1),
and the course pages name the lead in the header. v001 answers one section per
call, and only its instructors and response authors. A leadership page calling it
once per section is the carried "set-based" entry. The E9 README settles who is
answered: ruling 3 (chair and above are answered for any section the door passes;
the door passes only purview sections) as narrowed by decision 16 (a reader whose
only leadership is `LEAD_FACULTY` keeps v001's per-section check). It does not
settle the function's shape, the roles' spelling, or where the reader's date
comes from.

## Decision

- **An overload, not a replacement:** `public.section_staff_names(p_section_ids
  uuid[], p_reader_user_id uuid, p_reader_person_id uuid, p_reader_date date)
  RETURNS TABLE (section_id, role, person_id, display_name)`, in
  `views_sql/section_staff_names_v002.sql`, with v001's NOLOGIN owner
  `pulse_staff_name_definer`. The owner gains `SELECT` on
  `role_assignment.college_id` and `department (id, college_id)`, for the dean row.
- **One row per (section, role, person).** The roles are `INSTRUCTOR`, `AUTHOR`,
  `LEAD_FACULTY` (the mapped lead who holds a `LEAD_FACULTY` assignment, as
  `authz.lead_review_courses` reads it), `CHAIR` (on the course's department) and
  `DEAN` (on the department's college; never an assistant dean or the VP). A
  teacher who also published is two rows.
- **The reader checks.** Exactly one key, or nothing. v001's student, instructor
  and lead checks, applied to each section on its own. A reader holding `CHAIR`,
  `ASSISTANT_DEAN`, `DEAN` or `VP_ACADEMICS` anywhere is answered for every
  section passed. v001's "chair of an unled course" check is not repeated in v002,
  because the broad answer covers it. `CARE` and `ADMIN` reach nothing.
- **The door** `response_loop.section_staff_names(session, *, section_ids,
  reader_user_id=None, reader_person_id=None, scope, settings=None)` sends
  every id in one call. Given an `ActorScope`, it sends only the ids in
  `scope.purview.section_ids`, and it refuses a scope resolved for anyone other
  than `reader_person_id`. It computes the reader's date itself with
  `clock.today` (the application clock, in the institution's timezone). Each
  `StaffName` carries `section_id` and a `StaffNameRole`. The two existing
  callers pass one id and keep only the rows they used before (`AUTHOR` for the
  response's author, `INSTRUCTOR` for the survey page).

## Alternatives rejected

- **Replacing v001.** Nothing gained, and its tests are the record of its rule.
- **A SQL copy of the purview walk.** Declined by ruling 3. It would be a second
  copy of E9-01's walk to keep in step.
- **The broad answer for leads as well.** Decision 16: the database would then
  stop refusing a sibling lead's section to a lead, and the only guard left would
  be the Python door.
- **Collapsing rows to one per person.** That loses which role a name is shown
  under, which is what the labels need.

## Consequences

- **Residue (a): a chair, dean or VP who reaches the door with no `scope` is
  answered for every section passed.** The definer does not know the purview. So
  every Python caller asking as a leadership reader must pass the scope resolved
  for that reader, and E9-12 asserts that at the staff-name door. The door's
  `scope` is a required keyword with no default (the security review's fix
  round), so the opt-out is explicit at every call site: a caller writes
  `scope=None` or the call is a `TypeError`. The two callers this ticket leaves
  write `scope=None` and ask about one section that their own gate has already
  approved.
- **Residue (b): the reader's date is a parameter the definer trusts,** which ADR
  0191 had rejected. A caller who can run SQL as `pulse_app` could pass a past
  date, and a student whose enrollment has ended would then be answered the
  names of that section's staff (or a future date, for an enrollment not yet
  started). The door always computes the date from
  `services.clock` in the institution's timezone; no caller supplies one.
- The carried UTC-date entry is closed: near midnight, and under a moved
  development clock, the definer now judges an enrollment on the same day as the
  survey read. ADR 0193's "known edge" goes with it.
- `test_identity_grants.py` lists functions by name, so the overload does not
  change its count; the count of functions under the name is held to two in
  `test_the_staff_name_channel_answers_a_set_of_sections.py`.
