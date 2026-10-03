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

**Each pair differs in exactly one thing.** The level world plants three
sections of the *same* start cohort — same length, same start date, same course
week, same term — whose courses sit in three different bands of SPEC §8's
number table, so `level` is the only column that can separate them. The length
world plants a 12-week `U` section and a 6-week `E` section, both `UG`, both
starting in the term's first week, and reads course week 2 of each: they share
the term week as well as the course week, so `length_weeks` is the only column
that can separate *them*. A view that dropped either predicate folds the pair
into one row, and the figures are chosen so the folded mean is a number none of
the planted students submitted.

**Why the "in" half is a separate test each time.** "The other section is not in
this row" is satisfied by a view that dropped that section on the floor — a
`WHERE level = 'UG'` hard-coded, a join that lost it — and a benchmark that
silently omits every `UGGR` section in the institution is a worse defect than
one that folds them in, because nothing downstream can see it. So each pair
asserts that the excluded section is *keyed elsewhere*, present and correct
under its own cohort.
"""

from decimal import Decimal

import pytest
from fixtures.benchmark_views import (
    COHORT_WEEK_VIEW,
    GR,
    UG,
    UGGR,
    BenchmarkWorld,
    require_benchmark_view,
)

pytestmark = pytest.mark.integration

TWELVE_WEEKS = 12
SIX_WEEKS = 6
THE_COURSE_WEEK = 2

# The level world. Two undergraduate sections and one of each neighbouring band,
# all of start cohort `U`: twelve weeks, starting 2026-08-17, so course week 2 is
# term week 2 for every one of them.
#
# The hours are far apart on purpose, and each folded total is written out
# beside them. The two `UG` sections average 2.5; folding in the `UGGR` section
# gives 4.0 and folding in both neighbours gives 5.25 — neither of which any
# student in any of these sections submitted, which is what makes a folded row
# visible as a number rather than as a shrug.
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

# The length world. One twelve-week `U` section and one six-week `E` section,
# both `UG`, both starting 2026-08-17 — so course week 2 is term week 2 for both
# and the calendar cannot be what separates them.
TWELVE_WEEK_HOURS = Decimal("2.0")
SIX_WEEK_HOURS = Decimal("7.0")
MEAN_IF_THE_LENGTHS_ARE_FOLDED = Decimal("4.5")


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


def test_a_section_differing_only_in_level_is_outside_the_cohort(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 3's level half, the out side. §5.1: no level is folded into another.

    Four sections, identical in length, start date, term and course week, in
    three level bands. The undergraduate row is over the two `UG` sections and
    nothing else: two sections, two respondents, a mean of 2.5.

    `UGGR` is the near miss that matters. It is the band §5.1 names twice —
    "a `UGGR` section is compared against other `UGGR` sections and not against
    `UG` or `GR` ones" — and it is the one a reasonable implementer folds,
    because a dual-credit section looks like an undergraduate one from every
    direction except the one the spec cares about. §5.1 says why: "the
    dual-credit and developmental populations are the two whose experience is
    least like the undergraduate mean, so averaging them into it would hide
    exactly the signal the product exists to surface."

    **The mutation it exists to survive**: `level` dropped from the `GROUP BY`
    (a single row over all four sections, mean 5.5), the join predicate widened
    to `level IN ('UG', 'UGGR')` (mean 4.5), and a coarsening expression —
    `left(level, 2)`, a `CASE` folding `UGGR` into `UG` — which produces the
    same 4.5 by a route that reads as deliberate.
    **The near miss it tolerates**: two sections of the same level, which are
    one row and must stay one; that is the test below.
    """
    world = a_cohort_week_with_three_levels(benchmark_world)

    row = world.cohort_week(length_weeks=TWELVE_WEEKS, level=UG, course_week=THE_COURSE_WEEK)
    assert row is not None, (
        f"`{COHORT_WEEK_VIEW}` has no {UG} row for this cohort week, in which two undergraduate "
        "sections were answered. Every assertion below would be vacuous against an absent row, and "
        "'the graduate section is not in it' would be true of nothing at all "
        "(`docs/MISTAKES.md` entry 3)."
    )
    assert row["section_count"] == 2, (
        f"`section_count` is {row['section_count']!r} in the {UG} cohort week. Two undergraduate "
        f"sections answered it; the other two sections in this world are {UGGR} and {GR}, and §5.1 "
        "matches levels exactly. A 3 is one neighbour folded in and a 4 is both."
    )
    assert row["workload_mean"] == UG_MEAN, (
        f"`workload_mean` is {row['workload_mean']!r} in the {UG} cohort week, whose two sections "
        f"submitted {UG_FIRST_HOURS} and {UG_SECOND_HOURS} hours — a mean of {UG_MEAN}.\n\n"
        f"{MEAN_IF_UGGR_IS_FOLDED_IN} is the {UGGR} section folded in, which is the fold §5.1 "
        f"names outright. {MEAN_IF_BOTH_NEIGHBOURS_ARE_FOLDED_IN} is both neighbours folded in, "
        "which is `level` missing from the key altogether. Neither number was submitted by anybody "
        "in any of these sections, which is what makes this row discriminate."
    )


