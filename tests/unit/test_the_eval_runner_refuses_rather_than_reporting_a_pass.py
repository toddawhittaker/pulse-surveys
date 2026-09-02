"""The eval runner never reports a pass over a task it did not grade — ticket E2-12.

SPEC §9.3 is one sentence — "prompt or model changes must meet per-task
precision/recall floors" — and `CLAUDE.md` turns the threat and self-harm half of
it into a hard gate whose lowering is the repository owner's call. Neither
statement survives a runner that can exit 0 without measuring anything, and there
are more ways for that to happen than there are ways to measure: a floor declared
over a set that does not exist, a placeholder nobody filled in, a slot held open
for another epic that quietly acquired a number, a set with no positive case to
compute recall from, a missing credential, an answer produced under a different
prompt version.

Every one of those is a **refusal** here rather than a skip, and a refusal exits
non-zero. `docs/MISTAKES.md` entry 9: a gate that has never failed is a comment —
so each refusal below is asserted together with the near miss that must not
refuse, because a runner that refused everything would satisfy half this module
perfectly and would be exactly as useless as one that refused nothing.

**These are controls, not red tests, and the distinction matters when they
fail.** The runner is E2-12's own deliverable and it lives under `tests/`, so the
subject of this module ships in the same change as the module. A red here is a
broken test or a broken runner, and in both cases the repair is on this side of
the wall — it is not the implementer's half arriving late. The tests that are
genuinely red until the implementer's half lands are in
`test_the_eval_runner_builds_a_live_gateway.py`,
`test_the_changed_job_classifies_an_ai_surface.py` and
`test_the_eval_gate_fires_on_an_ai_touching_change.py`.

**No live call happens anywhere in this module.** Every task graded here is
handed a stub classifier through `evaluate`'s `classifiers` argument, which
nothing in CI passes. Two of the tests assert that the stub was never called at
all, which is the only way to tell a refusal that happened *before* the provider
was reached from one that happened after — and the credential refusal is only
worth anything if it is the first.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The module path `.github/workflows/ci.yml`'s `detect` job already pins:
# `[ -f tests/evals/runner.py ]`, and the eval step runs
# `python -m tests.evals.runner`. So this name is settled by the workflow rather
# than chosen here.
RUNNER_MODULE = "tests.evals.runner"

# A credential-shaped value that is not a credential. Nothing here resembles a
# real key and nothing was copied from a working `.env` (CLAUDE.md, secrets).
NOT_A_REAL_KEY = "e2-12-unit-test-placeholder-not-a-credential"

# What the runner reads the credential out of. `.env.example` documents it in the
# `AI_PROVIDER_*` triple.
PROVIDER_KEY_VARIABLE = "AI_PROVIDER_API_KEY"


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """Every test here runs under `.env.example`'s documented values.

    `docs/MISTAKES.md` entry 40: a test whose subject reads the process
    environment states the value it runs under, in its own fixture chain. Nothing
    below reads it *directly* — each one hands `evaluate` an explicit `environ`
    mapping, which is what that argument is for — but importing
    `tests.evals.runner` reaches `app.ai.contracts` and `app.ai.tasks`, and a
    module that builds anything out of `Settings` at import time would otherwise
    build it out of whatever the developer's shell happened to hold.

    Autouse rather than requested on each test: the reason is the same for all of
    them, and naming it twenty times is twenty places for the twenty-first to be
    forgotten.
    """


def eval_module(name: str) -> ModuleType:
    """Import one of `tests/evals/`'s modules, or fail naming the deliverable.

    The repository root goes on `sys.path` first. pytest puts `tests/` there —
    `tests/conftest.py` sits at that level and there is no `tests/__init__.py` —
    but not the root, while `python -m tests.evals.runner` runs with the root as
    the working directory and needs nothing else. So the two invocations resolve
    the same package through different paths, and this is the one line that makes
    the pytest side agree with the workflow side.

    A missing module fails with a message rather than raising a collection error:
    an import error is not a red, it is a module nobody can read the result of.
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
                f"There is no `{name}` module. E2-12's scope puts the runner at "
                "`tests/evals/runner.py`, which is the exact path "
                "`.github/workflows/ci.yml`'s `detect` job probes for and the module "
                "`python -m tests.evals.runner` imports."
            )
        raise


def declarations() -> ModuleType:
    """`tests.evals.declarations`, which holds the floor states."""
    return eval_module("tests.evals.declarations")


def runner() -> ModuleType:
    """`tests.evals.runner`."""
    return eval_module(RUNNER_MODULE)


def validity_cases() -> ModuleType:
    """`tests.evals.validity.cases`, for the two verdicts these probes use."""
    return eval_module("tests.evals.validity.cases")


