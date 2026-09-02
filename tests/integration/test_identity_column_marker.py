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
differently and the first version of this file only asked about one. The rest are
E1-01's, in the section below those: the strict rule over the person tables and
its planted controls. Their docstrings carry the reasoning;
`scripts/ci/check_invariants.py` is what makes the mark mean something, by
treating a skip, an xfail or an empty collection in that pass as a failure. Do
not count them from this paragraph — `pytest -m invariant --collect-only` is the
only currency that sees both marking forms (`docs/MISTAKES.md` entry 35).

**E1-12 adds the first table this convention has had to reach on its own**, at the
foot of the file. `web_login_subject` maps an IdP `(issuer, subject)` pair to a
`person`, and neither of its two text columns is named anything the identity
vocabulary knows — `idp_subject` matches no fragment in `IDENTITY_NAME_FRAGMENTS`
and was never going to. So the sweep above is silent about it whether it is marked
or not, and the criterion that it "stays green with the new columns marked" is a
criterion nothing here would have measured. The three tests at the foot are that
measurement: the table is reached by the fixed-point walk, its per-person key
carries the marker, and the closed list of columns a view may read from a person
table is still the same three structural keys.

**E1-01 adds a rule phrased over the *table* rather than over the marker**, and it
is here for the same reason everything else in this file is: the vocabulary is
defined here, so widening it widens every reader at once. The marker says what a
column holds, which cannot answer for `user` — ADR 0001 puts the key and the
platform reference there precisely so they are not identity, so `user` carries no
marked column and `user.lms_user_id` is read by a view with every guard above
green. `JOIN_KEY_COLUMNS` below is the closed list of columns a view may read
from a table that holds a person, and `person_table_reads_including_chains`
follows a view built on a view, which the one-hop dependency query cannot.

**It reads both dependency grains, and that is a security review's finding rather
than symmetry for its own sake.** A view taking `to_jsonb(u)` of a `user` row
carries every column that table has and records *no* column dependency, so the
column-grain rule is silent; and the whole-row rule above is scoped to marked
tables, where `user` is deliberately absent. The two guards that each cover one
grain left one table uncovered at both, which is the shape `docs/MISTAKES.md`
entry 35 records one level up: an enumeration of mechanisms that is complete on
the subject somebody had in mind.

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

**Batch A closes the two things E1-01 deferred, and both are at the foot of the
file.** The first is a hole in the catalog half rather than a new rule: Postgres
drops the `refobjsubid = 0` whole-row dependency as soon as the same view also
names a column of that table, so a whole-row read written as a join —
`SELECT u.id, to_jsonb(u) FROM enrollment e JOIN "user" u ON u.id = e.user_id` —
was recorded at column grain only and neither whole-row rule here could see it.
`decompiled_whole_row_reads` asks the same question of `pg_get_viewdef` and feeds
the answer into both, so the two guards now report the join form and the plain
one alike. The second is a *report* rather than a guard: the sweeps above are all
phrased over names and markers, so a table the walk reaches whose columns none of
them recognises is passed over in silence, which is how `web_login_subject` would
have shipped unmarked. `unclassified_reached_tables` names such a table, and
`REACHED_TABLES_THAT_CARRY_NOTHING` is where the tables the silence is acceptable
over are recorded — each with the columns that judgement was made against, so the
entry expires the moment one of them grows a column, and with the reason a
reviewer reads when it does. No count is written here: the mapping grows with
every ticket that adds a table the walk reaches, and a number in a docstring is a
record with a scheduled expiry (`docs/MISTAKES.md` entry 1). E2-05 added two,
`response` and `answer`.

What remains outside the search is stated on `IDENTITY_NAME_FRAGMENTS` below
rather than here, beside the tuple that decides it (`docs/MISTAKES.md` entry 14).
"""

import re
from importlib import import_module
from typing import Any, NamedTuple

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
#
# **A structural source for these three roots was attempted on 2026-08-28 and
# does not exist**, which is why the list is still written out. The grant-derived
# candidate — the tables `pulse_app` holds no `SELECT` on — over-reports five-fold,
# because the application role reads through views rather than through tables and
# most of what it cannot select holds no person at all; and a marker- or
# model-derived source is circular for the reason dispute E0-10-01 settled, since
# the marker is the thing these roots are used to check. The compensating control
# is `unclassified_reached_tables` at the foot of this file, which names a table
# the walk reached and recognised nothing on; the residual blind spot it does not
# cover is a person table with no foreign-key path into the graph at all. The full
# record is `docs/tickets/e1/deferred.md`, E1-01 item 2.
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
# **This row is conditional, and Batch A is what that cost.** Postgres records the
# whole-row dependency only while the view names *no* column of the same table:
# add one — a join condition is enough — and the `refobjsubid = 0` row is dropped
# and the read is recorded at column grain, where it looks like an ordinary key
# read. So this query is silent on `SELECT u.id, to_jsonb(u) FROM enrollment e
# JOIN public."user" u ON u.id = e.user_id`, which carries every column `user`
# has. `VIEW_DEFINITIONS` below is the second reading that closes it, and both
# whole-row rules take the union of the two.
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

# The stored definition of every view, as Postgres decompiles it back out of the
# rewrite rule. **This is not the author's text and must not be read as if it
# were**: the parser has already resolved the names, expanded a `SELECT *` into
# its columns, dropped the schema qualification the search path makes redundant,
# and normalised the whitespace. That is exactly what makes it usable here — the
# four-mechanism grammar in `test_identity_separated_views.py` exists because a
# human can spell a whole-row read four ways, and this text has one spelling.
#
# `pg_get_viewdef(oid, true)` is the pretty-printed form, which puts each clause
# of the `FROM` on its own line; nothing below depends on the layout, only on the
# tokens.
VIEW_DEFINITIONS = """
    SELECT c.relname AS view_name, pg_get_viewdef(c.oid, true) AS definition
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind IN ('v', 'm')
    ORDER BY 1
