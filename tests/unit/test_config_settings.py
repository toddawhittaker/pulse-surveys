"""`app.config.Settings` — ticket E0-01, acceptance criteria 2 and 3.

Criterion 2: `Settings` raises at startup when a required variable is absent,
with a message naming the variable. No silent fallback to a working default.

The ticket enumerates the configuration surface that exists this early
("database URL, Redis URL, institution timezone, environment name, log level,
AI provider base URL and model name, and the n-threshold and benchmark min-N
defaults") but does not spell the variables. The spellings below are **this
test's choice**, collected in one place so they are cheap to change — except
`DATABASE_URL`, which is already fixed by the migration-drift job in
`.github/workflows/ci.yml`.
"""

import pytest

# The surface the ticket enumerates, as environment variable names. Asserted as
# a subset of what is documented, not as an exact set: an implementer who also
# needs, say, an AI provider API key is not blocked by this test.
#
# Benchmark min-N is two numbers, not one: SPEC §11 open question 1 puts the
# mechanism in §5.1 and leaves the values unsettled, suggesting 3 sections and
# 15 respondents as starting points. Both are env-driven precisely so settling
# that question stays cheap, and neither value is asserted anywhere in this
# suite — a test pinning 3 and 15 would turn settling §11 into a test edit.
ENUMERATED_CONFIGURATION_VARIABLES = (
    "DATABASE_URL",
    "REDIS_URL",
    "INSTITUTION_TIMEZONE",
    "ENVIRONMENT",
    "LOG_LEVEL",
    "AI_PROVIDER_BASE_URL",
    "AI_MODEL_NAME",
    "N_THRESHOLD_DEFAULT",
    "BENCHMARK_MIN_SECTIONS_DEFAULT",
    "BENCHMARK_MIN_RESPONDENTS_DEFAULT",
)

# Deployment wiring: each of these differs per deployment, so a working literal
# default for any of them is exactly the silent misconfiguration criterion 2
# guards against. The institution timezone is here because survey windows are
# timezone-bound (SPEC §3.1) — a baked-in `America/New_York` would open windows
# at the wrong hour somewhere else and nothing would say so.
DEPLOYMENT_SPECIFIC_VARIABLES = (
    "DATABASE_URL",
    "REDIS_URL",
    "AI_PROVIDER_BASE_URL",
    "INSTITUTION_TIMEZONE",
    "ENVIRONMENT",
    "AI_MODEL_NAME",
)

# The other side of the split, asserted rather than merely omitted, so nobody
# tightens one of these into a required variable later:
#
#   N_THRESHOLD_DEFAULT   SPEC §4 settles it — "threshold value is configurable
#                         (default 5)". A spec-given default is not a silent
#                         fallback, so requiring it would contradict the spec.
#   BENCHMARK_MIN_*       §11 open question 1; defaulted, values unsettled.
#   LOG_LEVEL             not deployment-specific in the sense criterion 2 means.
DEFAULTED_VARIABLES = (
    "LOG_LEVEL",
    "N_THRESHOLD_DEFAULT",
    "BENCHMARK_MIN_SECTIONS_DEFAULT",
    "BENCHMARK_MIN_RESPONDENTS_DEFAULT",
)

#
# The n-threshold is also the one enumerated setting whose type is unambiguous:
# it is a count of respondents (§4.1, §5.1), so it must arrive from the string
# environment as an int.
N_THRESHOLD_VARIABLE = "N_THRESHOLD_DEFAULT"
N_THRESHOLD_FIELD = "n_threshold_default"


def load_settings_class() -> type:
    """Import `Settings` inside the test, so a missing module fails one test loudly."""
    from app.config import Settings

    return Settings


def test_configuration_surface_the_ticket_enumerates_is_documented(
    documented_env: dict[str, str],
) -> None:
    """Every setting E0-01 lists for the §6.3 surface appears in `.env.example`."""
    missing = [name for name in ENUMERATED_CONFIGURATION_VARIABLES if name not in documented_env]
    assert not missing, (
        f".env.example does not document {missing}. E0-01 requires the configuration "
        "surface that exists this early: database URL, Redis URL, institution "
        "timezone, environment name, log level, AI provider base URL and model name, "
        "and the n-threshold and benchmark min-N defaults."
    )


def test_settings_loads_from_the_documented_placeholders(
    configured_env: dict[str, str],
) -> None:
    """`.env.example` is itself a working configuration.

    The ticket makes `.env.example` the configuration documentation, and the e2e
    job in `.github/workflows/ci.yml` runs the stack off `cp .env.example .env`.
    Placeholders that do not validate would make both of those false.
    """
    settings_cls = load_settings_class()

    settings = settings_cls()

    assert settings is not None


@pytest.mark.parametrize("missing_variable", DEPLOYMENT_SPECIFIC_VARIABLES)
def test_absent_deployment_variable_raises_naming_the_variable(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    missing_variable: str,
) -> None:
    """Criterion 2: absent required variable raises, and the message names it.

    Matched case-insensitively: an operator reading the traceback needs to find
    the variable, and whether the library reports `DATABASE_URL` or
    `database_url` is not something the ticket decides.
    """
    monkeypatch.delenv(missing_variable, raising=False)

    # Import inside the block as well: an implementation that builds settings at
    # import time raises there, and that is still "raises at startup".
    with pytest.raises(Exception, match=f"(?i){missing_variable}"):
        load_settings_class()()


@pytest.mark.parametrize("defaulted_variable", DEFAULTED_VARIABLES)
def test_defaulted_variable_is_not_required(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    defaulted_variable: str,
) -> None:
    """The other half of criterion 2: a spec-given default is not a silent fallback.

    SPEC §4 makes the n-threshold "configurable (default 5)" and §11 leaves the
    benchmark values open behind defaults. Requiring any of them would
    contradict the spec, so this test exists to stop a later tightening. It
    asserts the variable is optional, never what its default is — the benchmark
    numbers are unsettled, and pinning them here would turn settling §11 open
    question 1 into a test edit.
    """
    monkeypatch.delenv(defaulted_variable, raising=False)
    settings_cls = load_settings_class()

    settings = settings_cls()

    assert settings is not None


def test_n_threshold_default_is_coerced_from_the_environment_string(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 2's other half: environment strings arrive as their declared types."""
    monkeypatch.setenv(N_THRESHOLD_VARIABLE, "7")
    settings_cls = load_settings_class()

    settings = settings_cls()

    assert hasattr(
        settings, N_THRESHOLD_FIELD
    ), f"Settings has no `{N_THRESHOLD_FIELD}` attribute for {N_THRESHOLD_VARIABLE}."
    value = getattr(settings, N_THRESHOLD_FIELD)
    assert value == 7, f"{N_THRESHOLD_VARIABLE}='7' arrived as {value!r}, not the int 7."
    assert isinstance(value, int)


def test_non_numeric_n_threshold_is_rejected_naming_the_variable(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A value that cannot be coerced fails loudly rather than falling back."""
    monkeypatch.setenv(N_THRESHOLD_VARIABLE, "not-a-number")

    with pytest.raises(Exception, match=f"(?i){N_THRESHOLD_VARIABLE}"):
        load_settings_class()()
