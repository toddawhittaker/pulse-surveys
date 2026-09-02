"""The grants that make identity unreachable, and the one door left open — ticket E0-10.

SPEC §8 requires that instructor and leadership read paths "structurally cannot
join to `user` identity columns — enforced in the database, not just the
application", and that "only the Care role's queue path can reach identity, and
only via the audited reveal action".
[ADR 0001](../../docs/adr/0001-identity-separation-by-database-role.md) settles
the mechanism: three roles, no grant of any kind on `user_identity` for either
runtime role, and a `SECURITY DEFINER` door that returns identity and leaves a
record of having done so.

**That door is two functions, not one, since E0-26 item 1.** E0-10 built one
function that returned identity and wrote the audit row in the same transaction —
the caller's — and its review measured what that leaves open: `BEGIN; SELECT …;
ROLLBACK;` returned the name and left `audit_log` empty, because Postgres has
already streamed the rows to the client by the time the caller decides. So the
door became `record_identity_reveal`, which writes the record and returns its id
and no identity on any path, and `reveal_student_identity`, which returns identity
only against a record the caller has already committed. Where this file says "the
door", it means both.

**A fourth role exists and is not a runtime one**: the door's owner. A
`SECURITY DEFINER` function executes as whoever owns it, so the owner *is* the
privilege the door opens, and owning it with the identity that runs migrations
makes the door a superuser one — measured on this stack, such a function read
`pg_catalog.pg_authid` for a `pulse_care` session that was refused that table
directly one statement later. The two tests at the end of the Care section below
hold the repair: no `SECURITY DEFINER` function in `public` is owned by a
superuser, and the owner's grants are exactly the four its job needs. Neither
names the role or the function, because E10 replaces the door and a rule
spelled with its name would retire with it.

**Since E1-12 there is a fifth role and a second kind of definer function**, and
the two are not the same kind of thing. `pulse_resolve_definer` (ADR 0094) owns
three point-resolution functions that turn a subject the caller already holds into
a row id: a uuid out, five column reads behind them, no identity column among
those and no `user_identity` read at all. `pulse_app` may execute those three and
may execute the Care door's halves *not at all*, which is now two assertions rather
than one — a door (`test_the_application_role_may_not_execute_the_reveal_function`)
and an inventory (`test_the_application_role_may_execute_only_the_point_resolvers`).
The second definer's grants are pinned exactly, like the first's, and for a
sharper reason: the connection that may call its functions is the one every screen
in the product runs on.

**Denial, never absence.** Every confidentiality assertion here is that the
server *refused* a statement, with the SQLSTATE that says why. "The name was not
in the result" is satisfied by a query that returned nothing for an unrelated
reason — an empty table, a broken fixture, a filter that happened to exclude
everything — and `.claude/review-fixtures/invariant-asserts-absence.diff` is that
mistake written down as a review fixture. Every refusal here is paired with a
control on the same connection in the same transaction, so that a refusal is
known to be about `user_identity` rather than about a role that can do nothing at
all (`docs/MISTAKES.md` entry 3).

**Both halves, catalog and behaviour.** Where two mechanisms could refuse the
same statement — no grant, and no such table — the behavioural test cannot say
which one did. So the grant model is also asserted as *stated*, out of
`has_table_privilege`, beside the tests that provoke the refusal. Entry 3's
second rule, in its own words: "the catalog test cannot see whether the rule
works and the behavioural test cannot see whether it exists".

**How these tests become `pulse_app`.** They `SET ROLE` from the bootstrap
session, which drops superuser and applies the target role's privileges exactly as
a login would. The question this used to leave open is now closed the other way:
`tests/fixtures/database.py` provisions the suite's application role as **`pulse_app`
itself**, so a login and a `SET ROLE` reach the same privileges and the choice is
no longer about which role is measured. Two reasons it stays a `SET ROLE`.
`pulse_care` has no login credential in this fixture — the migration establishes
the role and nothing hands it a password — so the Care tests have no alternative,
and one mechanism for both roles is worth more than two. And a `SET ROLE` runs
inside `db_session`'s transaction, which is what lets a control and the refusal it
qualifies sit in the same transaction on the same connection; over a second engine
they would be two, and "the view was readable" would no longer be a fact about the
moment the identity read was refused.

`test_the_suites_application_connection_authenticates_as_the_granted_role` is what
keeps those two facts tied together, because they are two constants in two files
and nothing else would notice them drifting apart.

**The two halves of the Care check are asserted separately, and that is the
ticket's instruction rather than a preference.** The `SECURITY DEFINER` function
takes the acting person and verifies a live `CARE` assignment itself, and
`services/safety.py` verifies independently before calling it. Where both can
refuse, a behavioural test cannot say which one did (`docs/MISTAKES.md` entry 3),
so `test_the_care_door_refuses_an_actor_with_no_live_care_assignment` calls the
door over SQL with no service anywhere in the picture — that is the half that has
to hold when the service is bypassed. The service's own half is a source-level
assertion in `tests/unit/test_care_session_is_bound_to_the_care_service.py`,
because its runtime interface is not named yet.

**E0-26 item 1 split that door in two and four tests here moved with it.** The
reveal returns nothing until a separately committed record exists, so
`record_identity_reveal` writes the record and the caller commits it before
`reveal_student_identity` will spend it. Two consequences run through this file.
The door is two functions rather than one, which
`test_pulse_care_may_execute_exactly_the_two_halves_of_the_care_door` states — and
states *alone*, because a count is a fact about a revision and the two downgrade
tests inspect an earlier one, where E0-10's single three-argument door is right.
`the_care_door` therefore asserts that the door exists and never how many halves it
has. And a call through the door cannot be made inside `db_session`, whose
transaction is never committed — so the four tests that go through it take a real
`pulse_care` login from `care_connections` and seed through `committed_rows`,
while every test that only reads the catalog still uses `db_session`.

**Where the line between this module and E0-26's runs.** This one asks whether the
*grants* let the door work and stop everything else; `tests/integration/test_the_
reveal_commits_its_record.py` asks what the door *does* — an uncommitted record, a
record written inside a savepoint, a revoked actor, a substituted subject, a
student with no identity row. Only the happy path is walked here, and it is walked
because a grant list trimmed one entry too far closes the door while every refusal
in this file stays green.

**What this module still does not cover.** The two-hat criterion — a reporting
path cannot obtain a `pulse_care` session even when the acting person also holds
a `CARE` assignment — needs the session factory's symbol, which E0-10 does not
spell. The structural half of it is in the unit test named above; the runtime
half waits on the interface.

**The E0-33 section** is a different question from every rule above it: not "is
this rule stated" but "was anything *else* stated". Asserting a refusal proves the
refusal and proves nothing about what a later migration granted beside it, and
`alembic check` reads no ACL, no `pg_roles` row and no `pg_proc` entry in either
direction. Its sibling for generated columns, check constraints and exclusion
constraints is `test_objects_the_drift_gate_cannot_compare.py`, and the view set
is in `test_identity_separated_views.py`.

**The last section is E1-01's**, and it is a third question again: not which
relations a role may read, but which *columns* it may read out of the views it is
allowed to read at all. Every rule above is relation-grained, so none of them can
see what a granted view returns — and a view runs with its owner's privileges, so
the grant on it is the whole of the exposure. The carried entry
`docs/tickets/e1/carried-from-e0.md` measured the disclosure that follows:
`user.lms_user_id` is the LTI `sub`, matched by no identity rule anywhere in this
repository, and a view returning it beside a comment resolves a named student at
the platform in one step. The set of columns `pulse_app` may select is therefore
enumerated as an equality, with the candidates read out of the catalog and the
sanctioned set written down here.
"""

import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# The two roles that serve requests, named by E0-10's scope and by ADR 0001
# before it. Two other roles are deliberately *not* named here. `pulse_migrate`,
# because the ticket's own "Reconcile first" section leaves open whether it
# exists at all or is the bootstrap identity under another name, and a test
# requiring it would settle that. And the `SECURITY DEFINER` function's owner,
# because it is discovered from the catalog rather than spelled: it is not a
# runtime role, nothing connects as it, and E10 replaces the function it owns.
APPLICATION_ROLE = "pulse_app"
CARE_ROLE = "pulse_care"
RUNTIME_ROLES = (APPLICATION_ROLE, CARE_ROLE)

# ADR 0001: "`user` holds the key and platform reference; `user_identity` holds
# name and email." E0-08 built it that way and `test_identity_schema.py` asserts
# the split.
IDENTITY_TABLE = "user_identity"

# The name `seed_identity` below writes onto the student it seeds. **This file's
# choice, and stated rather than borrowed since E1-11**: the helper's non-vacuity
# guard used to ask only that the seeded row carry some string, which it did
# because `identity_name` was `NOT NULL`. E1-11's D7 makes that column nullable
# (ADR 0050 — the roster exposes an address and no name), so the value is named
# here and the reveal's answer is recognised by it. One constant rather than a
# generator: each of the four tests using it seeds one student, and none compares
# two.
SEEDED_IDENTITY_NAME = "Robin Reveal-Me"

# SPEC §8's log, which "is append-only and includes all re-identifications". Named
# here because E0-26 item 1 made it a table this file provokes a refusal on: the
# Care connection now commits the record the door writes, so what that connection
# may do to the table is a question with an answer.
AUDIT_TABLE = "audit_log"

# The statement every denial test in this file runs. A constant rather than an
# f-string built at the call site, so that what `pulse_app` and `pulse_care` are
# each refused is literally the same statement — a refusal of two differently
# spelled queries would leave "the same statement, two roles, one answer each"
# unproven.
READ_IDENTITY = f'SELECT * FROM public."{IDENTITY_TABLE}" LIMIT 1'  # noqa: S608

# Every privilege a table can carry. "No grant of any kind" is the ticket's
# phrase, so all of them are checked rather than `SELECT` alone: `UPDATE` on
# `user_identity` reads nothing but lets a name be replaced with one the writer
# already knows, and `REFERENCES` lets a foreign key be built that probes for the
# existence of a value.
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")

# What the Care door's owner may do, and the whole of it. **Derived from sentences
# of the tickets rather than copied from the migration**, so that this constant can
# be checked against what was asked for instead of against the SQL it is supposed
# to police (`docs/MISTAKES.md` entry 19). Three come from E0-10:
#
#   - it "returns identity"                              → user_identity: SELECT
#   - it "verifies a live `CARE` assignment itself"       → role_assignment: SELECT
#   - it "writes the audit row in the same transaction"   → audit_log: INSERT
#
# The second is the one that surprises people and is not padding: it is the half
# of the two-condition design that has to hold when the service is bypassed, so
# the function reads the supervision table on its own account. The audit table's
# name is SPEC §8's.
#
# **The fourth arrived with E0-26 item 1 and is the widest of the four**:
#
#   - the reveal "takes only the record's id, so the subject is read from the
#     committed record and cannot be substituted by the caller", and it "re-checks
#     that the record's actor still holds `CARE`, and that the record is an
#     `IDENTITY_REVEAL`"                                  → audit_log: SELECT
#
# Say plainly what that buys the definer, because an entry added to make a
# function work is exactly the kind that is read as bookkeeping. Before it, the
# door's owner could **write** a record it could not read back: the subject, the
# actor and the case all arrived as arguments, and the row it inserted was
# write-only from where it stood. Now it can read every row of `audit_log` — who
# revealed whom, when, and under which case, across the whole institution and for
# all time — because the reveal reads its subject, actor and action out of the
# record instead of trusting a caller, and because whether the record is committed
# is a property of the row that is not independently grantable. That is the log
# §6.2 says is "reviewable by Admin" and "reviewed periodically outside the Care
# office", and the role holding it is reachable through one door `pulse_care` may
# open. It is not a route to a *name* — `user_identity: SELECT` was already in the
# set — but it is a route to the pattern of who has been named, which is its own
# disclosure.
#
# `pulse_care` gains nothing from this: the grant is the definer's, and
# `test_the_care_connection_cannot_forge_or_suppress_the_record_the_door_writes`
# is what says the Care connection still cannot touch that table itself.
REVEAL_DEFINER_PRIVILEGES = frozenset(
    {
        ("user_identity", "SELECT"),
        ("role_assignment", "SELECT"),
        ("audit_log", "INSERT"),
        ("audit_log", "SELECT"),
    }
)

# ---------------------------------------------------------------------------
# E1-12 — the second definer, and the first `EXECUTE` the application role holds.
# ---------------------------------------------------------------------------
#
# Until this ticket the answer to "what may `pulse_app` execute" was **nothing**,
# and that was the whole of the rule. E1-12 needs a launch subject and a web
# subject resolved to row ids on the application connection, and the column that
# answers the launch half — `user.lms_user_id` — is the one E1-10's round-3 review
# revoked from `pulse_app` precisely because a connection able to read it can
# enumerate every subject that ever launched. A view cannot help: a view can only
# be filtered on a column it exposes. So resolution goes through the third
# mechanism this file already recognises, `EXECUTE` on a `SECURITY DEFINER`
# function, and the inventory below is what keeps that door the size it was
# argued for (ADR 0094).
#
# **These are hand-written inventories and they move deliberately**
# (`docs/MISTAKES.md` entry 35). Each entry carries the sentence that admits it,
# from the ADR and the ticket rather than from the SQL it is policing, so the next
# person to add one has to be able to say what makes it legitimate.

# The role that owns the point-resolution functions. Named here where the reveal's
# owner is deliberately not: that one is discovered from the catalog because E10
# replaces the function it owns, while this one is spelled by ADR 0094 as part of
# the decision — "a NOLOGIN role that exists for nothing else, so 'the definer's
# privileges' is a list you can read in this file against these bodies".
RESOLVE_DEFINER_ROLE = "pulse_resolve_definer"

# Every `SECURITY DEFINER` function `pulse_app` may call, by name, and why.
#
# **Four entries, from two tickets, and one inventory rather than two.** E1-12 and
# E1-11 opened this door in the same epic and from opposite ends — the first so a
# verified subject reaches its stored identity, the second so a roster member
# reaches its `user` row — and each ticket's branch wrote the equality over its own
# set. Two rival closed sets over one fact is not an inventory; the merge is the
# union, and every entry keeps the sentence that admits it.
#
#   - `resolve_platform_user(lti_platform_id, lms_user_id) -> uuid` — E1-12's
#     launch door holds a `sub` from a token it has verified and needs the `user`
#     row it names. It returns a uuid or NULL and reads no identity column. The
#     caller can resolve a subject it already holds and can never enumerate the
#     subjects it does not, which is the property the revocation bought. **E1-11's
#     roster sync spends the same function for the same reason**: it matches an
#     NRPS member against `user.lms_user_id`, the column E1-10's round-3 review
#     revoked from this role because "a connection able to read it can enumerate
#     every subject that ever launched and join a response back to the person who
#     gave it".
#   - `resolve_person_for_user(user_id) -> uuid` — the second hop, ADR 0024's
#     `person.user_id` link read in the direction a door needs it. NULL is a
#     defined answer, not an error: ADR 0028 gives a student a `user` row and no
#     person, and E1-12's D1 makes "no person" a state the session carries.
#     **E1-11's D5 spends it on the other side of that same NULL**: the sync writes
#     the teaching instructor's `INSTRUCTOR` assignment only where the member's
#     `user` row already resolves to a `person`, and `pulse_app` holds no privilege
#     on `person` at all, which carries a name.
#   - `resolve_web_person(idp_issuer, idp_subject) -> uuid` — the web door's half,
#     over the linkage table `pulse_app` holds no grant on at all. A merge is never
#     inferred from a mutable claim, so this is the only route from a verified
#     `id_token` to an identity.
#   - `record_roster_email(user_id, identity_email)` — E1-11's D7, and one of the
#     two that **write**. ADR 0050 has the roster expose "an address and no name",
#     and E0-10 gives this role "no grant of any kind" on `user_identity` — so an
#     address reaches that table through one function, owned by a role holding two
#     of its columns and never `identity_name`, rather than through a grant.
#   - `record_teaching_instructor(person_id, section_id)` — the security round's F2,
#     and the same argument arriving on a second table. E1-11 first spent a
#     table-wide `INSERT` on `role_assignment` for the teaching instructor's row;
#     `guard_write` refuses only an `INSTRUCTOR` row and that is a Python rule, so a
#     **`CARE`** assignment — the row the reveal definers check for before they
#     return a name — passed unconditionally. A grant cannot bound a column's value,
#     so the write moved into a function whose body writes `'INSTRUCTOR'` and whose
#     signature is two uuids with nowhere to put a role. The grant is gone.
#
# What is *not* here is the point of the list: the two halves of the Care door.
# `pulse_app` is refused those by name in an `invariant`-marked test below, and a
# sixth entry appearing here is a new door into identity that some later ticket
# opened without arguing for it.
SANCTIONED_APPLICATION_EXECUTE = (
    "resolve_platform_user",
    "resolve_person_for_user",
    "resolve_web_person",
    "record_roster_email",
    "record_teaching_instructor",
)

# What the resolve definer may reach at table grain, and the whole of it.
# `web_login_subject` is E1-12's own table and this grant is the only read of it
# anywhere: the rows are written by the seed and by an administrator, and every
# reader goes through `resolve_web_person`.
RESOLVE_DEFINER_PRIVILEGES = frozenset({("web_login_subject", "SELECT")})

# And at column grain, which is where the interesting half is. ADR 0094: the owner
# "holds SELECT on exactly five columns and no identity-bearing column among them:
# ids, the platform reference, and the subject key being matched. It never reads
# `user_identity`, and neither function can return anything but a uuid."
#
#   - `user.id`, `user.lti_platform_id`, `user.lms_user_id` — the three
#     `resolve_platform_user` needs to match a subject at a registration and answer
#     with a row id.
#   - `person.id`, `person.user_id` — ADR 0024's link, read in one direction.
#
# A sixth entry — `person.identity_name`, say — would be a name reachable through a
# function `pulse_app` may call, which is ADR 0001's scheme undone in one line and
# is invisible to every other gate in this build.
RESOLVE_DEFINER_COLUMN_PRIVILEGES = frozenset(
    {
        ("user", "id", "SELECT"),
        ("user", "lti_platform_id", "SELECT"),
        ("user", "lms_user_id", "SELECT"),
        ("person", "id", "SELECT"),
        ("person", "user_id", "SELECT"),
    }
)

# Postgres reports an insufficient privilege as SQLSTATE 42501. Asserted on the
# code rather than on the message text, because "permission denied" also appears
# in errors about schemas and functions, and because a missing table (42P01) or a
# syntax error (42601) would satisfy a bare `raises` while saying nothing about
# what the role may do.
INSUFFICIENT_PRIVILEGE = "42501"

ROLE_EXISTS = "SELECT 1 FROM pg_roles WHERE rolname = :role"
CURRENT_ROLE = "SELECT current_user"
ROLE_ATTRIBUTES = (
    "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolreplication"
    " FROM pg_roles WHERE rolname = :role"
)

# Everything a role owns in a schema this project uses. Ownership is the hole
# under the whole scheme: an owner may grant to itself, so a runtime role that
# owns `user_identity` holds every privilege the migration revoked.
OWNED_RELATIONS = """
    SELECT n.nspname || '.' || c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_roles r ON r.oid = c.relowner
    WHERE r.rolname = :role
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND n.nspname NOT LIKE 'pg\\_%'
    ORDER BY 1
"""

OWNED_SCHEMAS = """
    SELECT n.nspname
    FROM pg_namespace n
    JOIN pg_roles r ON r.oid = n.nspowner
    WHERE r.rolname = :role AND n.nspname NOT LIKE 'pg\\_%'
    ORDER BY 1
"""

# Every role `:role` can become, whether by an explicit `SET ROLE` or by
# inheritance. A grant of a table-owning role to a runtime role voids every
# revoke this ticket writes, and it does so without touching a single grant.
REACHABLE_ROLES = """
    SELECT r.rolname, r.rolsuper
    FROM pg_roles r
    WHERE pg_has_role(:role, r.oid, 'USAGE') AND r.rolname <> :role
    ORDER BY 1
"""

PUBLIC_TABLES = """
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r'
    ORDER BY 1
"""

# Everything `has_table_privilege` can be asked about: tables, partitioned
# tables, views and materialised views. Wider than "the tables the function's
# body names" on purpose — the question is what the definer *can* reach, and a
# grant on something its body does not mention today is exactly the kind that
# arrives unnoticed.
PUBLIC_RELATIONS = """
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm')
    ORDER BY 1
"""

READ_VIEWS = """
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('v', 'm')
    ORDER BY 1
"""

# The `SECURITY DEFINER` functions this project defines, with what a call needs
# to know about them. Discovered rather than named: E0-10 says "a single
# `SECURITY DEFINER` function" and spells neither its name nor its arguments.
SECURITY_DEFINER_FUNCTIONS = """
    SELECT p.oid::regprocedure::text AS signature,
           p.proname AS name,
           pg_get_userbyid(p.proowner) AS owner,
           coalesce(p.proargnames, ARRAY[]::text[]) AS argument_names,
           array(
               SELECT format_type(a.argtype, NULL)
               FROM unnest(p.proargtypes::oid[]) WITH ORDINALITY AS a(argtype, idx)
               ORDER BY a.idx
           ) AS argument_types,
           has_function_privilege(:role, p.oid, 'EXECUTE') AS executable
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.prosecdef
      AND p.prokind IN ('f', 'p')
      AND NOT EXISTS (
          SELECT 1 FROM pg_depend d
          WHERE d.objid = p.oid
            AND d.classid = 'pg_proc'::regclass
            AND d.deptype = 'e'
      )
    ORDER BY 1
"""

# The source text of one function, for the shadow test to learn which relations
# it reads. `prosrc` is the author's own text, unlike a view's definition.
# `CAST(... AS regprocedure)` rather than `:signature::regprocedure`, which is not
# the same statement: SQLAlchemy's `text()` will not read `:signature` as a bind
# parameter when a colon follows it, so the `::` spelling silently sends the
# literal string.
FUNCTION_BODY = "SELECT p.prosrc FROM pg_proc p WHERE p.oid = CAST(:signature AS regprocedure)"

# The column list of one table, as the table itself declares it. The shadow is
# built from this rather than with `CREATE TABLE … (LIKE …)`, and the reason is
# a privilege: `LIKE` requires `SELECT` on the source table, which is exactly what
# `pulse_care` does not hold on `user_identity` — so the attacker's own role
# cannot use the form E0-09's test used. What matters is that the shadow carries
# **the same columns**: a shadow missing a column the function names would make
# the *vulnerable* function fail with "column does not exist", the call would be
# refused, and the test would pass green against the defect it exists to catch
# (`docs/MISTAKES.md` entry 3).
TABLE_COLUMNS = """
    SELECT a.attname, format_type(a.atttypid, a.atttypmod)
    FROM pg_attribute a
    WHERE a.attrelid = ('public.' || quote_ident(:table))::regclass
      AND a.attnum > 0
      AND NOT a.attisdropped
    ORDER BY a.attnum
"""

# How each spelling of a name resolves *for this session*. `to_regclass` answers
# NULL rather than raising for a name that resolves to nothing, so a missing
# relation is a failed assertion naming it rather than an error inside the query.
RESOLVE_BOTH = text("SELECT to_regclass(:bare)::oid, to_regclass(:qualified)::oid")

# The Care door, and the two halves E0-26 item 1 split it into. **Spelled here,
# where E0-10 refused to spell it**, and the change of stance is worth stating.
# E0-10 named neither the function nor its signature, so this file discovered both
# and bound arguments by matching parameter names against a table of fragments —
# roughly 120 lines whose whole job was to avoid settling an interface the ticket
# had left open. E0-26's "The shape, settled 2026-08-20 before any test was
# written" settles it: two calls, both signatures written out, in a section that
# exists because a test cannot be written against an interface that does not exist.
# So the guessing machinery is gone and the names are constants.
#
# **Most rules in this file are still spelled without them.** No `SECURITY
# DEFINER` function in `public` may be owned by a superuser, and the definer's
# grants are exactly what its job needs: both sweep over whatever is there, because
# E10 replaces this door and a rule carrying its name would retire with it.
#
# **One rule stopped being spellable as emptiness, and E1-12 and E1-11 are why.**
# "`pulse_app` may execute nothing" needed no name at all while the answer was
# zero; the answer is now five functions that return no identity (ADR 0094, E1-11's
# D7, and the security round's F2), so the rule is an equality over
# `SANCTIONED_APPLICATION_EXECUTE` at
# the head of this file. The **door** it may not open is still spelled without a
# name — `test_the_application_role_may_not_execute_the_reveal_function` discovers
# it as whatever `pulse_care` may execute — so when E10 replaces the door that
# refusal follows it rather than retiring with these two constants.
RECORD_FUNCTION = "record_identity_reveal"
REVEAL_FUNCTION = "reveal_student_identity"
CARE_DOOR_HALVES = 2

# The `EXECUTE` inventory for the application role is
# `SANCTIONED_APPLICATION_EXECUTE` at the head of this file, and it is one list.
# E1-11's branch carried a second constant over the same fact — a closed set of the
# three functions *that* ticket granted — and the merge folded its entries and its
# sentences into that one rather than leaving two equalities to disagree.
#
# The owners those five functions run as: NOLOGIN roles that exist for nothing
# else, so that "the definer's privileges" is a list you can read in one file
# against one body (ADR 0043's pattern, ADR 0094 and E1-11's D7).
# `pulse_resolve_definer` owns the three point resolvers, `pulse_roster_definer`
# the email write, and `pulse_instructor_definer` the teaching-instructor write the
# security round's F2 moved off a table grant. They are named here because the
# grantee sweep below asks *who* is named in an ACL anywhere in `public` and would
# otherwise report the grants they hold on `user`, `person`, `web_login_subject`,
# `user_identity` and `role_assignment` as roles no ticket sanctioned. What each
# may reach is pinned separately —
# `test_the_resolve_definers_privileges_are_exactly_the_point_lookups_it_answers`
# below for the first, and
# `tests/integration/test_the_roster_definers_answer_a_point_query_and_nothing_more.py`
# for the other two — and what is asserted here is only that they are expected to
# exist.
IDENTITY_DEFINER_ROLES = (
    RESOLVE_DEFINER_ROLE,
    "pulse_roster_definer",
    "pulse_instructor_definer",
)

# How the two halves are called. The record's third argument is a null case id:
# there is no case model until E10, and E0-10 shipped its reveal the same way.
RECORD_CALL = (
    f"SELECT public.{RECORD_FUNCTION}("
    "CAST(:actor AS uuid), CAST(:subject AS uuid), CAST(NULL AS uuid))"
)
REVEAL_CALL = f"SELECT * FROM public.{REVEAL_FUNCTION}(CAST(:reveal_id AS uuid))"  # noqa: S608


def require_role(session: Any, role: str) -> None:
    """Fail with the ticket's own words if `role` does not exist.

    Asserted rather than left to the statement that needs it, because `SET ROLE`
    and `has_table_privilege` both raise on an unknown role, and an error inside
    a query reads like a broken test rather than like a missing deliverable.
    """
    present = session.execute(text(ROLE_EXISTS), {"role": role}).scalar_one_or_none()
    assert present is not None, (
        f"There is no `{role}` role in this cluster. E0-10 establishes three database roles as "
        "migrations: `pulse_migrate` owns the schema and runs Alembic, `pulse_app` serves "
        "student, instructor, leadership and admin requests with no grant of any kind on "
        "`user_identity`, and `pulse_care` serves the Care queue. ADR 0009's provisioning table "
        "and this ticket's 'Reconcile first' section together require that migration to tolerate "
        "a role the bootstrap already created — so the role has to be there after "
        "`alembic upgrade head` whichever mechanism created it."
    )


class acting_as:  # noqa: N801 — a context manager used as a statement, not a type
    """Run the block as `role`, then hand the session back as it was found.

    `SET ROLE` to a non-superuser drops superuser for the session, so the
    privilege checks below are the ones a login as that role would meet. The
    alternative — a second engine with a password — needs the ticket to say
    whether these roles can log in at all, which it does not.

    Every statement expected to *fail* goes through `refused` below rather than
    being run here directly: a failed statement aborts the transaction, and
    `RESET ROLE` on an aborted transaction fails too, which would replace a clear
    assertion with a confusing one.
    """

    def __init__(self, session: Any, role: str) -> None:
        self.session = session
        self.role = role

    def __enter__(self) -> "acting_as":
        require_role(self.session, self.role)
        self.session.execute(text(f'SET ROLE "{self.role}"'))
        current = self.session.execute(text(CURRENT_ROLE)).scalar_one()
        assert current == self.role, (
            f'`SET ROLE "{self.role}"` left `current_user` as {current!r}. Every privilege '
            "assertion in this test is about the role the session is acting as, so a session that "
            "did not switch would be measuring the bootstrap superuser — which passes every "
            "control and fails every refusal, or worse, passes both."
        )
        return self

    def __exit__(self, *exception: Any) -> None:
        self.session.execute(text("RESET ROLE"))


def refused(session: Any, statement: str, parameters: dict[str, Any] | None = None) -> Any:
    """Run `statement`; answer the database error it provoked, or `None`.

    Inside a savepoint, so that a refusal leaves the surrounding transaction
    usable — the controls in these tests run before and after the statement that
    must fail, and they are what make the refusal attributable.
    """
    savepoint = session.begin_nested()
    try:
        session.execute(text(statement), parameters or {})
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.commit()
    return None


def sqlstate(failure: Any) -> str | None:
    """The SQLSTATE behind a SQLAlchemy error, if the driver reported one."""
    return getattr(getattr(failure, "orig", None), "sqlstate", None)


def read_views(session: Any) -> list[str]:
    """Every view in `public`, by name."""
    return [row[0] for row in session.execute(text(READ_VIEWS))]


def security_definer_functions(session: Any, role: str) -> list[Any]:
    """Every `SECURITY DEFINER` function this project defines, and whether `role` may call it."""
    require_role(session, role)
    return session.execute(text(SECURITY_DEFINER_FUNCTIONS), {"role": role}).mappings().all()


def the_care_door(session: Any) -> list[Any]:
    """Every `SECURITY DEFINER` function `pulse_care` may execute, whatever revision this is.

    **It asserts that the door exists and deliberately not how many halves it has**,
    and that division is the repair for a real failure rather than a preference.
    An earlier version of this helper asserted the count — one before E0-26 item 1,
    `CARE_DOOR_HALVES` after it — and both of the downgrade tests below broke on it:
    they run against the schema *at* the identity revision, where E0-10's single
    three-argument door is exactly right, and were being told by a helper that
    describes head. A count is a fact about a revision, and only the caller knows
    which revision it is looking at.

    So the count lives with the caller that knows: at head it is
    `test_pulse_care_may_execute_exactly_the_two_halves_of_the_care_door`, which
    states E0-26's settled number once and carries the reason for it; the two
    downgrade tests state none, because neither is about the door's shape.

    **What stays here is non-emptiness**, which is true at every revision that has a
    Care door at all and is what the callers below need before they can ask
    anything: the owner of nothing is not a role, and a shadow test with no function
    to attack reports success having attempted nothing.

    Which half is which is deliberately not decided here. Nothing in this module
    needs to know: seven of its callers want the owner, and the tests that call the
    door go through `open_the_care_door` below, which is the one place either name
    is spelled.
    """
    executable = [
        row for row in security_definer_functions(session, CARE_ROLE) if row["executable"]
    ]
    assert executable, (
        "No `SECURITY DEFINER` function in `public` is executable by `pulse_care`. E0-10: 'The "
        "Care path must remain open, and this ticket proves it… `pulse_care` gets `EXECUTE` on a "
        "single `SECURITY DEFINER` function… so a name cannot be obtained without leaving a "
        "record.' Care re-identification is the one legitimate route to identity (§4, §6.2) and "
        "is deliberately not blocked; this test is what stops a later change closing it silently."
    )
    return sorted(executable, key=lambda row: row["name"])


def the_reveal_definer(session: Any) -> str:
    """The one role that owns the Care door, whichever half is asked about.

    Every rule in this file about the definer — that it is not a superuser, that
    its grants are exactly what its job needs, that it is the control proving the
    identity probes can see a grant — is a rule about a *privilege set*. Two owners
    would be two privilege sets, only one of which any of those rules measured, so
    the shared owner is asserted here rather than assumed by picking the first row.

    **Its assertion holds at every revision**, which is what lets the two downgrade
    tests use it: E0-10's one door and E0-26's two both have exactly one owner, and
    a helper that also stated a count could not serve both.
    """
    door = the_care_door(session)
    owners = sorted({row["owner"] for row in door})
    assert len(owners) == 1, (
        f"The Care door — {[row['signature'] for row in door]} — is owned by {owners}. A "
        "`SECURITY DEFINER` function "
        "spends its owner's privileges, so two owners are two privilege surfaces — and every "
        "assertion in this file about what the definer may reach would be measuring one of them "
        "while the other went unread. ADR 0043 gives the reveal an owner of its own precisely so "
        "that the set of grants behind the door is short enough to read against the function body."
    )
    return owners[0]


CARE_PATH_IS_OPEN_DELIBERATELY = (
    "E0-10 keeps the Care path open on purpose: 'Care re-identification is the one legitimate "
    "route to identity (§4, §6.2), and it is deliberately not blocked.' A reveal the Care role "
    "cannot complete is this ticket's other failure mode, and the one every denial test in this "
    "file is silent about."
)


def attempt(connection: Any, statement: str, parameters: dict[str, Any]) -> tuple[list[Any], Any]:
    """Run `statement`; answer its rows and the database error it raised, if any.

    **`returns_rows` is checked rather than assumed, and that is a repair for two
    failures rather than defensiveness.** SQLAlchemy raises `ResourceClosedError`
    — "This result object does not return rows. It has been closed automatically."
    — from `.mappings().all()` on a statement with no result set, and that is not a
    `DatabaseError`, so it escapes this helper's `except` and reaches the test as an
    error rather than as an answer.

    Three callers here hand it statements that return nothing: the
    `CREATE TEMPORARY TABLE` that stands up each `pg_temp` shadow, and the `INSERT`
    and `DELETE` that the Care connection must be refused on `audit_log`. The first
    is the measured failure — the shadow test errored on its first shadow, before
    any assertion ran. **The other two are the more interesting half**: those
    statements are expected to be *refused*, so the `DatabaseError` arrives first
    and the bug never shows. Under the exact mutation that test's docstring names —
    `GRANT INSERT ON public.audit_log TO pulse_care` — the insert would succeed,
    this helper would raise `ResourceClosedError`, and the test would error out
    instead of failing on the assertion that says a forged record is possible. A
    test that cannot report the finding it exists to make is not a guard
    (`docs/MISTAKES.md` entry 3, and entry 13: the same quirk faced in two places,
    routed through one helper).
    """
    try:
        result = connection.execute(text(statement), parameters)
        rows = result.mappings().all() if result.returns_rows else []
    except DatabaseError as failure:
        return [], failure
    return rows, None


