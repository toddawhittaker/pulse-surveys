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
* **Values the spec settles** keep their default. The n-threshold is
  "configurable (default 5)" in §4, and the benchmark minimums are §11 open
  question 1. A spec-given default is not a silent fallback.

**A credential never reaches a log through this class**, and there are two ways
in, so there are two guarantees. `DATABASE_URL` and `REDIS_URL` carry passwords
today; the AI provider key, the SMTP password, and the LTI private key are
coming (§6.3), and SPEC §10 puts secrets in the environment precisely so they
stay out of logs.

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

from collections.abc import Iterable, Mapping
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationError, field_validator
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
    # Both URLs below carry a password in the same position. The AI provider
    # key (§6.3, E0-13), the SMTP password, and the LTI private key belong in
    # this group when they land.
    #
    # The cost is that reading one is `settings.database_url.get_secret_value()`
    # rather than `settings.database_url`. That is the point: extracting a
    # credential becomes an explicit act with a name a reviewer can search for,
    # instead of something that happens by writing an attribute.
    database_url: SecretStr = Field(description="SQLAlchemy URL for the application database.")
    redis_url: SecretStr = Field(description="Redis URL for the Celery broker and result backend.")

    # --- deployment wiring, no credential: required, no default ---------------
    ai_provider_base_url: str = Field(description="OpenAI-compatible API base URL (§7.4).")
    ai_model_name: str = Field(description="Model identifier passed to that provider.")
    institution_timezone: str = Field(
        description="IANA timezone the survey window follows (§3.1), such as America/New_York."
    )
    environment: str = Field(description="Deployment name, reported by /healthz. Free-form.")

    # --- settled by the spec: defaulted --------------------------------------
    log_level: str = Field(default="INFO", description="Root log level.")
    n_threshold_default: int = Field(
        default=5,
        ge=1,
        description="Responses below which raw comments stay hidden (§4).",
    )
    # §11 open question 1: the benchmark mechanism is specced (§5.1) and the
    # numbers are not. 3 and 15 are the suggested starting values, not settled
    # ones — expect them to move once there is real data behind them.
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
