"""The report says which stream is suppressed, per stream — E5.1-01, criterion 6's payload half.

The owner's ruling 1 makes suppression a fact about a stream: a stream's raw
comments are shown only when enough distinct students commented in that stream
that week. The work order's D5 carries that onto the wire: `small_n` moves from
the report's top level onto each stream object — `streams.instructor.small_n` and
`streams.course.small_n`, each with `suppressed` and `threshold` — and the
top-level member is removed. The frontend renders each group's notice from its own
stream's flag (D6), so a flag that answered for the week would put the notice on
the wrong group, or on neither.

**The world is the canonical report world** (`tests/fixtures/report_api.py`): its
full week holds five responses, each with an instructor-stream comment and none
with a course-stream comment. So in one week the instructor stream is shown and
the course stream is suppressed, and the response count — five — reaches the
threshold. Every count is read back before it is relied on.

**Marked `invariant`**: §4.1 item 3 at the payload boundary, and the module beside
it on the same payload is in the isolated pass for the same reason.

**Which failure a red is, before E5.1-01 lands.** `report_api_contract.stream_member`
fails naming the missing `streams.<stream>.small_n` member, and the top-level test
fails on an assertion that `small_n` is still there.
"""

from typing import Any

import pytest
from fixtures.report_api import FULL_WEEK, ReportDoor

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

THRESHOLD_FIELD = "threshold"


def test_each_stream_carries_its_own_suppression_flag_and_the_threshold(
    report_door: ReportDoor, report_api_contract: Any, comment_contract: Any
) -> None:
    """Both streams of one week: the instructor stream not suppressed, the course stream suppressed.

    The full week's instructor stream holds five commenters and its course stream
    none, in a week of five responses. Each stream's `small_n` must say so for
    itself, and each must carry the configured threshold — the number the notice
    states (§5.2: the notice states the threshold and no count).

    **The mutation it kills:** one week-level flag copied onto both streams —
    whether computed from the response count (five: neither suppressed) or from
    any stream being thin (both suppressed); either answers the two streams alike
    and one of them is wrong. **The near miss it kills:** a stream flag computed
    from the week's response count, which says the course stream — nobody
    commented in it — is not suppressed.
    """
    contract = report_api_contract
    rows = report_door.rows
    threshold = comment_contract.threshold()
    premise = (
        rows.responses_in(FULL_WEEK),
        rows.commenters_in(FULL_WEEK, contract.instructor_stream),
        rows.commenters_in(FULL_WEEK, contract.course_stream),
    )
    assert premise[0] >= threshold and premise[1] >= threshold and premise[2] == 0, (
        f"Course week {FULL_WEEK} holds (responses, instructor commenters, course commenters) = "
        f"{premise} against a threshold of {threshold}. This test needs the responses and the "
        "instructor commenters at or above it and the course stream empty, so the two streams' "
        "flags must differ and a flag computed from the responses is wrong for the course stream."
    )

    body, answered = report_door.payload(course_week=FULL_WEEK)

    def flag(stream: str) -> Any:
        return contract.stream_member(
            body, stream, contract.small_n_member, contract.suppressed_field, answered=answered
        )

    def printed(stream: str) -> Any:
        return contract.stream_member(
            body, stream, contract.small_n_member, THRESHOLD_FIELD, answered=answered
        )

    instructor, course = flag(contract.instructor_stream), flag(contract.course_stream)
    assert (instructor, course) == (False, True), (
        f"`streams.instructor.small_n.suppressed` is {instructor!r} and "
        f"`streams.course.small_n.suppressed` is {course!r}. The instructor stream has "
        f"{premise[1]} commenters and is shown; the course stream has none and is suppressed — in a "
        f"week of {premise[0]} responses. The owner's ruling 1 decides suppression per stream, on "
        "the stream's own commenters."
    )
    assert (printed(contract.instructor_stream), printed(contract.course_stream)) == (
        threshold,
        threshold,
    ), (
        f"The streams print thresholds of {printed(contract.instructor_stream)!r} and "
        f"{printed(contract.course_stream)!r}; the configured threshold is {threshold}. The notice "
        "states this number, so it is the number the gate applies."
    )


def test_the_payload_carries_no_week_level_small_n_member(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The top-level `small_n` is gone, not kept beside the per-stream ones (D5).

    **Why its absence is asserted rather than tolerated.** A week-level flag beside
    two stream-level ones is a second answer to one question, and the page's old
    reading of it renders one notice for the week — which, in a week where one
    stream is shown, sits above comments it says are hidden.

    **The canary** (`docs/MISTAKES.md` entry 3): the payload is a real report — its
    `streams` member is present — before the member is required to be missing.

    **The mutation it kills:** `small_n` left on `InstructorReport` after the
    per-stream member was added.
    """
    contract = report_api_contract
    body, answered = report_door.payload(course_week=FULL_WEEK)
    assert isinstance(body, dict) and contract.streams_member in body, (
        f"The report body carries no `{contract.streams_member}` member, so it is not a report and "
        f"the absence below means nothing. Body begins {answered.text[:400]!r}."
    )
    assert contract.small_n_member not in body, (
        f"The report still carries a top-level `{contract.small_n_member}`: "
        f"{body[contract.small_n_member]!r}. E5.1-01's work order (D5) moves it onto each stream "
        "and removes it from the report, because suppression is decided per stream."
    )


def test_each_streams_flag_is_the_comment_services_own_answer(
    report_door: ReportDoor, report_api_contract: Any, comment_contract: Any
) -> None:
    """The payload's flag is `stream_is_suppressed`'s answer, not a second computation of it.

    The work order's D1 makes `stream_is_suppressed` the one definition, and D5
    builds the payload's flag from it. Two copies of a threshold count drift — the
    payload's notice and the comment read would then disagree about one stream
    (`docs/MISTAKES.md` entry 13, in production code).

    **The mutation it kills:** the assembly layer counting for itself — the
    response count, or the stream's comment answers including released ones — and
    agreeing with the service only where the world happens to make them agree.
    Asserted for both streams of the full week, whose answers differ, so a
    constant cannot agree with both.
    """
    contract = report_api_contract
    report_door.refresh()
    is_suppressed = comment_contract.is_suppressed()
    answers = {
        stream: is_suppressed(
            report_door.world.session,
            section_id=report_door.rows.taught_section_id,
            week_id=report_door.rows.week_id(FULL_WEEK),
            stream=stream,
        )
        for stream in (contract.instructor_stream, contract.course_stream)
    }
    assert set(answers.values()) == {True, False}, (
        f"`{comment_contract.suppressed_name}` answers {answers} for the full week's two streams, "
        "which this world makes one shown and one suppressed. Until they differ, the agreement "
        "asserted below is agreement with a constant."
    )

    body, answered = report_door.payload(course_week=FULL_WEEK)
    for stream, expected in answers.items():
        carried = contract.stream_member(
            body, stream, contract.small_n_member, contract.suppressed_field, answered=answered
        )
        assert carried is expected, (
            f"The payload's `streams.{contract.payload_stream_key[stream]}.small_n.suppressed` is "
            f"{carried!r} and `{comment_contract.suppressed_name}` answers {expected!r} for the "
            "same section, week and stream."
        )
