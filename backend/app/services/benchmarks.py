"""Which sections a comparison figure is computed over, and the figure itself (SPEC §13).

SPEC §5.1 puts three populations on an instructor's report and this module is
where each becomes a list of section ids:

  - the **default set** — the same Lead Faculty's courses, filtered to the hero
    section's length and level, with the hero section itself taken out;
  - the **university line** — every section of that same length and level in the
    institution, hero included;
  - a **named set** — the member courses of one `comparison_set`, at the length
    that set declares.

The default set and the university line are past-referencing: week N of a
section is compared against week N of matching sections in the current term
*and* every term §4's retention rule still keeps. Nothing in those two filters
on a term, and that absence is the feature. **A named set is read differently**
(E9-05, SPEC §5.5): a leadership reader sees its figures over the set's sections
inside her purview, in the term she is viewing, one series per start cohort on
the term axis (`named_set_series`).

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
count it merely had to hand. ADR 0166's consequences carry the rule. E5's
term-axis read was the third place it was broken (`docs/disputes/E5-04-01.md`);
E9-05 deleted that read, because it answered a declared length and level
institution-wide and could not be narrowed to a reader's purview.

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
— is gone. So new or revised answers cannot move a figure already shown. A
named set's cutoff for course week *w* is its start cohort's own week-*w* close in
the viewed term (E9 decision 14): every section of one start cohort shares its
window closes, so this is the same earliest-close rule narrowed to the cohort,
and it too depends on no reader.
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
round 4; E9-05). A section's report is read by each person holding its teaching
grant, and by a leadership reader whose purview holds it (E9-09's drill-down).
Each knows the counts and sums of **her sections** — every section she teaches,
in any term, together with every section in her leadership purview if she holds
a leadership assignment — so she can subtract them, across every hat she wears.
A figure is shown only if its population clears both minimums and, for each
such person, the population less her sections is empty or clears them. Fix one
reader, one term, one length and level, one course week and its cutoff: every
population she can read a figure for is a union of disjoint atoms — her own
sections, each lead's set less her own (one per lead of a course among her
sections here), and the rest of the university. **The university
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
under `backend/app/` that names the two set functions, and since E9-05 deleted
the last reader of the four cohort views nothing here names them (E9-12 drops
them). `tests/unit/test_only_the_benchmark_service_names_the_benchmark_relations.py`
holds both: the functions answer for any section ids they are handed, and
this is where a population is resolved, the hero is excluded from its own set,
and each week's cutoff is applied. E5-14 deleted the two wrappers
`app.views_sql.queries` carried, which nothing called. Everything else —
`section`, `course`, `lead_faculty_course`, the comparison-set tables, and the
terms, weeks and windows — is read through SQLAlchemy Core, which is how
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
from zoneinfo import ZoneInfo

from sqlalchemy import Select, Uuid, any_, bindparam, column, func, select, table, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session, aliased

from app.config import Settings
from app.models.benchmark import ComparisonSet, ComparisonSetMember
from app.models.org import Course, CourseLevel, Section
from app.models.survey import REPORT_STREAMS
from app.models.term import SurveyWindow, Term, Week
from app.services import clock
from app.services.authz import (
    ActorScope,
    leadership_section_ids,
    taught_section_ids,
    teaching_instructors_of,
)
from app.services.reporting import (
    ComparisonFigure,
    comparison_after_suppression,
    week_is_published,
)
from app.services.section_codes import course_week_of, week_of_the_term

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

    A named set is not a member here: it is asked for by its own id through
    `named_set_series`, because it is a stored row rather than something derived
    from the hero section.
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
    to everything. A section that does not exist resolves to nothing too.

    The rule itself is `_default_sets_of`, which answers it for many sections in
    one statement; this is that, asked about one.
    """
    return _default_sets_of(session, [section_id])[section_id]


