"""The §7.4 tasks, one function each (SPEC §7.4, §3.3, §8).

SPEC §13 gives this module "validity / moderation / summary / draft / draft-check
calls". E0-13 implements the first of them end to end and E4-05 the third; the
other three have contracts in `contracts.py` and prompts that belong to their own
epics. The two that are here differ in more than their prompts, and the
differences are the interesting part of this module: the validity task judges one
comment for a student who is waiting, under a four-second budget, with SPEC
§3.3's floor underneath it; the summary task reads a week of them for a report
job nobody is waiting on, under a minute, with no floor at all.

A task here is the only thing that knows what its task *means*: which prompt file
to render, how long a student may be kept waiting for it, what to do when the
endpoint does not answer, and what to record afterwards. `gateway.py` knows none
of that — it takes text and a contract and hands back a validated object — which
is what keeps "replacing the provider library touches one file" true (§7.4,
E0-13's sixth criterion).

**Failing open means accepting the submission, not skipping the classification.**
§3.3: "Classifier latency budget: p95 < 2s; on provider timeout, the heuristic
floor applies and the submission is accepted, then classified async (fail open,
never block a student on an outage)." So `verdict_for_comment` catches the
one error that means "the endpoint was reached and did not classify", applies it,
and returns the contract — and the row `classify_comment_validity` then writes
says a floor decided it, under a
prompt version and a model ID that name no prompt and no model
([ADR 0054](../../../docs/adr/0054-a-floored-classification-names-the-floor-in-its-audit-pair.md)).
Everything else the gateway raises propagates: a rejected credential is not an
outage, and absorbing one would classify every comment by length for as long as
the credential stayed wrong, with nothing saying so.

**This fail-open is the only one in this codebase, and the spec is what says
why it may not be generalised from**: SPEC §3.3 sanctions it for the validity
check alone, and §6.2's moderation path — the one that routes a threat or a
self-harm disclosure to the Care queue — has none. (An earlier version of this
paragraph attributed the rule to `CLAUDE.md`, which never carried it; the E2
boundary review corrected the citation.)

**Every classification row is written here.** One function, `record_classification`,
so that "what gets stored when a model answers" is a question with one place to
read rather than a line at each call site. It writes and does not commit: the
caller owns the transaction, because E2's submit path stores the response and the
classification together or stores neither.

**The comment-validity task comes in two halves, and `classify_comment_validity`
is still the task.** `verdict_for_comment` judges and stores nothing;
`classify_comment_validity` is that call plus `record_classification`, and it is
what a caller uses when it already knows what the verdict will be recorded
against. The split exists because E2-08's submit path does not: a comment §3.3
bounces stores no `answer` row, and the verdict that bounced it still has to be
recorded (ADR 0114). Asking the model once and choosing where the row goes
afterwards is what the two halves buy, and the fail-open taxonomy stays in one
place either way.
"""

import threading
from collections.abc import Sequence
from importlib.resources import files
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.contracts import (
    CommentStream,
    CommentValidityOutput,
    ValidityVerdict,
    WeeklySummaryOutput,
    WeeklySummaryRecord,
)
from app.ai.gateway import (
    NOT_A_MODEL,
    AIGateway,
    AIProviderUnavailableError,
    AIResponseInvalidError,
)
from app.models.ai import Classification, ClassificationTask

# The prompt this task renders, named as ADR 0031 spells a `prompt_version`: the
# file's path stem under `app/ai/prompts/`, so the stored value names exactly one
# immutable file (ADR 0032). Changing the prompt means adding the next version
# beside it and changing this constant — never editing the file this names.
#
# **It named `validity.v1` until the trim of 2026-09-02, and that is exactly the
# move the paragraph above describes** (ADR 0120). `validity.v1.md` is still on
# disk and still unedited, because classifications recorded against it have to
# stay reproducible; `validity.v2.md` is the same instructions with the
# documentation that was riding in every request taken out. Rows written before
# the switch go on naming v1 and go on resolving to the text that produced them,
# which is the whole property this constant exists to carry.
VALIDITY_PROMPT_VERSION = "validity.v2"

