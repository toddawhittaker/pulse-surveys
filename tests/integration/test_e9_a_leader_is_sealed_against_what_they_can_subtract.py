"""§4.1 item 7 for a leader, through the drill-down and the series routes — E9-12 done-whens 5, 6 and 7.

> 5. **§4.1 item 7 for a leader.** The drill-down's comparison and university
>    figures are suppressed when the remainder after the reader's known set
>    (leadership purview and taught sections, §5.1) is non-empty and below a
>    minimum, one respondent either side; the named-set series is suppressed
>    below 3 sections or 10 respondents inside the purview. Marked `invariant`.
> 6. **Both hats, through the drill-down route.** A Math chair teaches Biology
>    section T; the drill-down's university line U is suppressed when U less
>    Math less T is non-empty and one respondent below a minimum, and shown at
>    the minimum; the twin world, with the chair not teaching T and U less Math
>    meeting both minimums, shows U. Marked `invariant`.
> 7. **The university line's two extra pieces, through the route.** With U less
>    the known set meeting both minimums, U is suppressed when (i) a default
>    comparison set of a purview section, less the known set, is non-empty and
>    thin, or (ii) the university less the known set and less those sets is
>    non-empty and thin. Each case has a shown twin, one respondent either side.
>    Marked `invariant`.

SPEC §5.1: "When a leader reads a section's report through the drill-down (§5.5),
or a named set's figures on a roll-up, the seal treats the leader exactly as it
treats an instructor, with the same sections as her sections — every section in
the person's leadership purview together with every section the person teaches."
E9-05 proved the seal at the service; this module proves it **through the routes
a leader uses**, with a leader's real session, over HTTP as `pulse_app`.

**The world** is E4-07's report world (`report_door`: the hero section `F1WW`,
taught by the door's instructor) with E5-05's benchmark cohort planted around it
(`tests/fixtures/report_benchmarks.py`: the hero's lead leads three more six-week
sections at the hero's level in **the hero's department**, ten people at course
week 2). This module adds a **second department** of the same college and plants
sections there; "Math" below is the hero's department and "Biology" the second.
Every section is six weeks at the hero's level in the hero's term, answered at
course week 2, which is the week every drill-down here reads. Every count is an
offset from the configured minimums, read from `Settings`, never a transcribed
number.

**Readers** are minted with `LeadReviewWorld`'s machinery over the bare report
world (`readers_at_the_report_door`): the Math chair, and for the series a dean of
the college. **Every withheld figure is asserted beside a shown one in the same
payload or the same world** (`docs/MISTAKES.md` entry 3): the default-set figures
on the same drill-down, the hero's own instructor reading the same report, or the
dean reading the same set.

**Expected green on today's branch**; each test names its mutation (done-when 9)
and its near miss.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fixtures.benchmark_views import COURSE_NUMBER_COLUMN, COURSE_TABLE
from fixtures.comparison_sets import (
    COMPARISON_SET_TABLE,
    LENGTH_COLUMN,
    LEVEL_COLUMN,
    member_of,
    membership_table,
)
from fixtures.e9_invariant_pass import (
    body_of,
    drill_down_url,
    readers_at_the_report_door,
    series_url,
)
from fixtures.lead_review import Reader
from fixtures.report_api import ReportDoor
from fixtures.report_benchmarks import (
    COMPARISON_POPULATION,
    FIGURE_FIELD,
    MEAN_FIELD,
    MEDIAN_FIELD,
    REASON_FIELD,
    SHARED_COURSE_NUMBER,
    SUPPRESSED_FIELD,
    THE_LEAD,
    UNIVERSITY_POPULATION,
    WEEK_CLEAR,
    WEEK_THIN_PEOPLE,
    WEEK_THIN_SECTIONS,
    PlantedBenchmarkCohort,
    answer_once,
    numbers_of,
    plant_a_section_beside,
    points_of,
    teach,
    workload_figures,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import SEEDED_COHORTS

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)
REPORTED_WEEK = WEEK_CLEAR
SAME_LETTER = "F"
SIX_WEEKS = 6
CHAIR_ROLE = "CHAIR"
DEAN_ROLE = "DEAN"
DEPARTMENT_TABLE = "department"
COLLEGE_TABLE = "college"
SERIES_FIGURES = ("instructor_mean", "course_mean", "workload_mean", "workload_median")


# ---------------------------------------------------------------------------
# Reading a figure.
# ---------------------------------------------------------------------------


def is_withheld(figure: Any) -> bool:
    """A member in the chokepoint's suppressed state: the flag, a reason, no figure, no number."""
    return (
        isinstance(figure, dict)
        and figure.get(SUPPRESSED_FIELD) is True
        and bool(figure.get(REASON_FIELD))
        and figure.get(FIGURE_FIELD) is None
        and not numbers_of(figure)
    )


