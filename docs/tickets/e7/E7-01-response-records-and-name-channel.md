# E7-01 — The response records and the name channel

**ID:** E7-01
**Branch:** `e7/response-records-and-name-channel`
**Depends on:** none
**Lane:** heavy
**Why this lane:** a definer and a grants file under `backend/app/views_sql/`,
a migration that grants on new tables and reads `person`, and amendments to the
invariant-marked grant tests in `tests/integration/test_identity_grants.py`.
**Size:** L
**Security-relevant:** the first channel that carries a staff member's name to
a student. A defect here hands a name to a reader outside the section, or puts
a name in a refusal body.

## Context

SPEC §5.3 has the instructor's response posted "non-anonymously under the
instructor's name", and an on-behalf response "attributed honestly to the Lead
Faculty". `carried-requirements.md` parked the name channel for this epic: the
survey page's heading should name the professor, and E7's attribution needs the
same channel. Today `pulse_app` holds no grant on `person` or `user_identity`,
by design, and staff names live in `person.identity_name`.

**The channel (ruling 4).** One SECURITY DEFINER function in the house pattern
(`backend/app/views_sql/teaching_instructor_v001.sql` and ADR 0043: a NOLOGIN
owner whose privileges can be read in the file, `search_path` with `pg_temp`
last, typed parameters, no dynamic SQL). For one section and one reader it
answers the names of the section's live teaching instructors, and the name of
anyone who has published a response to that section, and nothing else. It
answers only a reader of that section: an enrolled student with a live
enrollment, the section's instructor, or the lead or chair responsible for its
course (`authz.lead_review_courses`). Every other reader gets an empty answer,
the same as a section with no instructor. A column grant is the wrong shape:
`person` holds students too, and a grant cannot filter rows.

The student check must sit inside the definer, because the student is the
reader the channel widens. Whether the staff-reader check also sits in SQL, or
in Python before the call, is ADR 0191's decision; either way the tests below
pin it at the route.

**The records (rulings 3 and 7).** Two append-only tables, in `models/loop.py`:

- `instructor_response`: section, course week, author (`person` key,
  `RESTRICT`), the role the author wrote under (instructor, Lead Faculty, or the
  chair acting as lead), whether the text was seeded from an AI draft, the text,
  the time, and a database-assigned `sequence` column so that "latest" is
  insert order (as `moderation_state.sequence` is, ADR 0187). On-behalf is the
  role, not a second flag that could disagree with it. The text is non-blank and
  bounded, and the bound is one constant.
- `response_policy`: prefix, the person who set it, the role they set it under,
  the mode (encouraged or required), the time, and `sequence`. Ruling 1 keys a
  policy by prefix and responsible person. ADR 0192 states how a person who
  both leads courses and chairs the department is keyed (a lead's switch and a
  chair's switch in one prefix cover different courses).

`pulse_app` gets `SELECT` and column-grain `INSERT` on both, and no `UPDATE` or
`DELETE`. There is no `audit_log` row for a policy change or an on-behalf
response: these tables are the record (ruling 7), and `audit_log.subject_user_id`
must hold a student anyway.

Read first: SPEC §4, §4.1, §5.3, §8 and §13; ADRs 0043, 0187 and 0189;
`carried-requirements.md`; `backend/app/views_sql/moderation_decision_grants_v001.sql`
(column grants on an append-only table).

## Owns

- **M1**, with `down_revision = "b7d2e94c1a05"`: both tables, their `CHECK`s and
  indexes, the grants file, and the definer. Its downgrade refuses while either
  table holds a row, as E6-09 made the moderation downgrades do.
- `backend/app/views_sql/response_loop_grants_v001.sql` and
  `backend/app/views_sql/section_staff_names_v001.sql`.
- `backend/app/models/loop.py` (new).
- `backend/app/services/response_loop.py` (new), with the one Python call to the
  definer. Nothing else under `backend/app/` calls it.
- `backend/app/services/survey_read.py` and `backend/app/schemas/student.py`: the
  survey payload's section entry carries its instructors' names, read through
  the channel.
- `tests/integration/test_identity_grants.py`, amended by the new grants only.
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated; frontend code
  only as far as the type check needs (06 renders the name).
- SPEC §8 (the `response_policy` table in the list; the `instructor_response`
  line states the role and the sequence; the `audit_log` line no longer claims
  policy changes or on-behalf actions, per ruling 7) and §13 (`models/loop.py`,
  `services/response_loop.py` and the two `views_sql` files drawn as built).
- ADRs **0191** (the name channel: its shape, its readers, why not a grant) and
  **0192** (the two records, their keying and the two-hat case, why no
  `audit_log` row).

## Reuse, do not rewrite

`teaching_instructors_of`, `teaching_instructor_assigned` and
`lead_review_courses` in `services/authz.py`; `survey_read._live_enrollments`
(not grading's copy); `models/report._in_the_vocabulary` for the role `CHECK`;
`services/clock.now`.

## Done when

1. **The tables are append-only as production runs them.** Through the
   production connection, `pulse_app` can insert the listed columns of each
   table and read them, and cannot update or delete a row (MISTAKES entry 46).
   The downgrade refuses while a row exists, and runs clean on an empty table.
2. **The name reaches its readers.** A student with a live enrollment in a
   section gets that section's instructor's name, through the survey payload.
   The section's instructor, and the lead responsible for its course, get it
   through the service. Once a response is published to the section, its
   author's name is answered too.
3. **The name reaches nobody else.** The same call answers nothing for a student
   of another section, a student whose enrollment has ended, an instructor of a
   sibling section, a lead of a sibling course, and a chair of another
   department. Each test sits beside its passing twin in one world (entry 3).
   Each refused-reader case also calls the database function directly as
   `pulse_app`. If the staff check sits in Python, the function itself still
   answers nothing for a reader neither enrolled in nor teaching the section,
   including a two-hat person who is a student in section A and an instructor
   in section B, asking for section C. These tests are marked `invariant`.
4. **No refusal carries a name.** A refused read, at the service and over HTTP,
   carries no staff name in its body, its headers or its log line. The test
   plants a distinctive name and searches every refusal for it.
5. **The channel answers names, never other people.** The definer cannot return
   a student's name, an email address, or any column but the name, whatever
   section is asked. A test that enrols a student whose name is distinctive
   proves it.
6. **One door.** A unit test proves that `services/response_loop.py` is the only
   module under `backend/app/` that names the definer.
7. **The records match.** SPEC §8 and §13 are edited as listed; ADRs 0191 and
   0192 are written and indexed in `docs/adr/README.md`.

## Shares files with

- `services/response_loop.py`, `schemas/student.py`: 02 after this merges.
- `openapi.json`, `wire.gen.ts`, `docs/adr/README.md`: 04 and 08 in parallel.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 22, 35, 46, 50, 53 and 58.

## Known traps

- **Entry 53.** The reader check is a closed set. Attack it one level out: a
  student enrolled in a different section of the same course, an instructor
  whose teaching grant the roster ended.
- **Entry 22.** The new survey-payload member reaches every student fixture and
  the student payload tests. Change them in this ticket.
- **Entry 43.** A `Field(description=...)` or refusal sentence that names
  `section` after a comma or `from` trips the SQL sweep. Reword it.

## Not in this ticket

- The hold, the publish writer and the student results route (02).
- Any page (05, 06, 07).
- Staff names on leadership pages (E9).
