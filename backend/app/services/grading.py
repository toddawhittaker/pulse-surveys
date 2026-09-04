"""SPEC §3.4's participation score, computed and nothing else — E3-03.

For one section, this answers what fraction of the items each enrolled student
could have completed they have completed, and the per-week ledger that goes
beside it. It reads the database through a sync `Session` and does nothing else:
no network call, no AGS type, no job. Posting is E3-04's and E3-05's, and the
schedule is E3-06's, so the arithmetic can be measured without a platform
(`tests/unit/test_the_grading_module_reaches_no_network_ags_or_job.py` is the
sweep that keeps it that way).

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

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.ai import Classification, ClassificationTask
from app.models.base import Base
from app.models.identity import Enrollment
from app.models.org import Section
from app.models.survey import Answer, Response
from app.models.term import Week
from app.services import clock
from app.services.submissions import current_questions
from app.services.survey_windows import DerivedWindow, windows_for_section
from app.services.validity import REFUSED_VERDICT_TOKENS

__all__ = ["ParticipationScore", "participation_scores"]

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
