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

**The `invariant`-marked tests here are the ones about what a view may read**, and
they are at the foot of the file. Three are E0-10's and E0-34's:
`test_no_view_reads_a_column_the_identity_marker_names`,
`test_no_view_reads_a_whole_row_of_a_table_the_identity_marker_names`, and the
self-test that keeps the two of them apart. A view is read with its owner's
privileges, so it is the one route to identity that E0-10's grants do not close,
and this file holds the guard on it as the *database* reports it — at both of the
grains Postgres records, because it records a column read and a whole-row read
differently and the first version of this file only asked about one. Four more
are E1-01's, in the section below those: the strict rule over the person tables
and its three planted controls. Their docstrings carry the reasoning;
`scripts/ci/check_invariants.py` is what makes the mark mean something, by
treating a skip, an xfail or an empty collection in that pass as a failure. Do
not count them from this paragraph — `pytest -m invariant --collect-only` is the
only currency that sees both marking forms (`docs/MISTAKES.md` entry 35).

**E1-01 adds a rule phrased over the *table* rather than over the marker**, and it
is here for the same reason everything else in this file is: the vocabulary is
defined here, so widening it widens every reader at once. The marker says what a
column holds, which cannot answer for `user` — ADR 0001 puts the key and the
platform reference there precisely so they are not identity, so `user` carries no
marked column and `user.lms_user_id` is read by a view with every guard above
green. `JOIN_KEY_COLUMNS` below is the closed list of columns a view may read
from a table that holds a person, and `person_table_reads_including_chains`
follows a view built on a view, which the one-hop dependency query cannot.

**It is no longer the only guard on that door, and the other half is E0-34's.**
This one reads `pg_depend`, so it sees only views a migration has executed — a
`.sql` file under `backend/app/views_sql/` that joins `user_identity` and selects
a name passes it *vacuously* until a revision names that file.
`test_no_view_created_under_views_sql_names_an_identity_column` in
`test_identity_separated_views.py` reads those files as text and is the guard on
that state; it borrows this module's vocabulary rather than restating it, so
widening the convention here widens it there too. Neither subsumes the other:
this one sees through an alias and through a `WHERE` clause because Postgres
recorded the column dependency, and that one sees a file nothing has run.

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

# The columns a view may read from one of those tables, and the whole of the list.
# This is E1-01's strict rule: a view may name **no** column of `user`,
# `user_identity` or `person` except one of these three — whatever the column is
# called, and whether or not it carries a marker.
#
# **Why an allow-list of keys rather than a longer list of forbidden names.**
# E1-01's carried entry ("The §4.1 view sweep is blind to an aliased identity
# column and to join keys", `docs/tickets/e1/carried-from-e0.md`) measured two
# blind spots and rules the obvious repair out in as many words: the fix is
# "lineage and enumeration, not a longer fragment list". `IDENTITY_NAME_FRAGMENTS`
# above is a judgement about *names*, and the view's author picks the name — the
# reviewer's fixture selects `ui.display_name AS respondent_display_name` and
# matches no fragment. A rule phrased over the columns that may be read does not
# depend on the name at all: that column is refused because it is not `id`,
# `user_id` or `lti_platform_id`, and it would be refused if it were called `x`.
#
# **`lms_user_id` is deliberately absent, and it is the second blind spot.** It is
# the LTI `sub`, a stable per-person key at the platform, and
# [ADR 0014](../../docs/adr/0014-lms-owned-columns-are-marked-by-a-name-prefix.md)'s
# `lms_` prefix marks *ownership* rather than identity — so no rule in this module
# sees it and none was ever meant to. The carried entry: "a view returning it
# beside a comment lets an instructor resolve a named student in the LMS in one
# step, with every §4.1 guard green."
#
# **What the three buy.** A read view has to be able to join. The carried entry
# on the reveal's composition says what `section_roster` is for — it "hands
# instructor-scoped code the `user_id` of every enrolled student… the key is what
# makes a de-identified response addressable" — and `id` is what such a key is
# joined to. `lti_platform_id` is the platform reference ADR 0001 puts on `user`
# beside the key. Each of the three names a *row*; none of them names a person.
#
# The list is kept from growing into a schema by
# `test_every_join_key_the_bound_column_mechanism_allows_is_a_structural_key` in
# `test_identity_separated_views.py`, which requires each entry to be a primary
# key or a foreign key on one of the tables above: a name added here that is
# neither — `lms_user_id` is neither — turns that test red.
JOIN_KEY_COLUMNS = ("id", "user_id", "lti_platform_id")

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

# The same dependency, at **whole-row** grain — `refobjsubid = 0`, which is how
# Postgres records a reference to a table's row as a value rather than to any of
# its columns. This is a second question and not a relaxation of the `> 0` above,
# and it exists because of what that filter hides. Measured against the live
# database during E0-34's review:
#
#   SELECT to_jsonb(ui) FROM public.user_identity ui   ->  [(0, whole row)]
#   SELECT ui           FROM public.user_identity ui   ->  [(0, whole row)]
#   SELECT *            FROM public.user_identity      ->  [(1,id) … (4,identity_email)]
#   SELECT ui.identity_name FROM public.user_identity ui -> [(3, identity_name)]
#
# **The two grains are disjoint on this stack, and that is measured rather than
# assumed** — the four rows above are the whole of it: no column read records a
# whole-row dependency, and no whole-row read records a column one. That is what
# makes the two invariants below genuinely two rather than one subsuming the
# other, and `test_a_whole_row_view_reference_is_recorded_at_table_grain` asserts
# it in both directions so that a future Postgres changing its mind about
# dependency recording is a red rather than a silent overlap.
#
# So the two whole-row spellings record **no column dependency at all**, and the
# sweep above — `invariant`-marked, and the only guard on this door until now —
# returns nothing for a view carrying every student's name and email address.
# `row_to_json(ui)`, `hstore(ui)` and `TABLE public.user_identity` are the same
# shape; the file-side guard in `test_identity_separated_views.py` was blind to
# them too, and both halves were repaired in one round because one finding
# defeated both.
#
# Column names are deliberately absent from this query: at this grain there are
# none to report, and the assertion names the columns the *table* carries, which
# is what a whole-row reference reads.
VIEW_TABLE_DEPENDENCIES = """
    SELECT DISTINCT v.relname AS view_name, c.relname AS table_name
    FROM pg_depend d
    JOIN pg_rewrite rw ON rw.oid = d.objid AND d.classid = 'pg_rewrite'::regclass
    JOIN pg_class v ON v.oid = rw.ev_class
    JOIN pg_namespace vn ON vn.oid = v.relnamespace
    JOIN pg_class c ON c.oid = d.refobjid AND d.refclassid = 'pg_class'::regclass
    JOIN pg_namespace cn ON cn.oid = c.relnamespace
    WHERE v.relkind IN ('v', 'm')
      AND vn.nspname = 'public'
      AND cn.nspname = 'public'
      AND d.refobjsubid = 0
      AND c.oid <> v.oid
    ORDER BY 1, 2
"""

