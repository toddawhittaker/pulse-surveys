"""The prior term's benchmark world, written into a development stack — ticket E5-12.

SPEC §5.1 compares a section against every section of its own length and level,
and the exit line says "benchmarked against prior terms". Nothing seeded before
this ticket lived in a prior term at all, so every comparison a developer could
build was against the current one. This file fills the term before it: a week of
survey answers for each of the prior-term sections the mock platform publishes,
so that the hero section's comparison set has something to hold and one
deliberately thin cohort has too little.

**Filling the sections is necessary and it is not sufficient**, which this line
claimed otherwise until 2026-09-14. SPEC §5.1 draws a section's *default*
comparison set from its course's Lead Faculty's courses, so a section whose
course has no lead-faculty mapping resolves an empty set however many matching
sections this file fills. `scripts/seed.py` maps a lead to `BIOL 310` for exactly
that reason, and the self-check at the end of this file does not check it: the
recount counts what this file wrote, by section code, and a reader asking
`app.services.benchmarks.resolve_default_set` is the only thing that answers
whether the set resolves at all (`docs/MISTAKES.md` entry 58).

**It is a second seeder rather than a fattened demo story**, and ADR 0167 records
why. `scripts/seed_demo_story.py` is deterministic per its own section label and
is scoped to one section; `scripts/seed_exit_story.py` is frozen, because
`tests/e2e/exit-instructor-report.spec.ts` asserts its counts exactly. Neither is
touched here.

**Nothing this file generates is a contract.** The counts, the distributions and
the rotation below are demonstration material and no test asserts them — E4-20's
ruling, which E5-12 repeats. What is asserted is how this refuses, that it writes
no calendar date of its own, and that the self-check at the end counts people and
sections rather than rows.

## How it is run

Piped into the api container, exactly as the demo story's seeder is:

    docker compose exec -T api python - < scripts/seed_benchmark_history.py

`scripts/` is not in the `api` image, so the file cannot be executed there by
path. Two consequences, and this file is written for both: its own directory is
not on `sys.path`, so it cannot import `scripts/seed.py` and does not try; and
`__file__` is undefined, so nothing here reaches for it.

## The drive, end to end

The order is the whole of it, and step 2 is the one that cannot be moved. The
roster sync stamps `enrollment.started_on` from the **effective** development
clock and never rewrites it, so a launch made at the real clock enrolls a prior
term's students today — after their term ended — and every windowed figure for
the cohort is then silently wrong while every row looks plausible. That is the
E4-22 anchor rule.

1. `make up`, then `make migrate` and `make seed` — the demo institution, both
   terms and their start-letter maps, on the tool's side.
2. **For each prior-term section, set the development clock to that section's own
   first day before launching it.** The `/dev` console's clock control (E2-04,
   ADR 0109) sets a pretended now. The dates are the prior term's own
   start-letter map rows, read off `/dev` or out of the `start_letter_map` table
   rather than copied from here — the two `U` sections and the `E` section begin
   on the term's first Monday and the `R` section three weeks later.
3. **One staff launch per section, as the instructor persona, at that clock.**
   The launch is what provisions the section (SPEC §7.3) and what stores the
   roster address; the sync that follows is what enrolls the class.
4. `docker compose exec -T api python -c 'from app.jobs.tasks import
   derive_survey_windows; derive_survey_windows()'` — the windows are a scheduled
   job's output (ADR 0111) and this file writes none.
5. Pipe this file, as above. It writes an answer set for every course week of
   every section it finds, prints what it wrote, and then recounts the cohorts
   from the database and says whether they clear SPEC §11's two minimums.
6. **Clear the development clock**, so the rest of the stack is back in the
   present. Nothing here depends on it: this world is entirely in the past and
   every date it writes comes off a stored window.

`scripts/seed_demo_story.py`'s own runbook points here for the benchmark half.

## The rules it is built on, and where each comes from

**It judges the environment before it builds anything.** The raw `ENVIRONMENT`
value is read out of `os.environ` and compared first, and **every `app` import in
this file happens inside a function** for that reason and no other: `app.db`
builds a `Settings` when it is imported (ADR 0013), and a deployment carrying a
development stack's own values is refused during that validation — so an operator
who pipes this at a deployment by accident would meet a traceback about the AI
provider rather than a refusal about the environment. Once the environment has
been judged, the constructed `Settings` is asked `is_development` too, which is a
second belt on the same rule. ADR 0063 is the rule and ADR 0167 records the shape.

**It provisions nothing, and refuses loudly instead** (`docs/MISTAKES.md` entry
48). No person, no `user`, no course, no section, no enrollment, no `week` and no
`survey_window`: it reads them and exits non-zero with a sentence naming the
sections that are missing. A platform that offers a launch says the platform holds
the section — never that the tool will invent it.

**Every section is resolved by its course, its term and its code**, never by its
code alone. A code is a string the outside world also supplies, and a lookup on it
alone adopts whatever carries it: a stranger's section would be filled with a
term's worth of invented responses under students who are not its roster
(`docs/MISTAKES.md` entry 31). A row this file did not launch is therefore never
found, never adopted and never deleted.

**Every date it writes derives from rows.** The term's dates come from the `term`
row, a section's from its `section` row, and the moment a response was submitted
from the `survey_window` row of its own week. There is no calendar date in this
file and nothing here asks what time it is: the prior term's windows are all
closed at any clock a drive could be run under, so "which weeks have finished" is
not a question this file has to ask. That is criterion 2, and the E4-22 trap class
it names.

**It is deterministic, and idempotent by natural key.** Every choice below comes
from a `random.Random` seeded from the section label and the course week, so two
runs write the same rows. A `response` is matched on `(user_id, section_id,
week_id)` — the key §8 already enforces — and an `answer` on `(response_id,
question_id)`, with any answer the plan does not describe deleted; `DELETE` on
`answer` is the one this connection holds. A response in a week this file writes
that this file did not plan is a refusal rather than a silently wrong world, for
the reason the demo story's seeder measures at length: this connection holds no
`DELETE` on `response`, and a leftover row would make a week's counts disagree
with everything else about that week.

**No comments, and both ratings are drawn from 3 upwards.** A benchmark figure is
a workload statistic or a rating mean (SPEC §5.1); no comment of a prior term's is
ever shown to anybody, and a seeded comment would need a classification verdict
and a validity recomputation to be honest. So this world carries none — and
because SPEC §3.2 requires a comment when a rating is 2 or lower, every rating
here starts at 3, which keeps every row one the real submit path would have
accepted.

**The counts are stated rather than hoped.** `the_cohort_recount` at the end
recounts from the database, per cohort week: how many distinct sections answered,
and how many distinct **students** — the unit SPEC §5.1's respondent minimum
compares, and `docs/MISTAKES.md` entry 50 is the incident behind saying so.
`main` compares those against `app.config.Settings`'s two `benchmark_min_*`
fields, never against a number written here, and exits non-zero if the cohort
that is meant to pass does not clear both or the cohort that is meant to suppress
is not under the section minimum.
"""

