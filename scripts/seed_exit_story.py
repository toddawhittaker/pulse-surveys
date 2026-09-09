"""E4-15's diverging two-stream story for `BIOL-215-R3WW`, written into a development stack.

SPEC §14.3's exit line for E4 is "an instructor opens a real Monday report for a
seeded section with a **diverging two-stream story**" — a section whose instructor
stream trends up across six published weeks while its course stream trends down,
with a quiet week whose comments §4 conceals and a second quiet week that together
with the first crosses §4's cumulative release threshold. Nothing in
`scripts/seed.py` contains such a section, and `tests/e2e/exit-instructor-report.spec.ts`
is written against one. This file is that world's raw material and nothing else.

**How it is run, and why it is shaped this way.** The spec pipes this file's own
text into `docker compose exec -T api python -` (`tests/e2e/support/stack.ts`'s
`seedTheExitStory`), which is the currency that suite already uses for a job and
for a SQL statement. `scripts/` is not in the `api` image — `backend/Dockerfile`
copies the application and `docker-compose.yml` mounts only `scripts/db-init` — so
this file cannot import `scripts/seed.py` and does not try to. It imports `app.*`
and the standard library, plus SQLAlchemy, which it reaches the way every module
under `app/` reaches it because it is that image's own dependency.

**It takes no arguments.** The story is one section's, and a section name, a week
or a respondent spelled on a command line would be a second copy of the plan the
spec already holds.

**It refuses to run outside a development environment, before it reads anything.**
ADR 0063's rule and `scripts/seed.py`'s `check_environment_is_development` in a
smaller shape: an equality against the one name that is safe, asked of the
application's own `Settings` through `app.config.is_development` — which is the
same predicate the developer console and the SQL echo key on — rather than of a
raw mapping, because this process is the application's own and has a `Settings`.

**It provisions nothing, and refuses loudly instead** (`docs/MISTAKES.md` entry
48). A platform that offers a launch says the platform holds the section, never
that the tool has provisioned it. So this file creates no section, no person, no
`user`, no enrollment, no `week` and no `survey_window`: it reads them, and exits
non-zero with a plain sentence naming what is missing when any of them is. The
staff launch, the window derivation and the roster sync are the spec's job, done
before this runs.

**It writes no `weekly_summary` and no `release_batch`.** Those two are the only
things on §5.1's report that nothing but a scheduled job can produce, so a fixture
that wrote them would be a drive agreeing with itself about its own subject
(`docs/MISTAKES.md` entry 30). `generate_weekly_summaries` and
`cut_release_batches` run after this, from the spec, as themselves.

**It maintains `response.is_valid` through the one module that owns that column.**
`report_response_counts.valid_responses` is `response.is_valid` and never
`classification` (ADR 0147: the verdict table is append-only, so "the current
verdict" is an ordering question an aggregate cannot ask). A seeder that appended
a refusing verdict and stopped would leave a week whose stored verdict refuses a
comment reading a validity rate of 1.0. So every comment gets a verdict row
through `app.services.validity.record_verdict` and every response's column is then
set by `app.services.validity.recompute_response_validity`, which is that column's
one writer.

**The planted verdicts do not look floored, deliberately.** ADR 0054 makes
`(prompt_version, model_id) == ("character-floor", "no-model")` the pair that says
§3.3's character floor decided rather than a model, and
`app.services.validity.reclassify_floored_comments` finds exactly that pair on an
hourly beat and asks a provider again. A seeder that wrote the floor's pair would
watch the mock provider overwrite its refusing verdict within the hour and the
week's validity rate climb back to 1.0. So the pair written here is
`SEED_PROMPT_VERSION` and `NOT_A_MODEL`: honest — no prompt file and no model
produced these — and outside the sweep's set.

**Idempotency, and the one thing it cannot do.** The work order asked for a
seeder that clears its own ground first, in foreign-key order down to `response`.
Measured on the stack, the connection this process runs on cannot: `pulse_app`
holds `DELETE` on `answer` and on nothing else this file touches, and the `api`
container deliberately holds no superuser credential (`docker-compose.yml`'s
application-environment anchor blanks `DB_SUPERUSER` and its password in as many
words — "No application container may hold it"), so the bootstrap-superuser route
`scripts/seed.py` takes does not exist here. Widening the grant is not a repair:
it is a permanent widening of the connection every screen in the product runs on,
for a development fixture.

So this file is idempotent the way `scripts/seed.py` is — by matching natural
keys — and loud where it cannot be:

  * a `response` is matched on `(user_id, section_id, week_id)`, the key §8 already
    enforces, and its columns are set to what the plan says;
  * an `answer` is matched on `(response_id, question_id)`, and any answer of a
    story response that the plan does not describe is **deleted** — the one
    `DELETE` this connection holds, and what lets a re-run change a rating or drop
    a comment;
  * a `classification` is **appended**, which is right rather than a compromise:
    `_latest_verdicts` orders by `classified_at` and then by the key, so a re-run's
    verdict is the one that governs;
  * and a response this section holds that the plan does **not** describe is a
    refusal, not a silent wrong story. `tests/e2e/instructor-report.spec.ts` clears
    its own week in an `afterAll`, so the ordinary state of this section when this
    runs is empty; a leftover row means that hook did not finish, and the repair is
    `clearTheWeek`, named in the message.

**One departure from SPEC §3.2 is knowingly in these rows and is written here
rather than left to be discovered.** §3.2 makes the instructor comment required
when the instructor rating is 2 or lower, and the plan's week 1 instructor mean is
2.0 over eight responses — which is unreachable with integer ratings unless several
of them are 2 or lower. The plan puts one comment per stream in that week, so some
of its responses carry a low rating and no comment: rows the real submit path
(`app.services.submissions`) would have refused. Nothing E4 reads asks that
question — the report's distributions, rates, workload and comments do not — and
the alternative was either abandoning the fixed weekly means the spec asserts, or
writing eight instructor comments into week 1, which would make that week's comment
count equal its response count and quietly weaken the spec's own assertion that a
summary states responses rather than comments.
"""

