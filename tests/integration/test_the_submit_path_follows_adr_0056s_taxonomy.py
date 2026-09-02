"""E2-08 criterion 2 — ADR 0056's taxonomy, against the stack.

> The failure taxonomy against the stack: mock told to stall (E2-07) — submit
> accepted on the floor, floored classification row present, async
> re-classification lands a second row, and the request returns inside the §10
> budget rather than hanging on the worker (MISTAKES entry 41's near-miss is the
> test). Mock told to answer 503 — floors. Mock told to answer 500 — the recorded
> refused-behavior, not the floor. And the *unreachable* row runs too ... All
> three cells run, and the ADR names the choices.

**The near-miss pair the ticket names is 503 against 500** (`docs/MISTAKES.md`
entry 3). They differ by one digit and by nothing else: the same student, the
same section, the same comment, the same provider, one in-band selector apart.
ADR 0056 puts 503 in the floor because "the endpoint says it cannot serve now"
and 500 outside it because "our request is the problem far more often than it
means the provider is having an outage", and a route that floors on any 5xx
passes every other test in this file.

**The unreachable row is paired across two tests rather than inside one**, and
that is deliberate. A connection that fails cannot be minted by a mock that
answers, so its address is a closed loopback port — and the application's
provider address is fixed when it is built, so the accepted half of that pair is
`test_a_provider_answering_503_floors_and_the_submission_is_stored`, which makes
the identical submission against a provider that does answer. Building a second
application inside one test would leave the two sharing whatever `app.*` modules
the first import cached, which is the failure `tests/fixtures/app_imports.py`
exists to prevent.

**Where the §10 budget is measured, and where it is not.** SPEC §10's 2.5s is the
whole submit round trip, and E0-13's classifier budget is 4 seconds — so a
submission that waits for a stall cannot come in under 2.5s and the stall test
does not pretend to. The budget is measured where entry 41's defect would show:
with the broker down, over a classification that answers immediately. That is the
near miss — a request that is *prompt* when a background dependency is
unavailable, against one that holds the connection open while a client library
retries a worker's twenty times.
"""

import time
from typing import Any

import pytest
from fixtures.submit import (
    ANSWER_TABLE,
    CHARACTER_FLOOR,
    CLASSIFICATION_TABLE,
    SUBSTANTIVE_COMMENT,
    USER_TABLE,
    SubmitWorld,
    a_valid_submission,
)

pytestmark = pytest.mark.integration


def marked(mock_ai: Any, selector: str) -> str:
    """A floor-eligible comment carrying the mock's selector for `selector`."""
    return f"{SUBSTANTIVE_COMMENT} {mock_ai.marker_for(selector)}"


def a_student(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    open_now: tuple[Any, Any],
    *,
    ai_base_url: str,
    redis_url: str | None = None,
) -> Any:
    """The seeded world, a tool pointed at `ai_base_url`, and a signed-in student."""
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    client = open_submit_tool(ai_base_url=ai_base_url, redis_url=redis_url)
    return signed_in_student(client, world)


def accepted(response: Any, what: str) -> None:
    """Stop unless the route answered success, printing what it said instead."""
    assert 200 <= response.status_code < 300, (
        f"{what} answered {response.status_code} rather than success. Body begins "
        f"{response.text[:400]!r}."
    )


def the_comment_answer(world: SubmitWorld, response: Any) -> dict[str, Any]:
    """The one `answer` row of a response that holds a comment."""
    comments = [row for row in world.answers_of(response) if row["comment_text"] is not None]
    assert len(comments) == 1, (
        f"The stored response holds {len(comments)} comment answers: {comments}. Every submission "
        "in this module answers exactly one comment, so the classification below would otherwise "
        "be attributed to a row nothing here chose."
    )
    return comments[0]


def the_only_classification(world: SubmitWorld, answer: dict[str, Any]) -> dict[str, Any]:
    """The one `classification` row naming an answer, or a failure counting them."""
    rows = world.classifications_of(answer)
    assert len(rows) == 1, (
        f"{len(rows)} classification rows name the submitted comment: {rows}. A synchronous "
        "submit classifies each submitted comment once; none means §3.3's gating did not run, and "
        "two means it ran twice inside one request."
    )
    return rows[0]


