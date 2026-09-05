"""SPEC §3.4's participation score, and the gradebook column it is posted to — E3-03, E3-05.

Two halves, which is what SPEC §13 gives this file: "participation formula + AGS
passback".

**The formula** answers, for one section, what fraction of the items each
enrolled student could have completed they have completed, and the per-week
ledger that goes beside it. It reads the database through a sync `Session` and
nothing else — no network call, no AGS type, no job — so the arithmetic can be
measured without a platform. That property is unchanged and worth keeping:
`participation_scores` and every helper under it read the database and the clock.

**The line item** is in the middle of the file: SPEC §3.4's "One AGS line item per
section: 'Pulse Participation', created by the tool on first launch". A staff
launch asks for one through `request_line_item_creation`, a worker creates or
reconciles to it through `ensure_line_item`, and the id the platform served is
recorded on the section so that every later post can address it without walking a
container again (ADR 0128, ADR 0135).

**The weekly recompute** is at the foot: SPEC §3.4's "Re-posted whenever a
recomputation changes the value, ordinarily after each week closes."
`post_scores_for_all_sections` walks the sections whose term has not long ended,
computes each enrolled student's score through the formula above, compares it
against the latest `grade_sync` row for that student and section, and posts only
where the two differ (ADR 0137). The protocol is still `app.lti.ags`'s — what
lives here is which sections get asked, which students, when, and what is written
down afterwards.

`tests/unit/test_the_grading_module_reaches_no_network_ags_or_job.py` is E3-03's
criterion 8, and it is scoped to `participation_scores` and everything that
function reaches rather than to the whole file — `docs/disputes/E3-05-01.md`
carries the objection and the ruling that made it so, since SPEC §13 puts the
passback in this same module and a file-wide sweep would refuse it the imports
the spec says it holds. So the formula's own reach is guarded and the two halves
below it are not, which is why an import added here belongs to one half or the
other on purpose.

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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final
from uuid import UUID
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.lti.ags import (
    LINE_ITEM_ID_MEMBER,
    AgsCallError,
    AgsConflictError,
    AgsError,
    find_or_create_line_item,
    post_score,
)
from app.models.ai import Classification, ClassificationTask
from app.models.base import Base
from app.models.grades import GradeSync, GradeSyncOutcome
from app.models.identity import Enrollment
from app.models.lti import (
    AGS_LINE_ITEM_ADDRESS_COLUMN,
    AgsCall,
    RegistrationAddressError,
    refuse_invalid_fetched_address,
)
from app.models.org import Section
from app.models.survey import Answer, Response
from app.models.term import Term, Week
from app.services import clock
from app.services.authz import WriteSanction, guard_write, sanction_for
from app.services.identity import subject_for_user
from app.services.submissions import current_questions
from app.services.survey_windows import DerivedWindow, windows_for_section
from app.services.validity import REFUSED_VERDICT_TOKENS

__all__ = [
    "TERM_SWEEP_GRACE_DAYS",
    "ParticipationScore",
    "ensure_line_item",
    "outbound_transport",
    "participation_scores",
    "post_scores_for_all_sections",
    "request_line_item_creation",
    "score_timestamp_text",
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
# `app.models.lti.NrpsCall`, because the **formula** may not reach a module path
# holding `lti` — that is the rule keeping E3-04's AGS client out of the
# arithmetic, and the roster-sync log happens to share a module with it. The
# passback halves below reach that module freely and name it outright.
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


# ---------------------------------------------------------------------------
# SPEC §3.4's weekly recompute: post a score when it has changed (E3-06).
# ---------------------------------------------------------------------------

# How long after a term's last day the sweep goes on walking its sections. Two
# more weekly runs: one for the final week's post, one corrective pass for a
# reclassification that lands late. It stops there rather than never because SPEC
# §4 deletes raw responses at the end of the retention period — a sweep still
# walking a finished term would eventually recompute every student's score against
# comments that are no longer there and post the answer (ADR 0137).
TERM_SWEEP_GRACE_DAYS: Final[int] = 14

# What a conflict is recorded as. AGS 2.0 answers 409 when the platform holds a
# score newer than the one posted, and `AgsConflictError` carries no status of its
# own — it is the one refusal whose meaning is fixed by the protocol rather than
# read off a response — so the number is written here (ADR 0052, ADR 0137).
#
# Writing it rather than leaving the column NULL is what makes the section heal:
# D16 gives a `FAILED` row carrying a definite status a fresh delivery on the next
# run, and a conflict recorded as NULL would instead be read as a delivery whose
# outcome is unknown and re-sent byte for byte — the same instant the platform has
# already refused, every week, for as long as it holds something newer.
AGS_CONFLICT_STATUS: Final[int] = 409


def score_timestamp_text(instant: datetime) -> str:
    """The one rendering of a wire timestamp: UTC, ISO 8601, microseconds kept.

    ADR 0052 makes a retry the identical body re-sent, and identical means byte
    identical. `grade_sync` stores the instant that was sent, so a retry re-renders
    that stored instant and has to produce the exact characters the platform
    already accepted — which is only sound while there is one rendering, in one
    place. Two would drift the first time somebody preferred `Z` to `+00:00`.

    Three properties, each of which a different rendering gets wrong. A non-UTC
    aware instant is **converted** rather than relabelled, so a value that has been
    through a `timestamptz` column re-renders as what was sent. Microseconds
    survive, because Postgres stores them and ADR 0052 would otherwise read two
    deliveries a microsecond apart as retries of each other. And the offset is
    spelled `+00:00`, which is `datetime.isoformat`'s own spelling.
    """
    return instant.astimezone(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class _Delivery:
    """One student's post, decided before any HTTP call is made.

    The bytes are settled here rather than at the call site because ADR 0052's
    retry identity depends on which of two sources they came from: a retry carries
    the stored row's own characters and a new delivery carries the ones the formula
    just produced. Deciding that in one place, for the whole section, is also what
    makes "no HTTP call at all when nothing changed" a property of the shape rather
    than of a branch somebody has to remember.
    """

    user_id: UUID
    score_text: str
    ledger_text: str
    score_timestamp: datetime


def post_scores_for_all_sections(
    session: Session,
    *,
    settings: Settings,
    http: requests.Session | None = None,
    resolve: Callable[[str], Sequence[str]] | None = None,
) -> dict[str, int]:
    """Post every participation score that has changed since it was last sent.

    SPEC §3.4's "Re-posted whenever a recomputation changes the value, ordinarily
    after each week closes; fully automatic, no instructor action or override."
    `app.jobs.tasks.post_participation_scores` runs this weekly; the caller owns the
    session and the commit.

    **A difference, not a schedule** (ADR 0137). A posted score is not final when
    its week closes: E2-08's asynchronous reclassification can flip a comment that
    fell to §3.3's fail-open floor weeks after the window shut, which lowers the
    numerator of a number already sitting in somebody's gradebook. So the run is an
    idempotent sweep that posts where the computed pair differs from the latest
    `grade_sync` row and posts nothing otherwise, and the weekly beat entry is the
    ordinary trigger rather than the definition of the work.

    **No HTTP before a difference is found.** Scores and comparisons are computed
    from the database first, and a section where nobody needs a post makes no call
    at all — not a token grant, not a line-item read. Thirty thousand identical
    re-posts every Monday morning against every platform at once is the shape that
    avoids.

    **No retry and no backoff, which is ADR 0132's stance one layer up.** A failed
    post is recorded and left; the next weekly run is the retry, and it is the layer
    that has the memory a retry needs — it knows what has already been sent. A 409
    heals itself, because a conflict is recorded with its status and D16 gives a
    definitely-refused row a *fresh* delivery, whose real-time instant is later than
    whatever the platform holds. Re-sending the refused instant would ask the same
    question every Monday for the rest of term, which is why that narrowing is part
    of the sentence rather than a detail under it.

    **Each section is a transaction of its own** (D15): its work is committed before
    the next section starts, and a section that fails unexpectedly is rolled back,
    logged and stepped over so that one platform's bad afternoon does not leave every
    section after it ungraded. A post the platform *refused* is not such a failure —
    it is recorded, and the section commits with the record in it.

    **There is no savepoint, and its absence is the fix to a defect the commit grain
    introduced.** `app.services.survey_windows.derive_windows_for_all_sections` holds
    one because its whole walk is a single transaction, so a savepoint is the only
    way to undo one section of it. Here the section *is* the transaction, so
    `session.rollback()` takes back exactly the same work — and it is the only thing
    that can be called after a failure arriving from the commit itself, which a
    released savepoint cannot be rolled back after. The earlier shape held both, and
    a commit that failed reached a handler whose first statement raised
    `ResourceClosedError`: no log line, no rollback, no next section.

    **A section whose commit fails counts as nothing rather than as what it sent.**
    Its posts did reach the platform, and the rows describing them went back with the
    transaction, so the returned counts and `grade_sync` agree with each other and
    both under-report that section. Reporting the posts while holding no record of
    them would leave §6.1's console and the table disagreeing about a run nobody can
    reconstruct, and the next sweep re-posts what it finds no record of anyway.

    **The commit is per section because the rows are the record of a side effect
    that has already happened outside this process.** A score sitting in a gradebook
    is not undone by a worker dying, and under one commit at the end of the run the
    `grade_sync` and `ags_call` rows of every section already posted for would go
    with it — leaving Pulse believing it had posted nothing and re-posting the lot
    next Monday as new deliveries, with no account anywhere of the first ones. That
    is the argument `app.jobs.tasks.create_line_item` already makes one layer up
    about a single creation, at the grain a walk needs it.

    **The residue is named rather than hidden**: a section that fails unexpectedly
    mid-post still loses its own rows, because its work is one savepoint and a
    half-written section is not a record anybody can read. What D15 buys is that the
    loss is contained to the section it happened in instead of taking the whole
    walk's account with it (ADR 0137).

    Answers `{"posted": p, "failed": f}` — the counts of attempted posts that the
    platform took and did not, which is what the task hands to §6.1's console.
    """
    today = clock.today(session, settings=settings)
    # One real-time instant for the whole run, and real rather than effective on
    # purpose (ADR 0138): the AGS timestamp is a protocol ordering value the
    # platform compares against the one it holds, so a tool stamping it from the
    # development clock has made its own ordering rule movable. Content is
    # effective-clock — `participation_scores` counts elapsed weeks off
    # `clock.now` — and delivery is real-clock.
    stamped_at = datetime.now(UTC)
    transport = outbound_transport() if http is None else http

    # The walk is a list of ids rather than of rows, because each section is
    # committed before the next one begins and a commit expires every instance the
    # session holds. Re-reading the row inside its own section is what an expiry
    # would have done anyway, and it says what happens when the row has gone in the
    # meantime instead of raising `ObjectDeletedError` out of an attribute access.
    walked = list(
        session.scalars(
            select(Section.id)
            .join(Term, Term.id == Section.term_id)
            .where(
                Section.lms_ags_line_items_url.is_not(None),
                Term.end_date >= today - timedelta(days=TERM_SWEEP_GRACE_DAYS),
            )
            .order_by(Section.id)
        )
    )
    logger.info("the participation sweep found %d gradebook(s) inside its own bound", len(walked))

    posted = 0
    failed = 0
    for section_id in walked:
        try:
            answered = _post_one_sections_scores(
                session,
                section_id,
                settings=settings,
                http=transport,
                resolve=resolve,
                today=today,
                stamped_at=stamped_at,
            )
            # D15. Everything this section wrote down about what it sent is durable
            # here, before the next section is touched: the scores are already in a
            # gradebook and the record of them may not depend on a walk over the rest
            # of the institution finishing.
            session.commit()
        # Broad on purpose, and for `derive_windows_for_all_sections`' reason: a
        # narrow catch would let one section whose data no longer resolves starve
        # every section after it, this week and every week after.
        except Exception as escaped:
            # **One rollback, and no savepoint.** A section is a whole transaction
            # now — the section before it committed and the section after it has not
            # begun — so this takes back exactly the work a savepoint would have,
            # and it is the only thing here that can be called after a *commit* has
            # failed. A released savepoint cannot be rolled back, so the savepoint
            # this loop used to hold turned a failed commit into a
            # `ResourceClosedError` raised from inside this handler: the log line
            # below never ran, the session was never returned to a usable state, and
            # every remaining section of the institution was abandoned in silence
            # (E3-06's security re-review).
            session.rollback()
            # **The traceback is deliberately withheld**, which is where this
            # diverges from the window reconciler's `logger.exception`. A failure
            # on this path can carry a participation figure in its own text — a
            # refused insert renders its parameters, and those parameters are a
            # student's score and their ledger — and E3's breakdown decision 10
            # allows this job's log stream the outcome and the call and neither of
            # those. The class names of the failure and its cause are what an
            # operator reads; the rest is reproducible from the run.
            logger.error(
                "the participation sweep stepped over %s after an unexpected %s (%s)",
                section_id,
                type(escaped).__name__,
                type(escaped.__cause__).__name__,
            )
            continue
        posted += answered[0]
        failed += answered[1]
    return {"posted": posted, "failed": failed}


def _post_one_sections_scores(
    session: Session,
    section_id: UUID,
    *,
    settings: Settings,
    http: requests.Session | None,
    resolve: Callable[[str], Sequence[str]] | None,
    today: date,
    stamped_at: datetime,
) -> tuple[int, int]:
    """One section's whole run: what changed, and what the platform said about it."""
    section = session.get(Section, section_id)
    if section is None:
        logger.info(
            "%s was in the walk and is not there any more, so nothing was posted for it",
            section_id,
        )
        return 0, 0
    if section.ags_line_item_url is None:
        # ADR 0135's named window, closed by reusing the launch trigger's own
        # bounded publish rather than by adding a second schedule. Called through
        # this module so a substitution on it takes, and it never raises. Asked once
        # for the whole gradebook rather than once per student, and nothing is
        # posted this run: a score posted to an address this row does not hold goes
        # somewhere nobody chose.
        request_line_item_creation(session, section.id)
        logger.info(
            "%s records no participation column yet, so one was asked for and no score was posted "
            "for it this run",
            section.id,
        )
        return 0, 0

    scores = participation_scores(session, section, settings=settings)
    live = _live_enrollments(session, section, today=today)
    deliveries = [
        delivery
        for user_id in sorted(scores)
        if user_id in live
        and (delivery := _delivery_for(session, section, user_id, scores[user_id], stamped_at))
        is not None
    ]
    if not deliveries:
        return 0, 0

    subjects = _lms_user_ids(session, [delivery.user_id for delivery in deliveries])
    try:
        line_item = find_or_create_line_item(
            session, section.id, http=http, settings=settings, resolve=resolve
        )
    except AgsError as refusal:
        # The gradebook column could not be resolved, so no delivery was composed
        # and no `grade_sync` row is owed: the record of the attempt is the
        # `ags_call` rows the client already wrote, which the savepoint keeps. The
        # refusal's own text is never interpolated — `app/lti/ags.py` says why.
        logger.warning(
            "%s: its participation column could not be resolved (%s), so no score was posted for "
            "it this run",
            section.id,
            type(refusal).__name__,
        )
        return 0, 0

    posted = 0
    failed = 0
    for delivery in deliveries:
        subject = subjects.get(delivery.user_id)
        if subject is None:
            # A student the platform has no subject for cannot be addressed at all.
            # Unreachable through the foreign key, and answered rather than raised
            # so one unreadable row does not end the walk.
            logger.warning(
                "%s: a student it would have posted for carries no LMS subject, so nothing was "
                "sent for them",
                section.id,
            )
            continue
        outcome, response_code = _delivered(
            session,
            section,
            delivery,
            subject,
            line_item,
            http=http,
            settings=settings,
            resolve=resolve,
        )
        session.add(
            GradeSync(
                section_id=section.id,
                user_id=delivery.user_id,
                score_text=delivery.score_text,
                ledger_text=delivery.ledger_text,
                score_timestamp=delivery.score_timestamp,
                outcome=outcome,
                response_code=response_code,
            )
        )
        session.flush()
        if outcome is GradeSyncOutcome.POSTED:
            posted += 1
        else:
            failed += 1
    logger.info("%s: %d score(s) reached the platform and %d did not", section.id, posted, failed)
    return posted, failed


