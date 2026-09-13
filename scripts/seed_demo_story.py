"""E4-20's representative demo story for `BIOL-310-R7FF`, written into a development stack.

The exit story beside this one (`scripts/seed_exit_story.py`, E4-15) proves SPEC
§14.3's exit line for E4 with hand-planned numbers, and
`tests/e2e/exit-instructor-report.spec.ts` asserts those numbers exactly: one
comment per stream in each open week. That world is correct and it is thin —
driven in front of somebody, a Monday report carrying two comments a week reads
as a screenshot rather than as a section. This file is the other kind of demo
material: twenty students, most of whom answer, most of whom write something, in
a section nothing else in this repository launches. **The exit story is frozen
and this file does not touch it.** Fattening it would break the numbers its
end-to-end spec asserts.

**Nothing here is a contract, and that is the owner's ruling of 2026-09-09.** The
counts, the distributions, the drift and the rotation below are demonstration
material; no test asserts any of them. What is asserted, in
`tests/integration/test_the_demo_story_seeder_refuses_a_deployment_and_an_unlaunched_section.py`,
is the two ways this refuses: outside a development environment, and against a
world where the section was never launched.

## How it is run

Piped into the api container, exactly as the exit story's seeder is:

    docker compose exec -T api python - < scripts/seed_demo_story.py

`scripts/` is not in the `api` image — `backend/Dockerfile` copies the
application and `docker-compose.yml` mounts only `scripts/db-init` — so the file
cannot be executed in the container by path, and piping it is what puts it in
front of the application's own interpreter, configuration and database. Two
consequences follow and this file is written for both: its own directory is not
on `sys.path`, so it cannot import `scripts/seed.py` and does not try; and
`__file__` is undefined, so nothing here reaches for it.

## The drive, end to end

1. `make up`, then `make migrate` and `make seed` — the demo institution, its
   term and its people, on the tool's side.
2. **One staff launch of the new placement, as the instructor persona, at the
   real clock.** The mock platform's launch page offers it as `BIOL-310-R7FF`.
   The launch is what provisions the section (SPEC §7.3) and what stores the
   roster address; the sync that follows stamps `section.started_on` from the
   effective now and never rewrites it, and
   `app/services/enrollment_windows.py` counts every member of a section's first
   sync from the section's own start. A launch made at a pretended clock stamps
   a start nobody can undo.
3. `docker compose exec -T api python -c 'from app.jobs.tasks import
   derive_survey_windows; derive_survey_windows()'` — the windows are a
   scheduled job's output (ADR 0111) and this file writes none.
4. **Move the development clock forward, and do it before this file runs.** The
   `/dev` console's clock control (E2-04, ADR 0109) sets a pretend now;
   `2026-10-19T09:00` puts six of this section's twelve weeks behind it. This
   step is out of order in E4-20's own work order, which lists the clock move
   last: this file writes a response for every week whose survey window has
   *closed at the effective clock*, and at the real clock in September none has,
   so a run before the move writes nothing at all. It refuses rather than
   writing nothing, and the refusal says this.
5. Pipe this file, as above.
6. Run the two Monday jobs, the way `tests/e2e/support/stack.ts` runs them:
   `generate_weekly_summaries` and then `cut_release_batches`, each through
   `docker compose exec -T api python -c ...`. This file writes neither of their
   tables.
7. Open the instructor's report for `BIOL-310-R7FF`.

## The rules it is built on, and where each comes from

**It judges the environment before it builds anything.** `scripts/seed.py` does
the same and ADR 0063 is the rule; the exit story's seeder builds a `Settings`
first and asks `app.config.is_development` of it, and that shape cannot be copied
here. Under a deployment environment carrying a development stack's own values —
a blank AI provider URL, a mock identity provider — `Settings` refuses during
validation, and `app.db` builds one of its own the moment it is imported
(ADR 0013), so an operator who pipes this at a deployment by accident would meet
a traceback about the AI provider rather than a refusal about the environment.
So the raw `ENVIRONMENT` value is judged first, out of `os.environ`, and **every
`app` import in this file happens inside a function** for that reason and no
other. Once the environment has been judged, the constructed `Settings` is asked
`is_development` too, which is a second belt on the same rule.

**It provisions nothing, and refuses loudly instead** (`docs/MISTAKES.md` entry
48). No person, no `user`, no section, no enrollment, no `week` and no
`survey_window`: it reads them, and exits non-zero with a plain sentence naming
what is missing. A platform that offers a launch says the platform holds the
section — never that the tool will invent it.

**It writes no `weekly_summary` and no `release_batch`.** Those are the two
things on §5.1's report that only a scheduled job can produce, so a fixture that
wrote them would be a demo agreeing with itself about its own subject. Step 6
above runs the real jobs.

**It maintains `response.is_valid` through the module that owns that column.**
Every comment gets a verdict through `app.services.validity.record_verdict`, and
every response's column is then set by
`app.services.validity.recompute_response_validity`, which is that column's one
writer (ADR 0147).

**The planted verdicts do not look floored.** ADR 0054 makes
`("character-floor", "no-model")` the pair that says §3.3's character floor
decided rather than a model, and `reclassify_floored_comments` hunts exactly that
pair on an hourly beat. A seeder writing it would watch the mock provider
overwrite its refusing verdicts within the hour. So the pair here is
`SEED_PROMPT_VERSION` and `NOT_A_MODEL`: honest, and outside the sweep's set.

**Every row it writes is one the real submit path would have accepted.** SPEC
§3.2 requires an instructor comment when the instructor rating is 2 or lower, and
a course comment when the course rating is. So a response that carries no comment
on a stream draws that stream's rating from 3 upwards. The exit story departs
from this knowingly, because its weekly means are fixed by the spec it feeds;
nothing fixes the numbers here, so there is no reason to depart.

**It is deterministic, and idempotent by natural key.** Every choice below comes
from a `random.Random` seeded from the section code and the course week, so two
runs write the same rows. A `response` is matched on `(user_id, section_id,
week_id)` — the key §8 already enforces — and an `answer` on `(response_id,
question_id)`, with any answer the plan does not describe deleted; `DELETE` on
`answer` is the one this connection holds. A `classification` is appended, which
is right rather than a compromise: the latest verdict is the one that governs.

**A response this file did not plan, in a week it did plan, is a refusal rather
than a silently wrong story** — this connection cannot delete a `response`, for
the reason `scripts/seed_exit_story.py` measures at length. Responses in weeks
outside the plan are left alone, so clearing the development clock and re-running
narrows the story rather than jamming it.
"""