from __future__ import annotations

import os
import random
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Integer, Numeric, cast, distinct, func, select
from sqlalchemy.orm import Session

if TYPE_CHECKING:  # pragma: no cover - annotations only; see the docstring
    from app.models.org import Section
    from app.models.survey import Answer, Response

# ---------------------------------------------------------------------------
# The world this file fills.
# ---------------------------------------------------------------------------

# The term, by the name `scripts/seed.py` upserts it under. A name rather than a
# pair of dates, deliberately: the calendar is configuration and this file may not
# hold a copy of it (criterion 2), so the term is found by the one thing about it
# that is not a date. A copy of the name across two files is the same standing
# `scripts/seed_demo_story.py` has for its section label, and the refusal below
# names both files if the row is not there.
PRIOR_TERM_NAME = "Spring 2026"


@dataclass(frozen=True)
class PriorSection:
    """One prior-term section this file fills, and what its cohort is for.

    `code` is the §2.2 section code the `section` row carries and `label` is the
    section as a person writes it — the course prefix and number, then the code —
    which is how the mock platform publishes it and how a refusal names it.

    `must_pass` says which of the two demonstrations this section belongs to: the
    cohort that has to clear both of SPEC §11's minimums, or the thin one that has
    to sit under the section minimum so that suppression is visible in the world
    rather than only in a unit test. **It is a statement of intent and not a copy
    of the calendar**: which length and level a section actually has is read back
    off its own row, and the self-check compares the two.
    """

    label: str
    prefix: str
    number: str
    code: str
    must_pass: bool

    @property
    def subject_prefix(self) -> str:
        """The pattern the mock platform mints this section's students under."""
        return f"mock-lms-user-{self.label.lower()}-student-"


# The four sections `mock-lms/app/seed.py` publishes in the prior term. Three of
# them are twelve-week undergraduate sections, which is `BIOL-310-R7FF`'s own
# length and level and therefore its comparison set; the fourth is a six-week
# section on its own.
PRIOR_SECTIONS: tuple[PriorSection, ...] = (
    PriorSection("BIOL-310-U5FF", "BIOL", "310", "U5FF", must_pass=True),
    PriorSection("BIOL-310-U6WW", "BIOL", "310", "U6WW", must_pass=True),
    PriorSection("BIOL-310-R5FF", "BIOL", "310", "R5FF", must_pass=True),
    PriorSection("BIOL-215-E5WW", "BIOL", "215", "E5WW", must_pass=False),
)

# ---------------------------------------------------------------------------
# The shape of a week, in the demo story's currency.
# ---------------------------------------------------------------------------

# How many of a section's students answer in a week, as a share of the roster it
# actually has rather than as a count: the sections here carry twenty students and
# twelve, and a floor of seventeen would be a floor above one of those rosters.
# Drawn per week, so the set of respondents rotates. Nothing asserts either bound.
RESPONDENTS_FLOOR_SHARE, RESPONDENTS_CEILING_SHARE = 0.85, 1.0