# Where the student's text goes, spelled exactly as `prompts/README.md` requires:
# "The placeholder is `[[STUDENT_COMMENT]]`, replaced literally — with
# `str.replace`, never `str.format` or an f-string. These files carry JSON braces
# in their output examples, so `.format` raises on the example object before it
# ever reaches the placeholder."
COMMENT_PLACEHOLDER = "[[STUDENT_COMMENT]]"

# How long a student may wait for this classification before the floor takes over.
# §3.3 budgets the check at "p95 < 2s", and this is deliberately above that
# rather than equal to it: a hard limit at the budget would fall open on the
# slowest twentieth of ordinary calls, which is the floor deciding participation
# for one student in twenty on a healthy day. Twice the budget is the point where
# waiting longer costs the student more than the heuristic does.
#
# Not a configuration knob. The number follows from a figure in the spec, and an
# operator who could raise it could quietly spend a student's time to get a
# slightly better verdict.
VALIDITY_TIMEOUT_SECONDS = 4.0

# §3.3: "The prototype's ≥25-character heuristic is a placeholder only; production
# substantiveness is the classifier's call, with the character heuristic retained
# solely as the fail-open floor below." The comparison is `>=`, as written.
HEURISTIC_MINIMUM_CHARACTERS = 25

# What a floored classification records instead of a prompt version and a model
# ID. Neither is a prompt stem under `app/ai/prompts/` and neither names a model,
# deliberately: a reader resolving a stored version against that directory finds
# nothing, and knows no model was asked (ADR 0054). §7.4 rests auditability on
# "a specific prompt version and model ID produced a specific classification for
# a specific comment" — so a floor result carrying a real pair would be a record
# asserting that a model produced a verdict it was never asked for, and E2's
# async re-classification would have nothing to find.
#
# **The model marker is the gateway's constant, imported rather than spelled
# again**, because the gateway is what makes it mean something: it refuses to
# record that value from a provider that claims it, so a row carrying it can only
# have come from here. The prompt marker needs no such guarantee — a provider
# never supplies a prompt version at all.
#
# The two are load-bearing in a way a rename would break quietly: E2's
# re-classification finds floored rows by them, and §6.1's drift panel groups on
# them.
FLOOR_PROMPT_VERSION = "character-floor"
FLOOR_MODEL_ID = NOT_A_MODEL

# ---------------------------------------------------------------------------
# §7.4's weekly summary (E4-05)
# ---------------------------------------------------------------------------

# The prompt this task renders, named the way `VALIDITY_PROMPT_VERSION` above is
# and for the same reasons: the file's path stem under `app/ai/prompts/`, so a
# stored version names exactly one immutable file (ADR 0031, ADR 0032).
SUMMARY_PROMPT_VERSION = "summary.v1"

# The prompt a week **below SPEC §4's n-threshold** renders instead — the owner's
# ruling of 2026-09-09, which is that such a week's summary names themes only and
# may not reuse the commenters' own word strings.
#
# **Two live versions rather than one file with a switch**, and the reason is the
# renderer's settled signature: `render_summary_prompt(version, *, stream,
# comments)` takes three parameters and no fourth, deliberately, so that a caller
# holding identity has nowhere to put it (E4-05's second criterion, asserted as an
# equality). The version is the one dial a caller may turn, so the mode rides on
# it — which is also what `prompts/README.md` asks of a content change: add the
# next version beside the old one and leave the old one alone.
#
# What is unusual, and what
# [ADR 0162](../../../docs/adr/0162-the-small-n-summary-is-a-second-live-prompt-version-and-a-store-time-guard.md)
# records, is that **both stay live**: v1 is what an at-or-above-threshold week
# renders and v2 is what a small-N week renders, rather than v2 superseding v1.
# The gain is that a stored `prompt_version` then says which mode produced the
# row, with no second column and no inference.
SMALL_N_SUMMARY_PROMPT_VERSION = "summary.v2"

