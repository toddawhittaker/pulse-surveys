"""Application settings, entirely environment-driven (SPEC §6.3).

Every setting here is read from the environment and documented in
`.env.example`, which a unit test holds in sync with this class in both
directions.

The fields split into two groups, and the split is the point:

* **Deployment wiring** has no default. A database URL, a Redis URL, an AI
  provider base URL and model name, the institution timezone, the environment
  name, and the five settings that name the identity provider a web login is
  verified against all differ per deployment, and a working literal default for
  any of them is a misconfiguration that starts successfully and is wrong in
  production. The institution timezone is in this group because survey windows
  are timezone-bound (§3.1): a baked-in `America/New_York` opens the window at
  the wrong hour elsewhere and nothing says so. The identity provider is in it
  because its default was worse than wrong: `http://mock-idp:8000` is a service
  the base Compose file starts in *every* deployment, so a deployment that set
  none of the five trusted a provider that signs an `id_token` for any identity
  it is asked for, CARE and ADMIN included. ADR 0077 reverses that half of
  ADR 0075.
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


# The one `ENVIRONMENT` value that turns on a developer convenience. Free-form,
# and **not** an enumeration `Settings` enforces — `ENVIRONMENT` appears zero
# times in `docs/SPEC.md`, so this is a comparison against a convention
# `.env.example` documents. Anything that is not this exact string is treated as
# a deployment.
#
# It lives here rather than beside its readers because there are three of them
# and each used to hold its own copy: `app/db.py` before it lets the engine echo
# SQL and before it hides bound parameters (E0-37 item 1), `scripts/seed.py`
# before it will run at all (ADR 0063), and from E0-18 `app/main.py` before it
# serves `/docs` and `/openapi.json` (ADR 0074). Three copies of one string is
# `docs/MISTAKES.md` entry 13, and the module every one of them already imports
# is this one. E0-18 added the constant and migrated only its own reader onto
# it; **E0-37 item 2 migrated the other two**, so this is the one definition and
# `tests/unit/test_development_environment_has_one_definition.py` sweeps
# `backend/app` and `scripts` for a second.
DEVELOPMENT_ENVIRONMENT = "development"

# The two spellings by which a configuration can reach or name the mock identity
# provider `docker-compose.yml` starts, refused outside development by the two
# validators at the foot of `Settings` (ADR 0077).
#
# The first is the Compose service name, which is how a container on this stack
# reaches the mock. The second is the client the mock is registered with, which
# is how a configuration names the mock without addressing it — the case a rule
# about URLs cannot see, since a deployment carrying it is configured to be the
# mock's client whatever its addresses say.
#
# Written out here rather than derived from anything: it is a catalog of two, and
# a third spelling should cost a reviewed diff on these lines.
# `tests/unit/test_oidc_provider_configuration.py` holds each of them against the
# thing it names — the service in `docker-compose.yml`, and the client id
# `.env.example` configures — because a catalog that has gone stale refuses
# nothing and reports every configuration clean, exactly as a correct one does
# (`docs/MISTAKES.md` entry 35).
#
# `localhost` and the loopback addresses are deliberately *not* here. Inside a
# deployed container `localhost` is that container, so it cannot resolve to the
# mock; refusing it would refuse a provider running alongside the application,
# which is a supported deployment, and would protect nothing. ADR 0077 argues it.
MOCK_IDENTITY_PROVIDER_HOST = "mock-idp"
MOCK_IDENTITY_PROVIDER_CLIENT_ID = "mock-idp-client"


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


def _url_host(value: str) -> str | None:
    """A URL's host, read the way a resolver reads it, for every comparison below.

    `urlsplit(...).hostname` already does most of it: it strips an IPv6 literal's
    brackets and lower-cases the name, which is what makes `MOCK-IDP` and
    `mock-idp` one host (RFC 4343).

    What it leaves is the **one trailing dot** that makes a name fully qualified.
    `mock-idp.` and `mock-idp` reach the same container, and `localhost.` and
    `localhost` reach the same interface, so a catalog that compares strings is
    defeated by a one-character edit. Exactly one dot comes off: stripping every
    trailing dot, or stripping and then comparing by prefix, would turn
    `mock-idp.example.edu.` — a real institutional address — into a refusal.

    Written once and called by all three rules below rather than at each
    comparison, because a normalisation applied at one site and not another
    closes half of the hole it was written for (`docs/MISTAKES.md` entry 13).
    """
    host = urlsplit(value).hostname
    if host is None:
        return None
    return host[:-1] if host.endswith(".") else host


def _is_a_loopback_host(host: str | None) -> bool:
    """Whether this host names the machine the *reader* of the URL is sitting at.

    A class, not a list of spellings, and that is the whole point: a three-entry
    catalog of `localhost`, `127.0.0.1` and `::1` is defeated by `127.0.0.2`,
    which is an ordinary address in `127.0.0.0/8`, and by `::ffff:127.0.0.1`.
    Both send a browser to a listener on the user's own machine.

    **The IPv4-mapped form is unwrapped first, deliberately, and not because
    `is_loopback` gets it wrong.** Measured on the interpreter this project pins:
    on 3.13 `ip_address("::ffff:127.0.0.1").is_loopback` is already `True`,
    because that version reads the mapped address through. So a check written as
    "`is_loopback`, and failing that `ipv4_mapped.is_loopback`" has a second half
    that never runs here — a guard nobody has executed, which is a comment
    (`docs/MISTAKES.md` entry 9). Asking `ipv4_mapped` first gives the same
    answer for every address, keeps both halves live, and stops the rule
    depending on a library behaviour that has moved between versions.

    **This is a wider set than `_is_on_this_machine` above, and the two are
    deliberately not merged.** That one governs an *exemption* — cleartext is
    permitted because nothing crosses a network — and widening an exemption
    permits more; this one governs a *refusal*, and widening it refuses more. A
    single helper would mean every future widening moved both, in opposite
    directions of safety.
    """
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_loopback
    return address.is_loopback


def _is_a_deployment(environment: object) -> bool:
    """Whether this process is running anywhere other than a development stack.

    An exact comparison against the one development name, so `staging`,
    `production`, `development-blue` and `pre-development` are all deployments.
    A substring test would read as the same rule and would hand the mock to every
    environment named after development.

    A value that is not a string is not treated as a deployment, and that cannot
    let a mock address through: `environment` is required, so a `Settings` whose
    `ENVIRONMENT` never validated is already being refused for that variable and
    the process stops either way.
    """
    return isinstance(environment, str) and environment != DEVELOPMENT_ENVIRONMENT


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
            "OpenAI-compatible API base URL (§7.4). It carries no credential of its own — no "
            "user:password@ prefix; the key belongs in AI_PROVIDER_API_KEY. And it must be "
            "https unless it names this machine, with or without a key: plain http off this "
            "machine would put the comment being classified, and any credential sent with it, "
            "on the wire in the clear (§10)."
        )
    )
    ai_model_name: str = Field(description="Model identifier passed to that provider.")
    institution_timezone: str = Field(
        description="IANA timezone the survey window follows (§3.1), such as America/New_York."
    )
    # Free-form by this project's choice, not by the spec: `ENVIRONMENT` and
    # `healthz` each appear zero times in `docs/SPEC.md`, and §6.3 — the
    # configuration surface — names no environment variable. `.env.example` is
    # where the vocabulary is documented, and `development`, `staging` and
    # `production` are conventions nothing enforces. Two readers compare against
    # the first of those: `app/db.py` before it lets the engine echo SQL, and
    # `scripts/seed.py` before it will run at all (ADR 0063).
    # E0-18 adds a third reader, `app/main.py`, which compares against
    # `DEVELOPMENT_ENVIRONMENT` below before it serves `/docs` and
    # `/openapi.json` (ADR 0074).
    environment: str = Field(description="Deployment name, reported by /healthz. Free-form.")

    # --- the web door's identity provider (E0-18, ADR 0077) -------------------
    #
    # Five values, none of them a credential — the client is public and PKCE is
    # what binds a code to it (RFC 7636) — and all five required. ADR 0075
    # defaulted them to this repository's own development stack, and the
    # epic-boundary threat model measured what that meant: `docker-compose.yml`
    # starts `mock-idp` in every deployment, so an operator who deployed per
    # §7.2 and set none of these had a signing oracle for fake CARE and ADMIN
    # identities, which this application then verified correctly and trusted.
    # ADR 0077 reverses that half of ADR 0075; `PUBLIC_BASE_URL` and
    # `LTI_PLATFORM_AUTHORIZATION_ENDPOINT` keep their defaults for the reasons
    # at their own block below.
    #
    # The development values did not disappear, they moved: `docker-compose.yml`
    # gives all three `Settings`-building services `${OIDC_ISSUER:-...}` and the
    # four beside it, and `.env.example` documents them. So `docker compose up`
    # from a clean checkout still reaches a system a person can log in to (SPEC
    # §14.3), and a deployment's own `.env` still wins.
    #
    # **Two horizons, decided per value rather than per service.** A browser on
    # the host reaches these services on published ports at `localhost`; the
    # application's container reaches them by Compose service name. A value a
    # browser is redirected to is `localhost`; a value this tool fetches
    # server-side is the service name. Getting this backwards produces a stack
    # that passes every in-process test and sends a real browser to a name it
    # cannot resolve.
    #
    # **These five are declared after `environment` deliberately.** The two
    # validators at the foot of this class read `ENVIRONMENT` out of the fields
    # pydantic has already validated, and pydantic validates in declaration
    # order — so a `Settings` that declared `environment` below them would
    # accept a mock address everywhere.
    #
    # **Each description below carries the rule as well as the meaning**, and
    # that is not decoration. `_describe_invalid_settings` builds the startup
    # report out of the field name, this string, and pydantic's error code — a
    # validator's own message never reaches the operator (ADR 0056), so a
    # refusal whose reason lives only in the validator prints "rejected by this
    # setting's own validation" and sends somebody to re-type a URL that is
    # spelled correctly. `ai_provider_base_url` above carries its transport rule
    # for the same reason.
    oidc_issuer: str = Field(
        description=(
            "The `iss` a web login's `id_token` must state (OIDC Core 1.0 §3.1.3.7). Not "
            "browser-facing: it is compared against a claim, never redirected to. Outside "
            "ENVIRONMENT=development it may not address the mock provider this repository "
            "ships, the Compose service mock-idp, and it must be https unless it names a "
            "provider on this machine."
        )
    )
    oidc_authorization_endpoint: str = Field(
        description=(
            "Browser-facing OIDC authorization endpoint of the identity provider. Outside "
            "ENVIRONMENT=development it may not address the mock provider this repository "
            "ships, the Compose service mock-idp; it must be https; and it may not name this "
            "machine at all — localhost or any loopback address — because a browser, not this "
            "container, is what resolves it, so loopback there is the end user's own computer."
        )
    )
    oidc_token_endpoint: str = Field(
        description=(
            "Server-facing OIDC token endpoint, where this tool redeems a code. Outside "
            "ENVIRONMENT=development it may not address the mock provider this repository "
            "ships, the Compose service mock-idp, and it must be https unless it names a "
            "provider on this machine."
        )
    )
    oidc_jwks_url: str = Field(
        description=(
            "Server-facing key set a web login's `id_token` is verified against. Outside "
            "ENVIRONMENT=development it may not address the mock provider this repository "
            "ships, the Compose service mock-idp, and it must be https unless it names a "
            "provider on this machine."
        )
    )
    oidc_client_id: str = Field(
        description=(
            "This tool's registered client at the identity provider. The client is public: "
            "it holds no secret, and PKCE is what binds a code to it (RFC 7636). Outside "
            "ENVIRONMENT=development it may not be the mock provider's own registered "
            "client, mock-idp-client."
        )
    )

    # --- defaulted: optional, each for its own reason -------------------------
    #
    # The reason is on the field. It is not the same reason twice, and no
    # heading here summarizes it — see the module docstring for why not.

    # --- the launch door's addresses (E0-18) ----------------------------------
    #
    # Two values, both of them addresses a browser is sent to. They are
    # defaulted, and the reason is the third of the three this module keeps
    # apart: **the spec never spoke to them.** §6.3's configuration surface names
    # no LTI endpoint, §7.3 leaves the platform's addresses to the registration,
    # and E0-23 decided that `lti_platform` gains service-address columns in E1,
    # with the code that reads them. So the values below are E0's stand-in and
    # the ADR says so (docs/adr/0075).
    #
    # **Each default is this repository's own development stack**, spelled the
    # way `docker-compose.override.yml` publishes it — a browser-facing horizon
    # in both cases, per the note at the identity provider above. That is
    # deliberate and it is not the "working literal default" the module docstring
    # refuses: neither address can resolve in a deployment, and neither names
    # anything the base Compose file starts, so a deployment that forgets one
    # gets a launch that fails at its first hop rather than a system that is
    # quietly wrong. What a required field would buy instead is a startup
    # refusal, and what it would cost is that `docker compose up` from a clean
    # checkout — E0's own exit criterion (§14.3) — stops working without an
    # `.env` nobody has written yet.
    #
    # **The five `oidc_*` settings used to be in this block and are not any
    # more** (ADR 0077). The argument above did not hold for them: `mock-idp` is
    # a service every deployment starts, so their default *did* resolve.
    public_base_url: str = Field(
        default="http://localhost:8000",
        description=(
            "Browser-facing base URL of this tool. `/lti/launch` and "
            "`/auth/oidc/callback` are derived from it, and both mocks compare "
            "the result exactly against what they were registered with."
        ),
    )
    lti_platform_authorization_endpoint: str = Field(
        default="http://localhost:8080/oidc/authorize",
        description=(
            "Browser-facing OIDC authorization endpoint of the LTI platform. A settings "
            "field because `lti_platform` has no column for it until E1 (E0-23)."
        ),
    )
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
    def the_provider_url_carries_no_credential(cls, value: str) -> str:
        """Refuse `https://user:password@host/...`. The key has its own variable.

        A URL may carry userinfo, and an HTTP client turns it into a real
        `Authorization: Basic ...` header — measured on this stack. Two things go
        wrong at once when it does. This field is a plain `str`, not a
        `SecretStr`, so a password inside it appears in `repr(settings)`, in
        `model_dump()`, and in §6.3's admin configuration view, which is specified
        to show "AI provider (base URL, model, masked key)" and would render the
        password beside the masked key. And the rule below, which asks whether a
        credential is configured, would answer "no" while a credential was sitting
        in this string.

        Refusing it is what keeps both of those true by construction rather than
        by a second mechanism: the base URL stays a plain, displayable string
        because it cannot hold a secret, and "no `AI_PROVIDER_API_KEY`" really
        does mean "no credential". A proxy that wants Basic authentication is
        reached with `AI_PROVIDER_API_KEY`, or through one that does not.

        No value is quoted, as in every validator here: this message reaches the
        startup log, and the thing being refused is the credential itself.
        """
        parsed = urlsplit(value)
        if parsed.username or parsed.password:
            raise ValueError(
                "carries a credential in the URL itself, where it is neither masked in this "
                "application's own configuration view nor covered by the transport rule below; "
                "put the credential in AI_PROVIDER_API_KEY and remove the user:password@ prefix"
            )
        return value

    @field_validator("ai_provider_base_url")
    @classmethod
    def an_off_machine_endpoint_is_encrypted(cls, value: str) -> str:
        """Refuse to carry a student's comment, or the provider key, in cleartext.

        SPEC §10 makes transport encryption a requirement, and this is the one
        configuration in the surface that can quietly break it: `http://` to
        another host puts the comment being classified — and the bearer token, if
        one is configured — on the wire in the clear, and nothing else in the
        system would object.

        The rule is short. **Off this machine means `https`**, credential or not.
        An endpoint **on this machine** may be plain `http`, because nothing
        leaves the host — that is how a local vLLM or Ollama is reached, which
        `.env.example` and `README.md` both document.

        The key is not the thing this protects. Every request the gateway makes
        carries a student's free-text comment in its body; §4 confines that text
        to the surfaces it names and §10 keeps it off the wire in the clear, and
        that is true whether or not the endpoint asks for a credential. So the
        rule does not read `ai_provider_api_key` at all, and a keyless
        `http://vllm.internal/v1` — a model pod reached over plain HTTP inside a
        cluster — is refused (Todd, 2026-08-18). That deployment is served by
        terminating TLS at the model, or by running the model alongside the
        application, where the on-this-machine case above already permits it.

        No value is quoted, as in every validator here.
        """
        parsed = urlsplit(value)
        if parsed.scheme == "https" or _is_on_this_machine(parsed.hostname):
            return value
        raise ValueError(
            "would send the comment being classified, and any provider credential configured "
            "with it, in cleartext to an address off this machine — use https, or plain http "
            "only for an endpoint on this machine"
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

    @field_validator(
        "oidc_issuer",
        "oidc_authorization_endpoint",
        "oidc_token_endpoint",
        "oidc_jwks_url",
    )
    @classmethod
    def no_provider_url_addresses_the_mock_outside_development(
        cls, value: str, info: ValidationInfo
    ) -> str:
        """Refuse an identity provider URL that addresses the mock, in a deployment.

        The layer that makes the required fields above worth requiring. Making
        them required stops the deployment that configures *nothing*; this stops
        the one that configures the mock — by copying the development stack's
        values forward, which is the ordinary way a wrong value gets into a
        deployment's `.env`.

        All four URLs, because they fail differently and a rule covering some of
        them would read as covering the door. `oidc_jwks_url` and
        `oidc_token_endpoint` are fetched, so a mock there mints the session;
        `oidc_issuer` is never fetched at all — it is compared against the `iss`
        claim as a string (OIDC Core 1.0 §3.1.3.7) — so a mock there is what
        makes the mock's tokens acceptable; and `oidc_authorization_endpoint` is
        where a real browser is sent, so a mock there is the login page a person
        is asked to trust.

        **The host component, compared exactly**, and normalised once by
        `_url_host` — the port, the scheme and the path are not part of the
        question, since a container reaching `mock-idp` on any port reaches the
        mock, and neither is the case nor a trailing dot. A substring search for
        the service name would read as the same rule and would refuse
        `https://mock-idp.example.edu/oidc/token`, an ordinary institutional
        address that resolves nowhere near this stack.

        No value is quoted, as in every validator here: this message reaches the
        startup log. The field's name and description reach the operator through
        `_describe_invalid_settings`, which is what says *which* of the five is
        wrong without echoing what it holds.
        """
        if not _is_a_deployment(info.data.get("environment")):
            return value
        if _url_host(value) == MOCK_IDENTITY_PROVIDER_HOST:
            raise ValueError(
                "addresses the mock identity provider this repository ships for development — "
                f"the Compose service {MOCK_IDENTITY_PROVIDER_HOST}, which signs an id_token for "
                "any identity it is asked for, including CARE and ADMIN. Name the deployment's "
                f"own provider, or run with ENVIRONMENT={DEVELOPMENT_ENVIRONMENT}"
            )
        return value

    @field_validator("oidc_authorization_endpoint")
    @classmethod
    def the_login_page_is_not_on_the_users_own_machine_outside_development(
        cls, value: str, info: ValidationInfo
    ) -> str:
        """Refuse to send a browser to a listener on the machine reading the link.

        **This field alone, and the asymmetry is the reason the rule exists.**
        The other four `oidc_*` URLs are resolved by this container, where a
        loopback host is the container itself — a provider sidecar, which is an
        ordinary deployment that reaches nothing an attacker controls. This one
        is never resolved here at all: it is a string handed to a browser and
        resolved on the machine that browser runs on. So `localhost` means "this
        API process" in four settings and "whoever's laptop is reading this" in
        the fifth, and only the fifth is a finding.

        What it costs to get wrong: the development value is
        `http://localhost:8081/oidc/authorize`, which names no mock, so a
        deployment that sets the other four and forgets this one starts cleanly
        and then answers every web login with a redirect to a port on the
        browsing user's own computer. Whatever is listening there receives an
        institution-issued link that arrived from a Pulse URL and can render a
        login page asking for the credentials the real provider would have asked
        for.

        **A class, not a catalog** — `_is_a_loopback_host` carries why. The
        `127.0.0.0/8` and IPv4-mapped spellings are the ones a list of three
        misses, and the review that raised this arrived with a fourth spelling
        already in it.

        **It runs before the transport rule below and does not defer to it.**
        `http://localhost:8081/oidc/authorize` is exempt from that rule — there
        is no network between a process and itself — and is refused here anyway,
        because what is wrong with it is where the browser is sent rather than
        what it is sent over. An exemption that returned early would leave the
        finding open with every other row green.
        """
        if not _is_a_deployment(info.data.get("environment")):
            return value
        if _is_a_loopback_host(_url_host(value)):
            raise ValueError(
                "sends the browser to the machine it is running on rather than to an identity "
                "provider — this value is resolved by the end user's computer, never by this "
                "container, so a loopback host here is whatever that person happens to be "
                "running. Name the provider's browser-facing address, or run with "
                f"ENVIRONMENT={DEVELOPMENT_ENVIRONMENT}"
            )
        return value

    @field_validator(
        "oidc_issuer",
        "oidc_authorization_endpoint",
        "oidc_token_endpoint",
        "oidc_jwks_url",
    )
    @classmethod
    def a_provider_url_is_encrypted_off_this_machine_outside_development(
        cls, value: str, info: ValidationInfo
    ) -> str:
        """Refuse cleartext to another host, which is the mock's hole reached anonymously.

        The same rule `an_off_machine_endpoint_is_encrypted` applies to the model
        provider, and it is here for a sharper reason. `http://idp.example.edu/…`
        names no mock and would otherwise be a legal production configuration —
        and anyone on the path between this container and that host can answer
        the key-set fetch with a key set of their own, after which every token
        signed with the matching private key verifies correctly. That is the
        signing oracle this whole ticket exists to close, reached without ever
        naming `mock-idp`.

        All four, though only two are fetched. The authorization endpoint carries
        the request and its `state` past whoever is on the path; the issuer is
        fetched by nothing at all — it is compared against the `iss` claim as a
        string — and is included because OpenID Connect Discovery requires an
        Issuer Identifier to use `https`, so an `http` issuer is not an identity
        any conformant provider has.

        **Conditioned on the environment, unlike the model provider's copy of
        this rule**, and that is not an oversight to tidy up later: every address
        on the development stack is cleartext to *another container*
        (`http://mock-idp:8000`), so an unconditional version refuses the
        configuration `.env.example` ships and CI copies to `.env`, and takes
        SPEC §14.3's exit criterion with it.

        **The exemption is `_is_on_this_machine`, not the wider loopback class.**
        A provider beside the application is reached over the loopback interface
        where there is no wire to read, so refusing it would turn away a
        deployment while protecting nothing. Widening *that* set permits more
        cleartext; widening the refusal above refuses more addresses. They are
        two catalogs on purpose.
        """
        if not _is_a_deployment(info.data.get("environment")):
            return value
        if urlsplit(value).scheme == "https" or _is_on_this_machine(_url_host(value)):
            return value
        raise ValueError(
            "would fetch or redirect over plain http to an address off this machine, where "
            "anyone on the path can answer with a key set of their own and mint identities this "
            "application then verifies correctly — use https, or plain http only for a provider "
            f"on this machine, or run with ENVIRONMENT={DEVELOPMENT_ENVIRONMENT}"
        )

    @field_validator("oidc_client_id")
    @classmethod
    def the_client_registration_is_not_the_mocks_outside_development(
        cls, value: str, info: ValidationInfo
    ) -> str:
        """Refuse the mock's registered client id, in a deployment.

        The same rule on the setting that is not a URL, and its own validator
        because it is its own code path: this compares a whole value, the one
        above reads a parsed host. A rule phrased over "every `oidc_*` URL whose
        host is the mock" covers four of the five settings and reads as covering
        the surface, and the one it misses is the one that says *which
        registration* this tool is.

        Compared whole, not searched for. `mock-idp-client-2` at a real provider
        is a real client id, and an institution that named its own registration
        after the tool it replaced is not this rule's business.

        No value is quoted, for the reason the validator above gives.
        """
        if _is_a_deployment(info.data.get("environment")) and value == (
            MOCK_IDENTITY_PROVIDER_CLIENT_ID
        ):
            raise ValueError(
                "names the client the mock identity provider this repository ships for "
                "development is registered with, so this deployment is configured to be the "
                "mock's client. Register this tool at the deployment's own provider and name "
                f"that registration, or run with ENVIRONMENT={DEVELOPMENT_ENVIRONMENT}"
            )
        return value
