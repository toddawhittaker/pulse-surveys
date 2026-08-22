"""Who may read the OpenAPI schema over HTTP — ticket E0-18.

`create_app()` has always built `FastAPI(...)` without `docs_url` or
`openapi_url`, which serves the interactive documentation and the schema to any
caller. That was harmless while the schema described `/healthz`; E0-18 adds the
first real routes, so the ticket decides it and records the decision in an ADR:
**serve them only when `ENVIRONMENT` is exactly `"development"`** — the same value
`backend/app/db.py` and `scripts/seed.py` already key on.

Three tests, because the property has three halves and each fails differently:

  - development serves them, which is what a developer loses if the gate is
    written the wrong way round;
  - any other value does not, which is the reveal surface §6.2 and §5.5 are about
    — a launched browser enumerating every route of a system that holds student
    comment text;
  - the schema is still *producible* either way, because §7.1 keeps it for the
    future MCP server and §13's client generator calls `app.openapi()`
    in process. A gate that suppressed the schema itself rather than its route
    would satisfy the second test and break both of those, silently, in a script
    nobody runs until E1.

`ENVIRONMENT` is the variable, spelled as `tests/unit/test_config_settings.py` and
`tests/unit/test_healthz.py` spell it. `production` is used as the not-development
value rather than a nonsense string on purpose: it is the one an operator will
actually set, so a gate that special-cased some other name would be caught by the
other direction rather than by this one.
"""

from typing import Any

import pytest

ENVIRONMENT_VARIABLE = "ENVIRONMENT"

# The value E0-18 gates on, exact. Not a prefix and not case-insensitive: the
# ticket says "exactly `development`", and the two places that already key on it
# compare it whole.
DEVELOPMENT = "development"

# A value that is not it, and the one a deployment really carries.
PRODUCTION = "production"

# The two routes FastAPI serves by default. Both are gated together — the
# documentation page is useless without the schema, and the schema is the part
# that enumerates the routes.
DOCS_PATH = "/docs"
OPENAPI_PATH = "/openapi.json"
GATED_PATHS = (DOCS_PATH, OPENAPI_PATH)

# What `/healthz` answers, used as the control below. Without it, "the schema is
# not served" is satisfied by an application that serves nothing at all — which is
# what a `create_app()` raising, or a client pointed at the wrong app, looks like.
HEALTHZ_PATH = "/healthz"


def application_in(environment: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    """`create_app()` with `ENVIRONMENT` set to `environment`.

    Built inside the test rather than in a fixture so that a missing module fails
    one test loudly, the way `tests/unit/test_healthz.py` does it.
    """
    from app.main import create_app

    monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
    return create_app()


def client_for(application: Any) -> Any:
    """A test client on `application`, without running its lifespan.

    Neither route touches anything a lifespan sets up, and not entering it keeps
    this a unit test: nothing here needs a database, a broker or a mock.
    """
    from fastapi.testclient import TestClient

    return TestClient(application)


def test_the_schema_and_its_documentation_are_served_in_development(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Dies if the gate is inverted**, or written against the wrong value.

    This half is the cheap one to get wrong and the expensive one to notice: a gate
    that closed in development takes `/docs` away from every developer, and the
    only symptom is a 404 that reads like a route that was never added.
    """
    client = client_for(application_in(DEVELOPMENT, monkeypatch))

    for path in GATED_PATHS:
        response = client.get(path)
        assert response.status_code == 200, (
            f"`GET {path}` answered {response.status_code} with `{ENVIRONMENT_VARIABLE}` set to "
            f"{DEVELOPMENT!r}. E0-18's decision is to serve the documentation and the schema in "
            "development and nowhere else; a gate that closes here is the decision inverted."
        )


@pytest.mark.invariant
def test_the_schema_and_its_documentation_are_not_served_outside_development(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Dies if the gate is dropped**, which is the state of `main` today.

    **Marked `invariant` by E0-41, and it is the one of the three that is.** This
    is the direction §6.2 and §5.5 are about: a launched browser reading the whole
    route list of a system that holds student comment text, including the reveal
    surface. The other two tests here assert that the schema is *served* in
    development and *producible* in process — capabilities, not denials — and the
    isolated §4.1 pass is for the denials, so marking them would put a developer
    convenience behind a gate CLAUDE.md says may never be skipped.

    `create_app()` builds `FastAPI(...)` with neither `docs_url` nor `openapi_url`
    passed, so both are served to anyone who asks. E0-18 adds the first routes worth
    enumerating, and §6.2's reveal surface plus §5.5's roll-ups are what a route
    list points at.

    The `/healthz` control is what stops this passing on emptiness: an application
    that answered 404 to everything — a `create_app()` that failed halfway, a client
    on the wrong object — would satisfy the two assertions below without the gate
    existing at all, which is `docs/MISTAKES.md` entry 3.
    """
    client = client_for(application_in(PRODUCTION, monkeypatch))

    assert client.get(HEALTHZ_PATH).status_code == 200, (
        f"`GET {HEALTHZ_PATH}` does not answer 200 with `{ENVIRONMENT_VARIABLE}` set to "
        f"{PRODUCTION!r}, so this application is not serving anything and the two assertions "
        "below would hold against a system with no routes rather than against a closed gate."
    )
    for path in GATED_PATHS:
        response = client.get(path)
        assert response.status_code == 404, (
            f"`GET {path}` answered {response.status_code} with `{ENVIRONMENT_VARIABLE}` set to "
            f"{PRODUCTION!r}. E0-18 gates both on `{ENVIRONMENT_VARIABLE} == {DEVELOPMENT!r}`: "
            "outside development the schema hands a launched browser the whole route list of a "
            "system holding student comment text."
        )


def test_the_schema_is_still_produced_in_process_outside_development(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Dies if the gate suppresses the schema rather than the route that serves it.**

    The difference is invisible from HTTP — both spellings answer 404 — and it is
    the whole of what E0-18 means by "the schema stays *producible* either way".
    SPEC §7.1 keeps it for the future MCP server and §13's client generator calls
    `app.openapi()` in process; a `create_app()` that stopped building one breaks
    both, and the failure arrives in a script rather than in a request.

    The non-emptiness guard is the point of the second assertion: `{}` and
    `{"openapi": "3.1.0", "paths": {}}` are both dictionaries, and a schema
    describing no routes is the same defect wearing a passing type check.
    """
    application = application_in(PRODUCTION, monkeypatch)

    schema = application.openapi()

    assert isinstance(schema, dict), (
        f"`app.openapi()` returned {type(schema).__name__} rather than a dict outside "
        "development. E0-18 gates the *route*, not the generation."
    )
    assert schema.get("paths"), (
        f"`app.openapi()` describes no paths outside development (it carries {sorted(schema)}). "
        "A schema with nothing in it satisfies every type check and is useless to the MCP server "
        "§7.1 keeps it for and to the client generator §13 names."
    )
