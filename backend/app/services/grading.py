"""SPEC §3.4's participation score, and the gradebook column it is posted to — E3-03, E3-05.

Two halves, which is what SPEC §13 gives this file: "participation formula + AGS
passback".

**The formula** answers, for one section, what fraction of the items each
enrolled student could have completed they have completed, and the per-week
ledger that goes beside it. It reads the database through a sync `Session` and
nothing else — no network call, no AGS type, no job — so the arithmetic can be
measured without a platform. That property is unchanged and worth keeping:
`participation_scores` and every helper under it read the database and the clock.

**The line item** is at the foot of the file: SPEC §3.4's "One AGS line item per
section: 'Pulse Participation', created by the tool on first launch". A staff
launch asks for one through `request_line_item_creation`, a worker creates or
reconciles to it through `ensure_line_item`, and the id the platform served is
recorded on the section so that every later post can address it without walking a
container again (ADR 0128, ADR 0135). Posting a *score* is still E3-06's, and the
protocol is still `app.lti.ags`'s — what lives here is which sections get asked,
when, and what may be written down afterwards.

`tests/unit/test_the_grading_module_reaches_no_network_ags_or_job.py` sweeps this
file for exactly the imports the second half is made of. That sweep is E3-03's
criterion 8, written while this module held only the first half; the disagreement
and the repair it needs are in `docs/disputes/E3-05-01.md`.

## The formula

Ruled 2026-09-04 and written into SPEC §3.4: **completed items ÷ total items**
across the student's elapsed weeks, not valid weeks ÷ elapsed weeks. A week
carries one item per question in the set in force, a rating or workload item is
completed by being answered, and a comment item is completed by being answered
*and* not refused by §3.3's classifier. So a week is a fraction rather than a
pass or a fail, and `response.is_valid` — E2-08's per-response verdict — is not
an input here at all: a per-response boolean cannot say which of a week's items
counted.

## The answer is a function of the current classification state, not of the week

A comment's governing verdict is the latest `classification` row for it, and that
table is append-only (ADR 0055). E2-08's asynchronous re-classification can flip
a floored comment to `insufficient` weeks after its window closed, which lowers a
numerator this module has already answered. Nothing here is wrong when that
happens — this module answers for the state it is asked in — but a score posted
earlier is then stale, and noticing that is E3-06's re-post-on-difference sweep.
That is why the recompute is a sweep rather than a one-shot.

A comment carrying no verdict at all cannot occur: the §3.3 fail-open floor
writes one (`app/ai/tasks.py`'s floor constants). If one ever did, it counts —
fail open, because SPEC §3.3's whole posture is that a student is never penalised
for an outage.

## What it reads, and what it never re-derives

The calendar comes from `app.services.survey_windows.windows_for_section` and the
time from `app.services.clock`; the week's item count comes from
`app.services.submissions.current_questions`, which is the same
highest-version rule the submission path itself serves (ADR 0130). None of the
three is re-derived here, because a second copy of any of them is how two pages
come to disagree about one section.

`enrollment.ended_on` is read nowhere. SPEC §3.4's "scores stop updating" is a
rule about posting and E3-06 owns it; this module computes the same thing for a
dropped student that it computes for an enrolled one, so the behaviour lives in
one place (ADR 0131).
"""

import logging
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from typing import Final
from uuid import UUID
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.lti.ags import LINE_ITEM_ID_MEMBER, find_or_create_line_item
from app.models.ai import Classification, ClassificationTask
from app.models.base import Base
from app.models.identity import Enrollment
from app.models.lti import (
    AGS_LINE_ITEM_ADDRESS_COLUMN,
    RegistrationAddressError,
    refuse_invalid_fetched_address,
)
from app.models.org import Section
from app.models.survey import Answer, Response
from app.models.term import Week
from app.services import clock
from app.services.authz import WriteSanction, guard_write, sanction_for
from app.services.submissions import current_questions
from app.services.survey_windows import DerivedWindow, windows_for_section
from app.services.validity import REFUSED_VERDICT_TOKENS

