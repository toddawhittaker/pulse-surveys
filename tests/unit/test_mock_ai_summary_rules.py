"""What the mock AI provider answers for a weekly-summary prompt — E4-05.

E4-05's first acceptance criterion is that "the task round-trips against the mock
AI service in CI", and its trap list says why this module exists: "the mock AI
service needs the new task — check what the mock answers for an unknown task
before assuming". Today it answers one: `mock-ai/app/rules.py` extracts the
student's comment at the *validity* prompt's marker line and refuses anything else
with a 500 naming the line it looked for. A summary prompt carries neither that
line nor one comment, so the mock has to learn a second boundary or every summary
in a development stack is an extraction failure.

**This module asks what the mock answers; the gateway's reaction to it is
`tests/integration/test_ai_gateway_summary_roundtrip.py`'s subject.** The same
split `tests/unit/test_mock_ai_rules.py` and
`tests/integration/test_mock_ai_gateway_taxonomy.py` already keep, for the same
reason: what a mock says and what the tool does about it are different questions
with different repairs.

**The vocabulary is read from the mock and the shape from the contract.** E2-07's
third acceptance criterion makes the mock's rules served rather than copied, so
the summary marker line comes out of `GET /mock/rules`; and the answer's shape is
checked by building the real `WeeklySummaryOutput` out of it, which is stronger
than any key list this file could hold — the mock and the tool are two programs,
and the contract is the specification of the wire between them.

**What is deliberately not asserted.** Whether the mock's summaries are any good.
E2-07 puts eval use out of scope for exactly this reason: "a mock that passed
evals would be measuring itself". The mock derives a deterministic answer from the
comments it was sent, and that is all it is for.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fixtures.mock_ai import MockAiProvider, payload_of
from fixtures.summary_task import (
    COURSE_STREAM,
    INSTRUCTOR_STREAM,
    SUMMARY_PROMPT_VERSION,
    WEEKLY_SUMMARY_OUTPUT,
    SummaryApi,
)

# Two weeks of invented comments for one stream. They differ in every word, so an
# answer that is the same for both is a mock that is not reading them.
A_WEEK = (
    "The Thursday proofs went by too quickly to write anything down.",
    "Office hours were genuinely helpful once I got there.",
    "Please post the derivations afterwards if the pace has to stay.",
)
ANOTHER_WEEK = (
    "The reading list points at a chapter the library does not hold.",
    "The lab handout and the slides use different notation for the same quantity.",
)

# A line no prompt in this repository contains, for the drift matcher's control.
NOT_A_PROMPT_LINE = "### Kj3PxE8mZt5UwGh — this line is in no prompt file ###"

# The two fields ADR 0031 forbids a model to report, in every spelling they could
# arrive under. The gateway supplies both and rejects a payload carrying either
# before merging anything into it, so a mock that helpfully filled them in would
# be refused by a correct gateway on every call.
AUDIT_KEYS = ("prompt_version", "promptversion", "model_id", "modelid", "model")

# The member the comment-validity payload spells its verdict under. Here only as
# the thing a summary answer must *not* be: a mock that fell through to its old
# rule would answer a well-formed verdict to a summary request, and the tool would
# report it as a shape violation in the summary prompt.
VERDICT_KEY = "verdict"

# What the test supplies for the audit pair when it validates a payload, standing
# in for what the gateway supplies on a real call.
A_PROMPT_VERSION = "summary.v1"
A_MODEL_ID = "e4-05-mock-rules-test"


def summary_prompt(api: SummaryApi, stream_token: str, comments: tuple[str, ...]) -> str:
    """One week of one stream, rendered through the application's own renderer.

    Rendered rather than assembled here, because the boundary the mock dispatches
    on is a line of the real prompt: a hand-built prompt would let this module
    pass against a mock that had drifted away from the text the tool sends, which
    is `docs/MISTAKES.md` entry 9's shape and the defect the validity marker's
    drift test was written after.
    """
    return api.render()(
        api.constant(SUMMARY_PROMPT_VERSION),
        stream=api.stream(stream_token),
        comments=comments,
    )


def summary_payload(response: Any) -> dict[str, Any]:
    """The summary payload one completion carries, or a failure saying what it carried."""
    payload = payload_of(response)
    assert isinstance(payload, dict), (
        f"The completion's content parsed to {payload!r}, which is not an object. The mock "
        "answers with the weekly-summary payload, and that is a JSON object."
    )
    return payload


def test_the_mock_publishes_a_summary_marker_line_distinct_from_the_validity_one(
    mock_ai: MockAiProvider,
) -> None:
    """E2-07's third criterion, applied to the task E4-05 adds.

    "The mock's rules are served, not copied: its README/route states them, and
    the tests that aim at them read the served statement." A second task needs a
    second boundary, and a boundary nobody can read from outside is one every
    caller has to guess at.

    **The two lines must differ**, which is the assertion with teeth here. A mock
    publishing one marker for both tasks cannot dispatch on it: every summary
    prompt would be read as a comment and answered with a verdict, and every
    verdict would validate against nothing on the tool side.

    **The mutation this kills:** a summary marker that is the validity marker, or
    a rules document that gained the summary behaviour and not the statement of
    it.
    """
    summary_line = mock_ai.summary_marker_line().strip()
    validity_line = mock_ai.marker_line().strip()

    assert summary_line, "`GET /mock/rules` publishes an empty summary marker line."
    assert summary_line != validity_line, (
        f"the mock publishes {summary_line!r} for both tasks. It dispatches on the marker, so "
        "one line for two tasks is a mock that cannot tell a summary request from a validity "
        "one."
    )


def test_the_published_summary_marker_is_a_line_of_the_summary_prompt(
    configured_env: dict[str, str],
    summary_api: SummaryApi,
    mock_ai: MockAiProvider,
) -> None:
    """The drift test, the one `tests/unit/test_mock_ai_rules.py` already keeps for validity.

    The mock cannot import `backend/app/` — both packages are called `app` (SPEC
    §13, ADR 0039) — so the line it dispatches on is a second copy of a string
    that lives in the prompt. E1-07's lesson is that a second copy is fine when
    something holds it against the first and fatal when nothing does: a reworded
    prompt would leave every summary in a development stack answering an
    extraction failure, with nothing red.

    **Which prompt is asked of the application rather than written down here.**
    ADR 0032 keeps every committed prompt on disk forever, so a path pinned to
    `summary.v1.md` goes on passing after the tool has moved to `summary.v2` —
    guarding a file nothing sends while the drift it exists to catch runs loose.

    **The matcher is run in both directions** (`docs/MISTAKES.md` entry 3): a line
    that is certainly in no prompt must not match, or a comparison that had gone
    blind would report agreement between two strings with nothing to do with each
    other.
    """
    path = summary_api.prompt_path()
    assert path.is_file(), (
        f"{path} does not exist, so this test compares the mock's marker against nothing. The "
        "path comes from `app.ai.tasks.SUMMARY_PROMPT_VERSION`, which is the prompt the tool "
        "renders."
    )
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    assert (
        len([line for line in lines if line]) > 5
    ), f"{path} holds {len(lines)} lines, which is not a prompt."

    marker = mock_ai.summary_marker_line().strip()
    assert marker in lines, (
        f"the mock publishes {marker!r} as the line the week's comments follow, and no line of "
        f"{path.name} is that string. The mock reads the week as everything after that "
        "marker's last occurrence, so a prompt that no longer carries it hands the mock a "
        "prompt it cannot read."
    )
    assert NOT_A_PROMPT_LINE not in lines, (
        "the control for the comparison above: a line certainly in no prompt was reported as "
        "present, so the membership test is matching something other than what it reads."
    )


def test_a_summary_prompt_is_answered_with_the_summary_contract(
    configured_env: dict[str, str],
    summary_api: SummaryApi,
    mock_ai: MockAiProvider,
) -> None:
    """The answer validates as the contract, which is the whole of what the wire owes.

    §7.4: "every task declares its output as a Pydantic model rather than parsed
    JSON. The gateway validates against that model." So the strongest thing this
    module can say about the mock's answer is that the real contract accepts it —
    stronger than any key list held here, and it cannot drift, because the
    contract is what the tool will judge the answer by.

    **The audit pair is supplied by this test, not by the mock**, and its absence
    from the payload is asserted: ADR 0031 has the gateway supply both and reject
    a payload carrying either, so a helpful mock would be refused on every call
    and the failure would read as a shape violation in the summary prompt.

    **The mutation this kills:** the mock falling through to its validity rule and
    answering a verdict, which is what it does today for any prompt whose marker
    it does not know; and a summary-shaped payload that is not the contract's — an
    extra field, a theme with no count, a missing stream.
    """
    output_model = summary_api.contract(WEEKLY_SUMMARY_OUTPUT)

    response = mock_ai.post(summary_prompt(summary_api, INSTRUCTOR_STREAM, A_WEEK))
    payload = summary_payload(response)

    assert VERDICT_KEY not in payload, (
        f"the mock answered {payload!r} to a summary prompt, which carries a comment-validity "
        "verdict. That is the mock falling through to its old rule."
    )
    for name in AUDIT_KEYS:
        assert name not in payload, (
            f"the answer carries {name!r}. ADR 0031 forbids a model to report the prompt "
            "version or the model id; the gateway supplies both and rejects a payload naming "
            "either."
        )

    validated = output_model(**payload, prompt_version=A_PROMPT_VERSION, model_id=A_MODEL_ID)
    assert (
        validated.summary.strip()
    ), f"the mock's answer validated with an empty summary: {payload!r}."


@pytest.mark.parametrize("stream_token", (INSTRUCTOR_STREAM, COURSE_STREAM))
def test_the_answer_names_the_stream_the_prompt_asked_about(
    configured_env: dict[str, str],
    summary_api: SummaryApi,
    mock_ai: MockAiProvider,
    stream_token: str,
) -> None:
    """Both streams, because a mock that answers one of them is a mock that guessed.

    E4-05 refuses an answer whose stream is not the stream that was asked for, so
    a mock that always answered `instructor` would make every course-stream
    summary in a development stack a refusal — and a suite that asked only about
    the instructor stream would call that mock correct.

    **The mutation this kills:** a constant stream in the mock's answer, and a
    stream read from the wrong end of the prompt. **Its pair is the other
    parametrised row**, and neither row is worth anything alone.
    """
    response = mock_ai.post(summary_prompt(summary_api, stream_token, A_WEEK))
    payload = summary_payload(response)

    answered = str(payload.get("stream", "")).lower()
    assert answered == stream_token, (
        f"a prompt about the {stream_token!r} stream was answered about {answered!r}. SPEC "
        "§5.1 groups comments under 'About the instructor' / 'About the course', and E4-05 "
        "refuses an answer about the other one."
    )


def test_the_same_week_is_summarized_the_same_way_and_two_weeks_are_not(
    configured_env: dict[str, str],
    summary_api: SummaryApi,
    mock_ai: MockAiProvider,
) -> None:
    """Deterministic, and derived from the comments rather than constant.

    E2-07's design rule for this service is that "every request is decided by its
    own comment and by nothing this process remembers", which is what makes the
    gateway's bounded re-ask reach the same answer twice and the error path
    reachable at all. E4-05 asks for the same of the summary task: an answer
    derived from the extracted comments.

    **Both halves, and the second is the one with teeth.** A mock that answered
    one canned summary to everything is perfectly deterministic, and a test
    asserting only determinism would report it as correct — after which nothing in
    the suite would notice that the week's comments never reached the provider at
    all.

    **The mutation this kills:** a constant answer, and an answer derived from
    something other than the comments (the prompt's length, the stream alone).
    """
    once = summary_payload(mock_ai.post(summary_prompt(summary_api, INSTRUCTOR_STREAM, A_WEEK)))
    twice = summary_payload(mock_ai.post(summary_prompt(summary_api, INSTRUCTOR_STREAM, A_WEEK)))
    other = summary_payload(
        mock_ai.post(summary_prompt(summary_api, INSTRUCTOR_STREAM, ANOTHER_WEEK))
    )

    assert json.dumps(once, sort_keys=True) == json.dumps(twice, sort_keys=True), (
        "the same week was summarized two different ways. The gateway re-asks once on a shape "
        "violation, and a mock that answers differently each time makes that path — and every "
        "assertion about it — a race."
    )
    assert json.dumps(once, sort_keys=True) != json.dumps(other, sort_keys=True), (
        f"two different weeks were summarized identically: {once!r}. The answer is not derived "
        "from the comments, so nothing that passes through this mock proves the week's text "
        "ever left the tool."
    )


def test_no_theme_claims_more_comments_than_the_week_holds(
    configured_env: dict[str, str],
    summary_api: SummaryApi,
    mock_ai: MockAiProvider,
) -> None:
    """The one arithmetic a mock's themes still have to get right.

    A theme claiming four comments in a week of two is a number E4-10 renders and
    E7's draft check reads (§5.3, "with its comment count"). The mock invents its
    themes, which is fine — it decides nothing — but a count larger than the week
    is a number no reading of the week supports, and a development stack showing
    one teaches everybody who sees it that the figure means nothing.

    **The week here is the two-comment one on purpose**, so a mock that emitted a
    fixed count of three fails. **The mutation this kills:** exactly that fixed
    count, which is the natural way to write a canned theme list.
    """
    payload = summary_payload(
        mock_ai.post(summary_prompt(summary_api, COURSE_STREAM, ANOTHER_WEEK))
    )

    themes = payload.get("themes")
    assert isinstance(
        themes, list
    ), f"the answer carries {themes!r} as its themes; the contract's field is a sequence."
    for theme in themes:
        count = theme.get("comment_count") if isinstance(theme, dict) else None
        assert isinstance(count, int) and 1 <= count <= len(
            ANOTHER_WEEK
        ), f"a theme claims {count!r} of {len(ANOTHER_WEEK)} comments: {theme!r}."


def test_a_validity_prompt_still_gets_a_verdict(
    configured_env: dict[str, str],
    summary_api: SummaryApi,
    mock_ai: MockAiProvider,
) -> None:
    """The near miss for the whole dispatch: the task that was already there still works.

    Two markers, two answers, and the risk of adding the second is that the first
    stops being reachable — a dispatch that checks the summary marker with `in`
    against a prompt that quotes it, or a rules document whose new member shadows
    the old one, sends every comment-validity request down the summary path. E2's
    whole submit path runs through that request.

    **The mutation this kills:** the summary branch taken for any prompt, and the
    validity branch removed as "replaced". **Its pair is every summary assertion
    above**, so this cannot be satisfied by a mock that ignored E4-05 entirely:
    those tests fail if the summary path is missing, and this one fails if it ate
    the other.
    """
    response = mock_ai.ask("The pacing in week three was too fast for the lab work.")
    payload = payload_of(response)

    assert isinstance(payload, dict) and VERDICT_KEY in payload, (
        f"a comment-validity prompt was answered {payload!r}, which carries no verdict. Adding "
        "the summary task must not take the task E2's submit path depends on with it."
    )
    assert (
        "themes" not in payload
    ), f"a comment-validity prompt was answered with a summary payload: {payload!r}."
