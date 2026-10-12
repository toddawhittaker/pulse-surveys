"""No section outside a reader's purview feeds a named-set figure, over generated worlds — E9-05.

> 2. **No course outside the purview, generated.** Over generated forests,
>    mappings and named sets drawn from random course lists, for every reader
>    and every set, every section contributing to a served named-set figure is
>    inside the reader's purview. Marked `invariant`. The generator draws sets
>    that straddle a purview boundary, and a test asserts it does (MISTAKES
>    entry 15).

**The worlds** are E9-01's `world_plans` (`tests/fixtures/purview_walk.py`):
a containment tree, an assignment forest with assistant-dean insertions,
two-hat people and an instructor edge into a lead on a sibling's course, and a
Lead Faculty mapping. To each this module adds up to three named sets, each a
random non-empty list of the plan's courses. The plan is written by E9-01's
`build_world`, and then given a calendar: every course a `UGGR` number, every
section three weeks from 2026-08-17 (the start-letter map's cohort `2`), with
the term's first three `week` rows and a window per section per week, so every
course week of the one cohort has a cutoff and is published under the pinned
clock.

**What "contributing" is observed as.** E9-05's interface makes
`benchmarks._answered(session, section_ids, cutoffs)` the only caller of the two
set functions, and says the property records the `section_ids` passed to it.
So `_answered` is wrapped, every call `named_set_series` makes for one reader and
one set is recorded, and the union of those section sets is what contributed.

**The expectation is computed from the plan alone** (`docs/MISTAKES.md` entry
19): the reader's purview is `expected_scope` over `expected_purviews` — E9-01's
independent statement of SPEC §2.1 — and a set's sections are the plan's
sections of its member courses. Two assertions: the criterion (nothing recorded
lies outside the purview) and its control (what is recorded is exactly the set's
sections inside the purview, so a read that records nothing cannot pass).

**Which failure a red is, before E9-05 lands:** the property FAILS naming
`named_set_series`; the generator test is green before and after, and a red
there means the generator is broken, not the read.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
from fixtures.benchmark_views import benchmarks_module
from fixtures.comparison_sets import (
    COMPARISON_SET_TABLE,
    LENGTH_COLUMN,
    LEVEL_COLUMN,
    member_of,
    membership_table,
)
from fixtures.named_set_figures import NAMED_SET_SERIES, benchmarks_symbol
from fixtures.purview_walk import (
    LEADERSHIP_ROLES,
    BuiltWorld,
    WorldPlan,
    build_world,
    expected_purviews,
    expected_scope,
    world_plans,
)
from fixtures.supervision import require_table, seed_row, single_primary_key
from fixtures.survey_windows import (
    SECTION_END_COLUMN,
    SECTION_LENGTH_COLUMN,
    SECTION_START_COLUMN,
    SECTION_TABLE,
    SEEDED_COHORTS,
    SURVEY_WINDOW_TABLE,
    TERM_TABLE,
    WEEK_NUMBER_COLUMN,
    WEEK_TABLE,
    WINDOW_CLOSES_COLUMN,
    WINDOW_OPENS_COLUMN,
    WINDOW_SECTION_COLUMN,
    WINDOW_TERM_COLUMN,
    WINDOW_WEEK_COLUMN,
    WINDOWS_BY_TERM_WEEK,
)
from hypothesis import HealthCheck, find, given, settings
from hypothesis import strategies as st
from hypothesis.errors import NoSuchExample
from sqlalchemy import select, update

pytestmark = [pytest.mark.integration, pytest.mark.slow]

DATABASE_BACKED = settings(
    max_examples=15,
    deadline=None,
    # One `supervision_graph`, one transaction, every example writing fresh
    # colleges and fresh people — the arrangement E9-01's properties use.
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
    ],
)

COVERAGE_BUDGET = settings(
    max_examples=2000,
    deadline=None,
    database=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

# The calendar every generated section is given: the start-letter map's
# three-week cohort `2`, so three windows per section are enough to publish every
# course week. Its length and start come from the transcribed map.
THE_COHORT = "2"
LENGTH, FIRST_TERM_WEEK, START = SEEDED_COHORTS[THE_COHORT]
LEVEL = "UGGR"
FIRST_UGGR_NUMBER = 500

KINDS_AND_COUNTS = ("college", "department", "prefix", "course", "section")


@dataclass(frozen=True)
class NamedSetPlan:
    """A `WorldPlan` and the named sets drawn over it, each a tuple of course indexes."""

    world: WorldPlan
    sets: tuple[tuple[int, ...], ...]


@st.composite
def named_set_plans(draw: Any) -> NamedSetPlan:
    """A generated world and up to three named sets drawn from random course lists."""
    plan = draw(world_plans())
    courses = len(plan.course_prefix)
    drawn = draw(
        st.lists(
            st.lists(
                st.integers(min_value=0, max_value=courses - 1),
                min_size=1,
                max_size=courses,
                unique=True,
            ),
            min_size=1,
            max_size=3,
        )
    )
    return NamedSetPlan(world=plan, sets=tuple(tuple(sorted(members)) for members in drawn))


def leaders(plan: WorldPlan) -> list[int]:
    """Planned people holding at least one leadership assignment (E9-01's reading)."""
    return sorted({node.person for node in plan.nodes if node.role in LEADERSHIP_ROLES})


def sections_of(plan: WorldPlan, members: tuple[int, ...]) -> set[int]:
    return {section for section, course in enumerate(plan.section_course) if course in members}


def planned_purview_sections(plan: WorldPlan, person: int) -> frozenset[Any]:
    """A planned person's purview sections, from the plan alone, as plan indexes.

    `expected_purviews` and `expected_scope` read ids through a `BuiltWorld`; an
    identity mapping (each node's id is its index) lets them answer from the plan
    with no database at all, which is what `hypothesis.find` needs.
    """
    counts = {
        "college": plan.college_count,
        "department": len(plan.department_college),
        "prefix": len(plan.prefix_department),
        "course": len(plan.course_prefix),
        "section": len(plan.section_course),
    }
    pure = BuiltWorld(
        plan=plan,
        ids={kind: list(range(counts[kind])) for kind in KINDS_AND_COUNTS},
        persons=list(range(plan.person_count)),
        assignments=list(range(len(plan.nodes))),
        institution=None,
    )
    return expected_scope(pure, expected_purviews(pure), person)["section_ids"]


def straddles_a_purview(drawn: NamedSetPlan) -> bool:
    """Some reader's purview holds some, and not all, of some set's sections."""
    plan = drawn.world
    for person in leaders(plan):
        purview = planned_purview_sections(plan, person)
        for members in drawn.sets:
            sections = sections_of(plan, members)
            if sections & purview and sections - purview:
                return True
    return False


@pytest.mark.invariant
def test_the_generated_named_sets_straddle_a_purview_boundary() -> None:
    """MISTAKES entry 15: the property below is only as strong as the sets it is handed.

    A set wholly inside or wholly outside every reader's purview cannot tell a
    read that narrows the set to the purview from one that does not narrow it,
    or narrows it to nothing. So the generator must draw a set holding sections
    on both sides of some reader's boundary, and this asks it to.

    **Green before E9-05 lands; a red means the generator is broken**, not the
    read. **The mutation this kills:** a `named_set_plans` drawing sets of one
    course, or only of courses nobody's purview holds.
    """
    try:
        found = find(named_set_plans(), straddles_a_purview, settings=COVERAGE_BUDGET)
    except NoSuchExample:
        pytest.fail(
            f"`named_set_plans` drew no set straddling a purview boundary in "
            f"{COVERAGE_BUDGET.max_examples} attempts, so the property below asserts nothing "
            "about the case it exists for (docs/MISTAKES.md entry 15)."
        )
    assert straddles_a_purview(found), f"`find` returned a plan that does not straddle: {found}."


class AnsweredRecorder:
    """`benchmarks._answered`, wrapped: every `section_ids` it is called with, recorded."""

    def __init__(self, original: Any) -> None:
        self.original = original
        self.calls: list[frozenset[str]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if "section_ids" in kwargs:
            section_ids = kwargs["section_ids"]
        elif len(args) > 1:
            section_ids = args[1]
        else:
            pytest.fail(
                f"`_answered` was called as {args!r}, {kwargs!r}; E9-05's interface settles "
                "`_answered(session, section_ids, cutoffs)`."
            )
        self.calls.append(frozenset(str(section) for section in section_ids))
        return self.original(*args, **kwargs)


def recorder_on(monkeypatch: pytest.MonkeyPatch) -> AnsweredRecorder:
    """The recorder in place of `_answered`, installed once per test and reused per example."""
    module = benchmarks_module()
    current = getattr(module, "_answered", None)
    if isinstance(current, AnsweredRecorder):
        return current
    if not callable(current):
        pytest.fail(
            "`app.services.benchmarks` has no `_answered`. E9-05's interface keeps it as the only "
            "caller of the two set functions, and this property records what it is handed."
        )
    recorder = AnsweredRecorder(current)
    monkeypatch.setattr(module, "_answered", recorder)
    return recorder


def give_the_world_a_calendar(graph: Any, world: BuiltWorld) -> Any:
    """Courses at `UGGR`, three-week sections from 2026-08-17, weeks 1-3 and their windows.

    Answers the term's key. The `week` rows are written once per term — every
    example of one property shares the graph's term — and the windows once per
    section, at SPEC §3.1's hand-written Fall 2026 instants.
    """
    session, tables = graph.session, graph.tables
    courses = require_table(tables, "course")
    sections = require_table(tables, SECTION_TABLE)
    weeks = require_table(tables, WEEK_TABLE)
    course_key = single_primary_key(courses)
    section_key = single_primary_key(sections)
    week_key = single_primary_key(weeks)
    term = graph.new_branch(TERM_TABLE)[TERM_TABLE]
    term_id = term[single_primary_key(require_table(tables, TERM_TABLE))]

    for index, course_id in enumerate(world.ids["course"]):
        session.execute(
            update(courses)
            .where(courses.c[course_key] == course_id)
            .values(lms_number=str(FIRST_UGGR_NUMBER + index))
        )
    session.execute(
        update(sections)
        .where(sections.c[section_key].in_(world.ids["section"]))
        .values(
            **{
                SECTION_LENGTH_COLUMN: LENGTH,
                SECTION_START_COLUMN: START,
                SECTION_END_COLUMN: START + timedelta(days=LENGTH * 7 - 1),
            }
        )
    )

    term_column = next(
        column.name
        for column in weeks.columns
        if any(key.column.table.name == TERM_TABLE for key in column.foreign_keys)
    )
    week_ids: dict[int, Any] = {}
    for number in range(FIRST_TERM_WEEK, FIRST_TERM_WEEK + LENGTH):
        found = session.execute(
            select(weeks.c[week_key]).where(
                weeks.c[term_column] == term_id, weeks.c[WEEK_NUMBER_COLUMN] == number
            )
        ).scalar()
        if found is None:
            row = seed_row(
                session, tables, WEEK_TABLE, {TERM_TABLE: term}, **{WEEK_NUMBER_COLUMN: number}
            )
            found = row[week_key]
        week_ids[number] = found

    for section_id in world.ids["section"]:
        for number, week_id in week_ids.items():
            opens_at, closes_at = WINDOWS_BY_TERM_WEEK[number]
            seed_row(
                session,
                tables,
                SURVEY_WINDOW_TABLE,
                {},
                **{
                    WINDOW_SECTION_COLUMN: section_id,
                    WINDOW_WEEK_COLUMN: week_id,
                    WINDOW_TERM_COLUMN: term_id,
                    WINDOW_OPENS_COLUMN: opens_at,
                    WINDOW_CLOSES_COLUMN: closes_at,
                },
            )
    session.flush()
    return term_id


def plant_the_sets(graph: Any, world: BuiltWorld, sets: tuple[tuple[int, ...], ...]) -> list[Any]:
    """One named set per drawn course list, declaring three weeks at `UGGR`; their keys."""
    session, tables = graph.session, graph.tables
    courses = require_table(tables, "course")
    course_key = single_primary_key(courses)
    set_key = single_primary_key(require_table(tables, COMPARISON_SET_TABLE))
    membership = membership_table(tables)

    def seed(name: str, chain: dict[str, Any] | None = None, /, **values: Any) -> Any:
        return seed_row(session, tables, name, chain, **values)

    keys = []
    for members in sets:
        row = seed(COMPARISON_SET_TABLE, {}, **{LENGTH_COLUMN: LENGTH, LEVEL_COLUMN: LEVEL})
        for course in members:
            course_row = dict(
                session.execute(
                    select(courses).where(courses.c[course_key] == world.ids["course"][course])
                )
                .mappings()
                .one()
            )
            member_of(seed, membership, row, course_row)
        keys.append(row[set_key])
    session.flush()
    return keys


@pytest.mark.invariant
@DATABASE_BACKED
@given(drawn=named_set_plans())
def test_every_section_behind_a_named_set_figure_lies_inside_the_readers_purview(
    supervision_graph: Any,
    authz: Any,
    window_settings: Any,
    pinned_benchmark_clock: Any,
    monkeypatch: pytest.MonkeyPatch,
    drawn: NamedSetPlan,
) -> None:
    """For every reader and every set: what `_answered` is handed lies inside her purview.

    **The mutations this kills:** the set's resolved sections used whole; the
    narrowing done by the set's courses' department, or by the reader's
    *teaching* grants, or after the set functions answered rather than before;
    a lead's purview taken unclamped (the planted instructor edge into a lead
    then hands a sibling's section through); cohorts taken from the set rather
    than the purview, which reads sections of the set the reader never holds.

    **The control in the body:** what is recorded must equal the set's sections
    inside the purview — so a read that calls `_answered` with nothing, or never
    calls it, is red rather than vacuously inside.
    """
    plan = drawn.world
    graph = supervision_graph
    session = graph.session
    recorder = recorder_on(monkeypatch)
    read = benchmarks_symbol(NAMED_SET_SERIES)

    world = build_world(graph, plan)
    term_id = give_the_world_a_calendar(graph, world)
    set_keys = plant_the_sets(graph, world, drawn.sets)
    wanted = expected_purviews(world)
    section_ids = world.ids["section"]

    outside: list[str] = []
    inexact: list[str] = []
    for person in leaders(plan):
        held = expected_scope(world, wanted, person)["section_ids"]
        purview = {str(section) for section in held}
        scope = authz.resolve_scope(session, person_id=world.persons[person])
        for members, set_key in zip(drawn.sets, set_keys, strict=True):
            recorder.calls.clear()
            read(session, set_id=set_key, scope=scope, term_id=term_id, settings=window_settings)
            recorded = frozenset().union(*recorder.calls) if recorder.calls else frozenset()
            members_sections = {str(section_ids[s]) for s in sections_of(plan, members)}
            beyond = recorded - purview
            if beyond:
                outside.append(
                    f"person {person}, set of courses {members}: {sorted(beyond)} outside the "
                    "purview"
                )
            if recorded != members_sections & purview:
                inexact.append(
                    f"person {person}, set of courses {members}: recorded {sorted(recorded)}, the "
                    f"set's sections inside the purview are {sorted(members_sections & purview)}"
                )

    assert not outside, (
        f"A named-set figure was computed over sections outside its reader's purview: {outside}. "
        "SPEC §5.5: a leader's named-set figure 'is computed only over the set's sections inside "
        f"the reader's purview'. Plan: {plan}; sets: {drawn.sets}."
    )
    assert not inexact, (
        f"What the named-set read handed the set functions is not the set's sections inside the "
        f"purview: {inexact}. Plan: {plan}; sets: {drawn.sets}."
    )
