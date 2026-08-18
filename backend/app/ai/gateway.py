"""The one place a model is called from (SPEC §7.4).

§7.4: "All model calls go through one internal `AIGateway` with per-task prompts,
timeouts, retries, and eval hooks." This module is that gateway, and it is
deliberately small: it takes rendered prompt text and a Pydantic contract, sends
one request to an OpenAI-compatible endpoint, and hands back a validated instance
of that contract. It loads no prompt, opens no database connection, and decides
nothing about any particular task.

**This is the only module in `backend/app/` that imports a provider library**,
which is E0-13's sixth acceptance criterion; the confinement sweep under
`tests/unit/` is what keeps it true. §7.4's reason: the library "is young and
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
  in `input`, and an HTTP failure with the endpoint's response body in its
  message.

So a failure here is built from static text, the contract's name, and pydantic's
error-type codes — the same ingredients, for the same reason, as
`app.config.ConfigurationError`. It is raised *outside* the `except` block that
diagnosed it, because Python prints a chained cause's message too: `raise ...
from None` suppresses the display and leaves `__context__` set for anything that
inspects the chain.
"""

import asyncio
import threading
from functools import cache
from typing import Any, TypeVar

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
UNAUTHENTICATED = "pulse-no-key-configured"

# The fields on every §7.4 contract that the gateway fills in and the model may
# not. Derived from the contract base rather than written out, so a third audit
# value added to `AiTaskOutput` is covered by ADR 0031's rule without anybody
# remembering this module exists.
_AUDIT_FIELDS = frozenset(AiTaskOutput.model_fields)

# How much of a model-chosen string may appear in a failure message. A JSON key
# the model invented is the one piece of provider text a shape violation has to
# name in order to be diagnosable, and it is text a comment could have talked the
# model into producing.
_KEY_EXCERPT = 40

# One event loop per thread that makes a model call, held for the life of the
# thread.
_LOOPS = threading.local()


