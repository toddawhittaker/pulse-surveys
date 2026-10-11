"""The check's theme may carry no count; the weekly summary's theme still must — residue B.

E7-04's work order, residue B from the breakdown review (PR #306): "Keep the
summary's contract strict. Do NOT make `CommentTheme.comment_count` optional. Add
a separate check-only theme type (`CheckTheme` with `comment_count: int | None`)
used by `DraftCheckOutput`. A unit test proves the weekly summary still rejects a
theme with no count."

**Why two types rather than one optional field.** The weekly summary's count is
what E4-06's store-time guard refuses an overclaim of, and what the report shows
beside a shown stream's theme. A theme type with an optional count, shared by the
summary, would let a summary store a theme with no count — and the summary task
would then have a way to answer that no reviewer asked for. The check needs the
optional count for one reason only, decision 12's held stream.

**Built through the contracts, with a control first.** Every refusal is asserted
beside the same construction with a count, which is accepted, so a refusal is
attributable to the missing count and to nothing else in the model
(`docs/MISTAKES.md` entry 3).

**Which failure a red is.** Before E7-04: `test_the_check_theme_admits_*` fails
naming the missing `CheckTheme`; the summary tests are green on arrival — they
are the guard against the tempting edit, and the mutation below is their proof.
"""

from typing import Any

import pytest
from fixtures.response_draft import (
    CHECK_THEME,
    COMMENT_THEME,
    COUNT_FIELD,
    DRAFT_CHECK_OUTPUT,
    LABEL_FIELD,
    WEEKLY_SUMMARY_OUTPUT,
    contract,
    contracts,
    referenced_models,
)
from pydantic import ValidationError

A_LABEL = "e7-04 a theme"


@pytest.fixture(autouse=True)
def _a_stated_environment(configured_env: dict[str, str]) -> None:
    """`app.ai.contracts` is imported; the environment is stated (`docs/MISTAKES.md` entry 40)."""


def refused(model: Any, values: dict[str, Any]) -> bool:
    try:
        model(**values)
    except ValidationError:
        return True
    return False


def a_summary(themes: list[dict[str, Any]]) -> dict[str, Any]:
    """A `WeeklySummaryOutput` payload, as `tests/fixtures/summary_job.py`'s double builds one."""
    stream = next(iter(contracts().CommentStream))
    return {
        "stream": stream,
        "summary": "e7-04 a summary",
        "themes": themes,
        "prompt_version": "summary.v1",
        "model_id": "e7-04-a-model",
    }


def test_the_summary_theme_still_refuses_a_missing_count() -> None:
    """`CommentTheme` with `comment_count=None`, and with none given: both refused.

    **The mutation this kills:** `comment_count: int | None` on `CommentTheme` — the
    one-line edit the check's need invites, and the one residue B forbids.
    """
    theme = contract(COMMENT_THEME)
    assert not refused(theme, {LABEL_FIELD: A_LABEL, COUNT_FIELD: 3}), (
        "The control: `CommentTheme` refused a label with a count, so nothing below is about the "
        "count."
    )
    assert refused(theme, {LABEL_FIELD: A_LABEL, COUNT_FIELD: None}), (
        "`CommentTheme` accepted `comment_count=None`. Residue B: 'Do NOT make "
        "`CommentTheme.comment_count` optional.'"
    )
    assert refused(
        theme, {LABEL_FIELD: A_LABEL}
    ), "`CommentTheme` accepted a theme with no `comment_count` at all."


def test_the_weekly_summary_refuses_a_theme_with_no_count() -> None:
    """The same rule one level up, where a summary is validated: a countless theme is refused.

    **The mutation this kills:** the summary contract re-typed to take the check's
    theme (`themes: tuple[CheckTheme, ...]`), which keeps `CommentTheme` strict and
    loosens the summary anyway. **The control:** the same summary with a count.
    """
    output = contract(WEEKLY_SUMMARY_OUTPUT)
    counted = a_summary([{LABEL_FIELD: A_LABEL, COUNT_FIELD: 2}])
    assert not refused(
        output, counted
    ), f"The control: `{WEEKLY_SUMMARY_OUTPUT}` refused {counted!r}, a summary with a counted theme."
    countless = a_summary([{LABEL_FIELD: A_LABEL, COUNT_FIELD: None}])
    assert refused(output, countless), (
        f"`{WEEKLY_SUMMARY_OUTPUT}` accepted a theme with no count. Residue B: 'A unit test proves "
        "the weekly summary still rejects a theme with no count.'"
    )


@pytest.mark.parametrize("count", (None, 4), ids=("no-count", "a-count"))
def test_the_check_theme_admits_a_count_or_none(count: int | None) -> None:
    """`CheckTheme(label, comment_count=None)` and with an int: both accepted, the value kept.

    **The mutation this kills:** a `CheckTheme` that is `CommentTheme` under another
    name (the held theme cannot be named), or one that drops the count it was given.
    """
    theme = contract(CHECK_THEME)
    built = theme(**{LABEL_FIELD: A_LABEL, COUNT_FIELD: count})
    assert (
        getattr(built, COUNT_FIELD) == count and getattr(built, LABEL_FIELD) == A_LABEL
    ), f"`CheckTheme` built {built!r} from a label and a count of {count!r}."


def test_the_draft_check_output_uses_the_check_theme_and_the_summary_does_not() -> None:
    """Which contract composes which theme: the check `CheckTheme`, the summary `CommentTheme`.

    **The mutation this kills:** `DraftCheckOutput` left on `CommentTheme` (a held
    theme then cannot be answered at all, and an implementer "fixes" that by
    loosening `CommentTheme`), or the summary moved onto `CheckTheme`.
    """
    check_theme, comment_theme = contract(CHECK_THEME), contract(COMMENT_THEME)
    check_output, summary_output = contract(DRAFT_CHECK_OUTPUT), contract(WEEKLY_SUMMARY_OUTPUT)

    def composed(model: Any) -> set[type]:
        found: set[type] = set()
        for model_field in model.model_fields.values():
            found |= referenced_models(model_field.annotation)
        return found

    assert check_theme in composed(check_output), (
        f"`{DRAFT_CHECK_OUTPUT}` composes no `{CHECK_THEME}`; it composes "
        f"{sorted(t.__name__ for t in composed(check_output))}."
    )
    assert comment_theme not in composed(
        check_output
    ), f"`{DRAFT_CHECK_OUTPUT}` still composes `{COMMENT_THEME}`."
    assert comment_theme in composed(
        summary_output
    ), f"`{WEEKLY_SUMMARY_OUTPUT}` no longer composes `{COMMENT_THEME}`."
    assert check_theme not in composed(
        summary_output
    ), f"`{WEEKLY_SUMMARY_OUTPUT}` composes `{CHECK_THEME}`, whose count is optional."
