"""The runtime role reads the tool's key and can change nothing about it — E3-01, criterion 4.

> …and the application role still holds no write on the key table.

The word in that criterion is **still**. ADR 0082 left `tool_signing_key`
grantless, E1-06 added `SELECT` alone with the code that spends it, and the
sentence beside that grant in `tests/integration/test_identity_grants.py` says
why the rest is withheld: "an application connection that could write this column
could rotate the tool's identity… and could do it invisibly because a fresh key
signs perfectly."

E3-01 is the ticket most likely to undo that by accident, because it is the first
one that needs somebody to write the table at run time. The supply path answers
that with a privileged credential in an operator's hands (ADR 0126) rather than
with a grant, and this module is what makes the difference observable: the write
the operator script performs is refused on the connection the application runs on.

**Refusals, not absences.** Every assertion here is `pytest.raises` over a
statement the server considered and said no to, with the reason read out of the
message. "No row afterwards" is satisfied by a connection that failed for any
reason at all, by a statement that was never sent, and by a table that does not
exist — none of which is the guarantee. That is the shape
`tests/integration/test_application_role_privileges.py` established for the same
question about `CREATE TABLE`, and these follow it.

**Each refusal has its control, run first, on the same database.** A statement
that is malformed, or a table nobody can write, would produce the same red on the
left-hand side while saying nothing about the role — so every statement here is
run as the bootstrap identity and required to succeed, inside a transaction that
is rolled back. That pair is the difference between "this role is constrained" and
"this statement does not work".

**And the read is asserted too**, in the other direction. A role that had lost
`SELECT` would be refused every statement here for a reason that is not the one
under test, and the tool would answer 500 at `/lti/jwks` rather than serving a key
set. The catalog-level version of that grant is an equality in
`test_identity_grants.py`; this is the behavioural half.
"""

from typing import Any

import pytest
from fixtures.signing_key_tool import RETIRED_AT_COLUMN, SIGNING_KEYS, require_rotation_columns
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

pytestmark = pytest.mark.integration

# A value that is not a key and could not be mistaken for one. The insert below is
# expected to be refused, and the control's copy of it is rolled back, so nothing
# ever stores this — but a fixture holding PEM-shaped text would be the offender
# the repository-wide sweep in `tests/unit/test_mock_lms_service.py` exists to
# find, and the point of this module is that no key material is written anywhere.
NOT_A_KEY = "e3-01 refusal probe, not key material"

# The three writes the runtime role must not hold, spelled over columns E1-05
# already declared so that this test says something today and goes on saying it
# after E3-01 lands.
FORBIDDEN_WRITES = {
    "INSERT": f"INSERT INTO public.{SIGNING_KEYS} (private_key_pem) VALUES (:value)",  # noqa: S608
    "UPDATE": f"UPDATE public.{SIGNING_KEYS} SET private_key_pem = :value",  # noqa: S608
    "DELETE": f"DELETE FROM public.{SIGNING_KEYS}",  # noqa: S608
}

# The write E3-01 adds, and the one an operator script performs. Held apart from
# the three above because it is the new surface: a rotation is a column an
# application connection would love to be able to set, and "retire the tool's
# identity" is a write with no undo.
RETIREMENT_WRITE = f"UPDATE public.{SIGNING_KEYS} SET {RETIRED_AT_COLUMN} = now()"  # noqa: S608

# The read the tool genuinely needs, which is what E1-06's grant bought.
THE_GRANTED_READ = f"SELECT count(*) FROM public.{SIGNING_KEYS}"  # noqa: S608


def runs_as_the_bootstrap_identity(engine: Any, statement: str, **parameters: Any) -> None:
    """Run `statement` as the identity that migrates, then undo it.

    The control for each refusal below, and it is rolled back rather than
    committed for two reasons: a stray row would fail the non-vacuity guard in
    `test_the_published_key_set_carries_a_rotation.py`, and a `DELETE` that
    committed would take another test's planted keys with it
    (`docs/MISTAKES.md` entry 12's neighbourhood — a shared database is shared).
    """
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(statement), parameters)
        except Exception as failure:
            pytest.fail(
                f"`{statement}` failed as the bootstrap identity: {failure!r}. Then the refusal "
                "this controls says nothing about the application role — the statement is "
                "malformed, or the table is not writable by anybody, and either is a defect in "
                "this module or in the schema rather than a grant working."
            )
        finally:
            transaction.rollback()