import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.contracts import CommentValidityOutput, ValidityVerdict
from app.ai.gateway import NOT_A_MODEL
from app.config import Settings, is_development
from app.db import SessionLocal
from app.models.identity import Enrollment
from app.models.org import Section
from app.models.survey import (
    REPORT_STREAMS,
    Answer,
    Question,
    QuestionKind,
    QuestionSet,
    Response,
)
from app.models.term import SurveyWindow, Term, Week
from app.services.identity import subject_for_user
from app.services.section_codes import week_of_the_term
from app.services.validity import recompute_response_validity, record_verdict

# ---------------------------------------------------------------------------
# The section, and the people.
# ---------------------------------------------------------------------------

# `BIOL-215-R3WW`, by the §2.2 code the `section` row carries. The choice is E4-15's
# work order decision 1 and it is measured rather than preferred: the mock
# platform's three contexts are the only launchable sections, `NURS-8100-Q2FF`
# collides with the two student-survey specs, `MATH-140-E1FF` loses its learner to
# the E3 exit drive's roster drop, and this one receives no runtime roster
# amendment from any spec.
SECTION_CODE = "R3WW"
SECTION_LABEL = "BIOL-215-R3WW"

# The subject `mock-lms/app/seed.py` mints for the shared learner, and the pattern
# it mints a per-section student under.
LEARNER = "mock-lms-user-learner"


def student(ordinal: int) -> str:
    """One of `BIOL-215-R3WW`'s per-section students, by the `sub` the platform sends."""
    return f"mock-lms-user-{SECTION_LABEL.lower()}-student-{ordinal:02d}"


