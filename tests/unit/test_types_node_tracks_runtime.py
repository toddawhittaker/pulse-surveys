"""`@types/node`, the build image and the Node CI runs are one major — E1-02.

`.github/workflows/ci.yml` pins `NODE_VERSION`, and every Node job — tsc, eslint,
`npm audit`, the licence scan, Playwright, the production build — runs on that
runtime. `@types/node` is what tells `tsc` which standard-library surface exists.
Nothing tied the two together, and Dependabot #81 proposed `@types/node`
20.19.43 → 26.2.0 with the whole pipeline green: `tsc` would have accepted
`node:` APIs that the Node 20 the pipeline then ran did not have, and the
failure would have arrived at run time in the e2e job or later, as a missing
export rather than as a type error.

**The third document is `backend/Dockerfile`, and it was the gap.** Its
`FROM node:` stage is the Node that builds the frontend bundle the image ships,
and until this guard read it nothing did. Dependabot's `docker` ecosystem
watches `/backend` and proposed #132, node 20.20.2 → 26.8.1, on its own: every
gate was green because every gate ran Node 20, and merging it alone would have
built the shipped bundle on a runtime no check in this repository exercises.
That is #81 again from the other side — the types and the runtime were tied and
the image was not, so the pair that had a guard stayed together while the third
walked off.

This is `test_image_pins_agree.py`'s subject in another set of files: documents
naming one version of one thing, with no ecosystem reading more than one of
them. The `npm` ecosystem reads `package.json` and proposes the bump;
`github-actions` updates `uses:` lines and not an `env:` value, so nothing reads
`NODE_VERSION` at all; `docker` reads `FROM` lines and nothing else. Change any
one side and, without this test, every gate stays green.

The triage record's "done when" (`docs/tickets/deps-triage-2026-08-24.md`, entry
4) asks for exactly two things: this guard, and the `dependabot.yml` ignore that
keeps `@types/node` majors from arriving on their own. The ignore is the coverage
reduction and this is what makes it safe — with the majors tied, the bump arrives
when `NODE_VERSION` moves and is reviewed as the runtime move it is. The image
has no such ignore and needs none: a lone image bump is not silently merged, it
is loudly refused here.

**No file name, job name or dependency section is written into the comparison.**
Every `package.json` in the repository is read, and the pin is collected wherever
in the document it sits — `dependencies`, `devDependencies`, a workspace member's
own manifest — so the root npm workspace E1-02 lands (ADR 0083) does not need
telling about, and neither does the E1-04 scaffold moving the pin into
`frontend/package.json`. `NODE_VERSION` is collected the same way out of the
parsed workflow, so it may sit in the workflow's `env:`, a job's, or a step's.
Every Dockerfile in the repository is read the same way, so a second Node stage
— a frontend image of its own, a tools stage — joins the comparison by existing
rather than by being added to a list here.

**Only the major is compared.** `@types/node` publishes on its own patch cadence
and pinning it to the runtime's patch would mean a lockfile change every time
either moves; the guarantee that matters is that the type surface is the one the
runtime has, and that is a major-version property.

**A version this cannot read fails rather than being skipped.** `lts/*` and `20.x`
are legal `NODE_VERSION` values, `^20.19.43` is a legal npm range and
`node:lts-bookworm-slim` is a legal image tag, and none of them has a major this
test can compare honestly. Guessing one would make the agreement it reports
weaker than the one it claims.
"""

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# The dependency whose major must follow the runtime's.
TYPES_NODE = "@types/node"

# The workflow variable every Node job's `node-version:` reads.
NODE_VERSION = "NODE_VERSION"

# Installed trees are not the repository's declarations, and there are hundreds
# of manifests under one.
VENDORED = "node_modules"

# What a Dockerfile is called. `Dockerfile` is what this repository uses; the
# other two spellings are the conventional ones for a second file beside it, and
# they cost nothing to look for.
DOCKERFILE_NAMES = ("Dockerfile", "Dockerfile.*", "*.Dockerfile")

# A build stage on the Node image. `FROM`, any number of `--platform=`-style
# flags, an optional registry and namespace, then `node:` and the tag — which
# ends at the digest `@sha256:...` that ADR 0007 requires beside it, or at the
# whitespace before `AS <stage>`. Written for the line
# `backend/Dockerfile` actually holds and for the digest form Dependabot writes
# back into it, and case-insensitive on the keyword alone, because a Dockerfile
# instruction is case-insensitive and an image name is not.
NODE_STAGE = re.compile(
    r"^\s*(?i:FROM)\s+(?:--\S+\s+)*(?:[^\s/]+/)*node:(?P<tag>[^@\s]+)",
    re.MULTILINE,
)

