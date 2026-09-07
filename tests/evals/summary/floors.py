"""The weekly-summary floor slot — held open, and the ADR says what it waits for.

E4-05's fifth acceptance criterion refuses silence: "either this ticket sets an
enforcing floor for the summary task's eval metrics, or the ADR records why the
floor waits (and for what measurement), the way E2 staged the validity floors."
This file is the second half of that answer, and it is the same staging the
comment-validity floors went through — cases first, numbers after one clean run
against a real provider, dated and owned.

**Why a number cannot honestly be written here yet.** The validity floors were
sized from measured run-to-run variance on a named model under a named prompt
(`tests/evals/README.md` carries the arithmetic). No such run exists for
`summary.v1`, and a figure invented ahead of one is a floor nobody measured — the
thing `docs/MISTAKES.md` entry 9 is about, wearing a green tick.

**Deferred rather than awaiting measurement**, and the difference is not
bookkeeping. `AWAITING_MEASUREMENT` makes the runner refuse, which is right for a
task whose set is wired in and whose number is missing; it would make CI's live
eval job red on every AI-touching pull request from this one onward, over work
nobody could do without a measurement run. `DEFERRED` is the state that carries
no set and no number, and the summary cases are deliberately not attached to this
slot: they live in `tests/evals/summary/cases.py` with the checks that grade them
and are exercised offline, so this ticket ships a set that is known capable of
failing without spending a provider call per case on every merge.

**What moving this looks like.** One deliberate pull request whose subject is
setting the floor: a live run over the cases, the figures and their provenance
written into this file, `enforced(...)` in place of `deferred(...)`, and the cases
attached to the registry's summary slot. `CLAUDE.md` governs the direction of
travel from then on — floors move only in a pull request that says so.
"""

from __future__ import annotations

from tests.evals.declarations import TaskFloors, deferred

FLOORS: TaskFloors = deferred(
    note=(
        "Not set. E4-05 ships SPEC §5.1's contract as cases in tests/evals/summary/cases.py "
        "with the checks that grade them and a sycophantic variant they are proven to fail "
        "against, and stages the numbers the way E2 staged the validity floors: the first "
        "clean run against a real provider sets them, in a pull request whose subject is "
        "setting them. Until then this slot is reported as ungraded on every run so that its "
        "absence is visible rather than merely true, and the cases are exercised offline by "
        "tests/unit/test_the_summary_eval_cases_can_go_red.py rather than by this runner."
    )
)
