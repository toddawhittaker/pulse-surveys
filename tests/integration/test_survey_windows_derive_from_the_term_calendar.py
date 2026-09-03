"""A section's survey windows come from its calendar — ticket E2-06, criterion 1.

"Derived windows for the seeded Fall-2026 sections match §2.2's start letters and
§3.1's rhythm — checked against hand-computed dates for at least one 6-, 12- and
15-week section."

SPEC §3.1 is the rhythm: "opens Friday 18:00, closes Sunday 23:59:59 … in the
institution timezone", one window per active course week, and §2.2 is what says
which weeks those are — the start letter carries a length and a start date, and
the start date is a term-week Monday. So a section's windows are the Friday and
Sunday of each of its term weeks, and nothing about them is per-section
configuration.

**Every expected instant is a literal somebody wrote down**
(`tests/fixtures/survey_windows.py`, and `docs/MISTAKES.md` entry 19). The four
mistakes worth catching are all mistakes a re-derivation in the test would make
identically:

  - one zone conversion per *window* rather than per *instant*, which is right for
    fifteen weeks of Fall 2026 and an hour wrong for the one that straddles the
    daylight-saving fall-back;
  - a Friday counted from the section's own start date rather than from the term
    week's Monday, which agrees for every cohort that starts in term week 1;
  - the course-week axis used where the term-week axis belongs (§2.2's "two week
    axes"), which agrees for every cohort that starts in term week 1;
  - the whole term's windows written for a section rather than its own weeks.

The cohorts asserted are E (6 weeks from term week 1), U (12 from 1), V (15 from
1), H (6 from **13**) and Q (12 from **7**). The last two are what separate the
two axes: a section starting in term week 7 whose windows sit on term weeks 1-12
is wrong in a way no cohort starting at the term's beginning can show.

**What is not here.** The one-open rule and the read-time open/closed question
are `tests/integration/test_at_most_one_survey_window_is_open_at_a_time.py`'s;
the rule that no second module writes this table is
`tests/unit/test_survey_windows_have_one_writer.py`'s.
"""

import logging
from datetime import timedelta
from typing import Any

