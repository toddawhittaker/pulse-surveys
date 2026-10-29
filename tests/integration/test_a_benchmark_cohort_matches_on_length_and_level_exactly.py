"""E5-03 criterion 3 — a cohort is exact on both length and level, both sides asserted.

SPEC §5.1, the comparison-sets paragraph, first sentences:

> To be comparable, sections must match on **both** length (§2.2's length set)
> *and* level (§8's set: `DEV`, `UG`, `UGGR`, `GR`, `DR`) — an 8-week graduate
> course is never averaged against a 12-week undergraduate one. Levels match
> **exactly**; no level is folded into another. A `UGGR` section is compared
> against other `UGGR` sections and not against `UG` or `GR` ones, and a `DEV`
> section only against `DEV`.

Two rules, and each is asserted from both sides in one world, which is what the
criterion asks for: "a planted section differing only in level, and one
differing only in length, are each outside the cohort — the §5.1 no-folding
rule, both sides."

**Re-pointed by E9-12.** These tests read `benchmark_cohort_week`, the view that
keyed a cohort by length, level, term and course week; E9-12 retires it (README
decision 10). A cohort is now the **university population** E5-04's service
resolves for a section — `resolve_university(session, section_id=…)`, "all
same-length+level sections institution-wide" — and its figures come from
`benchmark_set_week` over that population. So each test asserts the rule where it
now lives (which sections the resolver puts in a section's population) and then
the figure over that population, so a fold is still visible as a number nobody
submitted.

**Each pair differs in exactly one thing.** The level world plants four sections
of the *same* start cohort — same length, same start date, same course week, same
term — whose courses sit in three different bands of SPEC §8's number table, so
`level` is the only thing that can separate them. The length world plants a
12-week `U` section and a 6-week `E` section, both `UG`, both starting in the
term's first week, and reads course week 2 of each.

**Why the "in" half is a separate test each time.** "The other section is not in
this population" is satisfied by a resolver that dropped that section on the
floor — a hard-coded `level = 'UG'` — and a benchmark that silently omits every
`UGGR` section is a worse defect than one that folds them in. So each pair asserts
that the excluded section's own population holds it.

**The figures are read over the resolved population's planted part.** The
resolver answers for the whole institution, and other tests' committed worlds may
hold sections of the same length and level; intersecting with the sections this
world planted keeps every expected number a number written here
(`docs/MISTAKES.md` entries 19 and 30), while the membership assertions are made
on the whole answer.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    GR,
    RESOLVE_UNIVERSITY,
    SET_FUNCTION,
    UG,
    UGGR,
    BenchmarkWorld,
    benchmarks_api,
)

pytestmark = pytest.mark.integration

THE_COURSE_WEEK = 2

# The level world. Two undergraduate sections and one of each neighbouring band,
# all of start cohort `U`: twelve weeks, starting 2026-08-17.
#
# The hours are far apart on purpose, and each folded total is written out
# beside them. The two `UG` sections average 2.5; folding in the `UGGR` section
# gives 4.0 and folding in both neighbours gives 5.25 — neither of which any
# student in any of these sections submitted.
UG_FIRST_HOURS = Decimal("2.0")
UG_SECOND_HOURS = Decimal("3.0")
UGGR_HOURS = Decimal("7.0")
GR_HOURS = Decimal("9.0")

UG_MEAN = Decimal("2.5")
UGGR_MEAN = Decimal("7.0")
GR_MEAN = Decimal("9.0")
# (2.0 + 3.0 + 7.0) / 3
MEAN_IF_UGGR_IS_FOLDED_IN = Decimal("4.0")
# (2.0 + 3.0 + 7.0 + 9.0) / 4
MEAN_IF_BOTH_NEIGHBOURS_ARE_FOLDED_IN = Decimal("5.25")

LEVEL_WORLD = ("ug-first", "ug-second", "uggr", "gr")

# The length world. One twelve-week `U` section and one six-week `E` section,
# both `UG`, both starting 2026-08-17.
TWELVE_WEEK_HOURS = Decimal("2.0")
SIX_WEEK_HOURS = Decimal("7.0")
MEAN_IF_THE_LENGTHS_ARE_FOLDED = Decimal("4.5")

LENGTH_WORLD = ("twelve", "six")


def a_cohort_week_with_three_levels(world: BenchmarkWorld) -> BenchmarkWorld:
    """Four sections of one start cohort, in three of SPEC §8's level bands."""
    world.build()
    for label, level in (
        ("ug-first", UG),
        ("ug-second", UG),
        ("uggr", UGGR),
        ("gr", GR),
    ):
        world.plant_section(label, cohort="U", level=level)
    for label, hours in (
        ("ug-first", UG_FIRST_HOURS),
        ("ug-second", UG_SECOND_HOURS),
        ("uggr", UGGR_HOURS),
        ("gr", GR_HOURS),
    ):
        world.respond(
            label,
            course_week=THE_COURSE_WEEK,
            subject=f"e5-03-level-{label}",
            workload=hours,
        )
    return world


