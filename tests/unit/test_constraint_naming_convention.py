"""`Base.metadata` carries a naming convention — ticket E0-04.

Acceptance criterion 4: "Constraint names in the generated migration follow the
configured convention rather than Postgres defaults." That criterion has two
halves in two places. This module holds the configuration half — the convention
exists and covers every kind of constraint autogenerate can emit — and
`tests/integration/test_generated_constraint_names.py` holds the half that needs
a server: the names a real Postgres ends up holding.

**Why it is worth asserting the convention at all**, rather than only the names
it produces. Without one, Postgres names an unnamed constraint itself, at
`CREATE TABLE` time, and Alembic never learns the name — so a later migration
that wants to drop or alter that constraint has nothing to name it by, and
`alembic check` cannot see it either. The failure is not at the moment the
convention is missing; it is one schema ticket later, on a migration nobody can
write without hand-copying a server-generated identifier.

**What is deliberately not asserted: the templates.** The five keys have to be
there, because a missing key is a kind of constraint that falls back to the
server. What each one expands to — `pk_%(table_name)s` or anything else — is the
implementer's to choose, and a test quoting SQLAlchemy's documented default
templates would make changing them a test edit rather than a decision.
"""

from typing import Any

# The five keys SQLAlchemy consults, one per constraint kind it can name. This
# is not a style list: `_prefix_dict` in `sqlalchemy/sql/naming.py` maps exactly
# these to `Index`, `PrimaryKeyConstraint`, `CheckConstraint`,
# `UniqueConstraint` and `ForeignKeyConstraint`, and a kind with no entry keeps
# whatever name the server gives it.
CONSTRAINT_KINDS = ("ix", "uq", "ck", "fk", "pk")


def load_base() -> Any:
    """Import the declarative `Base` inside the test, so a missing module fails loudly."""
    from app.db import Base

    return Base


def test_base_metadata_names_every_kind_of_constraint(configured_env: dict[str, str]) -> None:
    """E0-04 puts "a naming convention for constraints and indexes" on `Base.metadata`.

    Asserted as "every kind is covered" rather than "a convention is set",
    because a partial convention is the version that gets written and the one
    that hurts. SQLAlchemy's own default covers `ix` alone, so a `MetaData()`
    built with no argument already answers "yes" to "is there a convention" — and
    then every primary key, foreign key, unique and check constraint in the
    schema is still named by Postgres.

    The failure message lists what is missing rather than what is present, since
    that is the edit to make.
    """
    base = load_base()

    metadata = getattr(base, "metadata", None)
    assert metadata is not None, (
        "`app.db.Base` has no `metadata`, so it is not a declarative base. E0-04 ships one, "
        "and `env.py` autogenerates against its metadata."
    )

    convention = dict(getattr(metadata, "naming_convention", None) or {})
    missing = [kind for kind in CONSTRAINT_KINDS if not convention.get(kind)]

    assert not missing, (
        f"`Base.metadata.naming_convention` has no template for {missing} (it has "
        f"{sorted(convention)}). A constraint kind with no template is named by Postgres at "
        "CREATE TABLE time, so its name is never in a migration and no later migration can "
        "drop or alter it without quoting a server-generated identifier. SQLAlchemy's "
        "built-in default covers `ix` only, which is why 'a convention is set' is not the "
        "question this asks."
    )
