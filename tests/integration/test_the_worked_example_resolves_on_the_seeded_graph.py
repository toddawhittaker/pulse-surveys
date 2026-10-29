"""SPEC §2.1's worked example, resolved on the demo seed — E9-01, done-when 1.

> 1. On the seeded graph, the assistant dean's leadership scope holds exactly
>    PSYC 110 and its sections, plus the Math and Biology departments' whole
>    subtrees, and nothing else of Psychology. The Psychology chair's scope holds
>    the Psychology department and not the Math or Biology departments. Asserted
>    against named nodes, with a present twin for each absent one.

The seed is `scripts/seed.py`, run as a program by `tests/fixtures/seed.py`
against a database of its own — the fixture E0-17 built "for E9 to reuse". Its
assistant dean, "Demo Assistant Dean of Arts and Sciences", is scoped to the
College of Arts and Sciences, supervises the chairs of Mathematics and Biology,
and leads PSYC 110 under the chair of Psychology, who reports straight to the
dean. Every name below is the seed's own spelling, read out of the script.

**The expectation is read from the containment tables, not from `authz`.** Which
prefixes, courses and sections sit under Mathematics and Biology is read off the
seeded rows by following foreign keys, so a section the seed or a later launch
adds under those departments is expected too, and the comparison stays exact
(`docs/MISTAKES.md` entry 19).

**The scope is resolved through the production connection**: a `pulse_app`
session on the seeded database, which holds only what the migrations grant
(`docs/MISTAKES.md` entry 46). The names are found on the bootstrap identity,
because `pulse_app` is not granted the person table.

**Which failure a red is, before E9-01 lands.** `resolve_scope` answers today
with own grants only: the assistant dean gets PSYC 110 and none of Mathematics or
Biology, so the exact comparison fails on its assertion. The grants test fails
on the missing `ActorScope.grants` attribute.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fixtures.purview_walk import PURVIEW_LEVELS, difference, levels, role_token
from fixtures.supervision import (
    ROLE_COLUMN_CANDIDATES,
    foreign_key_columns,
    require_column,
    require_table,
    single_primary_key,
)

pytestmark = pytest.mark.integration

# The seed's own spellings (`scripts/seed.py`, `PEOPLE`, `COLLEGES`, `COURSES`).
ASSISTANT_DEAN = "Demo Assistant Dean of Arts and Sciences"
PSYCHOLOGY_CHAIR = "Demo Chair of Psychology"
SUPERVISED = ("Mathematics", "Biology")
UNSUPERVISED = "Psychology"
LED_COURSE = ("PSYC", "110")
OTHER_PSYCHOLOGY_COURSE = ("PSYC", "545")

PERSON_NAME_COLUMN = "identity_name"  # ADR 0066: `person.identity_name`, NOT NULL.
DEPARTMENT_NAME_COLUMN = "name"
PREFIX_CODE_COLUMNS = ("code", "lms_code", "prefix_code")
COURSE_NUMBER_COLUMN = "lms_number"


def seeded(run: Any) -> None:
    """Stop unless the seed run succeeded. A copy of `test_demo_seed_script.py::seeded`."""
    if not run.succeeded:
        pytest.fail(
            "The seed run this module is built on did not succeed, so nothing below can mean "
            "anything; `test_demo_seed_script.py` owns that failure.\n" + run.report()
        )


class SeededTree:
    """The seeded containment tree and people, read on the bootstrap identity."""

    def __init__(self, connection: Any, tables: dict[str, Any]) -> None:
        from sqlalchemy import select

        def rows(name: str) -> list[dict[str, Any]]:
            table = require_table(tables, name)
            return [dict(row) for row in connection.execute(select(table)).mappings()]

        def key(name: str) -> str:
            return single_primary_key(require_table(tables, name))

        def link(child: str, parent: str) -> str:
            found = foreign_key_columns(require_table(tables, child), parent)
            if len(found) != 1:
                pytest.fail(f"`{child}` has {found} keyed to `{parent}`; this reader needs one.")
            return found[0]

        self.departments = {
            row[DEPARTMENT_NAME_COLUMN]: row[key("department")] for row in rows("department")
        }
        prefix_code = require_column(require_table(tables, "prefix"), PREFIX_CODE_COLUMNS)
        self.prefixes = rows("prefix")
        self.prefix_key, self.prefix_department = key("prefix"), link("prefix", "department")
        self.prefix_code = prefix_code
        self.courses = rows("course")
        self.course_key, self.course_prefix = key("course"), link("course", "prefix")
        self.sections = rows("section")
        self.section_key, self.section_course = key("section"), link("section", "course")

        person_table = require_table(tables, "person")
        if PERSON_NAME_COLUMN not in person_table.c:
            pytest.fail(f"`person` has no `{PERSON_NAME_COLUMN}` column (ADR 0066).")
        self.people = {row[PERSON_NAME_COLUMN]: row[key("person")] for row in rows("person")}

        assignments = require_table(tables, "role_assignment")
        self.assignment_key = key("role_assignment")
        self.assignment_person = link("role_assignment", "person")
        self.assignment_role = require_column(assignments, ROLE_COLUMN_CANDIDATES)
        self.assignments = rows("role_assignment")

    def department(self, name: str) -> Any:
        if name not in self.departments:
            pytest.fail(f"The seed holds no department named {name!r}: {sorted(self.departments)}.")
        return self.departments[name]

    def person(self, name: str) -> Any:
        if name not in self.people:
            pytest.fail(f"The seed holds nobody named {name!r}.")
        return self.people[name]

    def course(self, code: str, number: str) -> Any:
        under = {
            row[self.prefix_key] for row in self.prefixes if str(row[self.prefix_code]) == code
        }
        found = [
            row[self.course_key]
            for row in self.courses
            if row[self.course_prefix] in under and str(row[COURSE_NUMBER_COLUMN]) == number
        ]
        if len(found) != 1:
            pytest.fail(f"The seed holds {len(found)} courses numbered {code} {number}.")
        return found[0]

    def sections_of(self, courses: set[Any]) -> frozenset[Any]:
        return frozenset(
            row[self.section_key] for row in self.sections if row[self.section_course] in courses
        )

    def subtree(self, department: Any) -> dict[str, frozenset[Any]]:
        """A department and everything the seeded tables put under it."""
        prefixes = {
            row[self.prefix_key]
            for row in self.prefixes
            if row[self.prefix_department] == department
        }
        courses = {
            row[self.course_key] for row in self.courses if row[self.course_prefix] in prefixes
        }
        out = {name: frozenset() for name in PURVIEW_LEVELS}
        out["department_ids"] = frozenset({department})
        out["prefix_ids"] = frozenset(prefixes)
        out["course_ids"] = frozenset(courses)
        out["section_ids"] = self.sections_of(courses)
        return out

    def assignments_of(self, person: Any) -> dict[str, str]:
        """Each of a person's assignments, as id → canonical role."""
        return {
            str(row[self.assignment_key]): role_token(row[self.assignment_role])
            for row in self.assignments
            if row[self.assignment_person] == person
        }