__all__ = [
    "ParticipationScore",
    "ensure_line_item",
    "outbound_transport",
    "participation_scores",
    "request_line_item_creation",
]

logger = logging.getLogger(__name__)

# This module's name in `authz.SANCTIONED_WRITERS`, resolved once at import so a
# name the catalog does not hold fails at startup rather than at the first write.
# `app.services.roster_sync` resolves its own the same way, for the same reason.
SANCTION: Final[WriteSanction] = sanction_for("grade_passback")

# SPEC §3.4's ledger line and the character its lines are joined with.
LEDGER_LINE = "Week {course_week}: {completed} of {total} items"
LEDGER_JOIN = "\n"

# The canonical percentage: one decimal place, always, rounded half up. ADR 0052
# makes the exact characters matter rather than the value — `61.5` and `61.50`
# are different AGS bodies — so the string is produced here and consumed
# unchanged by E3-02's store and E3-04's re-send. Half up is named because
# `Decimal.quantize` defaults to half even, which is a tenth low on every exact
# half at the second decimal.
PERCENTAGE_PLACES = Decimal("0.1")
PER_CENT = Decimal(100)

# Tier 3 compares against the section's earliest roster sync (ADR 0131). The row
# is read through the table on `Base.metadata` rather than through
# `app.models.lti.NrpsCall`, because this module may not name a module path
# holding `lti` — that is the rule keeping E3-04's AGS client out of the formula,
# and the roster-sync log happens to share a module with it.
NRPS_CALL = Base.metadata.tables["nrps_call"]


@dataclass(frozen=True, slots=True)
class ParticipationScore:
    """One student's participation in one section, as SPEC §3.4 states it.

    `total` is always greater than zero: a student with no elapsed enrolled week
    is absent from `participation_scores`' mapping rather than present with an
    empty denominator, which is how "nothing to post" is told from a real zero.
    """

    # Items the student completed across the weeks below.
    completed: int
    # Items those weeks carry in all — the denominator.
    total: int
    # The canonical percentage string, e.g. "80.0". Never a number.
    percentage: str
    # One line per elapsed week, in course-week order, newline-joined.
    ledger: str


def participation_scores(
    session: Session, section: Section, *, settings: Settings
) -> dict[UUID, ParticipationScore]:
    """Every enrolled student's participation in one section, keyed by their user id.

    One entry per enrolled student who has at least one elapsed enrolled week. A
    student with none is **absent from the mapping**, and a section whose first
    window has not closed answers an empty one: SPEC §3.4 wants "an absent score,
    never a posted zero, because a zero in a gradebook is a statement about a
    student and only absence is true before the first week closes". A student who
    was enrolled for a week and answered nothing is present, with a real "0.0".

    Which weeks are elapsed is a fact about the section, and which of those a
    student is credited with is a fact about their enrollment — §3.4's three
    tiers, resolved in `_first_course_week`. The two are separate on purpose: a
    late add can have no elapsed week of their own in a section that has several.
    """
    windows = windows_for_section(session, section, settings=settings)
    right_now = clock.now(session, settings=settings)
    elapsed = sorted(
        (window.course_week for window in windows if window.closes_at <= right_now),
    )
    if not elapsed:
        return {}

    items_per_week = _items_per_week(session)
    completed = _completed_items(session, section, windows)
    zone = ZoneInfo(settings.institution_timezone)
    first_sync_day = _first_sync_day(session, section, zone=zone)

    scores: dict[UUID, ParticipationScore] = {}
    for user_id, first_week in _first_enrolled_weeks(
        session, section, windows, first_sync_day=first_sync_day, zone=zone
    ).items():
        credited = [course_week for course_week in elapsed if course_week >= first_week]
        if not credited:
            continue
        scores[user_id] = _score(credited, completed[user_id], items_per_week)
    return scores


# ---------------------------------------------------------------------------
# The denominator: how many items a week carries.
# ---------------------------------------------------------------------------