# The objects the whole-row self-test plants and rolls back. Named for the ticket
# so that one surviving a fixture change is traceable to it.
PLANTED_IDENTITY_TABLE = "e0_34_planted_identity_table"
PLANTED_WHOLE_ROW_VIEW = "e0_34_planted_whole_row_view"
PLANTED_COLUMN_VIEW = "e0_34_planted_column_view"

# The objects E1-01's three controls plant, and the column they add to a real
# person table. Named for the ticket, like the two sets above, so that one
# surviving a fixture change is traceable to the test that made it.
#
# `display_name` is the reviewer fixture's own column name
# (`.claude/review-fixtures/identity-column-in-view.diff`), and it is not in this
# schema — which is the point of the control rather than an accident of it. The
# strict rule has to fire on a column the identity vocabulary cannot know about,
# so the control adds one and then reads it under an alias.
PLANTED_ALIAS_TABLE = "user_identity"
PLANTED_ALIAS_COLUMN = "display_name"

# The other half of the fixture's select list, and the carried entry's second
# finding: `user.lms_user_id` is the LTI `sub`, a stable per-person key at the
# platform that no rule in this module saw before E1-01. Spelled here rather than
# discovered, because the control's job is to stand up that exact disclosure.
#
# `test_identity_grants.py` carries the same two names for its own control, and
# they are copies for the reason `IDENTITY_NAME_FRAGMENTS` above is copied three
# times: a test module importing a sibling test module resolves only because of
# where pytest puts `tests/` on `sys.path`. Change one, change both.
USER_TABLE = "user"
LMS_USER_KEY = "lms_user_id"
PLANTED_ALIAS_VIEW = "e1_01_planted_alias_view"
PLANTED_CHAIN_SOURCE_VIEW = "e1_01_planted_chain_source_view"
PLANTED_CHAIN_READER_VIEW = "e1_01_planted_chain_reader_view"
PLANTED_JOIN_KEY_VIEW = "e1_01_planted_join_key_view"
PLANTED_ROSTER_SHAPE_VIEW = "e1_01_planted_roster_shape_view"
PLANTED_OFFENDING_VIEW = "e1_01_planted_offending_view"

# The table the roster-shaped control reads, and the column it reads from it.
# SPEC §8 names `enrollment` in the core table list, and the carried entry on the
# reveal's composition names this exact read: `section_roster` "hands
# instructor-scoped code the `user_id` of every enrolled student". A view of that
# shape must stay silent, or the strict rule would forbid the read path §4.1
# depends on.
ENROLLMENT_TABLE = "enrollment"
ENROLLMENT_KEY_COLUMN = "user_id"

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


