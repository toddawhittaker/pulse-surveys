"""The weekly summary, end to end against the mock provider — E4-05.

E4-05's first acceptance criterion, in full: "the task round-trips against the
mock AI service in CI: typed contract validated, shape violations retried,
persistent failure surfacing as the gateway's error, never as prose passed
through." This module is that round trip, over a real socket, through the tool's
own configuration and its own gateway — nothing here patches the backend, and the
task builds its own gateway from `Settings` exactly as E4-06's job will.

**The endpoint is the mock's own application on a loopback socket**, the harness
`tests/fixtures/mock_ai.py` describes: it reproduces the mock's routing, handlers,
statuses, bodies and delays over a connection the gateway opens itself, and
reproduces neither uvicorn nor the container. What it also gives is the count of
completion requests the gateway made, which is how two of the four assertions
below are made at all — "no call was made" and "exactly one re-ask" are both
properties of the wire rather than of a return value.

**What is asserted here and not at the unit level**: that the whole configured
path works, that a shape violation costs exactly one re-ask and then raises, and
that nothing about the week's comments reaches the failure. What is asserted at
the unit level instead (`tests/unit/test_the_weekly_summary_task.py`) is
everything that needs a provider to answer something specific — the refusal of an
answer about the wrong stream, and a provider outage propagating rather than being
summarized away. Driving those from here would need selectors the mock does not
publish, and inventing one would be this suite deciding an interface the ticket
leaves to the implementer.

**Whether the summary is any good is asked nowhere in pytest.** SPEC §9.3 answers
that with an eval set and a floor; `tests/evals/summary/` holds the cases and
E4-05 stages the floor. The mock reads a marker and derives an answer, so a stack
pointed at it is a stack that is not summarizing anything (ADR 0113 is why nothing
outside development may point at it).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fixtures.clock import DEVELOPMENT, ENVIRONMENT_VARIABLE
from fixtures.mock_ai import (
    MOCK_AI_PROVIDER_BASE_URL_VARIABLE,
    MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE,
    Endpoint,
    MockAiProvider,
)
from fixtures.summary_task import (
    INSTRUCTOR_STREAM,
    RESPONSE_INVALID_ERROR,
    WEEKLY_SUMMARY_OUTPUT,
    SummaryApi,
    call_summarize,
)

pytestmark = pytest.mark.integration

# The model the gateway is configured to ask for. The mock echoes what it was
# asked for in the completion envelope, so this is a value *this test chose*
# arriving back through the provider — which is what makes the recorded model id
# evidence rather than a constant agreeing with itself.
MODEL_NAME = "mock-summary-v1-e4-05"

# The prompt version the eval set is pinned to, imported from the set rather than
# from `app.ai.tasks`. It is the independent copy: a record whose prompt version
# is read back out of the same constant the task rendered under would agree with
# itself whatever either said (`docs/MISTAKES.md` entry 19).
EVAL_SET_MODULE = "tests.evals.summary.cases"

# One stream's week. Ordinary comments, no markers, nothing identifying.
A_WEEK = (
    "The Thursday proofs went by too quickly to write anything down.",
    "Office hours were genuinely helpful once I got there.",
    "Please post the derivations afterwards if the pace has to stay.",
)
RESPONSES_THAT_WEEK = 9

# A comment made of tokens that appear nowhere else in this repository, for the
# test asking whether a failure quotes the week back into its message.
NEEDLE_COMMENT = "Rb9NsWqvZm Xt4LdKj3Px E8mZt5UwGh Tf2YcRbVn8"
NEEDLE_CHUNKS = tuple(NEEDLE_COMMENT.split())


@pytest.fixture
def gateway_against_the_mock(
    monkeypatch: pytest.MonkeyPatch,
    care_service_environment: dict[str, str],
    mock_ai_endpoint: Endpoint,
) -> Endpoint:
    """Point the tool's own configuration at the mock, and say which environment it runs in.

    The twin of `gateway_against_the_mock` in
    `tests/integration/test_mock_ai_gateway_taxonomy.py`, and it is a second copy
    because that one lives in a test module rather than in a fixture file; folding
    the two together is a tidy-up for a ticket whose subject is that module.

    `care_service_environment` is depended on for what it does rather than for
    what it is named: it applies `.env.example`'s whole surface and then overwrites
    the database variables with the test container's, which is what any `app.*`
    import reaching `app.db` needs. `ENVIRONMENT` is set rather than inherited
    (`docs/MISTAKES.md` entry 40), and it is what decides that the `MOCK_*` triple
    is the one a gateway built here reads.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, DEVELOPMENT)
    monkeypatch.setenv(MOCK_AI_PROVIDER_BASE_URL_VARIABLE, mock_ai_endpoint.base_url)
    monkeypatch.setenv(MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE, MODEL_NAME)
    return mock_ai_endpoint


def eval_set() -> ModuleType:
    """The summary eval set, imported with the repository root on `sys.path`.

    pytest puts `tests/` on the path and not the root, while `tests.evals.*` is
    addressed from the root — the same two lines, for the same reason, as
    `tests/unit/test_the_planted_floor_breach_can_be_demonstrated.py`.
    """
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module(EVAL_SET_MODULE)


