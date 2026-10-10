"""The moderation floor slot — held open, not set. E10's live run sets it.

The set exists (`cases.py`), the number does not, and the runner refuses a
deferred slot that carries cases. So the cases stay off the registry's slot, as
the summary cases do, until the pull request whose subject is setting the floor
measures them against a real provider and attaches them.
"""

from __future__ import annotations

from tests.evals.declarations import TaskFloors, deferred

FLOORS: TaskFloors = deferred(
    note=(
        "Not set. The moderation cases are in tests/evals/moderation/cases.py and the threat "
        "and self-harm cases in tests/evals/threat/cases.py; E10's first live run sets the "
        "numbers, in a pull request whose subject is setting them."
    )
)