def a_cohort_week_with_two_lengths(world: BenchmarkWorld) -> BenchmarkWorld:
    """One twelve-week and one six-week undergraduate section, sharing a course week."""
    world.build()
    world.plant_section("twelve", cohort="U", level=UG)
    world.plant_section("six", cohort="E", level=UG)
    world.respond(
        "twelve",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-length-twelve",
        workload=TWELVE_WEEK_HOURS,
    )
    world.respond(
        "six",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-length-six",
        workload=SIX_WEEK_HOURS,
    )
    return world


def planted_in_the_population(
    world: BenchmarkWorld, label: str, planted: tuple[str, ...]
) -> list[str]:
    """Which of this world's planted sections the resolver puts in `label`'s university population."""
    world.session.flush()
    population = {
        str(section)
        for section in benchmarks_api()[RESOLVE_UNIVERSITY](
            world.session, section_id=world.section_id(label)
        )
    }
    return [other for other in planted if str(world.section_id(other)) in population]


def the_row(world: BenchmarkWorld, labels: list[str]) -> dict[str, Any]:
    """`benchmark_set_week`'s one row at the course week over `labels`, with the non-vacuity guard."""
    rows = [row for row in world.set_week(*labels) if row["course_week"] == THE_COURSE_WEEK]
    assert len(rows) == 1, (
        f"`{SET_FUNCTION}` answered {len(rows)} rows at course week {THE_COURSE_WEEK} over "
        f"{labels}, every one of which was answered then: {rows}. The assertions below would be "
        "vacuous (`docs/MISTAKES.md` entry 3)."
    )
    return rows[0]


