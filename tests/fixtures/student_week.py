"""E8-01 — the student's week under the hold: the names, the planting and the reads.

Eight test modules ask the results route and the two student comment reads the
same questions, so the driving lives here and each module asserts
(`docs/MISTAKES.md` entry 13). **This file defines no pytest fixture.** Every
module takes E7-02's `hold` world (`tests/fixtures/the_hold.py`) and passes it to
the plain functions below, so nothing new has to be registered and a tree without
E8-01 fails inside a test body naming what is missing (entry 44).

**The names E8-01's work order settles, transcribed once** (its "Settled
identifiers" and "Settled decisions"):

  - `StudentWeekResults` keeps `state`, `response` and `published_weeks` and gains
    `course_label: str` (always), `streams: list[StudentStream] | None` (`None`
    while `awaiting`, otherwise exactly two, instructor then course),
    `workload_median: float | None` (`None` while `awaiting`) and
    `released: list[StudentReleasedComment] | None` (`None` unless ruling 1 lets
    the group show);
  - `StudentStream {stream, trend, distribution, small_n, comments}`, with
    `stream` one of `instructor` and `course`, `trend` a list of
    `StudentTrendPoint {course_week, mean}`, `distribution` keyed "1" to "5", and
    `comments` a list of `StudentComment {text}`, empty when `small_n`;
  - `StudentReleasedComment {text, stream}`;
  - decision 1: one trend point per published, non-`awaiting` week up to and
    including the page's week; a held week has no point;
  - decision 2: the release group on the latest published week's page only,
    `None` while any published week of the section is `awaiting`, and holding
    only batches cut strictly before that week's report opened;
  - decision 3: `student_released_comments(..., as_of: datetime)`;
  - decision 4: comment order shuffled as on the instructor's report.

**What this file settles that the work order does not spell, and why it is not
an invention.** The two student reads' other parameters. The ticket says they
"take a section, a week or term, a stream and, for the released read, an as-of
instant" and filter `visible_cards` and `released_cards`; the two reads those
cards are dropped into already take `(session, section_id, week_id, stream)` and
`(session, section_id, term_id, stream)` (E4-04's settled signatures, asserted in
`tests/unit/test_the_report_comment_service_names_nothing_a_student_path_can_reach.py`).
So the student reads are spelled the same way with `as_of` added, and the manifest
names this as the one transcription a builder must match.

**E8-03's member.** E8-03 adds `participation` to the same payload in parallel.
Nothing here asserts the payload's whole key set: the held-week tests name a
FORBIDDEN list, and `participation` is named only where a walk over the payload
has to step around the student's own posted record (ruling 4: it is the
student's own record, not an aggregate, so the hold does not cover it).

**Release batches are planted, not cut, and that is deliberate.** The subject
here is the student's read of a batch, and decision 2's boundary is one second
either side of a report opening. The cutter stamps `cut_at` from the moving
development clock (ADR 0109: the effective instant keeps moving while it is
read), so no test can place a cut one second from an edge through it. So a batch
is two rows written as the superuser — `release_batch {section_id, term_id,
cut_at}` and its members `{batch_id, answer_id}`, ADR 0146's whole column sets —
naming comments the canonical world already holds. What the cutter decides to
cut is its own suite's subject (`test_the_cumulative_release_cuts_one_batch_
when_volume_crosses.py`) and is not re-asserted here.

**Every comment a test plants goes in through the product's own path**: a new
respondent's submission and a routed moderation verdict
(`DecisionDoor.plant_a_comment`), and every exclude or keep through E6-03's own
decision route. Every claim about the world is then read back **through the
instructor's report**, the reader that certainly can see what a student must not
(`docs/MISTAKES.md` entry 58, and the readable-something control): an absence on
the student's page means something only beside the same comment present, with
its status, on the instructor's.

**Nothing here decides an answer.** It plants, calls and reads back; every
expectation is written in the test that makes it (entries 19 and 30).
"""

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from fixtures.instructor_decisions import OK, a_reason
from fixtures.moderation import CLEAR
from fixtures.report_api import (
    COMMENT_STATUS_FIELD,
    COMMENT_TEXT_FIELD,
    COMMENTS_FIELD,
    DISTRIBUTION_FIELD,
    PAYLOAD_STREAM_KEY,
    RELEASED_MEMBER,
    SMALL_N_MEMBER,
    STREAMS_MEMBER,
    SUPPRESSED_FIELD,
    TAUGHT_COHORT,
)
from fixtures.report_comments import comment_service
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.student_read import (
    COURSE_NUMBER_COLUMN,
    COURSE_TABLE,
    COURSE_TITLE_COLUMN,
    PREFIX_CODE_COLUMNS,
    PREFIX_TABLE,
    TERM_NAME_COLUMN,
    course_label,
    scalars_in,
)
from fixtures.supervision import (
    foreign_key_columns,
    require_column,
    require_table,
    single_primary_key,
)
from fixtures.survey_windows import SECTION_CODE_COLUMN, SECTION_TABLE, TERM_TABLE
from fixtures.the_hold import (
    E8_01_MEMBERS,
    FIRST_ROW_AFTER_OPENING,
    INSTRUCTOR,
    LEAD_FACULTY,
    PUBLISHED_WEEKS,
    REQUIRED,
    HoldWorld,
    Student,
    payload_of,
    report_opens,
)

