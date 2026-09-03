"""The eval run reaches the model through the gateway on a measurement's timeout — ticket E2-18.

Dispute E2-12-06, pinned. An earlier draft of `tests/evals/live.py` reached the
model through `app.ai.tasks.verdict_for_comment`, which takes a supplied gateway,
writes no row and needs no session — everything an eval run wants, plus one thing
it must not have. That function is SPEC §3.3's submit path, and §3.3 says that on
a provider timeout "the heuristic floor applies and the submission is accepted",
so a merely slow answer comes back as the twenty-five-character count stamped
`character-floor`.

Two full runs over the ninety-eight-case set were voided that way, at two and then
five floored cases. The bias is what made them unsound rather than lossy: the set
is built out of the cases the character rule gets wrong, so a floored case scores
the heuristic's error as the model's, worst in the two families the set exists to
measure.

**The repair shipped with nothing asserting it** (`docs/MISTAKES.md` entry 2).
Reverting either half — the routing, or the sixty-second timeout — is green
across the whole suite today and is caught only by a paid run, and then only by
somebody reading the report closely. Both halves are pinned here.

**Two detectors, because the routing can regress in more than one currency.**
`test_the_eval_classifier_never_reaches_the_submit_paths_task` watches the named
function, which is the exact regression the dispute found.
`test_the_eval_classifier_calls_the_gateway_with_the_eval_timeout` watches what
reaches the gateway, which catches a route through §3.3's budget whatever
function carries it there. A guard that enumerates mechanisms misses the one it
was not told about (`docs/MISTAKES.md` entry 35), so the enumerated detector is
backed by a mechanism-independent one.

**And the enumerated detector has controls**, which is the other half of entry
35's rule: "require it to *find* each one on a subject that certainly has it".
The two control tests below route through the submit path deliberately, in each of
the two ways a caller can hold that function, and require the detector to see it.
Without them, a spy installed where nothing looks would report "no submit-path
call" forever, and the pin would be a comment.

**No provider is reached.** The gateway class is replaced by a recorder and the
submit path by a spy, so the only thing the classifier under test can call is a
local object. Nothing here opens a socket, and nothing here costs anything.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# SPEC §13 places the gateway; SPEC §7.4 names the class in prose: "All model
# calls go through one internal `AIGateway`".
GATEWAY_MODULE = "app.ai.gateway"
GATEWAY_CLASS = "AIGateway"

# SPEC §3.3's submit path, and the function dispute E2-12-06 found the eval run
# routed through. `tests/evals/live.py` names it in its own docstring as the thing
# it must not call.
TASKS_MODULE = "app.ai.tasks"
SUBMIT_PATH_FUNCTION = "verdict_for_comment"

# The module that builds what an eval run measures with.
EVAL_MODULE = "tests.evals.live"

# `EVAL_TIMEOUT_SECONDS` as committed. Written down rather than read from the
# module, because a test comparing a constant against itself cannot see it move
# (`docs/MISTAKES.md` entry 19) — and moving it is precisely the regression.
EXPECTED_EVAL_TIMEOUT_SECONDS = 60.0

# One comment to classify. Short, invented, and nothing depends on its content:
# every callee in this module is a recorder.
A_COMMENT = "Lab ran 40 min over."

# What the stand-ins answer with. Never inspected as a verdict — the classifier
# hands its callee's return value straight back, so anything distinguishable does.
GATEWAY_ANSWER = ("verdict-from-the-recording-gateway", "usage-from-the-recording-gateway")
SUBMIT_PATH_ANSWER = ("verdict-from-the-submit-path-spy", "usage-from-the-submit-path-spy")


def eval_module(name: str) -> ModuleType:
    """Import one of the modules under test, or fail naming the deliverable.

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
                f"There is no `{name}` module. E2-12 puts the eval runner and the live "
                "classifier it builds under `tests/evals/`."
            )
        raise


