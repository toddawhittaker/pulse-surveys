"""Summaries follow the stream's commenter count — ticket E5.1-01, criterion 5.

SPEC §5.1: below the n-threshold a stream's summary names themes only and may not
reuse the commenters' own word strings; above it nothing changes. ADR 0162 builds
that as two live prompt versions — `summary.v2` for a small-N stream, `summary.v1`
otherwise — with a store-time guard that refuses a small-N summary sharing a
twenty-character normalized run with a comment it was fed. "The stored
`prompt_version` then says which mode wrote each row."

**What changes here is what decides the mode.** It read the week's response count.
The work order's D4 makes it `stream_is_suppressed` for that stream — the same
definition that hides the stream's comments. So a stream whose comments are hidden
because it has one commenter, in a week of many responses, is the stream whose
summary must be written themes-only, and its sibling above the threshold keeps the
ordinary prompt. Under a response count, the hidden stream's summary was free to
quote the one comment the threshold was withholding.

**The world**: one section-week of `threshold + 1` responses — one student comments
about the instructor, `threshold` others about the course. Every count is read back
from the database first.

**The gateway double echoes the version it was asked for**, because the stored
version is read off the record the gateway returns (ADR 0148) and the real gateway
records the version the call was made under. `StreamAwareGateway` answers one
constant version whatever it is asked, which cannot tell a v2 call from a v1 call.
The double's echo is a control with its own test below: a red control means these
tests are broken, not the code.

**Marked `invariant`**: §4.1 item 3, one layer out — the summary is the surface
that can hand back words the comment read withholds.

**Which failure a red is, before E5.1-01 lands.** Assertions on stored rows: the
thin stream is written under `summary.v1`, and its quoting answer is stored.
"""

from typing import Any

import pytest
from fixtures.grading import (
    RESPONSE_SECTION_COLUMN,
    RESPONSE_USER_COLUMN,
    RESPONSE_WEEK_COLUMN,
    single_column_link,
)
from fixtures.report_comments import configured_threshold
from fixtures.submit import ANSWER_TABLE, COMMENT_TEXT_COLUMN, RESPONSE_TABLE
from fixtures.summary_job import (
    A_CLOSED_TERM_WEEK,
    A_COHORT,
    A_THEME_LABEL,
    ANOTHER_COHORT,
    COURSE_MARK,
    INSTRUCTOR_MARK,
    STREAM_MARKS,
    StreamAwareGateway,
    SummaryWorld,
)
from fixtures.summary_task import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.supervision import require_table, single_primary_key
from sqlalchemy import distinct, func, select

# `COURSE_STREAM` and `INSTRUCTOR_STREAM` above are the gateway's stream tokens —
# the keys `STREAM_MARKS` is keyed by — which are `fixtures.summary_task`'s
# spelling ("instructor"), not the stored one ("INSTRUCTOR").

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The two live prompt versions, from ADR 0162's decision: "v1 is what an
# at-or-above-threshold week renders and v2 is what a small-N week renders".
# Written out rather than read from `app.ai.tasks` (`docs/MISTAKES.md` entry 19).
SMALL_N_PROMPT_VERSION = "summary.v2"
ORDINARY_PROMPT_VERSION = "summary.v1"

# The guard's bound, from ADR 0162: twenty characters, case and whitespace normalized.
THE_GUARD_BOUND = 20

# Routing nonces, one per section. Tokens that appear nowhere else in this
# repository, so finding one in a prompt is evidence (`docs/MISTAKES.md` entry 3).
THIN_SECTION = "Zr4KpT7wQm"
OTHER_SECTION = "Lx9BvN3sHd"

INSTRUCTOR_TAIL = "greenhouse rotations clash with the tutorial on thursdays"
COURSE_TAIL = "the reading list arrived on the morning it was due"

# What the model is made to answer. The quoting summary lifts the instructor
# comment's tail whole; the compliant one shares no long run with it. The course
# summary quotes the course comments **on purpose**: the course stream is above the
# threshold, where §5.1 says nothing changes and the guard does not apply, so a
# build that put the whole week into small-N mode because one stream was thin
# refuses it and is red.
QUOTING_SUMMARY = "Greenhouse rotations clash with the tutorial on thursdays, one student says."
COMPLIANT_SUMMARY = "One student raised a scheduling concern this week."
COURSE_SUMMARY = "The reading list arrived on the morning it was due, several students say."


def instructor_comment(nonce: str) -> str:
    """The one instructor-stream comment of a section's week, carrying its marker and nonce."""
    return f"{INSTRUCTOR_MARK} {nonce} {INSTRUCTOR_TAIL}"