def output(verdict: Any, prompt_version: str) -> Any:
    """One `CommentValidityOutput`, built from the real contract.

    The real contract rather than a stand-in with the right attributes, because a
    stub shaped by this file would keep answering after a contract change and the
    whole of SPEC §7.4's argument for typed eval fixtures is that it should not
    (`docs/MISTAKES.md` entry 19).
    """
    contracts = eval_module("app.ai.contracts")
    contract = getattr(contracts, "CommentValidityOutput", None)
    if contract is None:
        pytest.fail(
            "`app.ai.contracts` exposes no `CommentValidityOutput`. E0-12 shipped the "
            "comment-validity contract and SPEC §7.4 makes it the eval fixture; if it is "
            "spelled differently, that spelling is the one line that changes here and in "
            "tests/evals/runner.py."
        )
    try:
        return contract(verdict=verdict, prompt_version=prompt_version, model_id="e2-12-stub-model")
    except Exception as failure:
        # Reported, never swallowed: `pytest.fail` raises out of this handler.
        pytest.fail(
            f"`CommentValidityOutput` could not be built from a verdict, a prompt version "
            f"and a model id: {failure}. ADR 0031 makes those two audit values required "
            "fields on every task contract and E2-12's work order says the task's own "
            "output is the single `verdict` field. A third required field is an interface "
            "question for the ticket rather than something to fill in blind."
        )


@dataclass(frozen=True)
class StubUsage:
    """What a stubbed call reports it cost.

    The shape of `app.ai.gateway.TaskUsage` — the fields
    `tests/evals/declarations.py`'s `TaskUsageLike` protocol names — supplied here
    rather than imported, because nothing in this module reaches a provider and a
    real `TaskUsage` would be a value with no run behind it. The numbers are
    arbitrary and distinct so that a total which dropped or double-counted one
    field is visible in the sum.

    `cache_read_tokens` is deliberately a *part* of `input_tokens` and not
    additional, which is the property the report's "of them served from cache"
    wording depends on.
    """

    input_tokens: int = 100
    output_tokens: int = 10
    cache_read_tokens: int = 40
    cache_write_tokens: int = 5
    total_tokens: int = 110
    requests: int = 1
    details: Mapping[str, int] = field(default_factory=lambda: {"reasoning_tokens": 3})


class Stub:
    """A classifier that answers from a table and counts what it was asked.

    The count is the point of the class. A refusal that happens after the
    provider was reached is a refusal that already spent money and already sent a
    student-shaped comment off the machine, and nothing about the returned report
    tells the two apart.

    **It answers with a `(output, usage)` pair since dispute E2-12-06**, because
    that is what the eval path returns now: `tests/evals/live.py` calls
    `gateway.run_task_with_usage` rather than going through §3.3's submit path,
    where a slow answer was being replaced by a character count. Nothing this
    module asserts moved with it — the refusals, the pin and the floor
    comparisons are all unchanged — and the usage half is here so that the shape
    the runner consumes is the shape it will meet in a live run.
    """

    def __init__(self, answers: dict[str, Any], prompt_version: str) -> None:
        self.answers = answers
        self.prompt_version = prompt_version
        self.asked: list[str] = []

    def __call__(self, comment: str) -> tuple[Any, StubUsage]:
        self.asked.append(comment)
        return output(self.answers[comment], self.prompt_version), StubUsage()


def build_task(
    *,
    name: str = "probe",
    floors: Any,
    cases: Sequence[Any] = (),
    positive: Any = None,
    prompt_version: str | None = "validity.v1",
    classifier: Callable[[], Callable[[str], Any]] | None = None,
) -> Any:
    """One `EvalTask` for a probe, with the fields this module cares about named."""
    return declarations().EvalTask(
        name=name,
        floors=floors,
        cases=tuple(cases),
        positive=positive,
        prompt_version=prompt_version,
        classifier=classifier,
    )


def build_case(case_id: str, comment: str, expected: Any, prompt_version: str) -> Any:
    """One `EvalCase`."""
    return declarations().EvalCase(
        case_id=case_id,
        comment=comment,
        expected=expected,
        prompt_version=prompt_version,
        family="probe",
    )


def balanced_set() -> tuple[Any, ...]:
    """Four substantive cases and four that are not, pinned to `validity.v1`.

    Eight cases so that three right out of four answers is exactly 0.75, which is
    a number a float comparison can be equal to. The at-the-floor case below
    turns on that equality.
    """
    cases_module = validity_cases()
    substantive = cases_module.SUBSTANTIVE
    insufficient = cases_module.INSUFFICIENT
    return (
        build_case("p-1", "substantive one", substantive, "validity.v1"),
        build_case("p-2", "substantive two", substantive, "validity.v1"),
        build_case("p-3", "substantive three", substantive, "validity.v1"),
        build_case("p-4", "substantive four", substantive, "validity.v1"),
        build_case("p-5", "insufficient one", insufficient, "validity.v1"),
        build_case("p-6", "insufficient two", insufficient, "validity.v1"),
        build_case("p-7", "insufficient three", insufficient, "validity.v1"),
        build_case("p-8", "insufficient four", insufficient, "validity.v1"),
    )