def test_a_section_at_another_level_is_keyed_under_that_level_rather_than_dropped(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 3's level half, the in side — the section is elsewhere, not gone.

    The same world. The `UGGR` section has its own row, keyed at its own level,
    carrying its own figures; so does the `GR` one. Without this, the assertion
    above is satisfied by a view that computes undergraduate cohorts and throws
    every other level away — a benchmark that silently has no dual-credit
    figures at all, which nothing downstream can detect because a suppressed
    figure and an absent one look the same to a reader (§4.1 item 7's whole
    subject is figures that are *not* shown).

    **The mutation it exists to survive**: a hard-coded `WHERE level = 'UG'`, or
    a join to a level lookup that has three of §8's five bands in it. Both leave
    the test above perfectly green.
    """
    world = a_cohort_week_with_three_levels(benchmark_world)
    require_benchmark_view(world.session, COHORT_WEEK_VIEW)

    dual_credit = world.cohort_week(
        length_weeks=TWELVE_WEEKS, level=UGGR, course_week=THE_COURSE_WEEK
    )
    assert dual_credit is not None, (
        f"`{COHORT_WEEK_VIEW}` has no {UGGR} row for this cohort week. A dual-credit section "
        f"answered it, submitting {UGGR_HOURS} hours. The level does not fold into {UG} (§5.1) and "
        "it does not vanish either: SPEC §8 lists five level bands and a cohort view that "
        "computes some of them has no way of saying which."
    )
    assert dual_credit["section_count"] == 1, (
        f"The {UGGR} row's `section_count` is {dual_credit['section_count']!r}; one dual-credit "
        "section answered this cohort week."
    )
    assert dual_credit["workload_mean"] == UGGR_MEAN, (
        f"The {UGGR} row's `workload_mean` is {dual_credit['workload_mean']!r}; its one section "
        f"submitted {UGGR_HOURS} hours."
    )

    graduate = world.cohort_week(length_weeks=TWELVE_WEEKS, level=GR, course_week=THE_COURSE_WEEK)
    assert graduate is not None and graduate["workload_mean"] == GR_MEAN, (
        f"The {GR} row is {graduate}; its one section submitted {GR_HOURS} hours. Both neighbours "
        "are asserted rather than one, because a rule that reaches two of §8's bands and not the "
        "third is the shape a hand-written level list takes."
    )


def test_a_section_differing_only_in_length_is_outside_the_cohort(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 3's length half, the out side. §5.1: sections must match on both.

    A twelve-week `U` section and a six-week `E` section, both undergraduate,
    both starting on the term's first Monday. Course week 2 of each is term week
    2 of the term, so these two rows agree on the level, the term, the calendar
    week *and* the course week: `length_weeks` is the only column in the key
    that can tell them apart, which is what makes this pair worth planting
    rather than describing.

    **The mutation it exists to survive**: `length_weeks` dropped from the
    `GROUP BY` or from the join predicate, which folds the two into one row with
    a mean of 4.5 — a figure that would put a six-week section's second week,
    a third of the way through its course, beside a twelve-week section's
    second week, an eighth of the way through its own.
    """
    world = a_cohort_week_with_two_lengths(benchmark_world)

    row = world.cohort_week(length_weeks=TWELVE_WEEKS, level=UG, course_week=THE_COURSE_WEEK)
    assert row is not None, (
        f"`{COHORT_WEEK_VIEW}` has no {TWELVE_WEEKS}-week {UG} row for course week "
        f"{THE_COURSE_WEEK}, which one twelve-week section answered. The assertions below would be "
        "vacuous."
    )
    assert row["section_count"] == 1, (
        f"`section_count` is {row['section_count']!r} in the {TWELVE_WEEKS}-week row. One "
        "twelve-week section answered this course week; the other section in this world runs six "
        "weeks, and §5.1 requires a match on both length and level."
    )
    assert row["workload_mean"] == TWELVE_WEEK_HOURS, (
        f"`workload_mean` is {row['workload_mean']!r} in the {TWELVE_WEEKS}-week row, whose one "
        f"section submitted {TWELVE_WEEK_HOURS} hours. {MEAN_IF_THE_LENGTHS_ARE_FOLDED} is the "
        f"six-week section folded in — it submitted {SIX_WEEK_HOURS} hours in the same course "
        "week, in the same term week, at the same level, so length is the only thing keeping the "
        "two apart."
    )


def test_a_section_of_another_length_is_keyed_under_that_length_rather_than_dropped(
    benchmark_world: BenchmarkWorld,
) -> None:
    """Criterion 3's length half, the in side.

    The six-week section has its own row at its own length. §2.2's length set has
    seven members plus the dissertation length, and "most sections are 6-week,
    then 12-week" — so a view that computed twelve-week cohorts and dropped the
    rest would be missing the *commonest* cohort in the institution while
    answering every twelve-week question correctly.

    **The mutation it exists to survive**: a `WHERE length_weeks = 12`, or a
    join to a hand-written length list that has some of §2.2's seven in it.
    """
    world = a_cohort_week_with_two_lengths(benchmark_world)
    require_benchmark_view(world.session, COHORT_WEEK_VIEW)

    row = world.cohort_week(length_weeks=SIX_WEEKS, level=UG, course_week=THE_COURSE_WEEK)
    assert row is not None, (
        f"`{COHORT_WEEK_VIEW}` has no {SIX_WEEKS}-week {UG} row for course week "
        f"{THE_COURSE_WEEK}, which a six-week section answered. §2.2's length set has seven "
        "members and §2.2 says most sections are six-week ones, so a view that answers only for "
        "twelve-week cohorts is missing the common case rather than an edge."
    )
    assert row["section_count"] == 1 and row["workload_mean"] == SIX_WEEK_HOURS, (
        f"The {SIX_WEEKS}-week row is {row}; its one section submitted {SIX_WEEK_HOURS} hours in "
        "its second course week."
    )