def is_shown(figure: Any) -> bool:
    """A member shown: not suppressed, and carrying its statistic."""
    return (
        isinstance(figure, dict)
        and figure.get(SUPPRESSED_FIELD) is False
        and bool(numbers_of(figure))
    )


def members_of(body: Any, population: str) -> dict[str, Any]:
    """One report's members for one population at course week 2: both points, mean, median."""
    found: dict[str, Any] = {
        f"the {stream} {population} point": points_of(body, stream, population).get(REPORTED_WEEK)
        for stream in STREAMS
    }
    workload = workload_figures(body, population)
    for name in (MEAN_FIELD, MEDIAN_FIELD):
        found[f"the {population} workload {name}"] = workload[name]
    return found


def not_shown(members: dict[str, Any]) -> list[str]:
    return [where for where, figure in members.items() if not is_shown(figure)]


def not_withheld(members: dict[str, Any]) -> dict[str, Any]:
    return {where: figure for where, figure in members.items() if not is_withheld(figure)}


# ---------------------------------------------------------------------------
# Building: a second department, courses in it, answers.
# ---------------------------------------------------------------------------


def key(cohort: PlantedBenchmarkCohort, table: str, row: Any) -> Any:
    return row[single_primary_key(require_table(cohort.world.tables, table))]


def the_home_department(cohort: PlantedBenchmarkCohort) -> dict[str, Any]:
    """The hero's own containment chain down to its department ("Math")."""
    if DEPARTMENT_TABLE not in cohort.spine:
        pytest.fail(f"The cohort's spine holds {sorted(cohort.spine)} and no department.")
    return dict(cohort.spine)


def a_second_department(cohort: PlantedBenchmarkCohort) -> dict[str, Any]:
    """A new department ("Biology") under the hero's college; its chain."""
    chain = {
        level: cohort.spine[level]
        for level in ("institution", COLLEGE_TABLE)
        if level in cohort.spine
    }
    cohort.world.seed(DEPARTMENT_TABLE, chain)
    if DEPARTMENT_TABLE not in chain:
        pytest.fail("Seeding a department left none in the chain. A broken world, not a red.")
    assert str(key(cohort, DEPARTMENT_TABLE, chain[DEPARTMENT_TABLE])) != str(
        key(cohort, DEPARTMENT_TABLE, cohort.spine[DEPARTMENT_TABLE])
    ), "The second department is the hero's own. A broken world, not a red."
    return chain


def sections_in(
    cohort: PlantedBenchmarkCohort, department: dict[str, Any], prefix: str, count: int
) -> list[str]:
    """`count` six-week sections at the hero's level, each on a new course of `department`."""
    labels = [f"{prefix}-{index}" for index in range(count)]
    for label in labels:
        course = cohort.world.seed(
            COURSE_TABLE, dict(department), **{COURSE_NUMBER_COLUMN: SHARED_COURSE_NUMBER}
        )
        plant_a_section_beside(cohort, label, letter=SAME_LETTER, course=course)
    return labels


def answered(
    cohort: PlantedBenchmarkCohort,
    labels: list[str],
    people: int,
    tag: str,
    week: int = REPORTED_WEEK,
) -> None:
    """`people` new students, dealt round-robin over `labels`, each answering one course week."""
    for index in range(people):
        answer_once(
            cohort,
            labels[index % len(labels)],
            subject=f"e9-12-{tag}-{week}-{index}",
            course_week=week,
        )


def minimums(contract: Any) -> tuple[int, int]:
    found = contract.minimums()
    return int(found[contract.minimum_sections]), int(found[contract.minimum_respondents])


def a_chair_of(
    readers: Any, cohort: PlantedBenchmarkCohort, chain: dict[str, Any], label: str
) -> Reader:
    department = key(cohort, DEPARTMENT_TABLE, chain[DEPARTMENT_TABLE])
    return readers.a_leader(label, grants=((CHAIR_ROLE, department),))