def course_comment(nonce: str, index: int) -> str:
    """One course-stream comment, carrying its marker and nonce."""
    return f"{COURSE_MARK} {nonce} {COURSE_TAIL}, student {index + 1}"


def _normalized(text: str) -> str:
    """Case and whitespace normalized, as ADR 0162 states the guard's comparison."""
    return " ".join(text.lower().split())


def _longest_shared_run(left: str, right: str) -> int:
    """The longest run of normalized characters two strings share. Written out, not imported."""
    first, second = _normalized(left), _normalized(right)
    best = 0
    for start in range(len(first)):
        for end in range(start + best + 1, len(first) + 1):
            if first[start:end] in second:
                best = end - start
            else:
                break
    return best


class AnswersByStreamAndSection(StreamAwareGateway):
    """A gateway that answers per section and stream, and records the version it was asked for.

    The section is read off the nonce in the prompt and the stream off the marker,
    the same way the base class reads the stream. Everything else — the contract
    objects, the recorded prompts — is the base class's and is not re-implemented
    (`docs/MISTAKES.md` entry 13).
    """

    def __init__(self, api: Any, *, answers: dict[tuple[str, str], str], otherwise: str) -> None:
        super().__init__(api)
        self.__dict__["answers"] = dict(answers)
        self.__dict__["otherwise"] = otherwise

    def _answer(self, kwargs: dict[str, Any]) -> Any:
        prompt = str(kwargs.get("prompt", ""))
        chosen = [
            text
            for (nonce, stream), text in self.answers.items()
            if nonce in prompt and STREAM_MARKS[stream] in prompt
        ]
        if len(chosen) > 1:  # pragma: no cover - a broken test, not a red
            pytest.fail(f"One prompt matched {len(chosen)} of this test's section-streams.")
        self.__dict__["summary"] = chosen[0] if chosen else self.otherwise
        record = super()._answer(kwargs)
        asked = kwargs.get("prompt_version")
        if not isinstance(asked, str):
            pytest.fail(
                f"The walk called the gateway with prompt_version={asked!r}. The summary task names "
                "the version on every call (`tests/unit/test_the_weekly_summary_task.py`), and this "
                "double records that version on its answer the way the real gateway does."
            )
        return record.model_copy(update={"prompt_version": asked})


def plant_a_week(world: SummaryWorld, *, cohort: str, nonce: str, threshold: int) -> None:
    """One closed week: one instructor-stream commenter, and `threshold` course-stream ones."""
    world.respond(
        f"{nonce}-instructor-0",
        cohort=cohort,
        term_week=A_CLOSED_TERM_WEEK,
        instructor_comment=instructor_comment(nonce),
    )
    for index in range(threshold):
        world.respond(
            f"{nonce}-course-{index}",
            cohort=cohort,
            term_week=A_CLOSED_TERM_WEEK,
            course_comment=course_comment(nonce, index),
        )


def counts_of(world: SummaryWorld, cohort: str) -> tuple[int, int, int]:
    """(responses, instructor commenters, course commenters) for one section's week.

    Commenters are distinct `response.user_id` behind a comment carrying the
    stream's marker — the unit E5.1-01 makes the threshold count.
    """
    tables = world.world.tables
    responses = require_table(tables, RESPONSE_TABLE)
    answers = require_table(tables, ANSWER_TABLE)
    link = single_column_link(answers, RESPONSE_TABLE)
    assert link is not None, f"No single-column foreign key on `{ANSWER_TABLE}` names a response."
    key = single_primary_key(responses)
    in_week = (
        responses.c[RESPONSE_SECTION_COLUMN] == world.section_id(cohort),
        responses.c[RESPONSE_WEEK_COLUMN] == world.week_id(A_CLOSED_TERM_WEEK),
    )
    session = world.world.session
    session.flush()
    count = session.execute(select(func.count()).select_from(responses).where(*in_week))

    def commenters(mark: str) -> int:
        statement = (
            select(func.count(distinct(responses.c[RESPONSE_USER_COLUMN])))
            .select_from(answers.join(responses, answers.c[link] == responses.c[key]))
            .where(*in_week, answers.c[COMMENT_TEXT_COLUMN].contains(mark))
        )
        return int(session.execute(statement).scalar_one())

    return int(count.scalar_one()), commenters(INSTRUCTOR_MARK), commenters(COURSE_MARK)


def rows_by_stream(world: SummaryWorld, contract: Any, cohort: str) -> dict[str, dict[str, Any]]:
    """One section's stored summaries for its one closed week, keyed by stored stream."""
    found: dict[str, dict[str, Any]] = {}
    for row in world.summaries(section_id=world.section_id(cohort)):
        found[str(row[contract.stream_column])] = row
    return found


