"""The draft and draft-check eval sets can fail, are typed, and are pinned — E7-04 done-when 8.

> Each task has typed cases for the behaviours above, and ships no floor.

`tests/evals/response_draft/` and `tests/evals/draft_check/` hold the cases and the
graders. This module is the proof that a grader means something, run offline:
every case's faithful answer passes it, and every planted breach fails it
(`docs/MISTAKES.md` entry 3's rule applied to an eval, as
`tests/unit/test_the_summary_eval_cases_can_go_red.py` applies it to the summary).
Without the breaches, a grader that passed everything would look identical to one
that works.

**What is deliberately not asserted.** Whether a real model writes good drafts or
good checks is a distribution, and SPEC §9.3 answers it with a floor after a live
run. Nothing here reaches a provider, and no floor is declared.

**Since the fix round the draft grader reaches the product** (G2: the held-week count
is graded by `app.services.reporting.states_a_count_of_people`, the one copy of the
rule). So the draft-set tests that grade a held case are red until that function
exists — an `ImportError` raised in the test body, naming it. The check-set grader
controls import no application module and are green on any tree. The typed and
pinned tests reach `app.ai.contracts` and the prompt directory.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest
from fixtures.response_draft import CHECK_THEME, contract, contracts

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / "backend" / "app" / "ai" / "prompts"


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """`docs/MISTAKES.md` entry 40: the contracts module is imported by some tests here."""


def eval_module(name: str) -> ModuleType:
    """One of `tests/evals/`'s modules, with the repository root on `sys.path`."""
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as failure:  # pragma: no cover - a red, not a branch
        if failure.name is not None and name.startswith(failure.name):
            pytest.fail(f"There is no `{name}`. E7-04 done-when 8: typed cases for each task.")
        raise


def drafts() -> ModuleType:
    return eval_module("tests.evals.response_draft.cases")


def checks() -> ModuleType:
    return eval_module("tests.evals.draft_check.cases")


def test_every_draft_cases_exemplar_passes_its_grader() -> None:
    """The control for the draft set: a faithful draft holds.

    **The mutation this kills:** a grader too strict to pass anything, which would
    make every breach test below vacuous.
    """
    module = drafts()
    assert module.CASES, "The draft set has no cases."
    for case in module.CASES:
        assert (
            module.grade(case, case.exemplar) == []
        ), f"{case.case_id}'s own exemplar fails its grader: {module.grade(case, case.exemplar)}."


def test_every_draft_breach_fails_its_grader() -> None:
    """Deflection, an empty promise, a mention in passing, and every count phrasing: each fails.

    **The mutations this kills:** a grader matching topics without a commitment (the
    deflection passes); one accepting a commitment with no action verb ("I will
    consider your feedback", fix-round G3); one accepting the problem named with no
    action (the in-passing breach, G4); and a count check that misses any of the
    fix-round review's phrasings or "a few of you" (G2).
    """
    module = drafts()
    by_id = {case.case_id: case for case in module.CASES}
    assert set(module.BREACHES) <= set(by_id), "A breach names a case that does not exist."
    for case_id, answers in module.BREACHES.items():
        for answer in answers:
            assert module.grade(
                by_id[case_id], answer
            ), f"{case_id}'s breach {answer!r} passes its grader."


def test_each_held_week_breach_fails_on_its_count_alone() -> None:
    """The held breaches address every criticism, so their only failure is the count.

    **Without this**, a breach that also failed to address a criticism would pass
    `test_every_draft_breach_fails_its_grader` against a grader with no count check
    at all (`docs/MISTAKES.md` entry 3). **The mutation this kills:** the count leg
    of `grade` deleted, or `states_a_count` answering False for a phrasing.
    """
    module = drafts()
    by_id = {case.case_id: case for case in module.CASES}
    held = [case_id for case_id in module.BREACHES if by_id[case_id].has_a_held_stream]
    assert held, "No breach is planted in a held week, so the count leg is untested."
    for case_id in held:
        for answer in module.BREACHES[case_id]:
            failures = module.grade(by_id[case_id], answer)
            assert len(failures) == 1 and "number" in failures[0], (
                f"{case_id}'s breach {answer!r} fails as {failures}; it is planted to fail on "
                "its count alone."
            )


def test_each_deflection_breach_fails_on_addressing_alone() -> None:
    """The shown-week breaches fail for not addressing a criticism, and for nothing else.

    **The mutation this kills:** `addresses` gutted to a topic match — every
    deflection names its topic, so each would pass.
    """
    module = drafts()
    by_id = {case.case_id: case for case in module.CASES}
    shown = [case_id for case_id in module.BREACHES if not by_id[case_id].has_a_held_stream]
    assert shown, "No deflection breach is planted."
    for case_id in shown:
        for answer in module.BREACHES[case_id]:
            failures = module.grade(by_id[case_id], answer)
            assert failures and all(
                "address" in failure for failure in failures
            ), f"{case_id}'s breach {answer!r} fails as {failures}."