from __future__ import annotations

import os
import random
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

if TYPE_CHECKING:  # pragma: no cover - annotations only; see the docstring
    from app.models.org import Section
    from app.models.survey import Answer, Response

# ---------------------------------------------------------------------------
# The section, and the people.
# ---------------------------------------------------------------------------

# `BIOL-310-R7FF`, by the §2.2 code its `section` row carries and by the label a
# person writes. E4-20 item 1 adds it to `mock-lms/app/seed.py`: start letter `R`,
# so it runs the same twelve weeks from 2026-09-07 as the exit story's section and
# one pretended clock serves both.
SECTION_CODE = "R7FF"
SECTION_LABEL = "BIOL-310-R7FF"

# The pattern the mock platform mints this section's students under, and the only
# people this file writes anything for. The shared learner and the dean are not
# members of this section by design, so neither appears here.
STUDENT_SUBJECT_PREFIX = f"mock-lms-user-{SECTION_LABEL.lower()}-student-"

# ---------------------------------------------------------------------------
# The shape of a week. The owner's parameters, ruled 2026-09-09.
# ---------------------------------------------------------------------------

# How many of the section's students answer in a week, and how many of them write
# something. Both are drawn per week, so the set rotates: 17 to 20 of twenty
# respond, and 14 to 17 of twenty — 70% to 85% — comment. Nothing asserts either
# range; they are here so a reader can see what "most of them" was decided to
# mean.
RESPONDENTS_FLOOR, RESPONDENTS_CEILING = 17, 20
COMMENTERS_FLOOR, COMMENTERS_CEILING = 14, 17

# How many of a week's responses carry a comment a classifier would refuse. Drawn
# from this bag, so most weeks carry one or two and some carry none, and the
# validity rate on the report reads a little under 100% rather than exactly at it.
REFUSED_COMMENTS_PER_WEEK = (0, 0, 1, 1, 2)

# The workload slider's range for this story, in half-hour steps: 4.0 to 14.0
# hours. §3.2's own range is 0 to 40 in half-hour steps, which is what the column
# admits; this is the part of it a three-credit course actually occupies.
WORKLOAD_LOWEST_HALF_HOURS, WORKLOAD_HIGHEST_HALF_HOURS = 8, 28