def summarize(api: SummaryApi, comments: tuple[str, ...], response_count: int) -> object:
    """One stream's week, through the task's own gateway and the configured endpoint."""
    return call_summarize(
        api.task(),
        comments,
        stream=api.stream(INSTRUCTOR_STREAM),
        response_count=response_count,
    )


def test_a_weeks_comments_round_trip_into_a_validated_record(
    gateway_against_the_mock: Endpoint,
    summary_api: SummaryApi,
) -> None:
    """Acceptance criterion 1's first clause, and criterion 6 with it.

    "Typed contract validated" — the object that comes back is the contract, built
    from what a provider said over a real connection, with the audit pair the
    gateway supplied. Criterion 6 rides on the same call: "prompt version and
    model id flow through the task's return so E4-06 can store them without
    re-deriving."

    **The model id is the value this test configured**, echoed by the provider and
    recorded by the gateway. A model id read from configuration and one read from
    the response envelope are the same string here on purpose — what is asserted
    is that the record names the model that answered, and a record naming
    something else names a call that did not happen.

    **The prompt version is compared against the eval set's pin**, not against the
    constant the task rendered under. Those two are held against each other by
    `tests/unit/test_the_summary_eval_cases_can_go_red.py`; comparing the record
    against the constant that produced it would be a comparison of the code with
    itself.

    **The mutation this kills:** a task that returns the provider's prose, or a
    dict, or an object missing the audit pair — each of which E4-06 would store as
    a summary and each of which reads as success from the job's side.
    """
    module = eval_set()
    output_model = summary_api.contract(WEEKLY_SUMMARY_OUTPUT)

    record = summarize(summary_api, A_WEEK, RESPONSES_THAT_WEEK)

    assert len(gateway_against_the_mock.completions) == 1, (
        f"the gateway made {len(gateway_against_the_mock.completions)} completion requests for "
        "one stream's week. SPEC §7.4: one call in, one validated object out — and a count of "
        "zero means nothing reached the endpoint and every assertion below is about a value "
        "computed on this machine."
    )
    assert isinstance(record.summary, output_model), (
        f"the task answered with {record.summary!r}, which is not a "
        f"`{WEEKLY_SUMMARY_OUTPUT}`. §7.4: 'every task declares its output as a Pydantic model "
        "rather than parsed JSON', and the gateway validates against it."
    )
    assert record.summary.summary.strip(), "the record carries an empty summary."
    assert record.response_count == RESPONSES_THAT_WEEK
    assert record.summary.prompt_version == module.PROMPT_VERSION, (
        f"the record was produced under {record.summary.prompt_version!r} and the eval set is "
        f"pinned to {module.PROMPT_VERSION!r}. ADR 0032 makes a committed prompt immutable, so "
        "these are two different texts and a measurement over the set would be about neither."
    )
    assert record.summary.model_id == MODEL_NAME, (
        f"the record names {record.summary.model_id!r} as the model that answered, and this "
        f"test configured {MODEL_NAME!r}. E4-06 stores this value as half of §7.4's audit pair."
    )


def test_a_two_comment_week_is_summarized_like_any_other(
    gateway_against_the_mock: Endpoint,
    summary_api: SummaryApi,
) -> None:
    """Acceptance criterion 4's other half: "two comments in, a summary out".

    SPEC §5.1 makes this the case that matters most: summaries "are generated
    **even in small-N weeks** — there, the summary is the only comment signal".
    §4 hides the raw comments from the instructor below the threshold, so a task
    that treated a thin week as not worth a call would leave that instructor with
    nothing at all — not a thinner report, an empty one.

    **The mutation this kills:** a minimum comment count in the task, which is a
    plausible thing to add beside the empty-week short-circuit and which silently
    removes the signal §4's small-N rule promises. **Its pair is the empty-week
    test below**, which is the only count that may skip the call.
    """
    small_week = (A_WEEK[0], A_WEEK[1])
    before = len(gateway_against_the_mock.completions)

    record = summarize(summary_api, small_week, 2)

    assert len(gateway_against_the_mock.completions) - before == 1, (
        f"a two-comment week cost {len(gateway_against_the_mock.completions) - before} "
        "completion request(s). §4: 'comments from under-threshold weeks are not discarded — "
        "they feed the summary'."
    )
    assert record.summary.summary.strip(), (
        "a two-comment week came back with no summary text. Below the n-threshold this is the "
        "only comment signal the instructor gets."
    )


