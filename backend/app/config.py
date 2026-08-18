"""Application settings, entirely environment-driven (SPEC §6.3).

Every setting here is read from the environment and documented in
`.env.example`, which a unit test holds in sync with this class in both
directions.

The fields split into two groups, and the split is the point:

* **Deployment wiring** has no default. A database URL, a Redis URL, an AI
  provider base URL and model name, the institution timezone, and the
  environment name all differ per deployment, and a working literal default for
  any of them is a misconfiguration that starts successfully and is wrong in
  production. The institution timezone is in this group because survey windows
  are timezone-bound (§3.1): a baked-in `America/New_York` opens the window at
  the wrong hour elsewhere and nothing says so.
* **Everything else carries a default** and is therefore optional.

Why a particular setting has a default is written at the field and nowhere
else. Three different reasons are in play — the spec settles the value, the
spec has deliberately *not* settled it, or the spec never spoke to it — and
they are easy to conflate because all three produce the same line of code.
Every attempt so far to compress them into one summarizing sentence has
produced a claim about the spec that the spec does not make, in this docstring,
in the group header below, and in `.env.example`. The per-field comments have
been right every time. They carry it alone now.

**A credential never reaches a log through this class**, and there are two ways
in, so there are two guarantees. `DATABASE_URL`, `CARE_DATABASE_URL` and
`REDIS_URL` carry passwords today; the AI provider key, the SMTP password, and
the LTI private key are coming (§6.3), and SPEC §10 puts secrets in the
environment precisely so they stay out of logs.

*When the configuration is refused*, no value is quoted back. The failure names
the variables at fault and says what is wrong with each, and it happens at
startup, where the only place it can go is the container log. This is enforced
by construction rather than by remembering: `Settings` converts any validation
failure into a `ConfigurationError` built only from field names, static field
descriptions, and pydantic's error-type codes. A field added later is covered
without anyone knowing this paragraph exists, which is the property that matters
— a fix that enumerated today's password-bearing fields would not survive the
next one.

*When the configuration is accepted*, the object that results lives on
`app.state` for the process lifetime and gets handed to whatever wants to
describe the running configuration. There the guarantee cannot be blanket,
because "hide everything" would make the object useless to the §6.3 admin
configuration view it is meant to feed. So it is per-field and carried by the
type: **a field that holds a credential is declared `SecretStr`**, which masks
it in `repr()`, `str()`, `model_dump()`, `model_dump_json()`, `dict(settings)`,
iteration, and the generated schema alike. The type travels with the value, so
anything built out of one is masked too; a guard written on the model would have
had to be repeated for every container the value can end up in.
"""

import ipaddress
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationError, ValidationInfo, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, SettingsConfigDict

# What pydantic's error-type codes mean, in words an operator can act on. Keyed
# on the code and never on the message, because a message is built from the
# value that failed and a code never is. An unknown code falls back to the code
# itself, which is a static string from the library.
_PROBLEM_EXPLANATIONS = {
    "missing": "not set",
    "string_type": "not text",
    "int_parsing": "not a whole number",
    "int_type": "not a whole number",
    "float_parsing": "not a number",
    "bool_parsing": "not a true or false value",
    "greater_than_equal": "below the smallest value this setting allows",
    "less_than_equal": "above the largest value this setting allows",
    "value_error": "rejected by this setting's own validation",
}


class ConfigurationError(Exception):
    """The environment does not configure the application, and startup stops here.

    Names the variables at fault and says what is wrong with each in general
    terms. It holds no configuration value, exposes no structured payload to
    serialize one into, and is raised with no exception chained behind it —
    pydantic's `ValidationError` retains the input it was given in `errors()`
    whatever is done to its rendering, and Python prints a chained cause's
    message too, so the only way to keep a password out of the startup log is
    for the exception that reaches it to have never held one.
    """


def _describe_invalid_settings(
    error: ValidationError,
    env_prefix: str,
    fields: Mapping[str, FieldInfo],
) -> list[str]:
    """Turn a validation failure into one line per variable, with no values in it.

    Every ingredient is static: the field name, the `description=` written in
    the class body, and pydantic's error-type code. Nothing is read from the
    input that failed, which is what makes this safe for a field nobody has
    written yet.
    """
    lines: list[str] = []
    for detail in error.errors():
        location = detail.get("loc") or ()
        field_name = str(location[0]) if location else ""
        variable = f"{env_prefix}{field_name}".upper() if field_name else "(unknown variable)"

        code = str(detail.get("type", ""))
        explanation = _PROBLEM_EXPLANATIONS.get(code, code or "invalid")

        field_info = fields.get(field_name) if field_name else None
        description = getattr(field_info, "description", None)

        lines.append(f"  {variable} — {explanation}")
        if description:
            lines.append(f"      {description}")
    return lines


