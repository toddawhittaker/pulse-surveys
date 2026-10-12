"""§4.1 item 4 through the routes: no roll-up list is ordered by a figure — E9-12 done-when 4.

> 4. **§4.1 item 4, ordering.** For two worlds that differ only in figures, every
>    list in every roll-up response has the same order. Marked `invariant`.

SPEC §4.1 item 4: "no ranking, no composite scores, and no score-sorting
anywhere". README decision 13 puts the property in E9-07 (over the pure card
function) and the invariant here, over every list the two roll-up routes serve.

**Two worlds that differ only in figures**, in one test: E6-05's lead-review world
is read by its chair (who holds all four of its sections: `F`, `Q`, the sibling
course's `Y` and the unmapped course's `4`), then **more students answer** and it
is read again. No section, course, node or name is added or removed between the
reads; the answers move every figure the two small sections carry, in opposite
directions:

  - first world — `Y`: one respondent rating the instructor 5, two enrolled who
    do not answer (rate 1 of 3, mean 5); `4`: one respondent rating 1 (rate 1 of
    1, mean 1);
  - second world — `Y` gains three respondents rating 1 (4 of 6, mean 2); `4`
    gains three rating 5 and four enrolled who do not answer (4 of 8, mean 4).

So `Y` is above `4` by mean and below it by rate in the first world, and the
reverse in the second: any list sorted by either figure changes order between the
reads. The owed read is swapped so every section the chair's nodes are computed
over carries a card (`owe_every_section`), which makes the attention list a list
of four in both worlds.

**"The same order"** is read per list, matched by path: the elements common to
both reads appear in the same relative order. A card may appear or disappear as
the figures change (a trend card, a response-rate card); no two elements may swap.
Elements are matched by their identity members (`kind`, `id`, `section_id`,
`rule`, `stream`, `course_week`, `term_week`, `section_start_date`, `name`,
`code`), never by a figure.

**Expected green on today's branch.**
"""

from typing import Any

import pytest
from fixtures.e9_invariant_pass import (
    FIGURE_KINDS,
    body_of,
    dumped,
    figures_url,
    owe_every_section,
    term_of,
    tree_nodes,
    tree_url,
)
from fixtures.lead_review import UNMAPPED_COHORT, LeadReviewWorld
from fixtures.report_api import RATING_POSITION, TERM_WEEK_OF_COURSE_WEEK
from fixtures.report_views import INSTRUCTOR_STREAM

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

SIBLING_COHORT = "Y"
THE_WEEK = 1
IDENTITY = (
    "kind",
    "id",
    "node_id",
    "section_id",
    "rule",
    "stream",
    "course_week",
    "term_week",
    "section_start_date",
    "name",
    "code",
)


def answering(
    review: LeadReviewWorld, cohort: str, ratings: list[int], silent: int, tag: str
) -> None:
    """New students in one cohort's section: one response each at `ratings`, plus `silent` enrolled."""
    world = review.door.world
    for index, rating in enumerate(ratings):
        student = world.student(f"e9-12-order-{tag}-{cohort}-{index}", cohorts=(cohort,))
        world.submit(
            term_week=TERM_WEEK_OF_COURSE_WEEK[THE_WEEK],
            comments=None,
            ratings={RATING_POSITION[INSTRUCTOR_STREAM]: rating},
            cohort=cohort,
            student=student,
        )
    for index in range(silent):
        world.student(f"e9-12-order-{tag}-{cohort}-silent-{index}", cohorts=(cohort,))
    review.door.door.commit()


def identity(element: Any) -> Any:
    if isinstance(element, dict):
        key = tuple((name, str(element[name])) for name in IDENTITY if name in element)
        return key or None
    if isinstance(element, str | int) and not isinstance(element, bool):
        return element
    return None


def lists_in(value: Any, path: tuple[Any, ...] = ()) -> dict[tuple[Any, ...], list[Any]]:
    """Every list at any depth, by a path of member names and element identities."""
    found: dict[tuple[Any, ...], list[Any]] = {}
    if isinstance(value, dict):
        for name, item in value.items():
            found.update(lists_in(item, (*path, name)))
    elif isinstance(value, list):
        keys = [identity(element) for element in value]
        if keys and all(key is not None for key in keys):
            found[path] = keys
        for element in value:
            found.update(lists_in(element, (*path, identity(element) or "?")))
    return found


def read_everything(review: LeadReviewWorld) -> dict[str, Any]:
    assert review.chair is not None
    term = term_of(review)
    tree = body_of(review.ask("GET", tree_url(term), token=review.chair.token), "The chair's tree")
    answers: dict[str, Any] = {"tree": tree}
    for node in tree_nodes(tree):
        if node.get("kind") in FIGURE_KINDS:
            url = figures_url(node["kind"], node["id"], term)
            answers[f"{node['kind']} {node['id']}"] = body_of(
                review.ask("GET", url, token=review.chair.token), f"The chair's {node['kind']}"
            )
    return answers


def test_every_rollup_list_keeps_its_order_when_only_the_figures_change(
    lead_review: LeadReviewWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The chair's tree and every node's figures, read before and after the answers move.

    **The premises, asserted:** the figures answers differ between the two reads
    (the worlds really differ in figures); the same nodes are read both times; and
    at least one list holds two or more elements in common, the prefix's
    attention list among them.

    **The mutation it kills:** attention cards sorted by a figure (worst trend,
    lowest response rate, lowest mean first); tree children or by-lead groups
    sorted by a count or a rate; cohorts sorted by a figure. **The near miss it
    spares:** cards appearing and disappearing as the figures change.
    """
    review = lead_review
    owe_every_section(monkeypatch)
    answering(review, SIBLING_COHORT, [5], silent=2, tag="first")
    answering(review, UNMAPPED_COHORT, [1], silent=0, tag="first")
    first = read_everything(review)

    answering(review, SIBLING_COHORT, [1, 1, 1], silent=0, tag="second")
    answering(review, UNMAPPED_COHORT, [5, 5, 5], silent=4, tag="second")
    second = read_everything(review)

    assert set(first) == set(second), (
        f"The two reads asked different nodes: {sorted(set(first) ^ set(second))}. The worlds "
        "differ only in figures, so the tree's nodes are the same."
    )
    changed = [
        where
        for where in first
        if where != "tree" and dumped(first[where]) != dumped(second[where])
    ]
    assert changed, (
        "No figures answer changed between the two worlds, so this pair does not differ in "
        "figures and says nothing about order."
    )

    swapped: dict[str, Any] = {}
    compared = 0
    for where in first:
        before, after = lists_in(first[where]), lists_in(second[where])
        for path in set(before) & set(after):
            seen_after = set(after[path])
            seen_before = set(before[path])
            common_before = [key for key in before[path] if key in seen_after]
            common_after = [key for key in after[path] if key in seen_before]
            if len(common_before) >= 2:
                compared += 1
            if common_before != common_after:
                swapped[f"{where} {path}"] = {"first": common_before, "second": common_after}
    attention_lists = [
        path
        for where in first
        for path, keys in lists_in(first[where]).items()
        if path and path[-1] == "attention" and len(keys) >= 2
    ]
    assert compared >= 1 and attention_lists, (
        f"{compared} lists held two or more elements in common and {len(attention_lists)} "
        "attention lists held two or more cards, so no order was compared."
    )
    assert not swapped, (
        f"These roll-up lists changed order when only the figures changed: {swapped}. SPEC §4.1 "
        "item 4: no score-sorting anywhere."
    )
