"""§4.1 item 2 through every E9 route: a lead is shown nothing of a sibling lead's course — E9-12 done-when 1.

> 1. **§4.1 item 2, through every route.** On the seeded world and on one
>    generated world, a Lead Faculty session's tree, roll-up, named-set series,
>    attention cards and drill-down responses carry no id, label or name of a
>    course mapped to another lead, or of its sections; a drill-down request for
>    such a section answers the same 404 as a section that does not exist. Each
>    has a present twin: the lead's own course appears. Marked `invariant`.

SPEC §4.1 item 2: "A Lead Faculty assignment never grants sibling leads' courses,
at any point in the purview union computation." This module drives E9's four
read routes over HTTP with a Lead Faculty session (`tests/fixtures/
e9_invariant_pass.py` names them), in two worlds:

  - **E6-05's lead-review world** (`tests/fixtures/lead_review.py`): lead A leads
    the report world's course (sections `F1WW` and `Q1WW`); sibling lead B leads
    a course under **the same prefix** (one section, cohort `Y`). The same prefix
    is the point: a prefix node is the first place A's view and B's course meet.
  - **One generated world**, drawn by E9-01's `world_plans` with the sibling-lead
    gadget planted: lead A, lead B on another course, and an instructor on a
    section of B's course **reporting to A** — the "at any point in the union"
    case the lead clamp exists for. The plan is found with `hypothesis.find`, so
    the world is one fixed, minimal draw, and the expectation is read off the plan
    alone (`docs/MISTAKES.md` entry 19), never off `authz`.

The seeded world is `tests/integration/test_e9_a_lead_sees_nothing_of_a_sibling_
course_on_the_seeded_institution.py`, at the service the routes call (no fixture
in this suite serves HTTP over the demo database — said in the work order's
report).

**What "carries no id, label or name" is read as.** The sibling course's id and
its sections' ids, and the strings a reader who may see them is served for them
(the course node's `name` and `label`, each section node's `name` and `label`),
read off **a chair's tree** in the same world — so the names are the product's
own spellings, never this file's — must occur nowhere in the lead's answer, keys
and values alike. Each answer's **present twin** is the lead's own course: its id
(and, on the tree, its name) occurs in the same answer, so an empty answer cannot
pass.

**Cards on every section.** The attention list is only evidence if the page
would make a card for a section it computed over. The shared owed read is
swapped (`owe_every_section`) so every section a node's figures are computed
over is owed: a card for B's section on A's prefix is then exactly "A's figures
were computed over B's section". The chair's same read carries B's section — the
control that the swap reaches a sibling course when the reader holds it.

**Which failure a red is.** These features exist on the branch this is written
against, so every test is expected **green** today; each docstring names the
mutation that turns it red (done-when 9) and the near miss that leaves it green.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.e9_invariant_pass import (
    FIGURE_KINDS,
    a_named_set,
    answer,
    body_of,
    cohort_letters,
    descendants,
    drill_down_url,
    figures_url,
    found_in,
    node_with_id,
    owe_every_section,
    scalar,
    series_url,
    term_of,
    tree_nodes,
    tree_url,
)
from fixtures.lead_review import LeadReviewWorld, Reader
from fixtures.moderation import CLEAR
from fixtures.purview_walk import build_world, world_plans
from fixtures.report_api import FULL_WEEK, TAUGHT_COHORT
from fixtures.report_views import INSTRUCTOR_STREAM
from hypothesis import HealthCheck, find, settings
from hypothesis.errors import NoSuchExample

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

SIBLING_COHORT = "Y"
SIX_WEEKS = 6
EIGHT_WEEKS = 8
DEAN_ROLE = "DEAN"

# The same budget E9-01's coverage tests give `find`: pure Python, no database.
PLAN_BUDGET = settings(
    max_examples=2000,
    deadline=None,
    database=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


# ---------------------------------------------------------------------------
# What a reader who may see a course is served for it.
# ---------------------------------------------------------------------------


def is_a_name(value: Any) -> bool:
    """A string worth searching for: four characters or more, and at least one letter.

    An empty label occurs in every answer, and a bare number can occur inside any
    id's hex, so neither is evidence of a leak when found.
    """
    return isinstance(value, str) and len(value) >= 4 and any(ch.isalpha() for ch in value)


def footprint_of(tree: Any, course_id: Any, section_ids: list[Any], what: str) -> dict[str, str]:
    """Every id, name and label a privileged tree carries for one course and its sections.

    Keyed by a description a failure message can print; see `is_a_name` for the
    strings left out.
    """
    course = node_with_id(tree, course_id)
    if course is None:
        pytest.fail(
            f"The privileged reader's tree holds no node with id {course_id} ({what}); the names "
            "this test forbids are read off that node. A broken world, not a red."
        )
    found: dict[str, str] = {f"{what}: course id": str(course_id)}
    for member in ("name", "label"):
        value = course.get(member)
        if is_a_name(value):
            found[f"{what}: course {member}"] = value
    for section_id in section_ids:
        found[f"{what}: section id {section_id}"] = str(section_id)
    for node in descendants(course):
        for member in ("name", "label"):
            value = node.get(member)
            if is_a_name(value):
                found[f"{what}: {node.get('kind')} {member} {value!r}"] = value
    return found


def without(forbidden: dict[str, str], allowed: list[str]) -> dict[str, str]:
    """`forbidden` less any string the reader's own nodes legitimately carry.

    Section codes repeat across courses (`F1WW` can be a code in two), so a
    sibling string that is also one of the lead's own is not evidence of anything
    and is dropped rather than asserted on.
    """
    return {
        what: text
        for what, text in forbidden.items()
        if not any(text == mine or text in mine for mine in allowed)
    }


def own_strings(tree: Any, course_id: Any) -> list[str]:
    node = node_with_id(tree, course_id)
    if node is None:
        return []
    strings = [str(node.get(m)) for m in ("name", "label") if isinstance(node.get(m), str)]
    for child in descendants(node):
        strings += [str(child.get(m)) for m in ("name", "label") if isinstance(child.get(m), str)]
    return strings


def get(review: LeadReviewWorld, reader: Reader, url: str) -> Any:
    return review.ask("GET", url, token=reader.token)


def lead_review_footprints(review: LeadReviewWorld) -> tuple[dict[str, str], dict[str, str]]:
    """(the sibling course's footprint, the own course's id and name), off the chair's tree."""
    assert review.chair is not None
    term = term_of(review)
    chair_tree = body_of(get(review, review.chair, tree_url(term)), "The chair's tree")
    sibling_section = review.world.section_id(SIBLING_COHORT)
    sibling = footprint_of(chair_tree, review.sibling_course, [sibling_section], "B's course")
    sibling[f"B's section code {review.code_of(SIBLING_COHORT)}"] = review.code_of(SIBLING_COHORT)
    own_node = node_with_id(chair_tree, review.own_course)
    assert own_node is not None, "The chair's tree does not hold lead A's course. A broken world."
    own = {"A's course id": str(review.own_course)}
    if isinstance(own_node.get("name"), str) and own_node["name"]:
        own["A's course name"] = own_node["name"]
    forbidden = without(sibling, own_strings(chair_tree, review.own_course))
    assert any("course name" in what for what in forbidden), (
        f"The sibling course's name is not distinct from lead A's in this world ({sibling}), so "
        "no name could be asserted absent. A broken world, not a red."
    )
    return forbidden, own