def test_a_week_with_no_comments_reaches_the_provider_not_at_all(
    gateway_against_the_mock: Endpoint,
    summary_api: SummaryApi,
) -> None:
    """The empty-week short-circuit, measured on the wire rather than on the answer.

    E4-05's fourth criterion says what comes back; this says what does not go out.
    The two are different claims, and only the second one costs money: an empty
    stream is common — §5.1's empty group "shows a one-line notice" — and a
    request per empty stream per section per week is a bill nobody chose.

    **Both halves are in one test on purpose.** A request counter that had stopped
    recording would report zero for everything, so the same counter is watched
    going up on a week that *does* have comments, in the same process and against
    the same endpoint. Without that, this test passes against a stack that reaches
    nothing at all (`docs/MISTAKES.md` entry 3).
    """
    before = len(gateway_against_the_mock.completions)

    record = summarize(summary_api, (), 0)

    assert len(gateway_against_the_mock.completions) == before, (
        f"a week with no comments cost {len(gateway_against_the_mock.completions) - before} "
        "completion request(s). There is nothing to summarize, and asking anyway is the "
        "request most likely to come back with something invented."
    )
    assert (
        tuple(record.summary.themes) == ()
    ), f"the empty week came back with themes: {list(record.summary.themes)}."

    summarize(summary_api, A_WEEK, RESPONSES_THAT_WEEK)
    assert len(gateway_against_the_mock.completions) > before, (
        "the canary for the count above: a week that does have comments also reached the "
        "endpoint zero times, so this test is measuring a recorder that is not recording."
    )


def test_a_persistently_malformed_answer_is_re_asked_once_and_then_raises(
    gateway_against_the_mock: Endpoint,
    mock_ai: MockAiProvider,
    summary_api: SummaryApi,
) -> None:
    """Acceptance criterion 1's second and third clauses, in one place.

    "Shape violations retried, persistent failure surfacing as the gateway's
    error, never as prose passed through." §7.4 is the rule and ADR 0053 makes the
    retry exactly one bounded re-ask made by the gateway itself, rather than the
    library's feedback loop — which would append a message after the one ending in
    the week's comments and break the injection boundary
    `backend/app/ai/prompts/README.md` rests on.

    **The mock is stateless, so the re-ask gets the same wrong answer**, which is
    what makes "then the error" reachable at all.

    **Both halves are asserted and neither is enough alone.** The error alone
    passes against a gateway that never retried, which would fail a whole week's
    summary on one bad answer; the count alone passes against a gateway that
    retried and then returned something. The count is asserted as exactly two,
    because an unbounded re-ask against a permanently malformed provider is a
    Monday-report job that never finishes.

    **The malformed answer is driven by the marker the mock publishes**, which is
    how E4-05's criterion 1 is reachable at all: it asks for the shape-violation
    path to be exercised "against the mock AI service in CI", so the mock's
    wrong-answer selectors have to reach the summary task as well as the validity
    one.
    """
    invalid = summary_api.error(RESPONSE_INVALID_ERROR)
    marker = mock_ai.marker_for("malformed")
    before = len(gateway_against_the_mock.completions)

    with pytest.raises(invalid):
        summarize(summary_api, (f"{marker} the pacing was fine this week", *A_WEEK), 4)

    asked = len(gateway_against_the_mock.completions) - before
    assert asked == 2, (
        f"the gateway made {asked} completion requests for a week the provider answered "
        "malformedly. §7.4 has it retry a shape violation and ADR 0053 makes that exactly one "
        "bounded re-ask — one request is a gateway that does not retry, and three or more is "
        "one that does not stop."
    )


def test_the_failure_does_not_carry_the_weeks_comments(
    gateway_against_the_mock: Endpoint,
    mock_ai: MockAiProvider,
    summary_api: SummaryApi,
) -> None:
    """SPEC §10 and E3's decision 10, at the boundary E4-06's job will log.

    "No student PII in logs." A Monday-report job catches what this raises and
    writes it somewhere; a message built by interpolating the prompt, or the
    payload that violated the contract, puts a week of a section's comments into
    that log. E0-13's roundtrip module found the same defect on the validity path
    — a shape-violation message built from the keys of the payload that violated
    it, which reassembles a comment when a model returns one as field names.

    **The needle is asserted to have reached the provider first.** A message
    cannot leak text that was never sent, so without the canary this passes
    against a stack that summarized nothing.

    **The whole exception chain is read**, because a polite message raised `from`
    one that quotes everything leaks exactly as much.
    """
    invalid = summary_api.error(RESPONSE_INVALID_ERROR)
    marker = mock_ai.marker_for("malformed")

    with pytest.raises(invalid) as raised:
        summarize(summary_api, (NEEDLE_COMMENT, f"{marker} bring back the malformed answer"), 2)

    sent = "\n".join(str(request) for request in gateway_against_the_mock.completions)
    assert NEEDLE_COMMENT in sent, (
        "the needle comment never reached the endpoint, so an assertion that the failure does "
        "not carry it would pass against a stack that sent nothing."
    )

    chain: list[BaseException] = []
    current: BaseException | None = raised.value
    while current is not None and not any(link is current for link in chain):
        chain.append(current)
        current = current.__cause__ or current.__context__
    said = "\n".join(str(link) for link in chain)

    leaked = sorted(chunk for chunk in NEEDLE_CHUNKS if chunk in said)
    assert not leaked, (
        f"the failure's message chain carries {leaked} out of a student's comment. The whole "
        f"chain said: {said[:400]!r}"
    )