# Where the week's comments go, and where the stream they belong to goes. Two
# placeholders rather than one because they are substituted at opposite ends of
# the file: the stream is named in the instructions, and the comments are the
# last thing in the message. `prompts/README.md`'s rule about `str.replace`
# rather than `str.format` applies to both — the file carries a JSON example, so
# `.format` raises on the braces before it reaches either marker.
SUMMARY_COMMENTS_PLACEHOLDER = "[[STUDENT_COMMENTS]]"
SUMMARY_STREAM_PLACEHOLDER = "[[COMMENT_STREAM]]"

# How long the summary call may take. **Deliberately not §3.3's four seconds**,
# which is the validity task's budget and belongs to a student waiting on a
# submit. Nobody waits on this one: §7.4 triggers it from the Monday report job,
# and SPEC §10 budgets that whole job at "500 sections < 30 min" rather than any
# per-call figure. A week of comments is also a much longer prompt than one
# comment, so borrowing the submit path's budget would fail ordinary summaries on
# a slow afternoon — and this path has no floor to fall onto when it does.
#
# Sixty seconds is a limit rather than an expectation: it is there so a provider
# that stops answering cannot hold a report job open indefinitely, and it is far
# enough above a normal answer that a merely slow one still lands. Not a
# configuration knob, for the reason `VALIDITY_TIMEOUT_SECONDS` gives.
SUMMARY_TIMEOUT_SECONDS = 60.0

# What a week with no comments answers instead of calling a model.
#
# **The pair is ADR 0054's rule applied to the second place in this codebase
# where a record exists without a call behind it.** The character floor names a
# prompt version that is no prompt stem and a model id that is no model, so that
# a reader resolving either finds nothing and knows none was asked; an empty week
# is the same situation arrived at for a different reason — there was nothing to
# summarize, so nothing was sent. A record naming `summary.v1` and a real model
# would assert a call nobody made, and E4-06 stores these records.
#
# The summary text is stated here rather than at each surface because §5.1 makes
# it product copy: "empty groups show a one-line notice, not a hidden heading".
# One sentence, in one place, so the report and any later reader of a stored
# summary read the same words.
EMPTY_WEEK_PROMPT_VERSION = "empty-week"
EMPTY_WEEK_SUMMARY = "No comments were submitted this week."

# The gateway this process uses, built on first classification and kept.
_GATEWAY_LOCK = threading.Lock()
_GATEWAY: AIGateway | None = None


def process_gateway() -> AIGateway:
    """The one `AIGateway` this process shares (§7.4: "one internal `AIGateway`").

    Shared rather than built per comment, because an `AIGateway` holds a client
    per thread that has used it: one shared gateway costs a connection pool per
    threadpool thread, and a gateway per comment costs one per comment. E0-13's
    review measured the second shape leaking sockets — 6 file descriptors to 23
    over 30 calls, reclaimed only at garbage collection.

    Built on first use rather than at import: `Settings()` reads the environment,
    and `backend/migrations/env.py` and CI's `migration-drift` job import this
    package's neighbours with the database variables alone.

    The lock covers construction only. Two threads arriving together must not
    build two clients and leave one of them orphaned; after that the object is
    read-only and each thread lazily builds its own bound state inside it.
    """
    global _GATEWAY
    with _GATEWAY_LOCK:
        if _GATEWAY is None:
            _GATEWAY = AIGateway()
        return _GATEWAY


class PromptError(Exception):
    """A prompt file is missing, or is not the prompt this code expects.

    Loud and early, because the quiet version is worse: a prompt whose
    `[[STUDENT_COMMENT]]` marker has been edited away renders to instructions
    with no comment after them, and the model then classifies nothing at all —
    confidently, and in the contract's own shape.
    """


def load_prompt(version: str) -> str:
    """The text of one prompt file, named by its path stem (ADR 0031).

    Read through `importlib.resources` rather than by building a path from
    `__file__`, so the lookup goes through the same mechanism that decides
    whether the file is in the installed distribution at all — `pyproject.toml`
    ships `app/ai/prompts/**/*` as package data for that reason, and
    `docs/MISTAKES.md` entry 18 is a directory that existed in the source tree
    and in no built artifact. `app.views_sql.read_sql` reads its SQL the same way.
    """
    source = files("app.ai") / "prompts" / f"{version}.md"
    try:
        return source.read_text(encoding="utf-8")
    except OSError:
        # `FileNotFoundError` is the case this is written for and it is an
        # `OSError`; the wider catch also covers a distribution where the
        # directory shipped and the file did not (`docs/MISTAKES.md` entry 18).
        problem = f"There is no prompt file `{version}.md` under `app/ai/prompts/`."
    raise PromptError(problem)


