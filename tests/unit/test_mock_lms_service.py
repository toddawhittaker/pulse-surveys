"""The mock platform as a *service* rather than as a protocol — ticket E0-14.

Two of E0-14's acceptance criteria are not about launches at all, and neither is
visible from a running stack.

**Criterion 1 — `docker compose up -d` brings `mock-lms` to healthy.** The health
gate in CI checks that, and `tests/unit/test_ci_health_gate.py` holds the
argument list it checks it with. What that gate cannot see is *where* the service
and its health check are declared. `docker compose up` merges
`docker-compose.override.yml` automatically, so a service declared only in the
override, or a health check declared only there, satisfies every gate anyone runs
while every non-development deployment brings up something else — the same shape
`tests/unit/test_compose_stack.py` was written for, applied to a service that did
not exist when it was written.

**Criterion 3 — issuer keys are generated per run; no private key is committed.**
The second half of that sentence is a claim about the repository, not about a
running platform, and no dynamic check can make it: a mock that loads a committed
key signs launches that verify against its own JWKS perfectly well, so every
launch test stays green. `tests/integration/test_mock_lms_launch.py` holds the
first half — two starts of the platform produce two different keys — and the
sweep below holds the second. Neither implies the other: a key generated per run
and *also* checked in is caught only here, and a key that is absent from the tree
and pinned in a Dockerfile is caught only there.

The sweep asserts an absence, which is `docs/MISTAKES.md` entry 3's subject, so
it is guarded twice. It counts what it read, because a scan that visited nothing
finds nothing; and the matcher itself is exercised against a private key header
and against a public one in its own test, because "run it against the text you
claim it catches *and* against the text you claim it allows" is what that entry
asks for. Neither guard is ceremony: the first version of a sweep like this one
can decode nothing and pass.
"""

import json
from pathlib import Path
from typing import Any

import pytest

# Directories a source sweep has no business reading. Build output, virtual
# environments and caches all hold third-party key material — a `cryptography`
# wheel ships test keys — and none of it is committed to this repository, which
# is what criterion 3 is about.
UNSWEPT_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "venv",
    }
)

# Files past this size are not source, and reading them costs more than the
# sweep is worth. **This suite's choice**: a PEM private key is under 4 KiB, so
# nothing the sweep is looking for hides above this line.
LARGEST_SWEPT_FILE = 1 << 20

# The PEM header every private key format writes, whatever the algorithm:
# `PRIVATE KEY`, `RSA PRIVATE KEY`, `EC PRIVATE KEY`, `ENCRYPTED PRIVATE KEY`.
# Assembled from pieces rather than written out, so that this module is not
# itself the thing the sweep finds.
#
# Split with an explicit `+` rather than written whole: the sweep reads every
# file in the tree, this module included, and a matcher that finds itself is a
# permanent red that teaches everyone to add an exclusion.
PEM_PRIVATE_MARKER = "PRIVATE" + " KEY-----"
PEM_PUBLIC_MARKER = "PUBLIC" + " KEY-----"
PEM_PRIVATE_HEADER = "-----BEGIN " + PEM_PRIVATE_MARKER

# The members that make a JSON Web Key a private key (RFC 7517, RFC 7518): `d`
# for RSA and EC, `k` for a symmetric key, and RSA's CRT parameters. A JWK is
# JSON, so a committed one would not carry a PEM header and the text matcher
# above would walk straight past it.
PRIVATE_JWK_MEMBERS = frozenset({"d", "p", "q", "dp", "dq", "qi", "k"})

# A number low enough that any real checkout clears it and high enough that a
# sweep which silently stopped after the first directory does not. **This
# suite's choice.**
FEWEST_CREDIBLE_SWEPT_FILES = 50


def swept_files(root: Path) -> list[Path]:
    """Every file the private-key sweep reads, in a stable order.

    Pruned while walking rather than filtered afterwards, so `.git` is skipped
    instead of enumerated: a repository's object store is most of its files and
    none of them is a committed source file.
    """
    found: list[Path] = []
    for parent, directories, names in root.walk():
        directories[:] = sorted(name for name in directories if name not in UNSWEPT_DIRECTORIES)
        for name in sorted(names):
            path = parent / name
            if path.is_symlink() or not path.is_file():
                continue
            if path.stat().st_size > LARGEST_SWEPT_FILE:
                continue
            found.append(path)
    return found


