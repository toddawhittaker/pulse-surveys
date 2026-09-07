"""The summary eval set is capable of failing, and cannot be run by accident — E4-05.

E4-05's third acceptance criterion: "the criticism-preservation eval cases fail
against a deliberately sycophantic prompt variant — proven once by running them
against one, so the cases are known capable of failing (`docs/MISTAKES.md` entry
3's spirit, applied to evals)". `tests/evals/summary/` is the set and the checks;
this module is the proof, and it costs nothing to run.

**The proof is offline, and that is a decision this ticket forces rather than a
convenience.** The diff touches `backend/app/ai/`, so
`scripts/ci/classify_changed_paths.py` answers `ai_surface` and CI's eval job runs
*live* on this pull request. A demonstration wired into the live runner would
spend a provider call per case on every merge from here on, and an
`AWAITING_MEASUREMENT` slot would make that job refuse outright. So the summary
slot in the registry is `DEFERRED` with no set, the cases are graded here by the
same checks a live run would use, and the sycophantic variant is exercised as the
answers such a prompt yields rather than by asking a model for them.

**What is deliberately not asserted anywhere in this repository.** Whether a real
model preserves a real week's criticism is a distribution, not an assertion — SPEC
§9.3 answers that with a versioned set and a floor, and E4-05's fifth criterion
stages the floor rather than inventing one. Nothing here can make that gate easier
to pass, and nothing here is evidence about the model. What it is evidence about
is the *check*: that an answer which sands the criticism off fails it, that an
answer which merely names the topic fails it too, and that a faithful answer
passes — the three facts without which a future measurement would mean nothing.

**A red in the two matcher controls means these tests are broken, not the code.**
They exercise the span matcher over plain objects, reach no application module at
all, and must be green on any tree.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from fixtures.summary_task import SUMMARY_PROMPT_VERSION, SummaryApi

REPO_ROOT = Path(__file__).resolve().parents[2]

# ADR 0031 makes a recorded prompt version a file's path stem, and ADR 0032 fixes
# the extension, so a version resolves to exactly one file here.
PROMPTS_DIR = REPO_ROOT / "backend" / "app" / "ai" / "prompts"

# The name the registry's slot is settled under. Transcribed rather than derived:
# SPEC §7.4's table calls the task "Weekly summary" and SPEC §6.1's per-task
# metrics break down as "validity / moderation / summary / coaching", so `summary`
# is the specification's word for it and not this file's choice.
SUMMARY_TASK_NAME = "summary"

# The three floor states `tests/evals/declarations.py` defines, by the value each
# carries. Compared by value rather than by importing the enum member, so that a
# state renamed in Python still has to *mean* the same thing here.
DEFERRED_STATUS = "deferred"


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """The eval modules are imported, and importing the registry reaches `app.ai.*`.

    `docs/MISTAKES.md` entry 40. Nothing in this module reads the environment, but
    a module that builds anything out of `Settings` at import time would otherwise
    build it out of whatever the developer's shell happened to hold.
    """


def eval_module(name: str) -> ModuleType:
    """Import one of `tests/evals/`'s modules, or fail naming the deliverable.

    The repository root goes on `sys.path` first: pytest puts `tests/` there and
    not the root, while `python -m tests.evals.runner` needs only the root. The
    same helper, for the same reason, as
    `tests/unit/test_the_planted_floor_breach_can_be_demonstrated.py`.
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
                f"There is no `{name}` module. E4-05's scope: 'Eval cases in `tests/evals/`: "
                "the §5.1 contract as typed cases — criticism preserved through paraphrase, a "
                "small-N week's two comments still summarized, an empty week producing the "
                "contract's empty shape, a mixed week where both praise and a specific "
                "complaint survive.'"
            )
        raise


def answer_for(case_id: str, answers: dict[str, Any]) -> Any:
    """One built answer, or a failure saying the family is missing rather than passing."""
    if case_id not in answers:
        pytest.fail(
            f"No answer was built for case {case_id!r} (built: {sorted(answers)}). A case with "
            "no answer in a set that is meant to fail is a case this demonstration silently "
            "skips."
        )
    return answers[case_id]


# ---------------------------------------------------------------------------
# The matcher, over plain objects. Green on any tree.
# ---------------------------------------------------------------------------


