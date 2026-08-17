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

**What this could not catch, and what E0-10 does about it.** As E0-08 shipped it,
the sweep had two holes, and its own security review found both. An identity
column whose name contains neither "name" nor "email" — `login_id`, `picture`,
`lis_person_sourcedid` — was not in it; and the table walk was one foreign-key
hop rather than a fixed point, so a table linking to a table that links to `user`
was never swept at all. Neither was exploitable in E0-08, because nothing there
has a read path or a grant. **E0-10 lands the grants, and closes both — here, in
this module.** `IDENTITY_NAME_FRAGMENTS` is widened and `people_tables` now
iterates to a fixed point; the two tests that plant those cases are at the foot
of the file and require the sweep to report them. The enumeration this file
computes is what E0-10's views and the CI invariant pass are both built on.

**One test here is `invariant`-marked**, and it is the last one:
`test_no_view_reads_a_column_the_identity_marker_names`. A view is read with its
owner's privileges, so it is the one route to identity that E0-10's grants do not
close, and this file holds the only guard on it. Its docstring carries the
reasoning; `scripts/ci/check_invariants.py` is what makes the mark mean
something, by treating a skip, an xfail or an empty collection in that pass as a
failure.

**That the fix lives in a test module is the decision, not an accident**, and
dispute E0-10-01 is where it was settled: the discovery rule is a judgement about
*names*, so there is nothing in the schema for it to be read off, and shipping the
list from `app.models` for this file to import would leave the test holding its
expectation inside the thing it checks (`docs/MISTAKES.md` entry 19). ADR 0022 and
E0-10 both already put it here. The consequence to keep in view: no implementation
change can move these two assertions, so **a mutation of this module is the only
way to check them**, and both were mutated in that dispute before being believed.

