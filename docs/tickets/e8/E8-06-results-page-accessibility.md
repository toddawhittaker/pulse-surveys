# E8-06 — The results page's accessibility and copy

**ID:** E8-06
**Branch:** `e8/results-page-accessibility`
**Depends on:** E8-02, E8-03
**Lane:** light
**Why this lane:** frontend only; it changes no read and no invariant test.
**Size:** S
**Security-relevant:** no.

## Context

The E8 boundary battery ran on 1ecd5b55 (`boundary-review.md`). This ticket fixes its page findings. E8-05 fixes the backend's.

## Done when

1. **The ledger keeps its lines** (a11y-copy MED). The participation ledger renders one list item per line; the server joins lines with `\n`, and a test uses `\n`.
2. **The score says it is a percentage** (a11y-copy and lti-oidc MED). The sentence reads as the student's participation percentage, with "%", and does not claim to be the figure the gradebook shows (the gradebook may scale it to its own maximum).
3. **One draw** (a11y-copy MED). TrendDuo's two panels draw together in one 600 ms moment, not one after the other.
4. **The percent histogram has a table** (a11y-copy MED): rating and percent, behind the same visually hidden toggle the trend uses.
5. **The histograms say what they rate** (a11y-copy MED): the visible title names ratings about the instructor or the course.
6. **Small words** (a11y-copy LOWs). With the results lead showing, the landing card does not add a second link to the same page; "h" is written "hours".
7. **The notice names no cause it cannot know** (code-reviewer LOW). A stream held while moderation finishes reads the same as a small one, so the comments notice does not say "once enough classmates have commented"; it says the comments are not shown this week and may appear later, with no number.
8. **Tests that can fail** (code-reviewer LOW, invariant-coverage LOW). The landing's awaiting and no-week tests render a second section whose lead does show, wait for it, then assert the first has none. A component test plants comparison and university figures on TrendDuo and the percent histogram and asserts neither reaches the text or the aria labels.
9. **Simpler** (code-reviewer simplifications 1–3): SmallNNotice takes its title and body from the caller; `showsData`, the `lengthWeeks` spread and `sharesOf`'s double default go; the unused `StudentTrendPoint` and `StudentReleasedComment` exports in `api/student.ts` go.

## Not in this ticket

Any backend change (E8-05).