# **The nine stable day-one members, and the two this story never uses.**
# `mock-lms/app/seed.py::with_the_add_and_the_drop` makes ordinal 4 a late add
# dated inside course week 4 and ordinal 7 a member the platform already reports
# departed — whom Pulse never enrolls at all (ADR 0095). A respondent on either
# would rest this story on E0-28's enrollment edge cases, which are the E3 exit's
# subject and not this one's.
POOL = (
    LEARNER,
    student(1),
    student(2),
    student(3),
    student(5),
    student(6),
    student(8),
    student(9),
    student(10),
)

# The eight who answer every week at or above §4's threshold: the pool less
# student 10, who is enrolled and answers nothing. Eight of the section's ten live
# members, which is the 8 / 10 response rate the spec computes by hand.
THE_EIGHT = POOL[:8]

# The two quiet weeks' respondents, and **they share nobody**. Four and three, both
# under a threshold of five, so the comments they hold carry seven distinct authors
# across two distinct closed under-threshold weeks — which is what opens all three
# legs of ADR 0152's release gate at once. An overlapping pair would fail leg (b)
# with the same two weeks and the same seven comments.
QUIET_WEEK_THREE = (student(1), student(2), student(3), student(5))
QUIET_WEEK_FOUR = (student(6), student(8), student(9))

# ---------------------------------------------------------------------------
# The sentences.
# ---------------------------------------------------------------------------
#
# **The seven held ones and the two of week 6 are a contract**, transcribed from
# `tests/e2e/exit-instructor-report.spec.ts`, which asserts that the seven are
# withheld from one week's response body and then carried by another week's
# release, and that week 6's two are on the page. A seeder that wrote different
# words would make that spec red naming a mismatch rather than quietly weaker.
#
# Every sentence here is comfortably over SPEC §3.3's twenty-five character floor,
# carries no marker the mock model provider answers to, and holds no `|` — the
# column separator the spec's own database reads come back on. Each is distinct
# inside its first forty characters, because the absence check compares
# forty-character prefixes.

# The four course-stream comments of quiet week 3.
HELD_IN_WEEK_THREE = (
    "Exit story alpha: the shared lab bench rota left two of us without a slot.",
    "Exit story bravo: the second reading assumed a module I have not taken yet.",
    "Exit story charlie: the recording cut out about twenty minutes into the session.",
    "Exit story delta: nobody replied on the message board and the pair task stalled.",
)

# The three course-stream comments of quiet week 4.
HELD_IN_WEEK_FOUR = (
    "Exit story echo: the worked example arrived after the exercise was already due.",
    "Exit story foxtrot: the reading list was long and the ordering made it workable.",
    "Exit story golf: two slides disagreed about which deadline actually applies.",
)

# One comment per stream in each of the four weeks at or above the threshold. Weeks
# 1, 2 and 5's sentences are this file's own — no test asserts them — and week 6's
# two are the spec's literals.
WEEK_ONE_INSTRUCTOR_COMMENT = (
    "Exit story week one instructor: the lecture pace left me behind from the start."
)
WEEK_ONE_COURSE_COMMENT = (
    "Exit story week one course: the opening module was clear and the reading was short."
)
WEEK_TWO_INSTRUCTOR_COMMENT = (
    "Exit story week two instructor: questions after class were answered in a hurry."
)
WEEK_TWO_COURSE_COMMENT = (
    "Exit story week two course: the lab manual matched the lecture and that helped."
)
WEEK_FIVE_INSTRUCTOR_COMMENT = (
    "Exit story week five instructor: the feedback on the midterm arrived quickly."
)
WEEK_SIX_INSTRUCTOR_COMMENT = (
    "Exit story week six instructor: office hours ran long and nobody was turned away."
)
WEEK_SIX_COURSE_COMMENT = (
    "Exit story week six course: the final project brief arrived far too late to plan."
)

# **The one comment whose stored verdict refuses it**, in week 5's course stream.
# Its words are as substantive as every other sentence here on purpose: the verdict
# is planted rather than asked of the classifier, so what the validity rate is a
# statement about is the *stored* verdict, and a sentence chosen to look
# insufficient would let a reader believe the rate came from the words.
WEEK_FIVE_REFUSED_COMMENT = (
    "Exit story week five course: the assessment weighting still is not clear to me."
)