def holds_pem_private_key(text: str) -> bool:
    """Whether `text` contains a PEM private-key header of any algorithm."""
    return "-----BEGIN " in text and PEM_PRIVATE_MARKER in text


def private_jwk_members(node: Any) -> bool:
    """Whether `node` contains a JSON Web Key carrying private material."""
    if isinstance(node, dict):
        if "kty" in node and PRIVATE_JWK_MEMBERS & set(node):
            return True
        return any(private_jwk_members(value) for value in node.values())
    if isinstance(node, list):
        return any(private_jwk_members(item) for item in node)
    return False


def holds_private_key(path: Path) -> bool:
    """Whether `path` holds private key material in either shape it could take."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    if holds_pem_private_key(text):
        return True
    try:
        return private_jwk_members(json.loads(text))
    except (ValueError, RecursionError):
        return False


def compose_service(base_compose: dict[str, Any], name: str) -> dict[str, Any]:
    """The `name` service out of a parsed Compose document, or a failure saying so."""
    services = base_compose.get("services") or {}
    service = services.get(name)
    if not isinstance(service, dict):
        pytest.fail(
            f"`docker-compose.yml` declares no `{name}` service (it declares "
            f"{sorted(services)}). E0-14's scope adds the mock platform to Compose as "
            f"`{name}` with a health check, and SPEC §7.2 lists it among the services the "
            "stack runs."
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


def test_the_base_compose_file_builds_the_mock_lms_service_from_this_repository(
    base_compose: dict[str, Any],
    mock_lms_service: str,
    mock_lms_dir: Path,
    repo_root: Path,
) -> None:
    """Criterion 1's static half: the service exists, in the file every deployment runs.

    Read against the *base* file alone, which is the point. `docker compose up`
    merges the development override, so a `mock-lms` declared only there comes up
    on a developer's machine and in the merged CI pass and nowhere else — and
    E0-18 then brings up a stack that is missing one of the two entry doors §9.2
    says every run exercises.

    The Dockerfile is checked for existence rather than for content: SPEC §13
    puts it at `mock-lms/Dockerfile`, and a `build:` pointing somewhere else is
    either a layout change or a typo, both of which are worth a red. A service
    that pulled an image instead would fail here too, which is correct — the mock
    is this repository's own code and there is no registry copy of it.
    """
    service = compose_service(base_compose, mock_lms_service)
    dockerfile = dockerfile_for(service, repo_root)
    assert dockerfile is not None, (
        f"The `{mock_lms_service}` service declares no `build:` (it declares "
        f"{sorted(service)}). The mock platform is this repository's own application — SPEC "
        "§13 puts it at `mock-lms/` with its own Dockerfile — so there is no image to pull."
    )
    assert dockerfile.is_file(), (
        f"The `{mock_lms_service}` service builds from `{dockerfile}`, which does not exist. "
        "SPEC §13 puts the mock platform's Dockerfile at `mock-lms/Dockerfile`."
    )
    assert mock_lms_dir in dockerfile.parents, (
        f"The `{mock_lms_service}` service builds from `{dockerfile}`, which is outside "
        f"`{mock_lms_dir}`. SPEC §13 keeps the mock platform's Dockerfile beside its "
        "application; a service named for the mock that builds the backend image would come "
        "up healthy and serve no launch."
    )


def test_the_mock_lms_service_declares_a_health_check_in_the_base_compose_file(
    base_compose: dict[str, Any],
    mock_lms_service: str,
) -> None:
    """Criterion 1's other static half, and the one that decides whether CI can see it.

    `scripts/ci/wait_for_health.sh` fails a service that declares no HEALTHCHECK,
    so naming `mock-lms` in the gate's argument list only means something if this
    service declares one. Declared *here* rather than in the override, for the
    reason `tests/unit/test_compose_stack.py` gives about `worker` and `beat`: a
    health check that lives only in the development override satisfies the merged
    gate while every other deployment runs a platform that reports no health at
    all.

    What the check *does* is not asserted, deliberately. E0-03 learned that a
    health gate only ever exercises the direction where the answer is yes, and
    the cure for that is a check that has been seen to say no — which is a thing
    to do to a running container, not a string to compare in a YAML file. Pinning
    a command here would pin an implementation E0-14 leaves open and still would
    not prove the check works.
    """
    service = compose_service(base_compose, mock_lms_service)
    healthcheck = service.get("healthcheck")
    assert isinstance(healthcheck, dict) and healthcheck.get("test"), (
        f"The `{mock_lms_service}` service declares no health check in `docker-compose.yml` "
        f"(it declares {sorted(service)}). E0-14's scope asks for one, and it is what makes "
        "criterion 1 checkable at all: `scripts/ci/wait_for_health.sh` fails a service with no "
        "HEALTHCHECK, so a service without one either fails the gate outright or — if it is "
        "declared in the development override instead — passes the merged run while every "
        "other deployment reports nothing."
    )


def test_the_private_key_matcher_finds_a_private_key_and_ignores_a_public_one() -> None:
    """The control on the sweep below, run before its silence is believed.

    `docs/MISTAKES.md` entry 3: a pattern searched against a file is a case of
    "a test passed for a reason unrelated to what it asserted" and looks like
    none, so run it against the text you claim it catches *and* the text you
    claim it allows. Both halves are here. Without the second, a matcher that
    answered `True` for everything would still make the sweep pass — it would
    just never be reached, because a repository with a public key in it would go
    red first and the matcher would be corrected without anyone learning it was
    wrong in both directions.

    The JWK half is separate from the PEM half because a checked-in key is at
    least as likely to arrive as a JSON key set — that is the shape a JWKS
    endpoint serves — and a text matcher looking for PEM armour walks straight
    past it.
    """
    assert holds_pem_private_key(PEM_PRIVATE_HEADER + "\nMIIE\n-----END " + PEM_PRIVATE_MARKER)
    assert not holds_pem_private_key("-----BEGIN " + PEM_PUBLIC_MARKER + "\nMIIB\n")
    assert private_jwk_members({"keys": [{"kty": "RSA", "n": "AQ", "e": "AQAB", "d": "AQ"}]})
    assert not private_jwk_members({"keys": [{"kty": "RSA", "n": "AQ", "e": "AQAB"}]})


def test_no_private_key_material_is_committed_to_the_repository(repo_root: Path) -> None:
    """Criterion 3's second half, which nothing dynamic can assert.

    SPEC §9.1 asks for "issuer keys generated per test run rather than fixtures
    checked into the repository", and E0-14 restates it as an acceptance
    criterion. The reason it needs a test of its own is that a committed key
    breaks nothing: launches signed with it verify against the JWKS the same mock
    publishes, so every protocol test in this suite stays green while the private
    half of the platform's identity sits in version control, is copied into every
    image, and is the same on every developer's machine and in every fork.

    The file count is not ceremony. This test asserts that a set is empty, and an
    empty set is what a sweep that read nothing produces — a bad root, a permission
    error, an exclusion list that grew until it covered the tree. So the sweep has
    to be seen to have read something before its silence counts as evidence.

    **What it does not cover**, stated rather than implied: it walks the working
    tree, not `git ls-files`, so an untracked key on a developer's machine reads
    as a failure here. That direction is the safe one — a red that says "there is
    a private key at this path" is worth investigating whether or not git is
    tracking it.
    """
    files = swept_files(repo_root)
    assert len(files) >= FEWEST_CREDIBLE_SWEPT_FILES, (
        f"The sweep read {len(files)} files under {repo_root}, which is too few for this "
        "repository — so the emptiness it is about to assert would be a fact about the sweep "
        "rather than about the tree. Check the root and the exclusion list above."
    )

    committed = [path.relative_to(repo_root) for path in files if holds_private_key(path)]
    assert not committed, (
        "Private key material is committed to the repository:\n"
        + "\n".join(f"  {path}" for path in committed)
        + "\n\nE0-14 criterion 3 and SPEC §9.1: issuer keys are generated per test run rather "
        "than checked in as fixtures. A committed signing key verifies against its own JWKS "
        "perfectly, so nothing else in this suite would notice — and it is the same key in "
        "every image, every fork and every developer's checkout, which makes it a credential "
        "the moment anything trusts this platform."
    )
