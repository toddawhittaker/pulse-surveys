"""Every task the eval runner knows about — E2-12.

One entry per task, joining that task's cases to that task's floor declaration.
The runner walks this tuple and nothing else, so a task added here is graded and
a task not here is invisible — which is why SPEC §9.3's strictest floor has an
entry with no set rather than no entry.

E2-12's out-of-scope list requires that "the structure here must accept them
without rework" for the moderation, summary and threat sets each epic builds. An
`EvalTask` is what that acceptance looks like: a name, a floor declaration, a
tuple of typed cases, the verdict precision and recall are about, the prompt
version the set is pinned to, and a factory that builds the live classifier.
"""

from __future__ import annotations

from tests.evals.declarations import EvalTask
from tests.evals.live import build_validity_classifier
from tests.evals.summary import floors as summary_floors
from tests.evals.threat import floors as threat_floors
from tests.evals.validity import cases as validity_cases
from tests.evals.validity import floors as validity_floors

VALIDITY = EvalTask(
    name="validity",
    floors=validity_floors.FLOORS,
    cases=validity_cases.CASES,
    positive=validity_cases.POSITIVE_VERDICT,
    prompt_version=validity_cases.PROMPT_VERSION,
    classifier=build_validity_classifier,
)

# SPEC §7.4's third task, and E4-05's fifth acceptance criterion answered in the
# one state that answers it honestly: "either this ticket sets an enforcing floor
# for the summary task's eval metrics, or the ADR records why the floor waits (and
# for what measurement), the way E2 staged the validity floors."
#
# **Deferred rather than awaiting measurement, and the difference is this pull
# request's CI run.** `AWAITING_MEASUREMENT` is a refusal: the runner exits
# non-zero on it, and this diff touches `backend/app/ai/`, so the eval job runs
# live here and would go red over a task nobody has measured. `DEFERRED` is the
# one state that carries no set and no number, which is exactly where the summary
# task stands until a real provider has answered its cases once.
#
# **The cases exist and are not attached here on purpose.** They live in
# `tests/evals/summary/cases.py` with the checks that grade them, and they are
# exercised offline by `tests/unit/test_the_summary_eval_cases_can_go_red.py` —
# the runner refuses a deferred slot that has acquired a set, and a set wired into
# this tuple would spend one provider call per case on every AI-touching pull
# request from now until the floor is set.
SUMMARY = EvalTask(
    name="summary",
    floors=summary_floors.FLOORS,
    cases=(),
    positive=None,
    prompt_version=None,
    classifier=None,
)

# One slot for the pair, following SPEC §9.3's own phrase "threat/self-harm
# recall floor". ADR 0030 keeps `THREAT` and `SELF_HARM` two enum members that
# may never be merged or aliased, so E10 is free to split this into two entries
# when it builds the set; nothing here depends on it staying one.
THREAT = EvalTask(
    name="threat",
    floors=threat_floors.FLOORS,
    cases=(),
    positive=None,
    prompt_version=None,
    classifier=None,
)

TASKS: tuple[EvalTask, ...] = (VALIDITY, SUMMARY, THREAT)
