"""The four §5.6 attention rules, each at its boundary — E9-07 done-when 7 (rules 1 to 4).

> 7. **Attention follows §5.6 exactly.** One seeded section per rule makes one
>    card naming its rule and stream; a section one week short of "two
>    consecutive weeks" and one at exactly 40% make none.

SPEC §5.6: instructor trend down two or more consecutive weeks; course trend
down two or more; response rate under 40%; response required and delinquent 48
hours or more.

The interface (the coordinator's settled note, taken from the light build):
`rollups.attention_cards(sections, *, figures, owed) -> list[AttentionCard]` is
pure. `HeldSection(section_id, code, start_date, course_id, course_name,
prefix_id, prefix_code, department_id, department_name, college_id,
college_name)`; `SectionWeekFigures(published, means, responses,
valid_responses, enrolled)`, where `means` is keyed `(stream, course_week)`.
`AttentionCard(rule, rule_name, stream, section_id, section_code, course_name,
course_week)`; rules `instructor_trend_down`, `course_trend_down`,
`response_rate_low`, `response_owed`; streams `INSTRUCTOR`, `COURSE` or None.

**Readings this file takes, each stated so a dispute can name it:**
  - "down two consecutive weeks" is two week-over-week declines ending at the
    latest published week: 4.5, 4.0, 3.5 fires; 4.0, 4.0, 3.5 (one decline) is
    "one week short" and does not.
  - the response rate is `responses / enrolled`; `valid_responses` is set equal
    to `responses` everywhere here, so the validity rate cannot decide anything.
  - the `means` keys use the card's stream spellings, `"INSTRUCTOR"` and
    `"COURSE"`.

The rule-4 tests that need the database (the owed read is `is_owed`'s rule, and
the swap test) are in
`tests/integration/test_the_attention_list_reads_the_shared_owed_rule.py`.

**Which failure a red is:** on dac77db5 these are expected to pass if the light
build's `attention_cards` already follows §5.6; a missing symbol FAILS on a
`pytest.fail` naming it.
"""

from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest

ROLLUPS_MODULE = "app.services.rollups"

INSTRUCTOR = "INSTRUCTOR"
COURSE = "COURSE"
INSTRUCTOR_TREND = "instructor_trend_down"
COURSE_TREND = "course_trend_down"
RATE_LOW = "response_rate_low"
OWED = "response_owed"
RULES = (INSTRUCTOR_TREND, COURSE_TREND, RATE_LOW, OWED)
STREAM_OF_RULE = {INSTRUCTOR_TREND: INSTRUCTOR, COURSE_TREND: COURSE, RATE_LOW: None, OWED: None}

WEEKS = (1, 2, 3)
FLAT = (4.0, 4.0, 4.0)
DOWN_TWICE = (4.5, 4.0, 3.5)
DOWN_ONCE = (4.0, 4.0, 3.5)
ENROLLED = 10
HEALTHY_RESPONSES = 8
UNDER_FORTY = 3
EXACTLY_FORTY = 4


def rollups() -> Any:
    import importlib

    try:
        module = importlib.import_module(ROLLUPS_MODULE)
    except ModuleNotFoundError as missing:
        if missing.name and ROLLUPS_MODULE.startswith(missing.name):
            pytest.fail(f"`{ROLLUPS_MODULE}` does not exist. E9-07 owns it.")
        raise
    for name in ("attention_cards", "HeldSection", "SectionWeekFigures"):
        if not hasattr(module, name):
            pytest.fail(
                f"`{ROLLUPS_MODULE}` has no `{name}`; the settled interface has the pure "
                "`attention_cards(sections, *, figures, owed)` over `HeldSection` and "
                "`SectionWeekFigures`."
            )
    return module


def a_section(module: Any, *, code: str = "F1WW", course_name: str = "MATH 101") -> Any:
    return module.HeldSection(
        section_id=uuid4(),
        code=code,
        start_date=date(2026, 8, 17),
        course_id=uuid4(),
        course_name=course_name,
        prefix_id=uuid4(),
        prefix_code="MATH",
        department_id=uuid4(),
        department_name="Mathematics",
        college_id=uuid4(),
        college_name="College of Arts and Sciences",
    )


def figures_of(
    module: Any,
    *,
    instructor: tuple[float, ...] = FLAT,
    course: tuple[float, ...] = FLAT,
    responses: int = HEALTHY_RESPONSES,
    enrolled: int = ENROLLED,
) -> Any:
    means: dict[tuple[str, int], float | None] = {}
    for week, value in zip(WEEKS, instructor, strict=True):
        means[(INSTRUCTOR, week)] = value
    for week, value in zip(WEEKS, course, strict=True):
        means[(COURSE, week)] = value
    return module.SectionWeekFigures(
        published=WEEKS,
        means=means,
        responses=responses,
        valid_responses=responses,
        enrolled=enrolled,
    )


