"""Rule 4 of §5.6 is `is_owed`'s rule, read once over a set; and the calm empty state — E9-07 done-when 7.

> Rule 4's test fails if the owed read stops using `is_owed`'s rule (replace it
> with a copy and the test goes red). The empty state carries the calm sentence.

The interface (the coordinator's settled note): `app.services.rollups` imports
`owed_section_weeks` **by name** from `app.services.response_loop`, with
`owed_section_weeks(session, *, section_ids, now, settings) -> set[tuple[UUID,
int]]` (section id, course week). `rollup_figures(session, *, scope, term_id,
kind, node_id, settings) -> RollupFigures` carries `attention` (cards with
`rule`, `section_id`, `course_week`) and `attention_empty`, which is the text of
`app.copy.leadership_rollup.NOTHING_NEEDS_ATTENTION` exactly when `attention` is
empty, else None.

**The world** is E7-03's response-loop world (`tests/fixtures/response_loop_doors.py`):
lead A leads the own course, whose taught section's course week
`ON_BEHALF_WEEK` reports at a hand-written instant; `own_course_required()`
plants a required policy before it. Reads use `pulse_app`'s session
(`docs/MISTAKES.md` entry 46), and the scope is `authz.resolve_scope` for lead A.

**Which failure a red is on dac77db5:** the light build has these names, so a red
is an assertion; if `rollup_figures` reads an org name it cannot reach, the
exception FAILS the test inside its body.
"""

from datetime import datetime
from typing import Any

import pytest
from fixtures.response_loop_doors import ON_BEHALF_WEEK, ONE_SECOND, OWED_AFTER, LoopWorld
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import TERM_TABLE
from fixtures.the_hold import report_opens

pytestmark = pytest.mark.integration

OWED_RULE = "response_owed"
CALM_SENTENCE = "Nothing needs attention this week"


def rule_of(card: Any) -> str:
    rule = card.rule
    value = getattr(rule, "value", None)
    return str(value if isinstance(value, str) else getattr(rule, "name", rule)).lower()


def figures_for_the_own_course(world: LoopWorld, authz: Any) -> Any:
    """Lead A's figures for her own course, on `pulse_app`'s session."""
    from app.config import Settings
    from app.services.rollups import rollup_figures

    session = world.hold.application_session
    review = world.review
    term = review.world.calendar.term[
        single_primary_key(require_table(review.world.tables, TERM_TABLE))
    ]
    try:
        scope = authz.resolve_scope(session, person_id=world.lead.person_id)
        return rollup_figures(
            session,
            scope=scope,
            term_id=term,
            kind="course",
            node_id=world.hold.own_course,
            settings=Settings(),
        )
    finally:
        session.rollback()


def owed_cards(figures: Any) -> list[tuple[str, int]]:
    return sorted(
        (str(card.section_id), card.course_week)
        for card in figures.attention
        if rule_of(card) == OWED_RULE
    )


def test_the_owed_card_appears_at_report_open_plus_48_hours_and_not_a_second_before(
    response_loop: LoopWorld, authz: Any
) -> None:
    """Required and unanswered: no owed card at +48h - 1s; one, for that section and week, at +48h.

    The real rule through the real payload, with the clock stood at each instant.

    **The mutations it kills:** a copied rule counting from the window's close
    (one second early); `>` for `>=`; the owed read ignoring the policy.
    **The near miss it spares:** other cards the world's figures make.
    """
    world = response_loop
    world.own_course_required()
    taught = (str(world.hold.taught), ON_BEHALF_WEEK)

    world.stand(OWED_AFTER - ONE_SECOND)
    before = owed_cards(figures_for_the_own_course(world, authz))
    world.stand(OWED_AFTER)
    at = owed_cards(figures_for_the_own_course(world, authz))

    assert taught in at, (
        f"At report open + 48h the owed cards are {at}; the taught section's week {ON_BEHALF_WEEK} "
        "is required and unanswered (§5.6 rule 4)."
    )
    assert (
        taught not in before
    ), f"One second before report open + 48h the owed cards already hold {taught}."


@pytest.mark.parametrize("required", (False, True), ids=("planted-owed", "planted-nothing"))
def test_the_owed_cards_are_exactly_what_the_shared_owed_read_answers(
    response_loop: LoopWorld, authz: Any, monkeypatch: pytest.MonkeyPatch, required: bool
) -> None:
    """The swap test: replace the shared read and the cards follow it, in both directions.

    `planted-owed`: no policy, so the real rule owes nothing, and the swapped
    read answers the taught section's week as owed; the card must appear.
    `planted-nothing`: the week is required and past +48h, so the real rule owes
    it, and the swapped read answers nothing; the card must not appear.

    **The mutation it kills:** `rollups` computing rule 4 with its own copy of the
    48-hour rule (or calling anything but `owed_section_weeks`). Either half alone
    could pass a copy that happens to agree with the world; together they cannot.
    **The control:** the swapped read was called, with the taught section among
    the ids it was handed.
    """
    import app.services.rollups as rollups

    world = response_loop
    if required:
        world.own_course_required()
    world.stand(OWED_AFTER)
    taught = world.hold.taught
    answered: set[Any] = set() if required else {(taught, ON_BEHALF_WEEK)}
    calls: list[list[str]] = []

    def swapped(session: Any, *, section_ids: Any, now: datetime, settings: Any) -> set[Any]:
        calls.append([str(section) for section in section_ids])
        return set(answered)

    monkeypatch.setattr(rollups, "owed_section_weeks", swapped)
    cards = owed_cards(figures_for_the_own_course(world, authz))

    assert calls and any(str(taught) in ids for ids in calls), (
        f"The swapped `owed_section_weeks` was called {len(calls)} times with ids {calls}; the "
        "attention list reads rule 4 through it, over the purview's sections."
    )
    expected = sorted((str(section), week) for section, week in answered)
    assert cards == expected, (
        f"With the shared owed read swapped to answer {expected}, the owed cards are {cards}. Rule "
        "4 is `is_owed`'s rule through `owed_section_weeks`, never a copy (done-when 7)."
    )