def test_a_section_differing_only_in_level_is_outside_the_cohort(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 3's level half, the out side. §5.1: no level is folded into another.

    Four sections, identical in length, start date, term and course week, in
    three level bands. The undergraduate section's population holds the two
    `UG` sections and neither neighbour, and the figure over it is two sections,
    a mean of 2.5.

    `UGGR` is the near miss that matters: the band §5.1 names twice, and the one
    a reasonable implementer folds.

    **The mutation it exists to survive**: the level predicate dropped from the
    university resolver (all four in, mean 5.25), widened to `level IN ('UG',
    'UGGR')` (mean 4.0), or a coarsening expression folding `UGGR` into `UG`.
    **The near miss it tolerates**: two sections of the same level, which are
    one population and must stay one.
    """
    world = a_cohort_week_with_three_levels(benchmark_world)

    population = planted_in_the_population(world, "ug-first", LEVEL_WORLD)
    assert population == ["ug-first", "ug-second"], (
        f"The {UG} section's university population holds {population} of this world's sections. "
        f"Two undergraduate sections answered; the other two are {UGGR} and {GR}, and §5.1 "
        "matches levels exactly."
    )
    row = the_row(world, population)
    assert row["section_count"] == 2 and row["workload_mean"] == UG_MEAN, (
        f"The figure over the {UG} population is {row}; its two sections submitted "
        f"{UG_FIRST_HOURS} and {UG_SECOND_HOURS} hours, a mean of {UG_MEAN}. "
        f"{MEAN_IF_UGGR_IS_FOLDED_IN} is the {UGGR} section folded in and "
        f"{MEAN_IF_BOTH_NEIGHBOURS_ARE_FOLDED_IN} is both neighbours."
    )


def test_a_section_at_another_level_is_keyed_under_that_level_rather_than_dropped(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 3's level half, the in side — the section is elsewhere, not gone.

    The same world. The `UGGR` section's own population holds it and no `UG` or
    `GR` section, carrying its own figure; so does the `GR` one's. Without this,
    the assertion above is satisfied by a resolver that answers undergraduate
    populations and throws every other level away.

    **The mutation it exists to survive**: a hard-coded `level = 'UG'`, or a level
    list holding three of §8's five bands. Both leave the test above green.
    """
    world = a_cohort_week_with_three_levels(benchmark_world)

    dual_credit = planted_in_the_population(world, "uggr", LEVEL_WORLD)
    assert dual_credit == ["uggr"], (
        f"The {UGGR} section's university population holds {dual_credit} of this world's "
        "sections; it is the one dual-credit section, and the level neither folds into "
        f"{UG} (§5.1) nor vanishes."
    )
    row = the_row(world, dual_credit)
    assert (
        row["section_count"] == 1 and row["workload_mean"] == UGGR_MEAN
    ), f"The figure over the {UGGR} population is {row}; its one section submitted {UGGR_HOURS}."

    graduate = planted_in_the_population(world, "gr", LEVEL_WORLD)
    assert graduate == ["gr"], (
        f"The {GR} section's university population holds {graduate}. Both neighbours are "
        "asserted, because a rule that reaches two of §8's bands and not the third is the shape a "
        "hand-written level list takes."
    )
    assert the_row(world, graduate)["workload_mean"] == GR_MEAN


def test_a_section_differing_only_in_length_is_outside_the_cohort(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 3's length half, the out side. §5.1: sections must match on both.

    A twelve-week `U` section and a six-week `E` section, both undergraduate,
    both starting on the term's first Monday: they agree on the level, the term,
    the calendar week and the course week, so length is the only thing that can
    tell them apart.

    **The mutation it exists to survive**: the length predicate dropped from the
    university resolver, which puts both in one population with a mean of 4.5.
    """
    world = a_cohort_week_with_two_lengths(benchmark_world)

    population = planted_in_the_population(world, "twelve", LENGTH_WORLD)
    assert population == ["twelve"], (
        f"The twelve-week section's university population holds {population} of this world's "
        "sections; the other runs six weeks, and §5.1 requires a match on both length and level."
    )
    row = the_row(world, population)
    assert row["section_count"] == 1 and row["workload_mean"] == TWELVE_WEEK_HOURS, (
        f"The figure over the twelve-week population is {row}; its one section submitted "
        f"{TWELVE_WEEK_HOURS} hours. {MEAN_IF_THE_LENGTHS_ARE_FOLDED} is the six-week section "
        "folded in."
    )


def test_a_section_of_another_length_is_keyed_under_that_length_rather_than_dropped(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 3's length half, the in side.

    The six-week section's own population holds it. "Most sections are 6-week,
    then 12-week" (§2.2), so a resolver answering twelve-week populations and
    dropping the rest would miss the commonest cohort in the institution.

    **The mutation it exists to survive**: a `length_weeks = 12` predicate, or a
    hand-written length list holding some of §2.2's seven.
    """
    world = a_cohort_week_with_two_lengths(benchmark_world)

    population = planted_in_the_population(world, "six", LENGTH_WORLD)
    assert population == ["six"], (
        f"The six-week section's university population holds {population} of this world's "
        "sections."
    )
    row = the_row(world, population)
    assert row["section_count"] == 1 and row["workload_mean"] == SIX_WEEK_HOURS, (
        f"The figure over the six-week population is {row}; its one section submitted "
        f"{SIX_WEEK_HOURS} hours in its second course week."
    )