# ---------------------------------------------------------------------------
# The payload, as the work order settles it.
# ---------------------------------------------------------------------------

COURSE_LABEL = "course_label"
STREAMS = "streams"
WORKLOAD_MEDIAN = "workload_median"
RELEASED = "released"

# E8-03's member, named only so that walks over the payload can step around it.
PARTICIPATION = "participation"

# `StudentStream`'s members, and the two stream names in the order they arrive.
STREAM = "stream"
TREND = "trend"
DISTRIBUTION = "distribution"
SMALL_N = "small_n"
COMMENTS = "comments"
STREAM_MEMBERS = frozenset({STREAM, TREND, DISTRIBUTION, SMALL_N, COMMENTS})
INSTRUCTOR_NAME = "instructor"
COURSE_NAME = "course"
STREAM_ORDER = (INSTRUCTOR_NAME, COURSE_NAME)
NAME_OF_STREAM = {INSTRUCTOR_STREAM: INSTRUCTOR_NAME, COURSE_STREAM: COURSE_NAME}

# `StudentTrendPoint`, `StudentComment` and `StudentReleasedComment`, whole.
COURSE_WEEK = "course_week"
MEAN = "mean"
TREND_POINT_MEMBERS = frozenset({COURSE_WEEK, MEAN})
TEXT = "text"
COMMENT_MEMBERS = frozenset({TEXT})
RELEASED_MEMBERS = frozenset({TEXT, STREAM})

# "keys "1".."5", same shape as the instructor report's rating distribution".
RATING_KEYS = ("1", "2", "3", "4", "5")

# What a held week may not carry (done-when 1), as members. Each is `None` while
# `awaiting`, and each is something on a released week.
FORBIDDEN_WHILE_HELD = (STREAMS, WORKLOAD_MEDIAN, RELEASED)

# The keys that exist only inside a figure, a comment or a batch. None of them
# may appear anywhere in a held week's body, under any parent: a figure moved
# to a member nobody listed is still a figure.
KEYS_ONLY_A_FIGURE_CARRIES = (TREND, DISTRIBUTION, SMALL_N, COMMENTS, MEAN, COURSE_WEEK)

# ---------------------------------------------------------------------------
# The two student reads in `app.services.report_comments`.
# ---------------------------------------------------------------------------

STUDENT_COMMENTS = "student_comments"
STUDENT_RELEASED_COMMENTS = "student_released_comments"
STUDENT_READ_SIGNATURES = {
    STUDENT_COMMENTS: ("session", "section_id", "week_id", "stream"),
    STUDENT_RELEASED_COMMENTS: ("session", "section_id", "term_id", "stream", "as_of"),
}
STUDENT_READS_ARE_OWED = (
    "E8-01's ticket adds two functions to `app.services.report_comments`, filtering "
    "`visible_cards` and `released_cards` (which read `report_comment` v004) to the `published` "
    "and `kept` statuses and returning text and stream only: "
    f"`{STUDENT_COMMENTS}(session, *, section_id, week_id, stream)` and "
    f"`{STUDENT_RELEASED_COMMENTS}(session, *, section_id, term_id, stream, as_of)`, the second "
    "returning only batches cut before `as_of` (work order decision 3)."
)

# ---------------------------------------------------------------------------
# The release tables (ADR 0146; `tests/integration/test_report_schema.py`).
# ---------------------------------------------------------------------------

RELEASE_BATCH = "release_batch"
RELEASE_BATCH_MEMBER = "release_batch_member"
BATCH_SECTION_COLUMN = "section_id"
BATCH_TERM_COLUMN = "term_id"
CUT_AT_COLUMN = "cut_at"
MEMBER_BATCH_COLUMN = "batch_id"
MEMBER_ANSWER_COLUMN = "answer_id"

