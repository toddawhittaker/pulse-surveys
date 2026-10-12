"""The attention list's order is the same whatever the figures are — E9-07 done-when 8.

> 8. **Order never follows a figure.** A Hypothesis property: for random
>    figures over a fixed tree, the order of every list in the payload is the
>    same. The sort keys are labels and codes.

README decision 13 and SPEC §4.1 item 4: aggregate lists sort by label or
section code, never by a figure. The coordinator's settled note scopes the
property to the pure `rollups.attention_cards(sections, *, figures, owed)`; the
tree's label order is held by the seeded tree test
(`tests/integration/test_the_rollup_tree_on_the_seeded_institution.py`).

**How "the same order" is asserted without choosing the rule order for the
builder.** A reference run in which every rule fires for every section gives the
full ordered list of `(section, rule)` keys. Every random draw must yield a
subsequence of that list, in the same order: a card may appear or not as the
figures change, but no two cards may swap places. The reference itself must be
in label order (course name, then section code), which is the "sort keys are
labels and codes" half.

The fixed sections are passed in an order that is not label order, so an output
that kept the input order is caught too.

**Which failure a red is:** a missing symbol FAILS on a `pytest.fail` naming it;
an order that follows a figure FAILS on the subsequence assertion with
Hypothesis's shrunk example. On dac77db5 this is expected to pass if the light
build sorts by labels.
"""

from datetime import date
from typing import Any
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROLLUPS_MODULE = "app.services.rollups"
INSTRUCTOR = "INSTRUCTOR"
COURSE = "COURSE"

# (section code, course name), deliberately listed out of label order.
FIXED_SECTIONS = (
    ("Q1WW", "STAT 250"),
    ("F1WW", "MATH 505"),
    ("A2WW", "STAT 250"),
    ("F1WW", "BIOL 101"),
)
SECTION_IDS = tuple(UUID(int=index + 1) for index in range(len(FIXED_SECTIONS)))
COURSE_IDS = {
    name: UUID(int=100 + index)
    for index, name in enumerate(sorted({c for _s, c in FIXED_SECTIONS}))
}
PREFIX_IDS = {"BIOL": UUID(int=201), "MATH": UUID(int=202), "STAT": UUID(int=203)}
MEAN_VALUES = st.sampled_from([None, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0])


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
            pytest.fail(f"`{ROLLUPS_MODULE}` has no `{name}`; the settled interface has it.")
    return module


def sections(module: Any) -> list[Any]:
    held = []
    for section_id, (code, course_name) in zip(SECTION_IDS, FIXED_SECTIONS, strict=True):
        prefix = course_name.split()[0]
        held.append(
            module.HeldSection(
                section_id=section_id,
                code=code,
                start_date=date(2026, 8, 17),
                course_id=COURSE_IDS[course_name],
                course_name=course_name,
                prefix_id=PREFIX_IDS[prefix],
                prefix_code=prefix,
                department_id=UUID(int=7),
                department_name="Mathematics",
                college_id=UUID(int=8),
                college_name="College of Arts and Sciences",
            )
        )
    return held


def rule_of(card: Any) -> str:
    rule = card.rule
    value = getattr(rule, "value", None)
    return str(value if isinstance(value, str) else getattr(rule, "name", rule)).lower()


def keys(cards: list[Any]) -> list[tuple[UUID, str]]:
    return [(card.section_id, rule_of(card)) for card in cards]


def everything_fires(module: Any) -> list[Any]:
    """Every rule for every section: two declines in both streams, 10% responding, week 3 owed."""
    figures = {
        section_id: module.SectionWeekFigures(
            published=(1, 2, 3),
            means={
                **{
                    (stream, week): value
                    for stream in (INSTRUCTOR, COURSE)
                    for week, value in zip((1, 2, 3), (4.5, 4.0, 3.5), strict=True)
                },
            },
            responses=1,
            valid_responses=1,
            enrolled=10,
        )
        for section_id in SECTION_IDS
    }
    owed = {(section_id, 3) for section_id in SECTION_IDS}
    return list(module.attention_cards(sections(module), figures=figures, owed=owed))


def test_the_reference_run_fires_every_rule_and_is_in_label_order() -> None:
    """The premise of the property, and the "sort keys are labels and codes" half.

    Four cards per section, and the sections' cards in course-name then
    section-code order, which is not the order the sections were passed in.

    **The mutations it kills:** cards in input order; cards sorted by section id
    (a key, not a label). **The near miss it spares:** any fixed order of the
    four rules within a section.
    """
    module = rollups()
    reference = everything_fires(module)
    per_section = {section_id: 0 for section_id in SECTION_IDS}
    for section_id, _rule in keys(reference):
        per_section[section_id] += 1
    assert set(per_section.values()) == {4}, (
        f"The all-rules run made {per_section} cards per section; every section meets all four "
        "rules there, so the property below would be checked against a partial reference."
    )
    labels = [(card.course_name, card.section_code) for card in reference]
    assert labels == sorted(
        labels
    ), f"The cards run in label order {labels}; decision 13: by label or section code."


@settings(max_examples=200, deadline=None)
@given(data=st.data())
def test_no_change_of_figures_reorders_the_attention_cards(data: st.DataObject) -> None:
    """For random figures and owed weeks over the fixed sections, the cards keep the reference order.

    **The mutation it kills:** any sort that reads a figure (worst trend first,
    lowest response rate first, most owed first), and any order that depends on
    which cards happen to appear. **The near miss it spares:** cards appearing
    and disappearing as the figures change.
    """
    module = rollups()
    reference = keys(everything_fires(module))
    position = {key: index for index, key in enumerate(reference)}

    figures: dict[UUID, Any] = {}
    owed: set[tuple[UUID, int]] = set()
    for section_id in SECTION_IDS:
        weeks = tuple(range(1, data.draw(st.integers(min_value=1, max_value=4)) + 1))
        means = {
            (stream, week): data.draw(MEAN_VALUES)
            for stream in (INSTRUCTOR, COURSE)
            for week in weeks
        }
        enrolled = data.draw(st.integers(min_value=1, max_value=40))
        responses = data.draw(st.integers(min_value=0, max_value=enrolled))
        figures[section_id] = module.SectionWeekFigures(
            published=weeks,
            means=means,
            responses=responses,
            valid_responses=data.draw(st.integers(min_value=0, max_value=responses)),
            enrolled=enrolled,
        )
        # At most one owed week per section: the settled order (course name,
        # section code, rule) says nothing about two owed weeks of one section,
        # so the property does not decide that tie for the builder.
        owed_week = data.draw(st.none() | st.sampled_from(weeks))
        if owed_week is not None:
            owed.add((section_id, owed_week))

    drawn = keys(list(module.attention_cards(sections(module), figures=figures, owed=owed)))
    unknown = [key for key in drawn if key not in position]
    assert not unknown, f"Cards {unknown} are not in the all-rules reference {reference}."
    places = [position[key] for key in drawn]
    assert places == sorted(places) and len(set(places)) == len(places), (
        f"Under these figures the cards ran {drawn}; the reference order is {reference}. Decision "
        "13: the order never follows a figure."
    )