class RecordingGateway:
    """Stands in for `AIGateway`, and remembers every call made to it.

    Construction is recorded because which flag built a gateway is visible nowhere
    else (`tests/unit/test_the_eval_runner_builds_a_live_gateway.py` is where that
    property is asserted). The task methods are recorded because *what the
    classifier asks the gateway to do* — above all with which timeout — is the
    property this module is about.

    Both `run_task` and `run_task_with_usage` are here so that a route arriving by
    either one is seen. A recorder that implemented only the method the current
    code calls would answer `AttributeError` to the other and turn a routing
    regression into an error nobody could read as a routing regression.
    """

    constructions: ClassVar[list[dict[str, Any]]] = []
    task_calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        RecordingGateway.constructions.append({"args": args, "kwargs": kwargs})

    def run_task(self, *args: Any, **kwargs: Any) -> object:
        RecordingGateway.task_calls.append({"method": "run_task", "args": args, "kwargs": kwargs})
        return GATEWAY_ANSWER

    def run_task_with_usage(self, *args: Any, **kwargs: Any) -> object:
        RecordingGateway.task_calls.append(
            {"method": "run_task_with_usage", "args": args, "kwargs": kwargs}
        )
        return GATEWAY_ANSWER


@pytest.fixture
def gateway_calls(
    monkeypatch: pytest.MonkeyPatch, configured_env: dict[str, str]
) -> list[dict[str, Any]]:
    """Every task call the classifier makes, with `AIGateway` replaced by a recorder.

    Substituted on the module rather than injected, because `tests/evals/live.py`
    reaches the class through the module object at call time and says in its own
    docstring that this is why.

    `configured_env` is `docs/MISTAKES.md` entry 40: importing the gateway and the
    tasks module reaches the settings, so the environment the run happens under is
    stated here rather than inherited from whatever shell started pytest.
    """
    RecordingGateway.constructions = []
    RecordingGateway.task_calls = []
    monkeypatch.setattr(eval_module(GATEWAY_MODULE), GATEWAY_CLASS, RecordingGateway, raising=False)
    return RecordingGateway.task_calls


@pytest.fixture
def submit_path_calls(
    monkeypatch: pytest.MonkeyPatch, configured_env: dict[str, str]
) -> Iterator[list[dict[str, Any]]]:
    """Every call to SPEC §3.3's submit path, from anywhere, for the length of one test.

    **The spy records and answers rather than raising.** A raising spy would turn a
    routing regression into an exception and the test into an error, which reads as
    a broken test rather than as the finding it is. Recording leaves the failure
    where it belongs: on an assertion that names the route it saw.

    **`tests.evals.live` is reloaded with the spy already installed**, and that is
    the part worth explaining. Patching an attribute on `app.ai.tasks` is seen by a
    caller that looks the name up at call time and *not* by one that bound it at
    import time with `from app.ai.tasks import verdict_for_comment` — the module
    would hold its own reference to the real function and the spy would sit
    watching a name nobody reads. That is `docs/MISTAKES.md` entry 35's shape: a
    guard enumerating mechanisms and missing the one a regression would actually
    use. Reloading the module after the patch re-runs its import-time bindings
    against the spy, so both styles are visible. The controls below prove both
    styles are seen rather than asserting it here.

    The undo is explicit and comes before the second reload: this fixture depends
    on `monkeypatch`, so its own teardown runs first, and reloading while the spy
    was still installed would leave the reloaded module bound to the spy for every
    test that followed.
    """
    tasks_module = eval_module(TASKS_MODULE)
    if not hasattr(tasks_module, SUBMIT_PATH_FUNCTION):
        pytest.fail(
            f"`{TASKS_MODULE}` exposes no `{SUBMIT_PATH_FUNCTION}`. That is SPEC §3.3's submit "
            "path — the function dispute E2-12-06 found the eval run routed through, and the "
            "one `tests/evals/live.py` must not call. If it has been renamed, this pin has to "
            "follow it: a spy on a name nothing calls reports 'no submit-path call' forever."
        )

    calls: list[dict[str, Any]] = []

    def spy(*args: Any, **kwargs: Any) -> object:
        calls.append({"args": args, "kwargs": kwargs})
        return SUBMIT_PATH_ANSWER

    monkeypatch.setattr(tasks_module, SUBMIT_PATH_FUNCTION, spy)
    importlib.reload(eval_module(EVAL_MODULE))

    yield calls

    monkeypatch.undo()
    importlib.reload(eval_module(EVAL_MODULE))


