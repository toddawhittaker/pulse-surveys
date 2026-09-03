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

TASKS: tuple[EvalTask, ...] = (VALIDITY, THREAT)
