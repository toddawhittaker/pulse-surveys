# 0157 — The trend points carry both week axes

## Context

SPEC §2.2 puts both week axes on every course-level page: the course week
leads, and the term week sits under it as a quiet sub-label. §5.1 applies that
rule to the report's trend charts. E4-08 built `PulseTrendChart` to it — the
component takes both numbers per point and computes neither, and its copy file
records why the client must never derive the term week from an offset, even
though today's arithmetic would get it right: the offset is a per-section
constant now, and E4-08's own rule anticipates the case where it stops being
one.

E4-07's shipped `TrendPoint` carries `course_week` and `mean` only. The gap
between what the chart needs and what the wire states had no consequence until
E4-11 tried to reconcile the component contracts with the shipped schema
(breakdown decision 5 makes E4-11 that reconciliation point), and surfaced
there: nothing in the payload gives the sub-label a source.

The service already computes the number it would need. `_section_weeks`
builds a `_SectionWeek` row for every published window, and each row already
carries `term_week` — `_payload`'s trend builder reads those same rows to
build each `TrendPoint`, and simply stopped one field short of using what was
in hand.

The owner's ruling of 2026-09-07 (breakdown decision 12) settled the shape:
the wire states the pair, and the client derives nothing.

## Decision

`TrendPoint` gains `term_week: int`, populated in `_payload`'s trend builder
from the `_SectionWeek` row each point is already built from —
`other.term_week`, beside the existing `other.course_week`.

Nothing else about the trend moves. The list is still one point per published
window, ordered the way `published` already orders it, and `mean` is
unchanged. The member is additive: every existing reader of the payload that
does not look at `term_week` sees no other difference.

## Alternatives rejected

**The client derives the term week from an offset.** `_section_weeks` builds
`course_week` as `number - first_term_week + 1`, one `first_term_week`
constant per section, so today `term_week - course_week` is invariant across
every window a section has — the client could compute
`term_week = week.term_week - week.course_week + point.course_week` and get
it right for every payload this codebase can currently produce. It is
rejected anyway because `week_of_the_term` is this codebase's one reading of
§2.2's axis mapping, and a client doing that arithmetic is a second reading
of the same mapping rather than a consumer of the server's one answer. The
two readings agree only because the mapping happens to be affine today; the
day it stops being one — a section pausing over a term break, which is
exactly the case E4-08's copy file names — the client's copy would disagree
with the report silently, because nothing would tell it its arithmetic had
stopped matching the server's. Stating the member is cheaper than auditing
every consumer for that day.

**A section-level start-offset member**, such as a single
`first_term_week: int` on `WeekView` that a client combines with each point's
`course_week`. This is the same second-authority problem moved one field
over: `_section_weeks` does compute a `first_term_week` today, so shipping it
is possible, but a client combining it with `course_week` is still deriving
the mapping outside the one function that is supposed to own it, and still
disagrees silently the day the mapping is no longer a single per-section
constant. Stating `term_week` per point instead means the client never holds
anything it has to combine — the number is already the answer, computed by
`week_of_the_term` and read off the row `_payload` already has open.

## Consequences

Each trend point costs a few more bytes on the wire — one integer per
published window, so at most as many extra integers as `published_weeks` has
entries.

The term week is now stated twice in one payload: once on `week.term_week`
for the report as a whole, and once per point on the trend the report also
carries. `tests/unit/test_the_payload_sketch_and_the_schema_are_reconciled.py`
and `tests/integration/test_the_trend_points_carry_the_term_week.py` hold the
two statements to each other, so a future change to one without the other is
a red test rather than a silent disagreement.

No migration and no new service computation: the field is carried from a row
`_payload` already reads, so `_section_weeks` and `week_of_the_term` stand
exactly as they were.