# The shape of a week's ratings, as weights over 3, 4, 5 — see the module
# docstring on why this world starts at 3. Each week's own weights are these with
# an independent -1/0/+1 applied to every entry, which is a wobble rather than a
# story arc: a seeder that engineered a trend would put a conclusion into
# demonstration data.
BASE_INSTRUCTOR_WEIGHTS = (6, 9, 6)
BASE_COURSE_WEIGHTS = (7, 8, 5)

# The lowest rating a response may carry. SPEC §3.2 requires a comment at 2 and
# below and nothing here writes one.
LOWEST_RATING = 3

# The workload slider's range for this world, in half-hour steps: 4.0 to 14.0
# hours. §3.2's own range is 0 to 40 in half-hour steps, which is what the column
# admits; this is the part of it a three-credit course actually occupies, and it
# is the demo story's range so that a comparison between the two reads sensibly.
WORKLOAD_LOWEST_HALF_HOURS, WORKLOAD_HIGHEST_HALF_HOURS = 8, 28

# SPEC §3.2's five questions, by the position and the shape `scripts/seed.py`
# writes them under. Checked rather than assumed, because everything below picks a
# question by its ordinal and the set is versioned: a v2 that moved the workload
# slider to position 3 would otherwise be seeded with ratings in a comment column.
INSTRUCTOR_RATING, INSTRUCTOR_COMMENT, COURSE_RATING, COURSE_COMMENT, WORKLOAD = 1, 2, 3, 4, 5

_DAYS_PER_WEEK = 7


class BenchmarkHistoryRefusedError(Exception):
    """The world this file needs is not there, and it will not invent it.

    One exception with a written-out message rather than a return code, so every
    refusal below reads as one sentence a person can act on and the caller has one
    place to print it. `docs/MISTAKES.md` entry 48 is the rule.
    """


# ---------------------------------------------------------------------------
# The plan, generated rather than written out.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedResponse:
    """One student's answers for one week of one section, before any of it is a row."""

    subject: str
    instructor_rating: int
    course_rating: int
    workload_hours: Decimal


def _drifted(weights: Sequence[int], rng: random.Random) -> tuple[int, ...]:
    """One week's rating weights: the base shape, wobbled by one in either direction."""
    return tuple(max(1, weight + rng.randint(-1, 1)) for weight in weights)


def _a_rating(rng: random.Random, weights: Sequence[int]) -> int:
    """A Likert rating drawn under `weights`, over `LOWEST_RATING` upwards."""
    values = list(range(LOWEST_RATING, LOWEST_RATING + len(weights)))
    return rng.choices(values, weights=list(weights))[0]


def plan_one_week(
    label: str, course_week: int, roster: Sequence[str]
) -> tuple[PlannedResponse, ...]:
    """Who answers this week of this section, and what they say.

    Seeded from the section label and the course week, so a re-run writes the same
    rows and a week's plan does not move when a week beside it does. Every bound is
    taken against the roster it is given, so a section whose class size changes is
    planned rather than crashed.
    """
    # S311: a seeded `random.Random` is exactly what is wanted here — nothing this
    # produces is a secret, and reproducibility is the requirement.
    rng = random.Random(f"{label}:course-week-{course_week}")  # noqa: S311

    most = max(1, round(len(roster) * RESPONDENTS_CEILING_SHARE))
    fewest = max(1, min(most, round(len(roster) * RESPONDENTS_FLOOR_SHARE)))
    respondents = rng.sample(list(roster), k=rng.randint(fewest, most))

    instructor_weights = _drifted(BASE_INSTRUCTOR_WEIGHTS, rng)
    course_weights = _drifted(BASE_COURSE_WEIGHTS, rng)

    return tuple(
        PlannedResponse(
            subject=subject,
            instructor_rating=_a_rating(rng, instructor_weights),
            course_rating=_a_rating(rng, course_weights),
            workload_hours=Decimal(
                rng.randrange(WORKLOAD_LOWEST_HALF_HOURS, WORKLOAD_HIGHEST_HALF_HOURS + 1)
            )
            / 2,
        )
        for subject in sorted(respondents)
    )


# ---------------------------------------------------------------------------
# Reading the world.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WeekOfTheSection:
    """One course week of one section, with the week row and window it needs."""

    course_week: int
    term_week: int
    week_id: UUID
    opens_at: datetime
    closes_at: datetime


@dataclass(frozen=True)
class SectionOfTheWorld:
    """One prior-term section as this database holds it, with its weeks and roster."""

    planned: PriorSection
    row: Section
    level: str
    weeks: tuple[WeekOfTheSection, ...]
    roster: Mapping[str, UUID]

    @property
    def cohort(self) -> tuple[int, str]:
        """The cohort key SPEC §5.1 compares by: a length in weeks and a level.

        Both read off the rows — the length is the section's own column, derived
        from its code, and the level is generated from the course's number
        (ADR 0015) — so neither is a number this file chose.
        """
        return (int(self.row.length_weeks), self.level)


