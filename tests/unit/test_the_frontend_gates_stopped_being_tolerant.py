"""The four frontend gates stop being tolerant — ticket E1-04, criterion 2.

ADR 0002 shipped every gate tolerant: the `detect` job probes the tree, each gate
runs its real check when its target exists, and otherwise prints a `::notice::`
naming the ticket that will make it enforcing and exits 0. Removing a tolerance is
an acceptance criterion of the ticket that lands the code, and E1-04 is that ticket
for four of them — `tsc`, `eslint`, the production build and the bundle budget.

**A tolerant job looks exactly like a passing job**, which ADR 0002 calls the real
cost of the decision, and E0-36's review then found the cost was larger than that:
the honesty of a tolerant gate rests entirely on its probe, and two of three probes
were answering false over trees that held the thing (`docs/MISTAKES.md` entry 36).
The way out of that shape is not a better probe, it is a gate that runs. So what
this module asserts is that the branch is *gone* rather than that it is correct:

- No step in `frontend-build` or `lint-frontend` consults a `detect` output any
  more. Those two jobs' work runs on every pull request that is not
  documentation-only, and there is nothing left to decide.
- Neither job carries a conditional `::notice::` standing in for work it did not
  do, except the documentation short-circuit's, which is E0-38's and stays.
- The frontend workspace declares the scripts those gates run, and the fast gate
  runs them against the workspace rather than only against the repository root —
  where `tsc` and `eslint` have been reading `playwright.config.ts` and the §9.2
  specs since E0-40, and nothing else.

**The `evals` gate is this module's control and not an oversight.** SPEC §14.3
gives the AI eval floors to E2 — "turns the AI eval floors enforcing, the last CI
tolerance E0 left" — so that job is still legitimately tolerant, and the reader
below is required to find its tolerance before its verdict about the two frontend
jobs is believed. A reader that could not see a tolerance branch would report both
frontend jobs clean over a workflow that had not been touched (`docs/MISTAKES.md`
entry 35: require the control to find the thing on a subject that certainly has
it).

**What lives elsewhere.** Which probe each gate waits on, and the `Makefile`'s copy
of the same conditions, are
`tests/unit/test_the_detect_probes_see_the_files_their_jobs_run.py`'s subject and
E1-04's edits to the probe set are there. That the newly-enforcing work also
short-circuits on a documentation-only diff is
`test_a_documentation_only_diff_does_not_run_the_expensive_gates.py`'s. This module
is the one that says the tolerance is gone.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_MANIFEST = REPO_ROOT / "frontend" / "package.json"

# The two jobs E1-04 flips, by the names E0-38 and E0-40 already address them by.
FRONTEND_BUILD_JOB = "frontend-build"
LINT_FRONTEND_JOB = "lint-frontend"
FLIPPED_JOBS = (FRONTEND_BUILD_JOB, LINT_FRONTEND_JOB)

# The job that is still tolerant, and why. E2 turns the eval floors enforcing;
# until then this is where a tolerance branch certainly exists, which is what makes
# it the control.
STILL_TOLERANT_JOB = "evals"

# The scripts the frontend workspace declares and the fast gate runs. `build` is
# what `frontend-build` has always named — ADR 0083's narrowed probe asks the
# manifest for it — and `typecheck` and `lint` are what E1-04 adds so that the two
# checkers read the application as well as the repository root.
WORKSPACE_SCRIPTS = ("build", "typecheck", "lint")

# The two the fast gate runs. `build` belongs to the other job.
FAST_GATE_SCRIPTS = ("typecheck", "lint")

# What the production-build job runs, found by the command rather than by the step
# that holds it — the step names are not this ticket's to settle, and a search
# keyed on one would report a clean pipeline over a renamed step
# (`docs/MISTAKES.md` entry 35).
PRODUCTION_BUILD = re.compile(r"^\s*npm\s+run\s+build\b", re.MULTILINE)
BUNDLE_BUDGET = re.compile(r"\bcheck_bundle_size\.py\b")

# The budget the gate reads, and the file E1-04 re-baselines against the first real
# build. A gate run without it measures against whatever the script defaults to,
# which is a number nobody reviewed.
COMMITTED_BUDGET = "ci/bundle-budget.json"

DETECT_OUTPUT = re.compile(r"needs\.detect\.outputs\.([A-Za-z0-9_-]+)")

# E0-38's classification, which every expensive gate is allowed — and required —
# to consult. Named here so the tolerance reader can tell the short-circuit's
# notice apart from ADR 0002's.
CLASSIFICATION = "inert"

NOTICE = "::notice::"

# How a step says it is working on the frontend workspace. npm's own spellings,
# GitHub's `working-directory`, and a plain `cd`. A list rather than one spelling,
# because which of them the implementation uses is not this test's to decide.
IN_THE_WORKSPACE = (
    re.compile(r"--workspace(?:s)?[=\s]+frontend\b"),
    re.compile(r"\s-w[=\s]+frontend\b"),
    re.compile(r"\bcd\s+\.?/?frontend\b"),
)


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


def label_of(step: dict[str, Any], index: int) -> str:
    """What to call a step in a failure message."""
    return str(step.get("name") or step.get("uses") or f"step {index}")


def condition_of(step: dict[str, Any]) -> str:
    """A step's `if:`, as text."""
    return str(step.get("if") or "")