def _model_call_loop() -> asyncio.AbstractEventLoop:
    """The loop this thread runs model calls on, created on first use.

    The gateway is synchronous — ADR 0013 makes the session synchronous, handlers
    are `def` and run in FastAPI's threadpool, and Celery tasks are synchronous
    too — while the library underneath it is not. Something has to drive a loop,
    and the two obvious ways are both wrong here:

    * `Agent.run_sync` calls `asyncio.get_event_loop()`, which emits a
      `DeprecationWarning` when the thread has no loop set. `pyproject.toml` turns
      a `DeprecationWarning` into an error on purpose — "a deprecated call our own
      code makes is a defect" — so under the test suite every model call fails,
      and in production it is a warning today and a `RuntimeError` in Python 3.14.
    * `asyncio.run` per call builds and closes a loop each time. The HTTP client
      is built once and its connection pool binds to the loop that first used it,
      so the second call would reach into a closed loop — and rebuilding the
      client per comment is a TLS handshake per comment, inside §3.3's p95 budget.

    So the loop is owned here, one per thread, and reused. The count is bounded by
    the size of the threadpool rather than by the number of comments, and a
    `AIGateway` can be shared across threads because each one drives its own.

    Calling this from a thread that already has a *running* loop raises — which is
    correct and deliberate: an async caller must not block its own loop on a model
    call, and there is no shape of this function that fixes that for it.
    """
    loop: asyncio.AbstractEventLoop | None = getattr(_LOOPS, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _LOOPS.loop = loop
    return loop


class AIGatewayError(Exception):
    """A model call did not produce a validated object, and said so on purpose.

    The base class exists so that a caller on §3.3's submit path can catch the
    gateway deliberately rather than catching everything. `TypeError` and
    `AttributeError` out of an unguarded parse are not this: they are the gateway
    falling over, and nothing can handle them meaningfully.
    """


class AIProviderUnavailableError(AIGatewayError):
    """The endpoint did not answer: it timed out, or it could not be reached.

    §3.3 names one of the two — "on provider timeout, the heuristic floor applies
    and the submission is accepted" — and the sentence it is in names the
    principle: "fail open, never block a student on an outage". A refused
    connection is that outage with a faster failure mode, so both arrive here and
    a caller decides what its own task does about it.

    **Deciding that is not this module's job**, and the split is deliberate.
    Comment validity falls open onto §3.3's character floor; moderation (§6.2)
    has no fail-open at all, because the verdict that routes a self-harm
    disclosure to the Care queue is not something to guess at. A gateway that
    absorbed the outage itself would have to hold both rules.
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


class AIGateway:
    """One client against one OpenAI-compatible endpoint (SPEC §6.3, §7.4).

    Built from `Settings`, so the base URL, the model and the credential all come
    from the environment and none of them is written down here. The client is
    constructed with the instance rather than at import time: a module that built
    one on import would need `AI_PROVIDER_BASE_URL` set to be importable at all,
    and CI's `migration-drift` job supplies the database variables alone.

    An instance is reusable and worth reusing — one connection pool, one client —
    and `_model_call_loop` is what makes that true across calls: the pool binds to
    the loop it was first used on, and that loop belongs to the thread rather than
    to the call.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Open a client on the configured endpoint.

        The credential is passed explicitly, always — including the inert
        placeholder when none is configured. The client would otherwise read
        `OPENAI_API_KEY` out of the ambient environment, and a process that picked
        up somebody else's key would send this institution's student comments to
        an endpoint on that account.
        """
        self._settings = settings or Settings()
        key = self._settings.ai_provider_api_key
        provider = OpenAIProvider(
            base_url=self._settings.ai_provider_base_url,
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
        self._model = OpenAIChatModel(self._settings.ai_model_name, provider=provider)
        self._agents: dict[type[AiTaskOutput], Agent[None, Any]] = {}

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

        Raises `AIProviderUnavailableError` if the endpoint did not answer,
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
        agent = self._agent_for(output_model)
        try:
            result = _model_call_loop().run_until_complete(
                agent.run(prompt, model_settings=ModelSettings(timeout=timeout))
            )
        except UnexpectedModelBehavior as violation:
            # What the library raises when an answer will not validate and the
            # retry budget it holds is spent — which is immediately, since this
            # gateway spends its own.
            failure: type[AIGatewayError] = AIResponseInvalidError
            message = (
                f"The answer did not validate as {output_model.__name__}: {_describe(violation)}."
            )
        except ModelHTTPError as refused:
            # The status code and nothing else. `ModelHTTPError` renders the
            # endpoint's response body into its own message, and that body is text
            # the endpoint wrote.
            failure = AIProviderRefusedError
            message = f"The model endpoint answered HTTP {refused.status_code}."
        except ModelAPIError:
            # The library's wrapper for a request that never got an answer: a
            # timeout or a connection failure. `ModelHTTPError` is a subclass of
            # it and is caught above.
            failure = AIProviderUnavailableError
            message = "The model endpoint did not answer within the task's timeout."
        else:
            return result.output, self._model_of(result)

        raise failure(message)

    def _agent_for(self, output_model: type[OutputT]) -> Agent[None, Any]:
        """The agent that asks for one task's output, built once per contract.

        `NativeOutput` rather than the library's default tool output, and §7.4 is
        the reason: "one call in, one validated object out — **no tool use**, no
        planning loop, no iterative retrieval". Native output asks for a JSON
        object against the payload's schema, so the request carries
        `response_format` and declares no tool at all. It also keeps the wire
        agreeing with the prompt, which tells the model to "return only this JSON
        object".

        `retries=0` because `run_task` owns the retry; see its docstring.
        """
        agent = self._agents.get(output_model)
        if agent is None:
            agent = Agent(
                self._model,
                output_type=NativeOutput(_payload_model(output_model)),
                retries=0,
            )
            self._agents[output_model] = agent
        return agent

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


def _describe(violation: UnexpectedModelBehavior) -> str:
    """A refused answer as field paths and pydantic error codes, and no values.

    The library hands the detail over as the retry prompt it would otherwise have
    sent: a list of pydantic error dicts on the `tool_retry` part of the chained
    `ToolRetryError`. Neither the message nor the input is read out of it.
    Pydantic's `msg` is built from the value that failed for several error types,
    and `input` is the value itself — which here is text a model wrote after
    reading a student's comment. The code is a static string from the library, and
    the location is a field name: the contract's, or a key the model invented,
    which is truncated.

    Reached by attribute rather than by importing the exception type, so a library
    that stops carrying it degrades to the general sentence below rather than
    raising something else while reporting a shape violation.
    """
    details = getattr(getattr(violation.__cause__, "tool_retry", None), "content", None)
    if not isinstance(details, list):
        return "the answer could not be read as the task's output"

    problems = sorted(
        f"{'.'.join(str(part) for part in detail.get('loc', ()))[:_KEY_EXCERPT]}: "
        f"{detail.get('type', 'invalid')}"
        for detail in details
        if isinstance(detail, dict)
    )
    return "; ".join(problems) or "the answer could not be read as the task's output"