def the_prior_term(session: Session) -> Any:
    """The `term` row this world lives in, by name, or a refusal naming the seed."""
    from app.models.term import Term

    found = list(session.scalars(select(Term).where(Term.name == PRIOR_TERM_NAME)))
    if len(found) != 1:
        raise BenchmarkHistoryRefusedError(
            f"This database holds {len(found)} term(s) named {PRIOR_TERM_NAME!r}, and this world "
            "needs exactly one. `scripts/seed.py` seeds it beside Fall 2026 — a term row, its week "
            "rows and its own start-letter map — so zero means `make seed` has not been run against "
            "this database since E5-12. This file seeds no term, no week and no start-letter row."
        )
    return found[0]


def the_sections(session: Session, term: Any) -> tuple[SectionOfTheWorld, ...]:
    """Every section this file fills, or a refusal naming the ones that are missing.

    Each is resolved by `(course, term, code)` — E0-06's own natural key for a
    section — so a row carrying one of these codes in another term, or under
    another course, is not this file's and is neither read nor written. It is not
    deleted either: this connection holds no `DELETE` on `section`, and a
    collision an operator put there is theirs to explain.
    """
    from app.models.org import Course, Prefix, Section

    found: list[SectionOfTheWorld] = []
    missing: list[str] = []
    for planned in PRIOR_SECTIONS:
        held = session.execute(
            select(Section, Course.level)
            .join(Course, Course.id == Section.course_id)
            .join(Prefix, Prefix.id == Course.prefix_id)
            .where(
                Section.term_id == term.id,
                Section.lms_section_code == planned.code,
                Course.lms_number == planned.number,
                Prefix.code == planned.prefix,
            )
        ).one_or_none()
        if held is None:
            missing.append(planned.label)
            continue
        row, level = held
        found.append(
            SectionOfTheWorld(
                planned=planned,
                row=row,
                level=str(level),
                weeks=the_weeks(session, row, term),
                roster=the_roster(session, row, planned),
            )
        )
    if missing:
        raise BenchmarkHistoryRefusedError(
            f"These sections are not in this database: {', '.join(missing)}. A staff launch is what "
            "provisions a section (SPEC §7.3) and this file creates none. Launch each of them from "
            "the mock platform as the instructor persona, **with the development clock set to that "
            "section's own first day** — the roster sync stamps every enrollment from the effective "
            "clock, so a launch at the real clock enrolls a prior term's students in the present — "
            "then run the roster sync and `derive_survey_windows`, then pipe this file again. The "
            "drive is written out in this file's module docstring."
        )
    return tuple(found)


def the_weeks(session: Session, section: Section, term: Any) -> tuple[WeekOfTheSection, ...]:
    """Every course week of one section, with the window row it hangs on.

    **Derived from the stored rows and never from a count.** The windows are a
    scheduled job's output (ADR 0111) and this file writes none; a file that knew
    how many weeks a section has would be a second copy of the calendar
    (`docs/MISTAKES.md` entry 19). The course-to-term translation is
    `app.services.section_codes.week_of_the_term` applied to week 1 and then
    counted forward, which is what `app.services.reporting` does with the same
    rows.
    """
    from app.models.term import SurveyWindow, Week
    from app.services.section_codes import week_of_the_term

    first_term_week = week_of_the_term(
        1, section_start=section.start_date, term_start=term.start_date
    )
    rows = session.execute(
        select(Week.number, SurveyWindow.week_id, SurveyWindow.opens_at, SurveyWindow.closes_at)
        .join(Week, Week.id == SurveyWindow.week_id)
        .where(SurveyWindow.section_id == section.id)
        .order_by(Week.number)
    ).all()
    if not rows:
        raise BenchmarkHistoryRefusedError(
            f"{section.lms_section_code} holds no `survey_window` row at all. A section provisioned "
            "by a launch has none until `app.jobs.tasks.derive_survey_windows` runs (ADR 0111), "
            "which is a scheduled job and is step 4 of the drive in this file's docstring. This "
            "file creates no window and no week."
        )
    return tuple(
        WeekOfTheSection(
            course_week=number - first_term_week + 1,
            term_week=number,
            week_id=week_id,
            opens_at=opens_at,
            closes_at=closes_at,
        )
        for number, week_id, opens_at, closes_at in rows
    )


