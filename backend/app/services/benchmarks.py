"""Which sections a comparison figure is computed over, and the figure itself (SPEC §13).

SPEC §5.1 puts three populations on an instructor's report and this module is
where each becomes a list of section ids:

  - the **default set** — the same Lead Faculty's courses, filtered to the hero
    section's length and level, with the hero section itself taken out;
  - the **university line** — every section of that same length and level in the
    institution, hero included;
  - a **named set** — the member courses of one `comparison_set`, at the length
    that set declares.

All three are past-referencing: week N of a section is compared against week N
of matching sections in the current term *and* every term §4's retention rule
still keeps. Nothing here filters on a term, and that absence is the feature.

**Every figure this module emits is sealed by `comparison_after_suppression`
and there is no second route to one.** SPEC §4.1 item 7 suppresses "a mean, a
median, or any other statistic" computed from a comparison set below either
configured minimum, and E4-07 made that decision the only way a `ComparisonFigure`
can be built (ADR 0155). This module is a caller of that chokepoint and adds
nothing to it: `_sealed` below is the single place a figure is constructed, it
takes the counts from the row the figure came from, and it is reached once per
figure — per week of a trend, and separately for a workload mean and its median.
A week the cohort answered nothing in is a *suppressed* point rather than an
absent one, because a gap in a chart and a withheld number say different things
to a reader.

**A benchmark figure counts every stored response, exactly as the section's own
report figures do; `response.is_valid` is not filtered.** SPEC §3.3 classifies a
submission and `report_workload` and `report_rating_distribution` do not read
the verdict either, so a comparison figure and the section figure drawn beside
it are computed over the same rows. Ruled in the open at E5's wave-2 launch and
recorded here because this is where comparison policy lives; the question came
from E5-03 and is closed in `docs/tickets/e5/deferred.md`.

**The arithmetic is not here.** Every mean, median and count comes from E5-03's
two `SECURITY DEFINER` set functions, which take a section-id array and answer
one row per course week (ADR 0165). This module resolves ids, asks, and seals.
Nothing in it averages, counts or divides, so there is no second implementation
of a benchmark figure to keep in step with the first — ADR 0166 records why the
per-term cohort views cannot be aggregated in their place.

**How the relations are reached.** The two set functions are called through
statements spelled in this file rather than through `app.views_sql.queries`,
which `tests/unit/test_the_org_views_are_read_only_through_the_grant.py` keeps
to a single importer — the authorization chokepoint. The development console
takes the same route for the same reason and says so at
`backend/app/api/dev.py`'s `_SECTION_ENROLLED_COUNTS`. Neither function is a
relation that sweep polices, so no exemption is involved; what is duplicated is
two statements, recorded in `docs/tickets/e5/deferred.md`. Everything else —
`section`, `course`, `lead_faculty_course`, the comparison-set tables and the
term-axis view — is read through SQLAlchemy Core, which is how
`app.services.reporting` reads the report views.
"""

import enum
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, column, select, table, text
from sqlalchemy.orm import Session

from app.models.benchmark import ComparisonSet, ComparisonSetMember
from app.models.org import Course, CourseLevel, Section
from app.services.reporting import ComparisonFigure, comparison_after_suppression

# ---------------------------------------------------------------------------
# The relations this module reads, as Core constructs.
# ---------------------------------------------------------------------------

# ADR 0046's read over `lead_faculty_mapping`: "one lead per course", so the
# hero's course has at most one person and that person's courses are the default
# set. Read through this view rather than through `role_assignment.course_id`,
# which E0-09 measured as accepting a row the mapping gives to a sibling lead —
# SPEC §4.1 invariant 2, reached through a benchmark.
_LEAD_FACULTY_COURSE = table(
    "lead_faculty_course",
    column("person_id"),
    column("course_id"),
)

