"""A process that was never given the Care credential refuses out loud — E0-10, PR #29.

`CARE_DATABASE_URL` is optional in `Settings` as of the fix on pull request #29,
and *absent is an ordinary state* rather than a misconfiguration:
`docker-compose.yml` hands it to `api` and blanks it on `worker` and `beat`,
because `pulse_care` is the only credential in the cluster that can execute
`public.reveal_student_identity` and those two processes never serve the §6.2
queue. ADR 0042 records that reversal and what it costs — the failure moved from
start-up to first use, deliberately.

That trade is only sound if a reveal attempted in one of those two processes says
what is wrong. Measured, a `None` reaching `create_engine` answers
`ArgumentError: Expected string or URL object, got None`, which names neither the
variable nor the reason and reads as a bug in the service rather than as a
request that reached the wrong process. So the refusal is its own exception,
raised before an engine is built, and this module holds it.

**Both spellings of absent, because Compose withholds by blanking.** `env_file:
- .env` has already delivered the real value by the time a service's own
`environment:` block applies, so an empty value is what removes it and an omitted
entry leaves it in place. A `SecretStr('')` that validated would leave `worker`
and `beat` looking configured and fail one layer down, in the message this
exception exists to replace. Whitespace-only is the third row and it is not
pedantry: a blanking line reformatted by hand or by a YAML tool is how an empty
value acquires a space, and `'' != ' '` to every check that does not strip.

**And the other direction, because "always refuses" passes the first test.** The
Care path is a requirement of E0-10 rather than an oversight, so a configured
process is asserted to get its engine. `create_engine` opens no socket, so that
costs no database here; what the engine can *do* once opened is asserted against
a real Postgres in `tests/integration/test_care_service_reveal.py` and
`tests/integration/test_identity_grants.py`.

Nothing here pins the wording of the message. It has to name the variable,
because that is what an operator reading a container log greps for; the rest of
the sentence — which process should hold it, and not to fix it by setting it
locally — is prose that should stay improvable.

**A second subject, added by the security review of Batch H: what this engine may
say out loud.** E0-37 item 1 gave `app.db`'s engine `hide_parameters=True`
outside development, because with `sqlalchemy.engine` configured at INFO by name
— which a `dictConfig` plausibly does — `echo=False` writes every statement and
every bound parameter. The Care engine was built beside it with `pool_pre_ping`
alone and got none of that, so the two connections in this cluster disagreed
about whether the values of a statement may be written down. Measured on the
fix's own branch: the main engine hid its parameters and this one logged them.

**It is the sharper of the two, which is why it is not merely consistency.** The
parameters crossing this connection are the arguments to
`public.reveal_student_identity` and the rows coming back are the identity itself
— the one thing SPEC §4.1's views and grants exist to keep apart from a response,
handed to a log stream a deployment ships elsewhere (§6.2, §10). So this engine
takes its options from the same function the main one does, and the two tests
below say so: one absolutely, outside development, and one as an agreement, so
that the two engines cannot drift apart without something going red.

**One fixture below is E0-39's repair round rather than this module's subject.**
The three non-development rows build a `Settings` with `.env.example`'s values in
place, and that ticket refuses its `mock-idp` addresses outside development — so the
row would stop in its own setup, on a rule about an identity provider, in a test
about what a database connection writes to a log. `deployed_identity_provider`
configures a provider that is not the mock and changes nothing else. No assertion
here moved.

**What is asserted here and what is asserted in `test_db_engine_configuration.py`.**
That module owns what the options *mean* — it builds a SQLite engine from them,
runs a statement carrying a marker, and reads the captured log. This one owns
whether they reach the engine `app.services.safety` actually builds, which is a
question no log capture can answer here: the Care engine points at Postgres and a
unit test has no server. Both halves, because the flag test cannot see whether
hiding works and the capture test cannot see whether this engine got it.
"""

import inspect
import sys
import uuid
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