def drill(readers: Any, reader: Reader, door: ReportDoor) -> Any:
    url = drill_down_url(door.rows.taught_section_id, REPORTED_WEEK)
    return body_of(readers.ask("GET", url, token=reader.token), f"{reader.label}'s drill-down")


def the_instructors_report(door: ReportDoor) -> Any:
    body, _answered = door.payload(course_week=REPORTED_WEEK)
    return body


# ---------------------------------------------------------------------------
# Done-when 5, the comparison figure: a default set reaching into Biology.
# ---------------------------------------------------------------------------


def a_default_set_reaching_biology(
    door: ReportDoor, contract: Any, plant: Callable[..., Any], *, biology_people: int
) -> PlantedBenchmarkCohort:
    """The hero's lead also leads the minimum number of sections in Biology, answered by `biology_people`.

    The hero's default set is then the cohort's three Math sections (ten people)
    and the Biology ones. The Math chair knows Math, so what is left of the
    default set after her known set is the Biology sections.
    """
    sections, _people = minimums(contract)
    cohort = plant(door, minimums=contract.minimums())
    biology = a_second_department(cohort)
    labels = sections_in(cohort, biology, "dw5-biology", sections)
    cohort.world.lead(THE_LEAD, *labels)
    answered(cohort, labels, biology_people, "dw5-biology")
    door.commit()
    return cohort


def test_the_default_set_is_withheld_from_a_chair_whose_remainder_is_one_respondent_short(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    committed_rows: Any,
    web_identity: Any,
    configured_env: dict[str, str],
) -> None:
    """The Math chair's drill-down: the default set less Math is Biology, one respondent short — withheld.

    **The control, same world:** the hero's own instructor, who knows the hero
    only, is served every default-set member on the same report.

    **The mutation it kills:** the reader dropped from the seal on the drill-down
    (`section_benchmarks(..., scope=None)` from `leadership_report`); the reader's
    known set taken as her taught sections only. **The near miss it spares:** the
    twin below, one respondent more, shown.
    """
    _sections, people = minimums(report_api_contract)
    cohort = a_default_set_reaching_biology(
        report_door, report_api_contract, benchmark_cohort, biology_people=people - 1
    )
    readers = readers_at_the_report_door(report_door, committed_rows, web_identity, configured_env)
    chair = a_chair_of(readers, cohort, the_home_department(cohort), "dw5-math-chair")

    control = members_of(the_instructors_report(report_door), COMPARISON_POPULATION)
    read = members_of(drill(readers, chair, report_door), COMPARISON_POPULATION)

    assert not not_shown(control), (
        f"The control failed: the hero's instructor is not served {not_shown(control)}; what she "
        "can subtract leaves the whole default set, which meets both minimums."
    )
    leaked = not_withheld(read)
    assert not leaked, (
        f"The Math chair is served default-set members {leaked}. She reads every Math section's "
        "own figures, so the default set less Math is Biology's sections, one respondent below "
        "the minimum (SPEC §5.1)."
    )


def test_the_default_set_is_shown_to_a_chair_whose_remainder_meets_both_minimums(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    committed_rows: Any,
    web_identity: Any,
    configured_env: dict[str, str],
) -> None:
    """Done-when 5's comparison twin: Biology's part at exactly the respondent minimum — shown.

    **The mutation it kills:** a seal that withholds from any leader whose
    purview touches the population, or reads the minimum as "more than".
    """
    _sections, people = minimums(report_api_contract)
    cohort = a_default_set_reaching_biology(
        report_door, report_api_contract, benchmark_cohort, biology_people=people
    )
    readers = readers_at_the_report_door(report_door, committed_rows, web_identity, configured_env)
    chair = a_chair_of(readers, cohort, the_home_department(cohort), "dw5-math-chair")

    read = members_of(drill(readers, chair, report_door), COMPARISON_POPULATION)
    assert not not_shown(read), (
        f"The Math chair is not served {not_shown(read)}; what is left of the default set after "
        "Math meets both minimums."
    )


# ---------------------------------------------------------------------------
# Done-whens 5 (university) and 6: U less Math (less T, when the chair teaches it).
# ---------------------------------------------------------------------------


