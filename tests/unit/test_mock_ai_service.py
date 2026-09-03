"""The mock AI provider as a *service* rather than as a provider — ticket E2-07.

Three of E2-07's four acceptance criteria are about a running stack, and none of
what makes them true is visible from one. This module holds the parts that go
green in every dynamic check and are still wrong, the same four kinds
`tests/unit/test_mock_lms_service.py` holds for the mock platform:

**Where the service is declared.** `docker compose up` merges
`docker-compose.override.yml` automatically, so a `mock-ai` declared only in the
override comes up on a developer's machine and in the merged CI pass and in no
deployment — and the base-file-only pass in the `docker` job then starts a stack
whose backend is pointed at a provider that is not there. ADR 0038 puts the mocks
in the base file, and this is where that is asserted for the third one.

**Where its health check is declared.** `scripts/ci/wait_for_health.sh` fails a
service that declares no HEALTHCHECK, so naming `mock-ai` in the gate's argument
list — which `tests/unit/test_ci_health_gate.py` does — only means something if
this service declares one, in the file every deployment runs.

**What the development override publishes, and where.** The ticket's
security-relevant note: "a new container is where a service gets exposed or
hidden ... The mock must not be reachable beyond what development needs." The
loopback-only rule over *every* published port lives in
`tests/unit/test_compose_stack.py` and is not repeated here; what is here is that
this service publishes nothing in the base file and exactly one debugging port in
the override, which is the decision the ticket asks the pull request to defend.

**What `.env.example` points the stack at.** Acceptance criterion 1 is "`make
up`, `.env` pointed at the mock", and criterion 4 is CI's e2e job running against
it — and the mechanism for both is one line in `.env.example`, because the e2e
job's first step is `cp .env.example .env`. The host in that line is compared
against the Compose service name rather than against a string written here, so a
service rename that misses one of the two is a red rather than a stack that comes
up with a backend pointed at a name nothing answers to (`docs/MISTAKES.md` entry
35).

**What is asserted elsewhere, deliberately.** That no workflow references a
repository secret — criterion 4's second half — is
`tests/unit/test_ai_provider_configuration.py::test_no_workflow_references_a_
repository_secret_beyond_the_permitted_set`, which already covers every workflow
in the repository. A second sweep for this ticket would be one rule written twice
(`docs/MISTAKES.md` entry 13).
"""

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from fixtures.mock_ai import (
    CONTAINER_PORT,
    MOCK_AI_PROVIDER_API_KEY_VARIABLE,
    MOCK_AI_PROVIDER_BASE_URL_VARIABLE,
    MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE,
    PUBLISHED_HOST_PORT,
)

# **This module moved to the `MOCK_AI_PROVIDER_*` triple, and the reason is the
# names rather than any new test.** The configuration split ruled on 2026-09-02
# gives the real provider and the in-repo mock a triple each —
# `AI_PROVIDER_{API_KEY,BASE_URL,MODEL_NAME}` and
# `MOCK_AI_PROVIDER_{API_KEY,BASE_URL,MODEL_NAME}` — and strikes `AI_MODEL_NAME`,
# which said which model without saying whose.
#
# Every assertion in this file is about the endpoint a development stack and CI's
# e2e job reach, and that endpoint is this repository's own `mock-ai` service. The
# ruling puts the description of that endpoint under the mock's names in every
# environment, and puts the real triple explicitly out of reach of the `mock-ai`
# host — so an assertion here that `AI_PROVIDER_BASE_URL` names `mock-ai` now
# asserts the exact thing the ruling forbids. What each test claims is unchanged:
# the documented mock endpoint resolves inside the Compose network, its key is
# blank because it authenticates nobody, and its model name is a value rather than
# something to fill in.
#
# The placeholder words below are unchanged: they are what a "not filled in yet"
# value reads like, and that has nothing to do with which provider is being named.
PLACEHOLDER_WORDS = ("replace", "your-", "example")

# The loopback address the override may bind a published port to. The general
# rule over every service is `tests/unit/test_compose_stack.py`'s; this is the
# one spelling that rule permits and this service uses.
LOOPBACK_HOST_IP = "127.0.0.1"