def open_the_care_door(
    connection: Any, *, actor: Any, subject: Any, refusal_means: str = ""
) -> list[Any]:
    """Record a reveal, commit it, and spend it — the whole door, on one Care connection.

    **Why this needs a connection rather than `db_session`.** E0-26 item 1 makes
    `reveal_student_identity` return nothing until a separately committed record
    exists, and `db_session` opens a transaction outside the session that is never
    committed. Every call through it would be refused, correctly, for a reason that
    has nothing to do with the grants this module is about. So the four tests below
    that go through the door take a real `pulse_care` login from `care_connections`
    and drive their own transactions, and the rows they ask about come from
    `committed_rows` rather than from `seed_rows`.

    That is also what `services/safety.py` does — "it records, commits, and then
    reveals in a second transaction" — so the sequence here is the production one
    rather than a shape invented for a test.

    A refusal at either half is a failed test, because every caller below is
    exercising the door working. The behavioural rules about *when* it refuses
    belong to `tests/integration/test_the_reveal_commits_its_record.py`, which is
    E0-26's own module; this file's business is whether the grants let the door
    work at all.
    """
    rows, failure = attempt(connection, RECORD_CALL, {"actor": actor, "subject": subject})
    assert failure is None, (
        f"`public.{RECORD_FUNCTION}` refused a call by `{CARE_ROLE}`: {failure}. "
        f"{refusal_means or CARE_PATH_IS_OPEN_DELIBERATELY}"
    )
    assert rows, (
        f"`public.{RECORD_FUNCTION}` returned no row. It is declared `RETURNS uuid` and answers "
        "the id of the `audit_log` row it wrote, which is the only thing the second half takes."
    )
    reveal_id = next(iter(rows[0].values()))
    connection.commit()

    revealed, failure = attempt(connection, REVEAL_CALL, {"reveal_id": reveal_id})
    assert failure is None, (
        f"`public.{REVEAL_FUNCTION}` refused a committed record: {failure}. "
        f"{refusal_means or CARE_PATH_IS_OPEN_DELIBERATELY}"
    )
    connection.commit()
    return revealed


def seed_identity(committed_rows: Any) -> dict[str, Any]:
    """One `user` with one `user_identity` row, committed, and how to name them.

    Committed rather than seeded into `db_session`'s transaction, because the Care
    connection that asks about this student is a second connection and would
    otherwise be asked to reveal somebody who, from where it is standing, does not
    exist.

    **The LMS subject is no longer returned, and that is E0-26 settling an
    interface E0-10 left open.** This used to hand back both the key and the LMS
    subject because E0-10 spelled no signature and the reveal might have taken
    either. `record_identity_reveal(in_actor_person_id uuid, in_subject_user_id
    uuid, in_case_id uuid)` takes the key, so `LMS_USER_ID_COLUMNS` has gone from
    this module with the argument-guessing machinery that needed it. The copy in
    `tests/integration/test_care_service_reveal.py` stays: the *service*'s
    `reveal_identity` keeps its own signature, which E0-26 does not change.

    **The name is stated here since E1-11, and was borrowed before it.** The
    non-vacuity guard below asks the seeded row to carry a recognisable value, and
    got one only because `user_identity.identity_name` was `NOT NULL` and
    `seed_row` fills what the schema requires. E1-11's D7 makes the column nullable
    — the roster sync stores an address for a member it has no name for (ADR 0050),
    and `record_roster_email`'s owner holds no privilege on the name column at all
    — so the helper leaves it and four tests here failed inside their own seeding
    (dispute E1-11-02, `docs/MISTAKES.md` entry 22). Passing the value makes this
    helper state its own premise instead of resting on a constraint two tickets
    away, and it is what the reveal's answer is now recognised by.
    """
    chain: dict[str, Any] = {}
    identity = committed_rows.seed(IDENTITY_TABLE, chain, identity_name=SEEDED_IDENTITY_NAME)
    committed_rows.commit()

    user = chain.get("user")
    assert user is not None, (
        f"Seeding `{IDENTITY_TABLE}` did not seed a `user` with it, so this test has no user to "
        "ask about. ADR 0001 splits the key onto `user` and the name and email onto "
        "`user_identity`, one row per user, which makes the link a NOT NULL foreign key the "
        "seeding helper follows."
    )
    values = {
        value
        for key, value in identity.items()
        if isinstance(value, str) and value and not key.endswith("_id")
    }
    assert SEEDED_IDENTITY_NAME in values, (
        f"The seeded `{IDENTITY_TABLE}` row does not carry the name this helper asked it to "
        f"({SEEDED_IDENTITY_NAME!r}): {dict(identity)}. There is then nothing for a reveal to "
        "return that could be recognised, and the tests below would be asserting that a function "
        "returned something rather than that it returned this student's identity.\n\n"
        "Until E1-11 this asked only for *some* non-key string and got one from the `NOT NULL` "
        "constraint on `identity_name`, which D7 legitimately removes; the value is stated in this "
        "file now."
    )
    user_key = next(
        (key for key in user if key in {"id", "user_id"}),
        None,
    )
    assert user_key is not None, (
        f"The seeded `user` row has columns {list(user.keys())} and none of them reads as its "
        "primary key. ADR 0016 makes every primary key one server-generated uuid."
    )
    return {"user_id": user[user_key], "identity_values": values}


def identity_in(rows: list[Any]) -> set[str]:
    """Every non-null value the door handed back, as strings."""
    return {str(value) for row in rows for value in row.values() if value is not None}


# ---------------------------------------------------------------------------
# The roles themselves: the two properties that would void every grant below.
# ---------------------------------------------------------------------------


def test_the_suites_application_connection_authenticates_as_the_granted_role(
    application_engine: Any,
) -> None:
    """The role the suite connects as and the role this ticket grants to are one role.

    Two constants in two files decide this — `TEST_APP_USER` in
    `tests/fixtures/database.py` and `APPLICATION_ROLE` here — and nothing else in the
    suite would notice them drifting apart. What drift costs is specific and
    silent: `application_engine` would authenticate as a role holding no grant on
    anything, every "permission denied" assertion in this module would pass
    whatever the migration did or did not revoke, and
    `test_application_role_privileges.py`'s guard against "tests that pass under
    privileges production does not have" would be inverted — passing under
    privileges production *exceeds*.

    That is not hypothetical: it was the state until E0-10, when
    `TEST_APP_USER` was still E0-04's `pulse_test_app` and this ticket's grants
    all belonged to `pulse_app`.
    """
    with application_engine.connect() as connection:
        current = connection.execute(text(CURRENT_ROLE)).scalar_one()

    assert current == APPLICATION_ROLE, (
        f"`application_engine` authenticates as {current!r}, and this ticket's grants belong to "
        f"`{APPLICATION_ROLE}` — the name `.env.example` gives `DB_APP_USER` and the name E0-10's "
        "migration establishes. Change `TEST_APP_USER` in `tests/fixtures/database.py`, or, if "
        "the deployment's application role is genuinely spelled some other way, change it here "
        "and in "
        "the migration together. Two spellings is the one outcome that reads as working: the "
        "connection succeeds, the queries run, and every grant assertion in this module measures a "
        "role nothing granted anything to."
    )


@pytest.mark.parametrize("role", RUNTIME_ROLES)
def test_a_runtime_role_holds_none_of_the_attributes_that_bypass_a_grant(
    db_session: Any, role: str
) -> None:
    """Criterion: "neither runtime role … is a superuser".

    All five attributes are asserted together because they are one property with
    five spellings, and each is a way out from under the grants this ticket is
    made of. `rolsuper` is the obvious one; `rolbypassrls` alone would read
    straight through a deny-all policy while leaving the role looking correct in
    `\\du`, which is what E0-02's security review measured on the real stack.

    The row is required to exist first: `WHERE rolname = :role` returning nothing
    makes every "not a superuser" assertion true of no row at all
    (`docs/MISTAKES.md` entry 3).
    """
    require_role(db_session, role)
    row = db_session.execute(text(ROLE_ATTRIBUTES), {"role": role}).one()

    held = [name for name, value in zip(row._fields, row, strict=True) if value]
    assert not held, (
        f"`{role}` holds {held}. ADR 0001's first consequence — 'runtime roles must not own "
        "tables and must not be superuser. Both bypass grants entirely, which would make the "
        "whole scheme decorative' — is the rule, and ADR 0009 sanctions a superuser for "
        "migrations precisely so that this half can stand unchanged. E0-10 is the ticket that "
        "tests it."
    )


@pytest.mark.parametrize("role", RUNTIME_ROLES)
def test_a_runtime_role_owns_no_table_and_no_schema(db_session: Any, role: str) -> None:
    """Criterion: "neither runtime role owns any table".

    An owner may grant to itself, so ownership is not a smaller version of a
    grant — it is the whole grant model rewritten by whoever holds it. Schema
    ownership is asserted with it because it is the same hole one step up: the
    owner of `public` can create a table there and own that.

    **The control is what makes the emptiness mean something.** "Owns nothing" is
    equally true of a query that finds no owners at all, so the same query is
    asked of the identity that ran the migrations and has to come back non-empty.
    """
    require_role(db_session, role)
    owned = [row[0] for row in db_session.execute(text(OWNED_RELATIONS), {"role": role})]
    schemas = [row[0] for row in db_session.execute(text(OWNED_SCHEMAS), {"role": role})]

    migrator = db_session.execute(text(CURRENT_ROLE)).scalar_one()
    by_the_migrator = [
        row[0] for row in db_session.execute(text(OWNED_RELATIONS), {"role": migrator})
    ]
    assert by_the_migrator, (
        f"The ownership query finds nothing owned by `{migrator}` either, which is the identity "
        "that ran every migration in this database. It cannot then be finding anything owned by "
        f"`{role}`, so the assertions below would pass against any ownership at all."
    )

    assert not owned and not schemas, (
        f"`{role}` owns the relations {owned} and the schemas {schemas}. A table's owner has "
        "every privilege on it regardless of what was granted or revoked, and may grant more to "
        "anyone — so a runtime role that owns `user_identity`, or owns the schema it could "
        "recreate it in, makes ADR 0001's separation decorative. Migrations run as the bootstrap "
        "identity (ADR 0009), which is what owns the schema."
    )


@pytest.mark.parametrize("role", RUNTIME_ROLES)
def test_a_runtime_role_cannot_become_a_role_that_owns_a_table(db_session: Any, role: str) -> None:
    """The same hole one indirection away: membership, not ownership.

    `GRANT pulse_migrate TO pulse_app` voids every revoke in this ticket without
    touching a single grant, and `\\du` shows it as one extra word. Nothing in
    the criteria names it, and it is the cheapest way for the guarantee to be
    lost during an unrelated fix — which is `docs/MISTAKES.md` entry 2's shape.

    The control is the same query asked of the bootstrap identity: a superuser is
    considered a member of every role, so it must come back non-empty, and a
    query that could not find a membership would say so here.
    """
    require_role(db_session, role)
    reachable = db_session.execute(text(REACHABLE_ROLES), {"role": role}).all()

    migrator = db_session.execute(text(CURRENT_ROLE)).scalar_one()
    assert db_session.execute(text(REACHABLE_ROLES), {"role": migrator}).all(), (
        f"`pg_has_role` reports that `{migrator}` — the bootstrap superuser these tests connect "
        "as — can become no other role, which cannot be true. The query is broken, and the "
        "assertion below would pass against any membership."
    )

    dangerous: list[str] = []
    for name, is_superuser in reachable:
        owned = db_session.execute(text(OWNED_RELATIONS), {"role": name}).all()
        if is_superuser or owned:
            dangerous.append(f"{name} (superuser={bool(is_superuser)}, owns {len(owned)})")

    assert not dangerous, (
        f"`{role}` can become {dangerous}. Membership is inherited privilege: a runtime role that "
        "can `SET ROLE` to the schema's owner, or to a superuser, holds everything this ticket "
        "revokes, and no grant on `user_identity` has to change for it. ADR 0001: 'Runtime roles "
        "must not own tables and must not be superuser' — reaching one is the same thing."
    )


# ---------------------------------------------------------------------------
# §4.1 — no instructor read path can reach an identity column, at each of the
# three doors the application role has *on this connection*: a direct `SELECT`, a
# join from a read view back to `user_identity`, and `EXECUTE` on the reveal
# function. There is a fourth door and it is not here, because it does not go
# through a grant at all — a view is read with its **owner's** privileges, so a
# later view that selects an identity column hands it over with all three of
# these still shut. `test_identity_column_marker.py`'s
# `test_no_view_reads_a_column_the_identity_marker_names` is that one, marked
# `invariant` for the same reason these are.
#
# This is the **one** §4.1 item E0-10 lands: item 1, "no student-visible path
# exposes another section", is deferred to E2 on the record, because there is no
# student-visible path here and the scoping that would make "another section"
# mean anything is E0-11's. Nothing in this file may be read as covering it.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_the_application_role_is_refused_a_select_on_user_identity(db_session: Any) -> None:
    """SPEC §4.1: identity is never displayed to an instructor or any leadership role.

    Asserted as a **refusal**, at the database, on the connection the instructor
    screens run on. An assertion that a name is missing from a result set is
    satisfied whenever the query returns nothing — including when it is broken
    for an unrelated reason — which is the finding
    `.claude/review-fixtures/invariant-asserts-absence.diff` exists to teach.

    Two controls make the refusal attributable. The session is asserted to be
    acting as `pulse_app` and not as the superuser it connected as; and the same
    role reads a view in the same transaction, which is what tells "this role may
    not read `user_identity`" apart from "this role can do nothing" and from
    "there is no such table".

    **The mutation it exists to survive** is `GRANT SELECT ON user_identity TO
    pulse_app` — added by a future ticket to make a query work, which is exactly
    how this guarantee would be lost, and which nothing else in the suite would
    notice.
    """
    views = read_views(db_session)
    assert views, (
        "There is no view in `public` for the control below to read, so a refusal on "
        f"`{IDENTITY_TABLE}` could not be told apart from a role that may read nothing at all. "
        "E0-10 ships the read views; `test_identity_separated_views.py` diagnoses their absence."
    )

    with acting_as(db_session, APPLICATION_ROLE):
        readable = [
            view
            for view in views
            if refused(db_session, f'SELECT * FROM public."{view}" LIMIT 1') is None  # noqa: S608
        ]
        assert readable, (
            f"`{APPLICATION_ROLE}` may not read any of {views}. The read paths for students, "
            "instructors, leadership and admin all run on this role, so a role that cannot read "
            "the views serves no screen — and a refusal on `user_identity` from a role that is "
            "refused everything says nothing about identity separation."
        )

        failure = refused(db_session, READ_IDENTITY)

    assert failure is not None, (
        f"`{APPLICATION_ROLE}` read `{IDENTITY_TABLE}` — the table ADR 0001 puts a person's name "
        f"and email address in — while holding a working grant on {readable}. SPEC §8: instructor "
        "and leadership read paths go through views that 'structurally cannot join to `user` "
        "identity columns — enforced in the database, not just the application'. E0-10: "
        "`pulse_app` 'has no grant of any kind on `user_identity`. An instructor screen cannot "
        "leak a name because the connection it runs on cannot read the table.'"
    )
    assert sqlstate(failure) == INSUFFICIENT_PRIVILEGE, (
        f"The read of `{IDENTITY_TABLE}` failed with SQLSTATE {sqlstate(failure)} rather than "
        f"{INSUFFICIENT_PRIVILEGE} (insufficient privilege): {failure}. A missing table, a syntax "
        "error or an aborted transaction would each satisfy 'it failed' while saying nothing "
        "about what this role may do — and a schema where the table is simply absent is not the "
        "guarantee §8 asks for, since the table has to exist for Care to reveal from."
    )


@pytest.mark.invariant
def test_the_application_role_is_refused_a_join_from_a_read_view_back_to_user_identity(
    db_session: Any,
) -> None:
    """The same invariant by the route a careless query actually takes.

    §8's wording is that the read paths "structurally cannot **join** to `user`
    identity columns". The join is the interesting case because it is what
    somebody writes when a screen needs a name: the view is permitted, so the
    statement looks like a small extension of something that already works.

    The control is the same view without the join, run first in the same
    transaction as the same role — so the refusal is attributable to the second
    table and not to the view, the syntax, or the role.
    """
    views = read_views(db_session)
    assert views, (
        "There is no view in `public` to join from, so this test would report success having "
        "attempted nothing."
    )

    with acting_as(db_session, APPLICATION_ROLE):
        for view in views:
            alone = refused(db_session, f'SELECT * FROM public."{view}" LIMIT 1')  # noqa: S608
            if alone is not None:
                continue
            join = (
                f'SELECT * FROM public."{view}" v JOIN public."{IDENTITY_TABLE}" i ON true LIMIT 1'  # noqa: S608
            )
            joined = refused(db_session, join)
            assert joined is not None, (
                f"`{APPLICATION_ROLE}` joined `public.{view}` to `{IDENTITY_TABLE}` and got rows. "
                "The view being safe is not the guarantee — the guarantee is that the connection "
                "the view is read on cannot reach the identity table at all, by any statement. "
                "SPEC §8 asks for read paths that 'structurally cannot join to `user` identity "
                "columns'."
            )
            assert sqlstate(joined) == INSUFFICIENT_PRIVILEGE, (
                f"The join from `{view}` to `{IDENTITY_TABLE}` failed with SQLSTATE "
                f"{sqlstate(joined)} rather than {INSUFFICIENT_PRIVILEGE}: {joined}. The view "
                "alone succeeded in this same transaction, so a failure for any other reason is "
                "not the identity separation refusing it."
            )
            return

    pytest.fail(
        f"`{APPLICATION_ROLE}` could not read any of {views} on its own, so no join was ever "
        "attempted and this test asserted nothing. That is diagnosed by "
        "`test_the_application_role_is_refused_a_select_on_user_identity`."
    )


@pytest.mark.invariant
def test_the_application_role_may_not_execute_the_reveal_function(db_session: Any) -> None:
    """The third door into identity, and the one Postgres opens by default.

    `EXECUTE` on a new function is granted to `PUBLIC` unless a migration revokes
    it. So a `SECURITY DEFINER` function that reads `user_identity` is, by
    default, callable by every role in the cluster — including the one every
    instructor screen runs on — and no grant on `user_identity` has to exist for
    that to be true. Revoking it is a line somebody has to write, and nothing
    else in this suite would notice its absence (`docs/MISTAKES.md` entry 2).

    **This was "`pulse_app` may execute nothing" until E1-12 and E1-11, and the
    narrowing is what those tickets had to argue for rather than a relaxation.**
    `pulse_app` now holds `EXECUTE` on the three point-resolution functions ADR
    0094 ships — a verified subject reaching its stored identity is E1-12's whole
    subject, and E1-11's roster sync matches a member to its `user` row through the
    same two — and on `record_roster_email`, which writes an address into a table
    this role holds no grant on at all (E1-11's D7, ADR 0050). Each answers a point
    question and returns no identity, so a rule phrased as emptiness would be red
    against the correct schema.

    **What this test asserts is the door, and it identifies the door by discovery.**
    Whatever `pulse_care` may execute is what `pulse_app` may not — never by name,
    because E10 replaces the Care door and a rule spelled with its name would
    retire with it. That is E0-10's sentence, and the reason `pulse_app` reaching
    either half is a §4.1 breach rather than an untidy grant:
    `reveal_student_identity` returns a name, and `record_identity_reveal` writes
    the audit row that makes the name accountable.

    **The inventory half is next door**, in
    `test_the_application_role_may_execute_only_the_point_resolvers`: that the four
    sanctioned functions are the only other thing this role may call. Two tests
    because they are two facts — this one is a door, that one is a closed set — and
    a merge that folded them into one would have lost whichever fact it phrased
    second.

    **What the four permitted functions can reach is pinned elsewhere, as
    equalities over their owners' grants**:
    `test_the_resolve_definers_privileges_are_exactly_the_point_lookups_it_answers`
    below, and
    `tests/integration/test_the_roster_definers_answer_a_point_query_and_nothing_more.py`.
    That is where "what could this door possibly reach" is answered, and it is a
    question about the owner rather than about the body.

    **The mutation it exists to survive**: dropping
    `REVOKE ALL ON FUNCTION … FROM PUBLIC` from any of the migrations, which puts
    every definer function in this schema — the Care door included — in this
    role's reach and leaves every other test in this file green.
    """
    functions = security_definer_functions(db_session, APPLICATION_ROLE)
    assert functions, (
        "This project defines no `SECURITY DEFINER` function in `public`, so this test swept "
        "nothing. E0-10 ships the Care door and E0-26 item 1 made it two functions; "
        "`test_the_care_roles_grants_are_enough_to_complete_a_reveal` diagnoses "
        "its absence."
    )

    door = {row["signature"] for row in the_care_door(db_session)}
    reachable = [
        row["signature"] for row in functions if row["executable"] and row["signature"] in door
    ]
    assert not reachable, (
        f"`{APPLICATION_ROLE}` may execute {reachable}, which is the door `{CARE_ROLE}` opens to "
        "identity. A `SECURITY DEFINER` function runs with its owner's privileges, so one that "
        "reads `user_identity` hands identity to whoever may call it — and Postgres grants "
        "`EXECUTE` to `PUBLIC` by default, which means this is the state a migration reaches by "
        "*not* saying anything. E0-10 gives that `EXECUTE` to `pulse_care` alone, and every screen "
        "in the product runs on this connection."
    )


def an_inventoried_execute(row: Any) -> bool:
    """Is this `EXECUTE` grant one a ticket argued for, by grantee *and* by function?

    Two entries, and the asymmetry between them is the design. `pulse_care` holds
    the Care door and the door is discovered rather than named, because E10
    replaces it and a rule spelled with its name would retire with it. `pulse_app`
    holds ADR 0094's point resolvers and E1-11's one writer, and those *are* named,
    because the argument that admits each is an argument about that function's body
    — a uuid out and no identity column read, or an address in and never a name —
    and neither generalises to the next function somebody wants to grant.
    """
    if row["grantee"] == CARE_ROLE:
        return True
    return (
        row["grantee"] == APPLICATION_ROLE
        and routine_name(row["routine"]) in SANCTIONED_APPLICATION_EXECUTE
    )


def routine_name(routine: str) -> str:
    """The bare function name out of a `regprocedure` rendering.

    `oid::regprocedure::text` prints `resolve_web_person(text,text)`, and prints a
    schema qualification where the schema is not on the search path. Both are
    stripped, so an inventory can be written as names — which is what the ADR that
    admits each entry writes.
    """
    return routine.split("(", 1)[0].strip().rsplit(".", 1)[-1].strip('"')


@pytest.mark.invariant
def test_the_application_role_may_execute_only_the_point_resolvers(db_session: Any) -> None:
    """E1-12 and E1-11: the inventory of doors this connection may open, as an equality.

    `EXECUTE` on a `SECURITY DEFINER` function is a privilege held in a different
    currency — the caller spends the *owner's* grants — and it is the currency this
    file's own sweep missed once already, in the worst possible place. Until this
    epic the rule was that `pulse_app` held none of it. ADR 0094 opens three point
    resolvers, each answering one question with a uuid; E1-11's D7 opens one writer
    that takes an address and never a name; and the security round's F2 opens a
    second writer that takes a person and a section and writes the one role its own
    body names. This is the assertion that those five are the only five.

    **Two of the five write, and that is not a widening of this rule but the
    instrument it now has to carry.** A grant bounds a table and its columns and
    cannot bound a column's *value*: there is no `GRANT INSERT (role =
    'INSTRUCTOR')`. So where a writer must be restricted to one value — an address
    and never a name, an `INSTRUCTOR` and never a `CARE` — the restriction lives in
    a function body and the caller holds `EXECUTE` rather than the grant. Each such
    door is a door, and each is here by name.

    **One equality over both tickets' grants, not one per ticket.** E1-12 and E1-11
    opened this door from opposite ends in the same epic and each branch pinned its
    own set; two closed sets over one fact is not an inventory, because each is
    satisfied by the other's grants being present. The merged list is
    `SANCTIONED_APPLICATION_EXECUTE` at the head of this file, where every entry
    carries the sentence that admits it.

    **Why an equality rather than a ceiling.** A sixth function granted to
    `pulse_app` is a sixth door into whatever its owner can read, and nothing else
    in this build would mention it: `alembic check` reads no `pg_proc` entry in
    either direction, the grantee sweep below asks *who* holds something rather
    than *how many things*, and the refusal above is scoped to the Care door. A
    convenience wrapper that returned "the person and their name" would satisfy
    every other test in this file.

    **Each sanctioned name must be *found*, not merely permitted**
    (`docs/MISTAKES.md` entry 35). A sweep that reported nothing for `pulse_app` —
    the wrong catalog, a filter that matches no function, a role that does not
    exist — satisfies "nothing beyond the inventory" perfectly, and would go on
    satisfying it after the grants were dropped and the doors stopped working.

    **The mutation it exists to survive**: `GRANT EXECUTE ON FUNCTION public.<a
    sixth definer function> TO pulse_app`, and its quieter sibling, a migration
    that omits `REVOKE ALL … FROM PUBLIC` on a new definer function — `PUBLIC`
    includes `pulse_app`, so both arrive here.
    **The near miss it tolerates**: a sixth `SECURITY DEFINER` function that
    `pulse_app` may not execute. That is somebody else's door and
    `test_no_role_outside_this_scheme_is_granted_anything_in_public` is where its
    grantee is judged.
    """
    functions = security_definer_functions(db_session, APPLICATION_ROLE)
    assert functions, (
        "This project defines no `SECURITY DEFINER` function in `public` at all, so this "
        "inventory is being compared against a sweep that looked at nothing."
    )

    executable = sorted({row["name"] for row in functions if row["executable"]})
    missing = [name for name in SANCTIONED_APPLICATION_EXECUTE if name not in executable]
    assert not missing, (
        f"`{APPLICATION_ROLE}` may execute {executable}, and {missing} are missing from it. Those "
        "are ADR 0094's point-resolution functions and E1-11's `record_roster_email`: without the "
        "first a verified subject reaches no stored identity on either door — E1-12's whole "
        "subject — and without the last the roster sync can store no address at all, while every "
        "refusal in this file stays green. It also means this sweep has not been seen finding an "
        "`EXECUTE` on a role that certainly holds one, so the equality below would be satisfied by "
        "an instrument that reports nothing for anybody."
    )

    beyond = [name for name in executable if name not in SANCTIONED_APPLICATION_EXECUTE]
    assert not beyond, (
        f"`{APPLICATION_ROLE}` may execute {beyond}, which no ticket sanctioned. The inventory is "
        f"{list(SANCTIONED_APPLICATION_EXECUTE)} and each entry carries the sentence that admits "
        "it, beside the constant at the top of this file. A `SECURITY DEFINER` function runs as "
        "its owner, so `EXECUTE` on one is a privilege on everything that owner can read — held by "
        "the connection every screen in the product runs on. If a fifth is genuinely needed, add "
        "it there with its sentence and say in the pull request what the caller can now reach that "
        "it could not before."
    )


def test_the_resolve_definers_privileges_are_exactly_the_point_lookups_it_answers(
    db_session: Any,
) -> None:
    """E1-12: the second definer is small, and its size is the whole of what the door opens.

    The same rule `test_the_reveal_functions_owner_holds_exactly_the_privileges_its_job_needs`
    holds over the Care door's owner, applied to the owner ADR 0094 introduces —
    and it matters more here, because `pulse_app` may call this one and `pulse_app`
    is the connection every request in the product runs on. What that connection
    can reach through these functions is exactly the set of grants this role holds.

    **Both grains, because the interesting half is at column grain.** Five of the
    six entries are `GRANT SELECT (…)` on `user` and `person`, which
    `has_table_privilege` does not report at all — the mechanism `COLUMN_GRANTEES`
    above was added for, and the one ADR 0001 rejects by name for `pulse_app`
    precisely because somebody always reaches for it. A whole-table `SELECT` on
    `person` granted here instead of five columns would look identical from the
    outside and would put `person.identity_name` behind a function `pulse_app` may
    call.

    **Exactly, not at least**, in both directions: the second list means the doors
    cannot answer and some other test is about to fail for a reason that reads as
    unrelated.

    **What it cannot see** (`docs/MISTAKES.md` entry 14): a change *within* those
    six. The functions could come to return a different shape over the same columns,
    or to match on something else, and nothing here moves. The grant is the outer
    bound on the blast radius rather than a description of the body;
    `tests/unit/test_no_service_reads_an_identity_table_directly.py` and the SQL
    file's own review are what read the bodies.
    """
    require_role(db_session, RESOLVE_DEFINER_ROLE)
    relations = [row[0] for row in db_session.execute(text(PUBLIC_RELATIONS))]
    assert relations, (
        "There is no table or view in `public`, so this sweep has nothing to ask about and the "
        "comparison below would be between an empty set and six expected members."
    )

    held_tables = {
        (relation, privilege)
        for relation in relations
        for privilege in TABLE_PRIVILEGES
        if db_session.execute(
            text(HAS_TABLE_PRIVILEGE),
            {
                "role": RESOLVE_DEFINER_ROLE,
                "relation": f"public.{relation}",
                "privilege": privilege,
            },
        ).scalar_one()
    }
    held_columns: set[tuple[str, str, str]] = set()
    for relation in relations:
        for column, _ in public_table_columns(db_session, relation):
            for privilege in COLUMN_PRIVILEGES:
                on_column = db_session.execute(
                    text(HAS_COLUMN_PRIVILEGE),
                    {
                        "role": RESOLVE_DEFINER_ROLE,
                        "relation": f"public.{relation}",
                        "column": column,
                        "privilege": privilege,
                    },
                ).scalar_one()
                if on_column and (relation, privilege) not in held_tables:
                    held_columns.add((relation, column, privilege))

    unexpected = sorted(
        [
            f"{relation}:{privilege}"
            for relation, privilege in held_tables - RESOLVE_DEFINER_PRIVILEGES
        ]
        + [
            f"{relation}.{column}:{privilege}"
            for relation, column, privilege in held_columns - RESOLVE_DEFINER_COLUMN_PRIVILEGES
        ]
    )
    missing = sorted(
        [
            f"{relation}:{privilege}"
            for relation, privilege in RESOLVE_DEFINER_PRIVILEGES - held_tables
        ]
        + [
            f"{relation}.{column}:{privilege}"
            for relation, column, privilege in RESOLVE_DEFINER_COLUMN_PRIVILEGES - held_columns
        ]
    )
    assert not unexpected and not missing, (
        f"`{RESOLVE_DEFINER_ROLE}` owns the point-resolution functions `{APPLICATION_ROLE}` may "
        f"call, so what it holds is what those functions can reach. Beyond what its job needs: "
        f"{unexpected}. Missing from what its job needs: {missing}.\n\n"
        "The first list is the one to read first, and a whole-table entry on `user` or `person` "
        "where a column entry was expected is the quietest way for it to be wrong: it reads as "
        "tidier SQL and it puts every column of those tables — `person.identity_name` among them — "
        "behind a function the application connection may call. ADR 0094 fixes the set at five "
        "columns and one table, and says of them: 'no identity-bearing column among them: ids, the "
        "platform reference, and the subject key being matched'.\n\n"
        "The second list means resolution cannot answer: without the column reads a subject "
        "resolves to nothing on either door, and without `web_login_subject:SELECT` the web door "
        "lands every person on the no-account page.\n\n"
        "If the owner has come to *own* a relation rather than to be granted on it, that shows up "
        "here as every privilege on that relation at once."
    )


