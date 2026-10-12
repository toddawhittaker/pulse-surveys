"""§4.1 item 2 on the seeded institution: the lead's tree and node figures hold no sibling course — E9-12 done-when 1.

> 1. … On the seeded world and on one generated world, a Lead Faculty session's
>    tree, roll-up, named-set series, attention cards and drill-down responses
>    carry no id, label or name of a course mapped to another lead, or of its
>    sections … Each has a present twin: the lead's own course appears.

The seeded half. The seed is `scripts/seed.py`, run as a program against a
database of its own (`tests/fixtures/seed.py`). Its Lead Faculty for Linear
Algebra and Statistics leads `MATH 505` and `STAT 250`; `MATH 210` (the Lead
Faculty for Calculus) and `MATH 040` (the Mathematics chair, in a lead hat) sit
under the same `MATH` prefix and are mapped to other people — the siblings SPEC
§4.1 item 2 is about, read here from `lead_faculty_mapping` itself rather than
from this docstring.

**At the service the routes call, not over HTTP**, and the work order's report
says so. No fixture in this suite serves the built application over the demo
database: every HTTP world here is the committed report world on the session
database. So this module reads `rollups.rollup_tree` and `rollups.rollup_figures`
— the two calls behind E9-07's two routes, with the signatures E9-07's own seeded
tests use — through `pulse_app`'s own connection (`docs/MISTAKES.md` entry 46),
with the scope resolved by `authz.resolve_scope` from the person alone, as
`deps.leadership_scope` resolves it. The named-set series and the drill-down are
asked over HTTP in the lead-review and generated worlds
(`test_e9_routes_show_a_lead_nothing_of_a_sibling_leads_course.py`); the seed
holds no named set, and the drill-down's service signature is settled nowhere
this suite can read.

**What is forbidden** is read off the VP's tree — the product's own spellings of
the sibling courses and their sections — and **the present twin** is the lead's
own two courses, by id and by name, in the same answers. The shared owed read is
swapped so every section a node's figures are computed over gets a card
(`tests/fixtures/e9_invariant_pass.py::owe_every_section`).

**Expected green on today's branch**; each test names its mutation and near miss.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest
from fixtures.e9_invariant_pass import FIGURE_KINDS, found_in, owe_every_section

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

TERM_NAME = "Fall 2026"
THE_LEAD = "Demo Lead Faculty for Linear Algebra and Statistics"
VP = "Demo VP of Academics"


def seeded(run: Any) -> None:
    if not run.succeeded:
        pytest.fail(
            "The seed run this module is built on did not succeed; `test_demo_seed_script.py` "
            "owns that failure.\n" + run.report()
        )


def person_named(demo: Any, name: str) -> Any:
    """A seeded person's key, read on the bootstrap identity (`pulse_app` reads no `person`)."""
    from sqlalchemy import text

    with demo.connect() as connection:
        keys = list(
            connection.execute(
                text("SELECT id FROM person WHERE identity_name = :name"), {"name": name}
            ).scalars()
        )
    assert len(keys) == 1, f"The seed holds {len(keys)} people named {name!r}."
    return keys[0]


def mapped_courses(demo: Any) -> dict[str, str]:
    """Every mapped course and the person it is mapped to, from `lead_faculty_mapping`."""
    from sqlalchemy import text

    with demo.connect() as connection:
        rows = connection.execute(
            text("SELECT course_id, person_id FROM public.lead_faculty_mapping")
        ).all()
    return {str(course): str(person) for course, person in rows}


def sections_of(demo: Any, courses: list[str]) -> dict[str, list[str]]:
    from sqlalchemy import text

    with demo.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT course_id, id FROM public.section WHERE course_id = ANY(CAST(:c AS uuid[]))"
            ),
            {"c": courses},
        ).all()
    found: dict[str, list[str]] = {course: [] for course in courses}
    for course, section in rows:
        found[str(course)].append(str(section))
    return found


@contextmanager
def production_session(demo: Any) -> Iterator[Any]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(demo.database.application_url)
    try:
        with Session(bind=engine) as session:
            yield session
    finally:
        engine.dispose()


def plain(value: Any) -> Any:
    """A service answer as JSON-shaped data, the shape the route would serialise."""
    from fixtures.named_set_figures import as_data

    return as_data(value)


def every_node(nodes: Any) -> Iterator[dict[str, Any]]:
    for node in nodes or []:
        yield node
        yield from every_node(node.get("children"))


def names_for(tree: Any, course_ids: set[str]) -> dict[str, str]:
    """The name and label of each listed course node, and of every node under it."""
    found: dict[str, str] = {}

    def is_a_name(value: Any) -> bool:
        return isinstance(value, str) and len(value) >= 4 and any(ch.isalpha() for ch in value)

    for node in every_node(tree.get("hierarchy")):
        if str(node.get("id")) in course_ids:
            for inner in [node, *every_node(node.get("children"))]:
                for member in ("name", "label"):
                    value = inner.get(member)
                    if is_a_name(value):
                        found[f"{inner.get('kind')} {member} {value!r}"] = value
    return found


