# E8-01 — The student's week under the hold

**ID:** E8-01
**Branch:** `e8/students-week-under-the-hold`
**Depends on:** none
**Lane:** heavy
**Why this lane:** it adds invariant-marked tests (§4.1 item 3 for students,
and the hold over the new figures and comments), extends two invariant-marked
sweeps (the student-path import sweep and the student payload-schema sweep),
and moves a surface in the invariant-marked copy inventory. A migration on
`role_assignment`, if its `EXPLAIN` asks for one, touches an identity table.
**Size:** L
**Security-relevant:** the first read that hands students what their
classmates wrote and how they rated the week. A defect here shows a held
week's figures or comments, shows a comment that was flagged, excluded or sent
to Care, shows a small stream's comments, or places a released comment in its
week.

## Context

E7's results route (`GET /student/sections/{section_id}/weeks/{course_week}/results`,
ADR 0193) answers a week's state and response only. SPEC §5.4 asks for the
rest: the two-stream trend, the distributions, the workload median and the
published comments grouped by stream, with the `small-N` state. This ticket
adds them to the same payload, under the same hold, and reads the hold through
`services/response_loop.py`'s own functions (`policy_of_record`,
`first_response`, `latest_response`, `week_state`, `_state_and_response` and
the set-based `_week_clocks`), never a copy.

What the payload gains:

- **`course_label`**, in every state, through `section_codes.course_label`
  (ruling 2).
- **`streams`**: for each of the instructor and course streams, the trend over
  the section's published weeks, this week's rating distribution, and either
  the comments or the small-N state. Built by a new `reporting.student_streams`,
  copying the pattern of `reporting.on_behalf_streams` and reusing
  `_published_weeks`, `_rating_counts`, `_mean_of`, `_held_streams`,
  `n_threshold` and `_course_label`.
- **`workload_median`** only, through `_workload` (§5.4 lists the median).
- **`released`**: the from-earlier-weeks group, by ruling 1.

**What the hold means for each piece.** In an `awaiting` week the payload
carries the course label, the state and the participation member 03 adds, and
nothing else: no figure, no comment, no small-N state, no batch. The trend on
any page leaves out every `awaiting` week, so week 4's page never carries week
3's held mean. The release group shows only on the latest published week's
page, only while no published week of the section is `awaiting`, and only
batches cut before that week's report opened (the cut runs at 02:40, before
the 06:00 opening).

**Comments a student may read.** Two new functions in
`services/report_comments.py`, `student_comments` and
`student_released_comments`, filter `visible_cards` and `released_cards`
(which read `report_comment` v004) to the `published` and `kept` statuses. They
return text and stream only, with no `answer_id`, no status and no time. They
take a section, a week or term, and a stream, and no parameter that could name
a person. This is the carried "note for E8" in `../e7/carried-from-e6.md`.

**The import sweep.** The four student-facing modules still import neither
`report_comments` nor `moderation`. `services/response_loop.py` becomes the one
module that reaches the student's comment read, and the sweep names it: it may
import the two student functions from `report_comments` and nothing else from
that module, and nothing from `moderation`.

Read first: SPEC §4, §4.1, §5.2 and §5.4; ADRs 0146, 0152, 0184, 0187, 0191
and 0193; `services/response_loop.py`, `services/reporting.py`
(`on_behalf_streams` is the pattern) and `services/report_comments.py`; the two
sweeps named below.

## Owns

- `backend/app/services/response_loop.py`: `student_week_results` gains the
  new members under the hold. The policy-of-record rule is written once
  (below).
- `backend/app/services/reporting.py`: `student_streams` (new function).
- `backend/app/services/report_comments.py`: `student_comments` and
  `student_released_comments` (new functions).
- `backend/app/schemas/response_loop.py`: `StudentWeekResults` and its new
  nested models, each with `extra="forbid"`.
- `tests/unit/test_the_report_comment_service_names_nothing_a_student_path_can_reach.py`:
  `response_loop` named with its allowance, the signature equality extended to
  the two student reads, and the docstring sentence that says the student
  assertion is E8's rewritten to name the tests that now make it.
- `tests/unit/test_the_student_payload_schema_carries_nothing_of_a_benchmark.py`:
  reaches the student models in `app.schemas.response_loop`.
- `tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`:
  `student_results` moves from `SURFACES_WITH_NO_CONFIDENTIALITY_LINE` to the
  governed surfaces.
- `frontend/src/copy/studentResults.ts`: the confidentiality line's key only.
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated.
- ADR **0197** (the student's read under the hold: the filter over v004, the
  release rule, the trend without held weeks, and why there is no new view).
- ADR 0191: the `role_assignment` `EXPLAIN`, recorded.
- M1, only if the `EXPLAIN` asks for it.

## Reuse, do not rewrite

