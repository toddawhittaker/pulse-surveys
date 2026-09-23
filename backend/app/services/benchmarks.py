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
nothing to it: `_sealed` below is the single place a figure is constructed, and
it is reached once per figure — per week of a trend, and separately for a
workload mean and its median. A week the cohort answered nothing in is a
*suppressed* point rather than an absent one, because a gap in a chart and a
withheld number say different things to a reader.

**And every figure is sealed against the counts of its own contributors** — the
distinct people whose answers that figure aggregates, and the distinct sections
those answers came from. That sentence is the whole of what a security review of
this ticket added, and it was not obvious: the first version sealed a per-stream
rating mean with the week's overall counts and a workload mean with counts of
people who had reported no hours, both of which are larger than the figure's own
population and so both of which show figures §4.1 item 7 means to withhold
(`docs/MISTAKES.md` entry 50's class). `_Contributors` below is the pair, read
off the same row as the number it describes so that no caller can hand over a
count it merely had to hand. ADR 0166's consequences carry the rule, and the
term axis — the third place it was broken — carries it through
`benchmark_cohort_term_axis`'s `_v002` body, which
`docs/disputes/E5-04-01.md`'s ruling settled.

**A benchmark figure counts every stored response, exactly as the section's own
report figures do; `response.is_valid` is not filtered.** SPEC §3.3 classifies a
submission and `report_workload` and `report_rating_distribution` do not read
the verdict either, so a comparison figure and the section figure drawn beside
it are computed over the same rows. Ruled in the open at E5's wave-2 launch and
recorded here because this is where comparison policy lives; the question came
from E5-03 and is closed in `docs/tickets/e5/deferred.md`.

**A published week's answers are frozen** (the owner's freeze-at-close ruling,
E5-14). Each figure for course week *w* counts a response only if the window it
was given in closed by *w*'s cutoff and it was last submitted by then. A
report's cutoff for *w* is the earliest week-*w* close among every section in
its term with its length and level (round 4), which is at or before its own
section's close and **depends on no reader**: every report over one population
and week shares one snapshot, so the within-term class — two reports of one
population frozen at two instants, whose difference is whatever closed between
— is gone. So new or revised answers cannot move a figure already shown.
Three residuals are carried rather than closed: snapshots compared across terms
(a reader's prior-term report against a current one), membership resolved at
read time (below), and the race at a window's close in the submit path. **That is not the
same as the figure depending only on rows fixed before it was shown**, and an
earlier version of this paragraph said it was: which sections a population holds
is resolved at read time, so the figure also depends on the lead mapping, on
each section's length and start date, and on the teaching grants, as they stand
when the report is read. A change to any of those after publication moves the
figure; freezing membership is carried to a later epic for the owner's ruling.

**A figure is sealed on what each of its readers would have left** (E5-14,
round 4). A section's report is read by each person holding its teaching grant,
and each knows the counts and sums of every section she teaches, in any term, so
she can subtract them. A figure is shown only if its population clears both
minimums and, for each such person, the population less her sections is empty or
clears them. Fix one reader, one term, one length and level, one course week
and its cutoff: every population she can read a figure for is a union of
disjoint atoms — her own sections, each lead's set less her own (one per lead of
a course she teaches here), and the rest of the university. **The university
line is shown only if every atom other than her own sections is empty or clears
both minimums** (rounds 5 and 6), and **a default-set figure is shown only if
its own lead atom does** (the per-person remainder above). So every combination
of figures she can compute is over atoms that clear both minimums. Per person,
never over the union
of co-instructors: none of them knows another's sections. `_university_population`
and `_tightest` carry the argument. The populations themselves are unchanged: the
default set leaves out only the reported section, and the university includes it.

**The arithmetic is not here.** Every mean, median and count comes from E5-03's
two `SECURITY DEFINER` set functions, which take a section-id array and the
course weeks asked for, each with its cutoff, and answer one row per course week
(ADR 0165). This module resolves ids, asks, and seals.
Nothing in it averages, counts or divides, so there is no second implementation
of a benchmark figure to keep in step with the first — ADR 0166 records why the
per-term cohort views cannot be aggregated in their place.

