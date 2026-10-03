"""A deployment refuses a session secret anyone could know (SPEC §7.3, ADR 0089).

`SESSION_SECRET` signs every session JWT, so a deployment started from the
placeholder `.env.example` ships signs sessions with a value readable in this
repository. Outside development `Settings` refuses that placeholder, an empty
value, and anything shorter than 32 characters, and the refusal names the
variable without quoting the value.

**The check is skipped when `ENVIRONMENT=development`.** `.env.example` ships
`ENVIRONMENT=development`, so an unedited copy of that file skips it. Changing
that default is carried to the hardening epic, because CI copies the file as it
is. The development pair at the foot of this module is what states the limit.

The placeholder is read from `.env.example` at test time, never from a copy, so
a placeholder changed in the file and not in `app.config` fails here.
"""

import secrets

import pytest
from fixtures.doors import DEPLOYED_IDENTITY_PROVIDER
from fixtures.mock_ai import DEPLOYED_AI_PROVIDER

DEPLOYMENTS = ("production", "staging")

# Distinctive enough that finding it in an error's text can only mean it leaked.
THIRTY_ONE_CHARACTERS = "q7Zx-short-secret-K3vW9pLm2Rt8n"
THIRTY_TWO_CHARACTERS = "q7Zx-long-enough-secret-K3vW9pLm"


def placeholder_from(documented_env: dict[str, str]) -> str:
    """The `SESSION_SECRET` value `.env.example` ships, with a guard on its length.

    The guard is not ceremony: a placeholder shorter than 32 characters would be
    refused by the length rule alone, and the placeholder tests would pass with
    the equality check deleted.
    """
    placeholder = documented_env.get("SESSION_SECRET", "")
    assert len(placeholder) >= 32, (
        "`.env.example`'s SESSION_SECRET is shorter than 32 characters, so a test "
        "refusing it could not tell the placeholder check from the length check."
    )
    return placeholder


@pytest.fixture
def deployment_settings(
    monkeypatch: pytest.MonkeyPatch,
    configured_env: dict[str, str],
    request: pytest.FixtureRequest,
) -> object:
    """Every setting deployment-valid except `SESSION_SECRET`, which each test sets.

    The provider values are set here rather than through the shared deployment
    fixtures, because those now set a valid session secret and this module is
    about the one they set.
    """
    monkeypatch.setenv("ENVIRONMENT", request.param)
    for name, value in {**DEPLOYED_IDENTITY_PROVIDER, **DEPLOYED_AI_PROVIDER}.items():
        monkeypatch.setenv(name, value)
    from app.config import Settings

    return Settings


def refusal_with(monkeypatch: pytest.MonkeyPatch, settings_cls: object, secret: str) -> str:
    """Build `Settings` with `secret`, expect the refusal, and answer its full text.

    The text includes every chained exception, because a startup traceback
    prints the cause as well.
    """
    from app.config import ConfigurationError

    monkeypatch.setenv("SESSION_SECRET", secret)
    with pytest.raises(ConfigurationError) as caught:
        settings_cls()  # type: ignore[operator]
    texts: list[str] = []
    current: BaseException | None = caught.value
    while current is not None and len(texts) < 10:
        texts.append(f"{current!s}\n{current!r}")
        current = current.__cause__ or current.__context__
    return "\n".join(texts)


def assert_names_only_session_secret(text: str) -> None:
    """The report names SESSION_SECRET and no other variable."""
    assert "SESSION_SECRET" in text, text
    reported = [
        line.strip().split(" ")[0]
        for line in text.splitlines()
        if line.startswith("  ") and not line.startswith("      ") and " — " in line
    ]
    assert reported == [
        "SESSION_SECRET"
    ], f"The refusal should be about SESSION_SECRET alone; it reported {reported}.\n{text}"


@pytest.mark.parametrize("deployment_settings", DEPLOYMENTS, indirect=True)
def test_a_deployment_refuses_the_example_placeholder(
    monkeypatch: pytest.MonkeyPatch,
    documented_env: dict[str, str],
    deployment_settings: object,
) -> None:
    placeholder = placeholder_from(documented_env)

    text = refusal_with(monkeypatch, deployment_settings, placeholder)

    assert_names_only_session_secret(text)
    assert placeholder not in text


@pytest.mark.parametrize("deployment_settings", DEPLOYMENTS, indirect=True)
@pytest.mark.parametrize("secret", ["", THIRTY_ONE_CHARACTERS], ids=["empty", "31-characters"])
def test_a_deployment_refuses_a_short_secret(
    monkeypatch: pytest.MonkeyPatch,
    deployment_settings: object,
    secret: str,
) -> None:
    text = refusal_with(monkeypatch, deployment_settings, secret)

    assert_names_only_session_secret(text)
    if secret:
        assert secret not in text


@pytest.mark.parametrize("deployment_settings", DEPLOYMENTS, indirect=True)
@pytest.mark.parametrize(
    "secret",
    [THIRTY_TWO_CHARACTERS, secrets.token_urlsafe(32)],
    ids=["32-characters", "token_urlsafe-32"],
)
def test_a_deployment_accepts_a_long_enough_secret(
    monkeypatch: pytest.MonkeyPatch,
    deployment_settings: object,
    secret: str,
) -> None:
    monkeypatch.setenv("SESSION_SECRET", secret)

    settings = deployment_settings()  # type: ignore[operator]

    assert settings.session_secret.get_secret_value() == secret


def test_the_two_boundary_values_are_the_lengths_they_claim() -> None:
    """The boundary pair is 31 and 32 characters, and the token is 43."""
    assert len(THIRTY_ONE_CHARACTERS) == 31
    assert len(THIRTY_TWO_CHARACTERS) == 32
    assert len(secrets.token_urlsafe(32)) == 43


@pytest.mark.parametrize("use_placeholder", [True, False], ids=["placeholder", "empty"])
def test_development_skips_the_check(
    monkeypatch: pytest.MonkeyPatch,
    configured_env: dict[str, str],
    documented_env: dict[str, str],
    use_placeholder: bool,
) -> None:
    """In development the placeholder and an empty value both start.

    This is the limit written down: `.env.example` ships
    `ENVIRONMENT=development`, so an unedited copy of it is never checked.
    """
    secret = placeholder_from(documented_env) if use_placeholder else ""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SESSION_SECRET", secret)
    from app.config import Settings

    settings = Settings()

    assert settings.session_secret.get_secret_value() == secret
