"""The bumped small-N summary prompt states a per-stream premise — ticket E6-02, done-when 7.

`summary.v2` told the model that "fewer students answered this week"
(`docs/tickets/e6/carried-from-e5.md`, "Summaries written before the per-stream
rule"). Since ADR 0182 a stream is small-N by its own commenter count, so for a
thin stream in a full week that sentence is false. ADR 0188 bumps the small-N
prompt to `summary.v3`, which speaks of the stream.

What the model does with the prompt is measured by the eval set
(`tests/evals/summary/cases.py`, the thin-stream case), not here. This module
asserts only the text: the false premise is gone from the new file and the new
file names the stream.

**The search has a canary** (`docs/MISTAKES.md` entry 3): the same normalized
phrase is required to be present in `summary.v2.md`, which ADR 0032 makes
immutable. If that canary is red, the search has gone blind (the phrase in v2 is
spelled differently from the ticket's quotation), and the absence below proves
nothing until the phrase is corrected.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIRECTORY = REPO_ROOT / "backend" / "app" / "ai" / "prompts"

# The false premise, in the words the ticket and `carried-from-e5.md` quote from v2.
WEEK_PREMISE = "answered this week"
CANARY = "fewer students answered this week"


def normalized(name: str) -> str:
    """A prompt file's text, lower-cased, with every run of whitespace made one space."""
    return re.sub(r"\s+", " ", (PROMPTS_DIRECTORY / name).read_text(encoding="utf-8")).lower()


def test_the_old_small_n_prompt_still_carries_the_week_premise_so_the_search_can_see() -> None:
    """The canary: the search below finds the premise where it is known to be."""
    assert CANARY in normalized("summary.v2.md"), (
        f"{CANARY!r} is not in summary.v2.md once whitespace and case are normalized. The "
        "ticket quotes that phrase from v2; if v2 spells it differently, correct the phrase "
        "here, or the absence test beside this one is searching for nothing."
    )


def test_the_bumped_small_n_prompt_does_not_say_the_week_was_thin() -> None:
    """Done-when 7: v3 drops "answered this week", which is false for a thin stream in a full week.

    **The mutation it kills:** `summary.v3.md` copied from v2 with only the
    version changed, so the model is still told the week was thin.
    """
    assert WEEK_PREMISE not in normalized("summary.v3.md"), (
        f"summary.v3.md still says {WEEK_PREMISE!r}. A stream is small-N by its own commenter "
        "count (ADR 0182), so in a well-answered week this premise is false; the bumped prompt "
        "must speak of the stream."
    )


def test_the_bumped_small_n_prompt_names_the_stream() -> None:
    """Done-when 7: v3 speaks of the stream, the present half beside the absence above."""
    assert "stream" in normalized("summary.v3.md"), (
        "summary.v3.md never uses the word 'stream'. Done-when 7 asks the bumped small-N "
        "prompt to speak of the stream rather than the week."
    )