def a_published_week_in_the_sibling_section(review: LeadReviewWorld) -> None:
    """One comment in B's section's full week, so its drill-down has a week to refuse past."""
    review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text="E9-12 sibling isolation: a clear comment in the sibling lead's section",
        verdict=CLEAR,
        cohort=SIBLING_COHORT,
    )


# ---------------------------------------------------------------------------
# The lead-review world: one route at a time.
# ---------------------------------------------------------------------------


def test_a_leads_tree_carries_nothing_of_a_sibling_leads_course(
    lead_review: LeadReviewWorld,
) -> None:
    """Lead A's tree names B's course nowhere; it names A's own course.

    **The mutation it kills:** the lead clamp dropped (a lead's purview widened to
    the prefix or to whatever reports to her); the tree built from containment
    under the lead's prefix rather than from her purview's held sections; the
    purview read by person through `transitive_purview` without the clamp.
    **The near miss it spares:** A's prefix itself appearing (it is the root of
    a lead's tree, SPEC §2.1) with counts over her held sections only.
    """
    review = lead_review
    assert review.lead is not None
    forbidden, own = lead_review_footprints(review)
    tree = body_of(get(review, review.lead, tree_url(term_of(review))), "Lead A's tree")

    assert found_in(tree, own) == own, (
        f"The present twin failed: lead A's tree does not carry her own course ({own}); it "
        f"carries {[(n.get('kind'), n.get('name')) for n in tree_nodes(tree)]}."
    )
    leaked = found_in(tree, forbidden)
    assert not leaked, (
        f"Lead A's tree carries the sibling lead's course: {leaked}. SPEC §4.1 item 2: a Lead "
        "Faculty assignment never grants sibling leads' courses."
    )


