"""What `create_app()` raises when configuration is wrong — ticket E0-01.

Criterion 2 says `Settings` "raises at startup when a required variable is
absent". These tests assert the *type* that reaches the caller, from the entry
point the caller actually uses.

The type is not decoration. E0-02 puts `create_app()` behind a Compose entry
point and wraps it so a misconfigured container prints a startup diagnostic
instead of an unhandled traceback, and `except` clauses do not match on
approximately the right exception. The two assertions here are the two halves of
that: the project's own error is what comes out, and pydantic's is not — because
converting every validation failure into a message that names variables without
quoting their values is the whole reason the conversion exists, and an escaping
`ValidationError` carries the input dict with it.

Asserted through `create_app()` rather than `Settings()` directly. Nothing
guarantees the factory does not catch and re-raise, and the factory is what the
caller holds.
"""

from typing import Any

import pytest

# Both shapes of bad configuration, because a conversion can cover one and miss
# the other: a variable that is not set at all, and one set to a value of the
# wrong type. `DATABASE_URL` is fixed by the migration-drift job in
# `.github/workflows/ci.yml`; `N_THRESHOLD_DEFAULT` is this test's spelling,
# matching `tests/unit/test_config_settings.py`.
ABSENT_VARIABLE = "DATABASE_URL"
MALFORMED_VARIABLE = "N_THRESHOLD_DEFAULT"
MALFORMED_VALUE = "not-a-number"

BROKEN_CONFIGURATIONS = ("absent variable", "malformed value")


def break_configuration(monkeypatch: pytest.MonkeyPatch, how: str) -> None:
    """Make the process environment one that `Settings` must refuse."""
    if how == "absent variable":
        monkeypatch.delenv(ABSENT_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(MALFORMED_VARIABLE, MALFORMED_VALUE)


def load_configuration_error() -> type[BaseException]:
    """The error type the application promises its callers."""
    from app.config import ConfigurationError

    return ConfigurationError


def build_app() -> Any:
    """Call the factory inside the test, so a missing module fails one test loudly."""
    from app.main import create_app

    return create_app()


@pytest.mark.parametrize("how", BROKEN_CONFIGURATIONS)
def test_create_app_raises_the_projects_own_configuration_error(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    how: str,
) -> None:
    """Bad configuration reaches the caller as `app.config.ConfigurationError`.

    One type for both shapes of failure. A caller that has to enumerate error
    types to catch a misconfiguration will miss one, and the one it misses is the
    one that kills the container.
    """
    break_configuration(monkeypatch, how)

    with pytest.raises(load_configuration_error()):
        build_app()


@pytest.mark.parametrize("how", BROKEN_CONFIGURATIONS)
def test_create_app_does_not_let_a_pydantic_validation_error_escape(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    how: str,
) -> None:
    """`pydantic.ValidationError` is not part of the startup contract.

    Two things ride on this. The caller's `except` clause is one: catching the
    library's exception type couples E0-02's startup handler to the fact that
    settings happen to be pydantic today. The credential guard is the other — a
    `ValidationError` carries the full input mapping in `errors()`, so one that
    escapes puts every configured value, passwords included, into the startup
    traceback (SPEC §10). Subclassing `ValidationError` would satisfy the first
    reading of this and not the second, so `isinstance` is what is asserted.
    """
    from pydantic import ValidationError

    break_configuration(monkeypatch, how)

    # Catching bare `Exception` is the point: the assertion below is about which
    # type came out, so narrowing the `raises` would decide it in advance.
    with pytest.raises(Exception) as exc_info:
        build_app()

    assert not isinstance(exc_info.value, ValidationError), (
        "create_app() let a pydantic ValidationError reach the caller. It carries "
        "the whole input mapping in errors(), and E0-02 will catch the project's "
        "own error type, not the library's."
    )