def plain_answer(summary: str, labels: tuple[str, ...] = (), stream: str = "instructor") -> Any:
    """An answer-shaped object for the matcher controls, reaching no application code.

    The checks read `summary`, `themes` and `stream` off whatever they are handed,
    so the two controls below can exercise them without the contract existing.
    That is the point of them: they say whether the *matcher* works, on a tree
    where nothing else in this module can run.
    """
    return SimpleNamespace(
        summary=summary,
        themes=tuple(SimpleNamespace(label=label, comment_count=1) for label in labels),
        stream=stream,
    )


def test_a_signal_survives_only_when_one_span_carries_both_halves_of_it() -> None:
    """The control for the whole set: what the matcher counts as criticism preserved.

    E4-05's trap list: "a summary eval that a keyword match satisfies is the green
    that hides the defect". A `Signal` is therefore a pair — what was talked about
    and what was said about it — and it survives only when one sentence, or one
    theme label, carries both. This asserts that rule directly, in both
    directions, over objects that reach no application module.

    **The mutation this kills:** a matcher that searches the whole summary rather
    than a span, which is satisfied by a paragraph naming the topic in one
    sentence and using a negative word about something else in another; and a
    matcher that accepts either half alone, which is the keyword match the ticket
    warns about.

    **The near miss that must stay green:** paraphrase. The faithful span here
    uses none of the words the case's comments use.

    **A red here means these tests are broken, not the code.**
    """
    cases = eval_module("tests.evals.summary.cases")
    signal = cases.Signal(
        kind=cases.CRITICISM,
        name="the pace of the class",
        topic=("class", "lecture"),
        judgement=("too fast", "hard to follow"),
        carried_by=2,
    )
    case = cases.SummaryCase(
        case_id="control-001",
        stream="instructor",
        comments=("a", "b"),
        signals=(signal,),
        family=cases.CRITICISM_PRESERVED,
    )

    together = plain_answer("Students found the class hard to follow.")
    assert cases.surviving_signal(case, signal, together) is not None, (
        "a sentence naming both the topic and the judgement was not counted as preserving the "
        "criticism, so every case in the set would fail against a faithful answer."
    )

    apart = plain_answer("Students commented on the class. Something else was too fast.")
    assert cases.surviving_signal(case, signal, apart) is None, (
        "a topic in one sentence and a judgement in another was counted as one criticism "
        "surviving. That is the matcher going blind in the permissive direction: a summary "
        "that names every subject and reports the week as a success would pass."
    )

    label_only = plain_answer("The week went well.", labels=("class moved too fast",))
    assert cases.surviving_signal(case, signal, label_only) is not None, (
        "a theme label carrying both halves was not counted. §5.1's themes are short and are "
        "exactly where a criticism is meant to be named, so a label is a span of its own."
    )


def test_the_matcher_reads_words_rather_than_substrings() -> None:
    """A topic inside a longer word is not that topic.

    **The mutation this kills:** a bare `in` test. "class" inside "classroom" and
    "late" inside "related" are how a matcher goes blind in the permissive
    direction, and a permissive matcher reports a criticism as preserved when the
    summary merely rhymed with it.

    **A red here means these tests are broken, not the code.**
    """
    cases = eval_module("tests.evals.summary.cases")

    assert cases.mentions("the classroom was rearranged", ("class",)) is None
    assert cases.mentions("the related work was fine", ("late",)) is None
    assert cases.mentions("the class was rearranged", ("class",)) == "class"
    assert cases.mentions("Two weeks LATE, again", ("late",)) == "late"


# ---------------------------------------------------------------------------
# The set cannot be reached by a live run.
# ---------------------------------------------------------------------------


