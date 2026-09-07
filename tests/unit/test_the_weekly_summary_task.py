"""What `summarize_stream` does around a model call — E4-05.

E4-05's scope: "the gateway task in `tasks.py`, per-stream: the input is the
week's comments for one stream (under-threshold ones included — §4 says they feed
the summary), with no identity, no section code, no user id in the prompt". SPEC
§7.4 governs the call itself: "one call in, one validated object out — no tool
use, no planning loop, no iterative retrieval".

This module is about the task's own decisions, which are the ones a provider
cannot make for it: whether to call at all, what to ask for, what to refuse, what
to let through, and what number it writes down beside the answer. Every one of
them is asserted against a gateway double, because none of them is a property of
what a provider says.

**The doubles supply the answers and never the verdict.** `docs/MISTAKES.md`
entry 30: a suite cannot measure a value its own fixture provides. So nothing here
asserts that a summary is *good* — that is SPEC §9.3's question, asked in
`tests/evals/summary/` and answered by a live run whose floor E4-05 stages
deliberately. What is asserted is the task's behaviour around whatever it is
handed.

**And entry 49's rule is why the failure tests read the way they do.** A task that
swallowed a provider outage and answered a plausible empty summary would look
identical, from the return value, to a week that genuinely had no comments. So the
error tests assert the *raise*, by class, and the empty-week test asserts that no
call was made at all rather than that something came back.
"""

from __future__ import annotations

from typing import Any

import pytest
from fixtures.summary_task import (
    COMMENT_THEME,
    COURSE_STREAM,
    EMPTY_WEEK_PROMPT_VERSION,
    EMPTY_WEEK_SUMMARY,
    INSTRUCTOR_STREAM,
    RESPONSE_INVALID_ERROR,
    SUMMARY_PROMPT_VERSION,
    SUMMARY_TIMEOUT_SECONDS,
    WEEKLY_SUMMARY_OUTPUT,
    RefusingGateway,
    ScriptedGateway,
    SummaryApi,
    call_summarize,
)

# ADR 0054's marker for "no model answered", which lives in `app.ai.gateway` as
# `NOT_A_MODEL` because the gateway is what knows one did not. The empty week
# never reaches a provider, so this is the only honest thing its record can name.
NOT_A_MODEL = "NOT_A_MODEL"

# One of ADR 0056's four, used as the failure a provider hands the task. Named
# rather than discovered, for the reason `tests/fixtures/ai_tasks.py` gives.
UNAVAILABLE_ERROR = "AIProviderUnavailableError"

# A week of comments for one stream. Three comments, and a response count that is
# deliberately not three: §3.2 makes both comments optional above the rating
# threshold, so a week of nine responses can carry three comments, and the
# distinction is the whole of what "the caller injects the count from data" means.
A_WEEK = (
    "The Thursday proofs went by too quickly to write anything down.",
    "Office hours were genuinely helpful once I got there.",
    "Please post the derivations afterwards if the pace has to stay.",
)
RESPONSES_THAT_WEEK = 9

# A comment made of tokens that appear nowhere else in this repository, for the
# tests asking whether a refusal quotes a student back into its message. The
# nonce is what makes a match evidence: an ordinary sentence could appear in a
# prompt template, and then "the comment did not leak" would be satisfied by a
# message that carried the whole prompt.
NEEDLE_COMMENT = "Rb9NsWqvZm Xt4LdKj3Px E8mZt5UwGh Tf2YcRbVn8"
NEEDLE_CHUNKS = tuple(NEEDLE_COMMENT.split())

# The same device for a theme *label*, in tokens of its own so that a leak says
# which of the two got out. A label is not something the caller sent: it is prose
# the model wrote, and a model summarizing a week writes labels out of the words
# the week used — "students called the handout [a quoted phrase]" is an ordinary
# label and an ordinary way for a student's sentence to reach a job log.
NEEDLE_LABEL = "Wq7ZmNbXt2 Ld9KjPx4Rb Uh5GwEt8Mz Yc3VnFbTr6"
NEEDLE_LABEL_CHUNKS = tuple(NEEDLE_LABEL.split())