def test_a_leads_node_figures_and_attention_cards_carry_nothing_of_a_sibling_leads_course(
    lead_review: LeadReviewWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every figures read of every node of A's tree: no id or name of B's course or section.

    The owed read is swapped so every section a node is computed over gets a
    card. **The controls:** A's prefix figures carry a card for her own taught
    section (the present twin), and the chair's figures for the *same prefix*
    carry a card for B's section and a cohort label holding B's start letter —
    so the swap reaches a sibling section when the reader holds it, and absence
    on A's side is A's purview.

    **The mutation it kills:** the figures route computing a node over its
    containment subtree rather than over the reader's held sections (A's prefix
    then holds B's section, its card and its start letter `Y`); the lead clamp
    dropped. **The near miss it spares:** cards and cohorts over A's own sections.
    """
    review = lead_review
    assert review.lead is not None and review.chair is not None
    # B's section answers a week, as A's does. On e32847b8, with B's section
    # unanswered, the chair's cohort label carried `F` alone (the unanswered `Q`
    # was absent too), so an unanswered section gives the control nothing to see.
    a_published_week_in_the_sibling_section(review)
    forbidden, _own = lead_review_footprints(review)
    calls = owe_every_section(monkeypatch)
    term = term_of(review)
    tree = body_of(get(review, review.lead, tree_url(term)), "Lead A's tree")
    nodes = [node for node in tree_nodes(tree) if node.get("kind") in FIGURE_KINDS]
    prefixes = [node for node in nodes if node.get("kind") == "prefix"]
    assert prefixes, f"Lead A's tree holds no prefix node: {[n.get('kind') for n in nodes]}."

    leaks: dict[str, Any] = {}
    taught = str(review.world.section_id(TAUGHT_COHORT))
    own_card_seen = False
    letters_seen: set[str] = set()
    for node in nodes:
        url = figures_url(node["kind"], node["id"], term)
        figures = body_of(get(review, review.lead, url), f"A's figures for {node['kind']}")
        leaked = found_in(figures, forbidden)
        if leaked:
            leaks[f"{node['kind']} {node.get('name')}"] = leaked
        if node.get("kind") == "prefix":
            own_card_seen = own_card_seen or taught in str(figures.get("attention"))
            letters_seen |= cohort_letters(figures)

    prefix = prefixes[0]
    chairs = body_of(
        get(review, review.chair, figures_url("prefix", prefix["id"], term)),
        "The chair's figures for the same prefix",
    )
    sibling_section = str(review.world.section_id(SIBLING_COHORT))
    assert calls, "The swapped owed read was never called, so no card was made on any page."
    assert sibling_section in str(chairs.get("attention")), (
        f"The control failed: the chair's figures for A's prefix carry no card for B's section "
        f"{sibling_section} with every section owed; attention is {chairs.get('attention')!r}."
    )
    assert SIBLING_COHORT in cohort_letters(chairs), (
        f"The control failed: the chair's cohort labels carry letters {cohort_letters(chairs)}, "
        f"not B's {SIBLING_COHORT!r}."
    )
    assert own_card_seen, (
        f"The present twin failed: A's prefix figures carry no card for her own section {taught} "
        "with every section owed."
    )
    assert not leaks, f"Lead A's node figures carry the sibling lead's course: {leaks}."
    assert SIBLING_COHORT not in letters_seen, (
        f"Lead A's prefix cohort labels carry the start letters {sorted(letters_seen)}, B's "
        f"{SIBLING_COHORT!r} among them: her figures were computed over B's section."
    )


def test_a_leads_figures_read_of_a_sibling_leads_course_answers_exactly_as_a_missing_node(
    lead_review: LeadReviewWorld,
) -> None:
    """Lead A asks the figures route for B's course and for a random id: one status, one body.

    **The present twin:** lead B, asking the same URL, is answered 200 — so the
    refusal is A's purview and not a URL nothing answers. **The refusal guard:**
    A's answer is a 4xx, so the equality is not two empty 200s.

    B's course shares A's prefix in this world, so there is no separate prefix
    node of B's to ask for; a lead is offered no by-lead group (E9-07 done-when
    3), so there is no group id of B's either. Both are recorded here rather than
    left unasked.

    **The mutation it kills:** the figures route answering any course id without
    the purview check (E9-12 battery row 1, the lead clamp dropped, reaches it
    this way too); a 403 or another sentence for a node that exists outside the
    purview, which tells the reader the id is real. **The near miss it spares:**
    whatever 404 and sentence the route picks for both.
    """
    review = lead_review
    assert review.lead is not None and review.sibling_lead is not None
    term = term_of(review)
    url = figures_url("course", review.sibling_course, term)

    theirs = answer(get(review, review.sibling_lead, url))
    outside = answer(get(review, review.lead, url))
    missing = answer(get(review, review.lead, figures_url("course", uuid4(), term)))

    assert theirs[0] == 200, (
        f"The present twin failed: lead B asking for her own course's figures answered {theirs[0]} "
        f"{str(theirs[1])[:300]!r}."
    )
    assert 400 <= outside[0] < 500, (
        f"Lead A asking for B's course's figures answered {outside[0]} {str(outside[1])[:300]!r}; "
        "a course outside the purview is refused (SPEC §4.1 item 2)."
    )
    assert outside == missing, (
        f"B's course answered A with {outside}; a course that does not exist answered {missing}. "
        "E9-07 done-when 11: the two are answered exactly alike."
    )


def test_a_leads_named_set_series_carries_nothing_of_a_sibling_leads_course(
    lead_review: LeadReviewWorld,
) -> None:
    """Two sets over both courses: A's series holds her own cohort and nothing of B's.

    An eight-week set at B's course's level: B's section is the only eight-week
    section in the world, so **any** cohort in A's answer is computed over it.
    The chair's answer to the same set holds that cohort (the control). A
    six-week set at A's level: A's answer holds her six-week cohort (the present
    twin). Neither answer of A's carries B's ids or names.

    **The mutation it kills:** the series reading cohorts or figures from the
    set's members rather than from the set's sections inside the reader's
    purview; the lead clamp dropped. **The near miss it spares:** every leader
    listing every set (SPEC §5.5) — only the figures are scoped.
    """
    review = lead_review
    assert review.lead is not None and review.chair is not None
    forbidden, _own = lead_review_footprints(review)
    term = term_of(review)
    both = (review.own_course, review.sibling_course)
    eight = a_named_set(review, *both, length=EIGHT_WEEKS, level_of=review.sibling_course)
    six = a_named_set(review, *both, length=SIX_WEEKS, level_of=review.own_course)

    leads_eight = body_of(get(review, review.lead, series_url(eight, term)), "A's 8-week series")
    chairs_eight = body_of(get(review, review.chair, series_url(eight, term)), "The chair's")
    leads_six = body_of(get(review, review.lead, series_url(six, term)), "A's 6-week series")

    assert chairs_eight.get("cohorts"), (
        "The control failed: the chair's series over the eight-week set holds no cohort, so B's "
        "eight-week section is not one the series reaches when the reader holds it."
    )
    assert leads_six.get("cohorts"), (
        "The present twin failed: lead A's series over the six-week set holds no cohort, though "
        "her own course runs a six-week section."
    )
    assert not leads_eight.get("cohorts"), (
        f"Lead A's series over the eight-week set holds cohorts {leads_eight.get('cohorts')!r}. "
        "She runs no eight-week section; the only one is the sibling lead's."
    )
    leaked = {**found_in(leads_eight, forbidden), **found_in(leads_six, forbidden)}
    assert not leaked, f"Lead A's series carry the sibling lead's course: {leaked}."


def test_a_drill_down_into_a_sibling_leads_section_answers_exactly_as_a_missing_section(
    lead_review: LeadReviewWorld,
) -> None:
    """A asks for B's section and for an id nothing holds: one status, one body; her own: 200.

    B's section has a published week, so the refusal is not the week's. **The
    present twin:** A's own section's drill-down answers 200 and carries none of
    B's footprint.

    **The mutation it kills:** the drill-down checking the section exists but not
    that it is in the purview; a 403 (or another sentence) for a section that
    exists outside the purview. **The near miss it spares:** whatever 404 and
    sentence the route picks for both.
    """
    review = lead_review
    assert review.lead is not None
    forbidden, _own = lead_review_footprints(review)
    a_published_week_in_the_sibling_section(review)
    sibling = review.world.section_id(SIBLING_COHORT)
    own = review.world.section_id(TAUGHT_COHORT)

    outside = answer(get(review, review.lead, drill_down_url(sibling, FULL_WEEK)))
    missing = answer(get(review, review.lead, drill_down_url(uuid4(), FULL_WEEK)))
    mine = body_of(get(review, review.lead, drill_down_url(own, FULL_WEEK)), "A's own section")

    assert outside[0] == 404, (
        f"Lead A's drill-down into B's section answered {outside[0]} {str(outside[1])[:300]!r}; "
        "done-when 1: the same 404 as a section that does not exist."
    )
    assert (
        outside == missing
    ), f"B's section answered {outside}; a section that does not exist answered {missing}."
    leaked = found_in(mine, forbidden)
    assert not leaked, f"Lead A's drill-down of her own section carries B's course: {leaked}."


def published_weeks_url(section_id: Any) -> str:
    """E9-11's drill-down week list (its pull request and integration test spell it)."""
    return f"/leadership/sections/{section_id}/published-weeks"