# The module E0-10 names for the Care queue, and SPEC §13 before it.
CARE_SERVICE_MODULE = "app.services.safety"

# The variable the refusal has to name. `.env.example` documents it and says it
# is "read by `app.services.safety` and by nothing else".
CARE_DATABASE_URL_VARIABLE = "CARE_DATABASE_URL"

# **Private symbols, named here deliberately.** ADR 0042 makes the Care pool
# private — there is no public factory, and
# `tests/unit/test_care_session_is_bound_to_the_care_service.py` asserts there
# must not be one — so the engine builder is the only place this refusal can be
# reached without a database. Naming it is the cost of that decision rather than
# a reach past it, and a rename is these two lines.
CARE_ENGINE_BUILDER = "_care_engine"
CARE_REFUSAL = "CareQueueNotConfiguredError"

# The public entry point ADR 0042 gives E10: "`reveal_identity` takes the acting
# person, the subject and an optional case id".
REVEAL = "reveal_identity"

# Absent, empty, and whitespace-only — the three ways a process ends up without
# the credential. The first is a deployment that never set it; the second is what
# `docker-compose.yml` writes; the third is what a formatter makes of the second.
WITHHELD_SPELLINGS = (None, "", "   ")

# An obvious fake: nothing here resembles a real credential and nothing here was
# copied from a working `.env` (CLAUDE.md, secrets). Named `...CREDENTIAL` rather
# than `...PASSWORD` because ruff's S105 flags the latter as a hardcoded
# password; `tests/unit/test_config_settings.py` made the same choice.
FAKE_CARE_CREDENTIAL = "fake-care-pw-Ht6WvNc2Xq9Lb"
CONFIGURED_CARE_URL = f"postgresql+psycopg://pulse_care:{FAKE_CARE_CREDENTIAL}@db:5432/pulse"

# Where the engine options come from, and the name of the function that answers
# them. The contract is that `app.services.safety` builds its engine with
# `**engine_options(settings)` — the same call `app.db` makes — so that there is
# one place deciding what either connection may write down.
DB_MODULE = "app.db"
ENGINE_OPTIONS_FUNCTION = "engine_options"

ENVIRONMENT_VARIABLE = "ENVIRONMENT"
LOG_LEVEL_VARIABLE = "LOG_LEVEL"

# The name of the constant that says which environment is the development one,
# read out of `app.config` rather than spelled here — E0-37 item 2 makes that the
# single definition site.
CONFIG_MODULE = "app.config"
DEVELOPMENT_ENVIRONMENT_CONSTANT = "DEVELOPMENT_ENVIRONMENT"

# Environments that are not development, each paired with a log level. **A copy
# of the table in `tests/unit/test_db_engine_configuration.py`**, and the reason
# it is copied rather than shared is the reason it exists at all: the two
# plausible one-line derivations of these options fail on different rows —
# `settings.environment != "production"` passes the first row and leaks in
# staging, `settings.log_level == "DEBUG"` passes the staging rows and leaks in a
# production deployment turned up to debug a problem, which is exactly when it is
# most likely to be turned up. A module that asserted only one row would be
# satisfied by either.
NON_DEVELOPMENT_ENVIRONMENTS = (
    ("production", "INFO"),
    ("production", "DEBUG"),
    ("staging", "DEBUG"),
)


def care_service(import_app_module: Callable[[str], ModuleType | None]) -> ModuleType:
    """Import the Care service against the environment the test has just set.

    Through `import_app_module` rather than a plain `import`, and that is what
    makes each test below about the configuration rather than about test order.
    The fixture drops every `app.*` module from `sys.modules` first, so the
    engine builder is reached with whatever it caches emptied — without assuming
    anything about *how* it caches, which is a construction choice ADR 0042
    leaves to the implementation.
    """
    module = import_app_module(CARE_SERVICE_MODULE)
    if module is None:
        pytest.fail(
            f"There is no `{CARE_SERVICE_MODULE}` module. E0-10 names it — 'The Care service "
            "module is `backend/app/services/safety.py`, which SPEC §13 already names for the "
            "Care queue' — and it is where the second connection pool is opened."
        )
    return module