A_SUMMARY = "Most of the week's comments are about the pace of the Thursday class."
A_THEME_LABEL = "Thursday class moved too quickly"


def an_answer(
    api: SummaryApi,
    stream_token: str = INSTRUCTOR_STREAM,
    theme_counts: tuple[int, ...] = (2,),
    label: str = A_THEME_LABEL,
) -> Any:
    """One well-formed `WeeklySummaryOutput`, as a provider would have produced it.

    `theme_counts` is how many comments each returned theme claims. It defaults to
    a count comfortably inside `A_WEEK`, so every test that is not about the count
    gets an answer nothing refuses on that ground; the two tests that are about it
    pass the number they are asserting. `label` is what the model called the theme,
    which matters to exactly one test: labels are model prose and can carry a
    student's words.
    """
    output_model = api.contract(WEEKLY_SUMMARY_OUTPUT)
    theme_model = api.contract(COMMENT_THEME)
    return output_model(
        stream=api.stream(stream_token),
        summary=A_SUMMARY,
        themes=tuple(theme_model(label=label, comment_count=count) for count in theme_counts),
        prompt_version=api.constant(SUMMARY_PROMPT_VERSION),
        model_id="e4-05-task-test-model",
    )


def chain_text(failure: BaseException) -> str:
    """Everything a raised failure and its causes said, as one string.

    The whole chain rather than the outermost message, because a polite message
    raised `from` one that quotes a week's comments leaks exactly as much. Read in
    one place so the two refusal tests below cannot drift into checking different
    amounts of the same chain (`docs/MISTAKES.md` entry 13).
    """
    chain: list[BaseException] = []
    current: BaseException | None = failure
    while current is not None and not any(link is current for link in chain):
        chain.append(current)
        current = current.__cause__ or current.__context__
    return "\n".join(str(link) for link in chain)


def test_a_week_with_no_comments_answers_the_empty_shape_without_reaching_a_model(
    summary_api: SummaryApi,
) -> None:
    """Acceptance criterion 4's zero half, and the call that must not happen.

    "Zero comments in, the contract's stated empty shape out, never an invented
    theme." §5.1 makes an empty group show "a one-line notice, not a hidden
    heading", and there is nothing for a model to summarize — so the call is not
    merely wasteful, it is a request for a summary of nothing, which is the one
    request most likely to come back with something invented.

    **The gateway used here fails on any attribute access at all**, so this
    asserts that no call was made without naming the method a call would travel
    through. A double that answered would let the empty path pass while spending a
    provider request per empty stream, on every section, every Monday.

    **The audit pair says a model did not answer**, which is ADR 0054's rule for
    the character floor applied to the one other place in this repository where a
    record exists without a call behind it. A record naming `summary.v1` and a
    real model id would be a record of a call nobody made — and E4-06 stores it.

    **The mutation this kills:** a task that calls the gateway with an empty
    comment list; one that answers an empty *summary* rather than the stated
    sentence, leaving §5.1's notice with nothing to render; and one that invents a
    theme. **Its pair is the test below**, where a week with comments must reach
    the gateway exactly once.
    """
    gateway = RefusingGateway()

    record = call_summarize(
        summary_api.task(),
        (),
        stream=summary_api.stream(INSTRUCTOR_STREAM),
        response_count=0,
        gateway=gateway,
    )

    assert (
        gateway.reached == []
    ), f"the task reached {gateway.reached} on the gateway for a week with no comments."
    assert tuple(record.summary.themes) == (), (
        f"a week with no comments came back with the themes {list(record.summary.themes)}. "
        "E4-05's fourth criterion: never an invented theme."
    )
    assert record.summary.summary == summary_api.constant(EMPTY_WEEK_SUMMARY), (
        f"the empty week's summary is {record.summary.summary!r} and `app.ai.tasks` publishes "
        f"{summary_api.constant(EMPTY_WEEK_SUMMARY)!r}. §5.1: an empty group shows a one-line "
        "notice, and the task states it rather than each surface inventing one."
    )
    assert record.summary.prompt_version == summary_api.constant(EMPTY_WEEK_PROMPT_VERSION), (
        f"the empty week's record names the prompt version "
        f"{record.summary.prompt_version!r}. ADR 0054's rule: a record produced without a "
        "model call names the reason in its audit pair rather than naming a prompt that was "
        "never rendered."
    )
    assert record.summary.model_id == summary_api.named(
        summary_api.gateway(),
        NOT_A_MODEL,
        "ADR 0054's consequences put the marker in `app/ai/gateway.py` as `NOT_A_MODEL`, "
        "'because the gateway is what knows no model answered'.",
    ), (
        f"the empty week's record names {record.summary.model_id!r} as the model that "
        "answered. No model answered."
    )
    assert record.response_count == 0


