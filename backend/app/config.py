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

Nothing here is logged. `Settings` carries no secret today, and when it does
(the masked AI provider key in §6.3), the rule that keeps it out of the logs is
that this object is never printed, formatted, or dumped at startup.
"""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    )

    # --- deployment wiring: required, no default -----------------------------
    database_url: str = Field(description="SQLAlchemy URL for the application database.")
    redis_url: str = Field(description="Redis URL for the Celery broker and result backend.")
    ai_provider_base_url: str = Field(description="OpenAI-compatible API base URL (§7.4).")
    ai_model_name: str = Field(description="Model identifier passed to that provider.")
    institution_timezone: str = Field(description="IANA timezone the survey window follows (§3.1).")
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
        """
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                f"{value!r} is not an IANA timezone name, such as America/New_York"
            ) from exc
        return value
