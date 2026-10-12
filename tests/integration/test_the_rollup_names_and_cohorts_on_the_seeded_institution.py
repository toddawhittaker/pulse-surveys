"""Staff names in one call, and one series per start cohort, over the demo seed — E9-07 done-whens 5 and 6.

> 5. **Names, in one call.** The payload names the dean, chairs, leads and each
>    section's instructor through E9-03's door in one call (a query-count
>    test), and omits the lead's name in the lead's own view.
>
> 6. **Series per start cohort.** For a node holding two start cohorts, the
>    payload carries one series per cohort on the term axis, each point at the
>    term week of its course week, with the cohort's label ("U sections ·
>    started 8/17").

The interface (the coordinator's settled note): `rollups` imports
`section_staff_names` by name, and one `rollup_tree` calls it exactly once.
`RollupNode` carries `kind`, `name`, `label`, `section_count`, `staff_name` and
`children`. `rollup_figures(...)` returns `cohorts`, one `RollupCohort
(section_start_date, label, weeks)` per distinct start date among the node's
sections, ordered by start date; each `RollupWeek` carries `course_week` and
`term_week`.

**The expected cohorts are read independently of the service and of the seed
script** (`docs/MISTAKES.md` entry 58): the college's sections from ADR 0046's
`containment_path`, their start dates from `section`, and the term's first day
from `term`, all as `pulse_app`, which holds `SELECT` on each.

**Which failure a red is on dac77db5:** `rollup_tree` cannot read a department's
name (`permission denied for table department`), so each test FAILS on that
exception inside its body.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

import pytest

pytestmark = pytest.mark.integration

TERM_NAME = "Fall 2026"
VP = "Demo VP of Academics"
MATH_CHAIR = "Demo Chair of Mathematics"
TWO_COURSE_LEAD = "Demo Lead Faculty for Linear Algebra and Statistics"
COLLEGE = "College of Arts and Sciences"


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


def term_id_of(session: Any) -> Any:
    from sqlalchemy import select

    from app.models.term import Term

    return session.execute(select(Term.id).where(Term.name == TERM_NAME)).scalar_one()


def tree_of(session: Any, authz: Any, person: Any) -> Any:
    from app.config import Settings
    from app.services.rollups import rollup_tree

    scope = authz.resolve_scope(session, person_id=person)
    return rollup_tree(session, scope=scope, term_id=term_id_of(session), settings=Settings())


def every_node(nodes: list[Any]) -> Iterator[Any]:
    for node in nodes:
        yield node
        yield from every_node(list(node.children or []))


def naming(node: Any, name: str) -> bool:
    return node.staff_name == name or name in (node.label or "")


# ---------------------------------------------------------------------------
# Done-when 5: names in one call, and the lead's own name omitted.
# ---------------------------------------------------------------------------


def test_the_vps_tree_reads_every_staff_name_in_one_call(
    seeded_demo: Any, demo_database: Any, authz: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One `rollup_tree` for the VP calls `section_staff_names` exactly once, and the names arrive.

    **The control:** the tree names somebody (the Mathematics chair, on the
    dean's department rows the VP's tree also holds), so one call is not zero
    names read some other way. **The mutation it kills:** a call per node, per
    level or per role. **The near miss it spares:** a call carrying every
    section of the purview at once.
    """
    import app.services.rollups as rollups

    seeded(seeded_demo)
    original = getattr(rollups, "section_staff_names", None)
    if original is None:
        pytest.fail(
            "`app.services.rollups` has no `section_staff_names`; the settled interface imports "
            "E9-03's door by name."
        )
    calls: list[int] = []

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(rollups, "section_staff_names", counted)
    vp = person_named(demo_database, VP)
    with production_session(demo_database) as session:
        tree = tree_of(session, authz, vp)

    named = [node.name for node in every_node(tree.hierarchy) if naming(node, MATH_CHAIR)]
    assert named, (
        f"No node of the VP's tree names {MATH_CHAIR!r}; the Mathematics department row's label "
        "is '… · Chair: {name}'."
    )
    assert len(calls) == 1, (
        f"One VP tree called `section_staff_names` {len(calls)} times; done-when 5: one call per "
        "payload."
    )