def _delivery_for(
    session: Session,
    section: Section,
    user_id: UUID,
    score: ParticipationScore,
    stamped_at: datetime,
) -> _Delivery | None:
    """What to send this student, or `None` where the platform already has it.

    ADR 0124's comparison, and there is no "the" row for a student and a section:
    the latest one by `created_at` is what the current value is, and a reader that
    took the last row written or the highest key would re-send whatever a student's
    score happened to be in September.

    Four answers, and the third is the whole of ADR 0052's retry identity:

      - **No row, or a pair that differs** — a new delivery, carrying the characters
        the formula just produced and this run's own instant.
      - **A `POSTED` row whose stored pair equals the computed one** — nothing, and
        no HTTP call on this student's account.
      - **A `FAILED` row whose stored pair equals the computed one and whose
        `response_code` is NULL** — a retry of *that* delivery, so the stored
        characters and the stored instant go out again. ADR 0129 gives that NULL one
        meaning: the call never reached the platform, so nobody knows whether the
        score landed. That unknown is what byte identity exists for — a platform
        that already holds the body accepts an equal timestamp as a repeat of one
        delivery and a value differing by a character as a second grade.
      - **A `FAILED` row whose stored pair equals the computed one and whose
        `response_code` is a number** — a fresh delivery, at this run's own instant
        (D16). The platform answered, and it answered no: the delivery was refused
        rather than lost, so there is no unknown for byte identity to protect. It
        matters most for a 409, where re-sending the refused instant asks the same
        question the platform already refused — every Monday, for the rest of the
        term — while a fresh real-time stamp is later than whatever the platform
        holds and heals the column on the next run.

    The comparison is over the **pair**, never the percentage alone. A
    reclassification, a question set that changed a week's denominator or a late add
    that moved which weeks count can each leave the number equal and the arithmetic
    behind it different, and SPEC §3.4 puts that arithmetic in the comment beside
    the score (ADR 0125).
    """
    latest = session.scalars(
        select(GradeSync)
        .where(GradeSync.section_id == section.id, GradeSync.user_id == user_id)
        .order_by(GradeSync.created_at.desc())
        .limit(1)
    ).first()
    if latest is not None and (latest.score_text, latest.ledger_text) == (
        score.percentage,
        score.ledger,
    ):
        if latest.outcome is GradeSyncOutcome.POSTED:
            return None
        if latest.response_code is None:
            return _Delivery(
                user_id=user_id,
                score_text=latest.score_text,
                ledger_text=latest.ledger_text,
                score_timestamp=latest.score_timestamp,
            )
    return _Delivery(
        user_id=user_id,
        score_text=score.percentage,
        ledger_text=score.ledger,
        score_timestamp=stamped_at,
    )