def a_biology_block(
    door: ReportDoor,
    contract: Any,
    plant: Callable[..., Any],
    readers: Any,
    *,
    block_people: int,
    t_people: int,
    chair_teaches_t: bool,
) -> Reader:
    """Biology holds T and an unled block; Math holds a block of its own; the chair chairs Math.

    - **T**, one section in Biology on a course whose lead leads nothing else (so
      its default set is empty), answered by `t_people`; the chair teaches it
      when asked.
    - **The Biology block**, the section minimum of unled sections, answered by
      `block_people`. It is what is left of U after Math (and T).
    - **The Math block**, the section minimum of sections in Math each led by a
      lead who leads nothing else, answered by the respondent minimum. The chair
      knows it; the hero's instructor does not — so U less what *the instructor*
      knows (the Math block and everything in Biology) always meets both
      minimums, and a withheld line is the leader's seal and never the
      instructor's.

    With `t_people` zero, T is empty (done-when 5's plain university pair).
    """
    sections, people = minimums(contract)
    cohort = plant(door, minimums=contract.minimums())
    math = the_home_department(cohort)
    biology = a_second_department(cohort)
    t = sections_in(cohort, biology, "dw6-t", 1)
    cohort.world.lead("e9-12-t-lead", *t)
    block = sections_in(cohort, biology, "dw6-block", sections)
    math_block = sections_in(cohort, math, "dw6-math-block", sections)
    for index, label in enumerate(math_block):
        cohort.world.lead(f"e9-12-math-block-lead-{index}", label)
    answered(cohort, t, t_people, "dw6-t")
    answered(cohort, block, block_people, "dw6-block")
    answered(cohort, math_block, people, "dw6-math-block")
    door.commit()
    chair = a_chair_of(readers, cohort, the_home_department(cohort), "dw6-math-chair")
    if chair_teaches_t:
        teach(door, cohort.world.section_id(t[0]), person=chair.person_id)
        door.commit()
    return chair


def test_the_university_line_is_withheld_from_a_chair_whose_remainder_is_one_short(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    committed_rows: Any,
    web_identity: Any,
    configured_env: dict[str, str],
) -> None:
    """Done-when 5, the university: U less Math is Biology's block, one respondent short — withheld.

    **The controls:** the default-set members in the same payload are shown (the
    seal is not withholding everything), and the hero's instructor is served the
    university line on the same report.

    **The mutation it kills:** the reader dropped from the university seal; the
    remainder computed as U less the reported section only. **The near miss:**
    the twin below.
    """
    _sections, people = minimums(report_api_contract)
    readers = readers_at_the_report_door(report_door, committed_rows, web_identity, configured_env)
    chair = a_biology_block(
        report_door,
        report_api_contract,
        benchmark_cohort,
        readers,
        block_people=people - 1,
        t_people=0,
        chair_teaches_t=False,
    )
    body = drill(readers, chair, report_door)
    control = members_of(the_instructors_report(report_door), UNIVERSITY_POPULATION)

    assert not not_shown(members_of(body, COMPARISON_POPULATION)), (
        "The control failed: the chair's default-set members are not shown, though the whole "
        "default set lies in Math."
    )
    assert not not_shown(
        control
    ), f"The control failed: the hero's instructor is not served {not_shown(control)}."
    leaked = not_withheld(members_of(body, UNIVERSITY_POPULATION))
    assert not leaked, (
        f"The Math chair is served university members {leaked}; U less Math is one department's "
        "sections answered by one respondent fewer than the minimum."
    )


def test_the_university_line_is_shown_to_a_chair_whose_remainder_meets_both_minimums(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    committed_rows: Any,
    web_identity: Any,
    configured_env: dict[str, str],
) -> None:
    """Done-when 5's university twin: Biology's block at the respondent minimum — shown.

    **The mutation it kills:** "the remainder must be empty" (every chair's
    university line withheld).
    """
    _sections, people = minimums(report_api_contract)
    readers = readers_at_the_report_door(report_door, committed_rows, web_identity, configured_env)
    chair = a_biology_block(
        report_door,
        report_api_contract,
        benchmark_cohort,
        readers,
        block_people=people,
        t_people=0,
        chair_teaches_t=False,
    )
    read = members_of(drill(readers, chair, report_door), UNIVERSITY_POPULATION)
    assert not not_shown(read), f"The Math chair is not served {not_shown(read)}."


