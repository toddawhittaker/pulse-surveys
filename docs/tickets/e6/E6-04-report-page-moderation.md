# E6-04 — Moderation on the instructor report page

**ID:** E6-04
**Branch:** `e6/report-page-moderation`
**Depends on:** E6-03 (the payload members and the decision routes)
**Lane:** light
**Size:** M
**Security-relevant:** low. The page renders what E6-03's payload allows. It
must not add a date, a count or a category of its own.

## Context

E6-03 puts the comment handle, the flag class and "decided by you" on the
instructor payload, and adds the decision routes. It carries no participation
note: ruling 6 dropped it, so this page renders no count of held comments.
This ticket builds the page side of SPEC §5.2's lifecycle:

- A flagged-collapsed card shows its chip and reason, and offers Exclude and
  "Keep for students".
- An excluded comment keeps its text visible to the instructor, muted, above
  the exclusion notice, with Undo.
- A kept comment shows a quiet logged-decision line, with Undo.
- Excluding an unflagged comment asks for a reason first.

Three carried items land here, because this is the next ticket to open the
report's interface:

- **Two older accessibility patterns** (`carried-from-e5.md`). The trend
  charts' data tables are visually hidden, so a sighted reader who cannot read
  the chart has no table. Text inputs are bordered in `--hairline`, about
  1.30:1 on paper, under WCAG 2.2 SC 1.4.11's 3:1. The reason prompt is a new
  text input, so the boundary fix lands before it.
- **The design mockups show one notice per week and a response count**
  (`carried-from-e5.md`). `design/InstructorMondayReport.dc.html`,
  `design/SmallNNotice.dc.html` and `design/AdminConsole.dc.html` still show one
  notice per week and say "responses".

Read first: `docs/DESIGN_BRIEF.md`, `design/tokens.css`, SPEC §5.2 and §7.6,
`design/CommentCard.dc.html`, ADRs 0182 and 0189, and E6-03's payload.

## Owns

- `frontend/src/components/CommentCard.tsx` (the flagged, excluded and kept
  variants, the actions, Undo and the reason prompt) and its tests.
- `frontend/src/components/CommentGroup.tsx`.
- `frontend/src/routes/instructor/InstructorMondayReport.tsx`, its fixtures and
  its stylesheet.
- `frontend/src/api/instructor.ts` (the decision calls).
- `frontend/src/copy/instructorReportCommentCopy.ts`.
- `design/tokens.css`, only for the input boundary token, and the stylesheet
  test that pins it, the way `reportContrastTokens.test.ts` pins the report's
  colours.
- The trend chart table's visibility to sighted readers, or a record arguing
  the hidden table is enough.
- `design/InstructorMondayReport.dc.html`, `design/SmallNNotice.dc.html`,
  `design/AdminConsole.dc.html`.
- The e2e drive of the report page, extended to one decision and its Undo.

## Reuse, do not rewrite

The existing `CommentCard` variants and `CommentGroup`; `frontend/src/lib/http.ts`
for the calls; the generated types in `api/wire.gen.ts` (never a hand-written
copy); the CSRF token handling the leadership pages already use.

## Done when

1. **The lifecycle on the page.** A flagged card offers Exclude and "Keep for
   students". Excluding mutes the text above the exclusion notice; keeping
   shows the logged-decision line; Undo on each restores the earlier card
   (vitest, and one e2e decision with its Undo).
2. **The reason prompt.** Excluding an unflagged comment asks for a reason and
   does not send without one; the server's refusal sentence shows inline.
3. **No date and no name.** No card shows a date, a time or a decider's name.
   "Decided by you" is the only attribution (vitest).
4. **Dropped (ruling 6).** This was the participation note; there is no note
   to render. The number is kept so the criteria below keep their numbers.
5. **Input boundaries reach 3:1.** Every text input's boundary measures at
   least 3:1 against its background, pinned by a stylesheet test.
6. **The chart table.** A sighted reader can open the trend chart's data
   table, or a record argues why the hidden table is enough.
7. **The mockups.** The three mockups show per-stream notices and say
   "commenters", not "responses".
8. **The copy inventory holds.** The §4.1 items 4 and 5 sweep passes over every
   new string.

## Shares files with

- `CommentCard.tsx`: E6-06 reuses its actions after this merges.
- `api/instructor.ts`: E6-03 before this.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 18.

## Known traps

- **Entry 18.** Check the built bundle, not only the source, when an e2e drive
  disagrees with vitest.
- **Entry 3.** A test that "no date is shown" passes on an empty page. Assert
  the card rendered first.
- **A light ticket can re-lane.** If a change reds an invariant-marked test,
  the ticket becomes heavy and the PR says so.

## Out of scope

- The leadership pages (06).
- Any backend change. A missing payload member goes back to 03's owner as a
  finding, not into this diff.
