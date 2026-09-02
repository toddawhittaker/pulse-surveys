"""The eval runner CI calls: `python -m tests.evals.runner --enforce-floors` — E2-12.

SPEC §9.3's gate, made executable. It walks `tests/evals/registry.py`, grades each
task that has both a set and a floor, and compares what it measured against what
was declared.

**Every way out of here that is not a graded comparison raises `EvalRefusalError`, and
a refusal exits non-zero.** That is the whole design, and it is aimed at one
failure: a run that reports success over work it did not do. The routes are

  - a floor declared with no set to measure it over;
  - the placeholder floor nobody has filled in yet;
  - a deferred slot that has acquired a set or a number;
  - a set with no case of the positive class, so recall cannot be computed;
  - a missing or blank `AI_PROVIDER_API_KEY`;
  - an answer produced under a prompt version the set is not pinned to;
  - a task with a floor and a set and nothing that can run it.

`docs/MISTAKES.md` entry 34's cousin, and E2-12's scope says it in one sentence:
"an AI-touching PR without the secret is a red gate naming what is missing, not a
quiet pass".

**`--enforce-floors` is accepted and enforcement does not depend on it.** The flag
is in the documented invocation and in `.github/workflows/ci.yml`, so it is
accepted rather than rejected; what it must not be is the switch that turns the
gate on. A gate whose enforcement rides on a flag is a gate that a copied command
line, a shortened Makefile recipe or a tired edit can disable while still looking
like it ran — and this one carries SPEC §9.3's floors. So the runner enforces
whether or not it is passed, and losing the flag from CI costs nothing.

**The credential.** `.env.example` documents a blank `AI_PROVIDER_API_KEY` as
legitimate, because the mock and a local model server authenticate nobody. That
is true of the application and false of this runner: it always builds a live
gateway, and a live gateway with no credential is a run against a provider that
will refuse it. So blank is refused here and the refusal names the variable.

**The report says what the run cost.** Each answered case comes back with the
gateway's `TaskUsage` beside the verdict, and the totals are printed with the
cache read shown as a share of the input rather than added to it — it is a part of
`input_tokens`, not something extra. The line also says plainly that a retried
call contributes only the request that answered, so the figures are a floor on
what the run cost rather than a complete account of it. `tests/evals/README.md`'s
cost expectations are measured from this rather than estimated.

**`--demonstrate-breach` runs the planted breach and never exits 0.**
`docs/MISTAKES.md` entry 9 is why it exists: a floor that has only ever been seen
passing is a comment, so E2-12 asks for the flip to be proven by breaking as well
as by clearing. The set it runs is `tests/evals/validity/breach.py`, whose every
expected verdict is deliberately wrong; it is not in the registry, so an ordinary
run cannot reach it, and it is imported only inside that branch. A breach exits 1
because a breached floor is a failed run — and so does a breach that failed to
breach, with a louder message, because a demonstration that proved nothing is
worse than none.

**No `print`.** `T20` is on for `tests/**` in `pyproject.toml` and this module is
a program rather than an application, so it writes to `sys.stdout` directly.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.ai.contracts import CommentValidityOutput
from tests.evals.declarations import (
    EvalRefusalError,
    EvalTask,
    FloorStatus,
    TaskFloors,
    TaskUsageLike,
    UsageTotals,
)
from tests.evals.measure import Measurement, holds_a_positive_case, measure
from tests.evals.registry import TASKS

# What a classifier answers: the validated output, and what the call cost.
#
# The pair rather than the output alone, because a run that cannot say what it
# spent leaves the README's cost expectations an estimate — and because the two
# come back from one gateway call, so carrying them separately would mean either a
# second call or a hidden accumulator.
Classifier = Callable[[str], tuple[CommentValidityOutput, TaskUsageLike]]

# The variable the live gateway's credential arrives in (`.env.example`,
# `AI_PROVIDER_*` triple). Named here rather than read through `Settings` so that
# the refusal below happens before anything builds a gateway, and so that the
# message can name the variable an operator actually has to set.
PROVIDER_KEY_VARIABLE = "AI_PROVIDER_API_KEY"


@dataclass(frozen=True)
class TaskReport:
    """What one task came to on this run."""

    task: str
    floors: TaskFloors
    measurement: Measurement | None
    breaches: tuple[str, ...]
    usage: UsageTotals = field(default_factory=UsageTotals)

    @property
    def graded(self) -> bool:
        """Whether this run actually measured anything for this task."""
        return self.measurement is not None


@dataclass(frozen=True)
class Report:
    """Every task's outcome, and whether the run as a whole may report success."""

    tasks: tuple[TaskReport, ...]

    @property
    def passed(self) -> bool:
        """True only when no floor was breached. A deferred slot is not a breach."""
        return not any(task.breaches for task in self.tasks)

    def text(self) -> str:
        """The run, as lines an operator reads in a CI log."""
        lines = ["SPEC §9.3 eval floors"]
        for task in self.tasks:
            lines.append(f"  {task.task}: {task.floors.status.value}")
            if task.measurement is not None:
                measurement = task.measurement
                lines.append(
                    f"    {measurement.cases} cases — "
                    f"precision {measurement.precision:.4f} "
                    f"(floor {task.floors.precision}), "
                    f"recall {measurement.recall:.4f} "
                    f"(floor {task.floors.recall})"
                )
                lines.append(
                    f"    tp {measurement.true_positives} "
                    f"fp {measurement.false_positives} "
                    f"fn {measurement.false_negatives} "
                    f"tn {measurement.true_negatives}"
                )
                lines.extend(usage_lines(task.usage))
                for case_id, expected, answered in measurement.disagreements:
                    lines.append(f"    disagreed on {case_id}: expected {expected}, got {answered}")
            else:
                lines.append(f"    ungraded — {task.floors.note}")
            for breach in task.breaches:
                lines.append(f"    BREACH: {breach}")
        lines.append("VERDICT: pass" if self.passed else "VERDICT: fail")
        return "\n".join(lines)