def test_the_drill_downs_week_list_for_a_sibling_leads_section_answers_exactly_as_a_missing_one(
    lead_review: LeadReviewWorld,
) -> None:
    """A asks B's section's published weeks and a random id's: one status, one body; B's own: 200.

    B's section has a published week, so B's answer lists one and A's refusal is
    the purview's, not an empty section's. **The present twin:** lead B, asking
    for her own section's weeks, is answered 200. **The refusal guard:** A's
    answer is a 4xx, so the equality is not two empty lists.

    **The mutation it kills:** the week list checking that the section exists but
    not that it is in the reader's purview (E9-12 privacy review, T2) — it then
    answers A with B's weeks, which tells A which course weeks B's section ran and
    published; a 403 or another sentence for a section that exists outside the
    purview. **The near miss it spares:** whatever 404 and sentence the route
    picks for both.
    """
    review = lead_review
    assert review.lead is not None and review.sibling_lead is not None
    a_published_week_in_the_sibling_section(review)
    sibling = review.world.section_id(SIBLING_COHORT)

    theirs = answer(get(review, review.sibling_lead, published_weeks_url(sibling)))
    outside = answer(get(review, review.lead, published_weeks_url(sibling)))
    missing = answer(get(review, review.lead, published_weeks_url(uuid4())))

    assert theirs[0] == 200, (
        f"The present twin failed: lead B's own week list answered {theirs[0]} "
        f"{str(theirs[1])[:300]!r}."
    )
    assert 400 <= outside[0] < 500, (
        f"Lead A asking for B's section's weeks answered {outside[0]} {str(outside[1])[:300]!r}; "
        "a section outside the purview is refused (SPEC §4.1 item 2)."
    )
    assert outside == missing, (
        f"B's section's week list answered A with {outside}; a section that does not exist "
        f"answered {missing}. Done-when 1: the same refusal as a section that does not exist."
    )


