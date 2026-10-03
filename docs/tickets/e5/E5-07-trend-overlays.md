# E5-07 — The TrendPair overlays

**ID:** E5-07
**Branch:** `e5/trend-overlays`
**Depends on:** nothing — builds day one against the README's payload sketch
**Lane:** light
**Security-relevant:** minimally; the aggregate-language rules (§4.1 item 4)
govern the legend and every suppression notice, and E5-13's inventory will
collect them.

## Context

§5.1: each TrendPair panel carries three lines — this section (hero), the
comparison set, and university-wide. E4 shipped the pair with one line per
panel; this ticket adds the two overlay series to `PulseTrendChart` and
`TrendPair`, fixture-driven; the page joins real data in E5-10.

A line must also be honestly absent: a suppressed series renders as a
stated suppression (the brief's treatment), never as an empty line or a
silently two-line chart, and a passing series with one suppressed week
shows a gap the reader can understand.

Read first: `docs/DESIGN_BRIEF.md` (line treatments, and how the mockup
distinguishes the three lines), `design/tokens.css`, SPEC §7.6, §5.1, §4.1
items 4 and 5; the README's payload sketch; the existing
`PulseTrendChart`/`TrendPair` and their E4 tests.

## Scope

- The two overlay series with typed props per the sketch: points,
  suppressed flag, reason.
- One legend for three lines (§5.1), lines distinguishable without color
  alone (dash pattern or marker per the brief) — the a11y gate reviews
  this epic's charts.
- Suppressed states: whole-series suppression and per-week gaps, each with
  the brief's treatment and accessible text carrying the same fact.
- The hero line stays visually the hero (the brief's contrast ruling from
  E4-21 governs; nothing here re-litigates the trend color).

## Acceptance criteria

1. Three lines render from fixture data in both panels' shape (the
   component is per-panel; the pair test shows both).
2. A suppressed comparison series renders the stated treatment and the
   accessible text says the series is suppressed — and the university line
   still renders: the two series suppress independently, one fixture each
   way.
3. A per-week gap renders as a gap, not an interpolated bridge — fixture
   with a mid-series suppressed week.
4. The legend names the three lines in the brief's vocabulary; no ranking
   or composite language (§4.1 item 4), self-checked before review.
5. Lines are distinguishable in a no-color rendering (dash/marker
   asserted in the DOM, not by screenshot).
6. Zero-fixture state: a chart given no benchmark props renders exactly
   E4's chart — the components stay usable by the student surface, which
   must never receive these props (§4.1 item 1; the payload enforces it,
   the component must not default-fabricate).
7. No raw hex; tokens only. No fetching; props in, DOM out.

## Known traps

- **A default prop that draws** — an overlay series defaulting to
  anything visible puts a third line where the student payload sends
  nothing; the absent-prop state is the E4 rendering, asserted (criterion
  6 is the §4.1 item 1 edge of this ticket).
- **Legend copy drifts into ranking language** — "vs average" shapes;
  follow the brief's words exactly.

## Out of scope

- Real data, the page join, e2e — E5-10.
- Workload figures — E5-08.
- The student TrendDuo — untouched, by design.
