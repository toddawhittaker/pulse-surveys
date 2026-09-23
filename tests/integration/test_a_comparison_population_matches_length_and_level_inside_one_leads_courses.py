"""SPEC §5.1's matching rule, asserted where the lead filter cannot stand in for it.

> To be comparable, sections must match on **both** length … *and* level … The
> default comparison set is the same Lead Faculty's courses filtered to matching
> length+level … The university-wide line is all same-length+level sections
> institution-wide.

**Why this module exists** (`docs/tickets/e5/deferred.md`, "The length half of
§5.1's matching has no test that fails without it"). With the length predicate
removed from the service's section matching, the whole backend suite stayed
green, because every planted world's other-length sections belonged to courses
the hero's lead did not hold: the lead filter excluded them on its own, and no
university world held another length at all. So in this world **every course is
led by the hero's lead**, and the only thing left to keep a section out is the
match on length or level.

**The world, in one table.** One lead holds every course below. The two
12-week and 8-week sections on one course are the case the deferred entry names —
a led course with sections of two lengths — and cohort `X` starts on the same
Monday as cohort `U` (both 17 August 2026 in the start-letter map), so start date
cannot be what separates them.

    label       course     level  cohort  length
    hero        its own    UG     U       12
    twelve      shared     UG     U       12
    eight       shared     UG     X        8
    eight-too   its own    UG     X        8
    uggr        its own    UGGR   U       12
    uggr-too    its own    UGGR   U       12

Every section is answered in course week 2 (which all of them run), so no
resolver can leave a section out for having no data.

**Each test asserts both directions of one boundary.** The section that must be
included is the control — a resolver that answered nothing would satisfy every
exclusion here (`docs/MISTAKES.md` entry 3) — and the forbidden sections are
named and asserted absent, rather than the answer compared with a full expected
set, so a failure says which half of the match gave way (`docs/MISTAKES.md`
entry 2: assert the forbidden state). Each boundary is also asked from the
other side — an 8-week reader against 12-week sections, a `UGGR` reader against
`UG` ones — because a match written as "no longer than" or "no higher than"
passes a test asked from one side only.

**Green on arrival, deliberately.** The service already filters on both halves;
this module is a pin proven by mutation, not a red. The mutations are named in
each docstring.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    COHORTS_BY_TERM,
    COURSE_NUMBER_COLUMN,
    COURSE_NUMBER_FOR_LEVEL,
    COURSE_TABLE,
    CURRENT_TERM,
    RESOLVE_DEFAULT_SET,
    RESOLVE_UNIVERSITY,
    UG,
    UGGR,
    BenchmarkWorld,
    PlantedSection,
    benchmarks_api,
    spread,
)
from fixtures.report_benchmarks import course_levels, lead_faculty_course_ids, section_lengths
from fixtures.survey_windows import (
    COHORT_SECTION_MODALITY,
    COHORT_SECTION_ORDINAL,
    SECTION_CODE_COLUMN,
    SECTION_END_COLUMN,
    SECTION_LENGTH_COLUMN,
    SECTION_START_COLUMN,
    SECTION_TABLE,
    TERM_TABLE,
)

pytestmark = [pytest.mark.integration]

THE_LEAD = "the-lead"

TWELVE_WEEK_COHORT = "U"
EIGHT_WEEK_COHORT = "X"
TWELVE_WEEKS = 12
EIGHT_WEEKS = 8

THE_COURSE_WEEK = 2
AN_HOURS_VALUE = Decimal("2.5")
A_RATING = Decimal("4")

HERO = "hero"
TWELVE = "twelve"
EIGHT = "eight"
EIGHT_TOO = "eight-too"
UGGR_SECTION = "uggr"
UGGR_TOO = "uggr-too"

# What each section is, as planted. Read back from the database by
# `the_world_is_what_this_module_says` before any resolver is asked anything.
PLANTED_LENGTH = {
    HERO: TWELVE_WEEKS,
    TWELVE: TWELVE_WEEKS,
    EIGHT: EIGHT_WEEKS,
    EIGHT_TOO: EIGHT_WEEKS,
    UGGR_SECTION: TWELVE_WEEKS,
    UGGR_TOO: TWELVE_WEEKS,
}
PLANTED_LEVEL = {
    HERO: UG,
    TWELVE: UG,
    EIGHT: UG,
    EIGHT_TOO: UG,
    UGGR_SECTION: UGGR,
    UGGR_TOO: UGGR,
}

RESOLVERS = (RESOLVE_DEFAULT_SET, RESOLVE_UNIVERSITY)


def sections_on_one_course(world: BenchmarkWorld, level: str, *sections: tuple[str, str]) -> None:
    """Several sections, one per `(label, cohort)`, all hung on one new course.

    `BenchmarkWorld.plant_section` seeds a fresh course for every section, and
    the case the deferred entry names is one course running two lengths. So the
    course is seeded once here and each section is seeded under it, the same
    three steps `plant_the_benchmark_cohort` in `tests/fixtures/report_benchmarks.py`
    takes for its set, and registered in `world.sections` so the ordinary
    `respond` and `section_id` machinery reaches it.

    The level is planted by choosing the course's number, never by writing a
    level: `course.level` is a stored generated column (ADR 0015).
    """
    chain = world.spine()
    course = world.seed(
        COURSE_TABLE, chain, **{COURSE_NUMBER_COLUMN: COURSE_NUMBER_FOR_LEVEL[level]}
    )
    chain[TERM_TABLE] = world.term_row(CURRENT_TERM)
    for label, cohort in sections:
        length_weeks, first_term_week, start = COHORTS_BY_TERM[CURRENT_TERM][cohort]
        row = world.seed(
            SECTION_TABLE,
            dict(chain),
            **{
                SECTION_CODE_COLUMN: f"{cohort}{COHORT_SECTION_ORDINAL}{COHORT_SECTION_MODALITY}",
                SECTION_LENGTH_COLUMN: length_weeks,
                SECTION_START_COLUMN: start,
                SECTION_END_COLUMN: start + timedelta(days=length_weeks * 7 - 1),
            },
        )
        world.sections[label] = PlantedSection(
            label=label,
            row=row,
            term=CURRENT_TERM,
            cohort=cohort,
            level=level,
            length_weeks=length_weeks,
            first_term_week=first_term_week,
            start_date=start,
            course=course,
        )


def the_world(world: BenchmarkWorld) -> Any:
    """Plant the table in this module's docstring, and answer the lead's person row."""
    world.build()
    world.plant_section(HERO, cohort=TWELVE_WEEK_COHORT, level=UG)
    sections_on_one_course(world, UG, (TWELVE, TWELVE_WEEK_COHORT), (EIGHT, EIGHT_WEEK_COHORT))
    world.plant_section(EIGHT_TOO, cohort=EIGHT_WEEK_COHORT, level=UG)
    world.plant_section(UGGR_SECTION, cohort=TWELVE_WEEK_COHORT, level=UGGR)
    world.plant_section(UGGR_TOO, cohort=TWELVE_WEEK_COHORT, level=UGGR)

    # `EIGHT` is not named: it shares `TWELVE`'s course, and SPEC §8 maps one
    # lead per course, so naming both would write the same mapping twice.
    lead = world.lead(THE_LEAD, HERO, TWELVE, EIGHT_TOO, UGGR_SECTION, UGGR_TOO)

    labels = tuple(PLANTED_LENGTH)
    world.answer_the_plan(
        dict(spread(labels, respondents=len(labels), subject_prefix="e5-14-matching")),
        course_week=THE_COURSE_WEEK,
        workload=AN_HOURS_VALUE,
        instructor_rating=A_RATING,
        course_rating=A_RATING,
    )
    world.session.flush()
    return lead


def the_world_is_what_this_module_says(world: BenchmarkWorld, lead: Any) -> None:
    """The premises, read back from the database before any resolver is asked.

    Three facts carry every test here, and each is the reason one of them can
    fail: every section's course is led by the one lead (so the lead filter
    excludes nothing), the lengths are as planted, and the levels are as planted.
    A world where `eight`'s course were not led would make its absence from the
    default set the lead filter's doing — the exact state the deferred entry
    records.
    """
    labels = list(PLANTED_LENGTH)
    course_key = world.key_of(COURSE_TABLE)

    assert world.course_of(EIGHT)[course_key] == world.course_of(TWELVE)[course_key], (
        f"`{EIGHT}` and `{TWELVE}` are meant to be two sections of one course, and they hang on "
        "two. The deferred entry's case is a led course running two lengths."
    )

    led = lead_faculty_course_ids(world, lead)
    unled = [label for label in labels if world.course_of(label)[course_key] not in led]
    assert not unled, (
        f"The lead is mapped to {len(led)} courses and these sections' courses are not among "
        f"them: {unled}. Every course in this world has to be led by the one lead, or the lead "
        "filter excludes a section before the length or level match is ever consulted."
    )

    lengths = dict(zip(labels, section_lengths(world, world.section_ids(*labels)), strict=True))
    assert (
        lengths == PLANTED_LENGTH
    ), f"The sections' stored lengths are {lengths}; this module was written for {PLANTED_LENGTH}."

    courses = [world.course_of(label) for label in labels]
    levels = dict(zip(labels, course_levels(world, courses), strict=True))
    assert levels == PLANTED_LEVEL, (
        f"The sections' courses carry the levels {levels}; this module was written for "
        f"{PLANTED_LEVEL}. SPEC §8's bands are a stored generated column off the course number."
    )


def resolved_for(world: BenchmarkWorld, resolver: str, reader: str) -> set[Any]:
    """One resolver's answer for one reading section, as a set of section ids."""
    api = benchmarks_api()
    return set(api[resolver](world.session, section_id=world.section_id(reader)))


