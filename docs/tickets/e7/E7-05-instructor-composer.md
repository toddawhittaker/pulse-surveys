# E7-05 — The instructor's composer

**ID:** E7-05
**Branch:** `e7/instructor-composer`
**Depends on:** E7-03 (publish and edit), E7-04 (draft and check), E7-06 (the
`ResponseCard` component)
**Lane:** light
**Size:** M
**Security-relevant:** the page where a response is written and published. A
defect here publishes without a person pressing publish, or shows a stale check
beside a changed draft.

## Context

SPEC §5.3 and the design's InstructorMondayReport: after reviewing the report,
the instructor writes a short response ("You said / we heard / here's what
changes"). The composer sits on the report page, below the comments.

- **Draft.** "Use draft" fills the editor from 04's draft route. The text stays
  editable and is never posted by the draft.
- **Check.** "Check draft with AI" runs 04's check route and quietly lists the
  unaddressed themes with their counts. It is never forced and never blocks
  publish. The result clears as soon as the draft text changes.
- **Publish.** Only a person pressing publish posts. After publishing, the page
  shows the as-students-see-it card (06's `ResponseCard`, instructor variant)
  with the instructor's name from 01's channel, and an Edit path. An edit
  publishes a new version through 03's edit route.
- **The hold banner.** In a required week with no response, a calm notice
  (`StateNotice`) says students will see this week's results once a response is
  published. No countdown, no blame.
- **Decisions on released comments.** SPEC §5.2 lets an instructor decide on a
  comment in a release batch, and the decision door already accepts one
  (ADR 0189). The "Comments from earlier weeks" list gains the same actions the
  week's comments have. This closes the carried entry "Released comments are
  read-only on the instructor page".
- **The reason bound, checked once.** A unit test reads
  `REASON_MAX_LENGTH` in `frontend/src/components/CommentCard.tsx` and
  `REASON_BOUND` in `backend/app/models/report.py` and fails when they differ.
  The response text bound from 01 gets the same test. This closes the carried
  entry "The reason bound is written twice".

If a `process/` pull request has added `@axe-core/playwright` before this
ticket is built, the report drive runs an axe scan on the composer and the
moderation cards and fails on a violation. If not, this ticket does not add it.

Read first: SPEC §5.2, §5.3 and §7.6; `docs/DESIGN_BRIEF.md`;
`design/tokens.css`; the InstructorMondayReport design and its ResponseCard and
AiPanel primitives; `frontend/src/components/AiPanel.tsx`.

## Owns

- `frontend/src/routes/instructor/`: the composer on the report page, and the
  released-comment actions.
- `frontend/src/components/InstructorResponse.tsx` (new, the composer, built so
  07 reuses it for on-behalf). It shows the published response with 06's
  `ResponseCard`, and does not fork it.
- `frontend/src/components/CommentCard.tsx`, as far as the released list needs.
- `frontend/src/api/instructor.ts`: the publish, edit, draft and check calls.
- `frontend/src/copy/`: the composer's and banner's words.
- The unit test that compares the two bounds.
- The instructor report e2e drive: draft, check, edit-clears-check, publish,
  as-students-see-it, edit.

## Done when

1. **Nothing posts without publish.** Using a draft, running a check and
   editing post nothing; only the publish button does, and a test proves the
   draft and check paths make no publish call.
2. **The check clears on edit.** After a check, changing one character removes
   the result; running it again shows a fresh one.
3. **As students see it.** After publish, the card shows the text and the
   instructor's name, and Edit opens the composer with the published text.
4. **The hold banner appears only in a required, unanswered week**, and is gone
   after publish.
5. **Released comments can be decided.** Keep, Exclude and Undo work on a
   released comment, with the same focus and announcement behaviour the week's
   cards have.
6. **The bounds agree.** The unit test fails when either constant changes alone.
7. **Keyboard and screen reader basics hold** for every new control, and every
   new string is in the copy inventory.

## Shares files with

- `frontend/src/components/ResponseCard.tsx`: 06 creates it; this ticket reuses
  it.
- `frontend/src/components/InstructorResponse.tsx`: 07 reuses it after this
  merges.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 18, 23 and 28.

## Known traps

- **The copy inventory.** A literal string in a component fails the inventory
  test; put every word in `frontend/src/copy/`.
- **Generated wire types.** Use the types in `wire.gen.ts`; a hand-written wire
  type in `api/` fails the sweep (ADR 0185).

## Not in this ticket

- The leadership pages (07) and the student page (06).
- Any backend change; a gap found here goes back to 03 or 04 as a ticket
  pull request.
