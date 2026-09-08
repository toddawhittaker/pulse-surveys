# E4-19 — The trend points carry both week axes

**ID:** E4-19
**Branch:** `e4/trend-term-weeks`
**Depends on:** E4-07
**Lane:** heavy
**Security-relevant:** no new data crosses the wire that the same payload does
not already state — the term weeks of the reader's own section's published
weeks, which `week` carries for one of them and `published_weeks` lets a
client count off from. The change is that the numbers arrive stated instead
of derivable.

## Context

SPEC §2.2 puts both week axes on every course-level page: the course week
leads, the term week sits under it as a quiet sub-label, and §5.1 applies
that to the report's trend charts. E4-08 built the chart to that rule —
`PulseTrendChart` takes both numbers per point and computes neither, and its
copy file records why the client must not derive the term week from an
offset: a section that pauses over a break week would make the derived number
disagree with the report.

E4-07's shipped `TrendPoint` carries `course_week` and `mean` only, so the
sub-label has no wire source. The gap surfaced while E4-11 reconciled the
component contracts with the schema (breakdown decision 5 makes E4-11 the
reconciliation point), and the ruling of 2026-09-07 is breakdown decision 12:
the wire states the pair, the client derives nothing.

The fix is small because the service already holds the number:
`app.services.reporting._section_weeks` builds a `_SectionWeek` per published
window carrying `term_week`, and `_payload` builds each `TrendPoint` from
exactly those rows.

## Scope

- `term_week: int` on `app.schemas.report.TrendPoint`, populated in
  `_payload`'s trend builder from the `_SectionWeek` row in hand.
- The payload sketch in `docs/tickets/e4/README.md` gains the member, in the
  same change as the schema — the reconciliation test holds the two to each
  other in both directions, so neither may move alone.
- The ADR for the construction choice (the alternatives were real: a
  section-level start-offset member, or client derivation).

## Acceptance criteria

1. Every trend point in the report payload carries the term week of the
   window row it was built from, proven through the route in a world where
   the section starts mid-term — `course_week != term_week` — so a
   `term_week` populated with the course week is a red, not an equivalent
   mutant.
2. In one payload, the trend point whose `course_week` equals
   `week.course_week` carries `term_week` equal to `week.term_week` — the
   two statements of the axis pair cannot disagree.
3. The sketch-reconciliation test passes with the member present on both
   sides, and reds if either side drops it.
4. No other payload member moves. Comments, rates, summaries and the
   published-week list are untouched; `PublishedWeeks` stays a list of course
   weeks — week navigation needs no term axis, the chart is the sub-label's
   only consumer.

## Known traps

- **The near-miss mutant is the point** (`docs/MISTAKES.md` entry 3): in a
  world whose section starts week one, `term_week = course_week` passes every
  test. The proving world must start mid-term.
- **Existing tests that construct `TrendPoint` directly go red when the field
  becomes required** (entry 22's shape). They are updated in the tests-first
  commit, on the test side of the wall, not left for the implementer to trip
  over.
- **Pydantic ignores unknown constructor keywords by default**, so a
  tests-first construction passing `term_week` today is silently green until
  the field exists. Reds must be assertions that read the field back, never
  constructions that merely pass it.

## Out of scope

- Frontend consumption of the member — E4-11.
- Any change to how course weeks are computed from term weeks
  (`week_of_the_term` and `_section_weeks` stand as they are).
