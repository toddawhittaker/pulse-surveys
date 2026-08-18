"""The one place a model is called from (SPEC §7.4).

§7.4: "All model calls go through one internal `AIGateway` with per-task prompts,
timeouts, retries, and eval hooks." This module is that gateway, and it is
deliberately small: it takes rendered prompt text and a Pydantic contract, sends
one request to an OpenAI-compatible endpoint, and hands back a validated instance
of that contract. It loads no prompt, opens no database connection, and decides
nothing about any particular task.

**This is the only module in `backend/app/` that imports a provider library**,
which is E0-13's sixth acceptance criterion; the confinement sweep in the unit
suite is what keeps it true. §7.4's reason: the library "is young and
fast-moving, so pin it and keep the gateway interface thin enough that replacing
it is a day's work". A second importer — a task building its own client, a batch
job, a helper — is another file that replacement has to touch, and each one looks
harmless in its own diff. The library is `pydantic-ai-slim[openai]`, which is
§7.4's `pydantic-ai` without the eight other extras the metapackage turns on;
[ADR 0053](../../../docs/adr/0053-the-gateway-speaks-openai-through-pydantic-ai.md)
records the decision and what was measured. **Nothing here imports `openai`**,
although that extra installs it: the SDK is what `pydantic-ai` talks to, not what
this project writes against, and a direct import would be the second importer the
criterion is about.

**Single-shot, and the retry does not soften it.** §7.4: "Every task in the table
above is one call in, one validated object out — no tool use, no planning loop,
no iterative retrieval." So the output mode is `NativeOutput`, which asks the
endpoint for a JSON object against the payload's schema: no tool is declared, and
the request carries `response_format` rather than `tools`. A shape violation
produces one more request, and that request is the *same prompt asked again*
rather than a conversation about what went wrong — see `run_task` for why the
library's own feedback retry is turned off.

**The audit pair is the gateway's to fill in, and a model that supplies it is
refused.** [ADR 0031](../../../docs/adr/0031-every-task-contract-carries-the-prompt-version-and-model-id.md):
"The gateway must reject a provider payload that contains either key, *before*
merging anything into it, and treat that as the shape violation §7.4 has it retry
on. Not overwrite quietly: a model returning an audit field is a model doing
something it was told not to do, and on the moderation path the value it invented
would otherwise land in a §6.2 audit record." The model is therefore never asked
for the contract itself. `_payload_model` derives the task's own output — the
contract minus the two audit fields, under the same `extra="forbid"` posture — and
that is what the endpoint answers against, so an answer carrying either key fails
validation before anything is merged. The field names are read off `AiTaskOutput`,
so a third audit value is covered the day it is added.

**Nothing raised here carries the credential, the prompt or the answer.** Three
separate reasons, and they land on the same rule:

* the API key is a secret (SPEC §10), and a gateway error is printed to the
  container log with its whole traceback;
* the prompt ends with a student's comment (`app/ai/prompts/README.md`), and a
  comment in a log is confidential text outside the read paths §4 defines;
* the answer is model output that may quote the comment back — and the library's
  own exceptions carry it: a validation failure arrives with the offending value
  in `input`, an HTTP failure with the endpoint's response body in its message,
  and a *rejected key* arrives as the key itself, because `extra="forbid"`
  reports the location of the offending key and that location is a string the
  model chose. E0-13's review measured a whole comment reconstructed out of four
  such locations, so `_describe` now emits a field name only when the schema
  declares it.

So a failure here is built from static text, the contract's name, declared field
names, and pydantic's error-type codes — the same ingredients, for the same
reason, as `app.config.ConfigurationError`. It is raised *outside* the `except`
block that diagnosed it, because Python prints a chained cause's message too:
`raise ... from None` suppresses the display and leaves `__context__` set for
anything that inspects the chain.

**One client per thread, and the loop it was built for.** The asynchronous client
underneath pools its connections, and a pooled connection belongs to the event
loop it was opened on: reuse it from another loop and it raises, which the layers
above turn into "the endpoint could not be reached". A gateway shared across a
threadpool therefore has to keep a client per thread — see `_ThreadBound`, which
holds the loop, the client and the agents together for exactly that reason.
"""