import pytest
from fixtures.survey_windows import (
    CRITERION_ONE_COHORTS,
    DST_FALL_BACK_TERM_WEEK,
    FALL_2026_TERM_WEEKS,
    SECTION_CODE_COLUMN,
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

pytestmark = pytest.mark.integration

# `week.term_id`, spelled here because E0-06 named it and no fixture constant
# does. The column is how a term's weeks are found at all.
WEEK_TERM_COLUMN = "term_id"

# Log records this module counts. A run of the derivation crosses SQLAlchemy and
# psycopg, either of which may warn about something that has nothing to do with a
# missing week, so the count is taken over the application's own loggers (SPEC
# §13 puts every one of ours under the `app` package).
APPLICATION_LOGGER_ROOT = "app"

# The cohort whose windows are asserted wherever one section is enough. `U` is a
# 12-week cohort starting in the term's first week, so it holds term week 11 —
# the daylight-saving week — and it is one of the two cohorts `scripts/seed.py`
# actually seeds twice (`MATH 210 U1WW`, `PSYC 110 U2WW`).
A_TWELVE_WEEK_COHORT = "U"

# The term week whose `week` row is left out to pose ADR 0018's lengthening gap.
# Chosen inside `U`'s span and away from both ends, so that a derivation which
# stopped at the gap rather than skipping it leaves a visibly truncated set
# rather than one short at the edge.
A_MISSING_TERM_WEEK = 5

# How far a planted window's instants are moved from the derived ones, for the
# entry-31 case. An hour: large enough that no rounding could produce it, small
# enough to still be a plausible window somebody configured by hand.
PLANTED_OFFSET = timedelta(hours=1)


def expected_windows(letter: str) -> list[tuple[int, Any, Any]]:
    """`(term week, opens_at, closes_at)` for every course week of one cohort.

    **This is a lookup, not a derivation.** The term week a course week lands in
    comes from `SEEDED_COHORTS`, whose two numbers are checked against each other
    by `tests/unit/test_the_fall_2026_window_calendar_is_spec_3_1s_rhythm.py`, and
    the instants come straight out of the hand-written table. No timezone, no
    weekday and no offset is computed anywhere in this module.
    """
    length_weeks, first_term_week, _start = SEEDED_COHORTS[letter]
    return [
        (
            first_term_week + course_week - 1,
            *WINDOWS_BY_TERM_WEEK[first_term_week + course_week - 1],
        )
        for course_week in range(1, length_weeks + 1)
    ]


def derive(service: Any, session: Any, section: Any, settings: Any) -> Any:
    """Run E2-06's one writer over one section."""
    return service.derive_windows_for_section(session, section, settings=settings)


# ---------------------------------------------------------------------------
# The control on this module's own seeding, before anything is believed of it.
# A red here means these tests are broken, not that the service is.
# ---------------------------------------------------------------------------


def test_the_fixture_seeds_a_term_of_eighteen_weeks_and_a_section_of_the_cohort_it_names(
    fall_2026: Any, metadata_tables: dict[str, Any], db_session: Any
) -> None:
    """The premise every assertion below rests on, asserted before any of them.

    Each test here says what the derivation produced *given* a term with eighteen
    numbered weeks and a section whose length and start date are §2.2's. If the
    fixture seeded seventeen weeks, or a section whose start date is not the one
    the cohort names, the criterion-1 tests would fail against a correct
    derivation and the failure would name the service (`docs/MISTAKES.md` entry
    13: when a test fails inside its own fixture, suspect the fixture first).

    It also asserts the `survey_window` table is **empty** for that section before
    anything derives. Every count below is an equality over what the writer wrote,
    and a row left over from somewhere else would be counted as the writer's.

    **Green today and green after E2-06 lands**: it names E0-06's `term` and
    `week`, E0-07's derived section columns and E2-05's `survey_window`, and
    nothing this ticket ships.
    """
    from sqlalchemy import func, select

    calendar = fall_2026.build()
    row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)
    length_weeks, _first, start = SEEDED_COHORTS[A_TWELVE_WEEK_COHORT]

    weeks = metadata_tables[WEEK_TABLE]
    term_key = calendar.key_of(TERM_TABLE)
    seeded = sorted(
        number
        for (number,) in db_session.execute(
            select(weeks.c[WEEK_NUMBER_COLUMN]).where(
                weeks.c[WEEK_TERM_COLUMN] == calendar.term[term_key]
            )
        )
    )
    assert seeded == list(range(1, FALL_2026_TERM_WEEKS + 1)), (
        f"The fixture seeded term weeks {seeded}, not 1 to {FALL_2026_TERM_WEEKS}. E0-06 emits a "
        "term's weeks as 1..N, and every window below is looked up by `(term_id, number)`."
    )

    assert row["length_weeks"] == length_weeks and row["start_date"] == start, (
        f"The seeded section carries {(row['length_weeks'], row['start_date'])} and cohort "
        f"{A_TWELVE_WEEK_COHORT!r} is {(length_weeks, start)}. Those two columns are the whole "
        "input to the derivation, so a section carrying something else is a test about a cohort "
        "nobody named."
    )

    windows = metadata_tables[SURVEY_WINDOW_TABLE]
    section_key = calendar.key_of(SECTION_TABLE)
    standing = db_session.execute(
        select(func.count())
        .select_from(windows)
        .where(windows.c[WINDOW_SECTION_COLUMN] == row[section_key])
    ).scalar_one()
    assert standing == 0, (
        f"`{SURVEY_WINDOW_TABLE}` already holds {standing} rows for this section before anything "
        "derived. E2-06's ticket says the table 'exists and nothing fills it', and every count "
        "below is an equality over rows the writer wrote."
    )
    assert section is not None, (
        "The seeded section could not be loaded through its mapped class, so there is no instance "
        "to hand the window service."
    )