def the_roster(session: Session, section: Section, planned: PriorSection) -> dict[str, UUID]:
    """One section's students' `user` rows, found through their enrollments.

    **The subject is resolved forward and never read off the row.** `pulse_app`
    holds `SELECT` on `user.id` alone — a connection that could read
    `lms_user_id` could enumerate every subject that ever launched — so the walk
    is over this section's enrollments, asking `app.services.identity` for each,
    which is ADR 0139's sanctioned definer door.

    Refuses rather than enrolls (`docs/MISTAKES.md` entry 48): the roster sync is
    what writes an enrollment (SPEC §7.3). What it refuses is an *empty* roster
    rather than a short one — the mock platform's class sizes are that file's
    business and not this one's, and a section whose sync has not run holds
    nobody at all.
    """
    from app.models.identity import Enrollment
    from app.services.identity import subject_for_user

    found: dict[str, UUID] = {}
    for user_id in session.scalars(
        select(Enrollment.user_id).where(Enrollment.section_id == section.id)
    ):
        subject = subject_for_user(session, user_id)
        if subject is not None and subject.startswith(planned.subject_prefix):
            found[subject] = user_id
    if not found:
        raise BenchmarkHistoryRefusedError(
            f"{planned.label} holds no enrollment for any student whose subject begins "
            f"{planned.subject_prefix!r}. The roster sync is what enrols them (SPEC §7.3), so this "
            "is the worker not running, the mock platform not serving its roster, or the staff "
            "launch not having stored the section's roster address. This file creates no user and "
            "no enrollment."
        )
    return found


def the_instrument(session: Session) -> dict[int, UUID]:
    """SPEC §3.2's five questions of the set in force, by position, shape-checked."""
    from app.models.survey import REPORT_STREAMS, Question, QuestionKind, QuestionSet

    instructor_stream, course_stream = REPORT_STREAMS
    expected: Mapping[int, tuple[QuestionKind, str | None]] = {
        INSTRUCTOR_RATING: (QuestionKind.LIKERT, instructor_stream),
        INSTRUCTOR_COMMENT: (QuestionKind.COMMENT, instructor_stream),
        COURSE_RATING: (QuestionKind.LIKERT, course_stream),
        COURSE_COMMENT: (QuestionKind.COMMENT, course_stream),
        WORKLOAD: (QuestionKind.WORKLOAD, None),
    }

    question_set_id = session.scalars(
        select(QuestionSet.id).order_by(QuestionSet.version.desc()).limit(1)
    ).one_or_none()
    if question_set_id is None:
        raise BenchmarkHistoryRefusedError(
            "This database holds no `question_set`. SPEC §3.2's instrument is seeded by "
            "`scripts/seed.py`; this file writes answers to it and does not write it."
        )
    asked: dict[int, tuple[UUID, QuestionKind, str | None]] = {
        position: (question_id, kind, stream)
        for question_id, position, kind, stream in session.execute(
            select(Question.id, Question.position, Question.kind, Question.stream).where(
                Question.question_set_id == question_set_id
            )
        )
    }
    for position, (kind, stream) in expected.items():
        found = asked.get(position)
        if found is None or found[1] != kind or found[2] != stream:
            raise BenchmarkHistoryRefusedError(
                f"Question {position} of the question set in force is {found!r}, and this world is "
                f"written for a {kind.value} question on the {stream!r} stream. Everything here "
                "picks a question by its ordinal and §3.2's set is versioned, so a set that has "
                "moved its questions would be seeded with a rating in a comment column. Re-run "
                "`make seed`, or correct this file against the set that is in force."
            )
    return {position: asked[position][0] for position in expected}


def refuse_a_foreign_response(
    session: Session,
    world: SectionOfTheWorld,
    plan: Mapping[int, tuple[PlannedResponse, ...]],
) -> None:
    """Refuse if a week this file writes holds a response this file did not plan.

    This connection holds no `DELETE` on `response` — `pulse_app` has one on
    `answer` and on nothing else here — so a leftover row cannot be cleared and
    must not be written around either: it would make a week's response count
    disagree with everything else about that week.
    """
    from app.models.survey import Response

    planned = {
        (world.roster[response.subject], week.week_id)
        for week in world.weeks
        for response in plan[week.course_week]
    }
    written_weeks = {week.week_id for week in world.weeks}
    foreign = [
        (user_id, week_id)
        for user_id, week_id in session.execute(
            select(Response.user_id, Response.week_id).where(Response.section_id == world.row.id)
        )
        if week_id in written_weeks and (user_id, week_id) not in planned
    ]
    if foreign:
        raise BenchmarkHistoryRefusedError(
            f"{world.planned.label} holds {len(foreign)} response row(s) in the weeks this world "
            "writes that it does not describe, and this connection holds no `DELETE` on `response` "
            "to clear them with. Left in place they would make a week's response count disagree "
            "with the rest of that week. Clear the section first — `clearTheWeek` in "
            "`tests/e2e/support/survey.ts` is that statement, run through the `db` container's own "
            "superuser."
        )


# ---------------------------------------------------------------------------
# Writing the world.
# ---------------------------------------------------------------------------


@dataclass
class Written:
    """What one run wrote, for the lines it prints at the end."""

    sections: int = 0
    responses: int = 0
    answers: int = 0