def test_both_hats_a_math_chair_teaching_biology_t_is_withheld_u_one_respondent_short(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    committed_rows: Any,
    web_identity: Any,
    configured_env: dict[str, str],
) -> None:
    """Done-when 6: she teaches T; U less Math less T is the block, one respondent short — withheld.

    T has one respondent and the block one fewer than the minimum, so U less
    Math alone (T and the block) meets both minimums — only her teaching hat makes
    the remainder thin.

    **The control, same world:** the default-set members on the same payload are
    shown.

    **The mutation it kills:** a leader sealed without her taught sections — her
    leadership purview alone as her known set. **The near misses it spares:** the
    two twins below.
    """
    _sections, people = minimums(report_api_contract)
    readers = readers_at_the_report_door(report_door, committed_rows, web_identity, configured_env)
    chair = a_biology_block(
        report_door,
        report_api_contract,
        benchmark_cohort,
        readers,
        block_people=people - 1,
        t_people=1,
        chair_teaches_t=True,
    )
    body = drill(readers, chair, report_door)
    assert not not_shown(
        members_of(body, COMPARISON_POPULATION)
    ), "The control failed: the chair's default-set members are not shown."
    leaked = not_withheld(members_of(body, UNIVERSITY_POPULATION))
    assert not leaked, (
        f"The Math chair who teaches T is served university members {leaked}. She knows Math and "
        "T, and U less both is one respondent below the minimum (SPEC §5.1: every hat counts)."
    )


def test_both_hats_at_the_minimum_the_university_line_is_shown(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    committed_rows: Any,
    web_identity: Any,
    configured_env: dict[str, str],
) -> None:
    """Done-when 6's shown twin: she teaches T, and U less Math less T is at the minimum — shown.

    **The mutation it kills:** a teaching hat that withholds the university line
    outright, whatever the remainder.
    """
    _sections, people = minimums(report_api_contract)
    readers = readers_at_the_report_door(report_door, committed_rows, web_identity, configured_env)
    chair = a_biology_block(
        report_door,
        report_api_contract,
        benchmark_cohort,
        readers,
        block_people=people,
        t_people=1,
        chair_teaches_t=True,
    )
    read = members_of(drill(readers, chair, report_door), UNIVERSITY_POPULATION)
    assert not not_shown(read), f"The Math chair who teaches T is not served {not_shown(read)}."


def test_both_hats_twin_world_a_chair_not_teaching_t_is_shown_u(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    committed_rows: Any,
    web_identity: Any,
    configured_env: dict[str, str],
) -> None:
    """Done-when 6's twin world: the same rows, the chair does not teach T — U less Math meets both.

    The world of the withheld test above, less the teaching grant: U less Math
    is T and the block, the section minimum plus one and exactly the respondent
    minimum.

    **The mutation it kills:** the seal counting sections a person does not
    teach (any section of the reported section's level she could see the
    roster of, say) as hers.
    """
    _sections, people = minimums(report_api_contract)
    readers = readers_at_the_report_door(report_door, committed_rows, web_identity, configured_env)
    chair = a_biology_block(
        report_door,
        report_api_contract,
        benchmark_cohort,
        readers,
        block_people=people - 1,
        t_people=1,
        chair_teaches_t=False,
    )
    read = members_of(drill(readers, chair, report_door), UNIVERSITY_POPULATION)
    assert not not_shown(read), (
        f"The Math chair who does not teach T is not served {not_shown(read)}; U less Math is T "
        "and the block, which meet both minimums."
    )


# ---------------------------------------------------------------------------
# Done-when 7: the university line's two extra pieces.
# ---------------------------------------------------------------------------


def a_lead_straddling_math_and_biology(
    door: ReportDoor,
    contract: Any,
    plant: Callable[..., Any],
    readers: Any,
    *,
    lead_set: int,
    rest: int,
) -> Reader:
    """Math holds `s0`, led by L, who also leads `l…` in Biology; Biology also holds unled `r…`.

    The chair knows Math. U less Math is `l…` and `r…`; (i) `s0`'s default set
    less Math is `l…`, answered by `lead_set`; (ii) U less Math less every
    default set of a Math section is `r…`, answered by `rest`. Answers the chair.
    """
    sections, _people = minimums(contract)
    cohort = plant(door, minimums=contract.minimums())
    math = the_home_department(cohort)
    biology = a_second_department(cohort)
    s0 = sections_in(cohort, math, "dw7-s0", 1)
    lead_sections = sections_in(cohort, biology, "dw7-l", sections)
    rest_sections = sections_in(cohort, biology, "dw7-r", sections)
    cohort.world.lead("e9-12-lead-l", *s0, *lead_sections)
    answered(cohort, s0, 2, "dw7-s0")
    answered(cohort, lead_sections, lead_set, "dw7-l")
    answered(cohort, rest_sections, rest, "dw7-r")
    door.commit()
    return a_chair_of(readers, cohort, math, "dw7-math-chair")


