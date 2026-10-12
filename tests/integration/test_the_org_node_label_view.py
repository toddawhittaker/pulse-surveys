"""The org-node label view the roll-up tree reads its names through (E9-07, re-laned heavy).

The roll-up tree has to say "Mathematics" and "College of Arts and Sciences"
(SPEC §2.1's labels), and `pulse_app` holds no `SELECT` on `institution`,
`college` or `department` by design. The orchestrator's ruling on the re-lane
settles the answer as a view, not a grant on those tables:

    `CREATE VIEW public.org_node_label (level, node_id, name, parent_id)`, one row
    per institution, college, department, prefix and course (no section); `level`
    in ('institution', 'college', 'department', 'prefix', 'course'); `name` the
    node's display name (a prefix's is its code); `parent_id` the containing
    node's id, NULL for the institution. No person, identity, email or figure
    column. `GRANT SELECT ON public.org_node_label TO pulse_app`; nothing else.

What a course's `name` holds is left to the builder ("the builder confirms the
column from the models"), so nothing here asserts a course's name beyond its
being a non-empty string.

**The world** is the demo seed (`scripts/seed.py`, run by `tests/fixtures/seed.py`
into a database of its own). Every read of the view and every refusal runs on
`pulse_app`'s own connection, the one production uses (`docs/MISTAKES.md` entry
46). **The expected tree comes from `containment_path`**, ADR 0046's view of
"every org node with the chain of ancestors above it", one row per node, and not
from the seed's own writer (`docs/MISTAKES.md` entry 58): the label view is
checked against the containment the purview is computed over.

**Which failure a red is, before the view lands:** every test here FAILS on an
assertion or a `pytest.fail` naming `org_node_label`; none errors in setup.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

pytestmark = pytest.mark.integration

VIEW = "org_node_label"
VIEW_COLUMNS = frozenset({"level", "node_id", "name", "parent_id"})
LEVELS = ("institution", "college", "department", "prefix", "course")

# ADR 0046's containment view, and its columns in containment order. The view
# carries a sixth level, `section`, which the label view must not.
CONTAINMENT_VIEW = "containment_path"
CONTAINMENT_COLUMNS = tuple(f"{level}_id" for level in LEVELS)
SECTION_COLUMN = "section_id"

# The org tables `pulse_app` holds no `SELECT` on, and must go on holding none.
# `prefix` and `course` are not here: `pulse_app` already holds `SELECT` on both
# (`RUNTIME_BASE_TABLE_PRIVILEGES` in `tests/integration/test_identity_grants.py`),
# and that is older than this ticket.
UNGRANTED_ORG_TABLES = ("institution", "college", "department")

INSUFFICIENT_PRIVILEGE = "42501"
UNDEFINED_TABLE = "42P01"

APPLICATION_ROLE = "pulse_app"
CARE_ROLE = "pulse_care"
WITHHELD_PRIVILEGES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")

# The seed's own spellings (SPEC §2.1's worked example, as
# `tests/integration/test_the_rollup_tree_on_the_seeded_institution.py` reads them).
ARTS_AND_SCIENCES = "College of Arts and Sciences"
BUSINESS_AND_TECHNOLOGY = "College of Business and Technology"
SEEDED_DEPARTMENTS = {"Biology", "Mathematics", "Psychology"}
SEEDED_PREFIXES = {"MATH", "STAT", "MIS", "PSYC"}

VIEW_IS_OWED = (
    "E9-07's re-lane settles `public.org_node_label (level, node_id, name, parent_id)`, one row "
    "per institution, college, department, prefix and course, granted `SELECT` to `pulse_app` "
    "and nothing else, in `backend/app/views_sql/org_node_label_v001.sql` under migration "
    "`e9f6c8e0a706`."
)


def seeded(run: Any) -> None:
    if not run.succeeded:
        pytest.fail(
            "The seed run this module is built on did not succeed; `test_demo_seed_script.py` "
            "owns that failure.\n" + run.report()
        )


@contextmanager
def application_connection(demo: Any) -> Iterator[Any]:
    """A connection as `pulse_app`, the role every read path in production uses."""
    from sqlalchemy import create_engine

    engine = create_engine(demo.database.application_url)
    try:
        with engine.connect() as connection:
            yield connection
    finally:
        engine.dispose()


def sqlstate(failure: Any) -> str | None:
    return getattr(getattr(failure, "orig", None), "sqlstate", None)


def label_rows(demo: Any) -> list[dict[str, Any]]:
    """Every row of the view, read as `pulse_app`; a FAILED naming the view if it is absent."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    with application_connection(demo) as connection:
        try:
            rows = connection.execute(
                text(f"SELECT level, node_id, name, parent_id FROM public.{VIEW}")  # noqa: S608
            ).mappings()
            return [dict(row) for row in rows]
        except DBAPIError as failure:
            pytest.fail(
                f"`pulse_app` could not read `public.{VIEW}` (SQLSTATE {sqlstate(failure)}): "
                f"{str(failure).splitlines()[0]}\n\n{VIEW_IS_OWED}"
            )


