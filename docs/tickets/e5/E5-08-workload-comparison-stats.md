# E5-08 — The workload comparison stats

**ID:** E5-08
**Branch:** `e5/workload-comparison-stats`
**Depends on:** nothing — builds day one against the README's payload sketch
**Lane:** light
**Security-relevant:** minimally; §4.1 item 4 governs the labels, and the
suppressed treatment is where a copy slip would leak an implication.

## Context

§5.1: workload mean and median for the section **against comparison-set and
university figures**. E4-09's StatPair renders the section's own pair; this
ticket grows the component (or adds a sibling — the brief decides) to three
columns: section, comparison set, university. Fixture-driven; E5-10 joins.

Each comparison column is independently suppressible (§4.1 item 7 covers a
mean and a median exactly as a line), and a suppressed column renders the
brief's absent treatment with honest accessible text — never a dash that
reads as "zero workload".

Read first: `docs/DESIGN_BRIEF.md` (the mockup's comparison block),
`design/tokens.css`, SPEC §7.6, §5.1, §4.1 items 4 and 7; the README
sketch; `StatPair` and its E4-09 tests.

## Scope

- The three-column workload display with typed props per the sketch's
  `workload_benchmark` member: mean and median per column, comparison and
  university columns carrying suppressed/reason.
- Suppressed and absent states per the brief; accessible text per column.
- One decimal convention, shared with the existing StatPair rendering.

## Acceptance criteria

1. Three columns render from fixtures; values keep E4-09's decimal
   convention, from fixtures a rounding bug cannot satisfy.
2. Comparison suppressed while university passes, and the reverse — two
   fixtures, each rendering one absent treatment and one figure.
3. The no-benchmark-props state renders exactly E4's section-only pair
   (the same absent-prop discipline as E5-07 criterion 6, same §4.1 item 1
   reason).
4. Accessible text carries the numbers and the suppression fact; a
   suppressed column's text never says or implies zero.
5. Labels live in the copy layout the inventory collects; no ranking or
   composite language, self-checked against §4.1 item 4.
6. No raw hex; tokens only. No fetching; props in, DOM out.

## Known traps

- **A suppressed statistic rendered as a number-shaped placeholder** —
  "0.0" or an em-dash in a numeric column both mislead; follow the brief's
  absent treatment and say why in the accessible text.
- **Sharing too early** — if the three-column shape wants a new component
  rather than props on StatPair, build the sibling; do not refactor
  E4-09's component under its consumers in a light diff.

## Out of scope

- Real data and the page join — E5-10.
- Trend lines — E5-07.
- Any decision about the values — the payload decides; this renders.