def test_a_count_is_graded_only_in_a_week_with_a_held_stream() -> None:
    """The count rule's twin: the same counting sentence passes in an all-shown week.

    Residue A: a shown stream's draft stating a count is accepted. **The mutation
    this kills:** a grader charging every week for a count.
    """
    module = drafts()
    shown = next(case for case in module.CASES if not case.has_a_held_stream)
    counting = shown.exemplar + " Three of you also asked for more office hours."
    assert (
        module.grade(shown, counting) == []
    ), f"A count in an all-shown week fails the grader: {module.grade(shown, counting)}."


def test_every_check_cases_expected_answer_passes_and_each_kind_of_error_fails() -> None:
    """The check grader, both ways. **Green on any tree.**

    Each case's expected answer passes; then the breaches, each one change away:
    an invented theme, a shown count off by one, a shown count dropped, a held
    theme given a count, an expected theme dropped, and an addressed theme named.
    **The mutation this kills:** a grader missing any one of those legs.
    """
    module = checks()
    assert module.CASES, "The check set has no cases."
    for case in module.CASES:
        expected = list(module.expected_pairs(case))
        assert (
            module.grade(case, expected) == []
        ), f"{case.case_id}'s expected answer fails its grader: {module.grade(case, expected)}."
        stored = case.stored()
        breaches: list[tuple[str, list[tuple[str, int | None]]]] = [
            ("an invented theme", [*expected, ("e7-04 an invented theme", 1)]),
        ]
        for index, (label, count) in enumerate(expected):
            rest = expected[:index] + expected[index + 1 :]
            breaches.append((f"{label!r} dropped", rest))
            if count is None:
                breaches.append((f"held {label!r} given a count", [*rest, (label, 2)]))
            else:
                breaches.append((f"{label!r} off by one", [*rest, (label, count + 1)]))
                breaches.append((f"{label!r} without its count", [*rest, (label, None)]))
        addressed = [label for label in stored if label not in case.unaddressed]
        if addressed:
            breaches.append(
                ("an addressed theme named", [*expected, (addressed[0], stored[addressed[0]])])
            )
        for what, answer in breaches:
            assert module.grade(case, answer), f"{case.case_id}: {what} passes the grader."


def test_the_check_sets_families_cover_a_held_theme_and_an_empty_answer() -> None:
    """The behaviours done-when 8 names have cases: a held theme without a count, and nothing.

    **The mutation this kills:** a set that quietly loses the held-stream family —
    the one case a live run would catch a model writing a count into.
    """
    module = checks()
    held = [case for case in module.CASES if any(c is None for _, c in module.expected_pairs(case))]
    empty = [case for case in module.CASES if not case.unaddressed]
    assert held, "No check case expects a held theme named without a count."
    assert empty, "No check case expects an empty answer."


def test_the_check_cases_are_typed_through_the_check_theme_contract() -> None:
    """SPEC §9.3: an eval case is a typed object built from the task's own contract.

    Red before E7-04, naming the missing `CheckTheme`. **The mutation this kills:**
    a contract change that the set does not follow — a renamed field, a count
    made required again — which breaks here rather than at the first live run.
    """
    contract(CHECK_THEME)
    module = checks()
    for case in module.CASES:
        built = module.expected_themes(case, contracts())
        assert [(t.label, t.comment_count) for t in built] == list(
            module.expected_pairs(case)
        ), f"{case.case_id}'s typed answer {built!r} is not its expected pairs."


@pytest.mark.parametrize(
    "name", ("tests.evals.response_draft.cases", "tests.evals.draft_check.cases")
)
def test_each_set_is_pinned_to_a_prompt_file_the_ticket_ships(name: str) -> None:
    """`PROMPT_VERSION` names a prompt file that exists (ADR 0031: a version is a file stem).

    Red before E7-04: the ticket owns `response_draft.v1.md` and `draft_check.v1.md`.
    **The mutation this kills:** a set pinned to a version nothing renders, which
    measures a prompt nobody sends.
    """
    version = eval_module(name).PROMPT_VERSION
    path = PROMPTS_DIR / f"{version}.md"
    assert path.is_file(), (
        f"`{name}` is pinned to {version!r} and there is no {path.relative_to(REPO_ROOT)}. E7-04 "
        "owns that prompt file."
    )