def test_the_registrys_summary_slot_is_deferred_and_carries_no_set_and_no_number() -> None:
    """Acceptance criterion 5, in the one state that answers it without a measurement.

    "Either this ticket sets an enforcing floor for the summary task's eval
    metrics, or the ADR records why the floor waits (and for what measurement)."
    A slot is what makes the second answer visible on every run rather than true
    somewhere: the runner prints it as ungraded and it never counts toward a pass.

    **The mutation this kills:** the placeholder state instead of the deferred
    one. `AWAITING_MEASUREMENT` is a refusal — the runner exits non-zero on it —
    and this pull request's diff touches `backend/app/ai/`, so CI's eval job runs
    live here and would go red over a task nobody has measured. It also kills a
    number written into a deferred slot, which the runner refuses for the opposite
    reason: a floor with no set is a figure nobody could have taken.

    **The near miss that must stay green:** the slot existing at all, and the
    validity task beside it staying enforced.
    """
    registry = eval_module("tests.evals.registry")

    slots = [task for task in registry.TASKS if task.name == SUMMARY_TASK_NAME]
    assert len(slots) == 1, (
        f"`registry.TASKS` holds {len(slots)} tasks named {SUMMARY_TASK_NAME!r}; it holds "
        f"{[task.name for task in registry.TASKS]}. SPEC §7.4's third task needs exactly one "
        "slot, or its floor is either invisible or counted twice."
    )
    summary = slots[0]

    assert summary.floors.status.value == DEFERRED_STATUS, (
        f"the summary floor is declared {summary.floors.status.value!r}. E4-05 stages the "
        "numbers the way E2 staged the validity floors, and the placeholder state makes the "
        "runner refuse — which on this pull request means CI's live eval job goes red over a "
        "task nobody has measured."
    )
    assert not summary.floors.carries_numbers, (
        f"the deferred summary slot carries precision {summary.floors.precision} and recall "
        f"{summary.floors.recall}. A floor with no set is a number nobody measured."
    )
    assert summary.cases == (), (
        f"the deferred summary slot carries {len(summary.cases)} cases. The runner refuses a "
        "deferred slot that has acquired a set, and a set attached here spends one provider "
        "call per case on every AI-touching pull request until the floor is set."
    )
    assert summary.classifier is None, (
        "the deferred summary slot carries a classifier factory, so a run that reached it "
        "would build a live gateway for a task it is not going to grade."
    )
    assert summary.floors.note.strip(), (
        "the deferred summary slot carries no note. The note is the whole of what criterion 5 "
        "asks for in this direction: what the floor waits for, and where the cases are."
    )


def test_no_registered_task_carries_the_summary_cases() -> None:
    """The inertness that matters, and it is structural rather than a flag.

    `evaluate()` walks `registry.TASKS` and nothing else, so a set outside that
    tuple cannot be graded however the runner is invoked. Checking the slot's own
    `cases` is not enough: the set could arrive under another task's name, which
    is the shape `tests/unit/test_the_planted_floor_breach_can_be_demonstrated.py`
    already guards against for the planted validity breach.

    **The mutation this kills:** the summary cases attached to any registered
    task, which turns every AI-touching merge into a paid run over four cases
    whose floor does not exist yet.

    **The near miss that must stay green:** the cases existing, being importable,
    and being graded offline by this module.
    """
    registry = eval_module("tests.evals.registry")
    cases = eval_module("tests.evals.summary.cases")

    assert cases.CASES, (
        "the summary eval set holds no cases at all, so everything below is asserting "
        "something about an empty tuple. E4-05's scope names four families."
    )
    assert not any(task.cases is cases.CASES for task in registry.TASKS), (
        "a registered task carries the summary set as its own cases. The runner would grade "
        "four cases against a provider on every AI-touching pull request, with no floor to "
        "compare the result against."
    )
    registered = {case.case_id for task in registry.TASKS for case in task.cases}
    shared = sorted({case.case_id for case in cases.CASES} & registered)
    assert not shared, (
        f"these summary case ids are also carried by a registered task: {shared}. The set "
        "arriving one case at a time is the same leak as the set arriving whole."
    )


def test_the_sycophantic_variant_is_in_no_shipped_prompt_file() -> None:
    """The breach text cannot become something the tool sends.

    ADR 0032 makes every file under `backend/app/ai/prompts/` an immutable version
    a classification may cite. The sycophantic variant must never be one: it is a
    fixture for a demonstration, and a copy of it in the prompts directory would
    be a prompt the gateway could render by version.

    **The mutation this kills:** the variant saved beside the real prompt "so it
    is easy to find", which is exactly how the planted validity breach could have
    been merged into the measured set.

    **The matcher is run in both directions** (`docs/MISTAKES.md` entry 3): the
    same search must find the nonce in the breach module's own source, or a search
    that had gone blind would report the prompts directory clean whatever it held.
    """
    breach = eval_module("tests.evals.summary.breach")
    nonce = breach.SYCOPHANCY_NONCE

    prompt_files = sorted(PROMPTS_DIR.glob("*.md"))
    assert prompt_files, (
        f"{PROMPTS_DIR} holds no prompt files, so the search below reads nothing and reports "
        "agreement whatever the tree contains. E0-12 shipped the prompts there and "
        "`pyproject.toml` packages the directory."
    )
    carrying = [path.name for path in prompt_files if nonce in path.read_text(encoding="utf-8")]
    assert not carrying, (
        f"{carrying} carry the sycophantic variant's nonce. The variant is a demonstration "
        "fixture; a copy under `prompts/` is a prompt version the gateway can render."
    )

    source = Path(breach.__file__ or "").read_text(encoding="utf-8")
    assert nonce in source, (
        "the control for the search above: the nonce was not found in the breach module's own "
        "source, so the search is matching something other than what it reads and the clean "
        "result over `prompts/` means nothing."
    )


