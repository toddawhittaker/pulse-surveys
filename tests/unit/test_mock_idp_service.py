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

The Compose files are parsed in `tests/fixtures/repo.py`, unmerged and one at a
time,
which is the whole point: `docker compose config` would merge the override back
in and hide the property under test.

**Two rules here have no HTTP surface at all**, and that is why the last tests
import the provider's settings class instead of driving it: a redirect URI is
judged when the settings are built, before anything is served, so the only way to
ask the question is to build them. RFC 6749 §3.1.2 gives the first — "the
endpoint URI MUST NOT include a fragment component" — and the second follows from
what this provider does with the URI: the authorization response appends
parameters of its own — `code` and `state` on the way to success, and after
E0-30 `error` and `error_description` on the way to a refusal — so a URI already
carrying one of those names is one it would return to with a duplicate parameter
on it. Both are configuration, so both fail at startup or not at all, and the
cost of missing either lands on whoever configured it rather than on whoever
wrote it.

Four of those six cases are ordinary. One is E0-16's finding: a **bare** `#`
was read through `urlsplit(...).fragment`, whose empty string is falsy, so the one
spelling that looks like a typo registered cleanly while the obvious one was
caught. Two are E0-30's, and are the same rule catching up with a response that
grew: once a refusal is a redirect, `error` and `error_description` go onto this
URI too, and a registration presenting either sends a client the operator's
preset instead of the provider's verdict. The accepted cases beside them all —
the shipped URI, and one carrying an unrelated query parameter — are what keep
the rules from being satisfied by a check that refuses everything.
"""

from pathlib import Path
from typing import Any

import pytest

# What is appended to the shipped redirect URI to make it one the authorization
# response could not return to unchanged, with the pattern each refusal's message
# has to match. Four cases, two rules:
#
#   - A fragment, which RFC 6749 §3.1.2 forbids outright. **The bare `#` is the
#     finding**: the check read `urlsplit(...).fragment`, which is the empty
#     string for a trailing `#` and therefore falsy, so that spelling registered
#     while `#stolen` was caught. One rule, two results, and only one of them was
#     ever wrong — which is why both are here.
#   - A query already carrying one of the names the authorization response
#     appends. Registering one means the provider emits the duplicate parameter
#     it refuses inbound. E0-16 had two of them, `code` and `state`; **E0-30's
#     error redirects add `error` and `error_description`**, which are appended to
#     this same URI on every post-validation refusal, and the two new cases here
#     are that finding. A refusal against a URI registered as
#     `…/callback?error=preset` is delivered as `?error=preset&error=invalid_scope`,
#     and a client reading the first `error` of two reads whatever the operator
#     put there rather than what the provider decided.
#
# The patterns are deliberately loose about wording and tight about subject: a
# message that quotes the offending URI contains the parameter name too, so
# matching the name works whether the sentence spells it out or shows it.
REFUSED_REDIRECT_SUFFIXES = {
    "a fragment": ("#stolen", r"(?i)fragment|#"),
    "an empty fragment": ("#", r"(?i)fragment|#"),
    "a preset state parameter": ("?state=preset", r"(?i)state"),
    "a preset code parameter": ("?code=preset", r"(?i)code"),
    "a preset error": ("?error=preset", r"(?i)error"),
    "a preset error_description": ("?error_description=preset", r"(?i)error_description"),
}

# A query parameter the authorization response will never collide with. The
# control that the two rules above did not become "no query, no fragment, ever",
# which would refuse configurations that are ordinary and correct.
UNRELATED_QUERY = "?tenant=x"


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


def redirect_uri_variable(environment: dict[str, str]) -> str:
    """The one Compose variable that carries the registered redirect URI."""
    assert environment, (
        "`docker-compose.yml` gives the `mock-idp` service no literal environment, so these tests "
        "have no configuration to build settings from. The mock platform is configured by Compose "
        "literals for the reason ADR 0037 gives, and this provider was expected to be too — if it "
        "reads its configuration another way, these tests need to be pointed at it."
    )
    names = sorted(name for name in environment if "REDIRECT" in name)
    assert len(names) == 1, (
        f"The `mock-idp` service's environment carries {names} — this cannot tell which one is "
        "the redirect URI, and setting the wrong one would make every refusal below a fact about "
        "a different variable."
    )
    return names[0]


def settings_built_with(
    settings_class: Any,
    environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    redirect_uri: str,
) -> Any:
    """Build the provider's settings from the container's environment, with one value swapped.

    The whole Compose environment first, so the settings are built from what the
    container is actually given rather than from a URI invented here, and then the
    redirect URI replaced with the value under test.
    """
    name = redirect_uri_variable(environment)
    for variable, value in environment.items():
        monkeypatch.setenv(variable, value)
    monkeypatch.setenv(name, redirect_uri)
    return settings_class.from_environment()


def test_the_registered_redirect_uri_the_provider_ships_with_is_accepted(
    mock_idp_settings: Any,
    mock_idp_compose_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control every refusal below rests on, and the reason it is its own test.

    A settings object that raised on *every* redirect URI would satisfy each of
    those refusals perfectly and would also refuse every deployment. Asserting it
    once, by name, is what makes the six refusals mean something — and it is
    separate rather than repeated inside each of them because "the shipped
    configuration builds" is a claim about this provider, not about any one bad
    value.

    It also pins the assumption the appended cases below depend on: the shipped
    URI carries neither a query nor a fragment, so appending one produces exactly
    the case each is named for.
    """
    clean = mock_idp_compose_environment.get(redirect_uri_variable(mock_idp_compose_environment))
    assert clean and "?" not in clean and "#" not in clean, (
        f"The shipped redirect URI is {clean!r}. The cases below append a query or a fragment to "
        "it, so a value that already carries one would make each of them a different test than "
        "its name says."
    )

    settings = settings_built_with(
        mock_idp_settings, mock_idp_compose_environment, monkeypatch, clean
    )
    assert settings is not None, (
        f"Building the provider's settings with `{redirect_uri_variable(mock_idp_compose_environment)}` "
        f"set to the value `docker-compose.yml` ships, {clean!r}, produced {settings!r}."
    )