def expected_nodes(demo: Any) -> tuple[dict[tuple[str, str], str | None], set[str]]:
    """Every non-section node in `containment_path`, as `(level, id) -> parent id`; and the sections.

    A row's level is its deepest non-null column (ADR 0046: "one row per node at
    every level, with the levels at and below it NULL"); its parent is the
    column one level up.
    """
    from sqlalchemy import text

    columns = ", ".join((*CONTAINMENT_COLUMNS, SECTION_COLUMN))
    with application_connection(demo) as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                text(f"SELECT {columns} FROM public.{CONTAINMENT_VIEW}")  # noqa: S608
            ).mappings()
        ]
    nodes: dict[tuple[str, str], str | None] = {}
    sections: set[str] = set()
    for row in rows:
        if row[SECTION_COLUMN] is not None:
            sections.add(str(row[SECTION_COLUMN]))
            continue
        filled = [index for index, column in enumerate(CONTAINMENT_COLUMNS) if row[column]]
        assert filled, f"A `{CONTAINMENT_VIEW}` row names no node at all: {row}."
        deepest = max(filled)
        parent = row[CONTAINMENT_COLUMNS[deepest - 1]] if deepest > 0 else None
        nodes[(LEVELS[deepest], str(row[CONTAINMENT_COLUMNS[deepest]]))] = (
            None if parent is None else str(parent)
        )
    return nodes, sections


def test_the_view_carries_exactly_level_node_id_name_and_parent_id(
    seeded_demo: Any, demo_database: Any
) -> None:
    """The column set is the settled four, and the relation is a view.

    **The mutation it kills:** a person, identity, email or figure column added
    to the view (a chair's name beside the department, a section count beside
    the prefix); the relation built as a table that a writer could fill.
    **The near miss it spares:** the four columns in another order.
    """
    from sqlalchemy import text

    seeded(seeded_demo)
    with demo_database.connect() as connection:
        kind = connection.execute(
            text(
                "SELECT c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = :name"
            ),
            {"name": VIEW},
        ).scalar_one_or_none()
        columns = set(
            connection.execute(
                text(
                    "SELECT a.attname FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relname = :name "
                    "AND a.attnum > 0 AND NOT a.attisdropped"
                ),
                {"name": VIEW},
            ).scalars()
        )
    assert kind == "v", f"`public.{VIEW}` has relkind {kind!r}, not a view ('v').\n\n{VIEW_IS_OWED}"
    assert columns == VIEW_COLUMNS, (
        f"`public.{VIEW}` carries columns {sorted(columns)}; the settled interface is exactly "
        f"{sorted(VIEW_COLUMNS)}. No person, identity, email or figure column."
    )


