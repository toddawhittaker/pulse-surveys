"""The planted floor breach is inert, separate, and certain to breach — ticket E2-12.

`docs/MISTAKES.md` entry 9: **before citing a guard, execute it against the case
you claim it stops.** An eval floor is the purest form of that failure, because it
produces a green line on every run that clears it and nothing about that line says
whether a run could fail at all. E2-12's scope asks for the flip to be "proven by
breaking, both ways" — the real set green, and a planted breach red, through the
same runner and the same provider.

`tests/evals/validity/breach.py` is that plant, and it is a set the current prompt
fails by construction: ten plainly substantive comments labelled `insufficient`
and ten contentless ones labelled `substantive`. The model answers each correctly,
the labels say otherwise, and both floors collapse.

**This module is what makes the demonstration predictable rather than hopeful.**
The live run is the orchestrator's and costs twenty provider calls; what is
asserted here needs none, and it is the three things that would make that run
worthless:

- the breach is out of the registry an ordinary run walks, so it can never be
  measured by accident;
- no comment is in both the breach set and the real one, so neither can be
  labelled two ways;
- the breach really does breach *these* floors when the model answers correctly,
  which is checked with a stub rather than hoped for.

The third is the one worth the module. Without it, a demonstration that came back
red would be evidence of something — a refusal, a missing key, a provider
outage — and nobody could say which, and a demonstration that came back green
would be read as a floor that does not gate rather than as a breach set that had
stopped being one.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The mode's contract: it never exits 0. A breach is a failed run, and a breach
# that did not breach is a worse finding than the one being looked for.
DEMONSTRATE_BREACH = "--demonstrate-breach"


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """The eval modules are imported, and importing them reaches `app.ai.*`.

    `docs/MISTAKES.md` entry 40. Nothing here reads the environment, but a module
    that builds anything out of `Settings` at import time would build it out of
    whatever the developer's shell happened to hold.
    """


def eval_module(name: str) -> ModuleType:
    """Import one of `tests/evals/`'s modules, or fail naming the deliverable.

    The repository root goes on `sys.path` first: pytest puts `tests/` there and
    not the root, while `python -m tests.evals.runner` needs only the root.
    """
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as failure:
        if failure.name is not None and (
            name == failure.name or name.startswith(f"{failure.name}.")
        ):
            pytest.fail(
                f"There is no `{name}` module. E2-12's scope asks for the flip to be proven "
                "by breaking as well as by clearing, and the planted breach lives under "
                "`tests/evals/validity/`."
            )
        raise


def test_the_breach_task_is_not_in_the_registry_an_ordinary_run_walks() -> None:
    """The inertness that matters, and it is structural rather than a flag.

    `evaluate()` walks `registry.TASKS` and nothing else, so a breach task outside
    that tuple cannot be reached by `python -m tests.evals.runner
    --enforce-floors` however it is invoked. A flag guarding a registered breach
    would be one edit — or one copied command line — away from grading twenty
    deliberately mislabelled cases as SPEC §9.3's floor and reporting the result.

    **The mutation this kills:** register the breach beside the real task "so it
    is easy to find", which makes every ordinary run measure it and fail forever;
    or, having noticed that, keep it registered and skip it on a flag, which puts
    the whole arrangement one boolean from the same place.

    **The near miss that must stay green:** the breach task existing at all, being
    importable, and being reachable through `--demonstrate-breach` — none of which
    this refuses.
    """
    registry = eval_module("tests.evals.registry")
    breach = eval_module("tests.evals.validity.breach")

    registered = [task.name for task in registry.TASKS]
    assert breach.BREACH_TASK.name not in registered, (
        f"the planted breach `{breach.BREACH_TASK.name}` is in `registry.TASKS` "
        f"({registered}), so every ordinary eval run grades twenty cases whose expected "
        "verdicts are deliberately wrong. It is meant to be reachable only through "
        f"`{DEMONSTRATE_BREACH}`."
    )
    assert not any(task.cases is breach.BREACH_CASES for task in registry.TASKS), (
        "a registered task carries the breach set as its own cases. The task name being "
        "absent is not enough if the set arrived under another one."
    )


def test_no_comment_is_in_both_the_breach_set_and_the_real_one() -> None:
    """A comment labelled two ways is a floor measured against a wrong answer.

    The breach set inverts its labels on purpose, so a comment that appeared in
    both would carry the true verdict in one file and the false one in the other.
    The real set is what the floors were measured on; a stray breach comment inside
    it moves those figures in the direction nobody re-checks, and the run stays
    green because the number still looks plausible.

    **The mutation this kills:** growing the breach set by copying rows out of
    `cases.py` and editing only the labels — the natural way to write it, and the
    one that quietly poisons the measured set. **The near miss that must stay
    green:** two comments that are merely similar, since this compares the strings
    a run actually sends.
    """
    cases = eval_module("tests.evals.validity.cases")
    breach = eval_module("tests.evals.validity.breach")

    real = {case.comment for case in cases.CASES}
    planted = {case.comment for case in breach.BREACH_CASES}
    shared = sorted(real & planted)

    assert not shared, (
        f"these comments are in both the measured set and the planted breach: {shared}.\n"
        "\n"
        "The breach labels every case wrongly on purpose, so a shared comment is labelled "
        "one way in `cases.py` and the other way in `breach.py`. Whichever run met it "
        "would be scoring the model against the other file's answer."
    )


def test_every_breach_case_is_labelled_against_what_the_prompt_will_say() -> None:
    """The set's own shape: inverted labels, in both directions, pinned to the real prompt.

    Both directions are needed and neither alone is the demonstration. Cases
    labelled `insufficient` that the model calls `substantive` are false positives
    and take precision down; cases labelled `substantive` that it calls anything
    else are false negatives and take recall down. A breach in one direction would
    prove one floor gates and say nothing about the other, and this ticket's floors
    are two numbers with two different arguments behind them.

    The pin is asserted because the runner refuses a set whose cases name a prompt
    the task does not — so a breach pinned to something else would be refused
    rather than measured, and the demonstration would show the pin working instead
    of the floors.

    **The mutation this kills:** a breach set labelled correctly, which passes and
    demonstrates nothing; or one that only inverts the substantive half.
    """
    cases = eval_module("tests.evals.validity.cases")
    breach = eval_module("tests.evals.validity.breach")

    assert breach.BREACH_CASES, "the planted breach holds no cases"

    positives = [c for c in breach.BREACH_CASES if c.expected == cases.POSITIVE_VERDICT]
    negatives = [c for c in breach.BREACH_CASES if c.expected != cases.POSITIVE_VERDICT]
    assert positives and negatives, (
        f"the breach set holds {len(positives)} case(s) of the positive class and "
        f"{len(negatives)} outside it. Both are needed: one direction breaches precision "
        "and the other breaches recall, and a set with only one proves only one floor "
        "gates anything."
    )

    drifted = sorted(
        {c.prompt_version for c in breach.BREACH_CASES if c.prompt_version != cases.PROMPT_VERSION}
    )
    assert not drifted, (
        f"the breach set is pinned to {drifted} and the real set to "
        f"{cases.PROMPT_VERSION!r}. The runner refuses a set whose cases name a prompt the "
        "task does not, so this would demonstrate the pin rather than the floors."
    )


def test_the_planted_breach_fails_both_floors_when_the_model_answers_correctly() -> None:
    """The control that makes the live demonstration mean something.

    A classifier that answers every breach case the way `validity.v1` will — the
    plainly substantive comments `substantive`, the contentless ones
    `insufficient` — is run over the planted set against **the floors the real set
    is graded by**, and both must breach. No provider is reached: the point is to
    know what the live run will show before spending twenty calls on it.

    Without this, a red demonstration is evidence of *something* — a refusal, an
    absent key, an outage — and nobody could say which; and a green one would be
    read as a floor that does not gate rather than as a breach set that had
    stopped being one.

    **The floors are the shipped ones, not a stricter pair.** A demonstration
    against numbers invented to be easy to fail shows a floor nobody enforces
    (`docs/MISTAKES.md` entry 19). `breach.py` imports them rather than restating
    them, and this reads them from the same place.

    **The mutation this kills:** relabelling the breach set correctly, or pointing
    it at floors of its own. **The near miss that must stay green:** the shipped
    floors moving in a deliberate pull request — this asserts that the planted set
    breaches whatever they are, not that they are any particular pair.
    """
    breach = eval_module("tests.evals.validity.breach")
    cases = eval_module("tests.evals.validity.cases")
    runner = eval_module("tests.evals.runner")
    contracts = eval_module("app.ai.contracts")

    substantive, insufficient = cases.SUBSTANTIVE, cases.INSUFFICIENT

    def as_the_prompt_would(comment: str) -> tuple[Any, Any]:
        """What a correct classifier answers, and a usage the runner can add up.

        The inversion is what makes this simple: a breach case labelled
        `insufficient` holds a substantive comment, and one labelled `substantive`
        holds a contentless one — so the right answer is always the opposite of the
        label. Deriving it that way rather than listing it keeps this control from
        being a second copy of the set.
        """
        expected = next(c.expected for c in breach.BREACH_CASES if c.comment == comment)
        answer = substantive if expected == insufficient else insufficient
        output = contracts.CommentValidityOutput(
            verdict=answer,
            prompt_version=cases.PROMPT_VERSION,
            model_id="e2-12-breach-control",
        )
        return output, _NoUsage()

    report = runner.evaluate(
        [breach.BREACH_TASK],
        classifiers={breach.BREACH_TASK.name: as_the_prompt_would},
        environ={"AI_PROVIDER_API_KEY": "e2-12-unit-test-placeholder-not-a-credential"},
    )

    assert not report.passed, (
        "a correct classifier cleared the floors over a set whose every label is wrong:\n"
        f"{report.text()}\n"
        "\n"
        "The live demonstration would come back green and prove the opposite of what it "
        "is for."
    )

    breaches = report.tasks[0].breaches
    assert any("precision" in breach_text for breach_text in breaches), (
        f"the run failed and no breach was about precision: {breaches}. The ten cases "
        "labelled `insufficient` hold plainly substantive comments, so a correct "
        "classifier produces ten false positives and no true positives at all."
    )
    assert any("recall" in breach_text for breach_text in breaches), (
        f"the run failed and no breach was about recall: {breaches}. The ten cases "
        "labelled `substantive` hold contentless comments, so a correct classifier finds "
        "none of the positives the set claims to hold."
    )


class _NoUsage:
    """A `TaskUsage` reporting nothing, for a control that reaches no provider.

    The runner sums usage across a run, so it needs the fields; a stub that reached
    no provider genuinely spent nothing, and reporting zero is the honest value
    here rather than a placeholder.
    """

    input_tokens = 0
    output_tokens = 0
    cache_read_tokens = 0
    cache_write_tokens = 0
    total_tokens = 0
    requests = 0
    details: ClassVar[dict[str, int]] = {}


def test_the_breach_mode_is_reachable_from_the_command_line() -> None:
    """The mode exists and is spelled the way the demonstration will be invoked.

    A planted breach nothing can run is a file, not a demonstration. This asserts
    only that the parser takes the flag — what the mode then does is the live run's
    to show, and it is the orchestrator's to perform once.

    **The mutation this kills:** shipping `breach.py` with no way to reach it,
    which leaves E2-12's proof-by-breaking clause satisfied by a docstring.
    """
    runner = eval_module("tests.evals.runner")
    arguments = runner.build_parser().parse_args([DEMONSTRATE_BREACH])

    assert getattr(arguments, "demonstrate_breach", False), (
        f"`{DEMONSTRATE_BREACH}` parses to nothing the runner acts on, so the planted "
        "breach cannot be run."
    )