`policy_of_record`, `first_response`, `latest_response`, `week_state`,
`_state_and_response` and `_week_clocks` in `services/response_loop.py`;
`_published_weeks`, `_rating_counts`, `_mean_of`, `_workload`, `_held_streams`,
`n_threshold` and `_course_label` in `services/reporting.py`; `visible_cards`
and `released_cards` in `services/report_comments.py`; `survey_read._live_enrollments`;
`section_codes.course_label`.

## Done when

1. **A held week serves nothing about the week.** In a required-mode
   section-week with no response, the payload carries the course label and the
   state and no figure, no distribution, no workload, no trend point, no
   comment, no small-N state and no batch. Asserted against the forbidden
   members, beside a passing twin in one world: the same week after a publish
   carries each of them. Marked `invariant`.
2. **A held week reaches no other page.** With week 3 `awaiting` and week 4
   released, week 4's trend has no point for week 3 in either stream, and
   neither week's page serves a batch. After week 3 is published, week 4's
   trend has the point. Read in that order, as a student meets it (MISTAKES
   entry 51). Marked `invariant`.
3. **Release batches follow ruling 1.** The group appears only on the latest
   published week's page; never on an earlier week's page; never while any
   published week of the section is `awaiting`; and it holds only batches cut
   before the latest week's report opened, tested one second either side of
   the opening. A comment in a batch never appears under its own week. Marked
   `invariant`.
4. **Only published and kept comments reach a student.** In one shown stream,
   a flagged-collapsed comment, an excluded comment and a comment with a Care
   verdict (threat or self-harm) are absent, and a kept comment and a
   published comment are present. The same holds in a release batch. The read
   goes through v004, and no student read queries `answer` itself. Marked
   `invariant`.
5. **§4.1 item 3, for students.** In a week where a stream has fewer distinct
   commenters than the threshold, the payload carries no comment text for that
   stream and carries its small-N state; the other stream at or above the
   threshold carries its comments. Tested at the threshold and one commenter
   below it. Marked `invariant`.
6. **Nothing identifies a comment or its week.** No comment in the payload
   carries an `answer_id`, a status, a time or a week. Comment order is
   randomized as on the instructor's report.
7. **Figures are the student's own section only, and never a benchmark.** The
   payload-schema sweep reaches every student model in
   `app.schemas.response_loop` and finds no benchmark, comparison, university
   or cohort member, with its controls. The student-route sweep still reaches
   the results route and finds no comparison-set or university figure. The
   payload has no response count, no classmate count, no response rate and no
   workload mean (ruling 6, §5.4).
8. **The import sweep names the one caller.** The four student-facing modules
   still import neither `report_comments` nor `moderation`.
   `services/response_loop.py` is in the sweep, allowed exactly
   `student_comments` and `student_released_comments` from `report_comments`
   and nothing from `moderation`. Planted imports of `visible_cards` and of
   `moderation` into `response_loop` each go red; the two allowed imports stay
   green. The signature equality covers both student reads and refuses a
   parameter that could name a person.
9. **The course is named in every state,** `awaiting` included, from
   `section_codes.course_label`.
10. **The surface owes its line.** `student_results` moves out of
    `SURFACES_WITH_NO_CONFIDENTIALITY_LINE` into the governed surfaces, and the
    copy inventory requires exactly one confidentiality line on it, the new key.
11. **The role-assignment reads are measured.** `EXPLAIN` of the student
    path's reads of `role_assignment` by section, at about twenty thousand rows,
    is recorded in ADR 0191. If it shows a sequential scan that matters, M1 adds
    a partial index on `section_id` where the role is instructor.
12. **The policy-of-record rule is written once.** `policy_of_record` and the
    set-based `_week_clocks` share one statement of the rule, or ADR 0197 argues
    the second copy. The existing hold and owed tests stay green unchanged.
13. **The records match.** ADR 0197 is written and indexed. Comments that name
    an E-ticket in the files this ticket edits are rewritten to say what the
    code does and cite an ADR or SPEC section.

## Shares files with

- `services/response_loop.py`, `schemas/response_loop.py`, `openapi.json`,
  `wire.gen.ts`: 03, in the same wave.
- `frontend/src/copy/studentResults.ts`: 03 and 02.
- `docs/adr/README.md`: 03 and 04.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 22, 35, 50, 51, 53 and 58.

## Known traps

- **Entry 51.** The hold is a property of the sequence of pages. A week that
  is held this Monday and released next Monday must not leave a trace on
  another week's page in between.
- **Entry 3.** Each absence test needs its present twin in the same world, or
  an empty payload passes it.
- **Entry 53.** The import sweep reads direct imports only. Say so in its
  docstring as a disclosed limit; the behavioural tests above are the proof.
- **Entry 22.** Moving `student_results` in the copy inventory reds that test
  until the line's key exists. Add both in one commit.
- **The calendar bomb.** Pin the clock; ADR 0184's 06:00 Monday opening and the
  02:40 cut both apply.

## Not in this ticket

- The page (02).
- The participation score and the landing card (03).
- A stored summary for students (E9 at the earliest, by the carried rule).
- The Lead Faculty name in the header (E9).
- The chair's department walk in `services/authz.py`.