def render_prompt(version: str, comment: str) -> str:
    """One prompt with the student's comment in it, and nothing after it.

    `prompts/README.md`: "The marker opens the input and has no closing half. A
    closing marker is a string the input can contain, and then the boundary sits
    wherever the student put it. 'To the end of the message' cannot be forged,
    and it means the gateway must append nothing after the comment." The
    placeholder is the last thing in the file, so replacing it in place is what
    keeps that true.

    A prompt with no placeholder is refused rather than sent. The alternative is
    a request that asks a model to classify a comment it was never given.
    """
    prompt = load_prompt(version)
    if COMMENT_PLACEHOLDER not in prompt:
        raise PromptError(
            f"The prompt `{version}.md` carries no {COMMENT_PLACEHOLDER} marker, so the comment "
            "has nowhere to go. `app/ai/prompts/README.md` states the scheme."
        )
    return prompt.replace(COMMENT_PLACEHOLDER, comment)


def character_floor(comment: str) -> CommentValidityOutput:
    """§3.3's fail-open floor: the verdict a comment's length alone decides.

    Two verdicts and never the third. `nonsense` is a judgement about content —
    §3.3's example is "adfasdfa" — and length cannot tell keyboard mashing from a
    terse real answer. Calling a short comment `nonsense` during an outage would
    reduce the section's validity rate over something the student did not do.

    The pair it carries says a model was not asked. See `FLOOR_PROMPT_VERSION`.
    """
    long_enough = len(comment.strip()) >= HEURISTIC_MINIMUM_CHARACTERS
    return CommentValidityOutput(
        verdict=ValidityVerdict.SUBSTANTIVE if long_enough else ValidityVerdict.INSUFFICIENT,
        prompt_version=FLOOR_PROMPT_VERSION,
        model_id=FLOOR_MODEL_ID,
    )


def record_classification(
    session: Session,
    task: ClassificationTask,
    output: CommentValidityOutput,
    *,
    answer_id: UUID | None = None,
) -> Classification:
    """Store one verdict, with the pair that says what produced it (SPEC §8).

    `answer_id` is the comment the verdict is about — ADR 0055's promised
    reference, which E2-08 added the column for. It is optional in the signature
    and not in the design: every caller that has an `answer` row passes it, and it
    defaults to `None` only because the rows written before E2 exist and name
    nothing. A verdict stored with no subject is a verdict the async
    re-classification cannot find and a disputed grade cannot be answered from.

    Appended, never updated: a re-run under a new prompt version is what §6.1's
    drift panel and §9.3's eval floors compare against the earlier answer, and an
    `UPDATE` deletes the row the comparison is with. The application's connection
    holds `SELECT` and `INSERT` on this table and nothing else, so that is a
    property of the database rather than of this function
    (`classification_grants_v001.sql`, ADR 0055).

    Flushed and not committed. The caller owns the transaction: E2's submit path
    writes the response and its classification together or writes neither, and a
    commit here would take that choice away from it.
    """
    row = Classification(
        answer_id=answer_id,
        task=task,
        verdict=output.verdict.value,
        prompt_version=output.prompt_version,
        model_id=output.model_id,
    )
    session.add(row)
    session.flush()
    return row


