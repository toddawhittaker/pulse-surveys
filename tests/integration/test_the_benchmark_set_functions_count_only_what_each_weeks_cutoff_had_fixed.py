"""The owner's "freeze at close" ruling, at the SQL functions — E5-14, boundary finding HIGH.

The owner's ruling of 2026-09-22, as the E5-14 work order records it:

> A comparison or university figure for course week *w* on a section's report
> counts only responses that were fixed at the moment the report's own section's
> week-*w* survey window closed. Concretely, with *T(w)* = the reported section's
> own `survey_window.closes_at` for course week *w*: a response contributes to
> week *w* only if the window it was submitted in … has `closes_at <= T(w)`,
> **and** its `last_submitted_at <= T(w)`.

and the orchestrator's SQL shape for it: `_v003` of both set functions takes
`(section_ids uuid[], course_weeks integer[], closed_by timestamptz[])`,
"`course_weeks[i]` pairs with `closed_by[i]`; each function returns rows only for
the course weeks asked, applying that week's cutoff."

**Why this is a confidentiality rule and not bookkeeping.** The boundary review
measured the defect it closes: a published comparison recomputed on every read
moved one student at a time while a later-starting section's same course week
was open, and one student's rating was recoverable from the difference
(`docs/MISTAKES.md` entry 51, a property that held in every payload and failed
across the sequence of them).

**This module pins the SQL half: the two `<=` comparisons and the per-week
pairing.** Which instant a report hands in as *T(w)* is the report's business and
is asserted through the route in
`test_a_published_benchmark_week_never_moves_after_its_own_close.py`.

**Every boundary is a pair, and every absence has its control in the same
test.** The instants differ by one microsecond — the smallest step a
`timestamptz` holds — so a comparison written `<` where `<=` belongs, or the
other way round, is red on exactly one side. And each "not counted" is asserted
beside the same section, same response, answering under a cutoff that does count
it, so an empty answer cannot be a world nobody planted (`docs/MISTAKES.md`
entry 3).

**Which failure a red here is on today's tree:** `require_benchmark_function`
fails naming the `_v003` signature, because `_v002` takes one argument.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    SET_FUNCTION,
    SET_RATING_FUNCTION,
    UG,
    WINDOWS_BY_TERM,
    BenchmarkWorld,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

THE_COHORT = "U"
THE_COURSE_WEEK = 2
THE_NEXT_WEEK = 3

# The smallest step a `timestamptz` tells apart. `tests/fixtures/grading.py`
# records the same fact for the same reason.
ONE_MICROSECOND = timedelta(microseconds=1)

# How long before its window's close a response is submitted, when the test is
# not about its stamp. Inside the window, and far from any boundary here.
AN_HOUR = timedelta(hours=1)

A_WORKLOAD = Decimal("6.5")
A_RATING = Decimal("4")

FUNCTIONS = (SET_FUNCTION, SET_RATING_FUNCTION)


def standard_close(world: BenchmarkWorld, label: str, course_week: int) -> datetime:
    """The Sunday close a section's course week has when nothing moves it."""
    planted = world.section(label)
    term_week = world.term_week_of(label, course_week)
    return WINDOWS_BY_TERM[planted.term][term_week][1]


THE_SECTION = "the-section"


def a_world_with_one_section(world: BenchmarkWorld) -> BenchmarkWorld:
    """The current term and one 12-week section in it, unanswered."""
    world.build()
    world.plant_section(THE_SECTION, cohort=THE_COHORT, level=UG)
    return world


def one_answered_section(
    world: BenchmarkWorld,
    *,
    closes_at: datetime | None = None,
    last_submitted_at: datetime | None = None,
    course_week: int = THE_COURSE_WEEK,
) -> str:
    """One student's response in `course_week` of the world's section, answering everything.

    `closes_at` moves that week's window close; `last_submitted_at` states the
    response's stamp. Either left out takes the ordinary value — the Sunday
    close, and an hour before it.
    """
    label = THE_SECTION
    close = closes_at or standard_close(world, label, course_week)
    if closes_at is not None:
        world.window_closing_at(label, course_week, closes_at)
    world.respond(
        label,
        course_week=course_week,
        subject=f"e5-14-freeze-{course_week}",
        workload=A_WORKLOAD,
        instructor_rating=A_RATING,
        course_rating=A_RATING,
        last_submitted_at=last_submitted_at or close - AN_HOUR,
    )
    world.session.flush()
    return label


def rows_at(
    world: BenchmarkWorld, function: str, label: str, cutoffs: dict[int, datetime]
) -> dict[int, list[dict[str, Any]]]:
    """The function's rows for one section and these cutoffs, grouped by course week."""
    rows = (
        world.set_week(label, cutoffs=cutoffs)
        if function == SET_FUNCTION
        else world.set_rating_week(label, cutoffs=cutoffs)
    )
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(int(row["course_week"]), []).append(row)
    return grouped


