"""Below the threshold a theme carries no count, anywhere — E7-04 done-when 3, and residue B.

> For a stream held below the threshold, neither task's prompt nor the check's
> payload carries a per-theme count. The check names the theme without a count,
> and the published-text path gets no count to repeat. Themes are read through
> the same filter as `_stored_summaries`: an old-format (`summary.v1`) row of a
> held stream gives no themes. Each case is tested beside a shown stream that
> does carry its counts. Marked `invariant`.

The epic's decision 12, and SPEC §5.3: "For a stream held below the n-threshold,
the check names the theme without a count, because a per-week count of a small
stream's comments is the participation trace §5.2 rules out." The work order's
residue B adds the check's rule both ways: a held theme with a count refused, a
shown theme without one refused, each beside its accepted twin (the shown half is
in `test_the_draft_check_names_only_stored_themes.py`).

**How a count is looked for.** The stored counts in this world are numbers no
other planted text carries (`assert_the_planted_texts_are_what_this_file_says`), and
`carries_number` finds one only as a number of its own — not inside a uuid's hex or
a longer number. Each absence stands beside two presences in the same request: the
held theme's *label* (so the theme reached the prompt and only its count did not)
and the shown theme's *count* (so counts do reach the prompt, and the search is not
blind to numbers).

**`docs/MISTAKES.md` entry 50.** A theme's count is a count of comments, not of
people; nothing here compares it with the threshold, and the threshold is read off
the report the instructor reads, never off a theme.

**Which failure a red is.** Before E7-04: a FAILED naming the missing route or
`CheckTheme`. Once built, a mutation fails an assertion naming the leaked number.
"""

from typing import Any

