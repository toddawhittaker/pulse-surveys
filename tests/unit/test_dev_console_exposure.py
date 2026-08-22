"""Who may reach the developer test console — the dev-only `GET /dev` route.

The test console is a development-only convenience: a page that lists the
web-login people and offers each as a one-click "sign in as this person" link,
so a developer can walk through both entry doors without typing URLs. Because it
is a become-any-user surface, it must be served **only** when `ENVIRONMENT` is
exactly `"development"` — the same gate `backend/app/main.py` puts on `/docs` and
`/openapi.json` (E0-18, ADR 0074), and the same value
`tests/unit/test_docs_exposure.py` keys on.

Named `test_dev_console_exposure.py` to sit beside `test_docs_exposure.py`, the
sibling gate test it is modelled on, and so its basename does not collide with
`tests/integration/test_dev_console.py` — `tests/` has no `__init__.py` and pytest
imports in prepend mode, so two modules sharing a basename fail collection.

This module holds the half of the contract that needs no roster: the gate in the
direction that matters. A `/dev` page enumerating everyone the institution can
sign in as, served to anyone who asks in production, is the single worst way this
feature could ship — so the production refusal is asserted here, airtight and
without a network, exactly the way the docs exposure test asserts its own.

**The development-serves direction lives in
`tests/integration/test_dev_console.py`.** The console fetches the roster from the
mock identity provider over `app.state.http`, so a faithful `200` needs that seam
mounted; a unit test built on a bare `create_app()` would have no roster to fetch
and a "not 404" assertion would pass on a `500`, which asserts nothing
(`docs/MISTAKES.md` entry 2). The two directions are a pair across the two
modules, and each names the other.
"""

from typing import Any

import pytest

ENVIRONMENT_VARIABLE = "ENVIRONMENT"

# The value the console is gated on, exact — not a prefix, not case-folded —
# because `/docs` and `backend/app/db.py` compare it whole and this route shares
# their gate.
DEVELOPMENT = "development"

# A value that is not it, and the one an operator actually sets. Chosen for the
# same reason `tests/unit/test_docs_exposure.py` chose it: a gate that
# special-cased some other spelling would be caught by this direction rather than
# slip through it.
PRODUCTION = "production"

# The route under test, and the liveness route used as the control below.
DEV_CONSOLE_PATH = "/dev"
HEALTHZ_PATH = "/healthz"


def application_in(environment: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    """`create_app()` with `ENVIRONMENT` set to `environment`.

    Built inside the test rather than in a fixture, the way `test_docs_exposure.py`
    builds it, so a missing module or a factory that raises fails one test loudly
    instead of erroring every collection.
    """
    from app.main import create_app

    monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
    return create_app()


def client_for(application: Any) -> Any:
    """A test client on `application`, without running its lifespan.

    The lifespan is deliberately not entered: the production refusal is decided by
    whether the route is registered at all, not by anything a lifespan sets up, and
    entering it would drag in the database and the roster seam this direction does
    not need.
    """
    from fastapi.testclient import TestClient

    return TestClient(application)


@pytest.mark.invariant
def test_the_dev_console_is_not_served_outside_development(
    configured_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """**Dies if the `/dev` gate is dropped or inverted** — the become-any-user guard.

    **Marked `invariant` by E0-41.** Served in production this page walks past §4
    and §6.2 together: whoever asks becomes the Care role, and the Care role is the
    one that can re-identify a student. The gate was already asserted and already
    correct; what it was not was unskippable, and the isolated pass is what makes a
    §4.1 assertion that.

    The development-serves direction stays unmarked in
    `tests/integration/test_dev_console.py`: it asserts a capability rather than a
    denial, and the §4.1 pass is for the denials.

    The console lists every web-login person as a one-click sign-in link. Served in
    production it hands whoever asks a menu of identities to enter the product as,
    so the gate is the whole safety of the feature: `/dev` must 404 anywhere
    `ENVIRONMENT` is not exactly `"development"`, the way `/docs` does (E0-18, ADR
    0074). The mutation this kills is the missing or reversed gate — a route
    registered unconditionally, or one whose condition is written the wrong way
    round.

    The `/healthz` control is what stops this passing on emptiness: an application
    answering 404 to everything — a `create_app()` that failed halfway, a client on
    the wrong object — would satisfy the `/dev` assertion without any gate existing,
    which is `docs/MISTAKES.md` entry 3.
    """
    client = client_for(application_in(PRODUCTION, monkeypatch))

    assert client.get(HEALTHZ_PATH).status_code == 200, (
        f"`GET {HEALTHZ_PATH}` did not answer 200 with `{ENVIRONMENT_VARIABLE}` set to "
        f"{PRODUCTION!r}, so this application is serving nothing and the assertion below would hold "
        "against a system with no routes rather than against a closed gate."
    )

    response = client.get(DEV_CONSOLE_PATH)
    assert response.status_code == 404, (
        f"`GET {DEV_CONSOLE_PATH}` answered {response.status_code} with `{ENVIRONMENT_VARIABLE}` set "
        f"to {PRODUCTION!r}. The developer test console is gated on `{ENVIRONMENT_VARIABLE} == "
        f"{DEVELOPMENT!r}` like `/docs`; outside development it must not exist, because it lists "
        "every web-login identity as a one-click sign-in link. Body begins "
        f"{response.text[:300]!r}."
    )