def compose_service(document: dict[str, Any], name: str, ticket: str) -> dict[str, Any]:
    """The `name` service out of a parsed Compose document, or a failure saying so.

    A second copy of `tests/unit/test_mock_lms_service.py`'s helper, and named as
    one. It takes the sentence to quote as an argument, because the mechanism is
    shared between the mocks and the *ticket* a missing service belongs to is not
    — the same split `import_mock_application` makes for its two failure messages.
    """
    services = document.get("services") or {}
    service = services.get(name)
    if not isinstance(service, dict):
        pytest.fail(
            f"The Compose document declares no `{name}` service (it declares {sorted(services)}). "
            f"{ticket}"
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


def published_ports(service: dict[str, Any]) -> list[str]:
    """Every `ports:` entry a service declares, in the short or the long form."""
    declared = service.get("ports") or []
    if not isinstance(declared, list):
        return []
    found: list[str] = []
    for entry in declared:
        if isinstance(entry, str):
            found.append(entry)
        elif isinstance(entry, dict):
            host_ip = entry.get("host_ip")
            published = entry.get("published")
            target = entry.get("target")
            found.append(":".join(str(part) for part in (host_ip, published, target) if part))
    return found


def test_the_base_compose_file_builds_the_mock_ai_service_from_this_repository(
    base_compose: dict[str, Any],
    mock_ai_service: str,
    mock_ai_dir: Path,
    repo_root: Path,
) -> None:
    """The service exists, in the file every deployment runs, built from this repository.

    Read against the *base* file alone, which is the point. `docker compose up`
    merges the development override, so a `mock-ai` declared only there comes up
    on a developer's machine and in the merged CI pass and nowhere else — and the
    `docker` job's base-file-only pass then starts a backend whose
    `MOCK_AI_PROVIDER_BASE_URL` names a service that is not running. ADR 0038 puts the
    mocks in the base file, and the ticket's own security note asks the pull
    request to defend the merged configuration rather than one file.

    **The mutation this kills:** the service declared in the override only; the
    service pulling an image instead of building (there is no registry copy of
    this repository's own code); and a `build:` pointing at another directory,
    which is how a service named for the mock ends up running the backend image —
    healthy, and answering no completion.

    **This is red today for a missing service rather than a missing file**, which
    is the failure worth having: it names the deliverable.
    """
    service = compose_service(
        base_compose,
        mock_ai_service,
        "E2-07 adds the mock AI provider to Compose so that e2e runs are self-contained (SPEC "
        "§9.2), and ADR 0038 puts a mock in the base file.",
    )
    dockerfile = dockerfile_for(service, repo_root)
    assert dockerfile is not None, (
        f"The `{mock_ai_service}` service declares no `build:` (it declares {sorted(service)}). "
        "The mock provider is this repository's own application, so there is no image to pull."
    )
    assert dockerfile.is_file(), (
        f"The `{mock_ai_service}` service builds from `{dockerfile}`, which does not exist. E2-07 "
        "puts the mock provider's Dockerfile beside its application, as `mock-lms/` and "
        "`mock-idp/` already do."
    )
    assert mock_ai_dir in dockerfile.parents, (
        f"The `{mock_ai_service}` service builds from `{dockerfile}`, which is outside "
        f"`{mock_ai_dir}`. A service named for the mock that builds another image would come up "
        "healthy and classify nothing."
    )


def test_the_mock_ai_service_declares_a_health_check_in_the_base_compose_file(
    base_compose: dict[str, Any],
    mock_ai_service: str,
) -> None:
    """The half that decides whether CI can see this service at all.

    `scripts/ci/wait_for_health.sh` fails a service that declares no HEALTHCHECK,
    so `tests/unit/test_ci_health_gate.py` naming `mock-ai` in the argument list
    means something only if there is a check to fail. Declared here rather than
    in the override for the reason `test_compose_stack.py` gives about `worker`
    and `beat`: a health check that lives only in the development override
    satisfies the merged gate while every other deployment runs a service that
    reports no health at all.

    **The mutation this kills:** the check moved to the override, or dropped in
    favour of the Dockerfile's own `HEALTHCHECK` — which Compose does inherit,
    but which E2-07's work order deliberately does not use, so that the check is
    visible in the file the reviewer reads.

    **What the check *does* is not asserted**, and that is E0-03's lesson rather
    than laziness: a health gate only ever exercises the direction where the
    answer is yes, and the cure is a check somebody has watched say no. Pinning a
    command here would pin an implementation and still prove nothing.
    """
    service = compose_service(
        base_compose,
        mock_ai_service,
        "E2-07 adds it with a health check, which is what makes the CI gate able to see it.",
    )
    healthcheck = service.get("healthcheck")
    assert isinstance(healthcheck, dict) and healthcheck.get("test"), (
        f"The `{mock_ai_service}` service declares no health check in the base Compose file (it "
        f"declares {sorted(service)}). `scripts/ci/wait_for_health.sh` fails a service with no "
        "HEALTHCHECK, so a service without one either fails the gate outright or — declared in "
        "the development override instead — passes the merged run while every other deployment "
        "reports nothing."
    )


def test_the_mock_ai_service_inherits_no_env_file_and_so_holds_no_credential(
    base_compose: dict[str, Any],
    mock_ai_service: str,
) -> None:
    """Why a mock may ride the base file at all: it is handed nothing.

    ADR 0038's argument for putting a mock in the file every deployment runs is
    that it holds no credential and reaches nothing. `env_file: - .env` hands a
    container the whole configuration surface — the superuser pair, the Care
    credential's parts, the provider key — and `tests/unit/test_compose_stack.py`
    spends four reviewer passes on services that take it. The cheapest way for
    this service to stay outside all of that is to take none of it.

    **The mutation this kills:** `env_file: - .env` copied onto this service from
    the `x-application` anchor, which is what a reader reaches for when the mock
    needs one literal value. E2-07 settles literal `environment:` values instead.

    **What this does not assert**, because `test_compose_stack.py` already does
    over the whole document: that no credential reaches it by any other route.
    That rule is closed-set and repository-wide, and a second copy here would be
    the weaker rule written twice.
    """
    service = compose_service(
        base_compose,
        mock_ai_service,
        "E2-07 adds it with literal environment values and no `env_file`.",
    )
    assert "env_file" not in service, (
        f"The `{mock_ai_service}` service declares `env_file: {service.get('env_file')!r}`. That "
        "hands this container the whole of `.env` — the superuser pair, the Care credential's "
        "parts and the provider key among it — for the sake of values E2-07 settles as literals. "
        "ADR 0038's reason a mock may sit in the base file is that it holds no credential."
    )


def test_the_development_override_publishes_the_mock_ai_on_the_loopback_interface(
    override_compose: dict[str, Any],
    base_compose: dict[str, Any],
    mock_ai_service: str,
) -> None:
    """Host exposure, decided and asserted: one port, loopback only, development only.

    E2-07's scope: "Decide host exposure (the other mocks publish 8080/8081; 8082
    if debugging wants it) and defend it in the PR against the merged compose
    config." The decision is 8082 on `127.0.0.1`, in the override — so a developer
    can curl the mock's rules and a deployment publishes nothing.

    **Both halves in one test, because each is satisfied by the other's absence.**
    A base file that publishes the port and an override that does not would pass
    a test that only looked at the override; and the general loopback rule in
    `test_compose_stack.py` is silent about a service that publishes nothing
    anywhere, which is the state this test also has to rule out — a mock nobody
    can reach from the host is not what the ticket decided.

    **The mutation this kills:** the mapping written as `8082:8000`, which binds
    every interface and serves this machine's mock provider to the network it is
    on. `test_compose_stack.py` holds that rule over every service; this one names
    the port, so a mapping that quietly moved to a port another service publishes
    is a red here rather than a collision at `docker compose up`.
    """
    assert override_compose, "The development override does not exist or declares nothing."

    service = compose_service(
        override_compose,
        mock_ai_service,
        "E2-07 publishes the mock provider for debugging in the development override only.",
    )
    published = published_ports(service)
    expected = f"{LOOPBACK_HOST_IP}:{PUBLISHED_HOST_PORT}:{CONTAINER_PORT}"
    assert expected in published, (
        f"The development override publishes {published} for `{mock_ai_service}`, and E2-07 "
        f"settles `{expected}`. The other two mocks publish 8080 and 8081; a mapping without the "
        f"`{LOOPBACK_HOST_IP}:` prefix serves this machine's mock provider to every interface, "
        "which is the omission `test_compose_stack.py` was written for."
    )

    in_base = compose_service(
        base_compose,
        mock_ai_service,
        "E2-07 adds it to the base file.",
    )
    assert not published_ports(in_base), (
        f"The base Compose file publishes {published_ports(in_base)} for `{mock_ai_service}`. "
        "Host publishing belongs to the development override: a `ports:` entry in the base file "
        "exposes this service in every deployment that runs it."
    )


def test_the_documented_provider_url_points_the_development_stack_at_the_mock(
    documented_env: dict[str, str],
    base_compose: dict[str, Any],
    mock_ai_service: str,
) -> None:
    """Acceptance criteria 1 and 4, in the one line that makes both true.

    CI's e2e job runs `cp .env.example .env` and then `docker compose up`, so this
    entry is what points the stack at the mock rather than at a hosted provider —
    which is criterion 4 ("CI's e2e job runs against it"), and the `.env` half of
    criterion 1. Without it the e2e run either reaches nothing and waits four
    seconds per submit, or reaches a real provider and spends real tokens.

    **The host is compared against the Compose service name, not against a string
    written here.** A catalog that has gone stale refuses nothing and reports
    exactly what a fresh one reports (`docs/MISTAKES.md` entry 35), and the same
    is true of a documented address: rename the service and this file would go on
    documenting a host nothing answers to, with every static test green and the
    stack unable to classify anything.

    **The mutation this kills:** the entry left at `.env.example`'s hosted
    placeholder; the host spelled `localhost`, which is the API container itself
    rather than the mock; and the port changed to the *published* 8082, which is
    the host's port and not the one the service listens on inside the network.
    """
    assert documented_env, ".env.example is missing or parsed to nothing."
    assert compose_service(
        base_compose, mock_ai_service, "E2-07 adds it."
    ), "There is no service to compare the documented host against."

    configured = documented_env.get(MOCK_AI_PROVIDER_BASE_URL_VARIABLE)
    assert configured, (
        f"`.env.example` documents no {MOCK_AI_PROVIDER_BASE_URL_VARIABLE}. It is a required setting "
        "and the file is what CI copies to `.env`."
    )
    parsed = urlsplit(configured)
    assert parsed.hostname == mock_ai_service, (
        f"`.env.example` points {MOCK_AI_PROVIDER_BASE_URL_VARIABLE} at host {parsed.hostname!r} and "
        f"the mock provider runs as the Compose service {mock_ai_service!r}. A container on this "
        "network reaches it by that name and by nothing else, so any other host is a development "
        "stack that classifies nothing — or that reaches a real provider and spends real tokens."
    )
    assert parsed.scheme == "http", (
        f"`.env.example` points {MOCK_AI_PROVIDER_BASE_URL_VARIABLE} at scheme {parsed.scheme!r}. The "
        "mock terminates no TLS; `https` to it fails to connect, which is a four-second stall per "
        "submit rather than a classification."
    )
    assert str(parsed.port) == CONTAINER_PORT, (
        f"`.env.example` names port {parsed.port} and the service listens on {CONTAINER_PORT} "
        f"inside the Compose network. {PUBLISHED_HOST_PORT} is the *host* port the development "
        "override publishes, which no container can reach."
    )


def test_the_documented_provider_key_is_blank_because_the_mock_authenticates_nobody(
    documented_env: dict[str, str],
) -> None:
    """The key entry stays documented and stops carrying a value.

    `.env.example` already states the rule this asserts: "Leave it empty when the
    endpoint authenticates nobody — vLLM, Ollama, a proxy on the same host. A
    blank value is read as absent." The mock is exactly that, and a leftover
    `replace-me-with-your-provider-key` is a value the gateway would send as a
    bearer token — inert against this mock, and a placeholder that reads as
    configuration somebody has to fill in.

    **The mutation this kills:** the entry deleted rather than blanked, which
    breaks `test_env_example_sync.py`'s rule that every `Settings` field has a
    documented entry; and the entry left at a placeholder, which is what makes a
    developer think the development stack needs a key.
    """
    assert documented_env, ".env.example is missing or parsed to nothing."
    assert MOCK_AI_PROVIDER_API_KEY_VARIABLE in documented_env, (
        f"`.env.example` no longer documents {MOCK_AI_PROVIDER_API_KEY_VARIABLE}. A `Settings` field "
        "with no documented entry fails `tests/unit/test_env_example_sync.py`, and the key is "
        "still what a deployment configures for a hosted provider — it is blank here, not gone."
    )
    assert documented_env[MOCK_AI_PROVIDER_API_KEY_VARIABLE] == "", (
        f"`.env.example` documents {MOCK_AI_PROVIDER_API_KEY_VARIABLE} as "
        f"{documented_env[MOCK_AI_PROVIDER_API_KEY_VARIABLE]!r}. The development stack talks to a mock "
        "that authenticates nobody, and the file's own rule for that case is a blank value, read "
        "as absent."
    )


def test_the_documented_model_name_is_a_value_and_not_a_thing_to_fill_in(
    documented_env: dict[str, str],
) -> None:
    """The model name has to work unedited, because CI never edits it.

    The mock's model name was a placeholder — `replace-with-your-model-id` — for
    as long as there was no endpoint in the stack to name a model on. It was
    spelled `AI_MODEL_NAME` when this test was written and is
    `MOCK_AI_PROVIDER_MODEL_NAME` since the configuration split ruled on
    2026-09-02; the old name is recorded here rather than erased, because the
    property has a history and the rename did not change it. The e2e job copies
    this file verbatim, so a placeholder is what the gateway would send as the
    model it is asking for, and what it would record as half of every
    classification's audit pair (ADR 0031).

    **The mutation this kills:** the entry left at its placeholder while the base
    URL moves to the mock, which is the half-done edit — the stack then reaches
    the mock and records `replace-with-your-model-id` against every classification
    E2 writes.
    """
    assert documented_env, ".env.example is missing or parsed to nothing."
    configured = documented_env.get(MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE, "")
    assert configured, f"`.env.example` documents no {MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE}."
    lowered = configured.lower()
    assert not any(word in lowered for word in PLACEHOLDER_WORDS), (
        f"`.env.example` documents {MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE} as {configured!r}, which reads as a "
        "value somebody is meant to replace. CI's e2e job copies this file unedited, so the "
        "development stack asks the mock for that model name and records it as the `model_id` of "
        "every classification (ADR 0031)."
    )