What remains outside the search is stated on `IDENTITY_NAME_FRAGMENTS` below
rather than here, beside the tuple that decides it (`docs/MISTAKES.md` entry 14).
"""

from importlib import import_module
from typing import Any

import pytest
from sqlalchemy import Table, inspect, text

pytestmark = pytest.mark.integration

# The token a comment carries to mark a column, matched case-insensitively as a
# substring. **This file's choice** of spelling, and the obvious one: the ticket,
# SPEC §8 and ADR 0001 all call these "identity columns".
MARKER_TOKEN = "identity"  # noqa: S105 — the marker convention's token, not a credential

# The name-prefix form of the same marker, following ADR 0014's precedent for
# LMS-owned columns. Two spellings because the ticket names neither.
MARKER_PREFIXES = ("identity_", "pii_")

# How a column name is recognised as holding a person. **Widened by E0-10**, whose
# fourth criterion is that "an identity column whose name contains neither 'name'
# nor 'email' is still caught": a roster sync storing an NRPS or LTI claim as
# `login_id`, `picture` or `lis_person_sourcedid` used to land an identity column
# that the sweep passed unnoticed.
#
# **`login_id`, never a bare `login`**, and that is measured rather than chosen.
# With `login` the sweep pulls in `role_assignment.permits_web_login` — a boolean
# about which doors a role opens (ADR 0026), on a table that reaches `person` and
# that carries no identity at all — and turns this module's own tripwire and
# `test_role_assignment_graph.py`'s sweep red over it. Both the implementer and
# the arbitrator of dispute E0-10-01 ran that; with `login_id` the widened set
# adds no member to what ("name", "email") already finds on today's schema.
#
# **Three copies of this tuple live in `tests/`** — this module,
# `test_identity_schema.py` and `test_role_assignment_graph.py` — and each runs
# its own sweep. They are copies deliberately: a test module importing a sibling
# test module works only because of where pytest puts `tests/` on `sys.path`, and
# a collection error is not a failing test. Change one, change all three; the
# dispute found the comment here claiming there were two.
#
# **What the widened set still cannot see**, stated rather than implied
# (`docs/MISTAKES.md` entry 14, and E0-10's criterion asks the pull request for
# this sentence): an identity column named none of these — `sis`, `banner`,
# `external_ref`, `initials`, `dob` — and any identity column on a table with no
# foreign-key path to `user`, `user_identity` or `person`. Both are *naming*
# judgements, and no test that reads a database can make one: a `text` column
# called `external_ref` and a `text` column holding a student number are the same
# object to Postgres. What closes that gap is not this tuple but the grant model,
# which withholds `user_identity` from `pulse_app` whatever anything is called.
IDENTITY_NAME_FRAGMENTS = (
    "name",
    "email",
    "login_id",
    "picture",
    "sourcedid",
    "phone",
    "sortable",
    "given",
    "family",
    "surname",
    "address",
    "photo",
    "avatar",
    "username",
)

# The tables that hold a person by construction. Anything with a foreign key to
# one of them is swept too — see `people_tables`.
PERSON_TABLES = ("user", "user_identity", "person")

# ---------------------------------------------------------------------------
# E0-10 changes this module in two places and adds three tests, and all of it is
# here rather than in a module of E0-10's own for one reason: this file is where
# the convention is *defined*, so the file that asserts the widened rule has to be
# the file that holds it. A copy of the discovery next door would be a copy that
# keeps the old definition — `docs/MISTAKES.md` entry 13, which has cost this
# project two dispute rounds. So the marker sweep, the two holes E0-08's security
# review found in it, and the view test built on top of them all read the same
# `IDENTITY_NAME_FRAGMENTS`, `people_tables` and `database_marked_columns`.
# ---------------------------------------------------------------------------

# Columns a roster sync could plausibly land that contain neither "name" nor
# "email". E0-10's fourth criterion names exactly these three, so they are the
# ticket's words rather than this file's guess — `docs/MISTAKES.md` entry 19 is
# about the difference, and this constant is the kind that must not drift from
# the document it came from. Deliberately *not* derived from
# `IDENTITY_NAME_FRAGMENTS`: these are the cases the ticket requires to be
# caught, and the tuple above is one answer to them, so a test that read the
# planted names out of the answer would be checking the answer against itself.
PLAUSIBLE_IDENTITY_COLUMN_NAMES = ("login_id", "picture", "lis_person_sourcedid")

# A column today's fragments already catch, planted beside them as the control.
# Without it, a failure below cannot be told apart from "the planted table is not
# swept at all", which is a different defect with a different fix.
RECOGNISED_IDENTITY_COLUMN_NAME = "display_name"

# Tables planted for one test and rolled back with it. Named for the ticket so
# that one surviving a fixture change is traceable.
PLANTED_ROSTER_TABLE = "e0_10_planted_roster_sync"
PLANTED_HOPS = ("e0_10_planted_hop_one", "e0_10_planted_hop_two", "e0_10_planted_hop_three")

# Every (view, table, column) a view depends on, at column grain. Postgres
# records the dependency when it stores the view's rewrite rule, which is why
# this sees through an alias: a view selecting `identity_name AS instructor`
# depends on `identity_name` and says so here. Reading the view's own column
# names instead would miss exactly that, and it is the shape somebody writes when
# a screen needs a name and the reviewer is reading the output columns.
VIEW_COLUMN_DEPENDENCIES = """
    SELECT DISTINCT v.relname AS view_name, c.relname AS table_name, a.attname AS column_name
    FROM pg_depend d
    JOIN pg_rewrite rw ON rw.oid = d.objid AND d.classid = 'pg_rewrite'::regclass
    JOIN pg_class v ON v.oid = rw.ev_class
    JOIN pg_namespace vn ON vn.oid = v.relnamespace
    JOIN pg_class c ON c.oid = d.refobjid AND d.refclassid = 'pg_class'::regclass
    JOIN pg_namespace cn ON cn.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.refobjsubid
    WHERE v.relkind IN ('v', 'm')
      AND vn.nspname = 'public'
      AND cn.nspname = 'public'
      AND d.refobjsubid > 0
      AND c.oid <> v.oid
    ORDER BY 1, 2, 3
