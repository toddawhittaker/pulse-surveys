"""What the real gateway does with the mock's deliberately wrong answers — E2-07.

E2-07's second acceptance criterion, in full: "The wrong-answer selectors work:
one e2e-reachable path each for unavailable (a stall past the budget, and a 503 —
the floor applies), refused (a 500 — E2-08's recorded behavior, not the floor),
and malformed shape (one retry, then the error surface), driven from the mock,
asserted from the tool side."

**Asserted from the tool side** is the phrase that puts these tests here rather
than beside the rest of the mock's behaviour in
`tests/unit/test_mock_ai_rules.py`. That module asks what the mock answers; this
one asks what the *classifier* does when it hears it, which is the only question
whose answer differs between a 503 and a 500. ADR 0056's table is what they
differ by: 503 is "the endpoint says it cannot serve now" and floors, 500 is
"answered about the request" and raises, and the record spends a paragraph on why
500 in particular is outside the floor ("a 500 means our request is the problem"
far more often than an outage). Those two rows are one status code apart and are
the reason the mock mints both — E2-08's tests need the near miss.

**Nothing here patches the backend.** The ticket's own point is that "the gateway
cannot tell this mock from a provider", so every case below is driven by the
comment text alone, through ordinary configuration: a provider base URL pointed at
an endpoint. The endpoint is the mock's own application on a loopback socket
(`tests/fixtures/mock_ai.py` says what that harness reproduces and what it does
not).

**Which variable that is moved on 2026-09-02, and the reason is the name rather
than any new test.** The configuration split gives the real provider and the
in-repo mock a triple each — `AI_PROVIDER_{API_KEY,BASE_URL,MODEL_NAME}` and
`MOCK_AI_PROVIDER_{API_KEY,BASE_URL,MODEL_NAME}` — and strikes `AI_MODEL_NAME`,
which said which model without saying whose. This module's fixture below states
`ENVIRONMENT=development` in its own body and points at the `mock-ai`
application, so the side it exercises is not an inference: it is the mock's, and
the ruled names for the mock's side are the `MOCK_*` ones. The base URL moves with
the model name because the two describe one endpoint — a model name from one
triple beside a base URL from the other is not a repair, it is a gateway
configured half from each.

E2-07's claim is untouched by any of this. The gateway still cannot tell this
service from a provider by anything it *answers*; what the split changes is which
variable tells the gateway where to look.

**The markers are read from the mock, not written here.** Acceptance criterion 3,
and the one deliberate copy of the vocabulary this ticket allows lives in
`tests/unit/test_mock_ai_rules.py` beside the test that diffs it.

**Each floored case is written so that the floor's answer differs from the
answer the mock would have given.** A test that only asserted "it did not raise"
would pass against a gateway that quietly returned the provider's verdict, and a
test whose floored verdict happened to match the mock's would be green either
way (`docs/MISTAKES.md` entry 3). ADR 0054's `character-floor` marker is the
other way to tell them apart, and this module deliberately does not use it: the
verdict is observable to E2's submit path, the audit pair's spelling is that
record's to change, and a test that pinned the string would be red for a rename.
"""

import time
from collections.abc import Callable
from typing import Any

import pytest
from fixtures.clock import DEVELOPMENT, ENVIRONMENT_VARIABLE
from fixtures.mock_ai import (
    INSUFFICIENT,
    MOCK_AI_PROVIDER_BASE_URL_VARIABLE,
    MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE,
    SUBSTANTIVE,
    Endpoint,
    MockAiProvider,
)

pytestmark = pytest.mark.integration

# The gateway's per-task timeout, measured and recorded in ADR 0053's
# consequences. Acceptance criterion 1 is "no 4s stall", so this is the number a
# healthy classification has to come back well inside.
GATEWAY_BUDGET_SECONDS = 4.0

# The model the gateway is configured to ask for. Any string does; a distinctive
# one keeps a failure message unambiguous about where the value came from.
MODEL_NAME = "mock-validity-v1"

# SPEC §3.3's own example of a comment that must be bounced, and a comment that
# is unambiguously substantive. Both are unmarked, so both are classified by the
# mock's published length rule — which is what makes criterion 1's "classifies
# deterministically" checkable at all.
SPEC_INSUFFICIENT_COMMENT = "it was okay"
ORDINARY_LONG_COMMENT = "The pacing in week three was too fast for the lab work."

# A comment short enough that the character floor calls it insufficient, used
# wherever a floored answer has to be distinguishable from the mock's own. Kept
# short deliberately: the stall marker answers `substantive` when it finally
# answers, so a floored result and an answered one differ.
SHORT_TAIL = "ok"