def _items_per_week(session: Session) -> int:
    """How many items one week carries — the size of the question set in force.

    ADR 0130: the set is the one the submission path itself would serve, read
    through `current_questions` rather than resolved a second way here. A count
    written as a literal would be right for exactly as long as one version of the
    set exists.
    """
    questions = current_questions(session)
    if not questions:
        raise RuntimeError(
            "The question set in force carries no questions. SPEC §3.2 ships five and a week's "
            "items are that set's questions; `scripts/seed.py` writes the v1 set."
        )
    return len(questions)


# ---------------------------------------------------------------------------
# The numerator: which of a student's answers completed their item.
# ---------------------------------------------------------------------------


def _completed_items(
    session: Session, section: Section, windows: list[DerivedWindow]
) -> defaultdict[UUID, dict[int, int]]:
    """How many items each student completed in each course week of one section.

    A rating or workload answer counts by existing: ADR 0115 deletes a withdrawn
    answer's row, so the rows present are a faithful record of what was answered
    and an absent row — a blank optional comment included — is one item not
    completed. A comment answer counts unless its latest verdict refuses it.
    """
    course_week_of = _course_weeks_by_week_id(session, section, windows)
    rows = session.execute(
        select(Response.user_id, Response.week_id, Answer.id, Answer.comment_text)
        .join(Answer, Answer.response_id == Response.id)
        .where(Response.section_id == section.id)
    ).all()

    refused = _refused_comments(
        session, [answer_id for _user, _week, answer_id, comment in rows if comment is not None]
    )

    completed: defaultdict[UUID, dict[int, int]] = defaultdict(dict)
    for user_id, week_id, answer_id, comment in rows:
        course_week = course_week_of.get(week_id)
        if course_week is None:
            continue
        if comment is not None and answer_id in refused:
            continue
        counts = completed[user_id]
        counts[course_week] = counts.get(course_week, 0) + 1
    return completed


def _refused_comments(session: Session, answer_ids: list[UUID]) -> set[UUID]:
    """Of the comment answers named, the ones whose latest verdict is in §3.3's refused set.

    The ordering is `app.services.validity._latest_verdicts`' own — `classified_at`
    descending and then the row's key, because `classified_at` is a server default
    at microsecond resolution and two rows written in one transaction can share a
    value. Read as an outer question rather than as a join: a comment with no
    classification row at all is simply not in the answer, which counts it (fail
    open), where an inner join would have dropped its item instead.
    """
    if not answer_ids:
        return set()
    latest: dict[UUID, str] = {}
    for answer_id, verdict in session.execute(
        select(Classification.answer_id, Classification.verdict)
        .where(
            Classification.answer_id.in_(answer_ids),
            Classification.task == ClassificationTask.COMMENT_VALIDITY,
        )
        .order_by(Classification.classified_at.desc(), Classification.id.desc())
    ):
        latest.setdefault(answer_id, verdict)
    return {answer_id for answer_id, verdict in latest.items() if verdict in REFUSED_VERDICT_TOKENS}


def _course_weeks_by_week_id(
    session: Session, section: Section, windows: list[DerivedWindow]
) -> dict[UUID, int]:
    """Which course week each of the section's `week` rows is, by that row's id.

    A response names the term's week (SPEC §2.2's term axis) and the ledger counts
    in course weeks, and `DerivedWindow` carries both axes precisely so neither has
    to be re-derived from the other.
    """
    course_week_of_term_week = {window.term_week: window.course_week for window in windows}
    return {
        week_id: course_week_of_term_week[number]
        for week_id, number in session.execute(
            select(Week.id, Week.number).where(
                Week.term_id == section.term_id,
                Week.number.in_(list(course_week_of_term_week)),
            )
        )
    }


# ---------------------------------------------------------------------------
# Which weeks are a student's: SPEC §3.4's three tiers (ADR 0131).
# ---------------------------------------------------------------------------


def _first_sync_day(session: Session, section: Section, *, zone: ZoneInfo) -> date | None:
    """The institution-timezone day the section's earliest roster sync fell on.

    `None` where the section has never been synced, which is the state seeded data
    is in and which makes every member of it tier 2. ADR 0131 takes the earliest
    call rather than any student's own first-sighting date, because only the log
    can say what the section's *first* sync was.
    """
    earliest: datetime | None = session.scalar(
        select(func.min(NRPS_CALL.c.called_at)).where(NRPS_CALL.c.section_id == section.id)
    )
    return None if earliest is None else earliest.astimezone(zone).date()


