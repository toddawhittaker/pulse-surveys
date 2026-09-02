"""The comment-validity precision and recall floors — E2-12.

**These numbers are not written yet, and that is the state this file ships in.**
SPEC §9.3's gate is "prompt or model changes must meet per-task precision/recall
floors", and a floor picked before anything was measured is a number chosen to
make the first run pass. So the declaration below is
`awaiting_measurement`, the runner refuses on it, and the numbers are filled in
from the first real run against `validity.v1` — recorded here with a sentence
saying what that run scored and how much headroom the floor leaves.

**Filling it in is one edit and it is deliberately conspicuous.** Replace the
call below with

    FLOORS = enforced(
        precision=<measured>,
        recall=<measured>,
        note="Measured against validity.v1 on <model id> on <date>: precision "
             "<p>, recall <r> over the 98 cases in cases.py. The floor sits "
             "<margin> below each, which is <the reason>.",
    )

and nothing else in the repository changes. A floor moved later is a diff in this
file, in the directory of the set it governs — which is what
`CLAUDE.md`'s "floors move only in a deliberate PR whose subject is moving them"
needs in order to be visible to a reviewer.

**What the note has to say, and why it is a required argument.** A floor with no
provenance cannot be defended when it is later in the way: nobody can tell a
number measured with headroom from a number lowered last quarter to get a merge
through. `.claude/review-fixtures/eval-floor-lowered.diff` is the shape that
review pass exists to catch, and it catches it by reading the diff — so the diff
has to carry the argument.
"""

from __future__ import annotations

from tests.evals.declarations import TaskFloors, awaiting_measurement

FLOORS: TaskFloors = awaiting_measurement(
    note=(
        "Placeholder. The precision and recall floors for the comment-validity task are "
        "picked against the first real run of `python -m tests.evals.runner` over "
        "tests/evals/validity/cases.py against validity.v1, and written here with the "
        "measured figures and the headroom they leave. Until then the runner refuses "
        "rather than grading the set against nothing: SPEC §11 open question 4 asks for "
        "'its eval set and threshold', and the set without the threshold is half of it."
    )
)
