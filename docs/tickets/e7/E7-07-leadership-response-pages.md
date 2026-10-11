# E7-07 — The leadership response pages

**ID:** E7-07
**Branch:** `e7/leadership-response-pages`
**Depends on:** E7-03 (the leadership routes), E7-05 (the composer)
**Lane:** light
**Size:** M
**Security-relevant:** the pages through which a lead changes what students
see across their courses and writes to a section's students. A defect here
offers a control the server would refuse, or shows a chair a switch they may
not use.

## Context

Three leadership pages over 03's routes, in the LeadershipRollup template.

- **The policy page.** For each prefix of the reader's courses, a `PolicyToggle`
  (§7.6) between encouraged and required. A Lead Faculty member's toggle covers
  the courses they lead in that prefix (ruling 1). A chair sees a toggle for the
  department's courses with no lead (ruling 5), and for a course with a lead
  sees the setting read-only, attributed by role ("set by the course's Lead
  Faculty"); no name until E9. The page says plainly that a change applies from
  the next week's report, not to a week already open (ruling 6).
- **Responses owed.** The section-weeks in the reader's courses whose required
  response is 48 hours or more past report open (§5.6 rule 4), each with the
  section label, the course week, and, past 96 hours, a way into the on-behalf
  composer. Calm empty state. No ranking, no instructor name, and no
  "delinquent" on the page.
- **On behalf.** 05's composer in its on-behalf mode: the section-week's stored
  summaries and ratings (no comments), the draft and the check, and publish
  under the reader's own name and role, with an as-students-see-it card that
  shows that attribution. It reuses 05's `InstructorResponse` and 06's
  `ResponseCard`, and forks neither.

If a `process/` pull request has added `@axe-core/playwright` before this
ticket is built, the leadership drive runs an axe scan on these pages and on
the moderation pages and fails on a violation. If not, this ticket does not add
it.

Read first: SPEC §5.3, §5.5, §5.6 and §7.6; `docs/DESIGN_BRIEF.md`;
`design/tokens.css`; the LeadershipRollup design and its PolicyToggle and
AttentionList primitives; `frontend/src/routes/leadership/ReviewQueue.tsx`,
which is the pattern for a page over the reader's own grant.

## Owns

- `frontend/src/routes/leadership/`: the three pages, and links to them from the
  leadership landing.
- `frontend/src/components/PolicyToggle.tsx` (new).
- `frontend/src/components/InstructorResponse.tsx`: the on-behalf mode only.
- `frontend/src/api/leadership.ts`: the new calls.
- `frontend/src/router.tsx`: the three routes.
- `frontend/src/copy/`: the pages' words.
- A leadership e2e drive of its own (not `leadership-moderation.spec.ts`, which
  08 owns): a lead sets required, sees a section owed, publishes on behalf; a
  chair sees a led course read-only.

## Done when

1. **The toggle follows the rulings.** A lead's toggle changes only their own
   courses in the prefix; a chair's read-only row has no control and names the
   setter's role; the page states when a change takes effect.
2. **The owed list matches the predicate.** On the running stack, a section owed
   for 48 hours appears and one at 47 hours does not, with the clock moved by
   the `/dev` clock routes from the seeded calendar, not a pinned date.
3. **On behalf reads no comments.** The on-behalf page shows summaries and
   ratings and no comment text; a planted distinctive comment is absent from
   the rendered page.
4. **Attribution is honest.** The as-students-see-it card on the on-behalf page
   shows the reader's name and role, never the instructor's.
5. **Refusals render as refusals.** A 404 from an on-behalf route (a taught
   section, a sibling course) shows the not-found state and nothing of the
   section.
6. **Keyboard and screen reader basics hold**, and every new string is in the
   copy inventory.

## Shares files with

- `frontend/src/router.tsx`: 06 before.
- `frontend/src/api/leadership.ts`: 08 before.
- `frontend/src/components/InstructorResponse.tsx`: 05 before.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 18, 28 and 58.

## Known traps

- **Entry 58.** Verify the drive through the pages as served, not through the
  seeder's own record of what it wrote.
- **The vocabulary.** §4.1 item 4 and §5.6 rule out ranking and blame. Say
  "response owed", not "delinquent" or "late".

## Not in this ticket

- Any backend change.
- Instructor names on these pages, and the dean's, assistant dean's and vice
  president's views (E9).
