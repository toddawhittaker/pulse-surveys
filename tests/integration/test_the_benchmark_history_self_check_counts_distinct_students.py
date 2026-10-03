"""The seeder's self-check counts people and sections, not rows — ticket E5-12.

Criterion 1 asks for counts that are "stated and reproducible ... asserted by a
seed self-check that prints the counts, not by hoping", and the third known trap
says what the counts have to be counts *of*:

    **Counting respondents** — the self-check counts distinct students per
    cohort-week, the unit the minimums compare (entry 50), or its printed
    reassurance is in the wrong currency.

That is the whole subject here. **Nothing in this module asserts anything about the
data the seeder generates** — E4-20's ruling stands and E5-12 repeats it — and
nothing here runs the seeder. What it exercises is the arithmetic the self-check
does over a database, against a world this test planted and knows the answer for.

**Why that arithmetic needs a test of its own, when the world it will really run
over is a world nobody asserts.** The self-check is the only thing standing between
"the demo drive worked" and a benchmark that silently suppresses in front of an
audience: it exits non-zero when the passing cohort is under either default. A
recount that counts *responses* where the minimum counts *people* reports a cohort
as passing that the product will then suppress — `docs/MISTAKES.md` entry 50 in its
exact shape, with a printed reassurance on top of it. And because the seeded world
comfortably clears both minimums by design, the over-count would never show itself
on the drive it was written for.

**One student, two sections — not two responses in one section.** The work order
describes the plant as "a student with two responses in one week", and E2-05's
`uq_response_user_id_section_id_week_id` makes that row impossible inside a single
section: one response per student, per section, per week. The shape that produces
the divergence is a student enrolled in two sections of the same cohort answering
in both, which is the ordinary case rather than an exotic one — SPEC §5.1's
comparison set is every section of a length and level — and it is the same world
`tests/integration/test_a_benchmark_cohort_counts_each_respondent_once.py` uses to
hold E5-03's view to the same unit.

**The interface is the ruling of 2026-09-13**, not this module's guess: the seeder
exports `the_cohort_recount(session, section_codes)`, taking an explicit sequence
of section codes and answering counts per `(length_weeks, level, course_week)` — a
distinct section count and a distinct student count, recounted from the database
and never from the plan. `main()` aims it at the seeder's own codes and separately
compares the answers against the two `benchmark_min_*` configuration values. That
explicit code list is what makes these two tests possible at all: they hand the
recount the codes of a cohort they planted themselves, so the counting is exercised
over a world whose right answer is known — without the drive, and without asserting
anything about the data the seeder generates.

**Guards are in the test bodies** (`docs/MISTAKES.md` entry 44): on a tree where
E5-12 is unbuilt, both tests below are FAILEDs naming the missing script.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_history import (
    SECTION_CODE_COLUMN,
    SECTION_TABLE,
    benchmark_history_module,
    call_recount,
    cohort_week_row,
    respondent_count_of,
    section_count_of,
)
from fixtures.benchmark_views import (
    PRIOR_TERM,
    UG,
    BenchmarkWorld,
)
from fixtures.supervision import require_table
from sqlalchemy import select, update

pytestmark = pytest.mark.integration

# The cohort this world plants: the 12-week undergraduate pair, in the prior term,
# at its first course week. Twelve weeks and `UG` because that is the cohort E5-12
# builds its passing world in — "a 12-week UG in the prior term, matching the hero
# BIOL-310-R7FF" — and the prior term because that is where this seeder's world
# lives; a recount narrowed to the current term would not be the thing under test.
THE_COHORT = "U"
THE_LENGTH = 12
THE_COURSE_WEEK = 1

# Four responses, three people, two sections. Written out rather than computed, so
# that this module's expectation and the recount's answer are not one derivation
# agreeing with itself (`docs/MISTAKES.md` entry 19): the plant below writes each
# one of these rows by hand and the numbers are what a reader gets by counting them.
EXPECTED_RESPONSES = 4
EXPECTED_RESPONDENTS = 3
EXPECTED_SECTIONS = 2

# The second section's own code. `BenchmarkWorld.plant_section` builds a code from
# the cohort letter alone, so two sections of one cohort come out of it carrying
# the same string — which is fine for E5-03's views, keyed by length and level, and
# wrong here: the recount is handed *codes*, and two sections behind one code would
# leave a lookup that resolves a code to a single row looking correct. So the second
# section is given an ordinal of its own, SPEC §2.2's shape (`{startLetter}`
# `{ordinal}{modality}`) with the start letter unchanged, which keeps both sections
# in the same cohort. The first section's code is read back from the database rather
# than written here, because it is that fixture's to choose.
SECOND_SECTION_CODE = f"{THE_COHORT}2WW"

# Workload figures, one per response, all exact halves of an hour so no rounding
# artefact can be mistaken for a miscount. Their values are not asserted anywhere —
# a response has to carry something for the row to be the ordinary shape.
SHARED_HOURS_IN_FIRST = Decimal("2.0")
SHARED_HOURS_IN_SECOND = Decimal("4.0")
FIRST_ONLY_HOURS = Decimal("5.0")
SECOND_ONLY_HOURS = Decimal("6.0")


def give_the_second_section_a_code_of_its_own(world: BenchmarkWorld) -> None:
    """Stamp the second section with its own ordinal, so the two codes differ.

    Written here rather than asked of `BenchmarkWorld`, which builds a section code
    from the cohort letter and is E5-03's fixture rather than this ticket's. The
    column is a stored one — a section's length and dates are what E0-07 derives
    from a code, not the code itself — so this is a value being corrected, never a
    derivation being bypassed.
    """
    table = require_table(world.tables, SECTION_TABLE)
    key = world.key_of(SECTION_TABLE)
    world.session.execute(
        update(table)
        .where(table.c[key] == world.section_id("second"))
        .values({SECTION_CODE_COLUMN: SECOND_SECTION_CODE})
    )
    world.session.flush()


def section_code_of(world: BenchmarkWorld, label: str) -> str:
    """The code one planted section carries, read back from the database.

    Read rather than constructed, so the codes handed to the recount are the ones
    its lookup will actually meet. A test that passed the strings it *meant* to
    write would be asking the recount about sections that might not exist
    (`docs/MISTAKES.md` entry 30).
    """
    table = require_table(world.tables, SECTION_TABLE)
    key = world.key_of(SECTION_TABLE)
    world.session.flush()
    return str(
        world.session.execute(
            select(table.c[SECTION_CODE_COLUMN]).where(table.c[key] == world.section_id(label))
        ).scalar_one()
    )


def a_prior_term_cohort_one_student_answered_in_twice(world: BenchmarkWorld) -> BenchmarkWorld:
    """Two prior-term sections of one cohort, four responses, three people.

    The shared student is enrolled in both sections, which is what makes their two
    responses "in cohort scope" rather than two unrelated rows.
    """
    world.build()
    world.build_prior_term()
    world.plant_section("first", cohort=THE_COHORT, level=UG, term=PRIOR_TERM)
    world.plant_section("second", cohort=THE_COHORT, level=UG, term=PRIOR_TERM)
    give_the_second_section_a_code_of_its_own(world)

    shared = world.student("e5-12-shared-respondent", enrolled_in=("first", "second"))
    world.respond(
        "first", course_week=THE_COURSE_WEEK, student=shared, workload=SHARED_HOURS_IN_FIRST
    )
    world.respond(
        "second", course_week=THE_COURSE_WEEK, student=shared, workload=SHARED_HOURS_IN_SECOND
    )
    world.respond(
        "first", course_week=THE_COURSE_WEEK, subject="e5-12-first-only", workload=FIRST_ONLY_HOURS
    )
    world.respond(
        "second",
        course_week=THE_COURSE_WEEK,
        subject="e5-12-second-only",
        workload=SECOND_ONLY_HOURS,
    )
    world.session.flush()
    return world


def the_recounted_row(world: BenchmarkWorld) -> Any:
    """`the_cohort_recount` over this world's two sections, narrowed to the planted week.

    The codes are read back off the two sections and handed in as the ruling's
    second parameter. That they are two *different* codes is asserted first: the
    plant means to plow two sections into one cohort, and a fixture that gave them
    one code would leave "this cohort week holds two sections" resting on something
    this module never checked (`docs/MISTAKES.md` entry 3).
    """
    module = benchmark_history_module()
    codes = [section_code_of(world, "first"), section_code_of(world, "second")]
    assert len(set(codes)) == EXPECTED_SECTIONS, (
        f"This world's two sections carry {codes}, which is not {EXPECTED_SECTIONS} distinct "
        "codes. The recount is handed section codes, so two sections behind one string would let "
        "a lookup that resolves a code to a single row answer correctly by accident."
    )
    rows = call_recount(module, world.session, codes)
    assert rows, (
        "The self-check's recount answered no rows at all over a world holding "
        f"{EXPECTED_RESPONSES} responses in one cohort week, for the two section codes {codes} it "
        "was handed. Every assertion below would be a statement about an empty list, which is "
        "`docs/MISTAKES.md` entry 3 — so this is asserted first and separately from what the "
        "numbers are."
    )
    return cohort_week_row(rows, length_weeks=THE_LENGTH, level=UG, course_week=THE_COURSE_WEEK)


def test_the_self_checks_recount_counts_a_student_who_answered_in_two_sections_once(
    benchmark_world: BenchmarkWorld,
) -> None:
    """E5-12's third known trap, and `docs/MISTAKES.md` entry 50: the unit is people.

    Three people wrote the four responses this cohort week holds. The number the
    self-check compares against `benchmark_min_respondents` is three.

    **The mutation this kills**: `COUNT(*)`, or `COUNT(user_id)` without `DISTINCT`,
    in the recount's query. Against the world the seeder actually builds — twenty
    students per section, seventeen to twenty responding each week, three sections —
    that mutation inflates every cohort-week figure by however many students are
    enrolled in more than one section, and the self-check's printed line says the
    cohort passes. Whether it *does* pass is then decided by E5-04 counting a
    different number, and the two disagree in the direction that looks fine until
    the benchmark suppresses in front of an audience.

    **The near miss it must not fire on**: the two section-only respondents. A
    recount that collapsed to "one row per cohort week" or deduplicated on something
    coarser than the person would answer one or two here rather than three, and the
    plant is built so an over-count and an under-count are different numbers.

    **The control**: the row exists at all, asserted in `the_recounted_row` before
    any figure is read off it.
    """
    world = a_prior_term_cohort_one_student_answered_in_twice(benchmark_world)

    row = the_recounted_row(world)

    assert respondent_count_of(row) == EXPECTED_RESPONDENTS, (
        f"The recount says {respondent_count_of(row)} respondents in the "
        f"{THE_LENGTH}-week {UG} cohort's course week {THE_COURSE_WEEK}; three people wrote its "
        f"{EXPECTED_RESPONSES} responses. One of them is enrolled in both sections and answered in "
        f"each, so a count of {EXPECTED_RESPONSES} is a count of responses wearing the name of a "
        "count of people. E5-12's known traps: the self-check counts distinct students per "
        "cohort-week, 'the unit the minimums compare'; `docs/MISTAKES.md` entry 50 is the incident "
        "— a threshold that protects people crossed by a count of something else. The whole row, "
        f"as the recount answered it: {row!r}"
    )


def test_the_self_checks_recount_counts_the_sections_a_cohort_week_holds_not_its_responses(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The other half of criterion 1's comparison: the section minimum's own unit.

    The self-check "exits nonzero if the passing cohort is under either default or
    the thin cohort is not under the section minimum", so the section figure decides
    as much as the respondent figure does — and the thin cohort exists precisely to
    sit under it. Two sections wrote the four responses here.

    **The mutation this kills**: a section figure that is really a row count or a
    response count. It cannot be seen on the passing cohort, which has three
    sections and hundreds of responses and is over the minimum on any reading; it
    shows up on the **thin** cohort, where a count of responses is far above a
    minimum expressed in sections and the self-check therefore reports a thin cohort
    that is not thin. The world then demonstrates nothing, and the suppression the
    ticket exists to show off never happens.

    **The near miss it must not fire on**: the shared respondent. Deduplicating
    sections by the *person* who answered in them, or counting enrollments, would
    give a different number from two here.
    """
    world = a_prior_term_cohort_one_student_answered_in_twice(benchmark_world)

    row = the_recounted_row(world)

    assert section_count_of(row) == EXPECTED_SECTIONS, (
        f"The recount says {section_count_of(row)} sections in the {THE_LENGTH}-week {UG} cohort's "
        f"course week {THE_COURSE_WEEK}; this world planted {EXPECTED_SECTIONS}, carrying "
        f"{EXPECTED_RESPONSES} responses between them. The section count is what the thin cohort's "
        "whole reason for existing is measured by — 'below the 3-section minimum, so every figure "
        "for it must suppress' — and a figure in the wrong currency there reports a cohort as thin "
        f"or not thin for reasons unrelated to how many sections it has. The whole row: {row!r}"
    )
