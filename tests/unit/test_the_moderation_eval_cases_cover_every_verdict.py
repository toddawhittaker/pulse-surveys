"""The moderation eval set: typed, all six verdicts, Care classes under `threat/`, no floor.

SPEC §9.3 measures moderation with typed cases, and its threat and self-harm
recall floor is the strictest in the suite. The cases ship now, unregistered; the
floors wait for E10's live run, so the threat slot stays deferred and holds no set,
and the moderation slot arrives with its floor in E10's floor-setting pull request.
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
    """No floor is set or moved (done-when 9): the threat slot stays empty, and no moderation slot yet.

    The moderation cases ship unregistered. A registry slot needs a `floors.py`
    beside it, and floor files are reviewed by the owner in their own pull
    request, so the moderation slot and its floor arrive together in E10's
    floor-setting pull request. Until then the threat slot stays deferred, with
    no numbers and no cases.

    **The mutation it kills:** a slot that carries numbers or cases before its
    floor is set, either the threat slot gaining them or a moderation slot
    registered early (with a floor file this ticket may not add).
    """
    registry = eval_module("tests.evals.registry")
    deferred = eval_module("tests.evals.declarations").FloorStatus.DEFERRED
    slots = {task.name: task for task in registry.TASKS}
    assert "moderation" not in slots, (
        "The registry has a moderation slot. It arrives with its floor in E10's floor-setting "
        "pull request, because floor files are owner-reviewed."
    )
    threat = slots["threat"]
    assert threat.floors.status is deferred
    assert not threat.floors.carries_numbers
    assert threat.cases == ()