def union(*many: dict[str, frozenset[Any]]) -> dict[str, frozenset[Any]]:
    out: dict[str, frozenset[Any]] = {name: frozenset() for name in PURVIEW_LEVELS}
    for one in many:
        out = {name: out[name] | one[name] for name in PURVIEW_LEVELS}
    return out


@contextmanager
def seeded_tree(demo: Any, tables: dict[str, Any]) -> Iterator[SeededTree]:
    with demo.connect() as connection:
        yield SeededTree(connection, tables)


@contextmanager
def production_session(demo: Any) -> Iterator[Any]:
    """A `pulse_app` session on the seeded database (`docs/MISTAKES.md` entry 46)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(demo.database.application_url)
    try:
        with Session(bind=engine) as session:
            yield session
    finally:
        engine.dispose()


def led_course_levels(tree: SeededTree) -> dict[str, frozenset[Any]]:
    course = tree.course(*LED_COURSE)
    out = {name: frozenset() for name in PURVIEW_LEVELS}
    out["course_ids"] = frozenset({course})
    out["section_ids"] = tree.sections_of({course})
    return out


@pytest.mark.invariant
def test_the_assistant_deans_scope_is_psyc_110_and_the_two_supervised_departments(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any], authz: Any
) -> None:
    """The first half of done-when 1, exactly, with a present twin for each absence.

    Expected: PSYC 110 and its sections, plus the whole subtrees of Mathematics
    and Biology; no college, no institution, nothing else of Psychology. Named
    twins: Mathematics and Biology present beside Psychology absent; PSYC 110
    present beside PSYC 545 absent.

    **The mutations this kill:** the union deferred (only PSYC 110 — the answer
    today); the assistant dean's own grant read off the college (Psychology and
    the college itself arrive); the lead clamp's opposite — PSYC 110's lead
    assignment pulling up its chair's department. A one-level walk is *not*
    killed here (the assistant dean's chairs are one edge away); the chain tests
    in `test_the_purview_walk_is_transitive_and_batched_by_level.py` kill it.
    """
    seeded(seeded_demo)
    with seeded_tree(demo_database, metadata_tables) as tree:
        person = tree.person(ASSISTANT_DEAN)
        supervised = [tree.department(name) for name in SUPERVISED]
        psychology = tree.department(UNSUPERVISED)
        expected = union(*(tree.subtree(d) for d in supervised), led_course_levels(tree))
        led = tree.course(*LED_COURSE)
        other_psychology = tree.course(*OTHER_PSYCHOLOGY_COURSE)

    with production_session(demo_database) as session:
        held = levels(authz.resolve_scope(session, person_id=person).purview)

    assert set(supervised) <= held["department_ids"], (
        f"The assistant dean's scope does not hold both supervised departments {SUPERVISED}: "
        f"it holds {sorted(map(str, held['department_ids']))}. SPEC §2.1: 'own led courses union "
        "every supervised chair's department'."
    )
    assert psychology not in held["department_ids"], (
        "The assistant dean's scope holds the Psychology department, whose chair reports straight "
        "to the dean. The assistant dean leads one course there and supervises nobody in it."
    )
    assert led in held["course_ids"], "The assistant dean's scope does not hold PSYC 110."
    assert (
        other_psychology not in held["course_ids"]
    ), "The assistant dean's scope holds PSYC 545, a Psychology course they do not lead."
    assert held == expected, (
        f"The assistant dean's scope differs from SPEC §2.1's worked example: "
        f"{difference(held, expected)}."
    )


@pytest.mark.invariant
def test_the_psychology_chairs_scope_is_psychology_and_not_the_supervised_departments(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any], authz: Any
) -> None:
    """The second half of done-when 1: the chair beside the assistant dean, on the same seed.

    The Psychology chair reports straight to the dean and has the assistant
    dean's PSYC 110 lead assignment reporting to them. Their scope is the
    Psychology subtree exactly — PSYC 110 inside it — and nothing of Mathematics
    or Biology. Present twin: Psychology.

    **The mutations this kill:** a walk upward instead of downward (the chair
    picks up the dean's college); a walk by person (the assistant dean's other
    hat reports to this chair as a lead, and a person-level walk would hand the
    chair the assistant dean's supervised departments).
    """
    seeded(seeded_demo)
    with seeded_tree(demo_database, metadata_tables) as tree:
        person = tree.person(PSYCHOLOGY_CHAIR)
        psychology = tree.department(UNSUPERVISED)
        supervised = [tree.department(name) for name in SUPERVISED]
        expected = tree.subtree(psychology)

    with production_session(demo_database) as session:
        held = levels(authz.resolve_scope(session, person_id=person).purview)

    assert (
        psychology in held["department_ids"]
    ), f"The Psychology chair's scope does not hold Psychology: {held['department_ids']}."
    assert not set(supervised) & held["department_ids"], (
        f"The Psychology chair's scope holds {SUPERVISED} departments, which the assistant dean "
        "supervises. The assistant dean's lead hat reports to this chair; a walk by person rather "
        "than by assignment carries the other hat's departments across."
    )
    assert held == expected, (
        f"The Psychology chair's scope differs from the Psychology subtree: "
        f"{difference(held, expected)}."
    )


def test_the_assistant_deans_scope_carries_one_grant_per_leadership_assignment(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any], authz: Any
) -> None:
    """`ActorScope.grants`: one `(assignment id, role, purview)` per leadership assignment.

    The ticket: "`ActorScope` gains `grants`: one `(assignment id, role,
    purview)` per leadership assignment, which gives the tree's roots and the
    by-lead gate in E9-07 without a second walk." The assistant dean holds two —
    the `ASSISTANT_DEAN` assignment, whose purview is the two supervised
    departments, and the `LEAD_FACULTY` assignment on PSYC 110, whose purview is
    the course and its sections — and the scope's purview is their union.

    **The mutations this kill:** one entry per person rather than per
    assignment; entries for non-leadership assignments; a grant carrying the
    person's whole union instead of the assignment's own purview (both entries
    would then be equal).
    """
    seeded(seeded_demo)
    with seeded_tree(demo_database, metadata_tables) as tree:
        person = tree.person(ASSISTANT_DEAN)
        roles = tree.assignments_of(person)
        supervised = union(*(tree.subtree(tree.department(name)) for name in SUPERVISED))
        led = led_course_levels(tree)

    by_role = {role: assignment for assignment, role in roles.items()}
    assert set(by_role) == {
        "ASSISTANT_DEAN",
        "LEAD_FACULTY",
    }, f"The seeded assistant dean holds {roles}; this test is written over the seed's two hats."
    expected = {
        (by_role["ASSISTANT_DEAN"], "ASSISTANT_DEAN"): supervised,
        (by_role["LEAD_FACULTY"], "LEAD_FACULTY"): led,
    }

    with production_session(demo_database) as session:
        scope = authz.resolve_scope(session, person_id=person)
        grants = {
            (str(assignment), role_token(role)): levels(purview)
            for assignment, role, purview in scope.grants
        }
        held = levels(scope.purview)

    assert grants == expected, (
        f"The assistant dean's grants are {sorted(grants)} with purviews differing from the "
        f"expectation by "
        f"{ {k: difference(grants.get(k, union()), v) for k, v in expected.items()} }."
    )
    assert held == union(
        *expected.values()
    ), "The scope's purview is not the union of its grants' purviews."