def names_of(world: BenchmarkWorld, section_ids: set[Any]) -> list[str]:
    """Section ids read back as this module's labels, for failure messages."""
    by_id = {world.section_id(label): label for label in PLANTED_LENGTH}
    return sorted(by_id.get(section_id, str(section_id)) for section_id in section_ids)


def assert_the_boundary(
    world: BenchmarkWorld,
    resolver: str,
    reader: str,
    *,
    included: str,
    excluded: tuple[str, ...],
    half: str,
) -> None:
    """The control first, then the forbidden sections, for one resolver and one reader."""
    answer = resolved_for(world, resolver, reader)
    assert world.section_id(included) in answer, (
        f"The control failed before the assertion it protects: `{resolver}` for `{reader}` "
        f"answers {names_of(world, answer)} and leaves out `{included}`, which matches it on "
        "length and level and is led by the same lead. Until it is included, the exclusions "
        "below are satisfied by a resolver that answers nothing."
    )
    leaked = [label for label in excluded if world.section_id(label) in answer]
    assert not leaked, (
        f"`{resolver}` for `{reader}` ({PLANTED_LENGTH[reader]} weeks, {PLANTED_LEVEL[reader]}) "
        f"answers {names_of(world, answer)}, which includes {leaked}: a different {half}, under "
        "the same lead. SPEC §5.1: 'to be comparable, sections must match on both length and "
        "level' — 'an 8-week graduate course is never averaged against a 12-week undergraduate "
        "one', and 'levels match exactly; no level is folded into another'."
    )


