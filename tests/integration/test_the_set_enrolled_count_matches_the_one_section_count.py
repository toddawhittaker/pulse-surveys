"""The set form of the enrolled count gives each section the answer it gets alone — E9-07 fix round R1.

The roll-up reads every section's enrolled count in one call,
`reporting._enrolled_students_of(session, *, weeks, settings) -> dict[UUID,
int]`, where the report reads one section at a time,
`reporting._enrolled_students(session, *, section, week, settings) -> int`. The
set form has two per-section rules to keep: a student counts only if still
enrolled when **that section's** window opens, and a member of **that
section's** staff is not counted. A set form that checked every enrolment
against the earliest opening in the set, or that pooled the sections' staff,
would agree with the one-section form for a single section and disagree for two.

**The world** is E4-03's report world, committed (`committed_report_world`), with
two sections of different cohorts:
  - A, cohort `U` (12 weeks from 2026-08-17), read at its course week 1, whose
    window opens 2026-08-21;
  - B, cohort `R` (12 weeks from 2026-09-07), read at its course week 1, whose
    window opens 2026-09-11.
Enrolled, each from the section's own start date:
  - `leaver`, in A and B, `ended_on` 2026-09-08: after A opens, before B opens.
    Counts in A, not in B.
  - `steady`, in A and B, never ended. Counts in both.
  - `a_only`, in A, never ended. Counts in A.
  - `teacher`, a user linked to a person who holds an `INSTRUCTOR` assignment on
    A and nothing on B; enrolled in A and B. Not counted in A (staff), counted in
    B.
So A counts 3 (`leaver`, `steady`, `a_only`) and B counts 2 (`steady`,
`teacher`).

Each `_SectionWeek` is built from the section's own `survey_window` row.
Reads run on `pulse_app`'s session (`docs/MISTAKES.md` entry 46).

**Expected on ca363fa8:** green; the code is believed right. A red is an
assertion naming which section disagrees and with what.
"""

from datetime import date
from typing import Any

import pytest
from fixtures.report_views import ReportWorld
from fixtures.supervision import single_primary_key
from fixtures.survey_windows import (
    SEEDED_COHORTS,
    WINDOW_CLOSES_COLUMN,
    WINDOW_OPENS_COLUMN,
)

pytestmark = pytest.mark.integration

EARLY, LATE = "U", "R"
COURSE_WEEK = 1
LEAVER_ENDED_ON = date(2026, 9, 8)
ENROLLMENT_TABLE = "enrollment"
USER_TABLE = "user"
SECTION_TABLE = "section"
PERSON_TABLE = "person"
STARTED_ON = "started_on"
ENDED_ON = "ended_on"

# Hand-derived from the world in the module docstring.
EXPECTED = {EARLY: 3, LATE: 2}


def term_week_of(cohort: str) -> int:
    _length, first_term_week, _start = SEEDED_COHORTS[cohort]
    return first_term_week + COURSE_WEEK - 1


def a_user(world: ReportWorld, label: str) -> Any:
    return world.seed(USER_TABLE, world.people_chain, lms_user_id=f"e9-07-r1-{label}")


def enrol(world: ReportWorld, user: Any, cohort: str, *, ended_on: date | None = None) -> None:
    world.seed(
        ENROLLMENT_TABLE,
        {},
        **{
            world.link(ENROLLMENT_TABLE, USER_TABLE): user[world.key_of(USER_TABLE)],
            world.link(ENROLLMENT_TABLE, SECTION_TABLE): world.section_id(cohort),
            STARTED_ON: SEEDED_COHORTS[cohort][2],
            ENDED_ON: ended_on,
        },
    )