# What a planted verdict says produced it. Neither half is a lie and neither half is
# ADR 0054's floor pair, which `app.services.validity.reclassify_floored_comments`
# hunts on an hourly beat — see this module's docstring.
SEED_PROMPT_VERSION = "development-seed.exit-story"

# ---------------------------------------------------------------------------
# The plan.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StoryWeek:
    """One course week of the story, as the rows it becomes.

    `instructor_ratings`, `course_ratings` and `workload_hours` are positional
    against `respondents`, so a week whose lists are not all the same length is a
    plan this file refuses to write rather than one it writes short.

    `instructor_comments` and `course_comments` are keyed by a respondent's
    position in `respondents`, because who says what inside a week is this file's
    business and the spec fixes only the counts and the sentences.
    """

    course_week: int
    respondents: tuple[str, ...]
    instructor_ratings: tuple[int, ...]
    course_ratings: tuple[int, ...]
    workload_hours: tuple[str, ...]
    instructor_comments: Mapping[int, str] = field(default_factory=dict)
    course_comments: Mapping[int, str] = field(default_factory=dict)


# **The plan, transcribed from E4-15's work order decision 5**, whose two rating
# sums per week are what makes this file and the spec agree without either reading
# the other. Every sum is written out beside its list:
#
#   week 1  instructor 1+1+2+2+2+2+3+3 = 16 over 8 = 2.0
#           course     5+5+5+5+4+4+4+4 = 36 over 8 = 4.5
#   week 2  instructor 1+2+2+2+3+3+3+4 = 20 over 8 = 2.5
#           course     5+5+4+4+4+4+4+4 = 34 over 8 = 4.25
#   week 3  instructor 2+3+3+4         = 12 over 4 = 3.0
#           course     3+3+4+4         = 14 over 4 = 3.5
#   week 4  instructor 3+3+4           = 10 over 3 = 3.333…
#           course     3+3+3           =  9 over 3 = 3.0
#   week 5  instructor 3+4+4+4+4+4+4+5 = 32 over 8 = 4.0
#           course     1+2+2+3+3+3+3+3 = 20 over 8 = 2.5
#   week 6  instructor 4+4+4+4+5+5+5+5 = 36 over 8 = 4.5
#           course     1+2+2+2+2+2+2+3 = 16 over 8 = 2.0
#
# The instructor stream rises strictly and the course stream falls strictly, which
# is the divergence §14.3's exit clause asks for. Week 6's workload values — 6, 7,
# 8, 9, 10, 11, 12 and 20 — sum to 83, so their mean is 10.375 and their median is
# (9 + 10) / 2 = 9.5: two different numbers, so a payload serving one in the other's
# place is red rather than plausible. Every value is inside §3.2's 0-to-40 range in
# half-hour steps.
STORY: tuple[StoryWeek, ...] = (
    StoryWeek(
        course_week=1,
        respondents=THE_EIGHT,
        instructor_ratings=(1, 1, 2, 2, 2, 2, 3, 3),
        course_ratings=(5, 5, 5, 5, 4, 4, 4, 4),
        workload_hours=("4", "5", "6", "7", "8", "9", "10", "18"),
        instructor_comments={0: WEEK_ONE_INSTRUCTOR_COMMENT},
        course_comments={0: WEEK_ONE_COURSE_COMMENT},
    ),
    StoryWeek(
        course_week=2,
        respondents=THE_EIGHT,
        instructor_ratings=(1, 2, 2, 2, 3, 3, 3, 4),
        course_ratings=(5, 5, 4, 4, 4, 4, 4, 4),
        workload_hours=("5", "6", "7", "8", "9", "10", "11", "19"),
        instructor_comments={0: WEEK_TWO_INSTRUCTOR_COMMENT},
        course_comments={0: WEEK_TWO_COURSE_COMMENT},
    ),
    StoryWeek(
        course_week=3,
        respondents=QUIET_WEEK_THREE,
        instructor_ratings=(2, 3, 3, 4),
        course_ratings=(3, 3, 4, 4),
        workload_hours=("6", "7", "8", "14"),
        # Every respondent of a quiet week leaves one course-stream comment, so the
        # held set carries as many distinct authors as it has comments — which is
        # leg (b) of ADR 0152's gate.
        course_comments=dict(enumerate(HELD_IN_WEEK_THREE)),
    ),
    StoryWeek(
        course_week=4,
        respondents=QUIET_WEEK_FOUR,
        instructor_ratings=(3, 3, 4),
        course_ratings=(3, 3, 3),
        workload_hours=("7", "8", "15"),
        course_comments=dict(enumerate(HELD_IN_WEEK_FOUR)),
    ),
    StoryWeek(
        course_week=5,
        respondents=THE_EIGHT,
        instructor_ratings=(3, 4, 4, 4, 4, 4, 4, 5),
        course_ratings=(1, 2, 2, 3, 3, 3, 3, 3),
        workload_hours=("5", "6", "7", "8", "9", "10", "11", "20"),
        # The first respondent carries both of this week's comments, and the course
        # one is the refused sentence — so exactly one of the week's eight responses
        # is invalid and the validity rate is 7 / 8.
        instructor_comments={0: WEEK_FIVE_INSTRUCTOR_COMMENT},
        course_comments={0: WEEK_FIVE_REFUSED_COMMENT},
    ),
    StoryWeek(
        course_week=6,
        respondents=THE_EIGHT,
        instructor_ratings=(4, 4, 4, 4, 5, 5, 5, 5),
        course_ratings=(1, 2, 2, 2, 2, 2, 2, 3),
        workload_hours=("6", "7", "8", "9", "10", "11", "12", "20"),
        instructor_comments={0: WEEK_SIX_INSTRUCTOR_COMMENT},
        course_comments={0: WEEK_SIX_COURSE_COMMENT},
    ),
)

