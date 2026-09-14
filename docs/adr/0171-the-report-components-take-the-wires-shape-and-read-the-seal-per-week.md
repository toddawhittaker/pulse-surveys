# 0171 — The report's benchmark components take the wire's shape, and a series is suppressed only when no week of it is drawable

**Status:** Accepted — E5-10.

## Context

E5-07 and E5-08 built the report's comparison overlays and workload columns
against the payload sketch in `docs/tickets/e5/README.md`, because the schema was
being written in parallel. The sketch gives a series one `suppressed` flag beside
its points and each point a bare numeric `mean`, and gives each workload column
one flag over a bare `mean` and `median`. What shipped instead
([ADR 0170](0170-a-benchmark-figure-is-sealed-at-every-point-and-the-e4-comparison-member-stays.md),
`app/schemas/report_benchmark.py`) seals every single figure on its own: a series
is its weeks and nothing else, every published week is present as a point, each
point's `mean` is a whole `{suppressed, reason, figure}`, and a workload column's
mean and median are two independently sealed figures.

E5-10 is the named reconciliation point (E5's breakdown decision 8), and it has
two construction questions the spec does not answer.

1. **Where does the reconciliation land?** The components already have props and
   fixtures in the sketch's shape. The page could map the payload into those
   props, or the props could be respelled as the wire spells them.
2. **What does a series with some weeks withheld look like?** SPEC §4.1 item 7
   governs each figure, and E5-07's treatment for a series that cannot be drawn
   is a notice in the copy registry's words. The spec says nothing about a series
   that can be drawn for four of its weeks and not the fifth, which is what the
   per-week seal makes possible and the sketch could not express.

## Decision

**One: one shape, and it is the wire's.** The component props are respelled as
the payload spells them — `course_week`, a `mean` that is a whole sealed figure,
a workload column that is two of them — so the page hands each component the
payload member and nothing is mapped on the way. The wire types are written once
in `frontend/src/api/instructor.ts`, whose standing rule is that every field is
the wire's spelling; the components carry structurally identical copies of their
own, because `PulseTrendChart.test.tsx` refuses an import from `../api` in the
trend family and this ticket does not widen that guard.

**Two: a series says it is suppressed when no week of it is drawable.** A week is
drawable only if its own seal says exactly `false` beside a real number. A series
with no drawable week gets E5-07's notice; a series with some draws those and
leaves a gap at each withheld week, with no extra notice; a member the payload
never sent draws nothing at all, which is §4.1 item 1's case and is unchanged. A
member that is present but carries no `points` array is "no drawable week" too,
which closes the crash `docs/tickets/e5/deferred.md` recorded against this
ticket.

## Alternatives rejected

**Keep the sketch-era props and map on the page.** It is the smaller diff and it
was rejected for two reasons. The sketch's shape survives in every component
fixture, which E5-10's third criterion forbids outright; and the map is lossy in
one direction that matters — a column whose median the server could report and
whose mean it could not has no sketch-shaped representation, so the page would
have to decide what to do with it, which is a suppression decision taken outside
the chokepoint.

**A notice whenever any week of a series is withheld.** Consistent, and it puts
"no line this week" under a line the reader can see, which is a sentence that
contradicts the picture. It also withholds more than §4.1 item 7 asks: the weeks
that cleared both minimums were cleared, and hiding them states nothing true. The
gap is already the honest rendering, and the series' table beside the chart says
"no figure that week" for the missing one.

**Tell a withheld week apart from an unreported one in the series' table.** Both
render as "no figure that week" today. A second sentence would publish, per week,
whether the comparison population was too thin — which is a shape of the set §4.1
item 7 means to say nothing about, and readable across a term of reports.

## Consequences

There is one spelling of a benchmark member in the client, and a schema change
is a compile error in the fixtures rather than a report rendering the wrong
member. Every question about whether a figure may be shown is asked in one
function per component, over one figure, which is what the fail-closed reading
E5-07 and E5-08's security rounds established now guards.

The cost is that the components' props are snake_case in the middle of a
camelCase tree, and that a payload which stopped sending a seal would show
notices everywhere rather than lines — loud, visible, and withholding nothing a
reader was entitled to.

A series whose weeks are all withheld is indistinguishable, on the page, from one
whose population reported nothing in any of those weeks. Both draw no line and
both say the set behind the line is too small to report on. That is the
conservative direction and it is stated here rather than discovered: the notice's
words come from `instructorReportTrendCopy.ts` and E5-13 owns the copy pass over
these surfaces.
