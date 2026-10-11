# E7-02 — The hold

**ID:** E7-02
**Branch:** `e7/the-hold`
**Depends on:** E7-01 (the tables, their grants and the name read)
**Lane:** heavy
**Why this lane:** it adds a student route and extends the invariant-marked
student-route sweep
(`tests/integration/test_every_student_route_carries_nothing_of_a_benchmark.py`
and its siblings) to cover it.
**Size:** M
**Security-relevant:** the gate that decides what a student reads for a week.
A defect here shows a held week to students, or holds back a week that a named
human already released.

## Context

SPEC §5.3: required mode "holds the student-facing aggregate until a response
is published". SPEC §5.4 names the student's page states: `awaiting`,
`published`, `on-behalf` and `small-N`. E7 builds the first three; `small-N`
belongs with the aggregates, in E8 (ruling 8).

This ticket builds the gate as functions in `services/response_loop.py` that
every later reader calls, and never copies:

- **The policy of record for a section-week (ruling 6).** The latest
  `response_policy` row for the course's prefix and its responsible person that
  was recorded at or before the week's report opened (`report_opens_at`,
  ADR 0184). With no such row, the week is encouraged. If the course's
  responsible person changes after the report opens, a held week stays held;
  ADR 0193 records how the gate knows it, since lead mappings keep no history.
- **The latest response.** The `instructor_response` row with the highest
  `sequence` for the section-week.
- **The student's state.** `awaiting` when the policy of record is required and
  no response exists; `published` when a response exists and its author wrote as
  the instructor; `on-behalf` when the first response was written under a
  leadership role; `unanswered` when the week is encouraged and has no response.
  A week whose report has not opened has no state; the route refuses it.
- **Released once, released for good (ruling 3).** A week is released by the
  first response row. Later rows change the text students read, never the
  release.
- **The one writer.** A service function that appends a response row and
  nothing else. It has no route of its own; 03's routes call it after their own
  checks. It does not decide who may publish; it refuses only what the table
  would refuse, so that the checks live in one place, the doors (03).

**The student results route** answers, for one of the student's own sections
and one published course week, the state and the response (text, author name
through 01's channel, author role, time). Nothing else: no aggregates, no
comments, no comparison figures. It reads the week the way the survey route
reads a section, through the student's live enrollment.

Read first: SPEC §4.1, §5.3, §5.4 and §8; ADRs 0184, 0187 and 0191;
`api/student.py` and `services/survey_read.py`, which are the pattern.

## Owns

- `backend/app/services/response_loop.py`: the policy of record, the latest
  response, the state, and the writer.
- `backend/app/api/student.py`: the results route, behind `require_student`.
- `backend/app/schemas/response_loop.py` (new) and `backend/app/copy/response_loop.py`
  (new): the results payload, and the refusal sentences.
- `backend/app/schemas/student.py`, if the route's payload sits there.
- The student-route sweep and payload-schema tests, extended to the new route.
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated.
- SPEC §5.4, only if the `unanswered` state needs naming there.
- ADR **0193** (the hold: the policy of record, release by the first row, the
  states, and the change of responsible person).

## Reuse, do not rewrite

`report_opens_at` and `week_is_published` in `services/reporting.py`;
`survey_read._live_enrollments`; `require_student` in `api/deps.py`;
`lead_review_courses` in `services/authz.py` for the responsible person;
`services/clock.now`; 01's name read.

## Done when

1. **Required holds.** In a required-mode section-week with no response, the
   student reads `awaiting`, and the payload carries no response, no name and
   no count.
2. **A publish releases.** After one response row, the student reads
   `published` with the text, the instructor's name and the role.
3. **On behalf is honest.** A first response written under the Lead Faculty
   role (or the chair acting as lead) reads `on-behalf`, with that person's
   name and role, never the instructor's.
4. **The policy of record is the policy in force at report open.** A switch to
   required recorded after the week's report opened does not hold that week; a
   switch to encouraged recorded after it opened does not release a held week.
   Both cases are tested at one second either side of the opening. If the
   course's responsible person changes after the report opens, a held week
   stays held; this too is tested one second either side of the opening.
5. **An edit never re-holds.** A second row for a released week changes the
   text the student reads and leaves the week released, including when the
   policy changed in between. The latest row by `sequence` is the one read,
   including two rows written in one transaction.
6. **Only the student's own section.** The route refuses a section the student
   is not enrolled in, an ended enrollment, and a week whose report has not
   opened, each with one refusal that names nothing of the section, its
   instructor or its response. Each refusal sits beside a passing twin in one
   world. These tests are marked `invariant`.
7. **The sweep covers the route.** The invariant-marked student-route sweep
   reaches the new route and finds no comparison-set or university figure.
8. **The records match.** ADR 0193 is written and indexed.

## Shares files with

- `services/response_loop.py`: 01 before; 03 after.
- `schemas/response_loop.py`, `copy/response_loop.py`: 03 after.
- `schemas/student.py`: 01 before.
- `openapi.json`, `wire.gen.ts`: 01 before; 03 after.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 22, 29, 51, 53 and 58.

## Known traps

- **Entry 51.** The hold is a property of the sequence of reads. Assert what
  two reads either side of a publish, and either side of an edit, reveal.
- **The calendar bomb.** Pin the clock; never rely on today's date
  (ADR 0184's 06:00 Monday opening applies).

## Not in this ticket

- The routes that publish and edit, and the policy routes (03).
- The student's page (06).
- Aggregates and comments on the student page (E8).
