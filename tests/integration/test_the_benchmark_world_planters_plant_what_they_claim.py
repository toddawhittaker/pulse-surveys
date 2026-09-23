"""The three planters E5-04 adds to `BenchmarkWorld`, checked before anything is measured over them.

E5-04's worlds turn on three things this suite could not plant before: which
courses a Lead Faculty leads, what a named comparison set contains, and how many
distinct people answered in how many sections. Every acceptance criterion in
that ticket is a statement about a figure computed over one of those, so a
planter that quietly wrote the wrong thing would make the criteria tests green
or red for a reason that has nothing to do with the service.

**These tests must be green on today's tree**, before E5-04 exists. They read
relations E5-01 and E5-03 already ship — `public.lead_faculty_course`,
`comparison_set` with its membership table, and `benchmark_set_week` — and they
assert only what the planters claim. A red here is a defect in
`tests/fixtures/benchmark_views.py`, and reading it first will save reading the
criteria modules at all.

**Why a control module rather than assertions inside the criteria tests.** A
world builder that under-plants makes a suppression test pass for the wrong
reason, which is `docs/MISTAKES.md` entry 3 with the machinery as the culprit
rather than the code. Pinning the machinery once, where a failure names the
planter, is the cheaper half of that discipline; the criteria modules then plant
both counts explicitly and assert the outcome.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    UG,
    BenchmarkWorld,
    spread,
)
from fixtures.comparison_sets import (
    COMPARISON_SET_TABLE,
    COURSE_TABLE,
    LENGTH_COLUMN,
    LEVEL_COLUMN,
    comparison_set_table,
    members_of,
    membership_table,
    one_key_column_to,
)
from fixtures.supervision import single_primary_key
from sqlalchemy import text

pytestmark = pytest.mark.integration

# ADR 0046's second view — "which courses a person leads" — whose columns
# `SANCTIONED_VIEW_COLUMNS` in `tests/integration/test_identity_grants.py` pins as
# `(person_id, course_id)`. The planter writes `lead_faculty_mapping` rows and
# this is the read over them, which is the same read E5-04's default set is
# resolved through.
LEAD_FACULTY_COURSE = """
    SELECT course_id FROM public.lead_faculty_course WHERE person_id = :person
