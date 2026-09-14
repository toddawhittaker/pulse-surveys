# 0170 — A benchmark figure is sealed at every point, there is no series-level flag, and E4's `comparison` member stays

**Status:** Accepted — E5-05.

## Context

E5-05 puts SPEC §5.1's second and third lines on each of the report's two
panels, and the reported week's workload mean and median "against comparison-set
and university figures", on the wire. [SPEC §4.1](../SPEC.md) item 7 settles what
may be *shown* — "no figure computed from a comparison set is shown below the
benchmark minimum — a mean, a median, or any other statistic, not only a drawn
line" — and E4-07 settled how that is enforced for the one member E4 shipped
([ADR 0155](0155-the-report-read-lives-beside-the-summary-walk-and-its-comparison-type-carries-a-private-token.md)):
a private construction token, a seal over the figure's own field values, a field
validator at the payload boundary, and `revalidate_instances="always"` so that
the validator cannot be skipped by building the report a level out.

Three construction questions follow from putting many figures on the wire where
there was one, and the spec answers none of them.

1. **What does the payload say about a whole series, or about a whole workload
   pair?** E5's payload sketch — the contract E5-07, E5-08 and E5-10 build
   fixtures against — gives each series a `suppressed` and a `reason` beside its
   points, and gives each workload population one `suppressed` over a bare `mean`
   and `median`. E5-04 seals per week and per statistic. Both readings render.
2. **Does the top-level `comparison` member E4 shipped stay?** It was placed so
   the chokepoint had somewhere to stand before there were figures to put through
   it, and `frontend/src/api/instructor.ts` says the frontend does not read it.
3. **Where do the new models live?** The natural answer is beside the rest of the
   payload in `app/schemas/report.py`.

## Decision

**One: suppression is stated per point and per statistic, and nowhere else.**
There is no `suppressed` or `reason` on a series and none over a workload pair.
A suppressed week is a point that is present and whose `mean` is a suppressed
figure; a suppressed workload statistic is one of two independently sealed
figures saying so. Both are declared divergences from E5's sketch, registered in
`tests/unit/test_the_benchmark_payload_sketch_and_the_schema_are_reconciled.py`
and reconciled by E5-10 on the frontend side.

**Two: the top-level `comparison` member stays, and carries the default set's
workload mean for the reported week** — the same sealed object
`workload_benchmark.comparison.mean` carries, assigned twice and computed once.
A later ticket may retire it once nothing reads it.

**Three: the five new models live in `app/schemas/report_benchmark.py`, and
`app/schemas/report.py` imports the module rather than its classes.** Two of
them declare a member called `comparison`, and E4-07 settled that the sealed
comparison type is *discovered* — "the one model in `app.schemas.report`
carrying a `comparison` member" — so that the guarantee is a property of the
module rather than a class name a caller can copy. Three such models in one
module makes that discovery unanswerable, and a module import keeps
`app.schemas.report` with exactly one.

Each new model that holds a figure carries `frozen=True`,
`revalidate_instances="always"`, and one `mode="after"` field validator **per
figure member** calling `refuse_an_unsealed_comparison`. The revalidation goes on
every model on the path from `InstructorReport` down to a figure —
`StreamsView` and `StreamReport` included — because pydantic accepts an instance
of a nested model without re-validating it unless that model asks to be, so a
level on the path that does not is a level a caller builds with `model_construct`
to stop every validator below it running.

## Alternatives rejected

**A series-level `suppressed` flag, as the sketch draws it.** Rejected because
nothing could compute it honestly. Every figure in the system is produced by
`comparison_after_suppression` over its own population's two counts; a flag about
a whole series is a statistic no chokepoint sealed, and the natural way to
produce one is to consult the counts once for the series — which is the per-report
suppression decision E5-04's criterion 7 exists to forbid. It also makes a
per-week seal invisible to anything drawing the panel. The cost of rejecting it
is that a frontend drawing an "all weeks withheld" notice derives it from the
points; E5-08's components already read a suppressed figure per column.

**One `suppressed` flag over the workload mean and median.** Rejected because
§4.1 item 7 names "a mean, a median, or any other statistic" separately and
E5-04 seals them separately. One flag makes "median shown where the mean was
suppressed" inexpressible, and — the direction that matters — lets a mean through
on a decision taken for the median.

**Retiring the top-level `comparison` member.** Rejected: it is not additive.
E4's own sketch reconciliation names the member, every E4 reader of the payload
has it, and this ticket's criterion 6 is that every E4 member is unchanged.
Filling it with something *other* than the workload mean was rejected for the
opposite reason — two members with one name saying two things about one
statistic.

**Putting the new models in `app/schemas/report.py`.** Rejected because it
breaks the discovery above, which is the mechanism ADR 0155 chose over a name.
Renaming the members to avoid the collision was rejected too: `comparison` and
`university` are the two populations SPEC §5.1 names and the two the sketch and
the frontend fixtures are built on.

**One validator naming several figure members.** Rejected: one deletion would
unseal several members at once, and the mutation battery could not tell which
member a guard was covering.

## Consequences

- Every report validates its benchmark members twice — once when the route
  builds it and once when the response re-reads it — and now over several models
  rather than one. That is the price of the guarantee being about what is shown
  rather than about who built it, and ADR 0155 already paid it for one member.
- **A served payload carrying a shown figure cannot be re-validated from its own
  serialized JSON.** The seal is a private attribute over the field values and is
  deliberately never serialized, so a figure rebuilt from a mapping carries none
  and the boundary refuses it. Round-tripping a report through its own schema
  worked while every comparison member was suppressed and empty; from E5-05 it
  works only for a payload whose figures are all withheld. Anything that needs a
  report object — a test, a future consumer — takes it from the service rather
  than from a body. Recorded in `docs/disputes/E5-05-01.md`.
- The report read now makes six calls into `app.services.benchmarks` per request,
  each resolving a population and asking E5-03's set functions. Nothing is cached
  and nothing is shared between the two panels, which keeps the assembly readable;
  if a report read becomes slow, this is the first place to look and the shape of
  the fix is one resolution per population rather than one per figure.
- `app/schemas/report.py` no longer holds the whole report contract. A reader
  looking for a payload member may have to open one more file, and the report
  schema's docstring says which and why.