@pytest.mark.parametrize("resolver", RESOLVERS, ids=list(RESOLVERS))
def test_a_twelve_week_readers_population_leaves_out_its_leads_eight_week_sections(
    benchmark_world: BenchmarkWorld, pinned_benchmark_clock: Any, resolver: str
) -> None:
    """The deferred entry's done-when: another length on a led course is out, the same is in.

    `twelve` (same course as `eight`, same length as the hero) is included;
    `eight` (a section of that same led course) and `eight-too` (a led course of
    its own) are excluded — from the default set and from the university
    population alike.

    **The mutation this kills:** `Section.length_weeks == hero.length_weeks`
    dropped from `_matching_sections` in `app.services.benchmarks`. Both eight-week
    sections then enter both populations, because nothing else in their way — the
    lead holds their courses and they share the hero's level.
    **Its near miss:** the level half dropped instead, which this test does not
    see (every section named here is `UG`) and
    `test_a_ug_readers_population_leaves_out_its_leads_uggr_sections` kills.
    """
    lead = the_world(benchmark_world)
    the_world_is_what_this_module_says(benchmark_world, lead)

    assert_the_boundary(
        benchmark_world,
        resolver,
        HERO,
        included=TWELVE,
        excluded=(EIGHT, EIGHT_TOO),
        half="length",
    )