# A version this test can take a major from: digits, optionally with more
# dot-separated numbers after them. `20`, `20.19`, `20.19.43`. Deliberately not
# `^20.19.43`, `>=20`, `20.x` or `lts/*` — see the module docstring.
PLAIN_VERSION = re.compile(r"^\d+(\.\d+)*$")


def package_manifests() -> list[Path]:
    """Every `package.json` this repository declares, vendored trees excluded."""
    return sorted(
        path
        for path in REPO_ROOT.rglob("package.json")
        if path.is_file() and VENDORED not in path.relative_to(REPO_ROOT).parts
    )


def dockerfiles() -> list[Path]:
    """Every Dockerfile this repository declares, vendored trees excluded.

    Collected the way the manifests above are, and for the same reason: the
    comparison names no file, so a Node stage added in a new image is compared
    because it exists rather than because someone remembered this list.
    """
    return sorted(
        {
            path
            for pattern in DOCKERFILE_NAMES
            for path in REPO_ROOT.rglob(pattern)
            if path.is_file() and VENDORED not in path.relative_to(REPO_ROOT).parts
        }
    )


def version_in_tag(tag: str) -> str:
    """The version an image tag opens with. `26.8.1-bookworm-slim` gives `26.8.1`.

    A Node tag is a version followed by an optional variant — `-bookworm-slim`,
    `-alpine` — so the version is everything before the first hyphen. A tag with
    no version there (`lts-bookworm-slim`, `latest`) is returned unchanged, and
    then fails the readability assertion below naming itself. Returning the tag
    rather than `None` is what keeps that failure one assertion instead of two,
    and it means this function never has to guess.
    """
    return tag.split("-", 1)[0]


def values_under(node: Any, key: str) -> set[str]:
    """Every value stored under `key` anywhere in a parsed document.

    Structural rather than positional, the way `test_image_pins_agree.py` collects
    an `image:`. It finds a pin in `dependencies` or in `devDependencies`, in the
    root manifest or in a workspace member's, and a `NODE_VERSION` in the
    workflow's `env:` or in a job's — and it goes on finding them when any of
    those move.

    Values are stringified because YAML 1.1 reads an unquoted `20` as an integer,
    and a guard that ignored the unquoted spelling would answer "found nothing"
    over a workflow that pins the runtime perfectly well.
    """
    found: set[str] = set()
    if isinstance(node, dict):
        for name, value in node.items():
            if name == key and isinstance(value, str | int | float):
                found.add(str(value))
            found |= values_under(value, key)
    elif isinstance(node, list):
        for item in node:
            found |= values_under(item, key)
    return found


def major_of(version: str) -> str:
    """The leading component of a plain version. `20.19.43` and `20` both give `20`."""
    return version.split(".", 1)[0]


