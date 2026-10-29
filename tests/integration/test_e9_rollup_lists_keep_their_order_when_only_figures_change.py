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
    do not answer (1 response, rate 1 of 3, mean 5); `4`: three respondents
    rating 3 (3 responses, rate 3 of 3, mean 3);
  - second world — `Y` gains four respondents rating 1 (5 responses, rate 5 of
    7, mean 1.8); `4` gains four enrolled who do not answer (3 responses, rate 3
    of 7, mean 3).

So between `Y` and `4` the order **by response count, by response rate and by
mean all flip** between the two worlds — `Y` below `4` on count and rate and
above it on mean in the first, the reverse of each in the second — while their
label order cannot move. No two of those figures tie in either world (the E9-12
battery found the first version tied on response count, 1 and 1 then 4 and 4, so
a sort by responses reordered nothing). Any list sorted by any of the three
changes order between the reads. The owed read is swapped so every section the
chair's nodes are computed over carries a card (`owe_every_section`), which makes
the attention list a list of four in both worlds.

The chair's reads are her tree, every node's figures **including her by-lead
groups** (`lead` and `no_lead`, E9-07), and two named-set series — an eight-week
set over the sibling course and a six-week set over the own course — whose
cohort and week lists are compared the same way.

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
    BY_LEAD_KINDS,
    FIGURE_KINDS,
    a_named_set,
    body_of,
    dumped,
    figures_url,
    owe_every_section,
    series_url,
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


def read_everything(review: LeadReviewWorld, sets: dict[str, Any]) -> dict[str, Any]:
    """The chair's tree, every node's and by-lead group's figures, and each named set's series."""
    assert review.chair is not None
    term = term_of(review)
    tree = body_of(review.ask("GET", tree_url(term), token=review.chair.token), "The chair's tree")
    answers: dict[str, Any] = {"tree": tree}
    for node in tree_nodes(tree):
        if node.get("kind") in (*FIGURE_KINDS, *BY_LEAD_KINDS):
            url = figures_url(node["kind"], node["id"], term)
            answers[f"{node['kind']} {node['id']}"] = body_of(
                review.ask("GET", url, token=review.chair.token), f"The chair's {node['kind']}"
            )
    for name, set_id in sets.items():
        answers[f"series {name}"] = body_of(
            review.ask("GET", series_url(set_id, term), token=review.chair.token),
            f"The chair's series over the {name} set",
        )
    return answers


def test_every_rollup_list_keeps_its_order_when_only_the_figures_change(
    lead_review: LeadReviewWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The chair's tree, every node's and by-lead group's figures, and two series, before and after.

    **The premises, asserted:** the figures answers differ between the two reads
    (the worlds really differ in figures); the same nodes are read both times; at
    least one list holds two or more elements in common, the prefix's attention
    list among them; at least one by-lead group was read; and a series' week list
    held two or more weeks.

    **The mutation it kills:** attention cards sorted by a figure — response
    count, response rate, mean or trend (E9-12 battery row 4, which the first
    version of this world did not separate from label order); tree children or
    by-lead groups sorted by a count or a rate; cohorts or series weeks sorted by
    a figure. **The near miss it spares:** cards appearing and disappearing as
    the figures change.
    """
    review = lead_review
    owe_every_section(monkeypatch)
    sets = {
        "eight-week": a_named_set(
            review, review.sibling_course, length=8, level_of=review.sibling_course
        ),
        "six-week": a_named_set(review, review.own_course, length=6, level_of=review.own_course),
    }
    answering(review, SIBLING_COHORT, [5], silent=2, tag="first")
    answering(review, UNMAPPED_COHORT, [3, 3, 3], silent=0, tag="first")
    first = read_everything(review, sets)

    answering(review, SIBLING_COHORT, [1, 1, 1, 1], silent=0, tag="second")
    answering(review, UNMAPPED_COHORT, [], silent=4, tag="second")
    second = read_everything(review, sets)

    by_lead_read = [where for where in first if where.split(" ")[0] in BY_LEAD_KINDS]
    assert by_lead_read, (
        f"No by-lead group was read; the chair's reads were {sorted(first)}. A chair is offered "
        "by-lead mode (E9-07 done-when 3), and its groups' figures are lists this test compares."
    )
    series_weeks = [
        len(cohort.get("weeks") or [])
        for where in first
        if where.startswith("series ")
        for cohort in first[where].get("cohorts") or []
    ]
    assert any(
        count >= 2 for count in series_weeks
    ), f"No series cohort held two or more weeks ({series_weeks}), so no week order was compared."

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