"""

# Words that may follow a relation name where an alias would otherwise stand, so
# that `FROM public."user" WHERE …` does not bind an alias called `where` and then
# go looking for `where.*`. Deliberately a stop list rather than a full grammar:
# the text being read is decompiled, so the shapes are Postgres's own and few.
#
# **`as` is in the list, and it is a discriminator rather than an oversight.**
# Postgres decompiles a *relation* alias with no `AS` (`FROM enrollment e`) and a
# *target-list* alias with one (`SELECT u.person AS p`). The binder below reads a
# comma-separated `FROM` list, so without this it would read the second shape as a
# relation called `person` carrying an alias, and bind a token off a column that
# happens to share a table's name. Refusing the word is what stops that. If a
# future Postgres starts writing `AS` for relation aliases, the alias goes unbound
# and the planted controls at the foot of this file go red saying so, because each
# of them asserts the binder bound the alias it planted.
CLAUSE_KEYWORDS = (
    "as",
    "on",
    "using",
    "where",
    "group",
    "order",
    "having",
    "limit",
    "offset",
    "join",
    "inner",
    "left",
    "right",
    "full",
    "cross",
    "natural",
    "lateral",
    "union",
    "intersect",
    "except",
    "window",
    "fetch",
    "for",
    "returning",
)

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

# The whole-row plants, added by the security review that found the second
# dependency grain unguarded on `user`. The alias on the first is the reviewer's
# own — a name a real author would choose for that column, which is what makes it
# the accident rather than the sabotage.
PLANTED_WHOLE_PERSON_VIEW = "e1_01_planted_whole_person_view"
PLANTED_WHOLE_PERSON_READER_VIEW = "e1_01_planted_whole_person_reader_view"
PLANTED_WHOLE_OTHER_VIEW = "e1_01_planted_whole_other_view"
PLANTED_WHOLE_ROW_ALIAS = "platform_ref"

# The table the roster-shaped control reads, and the column it reads from it.
# SPEC §8 names `enrollment` in the core table list, and the carried entry on the
# reveal's composition names this exact read: `section_roster` "hands
# instructor-scoped code the `user_id` of every enrolled student". A view of that
# shape must stay silent, or the strict rule would forbid the read path §4.1
# depends on.
ENROLLMENT_TABLE = "enrollment"
ENROLLMENT_KEY_COLUMN = "user_id"

# The keys the allow-side control plants, written out rather than intersected with
# `JOIN_KEY_COLUMNS`. **That intersection is what the first version did, and the
# mutation battery measured what it cost**: shrinking the allow-list shrank the
# plant with it, so dropping `id` or dropping `user_id` — the two mutations that
# control's docstring claims to kill — left it green, reading whichever keys
# survived. A control whose subject comes from the structure it is guarding cannot
# notice that structure getting smaller, which is the shape `REQUIRED_MECHANISM_
# LABELS` in `test_identity_separated_views.py` exists to avoid and which this
# module's own comments warn about twice.
#
# So these are literal, and a rename in the schema is a named failure in that
# control rather than a sample that quietly stops testing anything.
PLANTED_ALLOWED_KEYS = ("id", "user_id")

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
    being §6.2's Care queue.

    **`answer` is no longer hypothetical, and this sentence used to say it was.**
    E2-05 builds it: `response.user_id` is one hop from `user` and
    `answer.response_id` is a second, so `answer` is reached by the fixed point
    and by nothing else, and both tables are recorded in
    `REACHED_TABLES_THAT_CARRY_NOTHING` at the foot of this file. That makes this
    walk the first thing in the repository to depend on the extra hop against a
    real table rather than against a plant. `threat_case` is still hypothetical,
    and the property is still asserted over a planted chain as well, in
    `test_the_marker_sweep_follows_the_foreign_key_walk_to_a_fixed_point` below:
    a plant is what keeps the guard measurable when the schema's own two-hop
    tables happen to be reachable by one hop too.

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


def view_definitions(connection: Any) -> dict[str, str]:
    """Every view in `public`, and the definition Postgres decompiles it back to."""
    return {
        view: definition or "" for view, definition in connection.execute(text(VIEW_DEFINITIONS))
    }


def relation_tokens_bound_to(definition: str, table: str) -> set[str]:
    """Every token a decompiled definition can refer to `table`'s rows by.

    The table's own name, and every alias a `FROM` or a `JOIN` binds to it.
    Postgres emits an alias wherever the query had one and refers to the relation
    by name where it had none, so those two together are the whole vocabulary a
    reference to that table's row can be written in — in *this* text. That is a
    much smaller claim than the one `relation_bindings` in
    `test_identity_separated_views.py` has to make, and the reason the two are
    not one function: that one reads what a human wrote, where a schema
    qualification may or may not be present, a keyword may be cased any way, and
    the same relation may be named twice; this one reads what Postgres wrote.

    **Three introducers, not one, and the second two are a security review's
    finding.** A relation is bound after `FROM`, after `JOIN`, and after a **comma**
    in an old-style join list — `FROM enrollment e, "user" u WHERE u.id = e.user_id`
    — which Postgres decompiles as the comma list it was written as. The first
    version of this read `FROM` and `JOIN` only, so the reviewer's comma-join probe
    bound no alias, `to_jsonb(u.*)` matched no token, and the whole-row read was
    reported by nothing in the catalog half. The `ONLY` of `FROM ONLY "user" u`
    round-trips through the decompiler too and is skipped over here for the same
    reason: `relation_bindings` in `test_identity_separated_views.py` already reads
    it, and two readings of one question that disagree is `docs/MISTAKES.md`
    entry 13.

    **What it does not see, stated rather than left to be found**
    (`docs/MISTAKES.md` entry 14):

      - **a relation bound by a `WITH` clause.** `WITH ui AS (SELECT * FROM
        public.user_identity) SELECT to_jsonb(ui) FROM ui` binds `ui` to a CTE, and
        the whole row it takes is the CTE's rather than the table's. What holds
        that shape is `VIEW_COLUMN_DEPENDENCIES` and the strict rule built on it:
        a CTE cannot carry a column out of a table without the stored view
        depending on that column, so the read is recorded at column grain and
        reported there. This is not the file sweep's job and this note used to say
        it was.
      - **a quoted alias containing a space or punctuation.** `FROM public."user"
        "the person"` binds an alias `(\\w+)` cannot capture, so only the table's
        own name stays a token. Postgres writes such an alias only if a view's
        author did; the text sweep next door reads the file either way.

    The table's own name is a token whatever happens, so every unaliased spelling
    stays covered; what these two cost is the alias.

    **And it is blind to scope, which over-reports rather than under-reports.** A
    subquery may bind the same short alias to a different relation, and every
    token here is searched for across the whole definition — so a view binding `u`
    to `"user"` at the top level and `u` to something else inside a subquery that
    takes a whole row is reported. That direction costs a human reading two lines
    of a view definition; the other direction would cost the guard.
    """
    stop = "|".join(CLAUSE_KEYWORDS)
    pattern = re.compile(
        r"(?:(?:\bFROM\b|\bJOIN\b)\s+|,\s*)(?:\bONLY\b\s+)?"
        rf'(?:"?\w+"?\s*\.\s*)?"?{re.escape(table)}"?(?!\w)'
        rf'(?:\s+(?!(?:{stop})\b)"?(\w+)"?)?',
        re.IGNORECASE,
    )
    return {table} | {found.group(1) for found in pattern.finditer(definition) if found.group(1)}


def decompiled_whole_row_reads(connection: Any, tables: set[str]) -> set[tuple[str, str]]:
    """Every `(view, table)` whose stored definition reads `table`'s row whole.

    **The reading that closes the catalog's conditional blind spot**, which is
    E1-01's first deferred item. `VIEW_TABLE_DEPENDENCIES` records a whole-row
    reference at `refobjsubid = 0` only while the view names no column of the same
    table; a join condition is a named column, so
    `SELECT u.id, to_jsonb(u) FROM enrollment e JOIN public."user" u ON u.id =
    e.user_id` is recorded as an ordinary read of `user.id` and the row it also
    carries is recorded nowhere. Every column `user` has travels through that
    view, `lms_user_id` among them.

    **It matches `alias.*` and nothing else, and that narrowness is the decision.**
    Postgres decompiles *every* whole-row form to that one spelling: `to_jsonb(u)`
    comes back as `to_jsonb(u.*)`, a bare `SELECT u` as `u.*`, `TABLE public."user"`
    as a `SELECT` over the expanded columns. The four-mechanism grammar in
    `test_identity_separated_views.py` exists because a human writes whichever of
    the four they like; this text is the parser's, so one pattern answers for all
    of them. If a future Postgres decompiles a whole-row reference some other way,
    the planted controls at the foot of this module go red rather than the guard
    going quietly blind — which is why they plant the read and require it found,
    rather than asserting an absence over the live schema alone.

    **The token boundary is load-bearing in both directions**, and each is planted:
    an alias `u` must not match `us.*` written by a second relation, and an alias
    `r` must not match `ur.*`. Without the first the guard fires on correct SQL —
    the direction that gets a guard weakened — and without the second it fires on
    a whole-row read of a table nobody is guarding, which is the same thing one
    step along.

    **Its known false positive**, stated rather than discovered: a whole-row test
    that projects nothing, `WHERE u.* IS NOT NULL`, is reported. It reads the row,
    it is not a spelling anything in this repository writes, and a red on it is a
    human look at a view that tests a person's row for existence — which is worth
    having.
    """
    found: set[tuple[str, str]] = set()
    for view, definition in view_definitions(connection).items():
        for table in tables:
            for token in relation_tokens_bound_to(definition, table):
                whole = re.compile(rf'(?<![\w"])"?{re.escape(token)}"?\s*\.\s*\*', re.IGNORECASE)
                if whole.search(definition):
                    found.add((view, table))
                    break
    return found


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

    **Two readings since Batch A, and the second is here because the first is
    conditional.** Postgres drops the `refobjsubid = 0` row as soon as the view
    also names any column of the same table, so the join form of a whole-row read
    is recorded at column grain only and the catalog query is silent on it.
    `decompiled_whole_row_reads` asks the same question of `pg_get_viewdef`, and
    what this reports is the union: a pair the catalog records and a pair only the
    definition shows are one finding here, because they are one exposure.
    """
    tables = {table for table, _ in database_marked_columns(connection)}
    recorded = {
        (view, table)
        for view, table in connection.execute(text(VIEW_TABLE_DEPENDENCIES))
        if table in tables
    }
    return sorted(
        f"{view}: {table}"
        for view, table in recorded | decompiled_whole_row_reads(connection, tables)
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
    view in the migrated database, and since Batch A any of them written as a join
    that also names a column of the same table, which Postgres records at column
    grain only. **The near miss it tolerates**: a view reading a named column of a
    marked table, which is the test above's subject and produces neither a
    whole-row dependency nor an `alias.*` in the decompiled definition; and a view
    reading the whole row of a table that carries no marked column, which is most
    of the schema.
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
    # a healthy schema both readings return *nothing at all*: a view that reads
    # named columns records column dependencies and no whole-table one, and its
    # decompiled definition carries no `alias.*`, so an empty result is the correct
    # state rather than a sweep that has gone blind.
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


def person_table_rows_read_whole(connection: Any) -> dict[str, set[str]]:
    """Every view, and the person tables whose **row** it reads whole, spelled `table.*`.

    **The second dependency grain, and the hole a fresh-context security review
    found between the two.** Postgres records a reference to a row *as a value* at
    `refobjsubid = 0` and records no column dependency for it at all — the
    measurement is on `VIEW_TABLE_DEPENDENCIES` above — so
    `person_table_column_reads` is silent about `SELECT to_jsonb(u) FROM
    public."user" u`, which carries every column `user` has. `row_to_json(u)`, a
    bare `SELECT u`, `(u.*)::text` and `TABLE public."user"` are the same shape.

    `whole_row_identity_reads` above is the same grain and does not close it: it
    scopes to the tables the *marker* names, and `user` carries no marked column
    by construction — ADR 0001 puts the key and the platform reference there
    precisely so that they are not identity. So a whole-row read of `user` was
    invisible at the column grain, invisible at the row grain, and invisible to
    the file sweep next door. Three guards, one shape, nothing.

    **The scope is the union of both**, marked tables and person tables, rather
    than the person tables alone. A marked table that is not a person table —
    E10's `threat_case`, a planted one — is E0-34's subject and is deliberately
    also this rule's, because what this adds over that one is the chain fold: a
    view built on a view that reads such a row is exposed by it, and nothing else
    in the tree follows that hop. The overlap costs a second finding on the same
    view and each guard's message says a different thing about it, which is the
    same trade the two column-grain rules already make.

    Reported as `table.*` rather than as a column list. A whole-row reference has
    no column to name — that is what makes it invisible — and naming the table
    with a star is what tells a reader which of the two shapes they are looking
    at without them having to open the view.

    **It reads the catalog and the decompiled definition, which is Batch A's half
    of the same story.** The `refobjsubid = 0` row exists only while the view
    names no column of that table, so the join form — every column of `user`
    carried beside the key it joined on — was recorded at column grain and
    reported by nothing. `decompiled_whole_row_reads` is the second reading and
    the union is what this returns, so both spellings arrive here as `user.*` and
    travel down the chain fold together. The scope does not move with it: this
    still asks about the marked tables and the person tables, so a whole-row read
    of `enrollment` stays silent whichever reading finds it, and the pair that
    proves that is planted below.
    """
    tables = {table for table, _ in database_marked_columns(connection)} | set(PERSON_TABLES)
    recorded = {
        (view, table)
        for view, table in connection.execute(text(VIEW_TABLE_DEPENDENCIES))
        if table in tables
    }
    found: dict[str, set[str]] = {}
    for view, table in recorded | decompiled_whole_row_reads(connection, tables):
        found.setdefault(view, set()).add(f"{table}.*")
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

    Each finding is `(source, path)`: the base read — `user_identity.identity_name`
    for a column, `user.*` for a whole row — and the chain of views it arrived
    through, the reading view first. So a failure message names what leaked *and*
    where to look, which a set of view names alone cannot.

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
    # **Both grains seed the fold**, which is the security review's finding
    # arriving one level up: a view reading a *column* of a person table and a
    # view reading its whole *row* are the same exposure to whoever reads the
    # view, and the chain that carries the first carries the second. Seeding from
    # one of the two would have left a probe view over `to_jsonb(u)` flagged and
    # every view built on that probe clean.
    seeded: dict[str, set[str]] = {}
    for reads in (person_table_column_reads(connection), person_table_rows_read_whole(connection)):
        for view, sources in reads.items():
            seeded.setdefault(view, set()).update(sources)
    edges = view_dependency_edges(connection)

    found: dict[str, set[tuple[str, str]]] = {
        view: {(source, view) for source in sources} for view, sources in seeded.items()
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

    **Both dependency grains, which is a fresh-context security review's finding
    and was a live hole in the first version of this rule.** Postgres records a
    read of a row *as a value* at `refobjsubid = 0` and records no column
    dependency for it, so `SELECT to_jsonb(u) AS platform_ref FROM public."user" u`
    produced nothing at the column grain — and the whole-row rule next door scopes
    itself to the tables the marker names, where `user` is absent by construction.
    A view carrying every column `user` has was invisible to both, and to the file
    sweep in `test_identity_separated_views.py`, which had the mirror of the same
    gap. `person_table_rows_read_whole` is the second grain and it is folded in
    here rather than asserted separately, because a reader wants one answer to
    "what does this view reach" and the two grains are two spellings of one
    question.

    **And since Batch A that second grain is read twice**, because the catalog's
    answer to it is conditional: the `refobjsubid = 0` row survives only while the
    view names no column of the same table, so the identical read written as a
    join is recorded as an ordinary key read and nothing else.
    `decompiled_whole_row_reads` reads `pg_get_viewdef` for the one spelling
    Postgres decompiles every whole-row form to, and `person_table_rows_read_whole`
    returns the union — so the join form arrives here as `user.*` exactly as the
    plain form does, and travels the same chain.

    **And why it reaches through a chain.** `VIEW_COLUMN_DEPENDENCIES` is one hop:
    a view built on another view records its dependency against the intermediate
    view's columns, which carry no marker and belong to no person table, so the
    filter above returns nothing for it. `person_table_reads_including_chains`
    folds those hops to a fixed point and carries the base read forward, so the
    failure names `user_identity.identity_name` — or `user.*` — and the path it
    travelled rather than the intermediate view's invented column name. The fold
    is seeded from **both** grains, so a view built on the `to_jsonb` probe above
    inherits it too; a fold seeded from one would have flagged the probe and
    cleared everything downstream of it.

    **Marked `invariant` for the reason both of its neighbours are**: a view runs
    with its owner's privileges rather than its reader's, so this is a route to
    identity that no arrangement of ADR 0001's grants closes, and in a green
    checkmark a skipped assertion and a passing one look the same.

    **The mutation it exists to survive**: a view selecting `u.lms_user_id`, a
    view selecting `ui.<anything unmarked>` on a person table, and a view taking
    `to_jsonb(u)` of one — none of which any other test in this repository
    mentions — and any of those read through a second view that renames the
    column.
    **The near miss it tolerates**: a view joining a person table and reading only
    the keys `JOIN_KEY_COLUMNS` names, which is how a roster view is built and
    what makes a de-identified response addressable at all; and a whole-row read
    of a table that holds no person, which is most of the schema.

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
        f"{reported}. Each is a view reading, from one of {list(PERSON_TABLES)} — the tables that "
        f"hold a person — either a column that is not one of the join keys "
        f"{list(JOIN_KEY_COLUMNS)}, or the whole row.\n\n"
        "**A finding spelled `<table>.*` is the whole row**, and it is the shape that carries "
        "every column the table has while naming none of them: `to_jsonb(u)`, `row_to_json(u)`, a "
        'bare `SELECT u`, `(u.*)::text`, `TABLE public."user"`. Postgres records it at '
        "`refobjsubid = 0` and records no column dependency at all, which is why the rule reads "
        "two grains and why neither of the marker-based invariants above sees it on `user`.\n\n"
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

    **How deleting the plant kills this, which is not by an assertion.** Removing
    the `ALTER TABLE` leaves `CREATE VIEW` selecting a column that does not exist,
    so psycopg raises `UndefinedColumn` before the dependency check below is
    reached. That is still a kill of the right kind — a red carrying this test's
    name and the missing column's, diagnosable in one line — but it is an error
    rather than a failed assertion, and the distinction matters to whoever runs a
    battery here: only deleting the `CREATE VIEW` reaches the non-vacuity
    assertion. Left in this order deliberately, because the alternative is
    asserting a column exists that the next statement would have named anyway.
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
def test_a_whole_row_read_of_a_person_table_is_flagged_and_travels_down_the_chain(
    db_session: Any,
) -> None:
    """The grain a fresh-context security review walked around both guards through.

    Reproduced as the reviewer wrote it: `SELECT to_jsonb(u) AS platform_ref FROM
    public."user" u`. It carries every column `user` has — the LMS key included —
    and it was reported by nothing. The column-grain rule sees no dependency,
    because Postgres records a row-as-value at `refobjsubid = 0` and records no
    column dependency beside it. `test_no_view_reads_a_whole_row_of_a_table_the_
    identity_marker_names` above sees no *table*, because it scopes to the tables
    the marker names and `user` carries no marked column by design. The file sweep
    next door had the mirror of the same gap.

    **Four assertions, and the order is the argument.** The two negatives come
    first and they are the finding rather than ceremony: this planted view must be
    absent from the column-grain reading and absent from the older whole-row
    reading, or the hole has been closed somewhere else and this control is
    measuring a different thing. Then the rule must report it as `user.*`. Then a
    second view built on the first must inherit it — a view reading the probe's
    one column is exactly as exposed as the probe, and a fold seeded from the
    column grain alone would have flagged the probe and cleared everything
    downstream.

    **The pair is in the same transaction**: a whole-row read of a table that
    holds no person must stay silent. Without it, "flagged" is equally what a rule
    that flags every whole-row read anywhere would produce, and that rule would go
    red on the first legitimate `to_jsonb` in the schema and be repaired by
    narrowing it back to marked tables — which is the state this control exists to
    leave behind.

    **What this control proves is narrower than "the catalog covers whole-row
    reads", and the boundary is measured.** Postgres drops the `refobjsubid = 0`
    row as soon as the same view also names a column of that table, so the
    *catalog* half fires only on a view that touches **no** column of the person
    table — which the planted probe here does not, and which is why it is planted
    that way. Its join form,
    `SELECT to_jsonb(u) … FROM public.enrollment e JOIN public."user" u ON u.id =
    e.user_id`, records only `(1, id)`, and this control says nothing about it.

    **Batch A is what covers that spelling on this side**, and it is a separate
    control rather than a widening of this one:
    `test_a_whole_row_read_hidden_by_a_join_is_flagged_though_the_catalog_records_
    a_column` at the foot of the file plants the join form, asserts that the
    catalog query is still silent on it, and requires
    `decompiled_whole_row_reads` — which reads `pg_get_viewdef` — to report it
    into this same rule. The two controls answer for one grain each of the same
    question, which is why neither was folded into the other.

    The text side is unchanged and still independent: `identity_rows_read_whole`
    in `test_identity_separated_views.py` catches every form of it — a security
    re-pass tried to defeat it and did not — and every live view reaches the
    database through a `views_sql/` file, which
    `test_every_read_view_is_created_from_a_sql_file_under_views_sql` is what
    enforces.

    **The mutation it exists to survive**: reverting `person_table_rows_read_whole`
    to the marked-table scope `whole_row_identity_reads` uses, or dropping the
    whole-row seed from the chain fold.
    **The near miss it tolerates**: a whole-row read of `enrollment`, planted here
    and required to stay silent.
    """
    session = db_session
    assert ENROLLMENT_TABLE in inspect(session.connection()).get_table_names(), (
        f"There is no `{ENROLLMENT_TABLE}` table, so the silent half of this pair cannot be "
        "planted and the flag asserted above would stand alone — which is equally what a rule "
        "flagging every whole-row read in the schema would produce."
    )

    # One statement per line with its own suppression, as the sibling controls do.
    probe = f'CREATE VIEW public.{PLANTED_WHOLE_PERSON_VIEW} AS SELECT to_jsonb(u) AS {PLANTED_WHOLE_ROW_ALIAS} FROM public."{USER_TABLE}" u'  # noqa: S608
    reader = f"CREATE VIEW public.{PLANTED_WHOLE_PERSON_READER_VIEW} AS SELECT {PLANTED_WHOLE_ROW_ALIAS} FROM public.{PLANTED_WHOLE_PERSON_VIEW}"  # noqa: S608
    other = f"CREATE VIEW public.{PLANTED_WHOLE_OTHER_VIEW} AS SELECT to_jsonb(e) AS payload FROM public.{ENROLLMENT_TABLE} e"  # noqa: S608
    session.execute(text(probe))
    session.execute(text(reader))
    session.execute(text(other))

    connection = session.connection()
    whole = f"{USER_TABLE}.*"

    assert not person_table_column_reads(connection).get(PLANTED_WHOLE_PERSON_VIEW), (
        f"`{PLANTED_WHOLE_PERSON_VIEW}` takes `to_jsonb` of a person table's row and the "
        "*column*-grain reading reports it. That contradicts what was measured on this stack — a "
        "row-as-value records `[(0, whole row)]` and no column dependency at all — so either "
        "Postgres has changed what it records, in which case the second grain below may be "
        "redundant rather than wrong, or the view is not the shape this control believes it is. "
        "Read that before changing anything here."
    )
    assert not [
        entry
        for entry in whole_row_identity_reads(connection)
        if entry.startswith(f"{PLANTED_WHOLE_PERSON_VIEW}:")
    ], (
        f"`{PLANTED_WHOLE_PERSON_VIEW}` is reported by "
        "`test_no_view_reads_a_whole_row_of_a_table_the_identity_marker_names`'s own computation, "
        f"which scopes itself to the tables the marker names. Then `{USER_TABLE}` now carries a "
        "marked column — which contradicts ADR 0001's split and is diagnosed by "
        "`test_the_marker_does_not_reach_columns_that_hold_no_identity` — and this control is no "
        "longer evidence that the person-table scope catches something the marker scope cannot."
    )

    findings = person_table_reads_including_chains(connection)
    probed = findings.get(PLANTED_WHOLE_PERSON_VIEW, set())
    assert any(source == whole for source, _ in probed), (
        f"The strict rule does not report `{whole}` for `{PLANTED_WHOLE_PERSON_VIEW}`; it reported "
        f"{sorted(probed)}. The view carries every column of `{USER_TABLE}` — `{LMS_USER_KEY}` "
        "among them, which resolves a named student at the platform in one step — under one "
        f"harmless-looking column called `{PLANTED_WHOLE_ROW_ALIAS}`. Both assertions above say "
        "the two older guards are silent about it, so with this one silent as well the shape is "
        "reported by nothing in this repository."
    )

    inherited = findings.get(PLANTED_WHOLE_PERSON_READER_VIEW, set())
    assert any(source == whole for source, _ in inherited), (
        f"`{PLANTED_WHOLE_PERSON_READER_VIEW}` selects the probe's one column and does not inherit "
        f"`{whole}`; it reported {sorted(inherited)}. A view built on a view that reads a row whole "
        "hands on exactly what that row held, so the fold has to be seeded from both dependency "
        "grains — seeded from the column grain alone it flags the probe and clears every view "
        "downstream of it, which is the arrangement anybody would reach for once the probe itself "
        "went red."
    )
    paths = [path for source, path in inherited if source == whole]
    assert any(PLANTED_WHOLE_PERSON_VIEW in path for path in paths), (
        f"The inherited finding for `{PLANTED_WHOLE_PERSON_READER_VIEW}` does not name "
        f"`{PLANTED_WHOLE_PERSON_VIEW}` in its path: {sorted(inherited)}. The path is what tells a "
        "reader which of two view definitions to open."
    )

    assert not findings.get(PLANTED_WHOLE_OTHER_VIEW), (
        f"`{PLANTED_WHOLE_OTHER_VIEW}` takes `to_jsonb` of a `{ENROLLMENT_TABLE}` row — a table "
        f"that holds no person — and the rule reports {sorted(findings[PLANTED_WHOLE_OTHER_VIEW])}. "
        "A rule that flags every whole-row read anywhere would be red on the first legitimate "
        "`to_jsonb` in the schema, and the repair somebody reaches for under that pressure is the "
        "marked-table scope this control exists to have replaced."
    )


@pytest.mark.invariant
def test_a_view_that_reads_only_join_keys_of_a_person_table_is_not_flagged(
    db_session: Any,
) -> None:
    """The other half of the boundary: the reads a read path is built out of stay silent.

    A tripwire that fires on correct SQL is repaired by weakening it, and the
    casualty is the guard rather than the view. Two shapes are planted, and both
    are shapes this schema either has or would write next: a view reading `id` and
    `user_id` off a person table, and a view reading `enrollment.user_id`, which
    is what `section_roster` does and which the carried entry on the reveal's
    composition describes as "the whole point of the view".

    **The two keys are spelled out in `PLANTED_ALLOWED_KEYS` and not intersected
    with `JOIN_KEY_COLUMNS`**, which is a repair with a measurement behind it: the
    first version derived them from the allow-list, so shrinking the allow-list
    shrank the plant and both mutations named below left this green. That constant
    carries what it cost.

    **The offending view is planted in the same transaction as the two allowed
    ones**, and that is not decoration: silence is what a computation that has
    gone blind produces as well, so a control that only asserted an absence would
    be green with the rule deleted (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: dropping `id` or dropping `user_id`
    from `JOIN_KEY_COLUMNS`, either of which makes a roster-shaped view an
    offender — a red on correct SQL, which is the direction that gets a guard
    repaired by widening it back out to marked columns only.

    **What the roster-shaped half does *not* kill, stated because it would be easy
    to claim.** It does not catch widening `PERSON_TABLES` to "any table with a
    `user_id`": `user_id` is a join key either way, so `enrollment.user_id` stays
    allowed under both readings and this stays green. Other tests kill that
    mutation. What this half is, is a regression sample for the shape the real
    read path has — the one view in the schema this rule could most plausibly go
    red on by accident, planted so that it goes red *here*, in a test whose
    message says the read is legitimate, rather than in CI against
    `section_roster` itself.

    **The near miss it tolerates**: none beyond the shapes planted here; that is
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
    absent = [key for key in PLANTED_ALLOWED_KEYS if key not in on_identity]
    assert not absent, (
        f"`public.{PLANTED_ALIAS_TABLE}` has no {absent} column; it has {sorted(on_identity)}. The "
        "planted read below is spelled out rather than derived, so a renamed key is a named "
        "failure here instead of a sample that quietly stops testing anything."
    )
    select_keys = ", ".join(f"ui.{key}" for key in PLANTED_ALLOWED_KEYS)

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
        f"`{PLANTED_JOIN_KEY_VIEW}` reads {list(PLANTED_ALLOWED_KEYS)} off a person table and the "
        f"rule reports {sorted(findings[PLANTED_JOIN_KEY_VIEW])}. `JOIN_KEY_COLUMNS` currently "
        f"holds {list(JOIN_KEY_COLUMNS)}, so read the two lists against each other: a name planted "
        "here and missing there is a key that has been taken out of the allow-list, and a read "
        "view has to be able to join. A rule that forbids the key forbids the read path §4.1 "
        "depends on rather than the disclosure it is about."
    )
    assert not findings.get(PLANTED_ROSTER_SHAPE_VIEW), (
        f"`{PLANTED_ROSTER_SHAPE_VIEW}` reads `{ENROLLMENT_TABLE}.{ENROLLMENT_KEY_COLUMN}` — the "
        f"shape `section_roster` really has — and the rule reports "
        f"{sorted(findings[PLANTED_ROSTER_SHAPE_VIEW])}. `{ENROLLMENT_TABLE}` is not one of "
        f"{list(PERSON_TABLES)}, so nothing here should have looked at it at all; the Pulse-"
        "internal `user_id` is the design, and it is what makes a de-identified response "
        "addressable."
    )


# ---------------------------------------------------------------------------
# E1-12 — the web door's linkage table joins this file's subject matter.
# ---------------------------------------------------------------------------

# The table E1-12 adds and the column that identifies a person in it. `idp_subject`
# is the `sub` of a verified `id_token`: a stable per-person key at the identity
# provider, and the web door's exact counterpart to `user.lms_user_id`, which the
# carried entry measured as "a stable per-person key… flagged by nothing". The pair
# `(idp_issuer, idp_subject)` is unique and `person_id` is what it resolves to.
LINKAGE_TABLE = "web_login_subject"
LINKAGE_SUBJECT_COLUMN = "idp_subject"

# The whole of `JOIN_KEY_COLUMNS`, written out again as a literal. **The point is
# the duplication**: the pin below compares the constant against these three names,
# so widening the allow-list to admit a column of the new table — `person_id` is a
# foreign key and would pass the structural-key rule in
# `test_identity_separated_views.py` — cannot be done quietly. Changing the list is
# a change to this test in the same pull request, with the reason in it, which is
# what "moves deliberately" means for a hand-written inventory
# (`docs/MISTAKES.md` entry 35).
THE_THREE_STRUCTURAL_KEYS = ("id", "user_id", "lti_platform_id")


def test_the_web_login_linkage_table_is_swept_as_a_table_that_holds_a_person(
    migrated_engine: Any,
) -> None:
    """E1-12 criterion 5: the new table is inside this file's subject matter, not beside it.

    `web_login_subject` says which human an IdP subject is. That is the same class
    of fact `person` holds, and the fixed-point walk is what is supposed to notice —
    the table carries a foreign key to `person`, so `people_tables` reaches it
    without anybody adding a name to `PERSON_TABLES`.

    **Dies if the linkage is stored somewhere the walk cannot reach**: a column on
    `lti_platform`, a table keyed to `user_identity` by something other than a
    foreign key, a document column. Any of those leaves every rule in this module
    and every §4.1 sweep built on it computing over a set that does not include the
    place a person's IdP subject is stored — and the sweep would report success,
    because it looks at what it can reach.

    **Its control is the walk's own known members.** An empty or one-table walk
    satisfies nothing here, and a missing `person` table would make the reach a
    fact about nothing (`docs/MISTAKES.md` entry 3).
    """
    reached = people_tables(migrated_engine)
    missing = [name for name in PERSON_TABLES if name not in reached]
    assert not missing, (
        f"The walk did not even reach {missing}, the tables it starts from — it reached "
        f"{sorted(reached)}. Whatever it says about a new table is a fact about a broken "
        "reflection rather than about the schema."
    )
    assert LINKAGE_TABLE in reached, (
        f"`{LINKAGE_TABLE}` is not among the tables this file treats as holding a person: "
        f"{sorted(reached)}. E1-12 stores the mapping from an IdP `(issuer, subject)` pair to a "
        "`person` row there, which is the web door's whole answer to who somebody is. The walk "
        "collects anything with a foreign-key path to `person`, so a table it does not reach is "
        "either not linked to `person` by a key — in which case the linkage is expressed as "
        "something this schema cannot enforce — or not there at all."
    )


def test_the_web_login_linkage_tables_subject_key_carries_the_identity_marker(
    migrated_engine: Any,
) -> None:
    """E1-12 criterion 5: the marker is on the column the vocabulary cannot recognise.

    ADR 0022's convention is what every §4.1 reader is computed from, and the sweep
    at the top of this file finds a column by its *name*. `idp_subject` contains no
    fragment in `IDENTITY_NAME_FRAGMENTS` and never will: it is an opaque string a
    provider chose. So nothing above this line goes red if the marker is missing,
    and this is the assertion that does.

    **What the marker says, and why this column earns it.** It is the `sub` of a
    verified `id_token` — the web door's counterpart to `user.lms_user_id`, which
    `docs/tickets/e1/carried-from-e0.md` measured as the disclosure no identity rule
    in this repository sees: "a stable per-person key… a view returning it beside a
    comment lets an instructor resolve a named student in the LMS in one step, with
    every §4.1 guard green". The same is true at the provider, where the subject
    resolves to a directory entry.

    **Any of the three shapes counts**, as everywhere else in this file: a column
    comment, a name prefix, or a comment on the whole table, which is the shape D2
    chose because this table's columns are all of one kind. Pinning the mechanism
    here would make the implementer build to this file rather than to the ticket.

    **Dies if the table lands unmarked**, which is the state that costs something:
    the marker is what E0-10's views, this file's rules and the CI invariant pass
    are all computed from, so a column outside it is a column all three believe is
    safe to expose.
    """
    marked_columns = database_marked_columns(migrated_engine)
    assert marked_columns, (
        "Nothing in the migrated database carries the identity marker in any shape this file "
        "reads, so this test would be about the absence of a convention rather than about one "
        "table. The sweep at the top of this module is where that is diagnosed."
    )
    inspector = inspect(migrated_engine)
    present: set[str] = set()
    if LINKAGE_TABLE in inspector.get_table_names():
        present = {column["name"] for column in inspector.get_columns(LINKAGE_TABLE)}
    assert LINKAGE_SUBJECT_COLUMN in present, (
        f"`public.{LINKAGE_TABLE}` does not exist, or has no `{LINKAGE_SUBJECT_COLUMN}` column — "
        f"it has {sorted(present)}. E1-12 stores the provider's subject there, and this test "
        "cannot ask whether a column is marked before the column exists."
    )
    assert (LINKAGE_TABLE, LINKAGE_SUBJECT_COLUMN) in marked_columns, (
        f"`{LINKAGE_TABLE}.{LINKAGE_SUBJECT_COLUMN}` carries no identity marker in any shape this "
        f"file reads: no column comment containing {MARKER_TOKEN!r}, no comment on the table "
        f"containing it, no name beginning with one of {list(MARKER_PREFIXES)}. It is a stable "
        "per-person key at the identity provider and it matches no name fragment, so it is exactly "
        "the column ADR 0022's convention exists for and exactly the one the name-based sweep in "
        "this file cannot find on its own."
    )


def test_the_join_key_allow_list_is_still_the_three_structural_keys() -> None:
    """E1-12 criterion 5: E1-01's closed list stays closed, and a widening is deliberate.

    E1-01 replaced a list of forbidden names with an allow-list of keys, and the
    value of an allow-list is that it is short and that nothing can be added to it
    by accident. E1-12 is the first ticket to add a table the list governs, and the
    cheapest way to make a new view of it pass would be to add one of its columns
    here — `person_id` is a foreign key, so it would satisfy
    `test_every_join_key_the_bound_column_mechanism_allows_is_a_structural_key`
    in `test_identity_separated_views.py` and change nothing else in this suite.

    So the list is pinned against a literal written out beside it. This is not a
    test of the implementation and cannot be made to fail by one: it is the
    tripwire that makes moving a hand-written inventory a deliberate act, in the
    same pull request, with a sentence saying what a view may now read
    (`docs/MISTAKES.md` entry 35).

    **A legitimate addition changes this test**, and that is the intended cost. What
    it must not be changed for: a view of `web_login_subject`. No view reads that
    table today and the web door reaches it through a definer function instead —
    the whole reason the closed list did not have to move for this ticket.
    """
    assert tuple(JOIN_KEY_COLUMNS) == THE_THREE_STRUCTURAL_KEYS, (
        f"`JOIN_KEY_COLUMNS` is {list(JOIN_KEY_COLUMNS)}; this pin expects "
        f"{list(THE_THREE_STRUCTURAL_KEYS)}. Each of the three names a *row* and none of them "
        "names a person, which is the property that makes the list safe to be short. If a fourth "
        "is genuinely needed, change this test in the same pull request and say what a view may "
        "now read out of `user`, `user_identity`, `person` — and, since E1-12, out of the web "
        "door's linkage table."
    )


# ---------------------------------------------------------------------------
# Batch A — the two things E1-01 deferred (`docs/tickets/e1/deferred.md`, items 1
# and 2), closed here for the reason everything else in this file is here: the
# vocabulary and both whole-row readings are defined above, so the rule that
# widens them belongs beside them (`docs/MISTAKES.md` entry 13).
#
# The two are different kinds of thing, and reading them as one would be a
# mistake:
#
#   - **item 1 is a hole in a guard.** The catalog's whole-row dependency row is
#     conditional on the view naming no column of the same table, so the join form
#     of a whole-row read was recorded at column grain, where it looks like an
#     ordinary key read. `decompiled_whole_row_reads` above is the second reading
#     and both whole-row rules take the union of the two; the controls below plant
#     the hidden form against each of those two rules in turn, then the two near
#     misses, then the token boundary the reading rests on.
#   - **item 2 is not a guard but a report.** Every sweep above is phrased over a
#     name or a marker, so a table the walk reaches whose columns none of them
#     recognises is passed over in silence — which is exactly how
#     `web_login_subject` would have shipped unmarked, and E1-12's entry in
#     `deferred.md` says so in as many words. `unclassified_reached_tables` names
#     such a table instead, and `REACHED_TABLES_THAT_CARRY_NOTHING` is where the
#     ones the silence is acceptable over are recorded — each with the columns the
#     judgement was made against, which is what makes the entry expire rather than
#     exempt a name forever, and with the reason a reviewer reads when it does.
# ---------------------------------------------------------------------------

# The views item 1's controls plant, named for the batch so that one surviving a
# fixture change is traceable to the test that made it.
PLANTED_JOIN_HIDDEN_VIEW = "e1_batch_a_planted_join_hidden_view"
PLANTED_JOIN_HIDDEN_MARKED_VIEW = "e1_batch_a_planted_join_hidden_marked_view"
PLANTED_JOIN_NAMED_COLUMN_VIEW = "e1_batch_a_planted_join_named_column_view"
PLANTED_JOIN_OTHER_WHOLE_VIEW = "e1_batch_a_planted_join_other_whole_view"
PLANTED_ALIAS_BOUNDARY_VIEW = "e1_batch_a_planted_alias_boundary_view"

# The two binding shapes a security review found the first version of the binder
# blind to, and the near miss each is planted beside. The comma-join probe is the
# reviewer's own statement; the `ONLY` pair is the shape the sibling binder in
# `test_identity_separated_views.py` already read, so the two disagreed.
PLANTED_COMMA_JOIN_VIEW = "e1_batch_a_planted_comma_join_view"
PLANTED_COMMA_JOIN_NAMED_VIEW = "e1_batch_a_planted_comma_join_named_view"
PLANTED_ONLY_FORM_VIEW = "e1_batch_a_planted_only_form_view"
PLANTED_ONLY_FORM_NAMED_VIEW = "e1_batch_a_planted_only_form_named_view"

# A real table this rule does not guard, joined to a person table so that the near
# misses below are the shapes they claim to be. `course` is Pulse's own org
# structure (SPEC §2.1), it is in neither `PERSON_TABLES` nor the marked set, and
# each test that uses it asserts that before believing an absence — a near miss
# planted on a table the rule turns out to guard proves the opposite of what it
# claims.
UNGUARDED_JOIN_TABLE = "course"

# The four aliases the boundary control binds, and the whole point of them is the
# two overlaps: `us` starts with `u` and `ur` ends with `r`, while `u` and `r` are
# the two bound to the guarded table. Written out rather than generated, because a
# control whose subject is derived from the thing it guards cannot notice that
# thing changing — the note on `PLANTED_ALLOWED_KEYS` above carries what that cost
# the last time.
GUARDED_PREFIX_ALIAS = "u"
OTHER_ALIAS_STARTING_WITH_IT = "us"
GUARDED_SUFFIX_ALIAS = "r"
OTHER_ALIAS_ENDING_WITH_IT = "ur"

# The tables item 2's control plants, and the column name it plants on both.
# `external_ref` is not this file's invention: ADR 0022's Consequences name it as
# one of the identity columns the fragment set "still cannot see", beside `sis`,
# `banner`, `initials` and `dob`. So the plant is the record's own example, and the
# control asserts that the fragment rule really is silent about it rather than
# assuming so.
PLANTED_UNRECOGNISED_TABLE = "e1_batch_a_planted_unrecognised_table"
PLANTED_UNRECOGNISED_MARKED_TABLE = "e1_batch_a_planted_unrecognised_marked_table"
PLANTED_UNRECOGNISED_COLUMN = "external_ref"

# The column the pin's control adds to a recorded table. It matches no fragment in
# `IDENTITY_NAME_FRAGMENTS` deliberately: a column the sweeps could see on their
# own would take the table out of the mapping by the recognition rule and the
# control would be proving that instead of the pin.
PLANTED_DRIFT_COLUMN = "e1_batch_a_planted_note"


class CarriesNothing(NamedTuple):
    """One recorded table: the columns the reason was written against, and the reason.

    **The columns are half of the record and not decoration**, and a security
    review is what put them here. Without them an entry exempts a *name* forever:
    `enrollment` is recorded as carrying nothing about the person in it, a later
    ticket adds `last_seen_email` or a free-text note, and the report above stays
    green because the exemption was written against a table that no longer exists
    in the shape it was judged in. With them, the first column added expires the
    entry and a human re-reads the reason — which is the only thing the reason was
    ever worth.
    """

    columns: tuple[str, ...]
    reason: str


# Every table the fixed-point walk reaches that no rule in this file recognises
# anything on, with the columns that was judged against and the reason it is
# acceptable. **This is a record, not an exemption**: a table listed here is still
# swept by everything above, and all the entry claims is that the name-and-marker
# sweeps are correctly *silent* about it rather than blind to it.
#
# **Silent is not the same as harmless, and one entry here is the proof.** `user`
# holds a key that resolves a named student at the platform in one step; what
# makes the silence acceptable there is not the row's contents but the grants and
# the view rule, and its reason says so. An entry whose answer is "something else
# holds this" must name the something else — a reason that says "nothing to see"
# where that is untrue is the record this file most needs not to carry
# (`docs/MISTAKES.md` entry 1).
#
# Three directions are asserted, because a one-directional inventory rots in
# silence (the closed-set lesson: a closed-set guard is defeated one level out).
# `test_every_table_the_person_walk_reaches_is_recognised_or_recorded_as_carrying_
# nothing` requires every reached table to be recognised or listed here;
# `test_every_table_recorded_as_carrying_nothing_is_still_reached_and_still_
# unrecognised` requires every name here to be a table the walk still reaches, to
# be one nothing recognises, and to carry exactly the columns its reason was
# written against. So a dropped table, a table that gained a marker and a table
# that grew a column are three named reds rather than a line nobody re-reads.
#
# The reasons are one line each and they are what a reviewer reads when the table
# next changes: a table that grows a column holding a person belongs in the marker
# convention, not in a longer sentence here.
REACHED_TABLES_THAT_CARRY_NOTHING: dict[str, CarriesNothing] = {
    "user": CarriesNothing(
        ("id", "lms_user_id", "lti_platform_id"),
        "Not silent because there is nothing here: `lms_user_id` is the LTI `sub`, an opaque "
        "platform key that names a student in the LMS one step out, and no rule in this file "
        "sees it. What holds it is grant separation — `pulse_app` is granted no `SELECT` on this "
        "table — and the bound-column rule, which admits only the structural keys and never this "
        "one.",
    ),
    "audit_log": CarriesNothing(
        ("action", "actor_person_id", "case_id", "id", "occurred_at", "subject_user_id"),
        "References to people and no identity payload: an actor, a subject, a case, an action "
        "token and a timestamp.",
    ),
    "enrollment": CarriesNothing(
        (
            "ended_on",
            "id",
            "lms_window_end",
            "lms_window_start",
            "section_id",
            "started_on",
            "user_id",
        ),
        "A section membership: the two keys it joins on and the two dated pairs the enrollment "
        "window is derived from, and nothing about the person in it.",
    ),
    "lead_faculty_mapping": CarriesNothing(
        ("course_id", "id", "person_id"),
        "Two foreign keys, a person and a course, and no other column.",
    ),
    # The two E2-05 adds, and the first entries here that were written before
    # the tables existed. They are the reason `people_tables`' own docstring no
    # longer says `answer` is hypothetical: `response.user_id` puts `response`
    # one hop from `user` and `answer.response_id` puts `answer` two, so the
    # fixed-point walk E0-10 built for exactly this case reaches both the moment
    # E2-05's migration runs. Neither carries a name the vocabulary knows, so
    # without these two entries the report would name them and the repair would
    # be on the other side of the test wall from the ticket that caused it
    # (`docs/MISTAKES.md` entry 22).
    #
    # **E2-08 makes it three**, and it is the walk rather than the table that
    # moved: `classification.answer_id` is ADR 0055's promised reference, added by
    # that ticket, so `answer_id` puts `classification` three hops from `user` and
    # the fixed point reaches a table it had never reached before. The row itself
    # is unchanged in what it is about — a verdict — and the reachability is a
    # statement about foreign keys rather than about access: E2-08 grants that
    # table no privilege at all, and it keeps the `SELECT, INSERT` ADR 0055 gave
    # it. `docs/disputes/E2-08-04.md` is the record.
    "response": CarriesNothing(
        (
            "first_submitted_at",
            "id",
            "is_valid",
            "last_submitted_at",
            "section_id",
            "user_id",
            "week_id",
        ),
        "The three keys SPEC §8's uniqueness rule is written over — a student, a section and a "
        "week — and the two submission timestamps, and nothing about the person. What holds the "
        "student's identity is the same thing that holds it on `enrollment`: `user_id` is a "
        "foreign key, and the identity behind it sits on `user_identity`, which `pulse_app` is "
        "granted no `SELECT` on. Note that this is the table SPEC §4 is written about — the "
        "de-identification rules are about what a *view* of it may carry, which the bound-column "
        "rule above governs, not about a column on the row. The column pin expired this entry "
        "once already and did exactly what it is for: E2-08 added `is_valid`, §3.3's verdict "
        "about the submission as a whole — a boolean about a week, carrying nothing about who "
        "submitted it, and the column §3.4's participation score reads "
        "(`docs/disputes/E2-08-04.md`).",
    ),
    "answer": CarriesNothing(
        ("comment_text", "id", "question_id", "rating", "response_id", "workload_hours"),
        "Two foreign keys and the three value columns, exactly one of which a row holds. "
        "`comment_text` is a student's own words and can name anybody at all — that is why §5.2 "
        "moderates it and §4 randomises its display order and never shows a timestamp beside it "
        "— but it is not an identity *column* in this convention's sense: it holds no key to a "
        "person, and marking it would put every comment in the set the identity-separated views "
        "may not read, which is the opposite of what §5.1 requires of the instructor report.",
    ),
    "classification": CarriesNothing(
        ("answer_id", "classified_at", "id", "model_id", "prompt_version", "task", "verdict"),
        "A model's verdict about one comment, with the prompt version and model ID SPEC §7.4 "
        "requires of it, and `answer_id` — E2-08's addition, ADR 0055's promised reference — "
        "which names the comment rather than the person. The identity is two more hops away "
        "through `answer.response_id` and `response.user_id`, and it is `user_identity` that "
        "holds it, which `pulse_app` is granted no `SELECT` on. Marking anything here would put "
        "every verdict in the set the identity-separated views may not read, which is the "
        "opposite of what §5.1 and §6.1 need, so an entry is the right record and a marker is "
        "not. `pulse_app` reads and appends this table and can neither update nor delete a row "
        "(ADR 0055), which is what makes the audit trail an audit trail; what a *view* over it "
        "may join to is the bound-column rule above, not this entry.",
    ),
    "role_assignment": CarriesNothing(
        (
            "college_id",
            "course_id",
            "department_id",
            "id",
            "institution_id",
            "permits_launch",
            "permits_web_login",
            "person_id",
            "reports_to",
            "role",
            "section_id",
        ),
        "A role token, the scope keys the role is held over, and two booleans about which doors "
        "it opens; the person is a foreign key.",
    ),
}


def table_marker_carried_by(engine: Any, table_name: str) -> bool:
    """Does `table_name` carry ADR 0022's third shape — the marker on the whole table?

    Answered through `marked` rather than by reading the comment here, which is
    `docs/MISTAKES.md` entry 13 rather than fastidiousness: that function refuses
    a table comment on `user` — ADR 0001 puts the key and the platform reference
    there precisely so they are *not* identity — and a second implementation of
    the third shape would be the copy that does not carry that refusal. The empty
    column name is what isolates the shape: no prefix can match it and no column
    comment is passed, so the table comment is the only thing that can answer yes.

    **It is redundant today, on every table, and that is stated rather than left
    to be discovered** (`docs/MISTAKES.md` entry 14): `marked` applies a table
    comment to each of the table's columns, so a table carrying the third shape is
    already in `database_marked_columns` and no mutation of this function alone
    changes any answer below. It is written out because that redundancy is a
    property of how the marked-column set happens to project a table-level marker
    and not of the rule being asked — a `database_marked_columns` that ever
    reported the table rather than its columns would silently take the third shape
    out of the classification, and this is the line that would not move with it.
    """
    comment = (inspect(engine).get_table_comment(table_name) or {}).get("text")
    return marked(table_name, "", None, comment)


def pinned_column_drift(engine: Any) -> dict[str, tuple[list[str], list[str]]]:
    """Every recorded table whose live columns are not the ones its reason was judged against.

    `table -> (pinned, live)`, so a failure can print both and a reader can see
    which column arrived. Tables the walk no longer reaches, or that are gone
    altogether, are skipped here and caught by the reachability half beside this
    one — two questions, two messages, and this one has nothing useful to say
    about a table that is not there.

    The comparison is over the sorted names and nothing else: not the types, not
    the order, not the constraints. What the entry is a record of is *which
    columns a human read before writing that reason*, and a column arriving is the
    event that makes them read it again. A type change on an existing column does
    not, which is why this does not look at types and why saying so is worth a
    line (`docs/MISTAKES.md` entry 14).
    """
    inspector = inspect(engine)
    present = set(inspector.get_table_names())
    drifted: dict[str, tuple[list[str], list[str]]] = {}
    for name, record in REACHED_TABLES_THAT_CARRY_NOTHING.items():
        if name not in present:
            continue
        live = sorted(column["name"] for column in inspector.get_columns(name))
        if live != sorted(record.columns):
            drifted[name] = (sorted(record.columns), live)
    return drifted


def unclassified_reached_tables(engine: Any) -> set[str]:
    """Every table the person walk reaches that no rule here recognises anything on.

    E1-12's half of E1-01's second deferred item, in the words `deferred.md` gives
    it: "the sweep reports a table it reached whose column names it recognises none
    of, rather than passing over it". `web_login_subject` is the table that made
    the case. It carries a foreign key to `person`, so the fixed-point walk reaches
    it; its per-person key is called `idp_subject`, which matches no fragment in
    `IDENTITY_NAME_FRAGMENTS` and never will; so nothing in this repository would
    have gone red had it shipped unmarked, and the only thing holding it is a test
    somebody thought to write.

    A table is recognised when the fragment rule or any marker shape has something
    to say about it — `identity_bearing_columns` and `database_marked_columns`
    called live, never a copy of either (`docs/MISTAKES.md` entry 19), and
    `table_marker_carried_by` for the shape that is a comment on the table.
    Recognised does **not** mean safe: an unmarked column whose name matches a
    fragment is recognised here and is reported by the tripwire at the top of this
    file, which is the correct division — this asks whether the sweeps can see the
    table at all.

    What is left over is either a table the silence is acceptable over, in which
    case its name, its columns and the reason belong in
    `REACHED_TABLES_THAT_CARRY_NOTHING`, or a table like `web_login_subject`
    arriving unmarked, in which case the marker is missing and this is what says
    so. The two cannot be told apart mechanically — `external_ref` and a student
    number are the same object to Postgres, which is ADR 0022's own sentence — so
    the answer is a human's and the report is what asks for it.
    """
    recognised = {table for table, _ in identity_bearing_columns(engine)} | {
        table for table, _ in database_marked_columns(engine)
    }
    return {
        name
        for name in people_tables(engine)
        if name not in recognised
        and not table_marker_carried_by(engine, name)
        and name not in REACHED_TABLES_THAT_CARRY_NOTHING
    }


@pytest.mark.invariant
def test_a_whole_row_read_hidden_by_a_join_is_flagged_though_the_catalog_records_a_column(
    db_session: Any,
) -> None:
    """E1-01 deferred item 1: the whole-row spelling the catalog's own row does not survive.

    Postgres records a reference to a row as a value at `refobjsubid = 0`, and
    drops that row the moment the same view also names any column of the same
    table. A join condition names one. So

        SELECT u.id, to_jsonb(u) AS platform_ref
        FROM public.enrollment e
        JOIN public."user" u ON u.id = e.user_id

    is recorded as a read of `user.id` and of nothing else, while carrying every
    column `user` has — `lms_user_id` among them, which resolves a named student
    at the platform in one step. `VIEW_TABLE_DEPENDENCIES` returns no row for it,
    so both whole-row rules in this module were silent; the marker-based one would
    have been silent regardless, because `user` carries no marked column by
    construction.

    **The asymmetry is the whole deferred item, so it is asserted rather than
    described.** The catalog query must still be silent on this view *and* the new
    reading must report it, and it is the pair that says the second reading adds
    something. If the silence assertion ever fails, Postgres has begun keeping the
    whole-row row beside the column one: this item is moot and
    `decompiled_whole_row_reads` is redundant rather than wrong, which is worth
    knowing before anybody deletes either of the two.

    **The plant names a column of `"user"` deliberately.** `to_jsonb(u)` alone is
    E0-34's probe and is already caught — the control above it plants exactly
    that, and its docstring records the boundary this test moves. The named column
    is what makes Postgres drop the whole-row row, so a plant without one would be
    green against the guard as it stood before this change and would prove nothing.

    **The mutation it exists to survive**: deleting `decompiled_whole_row_reads`
    from `person_table_rows_read_whole`, or narrowing its pattern to the bare
    relation name so that an aliased join escapes it.
    **The near misses it tolerates**, each planted in a test of its own below: the
    same join reading only named columns of `"user"`, and a whole-row read of a
    table this rule does not guard sitting beside a person table in one view.

    Everything is planted inside `db_session`'s transaction and rolled back with
    it, so `public` is unchanged at the end and the assertions run in the same
    transaction as the plant (`docs/MISTAKES.md` entry 20).
    """
    session = db_session
    assert ENROLLMENT_TABLE in inspect(session.connection()).get_table_names(), (
        f"There is no `{ENROLLMENT_TABLE}` table to join through, so the join form this test is "
        "about cannot be planted at all."
    )

    hidden = f'CREATE VIEW public.{PLANTED_JOIN_HIDDEN_VIEW} AS SELECT {GUARDED_PREFIX_ALIAS}.id, to_jsonb({GUARDED_PREFIX_ALIAS}) AS {PLANTED_WHOLE_ROW_ALIAS} FROM public.{ENROLLMENT_TABLE} e JOIN public."{USER_TABLE}" {GUARDED_PREFIX_ALIAS} ON {GUARDED_PREFIX_ALIAS}.id = e.{ENROLLMENT_KEY_COLUMN}'  # noqa: S608
    session.execute(text(hidden))

    connection = session.connection()
    whole = f"{USER_TABLE}.*"

    at_column_grain = [tuple(row) for row in connection.execute(text(VIEW_COLUMN_DEPENDENCIES))]
    assert (PLANTED_JOIN_HIDDEN_VIEW, USER_TABLE, "id") in at_column_grain, (
        f"Postgres records no dependency of `{PLANTED_JOIN_HIDDEN_VIEW}` on `{USER_TABLE}.id`, so "
        "the planted view either was not created or is not the shape this test believes it is — "
        "and the named column is the whole mechanism here, because it is what makes the catalog "
        "drop the whole-row row. Every assertion below would be about a view nothing is looking at."
    )

    at_table_grain = [tuple(row) for row in connection.execute(text(VIEW_TABLE_DEPENDENCIES))]
    assert (PLANTED_JOIN_HIDDEN_VIEW, USER_TABLE) not in at_table_grain, (
        f"The catalog records a whole-row dependency of `{PLANTED_JOIN_HIDDEN_VIEW}` on "
        f"`{USER_TABLE}` after all: it reported {sorted(at_table_grain)}. That is *good* news and "
        "it retires this deferred item — Postgres has begun keeping the `refobjsubid = 0` row "
        "beside the column one, so `VIEW_TABLE_DEPENDENCIES` sees the join form on its own and "
        "`decompiled_whole_row_reads` is redundant rather than wrong. Read that measurement before "
        "changing anything: this assertion is the record of the behaviour the second reading "
        "exists for, and if it has changed the rest of this file should be simplified deliberately "
        "rather than left carrying a reading nothing needs."
    )

    detected = decompiled_whole_row_reads(connection, {USER_TABLE})
    assert (PLANTED_JOIN_HIDDEN_VIEW, USER_TABLE) in detected, (
        f"`{PLANTED_JOIN_HIDDEN_VIEW}` takes `to_jsonb` of a `{USER_TABLE}` row through a join and "
        f"the decompiled reading does not report it; it reported {sorted(detected)}. Postgres "
        f"decompiles every whole-row form to `{GUARDED_PREFIX_ALIAS}.*`, and the reading looks for "
        "that spelling against the tokens the definition's FROM and JOIN clauses bind to the "
        f"table. The definition it read is:\n\n{view_definitions(connection).get(PLANTED_JOIN_HIDDEN_VIEW)!r}"
    )

    read_whole = person_table_rows_read_whole(connection).get(PLANTED_JOIN_HIDDEN_VIEW, set())
    assert whole in read_whole, (
        f"The decompiled reading reports `{PLANTED_JOIN_HIDDEN_VIEW}` and the strict rule's "
        f"whole-row half does not: it reported {sorted(read_whole)}. Then the new reading is "
        "computed and discarded, which is the failure mode a second guard has that a first one "
        "does not — it is the union of the two readings that has to reach the rule, or the item is "
        "closed in a helper nobody consults."
    )

    reported = person_table_reads_reported(connection)
    assert any(
        PLANTED_JOIN_HIDDEN_VIEW in sentence and whole in sentence for sentence in reported
    ), (
        f"`{PLANTED_JOIN_HIDDEN_VIEW}` reads `{whole}` and the sentence the invariant prints does "
        f"not name it: it reported {reported}. The chain fold is seeded from both grains and this "
        "is the finding travelling all the way to "
        "`test_no_view_reads_a_column_of_a_person_table_outside_the_join_keys`, which is the test "
        "CI reads. A finding that stops short of it is a finding nobody is told about."
    )


@pytest.mark.invariant
def test_a_whole_row_read_hidden_by_a_join_reaches_the_marker_scoped_rule_as_well(
    db_session: Any,
) -> None:
    """The same closure on the other whole-row rule, which guards a different set.

    Two rules in this module ask "does a view read this row whole", and they scope
    themselves differently on purpose: `whole_row_identity_reads` asks it of the
    tables the *marker* names, and `person_table_rows_read_whole` asks it of those
    plus the tables that hold a person. The join form was invisible to both, and a
    repair wired into one of them would leave the other exactly as it was — which
    is the shape `docs/MISTAKES.md` entry 13 records: a hazard worked around in
    one of the two places facing it.

    So the plant here is over a **marked** table rather than over `user`.
    `user_identity` carries `identity_name` and `identity_email` and is what
    E0-34's rule was written about; a view naming one of its columns and taking
    its row is recorded at column grain only, exactly as on `user`, and this is the
    assertion that says the second reading reaches that rule too.

    **The mutation it exists to survive**: dropping `decompiled_whole_row_reads`
    from `whole_row_identity_reads` while leaving it in
    `person_table_rows_read_whole` — a mutation every other control in this batch
    survives, because every other plant is over `user`, which carries no marked
    column by construction.
    """
    session = db_session
    connection = session.connection()
    marked_tables = {table for table, _ in database_marked_columns(connection)}
    assert PLANTED_ALIAS_TABLE in marked_tables, (
        f"`{PLANTED_ALIAS_TABLE}` carries no marked column, so it is outside the scope "
        "`whole_row_identity_reads` guards and this plant would prove nothing about that rule. It "
        f"guards {sorted(marked_tables)}; the sweep at the top of this module is where a missing "
        "marker is diagnosed."
    )
    assert ENROLLMENT_TABLE in inspect(connection).get_table_names(), (
        f"There is no `{ENROLLMENT_TABLE}` table to join through, so the join form cannot be "
        "planted at all."
    )

    hidden = f"CREATE VIEW public.{PLANTED_JOIN_HIDDEN_MARKED_VIEW} AS SELECT ui.id, to_jsonb(ui) AS {PLANTED_WHOLE_ROW_ALIAS} FROM public.{ENROLLMENT_TABLE} e JOIN public.{PLANTED_ALIAS_TABLE} ui ON ui.{ENROLLMENT_KEY_COLUMN} = e.{ENROLLMENT_KEY_COLUMN}"  # noqa: S608
    session.execute(text(hidden))

    connection = session.connection()
    at_column_grain = [tuple(row) for row in connection.execute(text(VIEW_COLUMN_DEPENDENCIES))]
    assert (PLANTED_JOIN_HIDDEN_MARKED_VIEW, PLANTED_ALIAS_TABLE, "id") in at_column_grain, (
        f"Postgres records no dependency of `{PLANTED_JOIN_HIDDEN_MARKED_VIEW}` on "
        f"`{PLANTED_ALIAS_TABLE}.id`, so the planted view is not the shape this test believes it "
        "is — and the named column is the mechanism, because it is what makes the catalog drop the "
        "whole-row row."
    )

    at_table_grain = [tuple(row) for row in connection.execute(text(VIEW_TABLE_DEPENDENCIES))]
    assert (PLANTED_JOIN_HIDDEN_MARKED_VIEW, PLANTED_ALIAS_TABLE) not in at_table_grain, (
        f"The catalog records a whole-row dependency of `{PLANTED_JOIN_HIDDEN_MARKED_VIEW}` on "
        f"`{PLANTED_ALIAS_TABLE}` after all: it reported {sorted(at_table_grain)}. Postgres has "
        "begun keeping the `refobjsubid = 0` row beside the column one, which retires this whole "
        "batch's first item — read that measurement before changing anything here."
    )

    leaking = whole_row_identity_reads(connection)
    assert f"{PLANTED_JOIN_HIDDEN_MARKED_VIEW}: {PLANTED_ALIAS_TABLE}" in leaking, (
        f"`{PLANTED_JOIN_HIDDEN_MARKED_VIEW}` takes the whole row of a table the identity marker "
        f"names, through a join, and the marker-scoped rule does not report it: it reported "
        f"{leaking}. That view carries every column `{PLANTED_ALIAS_TABLE}` has — a student's name "
        "and email address — and the catalog is silent about it by the assertion above, so with "
        "this rule silent as well the shape is reported by nothing at this grain. The second "
        "reading has to reach *both* whole-row rules; wired into one of the two it closes half the "
        "item and leaves the other exactly where it was."
    )


@pytest.mark.invariant
def test_a_join_that_reads_only_named_columns_of_a_person_table_is_not_read_as_a_whole_row(
    db_session: Any,
) -> None:
    """The first near miss: the same join, without the whole-row form, stays silent.

    A guard that fires on correct SQL is repaired by weakening it, and the
    casualty is the guard rather than the view. `SELECT u.id … JOIN public."user"
    u ON u.id = e.user_id` is the shape a roster view has, and it must not become
    a whole-row finding merely because the reading now looks at the view's text
    instead of at a dependency row.

    **The offender is planted in the same transaction**, and it is not decoration:
    silence is also what a reading that has gone blind produces, so a control that
    asserted only an absence would be green with `decompiled_whole_row_reads`
    deleted (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: widening the pattern from
    `<token>.*` to "the token appears at all", which is the obvious way to write
    this reading and turns every aliased join into a whole-row finding.
    """
    session = db_session
    assert (
        ENROLLMENT_TABLE in inspect(session.connection()).get_table_names()
    ), f"There is no `{ENROLLMENT_TABLE}` table, so neither half of this pair can be planted."

    hidden = f'CREATE VIEW public.{PLANTED_JOIN_HIDDEN_VIEW} AS SELECT {GUARDED_PREFIX_ALIAS}.id, to_jsonb({GUARDED_PREFIX_ALIAS}) AS {PLANTED_WHOLE_ROW_ALIAS} FROM public.{ENROLLMENT_TABLE} e JOIN public."{USER_TABLE}" {GUARDED_PREFIX_ALIAS} ON {GUARDED_PREFIX_ALIAS}.id = e.{ENROLLMENT_KEY_COLUMN}'  # noqa: S608
    named = f'CREATE VIEW public.{PLANTED_JOIN_NAMED_COLUMN_VIEW} AS SELECT {GUARDED_PREFIX_ALIAS}.id AS member FROM public.{ENROLLMENT_TABLE} e JOIN public."{USER_TABLE}" {GUARDED_PREFIX_ALIAS} ON {GUARDED_PREFIX_ALIAS}.id = e.{ENROLLMENT_KEY_COLUMN}'  # noqa: S608
    session.execute(text(hidden))
    session.execute(text(named))

    connection = session.connection()
    detected = decompiled_whole_row_reads(connection, {USER_TABLE})

    assert (PLANTED_JOIN_HIDDEN_VIEW, USER_TABLE) in detected, (
        f"The reading reports nothing for `{PLANTED_JOIN_HIDDEN_VIEW}`, which takes `to_jsonb` of "
        f"a `{USER_TABLE}` row through the same join. It is blind, and the absence asserted below "
        "is a fact about the computation rather than about the view it names."
    )
    assert (PLANTED_JOIN_NAMED_COLUMN_VIEW, USER_TABLE) not in detected, (
        f"`{PLANTED_JOIN_NAMED_COLUMN_VIEW}` reads one named column of `{USER_TABLE}` through a "
        "join and the whole-row reading reports it as reading the row. That is a red on the shape "
        "every roster view has, and the repair somebody reaches for under that pressure is "
        "deleting the reading. The definition it read is:\n\n"
        f"{view_definitions(connection).get(PLANTED_JOIN_NAMED_COLUMN_VIEW)!r}"
    )
    assert not person_table_rows_read_whole(connection).get(PLANTED_JOIN_NAMED_COLUMN_VIEW), (
        f"The strict rule's whole-row half reports `{PLANTED_JOIN_NAMED_COLUMN_VIEW}`, which reads "
        "a join key by name and no row at all. The column-grain half is what answers for a named "
        "column, and it allows this one because `id` is in `JOIN_KEY_COLUMNS`."
    )


@pytest.mark.invariant
def test_a_whole_row_read_hidden_by_a_comma_join_is_flagged(db_session: Any) -> None:
    """The binding shape a security review walked the first version of the binder past.

    The reviewer's probe, copied whole rather than described:

        SELECT u.id, to_jsonb(u) AS payload
        FROM enrollment e, "user" u
        WHERE u.id = e.user_id

    It is the same exposure as the explicit-join form — every column `user` has,
    carried under one harmless-looking output column, with the whole-row
    dependency row dropped because `u.id` is named. What defeated the reading was
    not the star but the *binding*: a member of a comma-separated `FROM` list has
    no `FROM` and no `JOIN` in front of it, so the binder bound no `u`,
    `to_jsonb(u.*)` matched no token, and `decompiled_whole_row_reads` returned
    nothing. Only the text sweep next door still caught it, which is one guard
    where the pair is supposed to be two.

    **The binding is asserted before the flag**, and that ordering is the point:
    the star is in the text either way, so a green here that came from a lucky
    substring match would say nothing about the repair. `relation_tokens_bound_to`
    must bind `u` to `"user"` out of a comma list, and only then is the flag
    evidence of anything.

    **What the decompiler does with a comma join is read rather than assumed.**
    Postgres deparses each member of the join tree's `FROM` list and joins them
    with commas, so a stored comma join is expected to come back as one — but the
    control does not rest on that: it asserts the alias is bound and the read is
    flagged, which holds whichever canonical form the text turns out to be, and
    the definition is printed in every failure message so the run settles the
    question rather than this docstring (`docs/MISTAKES.md` entry 3).

    **The near miss is planted in the same transaction**: the same comma join
    reading only a named column must stay silent, or the repair is a binder that
    reports every comma list as a whole-row read.

    **The mutation it exists to survive**: dropping `,\\s*` from the introducer
    alternation in `relation_tokens_bound_to`, which is the state the reviewer
    found and which leaves the explicit-join controls above green.
    """
    session = db_session
    assert (
        ENROLLMENT_TABLE in inspect(session.connection()).get_table_names()
    ), f"There is no `{ENROLLMENT_TABLE}` table, so neither half of this pair can be planted."

    hidden = f'CREATE VIEW public.{PLANTED_COMMA_JOIN_VIEW} AS SELECT {GUARDED_PREFIX_ALIAS}.id, to_jsonb({GUARDED_PREFIX_ALIAS}) AS payload FROM public.{ENROLLMENT_TABLE} e, public."{USER_TABLE}" {GUARDED_PREFIX_ALIAS} WHERE {GUARDED_PREFIX_ALIAS}.id = e.{ENROLLMENT_KEY_COLUMN}'  # noqa: S608
    named = f'CREATE VIEW public.{PLANTED_COMMA_JOIN_NAMED_VIEW} AS SELECT {GUARDED_PREFIX_ALIAS}.id AS member FROM public.{ENROLLMENT_TABLE} e, public."{USER_TABLE}" {GUARDED_PREFIX_ALIAS} WHERE {GUARDED_PREFIX_ALIAS}.id = e.{ENROLLMENT_KEY_COLUMN}'  # noqa: S608
    session.execute(text(hidden))
    session.execute(text(named))

    connection = session.connection()
    definitions = view_definitions(connection)
    definition = definitions.get(PLANTED_COMMA_JOIN_VIEW, "")

    assert f"{GUARDED_PREFIX_ALIAS}.*" in definition, (
        f"The decompiled definition carries no `{GUARDED_PREFIX_ALIAS}.*`, so the whole-row form "
        "did not survive decompilation in the spelling this whole reading is built on and the "
        f"binding assertion below would be about the wrong thing. It reads:\n\n{definition!r}"
    )
    tokens = relation_tokens_bound_to(definition, USER_TABLE)
    assert GUARDED_PREFIX_ALIAS in tokens, (
        f"The binder does not bind `{GUARDED_PREFIX_ALIAS}` to `{USER_TABLE}` in a comma-separated "
        f"FROM list; it bound {sorted(tokens)}. That is the security review's finding exactly: a "
        "comma-list member has no `FROM` and no `JOIN` in front of it, so a binder reading only "
        f"those two keywords never learns what `{GUARDED_PREFIX_ALIAS}` is, and the whole-row read "
        f"below is invisible to it. The definition reads:\n\n{definition!r}"
    )

    detected = decompiled_whole_row_reads(connection, {USER_TABLE})
    assert (PLANTED_COMMA_JOIN_VIEW, USER_TABLE) in detected, (
        f"`{PLANTED_COMMA_JOIN_VIEW}` takes the whole row of `{USER_TABLE}` through a comma join "
        f"and the reading does not report it; it reported {sorted(detected)}. The alias is bound by "
        "the assertion above and the star is in the text by the one above that, so the failure is "
        "in the match rather than in the binding."
    )
    assert (PLANTED_COMMA_JOIN_NAMED_VIEW, USER_TABLE) not in detected, (
        f"`{PLANTED_COMMA_JOIN_NAMED_VIEW}` reads one named column of `{USER_TABLE}` through the "
        "same comma join and the reading calls it a whole-row read. A binder taught to read comma "
        "lists must not also start reporting every relation in one; that is a red on correct SQL, "
        "which is the direction that gets a guard weakened. The definition reads:\n\n"
        f"{definitions.get(PLANTED_COMMA_JOIN_NAMED_VIEW)!r}"
    )
    assert f"{USER_TABLE}.*" in person_table_rows_read_whole(connection).get(
        PLANTED_COMMA_JOIN_VIEW, set()
    ), (
        f"The reading reports `{PLANTED_COMMA_JOIN_VIEW}` and the strict rule's whole-row half does "
        "not, so the repair stops inside the helper and never reaches the rule CI reads."
    )


@pytest.mark.invariant
def test_a_whole_row_read_of_an_only_qualified_person_table_is_flagged(db_session: Any) -> None:
    """`FROM ONLY "user" u` — the shape the two binders in this suite disagreed about.

    `relation_bindings` in `test_identity_separated_views.py` reads `ONLY` and the
    first version of this binder did not, so one guard saw a relation the other did
    not — two readings of one question that disagree, which is `docs/MISTAKES.md`
    entry 13 in the small. `ONLY` suppresses inheritance and changes nothing about
    what the row carries: `SELECT u.id, to_jsonb(u) FROM ONLY public."user" u` is
    every column `user` has, with the whole-row dependency row dropped because
    `u.id` is named.

    **The binding is asserted before the flag**, as in the comma-join control, and
    for the same reason. **The near miss is planted beside it**: the same `ONLY`
    form reading one named column must stay silent.

    **Whether `ONLY` survives decompilation is read rather than assumed.** Postgres
    stores the inheritance flag on the range-table entry and the deparser writes
    `ONLY ` back out from it, so it is expected to round-trip; if it does not, the
    definition is the plain form, the binder already handled that, and this test
    stays green having proved something weaker than its name. The definition is
    printed in every failure here so the run says which happened.

    **The mutation it exists to survive**: dropping `(?:\\bONLY\\b\\s+)?` from
    `relation_tokens_bound_to`, which every other control in this batch survives
    because none of them writes the keyword.
    """
    session = db_session
    hidden = f'CREATE VIEW public.{PLANTED_ONLY_FORM_VIEW} AS SELECT {GUARDED_PREFIX_ALIAS}.id, to_jsonb({GUARDED_PREFIX_ALIAS}) AS payload FROM ONLY public."{USER_TABLE}" {GUARDED_PREFIX_ALIAS}'  # noqa: S608
    named = f'CREATE VIEW public.{PLANTED_ONLY_FORM_NAMED_VIEW} AS SELECT {GUARDED_PREFIX_ALIAS}.id AS member FROM ONLY public."{USER_TABLE}" {GUARDED_PREFIX_ALIAS}'  # noqa: S608
    session.execute(text(hidden))
    session.execute(text(named))

    connection = session.connection()
    definitions = view_definitions(connection)
    definition = definitions.get(PLANTED_ONLY_FORM_VIEW, "")

    assert f"{GUARDED_PREFIX_ALIAS}.*" in definition, (
        f"The decompiled definition carries no `{GUARDED_PREFIX_ALIAS}.*`, so the whole-row form "
        f"did not survive decompilation and nothing below is about the `ONLY` binding. It "
        f"reads:\n\n{definition!r}"
    )
    tokens = relation_tokens_bound_to(definition, USER_TABLE)
    assert GUARDED_PREFIX_ALIAS in tokens, (
        f"The binder does not bind `{GUARDED_PREFIX_ALIAS}` to `{USER_TABLE}` through an `ONLY` "
        f"qualifier; it bound {sorted(tokens)}. `relation_bindings` in "
        "`test_identity_separated_views.py` reads that keyword, so with this one blind to it the "
        "two halves of the §4.1 pair disagree about which relations a statement even mentions. The "
        f"definition reads:\n\n{definition!r}"
    )

    detected = decompiled_whole_row_reads(connection, {USER_TABLE})
    assert (PLANTED_ONLY_FORM_VIEW, USER_TABLE) in detected, (
        f"`{PLANTED_ONLY_FORM_VIEW}` takes the whole row of an `ONLY`-qualified `{USER_TABLE}` and "
        f"the reading does not report it; it reported {sorted(detected)}."
    )
    assert (PLANTED_ONLY_FORM_NAMED_VIEW, USER_TABLE) not in detected, (
        f"`{PLANTED_ONLY_FORM_NAMED_VIEW}` reads one named column of an `ONLY`-qualified "
        f"`{USER_TABLE}` and the reading calls it a whole-row read. The definition reads:\n\n"
        f"{definitions.get(PLANTED_ONLY_FORM_NAMED_VIEW)!r}"
    )


@pytest.mark.invariant
def test_a_whole_row_read_of_an_unguarded_table_beside_a_person_table_is_not_flagged(
    db_session: Any,
) -> None:
    """The second near miss: whose row was read whole, not merely whether one was.

    A view may legitimately take the whole row of a table that holds nobody, and
    the fact that a person table is joined into the same statement must not make
    that a finding. `SELECT u.id, to_jsonb(c) … FROM public."user" u JOIN
    public.course c` is the shape: a whole row of `course`, a key of `user`, and
    nothing that names a person.

    **The liveness control is the same view, asked about the other table**, which
    is stronger than planting a second one: the reading is required to report
    `course` for this exact definition, so the absence of `user` from its answer
    is a fact about which relation the `.*` is bound to and not about a reading
    that found no `.*` at all (`docs/MISTAKES.md` entry 3, and entry 35's rule
    that a mechanism must be *found* on a subject that certainly has it).

    **The guarded scope is asserted before the absence is believed.** If `course`
    were in `PERSON_TABLES` or carried a marker, this plant would be a whole-row
    read of a guarded table and the assertion below would be measuring the
    opposite of what it claims.

    **The mutation it exists to survive**: dropping the per-table binding and
    matching any `<something>.*` in the definition, which reports every view that
    takes any row whole as a person-table finding.
    """
    session = db_session
    inspector = inspect(session.connection())
    assert UNGUARDED_JOIN_TABLE in inspector.get_table_names(), (
        f"There is no `{UNGUARDED_JOIN_TABLE}` table, so the unguarded half of this pair cannot be "
        "planted and the absence below would stand alone."
    )

    connection = session.connection()
    guarded = {table for table, _ in database_marked_columns(connection)} | set(PERSON_TABLES)
    assert UNGUARDED_JOIN_TABLE not in guarded, (
        f"`{UNGUARDED_JOIN_TABLE}` is one of the tables the whole-row rule guards — it guards "
        f"{sorted(guarded)} — so a whole-row read of it is a real finding, and this near miss is "
        "asserting that a real finding goes unreported. Plant against a table the rule does not "
        f"guard; and if `{UNGUARDED_JOIN_TABLE}` has genuinely gained a person, that belongs where "
        "`PERSON_TABLES` is defined rather than here."
    )

    other = f'CREATE VIEW public.{PLANTED_JOIN_OTHER_WHOLE_VIEW} AS SELECT {GUARDED_PREFIX_ALIAS}.id, to_jsonb(c) AS payload FROM public."{USER_TABLE}" {GUARDED_PREFIX_ALIAS} JOIN public.{UNGUARDED_JOIN_TABLE} c ON true'  # noqa: S608
    session.execute(text(other))

    unguarded_answer = decompiled_whole_row_reads(connection, {UNGUARDED_JOIN_TABLE})
    assert (PLANTED_JOIN_OTHER_WHOLE_VIEW, UNGUARDED_JOIN_TABLE) in unguarded_answer, (
        f"The reading does not report `{PLANTED_JOIN_OTHER_WHOLE_VIEW}` as taking the whole row of "
        f"`{UNGUARDED_JOIN_TABLE}`; it reported {sorted(unguarded_answer)}. The view takes "
        "`to_jsonb(c)` of it, so either Postgres no longer decompiles a whole-row form to "
        "`alias.*` — in which case every control for this reading is measuring nothing and the "
        "pattern needs rewriting against what it does emit — or the reading cannot bind the alias. "
        "The definition it read is:\n\n"
        f"{view_definitions(connection).get(PLANTED_JOIN_OTHER_WHOLE_VIEW)!r}"
    )

    guarded_answer = decompiled_whole_row_reads(connection, {USER_TABLE})
    assert (PLANTED_JOIN_OTHER_WHOLE_VIEW, USER_TABLE) not in guarded_answer, (
        f"`{PLANTED_JOIN_OTHER_WHOLE_VIEW}` takes the whole row of `{UNGUARDED_JOIN_TABLE}` and "
        f"reads one key of `{USER_TABLE}`, and the reading reports it as a whole-row read of "
        f"`{USER_TABLE}`. The `.*` in that definition is bound to the other relation, so the "
        "reading is matching a star it did not attribute — which flags correct SQL, and the repair "
        "somebody reaches for is to stop reading definitions at all."
    )
    assert not person_table_rows_read_whole(connection).get(PLANTED_JOIN_OTHER_WHOLE_VIEW), (
        f"The strict rule's whole-row half reports `{PLANTED_JOIN_OTHER_WHOLE_VIEW}`, whose only "
        f"whole row is a `{UNGUARDED_JOIN_TABLE}` row. A rule that flags every whole-row read "
        "anywhere goes red on the first legitimate `to_jsonb` in the schema, and is then repaired "
        "by narrowing it back to something that misses the case this batch closed."
    )


@pytest.mark.invariant
def test_an_alias_bound_to_a_person_table_does_not_cross_match_an_overlapping_alias(
    db_session: Any,
) -> None:
    """The token boundary the reading rests on, planted in both directions.

    The reading looks for `<token>.*` where `<token>` is a name or alias bound to
    the guarded table. Without a boundary at each end of the token that search is
    a substring search, and a substring search over aliases is wrong in two
    different ways:

      - **an alias that is a prefix of another.** `u` is bound to `"user"`, `us`
        to a table nobody guards, and `to_jsonb(us)` decompiles to `us.*`. A
        pattern anchored only on the left reads that as `u` followed by
        something, and reports a whole-row read of `user` that does not exist.
      - **an alias that is a suffix of another.** `r` is bound to `"user"` and
        `ur` to the unguarded table, and `ur.*` contains `r.*` outright. A pattern
        with no left boundary reports the same thing.

    Both fire on correct SQL rather than missing a leak, which is the direction
    that gets a guard weakened rather than the direction that gets it noticed —
    `person_table_columns_bound` in `test_identity_separated_views.py` records the
    same lesson about the same boundary, learned from a mutation battery that
    found nothing to tell two versions apart until a two-alias shape was planted.

    **Three controls come before the absence**, because an absence is what a
    reading that binds nothing also produces: the definition must actually carry
    `us.*` and `ur.*` (so the text the boundary must not cross-match is there),
    both aliases must be bound to the guarded table by the reading's own binder
    (so it is the boundary being measured and not a failure to bind), and the
    reading must report the unguarded table for this same view.

    **The mutation it exists to survive**: dropping either end of the boundary —
    the `(?<![\\w"])` lookbehind, or the requirement that the token be followed
    immediately by its dot.
    """
    session = db_session
    inspector = inspect(session.connection())
    assert UNGUARDED_JOIN_TABLE in inspector.get_table_names(), (
        f"There is no `{UNGUARDED_JOIN_TABLE}` table, so the overlapping aliases cannot be bound "
        "to anything and this control cannot be planted."
    )

    boundary = f'CREATE VIEW public.{PLANTED_ALIAS_BOUNDARY_VIEW} AS SELECT {GUARDED_PREFIX_ALIAS}.id, {GUARDED_SUFFIX_ALIAS}.id AS second, to_jsonb({OTHER_ALIAS_STARTING_WITH_IT}) AS prefix_payload, to_jsonb({OTHER_ALIAS_ENDING_WITH_IT}) AS suffix_payload FROM public."{USER_TABLE}" {GUARDED_PREFIX_ALIAS} JOIN public."{USER_TABLE}" {GUARDED_SUFFIX_ALIAS} ON {GUARDED_SUFFIX_ALIAS}.id = {GUARDED_PREFIX_ALIAS}.id JOIN public.{UNGUARDED_JOIN_TABLE} {OTHER_ALIAS_STARTING_WITH_IT} ON true JOIN public.{UNGUARDED_JOIN_TABLE} {OTHER_ALIAS_ENDING_WITH_IT} ON true'  # noqa: S608
    session.execute(text(boundary))

    connection = session.connection()
    definition = view_definitions(connection).get(PLANTED_ALIAS_BOUNDARY_VIEW, "")

    overlapping = [
        f"{OTHER_ALIAS_STARTING_WITH_IT}.*",
        f"{OTHER_ALIAS_ENDING_WITH_IT}.*",
    ]
    missing = [spelling for spelling in overlapping if spelling not in definition]
    assert not missing, (
        f"The decompiled definition does not carry {missing}, so the text this boundary must not "
        f"cross-match is not there and the absence below is about nothing. It reads:\n\n"
        f"{definition!r}"
    )

    tokens = relation_tokens_bound_to(definition, USER_TABLE)
    unbound = [
        alias for alias in (GUARDED_PREFIX_ALIAS, GUARDED_SUFFIX_ALIAS) if alias not in tokens
    ]
    assert not unbound, (
        f"The binder does not bind {unbound} to `{USER_TABLE}` in this definition; it bound "
        f"{sorted(tokens)}. Then the reading has no token to cross-match with and this control is "
        "measuring a binder that found nothing rather than a boundary that held."
    )

    unguarded_answer = decompiled_whole_row_reads(connection, {UNGUARDED_JOIN_TABLE})
    assert (PLANTED_ALIAS_BOUNDARY_VIEW, UNGUARDED_JOIN_TABLE) in unguarded_answer, (
        f"The reading does not report `{PLANTED_ALIAS_BOUNDARY_VIEW}` as taking the whole row of "
        f"`{UNGUARDED_JOIN_TABLE}`, which it does twice; it reported {sorted(unguarded_answer)}. "
        "The reading is blind on this definition, so the absence below says nothing about the "
        "token boundary."
    )

    guarded_answer = decompiled_whole_row_reads(connection, {USER_TABLE})
    assert (PLANTED_ALIAS_BOUNDARY_VIEW, USER_TABLE) not in guarded_answer, (
        f"The reading reports a whole-row read of `{USER_TABLE}` for "
        f"`{PLANTED_ALIAS_BOUNDARY_VIEW}`, which reads two keys of it by name and takes the whole "
        f"row of `{UNGUARDED_JOIN_TABLE}` twice. The two aliases overlap deliberately — "
        f"`{OTHER_ALIAS_STARTING_WITH_IT}` starts with `{GUARDED_PREFIX_ALIAS}` and "
        f"`{OTHER_ALIAS_ENDING_WITH_IT}` ends with `{GUARDED_SUFFIX_ALIAS}` — so this is the token "
        "boundary failing at one end or the other, and the cost is a guard that is red on correct "
        f"SQL. The definition it read is:\n\n{definition!r}"
    )


@pytest.mark.invariant
def test_no_view_hides_a_whole_row_read_of_a_person_table_behind_a_join(
    migrated_engine: Any,
) -> None:
    """The live half of item 1: no view in the migrated database reads a row this way.

    The two rules above are asserted over the catalog, which is silent on the join
    form; this asserts the same absence over what Postgres decompiles every view
    back to. It is deliberately phrased over the guarded scope rather than over
    every table — the tables the marker names and the tables that hold a person —
    so a legitimate `to_jsonb` of a course or a section is not a finding.

    **There is no "the reading returned something" guard here**, for the reason
    the marker-based whole-row invariant above gives at greater length: on a
    healthy schema this answer is empty, and requiring a row would be a red on the
    day it landed for a reason having nothing to do with any view. The liveness is
    proved where a subject exists — the five planted controls above require this
    same computation to find the whole-row reads it certainly carries, and to
    leave alone the ones it certainly does not.

    **If this is red, it is a finding rather than a threshold.** Every live view
    reaches the database through a file under `backend/app/views_sql/`, and a
    whole-row read of a person table in one of them is what SPEC §8 forbids
    outright; the repair is the view, not this test.

    **The mutation it exists to survive**: any of the whole-row spellings added to
    a live view alongside a named column of the same table — the arrangement that
    was invisible to every guard in this repository's catalog half until Batch A.
    """
    with migrated_engine.connect() as connection:
        views = public_views(connection)
        definitions = view_definitions(connection)
        guarded = {table for table, _ in database_marked_columns(connection)} | set(PERSON_TABLES)
        hidden = sorted(
            f"{view}: {table}.*" for view, table in decompiled_whole_row_reads(connection, guarded)
        )

    assert views, (
        "The migrated database holds no view in `public`, so this reading looked at nothing and "
        "would report success. `test_identity_separated_views.py` is where their absence is "
        "diagnosed."
    )
    assert sorted(definitions) == views, (
        f"`VIEW_DEFINITIONS` reports definitions for {sorted(definitions)} and `public_views` "
        f"reports {views}. The two read the same catalog with the same filter, so a disagreement "
        "means this reading is looking at a different set of views from the one every other rule "
        "in this file guards — and the absence below would be an absence over the wrong set."
    )
    assert all(definitions.values()), (
        f"Postgres returned an empty definition for "
        f"{sorted(view for view, body in definitions.items() if not body)}. A view always "
        "decompiles to something, so this reading is searching empty strings and would report "
        "nothing whatever those views contain."
    )

    assert not hidden, (
        f"{hidden} — each is a view whose stored definition takes the whole row of a table that "  # noqa: S608
        "holds a person, or of a table the identity marker names, while Postgres records the "
        "dependency at column grain because the same view also names a column of that table.\n\n"
        "This is the shape E1-01 deferred and Batch A closed: `refobjsubid = 0` is dropped as soon "
        "as a column is named, so `SELECT u.id, to_jsonb(u) FROM public.enrollment e JOIN "
        'public."user" u ON u.id = e.user_id` was recorded as an ordinary read of `user.id` and '
        "carried every column `user` has beside it — `lms_user_id` included, which resolves a "
        "named student at the platform in one step.\n\n"
        "SPEC §8 requires the instructor and leadership read paths to go through views that "
        "'structurally cannot join to `user` identity columns — enforced in the database, not just "
        "the application', and §4.1 makes the resulting rules automated assertions. A view is read "
        "with its owner's privileges rather than its reader's, so no arrangement of ADR 0001's "
        "grants closes this. The repair is that the view stops carrying the row: select the "
        "columns it needs, which the join-key allow-list already permits."
    )


@pytest.mark.invariant
def test_every_table_the_person_walk_reaches_is_recognised_or_recorded_as_carrying_nothing(
    migrated_engine: Any,
) -> None:
    """E1-01 deferred item 2, E1-12's half: a table reached and recognised by nothing is named.

    The sweeps in this file are phrased over names and markers, so their silence
    has two causes and no way to tell them apart: the table carries nothing about
    a person, or it carries a person under a name the vocabulary has no reason to
    know. `web_login_subject` was the second, and `deferred.md` records what that
    cost — `idp_subject` matches no fragment and never will, so nothing in this
    repository would have gone red had the table shipped unmarked, and the only
    thing holding it is a test somebody thought to write.

    This is what makes the silence answerable. Every table the fixed-point walk
    reaches is either recognised by the fragment rule or by one of the three
    marker shapes, or its name is in `REACHED_TABLES_THAT_CARRY_NOTHING` with the
    reason it carries nothing. A new table joins one of those two sets in the pull
    request that adds it, and a reviewer is asked the question at the moment they
    can answer it.

    **The failure names the table**, which is the whole of the improvement over
    the silence it replaces.

    **Three non-vacuity guards.** The walk has to reach the tables it starts from,
    it has to reach more than those, and the marker set has to be non-empty —
    otherwise "everything reached is classified" is a fact about a walk that
    reached nothing (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: the report reading `PERSON_TABLES`
    instead of the walk, and the fragment or marker check inverted — both of which
    are caught here or by the planted control below.
    """
    reached = people_tables(migrated_engine)
    absent = [name for name in PERSON_TABLES if name not in reached]
    assert not absent, (
        f"The walk did not reach {absent}, the tables it starts from — it reached "
        f"{sorted(reached)}. Whatever it says about the rest of the schema is a fact about a "
        "broken reflection."
    )
    assert reached > set(PERSON_TABLES), (
        f"The walk reached exactly {sorted(reached)}, the tables it starts from and nothing else. "
        "Every table with a foreign-key path to one of them is supposed to be in that set — "
        "`enrollment`, `role_assignment`, `web_login_subject` — so the fixed point is not "
        "iterating, and a report over the tables it reached is a report over three tables this "
        "file already names."
    )
    assert database_marked_columns(migrated_engine), (
        "Nothing in the migrated database carries the identity marker in any shape this file "
        "reads, so 'recognised' means only the fragment rule here and the classification below is "
        "a weaker question than the one this test asks. The sweep at the top of this module is "
        "where that is diagnosed."
    )

    unclassified = unclassified_reached_tables(migrated_engine)
    inspector = inspect(migrated_engine)
    detail = {
        name: sorted(column["name"] for column in inspector.get_columns(name))
        for name in sorted(unclassified)
    }
    assert not unclassified, (
        f"{sorted(unclassified)} — the person walk reaches each of these and no rule in this file "
        f"recognises anything on them. Their columns are {detail}.\n\n"
        "That is not by itself a defect, and it is not by itself safe: the fragment rule reads "
        f"names ({list(IDENTITY_NAME_FRAGMENTS)}) and the marker reads a column comment, an "
        f"`{MARKER_PREFIXES[0]}` prefix or a comment on the whole table, so a column holding a "
        "person under a name none of those knows — `idp_subject`, `external_ref`, a student "
        "number — is invisible to every sweep above and this report is the only thing that says so."
        "\n\nTwo answers, and the pull request picks one. If a column here holds a person, mark it "
        "(ADR 0022) and this goes green with the sweeps able to see it. If the table genuinely "
        "carries nothing about a person, add its name to `REACHED_TABLES_THAT_CARRY_NOTHING` above "
        "with a one-line reason — that entry is the record the next reviewer reads, and the second "
        "test below is what stops it from rotting once the table changes."
    )


@pytest.mark.invariant
def test_every_table_recorded_as_carrying_nothing_is_still_reached_and_still_unrecognised(
    migrated_engine: Any,
) -> None:
    """The other direction of the inventory, so the record cannot rot in silence.

    `REACHED_TABLES_THAT_CARRY_NOTHING` is a hand-written list, and a hand-written
    list that is only ever read in one direction accumulates entries nobody
    re-examines: a table that has been dropped, or a table that later gained a
    marker and no longer needs an entry at all. Either leaves a name exempting
    something that is not there, and the exemption is invisible because the test
    it feeds is green.

    So three things are asserted of every name here. It must be a table the walk
    still reaches; it must still be one no rule recognises anything on; and it must
    still carry exactly the columns its reason was written against. The first two
    are the report's own conditions run the other way round. The third is a
    security review's, and it is the one that makes the entry expire: without it an
    entry exempts a *name* for as long as the name exists, and a table judged
    harmless in 2026 goes on being exempt through every column added to it
    afterwards.

    This is the closed-set lesson written into a test: a closed-set guard is
    defeated one level out, so the set is asserted from every end rather than from
    the end that happens to be convenient.

    **What this catches, said exactly, because the first version of this sentence
    was wrong.** It catches a *stale* entry — a table that has been dropped, and a
    table that has since gained a marker or an identity-shaped column name and no
    longer needs exempting — and, through the column pin, an entry whose subject
    has changed under it. What it does **not** catch is a name added for a table
    that genuinely is reached and recognised by nothing: exempting such a table is
    a human's judgement, recorded in the reason, and no test can second-guess it.
    The column pin is what stops that judgement outliving the thing it was made
    about.

    **The mutations it exists to survive**: adding `"nrps_call"` to the mapping,
    which the walk does not reach; adding `"web_login_subject"`, which the marker
    recognises; and ignoring `record.columns` in `pinned_column_drift`, which is
    what the planted control below drives.
    """
    assert REACHED_TABLES_THAT_CARRY_NOTHING, (
        "`REACHED_TABLES_THAT_CARRY_NOTHING` is empty, so this test compares nothing and the "
        "report it guards is exempting nothing. If every reached table is genuinely recognised "
        "now, delete this test in the same change and say so; an empty inventory asserted in both "
        "directions is two tests that cannot fail."
    )
    blank = sorted(
        name
        for name, record in REACHED_TABLES_THAT_CARRY_NOTHING.items()
        if not record.reason or not record.columns
    )
    assert not blank, (
        f"{blank} carry no reason, or no columns for the reason to have been written against. Both "
        "halves are the entry: the reason is what a reviewer reads when that table next gains a "
        "column, and the columns are what make that moment arrive. A name with neither is an "
        "exemption nobody has to justify and nothing can expire."
    )

    reached = people_tables(migrated_engine)
    unreachable = sorted(set(REACHED_TABLES_THAT_CARRY_NOTHING) - reached)
    assert not unreachable, (
        f"{unreachable} are recorded as tables the person walk reaches that carry nothing, and the "
        f"walk does not reach them: it reached {sorted(reached)}. Either the table has been "
        "dropped, or it no longer has a foreign-key path to a person table — in both cases the "
        "entry exempts nothing and belongs out of the mapping, in the pull request that made it "
        "false."
    )

    recognised = {table for table, _ in identity_bearing_columns(migrated_engine)} | {
        table for table, _ in database_marked_columns(migrated_engine)
    }
    recognised_now = sorted(
        name
        for name in REACHED_TABLES_THAT_CARRY_NOTHING
        if name in recognised or table_marker_carried_by(migrated_engine, name)
    )
    assert not recognised_now, (
        f"{recognised_now} are recorded as carrying nothing any rule in this file recognises, and "
        "each of them now carries something — a column whose name matches a fragment, a marked "
        "column, or a marker on the whole table. The entry is stale: the sweeps above can see the "
        "table on their own, so the exemption is doing nothing except hiding the next change to "
        "it. Take the name out of `REACHED_TABLES_THAT_CARRY_NOTHING` in the pull request that "
        "marked the column."
    )

    drifted = pinned_column_drift(migrated_engine)
    assert not drifted, (
        f"{sorted(drifted)} no longer carry the columns their entry was written against. Pinned "
        "against live, per table: "
        + "; ".join(
            f"`{name}` was judged on {pinned} and now holds {live}"
            for name, (pinned, live) in sorted(drifted.items())
        )
        + ".\n\nThis is not a schema defect and the repair is not to update the tuple and move on. "
        "The entry says a human read that table's columns and judged that the name-and-marker "
        "sweeps being silent about it was acceptable; a column has arrived since, and the "
        "judgement has to be made again over the table as it is now. Read the reason beside the "
        "name, decide whether it is still true of the new column — a free-text note, a "
        "'last contacted' address, a display name under a spelling the fragments miss are each a "
        "reason it is not — and then either mark the new column under ADR 0022, which takes the "
        "table out of this mapping altogether, or re-earn the entry by updating both the columns "
        "and the sentence in the same pull request."
    )


@pytest.mark.invariant
def test_a_column_added_to_a_recorded_table_expires_its_entry(db_session: Any) -> None:
    """The pin found doing its work, on a table that certainly has an entry.

    The closure test above asserts an absence — no recorded table has drifted —
    and an absence is also what a pin that compares nothing produces
    (`docs/MISTAKES.md` entry 3). So the drift is planted: a column is added to a
    table the mapping records, inside the transaction, and the same computation the
    closure test reads must report it.

    **The clean state is asserted first, in the same transaction.** Without it a
    failure here cannot be told from the mapping already disagreeing with the
    schema before this test touched anything — a different defect, with a different
    fix, diagnosed by the closure test rather than by this one.

    **The planted column is deliberately one no fragment matches.** A column called
    `student_email` would take `enrollment` out of the mapping through the
    recognition rule instead, and this control would go green having proved the
    wrong mechanism.

    **The mutation it exists to survive**: dropping the column comparison from
    `pinned_column_drift` — `if live != sorted(record.columns)` made unconditionally
    false, or the function reduced to `return {}` — which leaves every other test in
    this file green, because on the unmutated schema the drift is empty anyway. That
    is exactly the shape of guard that ships looking like a guarantee.
    """
    session = db_session
    assert ENROLLMENT_TABLE in REACHED_TABLES_THAT_CARRY_NOTHING, (
        f"`{ENROLLMENT_TABLE}` is not recorded in `REACHED_TABLES_THAT_CARRY_NOTHING`, so adding a "
        f"column to it drifts no entry and this control is about nothing. It records "
        f"{sorted(REACHED_TABLES_THAT_CARRY_NOTHING)}; plant against one of those."
    )

    connection = session.connection()
    before = pinned_column_drift(connection)
    assert not before, (
        f"{sorted(before)} had already drifted from their pinned columns before this test added "
        f"anything: {before}. The plant below would then be indistinguishable from the state the "
        "schema was already in, so this control proves nothing until the closure test above is "
        "green — that is where a mapping out of step with the schema is diagnosed."
    )

    session.execute(
        text(f"ALTER TABLE public.{ENROLLMENT_TABLE} ADD COLUMN {PLANTED_DRIFT_COLUMN} text")
    )

    connection = session.connection()
    after = pinned_column_drift(connection)
    assert ENROLLMENT_TABLE in after, (
        f"A column was added to `{ENROLLMENT_TABLE}`, which the mapping records against a fixed "
        f"column set, and the pin does not report it; it reported {sorted(after)}. Then an entry "
        "exempts a table name for as long as the name exists: the reason was written about the "
        "columns that were there when somebody read them, and every column added afterwards "
        "inherits the exemption without anybody looking at it."
    )
    pinned, live = after[ENROLLMENT_TABLE]
    assert PLANTED_DRIFT_COLUMN in live and PLANTED_DRIFT_COLUMN not in pinned, (
        f"`{ENROLLMENT_TABLE}` is reported as drifted and the planted column is not what the "
        f"report is about: it says the entry was judged on {pinned} and the table now holds "
        f"{live}. The drift is real but it is somebody else's, so this control has caught the "
        "state the assertion above was supposed to have refused."
    )
    assert ENROLLMENT_TABLE not in unclassified_reached_tables(connection) and (
        ENROLLMENT_TABLE,
        PLANTED_DRIFT_COLUMN,
    ) not in identity_bearing_columns(connection), (
        f"`{PLANTED_DRIFT_COLUMN}` is recognised by the fragment rule, or the report now names "
        f"`{ENROLLMENT_TABLE}`. Either way the planted column is visible to a sweep on its own, so "
        "the drift asserted above is not the thing being measured — the pin is what has to catch a "
        "column the sweeps cannot see, and a column they can see needs no pin to be noticed."
    )


@pytest.mark.invariant
def test_a_reached_table_recognised_by_nothing_is_reported_and_a_marked_one_is_not(
    db_session: Any,
) -> None:
    """The report found on subjects that certainly have the property, in both directions.

    Two tables are planted, identical but for one comment: each holds a foreign
    key to `person`, so the walk reaches both, and each holds one text column
    called `external_ref`, which ADR 0022's Consequences name as exactly the kind
    of identity column "the widened set still cannot see". One is marked with a
    comment on the whole table — ADR 0022's third shape, and the shape
    `web_login_subject` really uses — and the other carries no marker at all.

    The report must return the unmarked one and must not return the marked one.
    Between them those two assertions say the report is asking about
    classification rather than about the schema's shape: a rule that returned
    every reached table would fail the second, and a rule that returned none would
    fail the first.

    **The fragment rule's silence about `external_ref` is asserted rather than
    assumed** (`docs/MISTAKES.md` entry 3). If a future fragment made that name
    recognisable, the unmarked plant would be classified and this control would be
    measuring a table the sweeps can already see.

    **The mutations it exists to survive**: the report reading `PERSON_TABLES`
    instead of the walk, which kills the first assertion because neither plant is
    in that tuple; and the marker half of the classification dropped, which kills
    the second.

    Both tables are planted inside `db_session`'s transaction and rolled back with
    it — Postgres puts DDL inside the transaction — so `public` is unchanged at the
    end and the assertions run in the same transaction as the plant.
    """
    session = db_session
    person_key = primary_key_of(session.connection(), "person")

    for table in (PLANTED_UNRECOGNISED_TABLE, PLANTED_UNRECOGNISED_MARKED_TABLE):
        session.execute(
            text(
                f"CREATE TABLE {table} (id uuid PRIMARY KEY,"
                f' person_id uuid NOT NULL REFERENCES public.person("{person_key}"),'
                f" {PLANTED_UNRECOGNISED_COLUMN} text)"
            )
        )
    session.execute(
        text(
            f"COMMENT ON TABLE {PLANTED_UNRECOGNISED_MARKED_TABLE} IS "
            f"'{MARKER_TOKEN}: planted by Batch A'"
        )
    )

    connection = session.connection()
    reached = people_tables(connection)
    unreached = [
        table
        for table in (PLANTED_UNRECOGNISED_TABLE, PLANTED_UNRECOGNISED_MARKED_TABLE)
        if table not in reached
    ]
    assert not unreached, (
        f"The walk does not reach {unreached}, which hold a foreign key straight to `person`; it "
        f"reached {sorted(reached)}. That is the one hop it walked before any of this, so "
        "something more basic is wrong than the report — most likely that the planted tables are "
        "invisible to the reflection, in which case both assertions below prove nothing."
    )

    bearing = identity_bearing_columns(connection)
    assert (PLANTED_UNRECOGNISED_TABLE, PLANTED_UNRECOGNISED_COLUMN) not in bearing, (
        f"`{PLANTED_UNRECOGNISED_COLUMN}` now matches a fragment in "
        f"{list(IDENTITY_NAME_FRAGMENTS)}, so the unmarked plant is recognised by the name rule "
        "and is no longer the case this control is about — a table the sweeps can see nothing on. "
        "ADR 0022 names that column as one the widened set cannot see; if the set has widened "
        "again, pick a name it still cannot see and say which."
    )
    assert (PLANTED_UNRECOGNISED_MARKED_TABLE, PLANTED_UNRECOGNISED_COLUMN) in (
        database_marked_columns(connection)
    ), (
        f"The comment on `{PLANTED_UNRECOGNISED_MARKED_TABLE}` does not make its columns read as "
        "marked, so the near miss below is not the shape it claims to be: it would be an unmarked "
        "table absent from the report for some other reason. `marked` accepts a comment on the "
        "whole table carrying the token, which is what this plant writes and what "
        "`web_login_subject` really carries."
    )

    unclassified = unclassified_reached_tables(connection)
    assert PLANTED_UNRECOGNISED_TABLE in unclassified, (
        f"`{PLANTED_UNRECOGNISED_TABLE}` reaches `person` by a foreign key, carries a text column "
        f"called `{PLANTED_UNRECOGNISED_COLUMN}` that matches no fragment, carries no marker in "
        f"any of the three shapes, and has no entry in `REACHED_TABLES_THAT_CARRY_NOTHING` — and "
        f"the report does not name it; it reported {sorted(unclassified)}. That is the state "
        "E1-12's entry in `deferred.md` describes: a table the sweep reached and recognised "
        "nothing on, passed over in silence. A report that reads `PERSON_TABLES` rather than the "
        "walk fails here, because neither plant is in that tuple."
    )
    assert PLANTED_UNRECOGNISED_MARKED_TABLE not in unclassified, (
        f"`{PLANTED_UNRECOGNISED_MARKED_TABLE}` carries the identity marker on the whole table and "
        f"the report names it anyway; it reported {sorted(unclassified)}. The report's question is "
        "whether the sweeps above can see anything on the table, and a whole-table marker is one "
        "of the three shapes they read — so a report that names a marked table would be asking "
        "every ticket to record an exemption for a table it has just marked correctly."
    )