# ---------------------------------------------------------------------------
# Criterion 1 — the derived windows.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("letter", CRITERION_ONE_COHORTS)
def test_a_cohorts_windows_are_one_per_course_week_at_the_hand_computed_instants(
    letter: str,
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """Criterion 1, for a 6-, 12- and 15-week cohort and for two that start mid-term.

    One row per course week, on the term week that course week falls in, opening
    at the hand-written Friday instant and closing at the hand-written Sunday one.
    The whole set is compared at once so a failure prints both lists rather than
    stopping at the first row.

    **The mutations this kills.**

      - *A window per term week rather than per course week.* `H` runs six weeks
        in an eighteen-week term; a derivation that walked the term writes
        eighteen rows and this is an equality on the count.
      - *Course weeks read as term weeks.* `H` starts in term week 13 and `Q` in
        term week 7, so a derivation that put course week 1 on term week 1 lands
        their windows twelve and six weeks early — on dates that are still
        Fridays at 18:00, which is why the term week is asserted and not only the
        instant.
      - *The wrong end of the week.* Opening on the Monday, closing on the
        Saturday, or closing at 00:00:00 on the Monday after are each one literal
        away from correct and each fails here naming the instant.
      - *A naive datetime.* ADR 0019's column type refuses one outright, so this
        would fail in the writer — but the comparison is against aware UTC
        literals, so a stored value in some other zone fails here as an inequality
        rather than passing as an equal instant spelled differently.

    **The near miss it must not pass on**: a derivation that writes the right
    number of rows against the right weeks with every instant an hour out. That is
    the daylight-saving defect, and it is invisible in a count; the instants are
    compared exactly, and the sibling test below isolates the one week where the
    two ends disagree.
    """
    calendar = fall_2026.build()
    _row, section = calendar.cohort(letter)

    derive(survey_window_service, db_session, section, window_settings)

    found = [
        (window["term_week"], window["opens_at"], window["closes_at"])
        for window in calendar.windows_of(section)
    ]
    expected = expected_windows(letter)

    assert found == expected, (
        f"Cohort {letter!r} derived {len(found)} windows and §2.2 gives it "
        f"{SEEDED_COHORTS[letter][0]} course weeks from term week {SEEDED_COHORTS[letter][1]}.\n"
        f"  derived:  {found}\n"
        f"  expected: {expected}\n"
        "Each expected instant is written by hand in `tests/fixtures/survey_windows.py` from SPEC "
        "§3.1's rhythm — Friday 18:00 to Sunday 23:59:59 in the institution's timezone, stored as "
        "aware UTC — over the term-week Mondays `scripts/seed.py`'s Fall 2026 calendar produces. A "
        "set that is the right length on the wrong weeks is the two week axes of §2.2 confused; a "
        "set on the right weeks at the wrong instants is the rhythm."
    )


def test_the_window_across_the_daylight_saving_fall_back_converts_each_end_on_its_own_offset(
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """Term week 11 opens on daylight time and closes on standard time.

    The week of Sunday 1 November 2026 is the one week in Fall 2026 where the two
    ends of a window sit on different UTC offsets: Friday 30 October 18:00 is
    22:00Z at UTC-4, and Sunday 1 November 23:59:59 is 04:59:59Z the next morning
    at UTC-5. Fifty-four hours and fifty-nine minutes apart, not fifty-three
    fifty-nine.

    **The mutation this kills, and it is the whole reason this case has a test of
    its own**: one zone conversion per window instead of one per instant. The
    shortest correct-looking implementation resolves the offset once — off the
    week's Monday, or off the section's start date, or off `opens_at` — and adds a
    `timedelta` for the rest. It is right for seventeen of Fall 2026's eighteen
    weeks, right for every week of a spring term, and an hour wrong here. An hour
    is exactly long enough for a student's Sunday-evening submission to be refused
    by a window the screen said was open.

    **The near miss it must not pass on**: a fixed `UTC-5` or a fixed `UTC-4`. The
    first is wrong at both ends of this window and the second at one, and the
    assertion is on both instants, so neither passes.

    A separate test rather than a case inside the sweep above, because it fails
    for a different reason and reads differently: the sweep says "these windows are
    wrong", this says "the offset was resolved once".
    """
    calendar = fall_2026.build()
    _row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)

    derive(survey_window_service, db_session, section, window_settings)

    by_term_week = {window["term_week"]: window for window in calendar.windows_of(section)}
    opens_at, closes_at = WINDOWS_BY_TERM_WEEK[DST_FALL_BACK_TERM_WEEK]

    assert DST_FALL_BACK_TERM_WEEK in by_term_week, (
        f"Cohort {A_TWELVE_WEEK_COHORT!r} derived no window for term week "
        f"{DST_FALL_BACK_TERM_WEEK} (it derived {sorted(by_term_week)}). That cohort runs twelve "
        "weeks from the term's first, so the daylight-saving week is inside it — without that row "
        "there is nothing here to be right or wrong about."
    )

    window = by_term_week[DST_FALL_BACK_TERM_WEEK]
    assert (window["opens_at"], window["closes_at"]) == (opens_at, closes_at), (
        f"Term week {DST_FALL_BACK_TERM_WEEK} was derived as "
        f"{(window['opens_at'], window['closes_at'])} and SPEC §3.1's rhythm over that week is "
        f"{(opens_at, closes_at)}. Daylight time ends on the Sunday this window closes on, so "
        "Friday 18:00 is UTC-4 and Sunday 23:59:59 is UTC-5. An implementation that resolved one "
        "offset for the window and added a timedelta for the other end is out by an hour at "
        f"exactly one end, and the difference between the two instants here is "
        f"{window['closes_at'] - window['opens_at']} against an expected {closes_at - opens_at}."
    )


# ---------------------------------------------------------------------------
# ADR 0018's lengthening gap — tolerated loudly, repaired never.
# ---------------------------------------------------------------------------


def test_a_course_week_with_no_week_row_yields_no_window_a_warning_and_no_exception(
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """ADR 0018's silent direction, met loudly: no window, one warning, no crash.

    A term lengthened from twelve weeks to eighteen keeps twelve `week` rows and
    reports eighteen, "with no error, no log line, and every surviving row looking
    correct" — ADR 0018 measured it, and its closing ruling of 2026-08-31 gives
    the repair to E11 and gives E2-06 the obligation to *tolerate it loudly*.
    E2-06's own scope calls that "the quiet-failure shape refused loudly".

    So three things are asserted together, because each alone is satisfied by a
    wrong implementation:

      - **The other course weeks still derive.** A derivation that stopped at the
        gap, or that abandoned the section, leaves a section with no weekly cycle
        at all — and "no window for the missing week" would be true of it.
      - **Nothing is written for the missing week, and nothing is raised.** A
        `KeyError` or an `AttributeError` escaping here is an hourly Celery task
        that dies on its first bad term and never reaches the sections after it.
      - **Exactly one warning names the four things that identify the gap**: the
        section, its code, the course week and the term week number. A log line
        that says only "missing week" is a line nobody can act on, and one emitted
        per section per hour with no identifiers is noise that gets filtered.

    **The mutation this kills**: a repair. A derivation that created the absent
    `week` row, or that shifted the remaining course weeks up to fill the gap,
    would leave every count here correct and would be E11's decision taken by
    E2-06 — and a shifted set puts a section's week 6 window on the calendar week
    its week 5 belongs to, which the participation denominator (§3.4) then counts
    against the wrong week for the rest of the term.
    """
    calendar = fall_2026.build(without_term_weeks=(A_MISSING_TERM_WEEK,))
    row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)
    section_id = row[calendar.key_of(SECTION_TABLE)]
    section_code = row[SECTION_CODE_COLUMN]

    length_weeks, first_term_week, _start = SEEDED_COHORTS[A_TWELVE_WEEK_COHORT]
    missing_course_week = A_MISSING_TERM_WEEK - first_term_week + 1
    assert 1 <= missing_course_week <= length_weeks, (
        f"Term week {A_MISSING_TERM_WEEK} is not inside cohort {A_TWELVE_WEEK_COHORT!r}'s span, so "
        "leaving its row out poses no gap at all and this test would assert nothing."
    )

    with caplog.at_level(logging.WARNING):
        derive(survey_window_service, db_session, section, window_settings)

    found = [window["term_week"] for window in calendar.windows_of(section)]
    expected = [term_week for term_week, _, _ in expected_windows(A_TWELVE_WEEK_COHORT)]
    expected.remove(A_MISSING_TERM_WEEK)

    assert found == expected, (
        f"With term week {A_MISSING_TERM_WEEK}'s `week` row absent, the derivation wrote windows "
        f"for {found}; the section's other course weeks are {expected}. A short list that stops "
        "before the gap is a derivation that gave up at the first missing week; a list containing "
        f"{A_MISSING_TERM_WEEK} is a derivation that created the row ADR 0018's ruling gives to "
        "E11; a list shifted up by one is a section whose weeks no longer mean what the term's "
        "calendar says."
    )

    warnings = [
        record
        for record in caplog.records
        if record.levelno >= logging.WARNING
        and (
            record.name == APPLICATION_LOGGER_ROOT
            or record.name.startswith(f"{APPLICATION_LOGGER_ROOT}.")
        )
    ]
    assert len(warnings) == 1, (
        f"The derivation emitted {len(warnings)} warnings for one missing week: "
        f"{[record.getMessage() for record in warnings]}. E2-06 asks for one line naming the gap — "
        "silence is the quiet failure the scope refuses, and one per course week turns an ordinary "
        "lengthened term into an hourly wall of log."
    )

    said = warnings[0].getMessage()
    for label, needle in (
        ("the section's id", str(section_id)),
        ("the section code", str(section_code)),
        ("the course week", str(missing_course_week)),
        ("the term week", str(A_MISSING_TERM_WEEK)),
    ):
        assert needle in said, (
            f"The warning does not name {label} ({needle!r}). It said {said!r}. E2-06 settles the "
            "line as naming the section id, the section code, the course week and the term week "
            "number: this is the only signal that a term is short of weeks, it is read in a log "
            "aggregator long after the fact, and one that names none of them cannot be acted on."
        )


# ---------------------------------------------------------------------------
# Idempotence — the reconciler runs every hour, forever.
# ---------------------------------------------------------------------------


def test_a_second_derivation_writes_nothing_and_changes_nothing(
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
) -> None:
    """The hourly reconciler is safe to run again, and the second run is the one measured.

    E2-06's writer is called from a Celery beat entry that fires every hour and
    from `scripts/seed.py`, so a second run over a section that already has its
    windows is the ordinary case rather than the exceptional one. A writer that
    inserted again is refused by `uq_survey_window_section_id_week_id` — an
    `IntegrityError` out of an hourly task — and one that deleted and rewrote
    would give every window a new primary key each hour, which E2-08's responses
    and E4's reports will be keyed to.

    **The state the second run is measured against is the first run's**, which is
    the shape `docs/MISTAKES.md` entry 31 warns about — so the row identities are
    captured between the two runs and compared afterwards, rather than the counts
    alone. A delete-and-rewrite passes a count comparison perfectly.

    The sibling test below is the other half of entry 31's rule, and the half that
    matters more: a row the writer did not write, put in its way.
    """
    calendar = fall_2026.build()
    _row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)

    derive(survey_window_service, db_session, section, window_settings)
    after_first = calendar.windows_of(section)
    assert len(after_first) == SEEDED_COHORTS[A_TWELVE_WEEK_COHORT][0], (
        f"The first derivation wrote {len(after_first)} windows for a "
        f"{SEEDED_COHORTS[A_TWELVE_WEEK_COHORT][0]}-week cohort. Nothing below means anything "
        "until the first run has written the set the second run is supposed to leave alone "
        "(`docs/MISTAKES.md` entry 3)."
    )

    derive(survey_window_service, db_session, section, window_settings)
    after_second = calendar.windows_of(section)

    assert after_second == after_first, (
        "A second derivation changed the section's windows.\n"
        f"  after the first run:  {after_first}\n"
        f"  after the second run: {after_second}\n"
        "The rows carry their `week_id` and `term_id`, so a set that compares unequal here is "
        "either extra rows, rewritten instants, or the same windows under new keys — and the "
        "third is the one a count-only comparison would miss."
    )


