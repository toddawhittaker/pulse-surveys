# E7-11 — The response loop's accessibility fixes

**ID:** E7-11
**Branch:** `e7/response-loop-accessibility`
**Depends on:** E7-05, E7-06, E7-07 (merged)
**Lane:** light
**Why this lane:** frontend components, CSS and copy only; no heavy-lane path.
**Size:** S
**Security-relevant:** no.

## Context

The E7 boundary review's `a11y-copy` pass (`boundary-review.md`) found seven
MEDIUM and four LOW defects in the epic's new screens. This ticket fixes all
eleven. Read `docs/DESIGN_BRIEF.md`, `design/tokens.css`, SPEC §7.6, and the
prototypes `design/ResponseCard.dc.html` and `design/PolicyToggle.dc.html`.

## Done when

1. **The replace-draft question is announced.** When "Draft with AI" would
   replace existing text, the question group is named (`aria-labelledby` on its
   prompt) and focus moves to its "Replace with draft" button.
2. **The composer's live region is always present.** The status element is
   always rendered and hidden with `sr-only`, never `display: none`; a repeated
   message is still announced. A test asserts the region is in the
   accessibility tree while empty.
3. **Busy controls keep focus.** The policy switch and the composer's draft,
   check and publish buttons use `aria-disabled="true"` and ignore activation
   while a request is in flight, instead of `disabled`. A test asserts focus
   stays on the pressed control.
4. **Week navigation keeps the student's place.** After a week change on the
   student results page, focus moves to the page heading (`tabIndex={-1}`). A
   test asserts it.
5. **Each reply link names its course.** The survey page's "See your
   instructor's reply" link carries the section's course label in its
   accessible name, with the visible text inside the name.
6. **The switch's off state is visible.** The off-state border uses
   `var(--input-edge)` (3:1 or better on paper); the component notes the
   deviation from the prototype.
7. **The response card matches the prototype.** The reply text uses
   `--font-display` at `--text-3`, line height 1.55; the card has a `--hairline`
   border and `--shadow-card`.
8. **Advisory failures are quiet.** A draft or check outage shows a quiet
   status in `--spruce-60`, with no `aria-invalid` and no alert role;
   `aria-invalid` is set only when a publish or edit fails.
9. **The labels say what they do.** "Use draft" becomes "Draft with AI"; the
   policy switch has `aria-describedby` pointing at its consequence text; the
   owed page's copy says "sections" and "weeks", not "section-weeks".

## Not in this ticket

- The axe scan (needs a `process/` pull request for the package).
- Any backend change.
