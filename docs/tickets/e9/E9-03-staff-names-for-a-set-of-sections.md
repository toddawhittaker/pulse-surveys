# E9-03 — Staff names for a set of sections

**ID:** E9-03
**Branch:** `e9/staff-names-for-a-set-of-sections`
**Depends on:** none
**Lane:** heavy
**Why this lane:** a new version of a `SECURITY DEFINER` function under
`backend/app/views_sql/` that reads `person`, and a migration that grants on
it.
**Size:** M
**Security-relevant:** the one channel through which a staff name reaches a
reader (ADR 0191). A defect here names staff to a reader who should not see
them, or, through a wrong reader check, opens the channel to a student for a
section they are not in.

## Context

`section_staff_names` v001 answers one section at a time, to a student of the
section, its instructor, or its lead (or, for an unled course, its chair).
E9's tree labels name a dean, a chair, a lead and each section's instructor
(§2.1), and the course pages name the lead in the header (E9-08). A
leadership page calling v001 once per section is the carried "set-based"
entry.

**v002 is set-based.** It takes an array of section ids and the reader's keys,
and answers rows of `(section_id, role, person_id, display_name)` for each
section's live teaching instructors, its published responses' authors, its
course's lead, its department's chair and its college's dean. A student,
instructor, lead or chair reader keeps exactly v001's reach, per section.

**Ruling 3: leadership readers.** A reader holding any live leadership
assignment (`LEAD_FACULTY`, `CHAIR`, `ASSISTANT_DEAN`, `DEAN`,
`VP_ACADEMICS`) is answered for any section passed. The definer does not
recompute the purview. The Python door in `services/response_loop.py`
takes the reader's `ActorScope` from its caller (the route resolves it
through E9-01's `leadership_scope`) and passes only section ids inside its
purview. The door's parameter is the existing `ActorScope` type, so this
ticket does not wait on E9-01. A Python scoping bug would show staff names, never student
data, outside the purview; E9-12 asserts the door.

**The reader's date.** v001 judges "today" by the database's UTC date, so near
midnight it can disagree with the route (the carried entry). v002 takes the
reader's date as a parameter, computed by the door from `services/clock.now`
in the institution's timezone.

Read first: SPEC §2.1 (labels and headers), §4 and §5.3; ADRs 0109, 0191,
0192 and 0193; `views_sql/section_staff_names_v001.sql`; the door
`response_loop.section_staff_names`; the migration
`20261011_2c3d5a0de424_the_response_records_and_the_staff_name_channel.py`.

## Owns

- `backend/app/views_sql/section_staff_names_v002.sql` (new).
- Migration **`e9b2c4d6a802`**, planned `down_revision = "e9a1d0c3f201"`
  (re-pointed to the head it finds if 02 has not merged).
- `backend/app/services/response_loop.py`: the door becomes set-based, takes
  the reader's date from the app clock, and for a leadership reader passes
  only purview sections. Existing single-section callers call it with one id.
- `tests/integration/test_identity_grants.py`: the grant's row.
- SPEC §13: the new view file.
- ADR **0201** (the set-based channel and ruling 3); supersedes ADR 0191 in
  part, with a line in 0191.

## Reuse, do not rewrite

v001's reader checks, kept as they are for the four existing reader kinds;
`authz.teaching_instructors_of`; `services/clock.now`; ADR 0191's NOLOGIN
owner.

## Done when

1. **One call for many sections.** A leadership page's names for forty
   sections are read in one definer call: a query-count test over the door
   with forty sections counts one call.
2. **Each role is answered.** For a seeded section, the rows name its live
   instructor, a published response's author, the course's lead, the
   department's chair and the college's dean, each with its role. A course
   with no lead answers no lead row; a department with no chair answers no
   chair row.
3. **The existing readers keep their reach.** A student of section A gets A's
   rows and nothing for section B passed in the same call; an instructor of A
   likewise; a lead of A's course gets A's rows and nothing for a sibling
   lead's section. Each refused row has its present twin in the same call.
4. **A leadership reader is answered for what the door passes (ruling 3).** A
   dean's call with any section ids is answered; a person with no live
   assignment and no enrollment gets nothing; a Care-only and an Admin-only
   person get nothing. A `pulse_app` session cannot call v001 or v002 with a
   reader key it chooses to gain more than that key holds (the reader keys
   are checked inside the function, as in v001).
5. **The door passes purview sections only.** The door, given a leadership
   reader and a list containing a section outside their scope, calls the
   definer without it and answers no row for it.
6. **The date is the app clock's.** With the development clock moved so the
   UTC date and the institution's date differ, an enrollment ending today in
   the institution's timezone is answered the same way the survey read
   answers it.
7. **Nothing else changed.** The survey page, the instructor report and the
   response pages name the same people as before (existing tests green,
   unchanged).
8. **The records match.** ADR 0201 is written and indexed, ADR 0191 gains its
   line, and the carried UTC-date entry is named closed in the pull request.

## Shares files with

- `services/response_loop.py`: 07, 08 and 09.
- `tests/integration/test_identity_grants.py`: 02 and 12.
- Migration chain: 02 and 04.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 17, 46 and 50.

## Known traps

- **Entry 46.** Test the grant through `pulse_app`'s connection.
- **The chair of an unled course.** v001's chair limb answers only for a
  course with no lead; keep that limb exactly, and add the chair name as a
  separate role row.

## Not in this ticket

- Showing the names anywhere new (07, 08, 11).
- The purview itself (01).