def usage_lines(usage: UsageTotals) -> list[str]:
    """What one task's run cost, as lines an operator reads beside the rates.

    **The cache read is reported as a share of the input rather than beside it**,
    because that is what it is: `cache_read_tokens` counts tokens that are part of
    `input_tokens` and were served from the provider's cache. Adding the two would
    overstate a run by the cheapest thing in it, and nobody could reconcile the
    figure with an invoice.

    **And the caveat is printed rather than left to be discovered.** A call the
    gateway retried reports the usage of the request that answered, so `requests`
    can be lower than the number of attempts the provider actually billed. That
    makes these figures a floor on what the run cost. Saying so costs one line;
    implying completeness costs the first person who compares this against a bill.
    """
    if usage.calls == 0:
        return []
    cached = (
        f", {usage.cache_read_tokens} of them served from cache" if usage.cache_read_tokens else ""
    )
    written = f", {usage.cache_write_tokens} written to cache" if usage.cache_write_tokens else ""
    return [
        f"    cost: {usage.input_tokens} input tokens{cached}{written}, "
        f"{usage.output_tokens} output, {usage.total_tokens} total",
        f"    over {usage.requests} provider request(s) for {usage.calls} case(s) — a "
        "retried call contributes only the request that answered, so this is a floor on "
        "what the run cost rather than a complete account of it",
    ]


def declaration_problems(task: EvalTask) -> list[str]:
    """Everything wrong with one task's declaration, before anything is run.

    Structural rather than measured: none of these needs a provider, a credential
    or a model, so all of them are found on a machine with no network at all.
    """
    floors = task.floors
    problems: list[str] = []

    if floors.status is FloorStatus.DEFERRED:
        if task.cases:
            problems.append(
                f"`{task.name}` holds {len(task.cases)} cases and a deferred floor. The set "
                "arrived and the number did not, so this task would be reported and never "
                "graded — set the floor, or take the set out until there is one."
            )
        if floors.carries_numbers:
            problems.append(
                f"`{task.name}` has a deferred floor carrying numbers "
                f"(precision {floors.precision}, recall {floors.recall}). A slot held open "
                "for another epic states no floor; a number here is a floor nobody measured."
            )
        return problems

    if not task.cases:
        problems.append(
            f"`{task.name}` declares a floor and has no eval set, so there is nothing to "
            "measure it over. E2-12: the runner refuses to report a task with a floor and "
            "no set rather than passing it silently."
        )

    if floors.status is FloorStatus.AWAITING_MEASUREMENT:
        problems.append(
            f"`{task.name}`'s floor is the placeholder and has never been filled in. "
            f"{floors.note}"
        )
        return problems

    if floors.precision is None or floors.recall is None:
        problems.append(
            f"`{task.name}` is declared enforced and states "
            f"precision {floors.precision}, recall {floors.recall}. SPEC §9.3's gate is "
            "both numbers; half a floor is not one."
        )

    if task.cases and not holds_a_positive_case(task.cases, task.positive):
        problems.append(
            f"`{task.name}`'s set holds no case whose expected verdict is "
            f"{task.positive!r}, so recall cannot be measured over it and any figure "
            "reported would be about nothing."
        )

    if task.cases and task.prompt_version is None:
        problems.append(
            f"`{task.name}` has a set and no prompt version. ADR 0031 makes the recorded "
            "version the prompt file's stem and ADR 0032 makes that file immutable, so a "
            "set that does not say which prompt it was written against cannot be compared "
            "against a later run."
        )

    drifted = sorted(
        {case.prompt_version for case in task.cases if case.prompt_version != task.prompt_version}
    )
    if drifted:
        problems.append(
            f"`{task.name}` is pinned to {task.prompt_version!r} and holds cases pinned to "
            f"{drifted}. A set spanning two prompt versions produces one number about two "
            "measurements."
        )

    return problems


