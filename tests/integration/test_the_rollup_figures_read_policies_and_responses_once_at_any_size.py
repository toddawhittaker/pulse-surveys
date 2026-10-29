"""The roll-up figures read policies and responses a fixed number of times — E9-07 done-when 10.

> 10. **Set-based reads.** The payload for the seeded VP reads policies and
>     responses a fixed number of times, whatever the number of sections
>     (counted at two sizes).

The two sizes are two nodes the seeded VP holds: the College of Arts and
Sciences and one of its departments, Mathematics. The college holds every
Mathematics section and more, so a read issued once per section sends more
statements for the college than for the department.

The interface is the one the light builder's module already drives
(`tests/integration/test_the_rollup_tree_on_the_seeded_institution.py`):
`rollup_tree(session, scope=, term_id=, settings=)` and
`rollup_figures(session, scope=, term_id=, kind=, node_id=, settings=)`, with
the scope from `authz.resolve_scope` as `deps.leadership_scope` resolves it.
Every read goes through `pulse_app`'s connection (`docs/MISTAKES.md` entry 46),
and statements are counted on the wire by `tests/fixtures/statements.py`.

**Which failure a red is on dac77db5:** the tree cannot read a department's or a
college's name (`permission denied for table department`, the attempts file),
so the test FAILS on that exception inside its body, before any count.
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

POLICY_TABLE = "response_policy"
RESPONSE_TABLE = "instructor_response"


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


def root_named(tree: Any, name: str) -> Any:
    found = [node for node in tree.hierarchy if node.name == name]
    assert len(found) == 1, (
        f"The tree has {len(found)} roots named {name!r}: "
        f"{[(node.kind, node.name) for node in tree.hierarchy]}."
    )
    return found[0]


def naming(recorded: list[Any], table: str) -> int:
    return sum(1 for statement in recorded if table in statement.sql)


def test_the_vps_figures_read_policies_and_responses_as_often_for_a_college_as_for_a_department(
    seeded_demo: Any, demo_database: Any, authz: Any
) -> None:
    """The same number of policy reads and response reads at two node sizes, and at least one each.

    **The control:** the college holds strictly more sections than the
    department (read off the tree's own counts), so the two sizes really are two
    sizes; and each count is at least one, so equal counts are not two zeros
    from a figures read that never looked at responses (rule 4 of §5.6 needs
    both tables).

    **The mutation it kills:** `is_owed`, or any policy or response read, called
    once per section (or once per course) of the node. **The near miss it
    spares:** a fixed two or three reads of either table per payload.
    """
    from sqlalchemy import select

    from app.config import Settings
    from app.models.term import Term
    from app.services.rollups import rollup_figures, rollup_tree

    seeded(seeded_demo)
    vp = person_named(demo_database, VP)
    dean = person_named(demo_database, DEAN)
    with production_session(demo_database) as session:
        term_id = session.execute(select(Term.id).where(Term.name == TERM_NAME)).scalar_one()
        vp_scope = authz.resolve_scope(session, person_id=vp)
        dean_scope = authz.resolve_scope(session, person_id=dean)
        college = root_named(
            rollup_tree(session, scope=vp_scope, term_id=term_id, settings=Settings()), COLLEGE
        )
        department = root_named(
            rollup_tree(session, scope=dean_scope, term_id=term_id, settings=Settings()),
            DEPARTMENT,
        )
        assert college.section_count > department.section_count > 0, (
            f"The {COLLEGE} counts {college.section_count} sections and {DEPARTMENT} "
            f"{department.section_count}; the college holds the department and more, so this "
            "comparison needs the first strictly larger. A broken world, not a red."
        )

        counts: dict[str, tuple[int, int]] = {}
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
            assert recorded, f"The recorder saw nothing while {label}'s figures were read."
            counts[label] = (naming(recorded, POLICY_TABLE), naming(recorded, RESPONSE_TABLE))

    unread = sorted(
        f"{label} read {table} 0 times"
        for label, pair in counts.items()
        for table, count in zip((POLICY_TABLE, RESPONSE_TABLE), pair, strict=True)
        if count == 0
    )
    assert not unread, (
        f"{unread}. The attention list's rule 4 (§5.6) reads both tables, so a figures read "
        "naming neither is not the read this test counts."
    )
    assert counts[COLLEGE] == counts[DEPARTMENT], (
        f"(policy reads, response reads): {COLLEGE} with {college.section_count} sections "
        f"{counts[COLLEGE]}; {DEPARTMENT} with {department.section_count} sections "
        f"{counts[DEPARTMENT]}. Done-when 10: a fixed number of times whatever the number of "
        "sections."
    )