def three_quarters_stub() -> Stub:
    """A classifier scoring precision 0.75 and recall 0.75 over `balanced_set()`.

    Three of the four substantive cases are found, one is missed, and one
    insufficient case is called substantive: three true positives, one false
    negative, one false positive.
    """
    cases_module = validity_cases()
    substantive = cases_module.SUBSTANTIVE
    insufficient = cases_module.INSUFFICIENT
    return Stub(
        {
            "substantive one": substantive,
            "substantive two": substantive,
            "substantive three": substantive,
            "substantive four": insufficient,
            "insufficient one": substantive,
            "insufficient two": insufficient,
            "insufficient three": insufficient,
            "insufficient four": insufficient,
        },
        "validity.v1",
    )


def keyed() -> dict[str, str]:
    """A process environment holding a provider credential."""
    return {PROVIDER_KEY_VARIABLE: NOT_A_REAL_KEY}


def test_a_floor_declared_over_no_eval_set_is_refused() -> None:
    """E2-12: "the runner refuses to report a task with a floor and no set".

    A floor with nothing to measure it over is the shape that reads as a working
    gate from every angle except the one that matters: the declaration is there,
    the report names the task, and the number is never compared to anything. It
    is `docs/MISTAKES.md` entry 9 built into the structure — a guard cited as a
    guarantee and never executed.

    **The mutation this kills:** grade the tasks that have cases and pass over
    the ones that do not, which is the natural loop and is one `if` away from
    correct. **The near miss that must stay green:** the same floor with a set
    under it, asserted in the test below, since a runner that refused every task
    would pass this and grade nothing.
    """
    floors = declarations().enforced(precision=0.5, recall=0.5, note="a probe's floor")
    task = build_task(floors=floors, cases=(), positive=validity_cases().SUBSTANTIVE)

    with pytest.raises(declarations().EvalRefusalError) as refusal:
        runner().evaluate([task], classifiers={}, environ=keyed())

    assert "no eval set" in str(refusal.value), (
        "The runner refused, and not for the reason this test is about. E2-12's scope: the "
        "runner 'refuses to report a task with a floor and no set rather than passing it "
        f"silently'. What it said was:\n{refusal.value}"
    )


def test_the_same_floor_over_a_real_set_is_graded_rather_than_refused() -> None:
    """The near miss for the test above: a floor with a set under it must run.

    Without this, a runner that raised `EvalRefusalError` unconditionally would satisfy
    the refusal half of this module completely, and SPEC §9.3's gate would be a
    command that always exits 1 — which is the same non-signal as one that always
    exits 0, arriving from the other side.

    **The mutation this kills:** refuse whenever a floor is declared at all.
    """
    floors = declarations().enforced(precision=0.5, recall=0.5, note="a probe's floor")
    stub = three_quarters_stub()
    task = build_task(floors=floors, cases=balanced_set(), positive=validity_cases().SUBSTANTIVE)

    report = runner().evaluate([task], classifiers={"probe": stub}, environ=keyed())

    assert report.passed, f"a 0.75/0.75 run against a 0.5/0.5 floor did not pass:\n{report.text()}"
    assert report.tasks[0].graded, "the task was reported without being graded"
    assert len(stub.asked) == len(balanced_set()), (
        f"the classifier was asked {len(stub.asked)} times for a set of "
        f"{len(balanced_set())} cases. Every case gets exactly one call; a set graded on "
        "fewer answers is scored against a shifted alignment."
    )


def test_a_deferred_slot_with_no_set_is_reported_and_is_not_a_failure() -> None:
    """SPEC §9.3's threat floor today: a slot held open, named on every run, graded by nobody.

    E2-12's scope: "the threat/self-harm floor's *slot* exists in the structure
    with no set and no number — setting it is E10's". So a deferred slot must not
    fail the run, and it must not disappear from the report either. A floor
    nobody can see is not deferred, it is missing, and the next person to look
    for SPEC §9.3's strictest gate finds nothing where it should be.

    **The mutation this kills:** treat a task with no cases as a task that
    passed, which grades nothing and prints a green line. **The near miss that
    must stay green:** the same slot once E10 gives it a set *and* a number,
    which is graded like any other task.
    """
    floors = declarations().deferred(note="E10 sets this — SPEC §9.3's strictest floor.")
    task = build_task(name="threat", floors=floors, cases=())

    report = runner().evaluate([task], classifiers={}, environ=keyed())

    assert report.passed, f"a deferred slot failed the run:\n{report.text()}"
    assert not report.tasks[0].graded, (
        "a task with no set was reported as graded, so the run produced a measurement over "
        "nothing"
    )
    assert "threat" in report.text() and "ungraded" in report.text(), (
        "the deferred slot is not named in the report as ungraded. A gate whose absence is "
        f"invisible is one nobody notices is absent. The report said:\n{report.text()}"
    )


