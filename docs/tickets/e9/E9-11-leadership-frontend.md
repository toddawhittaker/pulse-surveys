# E9-11 — The leadership frontend

**ID:** E9-11
**Branch:** `e9/leadership-frontend`
**Depends on:** 04, 05, 07, 09
**Lane:** light
**Why this lane:** frontend only, over E9-04's, E9-05's, E9-07's and E9-09's
routes, with strings under prefixes those tickets placed (README decision
15). If a change reds an `invariant`-marked test, it stops and re-lanes.
**Size:** L
**Security-relevant:** the pages leaders read. A defect here sorts by a
figure, draws a by-lead control for a lead, shows a count beside a small-N
notice, or offers an action on the read-only drill-down.

## Context

SPEC §5.5's two-pane template, §2.2's term axis with per-cohort lines and a
cohort selector, §2.1's roots and labels, §5.6's attention cards, and §2's
switcher. This ticket draws them.

- **The tree** (`HierarchyNav`): hierarchy mode for everyone and by-lead mode
  only when the payload offers it; collapsed by default with expand and
  collapse all; clickable breadcrumbs; multiple roots for a union.
- **The roll-up page** (`AggregateHeader`, `MetricBlock`): per-cohort lines on
  the term axis with the cohort selector; response and validity rates;
  workload; the named-set selector, drawing E9-05's line beside the node's
  own, with its suppressed state.
- **The attention list** (`AttentionList`): each card names its rule and
  stream and links to the section's drill-down; the calm empty state.
- **The drill-down:** the instructor report's components, read-only, with a
  context bar ("Viewing as Dean · read-only"), no composer and no moderation
  actions, and the report's confidentiality line once.
- **The switcher and logout** in the app shell, over E9-04's routes.
- **The leadership landing** replaced by the roll-up, on the `landing` keys
  E9-04 moved.

**Carried here:** the rollup mockup's `SmallNNotice` count
(`design/LeadershipRollup.dc.html` passes `responded` and `total`); the six
server-required members kept optional in the frontend and the three names for
one figure type; comments naming tickets in `frontend/src/api/instructor.ts`.

Read first: SPEC §2, §2.1, §2.2, §4.1 items 4 and 5, §5.5 and §5.6;
`docs/DESIGN_BRIEF.md`, `design/tokens.css`, §7.6; the mockups
`LeadershipRollup`, `Leadership Rollup - States`, `HierarchyNav`,
`AggregateHeader`, `MetricBlock` and `AttentionList`; ADRs 0185 and 0196;
`../e6/carried-from-e5.md`'s optional-members entry.

## Owns

- `frontend/src/routes/leadership/`: the roll-up page, the tree and the
  drill-down page.
- `frontend/src/components/HierarchyNav.tsx`, `AttentionList.tsx` and
  `AggregateHeader.tsx` (new), and the app shell's switcher and logout.
- `frontend/src/api/leadership.ts` and `frontend/src/api/instructor.ts`: the
  calls; the views alias the generated types directly; one figure type name.
- Frontend copy under `leadership_rollup.` and `landing.`.
- `frontend/src/router.tsx`: the leadership routes.
- `design/LeadershipRollup.dc.html`: the count attributes removed.
- `scripts/seed.py`, only if 07 has not already added the roll-up data.

## Reuse, do not rewrite

`PulseTrendChart`, `TrendPair`, `StatPair`, `RatingHistogram`,
`ResponseRateBar`, `SmallNNotice`, `CommentGroup`, `CommentCard`, `WeekNav`,
`WeekEyebrow` and `LandingView`; the instructor report page's components for
the drill-down.

## Done when

1. **By-lead only when offered.** A lead's page shows no by-lead control; a
   chair's does (from mocked payloads, and in the e2e path).
2. **Order is the server's.** No list on these pages re-sorts by a figure; a
   test renders a payload whose figures are in descending order and whose
   labels are not, and the page keeps the label order.
3. **Per-cohort lines on the term axis,** with the cohort selector switching
   lines and the axis labelled TERM 01 to 18; the named-set line draws beside
   the node's and shows its suppressed state when the payload says so.
4. **The drill-down is read-only.** No composer, no exclude, keep or undo
   control, and the context bar names the reader's role; the confidentiality
   line appears once.
5. **No count beside a small-N notice,** on the pages and in the mockup.
6. **The switcher and logout.** The shell lists the landings E9-04's route
   offers, switches through the CSRF route, and logs out; after logout the
   app shows the signed-out state.
7. **The carried frontend entries.** The views alias the generated types (no
   `AddedLater` member is left optional that the server requires), and one
   comparison figure type name is imported everywhere.
8. **Words and basics.** Every string is in the copy registry under an
   existing prefix, with no change to the inventory test; aggregate copy
   counts sections, never instructors; keyboard and screen-reader basics hold,
   the tree included, and each chart has its data-table equivalent.
9. **One e2e path:** a chair lands on the roll-up, switches to by-lead mode,
   opens an attention card's section, and reads the drill-down. An axe scan
   runs on each page the path reaches.

## Shares files with

- `frontend/src/router.tsx`: 10.
- `scripts/seed.py`: 07 and 13.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 18, 19 and 23.

## Known traps

- **Entry 19.** A page test whose expected order is computed by sorting the
  same payload proves nothing; write the expected order out.
- **The calendar bomb.** Every e2e date comes from the seeded calendar
  relative to the real date; no pinned date.

## Not in this ticket

- Any backend change (04, 05, 07, 09).
- The `invariant`-marked tests (12).