@pytest.mark.parametrize("function", FUNCTIONS, ids=list(FUNCTIONS))
def test_a_response_whose_window_closed_exactly_at_the_cutoff_counts(
    benchmark_world: BenchmarkWorld, function: str
) -> None:
    """The ruling's `closes_at <= T(w)`, on its equal side: a window closing at the cutoff counts.

    This is the ordinary case, not an edge: the report's own sections and every
    same-cohort section of its set close at the very same instant, so a
    comparison written `<` here drops the whole of a same-cohort default set.

    **The mutation it kills:** `closes_at < closed_by[i]`. **Its near miss** is
    the test below — one microsecond later, not counted — which `<=` passes and
    `<` also passes; only this one tells them apart.
    """
    label = one_answered_section(a_world_with_one_section(benchmark_world))
    cutoff = standard_close(benchmark_world, label, THE_COURSE_WEEK)

    rows = rows_at(benchmark_world, function, label, {THE_COURSE_WEEK: cutoff})

    assert rows.get(THE_COURSE_WEEK), (
        f"`{function}` answered no row for course week {THE_COURSE_WEEK} with the cutoff set to "
        f"{cutoff.isoformat()}, which is exactly when that week's window closed, over a response "
        "last submitted an hour before it. The ruling counts a window whose `closes_at <= T(w)`; "
        f"it answered {rows}."
    )


@pytest.mark.parametrize("function", FUNCTIONS, ids=list(FUNCTIONS))
def test_a_response_whose_window_closed_one_microsecond_after_the_cutoff_does_not_count(
    benchmark_world: BenchmarkWorld, function: str
) -> None:
    """The other side of the same boundary: a window still open at the cutoff is not counted.

    The response itself was last submitted an hour *before* the cutoff, so the
    stamp rule would count it; only the window rule refuses it. That is the case
    the finding was about — a later-starting section whose same course week is
    still open when the reported section's week has closed — reduced to one
    microsecond.

    **The control, in the same test:** the same section and response under a
    cutoff one microsecond later, which does count it. So the absence is about
    the window's close and not about a world with nothing in it.

    **The mutation it kills:** the window rule left out, so only the stamp is
    compared; and `closes_at <= now()` in place of the cutoff, which counts this
    response on any day after the late window shut. **Its near miss** is the
    test above.
    """
    a_world_with_one_section(benchmark_world)
    cutoff = standard_close(benchmark_world, THE_SECTION, THE_COURSE_WEEK)
    label = one_answered_section(
        benchmark_world,
        closes_at=cutoff + ONE_MICROSECOND,
        last_submitted_at=cutoff - AN_HOUR,
    )

    control = rows_at(benchmark_world, function, label, {THE_COURSE_WEEK: cutoff + ONE_MICROSECOND})
    assert control.get(THE_COURSE_WEEK), (
        f"The control failed before the assertion it protects: with the cutoff at the window's "
        f"own close ({(cutoff + ONE_MICROSECOND).isoformat()}) `{function}` answered no row for "
        f"course week {THE_COURSE_WEEK}: {control}. Until it does, the absence below is a world "
        "with nothing in it."
    )

    rows = rows_at(benchmark_world, function, label, {THE_COURSE_WEEK: cutoff})
    assert not rows.get(THE_COURSE_WEEK), (
        f"`{function}` counted a response in course week {THE_COURSE_WEEK} whose window closed at "
        f"{(cutoff + ONE_MICROSECOND).isoformat()}, one microsecond after the cutoff "
        f"{cutoff.isoformat()}: {rows[THE_COURSE_WEEK]}. The ruling counts a response only if its "
        "window has `closes_at <= T(w)` — a window still open when the reported week closed is "
        "exactly the population that moved a published figure one student at a time."
    )


@pytest.mark.parametrize("function", FUNCTIONS, ids=list(FUNCTIONS))
def test_a_response_last_submitted_exactly_at_the_cutoff_counts(
    benchmark_world: BenchmarkWorld, function: str
) -> None:
    """The ruling's `last_submitted_at <= T(w)`, on its equal side.

    The window closed a day before the cutoff, so only the stamp is under test.

    **The mutation it kills:** `last_submitted_at < closed_by[i]`. **Its near
    miss** is the test below.
    """
    a_world_with_one_section(benchmark_world)
    closes = standard_close(benchmark_world, THE_SECTION, THE_COURSE_WEEK)
    cutoff = closes + timedelta(days=1)
    label = one_answered_section(benchmark_world, last_submitted_at=cutoff)

    rows = rows_at(benchmark_world, function, label, {THE_COURSE_WEEK: cutoff})

    assert rows.get(THE_COURSE_WEEK), (
        f"`{function}` answered no row for course week {THE_COURSE_WEEK} over a response last "
        f"submitted at {cutoff.isoformat()}, which is the cutoff itself, in a window that closed a "
        f"day earlier: {rows}. The ruling counts a response whose `last_submitted_at <= T(w)`."
    )