@pytest.mark.parametrize("case", sorted(REFUSED_REDIRECT_SUFFIXES))
def test_a_redirect_uri_the_provider_could_not_return_to_exactly_is_refused(
    mock_idp_settings: Any,
    mock_idp_compose_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    """Configuration that has no request able to ask about it, so it is asked here.

    Two rules, both about a URI the authorization response would have to *change*
    before it could use it:

      - **RFC 6749 §3.1.2: "the endpoint URI MUST NOT include a fragment
        component".** A provider that accepted one would serve every flow up to the
        redirect, where the browser keeps the configured fragment, drops the
        response's, or merges them depending on which browser it is — and the
        response lands somewhere nobody declared, with nobody having attacked
        anything. **The bare `#` is the finding**: it was checked with
        `urlsplit(...).fragment`, whose empty-string result for a trailing `#` is
        falsy, so the one spelling that looks like an oversight registered
        cleanly. It is here beside `#frag` because they are one rule and two
        results, and only one of them was ever wrong.
      - **A query already carrying a name the authorization response appends.**
        A URI presenting one is a URI the provider would return to carrying that
        name twice — the duplicate it refuses on the way in, emitted on the way
        out. That is not in the RFC; it follows from what this provider does with
        the URI, which is why it is checked where the URI is registered rather
        than where a request arrives.

        **The set of those names is not fixed, and it grew.** E0-16 appended
        `code` and `state`. E0-30 makes every post-validation refusal an RFC 6749
        §4.1.2.1 redirect to this same URI, which appends `error` and
        `error_description` as well, so those two belong in the rule for exactly
        the reason the first two do — and a client that reads the first `error` of
        two reads the value whoever wrote the configuration chose. That is why
        both new cases are here rather than one: a fix that adds `error` and stops
        leaves the description, which is the half a developer acts on.

    The failure this shape is prone to is the one `docs/MISTAKES.md` entry 3
    describes: `pytest.raises(Exception, match=...)` is satisfied by any exception
    whose message matches, so "it refused" and "it refused for this reason" are
    different claims. What separates them here is
    `test_a_redirect_uri_carrying_an_unrelated_query_parameter_is_accepted` below,
    which fails the moment the rule becomes "no query at all" — so an exception
    raised for one of these six suffixes is one raised about that suffix.

    The exception type is deliberately not pinned. What is asserted is that the
    failure *names* what was wrong with the value, which is what someone reading a
    container that will not start needs — E0-07's definition of done asks the same
    of the section-code parser, in the same words. The patterns match either the
    word or the offending value, since a message quoting the URI names it too.
    """
    suffix, pattern = REFUSED_REDIRECT_SUFFIXES[case]
    clean = mock_idp_compose_environment.get(redirect_uri_variable(mock_idp_compose_environment))
    assert clean, "The `mock-idp` service's environment carries no redirect URI to append to."

    with pytest.raises(Exception, match=pattern):
        settings_built_with(
            mock_idp_settings, mock_idp_compose_environment, monkeypatch, f"{clean}{suffix}"
        )


def test_a_redirect_uri_carrying_an_unrelated_query_parameter_is_accepted(
    mock_idp_settings: Any,
    mock_idp_compose_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other side of the query rule: what is refused is `code` and `state`, not a query.

    A redirect URI carrying a tenant, a locale or a return path is ordinary — real
    clients register them — and the authorization response appends its own
    parameters to whatever is there without touching them. So the check has to
    refuse the two names it would collide with and accept the rest, and a check
    that had quietly become "no query at all" would satisfy every refusal above
    while rejecting configurations that are fine.

    This is the assertion that would have caught the fragment rule being fixed by
    widening rather than by correcting: `urlsplit(...).fragment` being falsy for
    `#` is repaired either by looking for the character or by refusing anything
    with a `?` or a `#` in it, and only one of those two is right.
    """
    clean = mock_idp_compose_environment.get(redirect_uri_variable(mock_idp_compose_environment))
    assert clean, "The `mock-idp` service's environment carries no redirect URI to append to."

    settings = settings_built_with(
        mock_idp_settings,
        mock_idp_compose_environment,
        monkeypatch,
        f"{clean}{UNRELATED_QUERY}",
    )
    assert settings is not None, (
        f"Building the provider's settings with a redirect URI of {clean + UNRELATED_QUERY!r} "
        f"produced {settings!r}."
    )