def test_the_view_holds_one_row_per_node_at_five_levels_under_its_containing_node(
    seeded_demo: Any, demo_database: Any
) -> None:
    """Every institution, college, department, prefix and course, once, with its parent; no section.

    **The control:** the containment read is non-empty at every one of the five
    levels, so the equality below is not between two empty maps.

    **The mutations it kills:** a level missing (a prefix with no courses dropped
    by an inner join); a section row added; a node listed twice; a prefix
    parented to its college instead of its department; the institution given a
    parent. **The near miss it spares:** rows in any order.
    """
    seeded(seeded_demo)
    expected, sections = expected_nodes(demo_database)
    levels_present = {level for level, _node in expected}
    assert levels_present == set(LEVELS) and sections, (
        f"`{CONTAINMENT_VIEW}` read as `pulse_app` holds nodes at {sorted(levels_present)} and "
        f"{len(sections)} sections; the seeded institution has all five levels and sections. A "
        "broken world, not a red."
    )

    rows = label_rows(demo_database)
    keyed = [(str(row["level"]), str(row["node_id"])) for row in rows]
    repeated = sorted({key for key in keyed if keyed.count(key) > 1})
    assert not repeated, f"`{VIEW}` lists these nodes more than once: {repeated}."

    as_parented = {
        (str(row["level"]), str(row["node_id"])): (
            None if row["parent_id"] is None else str(row["parent_id"])
        )
        for row in rows
    }
    surplus = sorted(set(as_parented) - set(expected))
    missing = sorted(set(expected) - set(as_parented))
    misparented = sorted(
        (key, as_parented[key], expected[key])
        for key in set(as_parented) & set(expected)
        if as_parented[key] != expected[key]
    )
    section_rows = sorted(node for _level, node in as_parented if node in sections)
    assert not (surplus or missing or misparented or section_rows), (
        f"`{VIEW}` disagrees with `{CONTAINMENT_VIEW}`. Listed and not a node: {surplus}. A node "
        f"not listed: {missing}. Wrong parent (node, view's parent, containment's parent): "
        f"{misparented}. Section ids listed: {section_rows}."
    )


def test_the_view_names_each_node_and_a_prefix_by_its_code(
    seeded_demo: Any, demo_database: Any
) -> None:
    """The seed's colleges, departments and prefixes by their own spellings, under the right parents.

    Mathematics sits under the College of Arts and Sciences, MATH under
    Mathematics, PSYC under Psychology. Every row's name is a non-empty string;
    what a course's name holds is the builder's (the interface leaves it open).

    **The mutations it kills:** the department's or college's id served as its
    name; a prefix named by its department; a name column left NULL for a level
    the view joins to the wrong table. **The near miss it spares:** any course
    label at all.
    """
    seeded(seeded_demo)
    rows = label_rows(demo_database)
    assert rows, f"`{VIEW}` returned no rows over the seeded institution.\n\n{VIEW_IS_OWED}"

    unnamed = sorted(
        (str(row["level"]), str(row["node_id"]))
        for row in rows
        if not isinstance(row["name"], str) or not row["name"].strip()
    )
    assert not unnamed, f"These `{VIEW}` rows carry no name: {unnamed}."

    def named(level: str) -> dict[str, dict[str, Any]]:
        return {row["name"]: row for row in rows if row["level"] == level}

    colleges, departments, prefixes = named("college"), named("department"), named("prefix")
    assert {ARTS_AND_SCIENCES, BUSINESS_AND_TECHNOLOGY} <= set(
        colleges
    ), f"The college names are {sorted(colleges)}."
    assert (
        set(departments) >= SEEDED_DEPARTMENTS
    ), f"The department names are {sorted(departments)}."
    assert (
        set(prefixes) >= SEEDED_PREFIXES
    ), f"The prefix names are {sorted(prefixes)}; a prefix is named by its code."

    parentage = {
        ("Mathematics", "College of Arts and Sciences"): (
            departments["Mathematics"]["parent_id"],
            colleges[ARTS_AND_SCIENCES]["node_id"],
        ),
        ("MATH", "Mathematics"): (
            prefixes["MATH"]["parent_id"],
            departments["Mathematics"]["node_id"],
        ),
        ("PSYC", "Psychology"): (
            prefixes["PSYC"]["parent_id"],
            departments["Psychology"]["node_id"],
        ),
    }
    wrong = sorted(
        f"{child} under {parent}"
        for (child, parent), (held, expected) in parentage.items()
        if str(held) != str(expected)
    )
    assert not wrong, f"`{VIEW}` does not place: {wrong}."


