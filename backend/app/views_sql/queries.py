"""Typed ways into the read views, so no screen has to spell the SELECT (SPEC §13).

§13 puts "migrations + query helpers" in this package. What these helpers are is
typed convenience over the view SQL: each view's column list written out once, in
the order the view declares it, so a screen that needs a roster gets frozen rows
with names on them rather than a `SELECT` copied into every caller.

**What forecloses the hand-written base-table join is the database, not this
module**, and an earlier version of this docstring had it backwards. It argued
that a screen finding no helper writes `SELECT … FROM enrollment JOIN …` against
the base tables "which works, because `pulse_app` can read the view's *sources*
through the view's owner", and that "the refusal only fires when somebody reaches
for `user_identity`". Owner privileges chain through the view object and nowhere
else: a query naming a base table directly is checked against its own privileges.
Measured on this branch with `SET ROLE pulse_app` — `public.enrollment` 42501,
`public.section` 42501, `public.user_identity` 42501, `public.section_roster`
permitted. So a hand-rolled join is refused by Postgres rather than quietly
working, and identity is not the only thing it is refused. `CONTRIBUTING.md`'s
"Read paths go through `views_sql/`" states the same rule the right way round.

**`services/authz.py` is the only caller.** It imports both helpers, and
`ScopedReader.section_roster` and `ScopedReader.section_enrollment_counts`
check the purview and then pass the session and key straight through to
them — the chokepoint is the one door these two are reached from, not a
second way in beside it.

**These return plain frozen rows, not ORM entities, and deliberately.** A view is
not on `Base.metadata` (E0-10: views ship "as Alembic migrations under
`views_sql/`, not as ORM constructs"), so there is no mapped class to hand back,
and there should not be one: a mapped view invites a write path into a relation
that cannot take one, and makes `alembic check` compare a table that is not one.

**Nothing here filters by who is asking.** Scoping a read to an actor's purview
is `services/authz.py`'s single chokepoint, which is E0-11's, and a second
half-answer to the same question living here is how the two come apart. These
helpers take the keys they are given.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

__all__ = [
    "BenchmarkSetRatingWeekRow",
    "BenchmarkSetWeekRow",
    "SectionEnrollmentCount",
    "SectionRosterRow",
    "benchmark_set_rating_week",
    "benchmark_set_week",
    "section_enrollment_counts",
    "section_roster",
]

# The view columns, spelled once. Ordered as the view declares them, so a reader
# comparing this against `section_roster_v001.sql` is comparing two lists in the
# same order rather than looking each one up.
_SECTION_ROSTER = text(
    "SELECT enrollment_id, user_id, section_id, started_on, ended_on,"
    " course_id, term_id, lms_section_code, length_weeks,"
    " section_start_date, section_end_date"
    " FROM public.section_roster"
    " WHERE section_id = :section_id"
    " ORDER BY started_on, enrollment_id"
)

_SECTION_ENROLLMENT_COUNTS = text(
    "SELECT section_id, course_id, term_id, lms_section_code, enrolled_count"
    " FROM public.section_enrollment_count"
    " WHERE course_id = :course_id"
    " ORDER BY lms_section_code"
)


@dataclass(frozen=True, slots=True)
class SectionRosterRow:
    """One person's membership of one section, by key.

    No name and no email address, because `public.section_roster` selects
    neither — and the view's own column list is the whole of why. A view is read
    with its owner's privileges, so a view that *did* select an identity column
    would hand it to `pulse_app` without its empty grant on
    `public.user_identity` ever being consulted (§4, §8). What keeps that from
    happening is the structural sweep in
    `tests/integration/test_identity_column_marker.py`, not this connection.
    """

    enrollment_id: UUID
    user_id: UUID
    section_id: UUID
    started_on: date
    ended_on: date | None
    course_id: UUID
    term_id: UUID
    lms_section_code: str
    length_weeks: int
    section_start_date: date
    section_end_date: date


@dataclass(frozen=True, slots=True)
class SectionEnrollmentCount:
    """How many people one section holds."""

    section_id: UUID
    course_id: UUID
    term_id: UUID
    lms_section_code: str
    enrolled_count: int


def section_roster(session: Session, *, section_id: UUID) -> Sequence[SectionRosterRow]:
    """Everybody enrolled in `section_id`, oldest enrollment first."""
    rows = session.execute(_SECTION_ROSTER, {"section_id": section_id}).mappings()
    return [SectionRosterRow(**row) for row in rows]


def section_enrollment_counts(
    session: Session, *, course_id: UUID
) -> Sequence[SectionEnrollmentCount]:
    """One count per section of `course_id`, including the sections holding nobody."""
    rows = session.execute(_SECTION_ENROLLMENT_COUNTS, {"course_id": course_id}).mappings()
    return [SectionEnrollmentCount(**row) for row in rows]


# E5-03's two benchmark set functions, reached the way every read in this package
# is reached. They are functions rather than views because the comparison set
# E5-04 resolves is a list of sections rather than a key, and because a cohort
# figure over such a list is computed where the rows are and comes back as
# numbers: the application holds `EXECUTE` on two aggregate-returning bodies
# rather than `SELECT` on a relation keyed to a student. That is a statement
# about what joins the sanctioned read surface rather than about what this
# connection can reach — it has read `response` and `answer` since the E2
# submission path, and what it cannot read is a person. The SQL files carry the
# argument in full, and the amendment on `docs/disputes/E5-03-01.md` records the
# wider claim the ruling first made and withdrew.
#
# Written here rather than in the service that will call them so that E5-04 has
# no reason to spell a statement of its own — which is the state
# `tests/unit/test_the_org_views_are_read_only_through_the_grant.py` exists to
# prevent, and which here would put this ticket's arithmetic in a second place.
#
# The array is bound and cast rather than interpolated, and the ids are passed as
# text: the function takes `uuid[]`, and a list of literals spliced into the
# statement would be a caller's value reaching the SQL.
_BENCHMARK_SET_WEEK = text(
    "SELECT course_week, workload_mean, workload_median,"
    " response_count, respondent_count, section_count"
    " FROM public.benchmark_set_week(CAST(:section_ids AS uuid[]))"
    " ORDER BY course_week"
)

_BENCHMARK_SET_RATING_WEEK = text(
    "SELECT course_week, stream, rating_mean, rating_count"
    " FROM public.benchmark_set_rating_week(CAST(:section_ids AS uuid[]))"
    " ORDER BY course_week, stream"
)


@dataclass(frozen=True, slots=True)
class BenchmarkSetWeekRow:
    """One course week's workload statistics and counts over a set of sections.

    `workload_mean` and `workload_median` are `None` for a course week whose
    responses carry no hours: the week had data and this particular figure did
    not, and a zero would be a statement about how long those students worked
    that none of them made. The three counts are always real, and
    `respondent_count` is a count of **people** — the figure E5-04 compares
    against its minimum.
    """

    course_week: int
    workload_mean: Decimal | None
    workload_median: Decimal | None
    response_count: int
    respondent_count: int
    section_count: int


@dataclass(frozen=True, slots=True)
class BenchmarkSetRatingWeekRow:
    """One course week and stream's rating figures over a set of sections.

    `rating_count` counts ratings, not people. A stream nobody answered has no
    row rather than a row with a null mean.
    """

    course_week: int
    stream: str
    rating_mean: Decimal
    rating_count: int


def benchmark_set_week(
    session: Session, *, section_ids: Sequence[UUID]
) -> Sequence[BenchmarkSetWeekRow]:
    """The workload statistics and counts of each answered course week, over `section_ids`.

    An empty set answers no rows: a named set may have no members and a default
    set may be empty once the hero section is taken out of it, so it is an
    ordinary input rather than a programming error.
    """
    parameters = {"section_ids": [str(section_id) for section_id in section_ids]}
    rows = session.execute(_BENCHMARK_SET_WEEK, parameters).mappings()
    return [BenchmarkSetWeekRow(**row) for row in rows]


def benchmark_set_rating_week(
    session: Session, *, section_ids: Sequence[UUID]
) -> Sequence[BenchmarkSetRatingWeekRow]:
    """The per-stream rating figures of each answered course week, over `section_ids`."""
    parameters = {"section_ids": [str(section_id) for section_id in section_ids]}
    rows = session.execute(_BENCHMARK_SET_RATING_WEEK, parameters).mappings()
    return [BenchmarkSetRatingWeekRow(**row) for row in rows]