# ---------------------------------------------------------------------------
# The Care door: open, single, and audited.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_neither_runtime_role_holds_any_privilege_on_user_identity(db_session: Any) -> None:
    """The rule as *stated*, beside the tests that provoke it.

    Where two mechanisms could refuse the same statement, a behavioural test
    cannot say which one did — `docs/MISTAKES.md` entry 3's second rule — so the
    catalog is asked directly: no privilege of any kind, for either runtime role,
    including the ones a `SELECT` test would never notice. `UPDATE` reads nothing
    and lets a name be overwritten; `REFERENCES` lets a foreign key probe for a
    value's existence.

    **A column grant is the one that made "of any kind" false**, and closing it is
    E0-33's last repair. `GRANT SELECT (identity_name) ON public.user_identity TO
    pulse_app` is recorded in `pg_attribute.attacl`, which `has_table_privilege`
    does not read: measured on the running stack, the whole-table grant fails four
    tests in this file and the column grant failed **none**, because `SELECT *`
    stays refused and every behavioural refusal here selects `*`. So for that
    route this catalog assertion is not the second half of a pair — it is the only
    guard there is, which is why this test is now `invariant`-marked and its
    sibling behavioural tests cannot stand in for it.

    **Asked through `ways_to_reach_identity`**, so the two questions this file asks
    about identity are asked with one instrument: what a role a runtime role can
    *become* may do, and what the runtime roles may do themselves.
    `IDENTITY_PROBES` is the single place a mechanism is added, and a mechanism
    added there reaches both without anybody remembering this test exists.

    **The execute mechanism is filtered out here and nowhere else**, and that is
    the asymmetry rather than an exemption. Both runtime roles hold `EXECUTE` on a
    definer function *by design* — `pulse_care` on the Care door, because §4 and
    §6.2 require that door to be open, and since E1-12 and E1-11 `pulse_app` on
    five functions that return no identity (ADR 0094, E1-11's D7 and the security
    round's F2) — so a rule
    that reported either would fail against the correct schema. It is asserted
    separately instead, and on each side by an equality beside a refusal:
    `test_the_application_role_may_execute_only_the_point_resolvers` says which
    five `pulse_app` may call, `test_the_application_role_may_not_execute_the_
    reveal_function` says it may not open the Care door, and
    `test_pulse_care_may_execute_exactly_the_two_halves_of_the_care_door` says
    `pulse_care` may call exactly those two. Asked about a role a runtime role can
    *become*, the same mechanism is dangerous and is not filtered.

    **Two controls.** The application role must be able to read a view, so that
    "no privilege anywhere" cannot be the answer the probes give to everything.
    And the definer must be reported as *having* a route, so that a probe set which
    answers empty for every role fails here rather than passing.

    (`ways_to_reach_identity`, `IDENTITY_PROBES` and the three probes themselves
    live in E0-33's section at the end of this file, beside the membership sweep
    that is the other caller.)
    """
    views = read_views(db_session)
    assert views, "There is no view in `public`, so the control below has nothing to check."

    routes: dict[str, list[str]] = {}
    for role in RUNTIME_ROLES:
        require_role(db_session, role)
        routes[role] = [
            description
            for mechanism, description in ways_to_reach_identity(db_session, role)
            if mechanism != IDENTITY_BY_EXECUTE
        ]

    readable = [
        view
        for view in views
        if db_session.execute(
            text(HAS_TABLE_PRIVILEGE),
            {"role": APPLICATION_ROLE, "relation": f"public.{view}", "privilege": "SELECT"},
        ).scalar_one()
    ]
    assert readable, (
        f"`has_table_privilege` reports that `{APPLICATION_ROLE}` may read none of {views}. It "
        "then reports nothing for any table, and the assertion below is true of a database with "
        "no grants at all rather than of this ticket's grant model."
    )

    definer = the_reveal_definer(db_session)
    assert ways_to_reach_identity(db_session, definer), (
        f"The identity probes report no route at all for `{definer}`, the owner of the reveal "
        f"function — which holds `SELECT` on `{IDENTITY_TABLE}` by construction (ADR 0043) and "
        "may execute what it owns. So the probes answer empty for a role that certainly has a "
        "route, and the assertion below is satisfied by an instrument that finds nothing for "
        "anybody rather than by a schema that grants nothing."
    )

    granted = {role: found for role, found in routes.items() if found}
    assert not granted, (
        f"The runtime roles can reach `{IDENTITY_TABLE}`: {granted}. E0-10 gives `pulse_app` 'no "
        "grant of any kind' on it, and `pulse_care` no `SELECT` either — Care's access is the "
        "audited function and nothing else, so that a name cannot be obtained without leaving a "
        "record.\n\n"
        "**A route naming a single column is the quiet one.** It leaves `SELECT *` refused, so "
        "the three behavioural refusals in this file go on passing while every student's name is "
        "readable one column at a time — measured: the whole-table grant fails four tests here, "
        "the column grant failed none until this assertion existed. ADR 0001 rejects column "
        "grants by name in its 'Alternatives rejected', which is precisely why somebody reaches "
        "for one when a screen needs a name."
    )


def test_pulse_care_may_execute_exactly_the_two_halves_of_the_care_door(db_session: Any) -> None:
    """E0-10's central criterion, at the count E0-26 item 1 settled it to.

    "`pulse_care` gets `EXECUTE` on a **single** `SECURITY DEFINER` function that
    returns identity and writes the audit row in the same transaction, so a name
    cannot be obtained without leaving a record" — E0-10, and the reason it gave for
    the number is the one that still governs: every additional door is a way to
    obtain a name without leaving a record.

    E0-26 item 1 split that door because writing the record in the caller's
    transaction let the caller roll it back. `record_identity_reveal` writes the
    record and the caller commits it; `reveal_student_identity` returns identity
    only against a record that is already committed. The first half returns a `uuid`
    and no identity on any path, so it is not a second way to obtain a name — it is
    the turnstile in front of the one way, and two is the settled count. A **third**
    is the thing E0-10's sentence was about.

    **This was an assertion inside `the_care_door` until the two downgrade tests
    ran it against E0-10's schema and it reported a correct database as wrong.** A
    count is a fact about a revision. This test knows it is looking at head, so the
    count lives here; the downgrade tests state none, because neither is about the
    door's shape. That is also why this is a test rather than a stricter helper: a
    helper's assertion fires wherever the helper is called, including in nine places
    that are asking about something else.

    **Not `invariant`-marked, by this file's own line**, which the E0-33 section
    below draws: a marked test guards one *route* into identity — a direct read, a
    join from a view, `EXECUTE` on the reveal, `SET ROLE` — and an inventory asserts
    that the grant set has no member nobody sanctioned, which is a precondition for
    the doors being the only doors rather than an instance of §4.1 itself. "How many
    doors are there" is an inventory. The doors themselves are marked next door.

    **The mutation it exists to survive**: a later migration adding a third
    `SECURITY DEFINER` function and granting `EXECUTE` on it to `pulse_care` — a
    convenience wrapper, a bulk variant, an E10 replacement landed beside the old
    one rather than instead of it. Nothing else in this file counts them: the
    grantee sweeps ask *who* holds something, never *how many things*.
    """
    door = the_care_door(db_session)

    assert len(door) == CARE_DOOR_HALVES, (
        f"`{CARE_ROLE}` may execute {len(door)} `SECURITY DEFINER` functions: "
        f"{[row['signature'] for row in door]}. E0-26 item 1 settles the count at "
        f"{CARE_DOOR_HALVES} — `{RECORD_FUNCTION}`, which writes the record and returns its id "
        f"and no identity on any path, and `{REVEAL_FUNCTION}`, which returns identity only "
        "against a record the caller has already committed.\n\n"
        "**More than two is the case E0-10's 'single' was written about**: every additional door "
        "is a way to obtain a name without leaving a record, and the guarantee is that there is "
        "exactly one way in. Fewer than two means one half of the split is missing, and "
        "`tests/integration/test_the_reveal_commits_its_record.py` diagnoses which — its "
        "`reveal_interface` fixture fails naming the absent function."
    )


def test_the_care_role_is_refused_a_direct_select_on_user_identity(db_session: Any) -> None:
    """Criterion: "`pulse_care` cannot `SELECT` from `user_identity` directly".

    This is the criterion that makes the audit trail a property rather than a
    convention. If Care could read the table, the reveal function would be one of
    two ways to obtain a name and only one of them writes the row — which is the
    alternative ADR 0001 rejected in as many words: "it makes the audit trail a
    convention that a future code path can skip".

    The control is the function call the next test asserts succeeds: Care can
    reach identity, so a refusal here is about the *route*, not about Care being
    locked out.
    """
    with acting_as(db_session, CARE_ROLE):
        failure = refused(db_session, READ_IDENTITY)

    assert failure is not None, (
        f"`{CARE_ROLE}` read `{IDENTITY_TABLE}` directly. Then a name can be obtained without the "
        "reveal function, and therefore without the audit row it writes in the same transaction — "
        "and §4's 'every identity access is automatically audit-logged with actor, timestamp, and "
        "case' is a convention that the next code path can skip. "
        "`test_the_care_roles_grants_are_enough_to_complete_a_reveal` is the "
        "other half: the door stays open, through the function."
    )
    assert sqlstate(failure) == INSUFFICIENT_PRIVILEGE, (
        f"The read failed with SQLSTATE {sqlstate(failure)} rather than {INSUFFICIENT_PRIVILEGE}: "
        f"{failure}. A missing table would satisfy 'it failed' and would mean something else "
        "entirely."
    )


def test_the_care_roles_grants_are_enough_to_complete_a_reveal(
    care_connections: Any, committed_rows: Any
) -> None:
    """Criterion: "a `pulse_care` connection **can** still obtain identity".

    The Care path is a requirement and not an oversight (§4, §6.2: "traceability
    exists for safety"), and this test is what stops a later change closing it
    while every denial test above stays green. A wall where the ticket asks for a
    door fails nothing else in this file.

    **This module's question is whether the grants are enough**, which is why it
    lives here beside them and not only in E0-26's module. Every other test in this
    section asserts that something is *refused*, and a grant list trimmed one entry
    too far satisfies all of them: `EXECUTE` missing on either half, or the
    definer's `SELECT` on `audit_log` missing, closes the door while every refusal
    stays green. It was renamed when E0-26 item 1 split the door in two: the old
    name ended "…through_the_one_function_it_may_execute", which asserted the count
    in its title and asserted it wrongly the moment there were two. The count is now
    `test_pulse_care_may_execute_exactly_the_two_halves_of_the_care_door`'s alone.

    **The behavioural half is E0-26's**, in
    `tests/integration/test_the_reveal_commits_its_record.py`: what the reveal does
    with an uncommitted record, a revoked actor or a substituted subject is that
    module's subject, and this one deliberately only walks the happy path.

    The returned row is compared against the identity that was seeded, rather
    than merely being non-empty: a function that returns a row of nulls, or the
    user's key back, would satisfy "it returned something" and reveal nobody.
    """
    subject = seed_identity(committed_rows)
    hats = committed_rows.graph.care_and_instructor_person()
    committed_rows.commit()

    rows = open_the_care_door(care_connections(), actor=hats["person"], subject=subject["user_id"])

    assert identity_in(rows) & subject["identity_values"], (
        f"The Care door returned {rows} for the seeded user, which carries "
        f"{sorted(subject['identity_values'])}. E0-10 ships this door as the proof that Care "
        "re-identification works — 'E10 replaces the stub with the real audited reveal', so "
        "what E10 inherits has to be a door rather than a wall. A reveal that returns no identity "
        "is a wall with a handle painted on it."
    )


@pytest.mark.invariant
def test_the_care_connection_cannot_forge_or_suppress_the_record_the_door_writes(
    care_connections: Any, committed_rows: Any
) -> None:
    """The record is written *for* the caller and is not writable *by* it.

    **This test replaces `test_the_reveal_writes_its_audit_row_in_the_callers_own_
    transaction`, which E0-26 item 1 inverted.** That test asserted that rolling
    back removed the audit row again, on the reasoning that the write must
    therefore have been on the caller's transaction rather than on a second
    connection. Its own docstring said the assertion described today's mechanism
    rather than a guarantee, named E0-26 as the ticket that would invert it, and
    named the half worth keeping: "the record is not something a caller adds
    afterwards, and it is not written by a path that could be skipped." That half
    is what is below, and E0-26's own module holds the rollback behaviour —
    `tests/integration/test_the_reveal_commits_its_record.py::test_a_caller_that_
    rolls_back_keeps_no_name_it_is_not_recorded_as_having_taken` reads the
    surviving count from a second connection, which is what the old assertion could
    not do.

    **Why the property matters more after the split than before it.** The record is
    now committed by the *caller*: `record_identity_reveal` writes it and the caller
    runs the `COMMIT`. So "can this caller write one without going through the door,
    or remove one after going through it" is the question that decides whether §4's
    "every identity access is automatically audit-logged" is a property or a habit.
    A `pulse_care` connection that could `INSERT` into `audit_log` could record a
    reveal that never happened, or one naming somebody else; one that could `DELETE`
    could take a name and then take the record of having taken it, which is exactly
    the hole E0-26 exists to close, reached by a different route.

    **Behaviour, beside a catalog rule that already exists.**
    `test_the_runtime_roles_hold_no_privilege_on_a_base_table_beyond_the_reveals_own`
    asserts as an exact equality that `pulse_care` holds nothing on any base table
    including `audit_log`. That is the rule as *stated*; this is the rule
    *working*, and `docs/MISTAKES.md` entry 3 is why both exist — "the catalog test
    cannot see whether the rule works and the behavioural test cannot see whether
    it exists". Every other behavioural refusal in this file is about
    `user_identity`; nothing until now provoked one on the audit table.

    **Two controls.** The door is opened first on the same connection, so a refusal
    below is attributable to `audit_log` rather than to a role that can do nothing;
    and each refusal is checked on its SQLSTATE, because a malformed statement
    answers 42601 or 42703 and would satisfy a bare "it failed".

    **The mutation it exists to survive**: `GRANT INSERT ON public.audit_log TO
    pulse_care`, which is what somebody writes when the queue needs to log something
    the door does not log for it.

    **And the reason `attempt` checks `returns_rows` is this test**, though the
    check was added for a failure next door. Neither statement below returns rows,
    so under exactly the mutation named above the insert would succeed, the helper
    would raise `ResourceClosedError` — not a `DatabaseError`, so it escapes the
    `except` — and this test would error out rather than failing on the assertion
    that says a forged record is possible. It passed all the way through the repair
    round with that hole in it, because a refused statement raises before the rows
    are asked for: the bug was reachable only along the path where the finding is.
    """
    subject = seed_identity(committed_rows)
    hats = committed_rows.graph.care_and_instructor_person()
    committed_rows.commit()

    caller = care_connections()
    revealed = open_the_care_door(caller, actor=hats["person"], subject=subject["user_id"])
    assert identity_in(revealed) & subject["identity_values"], (
        "The control failed: the Care door did not return the seeded identity, so the refusals "
        "below would be about a connection that cannot do anything. "
        "`test_the_care_roles_grants_are_enough_to_complete_a_reveal` diagnoses that."
    )

    # `WHERE false` on the delete, because a privilege check does not depend on the
    # predicate and an unqualified `DELETE` written into a test file is a statement
    # whose harmlessness rests entirely on a rollback behaving.
    forgeries = {
        "forge a record": f'INSERT INTO public."{AUDIT_TABLE}" DEFAULT VALUES',
        "suppress a record": f'DELETE FROM public."{AUDIT_TABLE}" WHERE false',  # noqa: S608
    }
    for what, statement in forgeries.items():
        _, failure = attempt(caller, statement, {})
        caller.rollback()

        assert failure is not None, (
            f"`{CARE_ROLE}` could {what} directly: `{statement}` was accepted. The Care connection "
            "commits the record the door writes for it, so a connection that can also write or "
            "remove rows in that table decides what the log says — §4's 'every identity access is "
            "automatically audit-logged with actor, timestamp, and case' then records whatever the "
            "credential holder chose, and §6.2's review outside the Care office is reading it. "
            "SPEC §8 makes `audit_log` append-only, and the door's owner is the only role that "
            "may write to it."
        )
        assert sqlstate(failure) == INSUFFICIENT_PRIVILEGE, (
            f"`{statement}` failed with SQLSTATE {sqlstate(failure)} rather than "
            f"{INSUFFICIENT_PRIVILEGE} (insufficient privilege): {failure}. A missing table, a "
            "malformed statement or an aborted transaction would each satisfy 'it failed' while "
            f"saying nothing about what `{CARE_ROLE}` may do — and the table has to exist, since "
            "the door writes the record into it."
        )


@pytest.mark.invariant
def test_the_care_door_refuses_an_actor_with_no_live_care_assignment(
    care_connections: Any, committed_rows: Any
) -> None:
    """Criterion: the door refuses a non-Care actor **on its own**, with no service involved.

    E0-10 settles the design that an earlier version of the ticket left
    contradictory: the check lives in *both* places. `services/safety.py` verifies
    before calling, and the function takes the acting person and verifies a live
    `CARE` assignment itself. This is the second half, and the reason it has its
    own test is entry 3's second rule — where both can refuse, a behavioural test
    through the service cannot say which one did. Nothing here goes near the
    service: the call is SQL, on a `pulse_care` connection, exactly as a caller
    who reached the door by some other route would make it.

    **E0-26 item 1 moved the check to the first half of the door**, which is the
    one a caller reaches first: `record_identity_reveal` refuses an actor with no
    live `CARE` assignment, exactly as the old three-argument function did, so the
    refusal below arrives before any record exists to spend. It is asserted here as
    a raise, and this is where the assertion got stronger. The old version accepted
    either a raise or an empty result, because E0-10's words were "gets nothing"
    and it did not choose. E0-26's shape decides it: the record call is declared
    `RETURNS uuid`, so "no identity came back" is true of every call it will ever
    make and would be an assertion about nothing.

    **The control is the same call with a Care actor**, which is what tells "this
    actor is refused" apart from "this door refuses everyone" and from a database
    that has stopped working. Both actors are real people in the same graph: one
    holds a `CARE` assignment and a teaching assignment (§2.1's two-hat case), the
    other holds only a lead-faculty assignment.

    "Live" is read as "exists" here, because E0-09's `role_assignment` has no
    end-dating — an assignment that has been revoked is a deleted row today. When
    E10 or E9 adds validity dates, an expired assignment becomes a second case
    worth its own test, and this one keeps its meaning.

    **The reveal half re-checks the same thing**, and that is E0-26's module:
    `test_the_reveal_commits_its_record.py::test_the_reveal_refuses_a_record_whose_
    actor_no_longer_holds_care` revokes the assignment between the record and the
    reveal, which is the case this test cannot reach.
    """
    subject = seed_identity(committed_rows)
    hats = committed_rows.graph.care_and_instructor_person()
    without_care = hats["lead"][committed_rows.graph.person_column]
    committed_rows.commit()

    assert without_care != hats["person"], (
        "The fixture handed back the same person for the Care actor and the lead-faculty actor, "
        "so the two calls below would be the same call and the refusal would prove nothing. "
        "`SupervisionGraph.care_and_instructor_person` builds the lead with its own person."
    )

    caller = care_connections()
    allowed = open_the_care_door(
        caller,
        actor=hats["person"],
        subject=subject["user_id"],
        refusal_means=(
            "This is the control for the refusal below rather than the assertion: the actor here "
            "holds a live `CARE` assignment, so the door has to open before a refusal for an "
            "actor without one says anything about the assignment. "
            "`test_the_care_roles_grants_are_enough_to_complete_a_reveal` is where a Care actor "
            "being refused is diagnosed."
        ),
    )
    assert (
        identity_in(allowed) & subject["identity_values"]
    ), "The control call returned no identity, so there is nothing to contrast a refusal with."

    _, failure = attempt(
        caller, RECORD_CALL, {"actor": without_care, "subject": subject["user_id"]}
    )
    caller.rollback()

    assert failure is not None, (
        f"`public.{RECORD_FUNCTION}` accepted an actor who holds a lead-faculty assignment and no "
        "`CARE` assignment — the same call it accepted a moment ago for an actor who does hold "
        "one, which returned "
        f"{sorted(subject['identity_values'])}. The door is `SECURITY DEFINER`, so it reads "
        "`user_identity` with its owner's privileges no matter who calls it: the acting person's "
        "assignment is the only thing between a `pulse_care` connection and any student's name. "
        "E0-10: the function 'takes the acting person as an argument and verifies a live `CARE` "
        "assignment itself… a caller reaching the function by any other route still gets "
        "nothing'.\n\n"
        "**A record written here is worse than a name returned here**, which is why the refusal "
        "belongs on this half. `record_identity_reveal` returns no identity on any path, so a call "
        "it wrongly accepts hands back a committed record naming an innocent staff member — and "
        "the reveal that spends it then reads its actor out of that record."
    )


def public_table_columns(session: Any, table: str) -> list[tuple[str, str]]:
    """One table's columns and their types, as the table itself declares them."""
    return list(session.execute(text(TABLE_COLUMNS), {"table": table}).tuples())


def test_a_shadowed_table_does_not_change_what_the_care_door_returns(
    care_connections: Any, committed_rows: Any, db_session: Any
) -> None:
    """The E0-09 hijack, aimed at the two pieces of SQL in this ticket that bind late.

    Postgres searches the temporary schema **first** for relation names, and does
    so whether or not `pg_temp` appears in `search_path` — being unlisted is what
    puts it first. E0-09's trigger named `role_assignment` unqualified and every
    guard in it read a table the writer had created. A `SECURITY DEFINER` function
    is the same defect with the stakes moved: it runs with its owner's privileges,
    so a caller who can redirect a name inside it spends those privileges on a
    table of their own choosing, or — the cheaper attack — empties the assignment
    check that is supposed to refuse them.

    **The shadow is stood up by `pulse_care` itself**, not by the bootstrap
    identity, because that is who would do it: creating a temporary table needs
    only the `TEMPORARY` privilege, which Postgres grants to `PUBLIC` by default.
    E0-09's version of this test connected as the superuser and said so as a
    stated limit; this ticket's criterion asks for the stronger form.

    **The hijack is asserted to be live** between the two calls rather than
    assumed. Without that pair of assertions this test would pass on the day the
    temp table silently failed to be created, and it would look exactly as it
    looks now.

    **What is shadowed is discovered from the functions' own bodies**, so the test
    aims at the tables they actually read rather than at a guess. The shadow copies
    the real column list out of the catalog rather than using `CREATE TABLE …
    (LIKE …)`: `LIKE` needs `SELECT` on the source, which `pulse_care` does not
    have on `user_identity` — and a shadow missing a column would make the
    *vulnerable* function fail with "column does not exist", refusing the call and
    turning this test green against the defect (`docs/MISTAKES.md` entry 3).

    **E0-26 item 1 doubled what this has to cover, and it is one call rather than
    two.** The door is now `record_identity_reveal` and `reveal_student_identity`,
    and both read `role_assignment`, so the shadow set is the union of what both
    bodies name. Driving the whole door once with the shadows standing exercises
    both halves: the record call's assignment check meets an empty
    `role_assignment` if it binds late, and the reveal meets an empty
    `user_identity` and an empty `audit_log` if it does.

    **`audit_log` in the shadow set is why `user_identity` has to be in it too.**
    A vulnerable record call writes its row into `pg_temp.audit_log` and a
    vulnerable reveal reads it back from there, and the caller commits in between —
    so the committed-record check E0-26 adds is satisfied *inside the shadow* and
    is not what catches this. The empty `user_identity` is: there is no name in it
    to return. If a later change stops the reveal naming `user_identity`, this test
    stops covering the reveal half, and the non-emptiness assertion below is what
    would say so.

    **The shadow now stands on a real `pulse_care` login rather than on a `SET
    ROLE`**, because `pg_temp` is per session and the door has to be driven on the
    session that owns the shadow — and the door cannot be driven inside
    `db_session` at all, whose transaction is never committed. `db_session` stays
    for the catalog reads, which need the bootstrap identity's view and take no
    part in the attack.
    """
    subject = seed_identity(committed_rows)
    hats = committed_rows.graph.care_and_instructor_person()
    committed_rows.commit()

    caller = care_connections()
    baseline = open_the_care_door(caller, actor=hats["person"], subject=subject["user_id"])
    assert identity_in(baseline) & subject["identity_values"], (
        "The door did not return the seeded identity before any shadow existed, so the comparison "
        "after one is created would be between two wrong answers. "
        "`test_the_care_roles_grants_are_enough_to_complete_a_reveal` diagnoses that."
    )

    halves = the_care_door(db_session)
    bodies = "\n".join(
        db_session.execute(text(FUNCTION_BODY), {"signature": half["signature"]}).scalar_one() or ""
        for half in halves
    )
    tables = [row[0] for row in db_session.execute(text(PUBLIC_TABLES))]
    named = [table for table in tables if re.search(rf"\b{re.escape(table)}\b", bodies)]
    assert named, (
        f"The two halves of the door name none of the {len(tables)} tables in `public` anywhere in "
        "their bodies, so there is nothing to shadow and this test would report success having "
        "attempted nothing. A door that reads no table cannot be returning identity from one."
    )
    assert IDENTITY_TABLE in named, (
        f"The door's bodies name {named}, which does not include `{IDENTITY_TABLE}`. That table is "
        "what makes this test catch a late-binding *reveal*: with `audit_log` shadowed, a "
        "vulnerable record call writes its row into `pg_temp` and a vulnerable reveal reads it "
        "back from there, so the committed-record check is satisfied inside the shadow and only an "
        "empty identity table stops a name coming out. If the reveal has stopped naming it — "
        "reading identity through a view, say — the shadow set has to follow it there, or this "
        "test covers the record half alone while reading as though it covered both."
    )

    for table in named:
        columns = ", ".join(
            f'"{name}" {declared}' for name, declared in public_table_columns(caller, table)
        )
        assert columns, (
            f"`public.{table}` reports no columns, so the shadow would be an empty-shaped "
            "table and a vulnerable function would fail on the column list rather than read "
            "the shadow."
        )
        _, refusal = attempt(caller, f'CREATE TEMPORARY TABLE "{table}" ({columns})', {})
        assert refusal is None, (
            f"`{CARE_ROLE}` could not create a temporary table called `{table}`: {refusal}. "
            "The `TEMPORARY` privilege is granted to `PUBLIC` by default, which is what makes "
            "this attack available to any authenticated role — so if this deployment revokes "
            "it deliberately, that is a second control worth saying out loud in the pull "
            "request, and this test then has to stand the shadow up as the bootstrap identity "
            "the way E0-09's did, with the weaker claim stated."
        )
    caller.commit()

    for table in named:
        bare, qualified = caller.execute(
            RESOLVE_BOTH, {"bare": f'"{table}"', "qualified": f'public."{table}"'}
        ).one()
        assert bare is not None and qualified is not None and bare != qualified, (
            f'After `pulse_care` created a temporary table called "{table}", the bare name '
            f"resolves to {bare} and `public.{table}` to {qualified}. They have to differ, and "
            "neither may be null: if the bare name has not moved, the shadow is not on this "
            "session and the call below is the ordinary call the baseline already made."
        )
    caller.commit()

    shadowed = open_the_care_door(
        caller,
        actor=hats["person"],
        subject=subject["user_id"],
        refusal_means=(
            f"The shadow tables {named} are the only thing that changed between this call and the "
            "baseline one, which succeeded. So one of the two halves resolved a relation name "
            "into `pg_temp` — the assignment check finding an empty `role_assignment` and refusing "
            "a Care actor is the likeliest shape, and the reveal finding no record in an empty "
            "`audit_log` is the next. That is the hijack, and it is a refusal here rather than a "
            "wrong answer only by luck."
        ),
    )
    assert identity_in(shadowed) & subject["identity_values"], (
        f"With an empty `pg_temp` copy of {named} in the session, the door returned {shadowed} "
        f"instead of the identity it returned a moment ago ({sorted(subject['identity_values'])}). "
        "The functions are reading tables the caller created: Postgres searches the temporary "
        "schema first for relation names, and `pulse_care` needs only the `TEMPORARY` privilege — "
        "granted to `PUBLIC` by default — to put one there. ADR 0027's fix is both halves, and "
        "these functions need both more than the trigger did, because they run as their owner: "
        "schema-qualify every relation they name, and set "
        "`SET search_path = pg_catalog, public, pg_temp`, naming `pg_temp` last because omitting "
        "it is what puts it first. `test_identity_separated_views.py` asserts each half out of the "
        "catalog; this is the one that shows what they are for."
    )


def test_no_security_definer_function_is_owned_by_a_superuser(db_session: Any) -> None:
    """What the one door in the wall is allowed to spend, asserted over the owner.

    A `SECURITY DEFINER` function runs with its **owner's** privileges, so the
    owner is the privilege the door actually opens — the grants to `pulse_care`
    only decide who may knock. Owned by the identity that runs migrations, the
    reveal is a superuser-privileged execution path handed to a role that is
    otherwise refused everything: measured on this stack, such a function
    returned `count(*) = 19` from `pg_catalog.pg_authid` — every role's password
    verifier — to a `pulse_care` session that was refused that same table one
    statement later. That is not extra hygiene, it is a read of the cluster's
    password hashes through the door this ticket deliberately opens.

    **Phrased over every `SECURITY DEFINER` function rather than over this one by
    name.** E10 replaces the reveal with the real audited one; a rule spelled
    `reveal_student_identity` would retire with it while the hazard stays exactly
    where it is. Any function added here later — E10's, or a future rebuild of
    this one — meets the same rule without anybody remembering it exists.

    **The mutation it exists to survive** is the one that produced the `pg_authid`
    read: `ALTER FUNCTION … OWNER TO` the migration identity. That identity is a
    superuser (ADR 0009 sanctions it for exactly that job), so re-owning turns
    this red, which is the whole assertion.

    `rolbypassrls` is asserted with `rolsuper` because they are one property with
    two spellings here — either lets the definer read past a control the schema
    thinks it has, and E0-02's review measured both reading straight through a
    deny-all policy. `rolcanlogin` is deliberately *not* asserted: a login is a
    credential surface rather than a privilege the function can spend, and
    forbidding it here would pin a provisioning decision this ticket leaves to
    whoever installs Pulse.
    """
    functions = security_definer_functions(db_session, CARE_ROLE)
    assert functions, (
        "This project defines no `SECURITY DEFINER` function in `public`, so this test swept "
        "nothing and would report success. E0-10 ships the Care door and E0-26 item 1 made it two "
        "functions; `test_the_care_roles_grants_are_enough_to_complete_a_reveal` diagnoses "
        "its absence."
    )

    connected_as = db_session.execute(text(CURRENT_ROLE)).scalar_one()
    assert db_session.execute(text(ROLE_ATTRIBUTES), {"role": connected_as}).one().rolsuper, (
        f"`pg_roles` does not report {connected_as!r} as a superuser, and that is the identity "
        "these tests connect as — the bootstrap one ADR 0009 sanctions for migrations. So this "
        "query cannot recognise a superuser at all, and the assertion below would pass against a "
        "function owned by one."
    )

    unbounded: dict[str, str] = {}
    for function in functions:
        owner = function["owner"]
        attributes = db_session.execute(text(ROLE_ATTRIBUTES), {"role": owner}).one_or_none()
        assert attributes is not None, (
            f"`{function['signature']}` is owned by {owner!r}, which has no row in `pg_roles`. "
            "Then nothing below is true of anything, and the owner cannot be checked at all."
        )
        held = [name for name in ("rolsuper", "rolbypassrls") if getattr(attributes, name)]
        if held:
            unbounded[function["signature"]] = f"{owner} holds {held}"

    assert not unbounded, (
        f"{unbounded}. A `SECURITY DEFINER` function executes as its owner, so the owner's "
        "attributes are what the function may do — and a superuser owner means the one function "
        "`pulse_care` may execute can read anything in the cluster, including "
        "`pg_catalog.pg_authid`, which holds every role's password verifier. That was reproduced "
        "on this stack before the owner was separated out: 19 rows, to a session refused that "
        "table directly one statement later. ADR 0001's whole scheme is that identity is reachable "
        "by exactly one audited route; a superuser-owned definer makes that route a general "
        "one.\n\n"
        "The fix is a role that owns the function and holds nothing else — no login, no "
        "membership, no relation of its own, and only the privileges "
        "`test_the_reveal_functions_owner_holds_exactly_the_privileges_its_job_needs` pins. Note "
        "this rule is about functions and says nothing about views: a view is only ever a "
        "`SELECT`, so an added line in one cannot execute anything, and who owns a view is a "
        "separate decision."
    )


def test_the_reveal_functions_owner_holds_exactly_the_privileges_its_job_needs(
    db_session: Any,
) -> None:
    """Exactly four, because a fifth is what there is to catch.

    The owner exists to be small. Once it is not a superuser
    (`test_no_security_definer_function_is_owned_by_a_superuser`), what the door
    opens is precisely the set of grants that role holds — so the interesting
    assertion is not "it can do its job" but "it can do nothing else". **Exactly,
    not at least**: a `UPDATE` on `user_identity` added to make some later
    migration convenient is invisible to every other gate in this build, because
    `alembic check` reads no grants at all and no test but this one enumerates
    them.

    The expected set is derived from sentences of the tickets rather than from the
    migration, and `REVEAL_DEFINER_PRIVILEGES` at the top of this file shows the
    derivation for each entry: the door returns identity, checks the actor's `CARE`
    assignment itself, writes the record, and — the fourth, from E0-26 item 1 —
    reads the record back. The `role_assignment` entry is the one that surprises
    people and is the half of the design that has to hold when the service is
    bypassed.

    **It said "exactly three" until E0-26 item 1**, and the number moved because
    the door changed rather than because the rule softened. Splitting the door into
    a record the caller commits and a reveal that spends it means the reveal reads
    its subject, its actor and its action out of `audit_log` instead of taking them
    from whoever called it, which needs `SELECT` there. What that widens is written
    out beside the constant: the owner could previously write a record it could not
    read back, and can now read the whole log — who revealed whom and when. The
    assertion stays an equality, because the equality is the control: a fifth entry
    arriving to make some later migration convenient is what this exists to catch,
    and `>=` would wave it through.

    **What this cannot see, stated rather than implied** (`docs/MISTAKES.md` entry
    14): a change *within* those four. The door may come to read a different
    column of `user_identity`, or every row of `role_assignment` rather than the
    actor's, and nothing here moves. The grant is the outer bound on the blast
    radius, not a description of the body. That reading matters more for the fourth
    entry than for the other three: `audit_log: SELECT` is what a reveal reading one
    record needs and what a sweep of every record needs, and this test cannot tell
    the two apart.

    Vacuity has no route in: the expected set is non-empty, so a
    `has_table_privilege` that answered `false` to everything fails this rather
    than passing it, and one that answered `true` to everything fails it too.
    """
    owner = the_reveal_definer(db_session)
    relations = [row[0] for row in db_session.execute(text(PUBLIC_RELATIONS))]
    assert relations, (
        "There is no table or view in `public`, so this sweep has nothing to ask about and the "
        "comparison below would be between an empty set and four expected members — failing for "
        "a reason that has nothing to do with grants."
    )

    held = {
        (relation, privilege)
        for relation in relations
        for privilege in TABLE_PRIVILEGES
        if db_session.execute(
            text("SELECT has_table_privilege(:role, :relation, :privilege)"),
            {"role": owner, "relation": f"public.{relation}", "privilege": privilege},
        ).scalar_one()
    }

    unexpected = sorted(
        f"{relation}:{privilege}" for relation, privilege in held - REVEAL_DEFINER_PRIVILEGES
    )
    missing = sorted(
        f"{relation}:{privilege}" for relation, privilege in REVEAL_DEFINER_PRIVILEGES - held
    )
    assert not unexpected and not missing, (
        f"`{owner}` owns both halves of the Care door, so what it holds is what that door can "
        f"reach. Beyond what its job needs: {unexpected}. Missing from what its job needs: "
        f"{missing}.\n\n"
        "The first list is the one to read first. A `SECURITY DEFINER` function spends its "
        "owner's privileges on behalf of a caller who does not have them, so every grant this "
        "role holds is reachable through the door `pulse_care` may open — and nothing else in "
        "this build would notice a new one, because `alembic check` compares schema and not "
        "grants. If the owner has come to own a relation rather than to be granted on it, that "
        "shows up here as every privilege on that relation at once.\n\n"
        "The second list means the door cannot do its job and some other test is about to fail "
        "for a reason that reads as unrelated: without `role_assignment:SELECT` it cannot check "
        "the actor's `CARE` assignment, without `audit_log:INSERT` it cannot leave the record that "
        "makes the read legitimate, and without `audit_log:SELECT` the reveal cannot read back the "
        "record whose subject and actor it is supposed to use instead of its caller's word.\n\n"
        "**If `audit_log:SELECT` is the entry in the first list, read E0-26 item 1 before removing "
        "it.** It is the fourth grant, it arrived with the split door, and it is the widest of the "
        "four: it lets the owner read every row of the log rather than only write to it. The "
        "comment on `REVEAL_DEFINER_PRIVILEGES` says what that costs. Removing it closes the "
        "reveal, which is a §4 and §6.2 failure rather than a tightening."
    )


