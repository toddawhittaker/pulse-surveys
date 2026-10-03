"""E5-03's controls — the world this ticket's suite is measured over, checked on its own.

Every other module in this ticket is red until the migration lands, and a wall
of reds is exactly the state in which a *broken* world is invisible: if
`tests/fixtures/benchmark_views.py` planted two sections that were secretly
identical, or hung a response on the wrong week, the level and alignment tests
would go green later for the wrong reason and nobody would look again.

So these tests are green **today**, before anything is built, and they assert
the premises the rest of the suite rests on:

  - two sections that differ only in level really do differ only in level, and
    the same for length — read back out of the base tables, never through a
    view;
  - the course-week and term-week triples the alignment tests claim are the ones
    §2.2's seeded start-letter map produces;
  - the prior term is a second term with week rows of its own;
  - the prior term's hand-written window instants are SPEC §3.1's rhythm;
  - and the privilege probe the grant module uses can find a privilege on a
    relation that certainly has one.

A red here means this suite is measuring the wrong thing and every assertion
resting on it is void — not that E5-03 is wrong. That distinction is the whole
reason the file exists; `tests/fixtures/survey_windows.py` says the same about
its own control, and `docs/MISTAKES.md` entry 3's rule is the general form.
"""

from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fixtures.benchmark_views import (
    COURSE_NUMBER_COLUMN,
    COURSE_NUMBER_FOR_LEVEL,
    CURRENT_TERM,
    GR,
    PRIOR_TERM,
    PRIOR_TERM_COHORTS,
    PRIOR_TERM_START,
    PRIOR_TERM_WEEKS,
    PRIOR_WINDOWS_BY_TERM_WEEK,
    UG,
    UGGR,
    BenchmarkWorld,
)
from fixtures.grading import single_column_link
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import (
    CLOSES_WALL_CLOCK,
    CLOSES_WEEKDAY,
    INSTITUTION_TIMEZONE,
    MONDAY,
    OPENS_WALL_CLOCK,
    OPENS_WEEKDAY,
    SECTION_LENGTH_COLUMN,
    SECTION_START_COLUMN,
    SECTION_TABLE,
    SEEDED_COHORTS,
)
from sqlalchemy import text

pytestmark = pytest.mark.integration

APPLICATION_ROLE = "pulse_app"
LEVEL_COLUMN = "level"
COURSE_TABLE = "course"

# A relation `pulse_app` certainly holds `SELECT` on, for the probe control.
# E0-10 ships it and `SANCTIONED_VIEW_COLUMNS` in `test_identity_grants.py`
# carries its whole column list, so a probe that cannot find a privilege here is
# a probe that would answer `false` for everything.
A_CERTAINLY_GRANTED_VIEW = "public.section_roster"
HAS_TABLE_PRIVILEGE = "SELECT has_table_privilege(:role, :relation, :privilege)"

# The triples the alignment and axis modules claim, written out here so the claim
# is checked against the seeded map rather than derived from it. `(cohort,
# course week, term week)`.
#
# Four of these are asserted outright somewhere in this ticket's suite: `U`
# course week 2 with `R` course week 2 (both at their own second week, three
# term weeks apart), `U` course week 5 as `R` course week 2's calendar twin, and
# `E` course week 2 sharing both axes with `U` course week 2 so that only the
# length separates them. The other two are the degenerate case where the axes
# agree (`U` week 1) and a late-starting cohort the Hypothesis property draws
# (`Q`), both here because a transcription error in either would surface as an
# unreproducible property failure rather than as a named red.
CLAIMED_ALIGNMENTS = (
    ("U", 2, 2),
    ("R", 2, 5),
    ("U", 5, 5),
    ("E", 2, 2),
    ("U", 1, 1),
    ("Q", 2, 8),
)


