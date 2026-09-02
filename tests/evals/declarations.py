"""The types a task's eval set and its floor declaration are written in — E2-12.

Three floor states, and the difference between them is the whole of what stops
this gate reporting a pass it did not earn (`docs/MISTAKES.md` entry 9 — a gate
that has never failed is a comment).

**`ENFORCED`** — the numbers were measured against a real run and are recorded
here. The runner grades the task and compares.

**`AWAITING_MEASUREMENT`** — the set exists and the numbers do not yet. This is a
placeholder and the runner **refuses** on it: an unfilled floor is not a floor,
and a runner that skipped past one would exit 0 over a task nothing had graded.
It is the state SPEC §9.3's validity floor is in until the first live run
produces numbers to write down.

**`DEFERRED`** — the slot exists, the set is another epic's and so is the number.
The runner reports it and does not fail on it. This is the only state in which a
task with no cases is acceptable, and it is deliberately the one state that
carries no numbers at all: the moment somebody writes a number into a deferred
slot without a set, the declaration stops being deferred and the runner refuses.

SPEC §9.3 makes the threat and self-harm recall floor the strictest in the suite,
and `CLAUDE.md` makes lowering it a safety decision rather than an engineering
one. Neither statement is worth anything if the runner can pass a task it never
graded, which is why the states above are three rather than two.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class FloorStatus(enum.Enum):
    """Which of the three states a task's floor declaration is in."""

    ENFORCED = "enforced"
    AWAITING_MEASUREMENT = "awaiting_measurement"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class TaskFloors:
    """One task's precision and recall floors, in one of three states.

    Built through `enforced`, `awaiting_measurement` or `deferred` rather than
    directly, so a declaration cannot be written in a state the runner has no
    rule for.
    """

    status: FloorStatus
    precision: float | None
    recall: float | None
    note: str

    @property
    def carries_numbers(self) -> bool:
        """Whether this declaration states a floor at all."""
        return self.precision is not None or self.recall is not None


def enforced(*, precision: float, recall: float, note: str) -> TaskFloors:
    """A floor measured against a real run and enforced from now on.

    `note` records how the numbers were picked, which SPEC §9.3's gate is
    unreadable without: a floor with no provenance is a number somebody chose to
    make a run pass.
    """
    return TaskFloors(status=FloorStatus.ENFORCED, precision=precision, recall=recall, note=note)


def awaiting_measurement(*, note: str) -> TaskFloors:
    """The placeholder: a set exists, the numbers do not, and the runner refuses.

    Deliberately not "enforce nothing and pass". A task whose set is graded
    against no floor is a run that produces a number nobody compares, and the
    green it prints is indistinguishable from a real one.
    """
    return TaskFloors(
        status=FloorStatus.AWAITING_MEASUREMENT, precision=None, recall=None, note=note
    )


def deferred(*, note: str) -> TaskFloors:
    """A slot held open for the epic that builds the task, with no set and no number."""
    return TaskFloors(status=FloorStatus.DEFERRED, precision=None, recall=None, note=note)


@dataclass(frozen=True)
class EvalCase:
    """One case: a comment, the verdict it should draw, and the prompt it is pinned to.

    `expected` is a member of the task's own verdict enum out of
    `app.ai.contracts`, never a string. SPEC §7.4 makes the eval fixture the same
    typed object the task returns, so a contract change breaks the set rather
    than passing quietly, and ADR 0030 makes a bare-string comparison the thing
    that silently never matches.

    `prompt_version` is the prompt file's path stem (ADR 0031), and ADR 0032
    makes that file immutable once a classification cites it — so a case pinned
    to `validity.v1` states which text it was written against, and a run under a
    later prompt is a different measurement rather than the same one.
    """

    case_id: str
    comment: str
    expected: Any
    prompt_version: str
    family: str


@dataclass(frozen=True)
class EvalTask:
    """One task the runner knows about: its cases, its floor, and how to grade it.

    `positive` is the verdict precision and recall are computed *about*. §9.3
    asks for one pair per task and a three-way verdict has no single pair without
    saying which class is positive; each task's own package states its choice and
    argues it there.

    `classifier` builds the live callable that answers one comment. It is a
    factory rather than a callable so that nothing constructs a gateway — or
    reads a credential — for a task the runner is not going to grade.
    """

    name: str
    floors: TaskFloors
    cases: tuple[EvalCase, ...]
    positive: Any
    prompt_version: str | None
    classifier: Callable[[], Callable[[str], Any]] | None


class EvalRefusalError(Exception):
    """The runner declined to report on something, and says what in one sentence.

    Every route out of the runner that is not a graded comparison raises this: a
    missing credential, a floor with no set, a placeholder nobody filled in, a set
    pinned to a prompt the gateway is not running. It exists so that none of those
    can leave through the same door as a pass.
    """
