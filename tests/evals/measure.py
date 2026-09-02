"""Precision and recall over one task's answers — E2-12.

SPEC §9.3 asks for "per-task precision/recall floors" and does not say what the
positive class is. A three-way verdict has no single precision and recall pair
until somebody says which class the pair is about, so each task's package states
its choice beside its cases and argues it there; this module only does the
arithmetic.

**Both empty denominators resolve toward failing.** A model that never answers
the positive class has no precision to report, and treating that as 1.0 would let
a classifier which answers `insufficient` to everything clear a precision floor
of any height. It scores 0.0 instead. A set holding no positive case cannot
measure recall at all, and that is a broken set rather than a low score, so the
runner refuses it (`docs/MISTAKES.md` entry 3 — a test that can be satisfied by
emptiness).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from tests.evals.declarations import EvalCase


@dataclass(frozen=True)
class Measurement:
    """What one task's run came to, as counts and as the two rates."""

    cases: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    disagreements: tuple[tuple[str, Any, Any], ...]

    @property
    def precision(self) -> float:
        """Of the answers that named the positive class, the share that were right."""
        answered_positive = self.true_positives + self.false_positives
        if answered_positive == 0:
            return 0.0
        return self.true_positives / answered_positive

    @property
    def recall(self) -> float:
        """Of the cases that are the positive class, the share the model found."""
        actually_positive = self.true_positives + self.false_negatives
        if actually_positive == 0:
            return 0.0
        return self.true_positives / actually_positive


def measure(cases: Sequence[EvalCase], answers: Sequence[Any], positive: Any) -> Measurement:
    """Score `answers` against `cases`, one answer per case, in order.

    The two sequences are required to be the same length: a run that lost an
    answer would otherwise be scored against a shifted set, and every rate it
    produced would be about pairs nobody made.
    """
    if len(cases) != len(answers):
        raise ValueError(
            f"{len(cases)} cases and {len(answers)} answers. Every case gets exactly one "
            "answer; a mismatch means the run dropped one, and scoring a shifted set "
            "produces two rates about pairs that were never made."
        )

    true_positives = false_positives = false_negatives = true_negatives = 0
    disagreements: list[tuple[str, Any, Any]] = []
    for case, answer in zip(cases, answers, strict=True):
        expected_positive = case.expected == positive
        answered_positive = answer == positive
        if expected_positive and answered_positive:
            true_positives += 1
        elif answered_positive:
            false_positives += 1
        elif expected_positive:
            false_negatives += 1
        else:
            true_negatives += 1
        if case.expected != answer:
            disagreements.append((case.case_id, case.expected, answer))

    return Measurement(
        cases=len(cases),
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        true_negatives=true_negatives,
        disagreements=tuple(disagreements),
    )


def holds_a_positive_case(cases: Sequence[EvalCase], positive: Any) -> bool:
    """Whether recall can be measured over this set at all."""
    return any(case.expected == positive for case in cases)
