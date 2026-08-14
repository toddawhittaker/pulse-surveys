"""The test database has production's role shape — ticket E0-04.

Not one of E0-04's five acceptance criteria, and it is here because of what the
ticket says in the paragraph before them:

> The testcontainers fixture has the same gap and needs the same answer, or its
> tests pass under privileges production does not have.

[ADR 0009](../../docs/adr/0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)'s
provisioning table gives this fixture its own row, and E0-04 owns it.
`scripts/db-init` runs only where the Compose `initdb` hook exists, so a
container started by testcontainers has exactly one role — the cluster superuser
`initdb` made — unless something else provisions the second. A suite that runs
as that superuser bypasses every grant and every row-level security policy, so
from E0-08 onward the §4.1 confidentiality assertions would be made against a
connection nothing could stop. They would pass. They would mean nothing.

So this module asserts the shape rather than any behaviour built on it: two
roles, and the one the application uses cannot create a table.
`docs/adr/0001-identity-separation-by-database-role.md` line 71 is the rule —
"Runtime roles must not own tables and must not be superuser" — and ADR 0009
leaves that half standing while sanctioning the superuser for migrations.

**Not marked `invariant`, deliberately.** E0-04 says the invariant checker keeps
`--allow-empty` "until E0-10 adds the first §4.1 invariant", so marking anything
here would make that sentence false and would change what the CI gate reports.
These are preconditions for the §4.1 invariants rather than instances of them:
§4.1 is about what a reader can see, and this is about what a role can do.
"""

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

pytestmark = pytest.mark.integration

# `application_engine` and `migrated_engine` come from `tests/conftest.py`.

ROLE_ATTRIBUTES = (
    "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole"
    " FROM pg_roles WHERE rolname = current_user"
)
CURRENT_ROLE = "SELECT current_user"

# Creating a table is the privilege the whole scheme turns on: a role that owns
# a table can grant on it, and the grants are the enforcement (ADR 0001).
CREATE_FORBIDDEN_TABLE = "CREATE TABLE e0_04_privilege_canary (note text NOT NULL)"
DROP_FORBIDDEN_TABLE = "DROP TABLE IF EXISTS e0_04_privilege_canary"


def test_the_application_role_is_not_a_superuser(application_engine: Any) -> None:
    """The role `DATABASE_URL` points at holds none of the bypass attributes.

    All four are asserted together because they are one property with four
    spellings: each of them, on its own, is a way for a runtime connection to
    get out from under the grants the §4.1 separation is made of. `rolsuper` is
    the obvious one; `rolbypassrls` alone would defeat every row-level security
    policy E0-10 writes while leaving `rolsuper` false and the role looking
    correct in `\\du`.

    The row is asserted to exist first. `SELECT rolsuper ... WHERE rolname =
    current_user` returning nothing would make every "not a superuser" assertion
    below true of no row at all — `docs/MISTAKES.md` entry 3.
    """
    with application_engine.connect() as connection:
        row = connection.execute(text(ROLE_ATTRIBUTES)).one_or_none()

    assert row is not None, (
        "`pg_roles` has no row for the role this connection authenticated as, so there are "
        "no attributes to check and every assertion below would be vacuously true."
    )

    held = [name for name, value in zip(row._fields, row, strict=True) if value]
    assert not held, (
        f"The application role holds {held}. A runtime role with any of these is outside the "
        "grant model rather than inside it: `rolsuper` and `rolbypassrls` both read straight "
        "through a deny-all policy, which is what E0-02's security review measured on the "
        "real stack. ADR 0001 line 71 forbids it and ADR 0009 leaves that half standing. "
        "The fixture provisions this role itself, because `scripts/db-init` does not run in "
        "a testcontainers Postgres (ADR 0009's provisioning table)."
    )


def test_the_application_role_cannot_create_a_table(
    application_engine: Any,
    migrated_engine: Any,
) -> None:
    """`CREATE TABLE` as the application role is refused, and refused for that reason.

    Asserted as a refusal, not as the table's absence. "No such table afterwards"
    is satisfied by a connection that failed for any reason at all, by a
    statement that was never sent, and by a database that is read-only — none of
    which is the guarantee. `pytest.raises` says the server considered the
    statement and said no.

    **The control matters as much as the refusal**, and it is why the bootstrap
    engine is a parameter here. A database where *nobody* can create a table
    would pass the first half while being broken in a way that also makes every
    migration fail. So the same statement is run as the bootstrap identity and
    has to succeed. That pair is the difference between "this role is
    constrained" and "this database is unusable".

    E0-04 is the ticket that makes this concrete: it must not grant the
    application role `CREATE` to get migrations working. Alembic connects as the
    bootstrap identity instead.
    """
    with migrated_engine.begin() as connection:
        connection.execute(text(CREATE_FORBIDDEN_TABLE))
        connection.execute(text(DROP_FORBIDDEN_TABLE))

    with pytest.raises(ProgrammingError) as refusal, application_engine.begin() as connection:
        connection.execute(text(CREATE_FORBIDDEN_TABLE))

    assert "permission denied" in str(refusal.value).lower(), (
        "`CREATE TABLE` as the application role failed, but not with a permission error: "
        f"{refusal.value}. A syntax error or a missing database would satisfy `raises` here "
        "while saying nothing about what the role may do."
    )
