# E4-09 — The stat components

**ID:** E4-09
**Branch:** `e4/stat-components`
**Depends on:** nothing — builds against the README's payload sketch
**Lane:** light
**Security-relevant:** minimally; the aggregate-language rules (§4.1 item 4)
govern every label this ticket ships, and E4-12's inventory will collect
them.

## Context

The report's numbers rendered, per §7.6's component contract:
**RatingHistogram** (this-week distribution per stream, 1–5),
**StatPair** (workload mean and median side by side), and
**ResponseRateBar** (response rate, with the validity rate presented per the
design brief's treatment). All fixture-driven; the page joins them to real
data in E4-11.

The copy discipline is the point of care here: §4.1 item 4 bans ranking
language and composite scores anywhere, and these are the components whose
labels would drift into it ("top", "score", "underperforming" are the shapes
to refuse). Labels live in the copy module layout so the inventory governs
them.

Read first: `docs/DESIGN_BRIEF.md`, `design/tokens.css`, SPEC §7.6, §5.1,
§4.1 items 4 and 5; the payload sketch; the existing components
(`WorkloadSlider.tsx` for the numeric conventions the survey side set).

## Scope

- The three components with typed props per the sketch: distribution counts
  by rating value, workload mean/median as decimals, response and validity
  rates with their numerator and denominator available for the accessible
  text.
- Empty and small states: a zero-response week renders honestly (empty
  bars, an em-dash or the brief's treatment for absent statistics — follow
  the brief), never `NaN`, never `0%` pretending nobody-responded is
  everybody-hated-it.
- Keyboard and screen-reader basics: each figure has accessible text
  carrying the numbers, not just a drawn bar.

## Acceptance criteria

1. RatingHistogram renders five buckets from fixture counts, sums visible in
   accessible text, and a zero-count bucket is present, not omitted.
2. StatPair renders mean and median with one decimal convention, from
   fixtures a rounding bug cannot satisfy (avoid float-stable values — the
   "61.5" memory governs fixture choice).
3. ResponseRateBar renders rate plus "N of M" accessible text from the
   props' numerator and denominator — never recomputed from the rate.
4. The zero-response state renders the brief's absent treatment for every
   figure, driven by one fixture.
5. No raw hex; tokens only.
6. Every user-visible string in the diff lives in the copy layout the
   inventory collects, and none of them is ranking or composite language —
   self-checked against §4.1 item 4's list before review.
7. No fetching, no session, props in, DOM out.

## Known traps

- **A rate rendered from a float** ("62.000000001%") — format at one place
  with one rule, tested at a value that exposes it.
- **The validity rate's audience** — instructors and leadership only, never
  students (§3.3); nothing here decides that (the payload does), but the
  component must not bake "validity" into a shared component E8 would then
  inherit toward students.

## Out of scope

- Page assembly, real data — E4-11.
- Comparison-set and university workload figures beside the section's —
  E5's, through E4-07's guarded member.
- The copy inventory's growth itself — E4-12 (this ticket only keeps its
  strings collectable).