def _classifier_for(task: EvalTask, overrides: Mapping[str, Classifier] | None) -> Classifier:
    """The callable that answers one comment for this task."""
    if overrides is not None and task.name in overrides:
        return overrides[task.name]
    if task.classifier is None:
        raise EvalRefusalError(
            f"`{task.name}` declares a floor and a set and nothing that can run it. A task "
            "the runner cannot execute is a floor that can never be measured, which is a "
            "gate in name only."
        )
    return task.classifier()


def _answer(
    task: EvalTask, comment: str, case_id: str, pinned: str | None, classify: Any
) -> tuple[Any, TaskUsageLike]:
    """One answer and what it cost, with its prompt version checked against the case's pin.

    **The pin is the reason two full runs were voided rather than reported**
    (dispute E2-12-06), and it is unchanged by that repair. It caught an eval path
    that reached the model through §3.3's submit path, where a slow answer is
    replaced by a character count carrying `character-floor` as its version — a
    substitution that produces plausible numbers and biases them toward the two
    families this set exists to measure. `tests/evals/live.py` now calls the
    gateway directly, and this stays exactly as it was: it is the thing that would
    catch the next such substitution, whatever route it arrived by.
    """
    output, usage = classify(comment)
    try:
        answered_under = output.prompt_version
    except AttributeError as failure:
        raise EvalRefusalError(
            f"`{task.name}` case {case_id}: the object the task returned carries no "
            f"`prompt_version` ({output!r}). ADR 0031 makes it a required field on every "
            "contract, and without it a measurement cannot say which prompt produced it."
        ) from failure

    if pinned is not None and answered_under != pinned:
        raise EvalRefusalError(
            f"`{task.name}` case {case_id} is pinned to prompt {pinned!r} and the gateway "
            f"answered under {answered_under!r}. ADR 0032 makes a committed prompt file "
            "immutable, so this is a run against a different prompt rather than a rerun of "
            "the same one: regrow the set against the new version and measure a new floor, "
            "rather than reading this number as comparable."
        )
    return output.verdict, usage


def evaluate(
    tasks: Sequence[EvalTask] = TASKS,
    *,
    classifiers: Mapping[str, Classifier] | None = None,
    environ: Mapping[str, str] | None = None,
) -> Report:
    """Grade every gradable task and compare each against its floor.

    Raises `EvalRefusalError` rather than returning a report whenever something makes
    the run unmeasurable. `classifiers` substitutes a task's live classifier,
    which is how the unit tests reach the enforcement logic without a provider;
    nothing in CI passes it.
    """
    values = os.environ if environ is None else environ

    problems = [problem for task in tasks for problem in declaration_problems(task)]
    if problems:
        raise EvalRefusalError("\n".join(["the eval declarations are not runnable:", *problems]))

    anything_to_grade = any(task.floors.status is FloorStatus.ENFORCED for task in tasks)

    if anything_to_grade and not values.get(PROVIDER_KEY_VARIABLE, "").strip():
        raise EvalRefusalError(
            f"{PROVIDER_KEY_VARIABLE} is missing or blank, so no eval floor was measured. "
            f"The eval runner always builds a live gateway, and {PROVIDER_KEY_VARIABLE} is "
            "the credential it sends. Set it in `.env` for a local run, or supply the "
            "repository secret for a CI run. This is a refusal rather than a skip: a pull "
            "request that touches the AI surface and cannot reach a provider has not met "
            "SPEC §9.3's gate, and reporting it green would say that it had."
        )

    reports: list[TaskReport] = []
    for task in tasks:
        if task.floors.status is not FloorStatus.ENFORCED:
            reports.append(
                TaskReport(task=task.name, floors=task.floors, measurement=None, breaches=())
            )
            continue

        classify = _classifier_for(task, classifiers)
        answers: list[Any] = []
        usage = UsageTotals()
        for case in task.cases:
            verdict, spent = _answer(
                task, case.comment, case.case_id, case.prompt_version, classify
            )
            answers.append(verdict)
            usage = usage.plus(spent)
        measurement = measure(task.cases, answers, task.positive)

        breaches: list[str] = []
        if task.floors.precision is not None and measurement.precision < task.floors.precision:
            breaches.append(
                f"precision {measurement.precision:.4f} is below the floor "
                f"{task.floors.precision}"
            )
        if task.floors.recall is not None and measurement.recall < task.floors.recall:
            breaches.append(
                f"recall {measurement.recall:.4f} is below the floor {task.floors.recall}"
            )

        reports.append(
            TaskReport(
                task=task.name,
                floors=task.floors,
                measurement=measurement,
                breaches=tuple(breaches),
                usage=usage,
            )
        )

    return Report(tasks=tuple(reports))


