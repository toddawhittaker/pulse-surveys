"""The roll-up tree over the demo seed: roots per role, held-only counts, set-based reads (SPEC §5.5).

The seed is `scripts/seed.py`, run as a program against a database of its own
(`tests/fixtures/seed.py`), and every read here goes through `pulse_app`'s
connection, the one production uses (`docs/MISTAKES.md` entry 46). The scope is
resolved by `authz.resolve_scope` from the person alone, as
`deps.leadership_scope` resolves it.

The seed's own spellings: its VP of Academics; the Dean of Arts and Sciences
(Mathematics, Biology and Psychology); the Chair of Mathematics (MATH, STAT,
MIS); the Lead Faculty for Linear Algebra and Statistics (MATH 505, STAT 250);
and the assistant dean, who supervises the Mathematics and Biology chairs and
leads PSYC 110 (SPEC §2.1's worked example). Every section the seed writes is
in Fall 2026.
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
MATH_CHAIR = "Demo Chair of Mathematics"
PSYCHOLOGY_CHAIR = "Demo Chair of Psychology"
TWO_COURSE_LEAD = "Demo Lead Faculty for Linear Algebra and Statistics"
ASSISTANT_DEAN = "Demo Assistant Dean of Arts and Sciences"


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
        found = connection.execute(
            text("SELECT id FROM person WHERE identity_name = :name"), {"name": name}
        ).scalars()
        keys = list(found)
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


def tree_of(demo: Any, name: str, authz: Any) -> Any:
    from sqlalchemy import select

    from app.config import Settings
    from app.models.term import Term
    from app.services.rollups import rollup_tree

    person = person_named(demo, name)
    with production_session(demo) as session:
        term_id = session.execute(select(Term.id).where(Term.name == TERM_NAME)).scalar_one()
        scope = authz.resolve_scope(session, person_id=person)
        return rollup_tree(session, scope=scope, term_id=term_id, settings=Settings())


def roots(tree: Any) -> list[tuple[str, str]]:
    return [(node.kind, node.name) for node in tree.hierarchy]


def root_named(tree: Any, name: str) -> Any:
    found = [node for node in tree.hierarchy if node.name == name]
    assert len(found) == 1, f"The tree has {len(found)} roots named {name!r}: {roots(tree)}."
    return found[0]


@pytest.mark.parametrize(
    ("reader", "expected"),
    [
        (
            VP,
            [
                ("college", "College of Arts and Sciences"),
                ("college", "College of Business and Technology"),
            ],
        ),
        (
            DEAN,
            [
                ("department", "Biology"),
                ("department", "Mathematics"),
                ("department", "Psychology"),
            ],
        ),
        (MATH_CHAIR, [("prefix", "MATH"), ("prefix", "MIS"), ("prefix", "STAT")]),
        (TWO_COURSE_LEAD, [("prefix", "MATH"), ("prefix", "STAT")]),
        (
            ASSISTANT_DEAN,
            [("department", "Biology"), ("department", "Mathematics"), ("prefix", "PSYC")],
        ),
    ],
)
def test_each_role_is_rooted_where_section_2_1_says(
    seeded_demo: Any, demo_database: Any, authz: Any, reader: str, expected: list[Any]
) -> None:
    """VP at colleges, dean at departments, chair and lead at prefixes, the assistant dean at both.

    The roots are in name order, which is the only order the tree has.
    """
    seeded(seeded_demo)
    assert roots(tree_of(demo_database, reader, authz)) == expected


def test_a_prefix_reached_through_one_led_course_counts_that_course_and_its_sections(
    seeded_demo: Any, demo_database: Any, authz: Any
) -> None:
    """PSYC holds PSYC 110 (two sections) and PSYC 545 (one); the assistant dean leads only 110.

    The assistant dean's PSYC root counts one course and two sections; the
    Psychology chair, who holds the whole prefix, counts two and three (the
    wholly held twin). The same pair for MATH: the lead of MATH 505 counts one
    course and one section, the Mathematics chair three and four.
    """
    seeded(seeded_demo)
    partial = root_named(tree_of(demo_database, ASSISTANT_DEAN, authz), "PSYC")
    whole = root_named(tree_of(demo_database, PSYCHOLOGY_CHAIR, authz), "PSYC")
    assert (partial.course_count, partial.section_count) == (1, 2)
    assert partial.label == "1 course · 2 sections"
    assert (whole.course_count, whole.section_count) == (2, 3)

    lead_math = root_named(tree_of(demo_database, TWO_COURSE_LEAD, authz), "MATH")
    chair_math = root_named(tree_of(demo_database, MATH_CHAIR, authz), "MATH")
    assert (lead_math.course_count, lead_math.section_count) == (1, 1)
    assert (chair_math.course_count, chair_math.section_count) == (3, 4)


def test_the_deans_department_rows_name_their_chairs_and_count_prefixes(
    seeded_demo: Any, demo_database: Any, authz: Any
) -> None:
    """SPEC §2.1's department label: "N prefixes · N sections · Chair: {name}"."""
    seeded(seeded_demo)
    math = root_named(tree_of(demo_database, DEAN, authz), "Mathematics")
    assert math.label == f"3 prefixes · 7 sections · Chair: {MATH_CHAIR}"


def test_the_vps_college_row_names_its_dean(
    seeded_demo: Any, demo_database: Any, authz: Any
) -> None:
    """SPEC §2.1's college label: "N departments · N sections · Dean: {name}"."""
    seeded(seeded_demo)
    college = root_named(tree_of(demo_database, VP, authz), "College of Arts and Sciences")
    assert college.department_count == 3
    assert college.label.startswith("3 departments · ")
    assert college.label.endswith(f" · Dean: {DEAN}")


def test_the_seeded_vps_reads_send_policies_and_responses_a_fixed_number_of_times(
    seeded_demo: Any, demo_database: Any, authz: Any
) -> None:
    """The tree reads neither table; one college's figures read each exactly once.

    `tests/integration/test_the_rollup_figures_and_attention.py` counts the same
    two reads at two sizes of node.
    """
    from sqlalchemy import select

    from app.config import Settings
    from app.models.term import Term
    from app.services.rollups import rollup_figures, rollup_tree

    seeded(seeded_demo)
    person = person_named(demo_database, VP)
    with production_session(demo_database) as session:
        term_id = session.execute(select(Term.id).where(Term.name == TERM_NAME)).scalar_one()
        scope = authz.resolve_scope(session, person_id=person)
        with statements_recorded() as tree_reads:
            tree = rollup_tree(session, scope=scope, term_id=term_id, settings=Settings())
        college = root_named(tree, "College of Arts and Sciences")
        with statements_recorded() as figure_reads:
            rollup_figures(
                session,
                scope=scope,
                term_id=term_id,
                kind="college",
                node_id=college.id,
                settings=Settings(),
            )

    def naming(recorded: list[Any], table: str) -> int:
        return sum(1 for statement in recorded if table in statement.sql)

    assert tree_reads, "The recorder saw nothing while the tree was read."
    assert (naming(tree_reads, "response_policy"), naming(tree_reads, "instructor_response")) == (
        0,
        0,
    )
    assert (
        naming(figure_reads, "response_policy"),
        naming(figure_reads, "instructor_response"),
    ) == (1, 1)