@pytest.mark.parametrize(
    ("piece", "lead_offset", "rest_offset"),
    [("(i) a default set of a purview section", -1, 0), ("(ii) the rest of the university", 0, -1)],
    ids=["first-extra-piece", "second-extra-piece"],
)
def test_a_thin_extra_piece_withholds_the_university_line(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    committed_rows: Any,
    web_identity: Any,
    configured_env: dict[str, str],
    piece: str,
    lead_offset: int,
    rest_offset: int,
) -> None:
    """Done-when 7: U less Math meets both minimums, one extra piece is one respondent short — withheld.

    **The controls, same world:** the default-set members on the same payload
    are shown, and the hero's instructor is served the university line.

    **The mutations it kills:** (i) the first extra piece skipped for a leader, or
    built from her taught sections only (empty here); (ii) the second extra piece
    skipped, or computed less the reported section's default set only (empty
    here, so `l…` stays in and the piece clears). **The near miss it spares:**
    the twin below.
    """
    _sections, people = minimums(report_api_contract)
    readers = readers_at_the_report_door(report_door, committed_rows, web_identity, configured_env)
    chair = a_lead_straddling_math_and_biology(
        report_door,
        report_api_contract,
        benchmark_cohort,
        readers,
        lead_set=people + lead_offset,
        rest=people + rest_offset,
    )
    body = drill(readers, chair, report_door)
    control = members_of(the_instructors_report(report_door), UNIVERSITY_POPULATION)

    assert not not_shown(
        members_of(body, COMPARISON_POPULATION)
    ), "The control failed: the chair's default-set members are not shown."
    assert not not_shown(
        control
    ), f"The control failed: the hero's instructor is not served {not_shown(control)}."
    leaked = not_withheld(members_of(body, UNIVERSITY_POPULATION))
    assert not leaked, (
        f"The Math chair is served university members {leaked}, though {piece} less her known set "
        "is one respondent below the minimum (SPEC §5.1's extra pieces of the university line)."
    )


def test_both_extra_pieces_at_the_minimum_leave_the_university_line_shown(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    committed_rows: Any,
    web_identity: Any,
    configured_env: dict[str, str],
) -> None:
    """Done-when 7's shown twin, for both cases: `l…` and `r…` each at the respondent minimum.

    **The mutation it kills:** an extra piece that withholds whenever it is
    non-empty, or reads the minimum as "more than".
    """
    _sections, people = minimums(report_api_contract)
    readers = readers_at_the_report_door(report_door, committed_rows, web_identity, configured_env)
    chair = a_lead_straddling_math_and_biology(
        report_door, report_api_contract, benchmark_cohort, readers, lead_set=people, rest=people
    )
    read = members_of(drill(readers, chair, report_door), UNIVERSITY_POPULATION)
    assert not not_shown(read), f"The Math chair is not served {not_shown(read)}."


# ---------------------------------------------------------------------------
# Done-when 5, the named-set series: inside the purview, both minimums.
# ---------------------------------------------------------------------------


