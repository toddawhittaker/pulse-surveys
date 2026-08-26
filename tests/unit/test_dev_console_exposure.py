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

**E1-14 adds the method-mismatch pin ADR 0079 left open.** The router is
registered for `GET` unconditionally and only the handler is gated, so a `GET`
outside development is refused by the handler (asserted above) while any other
method is refused by the router itself, before the handler runs — `POST /dev`
answers `405` with `Allow: GET`, measured against the pinned Starlette 1.6.0,
while an unregistered path answers `404` to every method. One unauthenticated
request therefore confirms both that this build ships the console and that
`ENVIRONMENT` is not `development` — the same disclosure this module's `GET`
test asserts, arriving by a second door. ADR 0079's consequences section says
plainly that nothing in the suite asserted this before; `docs/adr/0087-*.md`
is the record that decided the disclosure stays, and these are its pins.

Every test below requests `deployed_identity_provider` (E0-39), for the reason
`tests/unit/test_docs_exposure.py` gives on its own production rows: with
`ENVIRONMENT` set to a deployment's value, `.env.example`'s `mock-idp` addresses are
refused at startup, so `create_app()` would raise inside the setup of a test about
the `/dev` gate. The fixture configures a provider that is not the mock and changes
nothing else; no assertion here moved.
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

# ADR 0079's measured `Allow` header value: one method, spelled exactly this way.
DEV_CONSOLE_ALLOWED_METHOD = "GET"