def rule_of(card: Any) -> str:
    rule = card.rule
    value = getattr(rule, "value", None)
    return str(value if isinstance(value, str) else getattr(rule, "name", rule)).lower()


def stream_of(card: Any) -> str | None:
    stream = card.stream
    if stream is None:
        return None
    value = getattr(stream, "value", stream)
    return str(value).upper()


def cards_for(
    *, owed: set[tuple[UUID, int]] | None = None, **figures: Any
) -> tuple[Any, list[Any]]:
    module = rollups()
    section = a_section(module)
    planted_owed = {(section.section_id, week) for _id, week in (owed or set())}
    cards = module.attention_cards(
        [section],
        figures={section.section_id: figures_of(module, **figures)},
        owed=planted_owed,
    )
    return section, list(cards)


def summary(cards: list[Any]) -> list[tuple[str, str | None]]:
    return sorted((rule_of(card), stream_of(card)) for card in cards)


def test_a_quiet_section_makes_no_card() -> None:
    """The control for every pair below: flat means, 80% responding, nothing owed — no card.

    **The mutation it kills:** a rule that fires on any figure at all.
    """
    _section, cards = cards_for()
    assert cards == [], f"A quiet section made cards {summary(cards)}."


@pytest.mark.parametrize(
    ("rule", "figures"),
    [
        (INSTRUCTOR_TREND, {"instructor": DOWN_TWICE}),
        (COURSE_TREND, {"course": DOWN_TWICE}),
        (RATE_LOW, {"responses": UNDER_FORTY}),
        (OWED, {"owed": {(uuid4(), 3)}}),
    ],
    ids=RULES,
)
def test_one_section_meeting_one_rule_makes_one_card_naming_that_rule_and_stream(
    rule: str, figures: dict[str, Any]
) -> None:
    """Each rule alone makes exactly one card, for its section, carrying its rule, name and stream.

    **The mutations it kills:** a rule wired to the wrong stream (an instructor
    decline reported as the course's); a card per week rather than per section;
    a card that does not name its section (it must link to the section's
    report). **The near miss:** the quiet section above.
    """
    section, cards = cards_for(**figures)
    assert summary(cards) == [(rule, STREAM_OF_RULE[rule])], (
        f"A section meeting only `{rule}` made cards {summary(cards)}; SPEC §5.6 and done-when 7: "
        f"one card naming `{rule}` with stream {STREAM_OF_RULE[rule]!r}."
    )
    (card,) = cards
    assert card.section_id == section.section_id and card.section_code == section.code, (
        f"The card names section {card.section_id} / {card.section_code!r}, not the section that "
        "met the rule; the card links to that section's report."
    )
    assert (
        isinstance(card.rule_name, str) and card.rule_name.strip()
    ), f"The `{rule}` card's `rule_name` is {card.rule_name!r}; each card names its rule."


def test_the_owed_card_carries_the_owed_course_week() -> None:
    """Rule 4's card names the week that is owed, so the reader knows which response is late."""
    _section, cards = cards_for(owed={(uuid4(), 2)})
    assert [(rule_of(card), card.course_week) for card in cards] == [
        (OWED, 2)
    ], f"Owed week 2 made {[(rule_of(card), card.course_week) for card in cards]}."


@pytest.mark.parametrize(
    ("stream_member", "rule"), [("instructor", INSTRUCTOR_TREND), ("course", COURSE_TREND)]
)
def test_one_decline_is_one_week_short_of_a_trend_and_makes_no_card(
    stream_member: str, rule: str
) -> None:
    """4.0, 4.0, 3.5 makes no card; 4.5, 4.0, 3.5 (the parametrised test above) makes one.

    **The mutation it kills:** "two or more" read as "one or more" (`>= 1`
    declines). **The near miss it spares:** two declines.
    """
    _section, short = cards_for(**{stream_member: DOWN_ONCE})
    _section, trend = cards_for(**{stream_member: DOWN_TWICE})
    assert rule in [
        rule_of(card) for card in trend
    ], f"The control failed: two declines made {summary(trend)}, no `{rule}` card."
    assert (
        short == []
    ), f"One decline ({DOWN_ONCE}) made {summary(short)}; §5.6 needs two or more consecutive weeks."


def test_a_response_rate_of_exactly_forty_percent_makes_no_card() -> None:
    """4 of 10 makes no card; 3 of 10 makes one. "Under 40%" is strict.

    **The mutation it kills:** `<=` for `<`. **The near miss it spares:** 30%.
    """
    _section, at = cards_for(responses=EXACTLY_FORTY)
    _section, under = cards_for(responses=UNDER_FORTY)
    assert summary(under) == [(RATE_LOW, None)], f"The control failed: 30% made {summary(under)}."
    assert at == [], f"Exactly 40% made {summary(at)}; §5.6: under 40%."