def _first_enrolled_weeks(
    session: Session,
    section: Section,
    windows: list[DerivedWindow],
    *,
    first_sync_day: date | None,
    zone: ZoneInfo,
) -> dict[UUID, int]:
    """The first course week each of the section's students is credited with.

    A student who dropped and re-added has two non-overlapping enrollment rows
    (`Enrollment`'s own docstring), and SPEC §3.4 dates the denominator from "the
    student's first enrolled week" — so the earliest of their rows decides. The
    gap between two rows is not read, for the same reason `ended_on` is not: what
    a drop stops is posting, and that is E3-06's.
    """
    first_weeks: dict[UUID, int] = {}
    for enrollment in session.scalars(
        select(Enrollment).where(Enrollment.section_id == section.id)
    ):
        week = _first_course_week(enrollment, windows, first_sync_day=first_sync_day, zone=zone)
        if week is None:
            continue
        held = first_weeks.get(enrollment.user_id)
        if held is None or week < held:
            first_weeks[enrollment.user_id] = week
    return first_weeks


def _first_course_week(
    enrollment: Enrollment,
    windows: list[DerivedWindow],
    *,
    first_sync_day: date | None,
    zone: ZoneInfo,
) -> int | None:
    """The earliest course week this enrollment is credited with, or `None` for no week at all.

    A week counts if the student could still have answered it — its window closes
    at or after the instant they were enrolled from. `None` means every one of the
    section's windows had closed before that instant, which is a student with
    nothing to score.
    """
    enrolled_from = _enrolled_from(enrollment, first_sync_day=first_sync_day, zone=zone)
    if enrolled_from is None:
        return min(window.course_week for window in windows)
    still_open = [window.course_week for window in windows if window.closes_at >= enrolled_from]
    return min(still_open) if still_open else None


def _enrolled_from(
    enrollment: Enrollment, *, first_sync_day: date | None, zone: ZoneInfo
) -> datetime | None:
    """The instant a student's enrollment runs from, under §3.4's tiers, or `None` for tier 2.

    - **Tier 1** — the platform dated them, so its instant is the answer. It is
      consulted first: §3.4 dates the denominator "from NRPS enrollment data" and
      falls back to the observed record only "where the platform supplies no
      enrollment dates".
    - **Tier 3** — the platform did not, the section has been synced, and this
      student was first seen after the day of that first sync. Their day begins in
      the institution's own timezone, which is the zone every window's wall clock
      is in.
    - **Tier 2** — otherwise the section's start, which is `None` here and every
      course week at the caller. A late add the first sync already contained
      cannot be told from a day-one student, and §3.4 accepts that under-credit
      outright: no rule can recover data the platform never supplied.
    """
    if enrollment.lms_window_start is not None:
        return enrollment.lms_window_start
    if first_sync_day is not None and enrollment.started_on > first_sync_day:
        return datetime.combine(enrollment.started_on, time.min, tzinfo=zone)
    return None


# ---------------------------------------------------------------------------
# The three numbers and the ledger, from one pass over the credited weeks.
# ---------------------------------------------------------------------------


def _score(
    credited_weeks: list[int], completed_by_week: dict[int, int], items_per_week: int
) -> ParticipationScore:
    """One student's score over the course weeks they are credited with.

    One pass produces the ledger and the two numbers together, so a line and the
    arithmetic beside it cannot come from different readings of the same weeks. A
    week the student missed is a line reading `0 of N` and its full share of the
    denominator — SPEC §3.4: "never omitted from the denominator".
    """
    lines: list[str] = []
    completed = 0
    for course_week in credited_weeks:
        done = completed_by_week.get(course_week, 0)
        completed += done
        lines.append(
            LEDGER_LINE.format(course_week=course_week, completed=done, total=items_per_week)
        )
    total = len(credited_weeks) * items_per_week
    return ParticipationScore(
        completed=completed,
        total=total,
        percentage=_percentage(completed, total),
        ledger=LEDGER_JOIN.join(lines),
    )


