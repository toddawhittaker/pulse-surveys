"""The app factory and `/healthz` — ticket E0-01, acceptance criterion 1.

"`uvicorn app.main:create_app --factory` starts and `GET /healthz` returns 200
with a JSON body naming the environment", carrying service name, version, and
environment.

Exercised in process: `create_app()` is the same callable `--factory` resolves,
and Starlette's `TestClient` runs the app through its lifespan without binding a
port.

The three JSON key spellings below are **this test's choice** — the ticket names
the three values but not the keys. So is `ENVIRONMENT`, the variable the body is
checked against; it is kept identical to the one in
`tests/unit/test_config_settings.py`.

Two tests below request `deployed_identity_provider`, and that is E0-39's repair
round rather than anything E0-01 asks for. `test_healthz_reports_the_environment_it
_was_configured_with` and `test_healthz_does_not_report_an_earlier_apps_cached_
environment` each set an environment name that is deliberately *not*
`development`, which is the whole point of both — and E0-39 refuses `.env.example`'s
`mock-idp` provider anywhere but development, so `create_app()` would raise inside
the setup of a test about what `/healthz` reports. The fixture configures a provider
that is not the mock and changes nothing else; the unmistakable environment names,
and every assertion, are untouched.

`test_healthz_does_not_report_an_earlier_apps_cached_environment` is E1-14's pin
(SPEC's carried entry, `docs/tickets/e1/carried-from-e0.md`): it builds two
applications with two different environments in one process, the exact scenario
ADR 0006 names as the reason `create_app()` builds a fresh `Settings()` per call
with no cache anywhere in the path rather than the `@lru_cache`d dependency
FastAPI's own documentation shows.
"""

from typing import Any

import pytest

SERVICE_KEY = "service"
VERSION_KEY = "version"
ENVIRONMENT_KEY = "environment"

ENVIRONMENT_VARIABLE = "ENVIRONMENT"
HEALTHZ_PATH = "/healthz"

# A value no implementation would arrive at by accident or by hardcoding.
UNMISTAKABLE_ENVIRONMENT_NAME = "e0-01-environment-under-test-7f3c1a"


def build_app() -> Any:
    """Call the factory inside the test, so a missing module fails one test loudly."""
    from app.main import create_app

    return create_app()


def get_healthz() -> Any:
    """`GET /healthz` against a freshly built app, through the lifespan."""
    from fastapi.testclient import TestClient

    with TestClient(build_app()) as client:
        return client.get(HEALTHZ_PATH)


def test_create_app_returns_an_application(configured_env: dict[str, str]) -> None:
    """`app.main:create_app` is a zero-argument factory returning an app to serve."""
    from fastapi import FastAPI

    app = build_app()

    assert isinstance(app, FastAPI)


def test_healthz_returns_200(configured_env: dict[str, str]) -> None:
    """The health endpoint answers 200 on a correctly configured app."""
    response = get_healthz()

    assert response.status_code == 200


def test_healthz_returns_a_json_object(configured_env: dict[str, str]) -> None:
    """The body is a JSON object, which is what the remaining criteria read."""
    response = get_healthz()

    assert response.headers["content-type"].startswith("application/json")
    assert isinstance(response.json(), dict)


def test_healthz_names_the_configured_environment(configured_env: dict[str, str]) -> None:
    """The body names the environment, and names the configured one."""
    expected = configured_env.get(ENVIRONMENT_VARIABLE)
    assert expected, (
        f".env.example does not document {ENVIRONMENT_VARIABLE}; there is no configured "
        "environment name for /healthz to report."
    )

    body = get_healthz().json()

    assert body.get(ENVIRONMENT_KEY) == expected


def test_healthz_reports_the_environment_it_was_configured_with(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reported environment tracks configuration; it is not a constant.

    The previous test passes just as happily against a hardcoded string that
    matches the `.env.example` placeholder. This one sets a value no
    implementation would ever hardcode. The spec does not constrain what an
    environment name may be, so the value is a free string here — asserting an
    enum of `development`/`staging`/`production` would invent an interface.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, UNMISTAKABLE_ENVIRONMENT_NAME)

    body = get_healthz().json()

    assert body.get(ENVIRONMENT_KEY) == UNMISTAKABLE_ENVIRONMENT_NAME