import asyncio
import threading
from functools import cache
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, create_model
from pydantic_ai import Agent, NativeOutput
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from app.ai.contracts import AiTaskOutput, ContractModel
from app.config import Settings

OutputT = TypeVar("OutputT", bound=AiTaskOutput)

# How many requests one task is worth. Two: the first answer, and one more if it
# violated the contract's shape. Not a configuration knob — §3.3 gives the
# validity check a p95 under two seconds and §7.4 forbids a loop, so the only
# question a number here could answer is "how many times may a broken model spend
# a student's wait", and the answer is once.
SHAPE_VIOLATION_ATTEMPTS = 2

# What the request sends when no credential is configured. An OpenAI-compatible
# server that authenticates nobody — vLLM, Ollama, a proxy on the same host —
# ignores it, and the client refuses to be constructed without something. It is a
# fixed, obviously-inert string rather than an empty one because an empty bearer
# token is a value some servers refuse outright.
#
# **It is sent, as `Authorization: Bearer pulse-no-key-configured`.** Removing the
# header entirely would mean building the client here rather than letting the
# provider build it, which means importing `openai` in this file. `.env.example`,
# `README.md` and `app.config` all describe it as it is; E0-13's review found
# them describing a header that was never sent.
UNAUTHENTICATED = "pulse-no-key-configured"

# The fields on every §7.4 contract that the gateway fills in and the model may
# not. Derived from the contract base rather than written out, so a third audit
# value added to `AiTaskOutput` is covered by ADR 0031's rule without anybody
# remembering this module exists.
_AUDIT_FIELDS = frozenset(AiTaskOutput.model_fields)

# What a failure message says instead of a location the schema does not declare.
# `extra="forbid"` reports the offending key as the error's location, and that key
# is a string the model wrote — which, on this path, is a string a student's
# comment can steer. A fixed token carries the same diagnostic weight as the key
# itself, since what a reader needs is the error *type*.
UNDECLARED_LOCATION = "<undeclared>"

# How many distinct problems one failure message names. A model can return a
# hundred undeclared keys, and a hundred copies of the same token is a log line
# nobody reads.
_PROBLEM_LIMIT = 5


class AIGatewayError(Exception):
    """A model call did not produce a validated object, and said so on purpose.

    The base class exists so that a caller on §3.3's submit path can catch the
    gateway deliberately rather than catching everything. `TypeError` and
    `AttributeError` out of an unguarded parse are not this: they are the gateway
    falling over, and nothing can handle them meaningfully.
    """


class AIProviderTimeoutError(AIGatewayError):
    """The endpoint accepted the request and did not answer in time.

    **This is the only failure §3.3's fail-open covers**, and the name says so:
    "Classifier latency budget: p95 < 2s; on provider timeout, the heuristic floor
    applies and the submission is accepted, then classified async (fail open,
    never block a student on an outage)."

    Deciding what to do about it is not this module's job. Comment validity falls
    open onto §3.3's character floor; moderation (§6.2) has no fail-open at all,
    because the verdict that routes a self-harm disclosure to the Care queue is
    not something to guess at. A gateway that absorbed the timeout itself would
    have to hold both rules.
    """


class AIProviderUnreachableError(AIGatewayError):
    """The request never reached an endpoint: the connection failed.

    A refused connection, a name that does not resolve, a TLS handshake that does
    not complete. **Deliberately not the same class as a timeout**, and
    [ADR 0056](../../../docs/adr/0056-only-a-timeout-fails-open.md) is why: §3.3
    sanctions the floor for a provider *timeout*, and a certificate failure is
    what an active network attacker looks like. Failing open on it would let
    anybody who can interrupt the connection decide that no classification
    happens — which is tolerable for a participation gate only until E2 puts
    moderation through the same code.
    """