def test_the_arithmetic_and_the_double_this_module_rests_on_are_what_they_say(
    summary_job_environment: Any, summary_contracts: Any
) -> None:
    """The control. **A red here means this module is broken, not the code.**

    Two claims everything below rests on. The overlaps: the quoting answer shares
    at least the guard's bound with the instructor comment, the compliant one and
    the default theme label share less, and the course answer shares at least the
    bound with a course comment (so its storing is the guard not applying, not the
    guard finding nothing). And the double: asked for a version, it answers under
    that version and with the summary routed to that section and stream.
    """
    fed = instructor_comment(THIN_SECTION)
    assert _longest_shared_run(QUOTING_SUMMARY, fed) >= THE_GUARD_BOUND
    assert _longest_shared_run(COMPLIANT_SUMMARY, fed) < THE_GUARD_BOUND
    assert _longest_shared_run(A_THEME_LABEL, fed) < THE_GUARD_BOUND
    assert _longest_shared_run(COURSE_SUMMARY, course_comment(THIN_SECTION, 0)) >= THE_GUARD_BOUND

    gateway = AnswersByStreamAndSection(
        summary_contracts,
        answers={(THIN_SECTION, INSTRUCTOR_STREAM): COMPLIANT_SUMMARY},
        otherwise=COURSE_SUMMARY,
    )
    record = gateway.run_task(
        prompt=f"a prompt carrying {fed}", prompt_version=SMALL_N_PROMPT_VERSION
    )
    answered = (record.prompt_version, record.summary)
    assert answered == (SMALL_N_PROMPT_VERSION, COMPLIANT_SUMMARY), (
        f"The double answered under {record.prompt_version!r} with {record.summary!r}; it was asked "
        f"for {SMALL_N_PROMPT_VERSION!r} about this section's instructor stream."
    )


def test_a_thin_stream_in_a_full_week_is_summarized_in_small_n_mode_beside_an_ordinary_one(
    summary_world: SummaryWorld, summary_job_contract: Any, summary_contracts: Any
) -> None:
    """Criterion 5: the thin stream's row is `summary.v2`, its sibling's `summary.v1`.

    One student commented about the instructor and `threshold` others about the
    course, in a week of `threshold + 1` responses. The instructor stream is below
    the commenter threshold, so its summary is written with the small-N prompt and,
    its answer quoting nothing, passes the guard and is stored. The course stream
    is above it and keeps the ordinary prompt — and its answer, which quotes a
    course comment, is stored, because the guard does not apply above the
    threshold.

    **Both rows in one test.** The ordinary row is asserted first, so a walk that
    wrote nothing cannot satisfy the small-N half.

    **The mutation it kills:** the small-N switch reading the week's response count
    — `threshold + 1` reaches the threshold and the thin stream is written under
    `summary.v1`. **Near misses it kills:** the switch reading the week's
    commenters across both streams (`threshold + 1`); and the switch set for the
    whole week when any stream is thin, which writes the course row under `v2` and
    refuses its quoting answer. **And the stored count:** the row's
    `response_count` stays the week's responses (D4, ADR 0148), not the stream's
    commenters.
    """
    contract = summary_job_contract
    contract.require_table(summary_world.world.tables)
    threshold = configured_threshold()
    assert threshold >= 2, f"The configured n-threshold is {threshold}; 1 is not below it."

    summary_world.build(A_COHORT)
    plant_a_week(summary_world, cohort=A_COHORT, nonce=THIN_SECTION, threshold=threshold)
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()
    counts = counts_of(summary_world, A_COHORT)
    assert counts == (threshold + 1, 1, threshold), (
        f"The week holds (responses, instructor commenters, course commenters) = {counts}; this "
        f"test planted {(threshold + 1, 1, threshold)}."
    )

    gateway = AnswersByStreamAndSection(
        summary_contracts,
        answers={
            (THIN_SECTION, INSTRUCTOR_STREAM): COMPLIANT_SUMMARY,
            (THIN_SECTION, COURSE_STREAM): COURSE_SUMMARY,
        },
        otherwise=COMPLIANT_SUMMARY,
    )
    contract.run(gateway=gateway)

    rows = rows_by_stream(summary_world, contract, A_COHORT)
    course = rows.get(contract.stored_course)
    assert course is not None, (
        f"The course stream has no stored summary; the walk wrote {sorted(rows)}. Its answer quotes "
        "a course comment, and the course stream is above the commenter threshold, where SPEC §5.1 "
        "says nothing changes — a refusal here is the small-N mode applied to the whole week."
    )
    assert course[contract.prompt_version_column] == ORDINARY_PROMPT_VERSION, (
        f"The course stream — {threshold} commenters, at the threshold — was written under "
        f"{course[contract.prompt_version_column]!r}. Above the threshold the ordinary prompt "
        f"applies ({ORDINARY_PROMPT_VERSION!r})."
    )

    instructor = rows.get(contract.stored_instructor)
    assert instructor is not None, (
        f"The instructor stream has no stored summary; the walk wrote {sorted(rows)}. Its answer "
        "quotes nothing, so the guard has nothing to refuse."
    )
    assert instructor[contract.prompt_version_column] == SMALL_N_PROMPT_VERSION, (
        f"The instructor stream — one commenter, in a week of {threshold + 1} responses — was "
        f"written under {instructor[contract.prompt_version_column]!r}.\n\n"
        "Its raw comment is hidden because the stream has fewer than the threshold of commenters, "
        "so its summary is the stream's only comment signal and must be written themes-only "
        f"({SMALL_N_PROMPT_VERSION!r}, ADR 0162). A summary written under the ordinary prompt "
        "because the week had enough responses may quote the one comment the threshold withheld."
    )
    assert instructor[contract.response_count_column] == threshold + 1, (
        f"The instructor summary states {instructor[contract.response_count_column]} responses; the "
        f"week holds {threshold + 1}. The work order's D4 keeps the stored count the week's "
        "responses (§5.1, ADR 0148); only the mode follows the stream."
    )