def test_healthz_does_not_report_an_earlier_apps_cached_environment(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E1-14 — `/healthz` reads settings per application, not from a process cache.

    ADR 0006 describes exactly this scenario as the one that forced `Settings()`
    to be built inside `create_app()` with no cache anywhere in the path: "two
    applications with two configurations in one process." It also names the
    idiom that fails it — a zero-argument `@lru_cache`d `get_settings()`
    dependency, the shape FastAPI's own documentation shows — and states what
    was measured: putting that idiom in makes the *second* application report
    the *first* application's environment, silently, with nothing raising.

    **Kills:** any reintroduction of that cache, or any other mechanism that
    resolves `settings.environment` from something keyed on the process rather
    than on the specific `app` a request came in on — a module-level `Settings`
    singleton, a cached reader, a global set once at import.

    **Near-miss this is built to avoid:** the two existing tests above
    (`test_healthz_names_the_configured_environment` and
    `test_healthz_reports_the_environment_it_was_configured_with`) already build
    two applications with two environments **across two test functions**, which
    is the shape ADR 0006 measured against — but relying on that catches the
    mutation only if the test runner happens to execute them in an order where
    the first one populates a process-wide cache before the second reads it.
    This test does not depend on suite ordering: both applications are built and
    queried inside one test, in a fixed sequence, so the mutation is caught
    whether this file runs alone, first, last, or under a randomizing test
    order plugin.

    Sequence matters: `app_a` is queried and fully consumed *before* `app_b` is
    even built, so a cache populated on first use has already been seeded with
    `first_environment` by the time `app_b` asks for its own. Under the
    rejected idiom, `app_b` would report `first_environment` back instead of
    `second_environment`.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    first_environment = "e1-14-first-app-environment-4c19a2"
    second_environment = "e1-14-second-app-environment-9b6e57"
    assert first_environment != second_environment, (
        "this test's two environment names must differ, or both apps below are "
        "configured identically and neither assertion says anything"
    )

    monkeypatch.setenv(ENVIRONMENT_VARIABLE, first_environment)
    with TestClient(create_app()) as client_a:
        body_a = client_a.get(HEALTHZ_PATH).json()

    monkeypatch.setenv(ENVIRONMENT_VARIABLE, second_environment)
    with TestClient(create_app()) as client_b:
        body_b = client_b.get(HEALTHZ_PATH).json()

    assert body_a.get(ENVIRONMENT_KEY) == first_environment, (
        f"the first application reported {body_a.get(ENVIRONMENT_KEY)!r} for "
        f"{ENVIRONMENT_KEY!r}, not {first_environment!r} — it was built with "
        f"`{ENVIRONMENT_VARIABLE}={first_environment!r}` and asked before the second "
        "application existed, so this failing is not yet the cache-sharing defect this "
        "test targets."
    )
    assert body_b.get(ENVIRONMENT_KEY) == second_environment, (
        f"the second application reported {body_b.get(ENVIRONMENT_KEY)!r} for "
        f"{ENVIRONMENT_KEY!r}, not {second_environment!r}, after being built with "
        f"`{ENVIRONMENT_VARIABLE}={second_environment!r}`. If it reported "
        f"{first_environment!r} instead, `/healthz` is answering from a value shared "
        "with the first application rather than reading its own — ADR 0006's rejected "
        "`@lru_cache` idiom, or an equivalent."
    )


def test_healthz_names_the_service(configured_env: dict[str, str]) -> None:
    """The body carries a non-empty service name."""
    body = get_healthz().json()

    assert isinstance(body.get(SERVICE_KEY), str)
    assert body[SERVICE_KEY].strip()


def test_healthz_carries_a_version(configured_env: dict[str, str]) -> None:
    """The body carries a non-empty version string."""
    body = get_healthz().json()

    assert isinstance(body.get(VERSION_KEY), str)
    assert body[VERSION_KEY].strip()