# ---------------------------------------------------------------------------
# The migration that establishes the roles, run twice.
# ---------------------------------------------------------------------------


def test_alembic_upgrade_head_succeeds_where_the_roles_already_exist(
    migrated_database: Any,
    empty_database: Any,
    alembic_config_pointed_at: Any,
) -> None:
    """The ticket's "Reconcile first": the role migration tolerates a role it did not create.

    `.env.example` defaults `DB_APP_USER=pulse_app`, `scripts/db-init` creates it
    at `initdb` on any volume the Compose stack initialised, and this ticket's
    migration creates the same name — so a bare `CREATE ROLE pulse_app` aborts
    with `role "pulse_app" already exists` on every developer machine while
    passing in CI, which is the worst available split.

    Roles are cluster-wide, so this test is the case itself rather than a
    simulation of it: `migrated_database` is asked for first, which puts the
    roles in the cluster, and then a second, empty database in that same cluster
    is migrated from zero. `empty_database` is where E0-04 put "`alembic upgrade
    head` succeeds against an empty database", and this is that claim once the
    roles exist.
    """
    from alembic import command

    config = alembic_config_pointed_at(empty_database)
    try:
        command.upgrade(config, "head")
    except Exception as failure:
        pytest.fail(
            f"`alembic upgrade head` failed against an empty database in a cluster where this "
            f"ticket's roles already exist: {failure!r}. E0-10's 'Reconcile first' section: the "
            "role migration 'has to tolerate a role that already exists, and still end with the "
            "attributes and grants this ticket requires — so `CREATE ROLE` guarded by a "
            "`pg_roles` lookup, followed by the `ALTER ROLE` and `GRANT`/`REVOKE` statements "
            "applied unconditionally'. ADR 0009's provisioning table is the reason this is not "
            "hypothetical: the Compose stack, CI's drift job, the testcontainers fixture and a "
            "managed Postgres provision roles four different ways."
        )


def test_the_role_migration_corrects_an_attribute_it_did_not_write(
    migrated_database: Any,
    empty_database: Any,
    alembic_config_pointed_at: Any,
    migrated_engine: Any,
) -> None:
    """The second half of idempotent: the `ALTER ROLE` runs whether or not the role was created.

    "Creating it only when absent and assuming a bootstrap-created role is
    already correct would leave the two mechanisms free to disagree." So the role
    is given an attribute this ticket forbids, the migration is run, and the
    attribute has to be gone — which is the difference between a migration that
    *creates* a correct role and one that *ends with* a correct role.

    `CREATEDB` is the attribute chosen because it is harmless in a throwaway
    container and is one of the five `test_a_runtime_role_holds_none_of_the_
    attributes_that_bypass_a_grant` forbids. It is put back either way in the
    `finally`, because roles outlive the transaction — nothing here is rolled
    back by a fixture.
    """
    from alembic import command

    with migrated_engine.connect() as connection:
        require_role(connection, APPLICATION_ROLE)

    with migrated_engine.begin() as connection:
        connection.execute(text(f'ALTER ROLE "{APPLICATION_ROLE}" CREATEDB'))

    try:
        config = alembic_config_pointed_at(empty_database)
        command.upgrade(config, "head")
        with migrated_engine.connect() as connection:
            drifted = connection.execute(
                text("SELECT rolcreatedb FROM pg_roles WHERE rolname = :role"),
                {"role": APPLICATION_ROLE},
            ).scalar_one()
    finally:
        with migrated_engine.begin() as connection:
            connection.execute(text(f'ALTER ROLE "{APPLICATION_ROLE}" NOCREATEDB'))

    assert drifted is False, (
        f"`{APPLICATION_ROLE}` was given `CREATEDB` before `alembic upgrade head` ran, and still "
        "held it afterwards. The migration therefore only creates the role when it is absent and "
        "trusts whatever it finds otherwise — which is the state E0-10 refuses: 'Creating it only "
        "when absent and assuming a bootstrap-created role is already correct would leave the two "
        "mechanisms free to disagree.' On a Compose volume the role comes from "
        "`scripts/db-init/01-application-role.sh`; in CI's drift job from a shell step; in these "
        "tests from `tests/fixtures/database.py`; on a managed Postgres from the operator. The "
        "migration is the one mechanism that runs everywhere, so it is the one that has to end "
        "with the "
        "attributes stated."
    )


# ---------------------------------------------------------------------------
# The downgrade, and the one privilege it deliberately leaves behind.
# ---------------------------------------------------------------------------
#
# This revision's `downgrade()` has to be the inverse of its `upgrade()`, and for
# this revision that is not only a question of which objects exist. A privilege on
# an object the downgrade drops goes with the object; a privilege on an object
# that **survives** does not, and has to be revoked by hand. The first spelling of
# this revision revoked the definer's two table grants and left
# `GRANT SELECT ON public.role_assignment TO pulse_care` one statement away, still
# in place afterwards — a role holding a grant with no function left to spend it
# through, which is the shape of privilege nobody ever notices again. Enumerating
# the rest then found `USAGE ON SCHEMA public`, held by all three roles and
# written by this revision alone.
#
# ADR 0043 states the repaired rule as a property of the object rather than of the
# role: **a privilege on anything that outlives the downgrade is revoked, one
# guarded `IF EXISTS` per role**, with `CONNECT ON DATABASE` the single deliberate
# exception. The tests below are that rule and that exception. They are written
# against the rule rather than against the list, so a grant a later ticket adds to
# a surviving table is covered without anybody adding a line here: the roles come
# from the catalog, the relations come from `pg_class`, and the privileges are the
# whole of `TABLE_PRIVILEGES`.
#
# **They run against a database of their own.** `empty_database` is a second
# database in the same container, migrated from zero and dropped when the test
# ends, and it is what keeps a downgrade out of the session database — where it
# would drop `audit_log`, both views and the reveal function for every test after
# it. A test that poisons the fixture it shares is worse than no test, because the
# failures land in modules that did nothing wrong. Roles are cluster-wide and
# privileges on tables are not, so a fresh database is the same arrangement of
# privileges with none of the blast radius: `tests/fixtures/database.py` has already
# created `pulse_app` and `pulse_care`, and the migration creates the definer.
#
# **Not `invariant`-marked**, on the line `test_application_role_privileges.py`
# draws for the same reason: §4.1 is about what a reader of a running system can
# see, and this is about what a migration leaves behind in a database that is
# being taken apart.

# Postgres reports a statement naming a role that does not exist as SQLSTATE
# 42704, `undefined_object`. Asserted on the code rather than on the message for
# the reason `INSUFFICIENT_PRIVILEGE` gives above, and here there is a second: the
# statement that provokes it also names a table, and a run where
# `public.role_assignment` had gone missing would raise a differently-coded error
# with an equally plausible-looking message.
UNDEFINED_OBJECT = "42704"

# E0-10's own revision, named rather than reached relatively. Both ends of the
# three tests below are pinned to it: they upgrade *to* it and downgrade to the
# revision below it, so that neither end moves when a later ticket lands a
# revision on top.
#
# **Why the upgrade is pinned as well as the downgrade.** `-1` is relative to
# head, so from the moment any revision lands on top of this one, `alembic
# downgrade -1` undoes *that* revision, E0-10's views and grants are all still
# standing, and every assertion below — each of which is that some set is empty —
# is satisfied by a database nobody has changed (`docs/MISTAKES.md` entry 3, note
# 24). E0-11 is the ticket where that arrived, and it was measured with a
# throwaway revision whose whole content was one view:
# [`docs/disputes/E0-11-02.md`](../../docs/disputes/E0-11-02.md). Left at head,
# the *upgrade* is the other half of the same problem in the other direction —
# `privileges_held` would report a later revision's unrevoked grant as a defect in
# E0-10's `downgrade()`, which cannot revoke a grant it never made, and
# the door's shape is E0-26's rather than E0-10's, which is a fact about head
# rather than about the revision these two tests inspect.
#
# **That second hazard has already fired once, and the repair is worth knowing
# before writing another test down here.** `the_care_door` used to assert the
# number of `SECURITY DEFINER` functions `pulse_care` may execute, and both tests
# below broke on it the day E0-26 landed: they run against the schema *at* the
# identity revision, where E0-10's single three-argument door is exactly right, and
# a helper describing head told them a correct database was wrong. The count now
# lives in `test_pulse_care_may_execute_exactly_the_two_halves_of_the_care_door`,
# which knows which revision it is looking at. **Anything a helper asserts, it
# asserts down here too** — so a helper used by a downgrade test may only state
# what is true at every revision it will meet.
#
# **Only one identifier is written down**, and that is deliberate. Alembic
# resolves `<revision>-1` against the chain, so the parent is derived rather than
# spelled: a revision inserted between E0-09's and this one changes what gets
# undone on its own, where a second constant here would quietly keep naming the
# wrong parent.
IDENTITY_REVISION = "446183e8cc5f"
BELOW_THE_IDENTITY_REVISION = f"{IDENTITY_REVISION}-1"

# E0-26 item 1's revision, pinned for the same reasons and asserted separately.
# The three tests above are about what *E0-10's* downgrade takes back and cannot
# reach this one: both of their ends are pinned below it. That left this
# revision's own `downgrade()` — including a hand-written `REVOKE SELECT ON
# public.audit_log FROM pulse_reveal_definer`, which exists precisely because a
# privilege on a table that survives is the one thing a `DROP FUNCTION` cannot
# carry — executed by no test at all. Two reviewers found that independently on
# PR #53, and the test below is the answer.
THE_COMMITTED_RECORD_REVISION = "b336333a2805"
BELOW_THE_COMMITTED_RECORD_REVISION = f"{THE_COMMITTED_RECORD_REVISION}-1"

# Which roles hold what on the `public` schema, and on the database, as the
# catalog records it. `aclexplode` is what makes this readable without pinning an
# ACL string: an `aclitem` renders as `grantee=privileges/grantor`, and the
# grantor half is whichever identity ran the `GRANT` — the deployment's own
# superuser, which is `pulse_admin` in one place and `pulse_test_admin` in this
# fixture. Matching that text would tie the assertion to a name `.env` chooses.
#
# The join to `pg_roles` drops the `PUBLIC` entry, which `aclexplode` reports with
# grantee oid 0. That is not a hole: Postgres grants `USAGE` on `public` to
# `PUBLIC` by default on a stock cluster, so that entry is not this revision's and
# revoking it is not this revision's job. What is asked here is only whether one
# of the three roles is named in its own right.
SCHEMA_GRANTEES = """
    SELECT r.rolname, a.privilege_type
    FROM pg_catalog.pg_namespace n
    CROSS JOIN LATERAL aclexplode(n.nspacl) AS a
    JOIN pg_catalog.pg_roles r ON r.oid = a.grantee
    WHERE n.nspname = 'public'
    ORDER BY 1, 2
"""

DATABASE_GRANTEES = """
    SELECT r.rolname, a.privilege_type
    FROM pg_catalog.pg_database d
    CROSS JOIN LATERAL aclexplode(d.datacl) AS a
    JOIN pg_catalog.pg_roles r ON r.oid = a.grantee
    WHERE d.datname = current_database()
    ORDER BY 1, 2
"""

HAS_TABLE_PRIVILEGE = "SELECT has_table_privilege(:role, :relation, :privilege)"


@contextmanager
def catalog_connection(database: Any) -> Iterator[Any]:
    """A bootstrap-identity connection to `database`, with its engine disposed after.

    An engine of its own rather than `migrated_engine`, because everything in this
    section runs against the database `empty_database` made for one test, and
    `migrated_engine` is bound to the session's.

    Opened and closed around each phase rather than held across a downgrade: an
    idle connection that has read a catalog holds no lock on a user table today,
    and a later reader who adds a query that does would find a `DROP TABLE` inside
    Alembic waiting on this test's own session, which is a hang rather than a
    failure.
    """
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            yield connection
    finally:
        engine.dispose()


def public_relations(connection: Any) -> list[str]:
    """Every table, partitioned table, view and materialised view in `public`, by name."""
    return [row[0] for row in connection.execute(text(PUBLIC_RELATIONS))]


def privileges_held(
    connection: Any, roles: Sequence[str], relations: Sequence[str]
) -> set[tuple[str, str, str]]:
    """Every `(role, relation, privilege)` the catalog says one of `roles` holds.

    Asked of `has_table_privilege` rather than read out of `relacl`, so that a
    privilege reaching a role by inheritance from another role is counted too — a
    grant of a table-owning role to a runtime role voids every revoke this
    revision writes without touching a single ACL entry, and an entry-by-entry
    reading would not see it.
    """
    return {
        (role, relation, privilege)
        for role in roles
        for relation in relations
        for privilege in TABLE_PRIVILEGES
        if connection.execute(
            text(HAS_TABLE_PRIVILEGE),
            {"role": role, "relation": f"public.{relation}", "privilege": privilege},
        ).scalar_one()
    }


def schema_grantees(connection: Any) -> set[tuple[str, str]]:
    """Every `(role, privilege)` named in `public`'s own ACL, `PUBLIC` excluded."""
    return {(row[0], row[1]) for row in connection.execute(text(SCHEMA_GRANTEES))}


def database_grantees(connection: Any) -> set[tuple[str, str]]:
    """Every `(role, privilege)` named in this database's ACL, `PUBLIC` excluded."""
    return {(row[0], row[1]) for row in connection.execute(text(DATABASE_GRANTEES))}


def the_identity_revision(config: Any) -> str:
    """`IDENTITY_REVISION`, after asking the script directory whether it still exists.

    Resolved rather than passed straight to `command.upgrade`, so that a constant
    left behind by a squash, a rebase or a renamed revision file fails with a
    message naming E0-10 — instead of Alembic's own `Can't locate revision
    identified by '446183e8cc5f'`, which reads like a broken environment.
    """
    from alembic.script import ScriptDirectory

    try:
        ScriptDirectory.from_config(config).get_revision(IDENTITY_REVISION)
    except Exception as failure:
        pytest.fail(
            f"`{IDENTITY_REVISION}` is not a revision in this tree: {failure!r}. That is E0-10's "
            "own revision — the one that creates the two read views, the reveal function and every "
            "grant the three tests below are about — and all three pin both ends of their work to "
            "it rather than to `head` and `-1`. If the revision has been renumbered or squashed, "
            "this constant is the one place to change; if E0-10's grants have moved to a different "
            "revision, point it there and say so in the pull request. Do not restore `head` and "
            "`-1`: that is `docs/disputes/E0-11-02.md`, and it makes every assertion below true of "
            "a database nobody has changed."
        )
    return IDENTITY_REVISION


def downgrade_below_the_identity_revision(config: Any, meaning: str) -> None:
    """Undo E0-10's revision and nothing else, failing the test if it does not complete."""
    from alembic import command

    try:
        command.downgrade(config, BELOW_THE_IDENTITY_REVISION)
    except Exception as failure:
        pytest.fail(
            f"`alembic downgrade {BELOW_THE_IDENTITY_REVISION}` did not complete: {failure!r}. "
            f"{meaning} A downgrade that stops part-way is worse than one that refuses to start: "
            "the objects before the failing statement are gone, the ones after it are still there, "
            "and the revision is still stamped as applied."
        )


def only_the_identity_revision_was_undone(
    views_at_the_revision: Sequence[str], views_now: Sequence[str]
) -> None:
    """Fail unless the step that was undone is the one that created the read views.

    Both ends of these tests are pinned to `IDENTITY_REVISION`, so this is no
    longer the guard against `-1` drifting that it was written as — it is the guard
    that the constant still names the revision the assertions describe. The views
    are what make that visible from the outside: E0-10's revision creates them, so
    a downgrade that leaves one standing did not undo E0-10, and every assertion
    after this point is about privileges some other revision writes — all of them
    satisfied by a database nobody has changed (`docs/MISTAKES.md` entry 3).
    """
    assert views_at_the_revision, (
        f"There is no view in `public` at revision {IDENTITY_REVISION}, so nothing here can tell "
        "which revision the downgrade undid — and E0-10's 'a section-roster view and an "
        "enrollment-count view' are missing besides. `test_identity_separated_views.py` diagnoses "
        "that."
    )
    surviving = sorted(set(views_at_the_revision) & set(views_now))
    assert not surviving, (
        f"After `alembic downgrade {BELOW_THE_IDENTITY_REVISION}` the views {surviving} still "
        "exist, so the step that was undone is not the one that created them — at "
        f"{IDENTITY_REVISION} `public` held {sorted(views_at_the_revision)}. `IDENTITY_REVISION` "
        "no longer names the revision that creates the read views: it has been renumbered, or "
        "E0-10's objects have moved to another revision. Every assertion below is about privileges "
        "*that* revision writes, and against any other revision they are all satisfied by a "
        "database nobody has changed."
    )


def test_downgrading_the_identity_revision_leaves_no_grant_on_a_surviving_table(
    empty_database: Any,
    alembic_config_pointed_at: Any,
) -> None:
    """After the downgrade, no role of this revision's holds anything still in the database.

    The rule is stated over the *objects that survive* rather than over a list of
    grants, and the survivors are read out of `pg_class` after the fact, so a table
    a later ticket adds is inside this assertion the day it exists. The three roles
    are the two runtime ones and the reveal function's owner, and the owner is
    discovered from the catalog rather than spelled — E10 replaces the
    function, and a rule written with the role's name would retire with it.

    **Both ends are pinned to E0-10's own revision** rather than to `head` and
    `-1`, and the constant at the top of this section says why at length. In one
    line: this test is about what *E0-10's* `downgrade()` takes back, and neither
    end of a relative step stays pointed at E0-10 once a later revision exists.

    **The baseline is asserted first, and it is not ceremony.** Every assertion
    after the downgrade is that a set is empty, and an empty set is what a database
    with no grants in it produces — a migration that never ran, a role that was
    never created, a `has_table_privilege` call answering about the wrong database.
    So two grants this revision certainly makes are read back at that revision
    before anything is undone: `pulse_care`'s `SELECT` on `role_assignment`, which
    is the one that was left behind, and the definer's `SELECT` on `user_identity`,
    which is the one with a name behind it. The schema grants are read the same way
    for the same reason.

    **The set difference is reported, not a boolean.** A failure here has to say
    which role holds which privilege on which table, because the fix is a `REVOKE`
    naming exactly those three things and a message saying "something survived"
    sends the reader back to the catalog to find out what.

    **The exact ACL string is deliberately not pinned.** `relacl` and `nspacl`
    render the grantor's name into every entry, and that name is the deployment's
    superuser — `pulse_admin` in production, `pulse_test_admin` in this fixture —
    so a text comparison would pass in one place and fail in the other while
    measuring nothing about the revoke.
    """
    from alembic import command

    config = alembic_config_pointed_at(empty_database)
    command.upgrade(config, the_identity_revision(config))

    with catalog_connection(empty_database) as connection:
        definer = the_reveal_definer(connection)
        roles = (APPLICATION_ROLE, CARE_ROLE, definer)
        views_at_the_revision = read_views(connection)
        at_the_revision = privileges_held(connection, roles, public_relations(connection))
        schema_at_the_revision = schema_grantees(connection)

    assert (CARE_ROLE, "role_assignment", "SELECT") in at_the_revision, (
        f"At revision {IDENTITY_REVISION}, `{CARE_ROLE}` does not hold `SELECT` on "
        "`public.role_assignment`. That grant is the one this test was written about — it outlived "
        "the downgrade while the definer's two beside it were revoked — so without it here, every "
        "assertion below is true of a database that never had the grant in the first place. What "
        f"the roles do hold is {sorted(at_the_revision)}. The reveal function reads "
        "`role_assignment` on its own account (ADR 0043), so if this grant has moved, say where in "
        "the pull request."
    )
    assert (definer, IDENTITY_TABLE, "SELECT") in at_the_revision, (
        f"At revision {IDENTITY_REVISION}, the reveal function's owner `{definer}` does not hold "
        f"`SELECT` on `public.{IDENTITY_TABLE}`. That is the privilege the one door in the wall "
        "spends (ADR 0043), and it is the second half of this test's baseline: with it absent, the "
        "assertion that nothing survives the downgrade is satisfied by a database where nothing "
        f"was ever granted. The roles hold {sorted(at_the_revision)}. "
        "`test_the_reveal_functions_owner_holds_exactly_the_privileges_its_job_needs` diagnoses a "
        "definer whose grants have moved."
    )
    assert set(roles) <= {role for role, _ in schema_at_the_revision}, (
        f"At revision {IDENTITY_REVISION}, `public`'s ACL names {sorted(schema_at_the_revision)}, "
        f"which does not cover all of {sorted(roles)}. ADR 0043 lists `USAGE ON SCHEMA public` for "
        "all three roles among the "
        "privileges this revision writes and the downgrade must revoke, so if the revision no "
        "longer grants it, the schema assertion below is asserting nothing. Fix this test rather "
        "than deleting the assertion: the question it exists to ask — did the downgrade take back "
        "what the upgrade gave on the schema — has an answer either way."
    )

    downgrade_below_the_identity_revision(
        config,
        "This revision's `downgrade()` has to run to the end, because the revokes are the last "
        "thing in it: a statement that raises before them leaves every privilege below in place "
        "with the objects already dropped.",
    )

    with catalog_connection(empty_database) as connection:
        views_now = read_views(connection)
        surviving_relations = public_relations(connection)
        left_over = privileges_held(connection, roles, surviving_relations)
        schema_now = schema_grantees(connection)

    only_the_identity_revision_was_undone(views_at_the_revision, views_now)

    assert surviving_relations, (
        f"There is no table or view left in `public` after `alembic downgrade "
        f"{BELOW_THE_IDENTITY_REVISION}`, so the cross "
        "product below is empty and 'no role holds anything' is true of nothing. This revision "
        "drops the objects it created and leaves the schema the tickets under it built standing; "
        "a database with none of that left has had more undone than one step."
    )

    left_behind = sorted(
        f"{role} holds {privilege} on public.{relation}" for role, relation, privilege in left_over
    )
    assert not left_behind, (
        f"After `alembic downgrade {BELOW_THE_IDENTITY_REVISION}`, {left_behind} — privileges on "
        "objects that survived the "
        "revision that granted them. ADR 0043: 'a privilege on anything that outlives the "
        "downgrade is revoked, one guarded `IF EXISTS` per role'. A privilege cannot outlive the "
        "object it is on, so the grants on the two views and on the reveal function need nothing; "
        "these are the ones on tables the downgrade leaves standing, and nothing else in this "
        "repository will ever revoke them. What that costs is not theoretical: a database "
        "downgraded past this revision holds a role that can still read the table the revision "
        "was the only reason to grant it on, with no function left to spend it through and no "
        "record anywhere that it holds it."
    )

    on_the_schema = sorted(
        f"{role} holds {privilege} on schema public"
        for role, privilege in schema_now
        if role in roles
    )
    assert not on_the_schema, (
        f"After `alembic downgrade {BELOW_THE_IDENTITY_REVISION}`, `public`'s ACL still names "
        f"{on_the_schema}. This revision "
        "is the only thing in the tree that grants `USAGE ON SCHEMA public` to these roles, so it "
        "is the only thing that can take it back. On a stock cluster nothing observable changes — "
        "`PUBLIC` holds `USAGE` on `public` by default and the roles keep reaching the schema "
        "through that — and it is revoked anyway, because 'the default happens to cover it' is not "
        "the same claim as 'this revision left nothing behind', and on a cluster where that "
        "default has been revoked the difference is a role that can still see the schema."
    )


def test_the_downgrade_leaves_the_application_roles_connect_privilege_in_place(
    empty_database: Any,
    alembic_config_pointed_at: Any,
) -> None:
    """The one exception to the rule above, asserted so nobody closes it as an oversight.

    `CONNECT ON DATABASE` is granted by this revision **and** by
    `scripts/db-init/01-application-role.sh` at `initdb`, and an ACL entry records
    no history: there is one entry, not two, so a single `REVOKE` removes both
    mechanisms' grants and takes the running application's login with it on any
    cluster where `PUBLIC` no longer holds `CONNECT`. That is why the rule the test
    above asserts stops here, and this test is what makes the stop deliberate — an
    exception recorded only in a comment is one the next reader closes as an
    oversight, tidily, in a pull request about something else.

    **Asserted over the ACL entry rather than over `has_database_privilege`**, and
    the difference is the whole test. `has_database_privilege('pulse_app',
    current_database(), 'CONNECT')` answers true for every role on a stock cluster,
    because Postgres grants `CONNECT` to `PUBLIC` on every new database — so that
    assertion passes with the grant revoked, passes with the role holding nothing
    at all, and cannot fail. The entry in `datacl` is the thing a `REVOKE` in
    `downgrade()` would remove, so it is the thing to look at.

    **This database is the strict case rather than the lenient one.**
    `empty_database` runs no `initdb` hook, so the `CONNECT` entry asserted here is
    one the revision granted itself — the case where revoking it is most
    defensible, and it is left alone anyway, because the ACL cannot tell the two
    sources apart and a downgrade must not depend on which script ran first.
    """
    from alembic import command

    config = alembic_config_pointed_at(empty_database)
    command.upgrade(config, the_identity_revision(config))

    with catalog_connection(empty_database) as connection:
        views_at_the_revision = read_views(connection)
        at_the_revision = database_grantees(connection)

    assert (APPLICATION_ROLE, "CONNECT") in at_the_revision, (
        f"At revision {IDENTITY_REVISION}, this database's ACL does not name `{APPLICATION_ROLE}` "
        f"as holding `CONNECT`: it names {sorted(at_the_revision)}. Then the assertion below is "
        "about an entry that was never "
        "there, and it would stay green with `REVOKE CONNECT ON DATABASE … FROM pulse_app` added "
        "to `downgrade()` — the exact edit it exists to catch. E0-10's migration grants `CONNECT` "
        "to both connection roles; if that has moved, this test needs pointing at wherever it "
        "moved to rather than relaxing."
    )

    downgrade_below_the_identity_revision(
        config,
        "The exception below is only meaningful against a downgrade that ran to the end.",
    )

    with catalog_connection(empty_database) as connection:
        views_now = read_views(connection)
        now = database_grantees(connection)

    only_the_identity_revision_was_undone(views_at_the_revision, views_now)

    assert (APPLICATION_ROLE, "CONNECT") in now, (
        f"`alembic downgrade {BELOW_THE_IDENTITY_REVISION}` removed `{APPLICATION_ROLE}`'s "
        "`CONNECT` entry from this "
        f"database's ACL. It now names {sorted(now)}. This is the one grant the downgrade "
        "deliberately leaves (ADR 0043, and the migration says so at the point of the omission): "
        "`scripts/db-init/01-application-role.sh` grants the same privilege at `initdb`, before "
        "this revision runs, and an ACL entry records no history — so revoking it here takes the "
        "other mechanism's grant with it, and with it the running application's login on any "
        "cluster where `PUBLIC` no longer holds `CONNECT`. `CONNECT` opens a session and reads no "
        "row; a role that can connect and holds no table privilege is precisely the pre-revision "
        "state that script sets out to establish. If this is being changed on purpose, the "
        "downgrade also has to stop the two connection roles ending up in different states "
        "according to which provisioning script happened to run."
    )


def test_the_downgrade_completes_when_a_role_it_revokes_from_is_absent(
    empty_database: Any,
    alembic_config_pointed_at: Any,
) -> None:
    """A missing role skips its own revokes and nobody else's.

    `REVOKE … FROM <role>` is an error rather than a no-op when the role is
    absent, and a downgrade is exactly the moment somebody is already dealing with
    a database in a state nobody planned — a cluster that applied an earlier
    spelling of this revision, a managed Postgres where the roles are the
    operator's to create, a restore that brought the schema and not the globals.
    So the revokes are guarded, and ADR 0043 requires **one guard per role**
    rather than one around all three, "because a cluster missing
    `pulse_reveal_definer` is no reason to leave what `pulse_care` holds".

    Both halves are asserted, because a downgrade that completes proves the guard
    only if the unguarded form would have failed (`docs/MISTAKES.md` entry 9, and
    entry 3 for the shape it prevents):

      - the **control** runs the bare `REVOKE ALL ON public.role_assignment FROM
        pulse_care` first and requires it to fail with `undefined_object`. Without
        that, a downgrade completing says nothing — it also completes on a cluster
        where the role was never absent, which is what a rename that silently did
        not happen would leave behind;
      - the **assertion** is that the guarded downgrade completes, that the
        revision's objects are gone, and that the two roles which *are* present
        were still revoked from. That last clause is what kills the tidier design
        ADR 0043 rejects: one `IF EXISTS` around the whole block skips every
        role's revokes when any one role is missing, and it completes just as
        cleanly.

    **The role is made absent by renaming it, not by dropping it.** `DROP ROLE`
    refuses while any database in the cluster records a privilege for the role, so
    dropping `pulse_care` here would mean `DROP OWNED BY` in the session database
    too — which revokes the grants half this file's other tests assert, in a
    database this test does not own. A rename leaves every ACL entry exactly where
    it is, keyed by oid, and makes `SELECT 1 FROM pg_roles WHERE rolname =
    'pulse_care'` empty, which is precisely the condition each guard tests and
    precisely what the bare `REVOKE` chokes on. It is undone in a `finally`, since
    a role outlives the transaction and outlives this database.
    """
    from alembic import command

    config = alembic_config_pointed_at(empty_database)
    command.upgrade(config, the_identity_revision(config))

    with catalog_connection(empty_database) as connection:
        definer = the_reveal_definer(connection)
        still_present = (APPLICATION_ROLE, definer)
        views_at_the_revision = read_views(connection)
        at_the_revision = privileges_held(connection, still_present, public_relations(connection))

    assert (definer, IDENTITY_TABLE, "SELECT") in at_the_revision, (
        f"At revision {IDENTITY_REVISION}, the reveal function's owner `{definer}` does not hold "
        f"`SELECT` on `public.{IDENTITY_TABLE}` — the roles that will still be present hold "
        f"{sorted(at_the_revision)}. "
        "That grant is on a table the downgrade leaves standing, so it is the one the last "
        "assertion in this test watches for. Without it there, that assertion is true before the "
        "downgrade runs and would stay true if `downgrade()` did nothing at all."
    )

    absent_under = f"{CARE_ROLE}_renamed_by_the_tests_{uuid4().hex[:8]}"
    with catalog_connection(empty_database) as connection:
        connection.execute(text(f'ALTER ROLE "{CARE_ROLE}" RENAME TO "{absent_under}"'))
        connection.commit()

    try:
        with catalog_connection(empty_database) as connection:
            lingering = connection.execute(
                text(ROLE_EXISTS), {"role": CARE_ROLE}
            ).scalar_one_or_none()
            assert lingering is None, (
                f"`{CARE_ROLE}` still has a row in `pg_roles` after being renamed to "
                f"`{absent_under}`, so the downgrade below meets a role that is present and this "
                "test would report the guard working having never exercised it."
            )
            unguarded = refused(
                connection, f'REVOKE ALL ON public.role_assignment FROM "{CARE_ROLE}"'
            )
            connection.rollback()

        assert unguarded is not None, (
            f"`REVOKE ALL ON public.role_assignment FROM {CARE_ROLE}` succeeded against a cluster "
            "with no such role. Then an unguarded revoke is a no-op here, the guard in "
            "`downgrade()` is not what makes the downgrade below complete, and this test is "
            "measuring nothing. The migration's own comment claims this statement is an error "
            "rather than a no-op, and this is the assertion that claim rests on."
        )
        assert sqlstate(unguarded) == UNDEFINED_OBJECT, (
            f"The unguarded revoke failed with SQLSTATE {sqlstate(unguarded)} rather than "
            f"{UNDEFINED_OBJECT}: {unguarded}. It has to fail *because the role is absent* — a "
            "missing `public.role_assignment` would satisfy 'it failed' while saying nothing about "
            "what a guard is for."
        )

        downgrade_below_the_identity_revision(
            config,
            f"`{CARE_ROLE}` does not exist in this cluster, which is the case the `IF EXISTS` "
            "guards around the revokes are for: the control above shows the unguarded statement "
            "raising `undefined_object` on this very database. Without the guard the downgrade "
            "stops mid-block, having dropped the function and both views and having revoked "
            "whatever came before the failing statement.",
        )

        with catalog_connection(empty_database) as connection:
            views_now = read_views(connection)
            surviving_relations = public_relations(connection)
            left_over = privileges_held(connection, still_present, surviving_relations)
    finally:
        with catalog_connection(empty_database) as connection:
            connection.execute(text(f'ALTER ROLE "{absent_under}" RENAME TO "{CARE_ROLE}"'))
            connection.commit()

    only_the_identity_revision_was_undone(views_at_the_revision, views_now)

    assert surviving_relations, (
        "There is no table or view left in `public` after the downgrade, so the assertion below "
        "has nothing to ask about. `test_downgrading_the_identity_revision_leaves_no_grant_on_a_"
        "surviving_table` diagnoses that."
    )

    left_behind = sorted(
        f"{role} holds {privilege} on public.{relation}" for role, relation, privilege in left_over
    )
    assert not left_behind, (
        f"With `{CARE_ROLE}` absent, the downgrade completed and left {left_behind} behind for the "
        "roles that were present. So the guard is around more than the arm that needed it: ADR "
        "0043 asks for 'one guarded `IF EXISTS` per role rather than one around all three, because "
        "a cluster missing `pulse_reveal_definer` is no reason to leave what `pulse_care` holds'. "
        "A single guard is tidier to read and this is what it costs — the roles that exist keep "
        "everything this revision granted them, on a database that no longer has the objects that "
        "justified any of it, and the downgrade reports success."
    )


