"""The comment-validity eval set is one the character rule cannot pass — ticket E2-12.

SPEC §11 open question 4: "the classifier replaces the 25-character prototype
heuristic; its eval set and threshold need real seeded data before E2 exits".
SPEC §3.3 keeps that heuristic "solely as the fail-open floor". So the set exists
to measure something the character count cannot do, and a set the character count
scores perfectly measures nothing worth paying a provider for — it would produce
a precision and a recall figure, both high, both meaningless, and a floor grown
against them would gate on nothing.

That is what this module is for. The strongest assertion here is the one that
runs SPEC §3.3's own rule over the shipped set and requires it to be wrong in
**both** directions: at least one comment under twenty-five characters that
deserves participation credit, and at least one at or over it that does not. A
set failing either half is a set that was easy to write and is not worth running.

**What this module cannot assert, said rather than implied.** E2-12 requires that
no comment name a real person. Nothing here can check that — a name is a fact
about the world, not a property of a string — so it is a review property, and the
set's own module docstring records that every comment is invented. The same goes
for "plausible": a test can count cases and measure lengths, and cannot tell a
plausible student comment from an implausible one.

**These are controls.** The set ships in this change, so a red here is a defect in
the set or in this module and the repair is on this side of the test wall. The
red tests for E2-12 are in the three modules whose subjects are the workflow, the
path classifier and the gateway's construction flag.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Where ADR 0032 puts the prompts, and where the version a case is pinned to has
# to resolve to a file. SPEC §13: "`ai/prompts/` — versioned prompt templates, one
# file per task+version".
PROMPTS_DIRECTORY = REPO_ROOT / "backend" / "app" / "ai" / "prompts"

# "Size to spend, not to ceremony: on the order of a hundred cases" (E2-12's
# scope). A range rather than a number, because the exact count is not a
# criterion and pinning one would make every added case a failing test — but the
# range has ends, because forty cases is not on the order of a hundred and neither
# is four hundred, and the second is a bill.
FEWEST_CASES = 80
MOST_CASES = 140

# ADR 0113: `mock-ai` selects its wrong answers from marker phrases inside the
# comment itself. A marker in an eval case would make the case measure the mock's
# obedience rather than a model's judgement — and worse, would pass against the
# mock and change meaning entirely against a real provider, where the marker is
# ordinary text.
MOCK_MARKER_PREFIX = "mock-ai:"


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
                f"There is no `{name}` module. E2-12's scope puts the comment-validity eval "
                "set under `tests/evals/`, as typed cases built from the contract SPEC §7.4 "
                "makes the eval fixture."
            )
        raise


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """The set is imported, and importing it reaches `app.ai.contracts`.

    `docs/MISTAKES.md` entry 40. Nothing here reads the environment, but a module
    building anything out of `Settings` at import time would build it out of
    whatever the developer's shell happened to hold — and a red would then depend
    on the machine rather than on the set.
    """


@pytest.fixture
def cases_module() -> ModuleType:
    """`tests.evals.validity.cases`."""
    return eval_module("tests.evals.validity.cases")


def test_the_set_holds_on_the_order_of_a_hundred_cases(cases_module: ModuleType) -> None:
    """E2-12: "on the order of a hundred cases, one live model call each".

    Both ends matter and for opposite reasons. Too few and the rates move by
    whole percentage points per case, so a floor cannot be set with any headroom
    and a single unlucky answer flips the gate. Too many and the gate becomes
    expensive enough that somebody proposes running it less often, which is the
    firing condition this ticket designed being negotiated away.

    **The mutation this kills:** ship the machinery with a handful of illustrative
    cases, which passes every structural test in this module.
    """
    count = len(cases_module.CASES)
    assert FEWEST_CASES <= count <= MOST_CASES, (
        f"the comment-validity set holds {count} cases and E2-12 asks for on the order of a "
        f"hundred (this module accepts {FEWEST_CASES}-{MOST_CASES}). Fewer, and each case "
        "moves the measured rate too far for a floor to have headroom; many more, and the "
        "run costs enough that somebody argues for firing the gate less often."
    )


def test_every_case_is_pinned_to_the_prompt_version_the_set_was_written_against(
    cases_module: ModuleType,
) -> None:
    """ADR 0031 and ADR 0032: a case that cannot say which prompt it is about is not comparable.

    ADR 0031 makes the recorded version the prompt file's path stem, and ADR 0032
    makes that file immutable once a classification cites it — a prompt change is
    an added file, never an edit. So the pinned version names exactly one text that
    will still be readable when this set is re-run, and a case carrying no version
    or a different one is a case measured against a text nobody can reconstruct.

    The version itself is not written here, and the prompt trim of 2026-09-02 is
    why it should not be: this reads whatever `cases.py` pins, so a bump is one
    edit in one place rather than a search through docstrings for a string that
    has stopped being true.

    **What this compares is the cases against the set's own constant**, which
    makes it blind to that constant being wrong — the mutation battery changed
    `PROMPT_VERSION` and killed nothing here, because every case is built from it
    and the comparison is the set against itself (`docs/MISTAKES.md` entry 19).
    `test_the_pinned_prompt_version_is_the_one_the_application_loads` below is what
    holds the constant against something outside this directory.

    **The mutation this kills:** drop the pin from the case type, or let cases
    default to whatever the gateway happens to answer under — which is the shape
    that reads correct and makes every run self-consistent and incomparable.
    """
    pinned = cases_module.PROMPT_VERSION
    assert pinned, "the set declares no prompt version at all"

    drifted = sorted(
        {case.prompt_version for case in cases_module.CASES if case.prompt_version != pinned}
    )
    assert not drifted, (
        f"the set is pinned to {pinned!r} and holds cases pinned to {drifted}. A set "
        "spanning two prompt versions produces one precision figure about two different "
        "programs."
    )


def test_the_pinned_prompt_version_is_the_one_the_application_loads(
    cases_module: ModuleType,
) -> None:
    """The pin names the prompt the run will actually be made under, and a file that exists.

    The test above compares the cases against `PROMPT_VERSION`, so it cannot see
    that constant being wrong — every case is built from it. Two things outside this
    directory settle whether it is right, and both are checked here.

    **The application's constant.** `app.ai.tasks.VALIDITY_PROMPT_VERSION` is what
    `tests/evals/live.py` renders and sends, so a set pinned to anything else is a
    set that refuses on its first case: the runner compares each answer's recorded
    version against the case's pin, and they would never match. That refusal is
    correct and it is a slow way to find a typo — this is the fast one, and it needs
    no provider.

    **A file on disk.** ADR 0031 makes the recorded version the prompt file's path
    stem and ADR 0032 makes that file immutable once a classification cites it, so
    a version naming no file is a measurement nobody can reproduce. A pin of
    `validity.vN` has to be `validity.vN.md` under `app/ai/prompts/`, which is the
    scheme ADR 0032 settles and the reason the extension is fixed there.

    **Both halves are red on a prompt bump, and both are the point.** The set was
    repinned to `validity.v2` on 2026-09-02 with the provider switch, ahead of the
    application constant and the file — so this fails twice over until the
    implementer lands both, and it is the red that says the two sides have not met
    yet. ADR 0032 keeps `validity.v1.md` on disk either way, so nothing about the
    old measurement becomes unreadable; what this refuses is a *set* claiming to be
    about a text the tool does not send.

    **The mutation this kills:** a `PROMPT_VERSION` that drifts from the
    application's — the whole set changes with it and every test that compares the
    set against itself stays green. **The near miss that must stay green:** a real
    prompt bump, where the application, the file and this constant move together in
    one reviewed change, which is exactly what ADR 0032 asks a prompt change to
    look like.
    """
    from app.ai.tasks import VALIDITY_PROMPT_VERSION

    pinned = cases_module.PROMPT_VERSION
    assert pinned == VALIDITY_PROMPT_VERSION, (
        f"the set is pinned to {pinned!r} and `app.ai.tasks` renders "
        f"{VALIDITY_PROMPT_VERSION!r}. Every case would be answered under a version the "
        "set does not name, so the runner refuses on the first one and no floor is ever "
        "measured."
    )

    prompt = PROMPTS_DIRECTORY / f"{pinned}.md"
    present = (
        sorted(path.name for path in PROMPTS_DIRECTORY.iterdir())
        if PROMPTS_DIRECTORY.is_dir()
        else "nothing — that directory does not exist"
    )
    assert prompt.is_file(), (
        f"the set is pinned to {pinned!r} and there is no {prompt.name} in "
        f"{PROMPTS_DIRECTORY.relative_to(REPO_ROOT)}, which holds {present}.\n"
        "\n"
        "ADR 0031 makes the recorded version the prompt file's path stem and ADR 0032 makes "
        "that file immutable once a classification cites it. A version naming no file is a "
        "measurement nobody can reproduce, which is the whole thing the pin buys."
    )


def test_all_three_of_the_spec_verdicts_appear_in_the_set(cases_module: ModuleType) -> None:
    """SPEC §7.4's Output column for this task: substantive / insufficient / nonsense.

    A set holding two of the three measures a classifier that has never been
    asked to produce the third. `nonsense` is the one most easily left out — it is
    the verdict §3.3 says reduces the validity rate rather than the one that
    decides credit — and a model that never emits it would score perfectly on a
    set that never asks for it.

    **The mutation this kills:** write a two-class set, which every other
    assertion in this module accepts.
    """
    expected = {case.expected for case in cases_module.CASES}
    wanted = {cases_module.SUBSTANTIVE, cases_module.INSUFFICIENT, cases_module.NONSENSE}
    assert expected == wanted, (
        f"the set covers {sorted(verdict.value for verdict in expected)} and SPEC §7.4 gives "
        f"this task {sorted(verdict.value for verdict in wanted)}."
    )


def test_no_two_cases_carry_the_same_comment(cases_module: ModuleType) -> None:
    """A duplicated comment is one measurement counted twice.

    It is not merely untidy. A duplicate weights whatever the model does with that
    one comment at double, so a set that accumulated a few of them scores a
    different rate from the set somebody thinks they wrote — and the drift is
    invisible, because the count is right.

    **The mutation this kills:** grow the set by pasting a family and editing half
    of it.
    """
    seen: dict[str, list[str]] = {}
    for case in cases_module.CASES:
        seen.setdefault(case.comment, []).append(case.case_id)
    repeated = {comment: ids for comment, ids in seen.items() if len(ids) > 1}
    assert not repeated, f"these comments appear more than once: {repeated}"


def test_no_case_is_empty_or_only_whitespace(cases_module: ModuleType) -> None:
    """An empty comment is not a case, and §3.3 does not classify one.

    "Optional comments left blank do not affect validity" — a blank answer never
    reaches the classifier at all, so a blank eval case measures a path the
    product does not have. It also makes the character heuristic and the model
    agree trivially, which inflates every rate in the report.
    """
    blank = [case.case_id for case in cases_module.CASES if not case.comment.strip()]
    assert not blank, f"these cases hold no comment: {blank}"


def test_no_case_carries_a_marker_that_drives_the_mock_provider(
    cases_module: ModuleType,
) -> None:
    """ADR 0113: `mock-ai` picks its answer out of the comment, so a marker owns the case.

    The mock reads `mock-ai:substantive`, `mock-ai:503`, `mock-ai:malformed` and
    four more out of the comment text itself, because E2-07's scope forbade the
    gateway telling the mock from a provider. A marker inside an eval case is
    therefore a case that measures obedience against the mock and means something
    completely different against a real provider, where it is ordinary text a
    model reads and ignores.

    The eval runner always builds a live gateway, so a marker here would not fire
    today. It would fire the moment anybody ran this set against the development
    stack to see what it does — which is exactly what somebody does before setting
    the floors.

    **The mutation this kills:** seed the set from comments written while testing
    the mock. **The near miss that must stay green:** a comment that mentions a
    model, a provider or a mock in ordinary prose, since the prefix is a namespace
    rather than a word.
    """
    carrying = [
        case.case_id for case in cases_module.CASES if MOCK_MARKER_PREFIX in case.comment.lower()
    ]
    assert not carrying, (
        f"these cases carry a `{MOCK_MARKER_PREFIX}` marker: {carrying}. ADR 0113 makes that "
        "prefix a selector the mock provider reads out of the comment, so the case would "
        "measure the mock's obedience rather than a classification."
    )


def test_the_short_substantive_family_sits_under_the_character_floor(
    cases_module: ModuleType,
) -> None:
    """The half of the set the heuristic denies credit to.

    SPEC §3.3's fail-open floor says a comment shorter than twenty-five characters
    is not substantive. "Lab ran 40 min over." is twenty characters, is specific,
    and is exactly the feedback an instructor can act on this afternoon — and
    under the prototype rule the student who wrote it loses the week.

    Both properties are asserted per case, because either one drifting silently
    turns the family into ordinary cases: a comment that grew past the threshold
    stops being a case the heuristic gets wrong, and one relabelled `insufficient`
    stops being a case at all.

    **The mutation this kills:** grow these comments while editing them, which is
    the natural direction for prose and takes the family out from under the
    boundary without changing a label. **The near miss that must stay green:**
    rewording inside the length budget, since this asserts the length and the
    label rather than the words.
    """
    threshold = cases_module.HEURISTIC_MINIMUM_CHARACTERS
    family = [case for case in cases_module.CASES if case.family == cases_module.SHORT_SUBSTANTIVE]

    assert family, (
        "the set holds no short-substantive case. E2-12's scope names it as one of "
        "'the two the 25-character rule misclassifies by construction', and without it the "
        "heuristic scores perfectly on half the boundary."
    )
    wrong = [
        (case.case_id, len(case.comment), case.expected.value)
        for case in family
        if len(case.comment) >= threshold or case.expected != cases_module.SUBSTANTIVE
    ]
    assert not wrong, (
        f"these short-substantive cases are not both under {threshold} characters and "
        f"labelled substantive: {wrong}"
    )


def test_the_long_vacuous_family_sits_at_or_over_the_character_floor(
    cases_module: ModuleType,
) -> None:
    """The half of the set the heuristic awards credit to.

    "good good good good good good" is twenty-nine characters and says nothing.
    The character rule awards participation credit for it, which is the other
    direction of SPEC §11 question 4's problem and the one with a grade attached.

    The pair with the test above, and the pairing is the point: a set with only
    short-substantive cases is passed by a classifier that has learned "always say
    substantive", and a set with only long-vacuous cases is passed by one that has
    learned the opposite. Neither is a classifier.

    **The mutation this kills:** shorten these while editing, so the family drops
    below the threshold and stops being cases the heuristic gets wrong.
    """
    threshold = cases_module.HEURISTIC_MINIMUM_CHARACTERS
    family = [case for case in cases_module.CASES if case.family == cases_module.LONG_VACUOUS]

    assert family, (
        "the set holds no long-vacuous case — 'a long vacuous one' is the second of the two "
        "families E2-12's scope names."
    )
    wrong = [
        (case.case_id, len(case.comment), case.expected.value)
        for case in family
        if len(case.comment) < threshold or case.expected == cases_module.SUBSTANTIVE
    ]
    assert not wrong, (
        f"these long-vacuous cases are not both at least {threshold} characters and labelled "
        f"as not substantive: {wrong}"
    )


def test_the_boundary_family_straddles_the_character_floor_in_both_directions(
    cases_module: ModuleType,
) -> None:
    """Two near-miss pairs, one character apart, at the place the heuristic changes its mind.

    At twenty-four characters SPEC §3.3's rule says insufficient and at
    twenty-five it says substantive, and the truth does not move with the count.
    So each of the two lengths appears once where the right answer is substantive
    and once where it is not — four cases, and none of the four is redundant:

      - 24 and substantive, 25 and substantive — a classifier that has quietly
        learned the character rule fails the first and passes the second;
      - 24 and insufficient, 25 and insufficient — it passes the first and fails
        the second.

    Take any one away and one of those two failure modes stops being detectable.

    **The lengths are asserted rather than trusted.** A case that drifted by one
    character still reads correctly and has silently stopped being a boundary
    case, and nothing else in this suite would notice.

    **The mutation this kills:** keep only the pair on one side of the boundary,
    or let an edit move a case off the boundary by a character.
    """
    threshold = cases_module.HEURISTIC_MINIMUM_CHARACTERS
    below, at = threshold - 1, threshold
    family = [case for case in cases_module.CASES if case.family == cases_module.BOUNDARY]

    assert family, "the set holds no boundary cases"

    found = {(len(case.comment), case.expected) for case in family}
    wanted = {
        (below, cases_module.SUBSTANTIVE),
        (at, cases_module.SUBSTANTIVE),
        (below, cases_module.INSUFFICIENT),
        (at, cases_module.INSUFFICIENT),
    }
    missing = wanted - found
    assert not missing, (
        "the boundary family does not cover both lengths in both directions. Missing "
        f"{sorted((length, verdict.value) for length, verdict in missing)}; the family holds "
        f"{sorted((len(case.comment), case.expected.value) for case in family)}."
    )


def test_the_character_heuristic_cannot_score_perfectly_on_this_set(
    cases_module: ModuleType,
) -> None:
    """The assertion the whole set exists to make true, run rather than argued.

    SPEC §3.3's twenty-five character rule is executed over the shipped cases and
    required to be wrong in **both** directions: it must award the positive
    verdict to at least one comment that does not deserve it, and withhold it from
    at least one that does. Precision below one, recall below one.

    A set the heuristic scores perfectly is a set on which a classifier can be
    compared against nothing: the floors could be met by counting characters, and
    SPEC §11 question 4 — "the classifier replaces the 25-character prototype
    heuristic" — would have been settled by writing down the heuristic's own
    score.

    Both halves are needed. A set where the heuristic only over-awards can be
    cleared by a stricter character count; one where it only under-awards can be
    cleared by a looser one. Only being wrong in both directions makes the
    threshold unmovable, which is what "the classifier's call" means.

    **The mutation this kills:** replace the set with long substantive comments
    and short vacuous ones — the set anybody writes first, and the one the
    character rule scores 1.0 on. **The near miss that must stay green:** any set
    that keeps one case of each hard family, since this asserts the property and
    not the case count.
    """
    measure_module = eval_module("tests.evals.measure")
    cases = cases_module.CASES
    answers = [cases_module.heuristic_verdict(case.comment) for case in cases]
    measurement = measure_module.measure(cases, answers, cases_module.POSITIVE_VERDICT)

    assert measurement.false_positives > 0, (
        "SPEC §3.3's character rule awards the substantive verdict to nothing in this set "
        "that does not deserve it, so the set never asks a classifier to be more careful "
        "than counting characters. E2-12's scope names 'a long vacuous one' as one of the "
        "two families that must be there by construction."
    )
    assert measurement.false_negatives > 0, (
        "SPEC §3.3's character rule withholds the substantive verdict from nothing in this "
        "set that deserves it, so the set never asks a classifier to be more generous than "
        "counting characters. E2-12's scope names 'a short substantive comment' as the other."
    )
    assert measurement.precision < 1.0 and measurement.recall < 1.0, (
        f"the character heuristic scores precision {measurement.precision} and recall "
        f"{measurement.recall} over this set. A floor grown against a set the prototype "
        "rule already clears gates nothing."
    )


def test_the_set_holds_enough_of_both_classes_for_a_rate_to_mean_anything(
    cases_module: ModuleType,
) -> None:
    """Both rates need a denominator, and a denominator of two is not a measurement.

    Recall is computed over the cases whose expected verdict is `substantive` and
    precision over the answers that claim it. A set of ninety-eight cases with
    three positives among them produces a recall that moves by a third per case,
    so any floor set on it is either unmeetable or meaningless.

    Ten of each is a floor rather than a target — the shipped set holds far more —
    and it is here so that a later trimming of the set cannot quietly take the
    denominator away. `.claude/review-fixtures/eval-floor-lowered.diff` plants
    exactly that move: "three cases are removed from the threat set — a narrowed
    set clears the same floor more easily, which is a lowered floor wearing a
    costume".
    """
    positives = [
        case for case in cases_module.CASES if case.expected == cases_module.POSITIVE_VERDICT
    ]
    negatives = [
        case for case in cases_module.CASES if case.expected != cases_module.POSITIVE_VERDICT
    ]

    assert len(positives) >= 10, (
        f"the set holds {len(positives)} cases of the positive class. Recall over that few "
        "moves in steps too large for a floor to sit between."
    )
    assert len(negatives) >= 10, (
        f"the set holds {len(negatives)} cases outside the positive class. Precision over "
        "that few is a rate a single answer can swing."
    )
