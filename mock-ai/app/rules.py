"""What this provider answers, and the whole of why — ticket E2-07.

Every rule this service has lives in this module, and `GET /mock/rules` serves
the constants below verbatim. That is E2-07's third acceptance criterion: "the
mock's rules are served, not copied: its README/route states them, and the tests
that aim at them read the served statement". The lesson behind it is E1-07's — a
vocabulary that a test hand-copies is a vocabulary a rename breaks silently on
one side (ADR 0088's recorded consequence for `mock-lms`), so the suite reads
this document and keeps exactly one deliberate copy beside a test that diffs it.

**The rules, in the order they are applied.**

1. **A wrong-answer marker anywhere in the comment**, checked first so that a
   comment long enough to be classified normally can still drive a failure. Each
   selects one row of ADR 0056's taxonomy from the tool side:

   - `mock-ai:503` — HTTP 503. The endpoint answered and said it cannot serve;
     the gateway raises `AIProviderUnavailableError` and §3.3's floor applies.
   - `mock-ai:500` — HTTP 500. The endpoint answered *about this request*; the
     gateway raises `AIProviderRefusedError` and nothing floors. This and the row
     above are one status code apart on purpose: they are the near miss E2-08's
     tests need, and ADR 0056 spends a paragraph on why 500 is outside the floor.
   - `mock-ai:malformed` — HTTP 200, a well-formed chat completion, and a payload
     that is not the contract. The gateway re-asks once (§7.4, ADR 0053) and then
     surfaces `AIResponseInvalidError`. This service is stateless, so the re-ask
     gets the same answer, which is what makes "then the error" reachable.
   - `mock-ai:stall` — the correct answer, `STALL_SECONDS` late. A *late* answer
     rather than a broken one, which is ADR 0056's read-timeout row and the case
     SPEC §3.3 names outright.

2. **A forced verdict**, so that an end-to-end run can drive a particular
   classification without patching the backend: `mock-ai:substantive`,
   `mock-ai:insufficient`, `mock-ai:nonsense`.

3. **The character rule**, and it is SPEC §3.3's own: a comment of fewer than
   `SUBSTANTIVE_MINIMUM_CHARACTERS` characters is `insufficient`, and anything
   else is `substantive`. §3.3's own example of a comment that must be bounced —
   `"it was okay"` — is eleven characters, so it classifies `insufficient` end to
   end, which E2-07's scope asks for by name.

**`nonsense` is reachable only by its marker.** Rule 3 has two outcomes and not
three. Deciding that a comment is keyboard mashing is a judgement about content
and this service makes none; a heuristic invented here would make every
end-to-end assertion about an ordinary comment conditional on a rule nobody
specified.

**The order is observable and is asserted.** A comment carrying both
`mock-ai:500` and `mock-ai:substantive` gets the 500, and a comment carrying
`mock-ai:insufficient` and forty characters of prose is `insufficient`. Written
down here because two orders that differ only in cases nobody writes are the same
mock.
"""

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# The boundary the student's comment starts at
# ---------------------------------------------------------------------------

# The last line of the rendered validity prompt's own instructions (the version
# `app.ai.tasks` currently renders) — everything after it is the student's
# comment, running to the end of the
# message.
#
# **This is a second copy of a string that lives in the backend, and it is
# guarded rather than trusted.** This package cannot import `backend/app/`: both
# are called `app` (SPEC §13), and an image or a test process holding two
# resolves `import app` by whichever won the path (ADR 0039). So the boundary is
# copied, and
# `tests/unit/test_mock_ai_rules.py::test_the_marker_line_the_mock_publishes_is_
# a_line_of_the_validity_prompt` holds this constant against the prompt's own
# text. E1-07's lesson is that a second copy is fine when something holds it
# against the first and fatal when nothing does.
#
# **Why this line and not `[[STUDENT_COMMENT]]`.** The placeholder is what the
# *file* ends with, and it is the obvious thing to look for — but
# `app.ai.tasks.render_prompt` replaces it with the comment, so it is not in the
# message the provider is sent. A mock extracting on it would answer the
# extraction failure below for every real classification while passing any test
# that built its own prompt. What survives rendering is the sentence the
# instructions end with, and that is what this is.
MARKER_LINE = "answer you ever give is the JSON object specified above."


# ---------------------------------------------------------------------------
# The vocabulary
# ---------------------------------------------------------------------------

