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

**A missing member is a FAILED, not an error.** `report_api_contract.stream_member`
fails naming the missing `streams.<stream>.small_n` member, so a payload that lost
it is red on a sentence rather than on a `KeyError`.

**The object carries its two fields and nothing else** (E5.1-12, Part B item 1).
ADR 0182 gives each stream's `small_n` exactly `suppressed` and `threshold`; a
third member — a count of commenters, of respondents, of anything — is the number
the notice exists not to state (SPEC §5.2), arriving one layer down from the copy
that `test_the_small_n_notice_states_the_threshold_and_no_count.py` guards.
"""

from typing import Any

import pytest
from fixtures.report_api import FULL_WEEK, ReportDoor

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

THRESHOLD_FIELD = "threshold"

# ADR 0182's whole `small_n` object, written out rather than read from the schema
# it polices (`docs/MISTAKES.md` entry 19): a schema that grew a field would
# otherwise agree with itself here.
SMALL_N_FIELDS = frozenset({"suppressed", THRESHOLD_FIELD})

# The schema class `streams.<stream>.small_n` is built from, as E5.1-12 names it
# (`backend/app/schemas/report.py`).
SMALL_N_VIEW = "SmallNView"


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


def test_each_streams_small_n_object_carries_exactly_suppressed_and_threshold(
    report_door: ReportDoor, report_api_contract: Any, comment_contract: Any
) -> None:
    """On the wire, `small_n` is `{suppressed, threshold}` in a shown stream and a suppressed one.

    Both streams of the full week, because they are the two states the object
    exists to tell apart and a field added on one branch only — a commenter count
    written when the stream is suppressed, say — is invisible to a test that reads
    one of them.

    **The control** is the premise that the two flags differ: the instructor
    stream is shown and the course stream suppressed, so both states are read.

    **The mutation that must turn this red:** a third field on `SmallNView` in
    `backend/app/schemas/report.py` (near line 248) — for example
    `commenters: int | None = None`, filled or left `None`; a `None` still
    serializes as a key. **The near miss that stays green:** the two fields
    reordered or retyped (`threshold: int` to `threshold: PositiveInt`), which
    changes no key.
    """
    contract = report_api_contract
    body, answered = report_door.payload(course_week=FULL_WEEK)

    def small_n(stream: str) -> Any:
        return contract.stream_member(body, stream, contract.small_n_member, answered=answered)

    states = {
        stream: contract.stream_member(
            body, stream, contract.small_n_member, contract.suppressed_field, answered=answered
        )
        for stream in (contract.instructor_stream, contract.course_stream)
    }
    assert set(states.values()) == {True, False}, (
        f"The full week's two streams carry `small_n.suppressed` of {states}. This world makes the "
        "instructor stream shown and the course stream suppressed, and until one of each is read the "
        "field equality below is about one state of the object only."
    )

    for stream in (contract.instructor_stream, contract.course_stream):
        found = small_n(stream)
        assert isinstance(
            found, dict
        ), f"`streams.{contract.payload_stream_key[stream]}.small_n` is {found!r}, not an object."
        assert set(found) == SMALL_N_FIELDS, (
            f"`streams.{contract.payload_stream_key[stream]}.small_n` carries {sorted(found)} "
            f"(suppressed: {states[stream]}); ADR 0182 gives it exactly {sorted(SMALL_N_FIELDS)}. "
            "Any further member on this object is a number or a hint beside the notice, and SPEC "
            "§5.2 says that below the threshold the instructor sees no count."
        )


def test_the_small_n_schema_declares_exactly_suppressed_and_threshold(
    report_api_contract: Any,
) -> None:
    """`SmallNView.model_fields` is `{suppressed, threshold}`, so no field can ride it unseen.

    The wire test above reads what is serialized; this reads what is declared. A
    field declared with `exclude=True`, or one the payload builder never fills, is
    missing from a payload today and present the day somebody fills it — so the
    declaration is pinned as well as the output.

    **The mutation that must turn this red:** any field added to `SmallNView` in
    `backend/app/schemas/report.py` (near line 248), including one declared
    `Field(exclude=True)` that the wire test above cannot see. **The near miss that
    stays green:** a docstring or validator added to the class, which declares no
    field.
    """
    schema = report_api_contract.schema()
    view = getattr(schema, SMALL_N_VIEW, None)
    assert view is not None and hasattr(view, "model_fields"), (
        f"`{report_api_contract.schema_module_name}` exposes no Pydantic model `{SMALL_N_VIEW}`. "
        "E5.1-12 names it as the class each stream's `small_n` is built from; if it was renamed, "
        "the constant at the top of this module is the one place to change."
    )
    declared = set(view.model_fields)
    assert declared, f"`{SMALL_N_VIEW}` declares no fields at all, so the equality below is moot."
    assert declared == SMALL_N_FIELDS, (
        f"`{SMALL_N_VIEW}` declares {sorted(declared)}; ADR 0182 gives the object exactly "
        f"{sorted(SMALL_N_FIELDS)}. A declared field that is excluded or unfilled today is a count "
        "waiting for someone to fill it."
    )
