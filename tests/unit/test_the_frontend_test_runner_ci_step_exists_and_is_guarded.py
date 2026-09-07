"""The `lint-frontend` job gains a vitest step, wired to the same short-circuit as its neighbours — ticket E4-16.

E4-16's scope: "The CI gate: a frontend-test step in the job family the change
detection already routes frontend diffs to, red meaning stop, with no tolerance
flag." Acceptance criterion 2: "A frontend diff trips the new gate through the
change-detection route; a docs-only diff does not — both directions asserted
the way the existing detection tests assert job selection." The known trap
named in the ticket: "A gate added but not routed — the change-detection
classifier decides which diffs run which jobs; a new step in an unrouted job
is a gate that never fires."

The settled design (pre-arbitrated, not this module's to relitigate): the
`test` script in `frontend/package.json` is `"vitest run"`, and CI runs it as
`npm run test --workspace frontend` inside the existing `lint-frontend` job
("Fast · tsc + eslint"), guarded per-step by
`if: needs.changed.outputs.inert != 'true'` exactly like that job's other work
steps — no new job, no change to `changed` or `detect`.

**This module does not re-derive the classifier's correctness.** Whether an
arbitrary path under `frontend/` is classified not-inert, and whether an
arbitrary documentation-only diff is classified inert, is already proven
generically in
`test_a_documentation_only_diff_does_not_run_the_expensive_gates.py`
(`test_a_diff_of_only_inert_documentation_is_classified_inert` and
`test_a_path_nobody_has_classified_is_not_inert`), over `is_inert` itself
rather than over any one step that reads its answer. What this module adds is
narrower and is the whole of what a new step needs proven of it: that the step
exists, that it runs the settled command, and that it is wired into the same
`needs.changed.outputs.inert != 'true'` guard every other step in this job
already uses — which is "membership" in an already-correct mechanism, not a
second copy of it.

That membership claim is checked two ways. First, the existing coverage tests
in that sibling module —
`test_every_expensive_gate_reaches_the_classification_and_conditions_its_work_on_it`
and `test_no_expensive_gate_is_guarded_the_wrong_way_round` — already sweep
every step in `lint-frontend` matching
`EXPENSIVE_COMMANDS["an npm install or workspace script"]`, which is the
pattern `^\\s*npm\\s+(?:ci|run\\s+[A-Za-z0-9:_-]+)\\b` — wide enough to match
`npm run test --workspace frontend` without being told about this ticket, the
same way it was widened for `npm run typecheck` and `npm run lint` in E1-04
rather than being taught a third named command. So once the vitest step lands
guarded, those two sibling tests extend to it with no edit here. **No entry is
added to `EXPENSIVE_COMMANDS` or `EXPENSIVE_GATES` by this ticket** — the
floor already reaches the settled command, and adding a redundant, narrower
entry that matches nothing until the step exists would only turn an unrelated
existing test red for the same reason this module's own tests are red, holding
the same fact in two places (`docs/MISTAKES.md` entry 19).

Second, and directly: the two tests below find the specific step by its own
command text and assert its existence and its guard sense on their own terms,
so this ticket's criterion is provable without waiting on, or depending on,
the sibling module continuing to look the way it looks today.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from test_a_documentation_only_diff_does_not_run_the_expensive_gates import (
    EXPENSIVE_COMMANDS,
    GUARDED,
    SWITCHED_OFF_BY_INERT,
    classification_prefixes,
    guard_sense,
    guard_verdict,
    jobs_of,
    signature_steps,
)

LINT_FRONTEND_JOB = "lint-frontend"

# The one command this ticket adds, and the one this module looks for by name
# rather than by the broader family pattern — the broader pattern is what the
# sibling module's coverage tests already sweep, and is imported above rather
# than restated. `(?!:)` is load-bearing and `\b` alone would not do the same
# job: a word boundary sits between "test" and a following `:` exactly as it
# does before a space, so `npm run test:e2e` — the shape of the root
# package's own `test:e2e` script — would otherwise be misread as this step.
VITEST_COMMAND = "npm run test --workspace frontend"
VITEST_STEP_PATTERN = re.compile(r"^\s*npm\s+run\s+test(?!:)\b", re.MULTILINE)

WORKSPACE_SCRIPT_PATTERN = EXPENSIVE_COMMANDS["an npm install or workspace script"]


def vitest_steps_in(job: Any) -> list[tuple[str, dict[str, Any]]]:
    """Every step in `job` that runs the settled vitest command, by name and body."""
    return signature_steps(job, VITEST_STEP_PATTERN)


def test_the_lint_frontend_job_gains_one_step_that_runs_the_settled_vitest_command(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """Half of criterion 2 and all of scope's "a frontend-test step": the step exists and says what it runs.

    The settled design names the command exactly: `npm run test --workspace
    frontend`. This does not accept a step that merely mentions vitest, or one
    that runs `vitest run` directly inside `frontend/` — a step that bypasses
    the package script would leave `frontend/package.json`'s own `test` entry
    unread by CI, which is a different and weaker gate than the one the
    ticket settles.

    **The mutation this survives:** no step added at all, which is the trap
    the ticket names by name — "a gate added but not routed" starts from "a
    gate not added". **The near miss that must stay green:** the step running
    with extra flags after the settled command (`npm run test --workspace
    frontend -- --reporter=dot`), since the ticket does not forbid that and a
    test that demanded an exact, unextended string would fail the day someone
    added a reporter flag for CI legibility.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)

    assert LINT_FRONTEND_JOB in jobs, (
        f"{ci_workflow_path} declares no `{LINT_FRONTEND_JOB}` job (it declares {sorted(jobs)}). "
        "E4-16 adds its step to that job by name; if it has been renamed, rename it here too."
    )

    found = vitest_steps_in(jobs[LINT_FRONTEND_JOB])
    assert found, (
        f"No step in `{LINT_FRONTEND_JOB}` runs `{VITEST_COMMAND}`.\n"
        "\n"
        "E4-16's settled design: `frontend/package.json` gains a `test` script (`vitest run`), "
        "and CI runs it as `npm run test --workspace frontend` inside `Fast · tsc + eslint`. "
        "That step does not exist yet."
    )

    assert len(found) == 1, (
        f"`{LINT_FRONTEND_JOB}` has more than one step running the settled vitest command: "
        f"{[name for name, _ in found]}. One step is what the settled design describes; if there "
        "are genuinely two, say why in the workflow and point this module at the one that matters."
    )

    step_name, step = found[0]
    run_text = str(step.get("run") or "")
    assert VITEST_COMMAND in run_text, (
        f"`{LINT_FRONTEND_JOB}` / {step_name!r} matches the vitest pattern but its `run:` text does "
        f"not contain the settled command `{VITEST_COMMAND}` verbatim:\n{run_text}\n"
        "\n"
        "Running `vitest run` directly, or against a different workspace flag, would bypass "
        "`frontend/package.json`'s own `test` script — the settled design runs the manifest's "
        "script through the workspace, the same way `typecheck` and `lint` already do in this job."
    )

    assert WORKSPACE_SCRIPT_PATTERN.search(run_text), (
        f"`{LINT_FRONTEND_JOB}` / {step_name!r} runs `{run_text.strip()}`, which the settled "
        "command should but does not match against "
        "`EXPENSIVE_COMMANDS['an npm install or workspace script']` in "
        "test_a_documentation_only_diff_does_not_run_the_expensive_gates.py. That pattern is what "
        "sweeps this job's steps into the sibling module's guard-existence and guard-direction "
        "tests; a step outside it is a step neither of those already-standing tests would ever "
        "look at."
    )


