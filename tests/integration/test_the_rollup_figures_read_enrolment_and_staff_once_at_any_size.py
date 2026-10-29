"""The roll-up figures read enrolment, sync days and staff a fixed number of times — E9-07 fix round R1.

Done-when 10 asks for a fixed number of reads "whatever the number of
sections". The first count (`test_the_rollup_figures_read_policies_and_
responses_once_at_any_size.py`) watches only `response_policy` and
`instructor_response`. The data-model review found the enrolled count read once
per section (the first sync day, the enrolment rows, the section's staff
assignments) and, where a section has a staff assignment, once per enrolled
student (the person-for-user definer). The demo seed has no staff assignments
and no students, which is why the first count could not see it.

**The world.** The demo seed, with rows planted on top through the bootstrap
identity: every section of the College of Arts and Sciences gets an
`INSTRUCTOR` assignment for a person of its own and three enrolled students.
Mathematics is one of that college's departments, so the college holds strictly
more sections, staff assignments and students than the department.

**What is counted.** Every statement sent while one node's figures are read,
grouped into four families by the relation or function it names: `enrollment`
(and the roster views over it), `nrps_call` (the first sync day), the
assignment reads (`role_assignment`, `assignment_scope`), and the person-for-user
definer (any function named `person…_for_user…`, so a set-based definer the fix
adds is counted too). Each family must be sent the same number of times for the
college as for the department.

**Which failure a red is on d9fab787:** the per-section and per-student reads
make the college's counts larger, so the equality FAILS, naming the family.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fixtures.statements import statements_recorded

pytestmark = pytest.mark.integration

TERM_NAME = "Fall 2026"
VP = "Demo VP of Academics"
DEAN = "Demo Dean of Arts and Sciences"
COLLEGE = "College of Arts and Sciences"
DEPARTMENT = "Mathematics"
STUDENTS_PER_SECTION = 3

FAMILIES = {
    "enrolment": ("enrollment", "section_roster", "section_enrollment_count"),
    "first sync day": ("nrps_call",),
    "staff assignments": ("role_assignment", "assignment_scope"),
}
PERSON_FOR_USER = "person-for-user definer"


def seeded(run: Any) -> None:
    if not run.succeeded:
        pytest.fail(
            "The seed run this module is built on did not succeed; `test_demo_seed_script.py` "
            "owns that failure.\n" + run.report()
        )


def person_named(demo: Any, name: str) -> Any:
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


def plant_staff_and_students(demo: Any, tables: dict[str, Any], college_name: str) -> int:
    """An instructor and three students on every section of the college; the sections planted."""
    from fixtures.supervision import SupervisionGraph, seed_row
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.config import DEVELOPMENT_ENVIRONMENT

    engine = create_engine(demo.database.superuser_url)
    try:
        with Session(bind=engine, info={"environment": DEVELOPMENT_ENVIRONMENT}) as session:
            sections = [
                dict(row)
                for row in session.execute(
                    text(
                        "SELECT s.* FROM public.section s "
                        "JOIN public.containment_path cp ON cp.section_id = s.id "
                        "JOIN public.college c ON c.id = cp.college_id "
                        "WHERE c.name = :college"
                    ),
                    {"college": college_name},
                ).mappings()
            ]
            graph = SupervisionGraph(session, tables)
            for section in sections:
                graph.assign("INSTRUCTOR", scope=section["id"], person=graph.person())
                # The section's own term rides the chain, so a composite key from
                # the enrolment to `section (id, term_id)` meets the same term.
                ancestors: dict[str, Any] = {"section": section}
                if section.get("term_id") is not None:
                    ancestors["term"] = dict(
                        session.execute(
                            text("SELECT * FROM public.term WHERE id = :term"),
                            {"term": section["term_id"]},
                        )
                        .mappings()
                        .one()
                    )
                for _student in range(STUDENTS_PER_SECTION):
                    seed_row(session, tables, "enrollment", dict(ancestors))
            session.commit()
    finally:
        engine.dispose()
    return len(sections)


def family_counts(recorded: list[Any]) -> dict[str, int]:
    import re

    lowered = [statement.sql.lower() for statement in recorded]
    counts = {
        family: sum(1 for sql in lowered if any(name in sql for name in names))
        for family, names in FAMILIES.items()
    }
    definer = re.compile(r"person\w*_for_user")
    counts[PERSON_FOR_USER] = sum(1 for sql in lowered if definer.search(sql))
    return counts


def root_named(tree: Any, name: str) -> Any:
    found = [node for node in tree.hierarchy if node.name == name]
    assert len(found) == 1, (
        f"The tree has {len(found)} roots named {name!r}: "
        f"{[(node.kind, node.name) for node in tree.hierarchy]}."
    )
    return found[0]


def test_a_college_and_one_of_its_departments_send_each_enrolment_and_staff_read_equally_often(
    seeded_demo: Any, demo_database: Any, authz: Any, metadata_tables: dict[str, Any]
) -> None:
    """Each of the four read families: the same count for the college as for Mathematics.

    **The controls:** the planting reached every section of the college; the
    college holds strictly more sections than the department; and the
    enrolment family and the person-for-user definer are each sent at least
    once for the college, so equal counts are not two zeros from a figures read
    that never asked who is enrolled (with a staff assignment on every section,
    the staff filter has someone to compare against).

    **The mutations it kills:** `reporting._enrolled_students` (or any of its
    reads) called once per section; `person_for_user` called once per student;
    a first-sync-day read per section. **The near miss it spares:** a fixed
    handful of grouped reads per payload, whatever the node's size.
    """
    from sqlalchemy import select

    from app.config import Settings
    from app.models.term import Term
    from app.services.rollups import rollup_figures, rollup_tree

    seeded(seeded_demo)
    planted = plant_staff_and_students(demo_database, metadata_tables, COLLEGE)
    assert planted >= 2, f"Only {planted} sections of the {COLLEGE} were found to plant on."

    vp = person_named(demo_database, VP)
    dean = person_named(demo_database, DEAN)
    with production_session(demo_database) as session:
        term_id = session.execute(select(Term.id).where(Term.name == TERM_NAME)).scalar_one()
        vp_scope = authz.resolve_scope(session, person_id=vp)
        college = root_named(
            rollup_tree(session, scope=vp_scope, term_id=term_id, settings=Settings()), COLLEGE
        )
        department = root_named(
            rollup_tree(
                session,
                scope=authz.resolve_scope(session, person_id=dean),
                term_id=term_id,
                settings=Settings(),
            ),
            DEPARTMENT,
        )
        assert college.section_count > department.section_count > 0, (
            f"The {COLLEGE} counts {college.section_count} sections and {DEPARTMENT} "
            f"{department.section_count}. A broken world, not a red."
        )

        counts: dict[str, dict[str, int]] = {}
        for label, kind, node_id in (
            (COLLEGE, "college", college.id),
            (DEPARTMENT, "department", department.id),
        ):
            with statements_recorded() as recorded:
                rollup_figures(
                    session,
                    scope=vp_scope,
                    term_id=term_id,
                    kind=kind,
                    node_id=node_id,
                    settings=Settings(),
                )
            counts[label] = family_counts(recorded)

    unread = [family for family in ("enrolment", PERSON_FOR_USER) if counts[COLLEGE][family] == 0]
    assert not unread, (
        f"The college's figures sent no statement of {unread} ({counts[COLLEGE]}). Every section "
        f"has {STUDENTS_PER_SECTION} students and an instructor, so the enrolled count reads both; "
        "if a renamed definer answers the staff hop, this module's pattern must learn its name."
    )
    differing = {
        family: (counts[COLLEGE][family], counts[DEPARTMENT][family])
        for family in counts[COLLEGE]
        if counts[COLLEGE][family] != counts[DEPARTMENT][family]
    }
    assert not differing, (
        f"(college with {college.section_count} sections, {DEPARTMENT} with "
        f"{department.section_count}) statements per family: {differing}. Done-when 10 and fix "
        "round R1: a fixed number of reads whatever the number of sections and students."
    )