@pytest.mark.parametrize("resolver", RESOLVERS, ids=list(RESOLVERS))
def test_an_eight_week_readers_population_leaves_out_its_leads_twelve_week_sections(
    benchmark_world: BenchmarkWorld, pinned_benchmark_clock: Any, resolver: str
) -> None:
    """The same boundary asked from the shorter side.

    Read from `eight`: `eight-too` is included; `hero` and `twelve` — the second
    a section of `eight`'s own course — are excluded. A 12-week section's week 2
    is not an 8-week section's week 2 in any sense §5.1 compares.

    **The mutation this kills:** the length predicate dropped (as above), and a
    one-sided comparison in its place — `length_weeks <= hero.length_weeks` or
    `>=` — which passes whichever of these two tests reads from the side the
    inequality happens to allow. **Its near miss:** matching on the *course*
    rather than the section's length (a course "runs" a length), which puts
    `twelve` in `eight`'s population because they share a course; that is
    refused here by name.
    """
    lead = the_world(benchmark_world)
    the_world_is_what_this_module_says(benchmark_world, lead)

    assert_the_boundary(
        benchmark_world,
        resolver,
        EIGHT,
        included=EIGHT_TOO,
        excluded=(HERO, TWELVE),
        half="length",
    )


@pytest.mark.parametrize("resolver", RESOLVERS, ids=list(RESOLVERS))
def test_a_ug_readers_population_leaves_out_its_leads_uggr_sections(
    benchmark_world: BenchmarkWorld, pinned_benchmark_clock: Any, resolver: str
) -> None:
    """The level half, in the same world: `UGGR` sections of the hero's length are out.

    Read from the hero (`UG`, 12 weeks): `twelve` is included; `uggr` and
    `uggr-too`, same length and same lead, are excluded. SPEC §5.1's own example:
    "a `UGGR` section is compared against other `UGGR` sections and not against
    `UG` or `GR` ones".

    **The mutation this kills:** the level predicate dropped from
    `_matching_sections` — the near miss of the length mutation above, asserted
    here so that neither half of the match can be removed with the suite green.
    **Its near miss:** the length predicate dropped instead, which this test does
    not see (every section named here runs 12 weeks) and the two length tests
    above kill.
    """
    lead = the_world(benchmark_world)
    the_world_is_what_this_module_says(benchmark_world, lead)

    assert_the_boundary(
        benchmark_world,
        resolver,
        HERO,
        included=TWELVE,
        excluded=(UGGR_SECTION, UGGR_TOO),
        half="level",
    )


@pytest.mark.parametrize("resolver", RESOLVERS, ids=list(RESOLVERS))
def test_a_uggr_readers_population_leaves_out_its_leads_ug_sections(
    benchmark_world: BenchmarkWorld, pinned_benchmark_clock: Any, resolver: str
) -> None:
    """The level boundary asked from the other side.

    Read from `uggr`: `uggr-too` is included; `hero` and `twelve`, `UG` sections
    of the same length under the same lead, are excluded.

    **The mutation this kills:** the level predicate dropped, and any one-way
    fold — `UGGR` readers matched against `UG` as well as `UGGR` because
    dual-credit is "undergraduate too" — which SPEC §5.1 forbids by name ("no
    level is folded into another") and which the `UG`-side test above cannot
    see. **Its near miss:** the fold written the other way (`UG` readers taking
    `UGGR` sections), killed by the `UG`-side test.
    """
    lead = the_world(benchmark_world)
    the_world_is_what_this_module_says(benchmark_world, lead)

    assert_the_boundary(
        benchmark_world,
        resolver,
        UGGR_SECTION,
        included=UGGR_TOO,
        excluded=(HERO, TWELVE),
        half="level",
    )