def test_a_week_with_comments_reaches_the_gateway_exactly_once(summary_api: SummaryApi) -> None:
    """SPEC §7.4's single-shot boundary: one call in, one validated object out.

    "No tool use, no planning loop, no iterative retrieval." A summary over a
    week's comments is exactly the task where a loop is tempting — summarize in
    batches, then summarize the summaries — and §7.4 refuses it for the reasons it
    gives: stable execution paths for the CI gates, and an auditable record that a
    specific prompt version and model id produced a specific answer.

    **The pair with the test above is the point.** Zero comments must produce zero
    calls and three comments exactly one, and neither number is interesting
    alone: a task that never called passes the first, and a task that always
    called passes nothing.

    **The mutation this kills:** a per-comment call, a map-reduce over batches, or
    a retry loop written into the task on top of the gateway's own bounded re-ask.
    """
    gateway = ScriptedGateway(an_answer(summary_api))

    record = call_summarize(
        summary_api.task(),
        A_WEEK,
        stream=summary_api.stream(INSTRUCTOR_STREAM),
        response_count=RESPONSES_THAT_WEEK,
        gateway=gateway,
    )

    assert len(gateway.calls) == 1, (
        f"the task made {len(gateway.calls)} gateway calls for one stream's week of "
        f"{len(A_WEEK)} comments. SPEC §7.4: one call in, one validated object out."
    )
    assert record.summary.summary == A_SUMMARY, (
        "the record does not carry the summary the gateway answered with, so what it carries "
        "came from somewhere else."
    )


