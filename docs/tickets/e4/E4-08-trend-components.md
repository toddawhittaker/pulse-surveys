# E4-08 — The trend components

**ID:** E4-08
**Branch:** `e4/trend-components`
**Depends on:** E4-16 for merge order only — builds day one against the
README's payload sketch; the PR waits for the runner
**Lane:** light
**Security-relevant:** minimally — no data access; the one §4.1-adjacent
duty is that nothing here invents copy (labels come from the copy modules
E4-12 governs) and aria labels carry no comparison language while no
comparison data exists (§4.1 item 1's chart clause, which E5 inherits).

## Context

The chart family for the report, per §7.6's component contract:
**PulseTrendChart** (single/three-line capable; in E4 exactly one line ever
renders, the section's own — the comparison and university lines are E5's)
and **TrendPair** (the stacked pair: instructor stream above, course stream
below, shared 1–5 y-scale, one legend). The x-axis is the course week
("WK 01…") with the quiet term-week sub-label ("TERM 04…") — §2.2's two-axes
rule — and week navigation's control renders here even though the page wires
it in E4-11.

One wording fact to hold apart: the chart axis follows **§2.2's chart
wording** ("WK 01…" with the quiet "TERM 04…" sub-label), while
`WeekEyebrow`'s wording was separately fixed by the FIX-01 ruling of
2026-09-03 as `COURSE WK NN, TERM WK NN` — that ruling governs the eyebrow
only, and nothing here restyles the eyebrow toward the chart or the chart
toward the eyebrow. (The eyebrow's carried course-length entry is
deliberately not this ticket's — README decision 9 says why it passes
through.)

Read first: `docs/DESIGN_BRIEF.md`, `design/tokens.css`, SPEC §7.6 (the
motion budget: hero line draws once, 600ms, everything else 150–220ms, all
motion gone under `prefers-reduced-motion`), §2.2, §5.1; the payload sketch
in this breakdown's README; E4-16's runner conventions once merged.

## Scope

- `PulseTrendChart` and `TrendPair` as components with typed props shaped by
  the sketch, plus Storybook-less fixture data in the component tests (the
  repo has no Storybook; fixtures live beside the tests).
- The shared scale, single legend, and stream labels per the design brief.
- The course-week axis with term-week sub-label, driven by props — no date
  arithmetic in the frontend; the server supplies both numbers (E4-07's
  criterion on the week axis).
- A gap week (null mean) renders as a gap, not a zero — a zero is a rating.
- Keyboard and screen-reader basics in-slice (§14.2 item 4): the chart's
  data is reachable as text (the design brief's data-table equivalent or
  aria approach — follow what it says, do not invent one).

## Acceptance criteria

1. TrendPair renders the two panels from sketch-shaped fixtures with one
   legend and a shared 1–5 scale — asserted structurally (both y-axes
   identical), not by pixel.
2. A null-mean week renders a visible gap; a 1.0 week renders at the scale's
   bottom; the two are distinguishable in the DOM.
3. The sub-label renders from the prop and never computes: fixture where
   course week 1 is term week 7 shows "TERM 07" under "WK 01".
4. No raw hex anywhere — tokens only; the lint or a test enforces it the way
   the existing components do.
5. Motion: the hero line's draw animation exists once, within budget, and is
   absent under `prefers-reduced-motion` — asserted at the CSS/attribute
   level.
6. No component in this diff fetches, imports the API client, or reads
   session state — props in, DOM out.

## Known traps

- **Do not build for three lines now.** PulseTrendChart's contract (§7.6)
  names the three-line variant, but E4 renders one line; the props type may
  admit a series list, and the rendering of multiple series is E5's to
  prove. Building unproven overlay rendering here is scope creep with a
  chart on it.
- **The axis is the server's** — a frontend that recomputes term weeks will
  disagree with the report the first time a section starts mid-term.
- **aria text is copy** — screen-reader labels are user-facing strings; keep
  them in the copy module layout the existing components use so E4-12's
  inventory collects them.

## Out of scope

- Any fetch, route, or page assembly — E4-11.
- Benchmark and university lines, cohort mode, term-axis aggregates — E5 and
  E9.
- TrendDuo (the student, benchmark-free variant) — E8.