def test_a_deferred_slot_that_has_acquired_a_set_is_refused() -> None:
    """The other direction: E10 ships the set and forgets the number.

    A set with a deferred floor is a task that gets measured against nothing and
    printed as ungraded, forever, with the run green. It is the exact failure the
    deferred state exists to avoid, arriving by the one route the deferred state
    creates.

    **The mutation this kills:** let `DEFERRED` mean "never look at this entry
    again", which is the obvious reading and is right until the day it is wrong.
    """
    floors = declarations().deferred(note="E10 sets this.")
    task = build_task(
        name="threat",
        floors=floors,
        cases=balanced_set(),
        positive=validity_cases().SUBSTANTIVE,
    )

    with pytest.raises(declarations().EvalRefusalError) as refusal:
        runner().evaluate([task], classifiers={}, environ=keyed())

    assert "deferred" in str(
        refusal.value
    ), f"refused, but not about the deferred floor:\n{refusal.value}"


def test_a_deferred_slot_that_has_acquired_a_number_is_refused() -> None:
    """And the other half of the same trap: a number written into a held-open slot.

    `deferred()` cannot produce this, so the case is built by constructing
    `TaskFloors` directly — which is what a later edit adding "just the recall
    floor for now" would amount to. A number with no set is a floor that reports
    on every run and is compared to nothing, and on this particular slot it is
    SPEC §9.3's strictest gate wearing a value.

    **The mutation this kills:** check the state and never the numbers.
    """
    module = declarations()
    floors = module.TaskFloors(
        status=module.FloorStatus.DEFERRED,
        precision=None,
        recall=0.98,
        note="E10 sets this.",
    )
    task = build_task(name="threat", floors=floors, cases=())

    with pytest.raises(module.EvalRefusalError) as refusal:
        runner().evaluate([task], classifiers={}, environ=keyed())

    assert "0.98" in str(
        refusal.value
    ), f"refused, and did not name the number that should not be there:\n{refusal.value}"


def test_the_placeholder_floor_is_refused_rather_than_run_against_nothing() -> None:
    """A set with no measured floor is a number nobody compares.

    This is the state the comment-validity floor ships in: the cases exist and the
    numbers are picked against the first real run. The tempting behaviour is to
    grade the set and print the figures without a comparison, which reads as
    useful output and exits 0 — a run that measured something and enforced
    nothing, on the gate SPEC §9.3 exists to be.

    **The mutation this kills:** treat `None` floors as "no floor to breach", so
    `measurement.precision < None` is never evaluated and the task passes.
    **The near miss that must stay green:** the same set once the numbers are
    written in, asserted immediately below.
    """
    floors = declarations().awaiting_measurement(note="picked against the first real run")
    stub = three_quarters_stub()
    task = build_task(floors=floors, cases=balanced_set(), positive=validity_cases().SUBSTANTIVE)

    with pytest.raises(declarations().EvalRefusalError) as refusal:
        runner().evaluate([task], classifiers={"probe": stub}, environ=keyed())

    assert "placeholder" in str(
        refusal.value
    ), f"refused, and not about the unfilled placeholder:\n{refusal.value}"
    assert stub.asked == [], (
        "the classifier was called before the runner noticed it had no floor to compare "
        "against. A refusal that spends provider calls first is a refusal that already "
        "cost money and already sent every comment in the set off this machine."
    )


def test_a_filled_in_floor_over_the_same_set_is_graded() -> None:
    """The near miss for the placeholder: writing the numbers in is all it takes.

    Same set, same stub, same everything except that the floor now carries
    numbers. If this fails while the test above passes, the runner refuses every
    floor rather than the unfilled one, and E2-12's own deliverable can never go
    green.
    """
    floors = declarations().enforced(precision=0.7, recall=0.7, note="measured on a probe run")
    stub = three_quarters_stub()
    task = build_task(floors=floors, cases=balanced_set(), positive=validity_cases().SUBSTANTIVE)

    report = runner().evaluate([task], classifiers={"probe": stub}, environ=keyed())

    assert (
        report.passed and report.tasks[0].graded
    ), f"a filled-in floor over a set that clears it did not pass:\n{report.text()}"