def test_is_owed_and_the_set_based_owed_read_agree_either_side_of_the_edge(
    response_loop: LoopWorld,
) -> None:
    """`is_owed` and `owed_section_weeks` give the same answer for each section, at +48h - 1s and +48h.

    The rule is written once. Two sections: the taught one (required) and the
    sibling course's (encouraged).

    **The control:** at +48h the taught section's week is owed, so agreement is
    not two empty answers. **The mutations it kills:** a set read with its own
    copy of the rule that drifts from `is_owed` at the edge or on the policy.
    """
    from app.config import Settings
    from app.services.response_loop import is_owed, owed_section_weeks

    world = response_loop
    world.own_course_required()
    session = world.hold.application_session
    sections = [world.hold.taught, world.hold.sibling_course_section]
    edge = report_opens(ON_BEHALF_WEEK) + OWED_AFTER

    answers: dict[datetime, tuple[list[bool], list[bool]]] = {}
    try:
        for now in (edge - ONE_SECOND, edge):
            owed = owed_section_weeks(session, section_ids=sections, now=now, settings=Settings())
            one_by_one = [
                is_owed(session, section_id=section, course_week=ON_BEHALF_WEEK, now=now)
                for section in sections
            ]
            as_a_set = [(section, ON_BEHALF_WEEK) in owed for section in sections]
            answers[now] = (one_by_one, as_a_set)
    finally:
        session.rollback()

    assert (
        answers[edge][0][0] is True
    ), f"The control failed: `is_owed` says the required week is not owed at +48h ({answers})."
    disagree = {str(now): pair for now, pair in answers.items() if pair[0] != pair[1]}
    assert not disagree, (
        f"`is_owed` and `owed_section_weeks` disagree (one by one, as a set) for [taught, "
        f"sibling]: {disagree}."
    )


@pytest.mark.parametrize("cards_made", (0, 1), ids=("no-card", "one-card"))
def test_the_calm_sentence_is_served_exactly_when_nothing_needs_attention(
    response_loop: LoopWorld,
    authz: Any,
    monkeypatch: pytest.MonkeyPatch,
    cards_made: int,
) -> None:
    """No card: `attention_empty` is the registry's "Nothing needs attention this week". A card: None.

    Both halves stand where the required week is owed (+48h), so the real
    payload carries an owed card; the no-card half replaces
    `rollups.attention_cards` with one answering nothing. The sentence is
    checked against the registry entry and against the ticket's words (a
    trailing full stop is allowed).

    **The mutations it kills:** the sentence missing or inlined rather than
    served from `app.copy.leadership_rollup`; the sentence served beside a card.
    """
    import app.services.rollups as rollups

    world = response_loop
    world.own_course_required()
    world.stand(OWED_AFTER)
    try:
        from app.copy.leadership_rollup import NOTHING_NEEDS_ATTENTION
    except ImportError:
        pytest.fail(
            "`app.copy.leadership_rollup` has no `NOTHING_NEEDS_ATTENTION`; the settled interface "
            "serves the empty state from it."
        )
    registered = str(getattr(NOTHING_NEEDS_ATTENTION, "text", NOTHING_NEEDS_ATTENTION))
    assert (
        registered.rstrip(".") == CALM_SENTENCE
    ), f"The registry's empty-state sentence is {registered!r}; the ticket's is {CALM_SENTENCE!r}."

    if cards_made == 0:

        def nothing(sections: Any, *, figures: Any, owed: Any) -> list[Any]:
            return []

        monkeypatch.setattr(rollups, "attention_cards", nothing)
    figures = figures_for_the_own_course(world, authz)

    if cards_made == 0:
        assert (
            list(figures.attention) == []
        ), f"With `attention_cards` answering nothing the payload carries {figures.attention!r}."
        assert figures.attention_empty == registered, (
            f"With no card, `attention_empty` is {figures.attention_empty!r}; it is the "
            f"registry's {registered!r}."
        )
    else:
        assert (
            figures.attention
        ), "The control failed: at +48h with the week required, the payload carries no card."
        assert (
            figures.attention_empty is None
        ), f"With a card, `attention_empty` is {figures.attention_empty!r}; it is None."
