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
"""

import inspect
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