def verdict_for_comment(
    comment: str,
    gateway: AIGateway | None = None,
) -> CommentValidityOutput:
    """§7.4's comment-validity task, judged and not yet recorded.

    One call in, one validated object out, and **no row and no session** — which
    is the whole of what separates this from `classify_comment_validity` below.

    On an endpoint that was reached and could not classify — it did not answer
    in time, or it answered to say it is temporarily unavailable — the character
    floor decides and the submission goes through: "fail open, never block a
    student on an outage" (§3.3). Every other gateway failure propagates,
    including a request that never arrived: a refused connection, a connect
    timeout against a route that drops packets, a failed TLS handshake. None of
    those is what §3.3 sanctions the floor for, and ADR 0056 has the table. E2's
    submit path is where a caller decides what to do with one.

    The gateway is a parameter so that a caller holding one can pass it; a
    caller that passes nothing gets `process_gateway()`, which is the one this
    process shares. Building one per comment is a connection pool per comment,
    and that shape was measured leaking sockets in E0-13's review.

    **Why the judging is separable at all**, since the pair below was one function
    until E2-08's security round: the submit path has to know the verdict *before*
    it knows whether an `answer` row will exist to name. A comment §3.3 bounces
    stores no answer and no response, and the verdict that bounced it still has to
    be recorded — §7.4 rests auditability on "a specific prompt version and model
    ID produced a specific classification". Splitting the call from the write is
    what lets the caller record the same single call against an answer or against
    none, without asking the model twice and without a second copy of the floor
    rule anywhere. The taxonomy stays here, in one place, where ADR 0056 put it.
    """
    gateway = gateway or process_gateway()
    try:
        return gateway.run_task(
            prompt=render_prompt(VALIDITY_PROMPT_VERSION, comment),
            prompt_version=VALIDITY_PROMPT_VERSION,
            output_model=CommentValidityOutput,
            timeout=VALIDITY_TIMEOUT_SECONDS,
        )
    except AIProviderUnavailableError:
        return character_floor(comment)


def classify_comment_validity(
    session: Session,
    comment: str,
    gateway: AIGateway | None = None,
    *,
    answer_id: UUID | None = None,
) -> CommentValidityOutput:
    """§7.4's comment-validity task: judge one comment and store the verdict.

    The two halves above and below composed — `verdict_for_comment` decides
    and `record_classification` writes — which is the whole of what this function
    is. §3.3 gates participation on the verdict, and refuses an `insufficient`
    comment to the student's face at submit time with coaching copy, so what this
    returns decides both what a student is told and what a section's validity rate
    says.

    Callers that want both in one step use this, which is every caller that
    already knows what the verdict will be recorded against: the async
    re-classification sweep, and any later task. E2-08's submit path calls the two
    halves separately, for the reason `verdict_for_comment` gives.

    `answer_id` is the `answer` row this comment was submitted on, stored on the
    verdict so that the row names what it judged (ADR 0055, E2-08). See
    `record_classification` for why it has a default at all.
    """
    output = verdict_for_comment(comment, gateway)
    record_classification(session, ClassificationTask.COMMENT_VALIDITY, output, answer_id=answer_id)
    return output


# ---------------------------------------------------------------------------
# §7.4's weekly summary (E4-05)
# ---------------------------------------------------------------------------


def render_comment_blocks(comments: Sequence[str]) -> str:
    """One week's comments as numbered blocks, in the order they were given.

    Numbered so that a model can count them and a theme's `comment_count` means
    something; blank-line separated so that a comment ending mid-sentence does
    not read as the beginning of the next one. Neither is decoration: a week is
    several comments where the validity task has one, and "the input" has to stay
    legible as a list without a closing marker to end it with.

    Nothing is dropped, deduplicated, truncated or reordered. §4: "comments from
    under-threshold weeks are not discarded — they feed the summary", so a
    renderer that lost one would remove a student's week from the only signal
    their instructor gets, and one that repeated a comment would inflate every
    theme count a model produces.
    """
    return "\n\n".join(
        f"Comment {number}:\n{comment}" for number, comment in enumerate(comments, start=1)
    )