def test_the_seeded_leads_tree_and_figures_hold_nothing_of_a_sibling_course(
    seeded_demo: Any, demo_database: Any, authz: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seeded lead's tree, and every node's figures and cards, name no sibling course.

    **Present twin:** both of her courses (`MATH 505` and `STAT 250` by the seed;
    by id here, read from the mapping) appear in her tree, and a card for one of
    her sections appears in her figures with every section owed. **Control:** the
    VP's figures for the lead's `MATH` prefix carry a card for a sibling section.

    **The mutation it kills:** the lead clamp dropped; a node's figures computed
    over its containment subtree rather than the reader's held sections (her
    `MATH` prefix then holds `MATH 210` and `MATH 040`). **The near miss it
    spares:** the `MATH` and `STAT` prefixes themselves, which root her tree.
    """
    from sqlalchemy import select

    from app.config import Settings
    from app.models.term import Term
    from app.services.rollups import rollup_figures, rollup_tree

    seeded(seeded_demo)
    lead_key = person_named(demo_database, THE_LEAD)
    lead = str(lead_key)
    vp = person_named(demo_database, VP)
    mapping = mapped_courses(demo_database)
    own = sorted(course for course, person in mapping.items() if person == lead)
    siblings = sorted(course for course, person in mapping.items() if person != lead)
    assert own and siblings, f"The seed maps {own} to the lead and {siblings} to others."
    sections = sections_of(demo_database, own + siblings)
    sibling_sections = [section for course in siblings for section in sections[course]]

    owe_every_section(monkeypatch)
    with production_session(demo_database) as session:
        term_id = session.execute(select(Term.id).where(Term.name == TERM_NAME)).scalar_one()
        lead_scope = authz.resolve_scope(session, person_id=lead_key)
        vp_scope = authz.resolve_scope(session, person_id=vp)
        tree = plain(rollup_tree(session, scope=lead_scope, term_id=term_id, settings=Settings()))
        vps_tree = plain(rollup_tree(session, scope=vp_scope, term_id=term_id, settings=Settings()))
        figures: dict[str, Any] = {}
        for node in every_node(tree.get("hierarchy")):
            if node.get("kind") in FIGURE_KINDS:
                figures[f"{node['kind']} {node.get('name')}"] = plain(
                    rollup_figures(
                        session,
                        scope=lead_scope,
                        term_id=term_id,
                        kind=node["kind"],
                        node_id=UUID(str(node["id"])),
                        settings=Settings(),
                    )
                )
        math = [n for n in every_node(tree.get("hierarchy")) if n.get("kind") == "prefix"]
        assert math, "The seeded lead's tree holds no prefix node."
        vps_prefix = {
            str(n["id"]): plain(
                rollup_figures(
                    session,
                    scope=vp_scope,
                    term_id=term_id,
                    kind="prefix",
                    node_id=UUID(str(n["id"])),
                    settings=Settings(),
                )
            )
            for n in math
        }

    forbidden = {f"sibling course id {c}": c for c in siblings}
    forbidden.update({f"sibling section id {s}": s for s in sibling_sections})
    own_names = names_for(vps_tree, set(own))
    sibling_names = names_for(vps_tree, set(siblings))
    forbidden.update(
        {
            what: text
            for what, text in sibling_names.items()
            if not any(text == mine or text in mine for mine in own_names.values())
        }
    )
    assert any(" name " in what for what in forbidden), (
        f"The VP's tree serves no distinct name for any sibling course ({sibling_names}), so no "
        "name could be asserted absent. A broken world, not a red."
    )

    missing_own = [course for course in own if course not in str(tree)]
    assert (
        not missing_own
    ), f"The present twin failed: the lead's tree does not carry her own courses {missing_own}."
    own_sections = [section for course in own for section in sections[course]]
    assert any(section in str(figures) for section in own_sections), (
        "The present twin failed: no figures answer of the lead's carries a card for one of her "
        "own sections with every section owed."
    )
    assert any(section in str(vps_prefix) for section in sibling_sections), (
        "The control failed: the VP's figures for the lead's prefixes carry no card for any "
        "sibling section with every section owed."
    )
    leaked = {"tree": found_in(tree, forbidden)}
    leaked.update({where: found_in(body, forbidden) for where, body in figures.items()})
    leaked = {where: found for where, found in leaked.items() if found}
    assert not leaked, (
        f"The seeded lead is served sibling courses: {leaked}. SPEC §4.1 item 2: a Lead Faculty "
        "assignment never grants sibling leads' courses."
    )
