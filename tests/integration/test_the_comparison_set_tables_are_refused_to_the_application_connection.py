"""`pulse_app` holds nothing on the comparison-set tables, proven on its own connection.

E5-01 criterion 6, in the ticket's words:

> Grants: `pulse_app` holds **no** privilege on the new tables, proven through the
> connection production uses (MISTAKES entry 46), not through the migrating engine
> — a refused SELECT and a refused INSERT, both asserted; and the
> `RUNTIME_BASE_TABLE_PRIVILEGES` equality record in
> `tests/integration/test_identity_grants.py` stays consistent with that in
> whichever direction the record's convention requires.

**No grants, on purpose.** The ticket follows E4-02's precedent — "a privilege
lands in the change that spends it" — so the first reader is E5-04 and the first
writer is E5-06, and each grants what it spends in its own pull request. This
ticket proves the *absence*, which is a thing worth proving rather than a thing
that happens by default: a `GRANT ALL ON ALL TABLES IN SCHEMA public` written into
any later revision would hand this connection both tables and nothing else in the
repository would notice for as long as nobody looked.

**Why the refusal and not the ACL.** `RUNTIME_BASE_TABLE_PRIVILEGES` in
`tests/integration/test_identity_grants.py` is a two-direction equality over every
base table, so a grant on either of these tables already fails that test the day
it is written; and the convention there is that an ungranted table appears in the
record by *not being in it*, so this ticket adds no line to it. What that test
cannot say is what happens when the connection production opens actually runs the
statement, which is `docs/MISTAKES.md` entry 46's second sentence: a suite that
drives everything through the migrating engine has not tested a grant at all. So
this module executes a real `SELECT` and a real `INSERT` as `pulse_app` and
requires each to be refused for insufficient privilege.

**Asserting refusal rather than absence is the whole design of the module.** "The
query returned no rows" is satisfied by an empty table, a dropped table and a
typo alike; "the server answered `42501`" is satisfied by one thing.

**Three controls, and none is ceremony.** The connection says it is `pulse_app`
and not a superuser; the same connection reads a table it certainly is granted, so
a refusal here cannot be a connection that can do nothing at all
(`docs/MISTAKES.md` entry 35); and both tables are shown to exist in the catalog
first, so a missing table cannot pass as a refused privilege.

**Which failure a red here is, before E5-01 lands.** Each test fails on the
catalog guard in its own body, naming the table SPEC §8 lists and E5-01 builds —
a FAILED and never an ERROR (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.comparison_sets import COMPARISON_SET_TABLE, EXPECTED_MEMBERSHIP_TABLE
from fixtures.supervision import sqlstate_of
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# The role `.env.example` gives `DB_APP_USER`. Spelled here rather than imported
# from a sibling test module, for the reason `test_identity_grants.py` gives about
# its own copies.
APPLICATION_ROLE = "pulse_app"

# What SPEC §8's inventory and the breakdown call the two tables. The membership
# table is named here rather than discovered — unlike the schema modules, this one
# asks the *catalog* a question and a name is what the catalog takes. A rename
# makes this file red with a message saying the table is not there, which is the
# right outcome for a grant test that would otherwise silently stop asking.
THE_TABLES = (COMPARISON_SET_TABLE, EXPECTED_MEMBERSHIP_TABLE)

# A relation the application role certainly reads, as the control every probe
# needs (`docs/MISTAKES.md` entry 35). `classification` has carried
# `SELECT, INSERT` for `pulse_app` since E0-13 and it is in
# `RUNTIME_BASE_TABLE_PRIVILEGES` today.
A_RELATION_THE_ROLE_CERTAINLY_READS = "classification"

# Postgres' insufficient-privilege SQLSTATE. Pinned exactly, because here the
# *reason* for the refusal is the criterion: `42P01` (undefined table) is a table
# that is not there and `23502` would be a row the role was allowed to attempt.
INSUFFICIENT_PRIVILEGE = "42501"

RELATION_EXISTS = text("SELECT to_regclass(:relation) IS NOT NULL")


def require_the_table_exists(engine: Any, relation: str) -> None:
    """Stop unless `public.<relation>` is in the catalog, naming the ticket that builds it.

    Called as the first statement of every test body and never from a fixture, so
    that the red while E5-01 is unbuilt is a failed assertion naming the table
    rather than an error in setup (`docs/MISTAKES.md` entry 44). It is also the
    control that keeps a missing table from passing as a refused privilege: a
    `SELECT` against a table that does not exist is refused too, with a different
    SQLSTATE and for a reason that has nothing to do with a grant.
    """
    with engine.connect() as connection:
        present = connection.execute(RELATION_EXISTS, {"relation": f"public.{relation}"}).scalar()
    if not present:
        pytest.fail(
            f"`public.{relation}` is not in the catalog, so nothing here is a statement about a "
            "grant. SPEC §8 lists `comparison_set` in its table inventory and E5-01 builds it and "
            "its membership table in a migration off head `e5a2b81c47d3`."
        )


def refusal_of_statement(engine: Any, statement: str) -> DatabaseError | None:
    """Run one statement on its own connection as this engine's role; answer the error.

    Its own connection and its own transaction per call, because a refused
    statement aborts the transaction it ran in — a second probe on the same
    connection would fail with `25P02` and read as a second refusal.
    """
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(statement))
        except DatabaseError as refused:
            transaction.rollback()
            return refused
        transaction.rollback()
        return None


def test_the_probe_connects_as_the_application_role_and_can_see_what_it_is_granted(
    migrated_database: Any, application_engine: Any
) -> None:
    """CONTROL — must be green today and after E5-01 lands.

    Two facts every refusal below rests on, asserted where a failure names them.
    The connection is `pulse_app` and not the migrating superuser, which passes
    every grant there is; and it can actually read a table this scheme grants it,
    so a refusal below is a refusal about *these* tables rather than the answer a
    connection with nothing gives to everything (`docs/MISTAKES.md` entry 35 — a
    guard that only ever reports absence cannot say what it can see).

    `migrated_database` is depended on and not used: `application_engine` is built
    from `provisioned_database`, which is the container before any migration ran,
    and without this the control could be asked of a database with no tables in it.
    """
    with application_engine.connect() as connection:
        role = connection.execute(text("SELECT current_user")).scalar_one()
        assert role == APPLICATION_ROLE, (
            f"This connection reports itself as {role!r} rather than as {APPLICATION_ROLE!r}, so "
            "nothing in this module is a statement about a grant."
        )
        rows = connection.execute(
            text(f"SELECT count(*) FROM public.{A_RELATION_THE_ROLE_CERTAINLY_READS}")  # noqa: S608
        ).scalar_one()

    assert rows is not None, (
        f"Counting `{A_RELATION_THE_ROLE_CERTAINLY_READS}` as `{APPLICATION_ROLE}` answered "
        "nothing at all. E0-13 grants this role `SELECT` on that table and "
        "`RUNTIME_BASE_TABLE_PRIVILEGES` records it, so a connection that cannot read it is a "
        "connection that can do nothing — and every refusal below would then be about the "
        "connection rather than about the comparison-set tables."
    )


@pytest.mark.parametrize("relation", THE_TABLES, ids=list(THE_TABLES))
def test_a_select_on_a_comparison_set_table_is_refused_to_the_application_role(
    migrated_database: Any, application_engine: Any, relation: str
) -> None:
    """Criterion 6, the read half, executed rather than read out of the ACL.

    The statement is run on the connection every screen in the product opens, and
    the assertion is that the *server refused it for insufficient privilege* —
    not that it came back empty. An empty answer is what a dropped table, an
    unseeded database and a broken query all produce, and asserting one would be
    a §4-shaped test that passes for a reason unrelated to what it claims
    (`docs/MISTAKES.md` entry 3).

    **The mutation it kills:** `GRANT SELECT ON public.comparison_set TO
    pulse_app` written into this ticket's own grants file "so E5-04 has it ready",
    which is precisely the convenience grant E4-02's precedent exists against.
    Also `GRANT ALL ON ALL TABLES IN SCHEMA public TO pulse_app` in any later
    revision, which grants both tables at once.

    **The near miss it tolerates:** a grant to any other role. Only `pulse_app` is
    asked about here, because it is the connection production uses;
    `RUNTIME_BASE_TABLE_PRIVILEGES` is where every role's whole surface is held as
    an equality.
    """
    require_the_table_exists(application_engine, relation)

    refused = refusal_of_statement(application_engine, f"SELECT * FROM public.{relation}")  # noqa: S608

    assert refused is not None, (
        f"`{APPLICATION_ROLE}` read `public.{relation}` successfully. E5-01 grants this role "
        "nothing on either comparison-set table on purpose: the first reader is E5-04 and the "
        "first writer is E5-06, and each grants what it spends in its own pull request "
        "(E4-02's precedent, quoted in `weekly_summary_grants_v001.sql`). A privilege that "
        "arrives before the change that uses it is a privilege no reviewer ever weighed."
    )
    state = sqlstate_of(refused)
    assert state == INSUFFICIENT_PRIVILEGE, (
        f"The read was refused with SQLSTATE {state!r} rather than {INSUFFICIENT_PRIVILEGE!r}: "
        f"{refused}. Only insufficient privilege is the criterion here — `42P01` means the table "
        "is not there, which the guard at the top of this test is supposed to have caught, and "
        "anything else means this module built a statement the server could not run."
    )


@pytest.mark.parametrize("relation", THE_TABLES, ids=list(THE_TABLES))
def test_an_insert_into_a_comparison_set_table_is_refused_to_the_application_role(
    migrated_database: Any, application_engine: Any, relation: str
) -> None:
    """Criterion 6, the write half, and it is not the read half again.

    A role can be refused a read and hold `INSERT` — the two are separate
    privileges and `RUNTIME_BASE_TABLE_PRIVILEGES` carries several tables where
    exactly one of them is granted. The write is the more serious of the two here:
    a connection that could insert a comparison set could define the cohort every
    instructor in the institution is measured against, from any request path,
    without passing E5-06's leadership scoping.

    **`DEFAULT VALUES` and no column list on purpose.** Postgres checks the
    role's privilege on the relation before it evaluates a single constraint, so a
    statement that would also violate `NOT NULL` still answers `42501` when the
    privilege is missing — and naming no column keeps the statement from failing
    at parse time for a reason about spelling. If the grant were ever made, this
    test would go red with an integrity violation rather than green, which is the
    right way round.

    **The mutation it kills:** `GRANT INSERT ON public.comparison_set_member TO
    pulse_app` — the one a reader adds while building E5-06 and forgets to record.
    """
    require_the_table_exists(application_engine, relation)

    refused = refusal_of_statement(
        application_engine, f"INSERT INTO public.{relation} DEFAULT VALUES"
    )

    assert refused is not None, (
        f"`{APPLICATION_ROLE}` inserted into `public.{relation}` — or was refused for some reason "
        "the driver did not raise. E5-01 grants this role no privilege on either table; E5-06 is "
        "the ticket that spends the write, at leadership scope, and it records the grant with the "
        "sentence it comes from."
    )
    state = sqlstate_of(refused)
    assert state == INSUFFICIENT_PRIVILEGE, (
        f"The insert was refused with SQLSTATE {state!r} rather than {INSUFFICIENT_PRIVILEGE!r}: "
        f"{refused}. A `23502` here would mean the role holds `INSERT` and the row was refused by "
        "a `NOT NULL` instead, which is the grant being in place and this test reporting the "
        "wrong reason for a red."
    )