@pytest.mark.parametrize("function", FUNCTIONS, ids=list(FUNCTIONS))
def test_a_response_last_submitted_one_microsecond_after_the_cutoff_does_not_count(
    benchmark_world: BenchmarkWorld, function: str
) -> None:
    """A response whose window closed in time but which was changed after the cutoff.

    This is the respond-on-behalf and the late revision case: the window closed
    before *T(w)*, and the row was written or rewritten afterwards. The ruling
    fixes a published figure at *T(w)*, so a stamp one microsecond later is out.

    **The control, in the same test:** the same response under a cutoff one
    microsecond later, which counts it.

    **The mutation it kills:** the stamp rule left out, so only the window is
    compared — under which a revision in a closed window rewrites a published
    week. **Its near miss** is the test above.
    """
    a_world_with_one_section(benchmark_world)
    closes = standard_close(benchmark_world, THE_SECTION, THE_COURSE_WEEK)
    cutoff = closes + timedelta(days=1)
    label = one_answered_section(benchmark_world, last_submitted_at=cutoff + ONE_MICROSECOND)

    control = rows_at(benchmark_world, function, label, {THE_COURSE_WEEK: cutoff + ONE_MICROSECOND})
    assert control.get(THE_COURSE_WEEK), (
        f"The control failed before the assertion it protects: with the cutoff at the response's "
        f"own stamp `{function}` answered no row for course week {THE_COURSE_WEEK}: {control}."
    )

    rows = rows_at(benchmark_world, function, label, {THE_COURSE_WEEK: cutoff})
    assert not rows.get(THE_COURSE_WEEK), (
        f"`{function}` counted a response last submitted at "
        f"{(cutoff + ONE_MICROSECOND).isoformat()}, one microsecond after the cutoff "
        f"{cutoff.isoformat()}: {rows[THE_COURSE_WEEK]}. A figure published at the cutoff would "
        "move when this row was written."
    )


@pytest.mark.parametrize("function", FUNCTIONS, ids=list(FUNCTIONS))
def test_each_course_week_is_held_to_its_own_cutoff(
    benchmark_world: BenchmarkWorld, function: str
) -> None:
    """`course_weeks[i]` pairs with `closed_by[i]`, and with nothing else.

    One section answered in two course weeks. Week 2 is asked with a cutoff one
    microsecond before its window closed, so it is out; week 3 with its own close,
    so it is in. Both are in the same call.

    **The mutations it kills:** one cutoff applied to every week — the first,
    the last, the largest — which answers both weeks or neither; and the arrays
    zipped out of step, which applies week 3's cutoff to week 2.
    """
    a_world_with_one_section(benchmark_world)
    one_answered_section(benchmark_world, course_week=THE_COURSE_WEEK)
    label = one_answered_section(benchmark_world, course_week=THE_NEXT_WEEK)
    week_two_close = standard_close(benchmark_world, label, THE_COURSE_WEEK)
    week_three_close = standard_close(benchmark_world, label, THE_NEXT_WEEK)

    rows = rows_at(
        benchmark_world,
        function,
        label,
        {THE_COURSE_WEEK: week_two_close - ONE_MICROSECOND, THE_NEXT_WEEK: week_three_close},
    )

    assert rows.get(THE_NEXT_WEEK), (
        f"`{function}` answered no row for course week {THE_NEXT_WEEK}, asked with its own close "
        f"as the cutoff: {rows}. Without it the absence of week {THE_COURSE_WEEK} below says "
        "nothing about per-week cutoffs."
    )
    assert not rows.get(THE_COURSE_WEEK), (
        f"`{function}` counted course week {THE_COURSE_WEEK} under a cutoff one microsecond before "
        f"that week's window closed: {rows[THE_COURSE_WEEK]}. Week {THE_NEXT_WEEK}'s cutoff, a "
        "week later, has been applied to it — the two arrays are paired index by index."
    )


@pytest.mark.parametrize("function", FUNCTIONS, ids=list(FUNCTIONS))
def test_a_course_week_nobody_asked_for_answers_no_row(
    benchmark_world: BenchmarkWorld, function: str
) -> None:
    """Rows only for the course weeks asked, even where another week holds data.

    The section is answered in weeks 2 and 3 and only week 3 is asked for.

    **The mutation it kills:** a body that answers every week the section set has
    rows in and uses the arrays only to look cutoffs up — which puts week 2 on
    the wire with no cutoff applied at all, the unfrozen figure the ruling ends.
    """
    a_world_with_one_section(benchmark_world)
    one_answered_section(benchmark_world, course_week=THE_COURSE_WEEK)
    label = one_answered_section(benchmark_world, course_week=THE_NEXT_WEEK)
    week_three_close = standard_close(benchmark_world, label, THE_NEXT_WEEK)

    rows = rows_at(benchmark_world, function, label, {THE_NEXT_WEEK: week_three_close})

    assert rows.get(THE_NEXT_WEEK), (
        f"`{function}` answered no row for course week {THE_NEXT_WEEK}, the one week asked for: "
        f"{rows}."
    )
    assert sorted(rows) == [THE_NEXT_WEEK], (
        f"`{function}` answered course weeks {sorted(rows)} when asked for {[THE_NEXT_WEEK]} "
        "alone. The ruling's SQL shape returns rows only for the course weeks asked."
    )