def script_of(step: dict[str, Any]) -> str:
    """A step's `run:`, as text."""
    return str(step.get("run") or "")


def prints_a_notice_guarded_by_a_probe(step: dict[str, Any]) -> bool:
    """ADR 0002's tolerance branch, exactly: a notice that runs when a probe said no.

    Two properties, and both are needed. It prints a workflow notice, and its
    condition reads a `detect` output — which is what a tolerance is, an `else` on
    the question "is the thing this gate checks in the tree at all".

    This is the shape the `evals` control looks for, and it is written to be
    indifferent to whether the same condition also carries E0-38's classification
    clause. A tolerant expensive gate reasonably carries both — print the notice
    when the diff was worth checking and there was nothing to check — and a
    predicate that refused to recognise a two-clause condition would report the
    one job that certainly is tolerant as fully enforcing.
    """
    return bool(NOTICE in script_of(step) and DETECT_OUTPUT.search(condition_of(step)))


def is_a_leftover_notice(step: dict[str, Any]) -> bool:
    """A notice about work that did not run, left behind after its condition went.

    The other half of a half-finished removal: the guard is deleted and the step
    that printed "nothing to build yet" stays, now printing it on every run over a
    tree that builds. Nothing goes red, and the pipeline says something about
    itself that stopped being true.

    E0-38's documentation short-circuit prints a notice of the same shape and is
    legitimate — a gate that did not run because the diff was Markdown has
    something true to say — so a condition that reads the classification is not
    counted. A notice still guarded by a probe is not counted here either; it is
    caught by the probe assertion, which names it more precisely.
    """
    if NOTICE not in script_of(step):
        return False
    condition = condition_of(step).lower()
    return CLASSIFICATION not in condition and not DETECT_OUTPUT.search(condition_of(step))


def reaches_the_workspace(step: dict[str, Any]) -> bool:
    """Whether this step runs where the frontend package is."""
    directory = str(step.get("working-directory") or "").strip()
    if directory and directory.removeprefix("./").split("/")[0] == "frontend":
        return True
    return any(pattern.search(script_of(step)) for pattern in IN_THE_WORKSPACE)


def steps_running_script(job: Any, script: str) -> list[tuple[str, dict[str, Any]]]:
    """Every step of `job` that runs `npm run <script>`, with its label."""
    pattern = re.compile(rf"^\s*npm\s+run\s+{re.escape(script)}\b", re.MULTILINE)
    return [
        (label_of(step, index), step)
        for index, step in enumerate(steps_of(job))
        if pattern.search(script_of(step))
    ]