"""

TWELVE_WEEKS = 12
THE_COURSE_WEEK = 2

# Hours and a rating, carried so that the responses this module plants are
# ordinary ones. Neither number is under test here.
HOURS = Decimal("2.5")
A_RATING = Decimal("4")

# The world the count control is planted in: two sections, five people, and one
# of the five answering in both — so the response count and the respondent count
# are deliberately different numbers (`docs/MISTAKES.md` entry 50's shape, which
# is the shape E5-04's criterion 2 is measured in).
COUNT_LABELS = ("count-one", "count-two")
COUNT_RESPONDENTS = 5
COUNT_DOUBLE_ANSWERERS = 1


def test_the_lead_planter_maps_one_person_to_every_course_it_was_given(
    benchmark_world: BenchmarkWorld,
) -> None:
    """`world.lead(name, *labels)` produces exactly those courses under one person.

    The default set is "the same Lead Faculty's courses", read through
    `public.lead_faculty_course`, so this is the fact every criterion-3 and
    criterion-5 world rests on.

    **The sibling lead is the control**, and it is not decoration: a planter that
    wrote one mapping row per *course* under whichever person it seeded last
    would satisfy a test that only counted rows. Two leads in one world, each
    asked about separately, is the shape §4.1 item 2 cares about and the shape
    that catches it.

    **The defect it would catch:** the mapping seeded through a fresh chain each
    time, so "the same lead" is three different people and every default set
    resolves to one course.
    """
    world = benchmark_world.build()
    for label in ("hers-one", "hers-two", "his-one"):
        world.plant_section(label, cohort="U", level=UG)

    hers = world.lead("hers", "hers-one", "hers-two")
    his = world.lead("his", "his-one")
    world.session.flush()

    person_key = world.key_of("person")
    her_courses = {
        row[0]
        for row in world.session.execute(text(LEAD_FACULTY_COURSE), {"person": hers[person_key]})
    }
    his_courses = {
        row[0]
        for row in world.session.execute(text(LEAD_FACULTY_COURSE), {"person": his[person_key]})
    }

    course_key = world.key_of(COURSE_TABLE)
    expected = {world.course_of(label)[course_key] for label in ("hers-one", "hers-two")}
    assert her_courses == expected, (
        f"`public.lead_faculty_course` answers {sorted(map(str, her_courses))} for the lead this "
        f"world gave two courses; it should answer {sorted(map(str, expected))}. Every default-set "
        "world in E5-04 is built by this planter, so a mapping written under a different person — "
        "or not written at all — makes those tests statements about an empty population."
    )
    assert his_courses == {world.course_of("his-one")[course_key]}, (
        f"The second lead's courses are {sorted(map(str, his_courses))} rather than the one course "
        "this world gave them. Two leads under one department is the world a default set has to be "
        "distinguishable in; a planter that puts every course under one person makes that world "
        "impossible to build and the criterion untestable."
    )


def test_the_comparison_set_planter_stores_the_declared_pair_and_its_members(
    benchmark_world: BenchmarkWorld,
) -> None:
    """`world.comparison_set(...)` writes ADR 0164's shape: a declared length and level, plus courses.

    ADR 0164: "a named set is a list of member courses plus one declared length
    and one declared level", membership at course grain. E5-04 resolves a set to
    "the member courses' sections of the declared length", so a planter that
    stored the pair and no members, or members under the wrong set, would make
    criterion 6's empty-set test indistinguishable from criterion 6 passing by
    accident.

    **The empty set is planted here too**, because it is a legitimate value (ADR
    0164: "a set may be empty") and because a planter that refused it would leave
    criterion 6 with nothing to drive.

    **The defect it would catch:** `member_of` handed the course row where the
    set row belongs, which the seeding walker would fill *somehow* and which
    would leave the set empty with no error anywhere.
    """
    world = benchmark_world.build()
    for label in ("member-one", "member-two", "outsider"):
        world.plant_section(label, cohort="U", level=UG)

    populated = world.comparison_set(
        "populated", length_weeks=TWELVE_WEEKS, level=UG, courses_of=("member-one", "member-two")
    )
    world.comparison_set("empty", length_weeks=TWELVE_WEEKS, level=UG)
    world.session.flush()

    set_table = comparison_set_table(world.tables)
    stored = dict(populated)
    assert stored[LENGTH_COLUMN] == TWELVE_WEEKS, (
        f"The set's declared `{LENGTH_COLUMN}` is {stored[LENGTH_COLUMN]!r} rather than "
        f"{TWELVE_WEEKS}. E5-04 resolves a named set to the member courses' sections *of the "
        "declared length*, so this column is half the resolution."
    )
    assert (
        str(stored[LEVEL_COLUMN]) == UG
    ), f"The set's declared `{LEVEL_COLUMN}` is {stored[LEVEL_COLUMN]!r} rather than {UG!r}."

    membership = membership_table(world.tables)
    rows = members_of(world.session, membership, populated)
    course_column = one_key_column_to(membership, COURSE_TABLE, world.key_of(COURSE_TABLE))
    held = {row[course_column] for row in rows}
    course_key = world.key_of(COURSE_TABLE)
    expected = {world.course_of(label)[course_key] for label in ("member-one", "member-two")}
    assert held == expected, (
        f"The set holds the courses {sorted(map(str, held))}; this world gave it "
        f"{sorted(map(str, expected))}. The outsider section's course is in this world and in no "
        "set, which is what makes 'the sections of the set's member courses' a narrower answer "
        "than 'every section'."
    )

    empty_rows = members_of(world.session, membership, world.comparison_sets["empty"])
    assert empty_rows == [], (
        f"The set planted with no courses holds {len(empty_rows)} membership rows. An empty set is "
        "a value ADR 0164 admits and E5-04's criterion 6 is about; a planter that cannot produce "
        "one leaves that criterion with nothing to drive."
    )

    assert single_primary_key(set_table) in stored, (
        f"The planted `{COMPARISON_SET_TABLE}` row carries no primary key value, so no test can "
        "hand a `set_id` to the service."
    )


def test_the_answer_plan_plants_the_respondents_and_the_responses_it_was_given(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The two counts the minimums are compared against, planted and read back separately.

    Five people answer across two sections and one of them answers in both, so
    there are six responses from five people. Both numbers are written in this
    test and both are read back from `benchmark_set_week`, which is the same
    function E5-04's figures are computed from.

    **This is the control that makes `docs/MISTAKES.md` entry 50's world
    trustworthy.** Criterion 2 needs a world where the responses clear the
    respondent minimum and the *people* do not, and the only way to know such a
    world was actually built is to read the two counts apart from each other.

    **The defect it would catch:** `answer_the_plan` enrolling but not
    responding, responding once per student regardless of the plan, or dealing
    every student into the same section — each of which produces a world whose
    counts are not the ones the criterion test wrote down.
    """
    world = benchmark_world.build()
    for label in COUNT_LABELS:
        world.plant_section(label, cohort="U", level=UG)

    plan = dict(spread(COUNT_LABELS, respondents=COUNT_RESPONDENTS, subject_prefix="e5-04-control"))
    doubled = sorted(plan)[0]
    plan[doubled] = (COUNT_LABELS[0], COUNT_LABELS[1])

    respondents = len(plan)
    responses = sum(len(labels) for labels in plan.values())
    assert (respondents, responses) == (
        COUNT_RESPONDENTS,
        COUNT_RESPONDENTS + COUNT_DOUBLE_ANSWERERS,
    ), (
        f"This test's own plan holds {respondents} people and {responses} responses, and it was "
        f"written to hold {COUNT_RESPONDENTS} and {COUNT_RESPONDENTS + COUNT_DOUBLE_ANSWERERS}. "
        "The plan is the premise of everything below it."
    )

    world.answer_the_plan(
        plan, course_week=THE_COURSE_WEEK, workload=HOURS, instructor_rating=A_RATING
    )

    rows = [row for row in world.set_week(*COUNT_LABELS) if row["course_week"] == THE_COURSE_WEEK]
    assert len(rows) == 1, (
        f"`benchmark_set_week` answered {len(rows)} rows at course week {THE_COURSE_WEEK} over the "
        f"two planted sections: {rows}. One course week over one set is one row."
    )
    row = rows[0]

    assert row["respondent_count"] == respondents, (
        f"`respondent_count` is {row['respondent_count']!r} where {respondents} distinct people "
        f"answered, one of them in both sections. This is the number "
        "`benchmark_min_respondents_default` is compared against."
    )
    assert row["response_count"] == responses, (
        f"`response_count` is {row['response_count']!r} where the plan submitted {responses} "
        "responses. Asserted beside the count above because the two differing is the whole point "
        "of this world."
    )
    assert row["section_count"] == len(COUNT_LABELS), (
        f"`section_count` is {row['section_count']!r} over {len(COUNT_LABELS)} sections that were "
        "both answered. A planter that dealt every student into one section leaves the other with "
        "no rows, and a section nobody answered in counts towards no figure — so the section count "
        "a criterion test planted would not be the one it measured."
    )


def test_the_planted_world_carries_a_section_the_set_function_can_be_asked_about(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The anti-vacuity control for this module: the world is real and readable.

    Every assertion above reads something back, so an empty world would fail
    them — except one: a world whose sections were never planted would fail
    `course_of` inside the fixture, which reads as a broken test. This asserts
    the ordinary case outright, so the module states its own premise.

    **The defect it would catch:** `plant_section` no longer recording the course
    row from the walker's chain, which every other test here would report as a
    missing planter rather than as what it is.
    """
    world = benchmark_world.build()
    world.plant_section("only", cohort="U", level=UG)
    world.session.flush()

    course: Any = world.course_of("only")
    assert course[world.key_of(COURSE_TABLE)] is not None, (
        "The planted section carries no course row. Two of E5-04's three populations are defined "
        "over courses — one lead's courses, and a named set's member courses — so a world without "
        "them cannot express either."
    )