**How the relations are reached, and by whom.** This module is the only one
under `backend/app/` that names the two set functions or the four cohort views,
and `tests/unit/test_only_the_benchmark_service_names_the_benchmark_relations.py`
holds it to that: the functions answer for any section ids they are handed, and
this is where a population is resolved, the hero is excluded from its own set,
and each week's cutoff is applied. E5-14 deleted the two wrappers
`app.views_sql.queries` carried, which nothing called. Everything else —
`section`, `course`, `lead_faculty_course`, the comparison-set tables and the
term-axis view — is read through SQLAlchemy Core, which is how
`app.services.reporting` reads the report views.
"""

import enum
from collections.abc import Collection, Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, column, select, table, text
from sqlalchemy.orm import Session

from app.models.benchmark import ComparisonSet, ComparisonSetMember
from app.models.org import Course, CourseLevel, Section
from app.services.authz import taught_section_ids, teaching_instructors_of
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
# date of the cohort inside it (ADR 0165). The key columns are that ruling's own;
# the two counts read here are `workload_respondent_count` and
# `workload_section_count`, which E5-04's `_v002` body added and which describe
# the responses that carried hours — the population the workload figures on this
# axis are computed from. The cohort week's overall `respondent_count` and
# `section_count` are deliberately not named: on this axis as on the other, a
# figure is sealed against its own contributors and against nothing else.
_COHORT_TERM_AXIS = table(
    "benchmark_cohort_term_axis",
    column("length_weeks"),
    column("level"),
    column("term_id"),
    column("section_start_date"),
    column("term_week"),
    column("workload_mean"),
    column("workload_median"),
    column("workload_respondent_count"),
    column("workload_section_count"),
)

# E5-03's two set functions, in their E5-14 `_v003` form: the section set, the
# course weeks asked for, and one cutoff per week. The arrays are bound and cast
# rather than interpolated: a list of literals spliced into the statement would be
# a caller's value reaching the SQL.
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
    " FROM public.benchmark_set_week(CAST(:section_ids AS uuid[]),"
    " CAST(:course_weeks AS integer[]), CAST(:closed_by AS timestamptz[]))"
    " ORDER BY course_week"
)

_SET_RATING_WEEK = text(
    "SELECT course_week, stream, rating_mean,"
    " rating_respondent_count, rating_section_count"
    " FROM public.benchmark_set_rating_week(CAST(:section_ids AS uuid[]),"
    " CAST(:course_weeks AS integer[]), CAST(:closed_by AS timestamptz[]))"
    " ORDER BY course_week, stream"
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
    week)` key, with its workload figures sealed. E9's term-axis rendering is the
    intended consumer; nothing in E5 reads it. E5-06's preview of a named set
    answers two counts and never a figure, so it is not a consumer either.
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
    out is not that. **Its figures include the hero; its sealing does not** —
    since E5-14 a university figure is shown only when the sections other than
    the hero clear both minimums, and the complement beyond the default set is
    empty or clears them too (`_university_population`).
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

    **The contributors are the ones the figure is sealed against, and that is
    the whole of what this signature is for.** It takes one `_Contributors`
    rather than two loose integers so that a caller cannot hand over a count it
    happened to have: for the default set and a named set the pair is read off
    the same row as the number it describes, and for the university line it is
    the narrower population the university sealing rule picks (`_university_population`). A
    security review of E5-04 found the earlier version sealing a rating mean with
    the week's overall counts and a workload mean with counts of people who
    reported no hours — `docs/MISTAKES.md` entry 50's class, and in the
    disclosing direction both times.
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


@dataclass(frozen=True, slots=True)
class _Answered:
    """Both set functions' answers over one section set, for the course weeks asked.

    `workload` is keyed by course week and `ratings` by course week and stream:
    one call to each function per population, and the rating call's rows serve
    both streams (the E5 boundary review's data-model finding).
    """

    workload: Mapping[int, _WorkloadWeek]
    ratings: Mapping[tuple[int, str], _RatingWeek]


_NOTHING = _Answered(workload={}, ratings={})


def _cutoff_arguments(cutoffs: Mapping[int, datetime]) -> dict[str, list[Any]]:
    """The two parallel arrays `_v003` takes, in ascending course-week order.

    **A naive instant is refused here, loudly.** The cutoff is compared with
    `survey_window.closes_at` and `response.last_submitted_at`, both aware, and a
    value with no offset means a different moment on a differently configured
    connection — the one input that would silently move which answers a
    published figure counts.
    """
    weeks = sorted(cutoffs)
    for week in weeks:
        if cutoffs[week].tzinfo is None:
            raise ValueError(
                f"The cutoff for course week {week} has no time zone. A benchmark cutoff is "
                "compared with stored instants, and a naive one means a different moment on "
                "every connection."
            )
    return {"course_weeks": weeks, "closed_by": [cutoffs[week] for week in weeks]}


def _answered(
    session: Session, section_ids: Sequence[UUID], cutoffs: Mapping[int, datetime]
) -> _Answered:
    """`benchmark_set_week` and `benchmark_set_rating_week` over one section set, once each.

    **The counts taken are each figure's own.** For the workload that is
    `workload_respondent_count` and `workload_section_count`, the responses that
    carried hours — ADR 0165 keeps a week's row when nobody reported any, so the
    week's overall counts and the hours' own counts diverge whenever a responder
    leaves the question blank, and the figures belong to the smaller pair. For a
    rating it is `rating_respondent_count` and `rating_section_count`, the people
    who answered *that stream* and their sections; `rating_count` counts ratings,
    not people, and is not read.

    **Only the course weeks `cutoffs` names are answered, each counting what was
    fixed by its own cutoff** — the freeze at close (`benchmark_set_week_v003.sql`).

    **An empty section list, or no week asked, is answered here rather than by
    the database.** A set under construction has no members and a default set may
    be empty once the hero is taken out of it, so it is an ordinary input; an
    empty Python list also gives the driver no element type to infer for the
    array argument, and the error that produces would read as a defect in the
    function. No sections means no rows, which every caller turns into a
    suppressed figure.
    """
    if not section_ids or not cutoffs:
        return _NOTHING
    parameters = {
        "section_ids": [str(section_id) for section_id in section_ids],
        **_cutoff_arguments(cutoffs),
    }
    workload = {
        int(row["course_week"]): _WorkloadWeek(
            workload_mean=row["workload_mean"],
            workload_median=row["workload_median"],
            contributors=_Contributors(
                respondents=int(row["workload_respondent_count"]),
                sections=int(row["workload_section_count"]),
            ),
        )
        for row in session.execute(_SET_WEEK, parameters).mappings()
    }
    ratings = {
        (int(row["course_week"]), str(row["stream"])): _RatingWeek(
            rating_mean=row["rating_mean"],
            contributors=_Contributors(
                respondents=int(row["rating_respondent_count"]),
                sections=int(row["rating_section_count"]),
            ),
        )
        for row in session.execute(_SET_RATING_WEEK, parameters).mappings()
    }
    return _Answered(workload=workload, ratings=ratings)


@dataclass(frozen=True, slots=True)
class _Population:
    """One comparison line's figures, and the contributors each figure is sealed against.

    For a named set the two are the same rows: every figure is sealed against
    its own contributors. A section-keyed population — the default set or the
    university — is sealed against the tightest of its own contributors and its
    non-empty remainders; see `_tightest`.
    """

    figures: _Answered
    workload_seal: Mapping[int, _Contributors]
    rating_seal: Mapping[tuple[int, str], _Contributors]


def _sealed_by_its_own(answered: _Answered) -> _Population:
    """A population whose every figure is sealed against the contributors on its own row."""
    return _Population(
        figures=answered,
        workload_seal={week: row.contributors for week, row in answered.workload.items()},
        rating_seal={key: row.contributors for key, row in answered.ratings.items()},
    )


def _tightest(
    own: _Contributors | None, remainders: Sequence[_Contributors | None]
) -> _Contributors:
    """The one pair a figure is sealed against, out of its population and its remainders.

    The E5-14 round-4 ruling shows a figure only if (a) its population clears
    both minimums and every remainder is **empty or** clears them too. A
    remainder is empty when nobody contributed to *this figure* at this week
    under this week's cutoff — no respondent and no section; a workload
    remainder whose week has responses but nobody who reported hours is empty.

    "Every pair clears both minimums" is the same statement as "the smallest
    count of sections and the smallest count of people among them clear both",
    so the pair handed to `comparison_after_suppression` is the component-wise
    minimum over the population's own contributors and each non-empty
    remainder's. The decision itself stays the chokepoint's; this only decides
    which counts it is asked about.
    """
    counted = [own if own is not None else NOBODY]
    counted += [
        remainder
        for remainder in remainders
        if remainder is not None and (remainder.respondents > 0 or remainder.sections > 0)
    ]
    return _Contributors(
        respondents=min(pair.respondents for pair in counted),
        sections=min(pair.sections for pair in counted),
    )


def _sealed_through(figures: _Answered, remainders: Sequence[_Answered]) -> _Population:
    """A population's figures, each sealed against `_tightest` of its own and its remainders' counts.

    Each figure is sealed on its own contributors in every population: a
    stream's raters for a rating point, the people who reported hours for a
    workload figure, at that course week and under that week's cutoff.
    """

    def workload_of(answered: _Answered, week: int) -> _Contributors | None:
        found = answered.workload.get(week)
        return None if found is None else found.contributors

    def rating_of(answered: _Answered, key: tuple[int, str]) -> _Contributors | None:
        found = answered.ratings.get(key)
        return None if found is None else found.contributors

    return _Population(
        figures=figures,
        workload_seal={
            week: _tightest(
                workload_of(figures, week), [workload_of(rest, week) for rest in remainders]
            )
            for week in figures.workload
        },
        rating_seal={
            key: _tightest(rating_of(figures, key), [rating_of(rest, key) for rest in remainders])
            for key in figures.ratings
        },
    )


class _Reads:
    """The two set functions over each distinct section set, asked at most once per report read.

    A population and one of its remainders are often the same list — a default
    set none of the section's instructors teaches has nothing taken out of it — and
    asking the database twice for the same answer is the cost the E5 boundary
    review measured and this replaces.
    """

    def __init__(self, session: Session, cutoffs: Mapping[int, datetime]) -> None:
        self._session = session
        self._cutoffs = cutoffs
        self._answered: dict[frozenset[UUID], _Answered] = {}

    def of(self, section_ids: Iterable[UUID]) -> _Answered:
        key = frozenset(section_ids)
        if key not in self._answered:
            self._answered[key] = _answered(self._session, sorted(key), self._cutoffs)
        return self._answered[key]


def _default_population(
    reads: _Reads, *, default_set: Sequence[UUID], taught: Sequence[AbstractSet[UUID]]
) -> _Population:
    """The default set's figures, sealed on the set and on what each instructor would have left.

    E5-14's round-4 ruling, condition (b_p). Each person p who holds the
    teaching grant on the reported section reads its report, and knows the
    count and the sum of every section she teaches herself, in any term — so she
    can subtract them. What is left for her, the set less `taught[p]`, must be
    empty or clear both minimums. Per person, and never over the union of the
    section's instructors: no co-instructor knows another's sections. The figure
    is still the whole set's.
    """
    remainders = [
        reads.of(section for section in default_set if section not in hers) for hers in taught
    ]
    return _sealed_through(reads.of(default_set), remainders)


def _university_population(
    reads: _Reads,
    *,
    university: Sequence[UUID],
    taught: Sequence[AbstractSet[UUID]],
    lead_sets_seen: Sequence[Sequence[AbstractSet[UUID]]],
) -> _Population:
    """The university line's figures, sealed so that no reader's subtraction isolates a thin population.

    The figure is the whole institution's, the reported section included (ADR
    0166, decision 5). A university point is shown only if (E5-14, rounds 4 to
    6), for every person p holding the teaching grant on the reported section:

      (a) its population clears both minimums;
      (b_p) the university less the sections p teaches is empty or clears them;
      (c_p) **every atom p could isolate** is empty or clears them: each lead
            atom — the default set of a section p teaches in this term at this
            length and level, less p's own sections (`lead_sets_seen[p]`) — and
            the rest of the university, less p's sections and every one of those
            default sets.

    **Why every atom, and why only these.** Fix one reader, one length and
    level, one term, one course week and one cutoff. Every population she can
    read a figure for is a union of disjoint atoms: her own sections, which she
    knows; one lead atom per lead of a course she teaches here; and the rest of
    the university. Every figure she sees is a combination of those atoms'
    aggregates. So the university is shown only if every atom other than her own
    sections is empty or clears both minimums, and a default-set figure is shown
    only if its own lead atom does ((b_p) on the default set); every
    combination she can compute is then over atoms that clear both minimums.
    Round 5 removed every default set she sees from the rest, and round 6 checks
    the lead atoms themselves: without that, a university figure over an empty
    rest was the default set she sees plus a second, thin lead atom, which she
    could subtract out. The closure is over one term: comparing figures across
    terms is a residual carried rather than closed.

    A section nobody teaches has no p, so (a) alone applies; nobody can read its
    report, because every report route requires the teaching grant.
    """
    remainders: list[_Answered] = []
    for hers, lead_sets in zip(taught, lead_sets_seen, strict=True):
        beyond_hers = [section for section in university if section not in hers]
        seen = {section for lead_set in lead_sets for section in lead_set}
        remainders.append(reads.of(beyond_hers))
        remainders.append(reads.of(section for section in beyond_hers if section not in seen))
        remainders.extend(
            reads.of(section for section in lead_set if section not in hers)
            for lead_set in lead_sets
        )
    return _sealed_through(reads.of(university), remainders)


def _trend(
    population: _Population, *, stream: str, cutoffs: Mapping[int, datetime]
) -> list[BenchmarkPoint]:
    """A comparison trend, one point for each course week `cutoffs` names, and no others.

    **One decision per week, taken from that week's own counts.** A series whose
    suppression was decided once — from the first week, or from totals across the
    weeks — either hides a week everybody answered or shows one a single student
    did, and the second is a comparison figure about one person on an
    instructor's chart.

    **The weeks are the caller's, and they are the whole series** — shown or
    suppressed. The *set of weeks a series carries* is itself a statement about
    the comparison population: a point for a week the reader's own section has
    not reached says that other sections answered in it, which is a cohort's
    week-by-week activity read off a series where every figure is withheld
    (ADR 0170). A week the population answered nothing in comes back as a
    suppressed point, because a gap in a chart and a withheld number are
    different statements to a reader.
    """
    points: list[BenchmarkPoint] = []
    for week in sorted(cutoffs):
        rated = population.figures.ratings.get((week, stream))
        points.append(
            BenchmarkPoint(
                course_week=week,
                figure=_sealed(
                    rated.rating_mean if rated else None,
                    population.rating_seal.get((week, stream), NOBODY),
                ),
            )
        )
    return points


def _workload(population: _Population, *, course_week: int) -> WorkloadComparison:
    """A population's workload mean and median at one course week.

    A week the population answered nothing in is a pair of suppressed figures
    over counts of zero, which is the same answer an empty set gives and the same
    answer a set below either minimum gives.
    """
    answered = population.figures.workload.get(course_week, _NOTHING_ANSWERED)
    seal = population.workload_seal.get(course_week, NOBODY)
    return WorkloadComparison(
        mean=_sealed(answered.workload_mean, seal),
        median=_sealed(answered.workload_median, seal),
    )


def _the_weeks_cutoff(cutoffs: Mapping[int, datetime], course_week: int) -> dict[int, datetime]:
    """The one cutoff a workload comparison at `course_week` is read under, or a loud refusal.

    A missing week is a caller's defect, and there is no right default for it:
    any instant chosen here would decide which answers a figure counts.
    """
    if course_week not in cutoffs:
        raise ValueError(
            f"No cutoff was given for course week {course_week}. A benchmark figure counts only "
            "what was fixed by its week's cutoff."
        )
    return {course_week: cutoffs[course_week]}


def _alike_in_this_term(session: Session, *, section_id: UUID) -> set[UUID]:
    """Every section in this section's term with its length and its course's level, itself included."""
    reported = (
        select(Section.term_id, Section.length_weeks, Course.level)
        .join(Course, Course.id == Section.course_id)
        .where(Section.id == section_id)
        .subquery()
    )
    return set(
        session.scalars(
            select(Section.id)
            .join(Course, Course.id == Section.course_id)
            .join(
                reported,
                (reported.c.term_id == Section.term_id)
                & (reported.c.length_weeks == Section.length_weeks)
                & (reported.c.level == Course.level),
            )
        )
    )


def _section_populations(
    session: Session,
    *,
    section_id: UUID,
    cutoffs: Mapping[int, datetime],
    wanted: Collection[BenchmarkPopulation],
) -> dict[BenchmarkPopulation, _Population]:
    """The section-keyed populations asked for, each resolved once and read through one `_Reads`.

    Each teaching instructor's sections are read once, through
    `app.services.authz`, which is where `assignment_scope` is read. The
    default set of every section an instructor teaches here — this term, this
    length and level — is resolved once per read and shared between
    instructors; `_university_population` says why the university needs them.
    """
    reads = _Reads(session, cutoffs)
    default_sets: dict[UUID, list[UUID]] = {
        section_id: resolve_default_set(session, section_id=section_id)
    }

    def default_set_of(section: UUID) -> list[UUID]:
        if section not in default_sets:
            default_sets[section] = resolve_default_set(session, section_id=section)
        return default_sets[section]

    taught = [
        taught_section_ids(session, person_id=person)
        for person in sorted(teaching_instructors_of(session, section_id=section_id))
    ]
    populations: dict[BenchmarkPopulation, _Population] = {}
    if BenchmarkPopulation.DEFAULT_SET in wanted:
        populations[BenchmarkPopulation.DEFAULT_SET] = _default_population(
            reads, default_set=default_sets[section_id], taught=taught
        )
    if BenchmarkPopulation.UNIVERSITY in wanted:
        alike = _alike_in_this_term(session, section_id=section_id)
        lead_sets_seen = [
            [set(default_set_of(mine)) for mine in sorted(hers & alike)] for hers in taught
        ]
        populations[BenchmarkPopulation.UNIVERSITY] = _university_population(
            reads,
            university=resolve_university(session, section_id=section_id),
            taught=taught,
            lead_sets_seen=lead_sets_seen,
        )
    return populations


# ---------------------------------------------------------------------------
# The public doors.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SectionBenchmarks:
    """Every comparison figure one instructor report shows, from one read of each population.

    `trends` is keyed by population and stream; `workloads` by population, at
    the reported course week.
    """

    trends: Mapping[tuple[BenchmarkPopulation, str], list[BenchmarkPoint]]
    workloads: Mapping[BenchmarkPopulation, WorkloadComparison]


def section_benchmarks(
    session: Session,
    *,
    section_id: UUID,
    course_week: int,
    streams: Sequence[str],
    cutoffs: Mapping[int, datetime],
) -> SectionBenchmarks:
    """SPEC §5.1's comparison and university figures for one report, each population read once.

    The report's own door. The default set and the university are each resolved
    once, and each set function is called at most once per distinct section set
    — the two populations and their remainders — with every published week's
    cutoff; the rating rows serve every stream.

    `cutoffs` is each published course week mapped to the **earliest** close of
    that week's window among every section in the reported section's term with
    its length and level (E5-14's round-4 ruling). It depends on no reader, so
    every report over one population and week shares one snapshot, and no
    answer given or revised later moves a figure already shown. Membership is
    still resolved at read time; see the module docstring.
    """
    _the_weeks_cutoff(cutoffs, course_week)  # the reported week must be among those read
    by_population = _section_populations(
        session,
        section_id=section_id,
        cutoffs=cutoffs,
        wanted=tuple(BenchmarkPopulation),
    )
    return SectionBenchmarks(
        trends={
            (population, stream): _trend(read, stream=stream, cutoffs=cutoffs)
            for population, read in by_population.items()
            for stream in streams
        },
        workloads={
            population: _workload(read, course_week=course_week)
            for population, read in by_population.items()
        },
    )


def benchmark_trend(
    session: Session,
    *,
    section_id: UUID,
    population: BenchmarkPopulation,
    stream: str,
    cutoffs: Mapping[int, datetime],
) -> list[BenchmarkPoint]:
    """One section's comparison trend against one population: a point per course week in `cutoffs`.

    **The series is exactly the weeks `cutoffs` names, one point each, shown or
    suppressed.** That is a confidentiality rule and not a convenience: a series
    whose weeks were the *union* of this section's and the comparison
    population's lets a reader subtract their own weeks and read off which weeks
    other sections answered in (ADR 0170). **Each week counts only what was
    fixed by its own cutoff**, and each figure is sealed per teaching instructor
    exactly as the report's are. `section_benchmarks` is the report's door
    and reads both populations at once; this one reads one.
    """
    populations = _section_populations(
        session,
        section_id=section_id,
        cutoffs=cutoffs,
        wanted=(population,),
    )
    return _trend(populations[population], stream=stream, cutoffs=cutoffs)


def benchmark_workload(
    session: Session,
    *,
    section_id: UUID,
    population: BenchmarkPopulation,
    course_week: int,
    cutoffs: Mapping[int, datetime],
) -> WorkloadComparison:
    """One section's comparison workload mean and median at one course week, under its cutoff."""
    week_cutoff = _the_weeks_cutoff(cutoffs, course_week)
    populations = _section_populations(
        session,
        section_id=section_id,
        cutoffs=week_cutoff,
        wanted=(population,),
    )
    return _workload(populations[population], course_week=course_week)


def named_set_trend(
    session: Session, *, set_id: UUID, stream: str, cutoffs: Mapping[int, datetime]
) -> list[BenchmarkPoint]:
    """A named set's comparison trend: a point per course week in `cutoffs`, shown or suppressed.

    There is no hero section here — a named set is asked about on its own — and
    nothing in E5 calls it: E5-06's preview answers two counts and no figure,
    and E9's leadership surfaces are the intended caller. **The cutoffs are a
    required argument and whose instants they are is E9's decision**, made
    together with the leadership reader's purview; a report's own cutoffs are
    its section's window closes. An empty or unresolvable set answers a
    suppressed point for every week asked rather than raising.
    """
    return _trend(
        _sealed_by_its_own(_answered(session, resolve_named_set(session, set_id=set_id), cutoffs)),
        stream=stream,
        cutoffs=cutoffs,
    )


def named_set_workload(
    session: Session, *, set_id: UUID, course_week: int, cutoffs: Mapping[int, datetime]
) -> WorkloadComparison:
    """A named set's workload mean and median at one course week, under that week's cutoff."""
    week_cutoff = _the_weeks_cutoff(cutoffs, course_week)
    return _workload(
        _sealed_by_its_own(
            _answered(session, resolve_named_set(session, set_id=set_id), week_cutoff)
        ),
        course_week=course_week,
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
    — which is what E9 is to draw — and it is not the
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
        # The hours' own contributors, not the cohort week's — the same rule the
        # course-week axis follows, reached through this view's `_v002` body. The
        # widening that made this possible is argued in the ruling appended to
        # `docs/disputes/E5-04-01.md` and admitted by the two column equalities
        # SPEC §4.1 item 1 is enforced through.
        reported_hours = _Contributors(
            respondents=int(row["workload_respondent_count"]),
            sections=int(row["workload_section_count"]),
        )
        points.append(
            TermAxisPoint(
                term_id=row["term_id"],
                section_start_date=row["section_start_date"],
                term_week=int(row["term_week"]),
                workload=WorkloadComparison(
                    mean=_sealed(row["workload_mean"], reported_hours),
                    median=_sealed(row["workload_median"], reported_hours),
                ),
            )
        )
    return points