# ---------------------------------------------------------------------------
# E0-33 item 3 — the grant set as a *set*, and the roles that can reach it.
# ---------------------------------------------------------------------------
#
# Everything above asserts a rule this scheme states. This section asserts that
# nothing else was stated: "asserting a refusal proves the refusal; it does not
# prove that nothing else was granted" (E0-33 item 3). `alembic check` reads
# `pg_roles`, ACLs, `pg_class` entries for views and `pg_proc` not at all, in
# either direction, so a grant added beside the line that needed it reaches `main`
# with the drift gate green — measured on the pinned Alembic 1.19 in E0-20 item 3b
# and repeated in ADR 0043.
#
# Five tests: two sweeps for who else has been granted something and what the
# connection roles hold on a base table; one for which roles they can become; one
# self-test standing a column grant up so the sweeps' emptiness means something;
# and one asserting the `nspname = 'public'` premise the whole file rests on.
#
# **Two of the three properties E0-20 item 3b called unasserted are now asserted,
# and this section does not duplicate them.** E0-10's own review round landed
# `test_no_security_definer_function_is_owned_by_a_superuser` and
# `test_the_reveal_functions_owner_holds_exactly_the_privileges_its_job_needs`
# above, and ADR 0043's last paragraph records that. E0-33's scope was written
# from E0-20's text and still says both are missing; they are not, and adding a
# second copy of either under a similar name would silently shadow the first —
# a redefined function at module scope is not a duplicate test, it is a deleted
# one (`docs/MISTAKES.md` entries 1 and 2). What is genuinely unasserted is the
# *set*: nothing enumerates who else has been granted something, what the two
# connection roles hold beyond the views, or which roles they can become.
#
# **Which of these is `invariant`-marked, and the line it is drawn on.** One is:
# `test_neither_runtime_role_can_become_a_role_that_may_read_identity`. The line
# this section first drew — §4.1 is about what a reader can see and these are
# about what a role may do — was the wrong one, and a security review of PR #40
# said why: every marked test in this file is a role-capability test, and one of
# them, `test_the_application_role_may_not_execute_the_reveal_function`, is
# exactly "may this role call this function". The line that actually separates
# them is **door from inventory**. A marked test guards one route into identity: a
# direct read, a join from a view, `EXECUTE` on the reveal, and now `SET ROLE`.
# The other two here are inventories — they assert that the grant set has no
# member nobody sanctioned — which is a precondition for the doors being the only
# doors rather than an instance of §4.1 itself.
#
# **E1-12 and E1-11 add a marked test on the inventory side of that line, and it
# is deliberate rather than a drift.** `test_the_application_role_may_execute_only_
# the_point_resolvers` is an equality over the five functions `pulse_app` may call,
# which by the rule above would be unmarked — but from the moment that set stopped
# being empty, "the doors are the only doors" is the assertion that the set has not
# grown, and there is no separate route-test that would notice a fifth door. The
# mark follows the guarantee rather than the shape.
#
# **E0-26 item 1 added two marks by that same line, and they are doors.**
# `test_the_care_door_refuses_an_actor_with_no_live_care_assignment` guards the
# route through the door itself — the acting person's `CARE` assignment is the only
# thing between a `pulse_care` connection and any student's name — and it was
# unmarked before only because the count of marked tests was never the point. And
# `test_the_care_connection_cannot_forge_or_suppress_the_record_the_door_writes`
# guards the record rather than the name, which §4 makes the same guarantee: an
# access nobody can prove happened is an access with no door in front of it, since
# the caller now commits that record itself. Do not count the marked tests from
# this comment; `pytest -m invariant --collect-only` is the only currency that sees
# both marking forms (`docs/MISTAKES.md` entry 35).
#
# The `SET ROLE` door earns its mark on its own evidence: the mutation its
# docstring records left all 42 tests in this suite passing while `pulse_app`
# could become `pulse_care` and call the reveal. Unmarked, that guard sits outside
# the pass where a skip is a build failure, which is the one place a
# confidentiality guard must not sit.

# Every base table in `public`. Separate from `PUBLIC_TABLES` above, which is
# `relkind = 'r'` and feeds the `pg_temp` shadow test — a partitioned parent would
# be missed there and must not be missed here, and a sweep that covered every kind of
# table but one is the shape `docs/MISTAKES.md` entry 14 records. Views are
# deliberately absent: reading them is what the application role is *for*.
PUBLIC_BASE_TABLES = """
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
    ORDER BY 1
"""

# Who is named in the ACL of every relation in `public`, and by what. `aclexplode`
# rather than a text match on the `aclitem` for the reason `SCHEMA_GRANTEES` gives
# above: the rendered form carries the grantor's name, which is `.env`'s choice.
# Grantee oid 0 is `PUBLIC` — the pseudo-role every other role is a member of —
# and it has no `pg_roles` row, so it is named here rather than dropped by the
# join. That entry is the whole reason this sweep is not just about roles: one
# `GRANT SELECT ON public.user_identity TO PUBLIC` hands a name to every
# connection in the cluster without mentioning a role at all.
RELATION_GRANTEES = """
    SELECT c.relname AS relation,
           pg_get_userbyid(c.relowner) AS owner,
           coalesce(r.rolname, 'PUBLIC') AS grantee,
           a.privilege_type AS privilege
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL aclexplode(c.relacl) AS a
    LEFT JOIN pg_roles r ON r.oid = a.grantee
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm')
    ORDER BY 1, 3, 4
"""

# Who is named in the ACL of a *column*. `pg_attribute.attacl`, which is a third
# place a privilege can be recorded and which neither of the sweeps beside this
# one reads. Measured on the running stack during a security review of PR #40:
#
#     GRANT SELECT (identity_name) ON public.user_identity TO pulse_app
#
#     pg_class.relacl      → pulse_app absent
#     pg_attribute.attacl  → pulse_app=r/pulse_admin
#     has_table_privilege(user_identity, 'SELECT')     → False
#     has_column_privilege(identity_name, 'SELECT')    → True
#     SELECT * FROM public.user_identity               → refused
#     SELECT identity_name FROM public.user_identity   → ALLOWED
#
# So the three `invariant`-marked refusals above go on passing — every one of them
# selects `*`, which is still refused — while the connection reads every student's
# name one column at a time. ADR 0001's "Alternatives rejected" names column
# grants explicitly, which is what makes this the thing somebody reaches for
# rather than a curiosity: a reader who wants an instructor screen to show a name
# finds the option already written down as considered.
COLUMN_GRANTEES = """
    SELECT c.relname AS relation,
           a.attname AS column_name,
           pg_get_userbyid(c.relowner) AS owner,
           coalesce(r.rolname, 'PUBLIC') AS grantee,
           g.privilege_type AS privilege
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL aclexplode(a.attacl) AS g
    LEFT JOIN pg_roles r ON r.oid = g.grantee
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm')
      AND a.attnum > 0
      AND NOT a.attisdropped
    ORDER BY 1, 2, 4, 5
"""

# The privileges Postgres will accept on a single column, which is a strict subset
# of `TABLE_PRIVILEGES`: `DELETE`, `TRUNCATE` and `TRIGGER` are table-wide or
# nothing. Enumerated rather than reusing the wider tuple because
# `has_column_privilege` raises on a privilege that cannot be column-scoped, which
# would be an error inside a query rather than a failed assertion.
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")

HAS_COLUMN_PRIVILEGE = "SELECT has_column_privilege(:role, :relation, :column, :privilege)"

# Every schema this database holds that is not Postgres's own. Read so that the
# `nspname = 'public'` scope every sweep in this file uses is an *asserted*
# premise rather than an assumption — see
# `test_public_is_the_only_schema_this_deployment_defines`.
NON_SYSTEM_SCHEMAS = """
    SELECT n.nspname
    FROM pg_namespace n
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND n.nspname NOT LIKE 'pg\\_%'
    ORDER BY 1
"""

# Who is named in the ACL of every `SECURITY DEFINER` function in `public`.
# `pg_proc.proacl`, and it is here because it was swept nowhere in either
# direction: an independent security review found the membership test below blind
# to the `EXECUTE` door, and the same door was open in the grantee sweep. `CREATE
# ROLE pulse_reporting; GRANT EXECUTE ON FUNCTION public.<the reveal> TO
# pulse_reporting` writes no `relacl` entry, so the relation sweep above does not
# see it, and the role is not `pulse_app`, so the `invariant`-marked refusal
# earlier in this file does not either — while the grantee may call the one
# function whose job is to return a name.
#
# **`SECURITY DEFINER` only, deliberately.** An ordinary function runs with the
# *caller's* privileges and can therefore hand out nothing the caller lacks, and
# Postgres grants `EXECUTE` on every new function to `PUBLIC` by default — so
# sweeping them all would flag that default as a finding and teach the next reader
# to add an exclusion. A definer function is the opposite case: every grantee on
# one is a deliberate decision, and `PUBLIC` on one is a hole.
SECURITY_DEFINER_GRANTEES = """
    SELECT p.oid::regprocedure::text AS routine,
           pg_get_userbyid(p.proowner) AS owner,
           coalesce(r.rolname, 'PUBLIC') AS grantee,
           a.privilege_type AS privilege
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    CROSS JOIN LATERAL aclexplode(p.proacl) AS a
    LEFT JOIN pg_roles r ON r.oid = a.grantee
    WHERE n.nspname = 'public'
      AND p.prosecdef
      AND p.prokind IN ('f', 'p')
      AND NOT EXISTS (
          SELECT 1 FROM pg_depend d
          WHERE d.objid = p.oid
            AND d.classid = 'pg_proc'::regclass
            AND d.deptype = 'e'
      )
    ORDER BY 1, 3, 4
"""

# Every role `:role` can *become*, whether or not it inherits that role's
# privileges. Deliberately not `REACHABLE_ROLES` above, which asks the same
# question with `'USAGE'`: that mode answers "are this role's privileges available
# without a `SET ROLE`", so a membership granted `WITH INHERIT FALSE` is absent
# from it — and from `has_table_privilege`, which is the other half of every grant
# assertion in this file. `'MEMBER'` is the mode that reports a membership the
# holder has to `SET ROLE` into, which is one statement away from the same
# privilege.
MEMBER_OF_ROLES = """
    SELECT r.rolname
    FROM pg_roles r
    WHERE pg_has_role(:role, r.oid, 'MEMBER') AND r.rolname <> :role
    ORDER BY 1
"""

# What either *connection* role holds on a base table, and the whole of it. Every
# entry carries the sentence it comes from, because an exact set is worth only as
# much as its derivation and because the next person to add one has to be able to
# tell what makes an entry legitimate.
#
#   - `pulse_care` reads `role_assignment`. ADR 0043 enumerates the privileges
#     this scheme writes that outlive its downgrade and must be revoked by hand —
#     "the definer's two table grants and its schema `USAGE`, `pulse_care`'s grant
#     on `role_assignment` and its schema `USAGE`, and `pulse_app`'s schema
#     `USAGE`". The reveal verifies the actor's live `CARE` assignment, and Care's
#     own queue path resolves the same assignments.
#   - `pulse_app` reads and inserts `classification`, **and holds nothing else on
#     it, which is the point of the entry.** SPEC §8: "`classification` is
#     append-only (re-runs create new rows) with prompt/model versioning."
#     `SELECT, INSERT` with `UPDATE`, `DELETE` and `TRUNCATE` withheld is what
#     makes append-only a property of the database rather than a rule every future
#     writer has to know. So the equality below is not only a ceiling on what the
#     application may reach — it is the only thing in this suite asserting that a
#     classification verdict cannot be rewritten or erased on the connection the
#     application runs on.
#   - `pulse_app` **reads** `lti_platform` and `lti_deployment`, and holds nothing
#     else on either. E0-18's launch door resolves every launch through them: the
#     issuer names the registration, the registered `client_id` is what an
#     `id_token`'s `aud` is compared against, the key set URL is where the
#     verifying key comes from, and `lti_deployment` is what the launch's
#     `deployment_id` claim is matched against. Without `SELECT`, every launch is
#     refused by Postgres with 42501 rather than by any check the door makes.
#     Two things make this a narrow widening rather than a convenience grant.
#     **These are configuration tables** — an issuer, a client id, a key set URL,
#     a deployment id — carrying no personal data, so nothing §4.1 governs is
#     reachable through them. And **`SELECT` alone**: the door registers nothing
#     and records no fetch, so `INSERT` and `UPDATE` stay withheld and a
#     registration remains something a deployment writes rather than something a
#     launch can create for itself.
#     Recorded here because widening this constant is exactly the conversation
#     this equality exists to force — a grant file may not justify its own grant.
#     Decided by the orchestrator on 2026-08-21, on E0-18 PR 1.
#   - `pulse_app` **reads** `tool_signing_key`, and holds nothing else on it.
#     E1-06 publishes the tool's key set at `/lti/jwks` and E1-11 signs a
#     `client_assertion` with the same row, both on the application connection, so
#     without `SELECT` the tool cannot present its own identity to any platform.
#     Three things make this the narrowest grant that does the job, and they are
#     worth stating because this is the only entry in this set that names a
#     **private key**.
#     **The grant is deliberately late.** ADR 0082 left the table grantless in
#     E1-05 — "a runtime role holding read access to a private key it never opens
#     is a credential at rest with no owner" — and put the grant in the ticket
#     whose code spends it, which is this one. Nothing before E1-06 could have
#     needed it, and a grant that had arrived with the schema would have sat
#     unused for a ticket.
#     **`SELECT` alone.** The seed writes the row and the seed runs as the
#     superuser (ADR 0009, ADR 0063), so `INSERT` and `UPDATE` stay withheld — an
#     application connection that could write this column could rotate the tool's
#     identity, which ADR 0082 forbids outright, and could do it invisibly because
#     a fresh key signs perfectly.
#     **It carries no personal data.** ADR 0082's own consequence section answers
#     the §4.1 question: "`tool_signing_key` is not a person table. It holds no
#     subject, no name and no address, so SPEC §4.1's `PERSON_TABLES` does not
#     change." What this grant widens is the credential surface rather than the
#     confidentiality one — the application role can now read the tool's private
#     signing key, which is the cost ADR 0082 accepts and records.
#     Decided in ADR 0082 and spent in E1-06.
#   - `pulse_app` **inserts and deletes** on `lti_launch_nonce`, and holds nothing
#     else on it. E1-08's replay guard (`app.lti.replay_guard.claim_nonce`) spends
#     a launch's nonce with `INSERT` on the application connection as the last
#     step of every valid launch — SPEC §9.1's single-use replay requirement — and
#     `purge_expired_nonces` reclaims the expired tail with `DELETE`, the
#     Celery-beat housekeeping ADR 0089 gives the Postgres-backed ledger in place
#     of a TTL Redis would have supplied for free.
#     **`INSERT` and `DELETE` only, no `SELECT` and no `UPDATE`.** The claim
#     reads single-use off a unique-constraint violation on the nonce column
#     rather than a targeted read, and the primary key is generated in Python
#     rather than read back with `RETURNING` — so nothing on this connection ever
#     needs to select the table. A spent nonce is never rewritten, so `UPDATE`
#     stays withheld too.
#     **It carries no personal data.** The table holds a nonce, a consumed-at
#     timestamp and an expiry — no subject, no name, no address — so SPEC §4.1's
#     `PERSON_TABLES` does not change and no identity-separated view is owed.
#     Decided and spent in E1-08.
#   - `pulse_app` **reads, inserts and deletes** on `lti_launch_state`, and holds
#     nothing else on it. This is the server-side handshake store dispute
#     E1-08-01 resolved E1-08 onto: `app.lti.in_flight.remember_launch` records
#     the handshake at `/lti/login` (`INSERT`), `look_up_launch` reads the
#     expected `nonce` back at `/lti/launch` to validate the token against it
#     (`SELECT`), and `consume_launch`/`purge_expired_launch_states` enforce
#     single-use and reclaim the expired tail (`DELETE`) — ADR 0089 records the
#     decision. Unlike `lti_launch_nonce` above, this table needs `SELECT`: the
#     nonce ledger only ever checks for a conflict, but the handshake is a
#     look-up the launch reads an answer out of.
#     **`SELECT`, `INSERT`, `DELETE`, no `UPDATE`.** A handshake row is written
#     once at login and read once at launch; nothing on this connection ever
#     rewrites one, so `UPDATE` stays withheld.
#     **It carries no personal data.** The table holds a `state`, a `nonce` and
#     an expiry — no subject, no name, no address — so SPEC §4.1's
#     `PERSON_TABLES` does not change and no identity-separated view is owed.
#     Decided and spent in E1-08.
#
# **Hand-written and derived from the record, not read out of the grant files**
# (`docs/MISTAKES.md` entry 19), which is the same decision
# `REVEAL_DEFINER_PRIVILEGES` at the top of this file makes and for the same
# reason: a constant assembled from `backend/app/views_sql/*.sql` at run time can
# be checked only against the SQL it is supposed to police. Every grant would then
# justify itself — the file says grant it, the catalog says granted, the test says
# fine — and a later ticket's convenience grant, which is the shape E0-33 item 3
# names, is exactly a line added to one of those files. Reading them would make
# this test blind to its own subject while looking stronger.
#
# The cost is honest and is the point: a ticket that legitimately grants something
# turns this red, and the pull request that adds the grant adds the entry and says
# why. That is a loud failure on a legitimate change, and the alternative is a
# silent pass on a widening.
#
# The definer is not here: it is not a connection role, and
# `test_the_reveal_functions_owner_holds_exactly_the_privileges_its_job_needs`
# pins its four grants as an equality already.
#   - `pulse_app` **reads** `prefix`, `term`, `start_letter_map`, `course` and
#     `section`, and **inserts** `course`, `section`, `user` and `launch_defect`.
#     On `user` it holds no table-wide `SELECT` at all — only `SELECT (id)`, in the
#     column set below. This is E1-10's launch-time provisioning, and it is the
#     first grant in this set that lets the application write a relation SPEC §2.1
#     puts on the *LMS's* side — so it is the entry that most needs its sentence.
#     **What it is for.** §2.1 gives courses and sections two arrival paths,
#     "hourly roster sync + launch-time ingestion", and §7.3 makes the first staff
#     launch of a section the thing that discovers it at all: "it has no way of its
#     own to learn that a section exists. So the first staff launch of a section
#     bootstraps every later sync of it." The reads are the look-ups that launch
#     has to make before it may write anything — the prefix the context label
#     names, the term whose dates contain the day of the launch, that term's
#     start-letter map row, and the course and section rows an upsert has to find
#     before it decides to insert.
#     **`user` is not one of those look-ups, and this entry used to say it was.**
#     The sentence above read "the course, section and user rows an upsert has to
#     find", which was false: the writer inserts a `user` row and never reads the
#     table, by design — `lms_user_id` is the `sub` claim verbatim and E1-01 keeps
#     it out of every view, so a connection able to `SELECT` it can enumerate every
#     launching subject this deployment has ever seen and join responses to people.
#     The round-3 security review found the grant and the false justification
#     together. What the writer actually needs is the primary key back from an
#     insert, which Postgres checks `SELECT` against per returned column — so the
#     grant is `SELECT (id)`, and `lms_user_id` is refused.
#     `tests/integration/test_the_application_role_writes_only_the_granted_columns.py`
#     provokes both halves.
#     **This is the grant ADR 0045 deferred, arriving narrowed rather than
#     widened.** That record wanted the opposite instrument — "refusing the
#     *application role* `INSERT`/`UPDATE` on these tables would be structural
#     rather than a convention" — and could not have it, because "the launch path
#     and E1's roster sync are the same connection, so the grant would have to
#     distinguish a sanctioned writer from an unsanctioned one, and no such
#     separation exists in E0." E1-10 does not solve that: one connection still
#     serves both. What it does is spend the smallest grant its writer needs, so
#     that the *database* refuses everything outside it and `guard_write`'s
#     sanction catalog (ADR 0090) is what refuses the rest in Python. The two are
#     different instruments and neither replaces the other.
#     **No `DELETE`, no `TRUNCATE`, and no table-wide `UPDATE` anywhere.** The
#     verbs withheld are the assertion here as they are on `classification`: a
#     launch discovers rows and never removes them, so a connection that could
#     delete a `course` could take a term's reports with it. `UPDATE` is granted
#     only at column grain, below.
#     **`user` has no `UPDATE` at all**, which is the narrowest entry in the group
#     and deliberate: ADR 0045 puts `user` in the guarded set because
#     "`user.lms_user_id` is the `sub` claim verbatim … and §4 keys every response
#     to it", so the row is insert-if-absent and never rewritten. Withholding
#     `UPDATE` makes that a property of the database rather than a rule the next
#     writer has to remember, in exactly the shape §8's append-only
#     `classification` grant takes.
#     **What these tables carry, for §4.1.** `prefix`, `term`, `start_letter_map`,
#     `course` and `section` are org and calendar configuration and hold no
#     personal data. `user` does not either: E0-10 separates identity onto
#     `user_identity`, which this role holds no privilege on by any mechanism —
#     the three `invariant`-marked refusals above are what say so — and `user`
#     itself carries the `sub` claim, which E1-01 keeps out of every view and which
#     no grant here makes readable through one. `launch_defect` is E1-10's own
#     append-only record, and its field set is enumerated and asserted in
#     `tests/integration/test_launch_provisioning_defects.py`: a defect kind, an
#     issuer, a deployment, a context id and a timestamp, and never a subject, a
#     name or an email.
#     Decided and spent in E1-10.
#   - `pulse_app` **reads and inserts** `enrollment` and `nrps_call`, and
#     **inserts** `role_assignment`. This is E1-11's roster sync, and it is the
#     second grant in this set that lets the application write a relation SPEC §2.1
#     puts on the LMS's side — the two relations of ADR 0045's four that nothing in
#     this project had written before.
#     **What each one is for.** §2.1's other arrival path is the "hourly roster
#     sync", and §3.4 reads what it writes: "Late adds: denominator starts at the
#     student's first enrolled week (from NRPS enrollment data)." The `SELECT` on
#     `enrollment` is the lookup that decides insert-or-update — a member already
#     enrolled must not be enrolled twice, and ADR 0023's exclusion constraint would
#     refuse the second row rather than answer the question. `nrps_call` is E1-11's
#     own record (its work order, D9): one row per NRPS HTTP call, which is §6.1's
#     "NRPS and AGS call logs with response codes", the discriminator between a
#     never-synced section and a synced-empty one, and the memory the launch
#     trigger's debounce is measured against — so the sync both writes it and reads
#     it back.
#     **`role_assignment` is not in this set, and the security round's F2 is why.**
#     E1-11 first granted `pulse_app` a table-wide `INSERT` on it, for the teaching
#     instructor's row — §2.1's fifth owned item, and a *purview grant*: the whole
#     oversight surface is computed from these rows. The review measured what that
#     bought: `guard_write` refuses only an `INSTRUCTOR` row and that is a Python
#     rule, so a **`CARE`** assignment — the row E0-10's reveal definers check for
#     before they return a name — passed unconditionally, on the connection every
#     screen in the product runs on. A grant cannot bound a column's *value*; there
#     is no `GRANT INSERT (role = 'INSTRUCTOR')`. So the grant is gone and the one
#     legitimate write goes through `public.record_teaching_instructor`, whose body
#     chooses the role and whose signature has nowhere to put another one — the
#     same instrument, and the same argument, as the email write one entry down.
#     The sync still asks `public.assignment_scope` (E0-11's view, already granted)
#     whether it has already written one, so no read on the table is spent either.
#     `pulse_care` holds `SELECT` on this table for the reveal's own assignment
#     check, one entry above, and that entry is now the only `role_assignment`
#     privilege in this inventory.
#     **No `DELETE`, no `UPDATE` on `nrps_call`, and no table-wide `UPDATE` on
#     `enrollment`.** The verbs withheld are the assertion,
#     as they are on `classification` and on E1-10's group. A drop is a *closed
#     window* rather than a deleted row (ADR 0023, and E1-11's D3: "the open/closed
#     window rows ARE the recorded transition"), so a connection able to delete an
#     enrollment could erase the record a participation figure is computed from; a
#     connection able to delete a `role_assignment` could revoke a dean's purview;
#     and `nrps_call` is an append-only log, which is only true if the grant says
#     so. `enrollment`'s `UPDATE` is granted at column grain, below.
#     **What these tables carry, for §4.1.** `enrollment` holds two foreign keys and
#     four dates and no identity of any kind; `role_assignment` holds a person
#     reference, a role and a scope, which is the graph §2.1 computes purview from
#     and which `pulse_care` already reads; `nrps_call` holds a section reference, a
#     URL, an HTTP status, a count and a timestamp — no subject, no name, no email.
#     E1-11's own review question ("does this ticket add a person table?", deferred
#     E1-01 item 2) is answered no on exactly this ground: `nrps_call` references
#     `section` and nothing else.
#     Decided and spent in E1-11.
#   - `pulse_app` **reads, inserts and deletes** `clock_override`, the single-row
#     development clock E2-04 adds, and holds no `UPDATE` on it. This is the
#     widening this test's docstring says will happen and has happened before, and
#     `docs/disputes/E2-04-02.md` is its record: the branch was run without the
#     grant, and five of the six cases in
#     `tests/integration/test_the_dev_console_sets_and_clears_the_clock.py` failed
#     with `permission denied for table clock_override` on the `GET /dev` render
#     and on both `POST`s alike. It is issued by
#     `backend/app/views_sql/clock_override_grants_v001.sql`, executed by revision
#     `a789f1920de3`, so a fresh database reproduces it.
#     **A verb per caller.** `SELECT` is `app.services.clock.now`, which every
#     scheduling and visibility read in the product goes through — the service
#     reads the row on the tool's connection and on the Celery worker's, and
#     `DATABASE_URL` names `pulse_app` for both. `INSERT` is `POST /dev/clock`,
#     which writes the pretended instant and the real instant it was anchored at.
#     `DELETE` is `POST /dev/clock/clear`, and it is also the first half of a set:
#     the table holds at most one row by a unique index over `(true)`, so replacing
#     an override is a delete and an insert rather than an update.
#     **`UPDATE` and `TRUNCATE` are withheld, and that is the assertion**, as it is
#     on `classification` and on E1-10's group. The two instants are one fact
#     written together: an anchor rewritten on its own leaves a clock running at
#     the right rate from the wrong origin, which no single reading of `now` can
#     detect and which
#     `test_now_adds_the_real_time_elapsed_since_the_override_was_anchored` is the
#     only thing in the suite that would catch. Withholding the verb makes
#     write-together a property of the database rather than a rule the next writer
#     has to remember.
#     **This grant does not weaken the ticket's "unreachable outside development".**
#     No grant can express "in development only", so the gate is behavioural and in
#     two places: `app.services.clock` refuses to read the table unless
#     `is_development(settings)`, and both `/dev` routes answer `404` outside
#     development. A deployment holding a stray `clock_override` row goes on
#     reading the real clock, which
#     `test_the_override_moves_neither_now_nor_today_outside_development` asserts in
#     both deployment environments.
#     **What this table carries, for §4.1.** `id`, `pretend_now` and `anchored_at`
#     — two timestamps and no person. No foreign key to anything, no view over it,
#     so it is outside `test_identity_column_marker.py`'s marker and outside the
#     policed inventory of
#     `tests/unit/test_the_org_views_are_read_only_through_the_grant.py`.
#     Decided and spent in E2-04, ruled in `docs/disputes/E2-04-02.md`.
#   - `pulse_app` **reads and inserts** `survey_window`, the table E2-06 fills, and
#     holds no `UPDATE` and no `DELETE` on it. The entry above predicted this one —
#     "E2 will do it again when the first student write path needs a grant on
#     `response`" — and it arrives one table early, because the development console
#     reads windows and the Celery worker writes them.
#     `docs/disputes/E2-06-03.md` is its record: the branch was run without the
#     grant and eight tests across the three development-console modules failed with
#     `permission denied for table survey_window` behind a 500, one of them
#     `invariant`-marked, so `pytest -m invariant` and
#     `scripts/ci/check_invariants.py` were red too. The grant is issued by revision
#     `c9b4e0a71d38`, so a fresh database reproduces it.
#     **A verb per caller, and both were measured.** `SELECT` has two readers: the
#     `/dev` console's open-window column, and the derivation's own "which windows
#     does this section already have", which is what makes the hourly reconciler
#     idempotent instead of a repeated `INSERT` refused by
#     `uq_survey_window_section_id_week_id`. `INSERT` is the derivation writing one.
#     Applying exactly these two and changing nothing else turned those three
#     modules green; neither verb is spare.
#     **`UPDATE`, `DELETE` and `TRUNCATE` are withheld, and that is the assertion**,
#     as on `classification`, on `clock_override` and on E1-10's group. SPEC §3.1:
#     "Missed weeks cannot be back-filled (this keeps the signal weekly and the
#     grading unambiguous)." Without `UPDATE` this connection structurally cannot
#     move a `closes_at` and reopen a week that has closed; without `DELETE` it
#     cannot remove a window that a response (E2-08) or a participation denominator
#     (§3.4) has already been counted against. It is also what makes E2-06's "an
#     existing `(section_id, week_id)` row is skipped, never rewritten" a property of
#     the database rather than a rule the next writer has to remember — re-deriving
#     after a calendar edit is E11's, ruled at the E2 breakdown on 2026-08-31, and
#     this connection could not do it if it tried.
#     **What this table carries, for §4.1.** `id`, `section_id`, `week_id`,
#     `term_id`, `opens_at` and `closes_at` — three references to structure and two
#     timestamps. No person, no subject, no name, no address. It carries no
#     identity-marked column and no view reads it, so there is no join from a window
#     to a person on this connection.
#     Decided and spent in E2-06, ruled in `docs/disputes/E2-06-03.md`; ADR 0111
#     records the ticket's decisions, this grant and its withheld verbs among them.
#   - `pulse_app` **reads** `week`, `question_set`, `question`, `response` and
#     `answer`, and holds no other verb on any of the five. These are E2-09's
#     student read path — the one `GET` that answers "for me, right now, what is
#     there?" — and the entry above predicted them by name: "E2 will do it again
#     when the first student write path needs a grant on `response`". It is the
#     read path that arrives first, so the verbs are `SELECT` and only `SELECT`;
#     E2-08's submit needs `INSERT` and `UPDATE` on `response` and `answer` and
#     they land in that ticket's own revision, with the code that issues them.
#     `docs/disputes/E2-09-02.md` is the record, and each of the five was measured
#     load-bearing one relation at a time: held out, the branch fails with
#     `permission denied for table week` behind a 500 on twelve of E2-09's
#     fourteen items; granted one at a time, Postgres refuses the next relation in
#     turn — `week`, then `question_set`, then `question`, then `response`, then
#     `answer`, then nothing. No verb here is spare.
#     **A statement per grant.** `week` is the term-week number a window is over,
#     which SPEC §2.2 makes a *row's own* `number` rather than something to
#     re-derive from the window's instants — a second reading of §3.1's rhythm
#     agrees with the first only while both are right, and §2.2's two week axes
#     are what E2-09 answers under `course_week` and `term_week`.
#     `question_set` and `question` are SPEC §3.2's five questions, which E2-10
#     renders from this one read. `response` and `answer` are the reader's **own**
#     submission, for the resubmit case.
#     **`INSERT`, `UPDATE`, `DELETE` and `TRUNCATE` are withheld on all five, and
#     that is the assertion**, as on `classification`, `clock_override` and
#     `survey_window`. A read path that structurally cannot write is a read path
#     that cannot alter a submission it was only meant to display, and it cannot
#     back-fill a missed week (§3.1) or move a question's wording out from under
#     the `answer` rows keyed to it (§3.2's versioned set). The write verbs the
#     entry below adds are E2-08's submit path's, and they are granted by that
#     ticket's own revision rather than widened here.
#     **What `SELECT` on `response` and `answer` is not.** It is not a widening of
#     what a student can see: §4.1 item 1's scoping is the read's `WHERE` clause —
#     E2-05's `(user_id, section_id, week_id)` key with the author left in — and
#     `test_the_student_read_path_names_nothing_outside_the_enrollment.py` is the
#     assertion that a classmate's stored submission does not come back. Neither
#     table carries an identity-marked column: a `response` names a section, a
#     week and the `user_id` §4 keys it to, and that key is what makes it the
#     reader's own rather than somebody's name.
#     **One of the five closes a gap that predates the ticket**, recorded rather
#     than quietly fixed: `app.services.survey_windows.derive_windows_for_section`
#     has selected `week` on this connection since E2-06's hourly beat, and no
#     revision had ever granted it. It lands here because this is the ticket whose
#     read needed it.
#     Decided and spent in E2-09, ruled in `docs/disputes/E2-09-02.md`; precedent
#     `docs/disputes/E2-04-02.md` and `docs/disputes/E2-06-03.md`.
#   - `pulse_app` also **writes and revises** `response` and `answer`, on top of
#     the reads the entry above grants — the four tables E2-08's submit path
#     touches are `question_set`, `question`, `response` and `answer`, and this is
#     the arrival the `survey_window` entry predicted ("E2 will do it again when
#     the first student write path needs a grant on `response`").
#     This is the first student write path in the product, and
#     [ADR 0110](../../docs/adr/0110-answer-values-are-validated-by-the-write-path.md)
#     names the shape in advance: "`pulse_app` is granted nothing on `answer` by
#     E2-05's migration at all, and E2-08 grants the privilege its own path needs
#     beside the code that justifies it — the same shape ADR 0055 gives
#     `classification`."
#     **A verb per caller, and each was measured** by asking what fails without
#     it; the branch was run with the grants file removed from the revision and
#     the route answers 500 on its first `SELECT` against `question_set`.
#     `question_set` `SELECT` finds the set in force and `question` `SELECT` reads
#     ADR 0110's `minimum_value`, `maximum_value`, `step` and the conditional-rule
#     columns — that record makes those three "the only statement of the ranges in
#     the system", and validating against them means reading them. `response`
#     `SELECT` finds a resubmission's existing row, `INSERT` writes the first
#     submission of a week, and `UPDATE` writes `last_submitted_at` on a
#     resubmission and `is_valid` when the async sweep revises a floored verdict.
#     `answer` `SELECT` reads the rows a resubmission revises and the comment text
#     the sweep re-classifies, `INSERT` writes a question answered for the first
#     time, `UPDATE` is
#     [ADR 0115](../../docs/adr/0115-a-resubmission-revises-its-answers-in-place.md)'s
#     in-place revision, and `DELETE` removes a question answered before and left
#     blank now.
#     **What is withheld is the assertion**, as on `classification`, on
#     `clock_override` and on `survey_window`. `response` `DELETE` is **not**
#     granted: SPEC §3.1 makes a missed week unfillable and §3.4 counts these rows,
#     so this connection structurally cannot remove a week a participation score
#     has already been computed from. Nothing beyond `SELECT` is granted on
#     `question` or `question_set` — the instrument is written by a migration and
#     by the seed, under the bootstrap identity — so a route cannot edit the
#     question it is validating against. `classification` gains a column in this
#     ticket and no privilege: it keeps `SELECT, INSERT` and stays append-only,
#     which is what makes ADR 0115's refusal-rather-than-delete the only way a
#     judged comment can go, since a referential action on that table is an
#     `UPDATE` this role does not hold.
#     **What these tables carry, for §4.1.** `question_set` and `question` hold the
#     instrument — a version, an ordinal, question text, bounds — and nothing about
#     anybody. `response` holds the three keys SPEC §8's uniqueness rule is written
#     over, two submission timestamps and `is_valid`; `answer` holds a response, a
#     question and exactly one of a rating, a comment or a workload figure. The
#     student's identity is a foreign key on `response` and the identity behind it
#     sits on `user_identity`, which `pulse_app` is granted no `SELECT` on — the
#     same argument `enrollment`'s entry makes, and the one
#     `tests/integration/test_identity_column_marker.py` records for both tables.
#     Decided and spent in E2-08, ruled in `docs/disputes/E2-08-03.md`; the whole
#     argument for each verb, and for the ones withheld beside them, is in
#     `backend/app/views_sql/survey_submission_grants_v001.sql`.
RUNTIME_BASE_TABLE_PRIVILEGES = frozenset(
    {
        (CARE_ROLE, "role_assignment", "SELECT"),
        (APPLICATION_ROLE, "classification", "SELECT"),
        (APPLICATION_ROLE, "classification", "INSERT"),
        (APPLICATION_ROLE, "lti_platform", "SELECT"),
        (APPLICATION_ROLE, "lti_deployment", "SELECT"),
        (APPLICATION_ROLE, "tool_signing_key", "SELECT"),
        (APPLICATION_ROLE, "lti_launch_nonce", "INSERT"),
        (APPLICATION_ROLE, "lti_launch_nonce", "DELETE"),
        (APPLICATION_ROLE, "lti_launch_state", "SELECT"),
        (APPLICATION_ROLE, "lti_launch_state", "INSERT"),
        (APPLICATION_ROLE, "lti_launch_state", "DELETE"),
        (APPLICATION_ROLE, "prefix", "SELECT"),
        (APPLICATION_ROLE, "term", "SELECT"),
        (APPLICATION_ROLE, "start_letter_map", "SELECT"),
        (APPLICATION_ROLE, "course", "SELECT"),
        (APPLICATION_ROLE, "course", "INSERT"),
        (APPLICATION_ROLE, "section", "SELECT"),
        (APPLICATION_ROLE, "section", "INSERT"),
        (APPLICATION_ROLE, "user", "INSERT"),
        (APPLICATION_ROLE, "launch_defect", "INSERT"),
        (APPLICATION_ROLE, "enrollment", "SELECT"),
        (APPLICATION_ROLE, "enrollment", "INSERT"),
        (APPLICATION_ROLE, "nrps_call", "SELECT"),
        (APPLICATION_ROLE, "nrps_call", "INSERT"),
        (APPLICATION_ROLE, "clock_override", "SELECT"),
        (APPLICATION_ROLE, "clock_override", "INSERT"),
        (APPLICATION_ROLE, "clock_override", "DELETE"),
        (APPLICATION_ROLE, "survey_window", "SELECT"),
        (APPLICATION_ROLE, "survey_window", "INSERT"),
        (APPLICATION_ROLE, "week", "SELECT"),
        (APPLICATION_ROLE, "question_set", "SELECT"),
        (APPLICATION_ROLE, "question", "SELECT"),
        (APPLICATION_ROLE, "response", "SELECT"),
        (APPLICATION_ROLE, "response", "INSERT"),
        (APPLICATION_ROLE, "response", "UPDATE"),
        (APPLICATION_ROLE, "answer", "SELECT"),
        (APPLICATION_ROLE, "answer", "INSERT"),
        (APPLICATION_ROLE, "answer", "UPDATE"),
        (APPLICATION_ROLE, "answer", "DELETE"),
    }
)