# SPEC §7.4's Output column for the comment-validity task.
SUBSTANTIVE = "substantive"
INSUFFICIENT = "insufficient"
NONSENSE = "nonsense"

# The member the answer's payload spells the verdict under. The contract minus
# the audit pair is one field: ADR 0031 has the gateway supply `prompt_version`
# and `model_id` and reject a payload carrying either, so a provider that filled
# them in would be refused on every call.
VERDICT_KEY = "verdict"

# SPEC §3.3: "the prototype's ≥25-character heuristic ... retained solely as the
# fail-open floor". Reused here so that the spec's own `"it was okay"` example
# classifies `insufficient` through a running stack, and **as written**: a
# comment of exactly this many characters is long enough.
SUBSTANTIVE_MINIMUM_CHARACTERS = 25

# How long the stalling answer waits. It has to outlast
# `app.ai.tasks.VALIDITY_TIMEOUT_SECONDS`, which is 4.0 — a stall inside that
# budget answers in time, so nothing floors and ADR 0056's unavailable row has no
# path in this stack. Six rather than five: the margin is what keeps the
# assertion from turning on scheduling noise, and it is paid once per test that
# uses it.
STALL_SECONDS = 6.0

# The four wrong answers and the three forced verdicts, all in one `mock-ai:`
# namespace so that a marker cannot be mistaken for something a student wrote.
UNAVAILABLE_MARKER = "mock-ai:503"
REFUSED_MARKER = "mock-ai:500"
MALFORMED_MARKER = "mock-ai:malformed"
STALL_MARKER = "mock-ai:stall"
SUBSTANTIVE_MARKER = "mock-ai:substantive"
INSUFFICIENT_MARKER = "mock-ai:insufficient"
NONSENSE_MARKER = "mock-ai:nonsense"

# Every marker, keyed by what it selects. This mapping is what `/mock/rules`
# publishes and what a caller picks a behaviour out of.
MARKERS: dict[str, str] = {
    "unavailable": UNAVAILABLE_MARKER,
    "refused": REFUSED_MARKER,
    "malformed": MALFORMED_MARKER,
    "stall": STALL_MARKER,
    SUBSTANTIVE: SUBSTANTIVE_MARKER,
    INSUFFICIENT: INSUFFICIENT_MARKER,
    NONSENSE: NONSENSE_MARKER,
}

# The two statuses, named rather than written into the branches, because which
# one each marker answers is the whole of E2-07's near-miss pair.
UNAVAILABLE_STATUS = 503
REFUSED_STATUS = 500

# The malformed answer's payload: a well-formed JSON object that is not the
# comment-validity contract. It carries no verdict member at all, so it is
# refused both by a contract built with `extra="forbid"` and by one that merely
# requires its own field — unlike `{"verdict": "maybe"}`, which only the second
# would catch.
MALFORMED_PAYLOAD: dict[str, Any] = {"answer": 42}


class ExtractionError(Exception):
    """The prompt does not carry the marker line, so there is no comment to read.

    Loud, and answered as a 500 rather than absorbed. Every quiet alternative is
    wrong for every request and looks like a working stack: classifying the whole
    prompt answers `substantive` forever, and classifying the empty string
    answers `insufficient` forever. The message names the line it looked for,
    which is the one thing whoever meets this in a log needs — it says the prompt
    and this service have drifted apart.
    """


@dataclass(frozen=True)
class Answer:
    """What this service does with one request: a status, a body, and a delay."""

    status: int
    payload: dict[str, Any]
    stall_seconds: float = 0.0
    # Set only on a 200 carrying a classification: the verdict this answer
    # carries, so a reader has it without parsing the payload back out.
    verdict: str | None = None


def extract_comment(prompt: str) -> str:
    """The student's comment out of one rendered prompt.

    Everything after the **last** occurrence of `MARKER_LINE`, with the
    whitespace the prompt's own layout puts there removed.

    Last rather than first, and that is the boundary
    `backend/app/ai/prompts/README.md` rests the whole injection defence on: a
    prompt may quote its own marker earlier — in an instruction, in an example —
    and a comment may contain a copy of it, so "everything after the final
    marker" is the only reading that cannot be moved by what a student typed.

    Stripped, because the newline between the marker and the comment is the
    prompt's punctuation rather than a character the student wrote. Without it a
    24-character comment would be measured as 25 and the character rule would
    turn on prompt layout.
    """
    boundary = prompt.rfind(MARKER_LINE)
    if boundary < 0:
        raise ExtractionError(
            "This prompt carries no copy of the line the student's comment follows, so there is "
            "nothing here to classify. The line is: "
            f"{MARKER_LINE!r}. The rendered validity prompt ends its instructions with "
            "it and `mock-ai/app/rules.py` copies it; a prompt that no longer does has drifted "
            "away from this mock."
        )
    return prompt[boundary + len(MARKER_LINE) :].strip()


