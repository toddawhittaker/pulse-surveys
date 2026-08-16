"""Every identity column announces itself — ticket E0-08, criterion 6.

"Every identity-bearing column is discoverable through the marker convention; a
test enumerates them and fails if a new one is added without the marker."

This is the tripwire [E0-10](../../docs/tickets/e0/E0-10-identity-separated-views.md)
and every later §4.1 confidentiality test depend on, so it has a module of its
own: when it goes red, the failure should name itself without anyone opening the
file. The rest of E0-08 is in `tests/integration/test_identity_schema.py`.

**The marker is discovered, not named.** E0-08's scope leaves the mechanism open
— "column-level comments or a marker convention" — so pinning one here would make
the implementer build to this file rather than to the ticket, which is the
failure `week_producer` in `test_term_calendar_schema.py` was written to avoid.
`database_marked_columns` below therefore accepts any of three shapes, and the
constants it reads are at the top of this file so a fourth is a small edit:

  - a Postgres **column comment** carrying the marker token — the mechanism the
    ticket names first;
  - a **name prefix** on the column, which is the shape
    [ADR 0014](../../docs/adr/0014-lms-owned-columns-are-marked-by-a-name-prefix.md)
    chose for the LMS-owned marker, over a comment, and for reasons that apply
    again here;
  - a **table comment** carrying the token, which marks that table's columns.
    [ADR 0001](../../docs/adr/0001-identity-separation-by-database-role.md) makes
    the protection a table-level grant, so a table-grained marker is a coherent
    reading of the criterion and this file does not refuse it.

**What is asserted is what Postgres reports, and that is a decision.** A marker
that lives only in `Column.info` — a dict the ORM carries and the database never
sees — is invisible here and these tests go red against it. The reason is that
the marker's stated job is for "E0-10's views and the CI invariant" to find the
columns programmatically: a view is a database object, and CI's invariant pass
asserts against a database. A marker that has to be resolved by importing Python
is one indirection away from every consumer that matters, and — the sharper
half — it can be *declared and never applied*, which is what
`test_a_marker_declared_in_the_model_reaches_the_database` exists to catch. If
the implementer disputes this reading, it is one function that changes, and the
pull request owes the argument for why the database need not carry it.

**What this cannot catch, stated rather than implied.** An identity column whose
name contains neither "name" nor "email" — `sortable`, `sis_login`, a `phone` —
is not in the sweep, and no test that reads a database can distinguish it from an
ordinary string column. The sweep is over the tables that hold a person: `user`,
`user_identity`, `person`, and anything with a foreign key to one of them, which
is what makes it reach E0-09's `role_assignment` and E1's roster tables without
being edited. That is the boundary of the search, and it is not the same claim as
"no unmarked identity column can exist" (`docs/MISTAKES.md` entry 14).
"""

from importlib import import_module
from typing import Any

import pytest
from sqlalchemy import Table, inspect

pytestmark = pytest.mark.integration

# The token a comment carries to mark a column, matched case-insensitively as a
# substring. **This file's choice** of spelling, and the obvious one: the ticket,
# SPEC §8 and ADR 0001 all call these "identity columns".
MARKER_TOKEN = "identity"  # noqa: S105 — the marker convention's token, not a credential

# The name-prefix form of the same marker, following ADR 0014's precedent for
# LMS-owned columns. Two spellings because the ticket names neither.
MARKER_PREFIXES = ("identity_", "pii_")

# Name and email spellings, as fragments of a column name. A copy of the tuple in
# `test_identity_schema.py`, deliberately: a test module importing a sibling test
# module works only because of where pytest puts `tests/` on `sys.path`, and a
# collection error is not a failing test. Change one, look at the other.
IDENTITY_NAME_FRAGMENTS = ("name", "email")

# The tables that hold a person by construction. Anything with a foreign key to
# one of them is swept too — see `people_tables`.
PERSON_TABLES = ("user", "user_identity", "person")