# The column-scoped grants, as `(role, relation, column, privilege)`. **A second
# constant rather than a fourth member on the one above**, because the two are
# read out of different catalogs — `pg_class.relacl` and `pg_attribute.attacl` —
# and `has_table_privilege` reports nothing at all about the entries here.
#
# **This set was empty until E1-10, and it says so.** Every grant this scheme
# wrote before then was table-level, which is why
# `test_the_runtime_roles_hold_no_privilege_on_a_base_table_beyond_the_reveals_own`
# below could treat a runtime role named in *any* column ACL as a widening by
# definition. That is no longer true, and the change is deliberate rather than a
# convenience: the alternative was `UPDATE` on `course` and `section` table-wide,
# which is strictly more than E1-10's writer needs and which would have handed the
# application connection the ability to rewrite a section's derived calendar —
# ADR 0021's four columns, whose whole rule is that `apply_section_code` is the
# only thing that writes them.
#
# The three entries, and why each is the narrowest that does the job:
#
#   - `course(lms_title)` — a launch corrects a fallback title once the platform
#     supplies a real one, and follows the platform when it renames a course. SPEC
#     §2.1 makes the title the LMS's, so following it is the rule rather than an
#     edit.
#   - `course(title_is_fallback)` — Pulse's own record of which of those two the
#     stored title is (ADR 0091), written by the same statement.
#   - `section(lms_context_memberships_url)` — SPEC §7.3's stored roster service
#     address, updated when a later staff launch advertises a different one.
#   - `user(id)` — **`SELECT`, not `UPDATE`**, and the round-3 security review's
#     LOW. The writer inserts a `user` row and reads the table never; what it needs
#     is the row's own key back, and Postgres checks `SELECT` per returned column
#     on an `INSERT … RETURNING`. Table-wide `SELECT` would have been read access to
#     `lms_user_id`, which is the `sub` claim verbatim (ADR 0045) and the stable
#     join key E1-01 keeps out of every view — so a connection holding it can
#     enumerate every subject that has ever launched and join a response to a
#     person, on the connection every screen in the product runs on. The narrowest
#     grant that does the job is one column, and it is the column that identifies
#     nobody.
#
# What is *not* here is the assertion: no `UPDATE` on `course.lms_number`, on
# `section.lms_section_code`, on the binding columns E1-10 adds to `section`, on
# any of ADR 0021's four calendar columns, or on `user` in any form. A launch
# discovers those and never revises them, and the database is what says so.
#
# **E1-11 spends three more, all on `enrollment`, and for the same reason E1-10
# spent its three**: the alternative is `UPDATE` on `enrollment` table-wide, which
# is strictly more than the sync needs and which would hand the application
# connection the ability to rewrite `started_on`, `user_id` and `section_id`.
#
#   - `enrollment(ended_on)` — a drop closes the window. SPEC §3.4: "Drops: scores
#     stop updating", which the tool can only act on once the row says when the
#     student left.
#   - `enrollment(lms_window_start)` / `enrollment(lms_window_end)` — the ADR 0048
#     extension's values, which a platform may revise between syncs (a drop dated
#     after the fact, a start corrected). `lms_`-prefixed because the platform owns
#     them (E0-05's rule), and updatable for the same reason `course.lms_title` is:
#     following the platform is the rule rather than an edit.
#
# **`started_on`, `user_id` and `section_id` are deliberately absent**, and that is
# the load-bearing half of this group. They are first-seen facts — which member,
# which section, and the day Pulse first saw them, which §3.4's fallback for an
# undated late add is computed from — so a connection that could rewrite them could
# re-date a student's whole term, and a re-add is a second row rather than an edit
# to the first (ADR 0023, E1-11's D3). No `UPDATE` anywhere on `nrps_call` or
# `role_assignment` either: an append-only log and a purview grant.
RUNTIME_COLUMN_PRIVILEGES = frozenset(
    {
        (APPLICATION_ROLE, "course", "lms_title", "UPDATE"),
        (APPLICATION_ROLE, "course", "title_is_fallback", "UPDATE"),
        (APPLICATION_ROLE, "section", "lms_context_memberships_url", "UPDATE"),
        (APPLICATION_ROLE, "user", "id", "SELECT"),
        (APPLICATION_ROLE, "enrollment", "ended_on", "UPDATE"),
        (APPLICATION_ROLE, "enrollment", "lms_window_start", "UPDATE"),
        (APPLICATION_ROLE, "enrollment", "lms_window_end", "UPDATE"),
    }
)


def base_tables(session: Any) -> list[str]:
    """Every base and partitioned table in `public`, by name."""
    return [row[0] for row in session.execute(text(PUBLIC_BASE_TABLES))]


# The three mechanisms by which a role may obtain a name in this schema, named so
# that a control can require each one to be *found* rather than merely not found.
IDENTITY_BY_GRANT = "grant"
IDENTITY_BY_COLUMN = "column"
IDENTITY_BY_EXECUTE = "execute"


def identity_by_grant(session: Any, role: str, table: str) -> list[str]:
    """Where `role` may read `table` directly, by any privilege.

    `has_table_privilege` answers for three situations at once, which is why this
    file needs no separate check for any of them: a role that was **granted** the
    privilege, a role that **owns** the table, and a **superuser**. The last two
    hold it without any ACL entry existing anywhere.
    """
    return [
        f"holds {privilege} on public.{table}"
        for privilege in TABLE_PRIVILEGES
        if session.execute(
            text(HAS_TABLE_PRIVILEGE),
            {"role": role, "relation": f"public.{table}", "privilege": privilege},
        ).scalar_one()
    ]


def column_grants_beyond_the_table(session: Any, role: str, table: str) -> list[str]:
    """Where `role` holds a privilege on a *column* of `table` and not on the table.

    Written as "and not on the table" so the three probes report disjoint routes.
    `has_column_privilege` answers true when the privilege is held table-wide as
    well, so without that clause a role with plain `SELECT` would be reported by
    two probes and the message would read as two findings. Subtracting the table
    case leaves exactly the interesting one, and its description says so: a role
    that can read one column of the identity table and cannot read the table.

    Takes the table as an argument rather than closing over `IDENTITY_TABLE`, so
    that `test_the_identity_probes_in_this_file_see_a_column_grant` can exercise it
    against a throwaway table of its own. Nothing in this suite grants on
    `user_identity`, not even inside a transaction it intends to roll back.
    """
    found: list[str] = []
    for column, _ in public_table_columns(session, table):
        for privilege in COLUMN_PRIVILEGES:
            on_column = session.execute(
                text(HAS_COLUMN_PRIVILEGE),
                {
                    "role": role,
                    "relation": f"public.{table}",
                    "column": column,
                    "privilege": privilege,
                },
            ).scalar_one()
            if not on_column:
                continue
            on_table = session.execute(
                text(HAS_TABLE_PRIVILEGE),
                {"role": role, "relation": f"public.{table}", "privilege": privilege},
            ).scalar_one()
            if not on_table:
                found.append(f"holds {privilege} on public.{table}.{column} and not on the table")
    return found


def identity_by_column(session: Any, role: str, table: str) -> list[str]:
    """Where `role` may read one column of `table` without reading the table."""
    return column_grants_beyond_the_table(session, role, table)


def identity_by_execute(session: Any, role: str, table: str) -> list[str]:
    """Where `role` may call a function that reads the identity table for it.

    A `SECURITY DEFINER` function runs as its **owner**, and this schema's owner
    holds `SELECT` on the identity table by construction (ADR 0043) — so `EXECUTE`
    on one is a privilege on identity held in a different currency. That is the
    mechanism the first version of this sweep missed, and it missed it in the worst
    possible place: `pulse_care` holds no table privilege on `user_identity` at all,
    deliberately, so the role designed to reach identity was invisible to a rule
    phrased over table privileges.

    **`table` is accepted and ignored**, so that the three probes share one
    signature and `IDENTITY_PROBES` can be a plain table of them. It is not an
    oversight: this route does not depend on which relation is named, because the
    caller spends the *owner's* privileges on whatever the body reads. A probe
    that filtered by table here would answer differently for a throwaway table
    than for the real one and make the self-test measure something else.
    """
    return [
        f"may EXECUTE {function['signature']}"
        for function in security_definer_functions(session, role)
        if function["executable"]
    ]


# The probes `ways_to_reach_identity` runs, as a table rather than as two blocks
# inside it. Two reasons, and neither is decoration.
#
# The controls below name these mechanisms when they require each one to be
# *found*, so a control cites the same constant the sweep is built from and the
# two cannot drift apart.
#
# And it gives a mutation run **one syntactically valid line** to delete for
# disabling a probe: remove any row and the module still parses, the sweep still
# runs, and the control for that mechanism is what goes red. Deleting a probe
# expression by hand leaves the file unparseable, which reports a collection error
# rather than a failed control — and an error is not a red, it is a run that proved
# nothing (`docs/MISTAKES.md` entry 16, a harness reporting kills it had not made).
#
# **Each of the three rows has a control that fires on its deletion alone**, with
# no mutation of the schema, and that took two attempts to get right. The grant and
# execute rows are covered by controls in
# `test_neither_runtime_role_can_become_a_role_that_may_read_identity`, which
# require each mechanism to be *found* on a role that certainly has it. The column
# row is covered by `test_the_identity_probes_in_this_file_see_a_column_grant`,
# which stands a column grant up on a throwaway table and asks **through this
# table** rather than calling the probe directly. The first version called it
# directly, so deleting the row left all 28 tests green and the control guarded
# nothing (`docs/MISTAKES.md` entry 9: a guard that has never been executed against
# the case it claims to stop is a comment).
IDENTITY_PROBES: tuple[tuple[str, Any], ...] = (
    (IDENTITY_BY_GRANT, identity_by_grant),
    (IDENTITY_BY_COLUMN, identity_by_column),
    (IDENTITY_BY_EXECUTE, identity_by_execute),
)


def ways_to_reach_identity(
    session: Any, role: str, table: str = IDENTITY_TABLE
) -> list[tuple[str, str]]:
    """Every route by which `role` may obtain a name, as `(mechanism, description)`.

    **Why this is closed at three, argued from the catalog rather than from a
    list.** This enumeration has now been widened twice, each time by a security
    review finding a currency it did not count, so the third version owes an
    argument of a different kind. Here it is: a privilege that yields identity
    *data* is recorded in exactly one of three places in a PostgreSQL catalog, and
    each probe reads one of them.

      - **`pg_class.relacl`** — the privilege is on the table. `has_table_privilege`
        answers it, and answers three situations at once: granted, held by
        **owning** the table, and held by being a **superuser**. So `rolsuper`
        needs no separate probe, an owner needs none, and a membership in a
        predefined role such as `pg_read_all_data` needs none — all of them come
        back as a table privilege on `user_identity`.
      - **`pg_attribute.attacl`** — the privilege is on a *column* of the table,
        which `relacl` does not record and `has_table_privilege` does not report.
        This is the one PR #40's review measured; the constant `COLUMN_GRANTEES`
        above carries the measurement.
      - **`pg_proc.proacl`** — the privilege is `EXECUTE` on a function that reads
        the table on the caller's behalf. It counts only for a `SECURITY DEFINER`
        function, which runs as its **owner**; an ordinary function runs as its
        caller and so hands out nothing the caller lacks. The function's own owner
        is caught by the same call, since an owner may always execute what it owns.

    `pg_database.datacl` and `pg_namespace.nspacl` are the two ACLs deliberately
    *not* probed, and they are not an omission: `CONNECT` and `USAGE` gate whether
    an object can be *reached*, and neither confers a read of anything. A role
    holding both and nothing else reads no row.

    So a fourth probe becomes necessary only if a new kind of object can carry
    identity — not if a new role, a new grant or a new function appears. Two such
    kinds exist and are handled outside this helper rather than inside it:

      - **a view that selects an identity column**, which is shut harder than any
        probe here could shut it:
        `test_identity_column_marker.py::test_no_view_reads_a_column_the_identity_marker_names`
        is `invariant`-marked precisely because a view is read with its *owner's*
        privileges rather than its reader's, so no arrangement of grants would make
        such a view safe;
      - **an object in another schema** — a `SECURITY DEFINER` function in a schema
        of its own would sit outside the `nspname = 'public'` scope every sweep in
        this file uses. That premise is now asserted rather than assumed, by
        `test_public_is_the_only_schema_this_deployment_defines`, which is the
        cheap way to close it: one assertion in one place, instead of widening
        five queries and changing what four E0-10 tests mean.

    **What it is scoped to** (`docs/MISTAKES.md` entry 14): `IDENTITY_TABLE` by
    default — the constant this whole module is written around — rather than every
    relation the identity marker names. Today they are the same one table. A second
    identity-bearing table is a change to this module's central constant and to
    every test in it, not a gap in this helper, and the marker convention lives in
    another module, so reading it from here would be a second copy of it (entry 13).
    `table` is an argument only so that
    `test_the_identity_probes_in_this_file_see_a_column_grant` can run the probes
    against a throwaway table of its own; nothing in this suite grants on
    `user_identity`, not even inside a transaction it means to roll back.

    **Two questions, and the caller decides which it is asking.** Asked about a
    role a runtime role can *become*, every route is dangerous. Asked about the
    runtime roles *themselves*, the execute route is the one legitimate door —
    `pulse_care` holds it by design — so the caller filters that mechanism out and
    says why. `test_neither_runtime_role_holds_any_privilege_on_user_identity` is
    the one that does.

    **One route is outside the catalog entirely**, and no probe of any kind would
    see it: a connection to this database made from inside it, through `dblink` or
    a loopback `postgres_fdw`, carrying a credential rather than holding a grant.
    Creating either needs privileges the runtime roles are separately denied, and
    E0-26 already owns the one place this project contemplates such a connection.
    """
    return [
        (mechanism, description)
        for mechanism, probe in IDENTITY_PROBES
        for description in probe(session, role, table)
    ]


def test_no_role_outside_this_scheme_is_granted_anything_in_public(db_session: Any) -> None:
    """Criterion: the grant set is *exactly* what the migrations wrote, on the grantee axis.

    Every other grant assertion in this file names a role and asks what it holds.
    That shape cannot see a role nobody thought to ask about, and neither can any
    gate in this build: `alembic check` reads no ACL in either direction, so
    `CREATE ROLE pulse_reporting; GRANT SELECT ON public.user_identity TO
    pulse_reporting` is two statements that hand out every name in the system
    while the drift job, the test suite and the invariant pass all stay green.

    So this asks the question from the other end — who is named in an ACL
    anywhere in `public` — and requires the answer to be the roles this scheme
    names, plus each object's own owner. The definer is discovered from the
    catalog rather than spelled, because E10 replaces the function it owns and a
    rule written with its name would retire with it.

    **Three ACLs, because an object's privileges are not all in `relacl`**, and
    both of the other two were added by a security review finding the sweep blind
    to them. `pg_class.relacl` is the relation. `pg_attribute.attacl` is a single
    column of one — `GRANT SELECT (identity_name) ON public.user_identity TO
    pulse_reporting` appears in no `relacl` anywhere, and `COLUMN_GRANTEES` above
    carries the measurement of what that grantee can then read. `pg_proc.proacl` is
    `EXECUTE`, for `SECURITY DEFINER` functions only: `GRANT EXECUTE ON FUNCTION
    public.<the reveal> TO pulse_reporting` also writes nothing to any `relacl`,
    and the role is not `pulse_app`, so neither this sweep as first written nor the
    `invariant`-marked refusal above would mention it — while the grantee may call
    the one function whose job is to return a name.

    **The allowed grantees on a definer function are `pulse_care`, and — since
    E1-12, E1-11 and that ticket's security round — `pulse_app` on the five
    functions `SANCTIONED_APPLICATION_EXECUTE` names.** E0-10's own sentence still governs
    the door that returns identity: `pulse_care` "gets `EXECUTE` on a **single**
    `SECURITY DEFINER` function". What this epic adds is a different kind of
    function — three point lookups answering with a uuid, owned by a role that
    reads five columns and no identity among them; one writer that takes an address
    and can never write a name; and one that takes a person and a section and
    writes the single role its body names — and each is admitted here **by name**,
    out of that constant at the top of this file, rather than by widening the rule
    to "the application role may execute definer functions". A sixth grant to
    `pulse_app` therefore still appears below, which is the whole point of writing
    the inventory down.

    Which five they are is *not* this test's question. This sweep owns the grantee
    axis — who is named in an ACL anywhere — and the count and contents are
    `test_the_application_role_may_execute_only_the_point_resolvers`'s, one
    equality in one place. E0-10's count for `pulse_care` is likewise
    `test_pulse_care_may_execute_exactly_the_two_halves_of_the_care_door`'s.

    **`PUBLIC` is in both sweeps and is the sharpest case, and it means different
    things on the two.** On a relation Postgres grants nothing to `PUBLIC` by
    default, so an entry is always deliberate. On a function it grants `EXECUTE` to
    `PUBLIC` by default, so an entry there is what a migration reaches by *not*
    saying anything. Either way, one line reaches every role in the cluster without
    naming one.

    **Two controls, one per sweep, because an ACL that was never materialised
    contributes no row** — and a database where nothing was granted satisfies "no
    unexpected grantee" perfectly (`docs/MISTAKES.md` entry 3). The relation sweep
    must find something: E0-10 grants `SELECT` on its read views, and the first
    `GRANT` on a relation materialises its whole ACL including the owner's own
    entries. The function sweep must find `pulse_care` holding `EXECUTE`, which is
    the one function grant this scheme certainly makes; requiring that exact entry
    rather than merely a non-empty result is what tells a working sweep from one
    reading the wrong catalog.

    **The column sweep has no live entry to require, and so it is controlled
    elsewhere**: this schema grants nothing at column level, so `attacl` is null
    everywhere and the sweep is correctly empty. An empty sweep proves nothing
    about the query, so `test_the_identity_probes_in_this_file_see_a_column_grant`
    stands a real column grant up on a throwaway table inside a transaction it
    rolls back and requires this same query to report it. That is where the
    emptiness here gets its meaning (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: `CREATE ROLE pulse_reporting; GRANT
    SELECT ON public.user_identity TO pulse_reporting`, and its two siblings in the
    other currencies — `GRANT SELECT (identity_name) ON public.user_identity TO
    pulse_reporting` and `GRANT EXECUTE ON FUNCTION public.<the reveal> TO
    pulse_reporting`. One reporting role added by a later ticket, three ways to
    give it a name, and no other test in this suite would mention any of them.
    Also `GRANT EXECUTE ON FUNCTION public.<the reveal> TO PUBLIC`, which should
    turn this red *and* the `invariant`-marked refusal above.
    **The near miss it tolerates**: another grant to one of the roles this scheme
    already names — `pulse_care` on a function, any of the three on a relation.
    That is the privilege axis, and
    `test_the_runtime_roles_hold_no_privilege_on_a_base_table_beyond_the_reveals_own`
    is where it is caught; a rule that went red on any new grant at all would fail
    on the third read view.
    """
    definer = the_reveal_definer(db_session)
    expected = {APPLICATION_ROLE, CARE_ROLE, definer, *IDENTITY_DEFINER_ROLES}
    granted = db_session.execute(text(RELATION_GRANTEES)).mappings().all()
    on_columns = db_session.execute(text(COLUMN_GRANTEES)).mappings().all()
    executable = db_session.execute(text(SECURITY_DEFINER_GRANTEES)).mappings().all()

    assert granted, (
        "No relation in `public` carries an access control list at all, so this sweep read "
        "nothing and would report success against any grant in the database. E0-10 grants "
        "`SELECT` on its two read views, and the first `GRANT` on a relation materialises that "
        "relation's whole ACL — so an empty sweep means the grants are missing, the views are "
        "missing, or this query is reading the wrong schema."
    )
    care_grants = [row for row in executable if row["grantee"] == CARE_ROLE]
    assert any(row["privilege"] == "EXECUTE" for row in care_grants), (
        f"No `SECURITY DEFINER` function in `public` names `{CARE_ROLE}` as holding `EXECUTE` in "
        f"its ACL: the sweep found {[dict(row) for row in executable]}. That grant is E0-10's "
        "central criterion — the Care role may call a single such function — so its absence means "
        "either the Care door is shut, which "
        "`test_the_care_roles_grants_are_enough_to_complete_a_reveal` diagnoses, "
        "or this sweep is not reading `pg_proc.proacl` at all. In the second case the assertion "
        "below is satisfied by any function grant to anybody."
    )

    beyond_on_relations = [
        f"{row['grantee']} holds {row['privilege']} on public.{row['relation']}"
        for row in granted
        if row["grantee"] not in expected and row["grantee"] != row["owner"]
    ]
    beyond_on_columns = [
        f"{row['grantee']} holds {row['privilege']} on public.{row['relation']}.{row['column_name']}"
        for row in on_columns
        if row["grantee"] not in expected and row["grantee"] != row["owner"]
    ]
    beyond_on_functions = [
        f"{row['grantee']} holds {row['privilege']} on {row['routine']}"
        for row in executable
        if row["grantee"] != row["owner"] and not an_inventoried_execute(row)
    ]
    unexpected = sorted(beyond_on_relations + beyond_on_columns + beyond_on_functions)
    assert not unexpected, (
        f"{unexpected}. On a relation, the roles this scheme names are {sorted(expected)} — the "
        "two connection roles of ADR 0001, the reveal function's own owner from ADR 0043, and the "
        f"three definer owners this epic adds ({', '.join(IDENTITY_DEFINER_ROLES)} — ADR 0094, "
        "E1-11's D7 and that ticket's security round) — plus whoever owns the relation, which is "
        "the migration identity ADR 0009 "
        f"sanctions. On a `SECURITY DEFINER` function it is `{CARE_ROLE}`, the owner, and "
        f"`{APPLICATION_ROLE}` on the functions `SANCTIONED_APPLICATION_EXECUTE` names, and "
        "nothing else: E0-10 gives the Care role `EXECUTE` on the door and E0-26 item 1 made that "
        f"door two halves, and `{APPLICATION_ROLE}` is refused that door in an `invariant`-marked "
        "test above, with the five functions it *may* call pinned as an equality beside it. "
        "Anything else holds a privilege that no ticket in this epic granted and that nothing in "
        "this repository will ever revoke.\n\n"
        "`PUBLIC` appearing here is the worst case and reads like the mildest, and it reads "
        "differently on the two kinds. On a relation it is always deliberate, because Postgres "
        "grants no table privilege to `PUBLIC` by default. On a function it is what a migration "
        "reaches by *not* revoking, because `EXECUTE` on a new function goes to `PUBLIC` — and "
        "every role in the cluster is a member, including `pulse_app`, which is refused "
        "`user_identity` by name one test above and would reach a name through the door "
        "anyway.\n\n"
        "A column entry is the quietest of the three and the one to read most carefully: "
        f"`GRANT SELECT (<a column>) ON public.{IDENTITY_TABLE} TO <anyone>` leaves `SELECT *` "
        "refused, so every `invariant`-marked refusal in this file goes on passing while the "
        "grantee reads names one column at a time. ADR 0001 rejects column grants by name, which "
        "is exactly why somebody reaches for one.\n\n"
        "None of this is visible to any gate: `alembic check` compares `Base.metadata` against the "
        "database, and `Base.metadata` holds tables and columns — no `pg_roles` row, no `relacl`, "
        "no `attacl`, no `proacl` (E0-20 item 3b, measured on the pinned Alembic 1.19)."
    )


@pytest.mark.invariant
def test_the_runtime_roles_hold_no_privilege_on_a_base_table_beyond_the_reveals_own(
    db_session: Any,
) -> None:
    """Criterion: exactly what the migrations wrote, not a superset — on the privilege axis.

    `test_neither_runtime_role_holds_any_privilege_on_user_identity` above pins one
    table. This pins the rest of them: over every base table in `public`, the two
    connection roles hold exactly the three privileges
    `RUNTIME_BASE_TABLE_PRIVILEGES` names, and that constant at the head of this
    section carries the sentence each one comes from.

    **What the equality buys beyond a ceiling.** Two of the three are `pulse_app`
    on `classification`, and the interesting half of that entry is what is *not*
    in it. SPEC §8 requires `classification` to be append-only; `SELECT, INSERT`
    granted with `UPDATE`, `DELETE` and `TRUNCATE` withheld is what makes
    append-only a property of the database rather than a rule the next writer has
    to remember. Nothing else in this suite asserts that, and an equality is the
    only shape that can: `>=` would be satisfied by a connection that can rewrite
    a moderation verdict.

    **What `pulse_app` reading `classification` means for §4.1: nothing, and the
    reason is worth one paragraph so it is not re-derived.** A classification row
    is a model verdict about comment text (§5.2's clear / harmful / privacy /
    nonsense) with prompt and model versioning; it carries no name, and the
    connection it is read on cannot reach `user_identity` by any statement, which
    is what the three `invariant`-marked refusals above assert. So there is no
    join from a verdict to a person on this connection. What *would* have a §4.1
    consequence is a **view** that joins `classification` to an identity-marked
    column, and that is
    `test_identity_column_marker.py`'s
    `test_no_view_reads_a_column_the_identity_marker_names`, which is
    `invariant`-marked because a view is read with its owner's privileges rather
    than its reader's.

    **One adjacent rule that this grant does not enforce and must not be read as
    enforcing.** §5.2 hides flagged comments from the instructor entirely below the
    n-threshold, and routes threat and self-harm classifications to Care where they
    are "never shown to the instructor". Those are `classification` rows, and this
    connection can read them — as it must, since it is the connection every screen
    runs on. Those rules live in the read path, in `services/`, and a table grant
    neither implements them nor breaks them. Nobody should conclude from this
    entry that a row `pulse_app` can read is a row an instructor may see.

    **Views are outside this on purpose**, and that is what keeps it from being a
    tripwire. Reading a view is what `pulse_app` exists to do, and a third read
    view granted to it by a later ticket is ordinary work; what is not ordinary is
    a grant on the table *behind* a view, which is SPEC §8's separation undone —
    "enforced in the database, not just the application" means the connection
    cannot reach the base table, not that the query politely does not. The
    control on what a view may expose is the identity-marker sweep in
    `test_identity_column_marker.py`, which is `invariant`-marked.

    **Two controls, and neither is ceremony.** `pulse_app` must hold `SELECT` on
    at least one view, or "holds nothing on a base table" is equally true of a
    role that holds nothing anywhere and every assertion here is about a database
    with no grants in it. And there must be base tables to sweep, or the cross
    product is empty.

    **Asked through `has_table_privilege`** rather than by reading `relacl`, so a
    privilege reaching a role by membership in another role counts:
    `GRANT pulse_reveal_definer TO pulse_app` writes no ACL entry anywhere and
    hands over `SELECT` on `user_identity`.

    **And through `COLUMN_GRANTEES` beside it, because `has_table_privilege` is
    blind to a column grant.** `RUNTIME_COLUMN_PRIVILEGES` is the expected set at
    column level, compared as an equality in both directions exactly as the table
    set is. **It was empty until E1-10**, because every grant this scheme wrote
    before then was table-level — ADR 0043's enumeration and E0-13's
    `SELECT, INSERT` on `classification` alike — and a runtime role named in any
    column ACL was therefore a widening by definition. E1-10 spends four
    column-scoped grants deliberately — three `UPDATE`s, in preference to the
    table-wide `UPDATE` on `course` and `section` that would otherwise have been
    needed, and one `SELECT` on `user(id)`, in preference to the table-wide read of
    `lms_user_id` the round-3 review found; the constant carries the sentence for
    each. Without this half,
    `GRANT UPDATE (verdict) ON public.classification TO pulse_app` would leave the
    append-only property broken with this test green, which is the same shape as
    the identity finding one table over and would have been left open by fixing
    only that one. And the *missing* half of the column comparison is what stops a
    later ticket quietly dropping one of E1-10's three, which would leave a launch
    unable to correct a fallback title and nothing saying why.

    **The mutation it exists to survive**: `GRANT SELECT ON public.enrollment TO
    pulse_app` — the convenience grant E0-33 names, added to make one query work,
    invisible to `alembic check` and to every other test here. Also `GRANT UPDATE
    ON public.classification TO pulse_app`, which is a widening *within* a table
    the role already reads and which no `>=` comparison could see, and its
    column-scoped form `GRANT UPDATE (verdict) ON public.classification TO
    pulse_app`, which no `has_table_privilege` answer reports at all.
    **The near miss it tolerates**: `GRANT SELECT ON <a new read view> TO
    pulse_app`, which stays green.

    **When this goes red for a good reason**, which will happen and has already
    happened once: E0-13's `classification` grant was legitimate, deliberate, and
    absent from the first version of this constant. E2 will do it again when the
    first student write path needs a grant on `response`. That is what this test
    is for — a widening of the confidentiality surface recorded deliberately, in
    the pull request that makes it, rather than arriving unnoticed. The failure
    message below carries how to tell one from a defect.

    **What this shape does not catch** (`docs/MISTAKES.md` entry 14):

      - **A grant written into `views_sql/` and never applied.** The comparison is
        against a hand-written record, so the file-to-database direction holds
        only for the three entries listed. A grants file that a revision stops
        executing shows up here only if it names one of them.
      - **Whether a listed grant is *right*.** The constant records what the
        record sanctions; a bad grant written into both the SQL and this file is
        wrong in both. Line-by-line review of `views_sql/` is the control ADR 0043
        names for that, and E0-34 is the ticket.
      - **A widening to a view**, deliberately — see above.
      - **Privileges on anything that is not a base table**: functions, schemas,
        the database itself. The first belongs to the two definer tests above, the
        second and third to the downgrade tests below.
    """
    tables = base_tables(db_session)
    views = read_views(db_session)
    assert tables, (
        "There is no base table in `public`, so this test swept nothing. Every table SPEC §8 lists "
        "should be here after `alembic upgrade head`."
    )
    assert views, (
        "There is no view in `public`, so the control below has nothing to find and this test "
        "cannot tell a role that reads through views from a role that holds nothing at all. "
        "`test_identity_separated_views.py` diagnoses that."
    )

    for role in RUNTIME_ROLES:
        require_role(db_session, role)
    readable_views = {
        view
        for view in views
        if db_session.execute(
            text(HAS_TABLE_PRIVILEGE),
            {"role": APPLICATION_ROLE, "relation": f"public.{view}", "privilege": "SELECT"},
        ).scalar_one()
    }
    assert readable_views, (
        f"`{APPLICATION_ROLE}` may read none of {views}. Then it holds nothing anywhere, the "
        "assertion below is true of a database with no grants in it, and the read paths for every "
        "screen in the product are shut. "
        "`test_the_application_role_is_refused_a_select_on_user_identity` reads the same fact from "
        "the other side."
    )

    held = privileges_held(db_session, RUNTIME_ROLES, tables)
    on_columns = db_session.execute(text(COLUMN_GRANTEES)).mappings().all()
    held_on_columns = {
        (row["grantee"], row["relation"], row["column_name"], row["privilege"])
        for row in on_columns
        if row["grantee"] in RUNTIME_ROLES and row["relation"] in tables
    }
    beyond_on_tables = [
        f"{role} holds {privilege} on public.{relation}"
        for role, relation, privilege in held - RUNTIME_BASE_TABLE_PRIVILEGES
    ]
    beyond_on_columns = [
        f"{role} holds {privilege} on public.{relation}.{column}"
        for role, relation, column, privilege in held_on_columns - RUNTIME_COLUMN_PRIVILEGES
    ]
    beyond = sorted(beyond_on_tables + beyond_on_columns)
    missing = sorted(
        [
            f"{role} should hold {privilege} on public.{relation}"
            for role, relation, privilege in RUNTIME_BASE_TABLE_PRIVILEGES - held
        ]
        + [
            f"{role} should hold {privilege} on public.{relation}.{column}"
            for role, relation, column, privilege in RUNTIME_COLUMN_PRIVILEGES - held_on_columns
        ]
    )
    assert not beyond and not missing, (
        f"Beyond what this scheme grants: {beyond}. Missing from it: {missing}. The connection "
        f"roles could read the views {sorted(readable_views)} throughout, so this is about base "
        "tables and not about a role that holds nothing.\n\n"
        "The first list is the one to read first. SPEC §8 puts the instructor and leadership read "
        "paths through views that 'structurally cannot join to `user` identity columns — enforced "
        "in the database, not just the application', and a connection holding a privilege on the "
        "base table behind a view is that enforcement removed while every view, every revoke and "
        "every refusal test stays exactly as it was. Nothing else notices: `alembic check` reads "
        "no ACL at all (E0-20 item 3b), and asserting a refusal on `user_identity` proves the "
        "refusal without proving that nothing else was granted (E0-33 item 3).\n\n"
        "**An entry naming a column** — `…public.classification.verdict` rather than "
        "`…public.classification` — is a grant `has_table_privilege` does not report at all, so "
        "it is read out of `pg_attribute.attacl` instead. The expected set at column level is "
        "`RUNTIME_COLUMN_PRIVILEGES`, which held nothing until E1-10 and now holds three "
        "column-scoped `UPDATE`s and one column-scoped `SELECT`, each with its sentence. Anything "
        "else at column grain is a "
        "widening by definition, and on an append-only table it is the whole of how append-only "
        "stops being true.\n\n"
        "The second list means this scheme has lost a grant it needs: without `SELECT` on "
        "`role_assignment` the Care path cannot resolve the actor whose assignment it is about, "
        "and without `INSERT` on `classification` the moderation classifier cannot record a "
        "verdict. Each entry in `RUNTIME_BASE_TABLE_PRIVILEGES` carries the sentence it comes "
        "from, and so does each entry in `RUNTIME_COLUMN_PRIVILEGES` beside it.\n\n"
        "**How to tell a legitimate new grant from a widening**, because this test cannot and the "
        "reader has to. Four questions, in order:\n"
        "  1. Does anything in the tree issue it? If no `.sql` file under `backend/app/views_sql/` "
        "and no revision grants it, nothing will reproduce it on a fresh database — it was run by "
        "hand against this one, and that is drift rather than a decision.\n"
        "  2. Does a record say why the role needs it — a ticket criterion, a SPEC section, an "
        "ADR? `pulse_app` on `classification` has SPEC §8's append-only sentence behind it. A "
        "grant whose only justification is that a query failed without it is the convenience grant "
        "this test exists for.\n"
        "  3. Is it the narrowest privilege that does the job? `SELECT, INSERT` rather than `ALL`. "
        "The verbs *withheld* are usually the assertion — on an append-only table they are what "
        "makes it append-only.\n"
        "  4. Does the table carry, or join to, an identity-marked column "
        "(`test_identity_column_marker.py`)? Then it is not a convenience grant at all, it is "
        "§4.1's wall, and the answer is no rather than a new entry here.\n\n"
        "If the grant survives all four, `RUNTIME_BASE_TABLE_PRIVILEGES` at the head of this "
        "section is the one place it is recorded — with its sentence, not just its name — and the "
        "pull request that adds it says which table and why. That is the cost of an exact set, and "
        "it is deliberate: the alternative is deriving this from the grant files themselves, where "
        "every grant justifies itself and a widening is green (`docs/MISTAKES.md` entry 19)."
    )