@pytest.mark.parametrize("table", UNGRANTED_ORG_TABLES)
def test_pulse_app_reads_the_view_and_is_still_refused_the_org_table_beneath_it(
    seeded_demo: Any, demo_database: Any, table: str
) -> None:
    """The view is the door; the table stays shut.

    **The control:** the same role reads the view's row for that level, so the
    refusal below is the table's grant and not a connection that reads nothing.

    **The mutation it kills:** the names supplied by a grant on the org table
    (`GRANT SELECT ON public.department TO pulse_app`, table-wide or by column)
    instead of, or beside, the view. **The near miss it spares:** the view's own
    `SELECT` grant.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    seeded(seeded_demo)
    through_the_view = [row for row in label_rows(demo_database) if row["level"] == table]
    assert through_the_view, (
        f"`pulse_app` read no `{table}` row through `{VIEW}`, so the refusal below would not "
        "show that the view is the only door."
    )

    failure: Any = None
    with application_connection(demo_database) as connection:
        try:
            connection.execute(text(f"SELECT * FROM public.{table} LIMIT 1"))  # noqa: S608
        except DBAPIError as raised:
            failure = raised
    assert failure is not None and sqlstate(failure) == INSUFFICIENT_PRIVILEGE, (
        f"`pulse_app` reading `public.{table}` directly was "
        f"{'answered' if failure is None else f'refused with SQLSTATE {sqlstate(failure)}'}; it "
        f"must be refused with {INSUFFICIENT_PRIVILEGE}. The re-lane's ruling keeps the rule that "
        "`pulse_app` is granted nothing on any org table, and puts the names in a view instead."
    )


def test_pulse_app_holds_select_on_the_view_and_no_other_privilege_and_care_holds_none(
    seeded_demo: Any, demo_database: Any
) -> None:
    """`GRANT SELECT ON public.org_node_label TO pulse_app`, and nothing else granted.

    A simple view over one table is auto-updatable in Postgres, so a write
    privilege on it would be a write path onto the org tables.

    **The mutations it kills:** `GRANT ALL`, or `INSERT`/`UPDATE`/`DELETE`, on
    the view to `pulse_app`; a grant to `pulse_care` or to `PUBLIC`.
    **The near miss it spares:** the one `SELECT` grant.
    """
    from sqlalchemy import text

    seeded(seeded_demo)
    relation = f"public.{VIEW}"
    with demo_database.connect() as connection:
        present = connection.execute(
            text("SELECT to_regclass(:relation)"), {"relation": relation}
        ).scalar_one()
        if present is None:
            pytest.fail(f"`{relation}` does not exist.\n\n{VIEW_IS_OWED}")

        def holds(role: str, privilege: str) -> bool:
            return bool(
                connection.execute(
                    text("SELECT has_table_privilege(:role, :relation, :privilege)"),
                    {"role": role, "relation": relation, "privilege": privilege},
                ).scalar_one()
            )

        application_select = holds(APPLICATION_ROLE, "SELECT")
        application_extra = [p for p in WITHHELD_PRIVILEGES if holds(APPLICATION_ROLE, p)]
        care_select = holds(CARE_ROLE, "SELECT")

    assert application_select, f"`{APPLICATION_ROLE}` holds no `SELECT` on `{relation}`."
    assert not application_extra, (
        f"`{APPLICATION_ROLE}` holds {application_extra} on `{relation}`; the interface grants "
        "`SELECT` and nothing else."
    )
    assert not care_select, (
        f"`{CARE_ROLE}` holds `SELECT` on `{relation}`; the interface grants it to "
        f"`{APPLICATION_ROLE}` only."
    )
