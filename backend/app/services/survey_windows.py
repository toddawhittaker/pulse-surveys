"""When a section's weekly survey opens and closes, and which window is open now — E2-06.

SPEC §3.1 gives the rhythm — "opens Friday 18:00, closes Sunday 23:59:59 … in the
institution timezone" — and §2.2 gives the weeks it applies to: a section's active
course weeks come from its start letter, and each of them falls in a week of the
term. This module is the arithmetic between those two sentences, and the one
writer of `survey_window` (ADR 0021's shape, and the ticket's fourth criterion,
swept by `tests/unit/test_survey_windows_have_one_assignment_site.py`).

**A module of its own, and SPEC §13's list names none that fits.**
`section_codes` reads a code against a term's map and is calendar *parsing*;
`clock` answers what time it is. Window scheduling is neither, and putting it in
either would make a service about codes, or a service about time, also the place
the weekly rhythm lives.

## Materialized up front, answered at read time

Every window a section's calendar implies is written in one idempotent pass
(`derive_windows_for_section`), and whether one is *open* is a comparison against
`app.services.clock` made when somebody asks (`open_window_for_section`). No row
is created at the moment a window opens.

That split is what makes the development clock useful, and it is ADR 0111's first
decision. Celery beat fires on real time — ADR 0109 leaves beat's own schedule
out of the override deliberately — so a design that wrote a window's row when the
window opened would never respond to a developer pretending it is Friday evening.
Pre-materialized rows plus a read-time comparison show the pretended Friday
immediately, in the tool and in the worker alike.

## The rhythm ships as constants, with the citation

§3.1 calls the rhythm "institution configuration". The configuration *surface* is
§6.3's and E11's; here the default ships as the four named constants below with
the spec section beside them, which is what E2-06's ticket settles and what the
epic README's deliberately-not-done list records.

## What this module reads about time, and how

Only `app.services.clock`. ADR 0109 states that as a review rule for scheduling
code, and `tests/unit/test_the_window_service_asks_the_clock_for_the_time.py`
enforces it over this module — where it has no exemptions, because every reading
of "now" here is a scheduling reading. A direct `datetime.now(UTC)` in this file
is invisible to every other test in E2-06 and its symptom is that the `/dev`
clock appears to do nothing at all.

Instants are stored aware and in UTC (ADR 0019: the column type refuses a naive
value), and **each end of a window is converted on its own offset** — see
`_instant` below, which is the one place a wall-clock time becomes an instant.

## What it does not do

It does not repair a term that is short of `week` rows (ADR 0018's lengthening
gap): a course week with no week row gets no window and one warning, and the
repair belongs to E11's calendar editor. It does not re-derive after a term or a
start-letter map is edited, and it never rewrites a window it did not write —
both are E11's, ruled at the E2 breakdown on 2026-08-31.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.config import Settings
from app.models.org import Section
from app.models.term import SurveyWindow, Term, Week
from app.services import clock
from app.services.section_codes import UnknownTermError, week_of_the_term

logger = logging.getLogger("app.services.survey_windows")

# SPEC §3.1's default rhythm, as a weekday offset from the term week's Monday and
# a wall-clock time in the institution's timezone. Four constants and not two
# datetimes, because a window is the same shape in every week of every term and
# the week's Monday is the only thing that moves.
#
# Monday is 0, so Friday is 4 and Sunday is 6. §2.2's calendar starts every term
# and every start letter on a Monday, which is what makes the offset arithmetic
# below a week's own arithmetic rather than a search for the next Friday.
OPENS_DAYS_AFTER_MONDAY = 4
OPENS_AT = time(18, 0, 0)
CLOSES_DAYS_AFTER_MONDAY = 6
CLOSES_AT = time(23, 59, 59)

DAYS_PER_WEEK = 7


@dataclass(frozen=True, slots=True)
class DerivedWindow:
    """One course week's window, before anything has been looked up or written.

    Carries both week axes (§2.2) because both are needed and neither can be
    recovered from the other here: the course week is what the section counts in,
    and the term week is what the `week` row is found by and what a warning about
    a missing one has to name.

    Frozen, like `section_codes.SectionCalendar` and for the same reason: it is a
    reading of a calendar, not a thing to edit.
    """

    course_week: int
    term_week: int
    opens_at: datetime
    closes_at: datetime


@dataclass(frozen=True, slots=True)
class _Calendars:
    """Everything a derivation reads, for a whole set of sections, read once.

    Three mappings and three statements, whatever the number of sections. Before
    E2-16 each section read its own term, that term's weeks and its own windows —
    5N+1 round trips over the walk, 2,501 an hour at 500 sections, most of them
    fetching the same term's eighteen week rows again. The reads do not depend on
    each other and none of them depends on what an earlier section wrote, so they
    are made up front and the writes stay where they were.

    **Plain values rather than ORM rows, deliberately.** A `Term` or a `Week`
    instance held across the loop is one the session may expire — a savepoint's
    rollback does exactly that — and the next attribute read would then be a lazy
    refresh, which is a per-section read the walk cannot see and this class exists
    to remove. A `date` and a `UUID` cannot go stale.
    """

    # A term's start date, which is the anchor every window is measured from.
    term_starts: dict[UUID, date]
    # A term's week rows by their number within the term (SPEC §2.2's term axis).
    week_ids: dict[UUID, dict[int, UUID]]
    # The weeks each section already has a window for, so a second pass skips them.
    written_week_ids: dict[UUID, set[UUID]]


def _read_calendars(session: Session, sections: Sequence[Section]) -> _Calendars:
    """The three reads the whole walk needs, made once for every section in it."""
    term_ids = {section.term_id for section in sections}
    section_ids = {section.id for section in sections}

    term_starts: dict[UUID, date] = dict(
        session.execute(select(Term.id, Term.start_date).where(Term.id.in_(term_ids)))
        .tuples()
        .all()
    )
    week_ids: dict[UUID, dict[int, UUID]] = {term_id: {} for term_id in term_ids}
    for term_id, number, week_id in session.execute(
        select(Week.term_id, Week.number, Week.id).where(Week.term_id.in_(term_ids))
    ):
        week_ids[term_id][number] = week_id
    written_week_ids: dict[UUID, set[UUID]] = {section_id: set() for section_id in section_ids}
    for section_id, week_id in session.execute(
        select(SurveyWindow.section_id, SurveyWindow.week_id).where(
            SurveyWindow.section_id.in_(section_ids)
        )
    ):
        written_week_ids[section_id].add(week_id)

    return _Calendars(term_starts=term_starts, week_ids=week_ids, written_week_ids=written_week_ids)


def windows_for_section(
    session: Session, section: Section, *, settings: Settings
) -> list[DerivedWindow]:
    """Every window a section's calendar implies, as instants — one per course week.

    The derivation on its own: no `week` row is looked up and nothing is written,
    so this answers what §3.1's rhythm over §2.2's calendar *says*, and
    `derive_windows_for_section` below answers what the database should hold.

    **It reads the section's own derived columns and not its code.**
    `length_weeks` and `start_date` are already the reading of that code against
    the term's start-letter map — `apply_section_code` is the only thing that
    writes them (SPEC §8) — so re-deriving them here would ask the map a second
    time for an answer the row already holds, and would make a window disagree
    with the section it belongs to the moment E11 lets somebody edit a map.

    The session is here for the term, whose start date is the calendar's anchor.
    Mapping a course week onto a term week is
    `app.services.section_codes.week_of_the_term` and is not re-derived here:
    SPEC §2.2's two week axes have one reading in this codebase, and a second copy
    of it is how a course-level page and an aggregate page come to disagree about
    the same section.
    """
    term = _term_of(session, section)
    return _windows_from(section, term.start_date, settings=settings)


def _windows_from(section: Section, term_start: date, *, settings: Settings) -> list[DerivedWindow]:
    """The arithmetic alone: a section's course weeks against its term's anchor.

    Split out of `windows_for_section` so that the batched walk can derive from a
    start date it has already read, and so that there is still exactly one copy of
    the arithmetic for both entry points to share.
    """
    zone = ZoneInfo(settings.institution_timezone)
    return [
        _window_for_course_week(section, term_start, course_week, zone=zone)
        for course_week in range(1, section.length_weeks + 1)
    ]


def derive_windows_for_section(
    session: Session, section: Section, *, settings: Settings
) -> list[SurveyWindow]:
    """Write the windows this section's calendar implies, and return the new rows.

    **The one writer of `survey_window`** (ADR 0021, criterion 4). Nothing else in
    `backend/app/` sets these columns, and `tests/unit/
    test_survey_windows_have_one_assignment_site.py` is the sweep that says so.

    One section's reads, then one section's writes. The walk below makes the same
    reads once for every section it visits and then calls the same writer, so the
    two paths cannot derive different calendars —
    `tests/integration/test_window_derivation_batches_its_reads.py` compares them
    over nine cohorts to say so.

    The caller owns the transaction. This flushes what it added so that a second
    call in the same transaction sees the rows the first one wrote.
    """
    return _write_windows_for_section(
        session, section, _read_calendars(session, [section]), settings=settings
    )


def _write_windows_for_section(
    session: Session, section: Section, calendars: _Calendars, *, settings: Settings
) -> list[SurveyWindow]:
    """Write one section's missing windows out of calendars already read.

    **Idempotent by skipping, never by rewriting.** A `(section_id, week_id)` that
    already has a row is left exactly as it is — instants included — because this
    runs every hour from a beat entry nobody is watching, and an hourly job that
    rewrote rows it did not write would take E11's re-derivation decision sixty
    times a day. The unique constraint over that pair is what makes the skip a
    guarantee rather than a convention: a blind second insert is refused by the
    database, so this cannot silently become an upsert.

    **A course week whose term has no `week` row yields no window, one warning and
    no exception** (ADR 0018's lengthening gap, which that ADR measures as
    reachable by an ordinary edit "with no error, no log line, and every surviving
    row looking correct"). The other course weeks are still written: a derivation
    that abandoned the section would leave it with no weekly cycle at all, which
    is a larger failure than the gap. The warning names the section, its code, the
    course week and the term week, because it is read in a log aggregator long
    after the fact and a line naming none of them cannot be acted on.

    **A section whose term is not in the calendars is refused rather than
    skipped**, with the same `UnknownTermError` the per-section read raised before:
    the batch reads the terms the sections name, so a term missing from it is a
    section naming one that is not in the database.
    """
    term_start = calendars.term_starts.get(section.term_id)
    if term_start is None:
        raise UnknownTermError(
            f"Section {section.lms_section_code!r} names the term {section.term_id!r}, which this "
            "session cannot load. A section's survey windows are derived from its term's calendar "
            "(SPEC §2.2, §3.1), so there is nothing to derive them from."
        )
    weeks = calendars.week_ids.get(section.term_id, {})
    already_written = calendars.written_week_ids.get(section.id, set())

    written: list[SurveyWindow] = []
    for window in _windows_from(section, term_start, settings=settings):
        week_id = weeks.get(window.term_week)
        if week_id is None:
            logger.warning(
                "section %s (%s) has no survey window for course week %d: its term has no week "
                "row numbered %d, so the term is short of the weeks its length claims "
                "(docs/adr/0018). No window was written and none was repaired.",
                section.id,
                section.lms_section_code,
                window.course_week,
                window.term_week,
            )
            continue
        if week_id in already_written:
            continue
        row = SurveyWindow(
            section_id=section.id,
            week_id=week_id,
            term_id=section.term_id,
            opens_at=window.opens_at,
            closes_at=window.closes_at,
        )
        session.add(row)
        written.append(row)

    if written:
        session.flush()
    return written


def derive_windows_for_all_sections(session: Session, *, settings: Settings) -> None:
    """Derive every section's windows — the hourly reconciler's whole walk.

    `app.jobs.tasks.derive_survey_windows` runs this on `crontab(minute="30")` and
    `scripts/seed.py` runs it once after seeding its sections. It exists because a
    section can appear in the middle of a term — a staff launch or a roster sync
    creates one at any hour — and E2-06 deliberately does not hook the writer into
    those flows; ADR 0111 records that choice and the staleness of up to an hour it
    accepts.

    **The reads are made once for the whole walk and the writes stay per section**
    (E2-16 item 5). The reads were measured at three per section — the term, that
    term's weeks and that section's existing windows — which is 1,500 statements an
    hour at 500 sections, nearly all of them fetching one term's rows again;
    `_read_calendars` makes the same three for every section at once. The writes
    are deliberately left alone, because the containment below is what the walk is
    for.

    **One section's failure does not end the hour**, the shape
    `app.services.roster_sync.sync_all_rosters` already takes: each section runs
    inside a savepoint, a failure rolls back that section's own partial work and is
    logged with its traceback against the section it belongs to, and the walk moves
    on. The catch is broad on purpose. A narrow one would let a single section
    whose code no longer resolves — the map edited underneath it, E11's surface —
    starve every section after it in the walk, in this hour and in every hour
    after, and the sections that never got their windows would be the quiet half of
    that failure. `logger.exception` is what keeps it from being quiet.
    """
    sections = list(session.scalars(select(Section)))
    logger.info("the survey-window reconciler found %d section(s)", len(sections))
    calendars = _read_calendars(session, sections)
    for section in sections:
        savepoint = session.begin_nested()
        try:
            _write_windows_for_section(session, section, calendars, settings=settings)
            savepoint.commit()
        except Exception:
            savepoint.rollback()
            logger.exception(
                "the survey-window reconciler could not derive windows for section %s", section.id
            )


def open_window_for_section(
    session: Session,
    section: Section,
    *,
    settings: Settings,
    at: datetime | None = None,
) -> SurveyWindow | None:
    """Which of a section's windows is open, or `None` — SPEC §3.1's one-open rule.

    **Both ends are inclusive**: open when `opens_at <= instant <= closes_at`. So a
    section is open at exactly Friday 18:00:00 and still open at exactly Sunday
    23:59:59, which is the second §3.1 names, and shut a microsecond either side.

    **`at` is the seam a test can stand a boundary on, and every production caller
    leaves it `None`**, in which case the instant comes from `app.services.clock` —
    which is what makes the `/dev` control move this answer in the tool and in the
    worker alike. The development override is an offset on real time (ADR 0109) and
    is therefore still moving while it is read, so it can put the clock a known
    distance from a boundary and can never put it *on* one; inclusive and exclusive
    differ at exactly that instant, and `at` is how the difference is asserted.

    **A naive `at` is refused before anything else happens.** ADR 0019 spends a
    `TypeDecorator` keeping naive datetimes out of this schema — "the same value on
    two differently configured connections is two different moments" — and this is
    that hazard one layer up, where no column type can catch it. The refusal is a
    deliberate `ValueError` naming the parameter, rather than the `TypeError`
    Python raises on its own when a naive datetime meets an aware one: that one
    arrives only on the code path that reaches a comparison, so a naive value
    outside every window would be answered `None` instead of refused
    (`docs/MISTAKES.md` entry 29).

    At most one row can match, and it is the *derivation* that guarantees it: a
    Friday-to-Sunday span cannot overlap the next week's (E2-06's criterion 2
    asserts it over every seeded cohort). The order is fixed anyway so that a
    hand-written row someone adds later cannot make this answer depend on the
    order the database returns.
    """
    instant = _reading_instant(session, at, settings=settings)
    return session.scalars(
        select(SurveyWindow)
        .where(SurveyWindow.section_id == section.id, *_open_at(instant))
        .order_by(SurveyWindow.opens_at)
    ).first()


def open_windows_now(session: Session, *, settings: Settings) -> dict[UUID, SurveyWindow]:
    """Every section's open window right now, keyed by section id.

    The same question as `open_window_for_section`, asked about a whole page of
    sections in one statement: the development console (`app.api.dev`) renders a
    row per section and reads the answer off this. Both go through `_open_at`, so
    there is one reading of §3.1's comparison and not two.

    **By section id rather than by `Section` instance**, which is what separates it
    from the function above. The console's sections query deliberately reduces
    `section.lms_context_memberships_url` to a boolean in the database so the
    roster address is never selected onto that page's connection at all (ADR 0100),
    and loading `Section` rows there to ask this per section would undo it.

    The clock is read once, so every row of the page answers the same instant.
    """
    found: dict[UUID, SurveyWindow] = {}
    for window in session.scalars(
        select(SurveyWindow)
        .where(*_open_at(clock.now(session, settings=settings)))
        .order_by(SurveyWindow.opens_at)
    ):
        # `setdefault` rather than assignment, so this and the singular above agree
        # about which row they answer if a section ever holds two overlapping
        # windows: both take the one that opened first.
        found.setdefault(window.section_id, window)
    return found


def _open_at(instant: datetime) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    """The comparison that makes a window open at `instant`, both ends inclusive.

    One expression, used by both readers. `<=` on each end is E2-06's settled rule
    and the difference between it and `<` is exactly two instants in a week — the
    opening second and the closing second — which is why it is written once.
    """
    return (SurveyWindow.opens_at <= instant, SurveyWindow.closes_at >= instant)


def _reading_instant(session: Session, at: datetime | None, *, settings: Settings) -> datetime:
    """The instant an open/closed question is answered at: `at`, or what the clock says.

    The refusal comes first, before the clock is read and before any comparison is
    made, which is the position `docs/MISTAKES.md` entry 29 is about.
    """
    if at is not None and at.utcoffset() is None:
        raise ValueError(
            f"`at` was given {at!r}, which carries no UTC offset. A survey window's instants are "
            "stored aware (ADR 0019) because a naive value means two different moments on two "
            "differently configured connections, and this service will not guess which one was "
            "meant. Attach the timezone the instant was read in."
        )
    if at is not None:
        return at
    return clock.now(session, settings=settings)


def _window_for_course_week(
    section: Section, term_start: date, course_week: int, *, zone: ZoneInfo
) -> DerivedWindow:
    """One course week's window: the term week it falls in, and its two instants.

    The term week's Monday is `term_start + (term_week - 1) * 7` — the term's
    start date is the calendar's anchor, and §2.2 puts every start letter on a
    term-week Monday, so a course week's Friday is that Monday's Friday and not a
    count of seven-day periods from the section's own start date. The two agree
    for every cohort that starts in the term's first week, which is why the
    derivation is written from the term's Monday rather than from the section's.
    """
    term_week = week_of_the_term(
        course_week, section_start=section.start_date, term_start=term_start
    )
    monday = term_start + timedelta(days=(term_week - 1) * DAYS_PER_WEEK)
    return DerivedWindow(
        course_week=course_week,
        term_week=term_week,
        opens_at=_instant(monday + timedelta(days=OPENS_DAYS_AFTER_MONDAY), OPENS_AT, zone),
        closes_at=_instant(monday + timedelta(days=CLOSES_DAYS_AFTER_MONDAY), CLOSES_AT, zone),
    )


def _instant(day: date, wall_clock: time, zone: ZoneInfo) -> datetime:
    """A wall-clock time on one day in the institution's zone, as an aware UTC instant.

    **The zone is resolved for this day, and each end of a window comes through
    here separately.** That is the whole of the daylight-saving handling and it is
    the reason this is a function rather than an offset computed once per window: in
    Fall 2026 the week of Sunday 1 November opens on UTC-4 and closes on UTC-5, so
    an implementation that resolved one offset and added a `timedelta` for the other
    end is right for seventeen weeks of the term and an hour wrong for the
    eighteenth — long enough for a student's Sunday-evening submission to be refused
    by a window the screen said was open.

    Converted to UTC before it is returned so that every instant this service hands
    out is spelled one way. The column would accept either (ADR 0019 refuses only a
    *naive* value), and one spelling is what keeps two rows comparable by eye.
    """
    return datetime.combine(day, wall_clock, tzinfo=zone).astimezone(UTC)


def _term_of(session: Session, section: Section) -> Term:
    """The term a section's windows are derived against, or a refusal saying it is absent.

    `SectionCodeError`'s family rather than a new exception of this module's: a
    section naming a term this session cannot load is exactly what
    `app.services.section_codes.UnknownTermError` is for, and the hourly walk
    already treats that family as one section's problem rather than the walk's.
    """
    term = session.get(Term, section.term_id)
    if term is None:
        raise UnknownTermError(
            f"Section {section.lms_section_code!r} names the term {section.term_id!r}, which this "
            "session cannot load. A section's survey windows are derived from its term's calendar "
            "(SPEC §2.2, §3.1), so there is nothing to derive them from."
        )
    return term