# The shape of a week's ratings, as weights over 1, 2, 3, 4, 5. Each week's own
# weights are these with an independent -1/0/+1 applied to every entry, which is
# the "mild week-to-week drift" the ruling asks for — a wobble rather than a
# story arc, since a seeder that engineered a trend would be putting a conclusion
# into demonstration data.
BASE_INSTRUCTOR_WEIGHTS = (1, 2, 6, 9, 6)
BASE_COURSE_WEIGHTS = (1, 3, 7, 8, 5)

# The lowest rating a stream may carry when the response says nothing on that
# stream. SPEC §3.2 requires the comment at 2 and below, so this is what keeps
# every row here one the real submit path would have accepted.
LOWEST_UNCOMMENTED_RATING = 3

# What a planted verdict says produced it. Neither half is a lie and neither half
# is ADR 0054's floor pair, which `reclassify_floored_comments` hunts hourly — see
# this module's docstring.
SEED_PROMPT_VERSION = "development-seed.demo-story"

# ---------------------------------------------------------------------------
# The sentences.
# ---------------------------------------------------------------------------
#
# Templates, drawn without replacement inside a week, which is what the ruling
# permits: nothing asserts a word of this. Every sentence is over §3.3's
# twenty-five character floor, holds no `|` (the separator a database read comes
# back on), names nobody, and carries no marker the mock model provider answers
# to. Each pool has to hold at least `COMMENTERS_CEILING - 1` sentences, because a
# week's commenters are split between the two streams and the split can leave all
# but one of them on either side; `refuse_an_impossible_plan` checks that rather
# than leaving it to the first week that meets it.

INSTRUCTOR_COMMENTS: tuple[str, ...] = (
    "The worked examples in class were the part that made the reading make sense.",
    "Questions after the lecture got answered properly instead of being rushed.",
    "The pace was quick this week and I lost the thread about halfway through.",
    "Office hours were busy but I still got a straight answer to my question.",
    "Feedback on the last problem set came back fast enough to be useful.",
    "The explanation of the second topic assumed a lot that we have not covered.",
    "Slides went up before class this week, which made note-taking much easier.",
    "I would have liked one more example before we were asked to try it ourselves.",
    "The demonstration was clear and I could follow every step of it live.",
    "Emails got answered the same day, which made a difference when I was stuck.",
    "The recap at the start of the session pulled the week together nicely.",
    "It was hard to hear the back half of the room during the group discussion.",
    "The pointers toward the extra reading were genuinely worth following up.",
    "I did not follow the notation change midway through and never caught up.",
    "Good balance this week between lecture and time to try things ourselves.",
    "The review before the quiz covered exactly what the quiz turned out to ask.",
    "Being asked to explain it back to a partner was more useful than I expected.",
    "The tangent in the middle was interesting but it ate most of the session.",
)

COURSE_COMMENTS: tuple[str, ...] = (
    "The lab manual matched the lecture this week and that made the work smooth.",
    "The reading was long but the ordering made it manageable across the week.",
    "Two of the practice questions had answers that disagree with the notes.",
    "The online material loaded slowly and one of the videos would not play.",
    "The weekly checklist is the thing that keeps this course organised for me.",
    "The assignment brief arrived late enough that the weekend got tight.",
    "I liked that the exercises built on each other instead of restarting.",
    "The dataset for the exercise was missing a column the instructions name.",
    "The supplementary notes filled the gap the textbook leaves in that chapter.",
    "There was more assigned this week than the schedule said there would be.",
    "The discussion board was quiet and my question sat there for three days.",
    "Splitting the long chapter across two weeks was the right call.",
    "The rubric made it obvious what a good answer was supposed to contain.",
    "The lab equipment booking filled up before most of us could get a slot.",
    "The optional practice set was the most useful thing on the page this week.",
    "The deadline on the portal and the deadline on the syllabus disagree.",
    "The examples in the course notes are close enough to the assessment to help.",
    "The video ran long and the last section was cut off before the summary.",
)

# What a comment looks like when a classifier refuses it. Deliberately under §3.3's
# twenty-five character floor and deliberately empty of content: what makes these
# invalid on the report is the *stored* verdict, and a sentence chosen to look
# insufficient is what lets a reader check that the two agree.
BRIEF_COMMENTS: tuple[str, ...] = ("ok", "fine", "n/a", "good", "none", "no comment")

# SPEC §3.2's five questions, by the position and the shape `scripts/seed.py`
# writes them under. Checked rather than assumed, because everything below picks a
# question by its ordinal and the set is versioned: a v2 that moved the workload
# slider to position 3 would otherwise be seeded with ratings in a comment column.
INSTRUCTOR_RATING, INSTRUCTOR_COMMENT, COURSE_RATING, COURSE_COMMENT, WORKLOAD = 1, 2, 3, 4, 5


