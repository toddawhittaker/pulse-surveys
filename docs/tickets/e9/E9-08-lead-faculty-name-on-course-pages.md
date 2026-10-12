# E9-08 — The Lead Faculty name on course pages

**ID:** E9-08
**Branch:** `e9/lead-faculty-name-on-course-pages`
**Depends on:** 03
**Lane:** heavy
**Why this lane:** the carried split's done-when makes the student import
sweep name the new module, and that sweep is `invariant`-marked, so the
ticket edits an invariant test. The rest is a pure move of the student read
into its own module and a staff name added to two page headers through
E9-03's door, which would be light alone.
**Size:** M
**Security-relevant:** the student's page. A defect in the move drops a hold
check, and a defect in the header names a lead to a student of another
section.

## Context

SPEC §2.1: "Course-level pages (instructor report, student results) carry the
Lead Faculty name in the header." Neither does today (ruling 5 of
`../e8/README.md`, carried). And `services/response_loop.py` is over 1,200
lines and holds the student read beside the response loop (the carried
split).

1. **The move, first and alone.** The student read (`student_week_results`
   and its private helpers) moves to `services/student_results.py`, as one
   commit that changes no behaviour: every existing student test stays green
   unchanged, and the import sweeps name the new module in place of the old
   for the student path.
2. **The lead's name.** The student results payload and the instructor report
   payload each gain the course's lead name, read through E9-03's door with
   the reader's own keys. A course with no lead carries no lead name, and no
   placeholder.

**Ruling 9** is already written into SPEC §5.4 by this breakdown. This ticket
adds one line to ADR 0197 pointing at it, since 0197 records the shares.

Read first: SPEC §2.1 and §5.4; ADRs 0191, 0197 and 0201;
`services/response_loop.py`; the student import sweep
(`tests/unit/test_the_report_comment_service_names_nothing_a_student_path_can_reach.py`)
and payload sweep
(`tests/unit/test_the_student_payload_schema_carries_nothing_of_a_benchmark.py`).

## Owns

- `backend/app/services/student_results.py` (new) and the matching removal
  from `backend/app/services/response_loop.py`.
- `backend/app/api/student.py`: the import.
- `backend/app/schemas/student.py` or `schemas/response_loop.py` (where the
  student model lives) and `backend/app/schemas/report.py`: the lead name
  member, `extra="forbid"` kept.
- `backend/app/services/reporting.py`: the lead name on the report payload.
- The import sweep (`invariant`-marked): the new module named with the
  allowance `response_loop.py` had. The test author writes this edit red
  before the move.
- `frontend/src/routes/student/StudentResults.tsx`, the instructor report
  header component, their tests and copy: the name in the header.
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated.
- SPEC §13: the new module.
- ADR 0197: the line pointing at SPEC §5.4's ruling 9.

## Reuse, do not rewrite

E9-03's door; every function moved, moved rather than rewritten.

## Done when

1. **The move changes nothing.** The commit that moves the student read
   changes no test file except the sweeps' module lists, and the whole suite
   is green on it.
2. **The sweeps reach the new module.** The import sweep names
   `services/student_results.py` with the allowance `response_loop.py` had;
   a planted import of `visible_cards` into the new module goes red, and the
   allowed imports stay green. `response_loop.py` no longer appears in the
   sweep's student list if it no longer holds the student read.
3. **The lead is named.** A student of a section whose course has a lead sees
   the lead's name in the results payload in every state, `awaiting`
   included (a staff name is not a figure about the week); the instructor of
   that section sees it on the report.
4. **No lead, no name.** A course with no lead carries no lead name in either
   payload, and the header shows none (a page test).
5. **No other section's lead.** A student enrolled in section A gets A's
   course's lead only, never the lead of a course they are not in, tested
   with two courses and two leads.
6. **The records match.** SPEC §13 draws the new module; ADR 0197 gains its
   line; comments naming a ticket in the moved code are rewritten.

## Shares files with

- `services/response_loop.py`: 03, 07 and 09 (this move is the largest
  conflict; whoever merges second re-applies its change on the moved code).
- `services/reporting.py`: 09.
- `schemas/report.py`: 09.
- `openapi.json`, `wire.gen.ts`: 04 to 07 and 09.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 22, 53 and 60.

## Known traps

- **Entry 60.** A move that imports names into a module that already binds
  them is silent; run every caller's suite.
- **Entry 53.** The import sweep reads direct imports only; a re-export from
  `response_loop.py` would pass it.

## Not in this ticket

- The leadership pages' names (07, 11).
- Changing the student read's behaviour.
