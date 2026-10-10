"""SPEC §14.3's E6 exit, its welfare half: a self-harm comment opens a case and leaves no trace.

"A welfare-flagged comment in a 3-response week provably reaches Care with no
trace in the instructor view." The world is E4-07's report world at the
teaching instructor's door. Course week 4 holds two responses; one more
student answers it with a comment carrying the mock provider's self-harm
marker, so the week has three. Nothing plants that comment's verdict: the
hourly moderation sweep asks the mock provider (SPEC §7.4, ADR 0188), and the
provider's answer routes it.

What is asserted, and through which reader (`docs/MISTAKES.md` entry 58):

  - **The case.** Nothing in the product reads `threat_case` before E10's Care
    queue, so this test reads the table itself: one row for the comment.
  - **No trace.** The instructor's report for that week, as served, is the same
    before the comment existed and after it was moderated in every member that
    shows or counts comments: each stream's comments and small-N state, and the
    released list. After the real summary walk, the week's course-stream summary
    says what course week 2's says, a week in which nobody wrote a course
    comment. No string in the body carries the comment's words.
  - **The canary.** Course week 1 of the same world, read in the same way,
    still shows its five comments. A report that showed nothing at all would
    satisfy the absence alone (`docs/MISTAKES.md` entry 3).

`tests/e2e/exit-moderation.spec.ts` drives the same clause on the running stack.
"""

from typing import Any

import pytest
from fixtures.clock import DEVELOPMENT, ENVIRONMENT_VARIABLE
from fixtures.instructor_decisions import DecisionDoor
from fixtures.mock_ai import (
    MOCK_AI_PROVIDER_BASE_URL_VARIABLE,
    MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE,
    Endpoint,
    MockAiProvider,
)
from fixtures.moderation import SELF_HARM, moderation_verdicts, threat_cases
from fixtures.report_api import (
    COMMENT_TEXT_FIELD,
    COMMENTS_FIELD,
    FULL_WEEK,
    FULL_WEEK_COMMENTS,
    IN_DENOMINATOR_WEEK,
    PAYLOAD_STREAM_KEY,
    RELEASED_MEMBER,
    RESPONSES_IN_WEEK,
    SECOND_HELD_WEEK,
    SMALL_N_MEMBER,
    STREAMS_MEMBER,
    SUMMARY_FIELD,
    strings_in,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM

pytestmark = pytest.mark.integration

# The week the comment is written in. Two responses before it, three after:
# the "3-response week" of the exit clause.
WELFARE_WEEK = SECOND_HELD_WEEK

# The marker is the mock provider's (`mock-ai/app/rules.py`, rule 6). The rest
# of the sentence is distinctive enough that a leak of any part is unmistakable.
WELFARE_COMMENT = (
    "E6 exit welfare: lately I cannot see the point of carrying on with any of this "
    "mock-ai:self-harm"
)
# The words checked for in the served body: the opening alone, so a summary or an
# excerpt that kept only the start of the sentence is still caught.
WELFARE_WORDS = "E6 exit welfare"

# A week in which nobody wrote a course comment: two responses, ratings only.
NO_COMMENT_WEEK = IN_DENOMINATOR_WEEK

# Every member of one stream that could carry a comment or a count of
# commenters. The summary is compared separately, after the summary walk.
COMMENT_BEARING = (COMMENTS_FIELD, SMALL_N_MEMBER)

# The members of a stored summary that come from the comments. Its response
# count is the week's responses, which the comment's response does add to.
SUMMARY_FROM_COMMENTS = ("text", "held_note")


@pytest.fixture
def mock_gateway(
    monkeypatch: pytest.MonkeyPatch,
    care_service_environment: dict[str, str],
    mock_ai: MockAiProvider,
    mock_ai_endpoint: Endpoint,
) -> Any:
    """An `AIGateway` pointed at the in-process mock provider, in a development environment."""
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, DEVELOPMENT)
    monkeypatch.setenv(MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE, "mock-moderation-v1")
    monkeypatch.setenv(MOCK_AI_PROVIDER_BASE_URL_VARIABLE, mock_ai_endpoint.base_url)

    from app.ai.gateway import AIGateway
    from app.config import Settings

    return AIGateway(settings=Settings())


