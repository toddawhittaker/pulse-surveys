"""The `evals` job stops being tolerant and starts firing on the right diffs — ticket E2-12.

ADR 0002's last tolerance. Today the `evals` job prints a `::notice::` saying the
first eval set and the floors that gate on it "are E2's, and this job stays
tolerant until then", and reports success. E2-12 lands the set and the floors, and
ADR 0002 makes removing the tolerance an acceptance criterion of the ticket that
lands the code.

**What replaces it is a step-level condition and not a job-level one**, and that
is settled rather than open. E0-36 made the aggregate `ci` check treat `skipped`
as a failure, so a job switched off by an `if:` fails the one check branch
protection points at, on every pull request that does not touch the AI surface.
`tests/unit/test_the_aggregate_ci_check_sees_an_upstream_failure.py` already
refuses a job-level `if:` over every job in the file, so nothing here repeats it.

**The condition composes with the classification that is already there.** Two
committed modules read these conditions —
`test_the_detect_probes_see_the_files_their_jobs_run.py` requires every expensive
gate's step to mention `needs.changed.outputs.inert`, and
`test_a_documentation_only_diff_does_not_run_the_expensive_gates.py` reads the
operator. So the new clause is added to the existing one rather than put in its
place, and the tempting repair after a red round — touching one of those two
modules — is the wrong one.

**One of the assertions here exists only to keep a committed test honest**, and it
is the ordering one. The sibling module's reader takes the *first* comparison in a
condition that references `needs.changed.outputs.*` against the literal `'true'`,
and reads its operator. A condition leading with `ai_surface == 'true'` reads to
it as "this step runs only when the diff is inert" — a false red on a guard that
is in fact correct, on a module this ticket may not touch. Leading with
`inert != 'true'` costs nothing and keeps that reader right.

**Every assertion in this module is red until the implementer's half lands.**
Unlike the runner and the eval set, none of this is under `tests/`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# What `python -m tests.evals.runner` looks like in a `run:` block. The same
# pattern `test_a_documentation_only_diff_does_not_run_the_expensive_gates.py`
# uses to recognise this gate, so the two modules cannot come to disagree about
# which job is the eval job.
EVAL_RUNNER = re.compile(r"^\s*python\s+-m\s+tests\.evals\.runner\b", re.MULTILINE)

# The flag the documented invocation carries.
ENFORCE_FLOORS = "--enforce-floors"

CHANGED_JOB = "changed"

# The two classifications the `changed` job must publish once this ticket lands.
# Compared as a whole set, never by containment: `docs/MISTAKES.md` entry 36 —
# "assert the whole set of outputs rather than the one you have in mind" — so a
# third output that arrived without a ticket fails with its name in the message,
# and a withdrawn `inert` fails as loudly as a missing `ai_surface`.
INERT = "inert"
AI_SURFACE = "ai_surface"
CLASSIFICATIONS = (INERT, AI_SURFACE)

INERT_REFERENCE = f"needs.{CHANGED_JOB}.outputs.{INERT}"
AI_SURFACE_REFERENCE = f"needs.{CHANGED_JOB}.outputs.{AI_SURFACE}"

# The manual trigger E2-12's scope names: "(b) on demand via `workflow_dispatch`".
WORKFLOW_DISPATCH = "workflow_dispatch"

# A comparison against a quoted literal, with the operator captured. The same
# shape the sibling module reads conditions with.
COMPARISON = re.compile(
    r"(?P<reference>needs\.[A-Za-z0-9_.\-]+)\s*(?P<operator>==|!=)\s*(?P<quote>['\"])"
    r"(?P<literal>[^'\"]*)(?P=quote)"
)

# A line whose first word is one of these runs nothing.
NOT_A_COMMAND = ("echo", "printf", ":")

SHELL_COMMENT = re.compile(r"#.*$")

# The tolerance as it stands today, copied whole out of `.github/workflows/ci.yml`
# — the line it begins on included, `docs/MISTAKES.md` entry 3, whose third
# incident was a pattern that matched nothing and passed against the exact text it
# existed to catch. The search below is run against this sample before it is
# trusted against the file, so a reader that has gone blind says so instead of
# reporting a tolerance that has been removed.
TOLERANT_NOTICE_AS_IT_STANDS = (
    '          echo "::notice::No tests/evals runner yet. E0-13 builds the gateway; the '
    "first eval set and the floors that gate on it are E2's, and this job stays tolerant "
    'until then."'
)

# What makes a notice a *tolerance* notice rather than an ordinary explanation.
# Two phrases, because either one on its own would catch the wrong thing: "stays
# tolerant" is the admission, and "no tests/evals runner yet" is the claim that is
# now false.
TOLERANCE_PHRASES = (
    re.compile(r"stays\s+tolerant", re.IGNORECASE),
    re.compile(r"no\s+tests/evals\s+runner\s+yet", re.IGNORECASE),
)


def jobs_of(workflow: dict[str, Any], workflow_path: Path) -> dict[str, Any]:
    """Every job in the workflow, or a failure naming what was read instead."""
    jobs = workflow.get("jobs") or {}
    if not jobs:
        pytest.fail(
            f"{workflow_path} declares no jobs, or did not parse. Every assertion in this "
            "module is about a job in that file, and an empty mapping satisfies most of them."
        )
    return dict(jobs)


def steps_of(job: Any) -> list[dict[str, Any]]:
    """The steps of one job, as a list of mappings."""
    return [step for step in ((job or {}).get("steps") or []) if isinstance(step, dict)]


def needs_of(job: Any) -> list[str]:
    """The jobs one job waits on, whether it named one or several."""
    declared = (job or {}).get("needs")
    if declared is None:
        return []
    if isinstance(declared, str):
        return [declared]
    return [str(name) for name in declared]


def command_lines(script: str) -> list[str]:
    """Every line of a `run:` block that could execute something."""
    joined = script.replace("\\\n", " ")
    found: list[str] = []
    for raw in joined.splitlines():
        line = SHELL_COMMENT.sub("", raw).strip()
        if not line or line.split()[0] in NOT_A_COMMAND:
            continue
        found.append(line)
    return found


def label_of(step: dict[str, Any], index: int) -> str:
    """How a step is named in a failure message."""
    return str(step.get("name") or step.get("uses") or f"step {index}")


def does_real_work(step: dict[str, Any]) -> bool:
    """Whether this step costs anything: an action, or a command that is not a notice.

    A `uses:` step counts. `actions/setup-python` and the locked install are the
    two that make this job expensive before the runner is even reached, and a
    condition on the runner alone would leave them running on every pull request
    in the repository.

    **`actions/checkout` is excluded and that is not an oversight.** Every job in
    this workflow checks out unconditionally, it costs seconds, and the steps that
    consult the classification need the tree present before they can decide
    anything. Requiring a condition on it would be this module inventing a rule
    the ticket does not have.
    """
    uses = str(step.get("uses") or "")
    if uses:
        return not uses.startswith("actions/checkout")
    return bool(command_lines(str(step.get("run") or "")))


def evals_job(jobs: dict[str, Any], workflow_path: Path) -> tuple[str, Any]:
    """The job that runs the eval runner, found by the command rather than by its name.

    Keyed on the command because the job's name is not this ticket's to settle and
    a search keyed on one would report a clean pipeline over a rename
    (`docs/MISTAKES.md` entry 35 — the control's inventory has to come from
    somewhere the guarded structure cannot shrink).
    """
    for name, job in jobs.items():
        for step in steps_of(job):
            if EVAL_RUNNER.search(str(step.get("run") or "")):
                return name, job
    pytest.fail(
        f"nothing in {workflow_path.name} runs `python -m tests.evals.runner`, so there is "
        "no eval gate to assert about. Either the job is gone — a larger finding than this "
        "ticket — or it invokes the runner some other way, and EVAL_RUNNER at the top of "
        "this file is the one line that changes.\n"
        "\n"
        "This is the canary rather than a formality: with the pattern matching nothing, a "
        "workflow whose eval steps were guarded by nothing at all would pass every "
        "assertion below."
    )


def conditions_of(step: dict[str, Any]) -> str:
    """A step's `if:`, as text."""
    return str(step.get("if") or "")


