"""The one place a model is called from (SPEC §7.4).

§7.4: "All model calls go through one internal `AIGateway` with per-task prompts,
timeouts, retries, and eval hooks." This module is that gateway, and it is
deliberately small: it takes rendered prompt text and a Pydantic contract, sends
one request to an OpenAI-compatible endpoint, and hands back a validated instance
of that contract. It loads no prompt, opens no database connection, and decides
nothing about any particular task.

**This is the only module in `backend/app/` that imports a provider library**,
which is E0-13's sixth acceptance criterion and
`tests/unit/test_provider_library_is_confined_to_the_gateway.py` is what keeps it
true. §7.4's reason: the library "is young and fast-moving, so pin it and keep the
gateway interface thin enough that replacing it is a day's work". A second
importer — a task building its own client, a batch job, a helper — is another
file that replacement has to touch, and each one looks harmless in its own diff.
Which library, and why it is not the one §7.4 names, is
[ADR 0053](../../../docs/adr/0053-the-gateway-speaks-openai-through-the-openai-sdk.md).

**Single-shot, and the retry does not soften it.** §7.4: "Every task in the table
above is one call in, one validated object out — no tool use, no planning loop,
no iterative retrieval." So the request declares no tools, sends one message and
reads one answer. The one thing that produces a second request is a *shape
violation* — the same prompt asked again, never a conversation about what went
wrong — because §7.4 has the gateway "retry on shape violations, and surface
persistent failures as errors rather than letting a malformed classification
propagate."

**The audit pair is the gateway's to fill in, and a model that supplies it is
refused.** [ADR 0031](../../../docs/adr/0031-every-task-contract-carries-the-prompt-version-and-model-id.md):
"The gateway must reject a provider payload that contains either key, *before*
merging anything into it, and treat that as the shape violation §7.4 has it retry
on. Not overwrite quietly: a model returning an audit field is a model doing
something it was told not to do, and on the moderation path the value it invented
would otherwise land in a §6.2 audit record." `_AUDIT_FIELDS` below is read off
`AiTaskOutput` rather than spelled again, so a third audit field would be covered
by the rule the day it is added.

**Nothing raised here carries the credential, the prompt or the answer.** Three
separate reasons, and they land on the same rule:

* the API key is a secret (SPEC §10), and a gateway error is printed to the
  container log with its whole traceback;
* the prompt ends with a student's comment (`app/ai/prompts/README.md`), and a
  comment in a log is confidential text outside the read paths §4 defines;
* the answer is model output that may quote the comment back.

So a failure here is built from static text, the contract's name, and pydantic's
error-type codes — the same ingredients, for the same reason, as
`app.config.ConfigurationError`. It is raised *outside* the `except` block that
diagnosed it, because Python prints a chained cause's message too: `raise ...
from None` suppresses the display and leaves `__context__` set for anything that
inspects the chain.
"""

import json
from typing import TypeVar

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, OpenAIError
from openai.types.chat import ChatCompletion
from pydantic import ValidationError

from app.ai.contracts import AiTaskOutput
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
    """The endpoint answered with an error status — a rejected credential, a
    rate limit, a model that does not exist.

    Not an outage and not a shape violation: the request itself was wrong, or the
    account behind it is. §3.3's fail-open does not cover this, and a caller that
    treated it as one would turn a permanently misconfigured credential into
    every comment being classified by the character floor with nothing saying so.
    """