@pytest.fixture
def gateway_against_the_mock(
    monkeypatch: pytest.MonkeyPatch,
    care_service_environment: dict[str, str],
    mock_ai_endpoint: Endpoint,
) -> Endpoint:
    """Point the tool's own configuration at the mock, and say which environment it runs in.

    `care_service_environment` is depended on for what it does rather than for
    what it is named: it applies `.env.example`'s whole surface and then
    overwrites the database variables with the test container's, which is what any
    `app.*` import reaching `app.db` needs.

    `ENVIRONMENT` is set rather than inherited (`docs/MISTAKES.md` entry 40).
    The address here is a loopback one, which every environment accepts, so
    nothing below turns on the value — but E2-07 makes `ENVIRONMENT` decide
    whether a provider base URL is refused at all, and a suite that left it
    to whatever `.env.example` happened to say would be one edit away from
    failing in its own setup.

    **It is also what decides which triple these two lines belong to.** The
    configuration split ruled on 2026-09-02 has a gateway read the
    `MOCK_AI_PROVIDER_*` triple in development and test, so a fixture that
    declares itself development and points at the `mock-ai` application is the
    mock's side by its own statement rather than by inference. The value the
    variable carries has not changed, and neither has anything this module
    asserts.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, DEVELOPMENT)
    monkeypatch.setenv(MOCK_AI_PROVIDER_BASE_URL_VARIABLE, mock_ai_endpoint.base_url)
    monkeypatch.setenv(MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE, MODEL_NAME)
    return mock_ai_endpoint


@pytest.mark.parametrize(
    ("comment", "expected"),
    ((SPEC_INSUFFICIENT_COMMENT, INSUFFICIENT), (ORDINARY_LONG_COMMENT, SUBSTANTIVE)),
)
def test_a_comment_is_classified_through_the_mock_deterministically_and_without_a_stall(
    gateway_against_the_mock: Endpoint,
    classify_comment: Callable[[str], Any],
    verdict_of_result: Callable[[Any], str],
    comment: str,
    expected: str,
) -> None:
    """Acceptance criterion 1, minus the parts only a running stack can show.

    "`make up`, `.env` pointed at the mock: a submit through the real gateway
    classifies deterministically with no external call and no 4s stall." The
    submit path is E2-08's; what this asserts is the sentence's middle: the real
    gateway, pointed at the mock the way `.env` points it, gets a verdict decided
    by the mock's published rule and gets it immediately.

    **Two rows, because one is not determinism.** A gateway that answered
    `insufficient` for everything passes the first row, and the character floor
    would answer both of these correctly on its own — so the value of the pair is
    that the two comments are classified *differently* and that the mock is what
    did it, which the request count asserts.

    **The timing is measured on a second call.** The first import of `app.ai` is
    slow enough to be worth seconds, and it happens inside the first call, so a
    stopwatch around that one measures the interpreter rather than the gateway.

    **The mutation this kills:** a stack that reaches nothing and floors on a
    timeout — which produces the same two verdicts, because the floor is a
    character count and these two comments sit either side of it. Without the
    elapsed-time bound and the request count, this whole test passes against a
    provider that is not there, which is exactly the state E2-07 exists to leave
    behind.
    """
    classify_comment(comment)
    asked_once = len(gateway_against_the_mock.completions)
    assert asked_once >= 1, (
        "The gateway made no completion request to the endpoint it was configured with. Every "
        "assertion below would then be about the character floor, which is what this ticket "
        "exists to stop happening on every submit."
    )

    started = time.monotonic()
    result = classify_comment(comment)
    elapsed = time.monotonic() - started

    assert (
        len(gateway_against_the_mock.completions) > asked_once
    ), "The second classification reached the endpoint no more than the first did."
    assert verdict_of_result(result) == expected, (
        f"{comment!r} classified as something other than {expected!r} through the mock. The mock's "
        "published rule is a length threshold, and this comment sits unambiguously on one side of "
        "it."
    )
    assert elapsed < GATEWAY_BUDGET_SECONDS, (
        f"A classification against the mock took {elapsed:.2f}s, against a per-task timeout of "
        f"{GATEWAY_BUDGET_SECONDS}s. Criterion 1 is 'no 4s stall': a submit that waits for the "
        "timeout is the state this ticket exists to leave behind, and it produces the right "
        "verdict anyway because the floor is the same character count the mock uses."
    )


def test_the_unavailable_marker_floors_the_classification_instead_of_raising(
    gateway_against_the_mock: Endpoint,
    mock_ai: MockAiProvider,
    classify_comment: Callable[[str], Any],
    verdict_of_result: Callable[[Any], str],
) -> None:
    """ADR 0056's unavailable row, reached from a comment: a 503 floors.

    "HTTP 408, 502, 503, 504 — the endpoint says it cannot serve now →
    `AIProviderUnavailableError` → floors". SPEC §3.3 is the reason: "on provider
    timeout, the heuristic floor applies and the submission is accepted ... never
    block a student on an outage", and ADR 0056 records that a hosted provider's
    outage usually arrives as a status rather than as a hanging socket.

    **What is asserted is a verdict the mock never gave.** The comment carries the
    503 marker, so the mock answers no verdict at all; a returned verdict can only
    have been computed here, and it is the character floor's — insufficient, for a
    comment under the threshold.

    **The mutation this kills:** 503 classified as refused or unreachable, which
    raises and blocks the student on the case §3.3 was written for. **Its pair is
    the test below**, where one status code away must not floor.
    """
    marker = mock_ai.marker_for("503")
    comment = f"{marker} {SHORT_TAIL}"

    result = classify_comment(comment)

    assert verdict_of_result(result) == INSUFFICIENT, (
        f"A comment carrying {marker!r} did not come back with the character floor's verdict. The "
        "mock answered 503 and no verdict, so the only verdict available is the floor's, and this "
        f"comment is shorter than the threshold. It came back {verdict_of_result(result)!r}."
    )


def test_the_refused_marker_raises_where_the_unavailable_marker_floors(
    gateway_against_the_mock: Endpoint,
    mock_ai: MockAiProvider,
    classify_comment: Callable[[str], Any],
    gateway_errors: Callable[[str], type[BaseException]],
    verdict_of_result: Callable[[Any], str],
) -> None:
    """The near miss this whole ticket exists to make testable, in one place.

    E2-07's scope: "The 503/500 pair exists on purpose: it is the near miss that
    separates ADR 0056's unavailable row from its refused row in E2-08's tests."
    Both calls are made here, against the same gateway and the same endpoint, and
    what is asserted is that they reach *different* outcomes: one returns a
    floored verdict and the other raises.

    **Why both in one test.** Two tests, each asserting one outcome, are both
    green against a gateway that treats every failure the same way if the two
    happen to run against different fixtures or different states — and a reader of
    a red would have to open the other file to see which half moved. ADR 0056's
    first version collapsed exactly this distinction ("one class covered every
    failure that was not an HTTP status"), and the record's whole argument is that
    the two are different events.

    **The mutation this kills:** 500 folded into the floor — which ADR 0056 calls
    out as the tempting one, since flooring on every 5xx is simpler than a set,
    "and it puts `500` in the floor — the status a provider returns when *our*
    request is the problem, so a schema it cannot parse would degrade every
    classification to the character floor silently and permanently".

    **The class is named rather than left as any exception**, because a bare
    `Exception` is satisfied by a `TypeError` from a call shape this fixture got
    wrong, which is a broken test reading as a rule firing.
    """
    refused = gateway_errors("AIProviderRefusedError")
    unavailable_marker = mock_ai.marker_for("503")
    refused_marker = mock_ai.marker_for("500")

    floored = classify_comment(f"{unavailable_marker} {SHORT_TAIL}")
    assert verdict_of_result(floored) == INSUFFICIENT, (
        "The 503 half of this pair did not floor, so the difference asserted below would be a "
        "difference between two failures rather than between the floor and a refusal."
    )

    with pytest.raises(refused) as raised:
        classify_comment(f"{refused_marker} {SHORT_TAIL}")

    assert not isinstance(raised.value, gateway_errors("AIProviderUnavailableError")), (
        f"The refusal raised {type(raised.value).__name__}, which is also the class that floors. "
        "ADR 0056 makes the four classes the interface E2 branches on, and a class that is both "
        "is one class."
    )


def test_the_stall_marker_floors_before_the_answer_arrives(
    gateway_against_the_mock: Endpoint,
    mock_ai: MockAiProvider,
    classify_comment: Callable[[str], Any],
    verdict_of_result: Callable[[Any], str],
) -> None:
    """The other path to the unavailable row: an answer that is late rather than absent.

    ADR 0056's first row — "read timeout: connection open, request sent, no answer
    in time" — and the one SPEC §3.3 names outright. The mock's stalling answer is
    a *correct* answer that arrives after the budget, so this is the case where
    flooring is unambiguously right and where a gateway that simply waited would
    produce the right classification eventually and a two-second p95 never.

    **The verdict is the discriminator, and the comment is chosen for it.** The
    stall marker answers `substantive` when it answers; the comment here is short,
    so the floor answers `insufficient`. A gateway that waited for the mock would
    come back substantive, and one that floored comes back insufficient — a
    difference no timing measurement is needed to see.

    **The timing is asserted anyway**, in the other direction from criterion 1's:
    the call has to come back *before* the mock's published stall elapses. Without
    it, a gateway with a timeout longer than the stall would answer insufficient
    only because the character floor and the mock happened to disagree in the
    other direction, and this test would be reporting a race.

    **The mutation this kills:** no per-task timeout at all, and a timeout longer
    than the mock's stall.
    """
    marker = mock_ai.marker_for("stall")
    stall = mock_ai.stall_seconds()

    started = time.monotonic()
    result = classify_comment(f"{marker} {SHORT_TAIL}")
    elapsed = time.monotonic() - started

    assert verdict_of_result(result) == INSUFFICIENT, (
        f"A comment carrying {marker!r} came back {verdict_of_result(result)!r}. The mock answers "
        "`substantive` after it has stalled, and the character floor answers `insufficient` for a "
        "comment this short — so `substantive` means the gateway waited for the provider instead "
        "of failing open."
    )
    assert elapsed < stall, (
        f"The classification took {elapsed:.2f}s against the mock's published stall of {stall}s, "
        f"so the gateway waited for the answer rather than giving up at its "
        f"{GATEWAY_BUDGET_SECONDS}s budget. SPEC §3.3 gates the submit path on this: p95 under two "
        "seconds, floor on timeout."
    )


def test_the_malformed_answer_is_asked_once_more_and_then_surfaces_as_an_error(
    gateway_against_the_mock: Endpoint,
    mock_ai: MockAiProvider,
    classify_comment: Callable[[str], Any],
    gateway_errors: Callable[[str], type[BaseException]],
) -> None:
    """The shape-violation path: §7.4's retry, then an error rather than a verdict.

    §7.4: "The gateway validates against that model, retries on shape violations,
    and surfaces persistent failures as errors rather than letting a malformed
    classification propagate." ADR 0053 makes the retry one bounded re-ask made by
    the gateway itself rather than the library's feedback loop, because the loop
    would append a message after the one ending in the student's comment and
    `app/ai/prompts/README.md` rests the injection boundary on there being nothing
    after it.

    **The mock is stateless, so the re-ask gets the same wrong answer**, which is
    what makes "then the error surface" reachable at all. That is the work order's
    reason for the selector behaving identically on every request.

    **Both halves are asserted and neither is enough alone.** The error alone
    passes against a gateway that never retried — which is a defect, since a
    model's one-off bad answer would then fail a submission. The request count
    alone passes against a gateway that retried and then returned something. And
    the count is asserted as *more than one and bounded*, not as a bare "more than
    one": a gateway that re-asked until it gave up would also be more than one,
    and an unbounded retry against a permanently malformed provider is the four
    seconds per submit this ticket is removing.

    **The mutation this kills:** the re-ask removed; the re-ask made unbounded;
    and a malformed payload accepted, which is the worst of the three — a verdict
    the model never gave, stored against a student's comment.
    """
    invalid = gateway_errors("AIResponseInvalidError")
    marker = mock_ai.marker_for("malformed")
    before = len(gateway_against_the_mock.completions)

    with pytest.raises(invalid):
        classify_comment(f"{marker} {ORDINARY_LONG_COMMENT}")

    asked = len(gateway_against_the_mock.completions) - before
    assert asked == 2, (
        f"The gateway made {asked} completion requests for one comment the mock answered "
        "malformedly. §7.4 has it retry a shape violation, and ADR 0053 makes that exactly one "
        "bounded re-ask — so one request is a gateway that does not retry, and three or more is "
        "one that does not stop."
    )


def test_the_gateway_declares_every_class_the_taxonomy_names(
    gateway_errors: Callable[[str], type[BaseException]],
) -> None:
    """A control on the lookup every assertion above depends on.

    **A red here means these tests are broken, or ADR 0056's interface has moved
    — and either way the failures above are not about the mock.** `gateway_errors`
    fails with a message when a name is missing, so a renamed class would turn
    every test in this module red at once with no indication that they share a
    cause. This is the one test that says so directly.

    It also asserts the shape of the family: each of the four is an
    `AIGatewayError`, which is what lets E2's submit path catch the base class and
    branch on the four (ADR 0056's consequences). A class that had drifted out of
    the family would be an error nothing on the submit path catches.
    """
    base = gateway_errors("AIGatewayError")
    for name in (
        "AIProviderUnavailableError",
        "AIProviderUnreachableError",
        "AIProviderRefusedError",
        "AIResponseInvalidError",
    ):
        found = gateway_errors(name)
        assert issubclass(found, base), (
            f"`{name}` is not a subclass of `AIGatewayError`. ADR 0056's consequences: 'the four "
            "classes are the interface E2 branches on' — a class outside the family is one the "
            "submit path's `except` does not catch."
        )