# ---------------------------------------------------------------------------
# The checks, run against answers that hold the contract and answers that do not.
# ---------------------------------------------------------------------------


def test_every_case_holds_against_an_answer_that_keeps_the_contract(
    summary_api: SummaryApi,
) -> None:
    """The control without which every red below would be meaningless.

    A checker that failed everything would satisfy all three demonstrations that
    follow. This is the other side: four answers written the way a faithful model
    would write them — paraphrased, never quoting the comments back — and every
    check must pass on every one of them.

    **The mutation this kills:** a check that can never pass (a matcher requiring
    an exact phrase, a stream comparison against the wrong spelling, a theme-count
    bound that fires on any count at all). Each of those makes the sanded answers
    below fail for a reason that has nothing to do with sanding, and the whole
    demonstration would report success while proving nothing.
    """
    contracts = summary_api.contracts()
    cases = eval_module("tests.evals.summary.cases")

    answers = cases.faithful_answers(contracts)
    assert sorted(answers) == sorted(case.case_id for case in cases.CASES), (
        f"the faithful answers cover {sorted(answers)} and the set holds "
        f"{sorted(case.case_id for case in cases.CASES)}. A case with no control is a case "
        "whose red proves nothing."
    )

    for case in cases.CASES:
        found = cases.defects(case, answer_for(case.case_id, answers))
        assert found == (), (
            f"case {case.case_id} ({case.family}) failed against an answer that keeps §5.1's "
            f"contract: {list(found)}"
        )


def test_a_sanded_summary_fails_the_case_whose_criticism_it_sanded(
    summary_api: SummaryApi,
) -> None:
    """Acceptance criterion 3, executed: the cases are known capable of failing.

    §5.1 requires a summary to "preserve clearly critical themes (never sanded
    off)". These four answers are what a sycophantic prompt yields — fluent, warm,
    shape-valid, and with the week's criticism removed — and every one of them
    must fail its case.

    **The failure has to be about the sanding**, which is why the defect naming
    the signal is asserted rather than merely "something failed". A check that
    happened to fail these on their theme counts would satisfy a weaker assertion
    and would say nothing about criticism at all (`docs/MISTAKES.md` entry 3, and
    entry 30's rule that a fixture must not be able to decide the outcome by
    accident).

    **The mutation this kills:** the criticism check removed, weakened to a
    keyword match, or applied to the whole summary rather than to one span. **The
    near miss that must stay green:** the mixed week's praise, which these answers
    keep — so this cannot be satisfied by a checker that rejects every fluent
    answer.
    """
    contracts = summary_api.contracts()
    cases = eval_module("tests.evals.summary.cases")
    breach = eval_module("tests.evals.summary.breach")

    sanded = breach.sanded_answers(contracts)

    for case in cases.CASES:
        answer = answer_for(case.case_id, sanded)
        found = cases.defects(case, answer)
        assert found, (
            f"case {case.case_id} ({case.family}) passed against an answer with its criticism "
            "sanded off. The cases cannot fail, so a measurement over them would report a "
            "number about nothing."
        )
        for signal in case.signals:
            if signal.kind != cases.CRITICISM:
                continue
            assert any(signal.name in defect for defect in found), (
                f"case {case.case_id} failed, and no defect names the criticism "
                f"{signal.name!r}: {list(found)}. It failed for some other reason, so this "
                "demonstration would go on passing after the criticism check was removed."
            )

    empty = answer_for(cases.EMPTY_WEEK_CASE.case_id, sanded)
    invented = cases.invented_themes(cases.EMPTY_WEEK_CASE, empty)
    assert invented, (
        "the empty week passed against an answer carrying an invented theme. E4-05's fourth "
        "criterion: zero comments in, the contract's stated empty shape out, never an "
        "invented theme."
    )


