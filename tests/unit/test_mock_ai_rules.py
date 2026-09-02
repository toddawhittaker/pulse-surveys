"""What the mock AI provider answers, and what it publishes about it — ticket E2-07.

E2-07's scope: "a small FastAPI service (`mock-ai/`, following the mock pattern)
speaking the OpenAI-compatible chat-completions surface the gateway uses,
returning deterministic `CommentValidityOutput`-shaped verdicts by simple
published rules — rules a test can aim at on purpose". This module is that aim.

**The rules are read from the mock, not written down here.** Acceptance criterion
3: "the mock's rules are served, not copied: its README/route states them, and the
tests that aim at them read the served statement (the E1-07 `ALL_SELECTORS` lesson
— no second hand-held copy)." So every threshold, marker and marker line below
comes out of `GET /mock/rules` through `tests/fixtures/mock_ai.py`, and a test
that needs to know the length rule asks the mock what its length rule is.

**With exactly one deliberate exception, which is the whole point of it.** The
block of literals below is this suite's own copy of the marker vocabulary and the
threshold, and `test_this_modules_copied_marker_vocabulary_is_the_one_the_mock_
serves` diffs it against the served document. Without one copy somewhere, a
rename inside `mock-ai/` renames both sides of every comparison at once and
nothing goes red — which is ADR 0088's recorded consequence for `mock-lms` and the
reason `tests/integration/test_mock_lms_wrong_launches.py` keeps the same pair.
One copy, one diff test, and no third.

**The verdict tokens are §7.4's, transcribed rather than derived**, and they live
in `tests/fixtures/mock_ai.py` because the mock and the tool both speak them.
Reading them off `app.ai.contracts` would make every assertion here a comparison
of the mock against the backend rather than against the specification both
implement; `tests/unit/test_ai_contracts.py` owns the derived direction, which is
what keeps the enum and §7.4's table in step.

**What is deliberately not asserted here.** Whether the gateway *reacts*
correctly to any of these answers is `tests/integration/
test_mock_ai_gateway_taxonomy.py`'s subject, because it needs a real socket and a
real classification. Whether the container comes up is the Compose health gate's,
and `tests/unit/test_mock_ai_service.py` holds the static half of that. And
whether the mock's classifications are any *good* is not a question anybody should
ask: SPEC §9.3 measures the real model, and E2-07 puts eval use out of scope
precisely because "a mock that passed evals would be measuring itself".
"""

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fixtures.mock_ai import (
    ALL_VERDICTS,
    HEALTH_PATH,
    INSUFFICIENT,
    MODELS_PATH,
    NONSENSE,
    OUTPUT_TOOL_NAME,
    RULES_PATH,
    SUBSTANTIVE,
    VERDICT_KEY,
    MockAiProvider,
    content_of,
    payload_of,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# Where the prompts live. ADR 0031 makes the recorded `prompt_version` a file's
# path stem and ADR 0032 fixes the extension, so a version resolves to exactly one
# file here with no lookup table between them.
PROMPTS_DIR = REPO_ROOT / "backend" / "app" / "ai" / "prompts"


def validity_prompt_path() -> Path:
    """The validity prompt the tool actually renders, not a version written down here.

    **This was `validity.v1.md` as a literal until the prompt trim of 2026-09-02,
    and the literal was the defect rather than the version.** ADR 0032 makes a
    committed prompt immutable, so `validity.v1.md` stays on disk forever — which
    means a test pinned to it goes on passing after the tool has moved to
    `validity.v2`, guarding a file nothing sends. The drift it exists to catch
    would then be live and invisible: the mock extracts the student's comment at
    the marker line of whatever prompt it *receives*, so a trim that reworded or
    dropped that line leaves every classification on a development stack answering
    the extraction-failure 500, with this test green.

    That is `docs/MISTAKES.md` entry 9's shape — a guard aimed at the case it used
    to be about — and the repair is to ask the application which prompt it renders
    rather than to remember. `app.ai.tasks.VALIDITY_PROMPT_VERSION` is the same
    constant `tests/evals/live.py` sends and the same one the eval set's pin is
    held against, so this is not a new coupling class in the suite.
    """
    from app.ai.tasks import VALIDITY_PROMPT_VERSION

    return PROMPTS_DIR / f"{VALIDITY_PROMPT_VERSION}.md"


# ---------------------------------------------------------------------------
# **The one deliberate hand-copy this ticket allows.**
#
# Every other constant in this file is fetched from `GET /mock/rules`. These are
# written out, and the two diff tests below hold them against the served document
# — the `ALL_SELECTORS` pair from `tests/integration/test_mock_lms_wrong_
# launches.py`, for the reason ADR 0088's consequences give: a vocabulary that is
# served *and* consumed through one source renames on both sides at once, so a
# rename inside the mock is invisible until something calls it with a stale name.
# Here it fails at a name instead.
#
# The strings are E2-07's work order, which settles them: four wrong-answer
# selectors and three forced verdicts, all in one `mock-ai:` namespace so that a
# marker cannot be mistaken for something a student wrote.
# ---------------------------------------------------------------------------
UNAVAILABLE_MARKER = "mock-ai:503"
REFUSED_MARKER = "mock-ai:500"
MALFORMED_MARKER = "mock-ai:malformed"
STALL_MARKER = "mock-ai:stall"
SUBSTANTIVE_MARKER = "mock-ai:substantive"
INSUFFICIENT_MARKER = "mock-ai:insufficient"
NONSENSE_MARKER = "mock-ai:nonsense"

COPIED_MARKERS: tuple[str, ...] = (
    UNAVAILABLE_MARKER,
    REFUSED_MARKER,
    MALFORMED_MARKER,
    STALL_MARKER,
    SUBSTANTIVE_MARKER,
    INSUFFICIENT_MARKER,
    NONSENSE_MARKER,
)

# The length rule, copied for the same reason and diffed by the same kind of test.
# SPEC §3.3 gives the number its meaning — "the prototype's ≥25-character
# heuristic ... retained solely as the fail-open floor" — and E2-07 reuses it so
# that the spec's own `"it was okay"` example classifies insufficient end to end.
COPIED_THRESHOLD = 25

# The two fields ADR 0031 forbids a model to report, in every spelling this could
# arrive under. The gateway supplies both and rejects a payload carrying either
# *before* merging anything into it, so a mock that helpfully filled them in
# would be answering with something the gateway must refuse.
AUDIT_KEYS = ("prompt_version", "promptversion", "model_id", "modelid", "model")

# The gateway's per-task timeout, measured and recorded in ADR 0053's
# consequences ("a four-second per-task timeout took 13.3 seconds and three
# requests to fail open"). It is here as the number the published stall has to
# exceed: a stall shorter than the budget answers in time and drives nothing.
GATEWAY_BUDGET_SECONDS = 4.0

# How much less than the published stall counts as "it waited". A margin rather
# than an equality, because a sleep is not a stopwatch and this suite runs under
# four xdist workers; half a second is far below the gap between the stall and
# the budget it must clear.
STALL_MEASUREMENT_MARGIN_SECONDS = 0.5

# The spec's own example of a comment that must be bounced, from §3.3's
# conditional-comment rule. Eleven characters, so the length rule reaches it.
SPEC_INSUFFICIENT_COMMENT = "it was okay"

# A comment that is unambiguously long, ordinary, and carries no marker.
ORDINARY_LONG_COMMENT = "The pacing in week three was too fast for the lab work."

# A line no prompt in this repository contains, for the drift matcher's control.
NOT_A_PROMPT_LINE = "### Kj3PxE8mZt5UwGh — this line is in no prompt file ###"


def comment_of_length(length: int) -> str:
    """A plain comment of exactly `length` characters, with no marker in it.

    Built rather than written out, because the two boundary cases differ by one
    character and a typed-out pair is the kind of fixture that is wrong in a way
    nobody sees. Every test that uses one asserts its length first anyway
    (`docs/MISTAKES.md` entry 13 — when a test fails inside its own fixture,
    suspect the fixture).

    **It may not end in whitespace, and that is not cosmetic.** The mock reads the
    comment as the text after the marker with surrounding whitespace removed, so a
    slice landing on a space would be one character shorter by the time the rule
    sees it — and the boundary pair, whose whole subject is one character, would
    be asserting the opposite of what it says.
    """
    stem = "the lab work was hard and the pacing was fast and the readings were long "
    built = (stem * (length // len(stem) + 1))[:length]
    if built != built.rstrip():
        built = built[:-1] + "!"
    assert len(built) == length and built == built.strip()
    return built


def verdict_of(response: Any) -> str:
    """The verdict one completion carries, or a failure saying what it carried."""
    payload = payload_of(response)
    assert isinstance(payload, dict), (
        f"The completion's content parsed to {payload!r}, which is not an object. The mock answers "
        "with the comment-validity payload, and that is a JSON object with one member."
    )
    verdict = payload.get(VERDICT_KEY)
    assert verdict in ALL_VERDICTS, (
        f"The payload carries {verdict!r} under {VERDICT_KEY!r}; it carries {sorted(payload)}. "
        f"SPEC §7.4 gives comment validity the output {' / '.join(ALL_VERDICTS)}, and the gateway "
        "validates what comes back against the contract built from that row."
    )
    return str(verdict)


# ---------------------------------------------------------------------------
# The served vocabulary, and this module's one copy of it.
# ---------------------------------------------------------------------------


def test_the_served_rules_document_publishes_every_part_of_the_vocabulary(
    mock_ai: MockAiProvider,
) -> None:
    """Criterion 3's precondition, and the non-vacuity guard for this whole module.

    Every other test here reads one of these four members, and
    `served_member` fails rather than answering `None` — so without this test the
    first thing a reader learns about a route that serves half a document is
    whichever unrelated test happened to run first.

    **The mutation this kills:** a `/mock/rules` that serves the markers alone,
    which is the natural first draft — the markers are the part a test obviously
    needs, and the threshold, the stall and the marker line are the parts a test
    would otherwise hard-code. Criterion 3 is about all four.

    **The near miss it must survive:** a document that publishes more than these
    four. Nothing here is an equality against a key set, because what else the
    mock chooses to publish about itself is not this ticket's business.
    """
    document = mock_ai.rules()
    assert document, f"`GET {RULES_PATH}` served an empty document."

    markers = mock_ai.markers()
    assert len(markers) >= len(COPIED_MARKERS), (
        f"`GET {RULES_PATH}` publishes {len(markers)} markers ({sorted(markers.values())}). E2-07 "
        f"gives the mock {len(COPIED_MARKERS)}: four deliberately wrong answers and three forced "
        "verdicts."
    )
    assert mock_ai.threshold() > 0
    assert mock_ai.stall_seconds() > 0
    assert mock_ai.marker_line().strip()


def test_this_modules_copied_marker_vocabulary_is_the_one_the_mock_serves(
    mock_ai: MockAiProvider,
) -> None:
    """The rename-kill: this file's literals against the mock's own published list.

    **The mutation this must kill:** rename one marker inside `mock-ai/` — say
    `mock-ai:500` to `mock-ai:refused` — and leave this module's constant alone.
    Without this test that shows up as whichever parametrised case selects the
    stale name quietly taking the *unmarked* path instead, so `mock-ai:500` would
    be classified by the length rule and answer 200 with a verdict, and the test
    named for the refused row would fail with a message about a verdict. Here it
    fails naming both spellings.

    **The near miss it must survive:** the same names published in a different
    order, or keyed differently in the document. Order is not part of a
    vocabulary — a consumer asks whether a string is a member — so this compares
    sorted, and multiplicity is compared too, because a served list carrying a
    name twice has the same *set* as one carrying it once.

    **Why this is not folded into the test above.** That one asks whether the
    route tells the truth about the mock; this one asks whether *this file* does.
    They have different repairs.
    """
    served = mock_ai.marker_strings()

    assert sorted(COPIED_MARKERS) == sorted(served), (
        f"This module's copied markers are {sorted(COPIED_MARKERS)} and the mock serves "
        f"{sorted(served)}. Copied here and not served: "
        f"{sorted(set(COPIED_MARKERS) - set(served))}; served and not copied here: "
        f"{sorted(set(served) - set(COPIED_MARKERS))}. Every marked case below selects its "
        "behaviour by one of these strings, so a name that has drifted is a case exercising the "
        "unmarked path under the name of the thing it was meant to drive."
    )


def test_this_modules_copied_length_threshold_is_the_one_the_mock_serves(
    mock_ai: MockAiProvider,
) -> None:
    """The same diff for the number the boundary pair is built from.

    **The mutation this must kill:** the mock's threshold moved to 20 or 30 while
    this file still says 25. The boundary tests build their comments from the
    served value, so they would go on passing against the moved rule and this
    module would silently stop asserting SPEC §3.3's number at all.

    Separate from the marker diff because the repairs differ: a moved threshold
    may be a deliberate decision about the mock, and a renamed marker is a rename.
    """
    assert mock_ai.threshold() == COPIED_THRESHOLD, (
        f"The mock publishes a length threshold of {mock_ai.threshold()} and this module copies "
        f"{COPIED_THRESHOLD}. SPEC §3.3 fixes the number — 'the prototype's ≥25-character "
        "heuristic ... retained solely as the fail-open floor' — and E2-07 reuses it so that the "
        'spec\'s own `"it was okay"` example classifies insufficient end to end.'
    )


def test_the_published_stall_is_longer_than_the_gateway_will_wait(
    mock_ai: MockAiProvider,
) -> None:
    """The stall has to outlast the budget, or it drives nothing.

    E2-07's second acceptance criterion needs "a stall past the budget" to reach
    ADR 0056's unavailable row. A stall of one second answers inside the
    gateway's four-second per-task timeout, so the classifier gets a verdict, the
    floor never applies, and the test that names the fail-open path passes for a
    reason unrelated to what it asserts.

    **The mutation this kills:** a stall shortened to fit inside the budget —
    which is exactly the change somebody makes to speed the suite up.
    """
    assert mock_ai.stall_seconds() > GATEWAY_BUDGET_SECONDS, (
        f"The mock publishes a stall of {mock_ai.stall_seconds()}s and the gateway's per-task "
        f"timeout is {GATEWAY_BUDGET_SECONDS}s (measured in ADR 0053's consequences). A stall "
        "inside the budget answers in time, so nothing floors and the unavailable row of ADR "
        "0056 has no path in this stack."
    )


# ---------------------------------------------------------------------------
# The length rule, and the boundary it turns on.
# ---------------------------------------------------------------------------


def test_the_specs_own_example_comment_is_classified_insufficient(
    mock_ai: MockAiProvider,
) -> None:
    """`"it was okay"` comes back insufficient, which E2-07's scope requires by name.

    "`\"it was okay\"` must classify insufficient so the spec's own example works
    end to end" — the sentence is in the ticket's scope, and it is there because
    SPEC §3.3 uses that string as the case a student is bounced on.

    **The mutation this kills:** the length rule inverted, absent, or applied to
    the whole prompt rather than to the extracted comment — the prompt is far
    longer than any threshold, so a mock that measured it would answer
    substantive for every comment ever sent.
    """
    assert len(SPEC_INSUFFICIENT_COMMENT) < mock_ai.threshold(), (
        f"{SPEC_INSUFFICIENT_COMMENT!r} is {len(SPEC_INSUFFICIENT_COMMENT)} characters and the "
        f"mock's threshold is {mock_ai.threshold()}, so this test would be asserting the long "
        "branch under the name of the short one."
    )

    assert verdict_of(mock_ai.ask(SPEC_INSUFFICIENT_COMMENT)) == INSUFFICIENT


def test_a_comment_one_character_below_the_threshold_is_insufficient(
    mock_ai: MockAiProvider,
) -> None:
    """The lower half of the boundary pair, at exactly threshold minus one.

    **The mutation this kills:** `>` written where `>=` belongs, or the comparison
    made against `len(comment) > threshold`. Every such mutation moves the
    boundary by one character and is invisible to any test that uses a comment
    comfortably on one side of it (`docs/MISTAKES.md` entry 3).

    **Its pair is the test below**, at exactly the threshold, and neither is worth
    anything alone: a mock that answered insufficient for everything passes this
    one, and a mock that answered substantive for everything passes that one.
    """
    threshold = mock_ai.threshold()
    comment = comment_of_length(threshold - 1)
    assert len(comment) == threshold - 1, (
        f"The fixture built a comment of {len(comment)} characters for a threshold of "
        f"{threshold}. This test is about one character, so a fixture that is off by one is the "
        "test being wrong rather than the mock."
    )

    assert verdict_of(mock_ai.ask(comment)) == INSUFFICIENT, (
        f"A {len(comment)}-character comment classified substantive against a published threshold "
        f"of {threshold}. The rule is that a comment shorter than the threshold is insufficient, "
        "so threshold minus one is the last character that is short."
    )


def test_a_comment_exactly_at_the_threshold_is_substantive(
    mock_ai: MockAiProvider,
) -> None:
    """The upper half of the boundary pair, at exactly the threshold.

    **The mutation this kills:** `>=` written where `>` belongs — the mirror of
    the test above, and the reason both are here. SPEC §3.3 writes the heuristic
    as "≥25 characters", so the threshold itself is substantive and one below it
    is not.
    """
    threshold = mock_ai.threshold()
    comment = comment_of_length(threshold)
    assert len(comment) == threshold, (
        f"The fixture built a comment of {len(comment)} characters for a threshold of "
        f"{threshold}."
    )

    assert verdict_of(mock_ai.ask(comment)) == SUBSTANTIVE, (
        f"A {len(comment)}-character comment classified insufficient against a published threshold "
        f"of {threshold}. SPEC §3.3 writes the heuristic as '≥25 characters', so a comment of "
        "exactly the threshold is long enough."
    )


def test_the_length_rule_counts_the_comment_and_not_the_prompts_own_whitespace(
    mock_ai: MockAiProvider,
) -> None:
    """The separator between the marker line and the comment is not part of it.

    This is the assumption the boundary pair above rests on, asserted rather than
    left implicit. The prompt puts a line break between its marker and the
    student's text; a mock that measured everything after the marker verbatim
    would count that break, and a 24-character comment would then be substantive
    because of a newline nobody typed. Which side of the boundary a comment falls
    on would be decided by prompt layout instead of by what the student wrote.

    **The mutation this kills:** extraction without surrounding whitespace
    removed. The comment here is one character *below* the threshold and is
    padded with blank lines and trailing spaces on both sides, so a mock that
    counts the padding answers substantive.

    **Its pair is the test above**, where the same construction at exactly the
    threshold must answer substantive — so this cannot be satisfied by a rule
    that strips characters it should have counted.
    """
    threshold = mock_ai.threshold()
    comment = comment_of_length(threshold - 1)
    padded = f"\n\n   {comment}   \n\n"

    assert verdict_of(mock_ai.ask(padded)) == INSUFFICIENT, (
        f"A {len(comment)}-character comment padded to {len(padded)} characters with blank lines "
        "and spaces classified substantive. The mock reads the student's comment as the text "
        "after the last marker line, and the whitespace the prompt's own layout puts there is not "
        "something the student wrote."
    )


def test_an_unmarked_comment_is_never_classified_nonsense(
    mock_ai: MockAiProvider,
) -> None:
    """`nonsense` is reachable only by its marker in v1, and this says so.

    E2-07's rule 3 has two outcomes and not three: short is insufficient,
    otherwise substantive. The third verdict exists in §7.4's vocabulary and the
    mock reaches it only when asked, which the README states — so a mock that
    started guessing at nonsense would make every e2e assertion about an
    unremarkable comment conditional on a heuristic nobody specified.

    **The mutation this kills:** any content-based nonsense rule — a keyboard-mash
    detector, a vowel ratio, a dictionary check. **The near miss that must stay
    green:** the nonsense *marker*, two sections below, which must still work.
    """
    assert verdict_of(mock_ai.ask(ORDINARY_LONG_COMMENT)) == SUBSTANTIVE


# ---------------------------------------------------------------------------
# The deliberately wrong answers.
# ---------------------------------------------------------------------------


def test_the_unavailable_marker_answers_a_503(mock_ai: MockAiProvider) -> None:
    """ADR 0056's unavailable row, minted by the mock: "the endpoint says it cannot serve now".

    A hosted provider having an outage answers with a status, not with a hanging
    socket — which is why 503 is in the floor at all. This is the status half of
    E2-07's second criterion; what the *gateway* does with it is
    `tests/integration/test_mock_ai_gateway_taxonomy.py`.

    **The mutation this kills:** a marker that returns 500 or 502 instead — the
    first is the other side of this ticket's whole near-miss pair, and the second
    would floor too, so a test asserting "not 200" would not tell them apart.
    """
    response = mock_ai.ask(f"{UNAVAILABLE_MARKER} the pacing was fine this week")

    assert response.status_code == 503, (
        f"`{UNAVAILABLE_MARKER}` answered {response.status_code} rather than 503. ADR 0056 puts "
        "503 in the fail-open floor — the endpoint answered and said it cannot serve — and E2-07's "
        "second criterion needs a path to that row. Body begins "
        f"{response.text[:200]!r}."
    )


def test_the_refused_marker_answers_a_500(mock_ai: MockAiProvider) -> None:
    """ADR 0056's refused row, and the other half of the pair this ticket exists for.

    "The 503/500 pair exists on purpose: it is the near miss that separates ADR
    0056's unavailable row from its refused row in E2-08's tests." ADR 0056's
    reasoning for keeping 500 out of the floor is that it means *our request* is
    the problem far more often than it means an outage.

    **The mutation this kills:** the two markers wired to the same status, or the
    500 marker answering 502 — either collapses the pair, and a suite that then
    reported both rows covered would be reporting one row twice.
    """
    response = mock_ai.ask(f"{REFUSED_MARKER} the pacing was fine this week")

    assert response.status_code == 500, (
        f"`{REFUSED_MARKER}` answered {response.status_code} rather than 500. ADR 0056 keeps 500 "
        "out of the floor deliberately, and E2-08's tests need a mock that can produce it. Body "
        f"begins {response.text[:200]!r}."
    )


def test_the_malformed_marker_answers_a_valid_envelope_carrying_a_payload_the_contract_refuses(
    mock_ai: MockAiProvider,
) -> None:
    """The shape-violation path: the HTTP is right and the object is wrong.

    Both halves matter and each defeats a different mutation. If the envelope were
    malformed too — a 200 that is not JSON, a missing `choices` — the gateway
    would fail before it ever validated a payload, and the retry-then-error path
    §7.4 describes would not be what was exercised. If the payload validated, the
    marker would drive nothing at all.

    **The mutation this kills:** a malformed answer that breaks the *envelope*
    rather than the payload, and a payload that happens to satisfy the contract.
    **The near miss:** `{"verdict": "maybe"}` would also be refused, so the value
    asserted is the settled `{"answer": 42}` — a payload with no verdict member at
    all, which is refused by a contract carrying `extra="forbid"` and by one that
    merely requires its own field.
    """
    response = mock_ai.ask(f"{MALFORMED_MARKER} the pacing was fine this week")

    assert response.status_code == 200, (
        f"`{MALFORMED_MARKER}` answered {response.status_code}. This selector is about the shape "
        "of the answer, not about the transport: an HTTP failure reaches a different row of ADR "
        "0056 entirely."
    )
    payload = payload_of(response)
    assert payload == {"answer": 42}, (
        f"`{MALFORMED_MARKER}` answered the payload {payload!r}. E2-07 settles it as "
        '`{"answer": 42}`: a well-formed JSON object that is not the comment-validity contract, '
        "so the gateway's shape-violation path is what runs."
    )


def test_the_stall_marker_answers_only_after_the_published_stall(
    mock_ai: MockAiProvider,
) -> None:
    """The delay is real, and it is the one the mock published.

    **The mutation this kills:** a stall marker that answers immediately — which
    passes any test asserting only the verdict, and leaves the fail-open path
    untested while looking exactly like coverage. The elapsed time is what
    separates the two.

    **The verdict is asserted as well as the delay**, because the point of this
    selector is a *late* answer rather than a broken one: the gateway must have
    given up on a request that would eventually have succeeded, which is what ADR
    0056's read-timeout row describes.

    This test costs the published stall in wall clock, once. That is the price of
    asserting that a delay exists at all.
    """
    stall = mock_ai.stall_seconds()

    started = time.monotonic()
    response = mock_ai.ask(f"{STALL_MARKER} {ORDINARY_LONG_COMMENT}")
    elapsed = time.monotonic() - started

    assert elapsed >= stall - STALL_MEASUREMENT_MARGIN_SECONDS, (
        f"`{STALL_MARKER}` answered after {elapsed:.2f}s against a published stall of {stall}s. A "
        "selector that does not actually wait drives none of the fail-open path it exists for."
    )
    assert verdict_of(response) == SUBSTANTIVE, (
        "The stalling answer is a correct answer that arrives late — that is what makes it a "
        "timeout rather than a failure."
    )


@pytest.mark.parametrize(
    ("marker", "verdict"),
    (
        (SUBSTANTIVE_MARKER, SUBSTANTIVE),
        (INSUFFICIENT_MARKER, INSUFFICIENT),
        (NONSENSE_MARKER, NONSENSE),
    ),
)
def test_each_forced_verdict_marker_answers_the_verdict_it_names(
    mock_ai: MockAiProvider, marker: str, verdict: str
) -> None:
    """All three of §7.4's verdicts are reachable on purpose.

    Three rows rather than one, because they fail differently: `substantive` and
    `insufficient` are also reachable by the length rule, so a marker that was
    ignored would still answer one of them for the right-length comment, while
    `nonsense` is reachable by nothing else at all.

    **The mutation this kills:** a forced-verdict marker that is parsed and
    discarded — each case here carries a comment whose *length* would give the
    other answer, so a mock that fell through to the length rule fails.
    """
    # Long enough that the length rule would answer `substantive`, so the
    # insufficient and nonsense rows cannot pass by falling through to it.
    comment = f"{marker} {ORDINARY_LONG_COMMENT}"
    assert len(comment) >= mock_ai.threshold()

    assert verdict_of(mock_ai.ask(comment)) == verdict, (
        f"`{marker}` did not produce {verdict!r}. A forced verdict is how E2-08 and every later "
        "e2e run drives a particular classification without patching the backend."
    )


# ---------------------------------------------------------------------------
# The order the rules are applied in.
# ---------------------------------------------------------------------------


def test_a_wrong_answer_marker_outranks_the_length_rule(mock_ai: MockAiProvider) -> None:
    """A 503 inside a long comment is still a 503.

    **The mutation this kills:** the rules applied in the other order, or applied
    as a chain that stops at the first *match* found by scanning the comment left
    to right. A comment long enough to be substantive is the ordinary case an e2e
    test drives, so a mock that answered 200 for it would make the unavailable
    path unreachable from any realistic comment.
    """
    comment = f"{ORDINARY_LONG_COMMENT} {UNAVAILABLE_MARKER}"
    assert len(comment) >= mock_ai.threshold()

    response = mock_ai.ask(comment)

    assert response.status_code == 503, (
        f"A comment carrying `{UNAVAILABLE_MARKER}` and otherwise long enough to be substantive "
        f"answered {response.status_code}. The wrong-answer markers are rule 1: they are decided "
        "before anything looks at the length."
    )


def test_a_wrong_answer_marker_outranks_a_forced_verdict(mock_ai: MockAiProvider) -> None:
    """`mock-ai:500` and `mock-ai:substantive` in one comment is a 500.

    The two selectors that can both claim a comment, and the only case where the
    published order is observable between rules 1 and 2. Without it, "rule 1 then
    rule 2" and "rule 2 then rule 1" are the same mock for every comment anybody
    writes.

    **The mutation this kills:** the forced verdicts checked first. **The near
    miss:** the pair below, which asserts the *other* order between rules 2 and 3
    — so neither can be satisfied by a mock that simply prefers whichever rule was
    written last.
    """
    response = mock_ai.ask(f"{SUBSTANTIVE_MARKER} {REFUSED_MARKER} {ORDINARY_LONG_COMMENT}")

    assert response.status_code == 500, (
        f"A comment carrying both `{REFUSED_MARKER}` and `{SUBSTANTIVE_MARKER}` answered "
        f"{response.status_code}. E2-07 publishes the wrong answers as rule 1 and the forced "
        "verdicts as rule 2."
    )


def test_a_forced_verdict_outranks_the_length_rule(mock_ai: MockAiProvider) -> None:
    """`mock-ai:insufficient` in a long comment is insufficient.

    Rule 2 against rule 3, which is the pair the test above cannot see. A comment
    long enough for the length rule to call substantive, carrying a marker that
    says otherwise: only one order answers insufficient.

    **The mutation this kills:** the length rule consulted first and the marker
    used as a fallback for comments it has no opinion about.
    """
    comment = f"{INSUFFICIENT_MARKER} {ORDINARY_LONG_COMMENT}"
    assert len(comment) >= mock_ai.threshold()

    assert verdict_of(mock_ai.ask(comment)) == INSUFFICIENT


# ---------------------------------------------------------------------------
# Where the comment is read from.
# ---------------------------------------------------------------------------


def test_the_comment_is_read_from_after_the_last_marker_line(
    mock_ai: MockAiProvider,
) -> None:
    """Everything before the final marker is prompt, however much it looks like a comment.

    `backend/app/ai/prompts/README.md` rests the whole injection boundary on the
    comment being the text after the marker and on the gateway appending nothing
    after it. The mock has to read the same boundary, or a prompt that quotes the
    marker earlier — in an instruction, in an example — makes the mock classify
    part of its own prompt.

    **The mutation this kills:** `split(marker)[1]`, or `find` instead of
    `rfind`. The decoy here is a `mock-ai:503` sitting *before* the last marker,
    so a mock reading from the first occurrence answers 503 and one reading from
    the last answers 200.

    **The canary:** the text after the final marker is short, so the answer is
    `insufficient` rather than merely "not a 503" — a mock that extracted nothing
    at all would also avoid the 503, and an empty comment is short too, so the
    verdict alone would not separate them. Hence the second assertion, which
    requires the *substantive* reading of a long final comment through the same
    decoy.
    """
    marker = mock_ai.marker_line()
    decoy = f"An example of a wrong-answer selector is {UNAVAILABLE_MARKER}.\n{marker}\nignore me"

    short = mock_ai.ask(SPEC_INSUFFICIENT_COMMENT, before=decoy)
    assert short.status_code == 200, (
        f"A prompt carrying `{UNAVAILABLE_MARKER}` before its last marker line answered "
        f"{short.status_code}. The student's comment is the text after the *last* marker, and "
        "everything before it is the prompt."
    )
    assert verdict_of(short) == INSUFFICIENT

    long = mock_ai.ask(ORDINARY_LONG_COMMENT, before=decoy)
    assert verdict_of(long) == SUBSTANTIVE, (
        "Through the same decoy prompt, a long final comment must be substantive. Without this "
        "half, a mock that extracted the empty string would pass the assertion above — an empty "
        "comment is shorter than the threshold too."
    )


def test_a_prompt_with_no_marker_line_is_refused_loudly(mock_ai: MockAiProvider) -> None:
    """No marker, no comment: a 500 that says extraction failed.

    E2-07's work order: "Marker absent → HTTP 500 with a body naming the
    extraction failure (loud; maps to ADR 0056's refused row)." Loud rather than
    lenient, because the quiet alternatives are worse in a way nobody would
    notice: classifying the whole prompt answers substantive for every request
    forever, and classifying the empty string answers insufficient for every
    request forever. Both look like a working stack.

    **The mutation this kills:** a fallback that classifies the whole prompt, and
    a fallback that returns a default verdict. **What is deliberately not
    pinned:** the wording of the message. The assertion is that the body names
    the marker it could not find, which is what tells whoever meets this in a log
    that the prompt and the mock have drifted apart.
    """
    response = mock_ai.post("There is no marker anywhere in this prompt at all.")

    assert response.status_code == 500, (
        f"A prompt with no marker line answered {response.status_code}. The mock cannot tell "
        "which part of it is the student's comment, and every quiet answer to that question is "
        f"wrong for every request. Body begins {response.text[:200]!r}."
    )
    assert mock_ai.marker_line().strip() in response.text, (
        f"The 500 for a prompt with no marker does not quote the marker it looked for "
        f"({mock_ai.marker_line()!r}); the body was {response.text[:300]!r}. That string is the "
        "one thing whoever meets this needs: it says which line the prompt has stopped ending "
        "with."
    )


def test_the_marker_line_the_mock_publishes_is_a_line_of_the_validity_prompt(
    configured_env: dict[str, str],
    mock_ai: MockAiProvider,
) -> None:
    """The drift test: the mock's copy of the marker against the prompt's own text.

    The mock cannot import `backend/app/`, so the marker it extracts on is a
    second copy of a string that lives in the validity prompt. E1-07's lesson is
    that a second copy is fine when something holds it against the first, and
    fatal when nothing does: an edit to the prompt's comment section that changed
    this line would leave every classification in the development stack answering
    the extraction-failure 500 — or, worse, a partial edit would leave the mock
    reading a boundary the prompt no longer has.

    **Which prompt is asked of the application rather than written down here**, and
    the trim of 2026-09-02 is why. ADR 0032 keeps every committed prompt on disk
    forever, so a path pinned to `validity.v1.md` goes on passing after the tool
    has moved to `validity.v2` — guarding a file nothing sends while the drift it
    exists to catch runs loose. `validity_prompt_path` says the rest.

    **A trimmed prompt is exactly the change that breaks this**, which is the
    point: if the new version reworded or dropped the marker line and the mock was
    left alone, this goes red rather than the development stack going quietly
    useless.

    **The mutation this kills:** the prompt's marker line reworded with the mock
    left alone, and the mock's constant retyped with a different dash, a
    different capitalisation, or an extra word.

    **The matcher is run in both directions** (`docs/MISTAKES.md` entry 3): a line
    that is certainly not in the prompt must not match, or a comparison that had
    gone blind — matching on emptiness, on a prefix, on a case fold that turns
    everything into everything — would report agreement between two strings that
    have nothing to do with each other.

    **Nothing here writes to the prompt.** This reads it.

    `configured_env` is requested because resolving which prompt to read imports
    `app.ai.tasks`, and a module that builds anything out of `Settings` at import
    time would otherwise build it out of whatever the developer's shell held
    (`docs/MISTAKES.md` entry 40). It is the first fixture in the signature so the
    environment is in place before the mock is started.
    """
    prompt_path = validity_prompt_path()
    assert prompt_path.is_file(), (
        f"{prompt_path} does not exist, so this test compares the mock's marker against "
        "nothing and would report agreement whatever it says.\n"
        "\n"
        "That path comes from `app.ai.tasks.VALIDITY_PROMPT_VERSION`, which is the prompt "
        "the tool renders. A version naming no file is a configuration that cannot classify "
        "anything, and ADR 0032's scheme is what makes the stem resolve to one file."
    )
    lines = [line.strip() for line in prompt_path.read_text(encoding="utf-8").splitlines()]
    assert len([line for line in lines if line]) > 5, (
        f"{prompt_path} holds {len(lines)} lines, which is not a prompt. A file that was "
        "read as empty makes the comparison below meaningless."
    )

    marker = mock_ai.marker_line().strip()
    assert marker in lines, (
        f"The mock publishes {marker!r} as the line the student's comment follows, and no line of "
        f"{prompt_path.name} is that string. The mock extracts the comment as everything "
        "after that marker's last occurrence, so a prompt that no longer ends its comment section "
        "with this line hands the mock a prompt it cannot read — every classification in the "
        "development stack then answers the extraction-failure 500."
    )
    assert NOT_A_PROMPT_LINE not in lines, (
        "The control for the comparison above: a line that is certainly in no prompt was reported "
        "as present, so the membership test is matching something other than what it reads."
    )


# ---------------------------------------------------------------------------
# The wire the gateway speaks (ADR 0053).
# ---------------------------------------------------------------------------


def test_a_completion_carries_the_task_payload_and_not_the_audit_pair(
    mock_ai: MockAiProvider,
) -> None:
    """The answer is the contract minus the two values the gateway supplies.

    ADR 0031, quoted in ADR 0053: "The gateway supplies both values; the model
    never reports them", and the gateway "must reject a provider payload that
    contains either key, *before* merging anything into it". A mock that filled
    in `prompt_version` or `model_id` would therefore be refused by a correct
    gateway on every single call — and the failure would read as a shape
    violation in the classifier rather than as a mock being too helpful.

    **The mutation this kills:** a payload carrying an audit field, and a payload
    carrying anything else at all: the contract's payload model is derived with
    `extra="forbid"`, so an added `confidence` or `reason` is refused too.
    """
    payload = payload_of(mock_ai.ask(ORDINARY_LONG_COMMENT))

    assert isinstance(payload, dict) and set(payload) == {VERDICT_KEY}, (
        f"The answer's payload is {payload!r}. E2-07 settles it as the contract payload minus the "
        f"audit pair — one member, {VERDICT_KEY!r} — and ADR 0053 derives the payload model with "
        'the contract\'s own `extra="forbid"`, so anything else is a shape violation.'
    )
    for name in AUDIT_KEYS:
        assert name not in payload, (
            f"The answer carries {name!r}. ADR 0031 forbids a model to report the prompt version "
            "or the model id; the gateway supplies both and rejects a payload that names either."
        )


def test_a_request_declaring_a_tool_gets_its_answer_in_a_tool_call(
    mock_ai: MockAiProvider,
) -> None:
    """The mock answers however it was asked, which is what keeps it honest to the stub.

    The gateway uses `NativeOutput` and declares no tool (ADR 0053), so this path
    is not on the road any classification takes today. It is here because
    `tests/integration/test_ai_gateway_validity_roundtrip.py`'s stub answers both
    ways on purpose — "a gateway using native JSON output and one using an output
    tool both get a well-formed answer, so neither mode is chosen from the test
    side" — and a mock that could only answer one way would silently become the
    thing that decides it.

    **The mutation this kills:** a tool-call branch that names a tool of its own
    invention rather than the one the request declared, which is the shape a
    client cannot read.
    """
    response = mock_ai.post(mock_ai.prompt_carrying(ORDINARY_LONG_COMMENT), tools=True)

    assert response.status_code == 200, f"A request declaring a tool answered {response.text[:200]}"
    message = response.json()["choices"][0]["message"]
    calls = message.get("tool_calls")
    assert isinstance(calls, list) and calls, (
        f"A request declaring a tool got back {message!r}, which carries no `tool_calls`. The "
        "stub the roundtrip test models answers under the name the request asked for."
    )
    call = calls[0]["function"]
    assert call.get("name") == OUTPUT_TOOL_NAME, (
        f"The tool call is named {call.get('name')!r} and the request declared "
        f"{OUTPUT_TOOL_NAME!r}. A client reads the answer back under the name it asked for."
    )
    arguments = json.loads(call["arguments"])
    assert arguments.get(VERDICT_KEY) in ALL_VERDICTS, (
        f"The tool call's arguments are {arguments!r}, which carry no verdict. Whichever way the "
        "answer travels, it is the same payload."
    )


def test_the_model_listing_probe_answers_with_a_model(mock_ai: MockAiProvider) -> None:
    """`GET /v1/models` answers, because a client may ask before it asks anything else.

    An OpenAI-compatible endpoint serves a model listing, and a provider library
    is free to probe it. The roundtrip stub answers one, so a mock that 404s here
    would differ from the stub in the one way that stops a client connecting at
    all.

    **The mutation this kills:** the route absent, or answering something that is
    not a listing.
    """
    response = mock_ai.client.get(MODELS_PATH)

    assert response.status_code == 200, (
        f"`GET {MODELS_PATH}` answered {response.status_code}. Body begins "
        f"{response.text[:200]!r}."
    )
    document = response.json()
    data = document.get("data") if isinstance(document, dict) else None
    assert isinstance(data, list) and data, (
        f"`GET {MODELS_PATH}` served {document!r}. A model listing is an object with a non-empty "
        "`data` array, each entry carrying an `id`."
    )
    assert all(
        isinstance(entry, dict) and entry.get("id") for entry in data
    ), f"`GET {MODELS_PATH}` served entries without an `id`: {data!r}."


def test_the_health_route_answers_two_hundred(mock_ai: MockAiProvider) -> None:
    """The route Compose's health check calls, asserted in process as well.

    The Compose health check is what CI's gate watches, and E0-03's lesson is that
    a health gate only ever exercises the direction where the answer is yes — so
    this asserts the route exists and answers, which is the half a static Compose
    test cannot see and a passing gate cannot distinguish from a check that was
    replaced with `true`.
    """
    response = mock_ai.client.get(HEALTH_PATH)

    assert response.status_code == 200, (
        f"`GET {HEALTH_PATH}` answered {response.status_code}. `scripts/ci/wait_for_health.sh` "
        "fails a service whose health check fails, and the check E2-07 declares in Compose calls "
        "this route."
    )


def test_the_completion_content_is_the_whole_of_what_the_gateway_reads(
    mock_ai: MockAiProvider,
) -> None:
    """A control on this module's own reader, run before its silence is believed.

    Every verdict assertion above goes through `content_of` and `payload_of` in
    `tests/fixtures/mock_ai.py`, and a reader that pulled the wrong field out of
    the envelope would report the same failure for every test at once. This is the
    one test that says the envelope itself is an OpenAI chat completion: an
    assistant role, a string content, and a `model` naming what answered.

    **A red here means these tests are broken, or the wire shape is — and reading
    this test first tells you which.**
    """
    response = mock_ai.ask(ORDINARY_LONG_COMMENT)
    document = response.json()

    assert document.get("object") == "chat.completion", (
        f"The envelope's `object` is {document.get('object')!r}. An OpenAI-compatible "
        "chat completion says so, and a client that switches on it would not recognise this."
    )
    message = document["choices"][0]["message"]
    assert message.get("role") == "assistant", f"The message's role is {message.get('role')!r}."
    assert isinstance(document.get("model"), str) and document["model"], (
        f"The envelope reports {document.get('model')!r} as the model that answered. The gateway "
        "records a model id per classification (ADR 0031), so an envelope naming nothing leaves "
        "half the audit pair with nowhere to come from."
    )
    assert content_of(response)
