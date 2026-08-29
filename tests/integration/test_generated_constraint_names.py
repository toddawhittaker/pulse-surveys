"""The names Postgres ends up holding are the convention's — ticket E0-04.

Acceptance criterion 4: "Constraint names in the generated migration follow the
configured convention rather than Postgres defaults."
`tests/unit/test_constraint_naming_convention.py` holds the half that can be
checked without a server — that a template exists for every kind of constraint.
This is the half that cannot: what a real Postgres records when a table declared
under that convention is created.

**Why the check is against the server and not against the migration text.** The
criterion says "in the generated migration", and the migration is a means to an
end: a name in a migration file that Postgres does not end up holding is worth
nothing, and a name Postgres holds is what a later `DROP CONSTRAINT` has to
match. Reading `pg_constraint` asks the question the criterion is really about,
and it cannot be satisfied by a name that renders into a file and never lands.

**Why the canary tables are not attached to `Base.metadata`.** `Base` is one
object shared by everything in this process, and a table left on it is drift for
every `alembic check` that runs afterwards — `tests/integration/
test_alembic_baseline.py` would fail with this module's name in the message. So
the tables are declared on a separate `MetaData` built with `Base.metadata`'s
own convention, which is the thing under test; nothing here asserts anything
about the convention's contents, only that it is the one in force.

The tables are created inside `db_session`'s transaction and go away with it,
which also means this module leans on the isolation `test_db_session.py`
asserts. That is the right direction of dependency: if the rollback does not
work, that module says so in its own words rather than this one failing
mysteriously two tests later.
"""

from typing import Any

import pytest
from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    text,
)

pytestmark = pytest.mark.integration

# Short on purpose. A convention's foreign-key template concatenates two table
# names and a column name, and Postgres truncates an identifier at 63 bytes
# without complaining — so a canary table named at leisure would make this test
# fail on the truncation rather than on anything E0-04 decides.
PARENT_TABLE = "e0_04_naming_parent"
CHILD_TABLE = "e0_04_naming_child"

# The names Postgres invents when nothing else does — `<table>_pkey`,
# `<table>_<column>_fkey`, `<table>_<column>_key`, `<table>_check`. Written out
# rather than derived, because the point is to compare against what a reader
# would actually see in `\d` on a database built without a convention.
#
# The check constraint is the one kind this set cannot speak for: it carries an
# explicit name whether or not a `ck` template exists, so it never falls through
# to the server default. Whether the `ck` key is present is asserted directly,
# in tests/unit/test_constraint_naming_convention.py.
POSTGRES_DEFAULT_NAMES = {
    f"{PARENT_TABLE}_pkey",
    f"{CHILD_TABLE}_pkey",
    f"{CHILD_TABLE}_parent_id_fkey",
    f"{CHILD_TABLE}_code_key",
    f"{CHILD_TABLE}_check",
}

CONSTRAINT_NAMES = (
    "SELECT conname FROM pg_constraint"
    " WHERE conrelid = to_regclass(:table) AND contype IN ('p', 'f', 'u', 'c')"
)
INDEX_NAMES = "SELECT indexname FROM pg_indexes WHERE tablename = :table"


def load_base() -> Any:
    """Import the declarative `Base` inside the test, so a missing module fails loudly."""
    from app.db import Base

    return Base


def canary_tables(convention: Any) -> tuple[Any, Any, Any]:
    """Two tables carrying one of every constraint kind, under `convention`.

    The check constraint is given a name of its own because the conventional
    `ck` template interpolates `%(constraint_name)s`, and SQLAlchemy refuses an
    anonymous constraint under such a template — deliberately, since there would
    be nothing to build a name out of. Naming it is how the documented
    convention is meant to be used, not a way around this test.

    `code` is unique and `label` is indexed, on separate columns on purpose: a
    column that is both produces a single unique index rather than a unique
    constraint plus an index, and the two kinds would stop being distinguishable.
    """
    metadata = MetaData(naming_convention=dict(convention))
    parent = Table(
        PARENT_TABLE,
        metadata,
        Column("id", Integer, primary_key=True),
    )
    child = Table(
        CHILD_TABLE,
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey(f"{PARENT_TABLE}.id")),
        Column("code", String(16), unique=True),
        Column("label", String(16), index=True),
        CheckConstraint("length(code) > 0", name="code_is_not_empty"),
    )
    return metadata, parent, child