class StoryRefusedError(Exception):
    """The world this story needs is not there, and this file will not invent it.

    One exception with a written-out message rather than a return code, so every
    refusal below reads as one sentence a person can act on and the caller has one
    place to print it. `docs/MISTAKES.md` entry 48 is the rule.
    """


# ---------------------------------------------------------------------------
# The plan, generated rather than written out.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedResponse:
    """One student's answers for one week, before any of it is a row.

    A response carries at most one comment, on one stream — which is what the
    ruling's "split between the instructor and course streams" comes to when each
    respondent writes at most once. `comment_is_refused` says the comment it does
    carry is one of the brief ones and that its stored verdict refuses it.
    """

    subject: str
    instructor_rating: int
    course_rating: int
    workload_hours: Decimal
    instructor_comment: str | None
    course_comment: str | None
    comment_is_refused: bool


def refuse_an_impossible_plan() -> None:
    """Refuse if the constants above cannot produce a week, before anything is read.

    First, so that an edit to this file is reported as an edit to this file rather
    than as something about the database — a comment pool one sentence too short
    surfaces as a `ValueError` out of `random.sample` in the middle of a write
    otherwise.
    """
    if COMMENTERS_CEILING > RESPONDENTS_FLOOR:
        raise StoryRefusedError(
            f"This file plans up to {COMMENTERS_CEILING} commenters in a week that may hold as few "
            f"as {RESPONDENTS_FLOOR} respondents. A commenter is one of the respondents, so the "
            "first of those numbers cannot be the larger."
        )
    shortest_pool = min(len(INSTRUCTOR_COMMENTS), len(COURSE_COMMENTS))
    if shortest_pool < COMMENTERS_CEILING - 1:
        raise StoryRefusedError(
            f"The shorter comment pool in this file holds {shortest_pool} sentences and a week can "
            f"put {COMMENTERS_CEILING - 1} of its commenters on one stream. Sentences are drawn "
            "without replacement inside a week, so a pool that short cannot fill it."
        )
    if len(BRIEF_COMMENTS) < max(REFUSED_COMMENTS_PER_WEEK):
        raise StoryRefusedError(
            f"This file holds {len(BRIEF_COMMENTS)} brief sentences and plans up to "
            f"{max(REFUSED_COMMENTS_PER_WEEK)} refused comments in a week."
        )


def _drifted(weights: Sequence[int], rng: random.Random) -> tuple[int, ...]:
    """One week's rating weights: the base shape, wobbled by one in either direction."""
    return tuple(max(1, weight + rng.randint(-1, 1)) for weight in weights)


def _a_rating(rng: random.Random, weights: Sequence[int], *, lowest: int) -> int:
    """A Likert rating drawn under `weights`, never below `lowest`.

    `lowest` is 1 for a stream this response comments on and
    `LOWEST_UNCOMMENTED_RATING` for one it does not, which is SPEC §3.2's "required
    if Q1 ≤ 2" read forwards: the rows this file writes are rows the submit path
    would have accepted.
    """
    values = range(lowest, 6)
    return rng.choices(list(values), weights=list(weights[lowest - 1 :]))[0]