def test_the_eval_timeout_is_longer_than_the_submit_paths_budget(
    configured_env: dict[str, str],
) -> None:
    """A measurement's timeout and a student's are different numbers, and this says which is which.

    SPEC §3.3's `VALIDITY_TIMEOUT_SECONDS` exists so a submission is never held on a
    slow provider: when it expires the submit path accepts the answer and falls
    back to the character rule. Nobody is waiting on an eval call, and this set is
    built out of the cases that character rule gets wrong — so an eval run cut off
    at the student's budget selects the slow answers out and scores the heuristic's
    errors as the model's, which is what voided two runs.

    The relation is asserted rather than the two values, because that is the
    property: whatever §3.3's budget becomes, the eval timeout has to be past it.
    Raising the submit path's budget to meet the eval timeout is the same defect
    arriving from the other side, and it is red here too.

    **The mutation this kills:** set `EVAL_TIMEOUT_SECONDS` back to §3.3's budget —
    the revert of dispute E2-12-06's fix, which is green everywhere else in this
    repository and shows up only as floored cases in a paid run.
    """
    from app.ai.tasks import VALIDITY_TIMEOUT_SECONDS

    live = eval_module(EVAL_MODULE)
    assert live.EVAL_TIMEOUT_SECONDS > VALIDITY_TIMEOUT_SECONDS, (
        f"`{EVAL_MODULE}.EVAL_TIMEOUT_SECONDS` is {live.EVAL_TIMEOUT_SECONDS} and SPEC §3.3's "
        f"`VALIDITY_TIMEOUT_SECONDS` is {VALIDITY_TIMEOUT_SECONDS}. §3.3's budget is a "
        "student's — it exists so a submission is never held on a slow provider, and it fails "
        "open to the twenty-five-character rule. An eval run held to it drops exactly the slow "
        "answers and scores the heuristic's errors as the model's, in the two families this "
        "set exists to measure. Dispute E2-12-06 voided two full runs that way."
    )


def test_the_eval_timeout_is_the_value_that_was_committed(configured_env: dict[str, str]) -> None:
    """Sixty seconds, written down, so moving it is a decision somebody makes on purpose.

    The relation above is the property, and it is satisfied by any number a hair
    over §3.3's budget — which would go on selecting slow answers out while
    reading as correct. `tests/evals/live.py` chose sixty against a median around
    two seconds and a tail past five, "far past the provider's tail rather than
    close to it", and that headroom is the thing a well-meaning tightening would
    take away.

    So the number is pinned. Moving it is not forbidden; it is a pull request whose
    subject is moving it, which is the same rule CI applies to an eval floor.

    **The mutation this kills:** trim the timeout toward §3.3's budget — six
    seconds, say — which keeps the relation above true, passes every other test,
    and quietly restores the sampling bias the sixty seconds was chosen to remove.
    """
    live = eval_module(EVAL_MODULE)
    assert live.EVAL_TIMEOUT_SECONDS == EXPECTED_EVAL_TIMEOUT_SECONDS, (
        f"`{EVAL_MODULE}.EVAL_TIMEOUT_SECONDS` is {live.EVAL_TIMEOUT_SECONDS} and was "
        f"committed as {EXPECTED_EVAL_TIMEOUT_SECONDS}. The value is deliberately far past the "
        "provider's tail rather than close to it, because a limit near the tail goes on "
        "selecting the slow answers out of the measurement. Changing it changes what SPEC "
        "§9.3's floors were measured over, so it belongs in a pull request that says so — and "
        "this line moves in that pull request."
    )


