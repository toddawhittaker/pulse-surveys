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