def test_the_call_names_the_summary_prompt_version_its_own_timeout_and_the_contract(
    summary_api: SummaryApi,
) -> None:
    """What the task asks the gateway for, which is where three criteria meet.

    ADR 0031 makes the recorded prompt version the file's stem and §7.4 makes
    every task's output "a Pydantic model rather than parsed JSON" that the
    gateway validates — so the call has to name both, and acceptance criterion 6
    ("prompt version and model id flow through the task's return") has nothing
    behind it if the version asked for is not the version stored.

    **The timeout is its own constant and is not §3.3's.** The validity budget is
    a student's, four seconds, because somebody is waiting on a submit; nobody is
    waiting on a Monday report job, and a summary over a week of comments is a
    longer call. Dispute E2-12-06 is the record of what happens when one budget is
    borrowed for a different caller: two full eval runs were voided because a
    merely slow answer was replaced by a character count.

    **The mutation this kills:** the summary call made under
    `VALIDITY_TIMEOUT_SECONDS`, which fails a normal-length summary on a slow
    afternoon and floors nothing (the summary path has no floor); the prompt
    rendered under one version and recorded under another; and an untyped call,
    which lets prose through as a summary.
    """
    gateway = ScriptedGateway(an_answer(summary_api))

    call_summarize(
        summary_api.task(),
        A_WEEK,
        stream=summary_api.stream(INSTRUCTOR_STREAM),
        response_count=RESPONSES_THAT_WEEK,
        gateway=gateway,
    )

    assert gateway.calls, "the task made no gateway call, so there is nothing here to read."
    asked = gateway.calls[0]
    assert asked, (
        "the gateway was called with no keyword arguments at all. `tests/evals/live.py` calls "
        "`run_task_with_usage(prompt=..., prompt_version=..., output_model=..., timeout=...)`, "
        "and a positional call shape is an interface question for the ticket."
    )

    assert asked.get("prompt_version") == summary_api.constant(SUMMARY_PROMPT_VERSION), (
        f"the call names the prompt version {asked.get('prompt_version')!r} and "
        f"`app.ai.tasks` publishes {summary_api.constant(SUMMARY_PROMPT_VERSION)!r}."
    )
    assert asked.get("timeout") == summary_api.constant(SUMMARY_TIMEOUT_SECONDS), (
        f"the call is made at a timeout of {asked.get('timeout')!r} and E4-05 settles "
        f"{summary_api.constant(SUMMARY_TIMEOUT_SECONDS)!r} for this task. A budget borrowed "
        "from the submit path is a measurement of something else (dispute E2-12-06)."
    )
    assert asked.get("output_model") is summary_api.contract(WEEKLY_SUMMARY_OUTPUT), (
        f"the call asks the gateway to validate against {asked.get('output_model')!r}. §7.4: "
        "the gateway validates against the task's own Pydantic model and surfaces persistent "
        "failures as errors rather than letting prose propagate."
    )

    prompt = str(asked.get("prompt", ""))
    for comment in A_WEEK:
        assert comment in prompt, (
            f"the prompt the task sent does not carry {comment!r}. §4: 'comments from "
            "under-threshold weeks are not discarded — they feed the summary'."
        )


def test_the_stated_response_count_is_the_callers_and_not_the_number_of_comments(
    summary_api: SummaryApi,
) -> None:
    """§5.1's "state the response count they draw from", from the one source that knows.

    A week's response count and its comment count are different numbers: §3.2
    makes both comments optional unless the rating is two or below, so nine
    responses can carry three comments. A task that answered `len(comments)` would
    put a smaller, plausible, wrong number under every summary — and being
    plausible is what would keep it there.

    **The mutation this kills:** the count derived inside the task from the
    comments it was given, or from the themes the model returned. The two numbers
    here differ on purpose, so a derivation cannot coincide with the truth.
    """
    gateway = ScriptedGateway(an_answer(summary_api))

    record = call_summarize(
        summary_api.task(),
        A_WEEK,
        stream=summary_api.stream(INSTRUCTOR_STREAM),
        response_count=RESPONSES_THAT_WEEK,
        gateway=gateway,
    )

    assert record.response_count == RESPONSES_THAT_WEEK, (
        f"the caller injected a response count of {RESPONSES_THAT_WEEK} over {len(A_WEEK)} "
        f"comments and the record states {record.response_count}. §5.1's sentence is about "
        "responses; the caller has that number and the model does not."
    )


def test_an_answer_about_the_other_stream_is_refused(summary_api: SummaryApi) -> None:
    """The cross-stream bleed the per-stream call exists to prevent, refused rather than stored.

    E4-05 settles one call per stream because "a cross-stream bleed (course
    complaint summarized into the instructor stream) is a real failure the split
    prevents structurally". Structurally means the request; this is the other
    half — an answer that comes back labelled with the stream nobody asked about
    is a shape violation, not a summary, and §7.4 has such things surface as the
    gateway's error "rather than letting a malformed classification propagate".

    **What would happen without this:** the answer validates — it is a
    well-formed `WeeklySummaryOutput` — so nothing else in the stack refuses it,
    and E4-06 stores a course summary under the instructor heading of §5.1's
    report. The instructor reads criticism of the course as criticism of
    themselves.

    **The class is named rather than left as any exception** (`docs/MISTAKES.md`
    entry 49's rule about establishing which layer refused): a bare `Exception`
    here is satisfied by a `TypeError` from a call shape this test got wrong.
    **Its pair is the test above**, where the matching stream is accepted — a task
    that refused every answer passes this one alone.
    """
    invalid = summary_api.error(RESPONSE_INVALID_ERROR)
    gateway = ScriptedGateway(an_answer(summary_api, COURSE_STREAM))

    with pytest.raises(invalid):
        call_summarize(
            summary_api.task(),
            A_WEEK,
            stream=summary_api.stream(INSTRUCTOR_STREAM),
            response_count=RESPONSES_THAT_WEEK,
            gateway=gateway,
        )