def test_the_eval_classifier_calls_the_gateway_with_the_eval_timeout(
    gateway_calls: list[dict[str, Any]], configured_env: dict[str, str]
) -> None:
    """What the eval run asks the gateway to do, and on whose clock.

    The mechanism-independent half of the routing pin. It does not care which
    function carries the call; it reads the timeout that reached the gateway. Any
    route through SPEC §3.3's submit path carries §3.3's budget, so a regression
    shows up here whether or not it arrives by the function the next test watches.

    Both halves are asserted. That the timeout is the eval module's own constant
    catches a call that never picked it up; that it is longer than §3.3's budget
    catches a mutation moving the constant and the call together, which is the
    edit an implementer makes in one pass.

    **No provider is reached.** `AIGateway` is a recorder for the length of this
    test and the classifier's only callee is that recorder.

    **The mutation this kills:** pass `VALIDITY_TIMEOUT_SECONDS` at the call site
    while leaving `EVAL_TIMEOUT_SECONDS` defined and unused, which no other test in
    this repository can see. **The near miss that must stay green:** the gateway
    method being renamed or gaining arguments, since this asserts the timeout that
    arrives rather than the shape of the call.
    """
    from app.ai.tasks import VALIDITY_TIMEOUT_SECONDS

    live = eval_module(EVAL_MODULE)
    classify: Callable[[str], object] = live.build_validity_classifier()
    classify(A_COMMENT)

    assert len(gateway_calls) == 1, (
        f"classifying one comment made {len(gateway_calls)} gateway task call(s): "
        f"{gateway_calls}. An eval run is one live model call per case (E2-12), and a case "
        "that reached the gateway zero times reached the model by some other route — which is "
        "the whole subject of dispute E2-12-06."
    )
    sent = gateway_calls[0]["kwargs"].get("timeout")
    assert sent == live.EVAL_TIMEOUT_SECONDS, (
        f"the eval classifier asked the gateway for a timeout of {sent!r} and "
        f"`{EVAL_MODULE}.EVAL_TIMEOUT_SECONDS` is {live.EVAL_TIMEOUT_SECONDS}. The call "
        f"recorded was {gateway_calls[0]!r}. A constant that is defined and not passed is not "
        "a timeout, it is a comment."
    )
    assert sent is not None and sent > VALIDITY_TIMEOUT_SECONDS, (
        f"the eval classifier asked the gateway for a timeout of {sent!r}, and SPEC §3.3's "
        f"budget is {VALIDITY_TIMEOUT_SECONDS}. A measurement held to a student's budget drops "
        "the slow answers, and the cases it drops are the ones the character rule gets wrong. "
        "Two full runs were voided that way (dispute E2-12-06)."
    )


def test_the_eval_classifier_never_reaches_the_submit_paths_task(
    submit_path_calls: list[dict[str, Any]],
    gateway_calls: list[dict[str, Any]],
    configured_env: dict[str, str],
) -> None:
    """The exact regression dispute E2-12-06 found: the eval run going through §3.3's path.

    `app.ai.tasks.verdict_for_comment` is everything an eval run wants — it takes a
    supplied gateway, writes no row, needs no session — and it fails open. On a slow
    answer it substitutes the twenty-five-character count and stamps
    `character-floor` as the prompt version, so the run reports the heuristic's
    verdicts as the model's over exactly the cases the heuristic gets wrong.

    The absence is asserted after the classifier has actually been called, not over
    a classifier nobody ran: "the submit path was not called" is worth nothing if
    nothing was called at all. The gateway recorder is in place for the same
    reason — the call has to be able to complete.

    **The controls below are what make this assertion mean something.** An absence
    test passes when the detector is broken, so the two tests after this one route
    through the submit path on purpose and require the same spy to see it.

    **The mutation this kills:** put the call back through
    `app.ai.tasks.verdict_for_comment`, which is what the earlier draft did, and
    which passes the prompt-version pin, the live-gateway construction test and
    every other test in this suite — it was caught by reading a paid run's output.
    """
    live = eval_module(EVAL_MODULE)
    classify: Callable[[str], object] = live.build_validity_classifier()
    classify(A_COMMENT)

    assert gateway_calls or submit_path_calls, (
        "classifying one comment called neither the gateway nor the submit path, so this "
        "test's absence assertion would hold over a classifier that did nothing at all."
    )
    assert not submit_path_calls, (
        f"the eval classifier reached `{TASKS_MODULE}.{SUBMIT_PATH_FUNCTION}`: "
        f"{submit_path_calls}.\n"
        "\n"
        "That is SPEC §3.3's submit path, and §3.3 fails open — on a provider timeout the "
        "heuristic floor applies and the submission is accepted. In an eval run that turns a "
        "merely slow answer into a twenty-five-character count stamped `character-floor`, and "
        "this set is built out of the cases that count gets wrong, so the floored cases are "
        "the heuristic's errors reported as the model's. Dispute E2-12-06: two full runs over "
        "the ninety-eight-case set were voided this way, at two and then five floored cases.\n"
        "\n"
        "The eval path calls the gateway directly, on `EVAL_TIMEOUT_SECONDS`, and lets a real "
        "outage raise and fail the run loudly."
    )