def build_parser() -> argparse.ArgumentParser:
    """The command line. Two flags, and neither can turn the gate off."""
    parser = argparse.ArgumentParser(
        prog="python -m tests.evals.runner",
        description=(
            "Run SPEC §9.3's eval sets against the live provider and compare each task "
            "against its declared precision and recall floors."
        ),
    )
    parser.add_argument(
        "--enforce-floors",
        action="store_true",
        help=(
            "Accepted for the documented invocation. Floors are enforced whether or not "
            "this is passed: a gate whose enforcement rides on a flag can be switched off "
            "by an edit to a command line, and this one carries SPEC §9.3's floors."
        ),
    )
    parser.add_argument(
        "--demonstrate-breach",
        action="store_true",
        help=(
            "Run the planted breach set instead of the registry, through the real "
            "provider, to watch these floors refuse a run. Never exits 0: a breach is a "
            "failure, and a breach that did not breach is a failure too."
        ),
    )
    return parser


def demonstrate_breach() -> int:
    """Run the planted breach through the real path and answer non-zero either way.

    `docs/MISTAKES.md` entry 9: a guard that has never been executed against the
    case it claims to stop is a comment. This is that execution, and E2-12's scope
    asks for it — the flip is "proven by breaking, both ways", the real set green
    and a planted breach red, through the same runner and the same provider.

    **It cannot exit 0, and the two ways of failing say different things.** A
    breach is the demonstration succeeding, and it exits 1 because a breached floor
    is a failed run and this mode must not be a way to make one look like a pass. A
    breach that did *not* breach exits 1 with a louder message: the floors let
    twenty deliberately mislabelled cases through, so either the run never reached
    the model or the floors are not gating anything, and both are worse findings
    than the demonstration was after.

    The breach set is imported here rather than at module scope so that an ordinary
    run never loads it. It is out of `registry.TASKS` as well, which is the
    inertness that matters — this import is the belt to that brace.
    """
    from tests.evals.validity.breach import BREACH_TASK

    try:
        report = evaluate([BREACH_TASK])
    except EvalRefusalError as refusal:
        sys.stdout.write(f"the breach demonstration was refused before it could run\n{refusal}\n")
        return 1

    sys.stdout.write(f"{report.text()}\n")
    if report.passed:
        sys.stdout.write(
            "DEMONSTRATION FAILED: the planted breach did not breach.\n"
            "Every expected verdict in tests/evals/validity/breach.py is deliberately "
            "wrong — ten plainly substantive comments labelled insufficient and ten "
            "contentless ones labelled substantive — so a run that clears the floors "
            "means either that nothing reached the model or that the floors are not "
            "gating what they claim to. Both are larger findings than this mode was "
            "looking for.\n"
        )
        return 1

    sys.stdout.write(
        "DEMONSTRATION SUCCEEDED: the floors refused a run, through the real provider "
        "and the real prompt. This exits non-zero because a breached floor is a failed "
        "run; that is what was being shown.\n"
    )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the evals and answer 0 for a pass, 1 for a breach or a refusal."""
    arguments = build_parser().parse_args(argv)

    if arguments.demonstrate_breach:
        return demonstrate_breach()

    try:
        report = evaluate()
    except EvalRefusalError as refusal:
        sys.stdout.write(f"eval run refused\n{refusal}\n")
        return 1

    sys.stdout.write(f"{report.text()}\n")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