def section_facts(world: BenchmarkWorld, label: str) -> dict[str, Any]:
    """One planted section's length, start date, course number and derived level.

    Read out of `section` and `course` directly. Every other module in this
    ticket reads a view; this one must not, or a control on the world would be
    measuring the thing the world is used to measure.
    """
    sections = require_table(world.tables, SECTION_TABLE)
    courses = require_table(world.tables, COURSE_TABLE)
    course_link = single_column_link(sections, COURSE_TABLE)
    assert course_link is not None, (
        "No single-column foreign key on `section` names a `course` row, so this control cannot "
        "reach the level a section's course derives."
    )
    course_key = single_primary_key(courses)
    section_key = single_primary_key(sections)

    world.session.flush()
    statement = text(
        f"SELECT c.{LEVEL_COLUMN} AS level, c.{COURSE_NUMBER_COLUMN} AS number,"  # noqa: S608
        f" s.{SECTION_LENGTH_COLUMN} AS length_weeks, s.{SECTION_START_COLUMN} AS start_date"
        f" FROM public.{SECTION_TABLE} s"
        f" JOIN public.{COURSE_TABLE} c ON c.{course_key} = s.{course_link}"
        f" WHERE s.{section_key} = :section"
    )
    row = world.session.execute(statement, {"section": world.section_id(label)}).mappings().one()
    return dict(row)


