"""`pulse_app` may now write a comparison set, and still may not edit a membership row.

E5-01 granted this role nothing on either table, on E4-02's precedent — "a
privilege lands in the change that spends it" — and named the two tickets that
would spend one: E5-04 reads a named set to resolve it, E5-06 writes one. E5-04
added the read. **This module changes with E5-06**, the second and last of them,
and what it now says is:

> Grants: the write verbs on E5-01's tables land here with the writer (INSERT,
> UPDATE, DELETE as the routes actually spend them, withheld verbs named),
> versioned-grants shape — the same E4-02 precedent E5-04's SELECT follows.

Work-order decision 6 fixes exactly which verbs:
`backend/app/views_sql/comparison_set_write_grants_v001.sql` grants `INSERT,
UPDATE, DELETE ON comparison_set` and `INSERT, DELETE ON
comparison_set_member`, and **`UPDATE` on the membership table is withheld**
because membership is replaced wholesale on a `PUT` — the rows not in the new
list are deleted and the new ones inserted — so nothing in this product edits a
membership row in place.

**E5-14 narrowed the set table's `UPDATE` to four columns** — `name`,
`length_weeks`, `level`, `updated_at` — after the data-model review found the
table-wide grant let this role rewrite a set's creator, which is what E5-06's
edit and delete scoping reads. So the set table's `UPDATE` is asserted per
column, both sides, below.

**The withheld verb is the whole assertion here**, and the granted ones are what
make it mean something. A role that could do nothing would be refused `UPDATE`
on the membership table too, and a module asserting only that refusal would be
green against a migration that granted nothing at all (`docs/MISTAKES.md` entry
35). So every granted verb is *executed* on the connection production opens, and
the one refusal sits among them.

**Executed rather than read out of the ACL** (`docs/MISTAKES.md` entry 46): a
suite that drives everything through the migrating engine has not tested a grant
at all, because that identity passes every check there is.
`tests/integration/test_identity_grants.py` holds the catalog's side of the same
fact, and the two are deliberately different instruments.

**"Granted" is asserted as "not refused for want of a privilege", not as
"succeeded".** Postgres checks the role's privilege on a relation before it
evaluates a single constraint, so an `INSERT ... DEFAULT VALUES` on a table full
of `NOT NULL` columns answers `42501` when the privilege is missing and `23502`
when it is there. `23502` is the grant being in place, and treating it as a
failure would make this module red against exactly the tree it is meant to
approve.

**Asserting refusal rather than absence is still the whole design of the
module.** "The query returned no rows" is satisfied by an empty table, a dropped
table and a typo alike; "the server answered `42501`" is satisfied by one thing.

**Three controls, and none is ceremony.** The connection says it is `pulse_app`
and not a superuser; the same connection reads a table it certainly is granted;
and both tables are shown to exist in the catalog first, so a missing table
cannot pass as a refused privilege.

**Which failure a red here is, before E5-06's migration lands.** The granted-verb
tests fail naming the grants file and the migration that should execute it; the
`SELECT` control and the withheld `UPDATE` go on passing — which is the right
shape for a ticket whose whole change to this module is five verbs.

**The file's name is E5-01's and is kept**, because the records that cite it —
ADR 0164's consequences, E5-01's own criterion 6 — name it by path. What it says
now is which writes are granted and which single verb is not.
"""

from typing import Any

import pytest
from fixtures.comparison_sets import (
    COMPARISON_SET_TABLE,
    EXPECTED_MEMBERSHIP_TABLE,
    INSUFFICIENT_PRIVILEGE,
    a_write_of,
    an_update_of_column,
    refusal_of_statement,
)
from fixtures.supervision import sqlstate_of
from sqlalchemy import text

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

# Decision 6's grant, verb by verb, as `(relation, verb)`. Written out rather
# than derived from the SQL file this polices (`docs/MISTAKES.md` entry 19): an
# expectation read out of the thing under test agrees with a grants file that
# says the wrong thing.
#
# **`UPDATE` on `comparison_set` left this tuple at E5-14.** The data-model review
# found the table-wide grant let `pulse_app` rewrite a set's `created_by_person_id`
# — the column E5-06's edit and delete scoping reads to decide *whose* set it is —
# and its `created_at` and `id`. The orchestrator's ruling makes the grant
# column-grain, `GRANT UPDATE (name, length_weeks, level, updated_at)`, with a new
# `comparison_set_write_grants_v002.sql`; the two tuples below it hold each side.
GRANTED = (
    (COMPARISON_SET_TABLE, "INSERT"),
    (COMPARISON_SET_TABLE, "DELETE"),
    (EXPECTED_MEMBERSHIP_TABLE, "INSERT"),
    (EXPECTED_MEMBERSHIP_TABLE, "DELETE"),
)