def one_response(
    session: Session,
    *,
    section: Section,
    week: WeekOfTheSection,
    user_id: UUID,
    submitted_at: datetime,
) -> Response:
    """This student's response for this week, matched on §8's own key or inserted."""
    from app.models.survey import Response

    response = session.scalars(
        select(Response).where(
            Response.user_id == user_id,
            Response.section_id == section.id,
            Response.week_id == week.week_id,
        )
    ).one_or_none()
    if response is None:
        response = Response(
            user_id=user_id,
            section_id=section.id,
            week_id=week.week_id,
            term_id=section.term_id,
            first_submitted_at=submitted_at,
            last_submitted_at=submitted_at,
            # Every response here carries ratings and hours and no comment, so
            # there is no verdict for `app.services.validity` to read and nothing
            # that could make one invalid (§3.3).
            is_valid=True,
        )
        session.add(response)
    else:
        response.first_submitted_at = submitted_at
        response.last_submitted_at = submitted_at
        response.is_valid = True
    session.flush()
    return response


def one_answer(
    session: Session,
    *,
    response: Response,
    question_id: UUID,
    rating: int | None = None,
    workload_hours: Decimal | None = None,
) -> Answer:
    """One answer of one response, matched on `(response_id, question_id)` or inserted.

    All three value columns are set on every write, not only the one that carries a
    value, because `answer`'s own CHECK is `num_nonnulls(...) = 1`: a row rewritten
    from a rating to a workload figure has to lose the rating in the same statement.
    """
    from app.models.survey import Answer

    answer = session.scalars(
        select(Answer).where(Answer.response_id == response.id, Answer.question_id == question_id)
    ).one_or_none()
    if answer is None:
        answer = Answer(response_id=response.id, question_id=question_id)
        session.add(answer)
    answer.rating = rating
    answer.comment_text = None
    answer.workload_hours = workload_hours
    session.flush()
    return answer


def _submitted_at(label: str, week: WeekOfTheSection, subject: str) -> datetime:
    """When this student answered: some moment inside this week's own window.

    Copied off the stored window rather than computed, for ADR 0142's reason — the
    windows are derived from the calendar and stored. Nothing on a report or in
    either Monday job compares a response's timestamp to anything, so all this has
    to be is coherent: a response submitted inside the week it is about.
    """
    span = int((week.closes_at - week.opens_at).total_seconds())
    # S311: seeded on purpose, and nothing here is a secret. See `plan_one_week`.
    rng = random.Random(f"{label}:{week.course_week}:{subject}")  # noqa: S311
    return week.opens_at + timedelta(seconds=rng.randrange(max(span, 1)))


def write_one_section(
    session: Session, world: SectionOfTheWorld, questions: Mapping[int, UUID]
) -> Written:
    """Write an answer set for every course week of one section."""
    from app.models.survey import Answer

    subjects = sorted(world.roster)
    plan = {
        week.course_week: plan_one_week(world.planned.label, week.course_week, subjects)
        for week in world.weeks
    }
    refuse_a_foreign_response(session, world, plan)

    written = Written(sections=1)
    for week in world.weeks:
        for planned in plan[week.course_week]:
            response = one_response(
                session,
                section=world.row,
                week=week,
                user_id=world.roster[planned.subject],
                submitted_at=_submitted_at(world.planned.label, week, planned.subject),
            )
            written.responses += 1

            one_answer(
                session,
                response=response,
                question_id=questions[INSTRUCTOR_RATING],
                rating=planned.instructor_rating,
            )
            one_answer(
                session,
                response=response,
                question_id=questions[COURSE_RATING],
                rating=planned.course_rating,
            )
            one_answer(
                session,
                response=response,
                question_id=questions[WORKLOAD],
                workload_hours=planned.workload_hours,
            )
            written.answers += 3

            # Every answer of this response the plan does not describe, removed:
            # the one `DELETE` this connection holds, and what makes a re-run over
            # an edited plan a re-seed rather than a merge.
            planned_questions = {
                questions[INSTRUCTOR_RATING],
                questions[COURSE_RATING],
                questions[WORKLOAD],
            }
            for stale in session.scalars(
                select(Answer).where(
                    Answer.response_id == response.id,
                    Answer.question_id.not_in(planned_questions),
                )
            ):
                session.delete(stale)
            session.flush()
    return written


def write_the_history(session: Session) -> tuple[Written, tuple[SectionOfTheWorld, ...]]:
    """Write every prior-term section's weeks, and hand back what was written."""
    term = the_prior_term(session)
    sections = the_sections(session, term)
    questions = the_instrument(session)

    written = Written()
    for world in sections:
        one = write_one_section(session, world, questions)
        written.sections += one.sections
        written.responses += one.responses
        written.answers += one.answers
    return written, sections


# ---------------------------------------------------------------------------
# The self-check: what the database holds, recounted.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CohortWeekCount:
    """One cohort week, as the database answers for it.

    `section_count` counts sections and `respondent_count` counts **people** — a
    distinct count over the response's author, because a student may sit in two
    sections of one cohort and the minimum it is compared against exists to
    protect people (`docs/MISTAKES.md` entry 50). Neither is a count of responses.
    """

    length_weeks: int
    level: str
    course_week: int
    section_count: int
    respondent_count: int


