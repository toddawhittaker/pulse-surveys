"""`frontend/package.json` gains vitest, jsdom and testing-library — exactly pinned, with a runnable script. Ticket E4-16.

Acceptance criterion 3: "Every added package is exactly pinned and the
lockfile is committed. No automated guard checks arbitrary packages for exact
pins (the only pin-equality guard is scoped to `@types/node`), so the pin
discipline here is enforced by review against the pin rule." Read in full,
that criterion is explicit that no *general* pin guard is being asked for —
review carries that, and CLAUDE.md's pinning rule is what review checks it
against.

**What this module asserts is narrower, and deliberately so.** It checks
exact-pin shape for exactly the three packages this ticket adds — vitest, and
whatever the settled DOM testing convention needs alongside it, jsdom and
`@testing-library/react` — and no other package in the manifest. A general
"every devDependency is exactly pinned" sweep would be a second, wider pin
guard the ticket's own criterion 3 says is not being built, and it would fail
on nothing this ticket controls the moment an unrelated dependency somewhere
in the tree carried a caret. Scoped to these three names, a failure here can
only mean this ticket's own packages are not pinned the way it commits to.

**What this module does not assert:** that the lockfile is committed, or that
it resolves these three packages consistently with the pin. `npm ci` in the
`lint-frontend` job already fails outright on a lockfile that does not match
the manifest it is asked to install from, which is a stronger and more
direct proof than a unit test parsing lockfile JSON would be.

No fixture is used to read the manifest. Per `docs/MISTAKES.md` entry 44, a
guard that can fail is called from the test body, as a plain function, so a
missing or unreadable manifest is a FAILED assertion naming the file rather
than an ERROR at setup that survives the very ticket it is meant to prove.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"

# Exactly the packages E4-16's scope names: vitest as the runner, and the
# settled DOM-testing convention beside it (SETTLED DESIGN item 1 — vitest +
# jsdom + @testing-library/react, all exactly pinned). Nothing else in this
# manifest, or in the root one, is this module's business — see the module
# docstring on why a wider sweep is not what criterion 3 asks for.
FRONTEND_TEST_RUNNER_PACKAGES = ("vitest", "jsdom", "@testing-library/react")

# A pin carries none of these: `^`, `~`, a comparison operator, a wildcard, an
# "or" bar, or whitespace (a hyphen range such as "1.2.3 - 2.0.0" always has
# one). Combined with "leads with a digit", this is the shape CLAUDE.md's
# "pin dependency versions" rule asks of a version string, scoped to reading
# rather than to resolving it — nothing here consults the lockfile or npm's
# own range semantics.
RANGE_SYNTAX = re.compile(r"[\^~<>=*x|]|\s")


def is_exact_pin(version: str) -> bool:
    """Whether `version` is pinned exactly rather than to a range, a wildcard or an alias."""
    return bool(version) and version[0].isdigit() and not RANGE_SYNTAX.search(version)


def read_frontend_manifest() -> dict[str, Any]:
    """`frontend/package.json`, parsed — or an empty mapping if it is absent or not valid JSON.

    Never raises. The caller asserts on the result, which is what keeps a
    missing or broken manifest a failed assertion rather than a setup error
    (`docs/MISTAKES.md` entry 44).
    """
    if not FRONTEND_PACKAGE_JSON.is_file():
        return {}
    try:
        document = json.loads(FRONTEND_PACKAGE_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return document if isinstance(document, dict) else {}


def test_the_frontend_test_runner_packages_are_declared_and_exactly_pinned() -> None:
    """Criterion 3, scoped to exactly the three packages this ticket adds.

    Two things have to be true before a pin is worth reading: the manifest has
    to parse, and each of the three packages has to be declared in
    `devDependencies` at all — a test runner is dev-only. Both are asserted
    before the pin shape is, so a manifest missing all three fails once,
    naming all three, rather than the pin-shape assertion below silently
    iterating over nothing and passing.

    **The mutation this survives:** any of the three pinned with a caret or
    tilde (`^2.1.5`, `~24.0.0`), which is the ordinary shape `npm install`
    writes without `--save-exact`. **The near miss that must stay green:** an
    unrelated package elsewhere in the manifest, or in the root
    `package.json`, carrying a range — this module reads three names only.
    """
    manifest = read_frontend_manifest()
    assert manifest, (
        f"{FRONTEND_PACKAGE_JSON} does not exist, or does not parse as a JSON object. E4-16 "
        "adds a devDependency for each of vitest, jsdom and @testing-library/react there, and "
        "there is nothing to check a pin against until the manifest itself can be read."
    )

    dev_dependencies = manifest.get("devDependencies")
    assert isinstance(dev_dependencies, dict), (
        f"{FRONTEND_PACKAGE_JSON} has no `devDependencies` object (found "
        f"{type(dev_dependencies).__name__ if dev_dependencies is not None else 'nothing'}). "
        "vitest, jsdom and @testing-library/react are dev-only — a test runner does not ship in "
        "the built bundle — so they belong there rather than in `dependencies`."
    )

    missing = [name for name in FRONTEND_TEST_RUNNER_PACKAGES if name not in dev_dependencies]
    assert not missing, (
        f"{FRONTEND_PACKAGE_JSON}'s `devDependencies` declares none of: {missing}.\n"
        "\n"
        "E4-16's settled design: vitest is the runner, and the DOM-testing convention beside it is "
        "jsdom and @testing-library/react, all exactly pinned. Until all three are declared there "
        "is no pin here to check."
    )

    ranged = {
        name: dev_dependencies[name]
        for name in FRONTEND_TEST_RUNNER_PACKAGES
        if not is_exact_pin(str(dev_dependencies[name]))
    }
    assert not ranged, "\n".join(
        [
            "These packages are declared but not pinned exactly (a leading digit, no `^`, `~`, "
            "comparison, wildcard or range):",
            *(f"  {name}: {version!r}" for name, version in ranged.items()),
            "",
            "CLAUDE.md: 'Pin dependency versions and commit lockfiles. No floating ranges, no "
            "unpinned tool versions.' A caret or tilde here resolves to whatever `npm ci` finds in "
            "the committed lockfile today and to something else the day the lockfile is "
            "regenerated, which is the property this rule exists to close off.",
        ]
    )


def test_the_frontend_package_gains_a_test_script_that_runs_vitest() -> None:
    """Scope: "`frontend/package.json` gains `\"test\": \"vitest run\"`" — the exact settled script.

    `vitest run` rather than bare `vitest`: the latter starts vitest's
    interactive watch mode, which does not exit and would hang the
    `lint-frontend` job rather than failing or passing it — a materially
    different and wrong behaviour for a CI script to have, not a cosmetic
    difference in the command.

    **The mutation this survives:** the script committed as `"vitest"`
    (watch mode) rather than `"vitest run"`. **The near miss that must stay
    green:** the script's value carrying extra vitest flags after `run`, such
    as `"vitest run --coverage"`, since the ticket does not forbid running
    with coverage and a test that demanded an exact, unextended string would
    fail the day someone added it — this asserts a prefix rather than
    equality for exactly that reason, while still refusing the watch-mode
    near miss.
    """
    manifest = read_frontend_manifest()
    assert manifest, (
        f"{FRONTEND_PACKAGE_JSON} does not exist, or does not parse as a JSON object, so it "
        "declares no `test` script."
    )

    scripts = manifest.get("scripts")
    assert isinstance(scripts, dict), (
        f"{FRONTEND_PACKAGE_JSON} has no `scripts` object "
        f"(found {type(scripts).__name__ if scripts is not None else 'nothing'})."
    )

    test_script = scripts.get("test")
    settled_shape = isinstance(test_script, str) and re.fullmatch(r"vitest run(\s.*)?", test_script)
    assert settled_shape, (
        f"`frontend/package.json`'s `scripts.test` is {test_script!r}, not `vitest run` (with or "
        "without further flags).\n"
        "\n"
        "E4-16 settles this script so that CI's `npm run test --workspace frontend` (asserted in "
        "test_the_frontend_test_runner_ci_step_exists_and_is_guarded.py) reaches vitest in run "
        "mode rather than hanging in watch mode, doing nothing, or running a different command."
    )
