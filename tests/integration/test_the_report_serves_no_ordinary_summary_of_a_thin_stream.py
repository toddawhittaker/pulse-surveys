"""An ordinary summary stored for a thin stream is not served — E6-09, done-when 2.

> Through the report route, a week holding a `summary.v1` row on a thin stream
> serves no summary for it, and a full stream's summary in the same week is served
> (the control).

SPEC §5.1: below the n-threshold a stream's summary "names themes only and may not
reuse the commenters' own word strings", which is what the small-N prompt is for.
A `summary.v1` row is the ordinary prompt's, written before the per-stream rule or
for a stream that has since thinned; it may quote the comments the threshold is
withholding. ADR 0188's rule is that such a row is not served.
`tests/integration/test_the_hourly_summary_walk_and_what_a_stored_summary_shows.py`
asserts it of a private helper; this asserts it where a reader meets it, through
the report route, and is marked `invariant` so the isolated §4.1 pass runs it
(`docs/MISTAKES.md` entries 35 and 53: find the rows the way the reader does).

**The world** is the canonical report world at the teaching instructor's door.
Course week 1's instructor stream holds five commenters (at the threshold, shown);
its course stream is given one commenter here, so it is thin. Each stream then
gets a `summary.v1` row. **The control is the full stream's summary in the same
read**: a route that served no summary at all would satisfy the absence alone
(`docs/MISTAKES.md` entry 3).

**Which failure a red is.** If the route serves stored rows without the mode rule,
the thin stream's assertion fails naming the served text. The rule exists today in
the reporting service, so this may be green on arrival; it is coverage, and the
mutation below is what shows it can go red.
"""

from typing import Any

import pytest
from fixtures.instructor_decisions import DecisionDoor
from fixtures.moderation import CLEAR
from fixtures.report_api import (
    FULL_WEEK,
    PAYLOAD_STREAM_KEY,
    SMALL_N_MEMBER,
    STREAMS_MEMBER,
    SUMMARY_FIELD,
    SUPPRESSED_FIELD,
    strings_in,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

WEEKLY_SUMMARY = "weekly_summary"
ORDINARY_PROMPT_VERSION = "summary.v1"

# The served summary's text member (the exit test reads the same one).
SUMMARY_TEXT = "text"

# Distinct, so a leak of either is unmistakable in a failure message.
THIN_SUMMARY_TEXT = "E6-09 an ordinary-mode summary of the thin course stream, quoting it whole"
FULL_SUMMARY_TEXT = "E6-09 an ordinary-mode summary of the full instructor stream"


def plant_a_summary(door: DecisionDoor, stream: str, text: str) -> None:
    """One `summary.v1` row for course week 1 of the taught section, committed."""
    rows = door.door.rows
    door.world.seed(
        WEEKLY_SUMMARY,
        {},
        section_id=rows.taught_section_id,
        week_id=rows.week_id(FULL_WEEK),
        stream=stream,
        summary_text=text,
        response_count=1,
        themes=[],
        prompt_version=ORDINARY_PROMPT_VERSION,
        model_id="e6-09-a-model",
    )
    door.door.commit()


def stream_of(body: Any, stream: str) -> dict[str, Any]:
    return body[STREAMS_MEMBER][PAYLOAD_STREAM_KEY[stream]]


def test_the_report_serves_no_ordinary_summary_of_a_thin_stream_beside_a_full_streams(
    decision_door: DecisionDoor,
) -> None:
    """Course week 1: the thin course stream's `summary.v1` is withheld, the full stream's served.

    **The mutation this kills:** the report payload built from every stored
    summary row whatever its prompt version (the mode check in the reporting
    service removed), which serves a summary that may quote comments the
    threshold withholds. **The near miss:** a rule that withholds every summary
    of the week, or every `summary.v1` row — the full stream's row is ordinary
    mode too, and it must be served.
    """
    door = decision_door
    door.plant_a_comment(
        course_week=FULL_WEEK,
        stream=COURSE_STREAM,
        text="E6-09 the one course comment of course week 1, which makes its stream thin",
        verdict=CLEAR,
    )
    assert door.door.rows.commenters_in(FULL_WEEK, COURSE_STREAM) == 1, (
        "Course week 1's course stream does not hold exactly one commenter, so it is not the thin "
        "stream this test is about."
    )
    assert door.door.rows.commenters_in(FULL_WEEK, INSTRUCTOR_STREAM) >= 5, (
        "Course week 1's instructor stream holds fewer than five commenters, so it is not the "
        "full stream the control needs."
    )
    plant_a_summary(door, COURSE_STREAM, THIN_SUMMARY_TEXT)
    plant_a_summary(door, INSTRUCTOR_STREAM, FULL_SUMMARY_TEXT)

    body = door.payload(FULL_WEEK)
    course, instructor = stream_of(body, COURSE_STREAM), stream_of(body, INSTRUCTOR_STREAM)
    assert course[SMALL_N_MEMBER][SUPPRESSED_FIELD] is True, (
        f"The course stream's `small_n` is {course[SMALL_N_MEMBER]!r}; with one commenter it is "
        "below the threshold, which is the premise of this test."
    )
    served = instructor.get(SUMMARY_FIELD)
    assert isinstance(served, dict) and served.get(SUMMARY_TEXT) == FULL_SUMMARY_TEXT, (
        f"The control: the full instructor stream's summary is served as {served!r}, not the "
        f"stored {FULL_SUMMARY_TEXT!r}. A route that serves no summary at all would satisfy the "
        "absence below."
    )
    assert course.get(SUMMARY_FIELD) is None, (
        f"The thin course stream's summary is served as {course.get(SUMMARY_FIELD)!r}. A "
        f"`{ORDINARY_PROMPT_VERSION}` row was written under the ordinary prompt, which may quote "
        "the comments the threshold withholds; SPEC §5.1 and ADR 0188 serve none for a thin stream."
    )
    leaked = [value for value in strings_in(body) if THIN_SUMMARY_TEXT[:40] in value]
    assert not leaked, f"The thin stream's ordinary summary is in the served report: {leaked}."