def test_a_missing_provider_credential_is_refused_and_the_variable_is_named() -> None:
    """E2-12: "a red gate naming what is missing, not a quiet pass".

    This ticket's own sequencing depends on it. The pull request that lands the
    eval steps touches `tests/evals/`, so its own eval steps fire; without the
    repository secret they must go red, and red does not merge. A runner that
    skipped when it found no key would make that pull request green over a gate
    that never ran, and the proof the wiring works would be a run that proved
    nothing.

    `docs/MISTAKES.md` entry 34's cousin: a gate that cannot do its work
    reporting a line that reads as success.

    **The mutation this kills:** `if not key: return Report(())`, or a `sys.exit(0)`
    with a notice. **The near miss that must stay green:** the same run with a
    key set, asserted below, so a runner that refused unconditionally is caught.
    """
    floors = declarations().enforced(precision=0.5, recall=0.5, note="a probe's floor")
    stub = three_quarters_stub()
    task = build_task(floors=floors, cases=balanced_set(), positive=validity_cases().SUBSTANTIVE)

    with pytest.raises(declarations().EvalRefusalError) as refusal:
        runner().evaluate([task], classifiers={"probe": stub}, environ={})

    assert PROVIDER_KEY_VARIABLE in str(refusal.value), (
        "the runner refused without naming the variable an operator has to set. The whole "
        "value of this refusal over a skip is that the log says what is missing. It said:\n"
        f"{refusal.value}"
    )


def test_a_blank_provider_credential_is_refused_exactly_as_a_missing_one_is() -> None:
    """The near miss that distinguishes the check from `if key is None`.

    `.env.example` ships `AI_PROVIDER_API_KEY=` blank on purpose — the mock and a
    local model server authenticate nobody — so the blank value is the *ordinary*
    state of this variable in every development checkout and in CI's e2e job,
    which copies that file verbatim. A presence check passes over it, and the
    live run then goes to a real provider with an empty bearer token.

    Whitespace is included for the same reason: a secret pasted with a trailing
    newline into a repository secret is a value that is present and is not a
    credential.

    **The mutation this kills:** `if PROVIDER_KEY_VARIABLE not in environ`.
    """
    floors = declarations().enforced(precision=0.5, recall=0.5, note="a probe's floor")
    task = build_task(floors=floors, cases=balanced_set(), positive=validity_cases().SUBSTANTIVE)

    for blank in ("", "   ", "\n"):
        with pytest.raises(declarations().EvalRefusalError) as refusal:
            runner().evaluate(
                [task],
                classifiers={"probe": three_quarters_stub()},
                environ={PROVIDER_KEY_VARIABLE: blank},
            )
        assert PROVIDER_KEY_VARIABLE in str(
            refusal.value
        ), f"a key of {blank!r} was refused without naming the variable:\n{refusal.value}"


def test_the_provider_is_not_reached_when_the_credential_is_missing() -> None:
    """The refusal happens before anything is asked, and that is not incidental.

    A refusal raised after the set has been classified has already spent the
    provider calls it was meant to prevent, and — more to the point — has already
    sent every comment in the set to a third party before deciding it should not
    have. Nothing in the returned refusal distinguishes the two orders, so it is
    asserted from the stub's side.

    **The mutation this kills:** check the credential inside the per-case loop,
    or after building the report.
    """
    floors = declarations().enforced(precision=0.5, recall=0.5, note="a probe's floor")
    stub = three_quarters_stub()
    task = build_task(floors=floors, cases=balanced_set(), positive=validity_cases().SUBSTANTIVE)

    with pytest.raises(declarations().EvalRefusalError):
        runner().evaluate([task], classifiers={"probe": stub}, environ={})

    assert stub.asked == [], (
        f"the classifier was asked {len(stub.asked)} times before the runner refused for "
        "want of a credential."
    )


def test_a_measurement_below_the_floor_fails() -> None:
    """SPEC §9.3's gate, in the direction that has to work.

    The stub scores 0.75 on both rates. Against a floor of 0.80 the run must
    fail, and the report must say which rate breached rather than only that
    something did — a log line that says "fail" and nothing else is a gate nobody
    can act on.

    **The mutation this kills:** compare with `<=` reversed, compare against the
    wrong rate, or accumulate breaches into a variable nothing reads.
    """
    floors = declarations().enforced(precision=0.80, recall=0.80, note="a probe's floor")
    task = build_task(floors=floors, cases=balanced_set(), positive=validity_cases().SUBSTANTIVE)

    report = runner().evaluate(
        [task], classifiers={"probe": three_quarters_stub()}, environ=keyed()
    )

    assert (
        not report.passed
    ), f"0.75 precision and 0.75 recall cleared a 0.80/0.80 floor:\n{report.text()}"
    assert report.tasks[0].breaches, "the run failed and the task recorded no breach"


