"""One image, named in two files that must not drift apart — ticket E0-02.

`docker-compose.yml` runs Postgres as the `db` service, and the
`migration-drift` job in `.github/workflows/ci.yml` runs it as a job service.
From E0-04 that job autogenerates `alembic check` against its own Postgres, so
the two have to be the same server: a drift gate run against a Postgres the
project does not deploy is checking the schema against something nobody ships.
The comment above the workflow's `image:` line says exactly this, and nothing
enforced it.

Nothing else notices if they part. ADR 0007 records that the drift "is visible
in a diff on both sides", and that turns out not to be so. Dependabot's
`docker-compose` ecosystem reads `docker-compose.yml` and proposes a bump there,
and its pull request shows that side alone; `github-actions` updates `uses:` and
not a job service's `image:`, so no ecosystem reads the workflow's copy at all.
Change either one and every gate stays green.

This module is neither about the Compose topology that `test_compose_stack.py`
holds nor about `.env.example`, which is why it is its own file: its subject is
two files agreeing about a third thing. E0-03 adds worker and beat, and E0-14
and E0-16 add the mock platforms; cross-file pin agreement lands here.

No job name and no service name is written down below. The test collects every
Postgres image reference in either document, wherever in the structure it sits,
and asserts they are all the same string. Renaming the job costs nothing;
adding a second Postgres that differs fails.

Agreement is checked together with pinning, because agreement on its own would
record the weaker rule as the enforced one. ADR 0007 requires a tag *and* a
digest, and two files that agree on a bare `postgres:17` are agreeing about a
name the registry can repoint under both of them at once.
"""

from pathlib import Path
from typing import Any


def image_references(node: Any) -> set[str]:
    """Every `image:` value anywhere in a parsed document.

    Structural rather than positional, so it finds a Compose service, a
    workflow job service, and a job container alike, and survives any of them
    moving.
    """
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "image" and isinstance(value, str):
                found.add(value)
            found |= image_references(value)
    elif isinstance(node, list):
        for item in node:
            found |= image_references(item)
    return found


def image_repository(reference: str) -> str:
    """The repository part of an image reference, with any tag and digest removed.

    The digest comes off first, and a colon is a tag separator only after the
    last `/`. That second half matters: a registry port looks exactly like a
    tag, so `example.test:5000/postgres` would otherwise reduce to
    `example.test` and stop being recognised as Postgres at all — a silent skip
    rather than a failure, which is the one outcome this module must not have.

    `postgres:17.10-bookworm@sha256:...` and a bare `postgres` both give
    `postgres`; `example.test:5000/postgres:17` gives `example.test:5000/postgres`.
    """
    name = reference.split("@", 1)[0]
    head, separator, tail = name.rpartition("/")
    if ":" in tail:
        tail = tail.rsplit(":", 1)[0]
    return f"{head}{separator}{tail}"


def is_pinned_by_tag_and_digest(reference: str) -> bool:
    """ADR 0007's rule: a reference names both a release and the bytes of one.

    A digest with no tag is pinned but unreadable — nothing says which release a
    human meant. A tag with no digest is readable but not pinned. `postgres` and
    `postgres@sha256:...` both fail; `postgres:17.10-bookworm@sha256:...` passes.
    """
    if "@sha256:" not in reference:
        return False
    return reference.split("@", 1)[0] != image_repository(reference)


def postgres_image_references(document: dict[str, Any]) -> set[str]:
    """Every reference in `document` that names the Postgres image."""
    return {
        reference
        for reference in image_references(document)
        if image_repository(reference).rsplit("/", 1)[-1] == "postgres"
    }


def test_postgres_image_is_pinned_identically_in_compose_and_ci(
    base_compose_path: Path,
    base_compose: dict[str, Any],
    ci_workflow_path: Path,
    ci_workflow: dict[str, Any],
) -> None:
    """The deployed Postgres and the one the drift gate checks against are the same.

    The two "found something at all" assertions below are not ceremony. This
    test compares two sets, and two empty sets are equal — so a workflow whose
    shape changed, or a `db` service that stopped naming an image, would turn
    this into a passing test that checks nothing. That is the precise failure
    mode a regex over `image:` lines would also have had, and it is worth
    spending two assertions to make impossible.
    """
    assert base_compose, (
        f"{base_compose_path} does not exist or declares nothing. E0-02 ships the base "
        "Compose file at the repository root (SPEC §13)."
    )
    assert ci_workflow, (
        f"{ci_workflow_path} does not exist or parsed to nothing. The CI pipeline is what "
        "makes the §14.2 definition of done enforceable, so it existing is a precondition "
        "of this test meaning anything."
    )

    in_compose = postgres_image_references(base_compose)
    in_workflow = postgres_image_references(ci_workflow)

    assert in_compose, (
        f"{base_compose_path} names no Postgres image, so there is nothing for the "
        "migration-drift job to be checked against. E0-02 runs Postgres as the `db` "
        "service (SPEC §7.2)."
    )
    assert in_workflow, (
        f"{ci_workflow_path} names no Postgres image. The migration-drift job runs one as "
        "a job service, so finding none means this test has quietly stopped checking "
        "anything rather than that the two agree."
    )

    assert in_compose == in_workflow, (
        f"The Postgres image differs between the two files. {base_compose_path.name} names "
        f"{sorted(in_compose)}; {ci_workflow_path.name} names {sorted(in_workflow)}. From "
        "E0-04 the migration-drift job autogenerates `alembic check` against its own "
        "Postgres, so a difference here checks the schema against a server the project "
        "does not deploy. No Dependabot ecosystem reads the workflow's copy, so nothing "
        "else is going to tell you: move both together or neither."
    )

    unpinned = sorted(
        reference
        for reference in in_compose | in_workflow
        if not is_pinned_by_tag_and_digest(reference)
    )

    assert not unpinned, (
        f"The Postgres image is not pinned by both tag and digest: {unpinned}. ADR 0007 "
        "requires both, and agreement alone is the weaker rule: a tag is mutable, so two "
        "files naming the same `postgres:17` agree about a name whose content the registry "
        "can change under both of them at once — which is the thing pinning exists to "
        "prevent. The tag says which release a human meant; the digest says which bytes "
        "actually run."
    )