# E5-03's term-axis cohort view, keyed by a length, a level, a term and the start
# date of the cohort inside it (ADR 0165). The four column names this module
# reads off it are the ruling's own, and the two counts are what its figures are
# suppressed against.
_COHORT_TERM_AXIS = table(
    "benchmark_cohort_term_axis",
    column("length_weeks"),
    column("level"),
    column("term_id"),
    column("section_start_date"),
    column("term_week"),
    column("workload_mean"),
    column("workload_median"),
    column("respondent_count"),
    column("section_count"),
)

# E5-03's two set functions. The array is bound and cast rather than
# interpolated: each function takes `uuid[]`, and a list of literals spliced into
# the statement would be a caller's value reaching the SQL.
# **Each figure's own counts are what is selected here**, which is what E5-04's
# fix round corrected. `workload_respondent_count` and `workload_section_count`
# describe the responses that carried hours — the population the mean and the
# median are computed from — and the rating read's two counts describe the people
# and the sections that answered *that stream*. The week's overall
# `respondent_count`, `response_count` and `section_count` are deliberately not
# selected: nothing in this module may seal a figure with them, and a column
# nobody reads is a column nobody reaches for by mistake.
_SET_WEEK = text(
    "SELECT course_week, workload_mean, workload_median,"
    " workload_respondent_count, workload_section_count"
    " FROM public.benchmark_set_week(CAST(:section_ids AS uuid[]))"
    " ORDER BY course_week"
)

_SET_RATING_WEEK = text(
    "SELECT course_week, stream, rating_mean,"
    " rating_respondent_count, rating_section_count"
    " FROM public.benchmark_set_rating_week(CAST(:section_ids AS uuid[]))"
    " ORDER BY course_week"
)


# ---------------------------------------------------------------------------
# What a caller asks for, and what it gets back.
# ---------------------------------------------------------------------------


class BenchmarkPopulation(enum.Enum):
    """The two populations a section is compared against (SPEC §5.1).

    A named set is not a member here: it is asked for by its own id through the
    `named_set_*` functions, because it is a stored row rather than something
    derived from the hero section.
    """

    DEFAULT_SET = "default-set"
    UNIVERSITY = "university"


@dataclass(frozen=True, slots=True)
class BenchmarkPoint:
    """One course week of a comparison trend, and the sealed figure for it."""

    course_week: int
    figure: ComparisonFigure


@dataclass(frozen=True, slots=True)
class WorkloadComparison:
    """A comparison set's workload mean and median at one course week.

    Two figures rather than one, each sealed on its own: SPEC §4.1 item 7 covers
    "a mean, a median, or any other statistic", so a population thin enough to
    suppress one suppresses both, and nothing here lets the median through on the
    mean's decision.
    """

    mean: ComparisonFigure
    median: ComparisonFigure


@dataclass(frozen=True, slots=True)
class TermAxisPoint:
    """One term week of one start cohort, on SPEC §2.2's other week axis.

    The row `benchmark_cohort_term_axis` holds for a `(term, start date, term
    week)` key, with its workload figures sealed. E5-06's preview of a named set
    and E9's term-axis rendering are the consumers; nothing in E5 draws it.
    """

    term_id: UUID
    section_start_date: date
    term_week: int
    workload: WorkloadComparison


# ---------------------------------------------------------------------------
# The three resolutions.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Hero:
    """The three facts about the section being reported on that a population needs."""

    course_id: UUID
    length_weeks: int
    level: CourseLevel


def _hero_of(session: Session, section_id: UUID) -> _Hero | None:
    """The section's course, length and level, or `None` if there is no such section.

    `None` rather than a raise, and the choice is recorded because no criterion
    covers it: a population that cannot be resolved yields suppressed figures
    everywhere below, which withholds a number rather than failing a report on
    an input a caller has already read out of the same database.
    """
    found = session.execute(
        select(Section.course_id, Section.length_weeks, Course.level)
        .join(Course, Course.id == Section.course_id)
        .where(Section.id == section_id)
    ).one_or_none()
    if found is None:
        return None
    return _Hero(course_id=found.course_id, length_weeks=found.length_weeks, level=found.level)