def test_a_measurement_exactly_at_the_floor_passes() -> None:
    """The boundary, from below: "meet" the floor means reaching it, not beating it.

    The pair with the test above. 0.75 against a floor of 0.75 must pass, and
    0.75 against 0.80 must fail; one comparison operator separates them, and a
    strict `>` would make every floor secretly one epsilon higher than it is
    written — which nobody would notice until a run scored exactly the declared
    number and went red for no stated reason.

    The eight-case set is chosen so that three right answers out of four is
    exactly 0.75 in binary floating point, so this is a real equality rather than
    an approximate one.

    **The mutation this kills:** `measurement.precision <= floor` in the breach
    test, or a `>` in place of `>=` wherever the comparison is spelled.
    """
    floors = declarations().enforced(precision=0.75, recall=0.75, note="a probe's floor")
    task = build_task(floors=floors, cases=balanced_set(), positive=validity_cases().SUBSTANTIVE)

    report = runner().evaluate(
        [task], classifiers={"probe": three_quarters_stub()}, environ=keyed()
    )

    assert report.passed, (
        "a run scoring exactly the declared floor was reported as a breach. §9.3's wording "
        f"is 'must meet per-task precision/recall floors'.\n{report.text()}"
    )


def test_a_precision_breach_fails_even_when_recall_clears() -> None:
    """Each rate is its own gate. Precision, with recall well clear.

    Half a floor is not a floor, and a runner that checked one rate would pass
    every set where the other happened to be high. On the validity task the two
    rates guard opposite errors — a precision breach is participation credit
    awarded for "it was okay", a recall breach is credit withheld from a student
    who wrote something real — so collapsing them into one number loses the
    distinction the gate is for.

    **The mutation this kills:** check precision and forget recall, or `and` the
    two comparisons where `or` was meant.
    """
    floors = declarations().enforced(precision=0.90, recall=0.10, note="a probe's floor")
    task = build_task(floors=floors, cases=balanced_set(), positive=validity_cases().SUBSTANTIVE)

    report = runner().evaluate(
        [task], classifiers={"probe": three_quarters_stub()}, environ=keyed()
    )

    assert not report.passed, f"a precision breach passed because recall cleared:\n{report.text()}"
    assert any(
        "precision" in breach for breach in report.tasks[0].breaches
    ), f"the breach recorded was not about precision: {report.tasks[0].breaches}"


def test_a_recall_breach_fails_even_when_precision_clears() -> None:
    """And the other rate, with precision well clear.

    The pair with the test above. SPEC §9.3 makes recall the rate that matters
    most on the task this structure is built to hold next — "threat/self-harm
    recall floor is the strictest in the suite (false negatives are the expensive
    error)" — so a runner that enforced precision alone would be enforcing the
    cheaper half of the gate everywhere it matters.

    **The mutation this kills:** check recall and forget precision.
    """
    floors = declarations().enforced(precision=0.10, recall=0.90, note="a probe's floor")
    task = build_task(floors=floors, cases=balanced_set(), positive=validity_cases().SUBSTANTIVE)

    report = runner().evaluate(
        [task], classifiers={"probe": three_quarters_stub()}, environ=keyed()
    )

    assert not report.passed, f"a recall breach passed because precision cleared:\n{report.text()}"
    assert any(
        "recall" in breach for breach in report.tasks[0].breaches
    ), f"the breach recorded was not about recall: {report.tasks[0].breaches}"


def test_a_classifier_that_never_answers_the_positive_class_scores_zero_precision() -> None:
    """The empty denominator, resolved toward failing.

    A model answering `insufficient` to every comment makes no positive claims at
    all, so the share of its positive claims that were right is undefined.
    Treating that as 1.0 is the mathematically tidy choice and it lets a
    classifier which never awards participation credit clear a precision floor of
    any height — a gate that a broken provider passes.

    **The mutation this kills:** `return 1.0` for a zero denominator, which is
    what several metric libraries do by default. **The near miss that must stay
    green:** a classifier that gets some positives right, asserted throughout the
    rest of this module.
    """
    cases_module = validity_cases()
    stub = Stub({case.comment: cases_module.INSUFFICIENT for case in balanced_set()}, "validity.v1")
    floors = declarations().enforced(precision=0.10, recall=0.10, note="a probe's floor")
    task = build_task(floors=floors, cases=balanced_set(), positive=cases_module.SUBSTANTIVE)

    report = runner().evaluate([task], classifiers={"probe": stub}, environ=keyed())

    assert not report.passed, (
        "a classifier that never answered the positive class cleared a precision floor:\n"
        f"{report.text()}"
    )


def test_a_set_with_no_case_of_the_positive_class_is_refused() -> None:
    """Recall over a set with no positives is a figure about nothing.

    It is also how a floor gets quietly lowered without the number moving:
    `.claude/review-fixtures/eval-floor-lowered.diff` plants exactly this
    disguise — "three cases are removed from the threat set — a narrowed set
    clears the same floor more easily, which is a lowered floor wearing a
    costume". The end point of that narrowing is a set with no positive case at
    all, and it must be a refusal rather than a perfect score.

    **The mutation this kills:** compute recall as `0/0 → 1.0` and grade the set.
    **The near miss that must stay green:** any set holding at least one positive
    case, which is every other set in this module.
    """
    cases_module = validity_cases()
    negatives = tuple(
        build_case(f"n-{index}", f"insufficient {index}", cases_module.INSUFFICIENT, "validity.v1")
        for index in range(4)
    )
    floors = declarations().enforced(precision=0.5, recall=0.5, note="a probe's floor")
    task = build_task(floors=floors, cases=negatives, positive=cases_module.SUBSTANTIVE)

    with pytest.raises(declarations().EvalRefusalError) as refusal:
        runner().evaluate([task], classifiers={}, environ=keyed())

    assert "recall" in str(
        refusal.value
    ), f"refused, and not about the unmeasurable recall:\n{refusal.value}"


