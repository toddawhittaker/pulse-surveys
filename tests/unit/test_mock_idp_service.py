"""The mock provider as a *service* rather than as a protocol — ticket E0-16.

E0-16's first acceptance criterion is "`docker compose up -d` brings `mock-idp`
to healthy", and no test in this suite can bring a stack up: the CI `docker` job
does that, and `tests/unit/test_ci_health_gate.py` holds the argument list it
waits with. What that gate cannot see is *where* the service and its health check
are declared. `docker compose up` merges `docker-compose.override.yml`
automatically, so a service declared only in the override — or a health check
declared only there — satisfies every gate anyone runs while every
non-development deployment brings up something else. That is the same shape
`tests/unit/test_compose_stack.py` was written for and
`tests/unit/test_mock_lms_service.py` repeated for the platform, applied to the
service that carries the *other* entry door: without it, E0-18 brings up a stack
missing one of the two doors SPEC §9.2 says every run exercises.

**Criterion 9's second half is not repeated here, deliberately.** "No private key
is committed" is a claim about the whole repository, and
`tests/unit/test_mock_lms_service.py` already sweeps every file in the tree for
PEM private-key armour and for a JWK carrying private members — `mock-idp/`
included, the moment it exists. A second sweep rooted at this ticket's directory
would be the same rule written twice and weaker in exactly the way that matters,
since a key checked in anywhere else is the same credential. The half that *is*
E0-16's own — keys generated at startup rather than loaded — is asserted in
`tests/integration/test_mock_idp_authorization_code_flow.py`, where two
independently started providers must publish different keys.

The Compose files are parsed in `tests/conftest.py`, unmerged and one at a time,
which is the whole point: `docker compose config` would merge the override back
in and hide the property under test.

**One rule here has no HTTP surface at all**, and that is why the last test
imports the provider's settings class instead of driving it: a redirect URI
carrying a fragment is refused when the settings are built, before anything is
served, so the only way to ask the question is to build them. RFC 6749 §3.1.2 is
the rule — "the redirect URI MUST NOT include a fragment component" — and the
cost of not enforcing it is that a client configured with one gets a redirect the
browser rewrites, with the authorization response landing somewhere nobody
declared.
"""

from pathlib import Path
from typing import Any

import pytest

# A redirect URI that is fine, and the same URI with the one thing RFC 6749
# §3.1.2 forbids added to it. The pair is the test: a settings object that raised
# on both would satisfy "the bad one is refused" while refusing every deployment.
FRAGMENT = "#stolen"


def compose_service(base_compose: dict[str, Any], name: str) -> dict[str, Any]:
    """The `name` service out of a parsed Compose document, or a failure saying so.

    A near-copy of the helper in `test_mock_lms_service.py`, and deliberately a
    copy rather than a shared fixture: what differs between the two is the
    sentence each failure cites, which is the whole content of the helper. Moving
    it would edit E0-14's module to no benefit of E0-14's.
    """
    services = base_compose.get("services") or {}
    service = services.get(name)
    if not isinstance(service, dict):
        pytest.fail(
            f"`docker-compose.yml` declares no `{name}` service (it declares {sorted(services)}). "
            f"E0-16's scope adds the mock provider to Compose as `{name}` with a health check, "
            "and SPEC §7.2 lists it among the services the stack runs: 'mock-idp — dev/test-only "
            "OIDC identity provider for web-login roles'."
        )
    return service


def dockerfile_for(service: dict[str, Any], repo_root: Path) -> Path | None:
    """Where a service's `build:` declaration says its Dockerfile is."""
    build = service.get("build")
    if isinstance(build, str):
        return repo_root / build / "Dockerfile"
    if isinstance(build, dict):
        context = repo_root / str(build.get("context", "."))
        dockerfile = build.get("dockerfile")
        return context / str(dockerfile) if dockerfile else context / "Dockerfile"
    return None


def test_the_mock_idp_directory_holds_the_application_spec_13_places_there(
    mock_idp_dir: Path,
) -> None:
    """The deliverable exists where SPEC §13 says, before anything else looks for it.

    §13's tree: `mock-idp/` holding a `Dockerfile` and an `app/` with "discovery,
    authorize, token, JWKS; seeded leadership/care/admin users". Kept separate
    from the tests that drive the provider so that "there is no mock IdP yet"
    reports as one failure naming the missing directory rather than as every test
    in two modules failing inside a fixture — `docs/MISTAKES.md` entry 13's
    advice read forward, and the same test `test_mock_lms_launch.py` carries for
    the platform.
    """
    assert (mock_idp_dir / "app").is_dir(), (
        f"{mock_idp_dir / 'app'} does not exist. SPEC §13 puts the in-repo OIDC provider at "
        "`mock-idp/`, with a `Dockerfile` and an `app/` holding discovery, authorize, token and "
        "JWKS, and the seeded leadership, Care and admin users."
    )