def _delivered(
    session: Session,
    section: Section,
    delivery: _Delivery,
    subject: str,
    line_item: Mapping[str, Any],
    *,
    http: requests.Session | None,
    settings: Settings,
    resolve: Callable[[str], Sequence[str]] | None,
) -> tuple[GradeSyncOutcome, int | None]:
    """Post one score and say what became of it, for the row that records the attempt.

    Every failure is answered rather than raised, because one student's refusal must
    not end the section's walk: a 409 on the alphabetically first student would
    otherwise leave everybody after them ungraded for the rest of term, with one row
    to explain it.

    The three outcomes are told apart by what an operator does about them. A 409 is
    recorded with its own literal status — the typed error carries none — because it
    is the one refusal waiting cannot fix. A refusal carrying a status is recorded
    with it. A call that never reached the platform is recorded with NULL, which is
    the single meaning ADR 0129 gives that column.

    **What is written here decides what the next run sends**, which is why the
    distinction is a correctness property rather than a note for a console. D16
    re-sends the stored bytes for a NULL and composes a fresh delivery for a status,
    so a status written as NULL would loop a refusal for ever and a NULL written as
    a status would turn a delivery that may already have landed into a second grade.

    **No exception's text is logged or interpolated.** `app/lti/ags.py` documents
    why: the message of a transport failure quotes the URL it could not reach, and
    a Result read filtered to one student carries that student's `sub` in its query.
    """
    try:
        post_score(
            session,
            section.id,
            user_id=subject,
            score=delivery.score_text,
            ledger=delivery.ledger_text,
            timestamp=score_timestamp_text(delivery.score_timestamp),
            line_item=line_item,
            http=http,
            settings=settings,
            resolve=resolve,
        )
    except AgsConflictError:
        logger.warning(
            "%s: the platform holds a newer score than the one offered for one of its students, so "
            "that post was recorded as refused and not retried",
            section.id,
        )
        return GradeSyncOutcome.FAILED, AGS_CONFLICT_STATUS
    except AgsCallError as refusal:
        logger.warning(
            "%s: a score was refused with status %s (%s), and the next scheduled run is the retry",
            section.id,
            refusal.status,
            type(refusal).__name__,
        )
        return GradeSyncOutcome.FAILED, refusal.status
    except AgsError as refusal:
        logger.warning(
            "%s: a score could not be posted (%s), and the next scheduled run is the retry",
            section.id,
            type(refusal).__name__,
        )
        return GradeSyncOutcome.FAILED, None
    return GradeSyncOutcome.POSTED, _accepted_status(session, section.id)