def test_an_answer_produced_under_a_different_prompt_version_is_refused() -> None:
    """A number measured against `validity.v2` is not a number about `validity.v1`.

    ADR 0032 makes a committed prompt file immutable and a prompt change an
    *added* file, so the version a case is pinned to names exactly one text. A run
    whose answers come back under a later version has measured a different
    program, and comparing that figure against a floor grown on the old one is
    the comparison SPEC §9.3's gate is trying to make impossible.

    The quiet version of this failure is the expensive one: the numbers still
    land in the floor's range, the gate goes green, and the prompt change it was
    supposed to judge was never judged.

    **The mutation this kills:** read the verdict and ignore the audit pair ADR
    0031 requires every contract to carry. **The near miss that must stay
    green:** an answer under the pinned version, asserted below.
    """
    cases_module = validity_cases()
    stub = Stub({case.comment: cases_module.SUBSTANTIVE for case in balanced_set()}, "validity.v2")
    floors = declarations().enforced(precision=0.1, recall=0.1, note="a probe's floor")
    task = build_task(floors=floors, cases=balanced_set(), positive=cases_module.SUBSTANTIVE)

    with pytest.raises(declarations().EvalRefusalError) as refusal:
        runner().evaluate([task], classifiers={"probe": stub}, environ=keyed())

    message = str(refusal.value)
    assert (
        "validity.v1" in message and "validity.v2" in message
    ), f"refused without naming both versions, so the log cannot say what drifted:\n{message}"


def test_an_answer_produced_under_the_pinned_prompt_version_is_graded() -> None:
    """The near miss for the test above: the ordinary case must not refuse.

    Without it, a runner comparing against the wrong constant — or against a
    version string it made up — would refuse every real run while passing the
    drift test perfectly.
    """
    floors = declarations().enforced(precision=0.1, recall=0.1, note="a probe's floor")
    task = build_task(floors=floors, cases=balanced_set(), positive=validity_cases().SUBSTANTIVE)

    report = runner().evaluate(
        [task], classifiers={"probe": three_quarters_stub()}, environ=keyed()
    )

    assert report.tasks[
        0
    ].graded, f"a run under the pinned prompt version was not graded:\n{report.text()}"


def test_the_shipped_registry_holds_the_validity_set_and_the_deferred_threat_slot() -> None:
    """The structure E2-12 ships, asserted over the real registry rather than a probe.

    Every other test here builds its own tasks, which is what makes them
    independent of the numbers that land later — and it also means all of them
    pass over a registry that is empty. This is the floor under them: the
    comment-validity task is registered with a non-empty set, and SPEC §9.3's
    threat and self-harm slot is registered with none.

    **The mutation this kills:** ship the machinery and register nothing, which
    leaves `python -m tests.evals.runner` exiting 0 having walked an empty tuple
    — `docs/MISTAKES.md` entry 3 in its purest form, a gate satisfied by
    emptiness. **The near miss that must stay green:** E4, E6 or E10 adding a
    third and fourth entry, since nothing here asserts the registry holds only
    two.
    """
    registry = eval_module("tests.evals.registry")
    states = declarations().FloorStatus
    by_name = {task.name: task for task in registry.TASKS}

    assert "validity" in by_name, (
        f"the registry holds {sorted(by_name)} and no comment-validity task. SPEC §11 open "
        "question 4 asks for that set before E2 exits."
    )
    assert by_name["validity"].cases, "the comment-validity task is registered with no cases"

    threat = next((task for task in registry.TASKS if task.floors.status is states.DEFERRED), None)
    assert threat is not None, (
        f"no task in the registry holds a deferred floor; it holds "
        f"{[(task.name, task.floors.status.value) for task in registry.TASKS]}. E2-12's "
        "scope: the threat/self-harm floor's slot exists in the structure with no set and "
        "no number, and SPEC §9.3 makes that the strictest floor in the suite."
    )
    assert not threat.cases, (
        f"the deferred slot `{threat.name}` carries {len(threat.cases)} cases. Setting that "
        "floor is E10's."
    )