def test_naming_the_topic_without_the_judgement_is_not_preserving_the_criticism(
    summary_api: SummaryApi,
) -> None:
    """The near miss the whole set is shaped around, and the ticket names it.

    "A summary eval that a keyword match satisfies is the green that hides the
    defect." These answers name every topic the week's comments were about — the
    pace, the reading list, the project brief — and say nothing about any of them.
    A check built on keywords passes all of them while the criticism has been
    removed as completely as in the sanded family.

    **The mutation this kills:** `Signal` collapsed to one list of words, which is
    the obvious simplification and the one that quietly makes this set stop
    measuring anything.

    **The near miss that must stay green:** the faithful answers, which paraphrase
    the comments rather than quoting them — so the repair for a red here is never
    "require the exact words".
    """
    contracts = summary_api.contracts()
    cases = eval_module("tests.evals.summary.cases")
    breach = eval_module("tests.evals.summary.breach")

    topic_only = breach.topic_only_answers(contracts)
    assert topic_only, "the topic-only family is empty, so this test asserts nothing."

    for case in cases.CASES:
        if case.case_id not in topic_only:
            continue
        found = cases.sanded_signals(case, topic_only[case.case_id])
        assert found, (
            f"case {case.case_id} ({case.family}) counted its criticism as preserved by an "
            "answer that names the topic and passes no judgement on it. That is the keyword "
            "match this set exists to be immune to."
        )


def test_the_mixed_week_fails_in_both_directions(summary_api: SummaryApi) -> None:
    """E4-05's fourth family, checked the way the ticket words it: *both* survive.

    "A mixed week where both praise and a specific complaint survive." A set that
    could only fail when the complaint went missing would report half a guarantee
    — an answer that reported the complaint and dropped everything students said
    worked is the other failure, and it is the one a model tuned away from
    sycophancy produces.

    **The mutation this kills:** a check that only looks at criticism signals.
    **The near miss that must stay green:** the faithful mixed answer, which
    carries both.
    """
    contracts = summary_api.contracts()
    cases = eval_module("tests.evals.summary.cases")
    breach = eval_module("tests.evals.summary.breach")

    mixed = cases.MIXED_WEEK_CASE
    kinds = {signal.kind for signal in mixed.signals}
    assert kinds == {cases.CRITICISM, cases.PRAISE}, (
        f"the mixed-week case carries signals of kinds {sorted(kinds)}. Both are needed: this "
        "test asserts one failure in each direction and each needs a signal to be about."
    )

    complaint_only = answer_for(mixed.case_id, breach.complaint_only_answers(contracts))
    dropped_praise = cases.sanded_signals(mixed, complaint_only)
    assert any(
        signal.name in defect
        for signal in mixed.signals
        if signal.kind == cases.PRAISE
        for defect in dropped_praise
    ), (
        f"an answer that reports the complaint and drops the praise was accepted: "
        f"{list(dropped_praise)}. E4-05 asks for both to survive."
    )

    praise_only = answer_for(mixed.case_id, breach.sanded_answers(contracts))
    dropped_complaint = cases.sanded_signals(mixed, praise_only)
    assert any(
        signal.name in defect
        for signal in mixed.signals
        if signal.kind == cases.CRITICISM
        for defect in dropped_complaint
    ), (
        f"an answer that keeps the praise and sands the complaint off was accepted: "
        f"{list(dropped_complaint)}."
    )


def test_the_summary_sets_pinned_prompt_version_is_the_one_the_application_renders(
    summary_api: SummaryApi,
) -> None:
    """The pin, held against the constant it deliberately does not import.

    `tests/evals/summary/cases.py` writes its prompt version down instead of
    reading it out of `app.ai.tasks`, for the reason the validity set gives about
    its own pin: a value read from the application follows every prompt bump
    silently and can never disagree with it, which is the one thing it is for
    (`docs/MISTAKES.md` entry 19). This is the test that makes the disagreement
    visible — a bump goes red here until somebody says the set has been
    re-measured, and that red is the conversation.

    **The mutation this kills:** the pin imported rather than written; the prompt
    version bumped with the set left pinned to the old text; and a version naming
    no file at all, which is a configuration that cannot summarize anything.
    """
    cases = eval_module("tests.evals.summary.cases")
    version = summary_api.constant(SUMMARY_PROMPT_VERSION)

    assert version == cases.PROMPT_VERSION, (
        f"the summary eval set is pinned to {cases.PROMPT_VERSION!r} and the application "
        f"renders {version!r}. ADR 0032 makes a committed prompt immutable, so this is a "
        "different prompt rather than the same one: re-measure the set against the new "
        "version, and move the pin in that pull request."
    )

    path = summary_api.prompt_path()
    assert path.is_file(), (
        f"{path} does not exist. E4-05's scope: '`prompts/summary.v1.md`, versioned like "
        "validity's', and ADR 0031 makes the recorded version that file's stem."
    )
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) > 5, (
        f"{path} holds {len(lines)} non-blank lines, which is not a prompt. A file read as "
        "empty would make every comparison against it meaningless."
    )