def _accepted_status(session: Session, section_id: UUID) -> int | None:
    """The status the platform answered on the call a successful post just made.

    `post_score` answers nothing, so the status a `POSTED` row records is read off
    the `ags_call` row that same post wrote — the newest one for this gradebook,
    since the score request is the last call the client makes. Read rather than
    assumed, because AGS 2.0 lets a platform answer either 200 or 201 to a Score and
    a constant here would record one of them as the other.

    Handing the status back from `post_score` would be plainer and is a change to a
    shared signature rather than to this file, so it is proposed in this ticket's
    pull request instead of taken.
    """
    return session.scalar(
        select(AgsCall.response_code)
        .where(AgsCall.section_id == section_id)
        .order_by(AgsCall.called_at.desc())
        .limit(1)
    )


def _live_enrollments(session: Session, section: Section, *, today: date) -> set[UUID]:
    """The students holding a live enrollment in this section today.

    SPEC §3.4's "Drops: scores stop updating; the LMS owns what happens to the
    column", and this is the one place that stop exists: ADR 0131 has
    `participation_scores` go on computing a departed student's score deliberately,
    because the formula answers what the enrolled weeks add up to and is not the
    place that decides who is still enrolled.

    The predicate is `app.services.authz`'s own — `started_on <= today AND (ended_on
    IS NULL OR ended_on >= today)` — so a drop-and-re-add has two rows and the live
    one wins, and a student whose enrollment ends *today* still posts, because they
    were enrolled today. Nothing is posted on the way out: no final zero, no
    blanking. What a gradebook does with the entry of a student who left is the
    platform's decision.
    """
    return set(
        session.scalars(
            select(Enrollment.user_id).where(
                Enrollment.section_id == section.id,
                Enrollment.started_on <= today,
                or_(Enrollment.ended_on.is_(None), Enrollment.ended_on >= today),
            )
        )
    )