def test_the_report_says_what_the_run_cost_with_the_cached_share_kept_separate() -> None:
    """Dispute E2-12-06's addition: the run reports its own usage, and does not overstate it.

    `tests/evals/README.md` states what an eval run costs. Until the gateway
    handed the usage back, that was an estimate; the whole point of summing it here
    is that the number in the log is the run's own.

    **The cache read must be reported as a share of the input and never added to
    it.** `cache_read_tokens` counts tokens that are part of `input_tokens` and
    were served from the provider's cache, so a total that adds them overstates
    every run by the cheapest thing in it — and the overstatement is invisible,
    because the figure still looks like a plausible token count. The stub's numbers
    are chosen so the two readings differ: eight cases at 100 input and 40 cached
    is 800, and the wrong reading is 1120.

    **And the retry caveat is asserted as text**, because it is the sentence that
    stops somebody reconciling this against an invoice and concluding the invoice
    is wrong. A call the gateway retried reports the usage of the request that
    answered, so these figures are a floor rather than a complete account.

    **The mutation this kills:** `input_tokens + cache_read_tokens` in the total,
    and dropping the caveat line so the figures read as complete. **The near miss
    that must stay green:** any wording of the line — this asserts the numbers and
    that the caveat is present, not how either is phrased.
    """
    floors = declarations().enforced(precision=0.5, recall=0.5, note="a probe's floor")
    cases = balanced_set()
    task = build_task(floors=floors, cases=cases, positive=validity_cases().SUBSTANTIVE)

    report = runner().evaluate(
        [task], classifiers={"probe": three_quarters_stub()}, environ=keyed()
    )

    spent = report.tasks[0].usage
    per_call = StubUsage()
    assert spent.calls == len(cases), (
        f"the run answered {len(cases)} cases and counted {spent.calls}. A total over fewer "
        "calls than the set holds is a cost report about a different run."
    )
    assert spent.input_tokens == per_call.input_tokens * len(cases), (
        f"input tokens summed to {spent.input_tokens} and the stub reported "
        f"{per_call.input_tokens} on each of {len(cases)} calls. If it came to "
        f"{(per_call.input_tokens + per_call.cache_read_tokens) * len(cases)}, the cache read "
        "was added to the input rather than counted inside it."
    )
    assert spent.cache_read_tokens == per_call.cache_read_tokens * len(cases), (
        f"cache reads summed to {spent.cache_read_tokens}; the stub reported "
        f"{per_call.cache_read_tokens} per call."
    )

    text = report.text()
    assert (
        str(spent.input_tokens) in text and str(spent.output_tokens) in text
    ), f"the report does not print the token totals it accumulated:\n{text}"
    assert str(spent.cache_read_tokens) in text, (
        "the report does not print the cached share separately. A run whose input was mostly "
        f"served from cache costs a fraction of one that was not, and the log cannot say "
        f"which this was:\n{text}"
    )
    assert "retried" in text and "floor" in text, (
        "the report does not say that a retried call contributes only the request that "
        "answered. Without that sentence the figures read as a complete account of what the "
        f"run cost, and the first retry makes that false:\n{text}"
    )


def test_a_task_that_was_not_graded_prints_no_cost() -> None:
    """The pair for the above: a deferred slot spent nothing, so it reports nothing.

    A cost line under a task the runner never ran is a number about no calls, and
    zero is the most misleading of the plausible values — it reads as "this ran and
    was free" rather than "this did not run".

    **The mutation this kills:** printing the usage block unconditionally, which
    puts `0 input tokens` under SPEC §9.3's threat slot on every run.
    """
    floors = declarations().deferred(note="E10 sets this.")
    task = build_task(name="threat", floors=floors, cases=())

    report = runner().evaluate([task], classifiers={}, environ=keyed())

    assert (
        "input tokens" not in report.text()
    ), f"a task the runner never ran carries a cost line:\n{report.text()}"


def test_enforcement_does_not_depend_on_the_command_line_flag() -> None:
    """`--enforce-floors` is accepted and is not the switch that turns the gate on.

    A gate whose enforcement rides on a flag is a gate a shortened Makefile
    recipe, a copied command line or a tired edit can switch off while the step
    still looks like it ran. `.github/workflows/ci.yml` runs the documented
    invocation, so the flag has to be accepted; what it must not be is
    load-bearing.

    Asserted two ways: the parser takes the flag and takes its absence, and
    `evaluate` — the function that does the comparing — has no parameter that
    could turn the comparison off.

    **The mutation this kills:** `if args.enforce_floors:` around the comparison,
    which is the obvious implementation of the flag's own name and leaves
    `python -m tests.evals.runner` exiting 0 over an unenforced set.
    """
    module = runner()
    parser = module.build_parser()

    parser.parse_args([])
    parser.parse_args(["--enforce-floors"])

    parameters = inspect.signature(module.evaluate).parameters
    switches = [name for name in parameters if "enforce" in name.lower()]
    assert not switches, (
        f"`evaluate` takes {switches}, so the comparison can be turned off by a caller. "
        "The flag is accepted at the command line for the documented invocation; "
        "enforcement is unconditional, because the alternative is a gate a command-line "
        "edit disables silently."
    )