def _blank_is_absent(value: object) -> object:
    """Read a blank string as "this process was not given the value".

    Blanking is how a value is *removed* in Compose: `env_file:` has already
    handed a service the whole of `.env` by the time its own `environment:`
    block is applied, so setting a variable to the empty string is what
    withholds it and omitting the entry leaves it in place. An empty string that
    validated would leave the withheld-from process looking configured and fail
    later, somewhere else.

    Whitespace is stripped first: a value that is only spaces is a blanking
    somebody reformatted, not a value.

    Written once and used by every optional field that can be withheld this way,
    rather than copied per field — the copy is the one nobody updates
    (`docs/MISTAKES.md` entry 13).
    """
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _is_on_this_machine(host: str | None) -> bool:
    """Whether a URL's host names this machine, so nothing crosses a network.

    `localhost` by name, and any address in a loopback range by value —
    `127.0.0.0/8` and `::1`. A name this cannot resolve is not this machine: the
    check is used to *permit* cleartext, so an unknown answer has to be "no".
    """
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _configuration_error(problems: Iterable[str]) -> ConfigurationError:
    """Assemble the error operators read at three in the morning."""
    report = "\n".join(problems)
    return ConfigurationError(
        "The environment does not configure this application:\n"
        f"{report}\n"
        "Set each variable named above and start again. .env.example documents "
        "all of them.\n"
        "No values are shown here on purpose: this message goes to the startup "
        "log, and the configuration carries credentials (SPEC §10)."
    )


