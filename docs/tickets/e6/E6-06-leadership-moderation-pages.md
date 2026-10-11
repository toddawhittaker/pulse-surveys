# E6-06 — The leadership queue and log pages

**ID:** E6-06
**Branch:** `e6/leadership-moderation-pages`
**Depends on:** E6-04 (the card actions it reuses) and E6-05 (the routes)
**Lane:** light
**Size:** M
**Security-relevant:** low. The pages render E6-05's payloads and add nothing
to them.

## Context

E6-05 serves the review queue and the exclusion log to leadership. This ticket
builds the two pages a Lead Faculty member, a chair and those above reach from
the leadership landing:

- **The review queue.** Each item shows the comment's text and its section,
  with Exclude and Keep. No week, no time, no count. Excluding needs no reason,
  because every queued comment carries a harmful flag.
- **The exclusion log.** One row per decision: the section, the decider's role,
  AI-flagged or the reason, the date, and the excerpt when E6-05 sends one.
  `design/ExclusionLogRow.dc.html` is the row's mockup.

Read first: `docs/DESIGN_BRIEF.md`, `design/tokens.css`, SPEC §5.2, §5.5 and
§7.6, `design/ExclusionLogRow.dc.html`, ADR 0190, and
`frontend/src/routes/leadership/ComparisonSets.tsx`, the pattern for a
leadership page.

## Owns

- `frontend/src/routes/leadership/ReviewQueue.tsx` and `ExclusionLog.tsx`
  (new), with their tests and fixtures.
- `frontend/src/components/ExclusionLogRow.tsx` (new).
- `frontend/src/router.tsx` and the leadership landing links.
- `frontend/src/api/leadership.ts` (the queue, decision and log calls).
- `frontend/src/copy/leadershipModerationCopy.ts` (new), beside
  `leadershipComparisonSetCopy.ts`.
- An e2e drive: a Lead Faculty seat excludes one queued comment and finds it in
  the log.

## Reuse, do not rewrite

E6-04's `CommentCard` actions, not a fork of them. `frontend/src/lib/http.ts`.
The generated types in `api/wire.gen.ts`. The leadership pages' CSRF handling.

## Done when

1. **The queue page.** It lists the queued comments with text and section only,
   and Exclude and Keep act and remove the item (vitest and the e2e drive).
2. **The log page.** Each row shows the section, the role, flagged or the
   reason, the date, and the excerpt only when sent; a row with no excerpt says
   so plainly (vitest, against the mockup).
3. **No name, no week.** Neither page shows a staff name, a week or a time of
   day (vitest).
4. **The landing.** A Lead Faculty member and a chair reach both pages from
   the leadership landing; an instructor-only seat has no link to them.
5. **Accessibility.** The e2e drive runs the axe check the instructor report
   drive already runs (`tests/e2e/instructor-report.spec.ts`) over both pages,
   and every control is reachable by keyboard.
6. **The copy inventory holds.** The §4.1 items 4 and 5 sweep passes over every
   new string; the log counts decisions and never ranks sections or people.

## Shares files with

- `CommentCard.tsx`: E6-04 before this.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 18.

## Known traps

- **Entry 3.** "No week is shown" passes on an empty page. Assert the rows
  rendered first.
- **Entry 18.** When the e2e drive and vitest disagree, check the built bundle.
- **§4.1 item 4.** A log sorted by count or grouped by instructor is a ranking.
  Sort by date or by section label.

## Out of scope

- Any backend change. A missing member goes back to E6-05's owner as a
  finding.
- The Care queue page (E10).