# A path this application registers nowhere — chosen the way
# `test_healthz.py`'s `UNMISTAKABLE_ENVIRONMENT_NAME` is chosen: a string no
# router in this tree would collide with by accident.
UNREGISTERED_PATH = "/e1-14-unregistered-path-9d2f6b"


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
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
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
    0074). **The route is registered unconditionally and the gate is the
    environment check inside the handler**, which answers 404 outside development
    — ADR 0079, written in E0-42's batch, records that mechanism. So the mutation
    this kills is that check going missing or being written the wrong way round,
    and *not* a conditional registration: this route has none, and a docstring
    naming a mechanism the code does not use sends the next reader looking in the
    wrong place (found by E0-42's security pass).

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


def test_post_to_the_dev_console_answers_405_with_allow_get_outside_development(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E1-14 — pins ADR 0079's measured method mismatch on `/dev`.

    ADR 0079's decision section records this exact measurement against the
    pinned Starlette (1.6.0): the router is included unconditionally and only
    the handler is gated, so a `GET` is refused by the handler (the test above)
    while any other method is refused by the router itself, before the handler
    ever runs — `POST /dev` answers `405` with `Allow: GET`. ADR 0079's
    consequences section says plainly that nothing in the suite asserted
    anything about another method on this route before now; this is that
    assertion.

    **This is a pin of accepted behaviour, not a new gate.** `docs/adr/0087-*.md`
    records E1-14's verdict as "keep": the environment name may be published, so
    the second door standing open at this size is accepted too, and the ADR
    updates ADR 0079's decision-section note to say so. The green below is
    green-now — `POST /dev` already answers `405` — not red-turned-green; what
    this pin buys is a red the moment a change makes it stop, which is
    `docs/MISTAKES.md` entry 2: behaviour shipped with nothing asserting it.

    **Kills:** closing `/dev` by registering it conditionally on the environment
    instead of gating inside the handler — the alternative ADR 0079's decision
    section names and rejects ("register the route only in development, the way
    ADR 0074 removes `/docs`"). Under that mechanism `POST /dev` would answer
    `404`, indistinguishable from an unregistered path, and the status-code
    assertion below fails.

    **Near-miss this must not pass on:** a handler that starts accepting `POST`
    (renders the console, redirects, answers `200`) fails the status-code
    assertion; a `405` that lists more than `GET` in `Allow` (the console added
    a second method without this pin's author noticing) passes the status
    assertion and fails the header one. Both are checked so a near-miss on
    either half is still caught.

    The `/healthz` line is the control `docs/MISTAKES.md` entry 3 asks for: an
    application answering nothing (a `create_app()` that failed halfway) would
    also answer non-200 to `POST /dev`, and this rules that out first, the same
    way the `GET` test above does.
    """
    client = client_for(application_in(PRODUCTION, monkeypatch))

    assert client.get(HEALTHZ_PATH).status_code == 200, (
        f"`GET {HEALTHZ_PATH}` did not answer 200 with `{ENVIRONMENT_VARIABLE}` set to "
        f"{PRODUCTION!r}, so this application is serving nothing and the assertions below would hold "
        "against a system with no routes rather than against the measured method mismatch."
    )

    response = client.post(DEV_CONSOLE_PATH)
    assert response.status_code == 405, (
        f"`POST {DEV_CONSOLE_PATH}` answered {response.status_code} with `{ENVIRONMENT_VARIABLE}` set "
        f"to {PRODUCTION!r}. ADR 0079 measures this as `405`: the router registers the route for `GET` "
        "only, so `POST` is refused by the router before the environment gate inside the handler is "
        f"ever reached. Body begins {response.text[:300]!r}."
    )
    assert response.headers.get("allow") == DEV_CONSOLE_ALLOWED_METHOD, (
        f"`POST {DEV_CONSOLE_PATH}` answered 405 with `Allow: {response.headers.get('allow')!r}`; ADR "
        f"0079 measures `Allow: {DEV_CONSOLE_ALLOWED_METHOD}` exactly, one method, because the route is "
        "registered for `GET` alone."
    )


def test_an_unregistered_path_answers_404_to_get_and_post_outside_development(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E1-14 — the baseline the `405` above is measured against.

    ADR 0079's decision section names three data points together: `GET /dev` →
    `404` (asserted by `test_the_dev_console_is_not_served_outside_development`,
    above), `POST /dev` → `405` with `Allow: GET` (asserted above), and `POST` to
    an unregistered path → `404`. This test pins the third.

    **Why this is not ceremony (`docs/MISTAKES.md` entry 3):** without it, the
    `405` assertion above cannot be told from a defect that answers `405` to
    *everything* unmatched — a global exception handler, a catch-all
    middleware, a `Starlette` refusal wired to the wrong exception type — which
    would leave `test_post_to_the_dev_console_answers_405_with_allow_get_
    outside_development` green while saying nothing about `/dev` specifically.
    This is that assertion's control.

    **Kills:** any change that makes an unmatched method answer something other
    than `404` for a path this application does not register at all — most
    concretely, a blanket `405` responder that would make the `POST /dev` pin
    above pass for a reason unrelated to `/dev`.

    `GET` is checked beside `POST` on the same path for the same reason: a path
    that answers `404` to `POST` and something else to `GET` is not
    "unregistered" — it exists and refuses one method, which is exactly the
    shape `/dev` has, and this control path must not accidentally have grown
    that shape too.
    """
    client = client_for(application_in(PRODUCTION, monkeypatch))

    get_response = client.get(UNREGISTERED_PATH)
    assert get_response.status_code == 404, (
        f"`GET {UNREGISTERED_PATH}` answered {get_response.status_code}, not 404. This path is chosen to "
        "collide with no router in this tree; if it now answers something else, either a route was added "
        "at this exact path or this application's default not-found handling changed under it, and "
        "either way the `POST /dev` pin above is no longer measured against a clean baseline."
    )

    post_response = client.post(UNREGISTERED_PATH)
    assert post_response.status_code == 404, (
        f"`POST {UNREGISTERED_PATH}` answered {post_response.status_code}, not 404. `POST "
        f"{DEV_CONSOLE_PATH}` is pinned at `405` in this module specifically because `/dev` is "
        "registered and this path is not; if an unregistered path also answers something other than "
        "404 to POST, that pin no longer demonstrates anything route-specific."
    )