# Tables that hold no person at all (SPEC §2.1: the institution/college/
# department/prefix hierarchy is Pulse's own org structure, built in the admin
# console). Used by the anti-blanket test below. `course` and `section` are
# deliberately absent: E0-05's marker module left the teaching-instructor link to
# this ticket, and a link on `section` would make it a people table.
TABLES_HOLDING_NO_PERSON = ("institution", "college", "department", "prefix")


def marked(
    table_name: str,
    column_name: str,
    comment: str | None,
    table_comment: str | None,
) -> bool:
    """Is this column marked as identity-bearing, by any of the three shapes?

    The table-comment shape does not apply to `user`, and that exclusion is
    principled rather than convenient: ADR 0001 puts the key and the platform
    reference on `user` and identity on `user_identity`, so a claim that `user`'s
    columns are identity columns contradicts the split this ticket exists to
    make. Without the exclusion, a `user` table whose comment merely *mentions*
    identity would mark its own columns, and the sweep below would then wave
    through the exact column criterion 3 forbids.
    """
    if any(column_name.lower().startswith(prefix) for prefix in MARKER_PREFIXES):
        return True
    if comment and MARKER_TOKEN in comment.lower():
        return True
    return (
        table_name != "user" and table_comment is not None and MARKER_TOKEN in table_comment.lower()
    )


def database_marked_columns(engine: Any) -> set[tuple[str, str]]:
    """Every `(table, column)` the *database* reports as marked."""
    inspector = inspect(engine)
    found: set[tuple[str, str]] = set()
    for table_name in inspector.get_table_names():
        table_comment = (inspector.get_table_comment(table_name) or {}).get("text")
        for column in inspector.get_columns(table_name):
            if marked(table_name, column["name"], column.get("comment"), table_comment):
                found.add((table_name, column["name"]))
    return found


def declared_marked_columns(tables: dict[str, Table]) -> set[tuple[str, str]]:
    """Every `(table, column)` the *model* declares as marked.

    Reads `Column.info` as well as the three shapes the database can carry, so
    that an `info={"identity": True}` marker counts as declared — which is what
    makes the comparison below able to report it as declared and not applied,
    rather than silently not seeing it at all.
    """
    found: set[tuple[str, str]] = set()
    for name, table in tables.items():
        for column in table.columns:
            info = " ".join(f"{key} {value}" for key, value in (column.info or {}).items())
            if marked(name, column.name, column.comment, table.comment) or (
                MARKER_TOKEN in info.lower()
            ):
                found.add((name, column.name))
    return found


def people_tables(engine: Any) -> set[str]:
    """Tables that hold a person: the three named ones, and anything linking to them."""
    inspector = inspect(engine)
    present = set(inspector.get_table_names())
    found = {name for name in PERSON_TABLES if name in present}
    for table_name in present:
        for key in inspector.get_foreign_keys(table_name):
            if key.get("referred_table") in PERSON_TABLES:
                found.add(table_name)
    return found


def identity_bearing_columns(engine: Any) -> set[tuple[str, str]]:
    """Every column on a people table whose name reads as a name or an email address."""
    inspector = inspect(engine)
    found: set[tuple[str, str]] = set()
    for table_name in sorted(people_tables(engine)):
        for column in inspector.get_columns(table_name):
            if any(f in column["name"].lower() for f in IDENTITY_NAME_FRAGMENTS):
                found.add((table_name, column["name"]))
    return found


@pytest.fixture(scope="session")
def declared_tables(migrated_database: Any) -> dict[str, Table]:
    """`Base.metadata`, with every model module registered on it.

    Reached through `app.models` and not through `app.models.identity`, because
    `migrations/env.py` imports the package and a module nobody imported is on no
    metadata — and because E0-08 leaves the LTI tables free to live in either of
    two modules. `Base` comes from `app.models.base` rather than from `app.db`,
    which builds an engine out of `Settings()` at import.
    """
    try:
        import_module("app.models")
        base_module = import_module("app.models.base")
    except ImportError as failure:
        pytest.fail(
            f"Importing the model package raised {failure!r}. E0-04 ships `app/models/base.py` "
            "with the declarative base, and every model module imports `Base` from it."
        )
    metadata = getattr(getattr(base_module, "Base", None), "metadata", None)
    if metadata is None:
        pytest.fail(
            "`app.models.base` exposes no `Base` with `metadata`, so there is nothing to read a "
            "declared marker off."
        )
    return dict(metadata.tables)


