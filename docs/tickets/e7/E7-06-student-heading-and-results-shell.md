# E7-06 — The student's heading and results page

**ID:** E7-06
**Branch:** `e7/student-heading-and-results-shell`
**Depends on:** E7-02 (the results route; 01's name is on the survey payload)
**Lane:** light
**Size:** S
**Security-relevant:** the first student page that shows a staff name. A defect
here shows a name or a response from another section, or teases a held week.

## Context

Two student surfaces.

- **The survey heading names the professor.** The owner asked for this on
  2026-09-03 (`carried-requirements.md`). 01 puts the section's instructors'
  names on the survey payload; this ticket renders them in the heading area of
  StudentWeeklySurvey.
- **The results page, as a shell (ruling 8).** StudentResults for one of the
  student's sections and a published week, reading 02's route. Per SPEC §5.4 the
  response leads the page:
  - `awaiting`: a closed door. No countdown, no teased data, no blame.
  - `published`: the `ResponseCard` with the instructor's name.
  - `on-behalf`: the same card at the same weight, attributed honestly to the
    lead's name and role, with nothing implying discipline.
  - `unanswered`: a calm line that there is no response this week.

  Students page back through published weeks only (`WeekNav`). The aggregates,
  comments and small-N state are E8's; the page leaves room for them and shows
  none.

Read first: SPEC §4.1, §5.4 and §7.6; `docs/DESIGN_BRIEF.md`;
`design/tokens.css`; the StudentResults and StudentWeeklySurvey designs.

## Owns

- `frontend/src/routes/student/`: the heading change and the results page.
- `frontend/src/components/ResponseCard.tsx` (new), with its instructor and
  on-behalf variants (§7.6). This ticket builds it because it merges first; 05
  and 07 reuse it.
- `frontend/src/api/student.ts`: the results call.
- `frontend/src/router.tsx`: the results route.
- `frontend/src/copy/`: the page's words.
- An e2e case: a student reads the instructor's name in the survey heading, the
  closed door in a held week, and the card after publish.

## Done when

1. **The heading names the professor** for each of the student's sections, and
   for a section with no instructor shows no name and no placeholder.
2. **Each state renders.** `awaiting`, `published`, `on-behalf` and `unanswered`
   each render as described, from a mocked route and on the running stack.
3. **The closed door teases nothing.** In `awaiting`, the page contains no
   number, date, countdown, name or response text.
4. **On behalf is honest.** The card names the lead and their role and never the
   instructor.
5. **Keyboard and screen reader basics hold**, and every new string is in the
   copy inventory and passes the student-copy rules.

## Shares files with

- `frontend/src/router.tsx`: 07 after this merges.
- `frontend/src/components/ResponseCard.tsx`: 05 and 07 reuse it after this
  merges; neither forks it.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 18 and 58.

## Known traps

- **The student-copy sweep.** A word like "average" or "other sections" in a
  student string fails `test_the_shipped_copy_names_nothing_a_student_may_not_see.py`.
- **The calendar bomb.** The e2e case derives its dates from the seeded
  calendar; it pins no date.

## Not in this ticket

- Aggregates, comments, the small-N notice and next-launch surfacing (E8).
- Any backend change.
