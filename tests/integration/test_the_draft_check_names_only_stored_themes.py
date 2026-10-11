"""The draft check names only the week's stored themes, with their stored counts — E7-04 done-when 2.

> A check answer naming a theme the stored summary does not hold, or a shown
> stream's stored theme with a different count, is refused; an answer naming
> stored themes with their stored counts is accepted. An empty list is accepted.

And the work order's residue B, the shown half: "a shown theme without [a count]
refused ... beside its accepted twin." The held half is in
`test_a_held_streams_themes_carry_no_count.py`, which is `invariant`.

**What the model says is scripted, so what is under test is the code after it.**
The ticket: "Two structural refusals, checked in code after the model answers ...
Anything else is refused as an invalid answer." A model will sooner or later name
a theme nobody raised, or round a count, and the instructor reads the check as a
statement about their students; the refusal is the product.

**A refusal is decision 2's 502.** Every refused answer here is built through
`CheckTheme` first (`fixtures.response_draft.check_answer`), so the gateway's shape
validation accepts it and a 502 can only come from the structural check under test
(`docs/MISTAKES.md` entry 3). `check_with` also requires that the model was asked,
so a refusal from somewhere before the model cannot pass for this one.

**Which failure a red is.** Before E7-04: a FAILED naming the missing route or
`CheckTheme`. Once built, a mutation shows up as an assertion on the status.
"""

import pytest
from fixtures.response_draft import (
    AN_INVENTED_THEME,
    COUNT_FIELD,
    HELD_THEME,
    LABEL_FIELD,
    SHOWN_THEME_A,
    SHOWN_THEME_A_COUNT,
    SHOWN_THEME_B,
    SHOWN_THEME_B_COUNT,
    DraftDoor,
    assert_unusable,
    check_with,
    unaddressed_of,
)

pytestmark = pytest.mark.integration


def test_a_check_naming_stored_themes_with_their_stored_counts_is_accepted(
    draft_door: DraftDoor,
) -> None:
    """The accepted twin every refusal below stands beside, and the payload it carries.

    Both shown themes with their stored counts, and the held theme with none. The
    route answers exactly those three, in decision 1's shape.

    **The mutation this kills:** a check that refuses everything (every refusal
    below passes against it); a route that rewrites what the model named — a
    count re-derived from somewhere other than the stored summary, or the held
    theme dropped rather than named without a count. **The near miss it must
    survive:** a route listing themes in another order; they are compared by label.
    """
    door = draft_door
    door.build_the_week()
    door.assert_the_streams_are(instructor_held=False, course_held=True)

    named = [
        (SHOWN_THEME_A, SHOWN_THEME_A_COUNT),
        (SHOWN_THEME_B, SHOWN_THEME_B_COUNT),
        (HELD_THEME, None),
    ]
    served = unaddressed_of(check_with(door, named))

    pairs = [(theme.get(LABEL_FIELD), theme.get(COUNT_FIELD)) for theme in served]
    assert sorted(pairs, key=lambda pair: str(pair[0])) == sorted(named, key=lambda p: p[0]), (
        f"The check served {served!r} for a model answer naming {named!r}. Each is a stored theme "
        "with its stored count (none for the held stream's), so the route has nothing to refuse "
        "and nothing to change."
    )


def test_an_empty_check_is_accepted(draft_door: DraftDoor) -> None:
    """A draft that addresses everything: the model names nothing, and the page says so.

    **The mutation this kills:** a check that treats an empty answer as a shape
    failure (a `min_length=1`, or a "the model said nothing" refusal) — the one
    answer a good draft is supposed to earn.
    """
    door = draft_door
    door.build_the_week()
    assert unaddressed_of(check_with(door, [])) == [], "The empty check served a theme."


def test_a_check_naming_a_theme_no_summary_holds_is_refused(draft_door: DraftDoor) -> None:
    """A theme the week's stored summaries do not hold, beside one they do.

    **The mutation this kills:** the membership check absent, or checking only the
    first theme named (the stored one comes first here), or reading the stored
    themes of every week of the section. **The near miss it must survive:** the
    accepted twin above, which names stored themes in the same world.
    """
    door = draft_door
    door.build_the_week()
    answered = check_with(door, [(SHOWN_THEME_A, SHOWN_THEME_A_COUNT), (AN_INVENTED_THEME, 2)])
    assert_unusable(
        answered, "check", f"names {AN_INVENTED_THEME!r}, which no stored summary holds"
    )


def test_a_check_naming_a_shown_theme_with_another_count_is_refused(draft_door: DraftDoor) -> None:
    """A stored theme of a shown stream, one comment off its stored count.

    One off, because a check comparing within a tolerance, or comparing only the
    label, passes it. **The mutation this kills:** the count leg of the check
    deleted — the label matched and the count trusted. **The near miss:** the
    accepted twin, which is the same label with `SHOWN_THEME_A_COUNT`.
    """
    door = draft_door
    door.build_the_week()
    answered = check_with(door, [(SHOWN_THEME_A, SHOWN_THEME_A_COUNT + 1)])
    assert_unusable(
        answered,
        "check",
        f"names the shown theme {SHOWN_THEME_A!r} with {SHOWN_THEME_A_COUNT + 1} comments where the "
        f"stored summary holds {SHOWN_THEME_A_COUNT}",
    )


def test_a_check_naming_a_shown_theme_without_a_count_is_refused(draft_door: DraftDoor) -> None:
    """Residue B's shown half: a shown stream's theme with no count at all.

    `CheckTheme.comment_count` is `int | None` so that a *held* theme can be named
    without one; that is no licence for a shown theme to lose its count. SPEC §5.3:
    the check names an unaddressed theme "with its comment count".

    **The mutation this kills:** a check admitting `None` for any theme because the
    contract does — the optional type standing in for the rule (`docs/MISTAKES.md`
    entry 23). **The near miss:** the accepted twin, the same theme with its count.
    """
    door = draft_door
    door.build_the_week()
    answered = check_with(door, [(SHOWN_THEME_B, None)])
    assert_unusable(answered, "check", f"names the shown theme {SHOWN_THEME_B!r} with no count")
