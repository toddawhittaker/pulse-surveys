"""The draft-check eval set, and what it means for a check to hold — E7-04.

SPEC §5.3: the check "compares the draft against the week's main comment themes
and quietly names any theme not yet addressed (with its comment count). For a
stream held below the n-threshold, the check names the theme without a count."

**A check can fail in five ways, and the grader names each.** It can name a theme
no stored summary holds; give a shown theme a count other than the stored one, or
none; give a held theme any count; miss a theme the draft does not address (the
recall half); or name a theme the draft plainly addresses (the precision half,
which is what makes the check quiet rather than nagging). The first three are the
product's structural refusals and are asserted in pytest too; they are graded here
as well because a live run's answer is what reaches them.

**Typed through the contract.** Each case's expected answer is built as the
task's own `CheckTheme` objects by `expected_themes`, handed the contracts module
by its caller, so a contract change breaks this set where it is used (SPEC §9.3),
while this module itself imports no application code (`docs/MISTAKES.md` entry 44:
an import here would turn every red in the companion test into a collection error).

**No number is declared, and nothing here reaches a provider.**
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from tests.evals.response_draft.cases import (
    A_SHOWN_WEEK,
    A_WEEK_WITH_A_HELD_STREAM,
    StoredSummary,
)

# The ticket's `backend/app/ai/prompts/draft_check.v1.md`, written out on purpose.
PROMPT_VERSION = "draft_check.v1"

NOTHING_ADDRESSED = "nothing_addressed"
EVERYTHING_ADDRESSED = "everything_addressed"
PARTLY_ADDRESSED = "partly_addressed"
HELD_THEME_WITHOUT_COUNT = "held_theme_named_without_count"


@dataclass(frozen=True)
class CheckCase:
    case_id: str
    family: str
    summaries: tuple[StoredSummary, ...]
    draft: str
    unaddressed: tuple[str, ...]
    prompt_version: str = PROMPT_VERSION

    def stored(self) -> dict[str, int | None]:
        """Every stored theme, label to the count the check may name it with."""
        return {
            theme.label: (None if summary.held else theme.comment_count)
            for summary in self.summaries
            for theme in summary.themes
        }


def expected_pairs(case: CheckCase) -> tuple[tuple[str, int | None], ...]:
    stored = case.stored()
    return tuple((label, stored[label]) for label in case.unaddressed)


def expected_themes(case: CheckCase, contracts: Any) -> tuple[Any, ...]:
    """The case's expected answer as `CheckTheme` objects, through the task's contract."""
    theme = contracts.CheckTheme
    return tuple(theme(label=label, comment_count=count) for label, count in expected_pairs(case))


def grade(case: CheckCase, answered: Sequence[tuple[str, int | None]]) -> list[str]:
    """Every way an answer (label, count pairs) fails `case`; empty when it holds."""
    stored = case.stored()
    failures: list[str] = []
    for label, count in answered:
        if label not in stored:
            failures.append(f"names {label!r}, which no stored summary holds")
        elif stored[label] is None and count is not None:
            failures.append(f"gives the held theme {label!r} a count ({count})")
        elif stored[label] is not None and count != stored[label]:
            failures.append(f"gives {label!r} {count!r} where the summary stores {stored[label]}")
    named = {label for label, _count in answered}
    failures += [f"misses {label!r}" for label in case.unaddressed if label not in named]
    failures += [
        f"names {label!r}, which the draft addresses"
        for label in sorted(named & set(stored) - set(case.unaddressed))
    ]
    return failures


CASES: tuple[CheckCase, ...] = (
    CheckCase(
        case_id="dc-na-001",
        family=NOTHING_ADDRESSED,
        summaries=A_SHOWN_WEEK,
        draft="Thank you all for completing the survey this week. See you on Tuesday.",
        unaddressed=(
            "lectures move too fast",
            "office hours help",
            "lab feedback arrives too late",
        ),
    ),
    CheckCase(
        case_id="dc-ea-001",
        family=EVERYTHING_ADDRESSED,
        summaries=A_SHOWN_WEEK,
        draft=(
            "You told me the proofs move too fast, so I will slow down and post the derivations. "
            "I am glad office hours help and will keep them. I will return lab report feedback "
            "within five days so it arrives before the next report."
        ),
        unaddressed=(),
    ),
    CheckCase(
        case_id="dc-pa-001",
        family=PARTLY_ADDRESSED,
        summaries=A_SHOWN_WEEK,
        draft="You told me the proofs move too fast, so I will slow down and post the derivations.",
        unaddressed=("office hours help", "lab feedback arrives too late"),
    ),
    CheckCase(
        case_id="dc-hc-001",
        family=HELD_THEME_WITHOUT_COUNT,
        summaries=A_WEEK_WITH_A_HELD_STREAM,
        draft="You told me the proofs move too fast, so I will slow down and post the derivations.",
        unaddressed=("office hours help", "forum questions go unanswered"),
    ),
)