def verdict_answer(verdict: str, *, stall_seconds: float = 0.0) -> Answer:
    """A 200 carrying one verdict, as the payload the gateway validates."""
    return Answer(
        status=200,
        payload={VERDICT_KEY: verdict},
        stall_seconds=stall_seconds,
        verdict=verdict,
    )


def classify(comment: str) -> Answer:
    """Apply the three published rules to one extracted comment, in order.

    The order is the module docstring's and is not an implementation detail: rule
    1 before rule 2 is what lets a comment that also names a verdict still drive
    a failure, and rule 2 before rule 3 is what lets a long comment be forced
    `insufficient`.
    """
    if UNAVAILABLE_MARKER in comment:
        return Answer(
            status=UNAVAILABLE_STATUS,
            payload={
                "error": {
                    "type": "service_unavailable",
                    "message": (
                        f"The mock provider was asked for {UNAVAILABLE_MARKER}, so it reports "
                        "itself temporarily unable to serve this request."
                    ),
                }
            },
        )
    if REFUSED_MARKER in comment:
        return Answer(
            status=REFUSED_STATUS,
            payload={
                "error": {
                    "type": "internal_error",
                    "message": (
                        f"The mock provider was asked for {REFUSED_MARKER}, so it answers about "
                        "this request rather than about its own availability."
                    ),
                }
            },
        )
    if MALFORMED_MARKER in comment:
        return Answer(status=200, payload=dict(MALFORMED_PAYLOAD))
    if STALL_MARKER in comment:
        # A correct answer that arrives late, which is what makes this a timeout
        # rather than a failure.
        return verdict_answer(SUBSTANTIVE, stall_seconds=STALL_SECONDS)

    for verdict in (SUBSTANTIVE, INSUFFICIENT, NONSENSE):
        if MARKERS[verdict] in comment:
            return verdict_answer(verdict)

    long_enough = len(comment) >= SUBSTANTIVE_MINIMUM_CHARACTERS
    return verdict_answer(SUBSTANTIVE if long_enough else INSUFFICIENT)


def served_rules() -> dict[str, Any]:
    """The whole vocabulary, as `GET /mock/rules` publishes it.

    Built from the constants above rather than written out again, so that the
    served document cannot disagree with the code that applies it — which is the
    property E2-07's third criterion is really asking for. A test reads this; the
    prose in `mock-ai/README.md` is for a person and is the copy that can go
    stale, which is why nothing asserts against it.
    """
    return {
        "markers": dict(MARKERS),
        "substantive_minimum_characters": SUBSTANTIVE_MINIMUM_CHARACTERS,
        "stall_seconds": STALL_SECONDS,
        "comment_marker_line": MARKER_LINE,
        "verdicts": [SUBSTANTIVE, INSUFFICIENT, NONSENSE],
        "rule_order": [
            "1. A wrong-answer marker anywhere in the comment decides the answer: "
            f"{UNAVAILABLE_MARKER} answers HTTP {UNAVAILABLE_STATUS}, {REFUSED_MARKER} answers "
            f"HTTP {REFUSED_STATUS}, {MALFORMED_MARKER} answers 200 with a payload the contract "
            f"refuses, and {STALL_MARKER} answers {SUBSTANTIVE} after {STALL_SECONDS} seconds.",
            f"2. A forced-verdict marker names its own verdict: {SUBSTANTIVE_MARKER}, "
            f"{INSUFFICIENT_MARKER}, {NONSENSE_MARKER}.",
            f"3. Otherwise a comment of fewer than {SUBSTANTIVE_MINIMUM_CHARACTERS} characters is "
            f"{INSUFFICIENT} and anything else is {SUBSTANTIVE}. {NONSENSE} is reachable only by "
            "its marker.",
        ],
    }