def _percentage(completed: int, total: int) -> str:
    """The canonical percentage string: one decimal place, always, rounded half up."""
    quotient = Decimal(completed) / Decimal(total) * PER_CENT
    return str(quotient.quantize(PERCENTAGE_PLACES, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# SPEC §3.4's line item: asked for on a launch, created by a worker (E3-05).
# ---------------------------------------------------------------------------


def outbound_transport() -> requests.Session | None:
    """The HTTP transport the creation worker calls a platform over. `None` in production.

    A module-level seam and not a detail: `app.lti.ags` takes its transport as an
    argument precisely so a test can drive it, and a Celery task has no caller to
    pass one. So the worker asks this function, and a test substitutes it — the
    same role ADR 0101's `resolve` plays for name resolution, and the same argument
    (`tests/fixtures/line_item_creation.py::reaching_the_platform` is the
    substitution).

    `None` is the honest production answer rather than a built session: the client
    builds one of its own, with redirects off and its resolution pinned, and a
    session assembled here would be a second place those decisions could be made.

    **Consulted through this module, never bound at import.** `ensure_line_item`
    calls `outbound_transport()` by name, so a substitution on
    `app.services.grading` takes; a `from app.services.grading import
    outbound_transport` elsewhere would bind the original and the substitution
    would silently do nothing.
    """
    return None


def request_line_item_creation(session: Session, section_id: UUID) -> bool:
    """Ask for this section's participation column to be created, if it needs one.

    SPEC §3.4's "created by the tool on first launch", from the door's side.
    `app.api.lti.launch` calls it after a staff launch has been committed, on the
    section `provision_from_launch` answered — which is the *only* decision point
    about who may trigger this. §7.3's rule (an instructor launch triggers, a
    leadership launch triggers only inside the launcher's own purview, a student
    launch triggers nothing) is already computed there, and asking it a second time
    here would be two answers to one question (`docs/MISTAKES.md` entry 13). The
    ruling of 2026-09-04 makes the student half a requirement rather than a
    default: a student launch must never cause a write to a platform's gradebook.

    **Two conditions, and each is a different fact about the section** (ADR 0135):

      - **No container address** — the platform advertised no AGS claim, so there
        is nowhere to create a column and nothing a worker could do but fail. E3-02
        settled that this is a configuration and not a fault, so it records no
        defect; an institution that grants this tool no gradebook scope would
        otherwise put a line on §6.3's console for every one of its sections.
      - **An id already recorded** — the column exists and this tool knows its
        address, so there is nothing to ask for. That check is the idempotence and
        the retry rule in one: while the id is NULL every qualifying launch asks
        again, and the moment one is stored no launch asks anything. It is also
        what pays for the deliberate absence of a debounce here, since a section in
        the steady state costs one column read per staff launch.

    **It never raises and never delays the launch.** The publish goes through
    `app.jobs.celery_app.publish_once`, so a broker that is not there refuses at
    once rather than holding a request that has already done its own job
    (`docs/MISTAKES.md` entry 41), and the broad `except` is what keeps a queue
    outage from becoming a person unable to enter the product. The failure is
    logged at error level, which is the visibility, and the next qualifying launch
    is the retry — there is no scheduled backstop in this ticket, and ADR 0135
    names E3-06's sweep as the one that becomes it.

    Answers whether a publish went out, for a caller that wants to say so.
    """
    section = session.get(Section, section_id)
    if section is None:
        logger.warning(
            "no section %s exists to ask a participation column for; a launch resolved an "
            "identifier this connection cannot read back",
            section_id,
        )
        return False
    if section.lms_ags_line_items_url is None:
        logger.info(
            "section %s advertises no gradebook container, so no participation column was asked "
            "for (a platform that grants no AGS scope is a state rather than a fault)",
            section_id,
        )
        return False
    if section.ags_line_item_url is not None:
        return False

    # Imported here rather than at module scope because `app.jobs.tasks` imports
    # this module: the task is a thin wrapper over these functions, so a top-level
    # import would be a cycle. Same shape as `app.services.roster_sync`'s trigger.
    from app.jobs.celery_app import publish_once
    from app.jobs.tasks import create_line_item

    try:
        publish_once(create_line_item, args=(str(section_id),))
    # Broad on purpose, and the docstring is the argument: kombu, redis-py and
    # Celery each raise their own family here, and an enumerated list of them is a
    # list that goes stale into a failed launch.
    except Exception:
        logger.exception(
            "section %s could not be enqueued for a participation column; the next staff launch "
            "will ask again",
            section_id,
        )
        return False
    return True


def ensure_line_item(
    session: Session,
    section_id: UUID,
    *,
    http: requests.Session | None = None,
    settings: Settings | None = None,
    resolve: Callable[[str], Sequence[str]] | None = None,
) -> None:
    """Create or reconcile to this section's participation column, and record its address.

    The worker half of SPEC §3.4's first-launch creation, and the only writer of
    `section.ags_line_item_url`. `app.jobs.tasks.create_line_item` is what runs it;
    the caller owns the session and the commit.

    **The row is locked first, and everything is decided under the lock.** Two
    staff launches of one section seconds apart are ordinary — a class opening the
    tool at the top of the hour — and both may reach a worker before either has
    written anything. `SELECT … FOR UPDATE` makes the second wait for the first,
    and re-reading both columns afterwards is what turns that wait into an answer:
    the second finds the id its predecessor recorded and returns without calling
    anything. Without the re-read the lock would only have serialised two identical
    creates.

    **No HTTP is attempted before either check.** A column that already exists and
    a section with no gradebook are both decided off the row, so the ordinary
    steady-state cost of this task is one locked read.

    **The answered id is judged before it is stored**, by the same fetched-address
    rules the roster address is judged by (`app.models.lti`). It is an address the
    *platform* chose at run time, and this tool fetches it with its own credentials
    on a schedule with nobody present — so a refusal stores nothing, logs at error,
    and leaves the column NULL for the next qualifying launch to retry. E3-04's
    client judges it as well, one layer down; two layers judging one untrusted
    value is the intent rather than an oversight, and neither is written in terms of
    the other.

    **The write passes the chokepoint.** `section` is LMS-owned (SPEC §2.1, §8), so
    the assignment is preceded by `guard_write` with this module's own catalog
    entry — ADR 0090's rule, and ADR 0136 records why `grade_passback` holds
    `section` and why the database narrows it to one column.

    Every AGS failure is left to propagate to the worker's log: creation carries no
    score, no ledger and no user identifier, so there is nothing in the traceback
    that may not appear there (E3's breakdown decision 10).
    """
    settings = Settings() if settings is None else settings
    section = session.get(Section, section_id, with_for_update=True)
    if section is None:
        logger.warning(
            "no section %s exists to create a participation column for; it was deleted after this "
            "job was enqueued",
            section_id,
        )
        return
    if section.ags_line_item_url is not None:
        logger.info(
            "section %s already records a participation column, so this run created nothing",
            section_id,
        )
        return
    if section.lms_ags_line_items_url is None:
        logger.info(
            "section %s advertises no gradebook container, so there is nothing to create a "
            "participation column in",
            section_id,
        )
        return

    document = find_or_create_line_item(
        session,
        section_id,
        http=outbound_transport() if http is None else http,
        settings=settings,
        resolve=resolve,
    )
    identifier = document.get(LINE_ITEM_ID_MEMBER)
    if not isinstance(identifier, str) or not identifier:
        logger.error(
            "the platform served a participation column carrying no address of its own for "
            "section %s, so nothing was recorded",
            section_id,
        )
        return
    try:
        refuse_invalid_fetched_address(
            settings.environment,
            column=AGS_LINE_ITEM_ADDRESS_COLUMN,
            address=identifier,
            resolve=resolve,
        )
    except RegistrationAddressError:
        logger.exception(
            "the address the platform gave its participation column is one this environment will "
            "not fetch, so nothing was recorded for section %s",
            section_id,
        )
        return

    guard_write(table="section", sanction=SANCTION)
    section.ags_line_item_url = identifier