def refused_to_the_application_role(engine: Any, statement: str, **parameters: Any) -> None:
    """`statement` is refused to the application role, and refused as a privilege error."""
    with pytest.raises(ProgrammingError) as refusal, engine.begin() as connection:
        connection.execute(text(statement), parameters)

    assert "permission denied" in str(refusal.value).lower(), (
        f"`{statement}` failed as the application role, and not with a permission error: "
        f"{refusal.value}. A syntax error, a missing column or a missing table would satisfy "
        "`raises` here while saying nothing about what the role may do — which is the whole "
        "assertion."
    )


def test_the_application_role_is_refused_every_write_to_the_signing_key_table(
    application_engine: Any, migrated_engine: Any
) -> None:
    """Criterion 4: the runtime connection cannot insert, change or remove a key.

    **The mutation this kills:** a grant widened to let the application write this
    table — the shortcut the supply path invites, because the alternative is
    telling an operator to hold a privileged credential. What it costs is
    everything ADR 0082 bought: a connection that can write this column can rotate
    the tool's identity, and a fresh key signs perfectly, so nothing looks wrong
    until a platform that fetched the old public half refuses an assertion.

    All three verbs, because they are three grants and a widening arrives one verb
    at a time. `INSERT` alone lets a compromised request path add a key of its own
    to the published set — the worst of the three, because it is additive and
    invisible. `UPDATE` replaces the tool's identity. `DELETE` takes the
    deployment's ability to sign away entirely.

    **The control runs first**, as the bootstrap identity, on the same database and
    rolled back: without it a schema nobody can write at all passes this test while
    being broken in a way that also stops every migration.
    """
    for statement in FORBIDDEN_WRITES.values():
        runs_as_the_bootstrap_identity(migrated_engine, statement, value=NOT_A_KEY)
        refused_to_the_application_role(application_engine, statement, value=NOT_A_KEY)


def test_the_application_role_cannot_retire_a_signing_key(
    application_engine: Any, migrated_engine: Any, metadata_tables: dict[str, Any]
) -> None:
    """The rotation column is not an exception to the rule, and it is the one at risk.

    E3-01 adds `retired_at`, and it is the only column on this table anybody has a
    run-time reason to want to set. A grant that arrived with it would be the
    narrowest-looking widening in the ticket and the most dangerous: retiring the
    last live key takes the deployment to 503 at `/lti/jwks` with no key to sign
    with, and retiring the newest one silently moves the signer back to a key
    platforms may already have stopped accepting. Neither is a write a request
    path should be able to make.

    **The mutation this kills:** a column-level grant — `GRANT UPDATE (retired_at)
    ON tool_signing_key TO pulse_app` — which is invisible to a table-wide
    privilege check and is exactly the currency `docs/MISTAKES.md` entry 35 is
    about. The statement here is the write itself, so the currency the privilege
    is held in does not matter.

    **The control is the same statement as the bootstrap identity**, rolled back:
    a `retired_at` that does not exist, or a statement this module spelled wrong,
    would otherwise read as the grant holding.
    """
    require_rotation_columns(metadata_tables[SIGNING_KEYS].c.keys(), "the declared table")

    runs_as_the_bootstrap_identity(migrated_engine, RETIREMENT_WRITE)
    refused_to_the_application_role(application_engine, RETIREMENT_WRITE)


def test_the_application_role_can_still_read_the_signing_key_table(
    application_engine: Any, migrated_engine: Any
) -> None:
    """The other direction, without which every refusal above is about the wrong thing.

    `migrated_engine` is a parameter and is not otherwise used: `application_engine`
    is built on the *provisioned* database rather than the migrated one, so asking
    for it alone would let this test run against a database with no schema, where
    the read fails with "relation does not exist" and reads as a missing grant.

    E1-06's grant is `SELECT` and the tool spends it on every request to
    `/lti/jwks` and on every client assertion it signs. A role that had lost it
    would be refused all four statements above with the same "permission denied",
    and this module would be green while the tool answered 500 at its own key set
    — which is `docs/MISTAKES.md` entry 3 in the shape a permission suite is most
    exposed to.

    **The mutation this kills:** the grant revoked, or narrowed to a column set
    that omits what the route reads.
    """
    with application_engine.connect() as connection:
        held = connection.execute(text(THE_GRANTED_READ)).scalar_one()

    assert held is not None, (
        f"`{THE_GRANTED_READ}` answered nothing as the application role. The count itself is not "
        "the subject — an empty table is fine — but the statement completing is: without `SELECT` "
        "the tool cannot publish its key set or sign anything, and every refusal asserted above "
        "would be a role that cannot reach the table at all rather than a role that may only read "
        "it."
    )