"""

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
    """Tables that hold a person: the three named ones, and anything that reaches one.

    **Iterated to a fixed point, which is E0-10's third criterion.** As E0-08
    shipped it this tested each table's foreign keys against `PERSON_TABLES`
    rather than against the set it was building, so it walked exactly one hop and
    a table linking to a table that links to `user` was never swept at all. The
    tables that was written about are `answer` and `threat_case` — the second
    being §6.2's Care queue — and neither exists yet, so the property is asserted
    over a planted chain in
    `test_the_marker_sweep_follows_the_foreign_key_walk_to_a_fixed_point` below.

    The loop terminates because `found` only grows and is bounded by `present`.
    On today's schema it reaches exactly the tables the one-hop version reached,
    so widening it changed no existing result — measured in dispute E0-10-01
    rather than reasoned about. (No count is written here on purpose: the set
    grows with every ticket that adds a table, and a number in a docstring is a
    record with a scheduled expiry, `docs/MISTAKES.md` entry 1.)
    """
    inspector = inspect(engine)
    present = set(inspector.get_table_names())
    found = {name for name in PERSON_TABLES if name in present}
    while True:
        reaching = {
            table_name
            for table_name in present
            for key in inspector.get_foreign_keys(table_name)
            if key.get("referred_table") in found
        }
        if reaching <= found:
            return found
        found |= reaching


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
        f"{unmarked} are named as a person's identity — one of {list(IDENTITY_NAME_FRAGMENTS)} — "
        "and carry no identity marker. E0-10 "
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


# ---------------------------------------------------------------------------
# E0-10 — the two holes, and the sweep that reads the views.
# ---------------------------------------------------------------------------


def primary_key_of(connection: Any, table: str) -> str:
    """The one primary key column of `table` (ADR 0016 makes it one uuid)."""
    columns = (inspect(connection).get_pk_constraint(table) or {}).get("constrained_columns") or []
    assert len(columns) == 1, (
        f"`{table}` reports {columns} as its primary key. ADR 0016 makes every primary key one "
        "server-generated uuid, and this test plants a foreign key to it."
    )
    return columns[0]


def test_the_marker_sweep_follows_the_foreign_key_walk_to_a_fixed_point(db_session: Any) -> None:
    """Criterion: "the marker sweep reaches every table that can hold identity".

    As E0-08 shipped it, `people_tables` above tested each table's foreign keys
    against the three-table constant rather than against the set it was building,
    so it walked **one hop**: a table linking to a table that links to `user` was
    never swept. The two E0-10 names are `answer` and `threat_case` — the second
    being §6.2's Care queue, the most identity-adjacent table in the system. This
    test is what holds the repair in place.

    **Neither of those tables exists yet**, and the criterion now says so and asks
    for the property instead: "plant a chain at least **three** links from a
    person table and show it is swept. Three, not two, because a walk repaired by
    hard-coding a second hop passes a two-link test." `answer` arrives with the
    survey tables in E2 and `threat_case` with the Care case model in E10, so a
    test naming them today could only fail on their absence. **The mutation this
    exists to survive is a second hard-coded hop.**

    The planted tables are dropped by `db_session`'s rollback: Postgres puts DDL
    inside the transaction.
    """
    session = db_session
    person_key = primary_key_of(session.connection(), "person")
    first, second, third = PLANTED_HOPS

    session.execute(
        text(
            f"CREATE TABLE {first} (id uuid PRIMARY KEY,"
            f' person_id uuid NOT NULL REFERENCES public.person("{person_key}"))'
        )
    )
    session.execute(
        text(
            f"CREATE TABLE {second} (id uuid PRIMARY KEY,"
            f" parent_id uuid NOT NULL REFERENCES public.{first}(id))"
        )
    )
    session.execute(
        text(
            f"CREATE TABLE {third} (id uuid PRIMARY KEY,"
            f" parent_id uuid NOT NULL REFERENCES public.{second}(id),"
            " full_name text NOT NULL)"
        )
    )

    reached = people_tables(session.connection())
    assert first in reached, (
        f"The sweep does not reach `{first}`, which holds a foreign key straight to `person`. "
        "That is the one hop it already walked before this ticket, so something more basic is "
        "wrong than the fixed point this test is about — most likely that the planted table is "
        "invisible to the reflection, in which case everything below proves nothing."
    )

    bearing = identity_bearing_columns(session.connection())
    assert (third, "full_name") in bearing, (
        f"`{third}.full_name` holds a person's name and the sweep never looked at it. It reaches "
        f"`person` in three steps — {third} → {second} → {first} → person — and the walk in "
        f"`people_tables` stopped short of it; it reached {sorted(reached)}. That is either the "
        "one-hop version E0-08 shipped, which tests each table's foreign keys against "
        "`PERSON_TABLES` rather than against the set it is building, or a walk repaired by "
        "hard-coding a second hop — which is why this test plants three links and not two. E0-10 "
        "lands the grants, which is what turns an unswept identity column into an "
        "instructor-visible one: its views and its CI invariant pass are both computed over this "
        "enumeration, so a table outside it is a table they believe holds nothing to protect. "
        "`answer` and `threat_case` are the tables the criterion was written about, both two hops "
        "out, and `threat_case` is §6.2's Care queue."
    )


def test_an_identity_column_named_neither_name_nor_email_is_still_caught(db_session: Any) -> None:
    """Criterion: a plausibly-named identity column, added unmarked, fails the tripwire.

    As E0-08 shipped it, discovery was by the fragments `("name", "email")`. A
    roster sync storing an NRPS or LTI claim as `login_id`, `picture` or
    `lis_person_sourcedid` landed an identity column that the sweep passed
    unmarked and unnoticed — the convention required a human to name a column in a
    way the sweep happened to recognise, which is the property a tripwire is
    supposed to remove.

    **The mechanism is a widened `IDENTITY_NAME_FRAGMENTS`, and the ticket's menu
    of four turned out to be a menu of one.** Dispute E0-10-01 measured the other
    three: a model declaration, a `Column.info` flag and a column comment are all
    ways of *marking* a column, and `database_marked_columns` is **subtracted**
    below — so each of them moves a planted column out of the failing set rather
    than into it, and a type-based marker is invisible because this sweep reads
    names and never types. The criterion's own second sentence settles it: the
    column is "added unmarked", by raw DDL, so it carries no model declaration and
    no type, and only a name-based rule can catch it.

    **The control is the fourth planted column.** `display_name` was caught before
    this ticket widened anything, so it proves the planted table is being swept at
    all — without it, a failure here reads as "the sweep never saw this table",
    which is a different defect with a different fix (`docs/MISTAKES.md` entry 3).

    **Nothing outside `tests/` can change this test's outcome, which is the
    decision rather than the defect** — see the module docstring and dispute
    E0-10-01. It follows that only a mutation of `IDENTITY_NAME_FRAGMENTS` checks
    it: remove `login_id` and this test names it.
    """
    session = db_session
    user_key = primary_key_of(session.connection(), "user")
    planted = ", ".join(
        f"{name} text"
        for name in (RECOGNISED_IDENTITY_COLUMN_NAME, *PLAUSIBLE_IDENTITY_COLUMN_NAMES)
    )
    session.execute(
        text(
            f"CREATE TABLE {PLANTED_ROSTER_TABLE} (id uuid PRIMARY KEY,"
            f' user_id uuid NOT NULL REFERENCES public."user"("{user_key}"), {planted})'
        )
    )

    connection = session.connection()
    unmarked = identity_bearing_columns(connection) - database_marked_columns(connection)

    assert (PLANTED_ROSTER_TABLE, RECOGNISED_IDENTITY_COLUMN_NAME) in unmarked, (
        f"`{PLANTED_ROSTER_TABLE}.{RECOGNISED_IDENTITY_COLUMN_NAME}` is unmarked, contains the "
        "word 'name', and sits on a table with a foreign key straight to `user` — and the sweep "
        "did not report it. The control has failed, so the assertion below would be about a table "
        "nothing is looking at rather than about the column names."
    )

    missed = [
        name
        for name in PLAUSIBLE_IDENTITY_COLUMN_NAMES
        if (PLANTED_ROSTER_TABLE, name) not in unmarked
    ]
    assert not missed, (
        f"{missed} were added to a table that holds a person, with no identity marker, and the "
        "convention passed them. Each is a real LTI or NRPS claim: `login_id` is the SIS login, "
        "`picture` is a portrait URL, `lis_person_sourcedid` is the student number. E0-10 asks "
        "for a convention that catches one — 'a declared list on the model, a type, a "
        "`Column.info` flag carried into the database, or a widened fragment set' — and asks the "
        "pull request to say what the new version cannot see, because every version has a blind "
        "spot and the unstated one is the one that bites. This test does not care which mechanism "
        "is chosen; it cares that an unmarked identity column reaches "
        "`test_every_identity_bearing_column_is_discoverable_through_the_marker`'s failing set."
    )


@pytest.mark.invariant
def test_no_view_reads_a_column_the_identity_marker_names(migrated_engine: Any) -> None:
    """Criterion: the structural test enumerates identity columns and finds none in any view.

    This is the test that makes the guarantee survive a view added three epics
    from now: SPEC §8 requires instructor and leadership read paths to go through
    views that "structurally cannot join to `user` identity columns", and a view
    added later that leaks one has to fail CI without anybody remembering to
    check.

    **Marked `invariant`, because it is the only guard on this door.** A view is
    read with its *owner's* privileges rather than its reader's, so a later
    `CREATE VIEW … SELECT ui.identity_name … JOIN public.user_identity ui`
    followed by `GRANT SELECT ON that view TO pulse_app` puts a name on an
    instructor screen with every grant E0-10 writes still intact — and all three
    of `test_identity_grants.py`'s `invariant`-marked doors stay green while it
    happens, because the direct select is still refused, the join is still
    refused, and the reveal function is still not executable by `pulse_app`.
    `backend/app/views_sql/identity_grants_v001.sql` states that exposure and
    names this test as the answer to it. Unmarked, the answer sat outside the
    isolated pass E0-10 has just made unskippable, where a skipped assertion and
    a passing one are the same green checkmark. The decorator **composes with**
    this module's `pytestmark = pytest.mark.integration` rather than replacing
    it, so the test still runs in the ordinary suite as well.

    Only this test in this module is marked. The others are the marker
    convention's own tripwires — they say what an identity column *is*, which is
    a precondition for §4.1 rather than an instance of it, and
    `test_application_role_privileges.py`'s docstring draws the same line for the
    same reason.

    **The mutation it exists to survive** is that view: add an identity column to
    `section_roster_v001.sql`'s select list, or a join to `user_identity` used
    only in a `WHERE` clause, and this goes red naming the view, the table and
    the column while nothing else in the tree does.

    **It reads the dependency, not the output columns.** Postgres records which
    *columns* of which tables a view's rewrite rule uses, so a view selecting
    `identity_name AS instructor`, or joining on it, or filtering by it, appears
    here — where a sweep over the view's own column names would see a column
    called `instructor` and pass. That is the version somebody writes when a
    screen needs a name.

    Three non-vacuity guards, and the third is the one that is easy to leave out:
    the dependency query has to return *something*, or an empty intersection is
    telling you about the query rather than about the views.
    """
    with migrated_engine.connect() as connection:
        views = sorted(
            {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT c.relname FROM pg_class c JOIN pg_namespace n"
                        " ON n.oid = c.relnamespace"
                        " WHERE n.nspname = 'public' AND c.relkind IN ('v', 'm')"
                    )
                )
            }
        )
        dependencies = connection.execute(text(VIEW_COLUMN_DEPENDENCIES)).all()
        marked_columns = database_marked_columns(migrated_engine)

    assert views, (
        "The migrated database holds no view in `public`, so this sweep looked at nothing and "
        "would report success. E0-10 ships a section-roster view and an enrollment-count view "
        "under `backend/app/views_sql/`; `test_identity_separated_views.py` is where their "
        "absence is diagnosed."
    )
    assert marked_columns, (
        "Nothing in the migrated database carries the identity marker, so the intersection below "
        "is empty whatever the views do. The sweep test at the top of this module is where that "
        "is diagnosed."
    )
    assert dependencies, (
        f"Postgres reports no column-level dependency for any of {views}, which cannot be true of "
        "a view that selects anything at all. The query in `VIEW_COLUMN_DEPENDENCIES` is not "
        "finding what it is meant to find, and the assertion below would pass against a view that "
        "returns every identity column in the schema."
    )

    leaking = sorted(
        f"{view}: {table}.{column}"
        for view, table, column in dependencies
        if (table, column) in marked_columns
    )
    assert not leaking, (
        f"{leaking} — each is a view reading a column the identity marker names. SPEC §8: the "
        "instructor and leadership read paths go through views that 'structurally cannot join to "
        "`user` identity columns — enforced in the database, not just the application', and "
        "§4.1's invariants are asserted against those views. A view that reads one is the whole "
        "confidentiality model reduced to whether the application remembers not to select the "
        "column — and the grant that would otherwise stop it does not apply, because a view runs "
        "with its owner's privileges rather than its reader's. If a column in this list is "
        "genuinely not identity, the fix is at the marker rather than here."
    )