class AIGateway:
    """One client against one OpenAI-compatible endpoint (SPEC §6.3, §7.4).

    Built from `Settings`, so the base URL, the model and the credential all come
    from the environment and none of them is written down here. The client is
    constructed with the instance rather than at import time: a module that built
    one on import would need `AI_PROVIDER_BASE_URL` set to be importable at all,
    and CI's `migration-drift` job supplies the database variables alone.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Open a client on the configured endpoint.

        The credential is passed explicitly, always — including the inert
        placeholder when none is configured. The client would otherwise read
        `OPENAI_API_KEY` out of the ambient environment, and a process that
        picked up somebody else's key would send this institution's student
        comments to an endpoint on that account.
        """
        self._settings = settings or Settings()
        key = self._settings.ai_provider_api_key
        self._client = OpenAI(
            base_url=self._settings.ai_provider_base_url,
            api_key=key.get_secret_value() if key is not None else UNAUTHENTICATED,
            # The client's own retry is off, so that the request count is the
            # gateway's decision and nothing else's. Left on, it would retry a
            # timeout twice more inside one attempt — three times the wait §3.3
            # budgets, arrived at by default rather than by choice.
            max_retries=0,
        )

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
        is recorded on the returned object (ADR 0031, ADR 0032). It is not sent
        to the model.

        Raises `AIProviderUnavailableError` if the endpoint did not answer,
        `AIProviderRefusedError` if it answered with an error status, and
        `AIResponseInvalidError` if it kept answering with something that is not the
        contract.
        """
        problem = ""
        for _ in range(SHAPE_VIOLATION_ATTEMPTS):
            answer, model_id = self._ask(prompt=prompt, timeout=timeout)
            try:
                return self._validated(
                    answer,
                    output_model=output_model,
                    prompt_version=prompt_version,
                    model_id=model_id,
                )
            except AIResponseInvalidError as invalid:
                problem = str(invalid)

        raise AIResponseInvalidError(
            f"The model did not answer with a valid {output_model.__name__} in "
            f"{SHAPE_VIOLATION_ATTEMPTS} attempts. The last attempt: {problem}"
        )

    # -- the wire ----------------------------------------------------------

    def _ask(self, *, prompt: str, timeout: float) -> tuple[str, str]:
        """Send one request and return what the model said and which model said it.

        The model ID comes off the *response* where the endpoint reports one,
        because ADR 0031 wants "the provider's own identifier for the model, as
        the provider spells it" — a hosted provider asked for `gpt-4o` answers as
        a dated build of it, and §9.3's eval floors compare runs of different
        models. The configured name is the fallback for an endpoint that reports
        nothing.
        """
        # Each branch names the failure and its class, and the raise happens
        # *after* the `except` block rather than inside it. Inside, Python would
        # attach the client's own exception as `__context__`, and a chained
        # exception's message is printed in the traceback too — so whatever that
        # one holds would reach the container log by the back door. `raise ...
        # from None` is not enough: it suppresses the display and leaves
        # `__context__` set for anything that walks the chain.
        # `app.config.Settings.__init__` takes the same shape for the same reason.
        try:
            completion = self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
            )
        except APITimeoutError:
            failure: type[AIGatewayError] = AIProviderUnavailableError
            message = "The model endpoint did not answer within the task's timeout."
        except APIConnectionError:
            failure = AIProviderUnavailableError
            message = "The model endpoint could not be reached."
        except APIStatusError as status:
            # The status code and nothing else. The body of an endpoint's error
            # is text it wrote, and an HTTP client's own exception renders the
            # request that caused it — headers included, which is where the
            # credential is.
            failure = AIProviderRefusedError
            message = f"The model endpoint answered HTTP {status.status_code}."
        except OpenAIError:
            # Everything else the client raises: a base URL it will not accept, a
            # configuration it refuses. Its message may quote what it was given,
            # so none of it is repeated here.
            failure = AIProviderRefusedError
            message = (
                "The model client refused the request before it was sent. "
                "Check AI_PROVIDER_BASE_URL and AI_MODEL_NAME."
            )
        else:
            return self._answer_of(completion)

        raise failure(message)

    def _answer_of(self, completion: ChatCompletion) -> tuple[str, str]:
        """The assistant's text and the model that produced it, or a shape violation.

        An answer with no choices, or a choice carrying no content, is a shape
        violation rather than an outage: the endpoint answered, and what it said
        was not usable. That distinction is what keeps §3.3's fail-open pointed at
        an outage.
        """
        content = completion.choices[0].message.content if completion.choices else None
        if not isinstance(content, str) or not content.strip():
            raise AIResponseInvalidError("The answer carried no assistant message text.")
        return content, completion.model or self.model_name

    # -- the contract ------------------------------------------------------

    def _validated(
        self,
        answer: str,
        *,
        output_model: type[OutputT],
        prompt_version: str,
        model_id: str,
    ) -> OutputT:
        """Turn one answer into one contract instance, or say why it is not one."""
        try:
            payload = json.loads(answer)
        except ValueError:
            raise AIResponseInvalidError("The answer was not JSON.") from None

        if not isinstance(payload, dict):
            raise AIResponseInvalidError(
                f"The answer was JSON but not an object; it was a {type(payload).__name__}."
            )

        usurped = sorted(_AUDIT_FIELDS & payload.keys())
        if usurped:
            # ADR 0031. Refused rather than overwritten: which value survived a
            # merge would then depend on an order nothing constrains, and on the
            # moderation path the value the model invented would land in a §6.2
            # audit record. The field names here are the contract's own, not the
            # model's, so naming them leaks nothing.
            raise AIResponseInvalidError(
                f"The answer supplied {usurped}, which the gateway fills in and a model may "
                "never report (ADR 0031)."
            )

        try:
            return output_model.model_validate(
                {**payload, "prompt_version": prompt_version, "model_id": model_id}
            )
        except ValidationError as invalid:
            problems = _describe(invalid)
        raise AIResponseInvalidError(
            f"The answer did not validate as {output_model.__name__}: {problems}."
        )


def _describe(invalid: ValidationError) -> str:
    """A validation failure as field paths and pydantic error codes, and no values.

    Neither the message nor the input is read. Pydantic's `msg` is built from the
    value that failed for several error types, and the `input` is the value
    itself — which here is text a model wrote after reading a student's comment.
    The code is a static string from the library, and the location is a field
    name: the contract's, or a key the model invented, which is truncated.
    """
    problems = sorted(
        f"{'.'.join(str(part) for part in detail.get('loc', ()))[:_KEY_EXCERPT]}: "
        f"{detail.get('type', 'invalid')}"
        for detail in invalid.errors()
    )
    return "; ".join(problems)
