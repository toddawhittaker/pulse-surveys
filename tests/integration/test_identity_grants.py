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

**The last section is E0-33's**, and it is a different question from every rule
above: not "is this rule stated" but "was anything *else* stated". Asserting a
refusal proves the refusal and proves nothing about what a later migration
granted beside it, and `alembic check` reads no ACL, no `pg_roles` row and no
`pg_proc` entry in either direction. Its sibling for generated columns, check
constraints and exclusion constraints is
`test_objects_the_drift_gate_cannot_compare.py`, and the view set is in
`test_identity_separated_views.py`.
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
# **The rules in this file are still spelled without them.** No `SECURITY DEFINER`
# function in `public` may be owned by a superuser; the definer's grants are
# exactly what its job needs; `pulse_app` may execute nothing. Those sweep over
# whatever is there, because E10 replaces this door and a rule carrying its name
# would retire with it. What is named below is only how a *test calls* the door,
# which is a different thing from what a rule is about.
RECORD_FUNCTION = "record_identity_reveal"
REVEAL_FUNCTION = "reveal_student_identity"
CARE_DOOR_HALVES = 2

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
    """
    chain: dict[str, Any] = {}
    identity = committed_rows.seed(IDENTITY_TABLE, chain)
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
    assert values, (
        f"The seeded `{IDENTITY_TABLE}` row carries no non-key string value: {dict(identity)}. "
        "There is then nothing for a reveal to return that could be recognised, and the test "
        "below would be asserting that a function returned something rather than that it returned "
        "the identity."
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

    **The mutation it exists to survive**: dropping
    `REVOKE ALL ON FUNCTION … FROM PUBLIC` from the migration, which leaves every
    other test in this file green.
    """
    functions = security_definer_functions(db_session, APPLICATION_ROLE)
    assert functions, (
        "This project defines no `SECURITY DEFINER` function in `public`, so this test swept "
        "nothing. E0-10 ships the Care door and E0-26 item 1 made it two functions; "
        "`test_the_care_roles_grants_are_enough_to_complete_a_reveal` diagnoses "
        "its absence."
    )

    reachable = [row["signature"] for row in functions if row["executable"]]
    assert not reachable, (
        f"`{APPLICATION_ROLE}` may execute {reachable}. A `SECURITY DEFINER` function runs with "
        "its owner's privileges, so one that reads `user_identity` hands identity to whoever may "
        "call it — and Postgres grants `EXECUTE` to `PUBLIC` by default, which means this is the "
        "state a migration reaches by *not* saying anything. E0-10 gives the `EXECUTE` to "
        "`pulse_care` alone."
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
    the asymmetry rather than an exemption. `pulse_care` holds `EXECUTE` on the
    reveal *by design* — §4 and §6.2 require that door to be open — so a rule that
    reported it would fail against the correct schema. It is asserted separately
    and in both directions instead: `test_the_application_role_may_not_execute_the_
    reveal_function` says `pulse_app` may call nothing, and
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
RUNTIME_BASE_TABLE_PRIVILEGES = frozenset(
    {
        (CARE_ROLE, "role_assignment", "SELECT"),
        (APPLICATION_ROLE, "classification", "SELECT"),
        (APPLICATION_ROLE, "classification", "INSERT"),
        (APPLICATION_ROLE, "lti_platform", "SELECT"),
        (APPLICATION_ROLE, "lti_deployment", "SELECT"),
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
    the one function whose job is to return a name. The allowed grantee on a
    definer function is `pulse_care` and nothing else, which is E0-10's own
    sentence: `pulse_care` "gets `EXECUTE` on a **single** `SECURITY DEFINER`
    function".

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
    expected = {APPLICATION_ROLE, CARE_ROLE, definer}
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
        if row["grantee"] != CARE_ROLE and row["grantee"] != row["owner"]
    ]
    unexpected = sorted(beyond_on_relations + beyond_on_columns + beyond_on_functions)
    assert not unexpected, (
        f"{unexpected}. On a relation, the roles this scheme names are {sorted(expected)} — the "
        "two connection roles of ADR 0001 and the reveal function's own owner from ADR 0043 — plus "
        "whoever owns it, which is the migration identity ADR 0009 sanctions. On a `SECURITY "
        f"DEFINER` function it is `{CARE_ROLE}` and the owner, and nothing else: E0-10 gives the "
        "Care role `EXECUTE` on the door and E0-26 item 1 made that door two halves, and "
        "`pulse_app` is refused both by name in an "
        "`invariant`-marked test above. Anything else holds a privilege that no ticket in this "
        "epic granted and that nothing in this repository will ever revoke.\n\n"
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
    blind to a column grant.** The expected set at column level is *empty*: every
    grant this scheme writes is table-level — ADR 0043's enumeration and E0-13's
    `SELECT, INSERT` on `classification` alike — so a runtime role named in any
    column ACL on a base table is a widening by definition. Without this,
    `GRANT UPDATE (verdict) ON public.classification TO pulse_app` would leave the
    append-only property broken with this test green, which is the same shape as
    the identity finding one table over and would have been left open by fixing
    only that one.

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
    beyond_on_tables = [
        f"{role} holds {privilege} on public.{relation}"
        for role, relation, privilege in held - RUNTIME_BASE_TABLE_PRIVILEGES
    ]
    beyond_on_columns = [
        f"{row['grantee']} holds {row['privilege']} on public.{row['relation']}"
        f".{row['column_name']}"
        for row in on_columns
        if row["grantee"] in RUNTIME_ROLES and row["relation"] in tables
    ]
    beyond = sorted(beyond_on_tables + beyond_on_columns)
    missing = sorted(
        f"{role} should hold {privilege} on public.{relation}"
        for role, relation, privilege in RUNTIME_BASE_TABLE_PRIVILEGES - held
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
        "empty: every grant this scheme writes is table-level, so a runtime role named in any "
        "column ACL is a widening by definition, and on an append-only table it is the whole of "
        "how append-only stops being true.\n\n"
        "The second list means this scheme has lost a grant it needs: without `SELECT` on "
        "`role_assignment` the Care path cannot resolve the actor whose assignment it is about, "
        "and without `INSERT` on `classification` the moderation classifier cannot record a "
        "verdict. Each entry in `RUNTIME_BASE_TABLE_PRIVILEGES` carries the sentence it comes "
        "from.\n\n"
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