class Settings(BaseSettings):
    """The configuration surface that exists this early in the build."""

    model_config = SettingsConfigDict(
        # A local `.env` is a developer convenience; in every deployed
        # environment the process environment is the only source.
        env_file=".env",
        env_file_encoding="utf-8",
        # Compose and the mock services put variables of their own in the same
        # file. Ignoring them keeps `.env` usable as one file without making
        # this class the union of everything anybody needs.
        extra="ignore",
        # Belt to the braces below: it keeps values out of a `ValidationError`
        # rendered by a path that bypasses `__init__`, such as
        # `model_validate`. It is not the fix and cannot be — it cleans the
        # message and leaves the input in `errors()`, one `json.dumps` away
        # from any structured logger.
        hide_input_in_errors=True,
    )

    def __init__(self, **overrides: Any) -> None:
        """Build from the environment, reporting a failure without quoting values.

        The conversion happens here, in the constructor, rather than in a
        factory a caller has to remember to use: `Settings()` is what every
        entry point writes, and it is the shape the startup path takes.

        The re-raise is deliberately outside the `except` block. Inside it,
        Python would attach the `ValidationError` as `__context__` — and a
        chained exception's message is printed in the traceback too, so the
        credential would reach the log by the back door. `raise ... from None`
        does not help: it suppresses the display but leaves `__context__` set
        for anything that inspects the chain.
        """
        try:
            super().__init__(**overrides)
        except ValidationError as invalid:
            problems = _describe_invalid_settings(
                invalid,
                str(type(self).model_config.get("env_prefix", "") or ""),
                type(self).model_fields,
            )
        else:
            return

        raise _configuration_error(problems)

    # --- deployment wiring, credential-bearing --------------------------------
    #
    # **Anything here that carries a credential is `SecretStr`, never `str`.**
    # That single choice covers every standard way a pydantic model turns
    # itself into data — `repr`, `str`, `model_dump`, `model_dump_json`,
    # `dict()`, iteration, and the OpenAPI schema — because the mask lives on
    # the value rather than on the model, so every container the value is
    # copied into inherits it.
    #
    # Each URL below carries a password in the same position. The AI provider
    # key (§6.3, E0-13), the SMTP password, and the LTI private key belong in
    # this group when they land.
    #
    # The cost is that reading one is `settings.database_url.get_secret_value()`
    # rather than `settings.database_url`. That is the point: extracting a
    # credential becomes an explicit act with a name a reviewer can search for,
    # instead of something that happens by writing an attribute.
    database_url: SecretStr = Field(description="SQLAlchemy URL for the application database.")
    # The second pool, and the reason it is a second entry rather than something
    # derived from the first: it names a different role, `pulse_care`, with a
    # credential of its own. Deriving it would mean one credential opening both
    # connections, which is the whole of ADR 0001's separation undone in a string
    # substitution. Only `app.services.safety` reads it (ADR 0042); every other
    # read path in the application runs on `database_url` and cannot reach
    # identity at all.
    #
    # Optional, and absent is the ordinary state rather than a misconfiguration.
    # The process that serves the Care queue is the only process that may hold
    # this credential: it is the one thing in the cluster that can execute
    # `public.reveal_student_identity`, so a container holding it can obtain a
    # student's name. `docker-compose.yml` therefore gives it to `api` and blanks
    # it on `worker` and `beat`, which never serve that queue — and `worker` is
    # the process that ships comment text to a third-party model provider. A
    # required field could not express that: `Settings` is built the same way in
    # all three, so requiring it here would force the credential into all three.
    #
    # An empty string is read as absent, because blanking is how `env_file:`
    # values are removed — a `SecretStr('')` that validated would leave the two
    # job processes looking configured and fail at `create_engine` instead.
    # `app.services.safety` is the only reader, and it refuses loudly when this
    # is `None` (ADR 0042, as amended).
    care_database_url: SecretStr | None = Field(
        default=None,
        description="SQLAlchemy URL for the Care queue's database connection (SPEC §6.2).",
    )
    redis_url: SecretStr = Field(description="Redis URL for the Celery broker and result backend.")
    # The AI provider credential (§6.3: "AI provider (base URL, model, masked
    # key)"). `SecretStr` for the reason the block above gives, and it is the
    # field that reason was written for: `app.ai.gateway` hands this value to a
    # third-party HTTP client, and the errors that client raises are printed to
    # the container log.
    #
    # Optional, and absent is an ordinary state rather than a misconfiguration:
    # `.env.example` says the base URL may name "a hosted provider, a proxy, or
    # a local server such as vLLM or Ollama", and the last two commonly want no
    # credential at all. A required field would make a local model impossible to
    # run against without inventing a value for it.
    #
    # An empty string is read as absent, by the same rule and for the same
    # reason as `care_database_url` below: blanking is how a value is withheld,
    # and a `SecretStr('')` that validated would send an empty bearer token
    # rather than no header.
    ai_provider_api_key: SecretStr | None = Field(
        default=None,
        description="Credential for the AI provider, when the endpoint wants one (SPEC §6.3).",
    )

    # --- deployment wiring, no credential: required, no default ---------------
    ai_provider_base_url: str = Field(
        description=(
            "OpenAI-compatible API base URL (§7.4). Must be https when AI_PROVIDER_API_KEY is "
            "set, unless it names this machine: plain http off this machine would put the "
            "credential and the comment being classified on the wire in the clear (§10)."
        )
    )
    ai_model_name: str = Field(description="Model identifier passed to that provider.")
    institution_timezone: str = Field(
        description="IANA timezone the survey window follows (§3.1), such as America/New_York."
    )
    environment: str = Field(description="Deployment name, reported by /healthz. Free-form.")

    # --- defaulted: optional, each for its own reason -------------------------
    #
    # The reason is on the field. It is not the same reason twice, and no
    # heading here summarizes it — see the module docstring for why not.

    # The spec never spoke to this one. §6.3 enumerates the configuration
    # surface and no log level is in it; no other section mentions one. INFO is
    # this project's choice, defaulted because a log level is not
    # deployment-specific in the way the required group above is.
    log_level: str = Field(default="INFO", description="Root log level.")

    # Settled by the spec: §4 makes the threshold "configurable (default 5)".
    # A spec-given default is not a silent fallback.
    n_threshold_default: int = Field(
        default=5,
        ge=1,
        description="Responses below which raw comments stay hidden (§4).",
    )

    # Deliberately *not* settled by the spec. §11 open question 1: the benchmark
    # mechanism is specced (§5.1) and the numbers are not. 3 and 15 are the
    # suggested starting values, not settled ones — expect them to move once
    # there is real data behind them. Defaulted so that answering §11 stays a
    # configuration change rather than a code change.
    benchmark_min_sections_default: int = Field(
        default=3,
        ge=1,
        description="Sections a comparison set needs before it is shown (§5.1).",
    )
    benchmark_min_respondents_default: int = Field(
        default=15,
        ge=1,
        description="Respondents a comparison set needs before it is shown (§5.1).",
    )

    @field_validator("ai_provider_api_key", mode="before")
    @classmethod
    def blank_provider_key_is_absent(cls, value: object) -> object:
        """A blank `AI_PROVIDER_API_KEY` means this endpoint wants no credential.

        A local OpenAI-compatible server — vLLM, Ollama, a proxy on the same
        host — authenticates nobody, and the way a developer says so is to leave
        the entry empty rather than to delete a line from `.env`.

        **What absent means on the wire**, since three documents described it
        wrongly until E0-13's review measured it: the request still carries an
        `Authorization` header, holding `app.ai.gateway`'s inert
        `UNAUTHENTICATED` placeholder. The client the gateway builds refuses to
        be constructed without a credential, and removing the header would mean
        building that client here rather than letting the provider library build
        it — which would put a second provider-library import in the tree. What a
        blank value avoids is an *empty* bearer token, which some servers refuse
        and none is helped by; an endpoint that authenticates nobody ignores the
        placeholder.

        `_blank_is_absent` above is the rule itself.
        """
        return _blank_is_absent(value)

    @field_validator("ai_provider_base_url")
    @classmethod
    def a_credentialled_endpoint_is_encrypted(cls, value: str, info: ValidationInfo) -> str:
        """Refuse to carry the provider key, or a student's comment, in cleartext.

        SPEC §10 makes transport encryption a requirement, and this is the one
        configuration in the surface that can quietly break it: `http://` with a
        key configured puts the bearer token *and* the comment being classified on
        the wire in the clear, and nothing else in the system would object.

        The rule is narrow on purpose. An endpoint **on this machine** may be
        plain `http`, because nothing leaves the host — that is how a local
        vLLM or Ollama is reached, which `.env.example` and `README.md` both
        document. Anything else, with a credential configured, must be `https`.

        **What this deliberately does not refuse**: cleartext to an off-machine
        endpoint with *no* credential, which is a service inside a private
        network — a vLLM pod reached over `http://` in the same cluster. That
        case still puts comment text on a network, and whether it is acceptable
        is the operator's call rather than this file's (ADR 0056).

        No value is quoted, as in every validator here: this message reaches the
        startup log.
        """
        if info.data.get("ai_provider_api_key") is None:
            return value
        parsed = urlsplit(value)
        if parsed.scheme == "https" or _is_on_this_machine(parsed.hostname):
            return value
        raise ValueError(
            "would send the configured provider credential, and the comment being classified, "
            "in cleartext to an address off this machine — use https, or plain http only for an "
            "endpoint on this machine"
        )

    @field_validator("care_database_url", mode="before")
    @classmethod
    def blank_care_database_url_is_absent(cls, value: object) -> object:
        """An empty `CARE_DATABASE_URL` means the process does not serve the Care queue.

        `docker-compose.yml` withholds this credential from `worker` and `beat`
        by setting it to the empty string, because `env_file:` has already handed
        them the whole of `.env` by the time the service's own `environment:`
        block is applied — blanking is what removes a value there, and omitting
        the entry leaves it in place.

        So the empty string is the spelling of "withheld", and it has to arrive
        here as `None`. A `SecretStr('')` would validate, leave those two
        processes looking configured, and turn a deliberate withholding into a
        connection attempt with no credential in it.

        `_blank_is_absent` above is the rule itself, and carries the rest of the
        reasoning.
        """
        return _blank_is_absent(value)

    @field_validator("institution_timezone")
    @classmethod
    def validate_institution_timezone(cls, value: str) -> str:
        """Reject a timezone the runtime cannot resolve, at startup rather than at 18:00.

        A typo here does not fail anywhere near where it was made: the survey
        window simply opens at the wrong hour, on a Friday, in production.

        The message does not quote the value it rejected, and no validator in
        this class ever should. `__init__` already keeps validator messages out
        of the startup log, but a validator on a future secret-bearing field —
        the SMTP password, the LTI private key — would otherwise put the value
        one bypassed code path away from a log line. Cheaper to never write it.
        """
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("not an IANA timezone name, such as America/New_York") from exc
        return value