def _default_sets_of(session: Session, section_ids: Collection[UUID]) -> dict[UUID, list[UUID]]:
    """`resolve_default_set` for every section asked about, in one statement (E9-05 fix round).

    One row per (asked section, member of its default set): the asked section's
    course's lead, every course that same person leads, and those courses'
    sections at the asked section's length and level, the asked section left out.
    Every section asked about is a key, with an empty list when it has no
    default set. The ids are bound as one array, so the statement is the same
    size however many sections a reader's purview holds.
    """
    asked = sorted(set(section_ids))
    found: dict[UUID, list[UUID]] = {section: [] for section in asked}
    if not asked:
        return found
    hero, member = aliased(Section), aliased(Section)
    hero_course, member_course = aliased(Course), aliased(Course)
    hero_lead = _LEAD_FACULTY_COURSE.alias("hero_lead")
    member_lead = _LEAD_FACULTY_COURSE.alias("member_lead")
    statement = (
        select(hero.id.label("hero_id"), member.id.label("member_id"))
        .select_from(hero)
        .join(hero_course, hero_course.id == hero.course_id)
        .join(hero_lead, hero_lead.c.course_id == hero.course_id)
        .join(member_lead, member_lead.c.person_id == hero_lead.c.person_id)
        .join(member, member.course_id == member_lead.c.course_id)
        .join(member_course, member_course.id == member.course_id)
        .where(
            hero.id == any_(bindparam("asked", asked, type_=ARRAY(Uuid))),
            member.length_weeks == hero.length_weeks,
            member_course.level == hero_course.level,
            member.id != hero.id,
        )
        .distinct()
    )
    for row in session.execute(statement):
        found[row.hero_id].append(row.member_id)
    for members in found.values():
        members.sort()
    return found


def resolve_university(session: Session, *, section_id: UUID) -> list[UUID]:
    """Every matching section in the institution, the hero section among them.

    Decision 5's other half (ADR 0166). The university line is what the whole
    institution looks like, and a line drawn with one section deliberately left
    out is not that. **Its figures include the hero; its sealing does not.**
    Since E5-14 a university figure is shown only when, for every instructor of
    the reported section, each piece that instructor could isolate by
    subtraction is empty or clears both minimums. `_university_population`
    holds the rule and ADR 0179 the argument.
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
    reads: _Reads, *, default_set: Sequence[UUID], known: Sequence[AbstractSet[UUID]]
) -> _Population:
    """The default set's figures, sealed on the set and on what each reader would have left.

    E5-14's round-4 ruling, condition (b_p), with E9's readers (SPEC §5.1). Each
    person p who reads the report knows the count and the sum of every one of
    her sections — every section she teaches, in any term, and every section in
    her leadership purview — so she can subtract them. What is left for her, the
    set less `known[p]`, must be empty or clear both minimums. Per person, and
    never over the union of the readers: no one of them knows another's
    sections. The figure is still the whole set's.
    """
    remainders = [
        reads.of(section for section in default_set if section not in hers) for hers in known
    ]
    return _sealed_through(reads.of(default_set), remainders)


def _university_population(
    reads: _Reads,
    *,
    university: Sequence[UUID],
    known: Sequence[AbstractSet[UUID]],
    lead_sets_seen: Sequence[Sequence[AbstractSet[UUID]]],
) -> _Population:
    """The university line's figures, sealed so that no reader's subtraction isolates a thin population.

    The figure is the whole institution's, the reported section included (ADR
    0166, decision 5). A university point is shown only if (E5-14, rounds 4 to
    6), for every person p who reads the report — each holder of the teaching
    grant on the reported section, and the leadership reader if one is named —
    with p's sections `known[p]` being every section p teaches together with
    every section in p's leadership purview (SPEC §5.1, E9-05):

      (a) its population clears both minimums;
      (b_p) the university less p's sections is empty or clears them;
      (c_p) **every atom p could isolate** is empty or clears them: each lead
            atom — the default set of one of p's sections in this term at this
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

    A section nobody teaches, read with no leadership reader, has no p, so (a)
    alone applies; no instructor can read its report, because every instructor
    report route requires the teaching grant.
    """
    remainders: list[_Answered] = []
    for hers, lead_sets in zip(known, lead_sets_seen, strict=True):
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


def _known_by_reader(
    session: Session, *, section_id: UUID, scope: ActorScope | None
) -> list[set[UUID]]:
    """Each reader's own sections, one set per person, in person order (SPEC §5.1).

    A reader is each holder of the teaching grant on the reported section, and
    the leadership reader `scope` names, if any. **A reader's sections are what
    one person can subtract, across every hat she wears**: every section she
    teaches, and every section in her leadership purview. So an instructor who
    also chairs a department is sealed against that department's sections even
    on her own report, and an instructor with no leadership assignment is sealed
    exactly as before E9 (her purview is empty).

    One set per **person**, never per hat: a chair reading a report of a section
    she also teaches is one reader whose sections are both. Every set is read
    through `app.services.authz`, where `assignment_scope` is read.
    """
    known: dict[UUID, set[UUID]] = {
        person: taught_section_ids(session, person_id=person)
        | leadership_section_ids(session, person_id=person)
        for person in teaching_instructors_of(session, section_id=section_id)
    }
    if scope is not None:
        known[scope.person_id] = (
            known.get(scope.person_id, set())
            | scope.purview.section_ids
            | taught_section_ids(session, person_id=scope.person_id)
        )
    return [known[person] for person in sorted(known)]


def _section_populations(
    session: Session,
    *,
    section_id: UUID,
    cutoffs: Mapping[int, datetime],
    wanted: Collection[BenchmarkPopulation],
    scope: ActorScope | None,
) -> dict[BenchmarkPopulation, _Population]:
    """The section-keyed populations asked for, each resolved once and read through one `_Reads`.

    Each reader's sections are read once (`_known_by_reader`). The default set
    of the reported section and of every one of each reader's sections here —
    this term, this length and level — is resolved in **one** statement
    (`_default_sets_of`) and shared between readers; `_university_population`
    says why the university needs them. Each reader's lead sets are kept once
    per distinct set, and `_Reads` asks the set functions once per distinct
    section set, so the number of statements does not grow with the number of
    sections in a reader's purview (E9-05 fix round). It grows only with the
    number of distinct lead sets among them, and the one default-set statement
    answers more rows.
    """
    reads = _Reads(session, cutoffs)
    known = _known_by_reader(session, section_id=section_id, scope=scope)
    alike = (
        _alike_in_this_term(session, section_id=section_id)
        if BenchmarkPopulation.UNIVERSITY in wanted
        else set()
    )
    mine_here = [hers & alike for hers in known]
    default_sets = _default_sets_of(
        session, {section_id}.union(*mine_here) if mine_here else {section_id}
    )
    populations: dict[BenchmarkPopulation, _Population] = {}
    if BenchmarkPopulation.DEFAULT_SET in wanted:
        populations[BenchmarkPopulation.DEFAULT_SET] = _default_population(
            reads, default_set=default_sets[section_id], known=known
        )
    if BenchmarkPopulation.UNIVERSITY in wanted:
        lead_sets_seen = [
            list(dict.fromkeys(frozenset(default_sets[mine]) for mine in sorted(here)))
            for here in mine_here
        ]
        populations[BenchmarkPopulation.UNIVERSITY] = _university_population(
            reads,
            university=resolve_university(session, section_id=section_id),
            known=known,
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
    scope: ActorScope | None,
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

    `scope` is the leadership reader, when one reads the report (E9-09's
    drill-down). She enters the seal exactly as an instructor of the section
    does, with every section in her purview and every section she teaches as
    what she already knows (SPEC §5.1). An instructor's own report passes
    `scope=None`. **Required, with no default:** a leadership caller that
    forgot its reader would otherwise be sealed against the instructors alone,
    so every caller states which it is.
    """
    _the_weeks_cutoff(cutoffs, course_week)  # the reported week must be among those read
    by_population = _section_populations(
        session,
        section_id=section_id,
        cutoffs=cutoffs,
        wanted=tuple(BenchmarkPopulation),
        scope=scope,
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
        scope=None,
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
        scope=None,
    )
    return _workload(populations[population], course_week=course_week)


