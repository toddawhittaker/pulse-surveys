# E6-10 — Keyboard focus survives a moderation decision

**ID:** E6-10
**Branch:** `e6/report-card-focus`
**Depends on:** E6-04
**Lane:** light
**Size:** S
**Security-relevant:** no.

## Context

The E6 boundary's `a11y-copy` review found that on the instructor report every
moderation control removes itself when pressed. `CommentCard.tsx` keys the card
body by status, so Keep, Exclude, Undo and Cancel unmount, focus falls to the
page body, and nothing is announced. A keyboard or screen-reader user must tab
back through the whole report. The leadership queue already handles this
(`ReviewQueue.tsx`).

## Owns

- `frontend/src/components/CommentCard.tsx` and its tests.
- `frontend/src/components/PulseTrendChart.tsx` and its tests.
- `frontend/src/components/ExclusionLogRow.tsx` and its copy, for the role
  sentence only (E6-09 owns the undo marker in the same file).
- An e2e step in `tests/e2e/instructor-report.spec.ts`.

## Done when

1. Opening the reason prompt focuses its textarea. Cancel returns focus to
   the Exclude button.
2. After a decision lands, focus moves to the new card's first control (or the
   card itself, with `tabIndex=-1`), and the outcome sentence is written to a
   status region that is present from the first render.
3. A refused reason is linked to its textarea by `aria-describedby`, and the
   field has `aria-invalid` while the refusal shows.
4. Each "Show the numbers" toggle names its stream, and the toggle does not
   claim `aria-expanded=false` while its tables are readable.
5. The log row says who decided in a sentence from the copy file, such as
   "Decided by the instructor", rather than a bare role word.
6. Vitest checks `document.activeElement` after each transition in 1 and 2, as
   `ComparisonSets.test.tsx` does. The e2e drive makes one decision by keyboard
   and checks where focus lands.