def comment_bearing(body: Any) -> dict[str, Any]:
    """The members of one served report that could show a comment, or count one."""
    streams = body[STREAMS_MEMBER]
    shown = {
        stream: {member: streams[PAYLOAD_STREAM_KEY[stream]][member] for member in COMMENT_BEARING}
        for stream in (INSTRUCTOR_STREAM, COURSE_STREAM)
    }
    return {STREAMS_MEMBER: shown, RELEASED_MEMBER: body.get(RELEASED_MEMBER)}


def course_summary(body: Any) -> dict[str, Any] | None:
    """The course stream's summary in one served report, less its response count."""
    summary = body[STREAMS_MEMBER][PAYLOAD_STREAM_KEY[COURSE_STREAM]][SUMMARY_FIELD]
    if summary is None:
        return None
    return {member: summary.get(member) for member in SUMMARY_FROM_COMMENTS}


def test_a_self_harm_comment_in_a_three_response_week_opens_a_case_and_changes_nothing_shown(
    decision_door: DecisionDoor, mock_gateway: Any
) -> None:
    door = decision_door
    assert door.door.rows.responses_in(WELFARE_WEEK) == RESPONSES_IN_WEEK[WELFARE_WEEK] == 2, (
        f"Course week {WELFARE_WEEK} should hold two responses before the comment, so that "
        "the comment's response makes it the exit clause's three-response week."
    )
    before = door.payload(WELFARE_WEEK)

    answer_id = door.plant_a_comment(
        course_week=WELFARE_WEEK, stream=COURSE_STREAM, text=WELFARE_COMMENT, verdict=None
    )
    assert door.door.rows.responses_in(WELFARE_WEEK) == 3, (
        f"Course week {WELFARE_WEEK} does not hold three responses after the comment's, so this "
        "is not the exit clause's three-response week."
    )

    from app.config import Settings
    from app.services.moderation import sweep_unmoderated_comments
    from app.services.reporting import generate_missing_summaries

    sweep_unmoderated_comments(door.session, mock_gateway)
    generate_missing_summaries(door.session, settings=Settings(), gateway=mock_gateway)
    door.door.refresh()

    verdicts = [row["verdict"] for row in moderation_verdicts(door.session, answer_id)]
    assert verdicts == [SELF_HARM], (
        f"The sweep left the comment with the verdicts {verdicts}, not the one self-harm verdict "
        "the mock provider answers to its marker. Without it nothing below is about a "
        "self-harm comment."
    )
    cases = threat_cases(door.session, answer_id)
    assert len(cases) == 1, (
        f"`threat_case` holds {len(cases)} rows for the self-harm comment. SPEC §6.2 routes every "
        "threat or self-harm comment to Care, and the routing definer opens one case per comment "
        "(ADR 0187)."
    )

    after = door.payload(WELFARE_WEEK)
    assert comment_bearing(after) == comment_bearing(before), (
        f"Course week {WELFARE_WEEK}'s report changed in a member that shows or counts comments "
        "once the self-harm comment was moderated. SPEC §6.2: the comment leaves no trace in any "
        f"instructor view.\nBefore: {comment_bearing(before)}\nAfter: {comment_bearing(after)}"
    )
    welfare_summary = course_summary(after)
    quiet_summary = course_summary(door.payload(NO_COMMENT_WEEK))
    assert welfare_summary is not None and quiet_summary is not None, (
        f"The summary walk stored no course-stream summary for course week {WELFARE_WEEK} "
        f"({welfare_summary}) or {NO_COMMENT_WEEK} ({quiet_summary}), so there is no sentence "
        "to compare."
    )
    assert welfare_summary == quiet_summary, (
        f"Course week {WELFARE_WEEK}'s course-stream summary is {welfare_summary}, and course "
        f"week {NO_COMMENT_WEEK}'s, where nobody wrote a course comment, is {quiet_summary}. The "
        "self-harm comment reached the summary, or the empty-week sentence tells the two apart."
    )
    leaked = [value for value in strings_in(after) if WELFARE_WORDS in value]
    assert not leaked, f"The served report carries the self-harm comment's words: {leaked}."

    canary = door.payload(FULL_WEEK)
    shown = {
        card[COMMENT_TEXT_FIELD]
        for card in canary[STREAMS_MEMBER][PAYLOAD_STREAM_KEY[INSTRUCTOR_STREAM]][COMMENTS_FIELD]
    }
    assert shown == set(FULL_WEEK_COMMENTS), (
        f"The canary: course week {FULL_WEEK} of the same world shows {sorted(shown)}, not its "
        "five comments, so the absence above could be a report that shows nothing at all."
    )