# ---------------------------------------------------------------------------
# One generated world.
# ---------------------------------------------------------------------------


def a_plan_with_the_sibling_gadget() -> Any:
    """The minimal `world_plans` draw holding the planted gadget (lead A, lead B, A's instructor).

    The gadget is planted on about half the draws (`tests/fixtures/
    purview_walk.py`), so `find` returns one quickly; its absence is a generator
    defect named here rather than a vacuous pass (`docs/MISTAKES.md` entry 15).
    """
    try:
        return find(world_plans(), lambda plan: plan.planted is not None, settings=PLAN_BUDGET)
    except NoSuchExample:
        pytest.fail(
            "`world_plans` never planted the sibling-lead gadget in "
            f"{PLAN_BUDGET.max_examples} draws, so there is no generated world to ask."
        )


def test_on_a_generated_world_a_lead_is_shown_nothing_of_a_sibling_leads_course(
    lead_review: LeadReviewWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The generated world: A's tree, figures, cards and drill-down hold no sibling course.

    The plan's lead A holds one `LEAD_FACULTY` assignment and is mapped to her own
    course; every course mapped to anybody else is a sibling's; an instructor on
    a section of B's course **reports to A's assignment**. Expectations come from
    the plan's mapping alone.

    **Present twins:** A's own course id is in her tree; a drill-down of her own
    section is answered differently from a missing section (no published week
    exists here, so it may be the week's refusal, never the section's). **The
    control:** a dean of every generated college is served the sibling courses'
    names, which are what A must not be.

    **The mutation it kills:** the lead clamp dropped — A's purview then holds the
    section whose instructor reports to her, and its course; the purview read by
    person through the union without the clamp. **The near miss it spares:** the
    instructor edge itself, which is legal and stays in the graph.
    """
    review = lead_review
    plan = a_plan_with_the_sibling_gadget()
    built = build_world(review.graph, plan)
    review.rows.commit()

    a_index = plan.nodes[plan.planted[0]].person
    own_courses = [c for c, lead in enumerate(plan.lead_of_course) if lead == a_index]
    sibling_courses = [
        c for c, lead in enumerate(plan.lead_of_course) if lead is not None and lead != a_index
    ]
    assert own_courses and sibling_courses, (
        f"The plan maps lead A to {own_courses} and others to {sibling_courses}; the gadget plants "
        "one of each. A broken generator, not a red."
    )
    ids = built.ids
    own_sections = [
        ids["section"][s] for s, course in enumerate(plan.section_course) if course in own_courses
    ]
    sibling_ids = {
        ids["course"][c]: [
            ids["section"][s] for s, course in enumerate(plan.section_course) if course == c
        ]
        for c in sibling_courses
    }
    session = review.session
    term = scalar(session, "SELECT term_id FROM section WHERE id = :s", s=own_sections[0])

    lead_a = review.a_leader("generated-lead-a", grants=(), person_id=built.persons[a_index])
    dean = review.a_leader(
        "generated-dean", grants=tuple((DEAN_ROLE, college) for college in ids["college"])
    )
    deans_tree = body_of(get(review, dean, tree_url(term)), "The generated dean's tree")
    forbidden: dict[str, str] = {}
    for course, sections in sibling_ids.items():
        forbidden.update(footprint_of(deans_tree, course, sections, f"sibling course {course}"))
    own_course_keys = [ids["course"][c] for c in own_courses]
    forbidden = without(
        forbidden, [text for key in own_course_keys for text in own_strings(deans_tree, key)]
    )

    owe_every_section(monkeypatch)
    tree = body_of(get(review, lead_a, tree_url(term)), "Generated lead A's tree")
    answers: dict[str, Any] = {"tree": tree}
    for node in tree_nodes(tree):
        if node.get("kind") in FIGURE_KINDS:
            url = figures_url(node["kind"], node["id"], term)
            answers[f"{node['kind']} {node['id']}"] = body_of(
                get(review, lead_a, url), f"Generated lead A's figures for {node['kind']}"
            )

    # No named-set series here: a series carries no ids or names, and this world
    # has no figure planted that would make a sibling's section visible in one,
    # so an absence check over it would have no present twin and prove nothing
    # (E9-12 privacy review, T3). The lead-review world's eight- and six-week
    # pair (`test_a_leads_named_set_series_carries_nothing_of_a_sibling_leads_
    # course`) is the series check.

    some_sibling = next(iter(sibling_ids.values()))[0]
    outside = answer(get(review, lead_a, drill_down_url(some_sibling, 1)))
    missing = answer(get(review, lead_a, drill_down_url(uuid4(), 1)))
    own_answer = answer(get(review, lead_a, drill_down_url(own_sections[0], 1)))

    assert str(own_course_keys[0]) in str(tree), (
        f"The present twin failed: generated lead A's tree does not carry her own course "
        f"{own_course_keys[0]}."
    )
    assert any("course name" in what for what in forbidden), (
        "The control failed: the dean's tree served no name for any sibling course, so no name "
        "could be asserted absent."
    )
    leaks = {where: found_in(body, forbidden) for where, body in answers.items()}
    leaks = {where: found for where, found in leaks.items() if found}
    assert not leaks, f"Generated lead A is shown sibling courses: {leaks}."
    assert (
        400 <= outside[0] < 500 and outside == missing
    ), f"A sibling section answered {outside}; a section that does not exist answered {missing}."
    assert own_answer != missing, (
        "The present twin failed: A's own section answered exactly as a missing one "
        f"({own_answer})."
    )


def test_the_chair_in_this_world_holds_both_courses(lead_review: LeadReviewWorld) -> None:
    """The world's premise, asserted where it can be read: the chair's tree holds A's and B's courses.

    Without it, the sibling course could be absent from every lead's answer
    because the tree reads nothing outside the report world's own course.
    **Not a criterion test**; it carries `invariant` with the module so the
    isolated pass reports a broken world beside the reds it would explain.
    """
    review = lead_review
    assert review.chair is not None
    tree = body_of(get(review, review.chair, tree_url(term_of(review))), "The chair's tree")
    held = {str(node.get("id")) for node in tree_nodes(tree)}
    assert {str(review.own_course), str(review.sibling_course)} <= held, (
        f"The chair's tree holds node ids {sorted(held)}; it should hold both courses of "
        "the department."
    )