def render_summary_prompt(
    version: str,
    *,
    stream: CommentStream,
    comments: Sequence[str],
) -> str:
    """One summary prompt: the stream in the instructions, the comments at the end.

    **The signature is the identity boundary** (E4-05's second acceptance
    criterion). It takes the stream and the comment texts and nothing else, so a
    caller holding a session, a section and a student has nowhere to put any of
    them — SPEC §4 keys responses to the LMS user id and lets identity out
    through the audited Care reveal alone, and comment text going to a provider
    is that boundary in a different door. Keeping identity out of a prompt is not
    a thing each caller remembers; it is a thing this signature makes impossible.

    **The comments are last and nothing follows them**, which is
    `prompts/README.md`'s injection boundary — "'to the end of the message'
    cannot be forged, and it means the gateway must append nothing after the
    comment". `render_prompt` above keeps the same property for one comment; here
    the placeholder is the last thing in the file, so replacing it in place is
    what keeps the last student's last word from being followed by an
    instruction it was written to defeat.

    Both placeholders are required. A prompt missing either is refused rather
    than half-rendered: a template with no stream marker asks a model to
    summarize a stream it was never told, and one with no comments marker asks it
    to summarize a week it was never shown. Neither failure is visible in the
    answer, which comes back well-formed and about nothing.

    The refusal names the version and the marker and quotes no comment. A
    `PromptError` raised inside E4-06's Monday job is written to a job log by
    whatever catches it, and SPEC §10 forbids student text there.
    """
    prompt = load_prompt(version)
    for placeholder in (SUMMARY_STREAM_PLACEHOLDER, SUMMARY_COMMENTS_PLACEHOLDER):
        if placeholder not in prompt:
            raise PromptError(
                f"The prompt `{version}.md` carries no {placeholder} marker, so a summary "
                "cannot be rendered from it. `app/ai/prompts/README.md` states the scheme, and "
                "the summary prompt names the stream in its instructions and ends with the "
                "week's comments."
            )
    prompt = prompt.replace(SUMMARY_STREAM_PLACEHOLDER, stream.value)
    return prompt.replace(SUMMARY_COMMENTS_PLACEHOLDER, render_comment_blocks(comments))