def symbol(module: ModuleType, name: str, why: str) -> Any:
    """One attribute of the Care service, or a failure naming what is missing."""
    found = getattr(module, name, None)
    if found is None:
        pytest.fail(
            f"`{CARE_SERVICE_MODULE}` has no `{name}`. {why} It defines " f"{sorted(vars(module))}."
        )
    return found


def withhold(monkeypatch: pytest.MonkeyPatch, spelling: str | None) -> None:
    """Put the process in the state `worker` and `beat` start in."""
    if spelling is None:
        monkeypatch.delenv(CARE_DATABASE_URL_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(CARE_DATABASE_URL_VARIABLE, spelling)


def care_engine(
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
) -> Any:
    """The engine `app.services.safety` builds for a process that holds the credential."""
    monkeypatch.setenv(CARE_DATABASE_URL_VARIABLE, CONFIGURED_CARE_URL)

    module = care_service(import_app_module)
    build_engine = symbol(
        module,
        CARE_ENGINE_BUILDER,
        "It is where the Care connection pool is opened on first use, so it is where the "
        "options that decide what this connection may write to a log are applied.",
    )
    return build_engine()


def hidden_parameters_of(engine: Any) -> Any:
    """Whether this engine hides bound parameters, wherever SQLAlchemy keeps that flag.

    Read off the engine or off its dialect, because which of the two holds it is
    a detail of the library rather than of this project, and a test that guessed
    one would report a version change as a defect in the Care service. `None`
    means neither has it, which the caller reports as this module needing an
    update rather than as a finding.

    **A copy of the helper in `tests/unit/test_db_engine_configuration.py`**, and
    a deliberate one: importing a test module out of another test module is not
    how anything else in this suite shares a helper, and the two questions are
    about two different engines in two different tickets. If SQLAlchemy moves the
    flag, both copies need the same edit and both say so.
    """
    for holder in (engine, getattr(engine, "dialect", None)):
        if holder is None:
            continue
        found = getattr(holder, "hide_parameters", None)
        if found is not None:
            return found
    return None


def engine_options_for(
    import_app_module: Callable[[str], ModuleType | None],
) -> dict[str, Any]:
    """What `app.db.engine_options` answers for the environment the test has just set.

    Imported through the fixture rather than at module scope, and after the Care
    service, so that both modules are read against one environment and a missing
    deliverable arrives as a failed assertion naming it.
    """
    module = import_app_module(DB_MODULE)
    if module is None:
        pytest.fail(
            f"`{DB_MODULE}` does not exist, so there is nothing for `{CARE_SERVICE_MODULE}` to "
            "take its engine options from. E0-04 ships it and E0-37 item 1 adds "
            f"`{ENGINE_OPTIONS_FUNCTION}` to it."
        )
    build_options = getattr(module, ENGINE_OPTIONS_FUNCTION, None)
    assert callable(build_options), (
        f"`{DB_MODULE}` exposes no callable `{ENGINE_OPTIONS_FUNCTION}` (it has "
        f"{sorted(vars(module))}).\n"
        f"  {ENGINE_OPTIONS_FUNCTION}(settings) answers the `create_engine` keyword arguments "
        "both engines are built with, and outside development they include "
        "`hide_parameters=True`.\n"
        "\n"
        "E0-37 item 1 adds it; the security review of that batch is what asks this module to "
        "read it, because the Care engine was built with `pool_pre_ping` alone and got none of it."
    )

    config = import_app_module(CONFIG_MODULE)
    if config is None:
        pytest.fail(f"`{CONFIG_MODULE}` does not exist, so no `Settings` can be built.")
    settings_class = getattr(config, "Settings", None)
    assert settings_class is not None, (
        f"`{CONFIG_MODULE}` exposes no `Settings`, so there is nothing to hand "
        f"`{ENGINE_OPTIONS_FUNCTION}`."
    )
    return dict(build_options(settings_class()))


def forget_the_app_package() -> None:
    """Drop every `app.*` module, so the next import reads the environment set now.

    `import_app_module` does exactly this once, before the test body runs. One
    test below has to look a constant up in `app.config` in order to know which
    environment to set, and then import the Care service against it — and a
    module that built something out of `Settings` at its first import would
    otherwise answer for the environment that was in force when the constant was
    read.

    **A copy of the helper in `tests/unit/test_db_engine_configuration.py`**,
    which needs it for the same reason and names this one in return. If a third
    module wants it, it belongs beside `import_app_module` in `tests/conftest.py`
    rather than in a third copy (`docs/MISTAKES.md` entry 13).
    """
    for name in [n for n in list(sys.modules) if n == "app" or n.startswith("app.")]:
        sys.modules.pop(name, None)


def development_environment_name(import_app_module: Callable[[str], ModuleType | None]) -> str:
    """The value of `ENVIRONMENT` that means development, read from its one definition."""
    config = import_app_module(CONFIG_MODULE)
    if config is None:
        pytest.fail(f"`{CONFIG_MODULE}` does not exist.")
    name = getattr(config, DEVELOPMENT_ENVIRONMENT_CONSTANT, None)
    assert isinstance(name, str) and name, (
        f"`{CONFIG_MODULE}` exposes no `{DEVELOPMENT_ENVIRONMENT_CONSTANT}` string. E0-37 item 2 "
        "makes it the single definition site, and a literal here would be one more copy of the "
        "value that item exists to remove."
    )
    return name


@pytest.mark.parametrize("spelling", WITHHELD_SPELLINGS)
def test_the_care_engine_refuses_a_process_without_the_credential_naming_the_variable(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
    spelling: str | None,
) -> None:
    """A reveal attempted in `worker` or `beat` fails with something an operator can act on.

    The exception type is asserted, not merely that something was raised, and
    that is the whole of what distinguishes this from the state before the fix:
    `create_engine(None)` raises too, with `ArgumentError: Expected string or URL
    object, got None`, and an operator reading that in a container log learns
    neither which variable decides this nor that the request reached a process
    that is not meant to serve the Care queue.

    Three rows rather than one, because two different guards have to hold and a
    single row cannot tell them apart. Deleting the absence check in the engine
    builder reddens every row; deleting the validator in `app.config` that reads
    a blank value as absent reddens the second and third only, which is the point
    of parametrising — Compose withholds this credential by blanking it, so the
    empty string is the spelling that actually ships.

    The variable name is asserted case-insensitively and nothing else about the
    message is. An operator greps for `CARE_DATABASE_URL`; whether the sentence
    around it says "only the API process serves the Care queue" today is prose
    that should stay improvable, and a test that pinned it would make it
    unchangeable (`docs/MISTAKES.md` entry 19's neighbour — a test holding a copy
    of what it checks).
    """
    withhold(monkeypatch, spelling)

    module = care_service(import_app_module)
    refusal = symbol(
        module,
        CARE_REFUSAL,
        "It is the error a process that was never given `CARE_DATABASE_URL` raises when "
        "something asks it to serve the Care queue (ADR 0042, as amended by E0-10).",
    )
    build_engine = symbol(
        module,
        CARE_ENGINE_BUILDER,
        "It is where the Care connection pool is opened on first use, and where the refusal "
        "has to happen — before anything is built with a value that is not there.",
    )

    with pytest.raises(refusal) as refused:
        build_engine()

    message = str(refused.value)
    assert CARE_DATABASE_URL_VARIABLE.lower() in message.lower(), (
        f"The refusal does not name {CARE_DATABASE_URL_VARIABLE}: {message!r}. An operator "
        "reading a container log has to learn which variable decides this and which process "
        "is meant to hold it — otherwise the message is only a better-typed version of the "
        "`ArgumentError` it replaced."
    )


def test_a_process_that_was_given_the_care_credential_still_gets_its_engine(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """The other half: refusing an absent credential must not refuse a present one.

    Without this, every assertion above is satisfied by an engine builder that
    raises unconditionally — which closes the Care path altogether, and E0-10
    calls that path "a requirement, not an oversight… this test is what stops a
    later change from silently closing it". §6.2's queue being quietly
    unavailable is also the cost ADR 0042 weighed the whole reversal against.

    `create_engine` opens no socket, so this needs no Postgres: what is asserted
    is that the builder produced an engine pointed at what it was configured
    with, not that anything can be done over it. The privileges that connection
    holds are asserted against a real server in
    `tests/integration/test_identity_grants.py`.

    The password is checked as well as the type, because an engine built against
    some other URL would satisfy `isinstance` while connecting somewhere this
    test never configured — the guard
    `tests/unit/test_db_engine_configuration.py` puts in front of its own leak
    assertion, for the same reason.
    """
    from sqlalchemy.engine import Engine

    monkeypatch.setenv(CARE_DATABASE_URL_VARIABLE, CONFIGURED_CARE_URL)

    module = care_service(import_app_module)
    build_engine = symbol(
        module,
        CARE_ENGINE_BUILDER,
        "It is where the Care connection pool is opened on first use.",
    )

    engine = build_engine()

    assert isinstance(engine, Engine), (
        f"`{CARE_SERVICE_MODULE}.{CARE_ENGINE_BUILDER}()` returned {engine!r} rather than a "
        "SQLAlchemy engine, so the assertions above are about a refusal with nothing on the "
        "other side of it. E0-10 asks for two runtime connection pools, the second of them on "
        "`pulse_care`."
    )
    configured = engine.url.password
    revealed = (
        configured.get_secret_value() if hasattr(configured, "get_secret_value") else configured
    )
    assert revealed == FAKE_CARE_CREDENTIAL, (
        f"The Care engine was built with the password {revealed!r}, not the one this test put "
        f"in {CARE_DATABASE_URL_VARIABLE}. It is pointed somewhere else, so a green result "
        "here says nothing about the connection the Care queue actually opens."
    )


def test_a_reveal_in_a_process_without_the_credential_refuses_naming_the_variable(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """The refusal reaches the caller, rather than being turned into another answer.

    The tests above are about the engine builder. This is about the door: a
    reveal requested in `worker` or `beat` — a routing mistake, or a task that
    should have been an API call — has to come back saying the process was never
    configured for this. The failure worth guarding against is not that nothing
    is raised but that something *else* is: a `try`/`except` around the pool that
    answered `NotCareStaffError` would tell a Care staffer they hold no
    assignment when what actually happened is that their request reached the
    wrong container, and §6.2 needs "refused" and "misconfigured" to be different
    answers for the same reason it needs "refused" and "no such student" to be.

    The call is assembled from the signature rather than written out, because
    E0-10 does not spell one — ADR 0042 says only that `reveal_identity` "takes
    the acting person, the subject and an optional case id". Every required
    parameter is handed a UUID, which is what a person key is in this schema; the
    optional ones are left alone. If a required parameter arrives that a UUID
    cannot stand in for, that is an interface question for the ticket rather than
    something to guess at here, and the failure will name the parameter.

    Nothing about argument validity should decide this: the actor's assignment is
    checked over the Care connection (ADR 0042's third consequence), so there is
    no connection to check it over and the configuration is the first thing that
    can be wrong.
    """
    withhold(monkeypatch, None)

    module = care_service(import_app_module)
    refusal = symbol(
        module,
        CARE_REFUSAL,
        "It is the error a process without `CARE_DATABASE_URL` raises when asked to serve the "
        "Care queue.",
    )
    reveal = symbol(
        module,
        REVEAL,
        "ADR 0042: 'E10 inherits an interface, not a queue. `reveal_identity` takes the acting "
        "person, the subject and an optional case id'.",
    )

    parameters = [
        parameter
        for parameter in inspect.signature(reveal).parameters.values()
        if parameter.default is parameter.empty
        and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]
    positional = [
        uuid.uuid4() for parameter in parameters if parameter.kind is not parameter.KEYWORD_ONLY
    ]
    keywords = {
        parameter.name: uuid.uuid4()
        for parameter in parameters
        if parameter.kind is parameter.KEYWORD_ONLY
    }

    with pytest.raises(refusal) as refused:
        reveal(*positional, **keywords)

    message = str(refused.value)
    assert CARE_DATABASE_URL_VARIABLE.lower() in message.lower(), (
        f"A reveal in a process without the credential raised the right type without naming "
        f"{CARE_DATABASE_URL_VARIABLE}: {message!r}. The container log is where this is read, "
        "and the variable is what the operator has to find."
    )


# ---------------------------------------------------------------------------
# What this connection may say out loud. Added by the security review of Batch H
# (E0-37); the module docstring says why it is the sharper of the two engines.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("environment", "log_level"), NON_DEVELOPMENT_ENVIRONMENTS)
def test_the_care_engine_hides_its_bound_parameters_outside_development(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
    environment: str,
    log_level: str,
) -> None:
    """The Care connection gets the same protection the main one got in E0-37 item 1.

    That item measured the hole and closed it on `app.db`: with
    `sqlalchemy.engine` configured at INFO **by name**, `Connection.__init__`
    reads `logger.isEnabledFor(INFO)` rather than the `echo` flag, so every
    statement and every bound parameter is written whatever `echo` says.
    `hide_parameters=True` outside development is what closes it. The Care engine
    was built beside it with `pool_pre_ping` alone, so the fix reached one of the
    two connections in this cluster and the review found the other still logging.

    **The parameters on this connection are the ones §4.1 exists for.** What
    crosses it is the reveal — the arguments to
    `public.reveal_student_identity`, and the identity coming back (§6.2). A
    deployment ships its logs somewhere; that is the one place the views and
    grants do not reach, and it is why this is a finding rather than an
    inconsistency.

    Read off the engine the module actually builds, not off the options: an
    `engine_options` that answers correctly and is not used here leaves the hole
    exactly where it was (`docs/MISTAKES.md` entry 23 — a validation that creates
    the appearance of a behaviour). What the flag *means* is asserted in
    `tests/unit/test_db_engine_configuration.py`, against a captured log; this
    engine points at Postgres, so no capture is possible in a unit test.

    Three rows for the reason the constant above gives — the two obvious
    one-line derivations each pass some of them and fail others.

    **The mutation this survives:** build the Care engine with `pool_pre_ping`
    alone, which is how it was written. **The near miss that must stay green:**
    any route to the same flags — `**engine_options(settings)`, or a call that
    adds more of them — since the engine is read rather than the call.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
    monkeypatch.setenv(LOG_LEVEL_VARIABLE, log_level)

    engine = care_engine(monkeypatch, import_app_module)

    hidden = hidden_parameters_of(engine)
    assert hidden is not None, (
        "Neither the Care engine nor its dialect carries a `hide_parameters` flag, so this test "
        "cannot read the property it is about. That is this module needing an update for the "
        "SQLAlchemy in `requirements.txt` — a broken test rather than a finding."
    )
    assert hidden is True, (
        f"The Care engine built with {ENVIRONMENT_VARIABLE}={environment!r} and "
        f"{LOG_LEVEL_VARIABLE}={log_level!r} does not hide its bound parameters "
        f"(`hide_parameters` is {hidden!r}).\n"
        "\n"
        "With `sqlalchemy.engine` configured at INFO by name — which a `dictConfig` plausibly "
        "does — every statement and every bound parameter on this connection is written to the "
        "log. The parameters here are a reveal's arguments and the rows are the identity it "
        "returns (SPEC §6.2, §10), which is the material §4.1's views and grants exist to keep "
        "out of a response and cannot reach a log stream at all.\n"
        "\n"
        f"E0-37 item 1 gave `{DB_MODULE}`'s engine this. The contract is that this module builds "
        f"its engine with `**{ENGINE_OPTIONS_FUNCTION}(settings)` from `{DB_MODULE}`, so that one "
        "function decides what either connection may write down."
    )
    assert not engine.echo, (
        f"The Care engine echoes SQL with {ENVIRONMENT_VARIABLE}={environment!r} and "
        f"{LOG_LEVEL_VARIABLE}={log_level!r}. Every statement on the one connection that can "
        "execute a reveal goes to the log. This is the same criterion E0-04 set for the main "
        "engine, and the same smaller one: the parameters are the assertion above."
    )


def test_the_care_engine_and_the_main_engine_are_configured_by_one_function(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """In development the two engines agree, which is what stops them drifting apart again.

    **An agreement rather than an absolute, and the difference is the point.**
    The test above says what must be true outside development, where the answer
    is settled. Here the assertion is that this engine's parameter handling is
    whatever `app.db.engine_options` says for the same settings — so a Care
    engine that hid parameters unconditionally, or one that stopped calling that
    function and hardcoded something of its own, is red even though its own
    behaviour looks safe.

    That is deliberate. The finding was not "this engine has the wrong flag", it
    was "this engine is configured somewhere else" — and a fix that copies the
    right flags into `safety.py` by hand passes the test above and reintroduces
    the finding the next time `engine_options` changes.

    **This file does not require a parameter to be visible in development**, and
    it must not: `tests/unit/test_db_engine_configuration.py` gives the reason —
    an implementation that never shows one satisfies every ticket here, and
    requiring the other direction would invent a feature nobody asked for. What
    is required is only that the two engines answer the same.

    **This passes on the tree as it stands**, since neither engine hides anything
    in development today. It is a guard, and its whole value is under the
    mutation below.

    **The mutation this survives:** `hide_parameters=True` written into
    `safety.py` directly instead of taken from `engine_options`. **The near miss
    that must stay green:** `engine_options` itself changing what it answers in
    development, since both sides move together.
    """
    development = development_environment_name(import_app_module)
    forget_the_app_package()
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, development)

    engine = care_engine(monkeypatch, import_app_module)
    options = engine_options_for(import_app_module)

    assert "hide_parameters" in options, (
        f"`{DB_MODULE}.{ENGINE_OPTIONS_FUNCTION}` answered {options!r}, which says nothing about "
        "`hide_parameters`, so there is no agreement here to assert. The test above is what says "
        "what the answer has to be outside development."
    )

    expected = options["hide_parameters"]
    hidden = hidden_parameters_of(engine)
    assert hidden == expected, (
        f"With {ENVIRONMENT_VARIABLE}={development!r} the Care engine hides parameters "
        f"({hidden!r}) and `{DB_MODULE}.{ENGINE_OPTIONS_FUNCTION}` says {expected!r}.\n"
        f"  options: {options!r}\n"
        "\n"
        "The two connections in this cluster are supposed to be configured by one function. The "
        "security review of E0-37 found them configured in two places — the main engine had item "
        "1's options and this one had `pool_pre_ping` alone — and this assertion is what makes "
        "that state red rather than invisible.\n"
        "\n"
        "Note which direction this fails in. A Care engine that hides *more* than the main one is "
        "red here too, and deliberately: it means this module has stopped reading "
        f"`{ENGINE_OPTIONS_FUNCTION}` and has its own copy of the decision, which is the finding "
        "arriving again by a slower route."
    )