def plan_one_week(course_week: int, roster: Sequence[str]) -> tuple[PlannedResponse, ...]:
    """Who answers this week, what they say, and which of them is refused.

    Seeded from the section code and the course week, so a re-run of this file
    writes the same rows and a week's plan does not move when a week beside it
    does. Every bound is taken against the roster it is given rather than against
    twenty, so a section whose class size changes is planned rather than crashed.
    """
    # S311: a seeded `random.Random` is exactly what is wanted here — nothing this
    # produces is a secret, and reproducibility is the requirement.
    rng = random.Random(f"{SECTION_LABEL}:course-week-{course_week}")  # noqa: S311

    most = min(RESPONDENTS_CEILING, len(roster))
    fewest = min(RESPONDENTS_FLOOR, most)
    respondents = rng.sample(roster, k=rng.randint(fewest, most))

    most_commenters = min(COMMENTERS_CEILING, len(respondents))
    fewest_commenters = min(COMMENTERS_FLOOR, most_commenters)
    commenters = rng.sample(respondents, k=rng.randint(fewest_commenters, most_commenters))

    # Where the week's commenters divide between the two streams. Both streams are
    # populated every week by construction, and neither takes more than two thirds
    # of them: a split drawn uniformly is uneven often enough to produce a week of
    # thirteen instructor comments against one course comment, which is not a
    # section anybody would recognise. Uneven inside those bounds is the point.
    fewest_on_a_stream = max(1, len(commenters) // 3)
    split = rng.randint(
        fewest_on_a_stream, max(fewest_on_a_stream, len(commenters) - fewest_on_a_stream)
    )
    on_the_instructor_stream = commenters[:split]
    on_the_course_stream = commenters[split:]

    said = dict(
        zip(
            on_the_instructor_stream,
            rng.sample(INSTRUCTOR_COMMENTS, k=len(on_the_instructor_stream)),
            strict=True,
        )
    )
    said.update(
        zip(
            on_the_course_stream,
            rng.sample(COURSE_COMMENTS, k=len(on_the_course_stream)),
            strict=True,
        )
    )

    refused = rng.sample(commenters, k=min(rng.choice(REFUSED_COMMENTS_PER_WEEK), len(commenters)))
    said.update(zip(refused, rng.sample(BRIEF_COMMENTS, k=len(refused)), strict=True))

    instructor_weights = _drifted(BASE_INSTRUCTOR_WEIGHTS, rng)
    course_weights = _drifted(BASE_COURSE_WEIGHTS, rng)
    speaks_to_the_instructor = set(on_the_instructor_stream)
    was_refused = set(refused)

    planned: list[PlannedResponse] = []
    for subject in sorted(respondents):
        comment = said.get(subject)
        to_the_instructor = comment is not None and subject in speaks_to_the_instructor
        to_the_course = comment is not None and subject not in speaks_to_the_instructor
        planned.append(
            PlannedResponse(
                subject=subject,
                instructor_rating=_a_rating(
                    rng,
                    instructor_weights,
                    lowest=1 if to_the_instructor else LOWEST_UNCOMMENTED_RATING,
                ),
                course_rating=_a_rating(
                    rng,
                    course_weights,
                    lowest=1 if to_the_course else LOWEST_UNCOMMENTED_RATING,
                ),
                workload_hours=Decimal(
                    rng.randrange(WORKLOAD_LOWEST_HALF_HOURS, WORKLOAD_HIGHEST_HALF_HOURS + 1)
                )
                / 2,
                instructor_comment=comment if to_the_instructor else None,
                course_comment=comment if to_the_course else None,
                comment_is_refused=subject in was_refused,
            )
        )
    return tuple(planned)


# ---------------------------------------------------------------------------
# Reading the world.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WeekOfTheSection:
    """One closed course week of this section, with the week row and window it needs."""

    course_week: int
    term_week: int
    week_id: UUID
    opens_at: datetime
    closes_at: datetime


def the_section(session: Session) -> Section:
    """The one `section` row `BIOL-310-R7FF` reached this database as."""
    from app.models.org import Section

    found = list(session.scalars(select(Section).where(Section.lms_section_code == SECTION_CODE)))
    if len(found) != 1:
        raise StoryRefusedError(
            f"{SECTION_LABEL} matches {len(found)} section row(s) on `lms_section_code = "
            f"{SECTION_CODE!r}`, and this story needs exactly one. Zero means no staff launch has "
            f"provisioned {SECTION_LABEL} yet — a launch is what provisions a section (SPEC §7.3), "
            "and this file creates none. Launch the placement the mock platform publishes as "
            f"{SECTION_LABEL}, as the instructor persona, at the real clock. More than one means "
            "two courses in this term carry the same §2.2 code, which is a seed defect rather "
            "than something to choose between."
        )
    return found[0]


def the_closed_weeks(
    session: Session, section: Section, *, effective_now: datetime
) -> tuple[WeekOfTheSection, ...]:
    """Every course week of this section whose survey window has closed, in order.

    **Derived from the stored rows and never from a count.** The windows are a
    scheduled job's output (ADR 0111) and the effective clock decides which have
    closed; a file that knew how many weeks this section has would be a second copy
    of the calendar (`docs/MISTAKES.md` entry 19).

    The course-to-term translation is `app.services.section_codes.week_of_the_term`
    applied to week 1 and then counted forward, which is exactly what
    `app.services.reporting._section_weeks` does with the same rows. Closed is
    `closes_at < now`, which is that module's comparison too — a window is open
    when `opens_at <= t <= closes_at`, both ends inclusive.
    """
    from app.models.term import SurveyWindow, Term, Week
    from app.services.section_codes import week_of_the_term

    term = session.get(Term, section.term_id)
    if term is None:  # pragma: no cover - `section.term_id` is a non-null foreign key
        raise StoryRefusedError(f"{SECTION_LABEL} names a term that holds no row.")

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
        raise StoryRefusedError(
            f"{SECTION_LABEL} holds no `survey_window` row at all. A section provisioned by a "
            "launch has none until `app.jobs.tasks.derive_survey_windows` runs (ADR 0111), which "
            "is a scheduled job and is step 3 of the drive in this file's docstring. This file "
            "creates no window and no week."
        )

    closed = tuple(
        WeekOfTheSection(
            course_week=number - first_term_week + 1,
            term_week=number,
            week_id=week_id,
            opens_at=opens_at,
            closes_at=closes_at,
        )
        for number, week_id, opens_at, closes_at in rows
        if closes_at < effective_now
    )
    if not closed:
        raise StoryRefusedError(
            f"None of {SECTION_LABEL}'s {len(rows)} survey windows has closed at the effective "
            f"clock, which is {effective_now.isoformat()}. This file writes a response for every "
            "closed week and there is nothing for it to write. Move the development clock forward "
            "first — the `/dev` console's clock control, ADR 0109 — to a point past the close of "
            "the weeks the story should cover, and then pipe this file again. That is step 4 of "
            "the drive in this file's docstring, and it comes before this one."
        )
    return closed


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
        raise StoryRefusedError(
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
            raise StoryRefusedError(
                f"Question {position} of the question set in force is {found!r}, and this story is "
                f"written for a {kind.value} question on the {stream!r} stream. Everything here "
                "picks a question by its ordinal and §3.2's set is versioned, so a set that has "
                "moved its questions would be seeded with a rating in a comment column. Re-run "
                "`make seed`, or correct this file against the set that is in force."
            )
    return {position: asked[position][0] for position in expected}


def the_roster(session: Session, section: Section) -> dict[str, UUID]:
    """This section's students' `user` rows, found through their enrollments.

    **The subject is resolved forward and never read off the row.** `pulse_app`
    holds `SELECT` on `user.id` alone — E1-10's security round revoked
    `SELECT (lms_user_id)`, because a connection that can read it can enumerate
    every subject that ever launched — so the walk is over this section's
    enrollments, asking `app.services.identity.subject_for_user` for each, which is
    ADR 0139's sanctioned definer door.

    Refuses rather than enrolls (`docs/MISTAKES.md` entry 48): the roster sync is
    what writes an enrollment (SPEC §7.3), and a seeder that wrote one would make
    "this fixture reached the product's own database" unfalsifiable. What it
    refuses is an *empty* roster rather than a short one — the mock platform's
    class size is that file's business and not this one's, and a section whose
    sync has not run holds nobody at all.
    """
    from app.models.identity import Enrollment
    from app.services.identity import subject_for_user

    found: dict[str, UUID] = {}
    for user_id in session.scalars(
        select(Enrollment.user_id).where(Enrollment.section_id == section.id)
    ):
        subject = subject_for_user(session, user_id)
        if subject is not None and subject.startswith(STUDENT_SUBJECT_PREFIX):
            found[subject] = user_id
    if not found:
        raise StoryRefusedError(
            f"{SECTION_LABEL} holds no enrollment for any student whose subject begins "
            f"{STUDENT_SUBJECT_PREFIX!r}. The roster sync is what enrols them (SPEC §7.3), so this "
            "is the worker not running, the mock platform not serving its roster, or the staff "
            "launch not having stored the section's roster address. This file creates no user and "
            "no enrollment."
        )
    return found


def refuse_a_foreign_response(
    session: Session,
    section: Section,
    plan: Mapping[int, tuple[PlannedResponse, ...]],
    weeks: Sequence[WeekOfTheSection],
    roster: Mapping[str, UUID],
) -> None:
    """Refuse if a week this file writes holds a response this file did not plan.

    This connection holds no `DELETE` on `response` — `pulse_app` has one on
    `answer` and on nothing else here, and the `api` container deliberately holds
    no superuser credential — so a leftover row cannot be cleared and must not be
    written around either: it would make a week's response count disagree with
    everything else about that week.

    **Only the weeks being written are examined.** A response in a week outside the
    plan belongs to a run made at a further-forward clock, and refusing over it
    would mean that clearing the development clock left this file unable to run at
    all.
    """
    from app.models.survey import Response

    planned = {
        (roster[response.subject], week.week_id)
        for week in weeks
        for response in plan[week.course_week]
    }
    written_weeks = {week.week_id for week in weeks}
    foreign = [
        (user_id, week_id)
        for user_id, week_id in session.execute(
            select(Response.user_id, Response.week_id).where(Response.section_id == section.id)
        )
        if week_id in written_weeks and (user_id, week_id) not in planned
    ]
    if foreign:
        raise StoryRefusedError(
            f"{SECTION_LABEL} holds {len(foreign)} response row(s) in the weeks this story writes "
            "that the story does not describe, and this connection holds no `DELETE` on `response` "
            "to clear them with. Left in place they would make a week's response count disagree "
            "with the rest of that week. Clear the section first — `clearTheWeek` in "
            "`tests/e2e/support/survey.ts` is that statement, run through the `db` container's own "
            "superuser."
        )


# ---------------------------------------------------------------------------
# Writing the story.
# ---------------------------------------------------------------------------


@dataclass
class Written:
    """What one run wrote, for the line it prints at the end."""

    responses: int = 0
    answers: int = 0
    comments: int = 0
    invalid: int = 0


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
            # Set here so the row is insertable — the column is `NOT NULL` with no
            # server default on purpose — and then decided by
            # `recompute_response_validity` once its comment carries a verdict.
            is_valid=True,
        )
        session.add(response)
    else:
        response.first_submitted_at = submitted_at
        response.last_submitted_at = submitted_at
    session.flush()
    return response


def one_answer(
    session: Session,
    *,
    response: Response,
    question_id: UUID,
    rating: int | None = None,
    comment_text: str | None = None,
    workload_hours: Decimal | None = None,
) -> Answer:
    """One answer of one response, matched on `(response_id, question_id)` or inserted.

    All three value columns are set on every write, not only the one that carries a
    value, because `answer`'s own CHECK is `num_nonnulls(...) = 1`: a row rewritten
    from a rating to a comment has to lose the rating in the same statement.
    """
    from app.models.survey import Answer

    answer = session.scalars(
        select(Answer).where(Answer.response_id == response.id, Answer.question_id == question_id)
    ).one_or_none()
    if answer is None:
        answer = Answer(response_id=response.id, question_id=question_id)
        session.add(answer)
    answer.rating = rating
    answer.comment_text = comment_text
    answer.workload_hours = workload_hours
    session.flush()
    return answer


def _submitted_at(week: WeekOfTheSection, subject: str) -> datetime:
    """When this student answered: some moment inside this week's own window.

    Copied off the stored window rather than computed, for ADR 0142's reason — the
    windows are derived from the calendar and stored, and the effective clock
    decides only which have closed. Nothing on the report or in either Monday job
    compares a response's timestamp to anything, so all this has to be is coherent:
    a response submitted inside the week it is about.
    """
    span = int((week.closes_at - week.opens_at).total_seconds())
    # S311: seeded on purpose, and nothing here is a secret. See `plan_one_week`.
    rng = random.Random(f"{SECTION_LABEL}:{week.course_week}:{subject}")  # noqa: S311
    return week.opens_at + timedelta(seconds=rng.randrange(max(span, 1)))


def write_the_story(session: Session, *, effective_now: datetime) -> Written:
    """Write a week's answers for every closed week of `BIOL-310-R7FF`."""
    from app.ai.contracts import CommentValidityOutput, ValidityVerdict
    from app.ai.gateway import NOT_A_MODEL
    from app.models.survey import Answer
    from app.services.validity import recompute_response_validity, record_verdict

    refuse_an_impossible_plan()
    section = the_section(session)
    weeks = the_closed_weeks(session, section, effective_now=effective_now)
    questions = the_instrument(session)
    roster = the_roster(session, section)

    subjects = sorted(roster)
    plan = {week.course_week: plan_one_week(week.course_week, subjects) for week in weeks}
    refuse_a_foreign_response(session, section, plan, weeks, roster)

    written = Written()
    for week in weeks:
        for planned in plan[week.course_week]:
            response = one_response(
                session,
                section=section,
                week=week,
                user_id=roster[planned.subject],
                submitted_at=_submitted_at(week, planned.subject),
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

            comments = {
                questions[INSTRUCTOR_COMMENT]: planned.instructor_comment,
                questions[COURSE_COMMENT]: planned.course_comment,
            }
            for question_id, text in comments.items():
                if text is None:
                    continue
                answer = one_answer(
                    session, response=response, question_id=question_id, comment_text=text
                )
                written.answers += 1
                written.comments += 1
                record_verdict(
                    session,
                    CommentValidityOutput(
                        verdict=(
                            ValidityVerdict.INSUFFICIENT
                            if planned.comment_is_refused
                            else ValidityVerdict.SUBSTANTIVE
                        ),
                        prompt_version=SEED_PROMPT_VERSION,
                        model_id=NOT_A_MODEL,
                    ),
                    answer_id=answer.id,
                )

            # Every answer of this response the plan does not describe, removed.
            # The one `DELETE` this connection holds, and what makes a re-run over
            # an edited plan a re-seed rather than a merge. It reaches a rating or
            # a workload figure and not a comment something else already
            # references: `classification`, `moderation_state` and
            # `release_batch_member` all reference `answer` with `RESTRICT`, so a
            # withdrawn comment somebody holds a verdict for is a foreign-key
            # refusal naming the table that holds it, which is the honest answer.
            planned_questions = {
                questions[INSTRUCTOR_RATING],
                questions[COURSE_RATING],
                questions[WORKLOAD],
                *(question_id for question_id, text in comments.items() if text is not None),
            }
            for stale in session.scalars(
                select(Answer).where(
                    Answer.response_id == response.id,
                    Answer.question_id.not_in(planned_questions),
                )
            ):
                session.delete(stale)
            session.flush()

            # SPEC §3.3's verdict about the whole submission, set by the one module
            # that owns the column (ADR 0147). Not `False` written by hand: what
            # `report_response_counts.valid_responses` counts is this column as
            # `app.services.validity` maintains it.
            if not recompute_response_validity(session, response):
                written.invalid += 1

    return written


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

    **Exactly, and `scripts/seed.py` strips surrounding whitespace where this does
    not.** That difference is deliberate: `main` below asks
    `app.config.is_development` of the validated `Settings` as well, and that
    predicate compares exactly — so a guard here that admitted `' development '`
    would admit a value the belt then refuses, and the two halves of one rule would
    disagree. The seed script has no such second half.

    A predicate over a mapping rather than a check against `os.environ`, so that
    what this does is a question about a value.
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
    # **This sentence deliberately does not name the section.** The two refusals
    # this file owes are told apart by what they say — the module test reads the
    # environment one for `ENVIRONMENT` or for the value it found, and the section
    # one for `BIOL-310-R7FF`. A refusal about the environment that also named the
    # section would satisfy both matchers, and a guard inverted to refuse
    # development would then pass the test written to catch exactly that
    # (`docs/MISTAKES.md` entry 3). Measured rather than imagined: the section was
    # in this sentence, both tests went green, and the section test proved nothing.
    return (
        f"seed_demo_story refuses to run with {ENVIRONMENT_VARIABLE}={found}. It runs only where "
        f"{ENVIRONMENT_VARIABLE} is {DEVELOPMENT_ENVIRONMENT!r}. This file writes a term of "
        "invented survey responses and comments for one section of the mock platform's world into "
        "whatever database it is pointed at, and there is no environment other than a developer's "
        "own where that is the right thing to do. See "
        "docs/adr/0063-the-demo-seed-runs-only-in-a-development-environment.md."
    )


def main() -> int:
    """Judge the environment, write the story, and say in one line what it wrote."""
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
    from app.services import clock

    settings = Settings()
    if not is_development(settings):
        # **The same rule asked of the validated field, and it is not expected ever
        # to fire.** The raw check above reads the variable pydantic reads, and the
        # process environment beats `.env`, so the two agree wherever this is run
        # the way its docstring says. It is here because what the rest of this file
        # does is keyed on the *validated* field rather than on the raw one — the
        # development clock most of all (ADR 0109), which answers real time on a
        # `Settings` that is not development's and would quietly make "every closed
        # week" a different set of weeks. An agreement check, stated as one.
        print(
            "seed_demo_story refuses to run: the raw "
            f"{ENVIRONMENT_VARIABLE} admitted this run, and the configuration this process then "
            f"validated names {ENVIRONMENT_VARIABLE}={settings.environment!r}, which "
            "`app.config.is_development` does not admit. Those two disagreeing is the thing this "
            "check exists for; look at what the process environment sets against what `.env` sets.",
            file=sys.stderr,
        )
        return 1

    with SessionLocal() as session:
        try:
            effective_now = clock.now(session, settings=settings)
            written = write_the_story(session, effective_now=effective_now)
        except StoryRefusedError as refused:
            session.rollback()
            print(f"seed_demo_story refused: {refused}", file=sys.stderr)
            return 1
        session.commit()

    print(
        f"seed_demo_story wrote {SECTION_LABEL}: {written.responses} responses, "
        f"{written.answers} answers and {written.comments} comment verdicts; "
        f"{written.invalid} response(s) left invalid. No weekly_summary and no release_batch: "
        "those are the two Monday jobs'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