# ---------------------------------------------------------------------------
# A named set's figures, for one leadership reader (E9-05, SPEC §5.1 and §5.5).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NamedSetWeek:
    """One course week of one start cohort, on both of SPEC §2.2's week axes, every figure sealed.

    `ratings` is keyed by the report's stream tokens (`INSTRUCTOR`, `COURSE`).
    """

    course_week: int
    term_week: int
    ratings: Mapping[str, ComparisonFigure]
    workload: WorkloadComparison


@dataclass(frozen=True, slots=True)
class NamedSetCohort:
    """One start cohort of the reader's purview in the viewed term, and its published weeks."""

    section_start_date: date
    weeks: list[NamedSetWeek]


def _purview_cohorts(
    session: Session,
    *,
    purview: AbstractSet[UUID],
    term_id: UUID,
    length_weeks: int,
    level: CourseLevel,
) -> dict[date, set[UUID]]:
    """The reader's sections of one term, length and level, grouped by start date.

    **The cohorts come from the purview and never from the set.** So a set
    wholly outside the purview answers the same cohorts as a thin set inside it,
    each week suppressed, and a reader cannot tell "outside my purview" from
    "too few" (E9-05 done-when 9).

    The statement selects the term's sections at that length and level, and the
    purview is applied here in Python, so the statement carries no parameter per
    purview section.
    """
    if not purview:
        return {}
    rows = session.execute(
        select(Section.id, Section.start_date)
        .join(Course, Course.id == Section.course_id)
        .where(
            Section.term_id == term_id,
            Section.length_weeks == length_weeks,
            Course.level == level,
        )
    ).all()
    cohorts: dict[date, set[UUID]] = {}
    for section_id, start_date in rows:
        if section_id in purview:
            cohorts.setdefault(start_date, set()).add(section_id)
    return cohorts


