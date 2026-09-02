"""A set the current prompt fails, so the gate can be watched going red — E2-12.

`docs/MISTAKES.md` entry 9: **before citing a guard, execute it against the case
you claim it stops.** A guard that has never been run is a comment, and an eval
floor is the purest form of that — it produces a green line on every run that
clears it, and nothing about that line says whether a run *could* fail. E2-12's
scope asks for the flip to be "proven by breaking, both ways": a planted floor
breach that runs red through the real runner, beside the real set that runs green.

**Every expected verdict in this module is deliberately wrong.** Ten obviously
substantive comments are labelled `insufficient`, and ten obviously contentless
ones are labelled `substantive`. The model answers each of them correctly, the
labels say otherwise, and both floors collapse: no true positives, so precision is
0.0, and no positive case found, so recall is 0.0. That is what "a case set the
current prompt fails" means here — the prompt is right and the set is not, which
is the only way to make a passing classifier fail on demand without breaking the
prompt, the floors or the model.

**It is inert in an ordinary run, by construction rather than by a flag.**
`BREACH_TASK` is not in `tests/evals/registry.py`'s `TASKS`, which is the only
tuple `evaluate()` walks, so `python -m tests.evals.runner --enforce-floors`
cannot reach this file. The runner loads it only under `--demonstrate-breach`, and
that mode cannot exit 0: a breach is a failure, and a breach that did not breach
is a failure with a different message, because a demonstration that proved nothing
is worse than none.

**Nothing here may ever be merged into `cases.py`.** A mislabelled case in the
real set is a floor measured against a wrong answer, in the direction nobody
checks.
`tests/unit/test_the_planted_floor_breach_can_be_demonstrated.py` asserts that no
comment appears in both, and that this task stays out of the registry.

**Why the labels are inverted rather than the comments made hard.** Writing
comments the model genuinely gets wrong would be a set whose redness depends on the
model staying bad at them — it would go green on a better model, which is the
opposite of what a demonstration needs, and it would quietly stop being a
demonstration with nothing saying so. Inverted labels fail for a reason that does
not move: the better the classifier, the harder this set fails.
"""

from __future__ import annotations

from tests.evals.declarations import EvalCase, EvalTask
from tests.evals.live import build_validity_classifier
from tests.evals.validity.cases import (
    INSUFFICIENT,
    POSITIVE_VERDICT,
    PROMPT_VERSION,
    SUBSTANTIVE,
)
from tests.evals.validity.floors import FLOORS

BREACH_FAMILY = "breach"

# Substantive by any reading, labelled `insufficient`. The model answers
# `substantive`, the label says otherwise, and each one becomes a false positive:
# precision 53/(53+k) with no true positives at all is 0.0.
_LABELLED_INSUFFICIENT = (
    "The Tuesday lab ran out of reagents halfway through the second experiment.",
    "The grading rubric for the essay does not mention the citation style we were taught.",
    "I could not follow the proof on slide fourteen because two of the steps were missing.",
    "The group project deadline lands on the same day as the midterm for this course.",
    "The recommended textbook edition is out of print and the library holds one copy.",
    "Recording the seminar would help; I missed the second half for a clinical placement.",
    "The problem set assumed matrix algebra that the prerequisite course does not cover.",
    "Feedback on draft one arrived the morning draft two was due, so I could not use it.",
    "The online quiz timed out at twenty minutes although the brief said thirty.",
    "Working through a real case study before the theory made the theory much clearer.",
)

# Contentless by any reading, labelled `substantive`. The model answers
# `insufficient` or `nonsense` — either is a negative for the positive class — and
# each becomes a false negative, taking recall to 0.0.
#
# None of these appears in `cases.py`, which the companion test asserts: a comment
# in both sets would be labelled two ways, and whichever run met it second would
# be measuring against the other one's answer.
_LABELLED_SUBSTANTIVE = (
    "meh",
    "yep",
    "sure",
    "whatever",
    "no thoughts",
    "it was a class",
    "nil",
    "nothing to add",
    "cool",
    "fine i guess",
)


def _breach_cases() -> tuple[EvalCase, ...]:
    """The twenty mislabelled cases, pinned to the prompt the real set is pinned to."""
    inverted: list[EvalCase] = []
    for index, comment in enumerate(_LABELLED_INSUFFICIENT, start=1):
        inverted.append(
            EvalCase(
                case_id=f"bx-fp-{index:03d}",
                comment=comment,
                expected=INSUFFICIENT,
                prompt_version=PROMPT_VERSION,
                family=BREACH_FAMILY,
            )
        )
    for index, comment in enumerate(_LABELLED_SUBSTANTIVE, start=1):
        inverted.append(
            EvalCase(
                case_id=f"bx-fn-{index:03d}",
                comment=comment,
                expected=SUBSTANTIVE,
                prompt_version=PROMPT_VERSION,
                family=BREACH_FAMILY,
            )
        )
    return tuple(inverted)


BREACH_CASES: tuple[EvalCase, ...] = _breach_cases()

# The same floors the real set is graded against, imported rather than restated.
# That is the whole point of the demonstration: it shows *these* numbers refusing
# a run, not some stricter pair invented to make refusing easy. A copy here could
# drift, and a drifted copy would demonstrate a floor nobody enforces
# (`docs/MISTAKES.md` entry 19).
BREACH_TASK = EvalTask(
    name="validity-breach",
    floors=FLOORS,
    cases=BREACH_CASES,
    positive=POSITIVE_VERDICT,
    prompt_version=PROMPT_VERSION,
    classifier=build_validity_classifier,
)