# Where the weekly cut sits against the report it precedes: Monday 02:40 against
# Monday 06:00, both in the institution's zone (E4-04's beat entry; ADR 0184).
CUT_BEFORE_OPENING = timedelta(hours=3, minutes=20)
ONE_SECOND = timedelta(seconds=1)

# The decision route's two actions (E6-03).
EXCLUDE = "exclude"
KEEP = "keep"

# The instructor report's comment statuses as it serves them (E4-04's spelling).
SHOWN_PUBLISHED = "published"
SHOWN_KEPT = "kept"
SHOWN_FLAGGED = "flagged_collapsed"
SHOWN_EXCLUDED = "excluded"


# ---------------------------------------------------------------------------
# Reading the route.
# ---------------------------------------------------------------------------


def read(world: HoldWorld, student: Student, course_week: int) -> tuple[dict[str, Any], Any]:
    """One read of the results route: the decoded body, held to its members, and the response.

    `payload_of` admits E8-01's four members; this requires them, on every state,
    so a tree without E8-01 fails here naming them rather than on a `KeyError`.
    """
    answered = world.results(student, course_week=course_week)
    what = f"The results read of course week {course_week} for {student.label}"
    body = payload_of(answered, what)
    missing = sorted(E8_01_MEMBERS - set(body))
    if missing:
        pytest.fail(
            f"{what} carries {sorted(body)} and lacks {missing}. E8-01's work order adds "
            f"`{COURSE_LABEL}: str` (always present), `{STREAMS}`, `{WORKLOAD_MEDIAN}` and "
            f"`{RELEASED}` to `StudentWeekResults`, each of the last three `None` while `awaiting`."
        )
    return body, answered


def streams_of(body: Mapping[str, Any], what: str) -> dict[str, dict[str, Any]]:
    """The two `StudentStream` entries by name, after requiring the settled shape.

    Exactly two, instructor first and course second, each carrying exactly
    `StudentStream`'s members. A failure here names the payload rather than
    letting a later index raise.
    """
    found = body.get(STREAMS)
    if not isinstance(found, list) or len(found) != 2:
        pytest.fail(
            f"{what} carries `{STREAMS}` = {str(found)[:400]!r}. The work order: on a released "
            "week, exactly two `StudentStream` entries, ordered instructor then course."
        )
    names = [entry.get(STREAM) if isinstance(entry, dict) else None for entry in found]
    if tuple(names) != STREAM_ORDER:
        pytest.fail(f"{what} carries streams named {names}; the work order: {STREAM_ORDER}.")
    for entry in found:
        if set(entry) != STREAM_MEMBERS:
            pytest.fail(
                f"{what} carries a stream with members {sorted(entry)}; `StudentStream` is exactly "
                f"{sorted(STREAM_MEMBERS)}."
            )
    return {entry[STREAM]: entry for entry in found}


def comment_texts(entry: Mapping[str, Any]) -> list[str]:
    """The texts one stream's `comments` carries, in the order served."""
    return [str(comment.get(TEXT)) for comment in entry.get(COMMENTS) or []]


def released_texts(body: Mapping[str, Any]) -> list[str]:
    """The texts the release group carries, or an empty list when it is `None`."""
    return [str(item.get(TEXT)) for item in body.get(RELEASED) or []]


def trend_weeks(entry: Mapping[str, Any]) -> list[int]:
    """The course weeks one stream's trend has a point for, sorted."""
    return sorted(int(point[COURSE_WEEK]) for point in entry.get(TREND) or [])


def means_by_week(entry: Mapping[str, Any]) -> dict[int, Any]:
    """One stream's trend as `{course_week: mean}`."""
    return {int(point[COURSE_WEEK]): point[MEAN] for point in entry.get(TREND) or []}


def outside_the_own_record(body: Mapping[str, Any]) -> dict[str, Any]:
    """The payload without `published_weeks` (week numbers, not counts) and E8-03's member."""
    stepped_around = (PUBLISHED_WEEKS, PARTICIPATION)
    return {key: value for key, value in body.items() if key not in stepped_around}


def numbers_outside_the_own_record(body: Mapping[str, Any]) -> list[Any]:
    """Every number the payload carries outside `published_weeks` and `participation`."""
    return [
        value
        for value in scalars_in(outside_the_own_record(body))
        if isinstance(value, int | float) and not isinstance(value, bool)
    ]