class AIResponseInvalidError(AIGatewayError):
    """The endpoint answered, and the answer was not the contract.

    Raised after the retry budget is spent, which is §7.4's "surfaces persistent
    failures as errors rather than letting a malformed classification propagate".
    A partially-populated object would be a stored verdict that no model produced.
    """


class AIProviderRefusedError(AIGatewayError):
    """The endpoint answered with an error status — a rejected credential, a rate
    limit, a model that does not exist, a schema it will not accept.

    Not an outage and not a shape violation: the request itself was wrong, or the
    account behind it is. §3.3's fail-open does not cover this, and a caller that
    treated it as one would turn a permanently misconfigured credential into
    every comment being classified by the character floor with nothing saying so.
    """


@cache
def _payload_model(contract: type[AiTaskOutput]) -> type[BaseModel]:
    """`contract` without the two values the gateway supplies (ADR 0031).

    This is the shape the model is actually asked for, and it is derived rather
    than declared per task for two reasons. It cannot drift from the contract — a
    field added to `CommentValidityOutput` is a field the endpoint is asked for in
    the same commit — and it is not a second model anybody can reach: §7.4 makes
    the contract "the runtime contract, the API response schema, and the eval
    fixtures", and E0-12 forbids forking it for any of the three. Nothing outside
    this module ever sees one of these.

    It carries the contract's own validation posture, `extra="forbid"` included,
    which is what refuses a payload supplying `prompt_version` or `model_id`:
    neither is declared here, so both arrive as extra keys and the answer is a
    shape violation before any merge happens.

    Cached because it is the same object every call, and because the derived class
    is what `pydantic-ai` builds a JSON schema from.
    """
    fields: dict[str, Any] = {
        name: (field.annotation, field)
        for name, field in contract.model_fields.items()
        if name not in _AUDIT_FIELDS
    }
    return create_model(
        f"{contract.__name__}Payload",
        __config__=ContractModel.model_config,
        **fields,
    )


@cache
def _declared_names(payload: type[BaseModel]) -> frozenset[str]:
    """Every property name anywhere in one payload's JSON schema.

    Read out of the schema rather than off `model_fields`, because a nested model
    — `CommentTheme` inside a summary's `themes` — declares names too, and a
    validation error can point at one of them. The schema is the same document the
    endpoint was sent, so this is the exact set of locations a well-behaved answer
    can produce.

    Anything outside this set came from the model rather than from us, and
    `_describe` refuses to print it.
    """
    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                names.update(str(key) for key in properties)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload.model_json_schema())
    return frozenset(names)


class _ThreadBound:
    """The event loop, the client and the agents one thread uses.

    All three are here together because they cannot be separated: the client pools
    its connections, a pooled connection is bound to the loop it was opened on,
    and an agent holds the model that holds the client. Hand a connection from one
    loop to another and it raises — which arrives at this module as
    `ModelAPIError`, so the gateway reports "the endpoint could not be reached"
    about an endpoint that answered perfectly.

    That is not hypothetical. E0-13's review measured one shared gateway across a
    threadpool answering every *second* submission from the character floor while
    the provider was healthy — the request went out, the answer came back, and it
    was discarded — so the same comment was counted or refused depending on which
    thread served it. Keeping the three together is what makes a gateway safe to
    share, and sharing one is what keeps the client count bounded by threads
    rather than by comments.
    """

    def __init__(self, settings: Settings) -> None:
        key = settings.ai_provider_api_key
        provider = OpenAIProvider(
            base_url=settings.ai_provider_base_url,
            api_key=key.get_secret_value() if key is not None else UNAUTHENTICATED,
        )
        # **The underlying client's own retry is turned off**, so that the number
        # of requests one task makes is this gateway's decision and nothing
        # else's. Left at its default of two, a timeout is retried twice *inside*
        # one call: measured against a stub that never answers, a four-second
        # per-task timeout took 13.3 seconds to fail open, in three requests.
        # §3.3 budgets the whole check at a p95 under two seconds, so that is a
        # student waiting through three timeouts to be told a character count
        # decided.
        #
        # Set on the client rather than passed to it, because the provider is what
        # builds it and takes no retry argument. The alternative is constructing
        # the client here, which means importing `openai` in this file — the
        # second provider-library importer E0-13's sixth criterion is about.
        provider.client.max_retries = 0
        self.loop = asyncio.new_event_loop()
        self.model = OpenAIChatModel(settings.ai_model_name, provider=provider)
        self.agents: dict[type[AiTaskOutput], Agent[None, Any]] = {}

    def agent_for(self, output_model: type[AiTaskOutput]) -> Agent[None, Any]:
        """The agent that asks for one task's output, built once per contract.

        `NativeOutput` rather than the library's default tool output, and §7.4 is
        the reason: "one call in, one validated object out — **no tool use**, no
        planning loop, no iterative retrieval". Native output asks for a JSON
        object against the payload's schema, so the request carries
        `response_format` and declares no tool at all. It also keeps the wire
        agreeing with the prompt, which tells the model to "return only this JSON
        object".

        `retries=0` because `AIGateway.run_task` owns the retry; see its
        docstring.
        """
        agent = self.agents.get(output_model)
        if agent is None:
            agent = Agent(
                self.model,
                output_type=NativeOutput(_payload_model(output_model)),
                retries=0,
            )
            self.agents[output_model] = agent
        return agent