def declared_names(*tables: Any) -> set[str]:
    """Every constraint and index name SQLAlchemy resolved for `tables`.

    Only genuine strings are collected. Without a convention SQLAlchemy leaves a
    constraint's name as an internal sentinel rather than as `None`, and letting
    one of those into the comparison would produce a mismatch whose message is
    about an object rather than about a missing convention.
    """
    found: set[str] = set()
    for table in tables:
        for constraint in table.constraints:
            if isinstance(constraint.name, str):
                found.add(str(constraint.name))
        for index in table.indexes:
            if isinstance(index.name, str):
                found.add(str(index.name))
    return found


def recorded_names(session: Any, *tables: str) -> set[str]:
    """Every constraint and index name Postgres holds for `tables`."""
    found: set[str] = set()
    for table in tables:
        found |= set(session.execute(text(CONSTRAINT_NAMES), {"table": table}).scalars())
        found |= set(session.execute(text(INDEX_NAMES), {"table": table}).scalars())
    return found


def test_generated_constraint_names_follow_the_convention_and_not_postgres(
    configured_env: dict[str, str],
    db_session: Any,
) -> None:
    """Criterion 4, against the server.

    Three assertions, and the first two are what stop the third passing for the
    wrong reason. A set comparison is satisfied by two empty sets — the exact
    shape `docs/MISTAKES.md` entry 3 records — so the names SQLAlchemy resolved
    are required to be non-empty before they are compared, and the names
    Postgres recorded are required to be non-empty before they are trusted to
    disagree with the defaults.

    The disjointness assertion is the criterion's own words: *rather than
    Postgres defaults*. It is separate from the equality assertion because the
    two fail for different reasons and want different messages. Equality fails
    when the ORM and the server disagree about a name; disjointness fails when
    they agree on a name the server chose, which is what happens when a
    convention key is missing and the constraint falls through to `<table>_pkey`.
    """
    base = load_base()
    convention = getattr(getattr(base, "metadata", None), "naming_convention", None)
    assert convention, (
        "`Base.metadata` carries no naming convention, so there is nothing for the generated "
        "names to follow and Postgres names every constraint itself. "
        "tests/unit/test_constraint_naming_convention.py says what is missing."
    )

    metadata, parent, child = canary_tables(convention)
    expected = declared_names(parent, child)
    assert len(expected) >= len(POSTGRES_DEFAULT_NAMES), (
        f"SQLAlchemy resolved only {sorted(expected)} for the canary tables, which is fewer "
        f"names than there are constraints on them ({len(POSTGRES_DEFAULT_NAMES)} at least). "
        "A constraint kind the convention does not cover keeps an unnamed sentinel here and "
        "is left to the server, so comparing what was collected would compare a short list "
        "against a short list and pass."
    )

    metadata.create_all(bind=db_session.connection())
    actual = recorded_names(db_session, PARENT_TABLE, CHILD_TABLE)

    assert actual, (
        f"Postgres holds no constraints or indexes for {PARENT_TABLE} and {CHILD_TABLE} after "
        "creating them, so either the DDL did not run or it ran somewhere else. Nothing "
        "below can mean anything until this does."
    )

    assert actual == expected, (
        f"The names Postgres recorded are {sorted(actual)}; the names the ORM resolved from "
        f"`Base.metadata.naming_convention` are {sorted(expected)}. A name only the ORM knows "
        "is a name no migration can drop or alter, and a name only the server knows is one "
        "autogenerate will keep proposing to create."
    )

    assert not (actual & POSTGRES_DEFAULT_NAMES), (
        f"These constraints kept the names Postgres invents for them: "
        f"{sorted(actual & POSTGRES_DEFAULT_NAMES)}. That is criterion 4's failure exactly — "
        "the convention did not reach this kind of constraint, so the name lives in the "
        "server and not in the migration, and it will change spelling the next time the "
        "table is recreated under a different column order."
    )