def public_views(connection: Any) -> list[str]:
    """Every view and materialised view in `public`, by name."""
    return sorted(
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


def column_grained_identity_reads(connection: Any) -> list[str]:
    """Every `view: table.column` where a view reads a column the marker names.

    Extracted from the test below so that the self-test can run the same
    computation over planted objects rather than a copy of it — and, more to the
    point, so that it can assert what this reading does **not** see. A whole-row
    reference records no column dependency at all, and that fact is now an
    assertion rather than a measurement in a review comment.
    """
    marked_columns = database_marked_columns(connection)
    return sorted(
        f"{view}: {table}.{column}"
        for view, table, column in connection.execute(text(VIEW_COLUMN_DEPENDENCIES))
        if (table, column) in marked_columns
    )


def whole_row_identity_reads(connection: Any) -> list[str]:
    """Every `view: table` where a view depends on the whole row of a marked table.

    The other grain, and a different question from the one above rather than a
    looser version of it. `refobjsubid = 0` is a reference to the row as a value —
    `to_jsonb(ui)`, `row_to_json(ui)`, a bare `SELECT ui`, `TABLE public.x` — and
    it reads every column the table has, including the ones the marker names,
    while recording no column dependency for any of them.

    The table is required to carry a marked column, not to *be* an identity table
    by name: the marker is the enumeration this module exists to maintain, and a
    table that carries one is a table whose whole row carries one.
    """
    tables = {table for table, _ in database_marked_columns(connection)}
    return sorted(
        f"{view}: {table}"
        for view, table in connection.execute(text(VIEW_TABLE_DEPENDENCIES))
        if table in tables
    )


@pytest.mark.invariant
def test_no_view_reads_a_whole_row_of_a_table_the_identity_marker_names(
    migrated_engine: Any,
) -> None:
    """The grain the column sweep cannot see: the row as a value.

    Found by review on E0-34 and measured against the live database. A view
    written `SELECT to_jsonb(ui) FROM public.user_identity ui` carries every
    student's name and email address, and Postgres records its dependency at
    `refobjsubid = 0` — so
    `test_no_view_reads_a_column_the_identity_marker_names`, which filters
    `refobjsubid > 0`, returns nothing for it. The file-side guard in
    `test_identity_separated_views.py` was blind to it as well: no column name is
    written and there is no `*`. Both halves of the §4.1 pair were green on a view
    that reads the whole identity table, which is why one review finding repaired
    two files.

    **Why this is a second assertion rather than a relaxed `> 0`.** The two
    dependency grains answer different questions and their failure messages want
    to say different things: one names the column that leaked, and at this grain
    there is no column to name — what leaked is every column the table has, and
    the message lists them. Relaxing the filter would also fold "reads the row"
    into "reads a column" for a reader trying to work out what to fix.

    **What it necessarily also catches**, said plainly because it is the cost: a
    view that names a marked table and reads *no* column of it records the same
    whole-table dependency. No view in this schema does that today. If one is ever
    wanted, this test is where the decision gets recorded, and the pull request
    owes the reason a read path names an identity table at all (SPEC §8 asks for
    views that structurally cannot join to identity).

    **The mutation it exists to survive**: any of the four spellings — `to_jsonb`,
    `row_to_json`, a bare row reference, `TABLE public.user_identity` — added to a
    view in the migrated database. **The near miss it tolerates**: a view reading a
    named column of a marked table, which is the test above's subject and records
    no dependency at this grain; and a view reading the whole row of a table that
    carries no marked column, which is most of the schema.
    """
    with migrated_engine.connect() as connection:
        views = public_views(connection)
        marked_columns = database_marked_columns(connection)
        leaking = whole_row_identity_reads(connection)

    assert views, (
        "The migrated database holds no view in `public`, so this sweep looked at nothing and "
        "would report success. `test_identity_separated_views.py` is where their absence is "
        "diagnosed."
    )
    assert marked_columns, (
        "Nothing in the migrated database carries the identity marker, so no table qualifies as "
        "identity-bearing and this sweep has nothing to look for. The sweep test at the top of "
        "this module is where that is diagnosed."
    )

    # **There is deliberately no "the query returned something" guard here**, and
    # that is the difference between this test and its column-grained sibling. On
    # a healthy schema this query returns *nothing at all*: a view that reads named
    # columns records column dependencies and no whole-table one, so an empty
    # result is the correct state rather than a sweep that has gone blind.
    # Requiring a row would have been a red on the day this landed, for a reason
    # having nothing to do with any view.
    #
    # The liveness this test needs is therefore proved somewhere a subject exists:
    # `test_a_whole_row_view_reference_is_recorded_at_table_grain` plants a view
    # that takes `to_jsonb` of a marked table and requires this same computation to
    # report it. That is `docs/MISTAKES.md` entry 3's rule met by a plant rather
    # than by an assumption about the schema — and entry 35's, which asks that a
    # mechanism be *found* on a subject that certainly has it rather than trusted
    # because it reports nothing.

    carried = {
        table: sorted(column for owner, column in marked_columns if owner == table)
        for table in {table for table, _ in marked_columns}
    }
    # The suppression below is on a *message*, not on a statement, and it is here
    # rather than avoided by rewording: the message quotes the exact query that was
    # measured, and quoting it is the whole value of the message to whoever reads
    # the red. Ruff sees an interpolated string containing `SELECT … FROM …` and
    # cannot tell prose about a query from a query. Nothing here reaches a cursor.
    #
    # **The `noqa` goes on the first fragment**, which is where ruff reports the
    # diagnostic for an implicitly concatenated message — not on the last, which is
    # where a multi-line *triple-quoted* string wants it. Getting that backwards
    # costs two errors rather than none: the `S608` stays unsuppressed and a
    # `RUF100` appears for the unused directive.
    assert not leaking, (
        f"{leaking} — each is a view depending on the whole row of a table the identity marker "  # noqa: S608
        f"names. Those tables carry {carried}, and a whole-row reference reads all of it.\n\n"
        "This is the shape that records **no column dependency at all**, so "
        "`test_no_view_reads_a_column_the_identity_marker_names` is green against it: "
        "`SELECT to_jsonb(ui) FROM public.user_identity ui` was measured returning "
        "`[(0, whole row)]` and no marked-column dependency whatever. A view is read with its "
        "owner's privileges rather than its reader's, so every grant ADR 0001 writes is still "
        "intact while the name is on the screen.\n\n"
        "If the view names the table without reading any column of it, that is the same "
        "dependency and this test cannot tell the two apart — the fix is still to stop naming it, "
        "and if it genuinely must, that is a decision to record here rather than a filter to "
        "widen."
    )


@pytest.mark.invariant
def test_a_whole_row_view_reference_is_recorded_at_table_grain(db_session: Any) -> None:
    """Both dependency grains, run against subjects that certainly have them.

    The two invariants above divide the space between them — one reads columns,
    one reads rows — and that division is a claim about what Postgres records.
    `docs/MISTAKES.md` entry 3's rule for a claim like that is to execute it
    against the thing it must catch *and* the thing it must allow, which is what
    this does: a table with a marked column, a view over it that takes the whole
    row, and a view over it that reads one column.

    Four assertions, and the third and fourth are the finding itself. The
    whole-row view must appear at table grain and must **not** appear at column
    grain; the column view must appear at column grain and must **not** appear at
    table grain. Without the two negatives, either invariant could be quietly
    replaced by the other on the belief that one subsumes it — and the whole
    reason this pair exists is that neither does.

    **All four were measured against the pinned image before this landed**, on a
    view reading a named column, a `SELECT *`, a `to_jsonb(ui)` and a bare
    `SELECT ui`: the column read reported only column dependencies, the whole-row
    reads reported only `(0, whole row)`, and neither reported the other's. So the
    two grains are disjoint here as a fact rather than as a design intention, and
    this test is what turns that fact into something that has to stay true.

    **If the fourth assertion fails**, the table-grained invariant is the wrong
    shape rather than the schema being wrong: it would mean Postgres has begun
    recording a whole-table dependency for an ordinary column read, and the
    invariant above would then flag every view that touches a marked table.
    Narrow it in that case and say so; do not delete it, because the first
    assertion is the leak.

    Everything here is planted inside `db_session`'s transaction and rolled back
    with it — Postgres puts DDL inside the transaction — so `public` is unchanged
    at the end. The marker is a column comment, which is one of the three shapes
    `marked` accepts, so the planted table qualifies as identity-bearing by the
    module's own convention rather than by anything this test asserts about it.
    """
    session = db_session
    session.execute(
        text(
            f"CREATE TABLE {PLANTED_IDENTITY_TABLE} "
            "(id uuid PRIMARY KEY, identity_name text NOT NULL)"
        )
    )
    session.execute(
        text(
            f"COMMENT ON COLUMN {PLANTED_IDENTITY_TABLE}.identity_name IS "
            f"'{MARKER_TOKEN}: planted by the E0-34 self-test'"
        )
    )
    # The two subjects, each on one line with its own suppression, which is the
    # shape this repository already uses for a statement built by interpolation
    # (`test_identity_grants.py`'s `READ_IDENTITY`, and the sweep samples in
    # `test_identity_separated_views.py`). Ruff reads them as SQL built from a
    # variable, which is what S608 is for; every name interpolated here is one of
    # the `PLANTED_*` module constants declared beside `VIEW_TABLE_DEPENDENCIES`,
    # nothing reaches these from outside the file, and the statements run inside
    # `db_session`'s transaction and are rolled back with it.
    # Per line rather than per file, so that a statement which ever does take an
    # argument from anywhere else is flagged again.
    whole_row_view = f"CREATE VIEW {PLANTED_WHOLE_ROW_VIEW} AS SELECT to_jsonb(planted) AS whole FROM public.{PLANTED_IDENTITY_TABLE} planted"  # noqa: S608
    column_view = f"CREATE VIEW {PLANTED_COLUMN_VIEW} AS SELECT planted.identity_name FROM public.{PLANTED_IDENTITY_TABLE} planted"  # noqa: S608
    session.execute(text(whole_row_view))
    session.execute(text(column_view))

    connection = session.connection()
    assert (PLANTED_IDENTITY_TABLE, "identity_name") in database_marked_columns(connection), (
        f"The planted `{PLANTED_IDENTITY_TABLE}.identity_name` does not read as marked, so neither "
        "sweep below regards it as identity-bearing and every assertion in this test is about a "
        "table nothing is looking at. The marker convention is what changed, not the dependency "
        "grain: `marked` accepts a column comment carrying the token, and this test writes one."
    )

    at_table_grain = whole_row_identity_reads(connection)
    at_column_grain = column_grained_identity_reads(connection)

    assert any(entry.startswith(f"{PLANTED_WHOLE_ROW_VIEW}:") for entry in at_table_grain), (
        f"`{PLANTED_WHOLE_ROW_VIEW}` takes `to_jsonb` of every row of a table carrying a marked "
        f"column, and the whole-row sweep does not report it; it reported {at_table_grain}. "
        "`test_no_view_reads_a_whole_row_of_a_table_the_identity_marker_names` asserts an absence "
        "and would be green over a schema full of these."
    )
    assert not any(entry.startswith(f"{PLANTED_WHOLE_ROW_VIEW}:") for entry in at_column_grain), (
        f"`{PLANTED_WHOLE_ROW_VIEW}` is reported by the *column*-grained sweep, which reported "
        f"{at_column_grain}. That would be good news and it contradicts what was measured on this "
        "database during E0-34's review — a whole-row reference recorded `[(0, whole row)]` and no "
        "column dependency at all. If Postgres now records both, this pair of invariants overlaps "
        "where it was designed not to, and that is worth knowing before anybody decides one of "
        "them is redundant."
    )
    assert any(entry.startswith(f"{PLANTED_COLUMN_VIEW}:") for entry in at_column_grain), (
        f"`{PLANTED_COLUMN_VIEW}` selects a marked column by name and the column-grained sweep "
        f"does not report it; it reported {at_column_grain}. That sweep is the older of the two "
        "invariants and the one E0-10 shipped, so this is the more serious of the two directions: "
        "with it blind, a view selecting `identity_name` outright passes."
    )
    assert not any(entry.startswith(f"{PLANTED_COLUMN_VIEW}:") for entry in at_table_grain), (
        f"`{PLANTED_COLUMN_VIEW}` reads one named column and the *whole-row* sweep reports it "
        f"anyway; it reported {at_table_grain}. Then `refobjsubid = 0` is not the whole-row grain "
        "it is being used as — Postgres is recording a table-level dependency for an ordinary "
        "column read — and "
        "`test_no_view_reads_a_whole_row_of_a_table_the_identity_marker_names` will flag every "
        "view that touches a marked table, including ones that read nothing from it. Narrow that "
        "test rather than deleting it: the whole-row read it was written for is a real leak that "
        "nothing else in this suite sees."
    )


@pytest.mark.invariant
def test_no_view_reads_a_column_the_identity_marker_names(migrated_engine: Any) -> None:
    """Criterion: the structural test enumerates identity columns and finds none in any view.

    This is the test that makes the guarantee survive a view added three epics
    from now: SPEC §8 requires instructor and leadership read paths to go through
    views that "structurally cannot join to `user` identity columns", and a view
    added later that leaks one has to fail CI without anybody remembering to
    check.

    **Marked `invariant`, because it is the guard on this door as the database
    reports it** — E0-34 adds the file-side twin,
    `test_no_view_created_under_views_sql_names_an_identity_column`, which reads
    the `views_sql/` sources as text and so catches the same join in a file no
    revision names yet. That one cannot see a column whose name it has no reason
    to know, nor a chain of views; this one cannot see a file nothing has
    executed. **E1-01 narrowed the first of those from both sides** — the text
    sweep gained a mechanism that reads what an alias is *bound to* rather than
    what a column is called, and this module gained the strict rule below, which
    reads the table rather than the marker and folds a chain of views to a fixed
    point. Neither closes the other's gap: text still cannot see a name that is
    never written, and the catalog still cannot see a file nothing has run. A view
    is
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

    The marked tests in this module are this one, its whole-row twin above, the
    self-test that separates them, and E1-01's strict rule with its three
    controls at the foot of the file. The others are the marker convention's own
    tripwires — they say what an identity column *is*, which is a precondition for
    §4.1 rather than an instance of it, and
    `test_application_role_privileges.py`'s docstring draws the same line for the
    same reason.

    **The mutation it exists to survive** is that view: add an identity column to
    `section_roster_v001.sql`'s select list, or a join to `user_identity` used
    only in a `WHERE` clause, and this goes red naming the view, the table and
    the column. Since E0-34 the file-side twin goes red on the same edit, which
    is the point of having both — but only this one sees it when the column
    reaches the view under an alias, and only that one sees it before any
    revision has run the file.

    **It reads the dependency, not the output columns.** Postgres records which
    *columns* of which tables a view's rewrite rule uses, so a view selecting
    `identity_name AS instructor`, or joining on it, or filtering by it, appears
    here — where a sweep over the view's own column names would see a column
    called `instructor` and pass. That is the version somebody writes when a
    screen needs a name.

    **And it reads only that grain**, which is the correction E0-34's review
    made. A reference to the *row* — `to_jsonb(ui)`, `SELECT ui`,
    `TABLE public.user_identity` — is recorded at `refobjsubid = 0` and carries no
    column dependency at all, so the `> 0` filter below hides it completely.
    `test_no_view_reads_a_whole_row_of_a_table_the_identity_marker_names` is that
    grain, and the two together are what "no view reads identity" now means here.

    Three non-vacuity guards, and the third is the one that is easy to leave out:
    the dependency query has to return *something*, or an empty intersection is
    telling you about the query rather than about the views.
    """
    with migrated_engine.connect() as connection:
        views = public_views(connection)
        dependencies = connection.execute(text(VIEW_COLUMN_DEPENDENCIES)).all()
        marked_columns = database_marked_columns(migrated_engine)
        leaking = column_grained_identity_reads(connection)

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


# ---------------------------------------------------------------------------
# E1-01 — the two things the marked-column sweep above cannot see, closed here
# rather than in a module of their own for the reason this file's E0-10 section
# gives: the vocabulary is defined here, so the rule that widens it belongs here
# (`docs/MISTAKES.md` entry 13).
#
# The two are the carried entry's, and neither is a defect in the sweep above —
# each is a question it was never asked:
#
#   - **the marker is not the boundary.** `test_no_view_reads_a_column_the_
#     identity_marker_names` filters `(table, column) in marked_columns`, so a
#     column on `user_identity` that carries no marker is invisible to it, and
#     `user` carries no marked column at all by construction (ADR 0001 splits the
#     key from the identity, and `marked` above refuses a table comment on
#     `user` on that ground). `user.lms_user_id` is therefore read by a view with
#     every guard in this file green;
#   - **a chain of views records its dependency one hop out.** `VIEW_COLUMN_
#     DEPENDENCIES` is one hop by construction: a view B built on a view A
#     records a dependency on *A's* columns, and A's columns carry no marker, so
#     B reads a name through A and appears here reading nothing. The gap is
#     recorded at `test_identity_separated_views.py`'s `identity_findings`, which
#     names the mirror case its own text sweep cannot see.
# ---------------------------------------------------------------------------


def person_table_column_reads(connection: Any) -> dict[str, set[str]]:
    """Every view, and the person-table columns it reads that are not join keys.

    One hop, straight off `VIEW_COLUMN_DEPENDENCIES` — the same query the sweep
    for a marked column uses, filtered differently. That one asks whether the
    column is *marked*; this asks whether the table is one a person is stored in
    and the column is not one of the keys a view may join on. They overlap on
    `user_identity.identity_name` and diverge in both directions: an unmarked
    column on a person table is here and not there, and a marked column on a
    table outside `PERSON_TABLES` — a planted one, or E10's case model — is there
    and not here.

    Each finding is spelled `table.column`, which is what the failure message
    quotes: naming the source column is E1-01's first criterion, and the same
    file already fails other sweeps with messages about other things.
    """
    found: dict[str, set[str]] = {}
    for view, table, column in connection.execute(text(VIEW_COLUMN_DEPENDENCIES)):
        if table in PERSON_TABLES and column not in JOIN_KEY_COLUMNS:
            found.setdefault(view, set()).add(f"{table}.{column}")
    return found


def view_dependency_edges(connection: Any) -> dict[str, set[str]]:
    """Every view, and the views it reads a column of — one hop.

    Read out of the same dependency query rather than a second one: `pg_class` is
    not filtered by `relkind` on the *referenced* side there, so a view built on
    a view is already reported, with the intermediate view in the `table_name`
    column. That is the whole of what makes the fold below possible without new
    SQL.
    """
    views = set(public_views(connection))
    edges: dict[str, set[str]] = {}
    for view, table, _ in connection.execute(text(VIEW_COLUMN_DEPENDENCIES)):
        if table in views:
            edges.setdefault(view, set()).add(table)
    return edges


def person_table_reads_including_chains(connection: Any) -> dict[str, set[tuple[str, str]]]:
    """Every view, and every person-table column it reads directly or through another view.

    Each finding is `(source, path)`: the base column — `user_identity.identity_name`
    — and the chain of views it arrived through, the reading view first. So a
    failure message names what leaked *and* where to look, which a set of view
    names alone cannot.

    **It is deliberately coarse, and the coarseness is the decision rather than a
    limitation to be repaired later.** A view B that reads any column of a view A
    inherits *all* of A's findings, including when B reads only the columns of A
    that carry nothing. Postgres records which of A's columns B depends on, so a
    column-precise lineage is possible; it is not built, because the failure
    direction of the coarse version is the safe one — B is named, a human reads
    two view definitions, and the answer is either a real leak or a `_v002.sql`
    that stops selecting from a view it does not need. The precise version fails
    the other way the first time a rename or an expression makes the mapping
    ambiguous.

    **The fold is bounded rather than run to exhaustion.** Postgres cannot hold a
    cycle among views — a view must exist before it can be referenced, and
    `CREATE OR REPLACE VIEW` refuses one that would introduce it — so the longest
    chain is shorter than the number of views that read another view, and the
    loop stops when nothing grew. The bound is there so that a future catalog
    which *did* report a cycle is a slow test rather than a hung one.
    """
    direct = person_table_column_reads(connection)
    edges = view_dependency_edges(connection)

    found: dict[str, set[tuple[str, str]]] = {
        view: {(source, view) for source in sources} for view, sources in direct.items()
    }
    for _ in range(len(edges) + 1):
        grew = False
        for reader, upstream in edges.items():
            inherited = {
                (source, f"{reader} <- {path}")
                for view in upstream
                for source, path in found.get(view, set())
            }
            if not inherited <= found.get(reader, set()):
                found.setdefault(reader, set()).update(inherited)
                grew = True
        if not grew:
            break
    return found


def person_table_reads_reported(connection: Any) -> list[str]:
    """The findings above as one sorted list of sentences, which is what a message prints."""
    return sorted(
        f"{view} reads {source} (through {path})"
        for view, findings in person_table_reads_including_chains(connection).items()
        for source, path in findings
    )


@pytest.mark.invariant
def test_no_view_reads_a_column_of_a_person_table_outside_the_join_keys(
    migrated_engine: Any,
) -> None:
    """E1-01: the strict rule — a view may read a person table's keys and nothing else.

    The two invariants above are phrased over the *marker*, which says what a
    column holds. This one is phrased over the *table*, which says what a row is:
    the tables `PERSON_TABLES` names hold a person by construction, so a view that
    reads a column of one of them is reading something about a named human unless
    the column is one of the keys `JOIN_KEY_COLUMNS` allows.

    **Why the marker cannot carry this rule.** ADR 0001 puts the key and the
    platform reference on `user` and identity on `user_identity`, and `marked`
    above refuses a table comment on `user` on exactly that ground — so `user`
    carries no marked column, and `test_no_view_reads_a_column_the_identity_
    marker_names` is silent about every column it has. `user.lms_user_id` is the
    LTI `sub`: a stable per-person key at the platform, matching no identity
    fragment, marked by nothing, and enough to resolve a named student in the LMS
    in one step. The carried entry measured that and this test is its "done when".

    **And why it reaches through a chain.** `VIEW_COLUMN_DEPENDENCIES` is one hop:
    a view built on another view records its dependency against the intermediate
    view's columns, which carry no marker and belong to no person table, so the
    filter above returns nothing for it. `person_table_reads_including_chains`
    folds those hops to a fixed point and carries the base column forward, so the
    failure names `user_identity.identity_name` and the path it travelled rather
    than the intermediate view's invented column name.

    **Marked `invariant` for the reason both of its neighbours are**: a view runs
    with its owner's privileges rather than its reader's, so this is a route to
    identity that no arrangement of ADR 0001's grants closes, and in a green
    checkmark a skipped assertion and a passing one look the same.

    **The mutation it exists to survive**: a view selecting `u.lms_user_id`, and
    a view selecting `ui.<anything unmarked>` on a person table — neither of
    which any other test in this repository mentions — and either of those read
    through a second view that renames the column.
    **The near miss it tolerates**: a view joining a person table and reading only
    the keys `JOIN_KEY_COLUMNS` names, which is how a roster view is built and
    what makes a de-identified response addressable at all.

    Three non-vacuity guards, and the third is the one that is easy to leave out:
    the dependency query has to return something, or an empty finding set is
    telling you about the query rather than about the views.
    """
    with migrated_engine.connect() as connection:
        views = public_views(connection)
        present = sorted(inspect(connection).get_table_names())
        dependencies = connection.execute(text(VIEW_COLUMN_DEPENDENCIES)).all()
        reported = person_table_reads_reported(connection)

    assert views, (
        "The migrated database holds no view in `public`, so this sweep looked at nothing and "
        "would report success. `test_identity_separated_views.py` is where their absence is "
        "diagnosed."
    )
    absent = [name for name in PERSON_TABLES if name not in present]
    assert not absent, (
        f"The migrated database has no {absent} table, so this rule is scoped to fewer tables than "
        f"it names and would pass over a view reading every column of the missing one. It holds "
        f"{present}."
    )
    assert dependencies, (
        f"Postgres reports no column-level dependency for any of {views}, which cannot be true of "
        "a view that selects anything at all. `VIEW_COLUMN_DEPENDENCIES` is not finding what it is "
        "meant to find, and the assertion below would pass against a view that returns every "
        "column of `user_identity`."
    )

    assert not reported, (
        f"{reported}. Each is a view reading a column of one of {list(PERSON_TABLES)} — the tables "
        f"that hold a person — that is not one of the join keys {list(JOIN_KEY_COLUMNS)}.\n\n"
        "SPEC §8 requires the instructor and leadership read paths to go through views that "
        "'structurally cannot join to `user` identity columns — enforced in the database, not just "
        "the application', and §4.1 makes the resulting rules automated assertions. This is the "
        "half of that neither marker-based invariant above can state: the marker says what a "
        "column *holds*, and these tables say what a row *is*. `user` carries no marked column by "
        "construction (ADR 0001's split, and `marked` above refuses a table comment on it), so "
        "every column it has — `lms_user_id`, the LTI `sub` — is invisible to the marked-column "
        "sweep and is a stable per-person key at the platform.\n\n"
        "**A finding whose path names more than one view is a chain**, and the column named is the "
        "one at the *base* of it: the view listed first reads a later one, which reads the person "
        "table. The intermediate view's column may be called anything at all, which is why the "
        "one-hop dependency query returns nothing for the reader and why this fold exists. The "
        "inheritance is deliberately coarse — the reader is named even if it selects only the "
        "intermediate view's harmless columns — and `person_table_reads_including_chains` says "
        "why that direction was chosen.\n\n"
        "If the column named is genuinely a join key that a read path needs, it is added to "
        "`JOIN_KEY_COLUMNS` above with the sentence that sanctions it, in a pull request that says "
        "which reads that opens — and never `lms_user_id`, which is the whole of what the carried "
        "entry measured."
    )


@pytest.mark.invariant
def test_a_view_that_aliases_an_unmarked_person_table_column_is_flagged(db_session: Any) -> None:
    """E1-01 criterion 1, on the catalog side: caught by lineage, not by the label.

    The planted view is the reviewer's fixture
    (`.claude/review-fixtures/identity-column-in-view.diff`), and its four
    load-bearing lines are copied rather than retyped — `docs/MISTAKES.md` entry
    3's canary rule, which is about a sentence retyped from where you think it
    begins:

        ui.display_name     AS respondent_display_name,
        u.lms_user_id
        JOIN user_identity ui ON ui.user_id = u.id

    So both of the carried entry's findings are in one planted view, which is how
    the fixture writes them. **The `FROM` is adapted and nothing else is**: the
    fixture reads `FROM response r` and joins `"user" u` to it, and `response`
    arrives with the survey tables in E2, so the view selects from `"user"`
    directly. Neither identity read changes with it.

    **Three assertions are what make this a test of the strict rule and not of
    the marker**, and each is a measurement rather than reasoning:

      - the planted column carries **no marker** in any of the three shapes
        `marked` accepts, so the enumeration this module maintains does not
        contain it;
      - neither does `user.lms_user_id`, which is ADR 0001's split holding: the
        LMS key is on `user` precisely because it is not identity;
      - `column_grained_identity_reads` — the older `invariant`-marked sweep's
        own computation — reports **nothing** for the planted view. That sweep is
        green on this file. If it ever stops being green on it, the marker has
        grown to cover the planted column and this control is measuring the wrong
        thing.

    Everything is planted inside `db_session`'s transaction and rolled back with
    it, Postgres putting DDL inside the transaction, so `public` is unchanged at
    the end and no other connection ever sees the column. The assertions run in
    the same transaction as the plant, which is the point: a mutation a fixture
    undoes before the assertion is a control that cannot fail
    (`docs/MISTAKES.md` entry 20).

    **The mutation it exists to survive**: reverting `person_table_column_reads`
    to the marked-columns filter its neighbour uses, which is the state this
    ticket found the sweep in.
    **The near miss it tolerates**: the same view reading `ui.user_id`, which is
    the allow side and is `test_a_view_that_reads_only_join_keys_of_a_person_
    table_is_not_flagged`.
    """
    session = db_session
    assert PLANTED_ALIAS_TABLE in PERSON_TABLES and USER_TABLE in PERSON_TABLES, (
        f"`{PLANTED_ALIAS_TABLE}` and `{USER_TABLE}` are not both in the person tables "
        f"{list(PERSON_TABLES)}, so one of the two reads planted below is not on a table this rule "
        "guards and the flag asserted at the end would be about something else entirely."
    )
    on_user = {column["name"] for column in inspect(session.connection()).get_columns(USER_TABLE)}
    assert LMS_USER_KEY in on_user, (
        f"`public.{USER_TABLE}` has no `{LMS_USER_KEY}` column; it has {sorted(on_user)}. ADR 0001 "
        "puts the LMS key and the platform reference on that table, and ADR 0014 prefixes an "
        "LMS-owned column `lms_`. If the key has been renamed, this constant follows it — the "
        "control cannot plant the disclosure the carried entry measured without the column that "
        "carries it, and the planted view below would fail to compile instead of failing to be "
        "caught."
    )

    session.execute(
        text(f"ALTER TABLE public.{PLANTED_ALIAS_TABLE} ADD COLUMN {PLANTED_ALIAS_COLUMN} text")
    )
    # One statement per line, the shape this repository already uses for
    # interpolated DDL in a test (`test_a_whole_row_view_reference_is_recorded_at_
    # table_grain` above). Every name interpolated is a constant declared at the
    # head of this module; nothing reaches these from outside the file, and the
    # transaction is rolled back.
    #
    # **This line carries no S608 suppression**, and that is measured rather than
    # chosen: ruff does not read this string as SQL built by interpolation, so
    # adding one earns a `RUF100` for an unused directive. The two planted
    # statements in the controls below are flagged and do carry it. A blanket
    # suppression on every line that looks SQL-ish is what `RUF100` exists to
    # stop.
    #
    # The rule is spelled in prose here rather than quoted, which is not fussiness:
    # ruff reads a suppression token anywhere in a comment, so a sentence quoting
    # the marker syntax *is* a directive, and one explaining a removed directive is
    # an unused one. Measured — it cost a round.
    planted_view = f'CREATE VIEW public.{PLANTED_ALIAS_VIEW} AS\nSELECT\n    ui.{PLANTED_ALIAS_COLUMN}     AS respondent_display_name,\n    u.{LMS_USER_KEY}\nFROM public."{USER_TABLE}" u\nJOIN {PLANTED_ALIAS_TABLE} ui ON ui.user_id = u.id'
    session.execute(text(planted_view))

    connection = session.connection()
    source = f"{PLANTED_ALIAS_TABLE}.{PLANTED_ALIAS_COLUMN}"
    join_key = f"{USER_TABLE}.{LMS_USER_KEY}"

    marked_columns = database_marked_columns(connection)
    assert (PLANTED_ALIAS_TABLE, PLANTED_ALIAS_COLUMN) not in marked_columns, (
        f"`{source}` reads as *marked*, so the marked-column sweep above already sees this view "
        "and the planted case no longer demonstrates anything the strict rule adds. The column is "
        "planted by raw DDL with no comment and no `identity_` prefix; if `marked` now accepts a "
        "third thing about it, read that change before this test."
    )
    assert (USER_TABLE, LMS_USER_KEY) not in marked_columns, (
        f"`{join_key}` reads as marked, which contradicts ADR 0001's split — `{USER_TABLE}` holds "
        "the LMS key and the platform reference precisely so that they are not identity — and "
        "`test_the_marker_does_not_reach_columns_that_hold_no_identity` above is where that is "
        "diagnosed. Until it is, the second finding asserted below would be the marker's rather "
        "than this rule's."
    )
    assert not [
        entry
        for entry in column_grained_identity_reads(connection)
        if entry.startswith(f"{PLANTED_ALIAS_VIEW}:")
    ], (
        f"`{PLANTED_ALIAS_VIEW}` is reported by the *marked-column* sweep. That is good news and it "
        "contradicts the assertion above, which says the planted column carries no marker — so one "
        "of the two computations has changed, and this control is no longer evidence that the "
        "strict rule catches something its neighbour cannot."
    )

    dependencies = connection.execute(text(VIEW_COLUMN_DEPENDENCIES)).all()
    assert (PLANTED_ALIAS_VIEW, PLANTED_ALIAS_TABLE, PLANTED_ALIAS_COLUMN) in [
        tuple(row) for row in dependencies
    ], (
        f"Postgres records no dependency of `{PLANTED_ALIAS_VIEW}` on `{source}`, so the planted "
        "view either was not created, does not read the column, or is invisible to "
        "`VIEW_COLUMN_DEPENDENCIES` — and the assertion below would be about a view nothing is "
        "looking at rather than about the rule."
    )

    findings = person_table_reads_including_chains(connection).get(PLANTED_ALIAS_VIEW, set())
    assert any(found == source for found, _ in findings), (
        f"The strict rule does not report `{source}` for `{PLANTED_ALIAS_VIEW}`; it reported "
        f"{sorted(findings)}. The view aliases the column to `respondent_display_name`, which is "
        "the shape the reviewer's fixture uses and the shape the sweep this ticket closed was "
        "measured green against: the guard keys on the *output label*, which the view's author "
        "chooses. The source column is what has to be named — E1-01 criterion 1 — because the "
        "same file fails other sweeps with messages about other things, and a red that points "
        "away from the defect spends the one moment somebody was looking."
    )
    assert any(found == join_key for found, _ in findings), (
        f"The strict rule does not report `{join_key}` for `{PLANTED_ALIAS_VIEW}`; it reported "
        f"{sorted(findings)}. That is the carried entry's second finding and the one nothing in "
        "this repository looked at before: the LTI `sub`, on a table that carries no marked column "
        "by construction, matching no identity fragment, and enough to resolve a named student in "
        "the LMS in one step. A rule that caught the aliased name and not this one would close "
        "half of what the entry measured."
    )


@pytest.mark.invariant
def test_a_view_that_reads_a_person_table_column_through_another_view_is_flagged(
    db_session: Any,
) -> None:
    """The chain: B reads A, A reads `user_identity`, and Postgres records B against A.

    The gap is a fact about `pg_depend` rather than about anybody's SQL. A view
    is stored as a rewrite rule over the relations it names, so a view built on
    another view records column dependencies against *that view's* columns — and
    an intermediate view's columns carry no marker, belong to no person table,
    and may be called anything the author likes. The one-hop query therefore
    reports the reader as reading nothing, which is the first assertion here.

    **The negative and the two assertions after it are the finding**, and they are
    the reason this is a test rather than a paragraph: the reader has no direct
    person-table read, and the fold reports one anyway, naming the base column and
    the path. Without the negative, a fold that had quietly collapsed into the
    one-hop version would pass on the positives alone — the source view is
    flagged directly, and asserting only that would be asserting the neighbour's
    rule.

    Both views are planted inside `db_session`'s transaction and roll back with
    it (`docs/MISTAKES.md` entry 20: the plant and the assertions are in one
    transaction).

    **The mutation it exists to survive**: deleting the fixed-point loop from
    `person_table_reads_including_chains`, or reading only the rows whose
    `table_name` is a base table.
    **The near miss it tolerates**: a chain whose base view reads only join keys,
    which is flagged nowhere — the source view has no finding to inherit.
    """
    session = db_session
    # Two statements, one per line with its own suppression, for the reason the
    # sibling control above gives. `identity_name` is the marked column this
    # schema really carries, so the base read is a real one.
    source_view = f"CREATE VIEW public.{PLANTED_CHAIN_SOURCE_VIEW} AS SELECT identity_name AS display_name FROM public.{PLANTED_ALIAS_TABLE}"  # noqa: S608
    reader_view = f"CREATE VIEW public.{PLANTED_CHAIN_READER_VIEW} AS SELECT display_name FROM public.{PLANTED_CHAIN_SOURCE_VIEW}"  # noqa: S608
    session.execute(text(source_view))
    session.execute(text(reader_view))

    connection = session.connection()
    direct = person_table_column_reads(connection)
    chained = person_table_reads_including_chains(connection)

    assert direct.get(PLANTED_CHAIN_SOURCE_VIEW), (
        f"The one-hop reading reports nothing for `{PLANTED_CHAIN_SOURCE_VIEW}`, which selects "
        f"`identity_name` straight out of `public.{PLANTED_ALIAS_TABLE}`. Then the base of this "
        "chain is not being seen at all and the reader below has nothing to inherit, so the "
        "assertion about the chain would be about a computation that is blind rather than about "
        "one that is closed."
    )
    assert PLANTED_CHAIN_READER_VIEW in view_dependency_edges(connection), (
        f"Postgres records no view-to-view dependency for `{PLANTED_CHAIN_READER_VIEW}`, which "
        f"selects from `{PLANTED_CHAIN_SOURCE_VIEW}`. The edge query is not seeing a chain that "
        "exists, and the fold has no hop to follow."
    )
    assert not direct.get(PLANTED_CHAIN_READER_VIEW), (
        f"The one-hop reading already reports {sorted(direct[PLANTED_CHAIN_READER_VIEW])} for "
        f"`{PLANTED_CHAIN_READER_VIEW}`, which reads no person table directly — it reads a view "
        "that does. If Postgres has begun recording a transitive column dependency, the fold below "
        "is unnecessary rather than wrong, and that is worth knowing before anybody decides which "
        "of the two to keep."
    )

    source = f"{PLANTED_ALIAS_TABLE}.identity_name"
    inherited = chained.get(PLANTED_CHAIN_READER_VIEW, set())
    assert any(found == source for found, _ in inherited), (
        f"The chain closure does not report `{source}` for `{PLANTED_CHAIN_READER_VIEW}`; it "
        f"reported {sorted(inherited)}. The reader selects a column called `display_name` from a "
        "view that selects `identity_name` from a person table, so every name in the reader's own "
        "dependency row belongs to the intermediate view — and the marked-column sweep, the "
        "whole-row sweep and the one-hop reading are all correctly silent about it. This fold is "
        "the only thing between that arrangement and an instructor screen."
    )
    paths = [path for found, path in inherited if found == source]
    assert any(PLANTED_CHAIN_SOURCE_VIEW in path for path in paths), (
        f"The chain closure reports `{source}` for `{PLANTED_CHAIN_READER_VIEW}` and the path it "
        f"names does not mention `{PLANTED_CHAIN_SOURCE_VIEW}`: it reported {sorted(inherited)}. "
        "The path is half of what the failure message is for — a reader told only that a view "
        "reads a name has two view definitions to open before knowing which."
    )


@pytest.mark.invariant
def test_a_view_that_reads_only_join_keys_of_a_person_table_is_not_flagged(
    db_session: Any,
) -> None:
    """The other half of the boundary: the reads a read path is built out of stay silent.

    A tripwire that fires on correct SQL is repaired by weakening it, and the
    casualty is the guard rather than the view. Two shapes are planted, and both
    are shapes this schema either has or would write next: a view reading the keys
    `JOIN_KEY_COLUMNS` allows off a person table — spelled from the table's own
    columns rather than named here, so that the sample cannot come to name a
    column the table does not have — and a view reading `enrollment.user_id`,
    which is what `section_roster` does and which the carried entry on the
    reveal's composition describes as "the whole point of the view".

    **The offending view is planted in the same transaction as the two allowed
    ones**, and that is not decoration: silence is what a computation that has
    gone blind produces as well, so a control that only asserted an absence would
    be green with the rule deleted (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: dropping `id` or `user_id` from
    `JOIN_KEY_COLUMNS`, which would make every roster-shaped view in the schema
    an offender and would be repaired by whoever met the red at the cheapest
    place — by widening the rule back out to marked columns only.
    **The near miss it tolerates**: none beyond the two planted here; that is
    what this test is.
    """
    session = db_session
    inspector = inspect(session.connection())
    on_enrollment = {
        column["name"]
        for column in (
            inspector.get_columns(ENROLLMENT_TABLE)
            if ENROLLMENT_TABLE in inspector.get_table_names()
            else []
        )
    }
    assert ENROLLMENT_KEY_COLUMN in on_enrollment, (
        f"`public.{ENROLLMENT_TABLE}` does not exist or has no `{ENROLLMENT_KEY_COLUMN}` column; "
        f"it has {sorted(on_enrollment)}. SPEC §8 names `{ENROLLMENT_TABLE}` in the core table "
        "list and the carried entry on the reveal's composition names this exact read, so if "
        "either has been renamed these constants follow it — the roster-shaped sample is the shape "
        "the real read path has, and dropping it would leave the allow side asserted only over a "
        "shape nobody writes."
    )

    on_identity = {column["name"] for column in inspector.get_columns(PLANTED_ALIAS_TABLE)}
    keys = sorted(set(JOIN_KEY_COLUMNS) & on_identity)
    assert keys, (
        f"`public.{PLANTED_ALIAS_TABLE}` carries none of the join keys {list(JOIN_KEY_COLUMNS)}, so "
        "there is no allowed read of a person table to plant. Either the schema has moved or the "
        "allow-list names columns this table does not have, which "
        "`test_every_join_key_the_bound_column_mechanism_allows_is_a_structural_key` in "
        "`test_identity_separated_views.py` is where it is diagnosed."
    )
    select_keys = ", ".join(f"ui.{key}" for key in keys)

    # Three views, one per line with its own suppression, as above: two the rule
    # must allow and one it must catch, so that the two absences below are
    # attributable to the views rather than to a rule that reports nothing.
    join_key_view = f"CREATE VIEW public.{PLANTED_JOIN_KEY_VIEW} AS SELECT {select_keys} FROM public.{PLANTED_ALIAS_TABLE} ui"  # noqa: S608
    roster_shape_view = f"CREATE VIEW public.{PLANTED_ROSTER_SHAPE_VIEW} AS SELECT e.{ENROLLMENT_KEY_COLUMN} FROM public.{ENROLLMENT_TABLE} e"  # noqa: S608
    offending_view = f"CREATE VIEW public.{PLANTED_OFFENDING_VIEW} AS SELECT ui.identity_name FROM public.{PLANTED_ALIAS_TABLE} ui"  # noqa: S608
    session.execute(text(join_key_view))
    session.execute(text(roster_shape_view))
    session.execute(text(offending_view))

    connection = session.connection()
    findings = person_table_reads_including_chains(connection)

    assert findings.get(PLANTED_OFFENDING_VIEW), (
        "The rule reports nothing for a planted view that selects `identity_name` straight out of "
        f"`public.{PLANTED_ALIAS_TABLE}`. It is blind, and the two absences asserted below are "
        "facts about the computation rather than about the two views they name."
    )
    assert not findings.get(PLANTED_JOIN_KEY_VIEW), (
        f"`{PLANTED_JOIN_KEY_VIEW}` reads {keys} off a person table and the rule reports "
        f"{sorted(findings[PLANTED_JOIN_KEY_VIEW])}. Every one of those is in "
        f"{list(JOIN_KEY_COLUMNS)}: a read view has to be able to join, and a rule that forbids "
        "the key forbids the read path §4.1 depends on rather than the disclosure it is about."
    )
    assert not findings.get(PLANTED_ROSTER_SHAPE_VIEW), (
        f"`{PLANTED_ROSTER_SHAPE_VIEW}` reads `{ENROLLMENT_TABLE}.{ENROLLMENT_KEY_COLUMN}` — the "
        f"shape `section_roster` really has — and the rule reports "
        f"{sorted(findings[PLANTED_ROSTER_SHAPE_VIEW])}. `{ENROLLMENT_TABLE}` is not one of "
        f"{list(PERSON_TABLES)}, so nothing here should have looked at it at all; the Pulse-"
        "internal `user_id` is the design, and it is what makes a de-identified response "
        "addressable."
    )