# The four columns a set edit writes, and the only four `pulse_app` may update.
UPDATABLE_SET_COLUMNS = ("name", "length_weeks", "level", "updated_at")

# The columns it may not, each a fact a leader's edit never changes. The creator is
# the one the ruling names, because it is what decides who may edit or delete a
# set; the key and the creation instant are the other two the review named.
WITHHELD_SET_COLUMNS = ("created_by_person_id", "id", "created_at")

# The one write verb decision 6 withholds, and the sentence it comes from.
WITHHELD = (EXPECTED_MEMBERSHIP_TABLE, "UPDATE")
WHY_IT_IS_WITHHELD = (
    "membership is replaced wholesale on a `PUT` — rows not in the new list are deleted and the "
    "new ones inserted — so nothing in this product edits a membership row in place, and a "
    "connection that could would be able to move one set's course into another set's cohort "
    "without touching either set row"
)

# A relation the application role certainly reads, as the control every probe
# needs (`docs/MISTAKES.md` entry 35). `classification` has carried
# `SELECT, INSERT` for `pulse_app` since E0-13 and it is in
# `RUNTIME_BASE_TABLE_PRIVILEGES` today.
A_RELATION_THE_ROLE_CERTAINLY_READS = "classification"

# `INSUFFICIENT_PRIVILEGE`, `refusal_of_statement` and `a_write_of` live in
# `tests/fixtures/comparison_sets.py`: E5-06's downgrade module asks the same
# question of a throwaway database, and one hazard gets one helper
# (`docs/MISTAKES.md` entry 13).

RELATION_EXISTS = text("SELECT to_regclass(:relation) IS NOT NULL")

GRANTS_ARE_OWED = (
    "E5-06 is the ticket that spends the writes. Decision 6 ships them as "
    "`backend/app/views_sql/comparison_set_write_grants_v001.sql` in the versioned shape "
    "`comparison_set_grants_v001.sql` models, executed by this ticket's migration — a file "
    "without a revision to run it grants nothing."
)


def require_the_table_exists(engine: Any, relation: str) -> None:
    """Stop unless `public.<relation>` is in the catalog, naming the ticket that builds it.

    Called as the first statement of every test body and never from a fixture, so
    that a red while a table is absent is a failed assertion naming it rather
    than an error in setup (`docs/MISTAKES.md` entry 44). It is also the control
    that keeps a missing table from passing as a refused privilege: a statement
    against a table that does not exist is refused too, with a different SQLSTATE
    and for a reason that has nothing to do with a grant.
    """
    with engine.connect() as connection:
        present = connection.execute(RELATION_EXISTS, {"relation": f"public.{relation}"}).scalar()
    if not present:
        pytest.fail(
            f"`public.{relation}` is not in the catalog, so nothing here is a statement about a "
            "grant. SPEC §8 lists `comparison_set` in its table inventory and E5-01 builds it and "
            "its membership table."
        )