def test_the_changed_job_publishes_both_classifications(
    ci_workflow: dict[str, Any], ci_workflow_path: Path
) -> None:
    """E2-12: the `changed` job emits `ai_surface` as a second output.

    `docs/MISTAKES.md` entry 36 — a probe that decides whether a gate runs is
    itself a gate — and its rule is to assert the whole set of outputs rather than
    the one you have in mind. So this compares the mapping: a missing `ai_surface`
    is the eval gate with nothing to wait on, a missing `inert` is E0-38's
    documentation-only saving gone from six other gates at once, and an output
    nobody here has heard of is a decision somebody made without a ticket.

    **The half that is easy to miss.** Publishing the output and never filling it
    leaves every reader holding the empty string, and `'' == 'true'` is false — so
    a step guarded by `ai_surface == 'true'` never runs again, with the job green.
    That is asserted from the classifier's side in
    `test_the_changed_job_classifies_an_ai_surface.py`; here it is the name.

    **The mutation this kills:** add the classification to the script and forget
    the `outputs:` block, which is the half a reviewer's eye slides over.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)
    job = jobs.get(CHANGED_JOB)
    assert job, (
        f"{ci_workflow_path} declares no `{CHANGED_JOB}` job (it declares {sorted(jobs)}). "
        "E0-38 built it and E2-12 grows it; if it has been renamed, CHANGED_JOB in this "
        "file is the one line that changes."
    )

    published = set((job.get("outputs") or {}).keys())
    assert published == set(CLASSIFICATIONS), "\n".join(
        [
            f"the `{CHANGED_JOB}` job publishes {sorted(published)} and E2-12 settles "
            f"{sorted(CLASSIFICATIONS)}.",
            f"  missing:   {sorted(set(CLASSIFICATIONS) - published) or 'nothing'}",
            f"  unexpected: {sorted(published - set(CLASSIFICATIONS)) or 'nothing'}",
            "",
            f"`{AI_SURFACE}` is what decides whether SPEC §9.3's floors run at all. Without "
            "it the eval steps have nothing to wait on, and with it declared and never "
            "filled every reader holds the empty string — which is not 'true', so the steps "
            "never run and the job stays green.",
        ]
    )


def test_the_workflow_can_be_run_on_demand(ci_workflow: dict[str, Any]) -> None:
    """E2-12: "(b) on demand via `workflow_dispatch`".

    The eval floors fire on AI-touching diffs, which is the right default and is
    not enough on its own. A provider changes a model behind a stable identifier,
    a floor needs re-measuring before it is moved, a key is rotated and somebody
    has to know the wiring still works — none of those is a diff, and without a
    manual trigger the only way to run the gate is to push a change to a file that
    does not need changing.

    **The mutation this kills:** wire the step-level `github.event_name ==
    'workflow_dispatch'` clause and never add the trigger, so the clause is dead
    text that reads as a working escape hatch.
    """
    # PyYAML parses a bare `on:` key as the boolean `True` under YAML 1.1's
    # truthy-word rules, so the trigger block is reached under either key. A
    # reader that looked only for the string would report a workflow with no
    # triggers at all — and would then say `workflow_dispatch` is missing, which
    # is true of the wrong thing.
    triggers = ci_workflow.get("on", ci_workflow.get(True))
    assert triggers is not None, (
        "the workflow declares no triggers, or this reader could not find them under "
        "either the `on` key or the boolean key PyYAML turns it into."
    )
    names = set(triggers) if isinstance(triggers, dict | list) else {str(triggers)}

    assert WORKFLOW_DISPATCH in names, (
        f"the workflow triggers on {sorted(names)} and not on `{WORKFLOW_DISPATCH}`. E2-12's "
        "scope names three situations in which the eval suite runs, and this is the second: "
        "'on demand via workflow_dispatch'. Without the trigger, a step condition naming it "
        "can never be true."
    )


def test_every_step_that_costs_anything_waits_on_both_classifications(
    ci_workflow: dict[str, Any], ci_workflow_path: Path
) -> None:
    """The composition E2-12 settles: inert **and** ai_surface, plus the manual escape.

    Three clauses on every step of the eval job that costs anything — and "costs
    anything" includes `actions/setup-python` and the locked install, not only the
    runner. A condition on the runner alone leaves a Python setup and a dependency
    install on every pull request in the repository, which is a quarter of what
    E0-38 measured and removed.

      - `needs.changed.outputs.inert` — E0-38's documentation-only short-circuit,
        which two committed modules require this gate to keep. It is not replaced.
      - `needs.changed.outputs.ai_surface` — E2-12's new clause. §9.3's gate is
        "prompt or model changes", and this is that question asked of the diff.
      - `github.event_name == 'workflow_dispatch'` — the manual run, which must
        fire the steps whatever the diff says, since a dispatch has no meaningful
        diff at all.

    **The job has to declare `changed` in `needs` first, and that half is worth
    nothing without it.** GitHub's `needs` context holds only declared needs, so a
    reference to an undeclared job is the empty string; `'' != 'true'` is true,
    the guard is dead, and the step runs on everything with nothing going red.

    **The mutation this kills:** replace the inert clause with the ai_surface one
    rather than composing them, which is the shape a "the guard is now about AI
    paths" edit produces and which two other modules would then be asserting about
    a clause that is gone. **The near miss that must stay green:** any grouping or
    spelling of the three clauses, since this reads which references appear rather
    than how they are arranged — except for the one ordering rule the test below
    states and gives its reason for.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)
    name, job = evals_job(jobs, ci_workflow_path)

    assert CHANGED_JOB in needs_of(job), (
        f"the `{name}` job does not declare `{CHANGED_JOB}` in `needs`, so every "
        f"`{INERT_REFERENCE}` and `{AI_SURFACE_REFERENCE}` in it evaluates to the empty "
        "string. `'' != 'true'` is true, so a guard written that way is dead and its step "
        "runs on everything, with nothing red anywhere."
    )

    working = [
        (label_of(step, index), step)
        for index, step in enumerate(steps_of(job))
        if does_real_work(step)
    ]
    assert working, (
        f"the `{name}` job has no step that costs anything, so there is nothing here to "
        "guard. A job of notices is the tolerance this ticket removes."
    )

    missing: list[str] = []
    for label, step in working:
        condition = conditions_of(step)
        absent = [
            clause
            for clause in (INERT_REFERENCE, AI_SURFACE_REFERENCE, WORKFLOW_DISPATCH)
            if clause not in condition
        ]
        if absent:
            missing.append(
                f"  {label}\n    condition: {condition or '(none)'}\n    missing: {absent}"
            )

    assert not missing, "\n".join(
        [
            f"these steps of the `{name}` job do not consult all three clauses:",
            *missing,
            "",
            "E2-12 settles the composition: the live steps run when the diff is not inert "
            "AND (it touches the AI surface OR the run was dispatched by hand). The inert "
            "clause is kept rather than replaced, because "
            "`test_the_detect_probes_see_the_files_their_jobs_run.py` requires every "
            "expensive gate to mention it and "
            "`test_a_documentation_only_diff_does_not_run_the_expensive_gates.py` reads its "
            "operator. Those two modules are not this ticket's to edit.",
        ]
    )