def test_every_identity_bearing_column_is_discoverable_through_the_marker(
    migrated_engine: Any,
) -> None:
    """Criterion 6: the enumeration finds every one of them, and names the ones it does not.

    **This is the tripwire.** The failure it is built for is a later ticket
    adding an identity column and not marking it — E1's roster sync landing a
    display name, E10 landing a contact address — after which E0-10's views and
    the CI invariant pass are both computing over a set that is quietly one
    column short, and nothing says so. The message below names the column.

    **Two non-vacuity guards run first, and neither is ceremony.** The sweep is
    over columns that exist, so an empty sweep — the three person tables missing,
    or the reflection returning nothing — satisfies "none of them is unmarked"
    perfectly (`docs/MISTAKES.md` entry 3). And the marked set is required to be
    non-empty, because "every identity column is marked" is also satisfied by a
    schema with no identity columns and no marker at all, which is the state this
    criterion exists to leave behind.
    """
    inspector = inspect(migrated_engine)
    present = sorted(inspector.get_table_names())
    absent = [name for name in PERSON_TABLES if name not in present]
    assert not absent, (
        f"The migrated database has no {absent} table, so there is nothing for this sweep to "
        f"walk and it would report success having looked at nothing. It holds {present}."
    )

    bearing = identity_bearing_columns(migrated_engine)
    assert bearing, (
        "No column on any table holding a person is named like a name or an email address, so "
        "this test would pass against a schema that stores no identity at all. E0-08 puts name "
        "and email on `user_identity` and a name on `person`; the sweep looks for the fragments "
        f"{list(IDENTITY_NAME_FRAGMENTS)} on {sorted(people_tables(migrated_engine))}."
    )

    marked_columns = database_marked_columns(migrated_engine)
    assert marked_columns, (
        "Nothing in the migrated database carries the identity marker in any shape this file "
        f"reads — no column comment containing {MARKER_TOKEN!r}, no table comment containing it, "
        f"no column name starting with one of {list(MARKER_PREFIXES)}. E0-08 asks for "
        "'column-level comments or a marker convention identifying every identity column, so "
        "E0-10's views and the CI invariant can both find them programmatically rather than by a "
        "hand-maintained list'. A marker that lives only in `Column.info` is not visible to "
        "either of those readers — see this module's docstring."
    )

    unmarked = sorted(f"{table}.{column}" for table, column in bearing - marked_columns)
    assert not unmarked, (
        f"{unmarked} hold a person's name or email address and carry no identity marker. E0-10 "
        "builds its views and its grants from this enumeration, and the CI invariant suite "
        "asserts against it, so a column missing from it is a column those two believe is safe "
        "to expose. Mark it — a column comment containing "
        f"{MARKER_TOKEN!r}, a comment on the whole table, or an "
        f"`{MARKER_PREFIXES[0]}` name prefix all count here. Marking says what the column holds; "
        "it does not decide who may read it, which is E0-10's decision and a separate one. If a "
        "column in this list is genuinely not a person's identity — a `person` category label "
        "that happens to be spelled `name`, say — take it out of the sweep in this file with the "
        "reason in the pull request, rather than leaving the marker convention with a hole in it."
    )