def summarize_stream(
    comments: Sequence[str],
    *,
    stream: CommentStream,
    response_count: int,
    small_n: bool = False,
    gateway: AIGateway | None = None,
) -> WeeklySummaryRecord:
    """§7.4's weekly-summary task for one stream: one call in, one record out.

    **One call per stream, and a week is two calls made by the caller.** §5.1
    groups every comment under "About the instructor" / "About the course", and
    the split is what stops a course complaint being summarized into the
    instructor's stream: the two calls never see each other's comments, so the
    bleed is prevented by the request rather than noticed in the answer. E4-06's
    job is what makes the second call. ADR 0148 records the choice and its cost.

    **An empty week reaches no model at all.** There is nothing to summarize, and
    a request for a summary of nothing is the request most likely to come back
    with something invented — while an empty stream is common enough (§5.1's
    empty group "shows a one-line notice") that a request per empty stream per
    section per week is a bill nobody chose. The record it answers with names
    `EMPTY_WEEK_PROMPT_VERSION` and the gateway's `NOT_A_MODEL`, because no model
    answered; see those constants for ADR 0054's rule. A *small* week is not this
    case: two comments in, a summary out, because below the n-threshold that
    summary is the only comment signal the instructor gets.

    **The response count is the caller's and is never derived here.** §5.1 has a
    summary state the count it draws from, and §3.2 makes a comment optional
    above the rating threshold — so nine responses can carry three comments, and
    `len(comments)` would put a smaller, plausible, wrong number under every
    summary. The caller has the real number; the model is not asked for it.

    **`small_n` is the same kind of value and arrives the same way.** The owner's
    ruling of 2026-09-09 is that a week below SPEC §4's n-threshold has its
    summary name themes only, reusing none of the commenters' word strings, and
    this function's whole part in that is to render the prompt that says so —
    `SMALL_N_SUMMARY_PROMPT_VERSION` rather than `SUMMARY_PROMPT_VERSION`, which
    the stored row then names. It is not derived here for the reason the count is
    not: the threshold is configuration read through one function in the service
    layer, and a second reading of it inside the AI layer is a second source for
    the number a confidentiality promise is made on. It defaults to `False`, which
    is the unchanged contract.

    **The instruction is soft and this function does not pretend otherwise.** A
    model may ignore it and a provider swap changes what ignoring means, so the
    ruling is also enforced structurally where the row is written —
    `app.services.reporting` refuses a small-N summary that reuses a run of a
    comment it was fed. This half is what makes the model *asked*; that half is
    what makes the answer *checked*.

    **An answer about the other stream is refused.** It validates — it is a
    well-formed `WeeklySummaryOutput` — so nothing else in the stack would stop
    it, and E4-06 would store a course summary under §5.1's instructor heading.
    `AIResponseInvalidError` is the class for it: §7.4 has the gateway surface a
    persistent shape violation "rather than letting a malformed classification
    propagate", and an answer to a question nobody asked is that.

    **There is no fail-open here, and that is a decision.** SPEC §3.3 sanctions
    the floor for the validity check alone, because a student must never be
    blocked by an outage at submit time. Nobody is blocked by a Monday report,
    there is no heuristic that could stand in for a summary, and a task that
    answered the empty shape on an outage would produce a record identical to a
    genuinely empty week's — turning "the only comment signal" week into a week
    that reports no comments. Every gateway failure propagates as its own class,
    so a reader of the job log is sent to the provider or to the prompt according
    to which one it was.

    **A theme claiming more comments than the week held is refused too**, and
    this is the last place that can. The count is a number the product shows and
    acts on — E4-10 renders it beside the theme and §5.3's draft check reads it —
    and §4 hides the raw comments below the n-threshold, so in exactly the weeks
    where an instructor cannot check it themselves, an inflated count turns two
    students into seven. The bound is the number of comments *this call sent*,
    which nothing downstream still knows: the eval checks bound it offline and
    the mock bounds its own answers, and neither is on the path a real provider's
    answer takes. Exactly the week's length is legitimate and is kept — a small
    section where every comment is about the same lab is the ordinary case.

    Nothing here rewrites an answer. A count clamped to something plausible would
    put a figure in front of an instructor that neither the model gave nor the
    week supports, and it would do it silently; the answer is refused whole.

    **Nothing raised or logged from here carries a comment.** E3's decision 10
    keeps student content out of worker logs, SPEC §10 requires it, and E4-06
    relies on it: the refusals below are built from the two stream tokens, the
    counts, and static text. **A theme's label is deliberately not quoted**,
    although naming the offending theme would read as more helpful — a label is
    model output written after reading a week of comments, so it is the one part
    of an answer that can carry a student's words back into a job log.
    """
    if not comments:
        return WeeklySummaryRecord(
            summary=WeeklySummaryOutput(
                stream=stream,
                summary=EMPTY_WEEK_SUMMARY,
                themes=(),
                prompt_version=EMPTY_WEEK_PROMPT_VERSION,
                model_id=NOT_A_MODEL,
            ),
            response_count=response_count,
        )

    gateway = gateway or process_gateway()
    # Which prompt this week renders, and the only thing `small_n` decides here.
    # The caller knows the week's response count and SPEC §4's threshold; this
    # function is told the answer rather than working it out, for the reason
    # `response_count` is the caller's — the threshold is configurable and read
    # through `app.services.report_comments.n_threshold`, and a second reading of
    # it in the AI layer is a second source for the number a promise is made on.
    version = SMALL_N_SUMMARY_PROMPT_VERSION if small_n else SUMMARY_PROMPT_VERSION
    output = gateway.run_task(
        prompt=render_summary_prompt(version, stream=stream, comments=comments),
        prompt_version=version,
        output_model=WeeklySummaryOutput,
        timeout=SUMMARY_TIMEOUT_SECONDS,
    )
    if output.stream is not stream:
        raise AIResponseInvalidError(
            f"The summary came back about the {output.stream.value!r} stream and the "
            f"{stream.value!r} stream was asked about. SPEC §5.1 groups comments under "
            "'About the instructor' / 'About the course', and a summary filed under the wrong "
            "heading reads as criticism of the wrong thing."
        )
    overclaimed = sorted(
        theme.comment_count for theme in output.themes if theme.comment_count > len(comments)
    )
    if overclaimed:
        raise AIResponseInvalidError(
            f"The summary carries {len(overclaimed)} theme(s) claiming {overclaimed} comments "
            f"out of the {len(comments)} this call sent. A theme cannot be carried by more "
            "comments than the week holds, and the count is a figure the report shows and "
            "§5.3's draft check reads."
        )
    return WeeklySummaryRecord(summary=output, response_count=response_count)
