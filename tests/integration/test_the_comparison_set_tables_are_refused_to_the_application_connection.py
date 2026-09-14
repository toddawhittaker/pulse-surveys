"""`pulse_app` may read the comparison-set tables and may not write them, on its own connection.

E5-01 granted this role nothing on either table, on E4-02's precedent — "a
privilege lands in the change that spends it" — and named the two tickets that
would spend one: E5-04 reads a named set to resolve it, E5-06 writes one. **This
module changes with E5-04**, which is the first of those two: the read is now
granted and every write verb is still refused.

> Grants: the first read of E5-01's tables lands here — SELECT on
> `comparison_set` and its membership relation to `pulse_app`, versioned-grants
> shape (the E4-02 precedent: a privilege lands in the change that spends it;
> E5-01 granted nothing on purpose).

**What the change costs and what it does not.** A set is a name, a declared
length and level, a creator key and a list of courses; ADR 0164 records that no
name is copied onto the row and the creator is a `person` key, which this
connection cannot resolve to anybody — its `SELECT` on `public."user"` is `(id)`
only. So the read adds no reach towards a student or a person. The writes are a
different matter and are the reason every one of them is still asserted as a
refusal: a connection able to insert a comparison set could define the cohort
every instructor in the institution is measured against, from any request path,
without passing E5-06's leadership scoping.

**The `SELECT` is now a positive control rather than a refusal**, and it is
doing more work in that role than it did in the other: it is what proves this
connection can reach these tables at all, so the three write refusals beside it
cannot be satisfied by a role that can do nothing, a table that is not there, or
a schema nobody migrated (`docs/MISTAKES.md` entry 35).

**Asserting refusal rather than absence is still the whole design of the
module.** "The query returned no rows" is satisfied by an empty table, a dropped
table and a typo alike; "the server answered `42501`" is satisfied by one thing.

**Three controls, and none is ceremony.** The connection says it is `pulse_app`
and not a superuser; the same connection reads a table it certainly is granted,
which is a second control independent of the one under test here; and both
tables are shown to exist in the catalog first, so a missing table cannot pass
as a refused privilege.

**Which failure a red here is, before E5-04's grant lands.** The `SELECT` test
fails naming the grants file and the migration that should execute it, and the
write tests go on passing — which is the right shape for a ticket whose whole
change to this module is one verb.

**The file's name is E5-01's and is kept**, because the records that cite it —
ADR 0164's consequences, E5-01's own criterion 6 — name it by path. What it says
now is that the writes are refused; the read that used to be refused beside them
is the control that makes those refusals mean anything.
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
def test_a_select_on_a_comparison_set_table_is_allowed_to_the_application_role(
    migrated_database: Any, application_engine: Any, relation: str
) -> None:
    """E5-04's own grant, executed on the connection production opens.

    The read is what this ticket spends: `resolve_named_set` reads a set's
    declared length and level and its member courses, and the service runs on
    `pulse_app` like everything else in the product. E5-01 withheld the grant
    until a ticket needed it, and this is that ticket, so what was a refusal here
    is now a statement that the privilege arrived with the change that uses it.

    **It is executed rather than read out of the ACL** — `docs/MISTAKES.md` entry
    46: a suite that drives everything through the migrating engine has not
    tested a grant at all, because that identity passes every check there is.

    **This test is also the positive control for the three refusals below.** A
    write refusal proves something only if the same connection can reach the same
    table for some other purpose; without this, `42501` on an `INSERT` is
    equally explained by a role that holds nothing anywhere.

    **The mutation it kills:** the grants file shipped without the migration that
    executes it, or executed for one of the two tables — which leaves half the
    resolution working and the other half failing at runtime with a privilege
    error nobody sees until a leadership preview is opened.
    """
    require_the_table_exists(application_engine, relation)

    refused = refusal_of_statement(application_engine, f"SELECT * FROM public.{relation}")  # noqa: S608

    assert refused is None, (
        f"`{APPLICATION_ROLE}` was refused a read of `public.{relation}`: {refused}\n\n"
        "E5-04 is the ticket that spends this privilege: SPEC §5.1 lets leadership define named "
        "comparison sets and `app.services.benchmarks` resolves one to the sections its figures "
        "are computed over, on the connection every request runs on. The grant ships as "
        "`backend/app/views_sql/comparison_set_grants_v001.sql` in the versioned shape "
        "`weekly_summary_grants_v001.sql` models, executed by this ticket's migration — a file "
        "without a revision to run it grants nothing."
    )


def a_write_of(verb: str, relation: str, tables: dict[str, Any]) -> str:
    """One write statement per verb, built so that only a privilege can refuse it.

    The update assigns a column to itself, and the column is read off the
    declared table rather than guessed: a statement naming a column that is not
    there is refused with `42703` before any privilege is consulted, and this
    module would then report a missing column as a withheld grant
    (`docs/MISTAKES.md` entry 3 in its SQLSTATE form).
    """
    if verb == "INSERT":
        return f"INSERT INTO public.{relation} DEFAULT VALUES"
    if verb == "DELETE":
        return f"DELETE FROM public.{relation}"  # noqa: S608
    table = tables.get(relation)
    if table is None:
        pytest.fail(
            f"There is no `{relation}` table on `Base.metadata` (there are {sorted(tables)}), so "
            "this module cannot name a column to write. E5-01 ships both tables in "
            "`backend/app/models/benchmark.py`."
        )
    column = next(iter(table.columns)).name
    return f'UPDATE public.{relation} SET "{column}" = "{column}"'  # noqa: S608


@pytest.mark.parametrize("relation", THE_TABLES, ids=list(THE_TABLES))
@pytest.mark.parametrize("verb", ["INSERT", "UPDATE", "DELETE"], ids=["insert", "update", "delete"])
def test_a_write_to_a_comparison_set_table_is_refused_to_the_application_role(
    migrated_database: Any,
    application_engine: Any,
    metadata_tables: dict[str, Any],
    relation: str,
    verb: str,
) -> None:
    """Every write verb, still withheld — the half E5-04 does not spend.

    A role can hold `SELECT` and be refused each write independently, so the
    three are asserted one at a time rather than as "it cannot write": a grant
    written as `GRANT SELECT, INSERT` gives this module exactly one red, and it
    names the verb.

    The write is the serious half. A connection that could insert or edit a
    comparison set could define the cohort every instructor in the institution is
    measured against, from any request path, without passing E5-06's leadership
    scoping — and a `DELETE` would remove a set that published figures were drawn
    against, which ADR 0164 calls "a benchmark that changes without anybody
    deciding it".

    **`DEFAULT VALUES` and no column list on the insert, on purpose.** Postgres
    checks the role's privilege on the relation before it evaluates a single
    constraint, so a statement that would also violate `NOT NULL` still answers
    `42501` when the privilege is missing — and naming no column keeps the
    statement from failing at parse time for a reason about spelling. The same
    reasoning has the update assign a column to itself, with the column read off
    the declared table: a name this module invented could be refused for not
    existing, which is a different SQLSTATE and a different fact.

    **The mutation it kills:** `GRANT SELECT, INSERT ON public.comparison_set TO
    pulse_app` in this ticket's own grants file — the widening a reader adds
    while building E5-06 and forgets to record; and `GRANT ALL`, which would flip
    all three of these at once.
    """
    require_the_table_exists(application_engine, relation)

    refused = refusal_of_statement(application_engine, a_write_of(verb, relation, metadata_tables))

    assert refused is not None, (
        f"`{APPLICATION_ROLE}` ran a {verb} against `public.{relation}` — or was refused for some "
        "reason the driver did not raise. E5-04 grants this role the read it spends and no verb "
        "more; E5-06 is the ticket that spends the writes, at leadership scope, and it records "
        "each grant with the sentence it comes from."
    )
    state = sqlstate_of(refused)
    assert state == INSUFFICIENT_PRIVILEGE, (
        f"The {verb} was refused with SQLSTATE {state!r} rather than {INSUFFICIENT_PRIVILEGE!r}: "
        f"{refused}. A `23502` or a `23503` here would mean the role holds the privilege and the "
        "row was refused by a constraint instead, which is the grant being in place and this test "
        "reporting the wrong reason for a red."
    )
