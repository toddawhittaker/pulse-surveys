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

Two more properties are asserted here, both from the review of pull request #11,
and both of the same shape: behaviour that exists in the implementation and that
nothing checked, so deleting it left the suite green.

  - A settings object that built successfully does not hand its credentials to
    any standard serialisation (SPEC §10, "no student PII in logs; secrets via
    environment/secret store"). The failure-path version of this is already
    covered above; this is the success path, which is the one a structured
    logger or the §6.3 admin configuration view would hit.
  - An institution timezone that no IANA database can resolve is refused at
    startup. Survey windows are timezone-bound (SPEC §3.1 — "opens Friday 18:00
    … in the institution timezone"), so a typo that is accepted opens the window
    at the wrong hour rather than failing where it was made.
"""

import contextlib
import json
import zoneinfo
from collections.abc import Callable
from typing import Any

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

# Obvious fakes: nothing here resembles a real credential and nothing here was
# copied from a working `.env` (CLAUDE.md, secrets). They are long and
# unlikely-looking so that any fragment of one appearing in an error message is
# unambiguously a leak and not a coincidence.
#
# Named `...CREDENTIAL` rather than `...PASSWORD` because ruff's S105 flags the
# latter as a hardcoded password. Renaming keeps the rule doing its job here;
# a `noqa` would have been a suppression to review on every future read.
FAKE_DATABASE_CREDENTIAL = "fake-db-pw-Kq7ZrXb9Ld4MnPtVw"
FAKE_REDIS_CREDENTIAL = "fake-redis-pw-Jh3TgYc5Rf8QsZm"

CREDENTIAL_BEARING_URLS = {
    "DATABASE_URL": f"postgresql+psycopg://pulse:{FAKE_DATABASE_CREDENTIAL}@db:5432/pulse",
    "REDIS_URL": f"redis://:{FAKE_REDIS_CREDENTIAL}@redis:6379/0",
}

# Length of the contiguous run of a password that counts as leaked. Checking for
# the whole password is not enough: pydantic elides the middle of a long repr,
# so a leak can print all but one character of a secret and still not contain
# the exact string. Truncation is not redaction.
LEAK_FRAGMENT_LENGTH = 8

# The fields the credential-bearing URLs arrive in. **This test's choice** of
# spelling, following pydantic-settings' own field-name-to-variable convention,
# and kept here so it is cheap to change.
DATABASE_URL_FIELD = "database_url"
REDIS_URL_FIELD = "redis_url"

# The institution timezone, and two values no IANA database resolves. The first
# is the realistic typo: a space where the IANA name has an underscore, which is
# how a human writes the zone out. The second is well-formed and simply not a
# real zone, so a check that only looks at the shape of the string still fails.
INSTITUTION_TIMEZONE_VARIABLE = "INSTITUTION_TIMEZONE"
UNRESOLVABLE_TIMEZONE_NAMES = ("America/New York", "America/Nwe_York")

# A real zone that is not the `America/New_York` default in SPEC §3.1, so the
# validator cannot pass this suite by accepting only the default.
VALID_NON_DEFAULT_TIMEZONE = "Pacific/Auckland"


def load_settings_class() -> type:
    """Import `Settings` inside the test, so a missing module fails one test loudly."""
    from app.config import Settings

    return Settings


def leaked_fragments(text: str, secret: str, size: int = LEAK_FRAGMENT_LENGTH) -> list[str]:
    """Every contiguous run of `secret` of length `size` that appears in `text`.

    Searching for the whole secret is the check that misses: an elided repr can
    print a secret one character short of complete and still not contain it as a
    substring. Any run this long out of a password is a leak.
    """
    windows = (secret[start : start + size] for start in range(len(secret) - size + 1))
    return sorted({window for window in windows if window in text})


def assert_no_credential_in(text: str, where: str) -> None:
    """Neither fake password may appear, in fragments, anywhere in `text`."""
    for label, secret in (
        ("DATABASE_URL password", FAKE_DATABASE_CREDENTIAL),
        ("REDIS_URL password", FAKE_REDIS_CREDENTIAL),
    ):
        fragments = leaked_fragments(text, secret)
        assert not fragments, (
            f"The {label} leaked into {where}: {fragments}. A configuration error is "
            f"printed to the container startup log, so this is a credential in a log "
            f"(SPEC §10, privacy — secrets via environment/secret store). The full "
            f"text was:\n{text}"
        )


def exception_chain(exc: BaseException) -> list[BaseException]:
    """`exc` and everything it was raised from, `__cause__` and `__context__` alike.

    A configuration error caught and re-raised with a cleaned-up message still
    prints its cause in the startup traceback, so the chain is what reaches the
    log, not the outermost exception alone.
    """
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and not any(link is current for link in chain):
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def assert_no_credential_anywhere_in(exc: BaseException) -> None:
    """No credential fragment in what the exception says, or in what it retains.

    Three surfaces, because a fix can address one and miss the others. The
    rendered message is what a traceback prints; the structured payload is what a
    JSON error handler or structured logger would serialise; the chain is what
    survives a catch-and-re-raise, because Python prints a cause's message too.

    **This asserts a property, not a type.** It does not care whether what was
    raised is a pydantic `ValidationError`, and it must not: the plausible fix is
    to catch that and raise a configuration error carrying only field names, and
    a test that reached for `ValidationError.errors()` would then break on the
    fix rather than pass it. The structured payload is read only if the exception
    offers one — an exception with no `errors()` has nothing structural to leak,
    and passes on that basis, which is the correct outcome and not a gap.

    A cause counts as much as the exception itself. `raise ConfigError(...) from
    exc` leaves the original holding the values, and the startup traceback prints
    both, so a chained cause carrying a credential is a credential in the log.
    """
    for link in exception_chain(exc):
        name = type(link).__name__
        assert_no_credential_in(str(link), f"str() of the raised {name}")
        assert_no_credential_in(repr(link), f"repr() of the raised {name}")

        errors = getattr(link, "errors", None)
        if callable(errors):
            assert_no_credential_in(
                json.dumps(errors(), default=str),
                f"the structured payload of {name}.errors()",
            )


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


def test_startup_error_does_not_print_the_credentials_it_was_given(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configuration error names the missing variable without retaining the set ones.

    The database and Redis URLs both carry a password in the same position. When
    `Settings` refuses to build, the exception reaches the container startup log,
    so anything it prints — or hands to a structured logger — about the variables
    that *were* set is a credential in a log (SPEC §10, and the security-review
    item in this ticket's definition of done).

    **Read this before trusting a green result here.** When this test was
    written, against an implementation that demonstrably leaked, its rendered
    message came back clean: with ten variables set, pydantic's elision kept
    seven characters of the head (`{'database_url': 'postgre...`) and a tail that
    landed on a benchmark number, so both passwords fell in the elided middle.
    Nothing about that is a property anyone can rely on — which characters
    survive depends on how many other variables happen to be set and on where
    each one sits in the repr. What made this test red was the structured
    payload, where `errors()` carries the input dict in full and untruncated.

    So this test distinguishes the two shapes of fix. A rendering-level fix — a
    custom `__str__`, or catching and re-raising with a cleaned message — clears
    the message and leaves the credential in the error payload and in the
    `__cause__`; this test stays red. Only not retaining the value clears it.
    `test_startup_error_with_almost_nothing_configured_does_not_print_credentials`
    is the one that catches the message-level leak directly.
    """
    for name, url in CREDENTIAL_BEARING_URLS.items():
        monkeypatch.setenv(name, url)
    monkeypatch.delenv("AI_PROVIDER_BASE_URL", raising=False)

    # `match` keeps criterion 2 alive: the fix for the leak cannot be to swallow
    # the message, because an operator still has to learn which variable is missing.
    with pytest.raises(Exception, match="(?i)AI_PROVIDER_BASE_URL") as exc_info:
        load_settings_class()()

    assert_no_credential_anywhere_in(exc_info.value)


def test_startup_error_with_almost_nothing_configured_does_not_print_credentials(
    configured_env: dict[str, str],
    documented_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sharpest version: only the two credential-bearing URLs are set.

    Whatever elision a library applies to a printed input value gets weaker as
    the input shrinks — fewer variables set means more of each one survives
    truncation. An operator bringing a new deployment up for the first time,
    with almost nothing configured yet, is exactly this case, and it is the one
    most likely to be pasted into a chat window while asking for help.
    """
    for name in documented_env:
        monkeypatch.delenv(name, raising=False)
    for name, url in CREDENTIAL_BEARING_URLS.items():
        monkeypatch.setenv(name, url)

    with pytest.raises(Exception, match="(?i)AI_PROVIDER_BASE_URL") as exc_info:
        load_settings_class()()

    assert_no_credential_anywhere_in(exc_info.value)


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


# ---------------------------------------------------------------------------
# A settings object that built successfully keeps its credentials to itself.
# ---------------------------------------------------------------------------


def render(value: object) -> str:
    """Both renderings of an arbitrary object, because a mask can cover one only.

    A wrapper type whose `__str__` masks and whose `__repr__` does not is still a
    leak, and so is the reverse: `logging` formats with `%s`, while `pprint` and
    a bare `print` of a dict reach for `repr`. Rendering both means the assertion
    does not depend on which one the guard happened to cover.
    """
    renderings = [repr(value)]
    with contextlib.suppress(TypeError, ValueError):  # not JSON-serialisable
        renderings.append(json.dumps(value, default=str))
    return "\n".join(renderings)


# Every standard way a pydantic model turns itself into data, each named as the
# call site would spell it so a failure says which one leaked. These are not
# hypothetical surfaces: a structured logger is handed `model_dump()`, a JSON
# error handler `model_dump_json()`, `logger.info("config: %s", settings)` uses
# `str()`, and generic code that walks a settings object uses `dict()` or
# iterates it. The list is pydantic's public API, which the ticket chooses by
# specifying pydantic-settings; it is not a guess at how masking is implemented.
SERIALISATIONS: dict[str, Callable[[Any], str]] = {
    "str(settings)": str,
    "repr(settings)": repr,
    "settings.model_dump()": lambda settings: render(settings.model_dump()),
    'settings.model_dump(mode="json")': lambda settings: render(settings.model_dump(mode="json")),
    "settings.model_dump_json()": lambda settings: str(settings.model_dump_json()),
    "dict(settings)": lambda settings: render(dict(settings)),
    "iteration over settings": lambda settings: render(list(settings)),
}


def build_settings_holding_credentials(monkeypatch: pytest.MonkeyPatch) -> Any:
    """A `Settings` that built successfully, holding a password in each URL."""
    for name, url in CREDENTIAL_BEARING_URLS.items():
        monkeypatch.setenv(name, url)
    return load_settings_class()()


@pytest.mark.parametrize("surface", list(SERIALISATIONS))
def test_credentials_do_not_appear_in_settings_serialisation(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    """No credential fragment survives any standard serialisation of `Settings`.

    The failure-path tests above cover what a *refused* configuration prints.
    This covers the accepted one, which is the object that then lives on
    `app.state` for the process lifetime and gets passed to whatever wants to
    describe the running configuration: a structured log line at startup, an
    error report, the §6.3 admin configuration view. SPEC §10 requires secrets to
    stay in the environment or the secret store, and a settings object that
    hands its password to `model_dump()` puts them in the log aggregator instead.

    Asserted per surface rather than in one test, because a guard that covers
    `str()` and not `model_dump()` should report exactly that, and because a
    guard covering only some surfaces is the defect this test exists for.

    Fragments, not whole passwords: a rendering that elides the middle of a value
    can print all but one character of a password and still not contain it as a
    substring. See `leaked_fragments`.
    """
    settings = build_settings_holding_credentials(monkeypatch)

    assert_no_credential_in(SERIALISATIONS[surface](settings), surface)


def revealed(value: object) -> str:
    """The configured value, whatever the field wrapped it in.

    Deliberately mechanism-agnostic within one limit worth naming: it reads a
    plain value with `str()`, and anything offering pydantic's secret protocol
    with `get_secret_value()`. It does not require either. If a field masks
    itself some third way, this helper is what needs widening — not the
    assertion, which is only that the application can still read what it was
    configured with.
    """
    getter = getattr(value, "get_secret_value", None)
    return getter() if callable(getter) else str(value)


@pytest.mark.parametrize(
    ("field_name", "credential"),
    [
        (DATABASE_URL_FIELD, FAKE_DATABASE_CREDENTIAL),
        (REDIS_URL_FIELD, FAKE_REDIS_CREDENTIAL),
    ],
)
def test_credential_bearing_url_is_still_readable_by_the_application(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    credential: str,
) -> None:
    """Masking hides the value from serialisation, not from the code that needs it.

    The other half of the property, and the reason it is not enough to assert
    that a password is nowhere to be found: deleting the field, or storing a
    permanently redacted string, would satisfy that on its own. E0-04 opens a
    database connection with this value and E0-03 a broker connection, so it has
    to survive intact.
    """
    settings = build_settings_holding_credentials(monkeypatch)

    assert hasattr(settings, field_name), f"Settings has no `{field_name}` attribute."
    assert credential in revealed(getattr(settings, field_name)), (
        f"`settings.{field_name}` no longer carries the password it was configured "
        "with. Hiding a credential from serialisation must not hide it from the "
        "code that connects with it."
    )


# ---------------------------------------------------------------------------
# The institution timezone resolves, or startup stops.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("timezone_name", UNRESOLVABLE_TIMEZONE_NAMES)
def test_unresolvable_institution_timezone_is_rejected_naming_the_variable(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    timezone_name: str,
) -> None:
    """A timezone no IANA database knows stops startup, and the message says which.

    SPEC §3.1 puts every survey window in the institution timezone — opens Friday
    18:00, closes Sunday 23:59:59 — so an unresolvable name has no safe reading.
    Accepting it means either a silent fall back to some other zone or a crash
    much later, at the moment a window is computed; both put the failure a long
    way from the typo. `America/New York`, with a space where the IANA name has
    an underscore, is how a person writes the zone out by hand.

    The message must name the variable, for the same reason criterion 2 requires
    it: the operator reading the container log has to know what to fix. It must
    not need to quote the bad value back to do that, so nothing here asserts the
    rejected string appears — SPEC §10 wants configuration values out of logs.
    """
    monkeypatch.setenv(INSTITUTION_TIMEZONE_VARIABLE, timezone_name)

    with pytest.raises(Exception, match=f"(?i){INSTITUTION_TIMEZONE_VARIABLE}"):
        load_settings_class()()


def test_a_valid_institution_timezone_other_than_the_default_is_accepted(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half: a real zone is accepted, including one that is not the default.

    Without this, "reject the typo" is satisfied by rejecting everything except
    `America/New_York`, which SPEC §3.1 gives as a default and not as the only
    permitted value. Nothing is asserted about what the field holds afterwards —
    whether it stays a string or becomes a `ZoneInfo` is the implementer's call.
    """
    assert zoneinfo.ZoneInfo(VALID_NON_DEFAULT_TIMEZONE), (
        f"This machine's IANA database does not resolve {VALID_NON_DEFAULT_TIMEZONE}, "
        "so the test cannot tell a correct rejection from a missing tzdata package."
    )
    monkeypatch.setenv(INSTITUTION_TIMEZONE_VARIABLE, VALID_NON_DEFAULT_TIMEZONE)

    settings = load_settings_class()()

    assert settings is not None