def test_a_window_the_service_did_not_write_is_left_exactly_as_it_was(
    fall_2026: Any,
    survey_window_service: Any,
    window_settings: Any,
    db_session: Any,
    seed_rows: Any,
) -> None:
    """`docs/MISTAKES.md` entry 31: put a row the writer did not write in its way.

    "Idempotency is a claim about a *second* run's interaction with whatever is
    already in the database. A fixture that starts empty tests only the loader's
    interaction with itself, which is the easy half and the half that cannot
    fail." So this test plants a `survey_window` on the natural key the writer
    matches on — `(section_id, week_id)` — carrying instants an hour away from the
    ones the derivation would produce, and then derives.

    E2-06 settles the behaviour: the writer **skips** an existing
    `(section_id, week_id)` row, and repairs nothing. Re-deriving after the term
    calendar or the start-letter map is edited is E11's, ruled on 2026-08-31. So
    the planted row must survive untouched, its neighbours must be written, and
    nothing may be raised.

    **The mutations this kills.**

      - *A blind insert.* The unique constraint refuses the second row and the
        whole run dies — including the windows for every section after this one in
        the hourly walk. Nothing in the empty-database idempotence test above
        reaches this, because there the writer only ever meets its own rows.
      - *An upsert that overwrites.* It looks harmless and it silently takes E11's
        decision: a window an administrator or a later ticket set deliberately is
        reset every hour by a job nobody is watching.
      - *A run that stops at the row it did not recognise*, leaving the section's
        other eleven weeks unwritten.

    **The near miss it must not pass on**: a writer that skips the whole section
    once it finds any existing window. The planted row is the section's *third*
    course week, so eleven neighbours are asserted present around it.
    """
    calendar = fall_2026.build()
    row, section = calendar.cohort(A_TWELVE_WEEK_COHORT)
    section_key = calendar.key_of(SECTION_TABLE)
    week_key = calendar.key_of(WEEK_TABLE)
    term_key = calendar.key_of(TERM_TABLE)

    length_weeks, first_term_week, _start = SEEDED_COHORTS[A_TWELVE_WEEK_COHORT]
    planted_term_week = first_term_week + 2
    derived_opens, derived_closes = WINDOWS_BY_TERM_WEEK[planted_term_week]
    planted_opens = derived_opens - PLANTED_OFFSET
    planted_closes = derived_closes - PLANTED_OFFSET

    seed_rows(
        SURVEY_WINDOW_TABLE,
        {},
        **{
            WINDOW_SECTION_COLUMN: row[section_key],
            WINDOW_WEEK_COLUMN: calendar.weeks[planted_term_week][week_key],
            WINDOW_TERM_COLUMN: calendar.term[term_key],
            WINDOW_OPENS_COLUMN: planted_opens,
            WINDOW_CLOSES_COLUMN: planted_closes,
        },
    )
    standing = calendar.windows_of(section)
    assert [window["term_week"] for window in standing] == [planted_term_week], (
        f"The planted window did not land: the section carries {standing}. Everything below is "
        "about what the derivation does when it meets a row it did not write, and there is no "
        "such row here (`docs/MISTAKES.md` entry 3)."
    )

    derive(survey_window_service, db_session, section, window_settings)

    found = {window["term_week"]: window for window in calendar.windows_of(section)}
    assert sorted(found) == [
        term_week for term_week, _, _ in expected_windows(A_TWELVE_WEEK_COHORT)
    ], (
        f"After deriving over a planted window the section carries windows for {sorted(found)}, "
        f"and a {length_weeks}-week cohort starting in term week {first_term_week} has "
        f"{[term_week for term_week, _, _ in expected_windows(A_TWELVE_WEEK_COHORT)]}. A set "
        "missing everything but the planted week is a writer that gave up when it met a row it "
        "had not written."
    )

    planted = found[planted_term_week]
    assert (planted["opens_at"], planted["closes_at"]) == (planted_opens, planted_closes), (
        f"The planted window for term week {planted_term_week} now reads "
        f"{(planted['opens_at'], planted['closes_at'])}; it was written as "
        f"{(planted_opens, planted_closes)} and the derivation's own answer for that week is "
        f"{(derived_opens, derived_closes)}. E2-06 skips an existing `(section_id, week_id)` row "
        "and repairs nothing — re-deriving after an edit is E11's, ruled at the E2 breakdown on "
        "2026-08-31. An hourly job that rewrites rows it did not write takes that decision every "
        "hour with nobody watching."
    )