def test_the_submit_path_detector_finds_a_call_it_is_meant_to_see(
    submit_path_calls: list[dict[str, Any]],
) -> None:
    """The control the absence test above is worthless without.

    `docs/MISTAKES.md` entry 35's rule: "when a guard enumerates mechanisms,
    require it to *find* each one on a subject that certainly has it, as a
    control. A guard that only ever reports absence cannot tell you which
    mechanisms it can see." The pin above reports an absence, and a spy installed
    on the wrong object, watching a renamed function or patched after the caller
    has taken its reference reports exactly that absence, forever and greenly. So
    two subjects here route through SPEC §3.3's submit path on purpose, and the
    same spy has to see both.

    **The two subjects are the two ways a caller holds that function.** One looks
    the name up on the module when it calls; the other takes the object once and
    calls it later, which is what `from app.ai.tasks import verdict_for_comment`
    does at a module's top level. In CPython both resolve through the module
    attribute, so what separates them is *when* — and "when" is the half a
    monkeypatched spy can get wrong. The fixture installs the spy before it
    reloads `tests/evals/live.py`, so that module's import-time bindings, if it
    ever takes any, are taken from the spy; nothing today can prove that ordering
    matters, because `tests/evals/live.py` does not bind the name at all, and it is
    written down here rather than left for the refactor that does.

    Both subjects hold the function through the module object rather than through
    a typed `from` statement, so this control commits to nothing about §3.3's
    signature. The pin is about the route, not about how the submit path is called.

    **The mutation this kills:** point `TASKS_MODULE` or `SUBMIT_PATH_FUNCTION` at
    something nothing calls, or patch the spy onto a copy of the module rather than
    the one importers read — each of which leaves
    `test_the_eval_classifier_never_reaches_the_submit_paths_task` green over every
    possible routing, including the one that voided two runs.
    """
    tasks_module = eval_module(TASKS_MODULE)

    def looked_up_when_called(comment: str) -> object:
        return getattr(tasks_module, SUBMIT_PATH_FUNCTION)(comment)

    looked_up_when_called(A_COMMENT)
    assert submit_path_calls, (
        f"a call made straight to `{TASKS_MODULE}.{SUBMIT_PATH_FUNCTION}` was not seen by the "
        "spy the routing pin relies on. The pin is therefore reporting an absence it could not "
        "detect, which is a green test asserting nothing."
    )

    bound_once = getattr(tasks_module, SUBMIT_PATH_FUNCTION)
    seen_so_far = len(submit_path_calls)

    def bound_before_calling(comment: str) -> object:
        return bound_once(comment)

    bound_before_calling(A_COMMENT)
    assert len(submit_path_calls) > seen_so_far, (
        f"a call through a reference to `{SUBMIT_PATH_FUNCTION}` taken from `{TASKS_MODULE}` "
        "and held was not seen, while a call that looked the name up was. That is the shape a "
        "module-level `from app.ai.tasks import "
        f"{SUBMIT_PATH_FUNCTION}` produces, and the routing pin would be blind to it."
    )