def _matching_sections(hero: _Hero) -> Select[tuple[UUID]]:
    """Every section of the hero's length and level, as a statement to narrow further.

    SPEC §5.1: "to be comparable, sections must match on both length and level".
    The length is the *section's* — one course runs 6-week and 12-week sections
    in the same term — and the level is the course's stored generated column
    (ADR 0015). **No term appears anywhere in this statement**, which is what
    makes every population past-referencing.
    """
    return (
        select(Section.id)
        .join(Course, Course.id == Section.course_id)
        .where(Section.length_weeks == hero.length_weeks, Course.level == hero.level)
    )


def resolve_default_set(session: Session, *, section_id: UUID) -> list[UUID]:
    """The hero's own Lead Faculty's matching sections, without the hero section.

    Three narrowings, and each is a sentence somebody wrote down:

      - the courses are the ones the hero's course's lead leads (SPEC §2.1, read
        through `lead_faculty_course`), never a sibling lead's — §4.1 invariant 2
        is about exactly that, and a benchmark is as good a route to a
        colleague's numbers as a report is;
      - length and level match (§5.1);
      - the hero section is excluded (E5's breakdown decision 5, ADR 0166). A
        section compared against a set it is a member of is compared partly
        against itself, and the thinner the set the more of the comparison is the
        section's own answers.

    A course with no lead has no default set, and resolves to nothing rather than
    to everything.
    """
    hero = _hero_of(session, section_id)
    if hero is None:
        return []
    the_lead = select(_LEAD_FACULTY_COURSE.c.person_id).where(
        _LEAD_FACULTY_COURSE.c.course_id == hero.course_id
    )
    their_courses = select(_LEAD_FACULTY_COURSE.c.course_id).where(
        _LEAD_FACULTY_COURSE.c.person_id.in_(the_lead)
    )
    statement = (
        _matching_sections(hero)
        .where(Section.course_id.in_(their_courses))
        .where(Section.id != section_id)
        .order_by(Section.id)
    )
    return [row.id for row in session.execute(statement)]


def resolve_university(session: Session, *, section_id: UUID) -> list[UUID]:
    """Every matching section in the institution, the hero section among them.

    Decision 5's other half (ADR 0166). The university line is what the whole
    institution looks like, and a line drawn with one section deliberately left
    out is not that — the effect of any one section on an institution-wide figure
    is small in exactly the cases where the exclusion would be invisible, and
    large in the ones where the population is small enough that the same minimums
    are about to suppress it anyway.
    """
    hero = _hero_of(session, section_id)
    if hero is None:
        return []
    return [row.id for row in session.execute(_matching_sections(hero).order_by(Section.id))]


def resolve_named_set(session: Session, *, set_id: UUID) -> list[UUID]:
    """The member courses' sections at the length the set declares (ADR 0164).

    **The declared length is half of what a set is**, not a label on it: a set
    naming three courses and declaring eight weeks resolves to the eight-week
    sections of those courses and to nothing else, because §5.1's comparability
    rule is an exact match and a course runs sections of more than one length.

    **The level is not re-checked here and that is deliberate.**
    `comparison_set_member` carries the set's level and the course's level under
    two composite foreign keys with a `CHECK` that they agree (E5-01), so a
    member of another level cannot be stored. Re-testing it in Python would be a
    second statement of a rule the database already holds, and the two could
    disagree.

    A set that does not exist, holds no members, or declares a length none of its
    courses runs all resolve to nothing — which every figure below turns into a
    suppression rather than an error (criterion 6).
    """
    declared = session.execute(
        select(ComparisonSet.length_weeks).where(ComparisonSet.id == set_id)
    ).one_or_none()
    if declared is None:
        return []
    statement = (
        select(Section.id)
        .join(ComparisonSetMember, ComparisonSetMember.course_id == Section.course_id)
        .where(
            ComparisonSetMember.set_id == set_id,
            Section.length_weeks == declared.length_weeks,
        )
        .order_by(Section.id)
    )
    return [row.id for row in session.execute(statement)]