def the_cohort_recount(session: Session, section_codes: Sequence[str]) -> list[CohortWeekCount]:
    """Recount the cohorts the named sections belong to, from the database.

    Per `(length_weeks, level, course_week)`: how many distinct sections carry a
    response in that cohort week, and how many distinct students wrote one. **From
    the rows and never from this file's plan** — a self-check that recounted its
    own intentions would agree with itself whatever was written.

    The course week is derived the way SPEC §2.2 derives it and the way E5-03's
    own views derive it: the week's number in its term, less the whole weeks
    between the section's first day and the term's.

    `section_codes` is explicit rather than implied so that the counting can be
    exercised over a world a caller planted; `main` hands it this file's own codes.
    """
    from app.models.org import Course, Section
    from app.models.survey import Response
    from app.models.term import Term, Week

    weeks_in = func.floor(cast(Section.start_date - Term.start_date, Numeric) / _DAYS_PER_WEEK)
    course_week = Week.number - cast(weeks_in, Integer)
    rows = session.execute(
        select(
            Section.length_weeks,
            Course.level,
            course_week.label("course_week"),
            func.count(distinct(Section.id)),
            func.count(distinct(Response.user_id)),
        )
        .select_from(Response)
        .join(Section, Section.id == Response.section_id)
        .join(Course, Course.id == Section.course_id)
        .join(Term, Term.id == Section.term_id)
        .join(Week, Week.id == Response.week_id)
        .where(Section.lms_section_code.in_(list(section_codes)))
        .group_by(Section.length_weeks, Course.level, course_week)
        .order_by(Section.length_weeks, Course.level, course_week)
    ).all()
    return [
        CohortWeekCount(
            length_weeks=int(length_weeks),
            level=str(level),
            course_week=int(week),
            section_count=int(sections),
            respondent_count=int(respondents),
        )
        for length_weeks, level, week, sections, respondents in rows
    ]


def the_intended_cohorts(sections: Sequence[SectionOfTheWorld]) -> dict[tuple[int, str], bool]:
    """Which cohort key each declared section landed in, and whether it must pass.

    The key is read off the rows — a section's length is its own column and a
    course's level is generated from its number (ADR 0015) — so this is what the
    world *is*, married to what this file meant it to be. A cohort whose sections
    disagree about that is a defect in this file's own table and says so.
    """
    intent: dict[tuple[int, str], bool] = {}
    for world in sections:
        key = world.cohort
        if intent.setdefault(key, world.planned.must_pass) != world.planned.must_pass:
            raise BenchmarkHistoryRefusedError(
                f"{world.planned.label} is a {key[0]}-week {key[1]} section, and another section in "
                "the same cohort is declared for the opposite demonstration in `PRIOR_SECTIONS`. "
                "One cohort cannot be both the one that must clear the minimums and the one that "
                "must sit under them."
            )
    return intent


def check_the_cohorts(
    counts: Sequence[CohortWeekCount],
    intent: Mapping[tuple[int, str], bool],
    *,
    minimum_sections: int,
    minimum_respondents: int,
) -> list[str]:
    """Every way the counted world falls short of what it was seeded to demonstrate.

    The two minimums are `app.config.Settings`'s, handed in by the caller: SPEC
    §11 leaves the numbers open and they are configuration, so a copy of either
    here would be a second place for them to be wrong.
    """
    faults: list[str] = []
    for count in counts:
        must_pass = intent.get((count.length_weeks, count.level))
        where = f"{count.length_weeks}-week {count.level}, course week {count.course_week}"
        if must_pass is None:
            faults.append(f"{where}: counted, but no section declared here belongs to that cohort")
        elif must_pass:
            if count.section_count < minimum_sections:
                faults.append(
                    f"{where}: {count.section_count} sections, and a comparison set is shown only "
                    f"at {minimum_sections}"
                )
            if count.respondent_count < minimum_respondents:
                faults.append(
                    f"{where}: {count.respondent_count} respondents, and a comparison set is shown "
                    f"only at {minimum_respondents}"
                )
        elif count.section_count >= minimum_sections:
            faults.append(
                f"{where}: {count.section_count} sections, which is at or above the minimum of "
                f"{minimum_sections} — this cohort exists to be suppressed, and it would now be "
                "shown"
            )
    for key, must_pass in sorted(intent.items()):
        if not any((count.length_weeks, count.level) == key for count in counts):
            faults.append(
                f"{key[0]}-week {key[1]}: no cohort week was counted at all, and this file seeded "
                f"sections for it {'to pass' if must_pass else 'to be suppressed'}"
            )
    return faults


# ---------------------------------------------------------------------------
# The environment guard, and the program.
# ---------------------------------------------------------------------------

# The variable a deployment is named by. Compared raw and before anything else,
# for the reason this module's docstring gives at length.
ENVIRONMENT_VARIABLE = "ENVIRONMENT"