def _lms_user_ids(session: Session, user_ids: Sequence[UUID]) -> dict[UUID, str]:
    """The platform's own subject for each of these students — the AGS `userId`.

    **This module reads no column of `user`, and cannot.** An AGS Score names its
    student by the LTI `sub`, which this system holds in exactly one place —
    `user.lms_user_id` — and E1-10's round-3 security review revoked that read from
    the application connection, because a connection able to make it can enumerate
    every subject that ever launched and join a response back to the person who
    gave it. So the subject comes from `app.services.identity.subject_for_user`,
    which is ADR 0094's `SECURITY DEFINER` mechanism run backwards (ADR 0139).

    **That door is not a containment, and this docstring said it was.** A scalar
    definer function is callable per row inside a `SELECT`, and this connection
    already lists `user.id`, so for anyone composing a query the door is as wide as
    the revoked column: ADR 0139 records the enumeration as given back rather than
    narrowed. What it buys is auditability — one inventoried, greppable function
    with a signature, an owner and a stated argument — and the line at a *name*,
    which stays unreachable from here by every mechanism this scheme has.

    So the call per student is a cost, not a guarantee: one statement beside the
    HTTP post each of these students is about to receive anyway. A student whose
    row has gone between the enrollment walk and this read is absent from the
    mapping, and the caller steps over them rather than failing the section they
    were in.
    """
    return {
        user_id: subject
        for user_id in user_ids
        if (subject := subject_for_user(session, user_id)) is not None
    }