def _population(
    session: Session, *, section_id: UUID, population: BenchmarkPopulation
) -> list[UUID]:
    """One of the two section-keyed populations, by the enumeration member naming it."""
    if population is BenchmarkPopulation.DEFAULT_SET:
        return resolve_default_set(session, section_id=section_id)
    return resolve_university(session, section_id=section_id)


# ---------------------------------------------------------------------------
# The figures, each one sealed.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Contributors:
    """How many people, and how many of their sections, one figure was computed from.

    **The unit of both numbers is stated because getting it wrong is this
    module's recorded defect.** `respondents` counts distinct **people** — never
    responses, never ratings — and `sections` counts the distinct **sections**
    those people's answers came from. Each figure carries its own pair, and a
    pair that belongs to a different population is the thing E5-04's fix round
    removed.
    """

    respondents: int
    sections: int


# What a figure computed from nothing is measured against. Zero in both
# currencies, which suppresses under any configured minimum.
NOBODY = _Contributors(respondents=0, sections=0)


def _sealed(figure: Decimal | None, contributors: _Contributors) -> ComparisonFigure:
    """The one place this module turns a number into a comparison figure.

    Every caller below reaches a figure through here, and here reaches
    `comparison_after_suppression` — which reads both configured minimums from
    `Settings`, compares them against the counts it is given, and is the only
    thing in this system that can seal a value (ADR 0155). A figure of `None`
    whose contributors clear both minimums is a cohort week that had responses
    and no hours: E5-03's views carry null rather than nought there deliberately,
    and a zero would be a claim about how long those students worked that nobody
    made.

    **The contributors are the figure's own, and that is the whole of what this
    signature is for.** It takes one `_Contributors` rather than two loose
    integers precisely so that a caller cannot hand over a count it happened to
    have: the pair is read off the same row as the number it describes. A
    security review of this ticket found the earlier version sealing a rating
    mean with the week's overall counts and a workload mean with counts of people
    who reported no hours — `docs/MISTAKES.md` entry 50's class, and in the
    disclosing direction both times, because a figure's own population is always
    the smaller one.
    """
    return comparison_after_suppression(
        None if figure is None else float(figure),
        sections=contributors.sections,
        respondents=contributors.respondents,
    )


@dataclass(frozen=True, slots=True)
class _WorkloadWeek:
    """One course week's workload statistics and the contributors *they* were computed from."""

    workload_mean: Decimal | None
    workload_median: Decimal | None
    contributors: _Contributors


@dataclass(frozen=True, slots=True)
class _RatingWeek:
    """One course week and stream's rating mean, and the contributors it was computed from."""

    rating_mean: Decimal
    contributors: _Contributors


_NOTHING_ANSWERED = _WorkloadWeek(workload_mean=None, workload_median=None, contributors=NOBODY)


def _weeks_of(session: Session, section_ids: Sequence[UUID]) -> dict[int, _WorkloadWeek]:
    """`benchmark_set_week` over these sections, by course week.

    The counts taken are `workload_respondent_count` and
    `workload_section_count`, which describe the responses that carried hours —
    the rows the mean and the median are computed over. ADR 0165 keeps a week's
    row when nobody reported any hours, so the week's overall counts and the
    hours' own counts diverge whenever a responder leaves the question blank, and
    the figures belong to the smaller pair.

    **An empty section list is answered here rather than by the database.** A set
    under construction has no members and a default set may be empty once the
    hero is taken out of it, so it is an ordinary input; an empty Python list also
    gives the driver no element type to infer for the `uuid[]` argument, and the
    error that produces would read as a defect in the function. No sections means
    no rows, which every caller turns into a suppressed figure.
    """
    if not section_ids:
        return {}
    parameters = {"section_ids": [str(section_id) for section_id in section_ids]}
    rows = session.execute(_SET_WEEK, parameters).mappings()
    return {
        int(row["course_week"]): _WorkloadWeek(
            workload_mean=row["workload_mean"],
            workload_median=row["workload_median"],
            contributors=_Contributors(
                respondents=int(row["workload_respondent_count"]),
                sections=int(row["workload_section_count"]),
            ),
        )
        for row in rows
    }