def the_environment_refusal(environ: Mapping[str, str]) -> str | None:
    """The sentence this refuses a deployment with, or `None` where it may run.

    ADR 0063's rule applied to the raw mapping: an equality against the one name
    that is safe, so `staging`, `production` and `development-blue` are all
    deployments. The name itself is `app.config.DEVELOPMENT_ENVIRONMENT` rather
    than a second copy of the string (`docs/MISTAKES.md` entry 13), which is safe
    to import here because `app.config` builds no `Settings` when it is imported.

    **This sentence deliberately does not name a section.** The two refusals this
    file owes are told apart by what they say — one names `ENVIRONMENT` or the
    value it found, the other names the sections that are missing — and a refusal
    about the environment that also named a section would satisfy both readings,
    so a guard inverted to refuse development would pass the test written to catch
    exactly that (`docs/MISTAKES.md` entry 3).
    """
    from app.config import DEVELOPMENT_ENVIRONMENT

    raw = environ.get(ENVIRONMENT_VARIABLE)
    if raw == DEVELOPMENT_ENVIRONMENT:
        return None

    if raw is None:
        found = "(not set)"
    elif not raw.strip():
        found = f"{raw!r} (set, but empty)"
    else:
        found = repr(raw)
    return (
        f"seed_benchmark_history refuses to run with {ENVIRONMENT_VARIABLE}={found}. It runs only "
        f"where {ENVIRONMENT_VARIABLE} is {DEVELOPMENT_ENVIRONMENT!r}. This file writes a prior "
        "term of invented survey responses for the mock platform's own sections into whatever "
        "database it is pointed at, and there is no environment other than a developer's own where "
        "that is the right thing to do. See "
        "docs/adr/0063-the-demo-seed-runs-only-in-a-development-environment.md."
    )


def main() -> int:
    """Judge the environment, write the world, then recount it and say whether it holds up."""
    refusal = the_environment_refusal(os.environ)
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 1

    # Every `app` import from here down, and none above: the guard has to answer
    # before a `Settings` is built, because `app.db` builds one when it is imported
    # and a deployment carrying a development stack's values is refused during that
    # construction. See this module's docstring.
    from app.config import Settings, is_development
    from app.db import SessionLocal

    settings = Settings()
    if not is_development(settings):
        # The same rule asked of the validated field. The raw check above reads the
        # variable pydantic reads, and the process environment beats `.env`, so the
        # two agree wherever this is run the way its docstring says; the two
        # disagreeing is the thing this check exists for.
        print(
            "seed_benchmark_history refuses to run: the raw "
            f"{ENVIRONMENT_VARIABLE} admitted this run, and the configuration this process then "
            f"validated names {ENVIRONMENT_VARIABLE}={settings.environment!r}, which "
            "`app.config.is_development` does not admit. Look at what the process environment sets "
            "against what `.env` sets.",
            file=sys.stderr,
        )
        return 1

    with SessionLocal() as session:
        try:
            written, sections = write_the_history(session)
            intent = the_intended_cohorts(sections)
        except BenchmarkHistoryRefusedError as refused:
            session.rollback()
            print(f"seed_benchmark_history refused: {refused}", file=sys.stderr)
            return 1
        session.commit()

        # Recounted after the commit, over what the database holds rather than over
        # what was just planned, and reported whatever it says: the rows are the
        # world an operator now has, and a check that rolled them back would leave
        # them with nothing to look at and no counts to explain it.
        codes = [planned.code for planned in PRIOR_SECTIONS]
        counts = the_cohort_recount(session, codes)

    print(
        f"seed_benchmark_history wrote {written.responses} responses and {written.answers} answers "
        f"across {written.sections} sections of {PRIOR_TERM_NAME}."
    )
    for count in counts:
        sections_held = "section" if count.section_count == 1 else "sections"
        students_held = "student" if count.respondent_count == 1 else "students"
        print(
            f"  {count.length_weeks}-week {count.level}, course week {count.course_week}: "
            f"{count.section_count} {sections_held}, {count.respondent_count} distinct "
            f"{students_held}"
        )

    faults = check_the_cohorts(
        counts,
        intent,
        minimum_sections=settings.benchmark_min_sections_default,
        minimum_respondents=settings.benchmark_min_respondents_default,
    )
    if faults:
        print(
            "seed_benchmark_history: the world it wrote does not demonstrate what it is for "
            f"(minimums: {settings.benchmark_min_sections_default} sections, "
            f"{settings.benchmark_min_respondents_default} respondents):",
            file=sys.stderr,
        )
        for fault in faults:
            print(f"  {fault}", file=sys.stderr)
        return 1

    print(
        "Every cohort week of the comparison set clears both minimums "
        f"({settings.benchmark_min_sections_default} sections, "
        f"{settings.benchmark_min_respondents_default} respondents), and the thin cohort is under "
        "the section minimum, so its figures suppress."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