# Which comments a planted verdict refuses. One, so that the validity rate of one
# week is observably below 1 while the week beside it is exactly 1 — the pair is
# what tells a real rate from a hard-coded, inverted or enrolment-denominated one.
REFUSED_COMMENTS = frozenset({WEEK_FIVE_REFUSED_COMMENT})

# SPEC §3.2's five questions, by the position and the shape `scripts/seed.py`
# writes them under. Asserted rather than assumed, because everything below picks a
# question by its ordinal and the set is versioned: a v2 that moved the workload
# slider to position 3 would otherwise be seeded with ratings in a comment column.
INSTRUCTOR_RATING, INSTRUCTOR_COMMENT, COURSE_RATING, COURSE_COMMENT, WORKLOAD = 1, 2, 3, 4, 5

# SPEC §5.1's two report groups, unpacked from the one declaration of them in
# `app.models.survey` rather than spelled again here — `scripts/seed.py` unpacks
# the same tuple for the same reason (`docs/MISTAKES.md` entry 13).
INSTRUCTOR_STREAM, COURSE_STREAM = REPORT_STREAMS

EXPECTED_INSTRUMENT: Mapping[int, tuple[QuestionKind, str | None]] = {
    INSTRUCTOR_RATING: (QuestionKind.LIKERT, INSTRUCTOR_STREAM),
    INSTRUCTOR_COMMENT: (QuestionKind.COMMENT, INSTRUCTOR_STREAM),
    COURSE_RATING: (QuestionKind.LIKERT, COURSE_STREAM),
    COURSE_COMMENT: (QuestionKind.COMMENT, COURSE_STREAM),
    WORKLOAD: (QuestionKind.WORKLOAD, None),
}