def _ratings_of(
    session: Session, section_ids: Sequence[UUID], *, stream: str
) -> dict[int, _RatingWeek]:
    """`benchmark_set_rating_week` over these sections, one stream, by course week.

    **The counts come from the rating row itself**, per stream, because the mean
    does. `rating_count` counts ratings and is not read here at all: it is not a
    count of people, so neither minimum can be measured against it. The row's
    `rating_respondent_count` and `rating_section_count` are the people who
    answered *this* question and the sections they answered it in, which is what
    a point on this stream's line is a statement about.

    The empty list is short-circuited for `_weeks_of`'s reason.
    """
    if not section_ids:
        return {}
    parameters = {"section_ids": [str(section_id) for section_id in section_ids]}
    rows = session.execute(_SET_RATING_WEEK, parameters).mappings()
    return {
        int(row["course_week"]): _RatingWeek(
            rating_mean=row["rating_mean"],
            contributors=_Contributors(
                respondents=int(row["rating_respondent_count"]),
                sections=int(row["rating_section_count"]),
            ),
        )
        for row in rows
        if str(row["stream"]) == stream
    }


def _trend_over(
    session: Session, section_ids: Sequence[UUID], *, stream: str, also_weeks: Sequence[int] = ()
) -> list[BenchmarkPoint]:
    """A comparison trend over one section set, suppressed week by week.

    **One decision per week, taken from that week's own counts.** A series whose
    suppression was decided once — from the first week, or from totals across the
    weeks — either hides a week everybody answered or shows one a single student
    did, and the second is a comparison figure about one person on an instructor's
    chart.

    `also_weeks` are weeks the *caller* has to be able to draw whether or not the
    comparison set answered in them; they come back as suppressed points, because
    a gap in a chart and a withheld number are different statements to a reader.

    **The workload read is asked here only for the weeks it names**, never for
    its counts: a week the set answered something in has a point on this stream's
    line even when nobody answered this stream, and that point is suppressed
    because its own contributors are nobody.
    """
    answered_weeks = _weeks_of(session, section_ids)
    ratings = _ratings_of(session, section_ids, stream=stream)
    weeks = sorted(set(answered_weeks) | set(ratings) | set(also_weeks))
    points: list[BenchmarkPoint] = []
    for week in weeks:
        rated = ratings.get(week)
        points.append(
            BenchmarkPoint(
                course_week=week,
                figure=_sealed(
                    rated.rating_mean if rated else None,
                    rated.contributors if rated else NOBODY,
                ),
            )
        )
    return points


def _workload_over(
    session: Session, section_ids: Sequence[UUID], *, course_week: int
) -> WorkloadComparison:
    """The workload mean and median over one section set at one course week.

    A week the set answered nothing in is a pair of suppressed figures over counts
    of zero, which is the same answer an empty set gives and the same answer a set
    below either minimum gives.
    """
    answered = _weeks_of(session, section_ids).get(course_week, _NOTHING_ANSWERED)
    return WorkloadComparison(
        mean=_sealed(answered.workload_mean, answered.contributors),
        median=_sealed(answered.workload_median, answered.contributors),
    )


# ---------------------------------------------------------------------------
# The public doors.
# ---------------------------------------------------------------------------


def benchmark_trend(
    session: Session,
    *,
    section_id: UUID,
    population: BenchmarkPopulation,
    stream: str,
) -> list[BenchmarkPoint]:
    """One section's comparison trend against a population, week by week.

    Every course week the hero section itself carries responses in appears in the
    series, whether or not the comparison population answered in it, so a report
    drawing the hero's own line has a comparison point — shown or suppressed — at
    every week of it.
    """
    section_ids = _population(session, section_id=section_id, population=population)
    hero_weeks = sorted(_weeks_of(session, [section_id]))
    return _trend_over(session, section_ids, stream=stream, also_weeks=hero_weeks)