def test_a_leads_own_tree_omits_her_name_and_her_chairs_tree_shows_it(
    seeded_demo: Any, demo_database: Any, authz: Any
) -> None:
    """The two-course lead's own tree names her nowhere as lead; the Mathematics chair's does.

    **The control:** the chair's tree carries "Lead: {name}" (or the lead as a
    node's staff name) for her courses. **The mutation it kills:** the lead's
    name shown in her own view. **The near miss it spares:** her name in the
    chair's view.
    """
    seeded(seeded_demo)
    lead = person_named(demo_database, TWO_COURSE_LEAD)
    chair = person_named(demo_database, MATH_CHAIR)
    with production_session(demo_database) as session:
        own = tree_of(session, authz, lead)
        chairs = tree_of(session, authz, chair)

    assert any(
        naming(node, TWO_COURSE_LEAD) for node in every_node(chairs.hierarchy)
    ), f"The control failed: the Mathematics chair's tree names {TWO_COURSE_LEAD!r} nowhere."
    shown = [
        (node.kind, node.name, node.label)
        for node in every_node(own.hierarchy)
        if naming(node, TWO_COURSE_LEAD)
    ]
    assert (
        not shown
    ), f"The lead's own tree names her: {shown}. Done-when 5: no lead name in the lead's own view."


# ---------------------------------------------------------------------------
# Done-when 6: one series per start cohort.
# ---------------------------------------------------------------------------


def start_dates_by_section(session: Any, college_id: Any) -> dict[str, date]:
    from sqlalchemy import text

    rows = session.execute(
        text(
            "SELECT s.id, s.start_date FROM public.containment_path cp "
            "JOIN public.section s ON s.id = cp.section_id "
            "WHERE cp.college_id = :college"
        ),
        {"college": college_id},
    ).all()
    return {str(row[0]): row[1] for row in rows}


def test_a_college_with_two_start_cohorts_carries_one_labelled_series_each_on_the_term_axis(
    seeded_demo: Any, demo_database: Any, authz: Any
) -> None:
    """One cohort per distinct start date, in date order, labelled with its count and date, on the term axis.

    Term week = course week + whole weeks from the term's first day to the
    cohort's start. The label is "N sections · started M/D" (N counted over the
    college's sections with that start date; "1 section" is allowed).

    **The control:** the college's sections start on at least two dates (the
    ticket owns seed additions if the term is too thin), and at least one cohort
    carries a week. **The mutations it kills:** cohorts merged into one line;
    points on the course-week axis (term week = course week); a cohort's label
    counting another cohort's sections; cohorts ordered by a figure.
    """
    from sqlalchemy import text

    from app.config import Settings
    from app.services.rollups import rollup_figures

    seeded(seeded_demo)
    vp = person_named(demo_database, VP)
    with production_session(demo_database) as session:
        term_id = term_id_of(session)
        term_start = session.execute(
            text("SELECT start_date FROM public.term WHERE id = :term"), {"term": term_id}
        ).scalar_one()
        tree = tree_of(session, authz, vp)
        colleges = [node for node in tree.hierarchy if node.name == COLLEGE]
        assert len(colleges) == 1, f"The VP's tree has {len(colleges)} roots named {COLLEGE!r}."
        college = colleges[0]
        starts = start_dates_by_section(session, college.id)
        scope = authz.resolve_scope(session, person_id=vp)
        figures = rollup_figures(
            session,
            scope=scope,
            term_id=term_id,
            kind="college",
            node_id=college.id,
            settings=Settings(),
        )

    distinct = sorted(set(starts.values()))
    assert len(distinct) >= 2, (
        f"The {COLLEGE}'s sections start on {distinct}; done-when 6 needs a node holding two start "
        "cohorts, and E9-07 owns roll-up additions to `scripts/seed.py` if the seeded term is too "
        "thin to show them."
    )
    served = [cohort.section_start_date for cohort in figures.cohorts]
    assert served == distinct, (
        f"The college's figures carry cohorts starting {served}; its sections start on {distinct}, "
        "one series per start date, in date order."
    )

    wrong_labels = []
    wrong_weeks = []
    for cohort in figures.cohorts:
        start = cohort.section_start_date
        count = sum(1 for begun in starts.values() if begun == start)
        pattern = rf"{count} sections? · started {start.month}/{start.day}"
        if not re.fullmatch(pattern, cohort.label):
            wrong_labels.append((str(start), cohort.label, f"{count} sections · started …"))
        offset = (start - term_start).days // 7
        wrong_weeks.extend(
            (str(start), week.course_week, week.term_week)
            for week in cohort.weeks
            if week.term_week != week.course_week + offset
        )
    assert any(
        cohort.weeks for cohort in figures.cohorts
    ), "No cohort of the college carries a week, so the term-axis check below ran over nothing."
    assert not wrong_labels, f"Cohort labels (start, served, expected): {wrong_labels}."
    assert not wrong_weeks, (
        f"Points off the term axis (start, course week, served term week): {wrong_weeks}. Each "
        "point sits at the term week of its course week."
    )