def test_the_probe_connects_as_the_application_role_and_can_see_what_it_is_granted(
    migrated_database: Any, application_engine: Any
) -> None:
    """CONTROL — must be green today and after E5-06 lands.

    Two facts every assertion below rests on, asserted where a failure names
    them. The connection is `pulse_app` and not the migrating superuser, which
    passes every grant there is; and it can actually read a table this scheme
    grants it, so a refusal below is a refusal about *these* tables rather than
    the answer a connection with nothing gives to everything
    (`docs/MISTAKES.md` entry 35 — a guard that only ever reports absence cannot
    say what it can see).

    `migrated_database` is depended on and not used: `application_engine` is
    built from `provisioned_database`, which is the container before any
    migration ran, and without this the control could be asked of a database
    with no tables in it.
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
        "connection that can do nothing — and every statement below would then be about the "
        "connection rather than about the comparison-set tables."
    )


@pytest.mark.parametrize("relation", THE_TABLES, ids=list(THE_TABLES))
def test_a_select_on_a_comparison_set_table_is_allowed_to_the_application_role(
    migrated_database: Any,
    application_engine: Any,
    metadata_tables: dict[str, Any],
    relation: str,
) -> None:
    """E5-04's grant, still held, and the control that these tables are reachable at all.

    The read is what E5-04 spends: `resolve_named_set` reads a set's declared
    length and level and its member courses, and the service runs on `pulse_app`
    like everything else in the product. E5-06's preview spends it too.

    **The mutation it kills:** E5-06's own grants file written as a `GRANT` that
    *replaces* rather than adds — a `REVOKE ALL` followed by the new verbs, which
    reads as tidy and takes the read with it.
    """
    require_the_table_exists(application_engine, relation)

    refused = refusal_of_statement(
        application_engine, a_write_of("SELECT", relation, metadata_tables)
    )

    assert refused is None, (
        f"`{APPLICATION_ROLE}` was refused a read of `public.{relation}`: {refused}\n\n"
        "E5-04 granted it, in `backend/app/views_sql/comparison_set_grants_v001.sql`, and E5-06 "
        "adds the write verbs beside it rather than in place of it."
    )


@pytest.mark.parametrize("relation,verb", GRANTED, ids=[f"{r}-{v}" for r, v in GRANTED])
def test_a_granted_write_reaches_the_comparison_set_tables_on_the_application_connection(
    migrated_database: Any,
    application_engine: Any,
    metadata_tables: dict[str, Any],
    relation: str,
    verb: str,
) -> None:
    """Each verb E5-06 spends, executed as the role production runs as.

    The API's whole job is to write a comparison set on this connection: the
    routes run on `pulse_app` like everything else, so a grants file that shipped
    without the migration to execute it, or that named one of the two tables,
    leaves a leadership write failing at runtime with a privilege error nobody
    sees until somebody defines a set.

    **"Granted" is `not 42501`, not "succeeded".** Postgres consults the
    privilege before any constraint, so a `DEFAULT VALUES` insert into a table of
    `NOT NULL` columns answers `23502` once the grant is there — the row was
    refused by a rule about the data, which is the grant being in place. Every
    statement here runs in its own transaction and is rolled back.

    **The mutations this kills:** a grants file listing only `comparison_set`,
    which leaves membership unwritable and every set empty; `GRANT SELECT,
    INSERT` where `INSERT, UPDATE, DELETE` belongs, which makes an edit or a
    delete fail at the last moment with a message no route translates; and a
    versioned SQL file with no revision executing it, which is a grant nobody
    made.

    **Expected red before E5-06's migration lands:** this assertion, naming the
    verb and the grants file.
    """
    require_the_table_exists(application_engine, relation)

    refused = refusal_of_statement(application_engine, a_write_of(verb, relation, metadata_tables))
    state = None if refused is None else sqlstate_of(refused)

    assert state != INSUFFICIENT_PRIVILEGE, (
        f"`{APPLICATION_ROLE}` was refused a {verb} on `public.{relation}` for want of the "
        f"privilege ({state}): {refused}\n\n{GRANTS_ARE_OWED}"
    )


@pytest.mark.parametrize("column", UPDATABLE_SET_COLUMNS, ids=list(UPDATABLE_SET_COLUMNS))
def test_an_update_of_a_set_column_an_edit_writes_is_granted(
    migrated_database: Any,
    application_engine: Any,
    metadata_tables: dict[str, Any],
    column: str,
) -> None:
    """E5-14's column-grain grant, the granted side: each column a set edit writes.

    `PUT /leadership/comparison-sets/{id}` rewrites a set's name, declared length
    and level and stamps `updated_at`; each is executed here as `pulse_app` and
    must not be refused for want of the privilege.

    **The mutation it kills:** the column list written short — `updated_at` left
    out, say — which fails every edit at its last statement with a privilege error
    no route translates. **Its pair** is the withheld-column test below.
    """
    require_the_table_exists(application_engine, COMPARISON_SET_TABLE)

    refused = refusal_of_statement(
        application_engine, an_update_of_column(COMPARISON_SET_TABLE, column, metadata_tables)
    )
    state = None if refused is None else sqlstate_of(refused)

    granted = ", ".join(UPDATABLE_SET_COLUMNS)
    assert state != INSUFFICIENT_PRIVILEGE, (
        f"`{APPLICATION_ROLE}` was refused an UPDATE of `{COMPARISON_SET_TABLE}.{column}` for want "  # noqa: S608 — an assertion message, not a statement
        f"of the privilege: {refused}\n\nE5-14's ruling grants `UPDATE ({granted})` on the set "
        "table, in `comparison_set_write_grants_v002.sql`."
    )


@pytest.mark.parametrize("column", WITHHELD_SET_COLUMNS, ids=list(WITHHELD_SET_COLUMNS))
def test_an_update_of_a_set_column_no_edit_writes_is_refused(
    migrated_database: Any,
    application_engine: Any,
    metadata_tables: dict[str, Any],
    column: str,
) -> None:
    """E5-14's column-grain grant, the withheld side: the creator, the key, the creation time.

    `created_by_person_id` is what E5-06's edit and delete scoping reads to decide
    whose set a request may change; a connection able to rewrite it can hand any
    set to any leader. The data-model review found the table-wide `UPDATE` allowed
    exactly that. Among the granted column updates above, this refusal is about
    the column, not about a connection that can write nothing.

    **The SQLSTATE is pinned exactly**, because anything else — a constraint
    refusing the row — would mean the privilege is there.

    **The mutation it kills:** the table-wide `UPDATE` left in place (or not
    revoked when the column grant is added — Postgres keeps both, and the
    table-level one wins); and a column list that includes the creator.
    """
    require_the_table_exists(application_engine, COMPARISON_SET_TABLE)

    refused = refusal_of_statement(
        application_engine, an_update_of_column(COMPARISON_SET_TABLE, column, metadata_tables)
    )

    assert refused is not None, (
        f"`{APPLICATION_ROLE}` ran an UPDATE of `{COMPARISON_SET_TABLE}.{column}`. E5-14's ruling "
        f"grants `UPDATE` on {list(UPDATABLE_SET_COLUMNS)} only, and revokes the table-wide grant."
    )
    state = sqlstate_of(refused)
    assert state == INSUFFICIENT_PRIVILEGE, (
        f"The UPDATE of `{COMPARISON_SET_TABLE}.{column}` was refused with SQLSTATE {state!r} "
        f"rather than {INSUFFICIENT_PRIVILEGE!r}: {refused}. Anything else means the role holds "
        "the privilege and something else refused the statement."
    )


def test_an_update_of_a_membership_row_is_still_refused_to_the_application_role(
    migrated_database: Any, application_engine: Any, metadata_tables: dict[str, Any]
) -> None:
    """The one write verb decision 6 withholds, asserted among the five it grants.

    A role can hold every other verb and be refused this one, so it is asserted
    on its own rather than as "it cannot write": the five granted verbs above are
    what make this refusal a statement about `UPDATE` on one table rather than
    about a connection that can do nothing.

    Why it is withheld: membership is replaced wholesale on a `PUT`, so nothing
    in this product edits a membership row in place — and a connection that
    could would be able to move one set's course into another set's cohort
    without touching either set row.

    **The mutations this kills:** `GRANT ALL ON comparison_set_member`, which is
    one word shorter than the right grant and flips this; and `GRANT INSERT,
    UPDATE, DELETE` copied from the set table's line, which is the likeliest way
    the withheld verb arrives by accident.

    **The SQLSTATE is pinned exactly**, because a `23503` here would mean the
    role holds the privilege and a constraint refused the row instead — the grant
    being in place and this test reporting the wrong reason for a red.
    """
    relation, verb = WITHHELD
    require_the_table_exists(application_engine, relation)

    refused = refusal_of_statement(application_engine, a_write_of(verb, relation, metadata_tables))

    assert refused is not None, (
        f"`{APPLICATION_ROLE}` ran an {verb} against `public.{relation}` — or was refused for some "
        f"reason the driver did not raise. Decision 6 withholds it and names why: "
        f"{WHY_IT_IS_WITHHELD}."
    )
    state = sqlstate_of(refused)
    assert state == INSUFFICIENT_PRIVILEGE, (
        f"The {verb} was refused with SQLSTATE {state!r} rather than {INSUFFICIENT_PRIVILEGE!r}: "
        f"{refused}. A `23502` or a `23503` here would mean the role holds the privilege and the "
        "row was refused by a constraint instead, which is the grant having arrived and this test "
        "reporting the wrong reason for a red."
    )