def declared_scripts() -> dict[str, Any]:
    """The `scripts` block of the frontend workspace manifest."""
    assert FRONTEND_MANIFEST.is_file(), (
        f"{FRONTEND_MANIFEST.relative_to(REPO_ROOT)} does not exist. E1-02 landed it as the "
        "workspace member ADR 0083 decided on, and E1-04 fills it — without it there is no "
        "package for `npm run … --workspace frontend` to run anything in, and the root lockfile "
        "resolves a workspace that is not there."
    )
    try:
        document = json.loads(FRONTEND_MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        pytest.fail(
            f"{FRONTEND_MANIFEST.relative_to(REPO_ROOT)} is not valid JSON ({error}). npm reads it "
            "as the workspace member's manifest and the `detect` job's probe reads it as text, so "
            "a file that does not parse fails the build in two places at once."
        )
    scripts = document.get("scripts")
    return dict(scripts) if isinstance(scripts, dict) else {}


def test_the_frontend_gates_consult_no_probe_and_print_no_tolerance_notice(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """Criterion 2: "the tolerance branches for them are gone from `ci.yml`".

    ADR 0002's pattern is one condition and two steps: the real work runs when the
    probe says the target is there, and a `::notice::` runs when it does not, and
    the job reports **success** either way. E1-04 lands the target, so both halves
    go — the condition because there is nothing left to decide, and the notice
    because there is no longer a case in which it would be true.

    Leaving the condition in place is the version of this that looks done. The
    probe answers true on every checkout from now on, so the pipeline behaves
    correctly and the tolerance is still there, one edit away from switching four
    gates off in silence for anybody who changes what the probe reads — which is
    exactly how E0-40 happened, three tickets ago, in this file.

    **The control is the `evals` job**, which SPEC §14.3 leaves tolerant until E2.
    The reader has to find a tolerance branch there before its silence about these
    two jobs means anything; a reader that recognised no tolerance at all would
    report a workflow nobody had edited as fully enforcing.

    **The mutation this kills:** delete the notice steps and leave
    `if: needs.detect.outputs.frontend == 'true'` on the real ones — or the
    reverse, delete the conditions and leave the notice steps printing on nothing.
    **The near miss that must stay green:** E0-38's documentation short-circuit,
    which is a condition and a notice of exactly this shape on exactly these jobs,
    and which this ticket does not touch.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)

    missing = [name for name in FLIPPED_JOBS if name not in jobs]
    assert not missing, (
        f"{ci_workflow_path} declares no {missing} job (it declares {sorted(jobs)}). E1-04 flips "
        "those two jobs by name; if one has been renamed or folded into another, rename it here "
        "in the same change rather than leaving this module looking for something that is gone."
    )

    control = [
        label_of(step, index)
        for index, step in enumerate(steps_of(jobs.get(STILL_TOLERANT_JOB)))
        if prints_a_notice_guarded_by_a_probe(step)
    ]
    assert control, "\n".join(
        [
            f"This reader found no tolerance branch in the `{STILL_TOLERANT_JOB}` job, which is "
            "the one job that certainly still has one.",
            "",
            "SPEC §14.3 gives the AI eval floors to E2 — 'turns the AI eval floors enforcing, the "
            "last CI tolerance E0 left' — so until then that gate probes for the eval sets and "
            "prints ADR 0002's notice when they are not there.",
            "",
            "Either that has changed, which is a larger finding than this ticket and worth "
            "knowing, or this reader cannot recognise a tolerance branch — in which case it would "
            "report the two frontend jobs clean over a workflow nobody had edited.",
        ]
    )

    probed: list[str] = []
    tolerated: list[str] = []
    for name in FLIPPED_JOBS:
        for index, step in enumerate(steps_of(jobs[name])):
            label = label_of(step, index)
            read = sorted(set(DETECT_OUTPUT.findall(condition_of(step) + "\n" + script_of(step))))
            if read:
                probed.append(f"  {name} / {label!r} consults {read}")
            if is_a_leftover_notice(step):
                tolerated.append(
                    f"  {name} / {label!r} — if: {condition_of(step) or 'nothing'}\n"
                    f"    {script_of(step).strip()[:160]}"
                )

    assert not probed, "\n".join(
        [
            "These steps still wait on a `detect` probe:",
            *probed,
            "",
            "E1-04 lands the frontend, so the question those probes ask is answered by the tree "
            "on every branch from now on. ADR 0002: 'Removing a tolerance is an acceptance "
            "criterion of the ticket that lands the corresponding code.'",
            "",
            "A condition that is always true is not harmless. It is a switch nobody is watching, "
            "and the failure it produces has no symptom — the steps turn themselves off, the "
            "notice runs in their place, and the job reports success. That is `docs/MISTAKES.md` "
            "entry 36, which this repository has recorded three times and lived with for the "
            "length of E0.",
            "",
            "The documentation-only short-circuit is a different clause and stays: "
            f"`needs.changed.outputs.{CLASSIFICATION}`, not `needs.detect.outputs.*`.",
        ]
    )

    assert not tolerated, "\n".join(
        [
            "These steps print a notice about work that did not run, with nothing deciding "
            "whether it did:",
            *tolerated,
            f"  the tolerance the control found in `{STILL_TOLERANT_JOB}`: {control}",
            "",
            "ADR 0002's tolerant gate is a condition and a notice together, and this is the half "
            "of the removal that leaves no symptom: the guard goes, the step that said 'nothing "
            "to build yet' stays, and it now prints that on every run over a tree that builds.",
            "",
            "E0-38's documentation short-circuit prints a notice of the same shape and is not "
            "counted here — a gate that did not run because the diff was Markdown has something "
            "true to say. Neither is a notice still guarded by a probe: that one is reported "
            "above, where the message is about the guard rather than the sentence.",
            "",
            "One case this cannot tell apart: a notice that reports a *measurement* — the "
            "measured bundle size, the build's duration — is not a tolerance at all and would "
            "land here. If that is what this is, it is this assertion that is wrong, and the "
            "route is `docs/disputes/E1-04-NN.md` rather than an edit to the test.",
        ]
    )


def test_the_frontend_workspace_declares_the_scripts_its_gates_run() -> None:
    """The manifest half: `npm run <script> --workspace frontend` has something to run.

    ADR 0083 landed `frontend/package.json` as a workspace member with no scripts
    at all, and narrowed the `detect` probe onto the `build` script for exactly
    that reason — the manifest's presence stopped answering any question, so the
    probe had to name what the job actually runs. E1-04 fills it, and the three
    scripts are what the four gates invoke: the production build, and the two
    checkers that now read the application rather than only the repository root.

    A gate that runs `npm run typecheck --workspace frontend` against a package
    that declares no such script fails loudly, so this is not a silent hazard —
    it is the half of the flip that has to land in the same commit as the workflow
    edit, and asserting it here says which of the two is missing when they arrive
    apart.

    **The mutation this kills:** land the workflow steps and leave the manifest as
    E1-02's stub, or drop one of the three. **The near miss that must stay green:**
    whatever each script actually runs — `tsc -b`, `tsc --noEmit`, `vite build`,
    `eslint .` — which is the frontend toolchain's business and not this module's.
    """
    scripts = declared_scripts()

    assert scripts, "\n".join(
        [
            f"{FRONTEND_MANIFEST.relative_to(REPO_ROOT)} declares no `scripts` block.",
            "",
            "E1-02 landed this manifest deliberately empty — ADR 0083: 'a private manifest of its "
            "own, landed empty by E1-02 for E1-04 to fill'. E1-04 is the ticket that fills it, "
            "and until it does there is no build for the production-build gate to run and no "
            "checker for the fast gate to run over the application.",
        ]
    )

    missing = [
        name
        for name in WORKSPACE_SCRIPTS
        if not isinstance(scripts.get(name), str) or not str(scripts.get(name)).strip()
    ]

    assert not missing, "\n".join(
        [
            f"{FRONTEND_MANIFEST.relative_to(REPO_ROOT)} declares no {missing}:",
            f"  declared: {sorted(scripts)}",
            "",
            "`build` is what the production-build gate and the bundle budget run, and what the "
            "`detect` probe read the manifest for while that gate was still tolerant (ADR 0083). "
            "`typecheck` and `lint` are what E1-04 adds so that `tsc` and `eslint` read the "
            "application — since E0-40 they have been reading `playwright.config.ts` and the "
            "§9.2 specs at the repository root, and nothing else.",
            "",
            "What each one runs is the frontend toolchain's business. That each one exists is "
            "what the gates depend on.",
        ]
    )


def test_the_production_build_and_the_bundle_budget_still_run(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """The other two gates: they run, they run in the workspace, and they read the budget.

    This is the control the rest of the module rests on and a criterion in its own
    right. Every other assertion here is about what these jobs no longer do, and a
    job whose real steps have been deleted along with its tolerance satisfies all
    of them perfectly: no probe consulted, no notice printed, nothing run.

    The budget file is named because a bundle gate run without one measures against
    whatever the script decides for itself. E1-04's scope says the number "is set
    here and recorded where the gate reads it, with one sentence on how it was
    chosen", and `ci/bundle-budget.json` is that place — the file's own comment
    says the current values are an estimate to be re-baselined against the first
    real production build, which is this ticket.

    **The mutation this kills:** delete the build step, the budget step, or the
    `--budget` argument while removing the tolerance around them. **The near miss
    that must stay green:** any step layout, any step names, and any numbers in the
    budget file — what those numbers are is the implementer's measurement, and
    `scripts/ci/test_ci_scripts.py` is where the file's shape is asserted.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)

    job = jobs.get(FRONTEND_BUILD_JOB)
    assert job, (
        f"{ci_workflow_path} declares no `{FRONTEND_BUILD_JOB}` job (it declares {sorted(jobs)}). "
        "That is the job E1-04 makes enforcing; if it has been renamed, rename it here in the "
        "same change."
    )

    building = [
        (label_of(step, index), step)
        for index, step in enumerate(steps_of(job))
        if PRODUCTION_BUILD.search(script_of(step))
    ]
    budgeting = [
        (label_of(step, index), step)
        for index, step in enumerate(steps_of(job))
        if BUNDLE_BUDGET.search(script_of(step))
    ]

    assert building, (
        f"No step in `{FRONTEND_BUILD_JOB}` runs the production build. Every other assertion in "
        "this module is about what this job no longer does — no probe, no tolerance notice — and "
        "an empty job satisfies all of them.\n"
        "\n"
        "E1-04 acceptance criterion 2: the four gates 'fail on their planted defects and pass on "
        "the real tree'. A gate with no step cannot do either."
    )
    assert budgeting, (
        f"No step in `{FRONTEND_BUILD_JOB}` runs `check_bundle_size.py`. The bundle budget is one "
        "of the four gates this ticket makes enforcing, and SPEC §10's performance rules are why "
        "it exists: Pulse renders inside an LMS iframe on campus wifi, and first paint is a "
        "response-rate problem."
    )

    outside = [
        f"  {FRONTEND_BUILD_JOB} / {label!r} runs the production build and names no workspace"
        for label, step in building
        if not reaches_the_workspace(step)
    ]
    assert not outside, "\n".join(
        [
            "The production build does not say which package it builds:",
            *outside,
            "",
            "`npm run build` at the repository root runs the root package's script, not the "
            "frontend's. ADR 0083: `npm run build --workspace frontend` runs a member's script.",
        ]
    )

    unbudgeted = [
        f"  {FRONTEND_BUILD_JOB} / {label!r}: {script_of(step).strip()[:200]}"
        for label, step in budgeting
        if COMMITTED_BUDGET not in script_of(step)
    ]
    assert not unbudgeted, "\n".join(
        [
            f"The bundle gate does not read `{COMMITTED_BUDGET}`:",
            *unbudgeted,
            "",
            "A budget check run without the committed file measures against whatever the script "
            "decides for itself, which is a limit nobody reviewed and a diff nobody can see. "
            "E1-04's scope: the number 'is set here and recorded where the gate reads it, with "
            "one sentence on how it was chosen'.",
            "",
            "If the budget moved to another path, this constant moves with it — one line, at the "
            "top of this module.",
        ]
    )


def test_the_fast_gate_type_checks_and_lints_the_frontend_workspace(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """E1-04's scope: `tsc` and `eslint` become enforcing over the application.

    Two of the four gates this ticket flips are the checkers, and the flip is not
    only the removal of a tolerance: since E0-40 the root `tsc` and `eslint` have
    been reading `playwright.config.ts` and the end-to-end specs, which is
    genuinely all the TypeScript this repository held. E1-04 lands several hundred
    lines more of it, in a package with its own `tsconfig` and its own eslint
    configuration, and a gate that goes on reading only the root would report a
    clean pipeline over every line of the new application.

    That failure is this repository's most-recorded one arriving through a
    workspace boundary rather than through a probe: a checker that exits 0 having
    read nothing (`docs/MISTAKES.md` entry 36, and
    `test_the_typescript_checker_reads_the_typescript_this_repository_holds` for
    the same shape one file over).

    **What is asserted:** the fast gate runs `npm run typecheck` and `npm run lint`,
    and each runs where the frontend package is — by npm's workspace flag, by
    `working-directory`, or by changing into the directory. Which of those is the
    implementation's choice.

    **The mutation this kills:** leave `lint-frontend` running only the root `npx
    tsc --noEmit` and `npx eslint .`, which is what it does today and what a flip
    that only deleted the tolerance would leave behind. **The near miss that must
    stay green:** the root checkers staying exactly where they are — nothing here
    asks for them to move, and
    `test_the_node_facing_gates_wait_on_the_root_package_manifest` requires them to
    stay.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)

    job = jobs.get(LINT_FRONTEND_JOB)
    assert job, (
        f"{ci_workflow_path} declares no `{LINT_FRONTEND_JOB}` job (it declares {sorted(jobs)}). "
        "That is the fast gate that runs the two checkers; if it has been renamed, rename it here "
        "in the same change."
    )

    unrun: list[str] = []
    outside: list[str] = []
    for script in FAST_GATE_SCRIPTS:
        found = steps_running_script(job, script)
        if not found:
            unrun.append(f"  npm run {script} — no step in `{LINT_FRONTEND_JOB}` runs it")
            continue
        for label, step in found:
            if not reaches_the_workspace(step):
                outside.append(
                    f"  {LINT_FRONTEND_JOB} / {label!r} runs `npm run {script}` and names no "
                    "workspace"
                )

    assert not unrun, "\n".join(
        [
            "The fast gate does not check the frontend workspace:",
            *unrun,
            "",
            "Since E0-40 the root `tsc` and `eslint` read `playwright.config.ts` and the §9.2 "
            "specs — all the TypeScript this repository held. E1-04 lands the application, and a "
            "gate that goes on reading only the root exits 0 over every line of it.",
            "",
            "E1-04 flips four gates, and two of them are these. `frontend/package.json` declares "
            "the scripts; this is the job that runs them.",
        ]
    )

    assert not outside, "\n".join(
        [
            "These steps run a workspace script without saying which workspace:",
            *outside,
            "",
            "`npm run typecheck` at the repository root runs the *root* package's script, which "
            "is not the one the frontend declares. ADR 0083: 'npm ci at the root installs every "
            "member, and `npm run build --workspace frontend` runs a member's script.'",
            "",
            "Any of the three spellings satisfies this — `--workspace frontend`, `-w frontend`, "
            "a `working-directory`, or a `cd`. What it cannot be is silent about which package it "
            "is checking.",
        ]
    )