def test_the_world_plants_two_sections_that_differ_only_in_level(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The premise under every level assertion in this ticket.

    Three sections of one start cohort, in three of SPEC §8's bands. They agree
    on length and start date — so the cohort key agrees on everything except the
    level — and their courses' numbers really do land in three different bands,
    which is the only way `course.level` can differ (ADR 0015 makes it a stored
    generated column derived from the number).

    Without this, `test_a_benchmark_cohort_matches_on_length_and_level_exactly`
    could pass against a world whose three sections were all `UG`: the excluded
    row would be absent because it was never planted, and the assertion would be
    measuring nothing.
    """
    world = benchmark_world.build()
    world.plant_section("ug", cohort="U", level=UG)
    world.plant_section("uggr", cohort="U", level=UGGR)
    world.plant_section("gr", cohort="U", level=GR)

    facts = {label: section_facts(world, label) for label in ("ug", "uggr", "gr")}

    levels = {label: str(fact["level"]) for label, fact in facts.items()}
    numbers = {label: fact["number"] for label, fact in facts.items()}
    assert levels == {"ug": UG, "uggr": UGGR, "gr": GR}, (
        f"The three planted sections derive the levels {levels}. Their courses carry the numbers "
        f"{numbers}, and SPEC §8 puts "
        f"{COURSE_NUMBER_FOR_LEVEL[UG]} in `{UG}`, {COURSE_NUMBER_FOR_LEVEL[UGGR]} in `{UGGR}` and "
        f"{COURSE_NUMBER_FOR_LEVEL[GR]} in `{GR}`. If they do not differ, every level assertion in "
        "this ticket is measuring one cohort against itself."
    )

    lengths = {fact["length_weeks"] for fact in facts.values()}
    starts = {fact["start_date"] for fact in facts.values()}
    assert len(lengths) == 1 and len(starts) == 1, (
        f"The three sections differ in more than their level: lengths {lengths}, start dates "
        f"{starts}. They are all of start cohort `U`, so a difference here means the level tests "
        "would pass against a world where the length is doing the separating."
    )


def test_the_world_plants_two_sections_that_differ_only_in_length(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The premise under the length assertions: same level, same start date, same term.

    `U` runs twelve weeks and `E` runs six, and §2.2's seed starts both on
    2026-08-17. So the two sections agree on the level, the term, the start date
    and — for their second course weeks — the calendar week as well, and
    `length_weeks` is the only column left that can separate them. That is what
    makes the length pair a one-variable experiment rather than a pair that
    differs in three things and is asserted about one.
    """
    world = benchmark_world.build()
    world.plant_section("twelve", cohort="U", level=UG)
    world.plant_section("six", cohort="E", level=UG)

    twelve = section_facts(world, "twelve")
    six = section_facts(world, "six")

    assert twelve["length_weeks"] == 12 and six["length_weeks"] == 6, (
        f"The planted lengths are {twelve['length_weeks']} and {six['length_weeks']}; §2.2's seed "
        "makes `U` a twelve-week cohort and `E` a six-week one."
    )
    assert str(twelve["level"]) == str(six["level"]) == UG, (
        f"The two sections derive the levels {twelve['level']!r} and {six['level']!r}; the length "
        "pair has to agree on the level or the exclusion it asserts could be either rule."
    )
    assert twelve["start_date"] == six["start_date"], (
        f"The two sections start on {twelve['start_date']} and {six['start_date']}. §2.2's seed "
        "starts both `U` and `E` on 2026-08-17, and the length test depends on their second course "
        "weeks falling in the same term week — otherwise a view keyed on the term week would "
        "separate them for the wrong reason and the test would pass."
    )


@pytest.mark.parametrize(
    ("cohort", "course_week", "term_week"),
    CLAIMED_ALIGNMENTS,
    ids=[f"{cohort}-week-{course_week}" for cohort, course_week, _ in CLAIMED_ALIGNMENTS],
)
def test_the_benchmark_calendar_literals_are_the_seeded_start_letter_map(
    benchmark_world: BenchmarkWorld, cohort: str, course_week: int, term_week: int
) -> None:
    """The transcription control: what the alignment tests claim is what the seed produces.

    Each triple is a sentence some other module in this ticket asserts — "course
    week 2 of `R` is term week 5", and so on. They are written out in this file
    rather than derived, because a test that computed its own expectation from
    the same table it is asserting about would agree with any table
    (`docs/MISTAKES.md` entry 19).

    Two independent checks per triple. The **map** says the cohort's first term
    week, and `first_term_week + course_week - 1` has to be the term week
    claimed. The **dates** say the same thing another way: the section's start
    date is that many weeks after the term's own start, so the arithmetic and
    the calendar have to agree. A transcription error in `SEEDED_COHORTS` would
    have to be present in both the term-week number and the date to survive.

    A red here means the alignment module is asserting the wrong week and its
    green would be meaningless — not that a view is wrong.
    """
    length_weeks, first_term_week, start = SEEDED_COHORTS[cohort]
    assert course_week <= length_weeks, (
        f"This suite claims a course week {course_week} for cohort {cohort!r}, which §2.2's seed "
        f"runs for {length_weeks} weeks."
    )
    assert first_term_week + course_week - 1 == term_week, (
        f"Cohort {cohort!r} starts in term week {first_term_week} by the seeded map, so its course "
        f"week {course_week} is term week {first_term_week + course_week - 1}. This suite's tests "
        f"claim term week {term_week}."
    )

    world = benchmark_world.build()
    world.plant_section("checked", cohort=cohort, level=UG)
    assert world.term_week_of("checked", course_week) == term_week, (
        f"The fixture hangs course week {course_week} of a {cohort!r} section on term week "
        f"{world.term_week_of('checked', course_week)}, and this suite's tests read the row at "
        f"term week {term_week}."
    )

    term_start = world.term_row(CURRENT_TERM)["start_date"]
    weeks_in = (start - term_start).days // 7
    assert weeks_in + 1 == first_term_week, (
        f"Cohort {cohort!r} starts on {start} and the term starts on {term_start}, which is "
        f"{weeks_in} weeks later — term week {weeks_in + 1} — while the map says term week "
        f"{first_term_week}. The date and the number disagree, so one of the two transcriptions "
        "in tests/fixtures/survey_windows.py is wrong and every course-week assertion in this "
        "ticket rests on it."
    )


def test_the_prior_term_is_a_second_term_with_weeks_of_its_own(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The premise under criterion 5: two terms, not one term read twice.

    `build_prior_term` seeds a term row and eighteen week rows of its own. If it
    quietly reused the current term's rows, the past-referencing test would be
    planting two sections in one term and asserting that they are two rows —
    which they would not be, and the red would name the view.
    """
    world = benchmark_world.build()
    world.build_prior_term()

    assert world.term_id(CURRENT_TERM) != world.term_id(PRIOR_TERM), (
        "The two terms have the same primary key, so this world holds one term and the "
        "past-referencing test has nothing to assert."
    )
    assert world.term_row(PRIOR_TERM)["start_date"] == PRIOR_TERM_START, (
        f"The prior term starts on {world.term_row(PRIOR_TERM)['start_date']} rather than on "
        f"{PRIOR_TERM_START}."
    )
    assert world.term_row(PRIOR_TERM)["start_date"] < world.term_row(CURRENT_TERM)["start_date"], (
        "The 'prior' term does not start before the current one, so criterion 5 would be asserting "
        "past-referencing over a term in the future."
    )

    prior_weeks = sorted(world.weeks[PRIOR_TERM])
    assert prior_weeks == list(range(1, PRIOR_TERM_WEEKS + 1)), (
        f"The prior term has the week numbers {prior_weeks}; it is seeded with "
        f"{PRIOR_TERM_WEEKS}."
    )
    assert world.week_id(2, PRIOR_TERM) != world.week_id(2, CURRENT_TERM), (
        "Term week 2 of the prior term and term week 2 of the current one are the same `week` row, "
        "so a prior-term response would hang on this term's calendar and the two cohorts could "
        "never be separate rows."
    )


def test_the_prior_terms_cohorts_start_on_its_own_first_monday() -> None:
    """The prior term's start-letter map, checked the way the Fall one is.

    **It asks for no fixture at all**, which is deliberate: the subject is the
    literals at the top of `tests/fixtures/benchmark_views.py`, so this control
    still answers on a tree where the world cannot be built. Its first version
    took `benchmark_world` and used nothing from it, and the red-run
    verification caught what that costs — the control errored in setup along
    with everything else, at the moment it was most needed.

    Both prior-term cohorts start in the term's first week, which is what makes
    a prior-term row differ from a current-term row in the term and in nothing
    else. A start date that had drifted would put the prior section's course
    weeks somewhere this suite does not expect, and criterion 5's red would name
    a filter rather than a fixture.
    """
    assert PRIOR_TERM_START.weekday() == MONDAY, (
        f"The prior term starts on {PRIOR_TERM_START}, which is weekday "
        f"{PRIOR_TERM_START.weekday()} rather than a Monday. Every start date in a start-letter "
        "map falls on a term-week Monday, which is what makes a course week map onto a term week "
        "at all."
    )
    for cohort, (length_weeks, first_term_week, start) in sorted(PRIOR_TERM_COHORTS.items()):
        assert first_term_week == 1 and start == PRIOR_TERM_START, (
            f"Prior-term cohort {cohort!r} is written as starting in term week {first_term_week} "
            f"on {start}; both prior-term cohorts start in the term's first week, on "
            f"{PRIOR_TERM_START}."
        )
        assert length_weeks in {entry[0] for entry in SEEDED_COHORTS.values()}, (
            f"Prior-term cohort {cohort!r} runs {length_weeks} weeks, which is not one of §2.2's "
            "lengths — so a prior-term section could never share a cohort key with a current-term "
            "one, and criterion 5 would be unassertable."
        )


@pytest.mark.parametrize("term_week", sorted(PRIOR_WINDOWS_BY_TERM_WEEK))
def test_the_prior_term_window_literals_are_spec_3_1s_rhythm(term_week: int) -> None:
    """The hand-written instants, read back into the institution's zone.

    SPEC §3.1: "opens Friday 18:00, closes Sunday 23:59:59 … in the institution
    timezone". `tests/fixtures/survey_windows.py` has this control over the Fall
    2026 literals and says why at length: an instant nothing reads is an instant
    nobody checks, and a fixture row carrying a time that contradicts its own
    calendar is a world no reader would trust.

    The prior term's six weeks all fall before daylight time begins on 2026-03-08,
    so every one of them is UTC-5 at both ends — which this test would catch if
    it were not, because it reads the wall clock rather than the offset.
    """
    zone = ZoneInfo(INSTITUTION_TIMEZONE)
    monday = date.fromordinal(PRIOR_TERM_START.toordinal() + (term_week - 1) * 7)
    opens_at, closes_at = PRIOR_WINDOWS_BY_TERM_WEEK[term_week]

    opens_local = opens_at.astimezone(zone)
    closes_local = closes_at.astimezone(zone)

    assert opens_local.weekday() == OPENS_WEEKDAY, (
        f"Prior term week {term_week} opens on {opens_local}, a weekday "
        f"{opens_local.weekday()}; SPEC §3.1 opens the window on the Friday of the term week whose "
        f"Monday is {monday}."
    )
    assert (opens_local.hour, opens_local.minute, opens_local.second) == OPENS_WALL_CLOCK, (
        f"Prior term week {term_week} opens at {opens_local.time()} in {INSTITUTION_TIMEZONE}; "
        f"SPEC §3.1 says {OPENS_WALL_CLOCK}."
    )
    assert closes_local.weekday() == CLOSES_WEEKDAY, (
        f"Prior term week {term_week} closes on {closes_local}, a weekday "
        f"{closes_local.weekday()}; SPEC §3.1 closes on the Sunday."
    )
    assert (closes_local.hour, closes_local.minute, closes_local.second) == CLOSES_WALL_CLOCK, (
        f"Prior term week {term_week} closes at {closes_local.time()} in {INSTITUTION_TIMEZONE}; "
        f"SPEC §3.1 says {CLOSES_WALL_CLOCK}."
    )
    assert date(opens_local.year, opens_local.month, opens_local.day) > monday, (
        f"Prior term week {term_week}'s window opens on {opens_local.date()}, which is not after "
        f"that term week's Monday, {monday}. The window belongs to the week it is written under."
    )


def test_the_privilege_probe_can_find_a_grant_it_is_pointed_at(db_session: Any) -> None:
    """The control on the grant module's probe.

    `has_table_privilege` answers `false` for a role that does not exist, for a
    relation that resolves somewhere else, and for a privilege spelled wrongly —
    so a module built on it that only ever asserts `false` cannot tell you
    whether it can see anything at all. `docs/MISTAKES.md` entry 35: require a
    guard to *find* the thing on a subject that certainly has it.

    `section_roster` is E0-10's and `pulse_app` holds `SELECT` on it;
    `SANCTIONED_VIEW_COLUMNS` in `test_identity_grants.py` carries its whole
    column list with the sentence that admits it. If this ever goes red, the
    write-privilege assertions in
    `test_the_benchmark_views_are_readable_by_the_runtime_role_and_written_by_nobody.py`
    are passing for a reason unrelated to what they assert.
    """
    holds = db_session.execute(
        text(HAS_TABLE_PRIVILEGE),
        {"role": APPLICATION_ROLE, "relation": A_CERTAINLY_GRANTED_VIEW, "privilege": "SELECT"},
    ).scalar_one()
    assert holds is True, (
        f"`has_table_privilege` says `{APPLICATION_ROLE}` holds no `SELECT` on "
        f"`{A_CERTAINLY_GRANTED_VIEW}`, which E0-10 grants it. Either this probe cannot see a "
        "privilege at all — in which case every `false` this ticket's grant module asserts is "
        "worthless — or a grant this project depends on has gone missing, which is "
        "`test_identity_grants.py`'s subject rather than this ticket's."
    )