def a_set_over_the_cohort_and_a_biology_course(
    door: ReportDoor, contract: Any, plant: Callable[..., Any]
) -> tuple[Any, PlantedBenchmarkCohort]:
    """A six-week named set over the cohort's three Math courses and one Biology course.

    E5-05's cohort answers week 2 with three sections and ten people, week 3 with
    three and nine, week 4 with two and ten. The Biology section answers weeks 3
    and 4 with the respondent minimum each, so a series counting it would clear
    both thin weeks. Answers the set's key and the cohort.
    """
    _sections, people = minimums(contract)
    cohort = plant(door, minimums=contract.minimums())
    biology = a_second_department(cohort)
    outside = sections_in(cohort, biology, "dw5-set-outside", 1)
    for week in (WEEK_THIN_PEOPLE, WEEK_THIN_SECTIONS):
        answered(cohort, outside, people, "dw5-set-outside", week=week)
    world = cohort.world
    stored = world.seed(
        COMPARISON_SET_TABLE, {}, **{LENGTH_COLUMN: SIX_WEEKS, LEVEL_COLUMN: cohort.level}
    )
    for label in (*cohort.labels, *outside):
        member_of(world.seed, membership_table(world.tables), stored, cohort.course_of(label))
    door.commit()
    return stored[single_primary_key(require_table(world.tables, COMPARISON_SET_TABLE))], cohort


def series_weeks(readers: Any, reader: Reader, set_id: Any, door: ReportDoor) -> dict[int, Any]:
    """The set's series as one reader is served it: the cohort-F weeks, by course week."""
    start = SEEDED_COHORTS[SAME_LETTER][2].isoformat()
    body = body_of(
        readers.ask("GET", series_url(set_id, door.rows.term_id), token=reader.token),
        f"{reader.label}'s series",
    )
    cohorts = [c for c in body.get("cohorts", []) if str(c.get("section_start_date")) == start]
    assert len(cohorts) == 1, f"{reader.label}'s series holds cohorts {body.get('cohorts')!r}."
    return {int(week["course_week"]): week for week in cohorts[0]["weeks"]}


def test_the_named_set_series_is_sealed_below_either_minimum_inside_the_purview(
    report_door: ReportDoor,
    report_api_contract: Any,
    benchmark_cohort: Callable[..., Any],
    committed_rows: Any,
    web_identity: Any,
    configured_env: dict[str, str],
) -> None:
    """The Math chair's series: week 2 shown; week 3 (one respondent short) and week 4 (one section short) withheld.

    Inside her purview the set is the three Math sections; the Biology member is
    outside it and must not be counted. **The control, same set:** the college's
    dean, whose purview holds the Biology section too, is served weeks 3 and 4
    — so the Biology answers are real and do clear the minimums when the reader
    holds them.

    **The mutation it kills:** the series computed over the set's sections
    whatever the purview (weeks 3 and 4 then clear for the chair); either
    minimum dropped from the series; the minimum read as "more than" (week 2
    then withheld). **The near miss it spares:** every leader listing the set.
    """
    set_id, cohort = a_set_over_the_cohort_and_a_biology_course(
        report_door, report_api_contract, benchmark_cohort
    )
    readers = readers_at_the_report_door(report_door, committed_rows, web_identity, configured_env)
    chair = a_chair_of(readers, cohort, the_home_department(cohort), "dw5-series-math-chair")
    college = key(cohort, COLLEGE_TABLE, cohort.spine[COLLEGE_TABLE])
    dean = readers.a_leader("dw5-series-dean", grants=((DEAN_ROLE, college),))

    chairs = series_weeks(readers, chair, set_id, report_door)
    deans = series_weeks(readers, dean, set_id, report_door)

    def figures(week: Any) -> dict[str, Any]:
        return {name: week.get(name) for name in SERIES_FIGURES}

    for course_week in (WEEK_THIN_PEOPLE, WEEK_THIN_SECTIONS):
        assert course_week in deans and not not_shown(figures(deans[course_week])), (
            f"The control failed: the dean is not served course week {course_week} "
            f"({deans.get(course_week)!r}); with the Biology section inside her purview the week "
            "meets both minimums."
        )
    assert REPORTED_WEEK in chairs and not not_shown(figures(chairs[REPORTED_WEEK])), (
        f"The chair is not served course week {REPORTED_WEEK} ({chairs.get(REPORTED_WEEK)!r}): "
        "three sections and ten people inside her purview meet both minimums."
    )
    for course_week, why in (
        (WEEK_THIN_PEOPLE, "one respondent below the minimum"),
        (WEEK_THIN_SECTIONS, "one section below the minimum"),
    ):
        assert course_week in chairs, f"The chair's series has no course week {course_week}."
        leaked = not_withheld(figures(chairs[course_week]))
        assert not leaked, (
            f"Course week {course_week} is served to the Math chair: {leaked}. Inside her purview "
            f"the set is {why}; the Biology member is outside it (SPEC §5.5, §4.1 item 7)."
        )