def test_the_inert_clause_comes_first_in_every_eval_step_condition(
    ci_workflow: dict[str, Any], ci_workflow_path: Path
) -> None:
    """An ordering rule, and it exists to keep a committed test from going red for nothing.

    `test_a_documentation_only_diff_does_not_run_the_expensive_gates.py` reads the
    sense of each expensive gate's guard by walking the condition and taking the
    **first** comparison of a `needs.changed.outputs.*` reference against the
    literal `'true'`. That reader was added after E0-38's third review pass flipped
    one character on the `test` job and the whole unit suite stayed green, and on
    this job the same character turns off SPEC §9.3's threat and self-harm recall
    floor on every code pull request.

    It was written when `inert` was the only classification the `changed` job
    published. A condition that leads with `ai_surface == 'true'` gives that reader
    an `==`, it concludes "this step runs only when the diff is inert", and it
    fails — on a guard that is correct, in a module E2-12 may not touch. Leading
    with `inert != 'true'` costs nothing and keeps the reader right.

    So this is a real constraint with a real reason rather than a style
    preference, and it is stated here so that the red it prevents is not
    diagnosed as a defect in the other module.

    **The mutation this kills:** write the condition as
    `needs.changed.outputs.ai_surface == 'true' && needs.changed.outputs.inert != 'true'`,
    which is the same boolean and reds a committed guard. **The near miss that
    must stay green:** any arrangement whose first classification comparison is
    the inert one.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)
    name, job = evals_job(jobs, ci_workflow_path)

    wrong: list[str] = []
    for index, step in enumerate(steps_of(job)):
        condition = conditions_of(step)
        comparisons = [
            match
            for match in COMPARISON.finditer(condition)
            if match.group("reference").startswith(f"needs.{CHANGED_JOB}.outputs.")
            and match.group("literal") == "true"
        ]
        if len(comparisons) < 2:
            continue
        if comparisons[0].group("reference") != INERT_REFERENCE:
            wrong.append(
                f"  {label_of(step, index)}\n"
                f"    condition: {condition}\n"
                f"    first classification compared: {comparisons[0].group('reference')}"
            )

    assert not wrong, "\n".join(
        [
            f"these steps of the `{name}` job do not lead with the inert clause:",
            *wrong,
            "",
            "`test_a_documentation_only_diff_does_not_run_the_expensive_gates.py` reads the "
            "sense of a guard from the first `needs.changed.outputs.*` comparison against "
            "'true'. Leading with `ai_surface == 'true'` hands it an `==`, it reports this "
            "gate as running only on documentation, and a committed module goes red over a "
            "condition that is in fact correct.",
            "",
            "The boolean is identical either way. Put the inert clause first.",
        ]
    )


def test_the_eval_runner_is_asked_to_enforce_the_floors(
    ci_workflow: dict[str, Any], ci_workflow_path: Path
) -> None:
    """The documented invocation, in the workflow: `--enforce-floors`.

    E2-12's first acceptance criterion names the command, and the runner is built
    so that dropping the flag changes nothing — enforcement does not ride on it,
    for reasons its own module docstring gives. This asserts the workflow still
    carries it, because the two together are what makes the CI log and the local
    command the same thing: an operator reading the step sees the invocation they
    can reproduce, rather than a shorter one that behaves differently by luck.

    **The mutation this kills:** invoke the runner bare and rely on the default,
    which works today and stops working the moment somebody decides the flag
    should mean something.
    """
    jobs = jobs_of(ci_workflow, ci_workflow_path)
    name, job = evals_job(jobs, ci_workflow_path)

    invocations = [
        line
        for step in steps_of(job)
        for line in command_lines(str(step.get("run") or ""))
        if EVAL_RUNNER.search(line)
    ]
    assert invocations, (
        f"the `{name}` job was found by the runner command and then no command line in it "
        "matched — which means `command_lines` dropped the step that matched, and this "
        "assertion would have passed over a job that never runs the runner at all."
    )
    without = [line for line in invocations if ENFORCE_FLOORS not in line]
    assert not without, (
        f"these invocations do not pass `{ENFORCE_FLOORS}`: {without}. E2-12's first "
        "acceptance criterion names the command as "
        f"`python -m tests.evals.runner {ENFORCE_FLOORS}`, and the CI step is what makes "
        "that the command an operator can reproduce."
    )


def test_the_tolerant_notice_no_longer_stands_in_for_the_eval_gate(
    ci_workflow: dict[str, Any], ci_workflow_path: Path
) -> None:
    """ADR 0002's last tolerance, removed by the ticket that lands the code it waited for.

    The notice in the `evals` job says the first eval set and its floors "are E2's,
    and this job stays tolerant until then". E2-12 is that work, so the sentence
    becomes false in the same change that makes it false — `docs/MISTAKES.md`
    entry 1, a record going on asserting something the change had made untrue —
    and ADR 0002 makes removing a tolerance an acceptance criterion of the ticket
    that lands the code rather than a tidy-up for later.

    It matters beyond bookkeeping. A tolerant job *looks like a passing job* in the
    checks interface unless somebody reads the log, which ADR 0002 calls "the real
    cost of the decision". Leaving the notice behind leaves a route by which this
    job can report success over an eval run that did not happen.

    **The searches are run against the text as it stands before they are trusted
    against the file** (`docs/MISTAKES.md` entry 3, whose third incident was a
    pattern that matched nothing and passed against the exact text it existed to
    catch). The sample is copied whole out of the workflow, the line it begins on
    included.

    **The mutation this kills:** land the eval set and leave the tolerance where
    it is, which is what ADR 0002's second consequence says happens — "if a ticket
    lands its code and forgets its flag, CI stays green and quieter than it should
    be". **The near miss that must stay green:** a notice that explains a *skipped*
    run — "this diff does not touch the AI surface" — which is not a tolerance and
    is worth keeping.
    """
    blind = [
        phrase.pattern
        for phrase in TOLERANCE_PHRASES
        if not phrase.search(TOLERANT_NOTICE_AS_IT_STANDS)
    ]
    assert not blind, (
        f"these patterns do not match the tolerance as it stands today: {blind}. The sample "
        "is copied whole out of `.github/workflows/ci.yml`, so a pattern that misses it has "
        "gone blind and the assertion below would report a removed tolerance over a "
        "workflow that still carries one."
    )

    jobs = jobs_of(ci_workflow, ci_workflow_path)
    name, job = evals_job(jobs, ci_workflow_path)

    surviving: list[str] = []
    for index, step in enumerate(steps_of(job)):
        script = str(step.get("run") or "")
        matched = [phrase.pattern for phrase in TOLERANCE_PHRASES if phrase.search(script)]
        if matched:
            surviving.append(f"  {label_of(step, index)} — matched {matched}")

    assert not surviving, "\n".join(
        [
            f"the `{name}` job still carries its tolerance notice:",
            *surviving,
            "",
            "ADR 0002: 'Removing a tolerance is an acceptance criterion of the ticket that "
            "lands the corresponding code.' E2-12 lands the eval set and the floors, so the "
            "sentence saying they are still to come is false in this very change.",
            "",
            "A tolerant job looks like a passing job in the checks interface unless someone "
            "reads the log, which is the cost ADR 0002 accepted and this ticket stops "
            "paying.",
        ]
    )