def test_a_theme_claiming_more_comments_than_the_week_held_is_refused(
    summary_api: SummaryApi,
) -> None:
    """An arithmetic no reading of the week supports, refused at the boundary that knows.

    A theme's `comment_count` is a number the product shows and acts on: E4-10
    renders it beside the theme, and §5.3's draft check names the themes a
    response has not addressed "with its comment count". A model that answers
    "seven comments raised this" over a week of three has stated something the
    caller can check and nothing else can — the eval checks bound it offline and
    the mock bounds its own answers, but neither is on the path a real provider's
    answer takes.

    **Why it matters more than a wrong number usually would.** §4 hides raw
    comments below the n-threshold, so in exactly the weeks where the instructor
    cannot see the comments, the theme counts are the only quantity they are given
    — and an inflated one turns two students into seven. The task is the last
    place that still knows how many comments it sent.

    **The refusal is the gateway's own class, and its message quotes nothing.**
    Same discipline as the cross-stream refusal: `AIResponseInvalidError`, so a
    caller branching on ADR 0056's four sees an answer the contract refuses rather
    than a provider fault; and no comment text in the chain, because a
    Monday-report job writes whatever it catches to a log (SPEC §10, E3's decision
    10). The needle is asserted to have reached the gateway first — a message
    cannot leak text that was never sent.

    **The mutation this kills:** the overclaim check deleted — a theme claiming
    more comments than the week held is filed as-is. **Its pair is the test
    below**, at exactly the week's length, which is what separates this from an
    off-by-one and from a task that refuses every theme.
    """
    invalid = summary_api.error(RESPONSE_INVALID_ERROR)
    comments = (NEEDLE_COMMENT, *A_WEEK)
    gateway = ScriptedGateway(
        an_answer(summary_api, theme_counts=(len(comments) + 1,)),
    )

    with pytest.raises(invalid) as raised:
        call_summarize(
            summary_api.task(),
            comments,
            stream=summary_api.stream(INSTRUCTOR_STREAM),
            response_count=RESPONSES_THAT_WEEK,
            gateway=gateway,
        )

    sent = str(gateway.calls[0].get("prompt", "")) if gateway.calls else ""
    assert NEEDLE_COMMENT in sent, (
        "the needle comment never reached the gateway, so the leak assertion below would pass "
        "against a task that sent nothing."
    )

    leaked = sorted(chunk for chunk in NEEDLE_CHUNKS if chunk in chain_text(raised.value))
    assert not leaked, (
        f"the refusal's message chain carries {leaked} out of a student's comment. A theme "
        "count is a number; saying which theme was wrong does not need the week's text."
    )