def test_the_node_types_the_build_image_and_the_ci_runtime_are_one_major(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """The types `tsc` checks, the image that builds, and the runtime CI runs agree.

    The four "found something at all" assertions below are the load-bearing part
    rather than ceremony. This test compares three sets of majors, and empty sets
    are equal to each other — so a manifest that stopped declaring the pin, a
    workflow that renamed its variable, a Dockerfile whose Node stage moved out of
    reach of the pattern, or a reader that went blind would all turn this into a
    passing test that checks nothing, which is the exact shape of the defect it
    exists to catch.

    **The mutations this survives, in every direction.** Move `@types/node` to a
    26.x pin while `NODE_VERSION` stays `'20'`, which is Dependabot #81 and was
    green; move `NODE_VERSION` to `'22'` while the pin stays, which is the runtime
    upgrade that forgets its types; or move the Dockerfile's `FROM node:` stage to
    26 while both stay at 20, which is Dependabot #132 and was also green. Any of
    them fails here and says which side moved. **The near miss that must stay
    green:** a patch or minor bump on any side — `@types/node` 20.19.43 → 20.20.0,
    `NODE_VERSION` `'20'` → `'20.19'`, the image 20.20.2 → 20.21.0 — since the tie
    is between majors and nothing else.
    """
    manifests = package_manifests()
    assert manifests, (
        f"No `package.json` was found under {REPO_ROOT}. This repository's Node toolchain — the "
        "Playwright runner, tsc, eslint, the licence scanner — is declared in one, so finding "
        "none means this test has gone blind rather than that the pin is fine."
    )

    pinned = {
        path: found
        for path in manifests
        if (found := values_under(json.loads(path.read_text(encoding="utf-8")), TYPES_NODE))
    }
    declared = {version for found in pinned.values() for version in found}
    assert declared, "\n".join(
        [
            f"No `package.json` in this repository declares `{TYPES_NODE}`:",
            *(f"  {path.relative_to(REPO_ROOT)}" for path in manifests),
            "",
            "`tsc` then types `node:` imports from whatever `@types/node` the resolver reaches, or "
            "from none at all, and this test has nothing to compare against `NODE_VERSION`. If the "
            "dependency has genuinely gone, so has the reason for this guard, and removing it is a "
            "decision for the ticket that removes the dependency.",
        ]
    )

    runtime = values_under(ci_workflow, NODE_VERSION)
    assert ci_workflow and runtime, "\n".join(
        [
            f"{ci_workflow_path} declares no `{NODE_VERSION}` anywhere, or did not parse.",
            "",
            "Every Node job in that workflow feeds this value to `actions/setup-node`, so a "
            "workflow without it runs whatever Node the runner image happens to ship — an "
            "unpinned runtime, which CLAUDE.md's pinning rule is about, and a runtime this test "
            "cannot name. Renaming the variable is fine; this test needs telling about the new "
            "name in the same change.",
        ]
    )

    images = sorted(dockerfiles())
    assert images, (
        f"No Dockerfile was found under {REPO_ROOT}. The frontend bundle this project ships is "
        "built in one, so finding none means this test has gone blind rather than that the "
        "image is fine."
    )

    staged = {
        path: {
            version_in_tag(match.group("tag"))
            for match in NODE_STAGE.finditer(path.read_text(encoding="utf-8"))
        }
        for path in images
    }
    built = {version for found in staged.values() for version in found}
    assert built, "\n".join(
        [
            "No Dockerfile in this repository has a `FROM node:` stage:",
            *(f"  {path.relative_to(REPO_ROOT)}" for path in images),
            "",
            "One of them builds the frontend bundle the runtime image ships, on a Node this test "
            "then has nothing to compare against `NODE_VERSION` — which is the state Dependabot "
            "#132 was proposed into. If the stage has genuinely gone, so has the reason for this "
            "part of the guard, and removing it is a decision for the ticket that removes the "
            "stage. If it is still there, this pattern has stopped seeing it: an `ARG` holding the "
            "image name, or a base image renamed, reads as absence here and must not.",
        ]
    )

    unreadable = sorted(
        version for version in declared | runtime | built if not PLAIN_VERSION.match(version)
    )
    assert not unreadable, "\n".join(
        [
            "These versions have no major this test can compare honestly:",
            *(f"  {version}" for version in unreadable),
            "",
            f"`{TYPES_NODE}` pins: {sorted(declared)}",
            f"`{NODE_VERSION}` values: {sorted(runtime)}",
            f"`FROM node:` tags: {sorted(built)}",
            "",
            "A range (`^20.19.43`, `>=20`), a wildcard (`20.x`), an alias (`lts/*`) or a moving "
            "image tag (`lts-bookworm-slim`, `latest`) resolves to a major at install or pull time "
            "rather than declaring one, so the agreement this test would report over it is weaker "
            "than the agreement it claims. CLAUDE.md pins dependency versions, CI runtimes and "
            "images; every side of this comparison is supposed to be exact.",
        ]
    )

    typed = {major_of(version) for version in declared}
    running = {major_of(version) for version in runtime}
    building = {major_of(version) for version in built}
    assert typed == running == building, "\n".join(
        [
            "The Node types, the image that builds the frontend, and the runtime CI runs are not "
            "all the same major.",
            f"  typed:    {sorted(typed)} from {sorted(declared)} in "
            f"{sorted(str(path.relative_to(REPO_ROOT)) for path in pinned)}",
            f"  running:  {sorted(running)} from {sorted(runtime)} in {ci_workflow_path.name}",
            f"  building: {sorted(building)} from {sorted(built)} in "
            f"{sorted(str(path.relative_to(REPO_ROOT)) for path, found in staged.items() if found)}",
            "",
            f"`{TYPES_NODE}` is what tells `tsc` which standard library exists. A major ahead of "
            "the runtime type-checks against APIs that are not there and the pipeline stays green "
            "— Dependabot #81 proposed exactly that, 20 to 26, and nothing went red. A major "
            "behind refuses code the runtime supports. The `FROM node:` stage is the Node that "
            "builds the bundle the image ships: a major ahead of CI ships a bundle built by a "
            "toolchain no gate here has run, which is Dependabot #132, and it was green too.",
            "",
            "No Dependabot ecosystem reads more than one of these files: `npm` reads the manifest "
            "and proposes the pin bump, `docker` reads the `FROM` lines and proposes the image "
            "bump, and `github-actions` updates `uses:` lines and not an `env:` value, so nothing "
            f"reads `{NODE_VERSION}` at all. Move all three together, in the change that decides "
            "the runtime — which is what the `@types/node` semver-major ignore in "
            "`.github/dependabot.yml` exists to make happen, and what this assertion makes "
            "unavoidable for the image.",
        ]
    )
