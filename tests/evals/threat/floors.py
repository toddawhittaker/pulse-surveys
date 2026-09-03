"""The threat and self-harm floor slot — held open, not set. E10 sets it.

SPEC §9.3: "threat/self-harm recall floor is the strictest in the suite (false
negatives are the expensive error)". `CLAUDE.md` goes further: it is a hard gate,
and lowering it is a safety decision and the repository owner's call.

Neither sentence can be true of a number nobody has. E6 builds the moderation
task, E10 builds the recall-floor eval work, and until one of them ships a set
there is nothing here to measure. So the slot is `deferred`: it carries no
precision, no recall and no cases, the runner names it in every report as
ungraded, and it never counts toward a pass.

**Why the slot exists at all rather than the task simply being absent.** A task
that is not in the registry is a task nobody is reminded about. This entry is
what makes "SPEC §9.3's strictest floor is not enforced yet" a line printed on
every eval run rather than a fact somebody has to go looking for — and it is the
structure E4, E6 and E10 add their sets to without reworking anything, which
E2-12's out-of-scope list requires.

**The one thing that must not happen here is a number without a set.** Writing a
recall figure into this file while `cases` stays empty would produce a task the
runner reports on and never grades, which is exactly the shape
`docs/MISTAKES.md` entry 9 is about — a gate cited as a guarantee and never
executed. The runner refuses that combination outright, and
`tests/unit/test_the_eval_runner_refuses_rather_than_reporting_a_pass.py`
asserts it in both directions.
"""

from __future__ import annotations

from tests.evals.declarations import TaskFloors, deferred

FLOORS: TaskFloors = deferred(
    note=(
        "Not set. SPEC §9.3 makes this the strictest floor in the suite and CLAUDE.md "
        "makes lowering it the repository owner's call; E6 builds the moderation task "
        "and E10 the recall-floor eval work, and neither the set nor the number is "
        "E2-12's to write. This slot is reported as ungraded on every run so that its "
        "absence is visible rather than merely true."
    )
)