def test_the_overclaim_refusal_does_not_quote_the_offending_themes_label(
    summary_api: SummaryApi,
) -> None:
    """The refusal names a number, never the model's prose about the week.

    The obvious message for this refusal names the theme it refused — "the theme
    'X' claims 7 of 3 comments" — and that label is the one part of the answer
    written out of the week's own words. §5.1's themes summarize what students
    said, so a model that met a blunt comment writes a blunt label, and a
    Monday-report job that logs what it caught has then written a student's phrase
    into an operator's log. SPEC §10 forbids exactly that, and E3's decision 10 and
    E4-06 both rest on it.

    **This is not covered by the other no-leak test, and a re-mutation proved
    it.** That one plants its needle in a *comment* and drives the *stream*
    refusal, so interpolating the offending theme's label into the overclaim
    message left every test in this module green. Two refusal paths, two message
    builders, and only one of them was watched — `docs/MISTAKES.md` entry 13's
    shape, one hazard met at two call sites and worked around at one.

    **The canary is what makes the silence mean discipline rather than
    blindness.** The needle is asserted to be in the answer the task was handed,
    and the task is asserted to have taken that answer, so "the chain does not
    carry it" is a statement about the message rather than about a fixture that
    never planted anything.

    **The mutation this kills:** the offending theme's label interpolated into the
    overclaim refusal message. **The near miss that must stay green:** a message
    naming the counts, the stream, or the number of themes — none of which is
    anybody's prose, and all of which a reader of the log actually needs.
    """
    invalid = summary_api.error(RESPONSE_INVALID_ERROR)
    answer = an_answer(summary_api, theme_counts=(len(A_WEEK) + 1,), label=NEEDLE_LABEL)
    gateway = ScriptedGateway(answer)

    assert NEEDLE_LABEL in answer.themes[0].label, (
        "the fixture did not plant the needle in the theme's label, so the assertion below "
        "would report discipline about a message that had nothing to leak."
    )

    with pytest.raises(invalid) as raised:
        call_summarize(
            summary_api.task(),
            A_WEEK,
            stream=summary_api.stream(INSTRUCTOR_STREAM),
            response_count=RESPONSES_THAT_WEEK,
            gateway=gateway,
        )

    assert len(gateway.calls) == 1, (
        f"the task made {len(gateway.calls)} gateway calls, so it may never have read the "
        "answer this test planted the needle in."
    )

    said = chain_text(raised.value)
    leaked = sorted(chunk for chunk in NEEDLE_LABEL_CHUNKS if chunk in said)
    assert not leaked, (
        f"the overclaim refusal's message chain carries {leaked} out of the offending theme's "
        f"label. A label is prose the model wrote about the week's comments; the refusal is "
        f"about two numbers and needs neither. The whole chain said: {said[:400]!r}"
    )


def test_a_theme_claiming_exactly_the_weeks_comments_is_kept(summary_api: SummaryApi) -> None:
    """The near miss: every comment in one theme is a real week, not an overclaim.

    A week where one thing happened is the ordinary case for a small section —
    three comments, all about the same lab — and a bound written as "fewer than
    the comments" would refuse it. The refusal above and this acceptance are one
    rule with one boundary, and the boundary is at the week's own length.

    **The theme reaches the record unchanged**, label and count both, because a
    check that silently clamped the number to something it liked would satisfy an
    assertion that merely says "no error" while still putting a figure in front of
    an instructor that the model did not give and the week does not support.

    **The mutation this kills:** `>=` written where `>` belongs, and a blanket
    refusal of any answer carrying themes. **Alone it proves nothing** — a task
    with no check at all passes it — which is why it is written as the pair to the
    test above and named for the boundary rather than for the outcome.
    """
    gateway = ScriptedGateway(an_answer(summary_api, theme_counts=(len(A_WEEK),)))

    record = call_summarize(
        summary_api.task(),
        A_WEEK,
        stream=summary_api.stream(INSTRUCTOR_STREAM),
        response_count=RESPONSES_THAT_WEEK,
        gateway=gateway,
    )

    themes = tuple(record.summary.themes)
    assert (
        len(themes) == 1
    ), f"the answer carried one theme and the record carries {len(themes)}: {themes!r}."
    assert themes[0].comment_count == len(A_WEEK), (
        f"the model said {len(A_WEEK)} comments carried the theme and the record says "
        f"{themes[0].comment_count}. A count the task adjusted is a figure nobody produced."
    )
    assert themes[0].label == A_THEME_LABEL, (
        f"the theme's label reached the record as {themes[0].label!r}. The task validates an "
        "answer; it does not rewrite one."
    )


