# E8-02 — The results page

**ID:** E8-02
**Branch:** `e8/results-page`
**Depends on:** E8-01 (the payload and the regenerated wire types)
**Lane:** light
**Why this lane:** frontend only. It renders what 01 serves and decides
nothing about what a student may read.
**Size:** M
**Security-relevant:** the page a student reads. A defect here shows a
benchmark line, teases a held week, or shows the small-N notice with a count.

## Context

E7-06 built StudentResults as a shell: the closed door, or the response card
with its attribution. SPEC §5.4 asks for the whole page, and 01 now serves it.
The order on the page, top to bottom:

1. **The course heading,** in every state (ruling 2).
2. **The response,** leading the page (the page is a reply, not a dashboard).
   The four states render as E7-06 built them.
3. **The trend:** a new `TrendDuo` component, which §7.6 names for the
   two-stream case with no benchmark. It reuses `PulseTrendChart` and draws
   one line per stream and no comparison or university line.
4. **This week's distributions,** one `RatingHistogram` per stream, with no
   benchmark.
5. **The workload median.**
6. **The comments,** in two `CommentGroup`s under "About the instructor" and
   "About the course", using `CommentCard`'s default variant. A stream in its
   small-N state shows `SmallNNotice` in its student audience in place of its
   comments: it frames suppression as protecting the student, says comments
   appear once enough classmates comment, and states no count.
7. **The from-earlier-weeks group,** when 01 serves one, with no week named.
8. **The confidentiality line,** once, from the key 01 added.

The participation block that 03 adds stays where 03 put it.

In `awaiting` the page shows the course heading, the closed door and the
participation block, and nothing from items 3 to 7. There is no classmate
count anywhere (ruling 6).

Read first: SPEC §4.1, §5.4 and §7.6; `docs/DESIGN_BRIEF.md`;
`design/tokens.css`; `design/StudentResults.dc.html` and
`design/SmallNNotice.dc.html`; E7-06's ticket.

## Owns

- `frontend/src/routes/student/StudentResults.tsx` and its test.
- `frontend/src/components/TrendDuo.tsx` (new) and its test.
- `frontend/src/components/SmallNNotice.tsx`: the student audience.
- `frontend/src/api/student.ts`: the results call's new members.
- `frontend/src/copy/studentResults.ts`: the page's new words.
- `design/StudentResults.dc.html`: stops passing `responded` and `total` to
  the small-N notice, and drops the classmate-count line.
- `tests/e2e/student-results.spec.ts`: the new page, and re-runnable on one
  stack.
- If the `process/` pull request has added `@axe-core/playwright`: an axe scan
  in `student-results.spec.ts` on every page it reaches.

## Reuse, do not rewrite

`ResponseCard`, `RatingHistogram`, `CommentGroup`, `CommentCard`,
`SmallNNotice`, `WeekNav`, `StateNotice`, `PulseTrendChart`. Add a variant or
an audience; never fork a component.

## Done when

1. **The page renders in order,** as listed above, for `published`,
   `on-behalf` and `unanswered`, from a mocked route and on the running stack.
2. **The closed door teases nothing.** In `awaiting`, the page holds the course
   heading, the closed door and the participation block, and no trend, no
   histogram, no workload, no comment, no small-N notice and no batch. Asserted
   against the rendered page.
3. **No benchmark reaches the page.** TrendDuo draws exactly two lines, one per
   stream, and no comparison or university line, in its chart, its text, its
   tooltips and its aria labels.
4. **Small-N is per stream.** With the instructor stream small and the course
   stream shown, the first group shows the student `SmallNNotice` with no
   number and the second shows its comments.
5. **The confidentiality line appears once** on the page, in every state that
   shows student data, with no shield or lock icon, and the copy inventory
   test passes.
6. **Comments show no time and no status,** and the from-earlier-weeks group
   names no week.
7. **The mockup states no count.** `design/StudentResults.dc.html` passes
   neither `responded` nor `total`, and shows no classmate-count line.
8. **The drive runs twice on one stack.** `student-results.spec.ts` covers the
   held page and the released page, and runs green twice in a row on one stack
   without a reset, leaving no rows a rerun trips over.
9. **Keyboard and screen reader basics hold.** The trend has a data-table
   equivalent, focus is visible, motion stops under reduced motion, and every
   new string is in the copy inventory and passes the student-copy rules. If
   the axe package has landed, the drive's scan finds no violation.
10. **The records match.** Comments that name an E-ticket in the files this
    ticket edits are rewritten to say what the code does.

## Shares files with

- `frontend/src/copy/studentResults.ts`: 01 and 03 before.
- `StudentResults.tsx`, its test, and `frontend/src/api/student.ts`: 03 before.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 18, 31 and 58.

## Known traps

- **The student-copy sweep.** A word like "average", "other sections" or
  "classmates responded" in a student string fails
  `test_the_shipped_copy_names_nothing_a_student_may_not_see.py`.
- **The calendar bomb.** The drive derives its dates from the seeded calendar;
  it pins no date.
- **Entry 31.** "Runs twice" means twice against a stack the first run left
  behind, not against a fresh one.

## Not in this ticket

- Any backend change. A gap in 01's payload goes back to 01's owner as a
  ticket pull request.
- The participation block and the landing card (03).
- `design/LeadershipRollup.dc.html` (E9).
- An AI summary on the page (none in §5.4).