def benchmark_workload(
    session: Session,
    *,
    section_id: UUID,
    population: BenchmarkPopulation,
    course_week: int,
) -> WorkloadComparison:
    """One section's comparison workload mean and median at one course week."""
    section_ids = _population(session, section_id=section_id, population=population)
    return _workload_over(session, section_ids, course_week=course_week)


def named_set_trend(session: Session, *, set_id: UUID, stream: str) -> list[BenchmarkPoint]:
    """A named set's comparison trend, week by week.

    There is no hero section here — a named set is asked about on its own, for
    E5-06's preview — so the series holds the weeks the set answered in and
    nothing else. An empty or unresolvable set answers an empty series rather
    than raising.
    """
    return _trend_over(session, resolve_named_set(session, set_id=set_id), stream=stream)


def named_set_workload(session: Session, *, set_id: UUID, course_week: int) -> WorkloadComparison:
    """A named set's workload mean and median at one course week."""
    return _workload_over(
        session, resolve_named_set(session, set_id=set_id), course_week=course_week
    )


def named_set_term_axis(session: Session, *, set_id: UUID) -> list[TermAxisPoint]:
    """The term-axis cohort a named set declares, one point per start cohort and term week.

    SPEC §2.2 carries two week axes and E5's breakdown decision 7 puts the
    term-axis read on E5-03's per-term cohort views rather than on the set
    functions, which key by course week alone. This is the thin pass-through of
    that read, with the same two minimums applied to each row's figures.

    **What it answers is the cohort the set declares, not the set's own member
    courses**, and that is a limit worth stating rather than discovering: the
    term-axis views are keyed by `(length, level, term, start date)` and hold no
    course, so there is no way to narrow one to a membership list. A set's term
    axis is therefore "what sections of this length and level did across the term"
    — which is what E5-06's preview is for and what E9 draws — and it is not the
    population `named_set_trend` and `named_set_workload` answer over. ADR 0166
    records the choice.

    A set that does not exist answers no points.
    """
    declared = session.execute(
        select(ComparisonSet.length_weeks, ComparisonSet.level).where(ComparisonSet.id == set_id)
    ).one_or_none()
    if declared is None:
        return []
    statement = (
        select(_COHORT_TERM_AXIS)
        .where(
            _COHORT_TERM_AXIS.c.length_weeks == declared.length_weeks,
            _COHORT_TERM_AXIS.c.level == declared.level,
        )
        .order_by(
            _COHORT_TERM_AXIS.c.term_id,
            _COHORT_TERM_AXIS.c.section_start_date,
            _COHORT_TERM_AXIS.c.term_week,
        )
    )
    points: list[TermAxisPoint] = []
    for row in session.execute(statement).mappings():
        # **These are the cohort week's overall counts, not the hours' own, and
        # that is the open defect this branch could not close.** The two set
        # functions now answer each figure's contributors;
        # `benchmark_cohort_term_axis` does not, and it cannot be widened from
        # this branch — see `docs/disputes/E5-04-01.md`. Until that is settled,
        # a term-axis workload figure is sealed against a population that is
        # never smaller than its own, so it can be shown where it should have
        # been suppressed. Nothing renders this door yet.
        cohort = _Contributors(
            respondents=int(row["respondent_count"]), sections=int(row["section_count"])
        )
        points.append(
            TermAxisPoint(
                term_id=row["term_id"],
                section_start_date=row["section_start_date"],
                term_week=int(row["term_week"]),
                workload=WorkloadComparison(
                    mean=_sealed(row["workload_mean"], cohort),
                    median=_sealed(row["workload_median"], cohort),
                ),
            )
        )
    return points
