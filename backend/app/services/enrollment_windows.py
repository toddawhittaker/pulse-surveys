"""When a student's enrolment runs from — SPEC §3.4's three tiers, in one place.

§3.4 says which weeks belong to a student: "Late adds: denominator starts at the
student's first enrolled week (from NRPS enrollment data). Where the platform
supplies no enrollment dates — most supply none — a student counts as enrolled from
the section's start date." E3-04 built that reading as the three tiers
[ADR 0131](../../../docs/adr/0131-a-late-adds-first-week-is-decided-in-three-tiers.md)
records, and until this module they lived inside `app.services.grading` as private
helpers of the participation formula.

**Two surfaces answer the same question and only one of them was reading these
rules.** The participation score divides by the weeks a student is credited with;
§5.1's response rate divides by the students enrolled while a week's window was
open. Those are two questions about one fact — when did this enrolment begin — and
the report path was answering it from `enrollment.started_on` alone, which is the
column a roster sync writes when it *first sights* somebody and which a
platform-dated late add carries at the section's start. The consequence was not an
error anybody could see: three weeks of a section's response rates divided by one
too many, each rendering as a plausible percentage.
[ADR 0161](../../../docs/adr/0161-the-enrollment-window-has-one-home.md) records
the promotion, and it is the sentence ADR 0147 had already claimed — that the
report's denominator is computed "on the clock and enrolment helpers
`app/services/grading.py` already uses, so §3.4's window rules are read once".

**What is here and what is deliberately not.** The tier resolution, the roster-log
read tier 3 rests on, and the "had this enrolment begun by the time that window
closed" comparison whose `None` convention the two callers must agree about.
**Not** which course weeks a student is credited with, and **not** whether an
enrolment had ended — those are the two callers' own questions and they answer them
differently on purpose. §3.4 has a drop stop a score from *updating* rather than
remove weeks already earned, so `app.services.grading` reads `ended_on` nowhere;
§5.1's denominator is the people who could have answered *that week*, so
`app.services.reporting` does read it. A shared helper that folded the end date in
would have made one of those two wrong.

**Nothing here opens a connection, reads configuration or writes anything.** Both
callers hand in a session and the institution's timezone, which is the zone every
window's wall clock is stated in (SPEC §3.1).
"""

from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.identity import Enrollment

__all__ = [
    "began_by",
    "enrolled_from",
    "first_sync_day",
]

# Tier 3 compares against the section's earliest roster sync (ADR 0131). The row is
# read through the table on `Base.metadata` rather than through
# `app.models.lti.NrpsCall`, because the participation **formula** reaches this
# function and may not reach a module path holding `lti` — that is the rule keeping
# E3-04's AGS client out of the arithmetic, and the roster-sync log happens to share
# a module with it
# (`tests/unit/test_the_grading_module_reaches_no_network_ags_or_job.py`). The
# constant moved here with the function that reads it, unchanged.
NRPS_CALL = Base.metadata.tables["nrps_call"]


def first_sync_day(session: Session, *, section_id: UUID, zone: ZoneInfo) -> date | None:
    """The institution-timezone day the section's earliest roster sync fell on.

    `None` where the section has never been synced, which is the state seeded data
    is in and which makes every member of it tier 2. ADR 0131 takes the earliest
    call rather than any student's own first-sighting date, because only the log
    can say what the section's *first* sync was.

    **Only calls that read a roster count** (E3-08's boundary round, LO-M4).
    `nrps_call` is SPEC §6.1's log at the grain of one HTTP call, so it holds the
    attempts as well as the reads: a call the platform refused, one the token
    endpoint refused before the roster was asked at all, and one this container
    refused to make are all rows here, and `members_seen` is NULL on every one of
    them (`app.services.roster_sync._record_call`). Counting those as "the
    section's first sync" dates the tier-3 boundary from a sync that never
    happened — and the ordinary way to get one is a new registration whose first
    scheduled walk ran before its credentials were right, which then costs every
    undated member of that section the weeks between, permanently. A read that
    found an empty roster is a different thing and does count: `members_seen` is
    `0` there, which is not NULL.

    `tests/integration/test_a_refused_roster_call_does_not_date_a_late_add.py`
    holds that distinction and names this function.
    """
    earliest: datetime | None = session.scalar(
        select(func.min(NRPS_CALL.c.called_at)).where(
            NRPS_CALL.c.section_id == section_id,
            NRPS_CALL.c.members_seen.is_not(None),
        )
    )
    return None if earliest is None else earliest.astimezone(zone).date()


def enrolled_from(
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
      one of the section's weeks at the caller. A late add the first sync already
      contained cannot be told from a day-one student, and §3.4 accepts that
      under-credit outright: no rule can recover data the platform never supplied.

    **`None` is a value with a meaning and not an absence to guard against**, which
    is why `began_by` below exists rather than each caller writing the comparison:
    a caller that read `None` as "no weeks" would silently drop every member of
    every section a platform dates nobody in — which is most of them.
    """
    if enrollment.lms_window_start is not None:
        return enrollment.lms_window_start
    if first_sync_day is not None and enrollment.started_on > first_sync_day:
        return datetime.combine(enrollment.started_on, time.min, tzinfo=zone)
    return None


def began_by(enrolled_from: datetime | None, *, closes_at: datetime) -> bool:
    """Had an enrolment begun by the time this window closed?

    A week counts if the student could still have answered it — its window closes
    at or after the instant they were enrolled from — and `None` counts for every
    week, because tier 2 is "from the section's start date".

    One function rather than a comparison at each caller, because the two callers
    are `app.services.grading`'s credited weeks and `app.services.reporting`'s
    per-week denominator, and the `None` convention is the half of this rule a
    second copy would get wrong.
    """
    return enrolled_from is None or closes_at >= enrolled_from
