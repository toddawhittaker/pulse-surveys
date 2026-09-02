"""The §7.4 tasks, one function each (SPEC §7.4, §3.3, §8).

SPEC §13 gives this module "validity / moderation / summary / draft / draft-check
calls". E0-13 implements the first of them end to end; the other four have
contracts in `contracts.py` and prompts that belong to E2, E4, E6 and E7.

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

**This fail-open is the only one in this codebase.** `CLAUDE.md` says so and says
why it may not be generalised from: §3.3 sanctions it for the validity check
alone, and §6.2's moderation path — the one that routes a threat or a self-harm
disclosure to the Care queue — has none.

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
from importlib.resources import files
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.contracts import CommentValidityOutput, ValidityVerdict
from app.ai.gateway import NOT_A_MODEL, AIGateway, AIProviderUnavailableError
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