class StoryRefusedError(Exception):
    """The world this story needs is not there, and this file will not invent it.

    Carried as one exception with a written-out message rather than as a return
    code, so that every refusal below reads as one sentence a person can act on and
    the caller has one place to print it. `docs/MISTAKES.md` entry 48 is the rule:
    the fixture has to reach the product's own database, and a seeder that
    provisioned what it found missing would make that unfalsifiable.
    """


# ---------------------------------------------------------------------------
# Reading the world.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WeekOfTheSection:
    """One course week of this section, with the week row and window it needs."""

    course_week: int
    term_week: int
    week_id: UUID
    submitted_at: datetime


def the_section(session: Session) -> Section:
    """The one `section` row `BIOL-215-R3WW` reached this database as."""
    found = list(session.scalars(select(Section).where(Section.lms_section_code == SECTION_CODE)))
    if len(found) != 1:
        raise StoryRefusedError(
            f"{SECTION_LABEL} matches {len(found)} section row(s) on `lms_section_code = "
            f"{SECTION_CODE!r}`, and this story needs exactly one. Zero means no staff launch has "
            "provisioned the section yet — a launch is what provisions it (SPEC §7.3), and this "
            "file creates no section. More than one means two courses in this term carry the same "
            "§2.2 code, which is a seed defect rather than something to choose between."
        )
    return found[0]


def the_weeks(session: Session, section: Section) -> tuple[WeekOfTheSection, ...]:
    """Course weeks 1 to 6 of this section, on both of §2.2's axes, with their windows.

    The course-to-term translation is `app.services.section_codes.week_of_the_term`,
    which is this codebase's one reading of §2.2's two axes — the same function
    `app.services.reporting._section_weeks` translates with. A second copy of the
    arithmetic here is how a fixture and a report come to disagree about which week
    a response is in (`docs/MISTAKES.md` entry 19).

    **The submission instants are the window's own opening**, copied off the stored
    row rather than computed. ADR 0142: the windows are derived from the calendar and
    stored, and the effective clock decides only which have closed. Nothing on the
    report or in either Monday job compares a response's timestamp to anything, so
    the only thing these two columns have to be is coherent — a response submitted
    inside the week it is about — and the window is where that instant already is.
    """
    term = session.get(Term, section.term_id)
    if term is None:  # pragma: no cover - `section.term_id` is a non-null foreign key
        raise StoryRefusedError(f"{SECTION_LABEL} names a term that holds no row.")

    weeks: list[WeekOfTheSection] = []
    for week in STORY:
        term_week = week_of_the_term(
            week.course_week, section_start=section.start_date, term_start=term.start_date
        )
        week_id = session.scalars(
            select(Week.id).where(Week.term_id == term.id, Week.number == term_week)
        ).one_or_none()
        if week_id is None:
            raise StoryRefusedError(
                f"Course week {week.course_week} of {SECTION_LABEL} is term week {term_week}, and "
                "this term holds no `week` row numbered that. The term axis is seeded by "
                "`scripts/seed.py`; this file creates no week."
            )
        window = session.execute(
            select(SurveyWindow.opens_at).where(
                SurveyWindow.section_id == section.id, SurveyWindow.week_id == week_id
            )
        ).one_or_none()
        if window is None:
            raise StoryRefusedError(
                f"Course week {week.course_week} (term week {term_week}) of {SECTION_LABEL} has no "
                "`survey_window` row. A section provisioned by a launch has none until "
                "`app.jobs.tasks.derive_survey_windows` runs (ADR 0111), which the exit drive runs "
                "before it calls this file; this file creates no window."
            )
        weeks.append(
            WeekOfTheSection(
                course_week=week.course_week,
                term_week=term_week,
                week_id=week_id,
                submitted_at=window[0],
            )
        )
    return tuple(weeks)


