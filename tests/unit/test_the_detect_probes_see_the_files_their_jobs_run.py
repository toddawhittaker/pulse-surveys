"""Each `detect` probe sees the file its own job runs — E0-36 findings 1 and 2, E0-40, E1-04, E2-13.

The `detect` job probes the tree and emits booleans; each gate job runs its real
steps only when its boolean is true, and prints a `::notice::` otherwise (ADR
0002). **A probe that answers false over a tree that has the thing therefore turns
its gate off and reports `success`** — not `skipped`, not `failure` — while the
work it names never runs.

E0-36 found two probes that could not see what their jobs needed: `evals` globbed
`tests/evals/**/*.py` without `shopt -s globstar`, so `**` degraded to a single
`*`; `e2e` used a flat glob that did not descend. Both were repaired to name the
file, or to use `find`, which cannot degrade on a shell option nobody sets.

**E0-40 is the third instance, and the first one that was live.** PR #61 committed
this repository's first `package.json`, `package-lock.json` and TypeScript
(`playwright.config.ts`, `tests/e2e/*.spec.ts`) — at the repository *root*. Every
Node-facing gate went on probing `frontend/package.json`, which does not exist and
is not due until E1: `npm audit`, the licence scan, `tsc` and `eslint` all
reported green over a tree they never read. So the probe is split to tell the
truth about where Node code lives:

- **`node`** — `package.json` at the repository root. It gates `npm audit` and the
  licence scan, both of which run at the root. It gated `tsc` and `eslint` too
  until E1-04, which is the ticket that lands the application those two check:
  ADR 0002 makes removing a tolerance an acceptance criterion of the ticket that
  lands the code, so those steps now run unconditionally and consult no probe.
  `tests/unit/test_the_frontend_gates_stopped_being_tolerant.py` is where that is
  asserted.
- **`frontend` is gone, and E1-04 is what removed it.** It named the frontend
  package's `build` script and gated the production build and the bundle budget
  while both were still legitimately waiting for the E1 scaffold. E1-04 lands the
  scaffold and makes all four frontend gates enforcing, so the last thing reading
  that boolean stopped reading it — and an emitted boolean nothing consults is a
  probe whose wrongness has no symptom, which is why it is withdrawn in the same
  change rather than left emitting.
- **`evals` is gone, and E2-13 is what removed it.** It asked whether
  `tests/evals/runner.py` existed, and the `evals` job's steps waited on it while
  that file was still to be written. E2-12 committed the runner and made the job
  enforcing: the tolerance clause went, because ADR 0002 makes removing one an
  acceptance criterion of the ticket that lands the code, and the job now gates on
  E0-38's changed-paths classification instead. The output stayed behind, because
  withdrawing it means editing this closed set and that was on the other side of
  the heavy lane's test wall. So since E2-12 the probe has had no reader at all,
  which is the shape this module's own history condemns twice over.
- **`e2e` is gone.** PR #61 made the Playwright gate unconditional on the specs
  being present, so nothing has consumed that output since; an emitted boolean
  nothing reads is a probe whose wrongness has no symptom.

**The cases plant their own trees and none of them reads this repository.** The
one surviving probe answers about a file that exists here today, and most of the
trees below hold files that this checkout also holds — so a battery that read the
real tree would assert the state of the checkout rather than the logic of the
probe, and would report every withdrawn probe as correctly absent for no better
reason than that nobody planted anything.

**Executed, not read.** The probe is pulled out of the parsed workflow, run under
`bash` with `GITHUB_OUTPUT` pointed at a temp file, and judged by what it emits. A
test that read the condition and objected to it would be asserting a mechanism,
and the spelling is not this module's to choose: `[ -f package.json ]` and
`test -f ./package.json` are the same answer to the same question and both pass
everything below.

**The wiring is asserted beside the probe**, because the probe being right buys
nothing on its own. A `node` output that no gate reads leaves `npm audit`
answering to `frontend/package.json` exactly as it does today, with this module
green — behaviour shipped with nothing asserting it, which is `docs/MISTAKES.md`
entry 2. So there are two halves here: what the probe emits over a planted tree,
and which probe each Node-facing gate waits on.

**And one more, which is the same subject through a different door.** A gate can
also report success over work that ran and did not pass: `playwright.config.ts`
retried once on CI, so a spec that failed and passed on the retry exited zero and
the e2e gate went green over a failing test — CLAUDE.md's rule against marking a
test flaky, arrived at through a config option rather than a marker. E0-40
decision 3 sets `retries: 0` and replaces `trace: 'on-first-retry'`, which needed
a retry to fire, with `trace: 'retain-on-failure'`. The guard for it is a text
assertion at the foot of this module rather than a module of its own: the ticket
allows one new test file and it is spent on the invariant-gate guard, and of the
files this ticket may touch, this is the one whose subject is a gate reporting
success over a check that did not honestly pass.

**E1-04 is the fourth ticket in this file's history, and it removes rather than
repairs.** It lands the frontend scaffold and makes all four frontend gates
enforcing, which takes the `frontend` probe's last two readers away — so the probe
goes, its cases become cases about a probe that must not be there, and the two
recipes carrying the same condition in the `Makefile` lose it too. The direction
matters: every earlier instance in this file was a probe that had gone blind, and
the repair each time was to make it see. A probe with nothing left to decide is the
same hazard reached from the other end, because the honest answer to a question
nobody asks is not to answer it.

**E2-13 is the fifth ticket in this file's history, and it removes for the second
time.** `evals` is the last probe to lose its readership, and the direction is
E1-04's rather than E0-36's: nothing had gone blind, the question simply stopped
being asked. What is left after it is a single probe, `node`, guarding two
supply-chain gates — and the eval trees stay planted below for the reason the
frontend trees did, because a tree the withdrawn probe would have answered `true`
over is the only tree that catches it outliving its readers.

**The probe has a second copy, and the mutation battery found it unguarded.** The
`Makefile` carries the same condition for `lint`, `typecheck`, `audit` and
`licenses`, so that `make ci` and the workflow agree; reverting either copy to
`frontend/package.json` while the other holds the root left the whole suite green.
That is `docs/MISTAKES.md` entry 13 — a hazard worked around in one of the two
places facing it — and the guard for it is here rather than in
`test_the_docker_gate_and_the_makefile_run_the_same_checks.py`, whose subject is
the image gate and `.dockerignore` rather than the node probe.

**And `tsconfig.json`, which is the founding defect one file over.** `tsc
--noEmit` over a config whose `include` does not reach the specs exits 0 having
read nothing — the same green-over-unread-work shape as a probe answering false,
proved by the battery, and caught today only as a side effect of eslint's typed
project service. So the include list is asserted to cover the files the checker
exists to read.

This is a separate module from `test_the_aggregate_ci_check_sees_an_upstream_failure.py`
even though both execute a `run:` block out of the same workflow, because shared
machinery is not a shared subject: that module's argument is about GitHub's
`needs` result semantics, and a filesystem probe battery inside it would make its
docstring answer two questions at once.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, NamedTuple

import pytest

DETECT_JOB = "detect"

# The probes the `detect` job emits, as E0-40 settles them and E1-04 and E2-13
# narrow them. This is a closed set: every case below compares the whole mapping,
# so an output that lingers after the gate reading it is gone fails as loudly as
# one that never arrives.
NODE = "node"
FRONTEND = "frontend"
EVALS = "evals"
PROBES = (NODE,)

# Probes that were emitted and are not any more. Named here rather than merely left
# out of `PROBES`, so that the failure a lingering probe produces says which one it
# is.
#
# `e2e` went in E0-40: PR #61 made the Playwright gate unconditional on the specs
# being present, and nothing had consumed the boolean since. `frontend` goes in
# E1-04 for the same reason arrived at from the other direction — its two
# consumers, the production build and the bundle budget, stop being tolerant, so
# the question it asks is no longer asked by anything. `evals` goes in E2-13, and
# it is the one that was left emitting after its reader had already gone: E2-12
# landed the runner, made the job enforcing and deleted the clause that read this
# boolean, and the output outlived it by a ticket.
WITHDRAWN = ("e2e", FRONTEND, EVALS)

# A `name=value` line as the probe writes it into `$GITHUB_OUTPUT`.
EMITTED = re.compile(r"^(?P<name>[A-Za-z0-9_-]+)=(?P<value>.*)$")

# The two frontend manifests the `frontend` probe used to tell apart: the
# workspace stub E1-02 landed, which exists so the repository has one lockfile and
# one resolution, and the scaffold E1-04 fills, which is the first tree with
# something to build. **They are kept now that the probe is gone, and they are the
# sharpest cases in the table.** Every case compares the whole emitted mapping, so
# a tree with a buildable frontend in it — the one tree a lingering `frontend`
# probe would answer `true` over — is where a probe that outlived its readers is
# caught rather than merely reported missing from an `outputs:` block.
FRONTEND_MANIFEST = "frontend/package.json"

WORKSPACE_STUB = json.dumps(
    {"name": "@pulse-surveys/frontend", "version": "0.0.0", "private": True}, indent=2
)

SCAFFOLD_WITH_A_BUILD = json.dumps(
    {
        "name": "@pulse-surveys/frontend",
        "version": "0.0.0",
        "private": True,
        "scripts": {"dev": "vite", "build": "tsc -b && vite build"},
    },
    indent=2,
)

# One file to plant: a path, or a `(path, content)` pair where the probe reads
# what the file says rather than counting that it is there.
PlantedFile = str | tuple[str, str]

# Every case is a planted tree and the whole answer the probe must give over it.
# The whole answer rather than the one key each case is about, so that a probe
# which turns `node` on whenever `frontend` is on cannot pass by being right about
# the key the case is named for.
#
# The first case is the one that makes the rest mean anything: over a tree with
# nothing in it every probe must answer false. A probe that answered true to
# everything would satisfy every other case here perfectly.
#
# **The eval trees are kept now that `evals` is gone, on the same argument the
# frontend trees are kept on.** A tree holding `tests/evals/runner.py` is the one
# tree in this table over which a surviving copy of that probe would answer
# `true`, so it is where a probe that outlived its reader is caught as a wrong
# *answer* rather than merely reported missing from an `outputs:` block. Deleting
# those rows along with the probe would take the catch away with it.
CASES: tuple[tuple[str, tuple[PlantedFile, ...], dict[str, str]], ...] = (
    (
        "an empty repository",
        (),
        {NODE: "false"},
    ),
    (
        "the tree PR #61 left: a manifest, a lockfile and TypeScript at the root",
        (
            "package.json",
            "package-lock.json",
            "playwright.config.ts",
            "tests/e2e/lms/launch.spec.ts",
        ),
        {NODE: "true"},
    ),
    (
        "a root package manifest and nothing else",
        ("package.json",),
        {NODE: "true"},
    ),
    (
        "the workspace stub E1-02 landed: a frontend manifest with nothing to build",
        ((FRONTEND_MANIFEST, WORKSPACE_STUB),),
        {NODE: "false"},
    ),
    (
        "the E1-04 scaffold: a frontend manifest that declares a build",
        ((FRONTEND_MANIFEST, SCAFFOLD_WITH_A_BUILD),),
        {NODE: "false"},
    ),
    (
        "the tree E1-02 left: the root toolchain and the workspace stub beside it",
        ("package.json", (FRONTEND_MANIFEST, WORKSPACE_STUB)),
        {NODE: "true"},
    ),
    (
        "both, once the E1-04 scaffold fills the workspace member",
        ("package.json", (FRONTEND_MANIFEST, SCAFFOLD_WITH_A_BUILD)),
        {NODE: "true"},
    ),
    (
        "a frontend manifest that is not a manifest at all",
        (FRONTEND_MANIFEST,),
        {NODE: "false"},
    ),
    (
        "a package manifest in some other subdirectory",
        ("tools/package.json",),
        {NODE: "false"},
    ),
    (
        "the eval runner E2-12 committed, which no probe answers for any more",
        ("tests/evals/__init__.py", "tests/evals/runner.py"),
        {NODE: "false"},
    ),
    (
        "an eval set in a subdirectory beside the runner",
        ("tests/evals/__init__.py", "tests/evals/runner.py", "tests/evals/validity/cases.py"),
        {NODE: "false"},
    ),
    (
        "an eval directory holding no Python at all",
        ("tests/evals/README.md",),
        {NODE: "false"},
    ),
    (
        "e2e specs, which no probe answers for any more",
        ("tests/e2e/lms/launch.spec.ts", "tests/e2e/idp/login.spec.ts"),
        {NODE: "false"},
    ),
    (
        "an e2e directory holding no specs",
        ("tests/e2e/README.md",),
        {NODE: "false"},
    ),
)

# ---------------------------------------------------------------------------
# The wiring half: which probe each Node-facing gate waits on.
#
# The tools are searched for by the command that runs them rather than by the job
# or step that holds them, because the job names are not this ticket's to settle
# and a search keyed on one would report a clean pipeline over a renamed job
# (`docs/MISTAKES.md` entry 35 — the control's inventory must come from somewhere
# the guarded structure cannot shrink). Each pattern is required to match
# something before its verdict counts.
# ---------------------------------------------------------------------------
RUNS_AT_THE_ROOT = {
    "npm audit": re.compile(r"\bnpm\s+audit\b"),
    "the npm licence scan": re.compile(r"\blicense-checker"),
    "tsc": re.compile(r"\btsc\b"),
    "eslint": re.compile(r"\beslint\b"),
}

# The two of those four that still *wait* on the probe, which from E1-04 is a
# narrower set than the four that run at the root.
#
# `tsc` and `eslint` were tolerant gates: they ran when a probe said there was
# TypeScript to read and printed a notice when it did not. E1-04 is the ticket that
# lands the application they check, and ADR 0002 makes removing a tolerance an
# acceptance criterion of the ticket that lands the code — so those two now run
# unconditionally, and `tests/unit/test_the_frontend_gates_stopped_being_tolerant.py`
# asserts that they consult no probe at all. `npm audit` and the licence scan are
# in a job this ticket does not touch and keep the guard they have.
#
# The wider set above is still used, for the short-circuit rule and as the canary:
# each of the four has to be findable in the workflow before any verdict about it
# counts.
WAITS_ON_THE_NODE_PROBE = {
    tool: RUNS_AT_THE_ROOT[tool] for tool in ("npm audit", "the npm licence scan")
}

# `needs.detect.outputs.<name>`, wherever it appears — a step's `if:`, or a `${{ }}`
# interpolation inside the script itself. The licence scan reads its probe the
# second way, in a shell `if`, so a reader that looked only at `if:` conditions
# would report that gate as consulting nothing at all.
DETECT_OUTPUT = re.compile(r"needs\.detect\.outputs\.([A-Za-z0-9_-]+)")

# E0-38's classification, which the supply-chain gate's steps also carry. Which
# steps must keep it is derived rather than listed — see the test at the foot of
# this module.
CHANGED_JOB = "changed"
INERT_OUTPUT = "needs.changed.outputs.inert"

FRONTEND_DIRECTORY = re.compile(r"\bcd\s+frontend\b")

SHELL_COMMENT = re.compile(r"#.*$")

# ---------------------------------------------------------------------------
# E0-40 decision 3: the Playwright gate stops passing over a spec that failed.
#
# Read as text. There is no TypeScript parser in this suite and adding one to
# assert two settings would be a dependency bought with a ticket's worth of
# reasoning, so these are line searches over the config's statements — with the
# `//` comment lines dropped first, because the comment this ticket falsifies
# quotes the setting it explains and a search over the whole file could not tell
# the quotation from the setting.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYWRIGHT_CONFIG = REPO_ROOT / "playwright.config.ts"

RETRIES = re.compile(r"\bretries\s*:")
NO_RETRIES = re.compile(r"^retries\s*:\s*0\s*,?$")

TRACE = re.compile(r"\btrace\s*:")
TRACE_ON_FAILURE = re.compile(r"^trace\s*:\s*'retain-on-failure'\s*,?$")

# The line as it stands and the line the ticket asks for, copied whole rather
# than retyped — `docs/MISTAKES.md` entry 3, whose third incident was a pattern
# that matched nothing and passed against the exact text it existed to catch. The
# searches above are run against both before they are trusted against the file,
# so a pattern that has gone blind says so instead of reporting a compliant
# config.
RETRY_LINE_BEFORE = "  retries: process.env.CI ? 1 : 0,"
RETRY_LINE_AFTER = "  retries: 0,"
TRACE_LINE_BEFORE = "    trace: 'on-first-retry',"
TRACE_LINE_AFTER = "    trace: 'retain-on-failure',"

# ---------------------------------------------------------------------------
# The probe's second copy. CLAUDE.md: run `make ci` before pushing, and where it
# disagrees with the workflow the workflow is right and the Makefile is the bug.
# A Makefile that probes a directory which does not exist does not report a bug —
# it prints its skip notice and exits 0, so `make ci` is green over four checks it
# never ran and the disagreement surfaces on someone else's pull request.
# ---------------------------------------------------------------------------
MAKEFILE = REPO_ROOT / "Makefile"

# The four node-facing targets, each with the tool that makes it one. The tool
# patterns are the same objects the workflow half uses rather than copies of them,
# so the two halves of this module cannot come to disagree about what counts as a
# node gate (`docs/MISTAKES.md` entry 19).
MAKEFILE_NODE_TARGETS = {
    "lint": "eslint",
    "typecheck": "tsc",
    "audit": "npm audit",
    "licenses": "the npm licence scan",
}

# The target that used to name the other manifest, and now must name none.
#
# **It was this module's control until E1-04**, on `docs/MISTAKES.md` entry 35's
# rule that a guard which only ever reports absence cannot say what it can see: the
# four node targets are asserted to name no qualified manifest, and a reader blind
# to qualified paths would report them all clean over a Makefile that was entirely
# wrong. `frontend-build` was the subject that certainly had one.
#
# E1-04 takes the probe out of that recipe — the production build and the bundle
# budget stop being tolerant — so the control moves to a sample instead, copied
# whole out of the recipe as it stood. The sample is the better control anyway,
# because it goes on exercising the reader after the tree has stopped containing
# an example, which is the state every removed tolerance leaves behind.
MAKEFILE_FRONTEND_TARGET = "frontend-build"

# The condition E1-04 deletes, copied whole out of the `frontend-build` recipe —
# the line it begins on included, `docs/MISTAKES.md` entry 3. `qualified_manifests`
# is run over this before it is trusted over the Makefile, so a reader that has
# gone blind says so instead of reporting four clean targets.
MAKEFILE_PROBE_AS_IT_STOOD = (
    "\t@if [ -f frontend/package.json ] && "
    'grep -Eq \'"build"[[:space:]]*:[[:space:]]*"\' frontend/package.json; then \\'
)

# What that recipe must run once the branch is gone, found by the command rather
# than by the line. Both must be there: a recipe that lost its tolerance and its
# work together satisfies every "no longer probes" assertion perfectly.
MAKEFILE_PRODUCTION_BUILD = re.compile(r"\bnpm\s+run\s+build\b")
MAKEFILE_BUNDLE_BUDGET = re.compile(r"\bcheck_bundle_size\.py\b")

# The frontend workspace scripts the fast gate runs in `.github/workflows/ci.yml`,
# which `make ci` has to run too. CLAUDE.md: `make ci` runs the same gates as the
# workflow, and where the two disagree the workflow is right and the Makefile is
# the bug — a disagreement whose whole cost falls on the person told to run `make
# ci` before pushing, since their green is over checks that never ran.
MAKEFILE_WORKSPACE_CHECKS = {
    "the frontend type check": re.compile(r"\bnpm\s+run\s+typecheck\b"),
    "the frontend lint": re.compile(r"\bnpm\s+run\s+lint\b"),
}

# The target `make ci` is, and the one every gate has to be reachable from. A
# recipe nothing runs is not a gate.
MAKEFILE_PIPELINE_TARGET = "ci"

# A target line: a name at the start of a line, then a colon that is not `:=`,
# then its prerequisites. `.PHONY` and the variable assignments above the targets
# are excluded by the leading character class.
MAKE_TARGET = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s*:(?!=)(?P<prerequisites>[^#]*)")

# ---------------------------------------------------------------------------
# The security review's MEDIUM, one class out from the probe split.
#
# `npx eslint` on a clean clone does not fail. npm 10's npx downloads the package
# and runs it, so a Makefile target that calls `npx` without installing the
# lockfile first executes `eslint@latest` and `typescript@latest` — resolved at
# run time, unpinned, with no integrity check — which is CLAUDE.md's pin rule
# defeated by a tool being helpful. `node_modules` is gitignored, so the clean
# clone is the ordinary case rather than the edge one.
#
# `.github/workflows/ci.yml` runs `npm ci` before every `npx` under the same
# condition. The Makefile's copies of those gates did not, which is
# `docs/MISTAKES.md` entry 13 again in the same pair of files this module already
# guards for the probe itself.
# ---------------------------------------------------------------------------
NPX_CALL = re.compile(r"\bnpx\b")
NPM_INSTALL = "npm ci"

# Any mention of the manifest, with whatever path leads to it. The prefix is
# captured rather than the whole path matched, because what is asserted is that
# every mention is the root one — an assertion about the absence of a prefix
# cannot be written as a search for a spelling.
MANIFEST_MENTION = re.compile(r"(?P<prefix>[A-Za-z0-9_./-]*)package\.json")

# ---------------------------------------------------------------------------
# E0-40 decision 2: the committed TypeScript gets a toolchain that reads it.
#
# `tsc --noEmit` over a config whose `include` reaches nothing exits 0. It is this
# ticket's own defect in another file — a checker reporting success over a tree it
# never read — and it is quieter, because there is no probe to inspect and no
# notice printed in place of the work.
# ---------------------------------------------------------------------------
TSCONFIG = REPO_ROOT / "tsconfig.json"
E2E_TREE = REPO_ROOT / "tests" / "e2e"
PLAYWRIGHT_CONFIG_NAME = "playwright.config.ts"

# A whole-line `//` comment. `tsconfig.json` is JSONC — TypeScript accepts
# comments and the file carries a nine-line one explaining what it covers — and
# `json` does not, so those lines are blanked before the parse. Blanked rather
# than removed, so a parse error still names the line it is on.
LINE_COMMENT = re.compile(r"^\s*//")

# What the matcher below must accept and must refuse, run before it is trusted
# against the real config. The third case is the one worth reading: a flat glob
# does not descend, which is the shape E0-36 found in the `e2e` probe and the
# shape a tsconfig `include` can have just as easily.
COVERAGE_CASES = (
    ("tests/e2e/**/*.ts", "tests/e2e/lms/launch.spec.ts", True),
    ("tests/e2e/**/*.ts", "tests/e2e/launch.spec.ts", True),
    ("tests/e2e/*.ts", "tests/e2e/lms/launch.spec.ts", False),
    ("tests/e2e", "tests/e2e/lms/launch.spec.ts", True),
    (PLAYWRIGHT_CONFIG_NAME, PLAYWRIGHT_CONFIG_NAME, True),
    (PLAYWRIGHT_CONFIG_NAME, "tests/e2e/launch.spec.ts", False),
    ("tests/unit/**/*.ts", "tests/e2e/launch.spec.ts", False),
)

# A line whose first word is one of these runs nothing. The tolerance notices in
# this workflow name the tools they are standing in for — "No frontend/package.json
# yet — tsc and eslint have nothing to check" — so a search that read every line as
# a command would report the notice step as a gate running tsc, and then complain
# that the gate it invented waits on the wrong probe.
NOT_A_COMMAND = ("echo", "printf", ":")


def run_scripts(node: Any) -> list[str]:
    """Every `run:` script anywhere inside a parsed workflow fragment."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "run" and isinstance(value, str):
                found.append(value)
            found.extend(run_scripts(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(run_scripts(item))
    return found


def strings_in(node: Any) -> list[str]:
    """Every string anywhere in a parsed YAML document.

    The parsed document rather than the file's text, because `ci.yml` explains its
    own history in comments — the line saying there is no `detect.outputs.e2e`
    read any more contains that reference, and a search over the raw file would
    read a comment describing the absence as evidence of the presence.
    """
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [
            found for key, value in node.items() for found in strings_in(key) + strings_in(value)
        ]
    if isinstance(node, list):
        return [found for item in node for found in strings_in(item)]
    return []


def jobs_of(workflow: dict[str, Any], workflow_path: Path) -> dict[str, Any]:
    """Every job in the workflow, or a failure naming what was read instead."""
    jobs = workflow.get("jobs") or {}
    assert jobs, (
        f"{workflow_path} declares no jobs, or did not parse. Every assertion in this module is "
        "about a job in that file, and an empty mapping satisfies most of them."
    )
    return dict(jobs)


def steps_of(job: Any) -> list[dict[str, Any]]:
    """The steps of one job, as a list of mappings."""
    return [step for step in ((job or {}).get("steps") or []) if isinstance(step, dict)]


def command_lines(script: str) -> list[str]:
    """Every line of a `run:` block that could execute something.

    Continuations joined, comments cut, and the lines that only print dropped. A
    commented-out command is a line that ships without running, and a notice is a
    line that names a tool without running it; counting either as an invocation
    would make this module assert about gates that are not there.
    """
    joined = script.replace("\\\n", " ")
    found: list[str] = []
    for raw in joined.splitlines():
        line = SHELL_COMMENT.sub("", raw).strip()
        if not line or line.split()[0] in NOT_A_COMMAND:
            continue
        found.append(line)
    return found


def configuration_lines(source: str) -> list[str]:
    """Every line of the Playwright config that sets something, stripped, comments dropped.

    A `//` line is prose. The one this ticket falsifies quotes the setting it
    explains — "One retry so `trace: 'on-first-retry'` has a retry to capture" —
    so a search over the whole file would find the old value in the sentence
    explaining why it went, and refuse a comment that is doing its job.
    """
    found: list[str] = []
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        found.append(line)
    return found


class MakefileTarget(NamedTuple):
    """One target: what make runs first, and the lines it then runs, in order."""

    prerequisites: list[str]
    recipe: list[str]

    @property
    def script(self) -> str:
        """The recipe as one block, for the assertions that do not care about order."""
        return "\n".join(self.recipe)


def makefile_targets(source: str) -> dict[str, MakefileTarget]:
    """Every target in the Makefile, with its prerequisites and its recipe lines.

    Recipe lines are the tab-indented ones, which is make's own rule rather than
    this module's convention. Everything else closes whichever target was open, so
    a comment or a `.PHONY` between two targets cannot carry one target's lines
    into another.

    One walk producing both halves rather than two functions asking the same
    question of the same text (`docs/MISTAKES.md` entry 13): the rule below needs
    the recipe *in order* and the prerequisite chain, and two readers would be
    free to disagree about where a target ends.
    """
    found: dict[str, MakefileTarget] = {}
    current: str | None = None
    for raw in source.splitlines():
        if raw.startswith("\t"):
            if current is not None:
                found[current].recipe.append(raw.strip())
            continue
        match = MAKE_TARGET.match(raw)
        if match is None:
            current = None
            continue
        current = match.group("name")
        if current not in found:
            found[current] = MakefileTarget(match.group("prerequisites").split(), [])
    return found


def installs_before_running(recipe: list[str]) -> list[str]:
    """The `npx` lines in this recipe that no `npm ci` precedes.

    Walked in order, because "the closure is installed" is a fact about the lines
    above this one rather than about the recipe as a set. A single line that does
    both — `npm ci && npx eslint .` — counts, and is checked by position within
    the line rather than assumed either way.
    """
    installed = False
    offenders: list[str] = []
    for line in recipe:
        install_at = line.find(NPM_INSTALL)
        call = NPX_CALL.search(line)
        if call and not (installed or (0 <= install_at < call.start())):
            offenders.append(line)
        if install_at != -1:
            installed = True
    return offenders


def installed_by_a_prerequisite(
    name: str, targets: dict[str, MakefileTarget], seen: frozenset[str] = frozenset()
) -> str | None:
    """The prerequisite of `name` that runs `npm ci`, if the chain reaches one.

    make runs a target's prerequisites to completion before its own recipe, so
    `lint: node-modules` is a real precondition and a legitimate way to satisfy the
    rule below. It is followed rather than assumed: the ancestor's recipe has to
    contain the install, and a name that is not a target in this file — a real file
    on disk, a target in an included makefile — reaches nothing and is reported as
    reaching nothing. `seen` keeps a cyclic or diamond graph from being walked
    twice.
    """
    for prerequisite in targets.get(name, MakefileTarget([], [])).prerequisites:
        if prerequisite in seen:
            continue
        ancestor = targets.get(prerequisite)
        if ancestor is None:
            continue
        if NPM_INSTALL in ancestor.script:
            return prerequisite
        deeper = installed_by_a_prerequisite(prerequisite, targets, seen | {name, prerequisite})
        if deeper is not None:
            return deeper
    return None


def reachable_from(name: str, targets: dict[str, MakefileTarget]) -> set[str]:
    """Every target `make <name>` would run, itself included.

    make builds a target's prerequisites to completion before its own recipe, so
    the closure is what one invocation actually runs. A gate in a recipe nothing
    reaches is not a gate: `make ci` is what CLAUDE.md tells people to run before
    pushing, and a check outside that closure is one they are never told about.
    """
    found: set[str] = set()
    pending = [name]
    while pending:
        current = pending.pop()
        if current in found or current not in targets:
            continue
        found.add(current)
        pending.extend(targets[current].prerequisites)
    return found


def qualified_manifests(recipe: str) -> list[str]:
    """Every `package.json` in this recipe that is reached through a directory."""
    return [
        f"{match.group('prefix')}package.json"
        for match in MANIFEST_MENTION.finditer(recipe)
        if match.group("prefix")
    ]


def tsconfig_document(source: str) -> Any:
    """`tsconfig.json` parsed, with whole-line comments blanked first."""
    blanked = "\n".join("" if LINE_COMMENT.match(line) else line for line in source.splitlines())
    try:
        return json.loads(blanked)
    except json.JSONDecodeError as error:
        pytest.fail(
            f"{TSCONFIG.name} did not parse after whole-line comments were blanked: {error}\n"
            "\n"
            "It is JSONC — TypeScript accepts comments there and the file carries one — and this "
            "reader drops only the lines that are entirely a comment. A trailing comma, a block "
            "comment or a comment at the end of a line of settings will land here.\n"
            "\n"
            "This fails rather than skipping. A config this cannot read is a config whose "
            "`include` it has not checked, and reporting a clean scan over one is the failure the "
            "test exists to prevent."
        )


def include_matcher(pattern: str) -> re.Pattern[str]:
    """A tsconfig `include` glob as a regex over repository-relative paths.

    `**/` spans any number of directories including none, `**` spans anything,
    `*` and `?` stop at a separator. Written out rather than handed to `fnmatch`,
    whose `*` crosses `/` — which would make the flat-glob case in `COVERAGE_CASES`
    pass and erase the distinction this whole module is about.
    """
    out: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            out.append(r"(?:[^/]+/)*")
            index += 3
        elif pattern.startswith("**", index):
            out.append(r".*")
            index += 2
        elif pattern[index] == "*":
            out.append(r"[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append(r"[^/]")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    joined = "".join(out)
    return re.compile(f"^{joined}$")


def covers(pattern: str, relative: str) -> bool:
    """Whether one `include` entry reaches this repository-relative file.

    An entry with no wildcard that names a directory covers everything under it,
    which is TypeScript's documented behaviour and a legitimate way to write this
    list; refusing it would be this test insisting on a spelling.
    """
    if not any(character in pattern for character in "*?") and (REPO_ROOT / pattern).is_dir():
        return relative.startswith(f"{pattern}/")
    return bool(include_matcher(pattern).match(relative))


def steps_running(jobs: dict[str, Any], pattern: re.Pattern[str]) -> list[tuple[str, str, Any]]:
    """Every step whose script invokes `pattern`, as (job name, step label, step)."""
    found: list[tuple[str, str, Any]] = []
    for job_name, job in jobs.items():
        for index, step in enumerate(steps_of(job)):
            lines = command_lines(str(step.get("run") or ""))
            if any(pattern.search(line) for line in lines):
                found.append((job_name, str(step.get("name") or f"step {index}"), step))
    return found


def detect_outputs_read_by(step: dict[str, Any]) -> set[str]:
    """Which `detect` outputs this step consults, in its condition or in its script."""
    text = "\n".join([str(step.get("if") or ""), str(step.get("run") or "")])
    return set(DETECT_OUTPUT.findall(text))


def inside_the_frontend_tree(step: dict[str, Any]) -> str | None:
    """How this step leaves the repository root, if it does."""
    directory = str(step.get("working-directory") or "").strip()
    if directory and directory.removeprefix("./").split("/")[0] == FRONTEND:
        return f"working-directory: {directory}"
    for line in command_lines(str(step.get("run") or "")):
        if FRONTEND_DIRECTORY.search(line):
            return line
    return None


def planted_tree(root: Path, files: tuple[PlantedFile, ...]) -> Path:
    """A repository tree holding exactly `files`.

    An entry is a path, which gets a marker line, or a `(path, content)` pair for
    the files a probe reads rather than counts. The `frontend` probe is the second
    kind from E1-02 onwards: `frontend/package.json` is committed by the workspace
    layout, so the probe asks what the manifest declares, and a table that could
    only plant paths could no longer state the case it turns on.
    """
    root.mkdir(parents=True)
    for entry in files:
        relative, content = (
            entry if isinstance(entry, tuple) else (entry, f"planted by {Path(__file__).name}\n")
        )
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def probe_outputs(scripts: list[str], tree: Path, workspace: Path) -> dict[str, str]:
    """Run the probe over `tree` and answer what it wrote to `$GITHUB_OUTPUT`."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.fail(
            "bash is not on PATH, so the probe cannot be executed. This fails rather than "
            "skipping: a skip here is indistinguishable from a probe that answers correctly."
        )

    output = workspace / "github-output"
    output.write_text("", encoding="utf-8")

    for index, script in enumerate(scripts):
        path = workspace / f"probe-{index}.sh"
        path.write_text(script, encoding="utf-8")
        # S603: the executable is a resolved absolute path, and the script is one
        # this test just wrote out of the repository's own workflow file.
        completed = subprocess.run(  # noqa: S603
            [bash, "-e", str(path)],
            cwd=tree,
            env=os.environ | {"GITHUB_OUTPUT": str(output)},
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            pytest.fail(
                f"The `{DETECT_JOB}` job's probe exited {completed.returncode} over a planted "
                f"tree, so it emitted nothing to judge.\n{completed.stderr.strip()}"
            )

    emitted: dict[str, str] = {}
    for line in output.read_text(encoding="utf-8").splitlines():
        match = EMITTED.match(line.strip())
        if match:
            emitted[match.group("name")] = match.group("value")
    return emitted


def test_every_detect_probe_answers_true_over_a_tree_that_holds_what_its_job_runs(
    ci_workflow_path: Path, ci_workflow: dict[str, Any], tmp_path: Path
) -> None:
    """E0-40 decision 1: `node` is the root manifest, `frontend` is the E1 one, and they differ.

    The consequential case is the second in the table. It plants what PR #61
    actually committed — `package.json`, `package-lock.json`,
    `playwright.config.ts` and a spec under `tests/e2e/` — and requires the probe
    that gates `npm audit`, the licence scan, `tsc` and `eslint` to answer true
    over it. Today no such probe exists and the four gates ask about
    `frontend/package.json`, so they run nothing, print a notice, and their jobs
    report **success**. Nothing anywhere is red or skipped.

    The frontend cases are the other direction and they are not decoration: a
    single probe renamed rather than split would answer true to both, and the
    production build would then run `npm run build` in a directory that does not
    exist. `frontend/package.json` alone must still leave `node` false.

    **E1-04 withdraws the `frontend` probe and keeps both of its trees, and E2-13
    does the same for `evals`.** The workspace stub and the scaffold that declares
    a `build` are the two trees the first probe told apart; the runner and the eval
    set beside it are the two the second answered `true` over. Each is the only
    tree in this table a surviving copy of its probe would fire on. Since every
    case compares the whole emitted mapping, planting those trees is what catches a
    probe that outlived its readers — a boolean nothing consults is one whose
    wrongness produces no symptom, and the next gate wired to it inherits an answer
    nobody has checked.

    **The empty-tree case comes first and it is the case the others rest on.**
    Several cases below assert that a probe answers *true*, and a probe that
    answered true to everything would satisfy all of them while turning every
    tolerance in this pipeline into a permanent lie in the other direction.

    **The whole emitted mapping is compared, not the key each case is named for.**
    That is how a withdrawn probe is caught: none of `e2e`, `frontend` or `evals`
    has a reader left, and a boolean nothing reads is one whose wrongness has no
    symptom. If any of them is still emitted, every case here fails.

    **The mutation this survives:** point the `node` probe at
    `frontend/package.json`, or at `[ -f package.json ] || [ -f frontend/package.json ]`,
    which is the tempting one-line version of the split and makes two questions one;
    or leave the `frontend` or `evals` probe in the job after its consumers stopped
    reading it.
    **The near miss that must stay green:** any spelling of the same question —
    `[ -f package.json ]`, `test -f ./package.json`, a `find -maxdepth 1` — since
    this judges what the probe emits and not how it decides.
    """
    assert (
        ci_workflow
    ), f"{ci_workflow_path} does not exist or parsed to nothing, so there is no probe to run."

    jobs = jobs_of(ci_workflow, ci_workflow_path)
    job = jobs.get(DETECT_JOB)
    assert job, (
        f"{ci_workflow_path} declares no `{DETECT_JOB}` job (it declares {sorted(jobs)}). Every "
        "tolerance in this pipeline is conditioned on what that job emits; if it has been "
        "renamed, rename it here too rather than leaving this module looking for something that "
        "is gone."
    )

    scripts = run_scripts(job)
    assert scripts, (
        f"The `{DETECT_JOB}` job runs no script, so it emits nothing. Every gate conditioned on "
        "`needs.detect.outputs.*` then reads an empty string, takes its tolerant branch, and "
        "reports success having run none of its steps — which is this module's subject arriving "
        "by a different route."
    )

    wrong: list[str] = []
    for index, (case, files, expected) in enumerate(CASES):
        workspace = tmp_path / f"case-{index}"
        workspace.mkdir()
        tree = planted_tree(workspace / "repo", files)
        emitted = probe_outputs(scripts, tree, workspace)
        if emitted != expected:
            wrong.append(
                f"  {case}\n"
                f"    planted:  {list(files) or 'nothing'}\n"
                f"    expected: {expected}\n"
                f"    emitted:  {emitted or 'nothing'}"
            )

    assert not wrong, "\n".join(
        [
            f"The `{DETECT_JOB}` job's probes gave the wrong answer over planted trees:",
            *wrong,
            "",
            "A probe that answers false over a tree that has the thing does not skip its gate — "
            "it turns the real steps off by their own `if:`, runs the `::notice::` step in their "
            "place, and the job reports **success**. So the aggregate `CI` check sees a green job "
            "and nothing anywhere is red or skipped.",
            "",
            f"`{NODE}` is E0-40's subject: PR #61 committed `package.json`, `package-lock.json` "
            "and TypeScript at the repository root, and `npm audit`, the licence scan, `tsc` and "
            "`eslint` went on asking about `frontend/package.json` — a path that does not exist "
            "and is not due until E1. Four gates green over a tree they never read.",
            "",
            f"`{FRONTEND}` is gone, and E1-04 removed it: that ticket lands the scaffold and makes "
            "the production build and the bundle budget enforcing, so the two jobs that read the "
            "boolean stopped reading it. The trees it used to tell apart are still planted here, "
            "because the one holding a manifest with a `build` script is the one a surviving copy "
            "of the probe would answer `true` over.",
            "",
            f"`{EVALS}` is gone too, and E2-13 removed it: E2-12 committed "
            "`tests/evals/runner.py`, made the `evals` job enforcing and deleted the clause that "
            "read this boolean, leaving an output nothing consults. The eval trees are still "
            "planted here for the same reason the frontend ones are — they are the trees a "
            "surviving copy would answer `true` over.",
            "",
            f"The comparison is over the whole mapping, so {list(WITHDRAWN)} showing up here is a "
            "probe that outlived its reader rather than a harmless extra line.",
            "",
            "The spelling is not prescribed. What has to hold is that a tree holding the file a "
            "job needs answers true, and a tree without it answers false.",
        ]
    )


def test_the_detect_job_publishes_no_probe_that_nothing_reads(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """E0-40 decision 5, E1-04 and E2-13: a probe goes when its last reader does.

    PR #61 made the Playwright gate unconditional on the specs being present —
    they are committed, so §9.2's both-doors requirement is enforced rather than
    tolerated — and `detect.outputs.e2e` had no reader after it. E1-04 does the
    same to `frontend`: it lands the scaffold and makes the production build and
    the bundle budget enforcing, and those two were the whole of that boolean's
    readership. An emitted boolean that nothing consults is worse than an unused
    variable: it is a probe whose wrongness produces no symptom at all, so nobody
    finds out it is wrong, and the next gate wired to it inherits an answer
    nothing has ever checked. E0-36 found `evals` and `e2e` wrong; the repair
    landed, and then one of the readers went away.

    **`evals` is E2-13's, and it is the instance where the two halves came apart
    by a whole ticket.** E2-12 committed the eval runner, made the `evals` job
    enforcing on E0-38's changed-paths classification and deleted the step that
    read this boolean — the removal ADR 0002 requires of the ticket landing the
    code. The output it filled stayed, because withdrawing it means editing
    `PROBES` above and that is on the other side of the heavy lane's test wall.
    So for one ticket the pipeline published a probe with no reader anywhere, and
    `docs/tickets/e2/deferred.md` carries the entry that says so. Its done-when is
    this: the output and the probe line that fills it are removed together, and
    `PROBES` drops `EVALS` in the same change.

    The set is asserted closed in both directions. A missing `node` is a gate that
    cannot run; a lingering `e2e`, `frontend` or `evals` is a probe nobody reads;
    an output nobody here has heard of is a decision that was made without the
    ticket, and it fails with the name in the message rather than passing quietly.

    **The mutation this survives:** leave the withdrawn line in the job's
    `outputs:` block after deleting the probe that fills it, which is the half of
    the removal that is easy to miss and leaves every reader of it holding an empty
    string — and `'' != 'true'`, so a gate guarded that way silently runs on
    everything. **The near miss that must stay green:** a probe whose
    *implementation* changed while its name did not, since this asserts names and
    readers rather than shell.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)
    job = jobs.get(DETECT_JOB)
    assert job, (
        f"{ci_workflow_path} declares no `{DETECT_JOB}` job (it declares {sorted(jobs)}), so "
        "there are no published probes to read."
    )

    published = set((job.get("outputs") or {}).keys())
    assert published == set(PROBES), "\n".join(
        [
            f"The `{DETECT_JOB}` job publishes {sorted(published)} and E0-40, E1-04 and E2-13 "
            f"between them settle {sorted(PROBES)}.",
            f"  missing:  {sorted(set(PROBES) - published) or 'nothing'}",
            f"  lingering: {sorted(published - set(PROBES)) or 'nothing'}",
            "",
            f"{list(WITHDRAWN)} are the ones to expect here. `e2e` has been consumed by nothing "
            "since PR #61 made the Playwright gate unconditional (E0-40 decision 5); `frontend` "
            "loses its last two readers in E1-04, which lands the scaffold and makes the "
            "production build and the bundle budget enforcing; and `evals` lost its only reader "
            "in E2-12, which committed the eval runner and made that job enforcing, so E2-13 "
            "withdraws the output and the probe line that fills it together.",
            "",
            f"`{NODE}` missing is the other direction: `npm audit` and the licence scan have "
            "nothing to wait on, so either they run unconditionally — a decision, and one for a "
            "ticket rather than for a deletion — or they go back to asking `frontend`, and this "
            "file's history says the second is what happens.",
        ]
    )

    references = [
        text
        for text in strings_in(ci_workflow)
        for name in WITHDRAWN
        if f"{DETECT_JOB}.outputs.{name}" in text
    ]
    assert not references, "\n".join(
        [
            "A withdrawn probe is still read somewhere in the workflow:",
            *(f"  {text.strip()[:200]}" for text in references),
            "",
            "Removing the output while leaving a reader is the worse half of the two: the "
            "reference evaluates to the empty string, a `== 'true'` guard is then false forever "
            "and the step it protects never runs again, with the job green.",
        ]
    )


def test_the_node_facing_gates_wait_on_the_root_package_manifest(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """E0-40's scope, as E1-04 leaves it: audit and the licence scan wait on `node`.

    This is the half the probe cannot assert about itself. A `node` output emitted
    by a correct probe and read by nothing leaves the gates exactly where they
    are — waiting on a manifest that does not exist, printing a notice, reporting
    success — with the battery above fully green. That is `docs/MISTAKES.md` entry
    2: the fix ships, and nothing asserts the thing the fix was for.

    Two properties per gate, and both come from the ticket rather than from the
    file: it consults `node`, and it does not consult `frontend`; and it runs at
    the repository root, where the manifest and the lockfile actually are. A step
    that kept `working-directory: frontend` while reading `node` would install and
    audit the wrong package.

    **`tsc` and `eslint` are no longer in this set, and E1-04 is why.** They were
    tolerant gates over TypeScript that did not exist; E1-04 lands the application
    they check, and ADR 0002 makes removing a tolerance an acceptance criterion of
    the ticket that lands the code. They now run unconditionally, and
    `tests/unit/test_the_frontend_gates_stopped_being_tolerant.py` asserts that the
    job holding them consults no probe at all. They stay in the canary below,
    because a gate that has vanished from the workflow altogether is a finding
    whichever set it belongs to.

    **The gates are found by the command that runs them, not by the job that holds
    them.** E0-40 does not settle whether `lint-frontend` keeps its name once tsc
    and eslint stop being about a frontend, and a search keyed on the job name
    would report a clean pipeline over a rename. Each pattern is required to match
    something first, so a tool spelled a new way — `npm run typecheck` for `tsc` —
    fails as an unfindable gate rather than as a gate that passed unexamined.

    **The mutation this survives:** point `npm audit` or the licence scan back at
    `frontend`, or drop their guard entirely while the probe stays — a pipeline
    whose remaining probe decides nothing. **The near miss that must stay green:**
    any job layout at all — one Node job or four, the conditions on the steps or on
    a wrapper — since this asks which probe the step that runs the tool consults.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)

    unfindable = [
        f"  {tool} — nothing in {ci_workflow_path.name} runs {pattern.pattern!r}"
        for tool, pattern in RUNS_AT_THE_ROOT.items()
        if not steps_running(jobs, pattern)
    ]
    assert not unfindable, "\n".join(
        [
            "These gates could not be found in the workflow, so nothing below was asserted about "
            "them:",
            *unfindable,
            "",
            "Every verdict in this test is 'the step that runs this tool waits on the right "
            "probe', and a tool that runs nowhere satisfies that having been looked at and not "
            "read. Either the gate is gone — which is a larger finding than this ticket — or it "
            "is spelled a new way and the pattern needs pointing at it.",
            "",
            "This is the canary rather than a formality: with the patterns matching nothing, a "
            "workflow in which every gate still asked `frontend` would pass this test.",
        ]
    )

    wrong_probe: list[str] = []
    wrong_directory: list[str] = []
    for tool, pattern in WAITS_ON_THE_NODE_PROBE.items():
        for job_name, label, step in steps_running(jobs, pattern):
            read = detect_outputs_read_by(step)
            if NODE not in read:
                wrong_probe.append(
                    f"  {job_name} / {label!r} runs {tool} and consults "
                    f"{sorted(read) or 'no probe at all'}"
                )
            elif FRONTEND in read:
                wrong_probe.append(
                    f"  {job_name} / {label!r} runs {tool} and consults `{FRONTEND}` as well as "
                    f"`{NODE}`, so it still waits for a directory that does not exist"
                )
            elsewhere = inside_the_frontend_tree(step)
            if elsewhere:
                wrong_directory.append(f"  {job_name} / {label!r} runs {tool} — {elsewhere}")

    assert not wrong_probe, "\n".join(
        [
            f"These gates do not wait on the `{NODE}` probe:",
            *wrong_probe,
            "",
            "E0-40 decision 1: the `node` probe — `[ -f package.json ]` at the repository root — "
            "gates `npm audit` and the licence scan. PR #61 committed the manifest and the "
            "lockfile those two read; both went on asking about `frontend/package.json`, which "
            "was not there and was not due until E1.",
            "",
            "The failure has no symptom, which is why it survived a review: each step switches "
            "itself off by its own `if:`, the notice step runs in its place, and the job reports "
            "**success**. `npm audit` ran clean at the root the whole time — CI simply never "
            "called it.",
            "",
            "A step consulting no probe at all is reported here too. Running these two "
            "unconditionally is a different decision from the one E0-40 settled, and it is the "
            "decision E1-04 takes for `tsc` and `eslint` — deliberately, in a ticket, with the "
            "tolerance branch removed in the same change. If it is right for the supply-chain "
            "gate as well, it belongs in a ticket rather than in a condition nobody wrote.",
        ]
    )

    assert not wrong_directory, "\n".join(
        [
            "These gates wait on the root manifest and then run somewhere else:",
            *wrong_directory,
            "",
            "The manifest and the lockfile these two read are at the repository root, and the "
            "root lockfile is the whole workspace's resolution (ADR 0083). An audit or a licence "
            "scan run inside the member package is asking about a subset of what ships.",
            "",
            "A gate that genuinely needs to work inside the frontend tree should say so in a step "
            "of its own — which is what the fast gate's workspace checks do, and they wait on no "
            "probe at all.",
        ]
    )


# E1-04 removed a test here, and the reason belongs in the file rather than only
# in a pull request. `test_the_frontend_build_gates_still_wait_on_the_frontend_package_manifest`
# asserted that the production build and the bundle budget go on waiting on the
# `frontend` probe. It was a control against a blanket edit — E0-38's second
# review pass found `if: needs.detect.outputs.frontend == 'true'` edited across
# three jobs at once, and a blanket rename would have passed every other assertion
# in this module. E1-04 withdraws that probe, so the property it held is now false
# by decision, and the same hazard is covered from the other side without a second
# copy of it: `test_the_detect_job_publishes_no_probe_that_nothing_reads` fails if
# anything in the workflow still reads `detect.outputs.frontend`, which is what a
# blanket rename leaves behind, and
# `tests/unit/test_the_frontend_gates_stopped_being_tolerant.py` requires those two
# gates to consult no probe at all and to still run.


def test_the_node_facing_gates_short_circuit_on_a_documentation_only_diff(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """E0-40 decision 6: the node gates join E0-38's documentation-only short-circuit.

    Their exemption goes with the reason for it. E0-38 exempted the fast tsc and eslint gate from the documentation-only
    short-circuit, and the reason it gave was that the job was free: with
    `detect.outputs.frontend` false, every step in it switched itself off. E0-40
    makes it cost a dependency install and two checkers on every pull request,
    and a documentation-only diff changes no TypeScript and no manifest — so what
    this ticket removes is the justification for the exemption. Decision 6 settles
    it: these gates short-circuit like the other expensive ones.

    Two things are required of each of the four, and the second is worth nothing
    without the first. Its job must declare `changed` in `needs`, because GitHub's
    `needs` context holds only declared needs and a reference to an undeclared one
    is the empty string — `'' != 'true'` is true, so the guard is dead, the step
    runs on everything, and nothing goes red. And its own condition must mention
    the classification.

    **What this reads is mention, not sense.** A clause flipped to
    `inert == 'true'` still mentions the classification and passes here. The
    sibling module's `test_no_expensive_gate_is_guarded_the_wrong_way_round` reads
    the operator, and E0-40 puts `lint-frontend` into that module's
    `EXPENSIVE_GATES` so that it reaches this job as well. What is asserted here is
    that the clause is there at all, per tool rather than per job — that module's
    signature pattern finds the install step and not the two checkers.

    **The mutation this survives:** rewrite one of these conditions wholesale as
    `needs.detect.outputs.node == 'true'`, dropping the inert clause — which is
    what a blanket edit over the probe reference produces, and which nothing else
    in the suite notices for the `npx` steps. **The near miss that must stay
    green:** any spelling or ordering of the clause — either side of the `&&`,
    `!= 'true'` or `== 'false'`. The guard must stay on the *step*: a job-level
    `if:` is refused by `test_the_aggregate_ci_check_sees_an_upstream_failure.py`,
    because a job switched off that way reports `skipped` and the required check
    reads a skip as a failure.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)

    unreachable: list[str] = []
    unguarded: list[str] = []
    guarded: list[str] = []
    for tool, pattern in RUNS_AT_THE_ROOT.items():
        for job_name, label, step in steps_running(jobs, pattern):
            needs = (jobs.get(job_name) or {}).get("needs") or []
            declared = [needs] if isinstance(needs, str) else list(needs)
            if CHANGED_JOB not in declared:
                unreachable.append(
                    f"  {job_name} / {label!r} runs {tool} — its job declares "
                    f"`needs: {declared or 'nothing'}`"
                )
            elif INERT_OUTPUT in str(step.get("if") or ""):
                guarded.append(f"  {job_name} / {label!r} runs {tool}")
            else:
                unguarded.append(
                    f"  {job_name} / {label!r} runs {tool} — `if: {step.get('if') or 'nothing'}`"
                )

    assert unreachable or unguarded or guarded, (
        f"No step in {ci_workflow_path.name} runs any of {sorted(RUNS_AT_THE_ROOT)}, so this test "
        "looked at nothing and passed. The test above fails first and more usefully when that is "
        "true; this assertion is here so that a green line from this one always means four gates "
        "were read."
    )

    assert not unreachable, "\n".join(
        [
            "These gates cannot see E0-38's classification, because their job does not declare "
            f"`{CHANGED_JOB}` in `needs`:",
            *unreachable,
            "",
            f"`{INERT_OUTPUT}` in a job that does not need `{CHANGED_JOB}` is the empty string. A "
            "guard written `!= 'true'` is then true forever and the step runs on every pull "
            "request; one written `== 'true'` is false forever and the step never runs again. "
            "Either way the condition says something the workflow does not do, and E0-38's second "
            "review pass found exactly that on exactly this job.",
            "",
            "So the `needs` entry is half of the fix and the condition is the other half. Adding "
            "the clause without the dependency is the version that looks done.",
        ]
    )

    assert not unguarded, "\n".join(
        [
            "These gates do not short-circuit on a documentation-only diff:",
            *unguarded,
            f"  already guarded: {[line.strip() for line in guarded] or 'none of them'}",
            "",
            "E0-40 decision 6: the node gates join E0-38's short-circuit. Their exemption was "
            "justified by being free — the probe never fired, so the steps never ran — and this "
            "ticket is what makes them cost a dependency install plus tsc and eslint on every "
            "pull request, including one that changes a line of Markdown and no TypeScript at "
            "all.",
            "",
            "For the steps that were guarded already, the risk runs the other way: their "
            "conditions carry both clauses, E0-40 rewrites the first, and the second goes out "
            "with it if the edit replaces the condition rather than editing a clause of it.",
        ]
    )


def test_the_e2e_gate_does_not_pass_over_a_spec_that_failed_once() -> None:
    """E0-40 decision 3: `retries: 0`, and a trace that survives without a retry to capture it.

    `retries: process.env.CI ? 1 : 0` means a spec that fails and passes on the
    second attempt exits zero, so the Playwright gate reports success over a test
    that failed. CLAUDE.md forbids marking a test flaky to make CI pass; this is
    that, reached through a configuration option instead of a marker, applied to
    every spec at once, and with no ADR. The two settings move together because
    `trace: 'on-first-retry'` only ever fires on a retry — take the retry away and
    leave the trace, and the debugging artifact the retry was buying is gone.
    `retain-on-failure` keeps it without one.

    **Read as text, and the limits said out loud.** Nothing here parses
    TypeScript, so this asserts that the config's statements say these two things
    and not what Playwright makes of them; a second `retries` set inside a
    `projects:` entry would be caught only because every `retries` line is
    required to be `0`, and a value computed elsewhere and spread in would not be
    caught at all. It is an anchor against a silent revert, which is what E0-40
    decision 8 asks for, rather than a proof about the runner.

    **The searches are exercised against copied lines before they are trusted.**
    Both spellings — the one in the file today and the one the ticket asks for —
    are run through the same patterns, so a pattern that matches nothing announces
    itself instead of reporting a compliant config (`docs/MISTAKES.md` entry 3).

    **The mutation this test kills:** restore `retries: process.env.CI ? 1 : 0`,
    or set `retries: 1` outright, or take the retry away and leave
    `trace: 'on-first-retry'`, which is the half-applied version that silently
    stops collecting traces. **The near misses that must stay green:** any
    reformatting of those lines — spacing, a trailing comma, a different key order
    — and a comment that explains the change by naming the value that went, which
    is the sentence the current comment will have to become.
    """
    assert PLAYWRIGHT_CONFIG.is_file(), (
        f"{PLAYWRIGHT_CONFIG} does not exist, so the e2e gate's retry behaviour is whatever "
        "Playwright defaults to and nothing in this repository says what it should be. E0-18 "
        "committed this file with the first §9.2 specs; if it has moved, this constant moves "
        "with it."
    )

    assert RETRIES.search(RETRY_LINE_BEFORE) and not NO_RETRIES.match(RETRY_LINE_BEFORE.strip()), (
        f"The retry search does not read {RETRY_LINE_BEFORE.strip()!r} as a retry setting that is "
        "not zero. That is the line this test exists to refuse, copied whole out of the file, so "
        "a pattern blind to it would pass over the defect itself."
    )
    assert NO_RETRIES.match(RETRY_LINE_AFTER.strip()), (
        f"The retry search does not accept {RETRY_LINE_AFTER.strip()!r}, which is the line E0-40 "
        "asks for. A pattern that accepts nothing fails the file no matter what it says, and the "
        "failure would look like an unbuilt ticket rather than a broken test."
    )
    assert TRACE.search(TRACE_LINE_BEFORE) and not TRACE_ON_FAILURE.match(
        TRACE_LINE_BEFORE.strip()
    ), (
        f"The trace search does not read {TRACE_LINE_BEFORE.strip()!r} as a trace setting that is "
        "not `retain-on-failure`."
    )
    assert TRACE_ON_FAILURE.match(TRACE_LINE_AFTER.strip()), (
        f"The trace search does not accept {TRACE_LINE_AFTER.strip()!r}, which is the line E0-40 "
        "asks for."
    )

    lines = configuration_lines(PLAYWRIGHT_CONFIG.read_text(encoding="utf-8"))
    assert lines, (
        f"{PLAYWRIGHT_CONFIG.name} holds no statement at all once comments and blank lines are "
        "dropped. Every assertion below is over that list, and an empty one satisfies all of "
        "them."
    )

    retries = [line for line in lines if RETRIES.search(line)]
    assert retries, (
        f"{PLAYWRIGHT_CONFIG.name} sets no `retries` at all. Playwright's default is 0, so the "
        "behaviour may well be right — but E0-40 decision 8 asks for an anchor that says so, and "
        "a setting nobody wrote down is one the next person adds back without noticing they are "
        "reversing a decision. The rule this restores is CLAUDE.md's: never mark a test flaky to "
        "make CI pass."
    )
    retrying = [line for line in retries if not NO_RETRIES.match(line)]
    assert not retrying, "\n".join(
        [
            f"{PLAYWRIGHT_CONFIG.name} retries a failed spec:",
            *(f"  {line}" for line in retrying),
            "",
            "A spec that fails once and passes on the retry exits zero, so `Test · Playwright e2e` "
            "reports success over a test that failed. That is CLAUDE.md's flaky rule reached "
            "through a configuration option rather than a marker, and applied to every spec at "
            "once rather than to the one somebody argued about.",
            "",
            "E0-40 decision 3 is explicit that this restores the documented rule rather than "
            "deciding anything new, which is why it carries no ADR. Putting a retry back is "
            "therefore a decision that needs one.",
        ]
    )

    traces = [line for line in lines if TRACE.search(line)]
    assert traces, (
        f"{PLAYWRIGHT_CONFIG.name} sets no `trace` at all, so a failing spec leaves nothing to "
        "debug from. The retry was buying that artifact through `on-first-retry`; E0-40 takes the "
        "retry away and keeps the artifact, and a config with neither has paid the price of the "
        "change without receiving the thing it was for."
    )
    wrong_trace = [line for line in traces if not TRACE_ON_FAILURE.match(line)]
    assert not wrong_trace, "\n".join(
        [
            f"{PLAYWRIGHT_CONFIG.name} keeps a trace mode that needs a retry to fire:",
            *(f"  {line}" for line in wrong_trace),
            "",
            "`on-first-retry` records a trace on the second attempt, so with `retries: 0` it "
            "records nothing, ever. The two settings are one change: `retain-on-failure` keeps "
            "the artifact for the run that failed, with no retry involved.",
            "",
            "This is the half of decision 3 that fails quietly. Nothing turns red — the gate just "
            "stops producing the file somebody will look for the next time a spec fails on CI.",
        ]
    )


def test_the_makefile_node_targets_probe_the_root_manifest_too() -> None:
    """The probe's second copy, which the mutation battery found guarded by nothing.

    `lint`, `typecheck`, `audit` and `licenses` each carry their own copy of the
    condition the `detect` job emits, because CLAUDE.md requires `make ci` to run
    the same gates the workflow does. Reverting either copy to
    `frontend/package.json` while the other holds the root left the whole suite
    green: the tests above read `ci.yml` and nothing read the Makefile. That is
    `docs/MISTAKES.md` entry 13 exactly — a hazard worked around in one of the two
    places facing it — and it is the reason the rule is asserted of both files in
    one module rather than of one file in two.

    **The consequence is asymmetric, and the Makefile is the worse half to lose.**
    A workflow probing a directory that does not exist prints a notice and reports
    success; so does the Makefile, which means `make ci` — the thing CLAUDE.md
    tells you to run before pushing — goes green over four checks it never ran. The
    person who would have caught the disagreement is the person the disagreement is
    hidden from.

    **What is asserted is the absence of a prefix, not the presence of a
    spelling.** Every `package.json` these four recipes name must be the root one.
    `[ -f package.json ]`, `test -f package.json` and a shell function that takes
    the path as an argument all pass; only a directory in front of the name fails.

    **The mutation this kills:** put `frontend/` back in front of the manifest in
    any one of the four recipes while `ci.yml` keeps the root probe. **The near
    miss that must stay green:** any spelling of the root probe — `[ -f
    package.json ]`, `test -f package.json`, a shell function taking the path.

    **The control moved in E1-04.** It used to be `frontend-build`, the one recipe
    that certainly named a qualified manifest, because a reader blind to qualified
    paths would report all four targets clean having read nothing
    (`docs/MISTAKES.md` entry 35). That ticket deletes the probe out of that recipe,
    so the reader is exercised against the condition as it stood instead — copied
    whole, entry 3 — which keeps the control working after the tree has stopped
    holding an example of the thing it looks for.
    """
    assert MAKEFILE.is_file(), (
        f"{MAKEFILE} does not exist, so nothing runs the pipeline's gates locally and CLAUDE.md's "
        "'run `make ci` before pushing' names a target that is gone."
    )

    targets = makefile_targets(MAKEFILE.read_text(encoding="utf-8"))
    recipes = {name: target.script for name, target in targets.items()}
    assert recipes, (
        f"No target in {MAKEFILE.name} was read as having a recipe. Every assertion below is over "
        "that mapping, and an empty one satisfies all of them — the reader has gone blind rather "
        "than the Makefile having been emptied."
    )

    assert qualified_manifests(MAKEFILE_PROBE_AS_IT_STOOD) == [
        "frontend/package.json",
        "frontend/package.json",
    ], (
        "The reader does not see a manifest reached through a directory in the condition E1-04 "
        "deletes, copied whole out of the `frontend-build` recipe:\n"
        f"  {MAKEFILE_PROBE_AS_IT_STOOD}\n"
        f"  read: {qualified_manifests(MAKEFILE_PROBE_AS_IT_STOOD)}\n"
        "\n"
        "This is the control for the assertions below rather than a criterion of its own. They "
        "say the four node targets name no qualified manifest, and a reader that cannot see a "
        "qualified manifest anywhere satisfies them over a Makefile that is entirely wrong."
    )

    unfindable: list[str] = []
    unprobed: list[str] = []
    wrong_manifest: list[str] = []
    for target, tool in sorted(MAKEFILE_NODE_TARGETS.items()):
        recipe = recipes.get(target)
        if recipe is None:
            unfindable.append(f"  {target} — no such target in {MAKEFILE.name} ({tool})")
            continue
        if not RUNS_AT_THE_ROOT[tool].search(recipe):
            unfindable.append(f"  {target} — nothing in it runs {tool}")
            continue
        if "package.json" not in recipe:
            unprobed.append(f"  {target} — runs {tool} and probes for no manifest at all")
            continue
        qualified = qualified_manifests(recipe)
        if qualified:
            wrong_manifest.append(f"  {target} — runs {tool} and probes {qualified}")

    assert not unfindable, "\n".join(
        [
            f"These node-facing targets could not be found in {MAKEFILE.name}:",
            *unfindable,
            "",
            "The assertions below are about which manifest each of them probes, and a target that "
            "is not there — or that no longer runs the tool it is named for — satisfies them "
            "having been looked at and not read. Either `make ci` stopped running that check, "
            "which is a larger finding than this ticket, or it is spelled a new way.",
        ]
    )

    assert not unprobed, "\n".join(
        [
            "These targets run a node tool and probe for no manifest:",
            *unprobed,
            "",
            "Read twice before repairing. Running the tool unconditionally is not obviously wrong "
            "at the root — the manifest is committed — but it makes `make ci` fail on a checkout "
            "with no `node_modules` where the workflow would have installed first, and it is a "
            "different shape from the workflow, which is the thing this test exists to keep in "
            "step. It is reported rather than accepted so the choice is made deliberately.",
        ]
    )

    assert not wrong_manifest, "\n".join(
        [
            "These targets probe a manifest inside a directory instead of the root one:",
            *wrong_manifest,
            "",
            "E0-40 decision 1: the `Makefile` `lint`/`typecheck`/`audit` branches follow the same "
            "split as the workflow so `make ci` and the workflow agree. `frontend/` does not "
            "exist and is not due until E1, so a target probing it prints its skip notice and "
            "exits 0.",
            "",
            "CLAUDE.md: run `make ci` before pushing, and where it disagrees with "
            "`.github/workflows/ci.yml` the workflow is right and the Makefile is the bug. A "
            "Makefile that silently skips what CI runs is that disagreement in the direction "
            "nobody sees until CI is red on somebody else's branch.",
        ]
    )


def test_the_makefile_frontend_build_runs_the_gate_rather_than_probing_for_it() -> None:
    """E1-04, the Makefile's copy: the production build and the bundle budget stop being optional.

    The recipe carries the workflow's tolerance in shell — `[ -f
    frontend/package.json ] && grep -Eq '"build"…'`, and a `skip` notice in the
    else — because CLAUDE.md requires `make ci` to run the gates the workflow runs.
    When the workflow's condition goes, this one has to go with it, and the
    Makefile is the worse of the two to forget: a workflow that skips a gate at
    least skips it on a pull request somebody looks at, while `make ci` prints its
    skip line to the one person who was told to run it before pushing and reports
    success.

    **Both halves are asserted, and the second is the one a careless removal
    loses.** The probe goes, *and* the build and the budget stay — a recipe that
    lost its condition and its body together passes every "no longer probes"
    assertion in this module perfectly.

    **The mutation this kills:** delete the `if`/`else` and the commands inside it
    together, or leave the `grep` in place after the workflow's flip. **The near
    miss that must stay green:** any spelling of the two commands, in any order,
    and a `$(PYTHON)` or a `python3` in front of the budget check — this reads what
    is run, not how it is written.
    """
    assert MAKEFILE.is_file(), (
        f"{MAKEFILE} does not exist, so CLAUDE.md's 'run `make ci` before pushing' names a file "
        "that is gone."
    )

    targets = makefile_targets(MAKEFILE.read_text(encoding="utf-8"))
    target = targets.get(MAKEFILE_FRONTEND_TARGET)
    assert target is not None, (
        f"There is no `{MAKEFILE_FRONTEND_TARGET}` target in {MAKEFILE.name} (there are "
        f"{sorted(targets)}). It is the local half of the production-build and bundle-budget "
        "gates, and `make build-gates` names it."
    )

    recipe = target.script
    unrun = [
        what
        for what, pattern in (
            ("the production build", MAKEFILE_PRODUCTION_BUILD),
            ("the bundle budget", MAKEFILE_BUNDLE_BUDGET),
        )
        if not pattern.search(recipe)
    ]
    assert not unrun, "\n".join(
        [
            f"The `{MAKEFILE_FRONTEND_TARGET}` recipe no longer runs {unrun}:",
            f"  {recipe or 'no recipe at all'}",
            "",
            "This is the control for the assertion below rather than an afterthought. That one "
            "says the recipe probes for no manifest, and a recipe that runs nothing at all "
            "satisfies it completely — which is what deleting the whole `if` block leaves behind.",
        ]
    )

    probed = qualified_manifests(recipe)
    assert not probed, "\n".join(
        [
            f"The `{MAKEFILE_FRONTEND_TARGET}` recipe still probes {probed} before it runs:",
            f"  {recipe}",
            "",
            "E1-04 makes the production build and the bundle budget enforcing, and ADR 0002 makes "
            "removing the tolerance an acceptance criterion of the ticket that lands the code. "
            "The workflow's copy of this condition goes in the same change; a Makefile that keeps "
            "it prints its skip line and exits 0, so `make ci` is green over two gates it never "
            "ran.",
            "",
            "ADR 0083 rejected the mirror image of this — 'a gate turned on and made meaningless' "
            "— for the same pair of gates. Left in place after the flip, the condition is a "
            "switch nobody is watching: the manifest is committed and declares a build, so it is "
            "true on every checkout until somebody renames a script.",
        ]
    )


def test_make_ci_runs_the_frontend_checks_the_workflow_runs(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """The second copy again, for the two checks E1-04 adds — `docs/MISTAKES.md` entry 13.

    E1-04 gives the fast gate two new steps: `npm run typecheck` and `npm run lint`
    in the frontend workspace, which is how `tsc` and `eslint` come to read the
    application rather than only `playwright.config.ts` and the §9.2 specs. The
    Makefile is the other place those gates are run from, and CLAUDE.md is explicit
    about the relationship: "`make ci` runs the same gates as
    `.github/workflows/ci.yml`… when the two drift, the workflow is the source of
    truth and this file is the bug."

    This is the same hazard this module already guards for the probe itself, and it
    has already happened twice in this pair of files — the `mock-lms` health wait
    that took two tickets to reach the Makefile, and the `npm ci` before `npx` that
    the workflow had and the Makefile did not. A check in one caller and not the
    other is worse than one in neither, because the person who runs `make ci` before
    pushing is told the tree is clean by a gate that never ran.

    **The requirement is derived from the workflow rather than written down here.**
    What the Makefile must run is whatever the fast gate runs; the workflow half is
    required to be non-empty first, so that a fast gate which never gained the steps
    fails as a workflow finding rather than as a silent pass here.

    **Where the recipes live is not asserted** — `lint`, `typecheck`, a target of
    their own — only that `make ci` reaches them. A recipe outside that closure is
    a check nobody is told to run.

    **What this cannot see**, said rather than implied away: a root package script
    of the same name would satisfy it. The workflow half requires the step to name
    the workspace it checks; this half asks only that the command is reached, since
    the Makefile may legitimately spell it `--workspaces` and run every member.

    **The mutation this kills:** add the two steps to `ci.yml` and stop. **The near
    miss that must stay green:** any placement and any flag spelling, and running
    both from one recipe.
    """
    assert (
        MAKEFILE.is_file()
    ), f"{MAKEFILE} does not exist, so there is no second copy of these gates to keep in step."

    jobs = jobs_of(ci_workflow, ci_workflow_path)
    workflow_text = "\n".join(
        line
        for job in jobs.values()
        for script in run_scripts(job)
        for line in command_lines(script)
    )

    in_the_workflow = [
        what for what, pattern in MAKEFILE_WORKSPACE_CHECKS.items() if pattern.search(workflow_text)
    ]
    assert in_the_workflow, "\n".join(
        [
            f"{ci_workflow_path.name} runs neither of the frontend workspace checks, so this test "
            "asserted nothing about the Makefile.",
            "",
            "E1-04 adds `npm run typecheck` and `npm run lint` for the frontend workspace to the "
            "fast gate. Until the workflow runs them there is nothing for `make ci` to keep in "
            "step with, and `test_the_fast_gate_type_checks_and_lints_the_frontend_workspace` is "
            "where that failure is diagnosed.",
        ]
    )

    targets = makefile_targets(MAKEFILE.read_text(encoding="utf-8"))
    reachable = reachable_from(MAKEFILE_PIPELINE_TARGET, targets)
    assert len(reachable) > 1, (
        f"`make {MAKEFILE_PIPELINE_TARGET}` reaches {sorted(reachable)}, which is not a pipeline. "
        "Either the target is gone or the prerequisite walk cannot read this Makefile, and either "
        "way the assertion below would report every check missing."
    )

    reachable_recipes = "\n".join(targets[name].script for name in sorted(reachable))
    missing = [
        f"  {what} — nothing `make {MAKEFILE_PIPELINE_TARGET}` runs matches {pattern.pattern!r}"
        for what, pattern in MAKEFILE_WORKSPACE_CHECKS.items()
        if what in in_the_workflow and not pattern.search(reachable_recipes)
    ]

    assert not missing, "\n".join(
        [
            f"`make {MAKEFILE_PIPELINE_TARGET}` does not run checks the workflow's fast gate runs:",
            *missing,
            f"  reachable targets: {sorted(reachable)}",
            "",
            "CLAUDE.md: run `make ci` before pushing, and where it disagrees with the workflow "
            "the workflow is right and the Makefile is the bug. The disagreement this produces "
            "is invisible in the direction that matters — the local run passes, and the pull "
            "request is where the type error or the lint error appears.",
            "",
            "Where the two commands go is not this test's business. That `make ci` reaches them "
            "is.",
        ]
    )


def test_every_makefile_recipe_that_runs_npx_installs_the_pinned_closure_first() -> None:
    """The security review's MEDIUM: `npx` on a clean clone fetches and runs whatever is latest.

    `npx eslint` does not fail when nothing is installed. npm 10 downloads the
    package and executes it, so a target that calls `npx` without `npm ci` above it
    runs `eslint@latest` and `typescript@latest` — resolved at run time from the
    registry, unpinned, with no lockfile integrity behind them. `node_modules` is
    gitignored, so every fresh clone takes that path; the measurement is the
    reviewer's, not an inference from the text.

    CLAUDE.md pins dependency versions and commits lockfiles, and no exception is
    written anywhere for a tool that resolves its own. `.github/workflows/ci.yml`
    runs `npm ci` before every `npx` under an identical condition. The Makefile's
    copies of those same gates did not, which is `docs/MISTAKES.md` entry 13 in
    the pair of files this module already guards for the probe itself — and it is
    the second time in this ticket that the Makefile copy was the one nobody read.

    **The rule.** Every recipe line that invokes `npx` must have `npm ci` above it
    in the same recipe, or the target must have a prerequisite whose recipe does.
    The prerequisite form is followed rather than credited: make runs prerequisites
    to completion first, so `lint: node-modules` is a genuine precondition, but
    only if `node-modules` is a target in this file that actually installs. A name
    the chain cannot resolve reaches nothing and is reported as reaching nothing.

    **`e2e` fails this rule, and it is not carved out.** `@npx playwright test`
    states its `npm ci` precondition in a comment above the target — and a comment
    is not a prerequisite. Make will not run it, README's instructions are not a
    guarantee, and this is the worst of the three: a downloaded test runner
    executed against a stack that is up, migrated and seeded. It needs the
    implementer's hand like the other two, and reading the recipe's actual shape is
    the only way to see that, since the comment says the right thing.

    **The mutation this kills:** delete the `npm ci` line from a node target while
    its `npx` call stays. Nothing else in this repository would notice: the target
    still exits 0, on a developer's machine it uses whatever is in `node_modules`
    already, and only a clean clone reveals it.

    **The near miss that must stay green:** `npm ci && npx eslint .` on one line,
    which satisfies the rule by position within the line — and the prerequisite
    form, which satisfies it through the chain rather than the recipe.
    """
    assert MAKEFILE.is_file(), (
        f"{MAKEFILE} does not exist, so CLAUDE.md's 'run `make ci` before pushing' names a file "
        "that is gone."
    )

    targets = makefile_targets(MAKEFILE.read_text(encoding="utf-8"))
    assert targets, (
        f"No target in {MAKEFILE.name} was read at all, so the sweep below looked at nothing. The "
        "reader has gone blind rather than the Makefile having been emptied."
    )

    calling = {
        name: target
        for name, target in sorted(targets.items())
        if any(NPX_CALL.search(line) for line in target.recipe)
    }
    assert calling, "\n".join(
        [
            f"No recipe in {MAKEFILE.name} was read as calling `npx`, so this test passed having "
            "found nothing to judge.",
            "",
            "That is the failure this assertion exists to name rather than a clean Makefile: the "
            "targets that lint, type-check, scan licences and run Playwright all reach for a Node "
            "tool, and a reader that cannot see those calls reports every one of them compliant.",
        ]
    )

    offenders: list[str] = []
    compliant: list[str] = []
    for name, target in calling.items():
        uninstalled = installs_before_running(target.recipe)
        chain = installed_by_a_prerequisite(name, targets)
        if not uninstalled:
            compliant.append(f"{name} (installs in its own recipe)")
        elif chain is not None:
            compliant.append(f"{name} (installs through the `{chain}` prerequisite)")
        else:
            for line in uninstalled:
                offenders.append(
                    f"  {name}: {line}\n" f"    prerequisites: {target.prerequisites or 'none'}"
                )

    assert compliant, "\n".join(
        [
            f"Every `npx` recipe in {MAKEFILE.name} was read as uninstalled, including the ones "
            "that install:",
            *(f"  {line}" for line in sorted(calling)),
            "",
            f"This reads `{NPM_INSTALL}` as the install, so a repository that has moved to another "
            "one — `npm install --frozen-lockfile`, a target of its own — needs this told about "
            "it. Reported here rather than in the list below, because a reader that recognises no "
            "install at all reports every recipe as an offender and the fix looks like a Makefile "
            "problem instead of a test problem.",
        ]
    )

    assert not offenders, "\n".join(
        [
            f"These {MAKEFILE.name} recipes run `npx` with nothing having installed the pinned "
            "closure first:",
            *offenders,
            f"  compliant: {compliant}",
            "",
            "On a clean clone — `node_modules` is gitignored, so that is the ordinary case — npm "
            "10's npx downloads the package and runs it. `npx eslint` becomes `eslint@latest`, "
            "`npx tsc` becomes `typescript@latest`, and `npx playwright test` becomes a test "
            "runner fetched at run time and pointed at a stack that is up and seeded. No pin, no "
            "lockfile integrity, no failure to notice.",
            "",
            "CLAUDE.md pins dependency versions and commits lockfiles, with no exception for a "
            "tool that resolves its own. `.github/workflows/ci.yml` runs `npm ci` before every "
            "`npx` under the same condition; these are the copies of those gates that did not "
            "follow.",
            "",
            "A comment above the target saying `npm ci` is a precondition does not satisfy this, "
            "and that is deliberate: make does not run comments. Either put the install in the "
            "recipe or give the target a prerequisite that does one.",
        ]
    )


def test_the_typescript_checker_reads_the_typescript_this_repository_holds() -> None:
    """E0-40 decision 2: `tsc --noEmit` over an include list that reaches the committed specs.

    This ticket's founding defect, one file over. A gate that probes a path which
    does not exist reports success having run nothing; a `tsc --noEmit` whose
    `include` reaches nothing **exits 0 having read nothing**, and it is the
    quieter of the two — there is no probe to inspect, no `::notice::` printed in
    its place, and the job log shows a checker that ran and was happy. The battery
    proved it: dropping `tests/e2e/**/*.ts` from the include list left `tsc`
    exiting 0, caught only as a side effect of eslint's typed project service,
    which is not a guarantee anybody wrote down.

    So what is asserted is coverage of the real files rather than the shape of the
    list: every `.ts` this repository holds under `tests/e2e`, plus the Playwright
    config, must be reached by some entry. A respelling — `["**/*.ts"]`, or the
    directory form `["tests/e2e", "playwright.config.ts"]` — passes, because it is
    the same answer to the same question.

    **The reader's limits, said out loud.** `tsconfig.json` is JSONC and carries a
    comment; whole-line comments are blanked before the parse and nothing else is,
    so a trailing comma or a comment at the end of a settings line fails the parse.
    That failure is loud and says what it could not read, which is the right
    direction: a config this cannot parse is one whose include list it has not
    checked. `exclude` and `files` are not modelled — an `exclude` that removes
    `tests/e2e` again would pass here, and the honest floor is that the include
    list reaches the specs.

    **The matcher is exercised before it is trusted.** Seven pattern-and-path pairs
    run first, three of which must be refused. The flat `tests/e2e/*.ts` against a
    spec one directory down is the case worth reading: it is E0-36's finding in a
    different file format, and a matcher built on `fnmatch` — whose `*` crosses `/`
    — would accept it and erase the distinction.

    **The mutation this kills:** drop `tests/e2e/**/*.ts` from `include`, or
    narrow it to a flat glob. **The near miss that must stay green:** any
    respelling that still reaches the files, and adding entries for TypeScript
    somebody commits later.
    """
    assert TSCONFIG.is_file(), (
        f"{TSCONFIG} does not exist. E0-40 decision 2 puts a root `tsconfig.json` over "
        f"`{PLAYWRIGHT_CONFIG_NAME}` and `tests/e2e/`, and without one `npx tsc --noEmit` at the "
        "root has nothing to read — which is a gate reporting success over an unchecked tree, "
        "this ticket's own subject."
    )

    misjudged = [
        f"  {pattern!r} vs {relative!r}: answered {covers(pattern, relative)}, want {expected}"
        for pattern, relative, expected in COVERAGE_CASES
        if covers(pattern, relative) is not expected
    ]
    assert not misjudged, "\n".join(
        [
            "The include matcher in this test answered wrongly about a pattern:",
            *misjudged,
            "",
            "Every verdict below is downstream of these. A matcher that accepted everything would "
            "report the config compliant whatever it says; one that accepted nothing would fail "
            "the config no matter what it says, and the failure would read as an unbuilt ticket "
            "rather than a broken test.",
        ]
    )

    document = tsconfig_document(TSCONFIG.read_text(encoding="utf-8"))
    include = document.get("include")
    assert isinstance(include, list) and include, (
        f"{TSCONFIG.name} has no non-empty `include`, so `tsc` decides for itself what to read.\n"
        f"  found: {include!r}\n"
        "\n"
        "The default is every TypeScript file under the config's directory, which would happen to "
        "cover the specs today and would also drag in whatever `node_modules` and a future "
        "`frontend/` bring. E0-40 decision 2 asks for a list that names what this checker is for."
    )

    required = [PLAYWRIGHT_CONFIG_NAME]
    if E2E_TREE.is_dir():
        required.extend(
            sorted(
                str(path.relative_to(REPO_ROOT))
                for path in E2E_TREE.rglob("*.ts")
                if path.is_file()
            )
        )

    assert (REPO_ROOT / PLAYWRIGHT_CONFIG_NAME).is_file() and len(required) > 1, "\n".join(
        [
            "This test found no TypeScript for the checker to be pointed at:",
            f"  {PLAYWRIGHT_CONFIG_NAME}: "
            f"{'present' if (REPO_ROOT / PLAYWRIGHT_CONFIG_NAME).is_file() else 'missing'}",
            f"  under {E2E_TREE.relative_to(REPO_ROOT)}: {len(required) - 1} file(s)",
            "",
            "The assertion below is 'every file the checker must read is covered', and an empty "
            "list of files satisfies it perfectly — which is the same shape as the defect it is "
            "guarding against. E0-18 committed four §9.2 specs and the Playwright config; if they "
            "have moved, this test needs pointing at where they went.",
        ]
    )

    uncovered = [
        relative
        for relative in required
        if not any(covers(str(pattern), relative) for pattern in include)
    ]
    assert not uncovered, "\n".join(
        [
            f"{TSCONFIG.name} does not reach TypeScript that `tsc --noEmit` is supposed to check:",
            *(f"  {relative}" for relative in uncovered),
            f"  include: {include!r}",
            "",
            "A `tsc` run whose include list misses these exits 0 having read nothing. Nothing in "
            "the pipeline is red, the job log shows a checker that ran, and the only thing still "
            "looking at those files is eslint's typed project service — which is a side effect "
            "rather than a guarantee, and which the next eslint configuration change may remove.",
            "",
            "This is the same failure as a probe that answers false over a tree that has the "
            "thing, which is what E0-40 exists to fix, arriving through a file the probe split "
            "does not touch.",
        ]
    )