import pytest
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.response_draft import (
    COUNT_FIELD,
    HELD_THEME,
    HELD_THEME_COUNT,
    HELD_V1_SUMMARY_TEXT,
    HELD_V1_THEME,
    HELD_V1_THEME_COUNT,
    LABEL_FIELD,
    ORDINARY_SUMMARY_VERSION,
    SHOWN_SUMMARY_TEXT,
    SHOWN_THEME_A,
    SHOWN_THEME_A_COUNT,
    DraftDoor,
    assert_unusable,
    carries_number,
    check_with,
    unaddressed_of,
    what_each_task_sent,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


def served_pairs(answered: Any) -> list[tuple[Any, Any]]:
    return [(theme.get(LABEL_FIELD), theme.get(COUNT_FIELD)) for theme in unaddressed_of(answered)]


def test_neither_prompt_carries_a_held_themes_count_and_both_carry_a_shown_ones(
    draft_door: DraftDoor,
) -> None:
    """The prompt half: the held theme by name only, the shown theme with its count.

    **The mutation this kills:** the gather rendering every stored theme with its
    stored count, whatever the stream — the default a renderer written from
    `CommentTheme` produces. **The near misses it must survive:** a gather that
    drops held themes entirely passes the count assertion and fails the label
    canary (the check could then never name a held theme); a gather that strips
    every count passes the held assertion and fails the shown twin.
    """
    door = draft_door
    door.build_the_week()
    door.assert_the_streams_are(instructor_held=False, course_held=True)

    for task, text in what_each_task_sent(door).items():
        assert HELD_THEME in text, (
            f"The {task}'s request does not carry the held stream's stored theme {HELD_THEME!r}. "
            "The ticket feeds both tasks the stored themes, and the check names a held theme "
            "without a count — it cannot name one it was never given. This is also the canary for "
            "the absence below: without it, a missing count is a missing theme."
        )
        assert carries_number(text, SHOWN_THEME_A_COUNT), (
            f"The {task}'s request does not carry {SHOWN_THEME_A_COUNT}, the stored count of the "
            f"shown theme {SHOWN_THEME_A!r}. 'A shown stream's themes keep their stored counts', "
            "and without this twin the held assertion below passes against a gather that sends "
            "no number at all."
        )
        assert not carries_number(text, HELD_THEME_COUNT), (
            f"The {task}'s request carries {HELD_THEME_COUNT}, the stored count of the held "
            f"stream's theme {HELD_THEME!r}. Decision 12: below the threshold a theme carries no "
            "count — not in either task's prompt — because a per-week count of a small stream's "
            "comments is the participation trace SPEC §5.2 rules out, and a model handed the "
            "number can write it into a response every student reads."
        )


def test_the_check_names_a_held_theme_without_a_count(draft_door: DraftDoor) -> None:
    """The payload half: the held theme is served by name with a null count.

    **The mutation this kills:** a route that fills a held theme's count back in
    from the stored summary on the way out — the payload then carries the number
    the prompt was kept from. **The near miss:** dropping the held theme from the
    payload, which also carries no count and is refused here by the pair check.
    """
    door = draft_door
    door.build_the_week()

    answered = check_with(door, [(HELD_THEME, None)])
    assert served_pairs(answered) == [(HELD_THEME, None)], (
        f"The check served {served_pairs(answered)!r} for a model answer naming the held theme "
        f"{HELD_THEME!r} without a count. SPEC §5.3: 'the check names the theme without a count'."
    )
    assert not carries_number(answered.text, HELD_THEME_COUNT), (
        f"The check's payload carries {HELD_THEME_COUNT}, the held theme's stored count, somewhere "
        f"in {answered.text[:400]!r}. Decision 12: not in the check's payload."
    )


def test_a_check_naming_a_held_theme_with_its_stored_count_is_refused(
    draft_door: DraftDoor,
) -> None:
    """Residue B's held half: a held theme *with* a count, even the true one, is refused.

    The stored count rather than an invented one, on purpose: a check that
    compares every theme's count with the stored one, whatever the stream, accepts
    this answer — and serves the participation trace verbatim. Only a check that
    knows the stream is held refuses it. **The near miss it must survive:** the
    held theme with no count, accepted above.
    """
    door = draft_door
    door.build_the_week()
    answered = check_with(door, [(HELD_THEME, HELD_THEME_COUNT)])
    assert_unusable(
        answered,
        "check",
        f"names the held stream's theme {HELD_THEME!r} with a count ({HELD_THEME_COUNT})",
    )
    assert not carries_number(
        answered.text, HELD_THEME_COUNT
    ), f"The refusal carries the held theme's count: {answered.text[:400]!r}."


def test_a_check_naming_a_shown_theme_with_its_stored_count_is_accepted(
    draft_door: DraftDoor,
) -> None:
    """The twin of the held refusal above: in the same world, a shown theme keeps its count.

    **The mutation this kills:** a "no counts at all" check, which passes every
    held-stream assertion in this module and drops what SPEC §5.3 says the check is
    for — naming an unaddressed theme "with its comment count".
    """
    door = draft_door
    door.build_the_week()
    answered = check_with(door, [(SHOWN_THEME_A, SHOWN_THEME_A_COUNT)])
    assert served_pairs(answered) == [(SHOWN_THEME_A, SHOWN_THEME_A_COUNT)], (
        f"The check served {served_pairs(answered)!r} for the shown theme {SHOWN_THEME_A!r} named "
        f"with its stored count {SHOWN_THEME_A_COUNT}."
    )


def test_an_old_format_row_of_a_held_stream_gives_neither_prompt_a_theme(
    draft_door: DraftDoor,
) -> None:
    """A `summary.v1` row of the held stream: no summary, no theme, no count, in either prompt.

    ADR 0188: "A stored ordinary-mode (`summary.v1`) summary of a stream that is now
    held is not served" — the ordinary prompt may have quoted the comments the
    threshold withholds, and its themes are the same paragraph's labels. The
    ticket: themes are read "through the same filter as `_stored_summaries`".

    **The premise is read off the report**: it serves the shown stream's summary
    and not the held stream's v1 row, so the planted rows are the ones the filter is
    about. **The mutation this kills:** a themes read written beside
    `_stored_summaries` without its filter — the near miss the ticket names. **The
    twin:** the shown stream's `summary.v1` row, whose label and count do arrive.
    """
    door = draft_door
    door.build_the_week(held_summary_version=ORDINARY_SUMMARY_VERSION)
    body = door.assert_the_streams_are(instructor_held=False, course_held=True)
    assert door.served_summary(body, COURSE_STREAM) is None, (
        "The report serves the held stream's `summary.v1` row, so this world is not the one ADR "
        "0188's filter is about and nothing below would test it."
    )
    assert door.served_summary(
        body, INSTRUCTOR_STREAM
    ), "The report serves no summary for the shown stream, whose `summary.v1` row it should serve."

    for task, text in what_each_task_sent(door).items():
        assert SHOWN_THEME_A in text and carries_number(text, SHOWN_THEME_A_COUNT), (
            f"The {task}'s request does not carry the shown stream's `summary.v1` theme "
            f"{SHOWN_THEME_A!r} with its count {SHOWN_THEME_A_COUNT}. That is the twin: a filter "
            "refusing every `summary.v1` row would pass the absences below."
        )
        assert SHOWN_SUMMARY_TEXT in text, f"The {task}'s request lacks the shown summary."
        leaked = [value for value in (HELD_V1_THEME, HELD_V1_SUMMARY_TEXT) if value in text]
        assert not leaked, (
            f"The {task}'s request carries {leaked} from the held stream's `summary.v1` row. The "
            "ticket: 'an old-format (`summary.v1`) row of a held stream gives no themes, as it "
            "gives no summary.'"
        )
        assert not carries_number(
            text, HELD_V1_THEME_COUNT
        ), f"The {task}'s request carries {HELD_V1_THEME_COUNT}, the held `summary.v1` theme's count."


def test_a_check_naming_an_old_format_held_theme_is_refused(draft_door: DraftDoor) -> None:
    """The check's stored-theme set is the filtered one: a v1 held theme is not a stored theme.

    Named the way a held theme is legitimately named — without a count — so the
    only thing wrong with it is that the filter withholds its row. **The mutation
    this kills:** the check comparing against every `weekly_summary` row of the
    week rather than the filtered read the prompt was built from. **The twin,
    asserted first in the same world:** the shown stream's v1 theme with its count,
    accepted.
    """
    door = draft_door
    door.build_the_week(held_summary_version=ORDINARY_SUMMARY_VERSION)

    accepted = check_with(door, [(SHOWN_THEME_A, SHOWN_THEME_A_COUNT)])
    assert served_pairs(accepted) == [(SHOWN_THEME_A, SHOWN_THEME_A_COUNT)], (
        "The twin: the shown stream's `summary.v1` theme with its stored count was not accepted, "
        "so a refusal below would not be about the held row."
    )

    refused = check_with(door, [(HELD_V1_THEME, None)])
    assert_unusable(
        refused,
        "check",
        f"names {HELD_V1_THEME!r}, a theme of the held stream's `summary.v1` row, which the "
        "`_stored_summaries` filter withholds",
    )