def the_instrument(session: Session) -> dict[int, UUID]:
    """SPEC §3.2's five questions of the set in force, by position, shape-checked."""
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
    for position, (kind, stream) in EXPECTED_INSTRUMENT.items():
        found = asked.get(position)
        if found is None or found[1] != kind or found[2] != stream:
            raise StoryRefusedError(
                f"Question {position} of the question set in force is {found!r}, and this story is "
                f"written for a {kind.value} question on the {stream!r} stream. Everything below "
                "picks a question by its ordinal, and §3.2's set is versioned, so a set that has "
                "moved its questions would be seeded with a rating in a comment column. Re-run "
                "`make seed`, or correct this file against the set that is in force."
            )
    return {position: asked[position][0] for position in EXPECTED_INSTRUMENT}


def the_respondents(session: Session, section: Section) -> dict[str, UUID]:
    """The nine respondents' `user` rows, found through their enrollments in this section.

    **The subject is resolved forward and never read off the row.** `pulse_app`
    holds `SELECT` on `user.id` alone — E1-10's security round revoked
    `SELECT (lms_user_id)` because a connection that can read it can enumerate
    every subject that ever launched — so the walk is over this section's
    enrollments, asking `app.services.identity.subject_for_user` for each, which is
    ADR 0139's sanctioned definer door.

    Refuses rather than enrolls, which is the whole of `docs/MISTAKES.md` entry
    48's rule at this file's boundary: the roster sync is what writes an enrollment
    (SPEC §7.3), and a seeder that wrote one would make "the fixture reached the
    product's own database" unfalsifiable.
    """
    found: dict[str, UUID] = {}
    for user_id in session.scalars(
        select(Enrollment.user_id).where(Enrollment.section_id == section.id)
    ):
        subject = subject_for_user(session, user_id)
        if subject in POOL:
            found[subject] = user_id
    missing = [subject for subject in POOL if subject not in found]
    if missing:
        raise StoryRefusedError(
            f"These respondents hold no enrollment in {SECTION_LABEL}: {missing}. The roster sync "
            "is what enrols them (SPEC §7.3), so this is the worker not running, the mock platform "
            "not serving its roster, or the staff launch not having stored the section's roster "
            "address. This file creates no user and no enrollment."
        )
    return found


def refuse_a_foreign_response(
    session: Session,
    section: Section,
    weeks: Sequence[WeekOfTheSection],
    respondents: Mapping[str, UUID],
) -> None:
    """Refuse if this section holds a response the plan does not describe.

    The connection this process runs on holds no `DELETE` on `response` — see this
    module's docstring for the measurement and why widening the grant is not the
    repair — so a leftover row cannot be cleared here and must not be written
    around either: it would make one week's response count disagree with the plan
    while every absence assertion in the exit drive stayed vacuously satisfied.

    So it is a refusal that names the row and the repair. The ordinary state of this
    section when this runs is empty, because `tests/e2e/instructor-report.spec.ts`
    clears its own week in an `afterAll`.
    """
    planned = {
        (respondents[subject], week.week_id)
        for week, plan in zip(weeks, STORY, strict=True)
        for subject in plan.respondents
    }
    foreign = [
        (user_id, week_id)
        for user_id, week_id in session.execute(
            select(Response.user_id, Response.week_id).where(Response.section_id == section.id)
        )
        if (user_id, week_id) not in planned
    ]
    if foreign:
        raise StoryRefusedError(
            f"{SECTION_LABEL} holds {len(foreign)} response row(s) this story does not describe, "
            "and this connection holds no `DELETE` on `response` to clear them with (`pulse_app` "
            "has one on `answer` alone, and the `api` container holds no superuser credential by "
            "design). Left in place they would make a week's response count disagree with the "
            "plan while every concealment assertion in the exit drive stayed vacuously satisfied. "
            "Clear the section first — `clearTheWeek` in `tests/e2e/support/survey.ts` is that "
            "statement, run through the `db` container's own superuser."
        )


# ---------------------------------------------------------------------------
# Writing the story.
# ---------------------------------------------------------------------------


@dataclass
class Written:
    """What one run wrote, for the completion line the exit drive reads."""

    responses: int = 0
    answers: int = 0
    verdicts: int = 0
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
            # `recompute_response_validity` once its comments carry verdicts.
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