class AIGateway:
    """One client per thread against one OpenAI-compatible endpoint (SPEC §6.3, §7.4).

    Built from `Settings`, so the base URL, the model and the credential all come
    from the environment and none of them is written down here. Nothing is
    constructed at import time: a module that built a client on import would need
    `AI_PROVIDER_BASE_URL` set to be importable at all, and CI's
    `migration-drift` job supplies the database variables alone.

    **Share one per process.** `app.ai.tasks` does, and the reason is
    `_ThreadBound`: an instance holds one client per thread that has used it, so
    one shared gateway costs a client per threadpool thread while a gateway per
    comment costs a client per comment — and E0-13's review measured that second
    shape leaking sockets, from 6 to 23 file descriptors over 30 calls, reclaimed
    only when the garbage collector got to it.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Read the configuration; build nothing until a thread asks."""
        self._settings = settings or Settings()
        self._local = threading.local()

    @property
    def model_name(self) -> str:
        """The model this gateway asks for, as `AI_MODEL_NAME` spells it."""
        return self._settings.ai_model_name

    def run_task(
        self,
        *,
        prompt: str,
        prompt_version: str,
        output_model: type[OutputT],
        timeout: float,
    ) -> OutputT:
        """One call in, one validated `output_model` out.

        `prompt` is the whole message, rendered by the caller with the student's
        text already in it and nothing after it — `app/ai/prompts/README.md`
        requires the input marker to run "to the end of the message", which only
        holds if the gateway appends nothing. It is sent as a single user message
        for the same reason.

        `prompt_version` is the stem of the prompt file the caller rendered, and
        is recorded on the returned object (ADR 0031, ADR 0032). It is not sent to
        the model.

        **A retry re-asks; it does not argue.** `pydantic-ai` can send a failed
        answer back to the model with the validation error attached, and that is
        turned off (`retries=0` on the agent, this loop instead). The reason is
        the prompt layout rather than taste: that retry appends a message *after*
        the one ending in the student's comment, and `prompts/README.md` rests the
        whole injection boundary on there being nothing after it — "'To the end of
        the message' cannot be forged, and it means the gateway must append
        nothing after the comment." The cost is real and worth stating: a model
        that made its mistake deterministically will make it again, so this buys
        less than a feedback retry would. ADR 0053 records the trade.

        Raises `AIProviderTimeoutError` if the endpoint did not answer in time,
        `AIProviderUnreachableError` if the connection never got there,
        `AIProviderRefusedError` if it answered with an error status, and
        `AIResponseInvalidError` if it kept answering with something that is not
        the contract.
        """
        problem = ""
        for _ in range(SHAPE_VIOLATION_ATTEMPTS):
            try:
                payload, model_id = self._ask(
                    prompt=prompt, output_model=output_model, timeout=timeout
                )
            except AIResponseInvalidError as invalid:
                problem = str(invalid)
                continue
            return output_model.model_validate(
                {
                    **payload.model_dump(),
                    "prompt_version": prompt_version,
                    "model_id": model_id,
                }
            )

        raise AIResponseInvalidError(
            f"The model did not answer with a valid {output_model.__name__} in "
            f"{SHAPE_VIOLATION_ATTEMPTS} attempts. The last attempt: {problem}"
        )

    # -- the wire ----------------------------------------------------------

    def _bound(self) -> _ThreadBound:
        """This thread's loop, client and agents, built on first use.

        One per thread rather than one per gateway, because a pooled connection
        cannot cross an event loop and a loop cannot be driven by two threads at
        once. The alternative shapes were measured and are worse: a shared client
        across per-thread loops silently falls open on every second call, and a
        gateway per call leaks sockets.
        """
        bound: _ThreadBound | None = getattr(self._local, "bound", None)
        if bound is None:
            bound = _ThreadBound(self._settings)
            self._local.bound = bound
        return bound

    def _ask(
        self, *, prompt: str, output_model: type[OutputT], timeout: float
    ) -> tuple[BaseModel, str]:
        """Send one request; return the task's own output and which model produced it.

        Every branch names the failure and its class, and the raise happens
        *after* the `except` block rather than inside it. Inside, Python would
        attach the library's own exception as `__context__`, and a chained
        exception's message is printed in the traceback too — so the response
        body, or the value that failed validation, would reach the container log
        by the back door. `raise ... from None` is not enough: it suppresses the
        display and leaves `__context__` set for anything that walks the chain.
        `app.config.Settings.__init__` takes the same shape for the same reason.
        """
        bound = self._bound()
        agent = bound.agent_for(output_model)
        try:
            result = bound.loop.run_until_complete(
                agent.run(prompt, model_settings=ModelSettings(timeout=timeout))
            )
        except UnexpectedModelBehavior as violation:
            # What the library raises when an answer will not validate and the
            # retry budget it holds is spent — which is immediately, since this
            # gateway spends its own.
            failure: type[AIGatewayError] = AIResponseInvalidError
            message = (
                f"The answer did not validate as {output_model.__name__}: "
                f"{_describe(violation, output_model)}."
            )
        except ModelHTTPError as refused:
            # The status code and nothing else. `ModelHTTPError` renders the
            # endpoint's response body into its own message, and that body is text
            # the endpoint wrote.
            failure = AIProviderRefusedError
            message = f"The model endpoint answered HTTP {refused.status_code}."
        except ModelAPIError as unanswered:
            # The library's wrapper for a request that never got an answer, and it
            # covers two different things (`ModelHTTPError` is a third and is
            # caught above). Only one of them is §3.3's fail-open case, so they
            # are separated here rather than reported as one — ADR 0056.
            if _timed_out(unanswered):
                failure = AIProviderTimeoutError
                message = "The model endpoint did not answer within the task's timeout."
            else:
                failure = AIProviderUnreachableError
                message = (
                    "The model endpoint could not be reached: the connection was refused, "
                    "the name did not resolve, or the TLS handshake failed."
                )
        else:
            return result.output, self._model_of(result)

        raise failure(message)

    def _model_of(self, result: Any) -> str:
        """The model that produced this answer, as the endpoint spells it.

        Read off the response rather than off the configuration, because ADR 0031
        wants "the provider's own identifier for the model, as the provider spells
        it" — a hosted provider asked for `gpt-4o` answers as a dated build of it,
        and §9.3's eval floors compare runs of different models. The configured
        name is the fallback for an endpoint that reports none.
        """
        for message in reversed(result.all_messages()):
            reported = getattr(message, "model_name", None)
            if isinstance(reported, str) and reported:
                return reported
        return self.model_name