@pytest.mark.invariant
def test_neither_runtime_role_can_become_a_role_that_may_read_identity(db_session: Any) -> None:
    """The grant that writes no grant: a membership into a role that can reach a name.

    `test_a_runtime_role_cannot_become_a_role_that_owns_a_table` above asks
    `pg_has_role(role, other, 'USAGE')`, which answers "are that role's privileges
    available to this one *without* a `SET ROLE`". A membership granted `WITH
    INHERIT FALSE` is absent from that answer, and it is absent from
    `has_table_privilege` too — so the grant appears in no ACL entry, in no
    privilege probe, and in no test in this file written before this one.
    `'MEMBER'` is the mode that reports a membership whether or not it inherits.

    **What counts as reaching identity is three mechanisms, not one**, and this
    enumeration has been widened twice by security review — each time by a currency
    it did not count. `ways_to_reach_identity` above carries the argument for the
    set being closed at three, made from the catalog's own structure rather than
    from a list of cases anybody thought of. The short form of what the two
    widenings found: `pulse_care` holds **no** table privilege on `user_identity`,
    which is the entire design, so a rule phrased over table privileges alone waves
    through a membership into the one role *designed* to reach identity — it holds
    `EXECUTE` on the function whose job is to return a name. And a grant of one
    *column* is recorded in `pg_attribute.attacl`, which no table-level probe reads
    and which leaves `SELECT *` refused while every name in the table is readable
    one column at a time.

    **Measured, on this stack, with the grant applied and revoked around it.** As
    `pulse_app`, after `GRANT pulse_care TO pulse_app WITH INHERIT FALSE`:
    `has_table_privilege(user_identity, 'SELECT')` false, `pg_has_role('pulse_care',
    'USAGE')` false — the mode the older test uses — `pg_has_role('pulse_care',
    'MEMBER')` **true**, and `has_function_privilege(reveal, 'EXECUTE')` false.
    Then, one statement later, after `SET ROLE pulse_care`: `EXECUTE` on the reveal
    **true**, `SELECT` on `role_assignment` **true**, and a direct read of
    `user_identity` still refused. The whole suite passed throughout. So the
    connection every instructor and leadership screen runs on becomes Care in one
    statement and calls the door; `role_assignment` is readable from there, which
    is where a `person_id` holding a live `CARE` assignment comes from; and the
    reveal verifies the actor it is *handed*, so the audit row that door writes
    names an innocent person. That last part is why this is more than an
    escalation — it is an escalation that launders itself through §4's audit trail.

    **Four controls, because every assertion here is that a set is empty**, and a
    sweep that finds nothing looks exactly like a sweep that cannot see
    (`docs/MISTAKES.md` entry 3):

      - the membership query run for the bootstrap identity must come back
        non-empty. A superuser is a member of every role, so a query that finds
        nothing for it is broken;
      - the membership query must report a **non-inheriting** membership. This is
        the control the mode itself rests on, and without it `MEMBER_OF_ROLES` can
        be edited from `'MEMBER'` to `'USAGE'` — which reads as a tidy-up making it
        consistent with `REACHABLE_ROLES` above — with every other control here
        still green, because a superuser satisfies `pg_has_role` in every mode and
        the remaining controls call the probe directly rather than through this
        query. The hole this test exists to close would be open again with the
        suite passing. So a throwaway role is created, granted to `pulse_app`
        `WITH INHERIT FALSE`, required to appear, and rolled back;
      - the predicate must **fire** on the reveal function's owner, by the grant
        mechanism. That role holds `SELECT` on `user_identity` by construction;
      - the predicate must **fire** on `pulse_care`, by the execute mechanism. That
        role may call exactly the two halves of the Care door, which is E0-10's
        central criterion as E0-26 item 1 amended it and is asserted by
        `test_pulse_care_may_execute_exactly_the_two_halves_of_the_care_door`.

    Three of the four are repairs for things a security review found rather than
    hygiene: each time, had the mechanism been probed for and *required to be
    found*, its absence would have shown up as a failing control instead of a green
    sweep. **The third mechanism, a column grant, has no live role to fire on** —
    nothing in this schema holds one — so it is controlled in
    `test_the_identity_probes_in_this_file_see_a_column_grant`, which stands one up
    on a throwaway table and requires `identity_by_column` to report it. None of
    these roles is in any reachable set today; they are controls on the probe, not
    on the schema.

    **The mutation it exists to survive**: `GRANT pulse_care TO pulse_app WITH
    INHERIT FALSE`, which was applied out of band and left all 42 tests passing.
    Also `GRANT pulse_reveal_definer TO pulse_care WITH INHERIT FALSE`, the same
    statement aimed at the grant mechanism rather than the execute one, and
    `GRANT <the migration identity> TO pulse_app WITH INHERIT FALSE` — a superuser
    and the owner of `user_identity`, which `has_table_privilege` reports as
    holding everything on it without any ACL entry existing. And one mutation of
    the test rather than of the schema: editing `MEMBER_OF_ROLES` from `'MEMBER'`
    to `'USAGE'`, which the second control is the only thing that catches.
    **The near miss it tolerates**: a membership in a role that can reach neither —
    a future `pulse_metrics` holding `SELECT` on a read view and nothing else —
    which stays green.

    **What it does not cover** (`docs/MISTAKES.md` entry 14): a reachable role that
    owns some table *other* than the identity one. That is a different escalation —
    an owner may grant itself more on what it owns — and it belongs to
    `test_a_runtime_role_cannot_become_a_role_that_owns_a_table`, which asks in
    `'USAGE'` mode and therefore has the non-inheriting hole this test closes for
    identity only. Changing that test's mode changes the meaning of an E0-10
    assertion, and is raised rather than done here.
    """
    definer = the_reveal_definer(db_session)
    connected_as = db_session.execute(text(CURRENT_ROLE)).scalar_one()

    assert db_session.execute(text(MEMBER_OF_ROLES), {"role": connected_as}).all(), (
        f"`pg_has_role` reports that `{connected_as}` — the bootstrap superuser these tests "
        "connect as — is a member of no other role, which cannot be true of a superuser. The "
        "query is broken, and the assertion below would pass against any membership at all."
    )

    # A membership that certainly does not inherit, made in order to be found and
    # then rolled back. The role is `NOLOGIN` and is granted nothing at all, so it
    # carries no privilege even in the event this transaction were somehow to
    # commit: what this control needs to exist is a *membership*, not a privilege.
    probe_role = f"pulse_membership_probe_{uuid4().hex[:8]}"
    savepoint = db_session.begin_nested()
    try:
        db_session.execute(text(f'CREATE ROLE "{probe_role}" NOLOGIN NOINHERIT'))
        db_session.execute(text(f'GRANT "{probe_role}" TO "{APPLICATION_ROLE}" WITH INHERIT FALSE'))
        rows = db_session.execute(text(MEMBER_OF_ROLES), {"role": APPLICATION_ROLE})
        reported = [name for (name,) in rows]
    finally:
        savepoint.rollback()

    assert probe_role in reported, (
        f"`{APPLICATION_ROLE}` was granted `{probe_role}` `WITH INHERIT FALSE` and the membership "
        f"query did not report it: it answered {reported}. `MEMBER_OF_ROLES` is therefore asking "
        "in `'USAGE'` mode — 'are that role's privileges available without a `SET ROLE`' — which "
        "answers false for exactly the membership this test exists to catch. That edit reads like "
        "a tidy-up making the query consistent with `REACHABLE_ROLES` above, and it leaves every "
        "other control here green: a superuser satisfies `pg_has_role` in every mode, and the two "
        "controls below call the identity probe directly rather than through this query. The mode "
        "is the whole test — `'MEMBER'` reports a membership whether or not it inherits."
    )

    definer_routes = ways_to_reach_identity(db_session, definer)
    assert any(mechanism == IDENTITY_BY_GRANT for mechanism, _ in definer_routes), (
        f"The identity probe finds no *grant* route for `{definer}` — the owner of the reveal "
        f"function, which reads `{IDENTITY_TABLE}` with that role's privileges. It found "
        f"{definer_routes}. Either the reveal cannot work, which "
        "`test_the_reveal_functions_owner_holds_exactly_the_privileges_its_job_needs` diagnoses, "
        "or this probe cannot see a table privilege on that table at all — in which case the "
        "sweep below reports nothing dangerous whatever anybody is a member of."
    )

    care_routes = ways_to_reach_identity(db_session, CARE_ROLE)
    assert any(mechanism == IDENTITY_BY_EXECUTE for mechanism, _ in care_routes), (
        f"The identity probe finds no *execute* route for `{CARE_ROLE}`, which may call exactly "
        f"one `SECURITY DEFINER` function by E0-10's central criterion. It found {care_routes}. "
        "This control is the repair for the defect that made it necessary: the first version of "
        "this test asked only about table privileges, and `pulse_care` deliberately holds none — "
        "so the role designed to reach identity was the one role the sweep waved through, and a "
        "membership into it passed. If this control ever goes quiet again, the sweep below is "
        "blind in exactly that way."
    )

    dangerous: list[str] = []
    for role in RUNTIME_ROLES:
        require_role(db_session, role)
        for (reachable,) in db_session.execute(text(MEMBER_OF_ROLES), {"role": role}):
            dangerous += [
                f"{role} can become {reachable}, which {description}"
                for _, description in ways_to_reach_identity(db_session, reachable)
            ]

    assert not dangerous, (
        f"{dangerous}. A membership is a privilege the holder reaches with one `SET ROLE`, and "
        "granted `WITH INHERIT FALSE` it is a privilege that appears in no ACL entry, in no "
        "`has_table_privilege` answer, in no `has_function_privilege` answer, and in "
        "`test_a_runtime_role_cannot_become_a_role_that_owns_a_table` — which asks in `'USAGE'` "
        "mode, where a non-inheriting membership does not appear. So every other assertion in "
        f"this file stays green: ADR 0001's 'no grant of any kind on `{IDENTITY_TABLE}`' is a "
        "statement about grants, and a membership is not one.\n\n"
        "**Read the mechanism in the message.** A *grant* route means the reachable role can read "
        f"`{IDENTITY_TABLE}` directly — by grant, by owning it, or by being a superuser, all three "
        "of which `has_table_privilege` reports. A *column* route means it can read one column of "
        "it and not the table, which leaves `SELECT *` refused and every `invariant`-marked "
        "refusal in this file passing. An *execute* route means it can call a `SECURITY DEFINER` "
        "function, which runs as its owner and therefore spends that owner's `SELECT` on "
        f"`{IDENTITY_TABLE}` on behalf of whoever called it. The last is the worst of the three "
        "and reads as the mildest: the caller obtains a name **and** the function writes an audit "
        "row naming the actor it was handed, so §4's 'every identity access is automatically "
        "audit-logged with actor, timestamp, and case' records somebody else."
    )


def test_the_identity_probes_in_this_file_see_a_column_grant(db_session: Any) -> None:
    """The column mechanism, executed against a grant made to be found.

    Every other mechanism in `IDENTITY_PROBES` has a live role to fire on, so its
    control can require a *find* on the real schema. This one has none: nothing
    here grants at column level, `pg_attribute.attacl` is null everywhere, and both
    the probe and `COLUMN_GRANTEES` correctly report nothing. An empty result
    proves nothing about a query (`docs/MISTAKES.md` entry 3), so the grant is
    stood up instead.

    **On a throwaway table, never on the identity table.** The transaction is
    rolled back by `db_session` either way, and a `GRANT` on `user_identity`
    written into a test file — even one intended to be undone — is a line whose
    correctness rests entirely on a fixture behaving. `ways_to_reach_identity` and
    all three probes take their table as an argument so that this test never has to
    write one.

    **Asked through `ways_to_reach_identity`, not through the probe directly**, and
    that is the repair rather than a detail. The first version of this test called
    `column_grants_beyond_the_table` itself, so deleting
    `(IDENTITY_BY_COLUMN, identity_by_column),` from `IDENTITY_PROBES` left all 28
    tests in this file green: the helper still worked, and nothing asked the probe
    *set* whether it still contained the column route. A control that cannot fail
    when the thing it guards is removed is not a control
    (`docs/MISTAKES.md` entry 9). Routed through the table, deleting that row turns
    this test red on an unmutated schema, which is the only shape that proves the
    row is load-bearing.

    **Three assertions, and the first is the finding.** The reviewer's measurement
    is reproduced in order: the *grant* mechanism must answer **nothing** for a role
    that holds only a column grant — which is what makes this route invisible to
    the probe that existed before it — while the *column* mechanism and the grantee
    sweep must both find it. Asserting only the last two would leave the reason the
    mechanism is needed unstated and unchecked.

    **The mutation it exists to survive**: deleting
    `(IDENTITY_BY_COLUMN, identity_by_column),` from `IDENTITY_PROBES`, or dropping
    `pg_attribute` from `COLUMN_GRANTEES`. Either leaves the schema untouched and
    every sweep reporting clean, and this is the only test that would notice.
    **The near miss it tolerates**: a role holding the privilege on the whole
    table, which the column mechanism deliberately does not report — that is the
    grant mechanism's finding, and reporting it twice would read as two holes where
    there is one.
    """
    probe_table = f"column_grant_probe_{uuid4().hex[:8]}"
    privilege = COLUMN_PRIVILEGES[0]
    savepoint = db_session.begin_nested()
    try:
        db_session.execute(text(f'CREATE TABLE public."{probe_table}" (note text, secret text)'))
        db_session.execute(
            text(f'GRANT {privilege} (secret) ON public."{probe_table}" TO "{APPLICATION_ROLE}"')
        )
        routes = ways_to_reach_identity(db_session, APPLICATION_ROLE, probe_table)
        swept = [
            dict(row)
            for row in db_session.execute(text(COLUMN_GRANTEES)).mappings()
            if row["relation"] == probe_table
        ]
    finally:
        savepoint.rollback()

    by_table = [found for mechanism, found in routes if mechanism == IDENTITY_BY_GRANT]
    by_column = [found for mechanism, found in routes if mechanism == IDENTITY_BY_COLUMN]

    assert not by_table, (
        f"The grant mechanism reports {by_table} for `{APPLICATION_ROLE}`, which was granted "
        f"{privilege} on *one column* of `public.{probe_table}`. `has_table_privilege` is "
        "therefore answering true for a column-scoped grant, the route this test is about is not "
        "invisible to the older probe on this server, and the two assertions below are measuring "
        "something else. That would be a change in Postgres's behaviour rather than in this "
        "schema — check the server version before changing anything."
    )
    assert by_column, (
        f"`ways_to_reach_identity` reports no column route for `{APPLICATION_ROLE}`, which was "
        f"just granted {privilege} on `public.{probe_table}.secret` and holds nothing on the "
        "table. Either the probe is blind or `IDENTITY_BY_COLUMN` is no longer in "
        "`IDENTITY_PROBES` — and this is the only test in the suite that can tell you either "
        f"way. With it gone, `GRANT {privilege} (<a column>) ON public.{IDENTITY_TABLE} TO "
        "pulse_app` is invisible to `test_neither_runtime_role_holds_any_privilege_on_user_"
        "identity` and to the membership sweep alike: the grant ADR 0001 rejects by name, which "
        "leaves `SELECT *` refused and every behavioural refusal in this file passing."
    )
    assert swept, (
        f"`COLUMN_GRANTEES` reports no entry for `public.{probe_table}` after a column grant was "
        f"made on it. The grantee sweep is not reading `pg_attribute.attacl`, so "
        "`test_no_role_outside_this_scheme_is_granted_anything_in_public` is empty of column "
        "entries because the query finds none rather than because the schema has none — and "
        "`CREATE ROLE pulse_reporting; GRANT SELECT (<a column>) ON public.user_identity TO "
        "pulse_reporting` would pass it."
    )


def test_public_is_the_only_schema_this_deployment_defines(db_session: Any) -> None:
    """The premise every sweep in this file rests on, asserted instead of assumed.

    `nspname = 'public'` appears in every catalog query here and in the two
    neighbouring modules. That is not a rule anybody wrote down — it is an
    observation about today's schema doing duty as a scope. A schema of its own
    plus `GRANT USAGE ON SCHEMA` puts a `SECURITY DEFINER` function, a view or a
    table outside every one of those sweeps, and nothing else in this build looks
    at `pg_namespace` at all: `alembic check` compares `Base.metadata`, which holds
    tables and columns.

    Three deliberate statements rather than one, and no non-`public` schema exists
    today — so this is the cheap end of the trade rather than a live hole. It is
    closed here, in one assertion, rather than by widening five queries and
    changing what four E0-10 tests mean on the last round before this ticket ships.

    **The control is that `public` itself is found.** A query that matched nothing
    would satisfy "no unexpected schema" perfectly, which is the shape this file
    guards against everywhere else (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: `CREATE SCHEMA reporting`, on its own —
    the first of the three statements, before anything is put in it.
    **The near miss it tolerates**: an extension installed into `public`, and any
    `pg_temp_*` or `pg_toast_*` schema Postgres makes for itself, none of which is
    a place a migration puts an object.

    **If a later ticket adds a schema deliberately**, this test is where that
    decision is recorded — and the pull request that adds it owes the widening of
    every sweep listed in the failure message, because until then those sweeps
    silently stop covering whatever moved.
    """
    schemas = [row[0] for row in db_session.execute(text(NON_SYSTEM_SCHEMAS))]

    assert "public" in schemas, (
        f"The schema query does not report `public` itself: it answered {schemas}. It is therefore "
        "not reading `pg_namespace` as intended, and the assertion below — that there is no other "
        "schema — would pass against a database full of them."
    )

    beyond = sorted(name for name in schemas if name != "public")
    assert not beyond, (
        f"This database defines the schemas {beyond} beside `public`. Every catalog sweep in this "
        "file, in `test_identity_separated_views.py` and in `test_identity_column_marker.py` is "
        "scoped to `nspname = 'public'`, so a table, a view or a `SECURITY DEFINER` function in "
        "one of these is outside all of them: outside the grantee sweeps, outside the identity "
        "probes, outside the marker sweep for a view that reads a name, and outside `alembic "
        "check`, which compares `Base.metadata` and holds no schema at all.\n\n"
        "If the schema is deliberate, widening those sweeps is part of the same change rather "
        "than a follow-up — a sweep that has silently stopped covering an object is worse than "
        "one that was never written, because the green reads as coverage."
    )


@pytest.mark.invariant
def test_downgrading_the_committed_record_revision_takes_back_the_definers_read_of_the_log(
    empty_database: Any,
    alembic_config_pointed_at: Any,
) -> None:
    """E0-26's own `downgrade()` gives back the fourth grant, and is executed here.

    **Why this exists.** The three tests above are pinned at both ends to E0-10's
    revision, so they undo E0-10's migration and never touch this one. Two
    reviewers on PR #53 found the same gap independently: this revision's
    `downgrade()` worked when either of them ran it by hand, and nothing in CI ran
    it. The part that matters is not the `DROP FUNCTION` — dropping a function
    takes its `EXECUTE` grant with it — but the hand-written `REVOKE SELECT ON
    public.audit_log FROM pulse_reveal_definer`, because `audit_log` survives the
    downgrade and a privilege on a surviving table is exactly what a `DROP` cannot
    carry. That is the same defect class E0-10's own round left behind once, which
    is why the test above exists at all.

    **Both ends pinned**, for the reason the section note gives at length: `-1` is
    relative to head, so the day a revision lands on top of this one, a relative
    step would undo that instead and every assertion here would be true of a
    database nobody had changed.

    **The baseline is read first and is not ceremony.** The assertions after the
    downgrade are that a privilege is *absent*, and absent is what a database
    produces when the migration never ran, when the role was never made, or when
    `has_table_privilege` was asked about the wrong database. So the two grants
    this revision certainly makes are read back at the revision before anything is
    undone.

    **The mutation it exists to survive**: deleting the `REVOKE` block from
    `downgrade()`, or dropping the second entry from `DOWNGRADE_SCRIPTS`. Either
    leaves `alembic check` green and every other test green, and leaves the
    definer holding `SELECT` on the whole audit log after a downgrade that is
    supposed to have taken it back.
    """
    from alembic import command

    config = alembic_config_pointed_at(empty_database)
    command.upgrade(config, THE_COMMITTED_RECORD_REVISION)

    with catalog_connection(empty_database) as connection:
        definer = the_reveal_definer(connection)
        at_the_revision = privileges_held(connection, (definer,), (AUDIT_TABLE,))
        halves_at_the_revision = len(the_care_door(connection))

    assert (definer, AUDIT_TABLE, "SELECT") in at_the_revision, (
        f"At revision {THE_COMMITTED_RECORD_REVISION}, the door's owner `{definer}` does not hold "
        f"`SELECT` on `public.{AUDIT_TABLE}`. That is the fourth grant E0-26 item 1 adds, and it "
        "is the whole subject of this test: with it absent here, the assertion below that the "
        "downgrade takes it back is satisfied by a database that never had it. What the owner "
        f"holds is {sorted(at_the_revision)}."
    )
    assert (definer, AUDIT_TABLE, "INSERT") in at_the_revision, (
        f"At revision {THE_COMMITTED_RECORD_REVISION}, `{definer}` does not hold `INSERT` on "
        f"`public.{AUDIT_TABLE}`. That grant is E0-10's and this revision does not touch it, so "
        "its absence means the baseline is wrong rather than that this revision is."
    )
    assert halves_at_the_revision == CARE_DOOR_HALVES, (
        f"At revision {THE_COMMITTED_RECORD_REVISION} the Care door has {halves_at_the_revision} "
        f"halves rather than {CARE_DOOR_HALVES}. The downgrade assertions below are about what "
        "this revision takes away, and they cannot mean anything if it did not put it there."
    )

    command.downgrade(config, BELOW_THE_COMMITTED_RECORD_REVISION)

    with catalog_connection(empty_database) as connection:
        after = privileges_held(connection, (definer,), (AUDIT_TABLE,))
        halves_after = len(the_care_door(connection))

    assert (definer, AUDIT_TABLE, "SELECT") not in after, (
        f"After downgrading below {THE_COMMITTED_RECORD_REVISION}, `{definer}` still holds "
        f"`SELECT` on `public.{AUDIT_TABLE}` — it holds {sorted(after)}. `audit_log` survives this "
        "downgrade, so the grant has to be revoked by hand: dropping the two functions takes their "
        "`EXECUTE` grants and nothing else. A definer left holding this read is an owner that can "
        "see who revealed whom across the whole institution, reachable through a door "
        f"`{CARE_ROLE}` may open, at a revision whose records say the grant does not exist."
    )
    assert (definer, AUDIT_TABLE, "INSERT") in after, (
        f"After the downgrade, `{definer}` no longer holds `INSERT` on `public.{AUDIT_TABLE}` — it "
        f"holds {sorted(after)}. That grant is E0-10's, not this revision's, and a `downgrade()` "
        "that takes back more than its own migration granted leaves the earlier revision unable to "
        "write its audit row: the reveal is then a door that returns a name and records nothing, "
        "which is worse than the defect E0-26 item 1 closed."
    )
    assert halves_after == 1, (
        f"After downgrading below {THE_COMMITTED_RECORD_REVISION} the Care door has {halves_after} "
        "halves rather than E0-10's single three-argument function. A downgrade that leaves the "
        "two-call door standing beside the restored one leaves both callable, and the old one "
        "takes its subject from its caller."
    )


# ---------------------------------------------------------------------------
# E1-01 — what the application role may read from a view, column by column.
# ---------------------------------------------------------------------------
#
# Every rule above is about *relations*: which role may read `user_identity`,
# which may execute the door, who else is named in an ACL. None of them can see
# what a view a role is allowed to read actually returns, and that is the gap the
# carried entry measured: "the set of columns `pulse_app` may read from a view is
# enumerated so a new grant on a join key fails the sweep rather than passing it"
# (`docs/tickets/e1/carried-from-e0.md`).
#
# It is a third question, not a restatement of the two next door.
# `test_identity_column_marker.py` asks what a view *reads*, out of `pg_depend`;
# `test_identity_separated_views.py` asks what a view *file says*, out of the
# text. This one asks what the application connection is *granted*, and the three
# disagree in both directions: a view can read a column it does not return, and a
# view whose column list is faultless can be granted to a role nobody sanctioned.
#
# **A `GRANT SELECT` on a view is the whole of the exposure.** A view runs with
# its owner's privileges, so the grant is not filtered by anything the reader
# holds; the columns of a view `pulse_app` may select are exactly the columns
# every instructor and leadership screen can put on a page.

# Every `(view, column, grantee)` a relation-level `SELECT` grant reaches, in
# `public`. Relation-level grants carry no column list, so the columns come from
# `pg_attribute` — a grant on the view is a grant on all of them.
#
# `aclexplode` rather than a text match on the `aclitem`, for the reason
# `RELATION_GRANTEES` above gives: the rendered form carries the grantor's name,
# which is `.env`'s choice. Grantee oid 0 is `PUBLIC`, which has no `pg_roles`
# row and is named here rather than dropped by the join — every role in the
# cluster is a member of it, `pulse_app` included, so a view granted to `PUBLIC`
# is a view `pulse_app` may read without being named anywhere.
APPLICATION_READABLE_VIEW_COLUMNS = """
    SELECT c.relname AS relation,
           a.attname AS column_name,
           coalesce(r.rolname, 'PUBLIC') AS grantee
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN LATERAL aclexplode(c.relacl) AS g
    LEFT JOIN pg_roles r ON r.oid = g.grantee
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    WHERE n.nspname = 'public'
      AND c.relkind IN ('v', 'm')
      AND g.privilege_type = 'SELECT'
    ORDER BY 1, 2, 3
"""

# The grantees whose `SELECT` puts a column within the application connection's
# reach. Two, and the second is the one that reads as mild: `PUBLIC` is the
# pseudo-role every role belongs to, so one `GRANT SELECT ON <a view> TO PUBLIC`
# is a grant to `pulse_app` that names no role at all.
#
# **A privilege reaching `pulse_app` by *membership* in another role is
# deliberately not counted here**, and that is not an oversight: it is the whole
# subject of `test_neither_runtime_role_can_become_a_role_that_may_read_identity`
# above, which asks `pg_has_role` in `'MEMBER'` mode because a membership granted
# `WITH INHERIT FALSE` appears in no ACL and in no `has_table_privilege` answer.
# Asking that question again here would report the same hole twice and would make
# this enumeration's expected set depend on the role graph rather than on what
# each view returns.
APPLICATION_READERS = (APPLICATION_ROLE, "PUBLIC")