def write_the_story(session: Session) -> Written:
    """Write the plan into `BIOL-215-R3WW`, and answer what was written."""
    section = the_section(session)
    weeks = the_weeks(session, section)
    questions = the_instrument(session)
    respondents = the_respondents(session, section)
    refuse_a_foreign_response(session, section, weeks, respondents)

    written = Written()
    for week, plan in zip(weeks, STORY, strict=True):
        if not (
            len(plan.respondents)
            == len(plan.instructor_ratings)
            == len(plan.course_ratings)
            == len(plan.workload_hours)
        ):
            raise StoryRefusedError(
                f"The plan for course week {plan.course_week} in this file lists "
                f"{len(plan.respondents)} respondents against "
                f"{len(plan.instructor_ratings)} instructor ratings, "
                f"{len(plan.course_ratings)} course ratings and "
                f"{len(plan.workload_hours)} workload values. The four are positional."
            )
        for seat, subject in enumerate(plan.respondents):
            response = one_response(
                session,
                section=section,
                week=week,
                user_id=respondents[subject],
                submitted_at=week.submitted_at,
            )
            written.responses += 1

            comments = {
                questions[INSTRUCTOR_COMMENT]: plan.instructor_comments.get(seat),
                questions[COURSE_COMMENT]: plan.course_comments.get(seat),
            }
            one_answer(
                session,
                response=response,
                question_id=questions[INSTRUCTOR_RATING],
                rating=plan.instructor_ratings[seat],
            )
            one_answer(
                session,
                response=response,
                question_id=questions[COURSE_RATING],
                rating=plan.course_ratings[seat],
            )
            one_answer(
                session,
                response=response,
                question_id=questions[WORKLOAD],
                workload_hours=Decimal(plan.workload_hours[seat]),
            )
            written.answers += 3

            for question_id, text in comments.items():
                if text is None:
                    continue
                answer = one_answer(
                    session, response=response, question_id=question_id, comment_text=text
                )
                written.answers += 1
                record_verdict(
                    session,
                    CommentValidityOutput(
                        verdict=(
                            ValidityVerdict.NONSENSE
                            if text in REFUSED_COMMENTS
                            else ValidityVerdict.SUBSTANTIVE
                        ),
                        prompt_version=SEED_PROMPT_VERSION,
                        model_id=NOT_A_MODEL,
                    ),
                    answer_id=answer.id,
                )
                written.verdicts += 1

            # Every answer of this response the plan does not describe, removed. The
            # one `DELETE` this connection holds, and what makes a re-run over an
            # edited plan a re-seed rather than a merge.
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
            # `app.services.validity` maintains it, and a seeder that decided it
            # itself would be a second answer to §3.3's question.
            if not recompute_response_validity(session, response):
                written.invalid += 1

    return written


def main() -> int:
    """Refuse outside development, write the story, and say in one line what it wrote."""
    settings = Settings()
    if not is_development(settings):
        print(
            "seed_exit_story refuses to run outside a development environment. It writes a term of "
            "invented survey responses into whatever database it is pointed at, and there is no "
            "environment other than a developer's own where that is the right thing to do. See "
            "docs/adr/0063-the-demo-seed-runs-only-in-a-development-environment.md.",
            file=sys.stderr,
        )
        return 1

    with SessionLocal() as session:
        try:
            written = write_the_story(session)
        except StoryRefusedError as refusal:
            session.rollback()
            print(f"seed_exit_story refused: {refusal}", file=sys.stderr)
            return 1
        session.commit()

    print(
        f"seed_exit_story wrote {SECTION_LABEL}: {written.responses} responses, "
        f"{written.answers} answers and {written.verdicts} comment verdicts across course weeks "
        f"{STORY[0].course_week} to {STORY[-1].course_week}; {written.invalid} response(s) left "
        "invalid. No weekly_summary and no release_batch: those are the two Monday jobs'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