def test_the_set_enrolled_count_equals_each_sections_own_count_and_the_hand_count(
    committed_report_world: ReportWorld,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    application_session: Any,
    configured_env: dict[str, str],
) -> None:
    """`_enrolled_students_of({A: wA, B: wB})` == each section alone == {A: 3, B: 2}.

    **The control:** the hand counts differ between A and B, and each section's
    window opens on a different day, so a set form that treats the two alike
    cannot match both.

    **The mutations it kills:** the `ended_on` re-check made once against the
    earliest opening in the set (B would count `leaver`: 3); one section's staff
    applied to another, or the staff pooled (B would drop `teacher`: 1).
    **The near miss it spares:** any grouping of the reads that keeps both rules
    per section.
    """
    from app.config import Settings
    from app.services import reporting

    for name in ("_enrolled_students_of", "_enrolled_students", "_SectionWeek"):
        if not hasattr(reporting, name):
            pytest.fail(f"`app.services.reporting` has no `{name}`; the settled interface has it.")
    section_model = getattr(reporting, "Section", None)
    if section_model is None:
        pytest.fail(
            "`app.services.reporting` names no `Section`; `_enrolled_students` takes one, so this "
            "test loads the row through the same model."
        )

    world = committed_report_world
    world.build(cohort=EARLY)
    world.section(LATE)
    windows = {cohort: world.window(term_week_of(cohort), cohort) for cohort in (EARLY, LATE)}

    leaver, steady, a_only, teacher = (
        a_user(world, label) for label in ("leaver", "steady", "a-only", "teacher")
    )
    for cohort in (EARLY, LATE):
        enrol(world, leaver, cohort, ended_on=LEAVER_ENDED_ON)
        enrol(world, steady, cohort)
        enrol(world, teacher, cohort)
    enrol(world, a_only, EARLY)

    person_link = sorted(
        {
            item.parent.name
            for item in metadata_tables[PERSON_TABLE].foreign_keys
            if item.column.table.name == USER_TABLE
        }
    )[0]
    person = world.seed(PERSON_TABLE, {}, **{person_link: teacher[world.key_of(USER_TABLE)]})
    committed_rows.graph.assign(
        "INSTRUCTOR",
        scope=world.section_id(EARLY),
        person=person[single_primary_key(metadata_tables[PERSON_TABLE])],
    )
    committed_rows.commit()

    opens = {cohort: windows[cohort][WINDOW_OPENS_COLUMN] for cohort in (EARLY, LATE)}
    assert opens[EARLY].date() < LEAVER_ENDED_ON < opens[LATE].date(), (
        f"The windows open {opens}; the leaver's last day {LEAVER_ENDED_ON} must fall between "
        "them. A broken world, not a red."
    )
    assert EXPECTED[EARLY] != EXPECTED[LATE], "The hand counts must differ (the control)."

    weeks = {
        world.section_id(cohort): reporting._SectionWeek(
            week_id=world.week_id(term_week_of(cohort)),
            term_week=term_week_of(cohort),
            course_week=COURSE_WEEK,
            opens_at=windows[cohort][WINDOW_OPENS_COLUMN],
            closes_at=windows[cohort][WINDOW_CLOSES_COLUMN],
        )
        for cohort in (EARLY, LATE)
    }
    settings = Settings()
    try:
        together = reporting._enrolled_students_of(
            application_session, weeks=weeks, settings=settings
        )
        alone = {
            section_id: reporting._enrolled_students(
                application_session,
                section=application_session.get(section_model, section_id),
                week=week,
                settings=settings,
            )
            for section_id, week in weeks.items()
        }
    finally:
        application_session.rollback()

    by_cohort = {cohort: world.section_id(cohort) for cohort in (EARLY, LATE)}
    expected = {by_cohort[cohort]: count for cohort, count in EXPECTED.items()}
    named = {
        cohort: (together.get(section_id), alone.get(section_id))
        for cohort, section_id in by_cohort.items()
    }
    assert alone == expected, (
        f"(set form, one section alone) per cohort: {named}; the hand counts are {EXPECTED}. The "
        "one-section count disagrees with the hand count, so either the world or the tier rules "
        "differ from this module's reading."
    )
    assert dict(together) == alone, (
        f"(set form, one section alone) per cohort: {named}. The set form must give each section "
        "the count it gets alone: the leaver is checked against that section's own opening, and "
        "only that section's staff are dropped."
    )