def keys_in(node: Any, path: str = "$") -> list[tuple[str, str]]:
    """Every dict key at every depth, with where it sits; `participation` is stepped around."""
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if path == "$" and key == PARTICIPATION:
                continue
            found.append((f"{path}.{key}", str(key)))
            found.extend(keys_in(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(keys_in(item, f"{path}[{index}]"))
    return found


# ---------------------------------------------------------------------------
# Planting.
# ---------------------------------------------------------------------------


def teacher_of(world: HoldWorld) -> Any:
    return world.person(world.names.teacher).person_id


def required_from_the_first_week(world: HoldWorld) -> None:
    """The own course required by its lead, a day before course week 1's report opens.

    In force for every week of the section (SPEC §5.3: the policy that governs a
    week is the one in force when its report opens).
    """
    world.a_policy(
        course=world.own_course,
        setter=world.person(world.names.lead).person_id,
        role=LEAD_FACULTY,
        mode=REQUIRED,
        set_at=report_opens(1) - timedelta(days=1),
    )


def a_reply_to(world: HoldWorld, course_week: int, body: str) -> None:
    """The teacher's response to one course week, ten minutes after its report opened."""
    world.a_response(
        section_id=world.taught,
        course_week=course_week,
        author=teacher_of(world),
        role=INSTRUCTOR,
        body=body,
        published_at=report_opens(course_week) + FIRST_ROW_AFTER_OPENING,
    )


def publish_now(world: HoldWorld, course_week: int, body: str) -> None:
    """The teacher publishes through E7-02's writer, at the clock's own instant."""
    world.publish(
        section_id=world.taught,
        course_week=course_week,
        author=teacher_of(world),
        role=INSTRUCTOR,
        body=body,
    )


def plant_comment(
    world: HoldWorld,
    *,
    course_week: int,
    stream: str,
    text: str,
    verdict: str | None = CLEAR,
    cohort: str = TAUGHT_COHORT,
) -> Any:
    """One new respondent's comment, committed; its answer id.

    **The verdict is routed at once only if the week's window has already closed
    by the world's clock**; otherwise it is owed (`PendingVerdicts`), and the
    comment is in no reader's view until `route_owed_verdicts` routes it. The
    hold world's clock, as built, has closed course week 1 only (dispute
    E8-01-01 measured it), so a comment planted into any later week must be
    followed by `route_owed_verdicts` before anything decides on it or reads it.
    """
    return world.review.plant(
        course_week=course_week, stream=stream, text=text, verdict=verdict, cohort=cohort
    )


def route_owed_verdicts(world: HoldWorld, *, standing_after: int) -> None:
    """Stand an hour after `standing_after`'s report opens, and route every verdict now owed.

    Moving the clock alone routes nothing (`HoldWorld.stand_at` only pretends);
    the canonical world routes its owed verdicts the same way, with an explicit
    `plant_pending()` after setting the clock (`tests/fixtures/report_api.py`,
    `_build_report_door`). Committed, because the application connects for itself.
    """
    world.stand_after_the_opening(standing_after)
    world.door.world.plant_pending()
    world.door.commit()


def answer_id_of(world: HoldWorld, text: str) -> Any:
    """The one canonical-world `answer` carrying `text`."""
    world.door.refresh()
    return world.review.door.answer_id_of(text)


def decide(world: HoldWorld, answer_id: Any, action: str) -> None:
    """One exclude or keep through E6-03's decision route, required to land.

    An exclusion carries a stated reason, because SPEC §5.2 requires one for a
    comment the AI did not flag and every exclusion here is of such a comment.
    """
    reason = a_reason(40) if action == EXCLUDE else None
    answered = world.review.door.decide(answer_id, action, reason)
    assert answered.status_code == OK, (
        f"E6-03's decision route answered {answered.status_code} to {action!r} on {answer_id}, "
        f"so the comment is not in the state this world says it is. Body {answered.text[:300]!r}. "
        "A broken world, not a red."
    )


def a_batch(world: HoldWorld, *, cut_at: datetime, answer_ids: Iterable[Any]) -> Any:
    """One `release_batch` of the taught section's term, cut at `cut_at`, holding these comments.

    Written as the superuser and committed; the batch's key. See the module
    docstring for why it is planted rather than cut.
    """
    members = list(answer_ids)
    assert members, "A batch with no members releases nothing; the test planting it is broken."
    batch = world.rows.seed(
        RELEASE_BATCH,
        {},
        **{
            BATCH_SECTION_COLUMN: world.taught,
            BATCH_TERM_COLUMN: world.term_id(),
            CUT_AT_COLUMN: cut_at,
        },
    )
    key = single_primary_key(require_table(world.tables, RELEASE_BATCH))
    for answer_id in members:
        world.rows.seed(
            RELEASE_BATCH_MEMBER,
            {},
            **{MEMBER_BATCH_COLUMN: batch[key], MEMBER_ANSWER_COLUMN: answer_id},
        )
    world.rows.commit()
    return batch[key]


# ---------------------------------------------------------------------------
# The instructor's report, as the readable-something control.
# ---------------------------------------------------------------------------


def instructor_report(world: HoldWorld, course_week: int) -> dict[str, Any]:
    """The teaching instructor's report for one course week of the taught section."""
    world.door.refresh()
    with world.door.carrying_no_cookie():
        body, _answered = world.door.payload(course_week=course_week)
    return body


def instructor_statuses(body: Mapping[str, Any], stream: str) -> dict[str, str]:
    """`{text: status}` for one stream of the instructor's report."""
    entry = body[STREAMS_MEMBER][PAYLOAD_STREAM_KEY[stream]]
    return {
        str(card[COMMENT_TEXT_FIELD]): str(card.get(COMMENT_STATUS_FIELD))
        for card in entry.get(COMMENTS_FIELD) or []
    }


def instructor_released_statuses(body: Mapping[str, Any]) -> dict[str, str]:
    """`{text: status}` for the instructor's released-from-earlier-weeks list."""
    return {
        str(card[COMMENT_TEXT_FIELD]): str(card.get(COMMENT_STATUS_FIELD))
        for card in body.get(RELEASED_MEMBER) or []
    }


def instructor_suppressed(body: Mapping[str, Any], stream: str) -> Any:
    return body[STREAMS_MEMBER][PAYLOAD_STREAM_KEY[stream]][SMALL_N_MEMBER][SUPPRESSED_FIELD]


def instructor_distribution(body: Mapping[str, Any], stream: str) -> Any:
    return body[STREAMS_MEMBER][PAYLOAD_STREAM_KEY[stream]][DISTRIBUTION_FIELD]


# ---------------------------------------------------------------------------
# The course label, built from the rows (entry 19), never from the code.
# ---------------------------------------------------------------------------


def _row(world: HoldWorld, table_name: str, key_value: Any) -> Mapping[str, Any]:
    table = require_table(world.tables, table_name)
    key = single_primary_key(table)
    session = world.rows.session
    session.rollback()
    found = session.execute(select(table).where(table.c[key] == key_value)).mappings().one()
    session.rollback()
    return found


def _parent(world: HoldWorld, child_table: str, parent_table: str, row: Mapping[str, Any]) -> Any:
    columns = foreign_key_columns(require_table(world.tables, child_table), parent_table)
    assert len(columns) == 1, f"`{child_table}` has {columns} foreign keys into `{parent_table}`."
    return _row(world, parent_table, row[columns[0]])


def label_of(world: HoldWorld, section_id: Any) -> str:
    """FIX-01 item 2's label for one section, composed from its own rows."""
    section = _row(world, SECTION_TABLE, section_id)
    course = _parent(world, SECTION_TABLE, COURSE_TABLE, section)
    prefix = _parent(world, COURSE_TABLE, PREFIX_TABLE, course)
    term = _parent(world, SECTION_TABLE, TERM_TABLE, section)
    code_column = require_column(require_table(world.tables, PREFIX_TABLE), PREFIX_CODE_COLUMNS)
    return course_label(
        prefix[code_column],
        course[COURSE_NUMBER_COLUMN],
        section[SECTION_CODE_COLUMN],
        course[COURSE_TITLE_COLUMN],
        term[TERM_NAME_COLUMN],
    )


# ---------------------------------------------------------------------------
# The two student reads, called directly.
# ---------------------------------------------------------------------------


def student_read(name: str) -> Any:
    """One of the two student reads, or a failure naming the ticket."""
    module = comment_service()
    found = getattr(module, name, None)
    if not callable(found):
        pytest.fail(
            f"`{module.__name__}` exposes no callable `{name}`; it exposes "
            f"{sorted(entry for entry in vars(module) if not entry.startswith('_'))}.\n\n"
            f"{STUDENT_READS_ARE_OWED}"
        )
    return found


def call_student_read(world: HoldWorld, name: str, **keywords: Any) -> list[Any]:
    """Call one student read on `pulse_app`'s connection; what it returned, as a list."""
    function = student_read(name)
    session = world.application_session
    try:
        answered = function(session, **keywords)
    except TypeError as mismatch:
        session.rollback()
        pytest.fail(
            f"`{name}` refused the keywords {sorted(keywords)}: {mismatch}\n\n"
            f"{STUDENT_READS_ARE_OWED}"
        )
    session.rollback()
    return list(answered)


def text_of(item: Any) -> str:
    """A returned comment's text, whether it is an object carrying `text` or a mapping."""
    if isinstance(item, Mapping):
        return str(item[TEXT])
    return str(item.text)
