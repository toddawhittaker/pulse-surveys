"""Each `detect` probe sees the file its own job runs — E0-36 findings 1 and 2, E0-40.

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

- **`node`** — `package.json` at the repository root. It gates `npm audit`, the
  licence scan, `tsc` and `eslint`, all of which run at the root.
- **`frontend`** — `frontend/package.json`. It gates the production build and the
  bundle budget, which are still legitimately waiting for the E1 scaffold.
- **`evals`** — unchanged.
- **`e2e` is gone.** PR #61 made the Playwright gate unconditional on the specs
  being present, so nothing has consumed that output since; an emitted boolean
  nothing reads is a probe whose wrongness has no symptom.

**The cases plant their own trees and none of them reads this repository.** One of
the three probes answers about a file that exists here today and two about files
that do not, and a battery that read the real tree would assert the state of the
checkout rather than the logic of the probe.

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

This is a separate module from `test_the_aggregate_ci_check_sees_an_upstream_failure.py`
even though both execute a `run:` block out of the same workflow, because shared
machinery is not a shared subject: that module's argument is about GitHub's
`needs` result semantics, and a filesystem probe battery inside it would make its
docstring answer two questions at once.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

DETECT_JOB = "detect"

# The probes the `detect` job emits, as E0-40 settles them. This is a closed set:
# every case below compares the whole mapping, so an output that lingers after the
# gate reading it is gone fails as loudly as one that never arrives.
NODE = "node"
FRONTEND = "frontend"
EVALS = "evals"
PROBES = (FRONTEND, NODE, EVALS)

# Emitted until E0-40 and consumed by nothing since PR #61 made the Playwright
# gate unconditional. Named here rather than merely left out of `PROBES`, so that
# the failure a lingering probe produces says which one it is.
WITHDRAWN = ("e2e",)

# A `name=value` line as the probe writes it into `$GITHUB_OUTPUT`.
EMITTED = re.compile(r"^(?P<name>[A-Za-z0-9_-]+)=(?P<value>.*)$")

# Every case is a planted tree and the whole answer the probe must give over it.
# The whole answer rather than the one key each case is about, so that a probe
# which turns `node` on whenever `frontend` is on cannot pass by being right about
# the key the case is named for.
#
# The first case is the one that makes the rest mean anything: over a tree with
# nothing in it every probe must answer false. A probe that answered true to
# everything would satisfy every other case here perfectly.
CASES = (
    (
        "an empty repository",
        (),
        {FRONTEND: "false", NODE: "false", EVALS: "false"},
    ),
    (
        "the tree PR #61 left: a manifest, a lockfile and TypeScript at the root",
        (
            "package.json",
            "package-lock.json",
            "playwright.config.ts",
            "tests/e2e/lms/launch.spec.ts",
        ),
        {FRONTEND: "false", NODE: "true", EVALS: "false"},
    ),
    (
        "a root package manifest and nothing else",
        ("package.json",),
        {FRONTEND: "false", NODE: "true", EVALS: "false"},
    ),
    (
        "a frontend package manifest, which is what E1 will land",
        ("frontend/package.json",),
        {FRONTEND: "true", NODE: "false", EVALS: "false"},
    ),
    (
        "both manifests, once the E1 scaffold sits beside the root toolchain",
        ("package.json", "frontend/package.json"),
        {FRONTEND: "true", NODE: "true", EVALS: "false"},
    ),
    (
        "a package manifest in some other subdirectory",
        ("tools/package.json",),
        {FRONTEND: "false", NODE: "false", EVALS: "false"},
    ),
    (
        "the eval runner that `python -m tests.evals.runner` imports",
        ("tests/evals/__init__.py", "tests/evals/runner.py"),
        {FRONTEND: "false", NODE: "false", EVALS: "true"},
    ),
    (
        "an eval set in a subdirectory beside the runner",
        ("tests/evals/__init__.py", "tests/evals/runner.py", "tests/evals/validity/cases.py"),
        {FRONTEND: "false", NODE: "false", EVALS: "true"},
    ),
    (
        "an eval directory holding no Python at all",
        ("tests/evals/README.md",),
        {FRONTEND: "false", NODE: "false", EVALS: "false"},
    ),
    (
        "e2e specs, which no probe answers for any more",
        ("tests/e2e/lms/launch.spec.ts", "tests/e2e/idp/login.spec.ts"),
        {FRONTEND: "false", NODE: "false", EVALS: "false"},
    ),
    (
        "an e2e directory holding no specs",
        ("tests/e2e/README.md",),
        {FRONTEND: "false", NODE: "false", EVALS: "false"},
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

# The two gates that keep waiting on `frontend/package.json`, and the near miss
# this whole module needs. E0-38's second review pass found that adding a guard to
# `frontend-build` had been done with a blanket edit over
# `if: needs.detect.outputs.frontend == 'true'`, a string that appears in three
# jobs — so a blanket edit is the documented way this file gets changed, and a
# blanket `frontend` → `node` rename would satisfy every assertion about the four
# tools above while pointing the production build at a manifest that is not the
# one it builds from.
RUNS_IN_THE_FRONTEND_TREE = {
    "the production build": re.compile(r"\bnpm\s+run\s+build\b"),
    "the bundle budget": re.compile(r"\bcheck_bundle_size\.py\b"),
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


def planted_tree(root: Path, files: tuple[str, ...]) -> Path:
    """A repository tree holding exactly `files`, each with a line of content."""
    root.mkdir(parents=True)
    for relative in files:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"planted by {Path(__file__).name}\n", encoding="utf-8")
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
    exist. `frontend/package.json` alone must leave `node` false, and
    `package.json` alone must leave `frontend` false.

    **The empty-tree case comes first and it is the case the others rest on.**
    Several cases below assert that a probe answers *true*, and a probe that
    answered true to everything would satisfy all of them while turning every
    tolerance in this pipeline into a permanent lie in the other direction.

    **The whole emitted mapping is compared, not the key each case is named for.**
    That is how a withdrawn probe is caught: `e2e` has been consumed by nothing
    since PR #61 made the Playwright gate unconditional, and a boolean nothing
    reads is one whose wrongness has no symptom. If it is still emitted, every case
    here fails.

    **The mutation this survives:** point the `node` probe at
    `frontend/package.json`, or at `[ -f package.json ] || [ -f frontend/package.json ]`,
    which is the tempting one-line version of this split and makes the two
    booleans indistinguishable. **The near miss that must stay green:** any
    spelling of the same question — `[ -f package.json ]`, `test -f ./package.json`,
    a `find -maxdepth 1` — since this judges what the probe emits and not how it
    decides.
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
            f"`{FRONTEND}` stays, and it is a different question: the production build and the "
            "bundle budget are still waiting for the E1 scaffold. The two must be able to "
            "disagree, which is why the table plants each manifest without the other.",
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
    """E0-40 decision 5: the `e2e` output goes, and the probe list is closed.

    PR #61 made the Playwright gate unconditional on the specs being present —
    they are committed, so §9.2's both-doors requirement is enforced rather than
    tolerated — and `detect.outputs.e2e` has had no reader since. An emitted
    boolean that nothing consults is worse than an unused variable: it is a probe
    whose wrongness produces no symptom at all, so nobody finds out it is wrong,
    and the next gate wired to it inherits an answer nothing has ever checked.
    E0-36 found this one wrong; the repair landed, and then its reader went away.

    The set is asserted closed in both directions. A missing `node` is the gate
    that cannot run; a lingering `e2e` is the probe nobody reads; an output nobody
    here has heard of is a decision that was made without the ticket, and it fails
    with the name in the message rather than passing quietly.

    **The mutation this survives:** leave the `e2e` line in the job's `outputs:`
    block after deleting the probe that fills it, which is the half of the removal
    that is easy to miss and leaves every reader of it holding an empty string —
    and `'' != 'true'`, so a gate guarded that way silently runs on everything.
    **The near miss that must stay green:** a probe whose *implementation* changed
    while its name did not, since this asserts names and readers rather than shell.
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
            f"The `{DETECT_JOB}` job publishes {sorted(published)} and E0-40 settles "
            f"{sorted(PROBES)}.",
            f"  missing:  {sorted(set(PROBES) - published) or 'nothing'}",
            f"  lingering: {sorted(published - set(PROBES)) or 'nothing'}",
            "",
            f"{list(WITHDRAWN)} is the one to expect here. It has been consumed by nothing since "
            "PR #61 made the Playwright gate unconditional, and E0-40 decision 5 removes it with "
            "this test in the same change.",
            "",
            f"`{NODE}` missing is the other direction and the more expensive one: the four gates "
            "E0-40 exists for have nothing to wait on, so either they run unconditionally or they "
            "go on asking `frontend` — and this file's history says the second is what happens.",
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
    """E0-40's scope: audit, licence scan, tsc and eslint run at the root, on the `node` probe.

    This is the half the probe cannot assert about itself. A `node` output emitted
    by a correct probe and read by nothing leaves all four gates exactly where they
    are — waiting on a manifest that does not exist, printing a notice, reporting
    success — with the battery above fully green. That is `docs/MISTAKES.md` entry
    2: the fix ships, and nothing asserts the thing the fix was for.

    Two properties per gate, and both come from the ticket rather than from the
    file: it consults `node`, and it does not consult `frontend`; and it runs at
    the repository root, where the manifest, the lockfile and the TypeScript
    actually are. A step that kept `working-directory: frontend` while reading
    `node` would install and audit nothing, because the directory is not there.

    **The gates are found by the command that runs them, not by the job that holds
    them.** E0-40 does not settle whether `lint-frontend` keeps its name once tsc
    and eslint stop being about a frontend, and a search keyed on the job name
    would report a clean pipeline over a rename. Each pattern is required to match
    something first, so a tool spelled a new way — `npm run typecheck` for `tsc` —
    fails as an unfindable gate rather than as a gate that passed unexamined.

    **The mutation this survives:** add the `node` probe and change nothing else,
    which is a green pipeline whose four gates still do not run. **The near miss
    that must stay green:** any job layout at all — one Node job or four, the
    conditions on the steps or on a wrapper — since this asks which probe the step
    that runs the tool consults.
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
            "workflow in which all four gates still asked `frontend` would pass this test.",
        ]
    )

    wrong_probe: list[str] = []
    wrong_directory: list[str] = []
    for tool, pattern in RUNS_AT_THE_ROOT.items():
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
            "gates `npm audit`, the licence scan, `tsc` and `eslint`. PR #61 committed the "
            "manifest, the lockfile and the TypeScript those four read; every one of them went on "
            "asking about `frontend/package.json`, which is not there and is not due until E1.",
            "",
            "The failure has no symptom, which is why it survived a review: each step switches "
            "itself off by its own `if:`, the notice step runs in its place, and the job reports "
            "**success**. `npm audit` runs clean at the root today — CI simply never calls it.",
            "",
            "A step consulting no probe at all is reported here too. Running the four "
            "unconditionally is a different decision from the one the ticket settled, and one the "
            "E1 tree would have to live with; if it is the right one, it belongs in the ticket "
            "rather than in a condition nobody wrote.",
        ]
    )

    assert not wrong_directory, "\n".join(
        [
            "These gates wait on the root manifest and then run somewhere else:",
            *wrong_directory,
            "",
            "The manifest, the lockfile and the TypeScript are at the repository root. A step "
            "that reads `node` and then changes into `frontend/` fails outright once the probe "
            "answers true, because that directory does not exist until E1 — a red rather than a "
            "silence, but a red produced by a half-applied split.",
            "",
            "A gate that genuinely needs to read the frontend tree as well should say so in a "
            "step of its own, waiting on the `frontend` probe.",
        ]
    )


def test_the_frontend_build_gates_still_wait_on_the_frontend_package_manifest(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """The other half of the split, and the near miss the test above cannot see.

    `npm run build` and the bundle budget are about a frontend that does not exist
    yet, and E0-40 leaves them exactly where they are: waiting on
    `frontend/package.json`, correctly answering false, correctly printing their
    notice. The split is only honest if the two probes stay different questions.

    **This is a control, not a criterion of its own**, and it is here because of
    how this file gets edited. E0-38's second review pass found that adding a guard
    to `frontend-build` had been done with a blanket edit over
    `if: needs.detect.outputs.frontend == 'true'` — a string that appears in three
    jobs — which gave `lint-frontend` four guards it could not evaluate. E0-40 asks
    for exactly that string to be changed in some of those places and not others.
    A blanket rename passes every assertion in the test above and points the
    production build at a manifest that is not the one it builds from.

    **The mutation this survives:** rename every `detect.outputs.frontend` to
    `detect.outputs.node`. **The near miss that must stay green:** a step that
    reads both because it genuinely needs both — nothing here forbids that for
    these two gates, only the reverse.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)

    unfindable = [
        f"  {tool} — nothing in {ci_workflow_path.name} runs {pattern.pattern!r}"
        for tool, pattern in RUNS_IN_THE_FRONTEND_TREE.items()
        if not steps_running(jobs, pattern)
    ]
    assert not unfindable, "\n".join(
        [
            "These gates could not be found in the workflow, so this control asserted nothing:",
            *unfindable,
            "",
            "This test is what stops a blanket rename of `detect.outputs.frontend` passing as a "
            "probe split, and it can only do that while it can still find the two gates that must "
            "not be renamed.",
        ]
    )

    renamed: list[str] = []
    for tool, pattern in RUNS_IN_THE_FRONTEND_TREE.items():
        for job_name, label, step in steps_running(jobs, pattern):
            read = detect_outputs_read_by(step)
            if FRONTEND not in read:
                renamed.append(
                    f"  {job_name} / {label!r} runs {tool} and consults "
                    f"{sorted(read) or 'no probe at all'}"
                )

    assert not renamed, "\n".join(
        [
            f"These gates no longer wait on the `{FRONTEND}` probe:",
            *renamed,
            "",
            "E0-40 decision 1: 'the production-build and bundle-budget gates keep waiting on "
            "`frontend/package.json`, which is still legitimately absent until E1'. Pointing them "
            "at the root manifest makes them run on every pull request from now on, in a "
            "directory that holds no application to build.",
            "",
            "The likely cause is a blanket edit. The string this ticket changes appears in "
            "several jobs and only some of them are its subject — which is how E0-38's second "
            "review pass found four unevaluable guards on `lint-frontend`.",
        ]
    )


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