def test_a_marker_declared_in_the_model_reaches_the_database(
    migrated_engine: Any, declared_tables: dict[str, Table]
) -> None:
    """The two sides of the marker agree — the model's set is the database's set.

    Two failures, one assertion, and they are different defects:

      - **Declared and not applied.** A marker written into the model — a
        `comment=`, an `info={"identity": True}` — that no migration carried into
        Postgres. Everything that reads the model sees a complete convention and
        everything that reads the database sees a partial one, and E0-10 reads
        the database.
      - **Applied and not declared.** A comment written by hand in a migration
        with no counterpart in the model. ADR 0014 rejected column comments for
        the LMS marker on exactly this ground: `alembic check` does not compare
        comments by default, so the two drift and nothing reports it.

    Both sides are required to be non-empty first, because an empty set equals an
    empty set and that would be this test's most likely way of passing while the
    convention does not exist (`docs/MISTAKES.md` entry 3).
    """
    declared = declared_marked_columns(declared_tables)
    in_database = database_marked_columns(migrated_engine)

    assert declared, (
        "No column on `Base.metadata` carries an identity marker in any shape this file reads. "
        "E0-08 asks for the marker; `test_every_identity_bearing_column_is_discoverable_through_"
        "the_marker` is where its absence is diagnosed, and this test cannot compare two sides "
        "when one of them is empty."
    )
    assert in_database, (
        "No column in the migrated database carries an identity marker, so either no migration "
        "was written for the marker or it did not survive one. An empty set on this side would "
        "make the comparison below vacuous."
    )

    declared_only = sorted(f"{table}.{column}" for table, column in declared - in_database)
    database_only = sorted(f"{table}.{column}" for table, column in in_database - declared)
    assert not declared_only and not database_only, (
        "The marker disagrees between the model and the database. Declared and not present in "
        f"Postgres: {declared_only}. Present in Postgres and not declared: {database_only}. The "
        "first is the one that costs something: E0-10 builds views and grants against the "
        "database, and CI's invariant pass asserts against a database, so a marker that only the "
        "ORM carries is invisible to both. The second is the drift ADR 0014 rejected column "
        "comments over — `alembic check` does not compare comments by default, so a comment "
        "written by hand into a migration has nothing keeping it in step with the model."
    )


def test_the_marker_does_not_reach_columns_that_hold_no_identity(
    migrated_engine: Any,
) -> None:
    """The other direction: a marked column is one somebody meant to mark.

    Without this, the cheapest way to make the sweep above pass forever is to
    mark everything — after which the enumeration E0-10 builds its views from
    covers the whole schema, the tripwire can never fire again, and both facts
    are invisible in a green suite. That is `docs/MISTAKES.md` entry 2 in the
    shape a marker convention takes: the guard is still there and no longer
    discriminates.

    Two places are checked. **`user`**, because ADR 0001 puts the key and the
    platform reference there precisely so that they are *not* identity — a
    marked column on `user` either contradicts that split or is decoration, and
    both make the marker unreadable as one. **The four containment tables**,
    because SPEC §2.1 builds the institution/college/department/prefix hierarchy
    in the admin console and no person appears in it; `institution.name` is the
    name of an institution.
    """
    marked_columns = database_marked_columns(migrated_engine)
    assert marked_columns, (
        "Nothing is marked at all, so this test would pass against a schema with no marker "
        "convention — which is the state criterion 6 exists to leave behind. The sweep test in "
        "this module is where that is diagnosed."
    )

    misplaced = sorted(
        f"{table}.{column}"
        for table, column in marked_columns
        if table == "user" or table in TABLES_HOLDING_NO_PERSON
    )
    assert not misplaced, (
        f"{misplaced} carry the identity marker on tables that hold no person's identity. `user` "
        "holds the LMS key and the platform reference and nothing else (E0-08, ADR 0001) — that "
        "split is what lets `pulse_app` read `user` freely while holding no grant on "
        "`user_identity`, so marking a `user` column as identity either says the split failed or "
        "says nothing. The institution, college, department and prefix hierarchy is Pulse's own "
        "org structure (SPEC §2.1); a college has a name and is not a person. A marker that "
        "appears where it does not apply stops being readable as one, and an enumeration that "
        "grows to cover the schema stops being a tripwire."
    )