def test_a_provider_failure_is_raised_rather_than_summarized_away(
    summary_api: SummaryApi,
) -> None:
    """No floor on this path, and that is a decision rather than an omission.

    SPEC §3.3's fail-open floor belongs to the validity task alone: it exists so a
    student is never blocked by an outage at submit time. Nobody is being blocked
    on a Monday report, and there is no character count that could stand in for a
    summary — so a provider failure has to leave this task as a failure. A task
    that answered the empty shape on an outage would produce a record identical to
    a genuinely empty week's, and §5.1's "the summary is the only comment signal"
    week would silently become a week that reports no comments at all.

    **`docs/MISTAKES.md` entry 49 is exactly this shape**: a return value that
    collapses "refused" and "the dependency was down" into one is a value no test
    can read, so what is asserted is the raise and its class.

    **The mutation this kills:** a `try/except` around the gateway call returning
    the empty shape, or re-raising as `AIResponseInvalidError` — which would tell
    E4-06's job that the model answered badly when in fact the provider never
    answered, and send whoever reads the job log to the prompt instead of to the
    provider.
    """
    unavailable = summary_api.error(UNAVAILABLE_ERROR)
    invalid = summary_api.error(RESPONSE_INVALID_ERROR)
    gateway = ScriptedGateway(unavailable("the provider said it cannot serve this request"))

    with pytest.raises(unavailable) as raised:
        call_summarize(
            summary_api.task(),
            A_WEEK,
            stream=summary_api.stream(INSTRUCTOR_STREAM),
            response_count=RESPONSES_THAT_WEEK,
            gateway=gateway,
        )

    assert not isinstance(raised.value, invalid), (
        f"the provider's outage surfaced as {type(raised.value).__name__}, which is the class "
        "that means the model answered with something the contract refuses. ADR 0056 makes the "
        "four classes the interface callers branch on, and a class that is both is one class."
    )


def test_a_refusal_does_not_quote_the_students_comments_back(summary_api: SummaryApi) -> None:
    """E3's decision 10 extended: no student content in what this task raises or logs.

    E4-05's trap list: "comment text in a failure log — the gateway's error paths
    must not interpolate the input; E3's decision 10 (no student content in worker
    logs) extends here and E4-06 relies on it". SPEC §10 puts it as a requirement:
    no student personally identifiable information in logs. A refusal raised from
    inside a Monday-report job is written to a job log by whatever catches it, and
    a message built by interpolating the prompt puts a week of comments there.

    **The comment is asserted to have reached the provider first.** A message
    cannot leak text that was never sent, so without that canary this passes
    against a task that sent nothing at all (`docs/MISTAKES.md` entry 3).

    **The whole exception chain is read**, because a message that quotes nothing
    and is raised `from` one that quotes everything leaks exactly as much.

    **The mutation this kills:** a refusal built as f"...{comments}..." or
    f"...{prompt}...", which is the natural way to write a message that says what
    went wrong.
    """
    invalid = summary_api.error(RESPONSE_INVALID_ERROR)
    comments = (NEEDLE_COMMENT, *A_WEEK)
    gateway = ScriptedGateway(an_answer(summary_api, COURSE_STREAM))

    with pytest.raises(invalid) as raised:
        call_summarize(
            summary_api.task(),
            comments,
            stream=summary_api.stream(INSTRUCTOR_STREAM),
            response_count=RESPONSES_THAT_WEEK,
            gateway=gateway,
        )

    sent = str(gateway.calls[0].get("prompt", "")) if gateway.calls else ""
    assert NEEDLE_COMMENT in sent, (
        "the needle comment never reached the gateway, so an assertion that the refusal does "
        "not carry it would pass against a task that sent nothing."
    )

    said = chain_text(raised.value)

    leaked = sorted(chunk for chunk in NEEDLE_CHUNKS if chunk in said)
    assert not leaked, (
        f"the refusal's message chain carries {leaked} out of the student's comment. The "
        f"whole chain said: {said[:400]!r}"
    )