def test_the_base_compose_file_builds_the_mock_idp_service_from_this_repository(
    base_compose: dict[str, Any],
    mock_idp_service: str,
    mock_idp_dir: Path,
    repo_root: Path,
) -> None:
    """Criterion 1's static half: the service exists, in the file every deployment runs.

    Read against the *base* file alone, which is the point. `docker compose up`
    merges the development override, so a `mock-idp` declared only there comes up
    on a developer's machine and in the merged CI pass and nowhere else.

    The Dockerfile is checked for existence rather than for content: SPEC §13's
    layout puts it at `mock-idp/Dockerfile` beside the application it builds, and
    a `build:` pointing somewhere else is either a layout change or a typo, both
    of which are worth a red. A service that pulled an image instead would fail
    here too, which is correct — the mock is this repository's own code and there
    is no registry copy of it.
    """
    service = compose_service(base_compose, mock_idp_service)

    dockerfile = dockerfile_for(service, repo_root)
    assert dockerfile is not None, (
        f"The `{mock_idp_service}` service declares no `build:` (it declares {sorted(service)}). "
        "The mock provider is this repository's own application — E0-16's scope is a `mock-idp/` "
        "FastAPI application and Dockerfile — so there is no image to pull."
    )
    assert dockerfile.is_file(), (
        f"The `{mock_idp_service}` service builds from `{dockerfile}`, which does not exist. "
        "E0-16 puts the mock provider's Dockerfile at `mock-idp/Dockerfile`, beside `mock-lms/`."
    )
    assert mock_idp_dir in dockerfile.parents, (
        f"The `{mock_idp_service}` service builds from `{dockerfile}`, which is outside "
        f"`{mock_idp_dir}`. A service named for the provider that built the backend image, or "
        "the platform's, would come up healthy and serve no discovery document."
    )


def test_the_mock_idp_service_declares_a_health_check_in_the_base_compose_file(
    base_compose: dict[str, Any],
    mock_idp_service: str,
) -> None:
    """Criterion 1's other static half, and the one that decides whether CI can see it.

    `scripts/ci/wait_for_health.sh` fails a service that declares no HEALTHCHECK,
    so naming `mock-idp` in that gate's argument list only means something if this
    service declares one. Declared *here* rather than in the override, for the
    reason `tests/unit/test_compose_stack.py` gives about `worker` and `beat`: a
    health check that lives only in the development override satisfies the merged
    gate while every other deployment runs a provider that reports no health at
    all.

    What the check *does* is not asserted, deliberately. E0-03 learned that a
    health gate only ever exercises the direction where the answer is yes, and the
    cure is a check that has been seen to say no — which is something to do to a
    running container, not a string to compare in a YAML file. Pinning a command
    here would pin an implementation E0-16 leaves open and still would not prove
    the check works.
    """
    service = compose_service(base_compose, mock_idp_service)

    healthcheck = service.get("healthcheck")
    assert isinstance(healthcheck, dict) and healthcheck.get("test"), (
        f"The `{mock_idp_service}` service declares no health check in `docker-compose.yml` (it "
        f"declares {sorted(service)}). E0-16's scope asks for one, and it is what makes criterion "
        "1 checkable at all: `scripts/ci/wait_for_health.sh` fails a service with no HEALTHCHECK, "
        "so a service without one either fails the gate outright or — if it is declared in the "
        "development override instead — passes the merged run while every other deployment "
        "reports nothing."
    )


def test_a_redirect_uri_carrying_a_fragment_is_refused_when_the_settings_are_built(
    mock_idp_settings: Any,
    mock_idp_compose_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RFC 6749 §3.1.2: "the endpoint URI MUST NOT include a fragment component".

    There is no request that can ask this. The redirect URI is configuration, and
    a provider that accepted one with a fragment would serve every flow perfectly
    — right up to the redirect, where the browser keeps the fragment it was
    configured with, drops the one the response carried, or merges them depending
    on which browser it is. The authorization response then lands somewhere
    nobody declared, which is the same class of failure as an unregistered
    redirect URI and arrives without anyone having attacked anything.

    **The clean value goes first, and it is not ceremony.** A settings object that
    raised on every redirect URI would satisfy "the one with a fragment is
    refused" and would also refuse every deployment; the control is what says the
    refusal is about the fragment. Both are built from the environment the
    container is actually given — the Compose service's own literals — so this
    asks the question against the configuration that ships rather than against a
    URI invented here.

    The exception type is deliberately not pinned. What is asserted is that the
    failure *names* what was wrong with the value, which is what a person reading
    a container that will not start needs; E0-07's definition of done asks the
    same of the section-code parser, in the same words.
    """
    assert mock_idp_compose_environment, (
        "`docker-compose.yml` gives the `mock-idp` service no literal environment, so this test "
        "has no configuration to build settings from. The mock platform is configured by Compose "
        "literals for the reason ADR 0037 gives, and this provider was expected to be too — if it "
        "reads its configuration another way, this test needs to be pointed at it."
    )

    redirect_names = sorted(name for name in mock_idp_compose_environment if "REDIRECT" in name)
    assert len(redirect_names) == 1, (
        f"The `mock-idp` service's environment carries {redirect_names} — this cannot tell which "
        "one is the redirect URI whose fragment is being refused, and setting the wrong one would "
        "make the refusal below a fact about a different variable."
    )
    name = redirect_names[0]
    clean = mock_idp_compose_environment[name]

    for variable, value in mock_idp_compose_environment.items():
        monkeypatch.setenv(variable, value)

    monkeypatch.setenv(name, clean)
    settings = mock_idp_settings.from_environment()
    assert settings is not None, (
        f"Building the provider's settings from the Compose environment with `{name}` set to "
        f"{clean!r} produced {settings!r}. That is the configuration the container runs with, so "
        "the refusal below would be a fact about settings that never build."
    )

    monkeypatch.setenv(name, f"{clean}{FRAGMENT}")
    with pytest.raises(Exception, match=r"(?i)fragment|#"):
        mock_idp_settings.from_environment()
