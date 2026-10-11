# E7-03 — Publish, policy and on-behalf

**ID:** E7-03
**Branch:** `e7/publish-policy-on-behalf`
**Depends on:** E7-02 (the gate and the writer), E7-04 (the draft and check
tasks and the gather)
**Lane:** heavy
**Why this lane:** it gives a Lead Faculty member (or a chair acting as lead) a
new read of one section-week's stored summaries and ratings, and its
sibling-isolation, taught-section and withheld-summary tests are marked
`invariant`.
**Size:** L
**Security-relevant:** the first write a person makes that students read, and
the first leadership read of a section's summaries. A defect here lets a lead
read a sibling lead's section, lets someone edit another person's response, or
hands a lead a summary carrying a comment the instructor excluded.

## Context

**The instructor's routes.** Publish a response for one of their sections and a
published week, and edit it. One response per section-week (ruling 3): a
publish when a response already exists is refused, and an edit by anyone but
the first publisher is refused. Both call 02's writer.

**The policy routes (rulings 1 and 5).** A Lead Faculty member reads and sets
the policy for each prefix of the courses they lead. A chair reads and sets it
for the courses in their department that have no lead. For a course that has a
lead, the chair reads the setting with attribution by role ("set by the course's
Lead Faculty") and cannot change it; the setter's name waits for E9. Each change
appends a `response_policy` row. The assistant dean, the dean and the vice
president are refused until E9, as the review queue refuses them (ADR 0190).

**The predicates (ruling 2, ruling 10).** For a section-week whose policy of
record (02) is required and which has no response: owed from report open + 48
hours (SPEC §5.6 rule 4), and on-behalf enabled from report open + 96 hours.
Both are functions in `services/response_loop.py`, computed on read; E9's
attention list will call the first.

**The responses-owed read.** For a lead or a chair acting as lead, the
section-weeks in their own courses that are owed now, with the section label
and the course week, and no instructor name (E9).

**On behalf (ruling 9).** Past 96 hours, the responsible lead (or the chair
acting as lead) reads that section-week's stored summaries and rating
distributions, as the section's own report shows them, and no comment text.
They may run the draft and the check (04's tasks, over the same gather) and
publish under their own name and role through 02's writer. Two rules close this
reader's view:

- **No taught section.** The on-behalf read, draft, check and publish refuse a
  section the reader teaches or has taught (`taught_or_once_taught_section_ids`),
  with the same 404 as a section outside their courses (E6's ruling 7).
- **No summary written before the week's latest exclusion.** A stored summary
  whose `generated_at` is not strictly later than the latest decision in that
  section-week that removes a comment from the shown set (an exclusion, or the
  undo of a keep) may carry that comment, so this reader is not shown it
  and the draft gather for this reader leaves it out. This closes the carried
  entry "A stored summary can carry a comment excluded after it was written"
  for this reader.

Read first: SPEC §2.1, §4.1, §5.3, §5.5 and §5.6; ADRs 0153, 0184, 0189, 0190,
0191, 0192 and 0193; `carried-from-e6.md`'s summary entry; and `api/leadership.py`'s
review-queue routes, which are the pattern for a door scoped to the reader's
own grant.

## Owns

- `backend/app/services/response_loop.py`: the publish and edit doors, the
  policy read and write, the two predicates, the owed read, and the on-behalf
  doors.
- `backend/app/services/reporting.py`: the filter that leaves out a summary
  written before the week's latest exclusion, beside 04's gather.
- `backend/app/api/instructor.py`: publish and edit, behind
  `csrf_verified_instructor`.
- `backend/app/api/leadership.py`: the policy, owed and on-behalf routes, behind
  `require_leadership` and `csrf_verified_leadership`.
- `backend/app/schemas/response_loop.py` and `backend/app/copy/response_loop.py`:
  the new payloads and refusals.
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated.
- SPEC §5.3, only if a built fact differs from what it now says.
- ADR **0194** (the doors, the policy scope and its two-hat case, the predicates,
  the on-behalf view and the summary filter).

## Reuse, do not rewrite

`lead_review_courses`, `taught_or_once_taught_section_ids`,
`teaching_instructor_assigned` in `services/authz.py`; `_readable_section`,
`_stored_summaries`, `_rating_counts`, `_response_counts`, `_course_label` and
`report_opens_at` in `services/reporting.py`; `section_week_moderated` in
`services/report_comments.py`; 02's gate and writer; 04's tasks and gather;
`person_of` and the CSRF gates in `api/deps.py`.

## Done when

1. **Publish and edit.** An instructor publishes a response for a published
   week and edits it; each is one appended row naming them and their role. A
   second publish is refused. An edit by anyone but the first publisher is
   refused, including the lead after an on-behalf response the instructor tries
   to edit, and the other way round. Each refusal writes no row.
2. **An edit never re-holds.** After an edit in a required week, the student
   state (02) stays released.
3. **Policy scope (rulings 1 and 5).** A lead's switch for a prefix holds the
   courses in it they lead and changes nothing for another lead's course in the
   same prefix. A chair's switch holds the department's unled courses in that
   prefix. A chair's attempt to set the policy of a course with a lead is
   refused and writes no row, and the chair can read that course's setting.
4. **A sibling lead's setting reaches nobody else.** Sibling lead B sets prefix
   P to required. Lead A's policy read for P still answers encouraged, carries
   no attribution, and is byte-identical to the read before B's change. A
   chair's read of a course in P with a lead shows only that course's own
   lead's setting. Marked `invariant`.
5. **The policy of record is the policy in force at report open.** A toggle
   after report open changes nothing for that week, through these routes, in
   both directions.
6. **The clocks start at report open (ruling 2).** Owed and on-behalf are each
   false one second before report open + 48h and + 96h, and true at it, with
   the clock pinned. An encouraged week and a published week are never owed.
7. **On behalf only past 96 hours.** An on-behalf read, draft, check or publish
   before + 96h is refused and writes no row.
8. **No taught section.** For a lead who also teaches a section of a course
   they lead, every on-behalf route refuses that section with the same 404 as a
   section of a sibling lead's course, and writes no row; the course's other
   sections are served. The same holds for a teaching grant the roster ended.
   Marked `invariant`.
9. **No sibling course.** No route in this ticket reads, sets, lists or
   publishes for a course outside the reader's own `lead_review_courses`. Each
   refusal is the same 404 and names nothing of the section. The refusal for a
   sibling's section is byte-identical whether that week is encouraged or
   required, before or after + 96h, and answered or not. Marked `invariant`.
10. **No summary written before the week's latest exclusion.** A summary is
    withheld when any decision in that section-week that removes a comment
    from the shown set (an exclusion, or the undo of a keep) is not strictly
    earlier than the summary's `generated_at`. The instructor excludes a
    comment after the week's summary was written; the lead's on-behalf read
    carries no summary for that stream, and the draft gather for the lead
    carries none either. The undo of a keep withholds the same way. A tie
    between the decision and `generated_at` withholds, and is tested. A
    summary written strictly after every such decision is served. Marked
    `invariant`.
11. **No comment text up-chain.** The on-behalf payload carries no comment text
    at any threshold; a planted distinctive comment is absent from every
    on-behalf response body. Marked `invariant`.
12. **The gates run at dispatch.** Each write with no CSRF token, or from
    another origin, is refused over HTTP against the built application, beside
    the same write with the token (MISTAKES entry 47).
13. **The records match.** ADR 0194 is written and indexed.

## Shares files with

- `services/response_loop.py`, `schemas/response_loop.py`, `copy/response_loop.py`:
  02 before.
- `api/instructor.py`, `services/reporting.py`: 04 before.
- `api/leadership.py`: 08 before.
- `openapi.json`, `wire.gen.ts`, `docs/adr/README.md`: 02 before.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 22, 29, 35, 47, 50, 51 and 53.

## Known traps

- **Entry 53.** Test the taught-section refusal one level out: a section the
  lead taught last term, a two-hat person who chairs and leads.
- **Entry 51.** The summary filter depends on the order of two writes. Assert
  what two reads either side of the exclusion reveal.
- **The calendar bomb.** Pin the clock for every predicate test.

## Not in this ticket

- The pages (05, 07).
- The draft and check prompts and the instructor's draft routes (04).
- The assistant dean's, the dean's and the vice president's views (E9).