def _cohort_cutoffs(
    session: Session,
    *,
    term: Term,
    length_weeks: int,
    level: CourseLevel,
    start_date: date,
) -> dict[int, datetime]:
    """Each course week's cutoff for one start cohort: its earliest window close (E9 decision 14).

    Every section of one start cohort, length and level in one term shares its
    window closes, so this is ADR 0178's earliest close within the population,
    narrowed to the cohort. It is computed over **every** such section, not only
    the reader's, so it depends on no reader: two leaders reading one cohort's
    week read one snapshot. The stored term week is read back as a course week
    through `section_codes.course_week_of`, and only the cohort's own course
    weeks are kept.
    """
    rows = session.execute(
        select(Week.number, func.min(SurveyWindow.closes_at))
        .join(Week, Week.id == SurveyWindow.week_id)
        .join(Section, Section.id == SurveyWindow.section_id)
        .join(Course, Course.id == Section.course_id)
        .where(
            Section.term_id == term.id,
            Section.length_weeks == length_weeks,
            Section.start_date == start_date,
            Course.level == level,
        )
        .group_by(Week.number)
    ).all()
    cutoffs: dict[int, datetime] = {}
    for number, closes_at in rows:
        course_week = course_week_of(number, section_start=start_date, term_start=term.start_date)
        if 1 <= course_week <= length_weeks:
            cutoffs[course_week] = closes_at
    return cutoffs


def named_set_series(
    session: Session, *, set_id: UUID, scope: ActorScope, term_id: UUID, settings: Settings
) -> list[NamedSetCohort]:
    """A named set's figures for one leadership reader in one term: one series per start cohort.

    SPEC §5.1 and §5.5, E9 ruling 5 and decisions 10 and 14. For the set's
    declared length L and level V:

      - **cohorts** are the start dates of the reader's purview sections of the
        term at L and V (`_purview_cohorts`);
      - **cohort C's population** is the set's resolved sections
        (`resolve_named_set`) inside the purview that start on C — never a
        section outside the purview, whatever the set names;
      - **week N's cutoff** is C's earliest week-N close (`_cohort_cutoffs`),
        and only the weeks whose report has opened are answered;
      - **each figure is sealed** against its own contributors and, as a second
        layer behind the narrowing, against what is left after removing what
        the reader already knows (her purview and the sections she teaches).
        That remainder is empty by construction, so the purview narrowing is
        what keeps a sibling's course out; the seal is the backstop.

    Both benchmark minimums apply to every figure (§4.1 item 7), so a set with
    no section inside the purview answers suppressed figures, the same as a thin
    one. **One door rather than a trend and a workload read**, so each cohort's
    population is read by each set function once (ADR 0203).

    Never raises: an unknown set or term answers no cohorts. The route
    distinguishes those two before it calls here
    (`app.services.comparison_sets.named_set_figures`).
    """
    declared = session.execute(
        select(ComparisonSet.length_weeks, ComparisonSet.level).where(ComparisonSet.id == set_id)
    ).one_or_none()
    term = session.get(Term, term_id)
    if declared is None or term is None:
        return []
    members = set(resolve_named_set(session, set_id=set_id))
    known = scope.purview.section_ids | taught_section_ids(session, person_id=scope.person_id)
    now = clock.now(session, settings=settings)
    zone = ZoneInfo(settings.institution_timezone)
    series: list[NamedSetCohort] = []
    cohorts = _purview_cohorts(
        session,
        purview=scope.purview.section_ids,
        term_id=term.id,
        length_weeks=declared.length_weeks,
        level=declared.level,
    )
    for start_date in sorted(cohorts):
        cutoffs = {
            course_week: closes_at
            for course_week, closes_at in _cohort_cutoffs(
                session,
                term=term,
                length_weeks=declared.length_weeks,
                level=declared.level,
                start_date=start_date,
            ).items()
            if week_is_published(closes_at, now=now, zone=zone)
        }
        population = sorted(members & cohorts[start_date])
        reads = _Reads(session, cutoffs)
        sealed = _sealed_through(
            reads.of(population),
            [reads.of(section for section in population if section not in known)],
        )
        trends = {
            stream: {
                point.course_week: point.figure
                for point in _trend(sealed, stream=stream, cutoffs=cutoffs)
            }
            for stream in REPORT_STREAMS
        }
        series.append(
            NamedSetCohort(
                section_start_date=start_date,
                weeks=[
                    NamedSetWeek(
                        course_week=course_week,
                        term_week=week_of_the_term(
                            course_week, section_start=start_date, term_start=term.start_date
                        ),
                        ratings={stream: trends[stream][course_week] for stream in REPORT_STREAMS},
                        workload=_workload(sealed, course_week=course_week),
                    )
                    for course_week in sorted(cutoffs)
                ],
            )
        )
    return series
