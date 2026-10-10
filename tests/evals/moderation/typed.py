"""How a moderation case is built: through the task's own output contract.

Shared by `tests/evals/moderation/cases.py` and `tests/evals/threat/cases.py`.
"""

from __future__ import annotations

from app.ai.contracts import ModerationOutput, ModerationVerdict
from tests.evals.declarations import EvalCase

# The prompt file the set was written against (ADR 0031, ADR 0032). Written out,
# not imported from `app.ai.tasks`, so a prompt bump has to be met here on purpose.
PROMPT_VERSION = "moderation.v1"

# The model id a case's typed output carries. No model answered a case.
NOT_A_MODEL = "eval-case"


def verdict(token: str) -> ModerationVerdict:
    """`token` validated through the task's own output contract."""
    return ModerationOutput(
        verdict=token, prompt_version=PROMPT_VERSION, model_id=NOT_A_MODEL
    ).verdict


def case(case_id: str, comment: str, token: str) -> EvalCase:
    """One case, its family the verdict it should draw."""
    return EvalCase(
        case_id=case_id,
        comment=comment,
        expected=verdict(token),
        prompt_version=PROMPT_VERSION,
        family=token,
    )