def _timed_out(failure: BaseException) -> bool:
    """Whether this failure is the endpoint not answering in time.

    Decided on the exception chain rather than on a message, because the layers
    above flatten both cases into one class with a sentence in it — "Request timed
    out." against "Connection error." — and a rule that reads either sentence is a
    rule that breaks when the library rewords it. `httpx.TimeoutException` is the
    common parent of a connect timeout and a read timeout, and it is the deepest
    layer this project declares a dependency on.

    Measured, on the pinned versions: a stub that holds the request produces
    `ModelAPIError <- APITimeoutError <- httpx.ReadTimeout`; a refused connection
    and a failed TLS handshake both produce `ModelAPIError <- APIConnectionError
    <- httpx.ConnectError`, with no `TimeoutException` anywhere in either.

    A chain this cannot read falls to `False`, which is the safe direction: an
    unrecognised failure is surfaced rather than absorbed by §3.3's floor.
    """
    seen: list[BaseException] = []
    current: BaseException | None = failure
    while current is not None and not any(link is current for link in seen):
        seen.append(current)
        if isinstance(current, httpx.TimeoutException):
            return True
        current = current.__cause__ or current.__context__
    return False


def _describe(violation: UnexpectedModelBehavior, contract: type[AiTaskOutput]) -> str:
    """A refused answer as declared field names and pydantic error codes.

    The library hands the detail over as the retry prompt it would otherwise have
    sent: a list of pydantic error dicts on the `tool_retry` part of the chained
    `ToolRetryError`. Three things are deliberately not read out of it, and the
    third is the one that cost a HIGH finding in review:

    * the `msg`, which pydantic builds out of the value that failed;
    * the `input`, which *is* the value that failed;
    * any part of the `loc` that the payload's schema does not declare. An
      `extra_forbidden` error reports the offending key as its location, so the
      location is a string the model wrote — and a model writes what it has just
      read. The review measured a whole comment, name and email address included,
      reconstructed across four such locations and joined into one message, on its
      way to the container log through an exception nothing catches. SPEC §10
      forbids student text in a log outright, and E2 puts moderation through this
      same function, where the leaked class is a threat or a self-harm
      disclosure.

    So a location is printed when the schema declares it and replaced with
    `UNDECLARED_LOCATION` otherwise, list indices pass through as themselves, and
    the result is deduplicated and capped — a hundred invented keys are a hundred
    copies of one token. What is left is the error *type*, which is what a reader
    diagnosing a bad prompt actually needs.

    The detail is reached by attribute rather than by importing the exception
    type, so a library that stops carrying it degrades to the general sentence
    below rather than raising something else while reporting a shape violation.
    """
    details = getattr(getattr(violation.__cause__, "tool_retry", None), "content", None)
    if not isinstance(details, list):
        return "the answer could not be read as the task's output"

    declared = _declared_names(_payload_model(contract))
    problems = sorted(
        {
            f"{_location(detail.get('loc', ()), declared)}: {detail.get('type', 'invalid')}"
            for detail in details
            if isinstance(detail, dict)
        }
    )
    if not problems:
        return "the answer could not be read as the task's output"

    shown = "; ".join(problems[:_PROBLEM_LIMIT])
    hidden = len(problems) - _PROBLEM_LIMIT
    return f"{shown} (and {hidden} more)" if hidden > 0 else shown


def _location(loc: Any, declared: frozenset[str]) -> str:
    """One error's location, with anything the model invented replaced.

    An integer is a list index and passes through. A string passes through only
    when it names something the schema declares; anything else is a key the model
    chose, and is printed as `UNDECLARED_LOCATION` rather than as itself.
    """
    if not isinstance(loc, tuple | list) or not loc:
        return "(root)"
    parts = [
        str(element)
        if isinstance(element, int) or (isinstance(element, str) and element in declared)
        else UNDECLARED_LOCATION
        for element in loc
    ]
    return ".".join(parts)
