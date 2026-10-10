"""The moderation eval set: typed, all six verdicts, Care classes under `threat/`, no floor.

SPEC §9.3 measures moderation with typed cases, and its threat and self-harm
recall floor is the strictest in the suite. The cases ship now; the floors wait
for E10's live run, so both registry slots stay deferred and hold no set.
"""

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """Importing the cases reaches `app.ai.contracts` (`docs/MISTAKES.md` entry 40)."""


def eval_module(name: str) -> ModuleType:
    """One of `tests/evals/`'s modules; pytest puts `tests/` on the path, not the root."""
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module(name)


def test_the_moderation_set_holds_every_verdict_as_the_contracts_enum() -> None:
    from app.ai.contracts import ModerationVerdict

    moderation_cases = eval_module("tests.evals.moderation.cases")
    expected = {case.expected for case in moderation_cases.CASES}
    assert expected == set(ModerationVerdict)
    assert all(isinstance(case.expected, ModerationVerdict) for case in moderation_cases.CASES)
    assert {case.prompt_version for case in moderation_cases.CASES} == {"moderation.v1"}
    ids = [case.case_id for case in moderation_cases.CASES]
    assert len(ids) == len(set(ids))


def test_the_threat_and_self_harm_cases_live_under_threat_and_are_in_the_set() -> None:
    moderation_cases = eval_module("tests.evals.moderation.cases")
    threat_cases = eval_module("tests.evals.threat.cases")
    tokens = {case.expected.value for case in threat_cases.CASES}
    assert tokens == {"threat", "self_harm"}
    assert set(threat_cases.CASES) <= set(moderation_cases.CASES)


def test_no_moderation_floor_is_set_and_no_slot_carries_a_set() -> None:
    registry = eval_module("tests.evals.registry")
    deferred = eval_module("tests.evals.declarations").FloorStatus.DEFERRED
    slots = {task.name: task for task in registry.TASKS}
    for name in ("moderation", "threat"):
        assert slots[name].floors.status is deferred
        assert not slots[name].floors.carries_numbers
        assert slots[name].cases == ()