def test_a_thin_streams_quoting_summary_is_refused_in_a_full_week(
    summary_world: SummaryWorld, summary_job_contract: Any, summary_contracts: Any
) -> None:
    """Criterion 5's guard half: the thin stream's reuse guard refuses a quoting answer.

    Two sections, each a week of `threshold + 1` responses with one instructor
    commenter. The model quotes the instructor comment in one section and not in
    the other. The quoting section's instructor summary is not stored; the other
    section's is.

    **The pair is the second section**, asserted first: a walk that stored nothing
    satisfies the refusal (`docs/MISTAKES.md` entry 3).

    **The mutation it kills:** the guard scoped by the week's response count, which
    treats this week as ordinary and stores the summary carrying the one hidden
    comment's words — the disclosure SPEC §5.1's ruling of 2026-09-09 closed,
    reopened for every thin stream in a busy week.
    """
    contract = summary_job_contract
    contract.require_table(summary_world.world.tables)
    threshold = configured_threshold()
    assert threshold >= 2, f"The configured n-threshold is {threshold}; 1 is not below it."

    summary_world.build(A_COHORT)
    summary_world.add_section(ANOTHER_COHORT)
    plant_a_week(summary_world, cohort=A_COHORT, nonce=THIN_SECTION, threshold=threshold)
    plant_a_week(summary_world, cohort=ANOTHER_COHORT, nonce=OTHER_SECTION, threshold=threshold)
    summary_world.clock_after(A_CLOSED_TERM_WEEK)
    summary_world.commit()
    for cohort in (A_COHORT, ANOTHER_COHORT):
        counts = counts_of(summary_world, cohort)
        assert counts == (threshold + 1, 1, threshold), (
            f"Section {cohort}'s week holds (responses, instructor commenters, course commenters) = "
            f"{counts}; this test planted {(threshold + 1, 1, threshold)}."
        )

    gateway = AnswersByStreamAndSection(
        summary_contracts,
        answers={
            (THIN_SECTION, INSTRUCTOR_STREAM): QUOTING_SUMMARY,
            (OTHER_SECTION, INSTRUCTOR_STREAM): COMPLIANT_SUMMARY,
        },
        otherwise=COURSE_SUMMARY,
    )
    contract.run(gateway=gateway)

    other = rows_by_stream(summary_world, contract, ANOTHER_COHORT).get(contract.stored_instructor)
    assert other is not None, (
        "The section whose instructor summary quotes nothing has no stored instructor summary, so "
        "the refusal asserted below could be a walk that stored nothing at all."
    )

    refused = rows_by_stream(summary_world, contract, A_COHORT).get(contract.stored_instructor)
    assert refused is None, (
        f"The instructor summary {refused[contract.text_column]!r} was stored under "
        f"{refused[contract.prompt_version_column]!r}. It shares "
        f"{_longest_shared_run(QUOTING_SUMMARY, instructor_comment(THIN_SECTION))} normalized "
        f"characters with the stream's one comment, against a bound of {THE_GUARD_BOUND}.\n\n"
        "That comment is hidden: one student commented in this stream, below the threshold. The "
        "guard applies below the threshold (ADR 0162), and the threshold is the stream's commenter "
        "count — so a guard scoped by the week's responses lets this summary hand the hidden "
        "comment back."
    )