# What the application connection may read from a view, and the whole of it:
# every `(view, column)` pair, written out by hand.
#
# **Hand-written and derived from the record, never read out of the view files**
# — the same decision `RUNTIME_BASE_TABLE_PRIVILEGES` and
# `REVEAL_DEFINER_PRIVILEGES` make above, for the same reason
# (`docs/MISTAKES.md` entry 19). A set assembled from `backend/app/views_sql/*.sql`
# at run time, or copied out of them without a sentence per entry, can be checked
# only against the SQL it is supposed to police: the file says select it, the
# catalog says granted, the test says fine, and a later ticket's column — which
# is exactly how `lms_user_id` would arrive — justifies itself on the way past.
#
# The cost is honest and is the point: a ticket that legitimately adds a column to
# a read view turns this red, and the pull request that adds it adds the entry and
# says why. That is a loud failure on a legitimate change, and the alternative is
# a silent pass on a widening.
#
# **`section_roster.user_id` is expected and allowed**, and it is worth saying
# outright because it looks like the thing this rule is against. The
# Pulse-internal uuid is the design — the carried entry on the reveal's
# composition calls it "the whole point of the view", since "the key is what makes
# a de-identified response addressable". `lms_user_id` is the one that must never
# appear: it is the LTI `sub`, it resolves a named student at the platform in one
# step, and ADR 0014's `lms_` prefix marks where the value came from rather than
# what it holds.
#
# **Per view, because the sanction is per view.** Each entry below carries the
# sentence that admits it, and the sentences come from the ticket, SPEC and the
# ADR rather than from the SQL: the five views are E0-10's two and ADR 0046's
# three, and what each is *for* is written down in those records.
SANCTIONED_VIEW_COLUMNS: dict[str, tuple[str, ...]] = {
    # E0-10's scope, in its own words: "a section-roster view and an
    # enrollment-count view that expose section membership and counts with **no**
    # identity columns reachable". This is the membership half, one row per
    # enrolment — `enrollment_id` is the row's key.
    #
    # **`user_id` is the Pulse-internal key and is the design**, not an oversight.
    # The carried entry on the reveal's composition states it as the view's
    # purpose: `section_roster` "hands instructor-scoped code the `user_id` of
    # every enrolled student — that is the whole point of the view, and the key is
    # what makes a de-identified response addressable". It names a `user` row and
    # resolves to a name nowhere: every path from it to `user_identity` is shut by
    # ADR 0001's grants, which the `invariant`-marked refusals earlier in this file
    # assert. `lms_user_id` is the value that is different in kind — SPEC §4 keys
    # responses "to the **LMS user ID** (`sub` from the launch)", so it is the one
    # identifier here that means something outside this database — and it is
    # absent, and must stay absent.
    #
    # **`lms_section_code` is an LMS key that resolves to a section**, never to a
    # person: ADR 0014 puts the `lms_` prefix on `section.lms_section_code` as an
    # ownership marker, and SPEC §8 derives `length_weeks` and the section's start
    # and end dates from that code through `start_letter_map`. Those three travel
    # with it for that reason. `started_on` and `ended_on` are the other two dates
    # on the roster row; every one of the four is a date rather than an
    # identifier.
    "section_roster": (
        "enrollment_id",
        "user_id",
        "section_id",
        "course_id",
        "term_id",
        "lms_section_code",
        "length_weeks",
        "section_start_date",
        "section_end_date",
        "started_on",
        "ended_on",
    ),
    # The counts half of the same E0-10 sentence. It carries no person key at all,
    # and the contrast with `section_roster` above is the point rather than a
    # detail: membership has to name the row it is about, and a count does not, so
    # the two views differ by exactly the column that needed arguing for.
    "section_enrollment_count": (
        "section_id",
        "course_id",
        "term_id",
        "lms_section_code",
        "enrolled_count",
    ),
    # ADR 0046's first view: "one assignment, its scope node, its edge". SPEC §8
    # spells the scope exactly — an assignment carries "its **scope as one
    # nullable foreign key per containment level** — `institution_id`,
    # `college_id`, `department_id`, `course_id`, `section_id` — of which exactly
    # one is non-null" — so the five scope columns are that sentence, and
    # `reports_to` is the edge, which ADR 0046's consequences say is carried now
    # because "E9 walks that edge".
    #
    # **There is deliberately no `prefix_id` here and there is one in
    # `containment_path` below**, which reads like an inconsistency and is not:
    # SPEC §8 says "there is deliberately no `prefix_id`, because no role in
    # §2.1's table is scoped to a prefix", while containment has six levels and a
    # prefix is one of them. The two views answer different questions.
    #
    # `person_id` names a `person` row and nothing else. `person.identity_name` is
    # marked identity (ADR 0022) and stays behind the view boundary; the key does
    # not carry it.
    #
    # **`permits_launch` and `permits_web_login` arrived with E1-13**, and this
    # enumeration going red on them is E1-01's guard doing its job rather than a
    # widening slipping past. They are ADR 0026's two stored generated columns on
    # `role_assignment`, each derived from `role` and from nothing else: "Derived,
    # so no write path can contradict the role; stored as columns, so the fact is
    # on the row where a view, a seed script or a psql session can read it." The
    # view withheld them until a ticket needed them — its own header said a later
    # `_v002` would add them — and E1-13 is that ticket: the landing resolution
    # filters a person's assignments by the entered door's permission column, so
    # "a Care assignment is unreachable from a launch" is a property of the row
    # rather than of a Python branch. Neither column carries anything about a
    # person: each is a boolean function of one enum value, so nothing here
    # narrows toward an identity, and what they widen is a fact SPEC §2.1's table
    # already states in public.
    "assignment_scope": (
        "assignment_id",
        "person_id",
        "role",
        "reports_to",
        "institution_id",
        "college_id",
        "department_id",
        "course_id",
        "section_id",
        "permits_launch",
        "permits_web_login",
    ),
    # ADR 0046's second: "which courses a person leads". SPEC §8:
    # "`lead_faculty_mapping` maps a person to the courses they lead (one lead per
    # course)". The pair is the whole answer, and ADR 0046 says why the courses
    # come from the mapping rather than from the assignment — the mapping carries
    # `UNIQUE (course_id)` and has exactly one answer per course.
    "lead_faculty_course": ("person_id", "course_id"),
    # ADR 0046's third: "every org node with the chain of ancestors above it",
    # emitting "one row per node at every level". Six columns for SPEC §2.1's six
    # containment levels, which is the same six `Purview` holds a set for. No
    # person table appears anywhere in it.
    "containment_path": (
        "institution_id",
        "college_id",
        "department_id",
        "prefix_id",
        "course_id",
        "section_id",
    ),
}

EXPECTED_APPLICATION_READABLE_COLUMNS: frozenset[tuple[str, str]] = frozenset(
    (view, column) for view, columns in SANCTIONED_VIEW_COLUMNS.items() for column in columns
)

# The views E1-01's controls plant. Named for the ticket so that one surviving a
# fixture change is traceable to it.
#
# The last two are the mutation battery's: a view granted to a role that is not an
# application reader, and a view granted one *column* at a time. Each covers a
# half of the candidate sweep that the first two left untouched — an ungranted
# view has a `NULL` `relacl` and so exercises no filter at all, and a
# table-granted view never reaches `pg_attribute.attacl`.
PLANTED_GRANTED_VIEW = "e1_01_planted_granted_view"
PLANTED_UNGRANTED_VIEW = "e1_01_planted_ungranted_view"
PLANTED_CARE_GRANTED_VIEW = "e1_01_planted_care_granted_view"
PLANTED_COLUMN_GRANTED_VIEW = "e1_01_planted_column_granted_view"

# The join key the carried entry names, and the table ADR 0001 puts it on. Spelled
# here rather than discovered, because the control's whole job is to stand up the
# exact disclosure that entry measured: "`user.lms_user_id` is a stable per-person
# join key (the LTI `sub`), and it is flagged by nothing".
LMS_USER_KEY = "lms_user_id"
USER_TABLE = "user"


def mentions(message: str, word: str) -> bool:
    """Does `message` name `word` as a whole word?

    A whole word rather than a substring, because the control below asks whether a
    *failure message* names a column, and the pair this rule is about is exactly
    the pair a substring check gets wrong: `user_id` occurs inside `lms_user_id`,
    so a message naming only the harmless key would satisfy a substring test for
    the dangerous one. `\\b` refuses that — `_` is a word character — and it is the
    difference between "the guard named the leak" and "the guard said something
    that contained the right letters".

    A second copy of a three-line regex, and deliberately: `test_identity_
    separated_views.py` has the other. A test module importing a sibling test
    module resolves only because of where pytest puts `tests/` on `sys.path`, so
    borrowing costs a file loader — that module's `identity_marker_module` is what
    it takes — and a loader for this is more machinery than the duplication.
    `IDENTITY_NAME_FRAGMENTS` next door records the same trade for the same
    reason.
    """
    return re.search(rf"\b{re.escape(word)}\b", message) is not None


def columns_the_application_role_may_read(session: Any) -> set[tuple[str, str]]:
    """Every `(view, column)` the application connection may `SELECT`, out of the catalog.

    **Two ACLs, because a `SELECT` on a column is not recorded where a `SELECT` on
    a relation is.** `pg_class.relacl` carries the grant on the view and says
    nothing about columns, so every column of the view is reachable through it;
    `pg_attribute.attacl` carries a grant on one column of it, appears in no
    `relacl` anywhere, and is invisible to `has_table_privilege` — measured on
    this stack during a security review of PR #40, and `COLUMN_GRANTEES` above
    carries the measurement. A view granted at column level to `pulse_app` is a
    view this sweep would miss entirely if it read only the first.

    **The candidate set comes from the catalog and not from a list in this file**,
    which is E1-01's scope in as many words: "the enumeration's inventory comes
    from somewhere the guarded structure cannot shrink". A hand-kept list of views
    would answer for the views somebody remembered, and the grant this rule exists
    to catch is one nobody wrote down.
    """
    views = set(read_views(session))
    granted = {
        (row["relation"], row["column_name"])
        for row in session.execute(text(APPLICATION_READABLE_VIEW_COLUMNS)).mappings()
        if row["grantee"] in APPLICATION_READERS
    }
    granted |= {
        (row["relation"], row["column_name"])
        for row in session.execute(text(COLUMN_GRANTEES)).mappings()
        if row["relation"] in views
        and row["privilege"] == "SELECT"
        and row["grantee"] in APPLICATION_READERS
    }
    return granted


@pytest.mark.invariant
def test_the_columns_the_application_role_may_read_from_a_view_are_exactly_the_enumerated_set(
    db_session: Any,
) -> None:
    """E1-01 criterion 2: an equality, so that a new column is a decision and not a diff.

    Every other grant rule in this file is about relations, and a relation-grained
    rule cannot see what a view returns. This one is the column enumeration the
    carried entry asks for: the set of `(view, column)` pairs `pulse_app` may
    select is compared, both directions, against a set written down in this file
    — so a column added to a read view, or a grant on a view nobody sanctioned,
    fails here rather than passing everything.

    **Views only, and base tables keep their table-grained equality.** They are
    different questions and the answers are shaped differently: a base table's
    rule is that the connection holds *no* privilege, which
    `test_the_runtime_roles_hold_no_privilege_on_a_base_table_beyond_the_reveals_own`
    states exactly, and a view's rule is that it holds `SELECT` on precisely the
    columns somebody sanctioned. Widening the base-table test to column grain
    would compare an empty set against an empty set, which is a rule that cannot
    fail; narrowing this one to relations would say nothing about `lms_user_id`,
    which is the point of it.

    **Marked `invariant` because it is a door rather than an inventory**, by the
    line this file's E0-33 section draws: a marked test guards one route into
    identity, and a column list a screen may read is that route at its last
    possible moment — after the view text, after the dependency graph, in the
    grant that decides what the application connection can put on a page.

    **The mutation it exists to survive**: `GRANT SELECT ON <a view exposing
    lms_user_id> TO pulse_app`, which is the carried entry's second finding and
    which every other test in this suite is green against — the marked-column
    sweeps say nothing, because `lms_` is ADR 0014's ownership marker rather than
    an identity one, and the relation-grained grant rules say nothing, because
    reading a view is what `pulse_app` exists to do. Also `GRANT SELECT (<a
    column>) ON <a view> TO pulse_app`, which is recorded in a third catalog, and
    `GRANT SELECT ON <a view> TO PUBLIC`, which names no role.
    **The near miss it tolerates**: none by construction — a new column on a
    granted view is a red, deliberately, and the entry that answers it is one line
    with the sentence that sanctions it.

    **Which is also how this test is defeated, so it is not defeated alone.**
    Writing the entry is the cheap repair for any red here, including the one red
    that must never be repaired that way, and no equality can tell a sanctioned
    column from a sanctioned mistake. The guards that stand behind it are
    `test_no_sanctioned_view_column_is_an_lms_join_key` below, which refuses that
    entry by name, and the two lineage rules, which refuse the *read* whatever the
    view calls the column: `test_identity_column_marker.py`'s strict rule at
    column grain, and `test_identity_separated_views.py`'s file-text sweep for a
    whole-row read. That split is measured rather than tidy, and the docstring on
    the name guard below says what it rests on.

    Two non-vacuity guards. There must be views, or the catalog sweep has nothing
    to enumerate; and the candidate set must be non-empty, or "the columns
    `pulse_app` may read are exactly these" is equally true of a connection that
    may read nothing at all and every screen in the product is shut.
    """
    views = read_views(db_session)
    assert views, (
        "There is no view in `public`, so this enumeration is over an empty set and would report "
        "success against any grant at all. `test_identity_separated_views.py` diagnoses that."
    )

    candidates = columns_the_application_role_may_read(db_session)
    assert candidates, (
        f"`{APPLICATION_ROLE}` may read no column of any of {views}. Either the grants are missing "
        "— in which case every read path in the product is shut, and "
        "`test_the_runtime_roles_hold_no_privilege_on_a_base_table_beyond_the_reveals_own` reads "
        "the same fact from the other side — or this sweep is reading the wrong catalog, in which "
        "case the comparison below is between an empty set and a hand-written one and says nothing "
        "about the database."
    )

    sanctioned = EXPECTED_APPLICATION_READABLE_COLUMNS
    surplus = sorted(f"{view}.{column}" for view, column in candidates - sanctioned)
    missing = sorted(f"{view}.{column}" for view, column in sanctioned - candidates)

    # **The operand is a bool on purpose, and it is a repair rather than a
    # style.** Written as `assert not surplus and not missing`, pytest's assertion
    # rewriting appends the *repr of the lists* to the exception, so the offending
    # column appears in `str(failure.value)` whatever this message says — and
    # `test_a_granted_view_exposing_the_lms_join_key_fails_the_enumeration`, whose
    # whole job is to establish that the message names it, passed against a
    # version of this message that printed only counts. Measured by the mutation
    # battery, not reasoned about; `docs/MISTAKES.md` entry 3 in the place a
    # control was supposed to close.
    #
    # With a plain bool there is nothing for the rewriter to expand — the
    # explanation is `assert False` — so the names below are the only names in the
    # failure, and the control that reads them is load-bearing. Nothing is lost to
    # a human reader: the message prints both lists in full, which the rewriter's
    # own output does less legibly.
    agrees = not surplus and not missing
    assert agrees, (
        f"Granted and not sanctioned: {surplus}. Sanctioned and not granted: {missing}.\n\n"
        "The first list is the one to read first. A view is read with its **owner's** privileges, "
        "so a `GRANT SELECT` on one hands every column it returns to the grantee whatever the "
        "grants on the tables underneath say — SPEC §8's separation is 'enforced in the database, "
        "not just the application', and this is the last place in the database where what an "
        "instructor's connection may see is decided. Nothing else in this build looks at it: "
        "`alembic check` reads no ACL and no `pg_class` entry for a view (E0-20 item 3b), the "
        "marked-column sweeps ask what a view *reads* rather than what it *returns*, and every "
        "other grant rule in this file is about relations.\n\n"
        f"**`{LMS_USER_KEY}` in that first list is the disclosure this rule was written for.** It "
        "is the LTI `sub`: a stable per-person key at the platform, marked `lms_` for ownership by "
        "ADR 0014 and by nothing for identity, matching no identity fragment and carrying no "
        "marker. A view returning it beside a comment lets an instructor resolve a named student "
        "in the LMS in one step with every §4.1 guard green, which is what "
        "`docs/tickets/e1/carried-from-e0.md` measured. A Pulse-internal `user_id` is a different "
        "thing and is expected: it names a row here and nothing anywhere else.\n\n"
        "The second list means a column this project sanctioned is not readable, which shuts a "
        "read path rather than opening one — a view replaced by a `_v002.sql` that dropped a "
        "column, or a grants file a revision stopped executing.\n\n"
        "If a column in the first list is legitimate, `EXPECTED_APPLICATION_READABLE_COLUMNS` at "
        "the head of this section is the one place it is recorded, with the sentence that "
        "sanctions it rather than just its name, and the pull request says which screen needs it. "
        "That constant is deliberately not read out of `backend/app/views_sql/`: a set derived "
        "from the files it polices lets every grant justify itself (`docs/MISTAKES.md` entry 19)."
    )


@pytest.mark.invariant
def test_no_sanctioned_view_column_is_an_lms_join_key() -> None:
    """The repair this enumeration invites, refused: an entry rather than a fix.

    An equality fails in two directions and only one of them has an honest repair.
    A column granted and not sanctioned is either a widening to undo or a decision
    to record — and recording it is one line in the constant above, which is
    exactly what somebody under time pressure would write for the column this
    whole ticket is about. So the constant is held to the one name the carried
    entry measured: `lms_user_id` may not appear in it, on any view, ever.

    **What this does not do, said plainly, because it would be easy to read as
    more.** It reads names, and a view may call a column anything: `SELECT
    u.lms_user_id AS platform_key` sanctioned as `platform_key` passes here. That
    case is not this test's, and the guard that owns it depends on how the view
    reached the column:

      - **a column-grain read** — `u.lms_user_id`, aliased or not, in a select
        list or a `WHERE` — is caught by
        `test_identity_column_marker.py`'s `test_no_view_reads_a_column_of_a_
        person_table_outside_the_join_keys`, which reads the lineage out of
        `pg_depend` and does not care what the view called it;
      - **a whole-row read** — `to_jsonb(u)` and its spellings — is caught by
        `test_identity_separated_views.py`'s file-text sweep, and **not**
        reliably by the catalog. Measured by a security re-pass: Postgres drops
        the `refobjsubid = 0` row as soon as the same view also names a column of
        that table, so `SELECT to_jsonb(u) … JOIN public."user" u ON u.id =
        e.user_id` records only `(1, id)` and the catalog's whole-row closure
        does not fire on it.

    That second one rests on every live view shipping as a file under
    `views_sql/`, which is a rule with a test behind it rather than a convention:
    `test_every_read_view_is_created_from_a_sql_file_under_views_sql`. A view
    created by an `op.execute` in a revision would be outside the text sweep, and
    that test is what makes it impossible to have one.

    So the three are a chain rather than a pair: this one refuses the cheap
    repair, the catalog refuses the aliased column read, the file sweep refuses
    the whole-row read, and none of them covers another's case.

    **The mutation it exists to survive**: adding `("<any view>", "lms_user_id")`
    to `SANCTIONED_VIEW_COLUMNS` to make the enumeration green.
    **The near miss it tolerates**: `section_roster.user_id`, which is sanctioned
    above with the sentence that admits it and is a different identifier —
    Pulse-internal, and resolving to a name nowhere.
    """
    assert SANCTIONED_VIEW_COLUMNS, (
        "`SANCTIONED_VIEW_COLUMNS` is empty, so this test reads nothing and reports success. The "
        "enumeration it belongs to would be failing on every granted column at the same time; "
        "that test is where an empty constant is diagnosed."
    )

    named = sorted(
        f"{view}.{column}"
        for view, columns in SANCTIONED_VIEW_COLUMNS.items()
        for column in columns
        if column == LMS_USER_KEY
    )
    assert not named, (
        f"{named} — `{LMS_USER_KEY}` is sanctioned as readable by `{APPLICATION_ROLE}`.\n\n"
        "That is the LTI `sub`: a stable per-person key at the platform, which resolves a named "
        "student in the LMS in one step. SPEC §4 keys responses to it, ADR 0014's `lms_` prefix "
        "marks only where the value came from, and no identity rule in this repository matches it "
        "— which is what `docs/tickets/e1/carried-from-e0.md` measured and what E1-01 exists to "
        "close.\n\n"
        "If this entry was added to make the enumeration green, that is the repair this test "
        "refuses: the column comes out of the view, in a `_v002.sql` under ADR 0041, rather than "
        "into this constant. If a read path genuinely needs to identify a person at the platform, "
        "it is a decision for the spec and for Todd rather than for a grant list."
    )


@pytest.mark.invariant
def test_a_granted_view_exposing_the_lms_join_key_fails_the_enumeration(db_session: Any) -> None:
    """The enumeration seen *finding* something, on the exact grant the carried entry names.

    `docs/MISTAKES.md` entry 35: a guard that enumerates and only ever reports
    absence cannot tell you which of its mechanisms it can still see. So the grant
    is stood up rather than reasoned about — a view returning `user.lms_user_id`,
    granted `SELECT` to the application role, which is two statements a later
    ticket writes to make one screen work.

    **Everything is planted inside `db_session`'s transaction and rolled back with
    it.** Postgres puts DDL *and* a `GRANT` inside the transaction, so `public` is
    unchanged at the end and no other connection ever sees either. The assertions
    run in the same transaction as the plant, which is what makes them mean
    anything: a mutation a fixture undoes before the assertion is a control that
    cannot fail (`docs/MISTAKES.md` entry 20).

    **Three assertions, in order, and the middle one is the control on the
    control.** The column has to exist — otherwise the plant is a view of
    something else. The enumeration's *candidate* set has to contain it —
    otherwise the failure below is the empty-expectation failure rather than this
    grant. And the guard's message has to name the *entry* — the view and the
    column together, as a whole word — because a red that does not name what
    leaked is repaired by whatever is cheapest, and on this file the cheapest
    repair is an entry in the sanctioned set. The bare column name would not do:
    the guard's message explains in prose what `lms_user_id` is, so a check for
    that word passes whatever the granted set contains.

    **That third assertion was measured guarding nothing, and the repair is in the
    guard rather than here.** The mutation battery changed the guard's message to
    print `len(surplus)` instead of the names and this control stayed green:
    pytest's assertion rewriting appends the repr of the compared lists to the
    exception, so the entry was in `str(failure.value)` no matter what the message
    said, and `mentions` was reading the rewriter's output rather than anything
    anybody wrote. The guard now compares a bool, so the explanation is
    `assert False` and the authored message is the whole of the text — which is
    what makes the check below load-bearing. `docs/MISTAKES.md` entry 3, found
    inside a control written to close entry 35.

    **The mutation it exists to survive**: narrowing the candidate sweep to a
    hand-kept list of views, which is the shape E1-01's scope forbids and which
    would leave a planted view invisible; and dropping either ACL from
    `columns_the_application_role_may_read`.
    **The near miss it tolerates**: the same view left ungranted, which is the
    other control below.
    """
    session = db_session
    columns = {name for name, _ in public_table_columns(session, USER_TABLE)}
    assert LMS_USER_KEY in columns, (
        f"`public.{USER_TABLE}` has no `{LMS_USER_KEY}` column; it has {sorted(columns)}. ADR 0001 "
        f"puts the LMS key and the platform reference on that table and ADR 0014 prefixes an "
        "LMS-owned column `lms_`, so if the key has been renamed this constant follows it — the "
        "control cannot plant the disclosure the carried entry measured without the column that "
        "carries it."
    )

    # One statement per line with its own suppression, the convention this file
    # already uses for interpolated DDL (`READ_IDENTITY` above, and the planted
    # objects in `test_identity_column_marker.py`). Every name interpolated is a
    # module constant declared beside `PLANTED_GRANTED_VIEW`; nothing reaches
    # these from outside the file, and the transaction is rolled back.
    planted = f'CREATE VIEW public.{PLANTED_GRANTED_VIEW} AS SELECT u.{LMS_USER_KEY} FROM public."{USER_TABLE}" u'  # noqa: S608
    session.execute(text(planted))
    session.execute(text(f'GRANT SELECT ON public.{PLANTED_GRANTED_VIEW} TO "{APPLICATION_ROLE}"'))

    candidates = columns_the_application_role_may_read(session)
    assert (PLANTED_GRANTED_VIEW, LMS_USER_KEY) in candidates, (
        f"`{APPLICATION_ROLE}` was granted `SELECT` on a view returning `{LMS_USER_KEY}` and the "
        f"candidate sweep does not report it. It reported {sorted(candidates)}. The sweep is "
        "blind — to `pg_class.relacl`, to `pg_attribute`, or to views in `public` — and the "
        "enumeration above is then an equality between a hand-written set and whatever a broken "
        "query returns."
    )

    with pytest.raises(AssertionError) as failure:
        test_the_columns_the_application_role_may_read_from_a_view_are_exactly_the_enumerated_set(
            session
        )

    # **The column's name alone would not do**, and that is `docs/MISTAKES.md`
    # entry 3 caught in the act: the guard's own failure message explains what
    # `lms_user_id` is, in prose, so a check for the bare word passes whatever the
    # granted set contains. What is asked for is the *entry* — the view and the
    # column together, as the surplus list spells it — which nothing but a real
    # finding can put in that message.
    #
    # **And the text read here is the authored message and nothing else**, which
    # is the second half of the same lesson: while the guard asserted on the lists
    # themselves, pytest's rewriter appended their repr and this check passed
    # against a message that had stopped naming anything. The guard asserts a bool
    # now for that reason, and the comment above `agrees` carries the measurement.
    reported = f"{PLANTED_GRANTED_VIEW}.{LMS_USER_KEY}"
    assert mentions(str(failure.value), reported), (
        f"The enumeration failed on the planted grant and its message does not name `{reported}`. "
        f"What it said: {failure.value}\n\n"
        "The message is the criterion rather than a courtesy: a reader who is told only that the "
        "granted set differs from the sanctioned one has two lists to diff, and the repair that "
        "presents itself for either is an entry in the sanctioned set. It is also possible this "
        "caught a *different* failure inside the guard — an empty candidate set, no views at all — "
        "in which case the planted grant was never enumerated and this control would otherwise "
        "have passed for a reason unrelated to what it asserts (`docs/MISTAKES.md` entry 3)."
    )


@pytest.mark.invariant
def test_a_column_grant_on_a_view_reaches_the_enumeration(db_session: Any) -> None:
    """The other ACL, stood up: a grant on one column, on a view granted to nobody.

    `columns_the_application_role_may_read` reads two catalogs, and until now only
    one of them had a subject. `pg_class.relacl` carries a grant on the whole
    view; `pg_attribute.attacl` carries a grant on a single column of it, appears
    in no `relacl` anywhere, and is invisible to `has_table_privilege` — measured
    on this stack during a security review of PR #40, which `COLUMN_GRANTEES`
    above records. Deleting that half of the union left every test green, because
    both plants beside this one use a relation grant. So this one does not.

    **Three assertions, and the middle one is the finding rather than bookkeeping.**
    The granted column must be enumerated. The view's *other* column must **not**
    be — that is what makes this a column grant rather than a table grant, and it
    is the reviewer's own measurement reproduced: `SELECT *` on such a view is
    refused while the granted column reads fine. And the guard must fail naming
    the entry, because a candidate the enumeration never compares is a candidate
    that changes nothing.

    **Why this matters beyond covering a branch.** A column grant is the quietest
    way to widen this surface: it leaves the view ungranted as far as every
    relation-level rule in this file can see, and ADR 0001 rejects column grants
    by name — which is exactly why somebody reaches for one when a screen needs a
    single value.

    Everything is planted inside `db_session`'s transaction and rolled back with
    it (`docs/MISTAKES.md` entry 20: the plant and the assertions are in one
    transaction).

    **The mutation it exists to survive**: deleting the `COLUMN_GRANTEES` half of
    the union in `columns_the_application_role_may_read`, or narrowing it to base
    tables.
    **The near miss it tolerates**: the ungranted column of the same view, which
    must stay out — asserted here rather than assumed.
    """
    session = db_session
    columns = [name for name, _ in public_table_columns(session, USER_TABLE)]
    assert LMS_USER_KEY in columns, (
        f"`public.{USER_TABLE}` has no `{LMS_USER_KEY}` column; it has {sorted(columns)}. The "
        "planted view below selects it beside a key, and the column grant is made on it."
    )

    # Two columns, so that the grant can be narrower than the view.
    planted = f'CREATE VIEW public.{PLANTED_COLUMN_GRANTED_VIEW} AS SELECT u.id, u.{LMS_USER_KEY} FROM public."{USER_TABLE}" u'  # noqa: S608
    session.execute(text(planted))
    session.execute(
        text(
            f"GRANT SELECT ({LMS_USER_KEY}) ON public.{PLANTED_COLUMN_GRANTED_VIEW} "
            f'TO "{APPLICATION_ROLE}"'
        )
    )

    candidates = columns_the_application_role_may_read(session)
    assert (PLANTED_COLUMN_GRANTED_VIEW, LMS_USER_KEY) in candidates, (
        f"`{APPLICATION_ROLE}` holds `SELECT` on the `{LMS_USER_KEY}` column of "
        f"`public.{PLANTED_COLUMN_GRANTED_VIEW}` and the candidate sweep does not report it; it "
        f"reported {sorted(candidates)}.\n\n"
        "The sweep is reading `pg_class.relacl` only. A column grant is recorded in "
        "`pg_attribute.attacl`, which no relation-level query and no `has_table_privilege` answer "
        "reads — so the enumeration would be blind to the one shape ADR 0001 rejects by name, "
        "while every other rule in this file goes on passing."
    )
    assert (PLANTED_COLUMN_GRANTED_VIEW, "id") not in candidates, (
        f"The sweep reports `id` as readable on `public.{PLANTED_COLUMN_GRANTED_VIEW}`, and the "
        f"grant was `SELECT ({LMS_USER_KEY})` on that column alone. Then it is expanding a column "
        "grant to the whole view, the assertion above is satisfied by the wrong mechanism, and the "
        "enumeration would report columns nobody may read — which fails in the direction that gets "
        "a guard widened until it stops discriminating."
    )

    with pytest.raises(AssertionError) as failure:
        test_the_columns_the_application_role_may_read_from_a_view_are_exactly_the_enumerated_set(
            session
        )

    reported = f"{PLANTED_COLUMN_GRANTED_VIEW}.{LMS_USER_KEY}"
    assert mentions(str(failure.value), reported), (
        f"The enumeration failed and its message does not name `{reported}`. What it said: "
        f"{failure.value}\n\nA candidate the comparison never mentions is a candidate that changes "
        "nothing: the sweep would be finding the column grant and the equality would be failing "
        "for some other reason. The comment in the sibling control above says why this reads the "
        "authored message and why the guard asserts a bool."
    )


@pytest.mark.invariant
def test_a_view_the_application_role_cannot_read_is_outside_the_enumeration(
    db_session: Any,
) -> None:
    """The allow side: a view is the enumeration's business only once it is granted.

    The same view as the control above, planted without the `GRANT`. A view
    `pulse_app` cannot read exposes nothing to any screen, whatever its column
    list says — that is what a grant model is *for* — so an enumeration that
    reported it would be red on every internal view anybody ever adds, and would
    be repaired by narrowing it back to the views somebody remembered.

    **The grant is then made, in the same transaction, and the same sweep is asked
    again.** Without that second half, the silence asserted first is equally the
    silence of a sweep that has gone blind (`docs/MISTAKES.md` entry 3) — the two
    halves together say that the *grant* is what moved the answer and not the
    view's existence.

    **A third view carries the grantee filter, and it is here because the pair
    above does not.** The mutation battery deleted
    `if row["grantee"] in APPLICATION_READERS` from the candidate sweep and every
    test stayed green: an ungranted view has a `NULL` `relacl`, `aclexplode`
    returns no row for it at all, and a filter over rows that do not exist is a
    filter nothing runs. So a view granted to `pulse_care` is planted beside it —
    a real ACL entry, a real grantee, and one this enumeration must not count.
    `pulse_care` is the honest choice rather than an invented role: it exists, it
    is a runtime role, and the reason it is excluded is the design (ADR 0001 gives
    it one door and no read paths) rather than an accident of who was named.

    **The mutation it exists to survive**: dropping the grantee filter from
    `columns_the_application_role_may_read`, so that every ACL entry on every view
    in `public` is enumerated whoever holds it.
    **The near miss it tolerates**: none; the three plants are the test.
    """
    session = db_session
    planted = f'CREATE VIEW public.{PLANTED_UNGRANTED_VIEW} AS SELECT u.{LMS_USER_KEY} FROM public."{USER_TABLE}" u'  # noqa: S608
    session.execute(text(planted))

    assert PLANTED_UNGRANTED_VIEW in read_views(session), (
        f"`{PLANTED_UNGRANTED_VIEW}` is not a view in `public` at all, so the absence asserted "
        "below would be a fact about a view that was never created rather than about a grant that "
        "was never made."
    )
    ungranted = columns_the_application_role_may_read(session)
    assert not [view for view, _ in ungranted if view == PLANTED_UNGRANTED_VIEW], (
        f"`{PLANTED_UNGRANTED_VIEW}` is enumerated as readable by `{APPLICATION_ROLE}` and no "
        f"grant on it was ever made. The sweep reported {sorted(ungranted)}. It is therefore "
        "reporting views rather than grants, and the equality above would go red on any view this "
        "project creates for its own use — after which the cheapest repair is a list of the views "
        "that count, which is what E1-01's scope forbids."
    )

    session.execute(
        text(f'GRANT SELECT ON public.{PLANTED_UNGRANTED_VIEW} TO "{APPLICATION_ROLE}"')
    )
    granted = columns_the_application_role_may_read(session)
    assert (PLANTED_UNGRANTED_VIEW, LMS_USER_KEY) in granted, (
        f"The same view, now granted `SELECT` to `{APPLICATION_ROLE}`, is still not enumerated; "
        f"the sweep reported {sorted(granted)}. Then the silence asserted above was the sweep "
        "failing to see a grant rather than the grant's absence, and this control establishes "
        "nothing about either."
    )

    # The third plant: a view with a real ACL entry naming somebody who is not an
    # application reader. Its own non-vacuity comes first — the ACL row has to
    # exist, or this is the ungranted case again under another name, which is
    # exactly how the grantee filter came to be uncovered.
    care_view = f'CREATE VIEW public.{PLANTED_CARE_GRANTED_VIEW} AS SELECT u.{LMS_USER_KEY} FROM public."{USER_TABLE}" u'  # noqa: S608
    session.execute(text(care_view))
    session.execute(text(f'GRANT SELECT ON public.{PLANTED_CARE_GRANTED_VIEW} TO "{CARE_ROLE}"'))

    acl = [
        dict(row)
        for row in session.execute(text(APPLICATION_READABLE_VIEW_COLUMNS)).mappings()
        if row["relation"] == PLANTED_CARE_GRANTED_VIEW
    ]
    assert any(row["grantee"] == CARE_ROLE for row in acl), (
        f"`public.{PLANTED_CARE_GRANTED_VIEW}` was granted `SELECT` to `{CARE_ROLE}` and the "
        f"relation-ACL query reports {acl} for it. With no row there, the grantee filter below has "
        "nothing to filter and its absence asserts nothing — which is the defect this plant was "
        "added for: an *ungranted* view carries a `NULL` `relacl`, `aclexplode` returns no row at "
        "all, and deleting the filter left the whole suite green."
    )
    reachable = columns_the_application_role_may_read(session)
    assert not [view for view, _ in reachable if view == PLANTED_CARE_GRANTED_VIEW], (
        f"`{PLANTED_CARE_GRANTED_VIEW}` is granted to `{CARE_ROLE}` and to nobody else, and the "
        f"candidate sweep counts it as readable by `{APPLICATION_ROLE}`; it reported "
        f"{sorted(reachable)}.\n\n"
        "The sweep is reporting every ACL entry rather than the entries that put a column within "
        "the application connection's reach. `APPLICATION_READERS` is the filter — the application "
        f"role and `PUBLIC`, which every role is a member of — and `{CARE_ROLE}` is neither: ADR "
        "0001 gives it one `SECURITY DEFINER` door and no read path, so a view it alone may read "
        "is outside this enumeration by design.\n\n"
        "With the filter gone, the sanctioned set would have to grow to cover grants made to other "
        "roles entirely, and the equality would stop saying anything about what an instructor's "
        "connection can put on a page."
    )