def test_the_vitest_step_is_switched_off_by_an_inert_diff_and_by_nothing_else(
    ci_workflow_path: Path, ci_workflow: dict[str, Any]
) -> None:
    """The other half of criterion 2: both directions of routing, through one guard-sense check.

    `SWITCHED_OFF_BY_INERT` is a single verdict that already encodes both
    directions of the acceptance criterion: it holds exactly when the
    condition is `needs.changed.outputs.inert != 'true'` — true (the step
    runs) on a diff the classifier calls not-inert, which a change under
    `frontend/` always is by construction of `is_inert`, and false (the step
    is skipped) on a diff the classifier calls inert, which a docs-only diff
    always is. So one assertion of membership in that verdict is both
    directions of E4-16's criterion 2, given the classifier's own correctness,
    which is proven elsewhere and not re-derived here (see the module
    docstring).

    **The mutation this survives:** the step guarded `== 'true'` instead of
    `!= 'true'` — E0-38's third review pass made exactly this slip on another
    job and the whole unit suite stayed green — which would run the vitest
    suite only on documentation-only diffs and never on a change that touches
    a component. **The near miss that must stay green:** the guard spelled
    through a different but equivalent prefix, such as reading
    `needs.changed.outputs.inert` through a job-level `env:` copy rather than
    directly — `classification_prefixes` already resolves either shape, and
    duplicating that resolution here rather than importing it is exactly the
    two-copies hazard `docs/MISTAKES.md` entry 19 warns about.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)

    assert (
        LINT_FRONTEND_JOB in jobs
    ), f"{ci_workflow_path} declares no `{LINT_FRONTEND_JOB}` job (it declares {sorted(jobs)})."

    found = vitest_steps_in(jobs[LINT_FRONTEND_JOB])
    assert found, (
        f"No step in `{LINT_FRONTEND_JOB}` runs `{VITEST_COMMAND}`, so there is no guard to read. "
        "See test_the_lint_frontend_job_gains_one_step_that_runs_the_settled_vitest_command for "
        "the existence half of this criterion."
    )

    prefixes = classification_prefixes(jobs, LINT_FRONTEND_JOB)
    assert prefixes, (
        f"`{LINT_FRONTEND_JOB}` has no route to the diff classification at all — it neither "
        "classifies for itself nor needs a job that does. Every other step in this job already "
        "reads `needs.changed.outputs.inert`, so this would mean the job's own wiring to `changed` "
        "has been removed, not that the vitest step alone lacks a route."
    )

    step_name, step = found[0]
    condition = str(step.get("if") or "")
    verdict = guard_verdict(condition, prefixes)

    assert verdict == GUARDED, (
        f"`{LINT_FRONTEND_JOB}` / {step_name!r} does not switch on the diff classification at all "
        f"(`if: {condition or '(none)'}`), so a documentation-only pull request would still run "
        "the vitest suite, and E4-16's criterion 2 — 'a docs-only diff does not' trip this gate — "
        "does not hold."
    )

    sense = guard_sense(condition, prefixes)
    assert sense == SWITCHED_OFF_BY_INERT, (
        f"`{LINT_FRONTEND_JOB}` / {step_name!r} carries `if: {condition}`, which this module reads "
        f"as {sense!r} rather than {SWITCHED_OFF_BY_INERT!r}.\n"
        "\n"
        "The step must be switched OFF by an inert diff (`!= 'true'`), the same sense every other "
        "step in this job already uses. The reversed sense — `== 'true'` — is the one-character "
        "slip E0-38's third review pass made on a different job: the vitest suite would then run "
        "only on documentation-only diffs and never on a change that touches a component, with the "
        "required check reporting success either way."
    )