# ---------------------------------------------------------------------------
# The floor: `AIProviderUnavailableError`, which ADR 0056 puts inside it.
# ---------------------------------------------------------------------------


def test_a_provider_answering_503_floors_and_the_submission_is_stored(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> None:
    """ADR 0056: "HTTP 408, 502, 503, 504 — the endpoint says it cannot serve now" floors.

    SPEC §3.3's one sanctioned fail-open: "on provider timeout, the heuristic
    floor applies and the submission is accepted, then classified async (fail
    open, never block a student on an outage)". A hosted provider's outage is a
    load balancer answering 503, which ADR 0056's rewrite moved into the floor
    after measuring that it "raised, blocking every student on precisely the case
    §3.3's sentence was written for".

    **The floored row is compared against a row a model actually produced**, by a
    second student whose comment the same provider classifies normally. ADR 0054's
    own consequence says why the comparison rather than the strings: "it asserts a
    *difference* rather than these particular strings, so the shape is pinned and
    the spelling stays this record's to change". The pair a floor stores is
    `character-floor` / `no-model` today, and this test goes on being right when
    either is renamed.

    **The mutation it kills:** a floored classification recorded with the prompt
    version and model id a real call would have used — ADR 0054's first rejected
    alternative, "a record that says a model classified a comment it was never
    sent", which makes the async re-classification unable to find the comments no
    model has judged. It also kills the floor removed altogether, which turns
    every submission during an outage into a refusal.

    **This is also the accepted half of the unreachable pair** — see the module
    docstring. The submission below is identical to the one
    `test_a_provider_that_cannot_be_reached_does_not_floor` makes; the address is
    the only difference.
    """
    student = a_student(
        open_submit_tool,
        submit_world,
        signed_in_student,
        open_now,
        ai_base_url=mock_ai_endpoint.base_url,
    )
    world = student.world
    healthy = signed_in_student(student.client, world, world.another_student())

    real = healthy.submit(a_valid_submission(comment=marked(mock_ai, "substantive")))
    accepted(real, "A submission whose comment the provider classified")

    floored = student.submit(a_valid_submission(comment=marked(mock_ai, "503")))

    accepted(floored, "A submission made while the provider answered 503")
    student_id = world.student[world.key_of(USER_TABLE)]
    stored = [row for row in world.responses() if row["user_id"] == student_id]
    assert len(stored) == 1, (
        f"A submission made during a provider outage left {len(stored)} responses for the "
        "student. SPEC §3.3 accepts it on the floor: 'never block a student on an outage'."
    )
    assert stored[0]["is_valid"] is True, (
        f"The floored submission stored `is_valid` {stored[0]['is_valid']!r}. ADR 0054: the "
        "floor's verdict over a comment of 25 characters or more is `substantive`, and it is "
        "'never `nonsense`' — 'calling a short comment nonsense during an outage would reduce a "
        "section's validity rate over something the student did not do'."
    )

    floored_pair = world.audit_pair_of(
        the_only_classification(world, the_comment_answer(world, stored[0]))
    )
    real_stored = [row for row in world.responses() if row["user_id"] != student_id]
    assert len(real_stored) == 1, "The control student's response is missing."
    real_pair = world.audit_pair_of(
        the_only_classification(world, the_comment_answer(world, real_stored[0]))
    )

    assert floored_pair != real_pair, (
        f"A floored classification and one a model produced carry the same prompt version and "
        f"model id: {floored_pair}. ADR 0054 exists so that 'a reader can tell the two apart with "
        "no schema knowledge' — E2's async re-classification finds the floor rows by exactly this "
        "pair, and if every row already looks classified there is nothing to find."
    )


def test_a_stalling_provider_floors_the_submission(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> None:
    """ADR 0056's other floor row: "Read timeout — connection open, request sent, no answer".

    The same outcome as the 503 cell reached at a different layer, which is ADR
    0056's own reading: "A read or write timeout and an availability status are
    the same event seen at two layers, and a student should not be blocked by
    either." Both are asserted because the two travel different code paths — one
    is an exception out of the transport and one is a status out of the
    response — and a taxonomy that classified only one of them correctly would
    pass whichever test was written.

    **No timing is asserted here, deliberately.** E0-13's classifier budget is
    four seconds and SPEC §10's whole-round-trip figure is 2.5, so a submission
    that waits out a stall cannot satisfy the second. §10 says in as many words
    that the two figures "measure different spans ... Do not reconcile them into
    one number", and the budget is measured in
    `test_a_submission_is_prompt_while_the_broker_is_unreachable`, where entry
    41's defect is what a slow request would mean.

    **The mutation it kills:** `_unanswered_outcome` matching on
    `TimeoutException` rather than on `ReadTimeout` and `WriteTimeout`
    specifically — the mistake ADR 0056's rewrite corrects — which would move the
    connect-timeout case into the floor along with this one.
    """
    student = a_student(
        open_submit_tool,
        submit_world,
        signed_in_student,
        open_now,
        ai_base_url=mock_ai_endpoint.base_url,
    )
    world = student.world

    answered = student.submit(a_valid_submission(comment=marked(mock_ai, "stall")))

    accepted(answered, "A submission made while the provider stalled past the classifier budget")
    responses = world.responses()
    assert len(responses) == 1, (
        f"A stalled classification left {len(responses)} responses: {responses}. §3.3's fail-open "
        "accepts the submission and classifies it async."
    )
    classification = the_only_classification(world, the_comment_answer(world, responses[0]))
    assert classification["verdict"], (
        f"The stored classification carries no verdict: {classification}. ADR 0054 makes a floored "
        "result 'a `CommentValidityOutput` like any other' — E2 has one shape to read, whichever "
        "produced it."
    )


# ---------------------------------------------------------------------------
# Outside the floor: the two rows ADR 0056 keeps out of it, and ADR 0114's
# answer to them.
# ---------------------------------------------------------------------------


def test_a_provider_answering_500_does_not_floor_and_stores_nothing(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
    registry_texts: Any,
) -> None:
    """The near miss the ticket names: a 503 floors and a 500 does not.

    ADR 0056 item 13: "A 500 means our request is the problem far more often than
    it means the provider is having an outage — a payload the model cannot parse
    returns exactly this — and the outage shape has its own statuses in the floor
    above. Flooring on either hides a condition that never resolves on its own,
    one comment at a time." The record's own answer to what E2 should do instead
    is "E2 sees the error on the submit path and answers for it", which is ADR
    0114: 503 to the student with `Retry-After: 60` and the
    `submit.classifier_down` copy, and nothing stored.

    **The 503 half runs first, in this same test, on this same provider**, so the
    only difference between the accepted case and the refused one is one digit of
    the selector inside the comment. That is what makes this a near-miss pair
    rather than two unrelated assertions: a route that floors on every 5xx passes
    the first half and fails only here.

    **The mutation it kills:** `except AIGatewayError` at the submit path, which
    catches the base class ADR 0056 warns about — "matching on a base class is a
    decision about every subclass, including the ones added after you write it" —
    and would widen the spec-sanctioned fail-open to every failure there is. It
    also kills the opposite overshoot: a raw 500 to the student, which ADR 0114
    rejects, and which would show up here as a 5xx carrying no registry string.
    """
    student = a_student(
        open_submit_tool,
        submit_world,
        signed_in_student,
        open_now,
        ai_base_url=mock_ai_endpoint.base_url,
    )
    world = student.world
    floors = signed_in_student(student.client, world, world.another_student())

    accepted(
        floors.submit(a_valid_submission(comment=marked(mock_ai, "503"))),
        "A submission made while the provider answered 503, which ADR 0056 floors on",
    )

    refused = student.submit(a_valid_submission(comment=marked(mock_ai, "500")))

    assert refused.status_code == submit_contract.classifier_down, (
        f"A submission made while the provider answered 500 was answered {refused.status_code} "
        f"rather than ADR 0114's {submit_contract.classifier_down}. A 2xx here is the floor "
        "applied to a status ADR 0056 keeps outside it, which widens SPEC §3.3's one sanctioned "
        f"fail-open by the back door. Body begins {refused.text[:400]!r}."
    )
    assert refused.headers.get("retry-after") == submit_contract.retry_after_seconds, (
        f"The refusal carries `Retry-After: {refused.headers.get('retry-after')!r}`; ADR 0114 "
        f"settles {submit_contract.retry_after_seconds!r}. It is the difference between a refusal "
        "a student can act on and one that reads as the tool being broken."
    )
    expected = registry_texts()[submit_contract.classifier_down_key]
    assert expected in refused.text, (
        f"The refusal served {refused.text[:300]!r}, which does not carry the registry's "
        f"`{submit_contract.classifier_down_key}` text {expected!r}. Criterion 4: every "
        "user-facing string this path serves is externalized."
    )
    stored = [
        row
        for row in world.responses()
        if row["user_id"] == world.student[world.key_of(USER_TABLE)]
    ]
    assert stored == [], (
        f"A refused submission stored {stored}. ADR 0114's refusal keeps the answers in the form "
        "and writes nothing, so a student who retries in a minute is not resubmitting over a row "
        "they were never told existed."
    )


def test_a_provider_that_cannot_be_reached_does_not_floor(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    unreachable_ai_provider: str,
    submit_contract: Any,
    registry_texts: Any,
) -> None:
    """ADR 0056's `AIProviderUnreachableError` row, run at the integration level.

    The ticket says why it has to be run this way: "a mock that answers cannot
    mint a connection that fails", so the provider address is a loopback port
    nothing is listening on. And it says what is at stake: "flooring on a
    blackholed provider is the exact defect ADR 0056's 2026-08-31 amendment
    records returning once already", where a chain walk that matched
    `TimeoutException` floored "with **zero requests reaching any server**".

    ADR 0056's reasoning, quoted because it is the whole point of keeping this row
    out of the floor: "A connect timeout is in this group *because* it is the
    cheapest thing an attacker can force: if it floored, anyone able to drop
    packets could decide that no classification happens."

    **The accepted half of this pair is
    `test_a_provider_answering_503_floors_and_the_submission_is_stored`**, which
    makes the identical submission against a provider that answers — see the
    module docstring for why it is a second test rather than a second half of this
    one. `mock_ai_endpoint` is requested here even though nothing sends to it, so
    that both tests stand up the same machinery and a failure here cannot be the
    mock failing to start.

    **The mutation it kills:** the fail-open written as "any failure to classify",
    which is the state ADR 0056 was written to leave behind and which this address
    reaches without a network, a certificate or an attacker.
    """
    student = a_student(
        open_submit_tool,
        submit_world,
        signed_in_student,
        open_now,
        ai_base_url=unreachable_ai_provider,
    )
    world = student.world

    refused = student.submit(a_valid_submission(comment=marked(mock_ai, "substantive")))

    assert refused.status_code == submit_contract.classifier_down, (
        f"A submission made while the provider was unreachable was answered "
        f"{refused.status_code} rather than ADR 0114's {submit_contract.classifier_down}. A 2xx "
        "is the floor applied to a connection that reached no endpoint, which is the defect ADR "
        f"0056 records returning once already. Body begins {refused.text[:400]!r}."
    )
    assert refused.headers.get("retry-after") == submit_contract.retry_after_seconds
    expected = registry_texts()[submit_contract.classifier_down_key]
    assert expected in refused.text, (
        f"The refusal served {refused.text[:300]!r}, which does not carry the registry's "
        f"`{submit_contract.classifier_down_key}` text."
    )
    assert world.responses() == [], f"A refused submission stored {world.responses()}."


# ---------------------------------------------------------------------------
# `docs/MISTAKES.md` entry 41 — the request path and the background dependency.
# ---------------------------------------------------------------------------


def test_a_submission_is_prompt_while_the_broker_is_unreachable(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    unreachable_broker: str,
    submit_contract: Any,
) -> None:
    """`docs/MISTAKES.md` entry 41's near miss, posed directly.

    > A request path may not be able to fail because a background dependency was
    > unavailable, and it may not wait to find out. When a handler enqueues work,
    > publish with retries off, keep the result backend out of it for a task whose
    > answer nobody reads, and catch broadly.

    The floor is reached through a 503 rather than through a stall, so the
    classifier answers immediately and the only thing that can make this request
    slow is the enqueue. Entry 41's incident is the measurement this stands on:
    `task.delay(...)` against a Redis that was not there held each request "for
    roughly twenty seconds and then raised", out of a handler that had already
    done its own job — and the whole suite went from seven minutes to fourteen.

    **Both halves of the enqueue are asserted**: the request succeeds (a broker
    that is down may not make a submission fail) and it comes back inside SPEC
    §10's 2.5 seconds (it may not wait to find out). Either on its own passes
    against half of the defect — `retry=False` with the result backend still in
    play is fast and raises, and a broad `try/except` around a twenty-second retry
    succeeds and hangs.

    **The mutation it kills:** `delay(...)` in place of `apply_async(...,
    retry=False, ignore_result=True)`, and the broad `except` removed from around
    it. Its pair, with a broker that answers, is the test below.
    """
    student = a_student(
        open_submit_tool,
        submit_world,
        signed_in_student,
        open_now,
        ai_base_url=mock_ai_endpoint.base_url,
        redis_url=unreachable_broker,
    )
    world = student.world

    answered, elapsed = student.submit_timed(a_valid_submission(comment=marked(mock_ai, "503")))

    accepted(answered, "A submission floored on a 503 while the broker was unreachable")
    assert elapsed < submit_contract.submit_budget_seconds, (
        f"The request took {elapsed:.1f}s with the broker at a closed port. SPEC §10: 'survey "
        f"submit p95 < 2.5s including synchronous validity check'. The classification answered "
        "immediately, so the time was spent somewhere else — and a client library's defaults on a "
        "request path turn a dependency that is down into a request that is hanging "
        "(`docs/MISTAKES.md` entry 41)."
    )
    responses = world.responses()
    assert len(responses) == 1, f"The submission left {len(responses)} responses: {responses}."
    the_only_classification(world, the_comment_answer(world, responses[0]))


def test_a_submission_is_prompt_with_a_broker_that_answers(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    broker_url: str,
    submit_contract: Any,
) -> None:
    """The other direction: with a broker that answers, the same submission still lands.

    Written because the test above is satisfied by a route that never enqueues at
    all — "prompt while the broker is down" is trivially true of a handler that
    does not publish. This one is the near miss that distinguishes the fix from
    doing nothing: a real broker is running, the same submission is made, and it
    succeeds inside the same budget rather than raising on a publish the handler
    was never written to do.

    **What it deliberately does not assert:** that a message reached the queue.
    Reading the queue would pin the task's routing key and its name, neither of
    which E2-08 settles;
    `test_the_re_classification_lands_a_second_row_over_a_floored_answer` is where
    the async path is shown to exist and to do something.
    """
    student = a_student(
        open_submit_tool,
        submit_world,
        signed_in_student,
        open_now,
        ai_base_url=mock_ai_endpoint.base_url,
        redis_url=broker_url,
    )
    world = student.world

    answered, elapsed = student.submit_timed(a_valid_submission(comment=marked(mock_ai, "503")))

    accepted(answered, "A submission floored on a 503 with a broker that answers")
    assert elapsed < submit_contract.submit_budget_seconds, (
        f"The request took {elapsed:.1f}s against a broker that is up, over a classification that "
        "answered immediately. SPEC §10 gives the whole round trip 2.5 seconds."
    )
    assert len(world.responses()) == 1


# ---------------------------------------------------------------------------
# The async half of §3.3's fail-open.
# ---------------------------------------------------------------------------


def test_the_re_classification_lands_a_second_row_over_a_floored_answer(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    import_app_module: Any,
    reclassify: Any,
) -> None:
    """§3.3: "the submission is accepted, then classified async".

    The sweep is run in this process rather than waited for, because a worker is
    not what is under test: E2-08's work order puts the entry point in
    `backend/app/jobs/tasks.py` as a thin wrapper over `services/validity.py` and
    adds "a beat schedule entry ... sweeping unresolved floored classifications",
    and this calls the wrapper directly. The entry point is **found** rather than
    named, for the reason `tests/fixtures/ai_tasks.py` gives: no ticket spells its
    name, and pinning one here would make the implementer build to this test
    instead of to the ticket.

    **What this proves and what it does not.** The provider is still answering 503
    when the sweep runs — the selector is inside the stored comment, so it cannot
    be otherwise — so the second row is a second floor rather than a model's
    verdict. That is exactly what append-only means (ADR 0055: "re-runs create new
    rows", enforced by a grant that withholds `UPDATE` and `DELETE`), and it is
    what the criterion asks for: the sweep finds the unresolved floored row, runs
    it again, and records what happened. Whether the *verdict* changes is the
    provider's business.

    **The mutation it kills:** an async half that is declared and never written —
    the state where §3.3's promise that a floored submission is "then classified
    async" is a sentence in a docstring. It also kills a sweep that updates the
    floored row in place, which the E0-13 grant refuses and which would leave the
    audit trail with one row saying two things.
    """
    student = a_student(
        open_submit_tool,
        submit_world,
        signed_in_student,
        open_now,
        ai_base_url=mock_ai_endpoint.base_url,
    )
    world = student.world

    accepted(
        student.submit(a_valid_submission(comment=marked(mock_ai, "503"))),
        "A submission floored while the provider answered 503",
    )
    answer = the_comment_answer(world, world.responses()[0])
    before = world.classifications_of(answer)
    assert len(before) == 1, (
        f"The floored submission left {len(before)} classification rows: {before}. The sweep below "
        "is required to add one, so a wrong number here makes that count mean nothing."
    )

    tasks = import_app_module("app.jobs.tasks")
    assert tasks is not None, (
        "There is no `app.jobs.tasks` module, so there is nothing for the submit path to enqueue. "
        "E2-08's work order puts the async re-classification there as a thin wrapper."
    )
    reclassify(tasks)

    after = world.classifications_of(answer)
    assert len(after) > len(before), (
        f"The re-classification left the answer with {len(after)} classification rows, the same "
        f"{len(before)} the submit path wrote. §3.3 promises a floored submission is 'then "
        "classified async', and ADR 0055 makes `classification` append-only so a re-run is a new "
        "row rather than an edit."
    )


def test_a_bounce_keeps_the_verdict_that_produced_it(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    submit_contract: Any,
) -> None:
    """A bounced submission stores no response and keeps the classification that bounced it.

    SPEC §8 makes `classification` append-only and ADR 0055 makes the grant what
    enforces it — "`SELECT, INSERT` on the table and nothing else, so the
    connection the API and the worker hold cannot `UPDATE` or `DELETE` a row
    however the application is written". A bounce that rolls its whole
    transaction back is the third way to lose the row, and the one no grant can
    stop: the verdict is never committed at all.

    What that costs is the record §7.4 rests auditability on — "a specific prompt
    version and model ID produced a specific classification for a specific
    comment". A student bounced three times is three model calls that were made,
    paid for and answered, with nothing anywhere saying so: §6.1's drift panel
    samples across tasks and would sample none of them, and an admin asking why a
    student says the tool keeps refusing their comment has no row to look at.

    **`answer_id` is `NULL` on these rows and that is the design**, not an
    omission: nothing is stored as submitted on a bounce, so there is no `answer`
    row for the verdict to name. ADR 0055's rule that "the row names no comment"
    is what makes that legal — the column is nullable, and the *text* is
    deliberately not stored beside it, because a comment is "short and often
    formulaic … so a digest of one is recoverable by dictionary in seconds".

    **Both bounces are made, and their audit pairs are compared.** A comment the
    model calls `insufficient`, and a comment short enough that the character
    floor calls it `insufficient` while the provider answers 503 — ADR 0054 puts
    the floor's verdict at `substantive` or `insufficient` and never `nonsense`,
    so the floored path bounces too, which is the near miss this pair is written
    against. Both have to leave a row: an implementation that kept the model's row
    and rolled back the floor's would pass a test that only made the first
    submission. The two pairs differ for the reason ADR 0054 gives — a floored row
    names the floor in its prompt version and model id — and comparing them is how
    that is asserted without either test holding a copy of the two strings.

    **The mutation it kills:** the bounce implemented as "raise, and let the
    request's transaction roll back". It is the natural way to write it, it makes
    every other assertion in this ticket pass, and it silently discards the audit
    row §7.4 requires — which is `docs/MISTAKES.md` entry 2's shape reached
    through a mechanism nobody chose.
    """
    student = a_student(
        open_submit_tool,
        submit_world,
        signed_in_student,
        open_now,
        ai_base_url=mock_ai_endpoint.base_url,
    )
    world = student.world

    def rows_added_by(submit: Any) -> list[dict[str, Any]]:
        """Every `classification` row one submission left behind."""
        before = {row["id"] for row in world.rows_of(CLASSIFICATION_TABLE)}
        answered = submit()
        assert answered.status_code == submit_contract.unprocessable, (
            f"The submission was answered {answered.status_code} rather than "
            f"{submit_contract.unprocessable}. §3.3 bounces a comment the classifier will not "
            f"call substantive, before submission. Body begins {answered.text[:400]!r}."
        )
        return [row for row in world.rows_of(CLASSIFICATION_TABLE) if row["id"] not in before]

    judged = rows_added_by(
        lambda: student.submit(a_valid_submission(comment=marked(mock_ai, "insufficient")))
    )
    assert len(judged) == 1, (
        f"A bounce on a verdict the model produced left {len(judged)} classification rows: "
        f"{judged}. The model was asked, it answered, and SPEC §7.4 requires that every "
        "classification store the prompt version and model ID that produced it — a bounce that "
        "rolls the row back leaves the call unrecorded and unbillable to anything."
    )

    # A comment below SPEC §3.3's character heuristic, carrying the selector that
    # makes the provider answer 503. ADR 0056 floors on that status; ADR 0054
    # puts the floor's verdict at `insufficient` below the threshold; §3.3
    # bounces on `insufficient`. So this is the floored path arriving at the same
    # outcome by a different route, and it is the near miss.
    unavailable = mock_ai.marker_for("503")
    short = f"{unavailable} brief"
    assert len(short) < CHARACTER_FLOOR, (
        f"{short!r} is {len(short)} characters and SPEC §3.3's heuristic floor is "
        f"{CHARACTER_FLOOR}. This half of the test needs a comment the *floor* calls "
        "insufficient; a longer one would floor to `substantive`, be accepted, and this would "
        "stop being a test about a bounce at all."
    )

    floored = rows_added_by(lambda: student.submit(a_valid_submission(comment=short)))
    assert len(floored) == 1, (
        f"A bounce on a floored verdict left {len(floored)} classification rows: {floored}. The "
        "provider was unavailable, the character heuristic decided, and ADR 0054 makes that "
        "decision 'a `CommentValidityOutput` like any other' — E2 has one shape to read, whichever "
        "produced it, and one row to store."
    )

    assert world.responses() == [], (
        f"A bounced submission stored {world.responses()}. The ticket's Scope: 'nothing is stored "
        "as submitted on a bounce'."
    )
    assert world.rows_of(ANSWER_TABLE) == [], (
        f"A bounced submission stored {world.rows_of(ANSWER_TABLE)} answers. Without a response "
        "there is nothing for them to belong to."
    )
    for row in (*judged, *floored):
        assert row["answer_id"] is None, (
            f"A bounce's classification row names answer {row['answer_id']!r}. Nothing is stored "
            "on a bounce, so there is no `answer` row for it to name — a value here points at a "
            "row that does not exist, or at somebody else's."
        )

    assert world.audit_pair_of(judged[0]) != world.audit_pair_of(floored[0]), (
        f"A bounce the model produced and a bounce the character floor produced carry the same "
        f"prompt version and model id: {world.audit_pair_of(judged[0])}. ADR 0054 exists so that "
        "'a reader can tell the two apart with no schema knowledge', and a floor row that looks "
        "like a model's is a classification that never happened, filed as one that did."
    )


def test_the_wall_clock_is_the_one_this_module_measures_with() -> None:
    """The control on the two timing assertions above (`docs/MISTAKES.md` entry 3).

    `submit_timed` reports `time.perf_counter()` differences, and a helper that
    reported zero — a counter read once, a subtraction the wrong way round — would
    make both budget assertions pass against a request that took a minute. A tenth
    of a second is asked for and a tenth of a second has to be seen.

    **A red here means this module's instrument is broken, not the submit path.**
    """
    started = time.perf_counter()
    time.sleep(0.1)
    measured = time.perf_counter() - started

    assert 0.05 < measured < 2.0, (
        f"A deliberate 0.1s sleep measured as {measured:.3f}s. The two §10 budget assertions in "
        "this module are differences of the same clock, so a reading that cannot see a tenth of a "
        "second cannot see a twenty-second retry either."
    )
