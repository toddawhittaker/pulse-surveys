"""The grants that make identity unreachable, and the one door left open — ticket E0-10.

SPEC §8 requires that instructor and leadership read paths "structurally cannot
join to `user` identity columns — enforced in the database, not just the
application", and that "only the Care role's queue path can reach identity, and
only via the audited reveal action".
[ADR 0001](../../docs/adr/0001-identity-separation-by-database-role.md) settles
the mechanism: three roles, no grant of any kind on `user_identity` for either
runtime role, and one `SECURITY DEFINER` function that returns identity and
writes the audit row in the same transaction.

**A fourth role exists and is not a runtime one**: the function's owner. A
`SECURITY DEFINER` function executes as whoever owns it, so the owner *is* the
privilege the door opens, and owning it with the identity that runs migrations
makes the door a superuser one — measured on this stack, such a function read
`pg_catalog.pg_authid` for a `pulse_care` session that was refused that table
directly one statement later. The two tests at the end of the Care section below
hold the repair: no `SECURITY DEFINER` function in `public` is owned by a
superuser, and the owner's grants are exactly the three its job needs. Neither
names the role or the function, because E10 replaces the function and a rule
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
`tests/conftest.py` provisions the suite's application role as **`pulse_app`
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
so `test_the_reveal_function_refuses_an_actor_with_no_live_care_assignment` calls
the function over SQL with no service anywhere in the picture — that is the half
that has to hold when the service is bypassed. The service's own half is a
source-level assertion in `tests/unit/test_care_session_is_bound_to_the_care_
service.py`, because its runtime interface is not named yet.

**What this module still does not cover.** The two-hat criterion — a reporting
path cannot obtain a `pulse_care` session even when the acting person also holds
a `CARE` assignment — needs the session factory's symbol, which E0-10 does not
spell. The structural half of it is in the unit test named above; the runtime
half waits on the interface.
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

# What the reveal function's owner may do, and the whole of it. **Derived from
# three sentences of E0-10 rather than copied from the migration**, so that this
# constant can be checked against the ticket instead of against the SQL it is
# supposed to police (`docs/MISTAKES.md` entry 19):
#
#   - it "returns identity"                              → user_identity: SELECT
#   - it "verifies a live `CARE` assignment itself"       → role_assignment: SELECT
#   - it "writes the audit row in the same transaction"   → audit_log: INSERT
#
# The second is the one that surprises people and is not padding: it is the half
# of the two-condition design that has to hold when the service is bypassed, so
# the function reads the supervision table on its own account. The audit table's
# name is SPEC §8's.
REVEAL_DEFINER_PRIVILEGES = frozenset(
    {
        ("user_identity", "SELECT"),
        ("role_assignment", "SELECT"),
        ("audit_log", "INSERT"),
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

# How an argument of the reveal function is filled, matched against a fragment of
# its name. **This file's choice**, and the one place a name the ticket does not
# spell is guessed at — deliberately narrow, and a parameter none of these
# reaches stops the test with a message saying so rather than being filled with
# something plausible. Order matters: `care_person_id` is an actor, not a person
# picked at random, and `student_user_id` is the subject.
REVEAL_ARGUMENT_ROLES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("case",), "case"),
    (("note", "reason", "justification", "disposition"), "note"),
    (("actor", "care", "staff", "revealer", "requester", "requested_by"), "actor"),
    (("user", "subject", "student", "sub", "identity"), "subject"),
    (("person",), "actor"),
)

# Where a `user` row keeps the LMS subject, if the reveal takes one instead of a
# key. A copy of the candidate list in `test_identity_schema.py`; SPEC §4 says
# responses are "keyed to the LMS user ID (`sub` from the launch)".
LMS_USER_ID_COLUMNS = ("lms_user_id", "lms_sub", "lms_subject", "lms_id", "sub")

REVEAL_NOTE = "E0-10 proof of mechanism"


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


def row_counts(session: Any) -> dict[str, int]:
    """How many rows every table in `public` holds, right now, in this transaction."""
    names = [row[0] for row in session.execute(text(PUBLIC_TABLES))]
    return {
        name: session.execute(text(f'SELECT count(*) FROM public."{name}"')).scalar_one()  # noqa: S608
        for name in names
    }


def security_definer_functions(session: Any, role: str) -> list[Any]:
    """Every `SECURITY DEFINER` function this project defines, and whether `role` may call it."""
    require_role(session, role)
    return session.execute(text(SECURITY_DEFINER_FUNCTIONS), {"role": role}).mappings().all()


def the_reveal_function(session: Any) -> Any:
    """The one `SECURITY DEFINER` function `pulse_care` may execute.

    Fails, rather than choosing, when there is more than one: E0-10 says
    "`pulse_care` gets `EXECUTE` on a **single** `SECURITY DEFINER` function", so
    two is the criterion reporting itself and not something for this file to
    disambiguate.
    """
    executable = [
        row for row in security_definer_functions(session, CARE_ROLE) if row["executable"]
    ]
    assert executable, (
        "No `SECURITY DEFINER` function in `public` is executable by `pulse_care`. E0-10: 'The "
        "Care path must remain open, and this ticket proves it… `pulse_care` gets `EXECUTE` on a "
        "single `SECURITY DEFINER` function that returns identity and writes the audit row in the "
        "same transaction, so a name cannot be obtained without leaving a record.' Care "
        "re-identification is the one legitimate route to identity (§4, §6.2) and is deliberately "
        "not blocked; this test is what stops a later change closing it silently."
    )
    assert len(executable) == 1, (
        f"`pulse_care` may execute {len(executable)} `SECURITY DEFINER` functions: "
        f"{[row['signature'] for row in executable]}. The ticket says a single one, and the "
        "reason is the audit: every additional door is a way to obtain a name without leaving a "
        "record, and the whole guarantee is that there is exactly one way in."
    )
    return executable[0]


def reveal_arguments(function: Any, context: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Bind the reveal function's parameters from what this test has seeded.

    Returns the argument list to interpolate and the parameters to bind. Every
    placeholder is cast to the parameter's declared type, which does two things:
    a `None` for the case id arrives as a typed NULL rather than as "could not
    determine data type", and a value bound as text reaches a `uuid` parameter as
    a uuid.

    **What it refuses to do is guess.** A parameter no fragment in
    `REVEAL_ARGUMENT_ROLES` reaches stops the test with a message naming it,
    because E0-10 names neither the function nor its signature, and filling an
    unknown parameter with something plausible would make the test pass against a
    design the ticket never asked for.
    """
    names = list(function["argument_names"])
    types = list(function["argument_types"])

    if not names and len(types) == 1:
        # One unnamed argument: the subject, by elimination. The same
        # accommodation `SectionCodeService.call` makes in tests/conftest.py, for
        # the same reason — a single parameter's *name* is not something the
        # ticket decides.
        names = ["subject"]
    if len(names) < len(types):
        pytest.fail(
            f"`{function['signature']}` takes {len(types)} argument(s) and names {names}. This "
            "test binds arguments by name, and cannot tell which value belongs where without "
            "them. E0-10 does not spell the function's signature at all; say what it is in the "
            "pull request and `REVEAL_ARGUMENT_ROLES` in this file is the one place that changes."
        )

    rendered: list[str] = []
    parameters: dict[str, Any] = {}
    for index, (name, declared) in enumerate(zip(names, types, strict=False)):
        role = next(
            (
                role
                for fragments, role in REVEAL_ARGUMENT_ROLES
                if any(fragment in (name or "").lower() for fragment in fragments)
            ),
            None,
        )
        if role is None:
            pytest.fail(
                f"`{function['signature']}` takes a parameter `{name}` of type {declared}, and "
                "this test has nothing to fill it from. It can supply the user whose identity is "
                "being revealed, the person acting (who holds a live `CARE` assignment), a null "
                "case id — E0-10 ships the reveal before there is any case model — and a short "
                "note. A parameter outside that set is an interface question for the ticket: say "
                "what it is for in the pull request and add it to `REVEAL_ARGUMENT_ROLES` here."
            )
        value = reveal_argument_value(role, declared, context, function["signature"], name)
        key = f"arg{index}"
        parameters[key] = value
        rendered.append(f"CAST(:{key} AS {declared})")

    return ", ".join(rendered), parameters


def reveal_argument_value(
    role: str, declared: str, context: dict[str, Any], signature: str, name: str | None
) -> Any:
    """One argument's value, chosen by what the parameter is for and what it is typed."""
    if role == "case":
        return None
    if role == "note":
        return REVEAL_NOTE
    if role == "actor":
        if "uuid" in declared:
            return context["actor_person_id"]
    elif role == "subject":
        if "uuid" in declared:
            return context["user_id"]
        if context.get("lms_user_id") is not None:
            return context["lms_user_id"]
    pytest.fail(
        f"`{signature}` takes `{name}` as {declared}, and this test reads it as the "
        f"{role} but has no value of that type for it. It holds the seeded user's key and LMS "
        "subject and the acting person's key. E0-10 spells no signature for the reveal function, "
        "so this is an interface question for the ticket rather than something to coerce here."
    )


def attempt_the_reveal(
    session: Any, function: Any, context: dict[str, Any]
) -> tuple[list[Any], Any]:
    """Call the reveal as `pulse_care`; answer its rows, or the error it raised.

    The call runs inside a savepoint that is *released* on success, so the rows
    the function wrote stay in the enclosing transaction for a caller that wants
    to count them, and a refusal leaves the transaction usable — which is what
    lets `RESET ROLE` run and the failure be reported as itself rather than as a
    `PendingRollbackError` from the context manager unwinding.

    Answering rather than asserting, because both outcomes are a criterion: the
    Care path must work for an actor holding a live `CARE` assignment, and the
    function must refuse one who does not. A helper that asserted either would
    make the other test read backwards.
    """
    arguments, parameters = reveal_arguments(function, context)
    name = function["name"]
    statement = text(f'SELECT * FROM public."{name}"({arguments})')  # noqa: S608

    with acting_as(session, CARE_ROLE):
        savepoint = session.begin_nested()
        try:
            rows = session.execute(statement, parameters).mappings().all()
        except DatabaseError as failure:
            savepoint.rollback()
            return [], failure
        savepoint.commit()

    return rows, None


CARE_PATH_IS_OPEN_DELIBERATELY = (
    "E0-10 keeps the Care path open on purpose: 'Care re-identification is the one legitimate "
    "route to identity (§4, §6.2), and it is deliberately not blocked.' A reveal the Care role "
    "cannot complete is this ticket's other failure mode, and the one every denial test in this "
    "file is silent about."
)


def call_the_reveal(
    session: Any, function: Any, context: dict[str, Any], *, refusal_means: str = ""
) -> list[Any]:
    """The reveal, where a refusal is a failed test rather than an answer."""
    rows, failure = attempt_the_reveal(session, function, context)
    assert failure is None, (
        f"`{function['signature']}` refused a call by `{CARE_ROLE}`: {failure}. "
        f"{refusal_means or CARE_PATH_IS_OPEN_DELIBERATELY} The arguments supplied were "
        f"{context}; if this test read the parameters wrongly, the signature is the interface "
        "E0-10 does not spell and `REVEAL_ARGUMENT_ROLES` is where its reading of it lives."
    )
    return rows


def seed_identity(seed_rows: Any) -> dict[str, Any]:
    """One `user` with one `user_identity` row, and what a caller needs to name them."""
    chain: dict[str, Any] = {}
    identity = seed_rows(IDENTITY_TABLE, chain)
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
    lms_key = next((key for key in LMS_USER_ID_COLUMNS if key in user), None)
    return {
        "user_id": user[user_key],
        "lms_user_id": user[lms_key] if lms_key else None,
        "identity_values": values,
    }


# ---------------------------------------------------------------------------
# The roles themselves: the two properties that would void every grant below.
# ---------------------------------------------------------------------------


def test_the_suites_application_connection_authenticates_as_the_granted_role(
    application_engine: Any,
) -> None:
    """The role the suite connects as and the role this ticket grants to are one role.

    Two constants in two files decide this — `TEST_APP_USER` in
    `tests/conftest.py` and `APPLICATION_ROLE` here — and nothing else in the
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
        "migration establishes. Change `TEST_APP_USER` in `tests/conftest.py`, or, if the "
        "deployment's application role is genuinely spelled some other way, change it here and in "
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
        "nothing. E0-10 ships exactly one, for the Care reveal; "
        "`test_the_care_role_obtains_identity_through_the_one_function_it_may_execute` diagnoses "
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


def test_neither_runtime_role_holds_any_privilege_on_user_identity(db_session: Any) -> None:
    """The rule as *stated*, beside the tests that provoke it.

    Where two mechanisms could refuse the same statement, a behavioural test
    cannot say which one did — `docs/MISTAKES.md` entry 3's second rule — so the
    catalog is asked directly: no privilege of any kind, for either runtime role,
    including the ones a `SELECT` test would never notice. `UPDATE` reads nothing
    and lets a name be overwritten; `REFERENCES` lets a foreign key probe for a
    value's existence.

    The control is the same function asked about a table the role *may* read, so
    that "no privilege anywhere" cannot be the answer `has_table_privilege` gives
    to everything.
    """
    views = read_views(db_session)
    assert views, "There is no view in `public`, so the control below has nothing to check."

    held: dict[str, list[str]] = {}
    controls: dict[str, list[str]] = {}
    for role in RUNTIME_ROLES:
        require_role(db_session, role)
        held[role] = [
            privilege
            for privilege in TABLE_PRIVILEGES
            if db_session.execute(
                text("SELECT has_table_privilege(:role, :table, :privilege)"),
                {"role": role, "table": f"public.{IDENTITY_TABLE}", "privilege": privilege},
            ).scalar_one()
        ]
        controls[role] = [
            view
            for view in views
            if db_session.execute(
                text("SELECT has_table_privilege(:role, :table, 'SELECT')"),
                {"role": role, "table": f"public.{view}"},
            ).scalar_one()
        ]

    assert controls[APPLICATION_ROLE], (
        f"`has_table_privilege` reports that `{APPLICATION_ROLE}` may read none of {views}. It "
        "then reports nothing for any table, and the assertion below is true of a database with "
        "no grants at all rather than of this ticket's grant model."
    )
    granted = {role: privileges for role, privileges in held.items() if privileges}
    assert not granted, (
        f"The runtime roles hold privileges on `{IDENTITY_TABLE}`: {granted}. E0-10 gives "
        "`pulse_app` 'no grant of any kind' on it, and `pulse_care` no `SELECT` either — Care's "
        "access is the audited function and nothing else, so that a name cannot be obtained "
        "without leaving a record."
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
        "`test_the_care_role_obtains_identity_through_the_one_function_it_may_execute` is the "
        "other half: the door stays open, through the function."
    )
    assert sqlstate(failure) == INSUFFICIENT_PRIVILEGE, (
        f"The read failed with SQLSTATE {sqlstate(failure)} rather than {INSUFFICIENT_PRIVILEGE}: "
        f"{failure}. A missing table would satisfy 'it failed' and would mean something else "
        "entirely."
    )


def test_the_care_role_obtains_identity_through_the_one_function_it_may_execute(
    db_session: Any, seed_rows: Any, supervision_graph: Any
) -> None:
    """Criterion: "a `pulse_care` connection **can** still obtain identity".

    The Care path is a requirement and not an oversight (§4, §6.2: "traceability
    exists for safety"), and this test is what stops a later change closing it
    while every denial test above stays green. A wall where the ticket asks for a
    door fails nothing else in this file.

    The returned row is compared against the identity that was seeded, rather
    than merely being non-empty: a function that returns a row of nulls, or the
    user's key back, would satisfy "it returned something" and reveal nobody.
    """
    subject = seed_identity(seed_rows)
    hats = supervision_graph.care_and_instructor_person()
    function = the_reveal_function(db_session)
    rows = call_the_reveal(
        db_session,
        function,
        {
            "user_id": subject["user_id"],
            "lms_user_id": subject["lms_user_id"],
            "actor_person_id": hats["person"],
        },
    )

    returned = {str(value) for row in rows for value in row.values() if value is not None}
    assert returned & subject["identity_values"], (
        f"`{function['signature']}` returned {rows} for the seeded user, which carries "
        f"{sorted(subject['identity_values'])}. E0-10 ships this function as the proof that Care "
        "re-identification still works — 'E10 replaces the stub with the real audited reveal', so "
        "what E10 inherits has to be a door rather than a wall. A reveal that returns no identity "
        "is a wall with a handle painted on it."
    )


def test_the_reveal_writes_its_audit_row_in_the_callers_own_transaction(
    db_session: Any, seed_rows: Any, supervision_graph: Any
) -> None:
    """The function writes the record itself, on the caller's transaction — no more than that.

    Two things are asserted, and both are about *where* the write happens:

      - calling the function **adds a row somewhere** while the caller has the
        identity in hand. An implementation that returns identity and leaves the
        logging to its caller adds nothing here, and that is the one this kills;
      - rolling the transaction back **removes it again**, which is what says the
        write was made on the caller's transaction rather than on a second
        connection of the function's own. `plpgsql` has no autonomous transaction,
        so today there is nowhere else for it to have gone.

    **What this test does not prove, stated because its previous name claimed it.**
    It was called `test_a_rollback_discards_the_revealed_identity_and_its_audit_
    row_together`, after E0-10's criterion "rolling back the transaction discards
    both the read and the audit row, so the two cannot come apart". The assertions
    below are correct and the conclusion drawn from them was not. A rollback
    discards both *inside the database*; Postgres has already streamed the result
    rows to the client by the time the caller decides what to do with the
    transaction, so

        BEGIN;
        SELECT * FROM public.reveal_student_identity(<a real CARE person>, <a user>, NULL);
        ROLLBACK;

    returns the real name and email address and leaves `audit_log` at zero rows.
    That was reproduced twice on the pinned image during E0-10's review, each time
    with the controls that make it a finding rather than a coincidence: a non-CARE
    actor is still refused, and the identical call without the `ROLLBACK` does
    write the row, so the rollback alone is the difference. **The read and the
    record can come apart, and the party who can separate them is the one holding
    the Care credential.** Nothing in this file closes that, and no reader should
    leave this test believing otherwise.

    Closing it is **`docs/tickets/e0/E0-26-review-debt-from-e0-10.md` item 1**,
    which is done when a caller that rolls back keeps no name it is not recorded
    as having taken, and which needs the audit row written over a **second
    connection** that commits independently — `dblink` or a loopback
    `postgres_fdw`, each of which puts a credential inside a `SECURITY DEFINER`
    function and wants its own ADR. E0-26 must land before E10 builds the queue
    that calls this door.

    **So the second assertion below is asserting today's mechanism, and E0-26 will
    invert it.** When the write moves to a second connection the row will survive
    the rollback deliberately, and that is the fix rather than a regression: this
    test is then the one to rewrite, against E0-26's own requirement that the
    surviving row is read back from a connection other than the one that rolled
    back. Until then it holds the property the current design does have — the
    record is not something a caller adds afterwards, and it is not written by a
    path that could be skipped.

    **The audit table is not named**, because E0-10 does not name it and SPEC §8's
    `audit_log` is a list of tables rather than a decision about this one. What is
    asserted is that *some* table gained a row and lost it again, which is the
    property; which table it was is in the failure message.
    """
    subject = seed_identity(seed_rows)
    hats = supervision_graph.care_and_instructor_person()
    function = the_reveal_function(db_session)
    context = {
        "user_id": subject["user_id"],
        "lms_user_id": subject["lms_user_id"],
        "actor_person_id": hats["person"],
    }

    before = row_counts(db_session)
    savepoint = db_session.begin_nested()
    revealed = call_the_reveal(db_session, function, context)
    during = row_counts(db_session)
    savepoint.rollback()
    after = row_counts(db_session)

    assert revealed, (
        f"`{function['signature']}` returned no row, so nothing was revealed and the audit "
        "assertion below would be about a call that did nothing. "
        "`test_the_care_role_obtains_identity_through_the_one_function_it_may_execute` diagnoses "
        "that."
    )

    written = {name: during[name] - before[name] for name in before if during[name] > before[name]}
    assert written, (
        f"Calling `{function['signature']}` returned identity and wrote no row to any table: the "
        f"counts across {len(before)} tables are unchanged. §4 requires that 'every identity "
        "access is automatically audit-logged with actor, timestamp, and case', and E0-10 puts "
        "the write inside the function rather than beside it. An audit the caller is trusted to "
        "write afterwards is the design ADR 0001 rejected — it is a step a later code path can "
        "skip — and it passes every other test in this file. (What the write being inside the "
        "function does *not* buy is a record the caller cannot discard: see this test's "
        "docstring, and E0-26 item 1.)"
    )

    surviving = {name: after[name] - before[name] for name in before if after[name] != before[name]}
    assert not surviving, (
        f"After rolling the transaction back, {surviving} still differs from the counts before "
        "the reveal. So the audit row was not written on the transaction the caller controls, and "
        "this assertion — which is a description of today's mechanism rather than a guarantee — "
        "no longer holds.\n\n"
        "**Read E0-26 item 1 before treating this as a regression.** That ticket moves the audit "
        "write onto a second connection that commits independently, precisely so that the row "
        "survives a caller's `ROLLBACK`, because Postgres has already streamed the identity to "
        "that caller by then and the record must not be theirs to discard. If that is what has "
        "just landed, this test is the one to rewrite, against E0-26's own requirement that the "
        "surviving row is read back from a connection other than the one that rolled back — and "
        "the assertion above, that the row is written by the function rather than by its caller, "
        "is the half to keep."
    )


def test_the_reveal_function_refuses_an_actor_with_no_live_care_assignment(
    db_session: Any, seed_rows: Any, supervision_graph: Any
) -> None:
    """Criterion: the function refuses a non-Care actor **on its own**, with no service involved.

    E0-10 settles the design that an earlier version of the ticket left
    contradictory: the check lives in *both* places. `services/safety.py` verifies
    before calling, and the function takes the acting person and verifies a live
    `CARE` assignment itself. This is the second half, and the reason it has its
    own test is entry 3's second rule — where both can refuse, a behavioural test
    through the service cannot say which one did. Nothing here goes near the
    service: the call is SQL, on a `pulse_care` connection, exactly as a caller
    who reached the function by some other route would make it.

    **The control is the same call with a Care actor**, which is what tells "this
    actor is refused" apart from "this function refuses everyone", from a wrong
    argument binding, and from a database that has stopped working. Both actors
    are real people in the same graph: one holds a `CARE` assignment and a
    teaching assignment (§2.1's two-hat case), the other holds only a lead-faculty
    assignment.

    **What counts as refusing is left open**, because the ticket's words are "gets
    nothing": raising and returning no identity both pass. The assertion is that
    no identity comes back, and it is not the weak "a name is absent from the
    result" shape only because the control above obtained that same identity
    through that same call seconds earlier.

    "Live" is read as "exists" here, because E0-09's `role_assignment` has no
    end-dating — an assignment that has been revoked is a deleted row today. When
    E10 or E9 adds validity dates, an expired assignment becomes a second case
    worth its own test, and this one keeps its meaning.
    """
    subject = seed_identity(seed_rows)
    hats = supervision_graph.care_and_instructor_person()
    function = the_reveal_function(db_session)

    without_care = hats["lead"][supervision_graph.person_column]
    assert without_care != hats["person"], (
        "The fixture handed back the same person for the Care actor and the lead-faculty actor, "
        "so the two calls below would be the same call and the refusal would prove nothing. "
        "`SupervisionGraph.care_and_instructor_person` builds the lead with its own person."
    )

    allowed = call_the_reveal(
        db_session,
        function,
        {
            "user_id": subject["user_id"],
            "lms_user_id": subject["lms_user_id"],
            "actor_person_id": hats["person"],
        },
        refusal_means=(
            "This is the control for the refusal below rather than the assertion: the actor here "
            "holds a live `CARE` assignment, so the reveal has to succeed before a refusal for an "
            "actor without one says anything about the assignment. "
            "`test_the_care_role_obtains_identity_through_the_one_function_it_may_execute` is "
            "where a Care actor being refused is diagnosed."
        ),
    )
    assert (
        allowed
    ), "The control call returned no row, so there is nothing to contrast a refusal with."

    rows, failure = attempt_the_reveal(
        db_session,
        function,
        {
            "user_id": subject["user_id"],
            "lms_user_id": subject["lms_user_id"],
            "actor_person_id": without_care,
        },
    )

    leaked = {str(value) for row in rows for value in row.values() if value is not None}
    assert failure is not None or not (leaked & subject["identity_values"]), (
        f"`{function['signature']}` returned {rows} for an actor who holds a lead-faculty "
        f"assignment and no `CARE` assignment — the identity {sorted(subject['identity_values'])} "
        "that the same call returned a moment ago for an actor who does hold one. The function is "
        "`SECURITY DEFINER`, so it reads `user_identity` with its owner's privileges no matter who "
        "calls it: the acting person's assignment is the only thing between a `pulse_care` "
        "connection and any student's name. E0-10: the function 'takes the acting person as an "
        "argument and verifies a live `CARE` assignment itself… a caller reaching the function by "
        "any other route still gets nothing'.\n\n"
        "**Raising or returning nothing are both accepted here**, because the ticket says "
        "'gets nothing' and does not choose between them — but they are not equally good, and the "
        "pull request should say which was chosen. A raise is auditable and tells the caller it "
        "was refused; an empty result is indistinguishable from a student who does not exist, "
        "which is a difference §6.2's queue will care about at E10."
    )


def public_table_columns(session: Any, table: str) -> list[tuple[str, str]]:
    """One table's columns and their types, as the table itself declares them."""
    return list(session.execute(text(TABLE_COLUMNS), {"table": table}).tuples())


def test_a_shadowed_table_does_not_change_what_the_reveal_function_returns(
    db_session: Any, seed_rows: Any, supervision_graph: Any
) -> None:
    """The E0-09 hijack, aimed at the one piece of SQL in this ticket that binds late.

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

    **What is shadowed is discovered from the function's own body**, so the test
    aims at the tables it actually reads rather than at a guess. The shadow copies
    the real column list out of the catalog rather than using `CREATE TABLE …
    (LIKE …)`: `LIKE` needs `SELECT` on the source, which `pulse_care` does not
    have on `user_identity` — and a shadow missing a column would make the
    *vulnerable* function fail with "column does not exist", refusing the call and
    turning this test green against the defect (`docs/MISTAKES.md` entry 3).
    """
    subject = seed_identity(seed_rows)
    hats = supervision_graph.care_and_instructor_person()
    function = the_reveal_function(db_session)
    context = {
        "user_id": subject["user_id"],
        "lms_user_id": subject["lms_user_id"],
        "actor_person_id": hats["person"],
    }

    baseline = call_the_reveal(db_session, function, context)
    revealed = {str(value) for row in baseline for value in row.values() if value is not None}
    assert revealed & subject["identity_values"], (
        "The reveal did not return the seeded identity before any shadow existed, so the "
        "comparison after one is created would be between two wrong answers. "
        "`test_the_care_role_obtains_identity_through_the_one_function_it_may_execute` diagnoses "
        "that."
    )

    body = db_session.execute(
        text(FUNCTION_BODY), {"signature": function["signature"]}
    ).scalar_one()
    tables = [row[0] for row in db_session.execute(text(PUBLIC_TABLES))]
    named = [table for table in tables if re.search(rf"\b{re.escape(table)}\b", body or "")]
    assert named, (
        f"`{function['signature']}` names none of the {len(tables)} tables in `public` anywhere in "
        "its body, so there is nothing to shadow and this test would report success having "
        "attempted nothing. A reveal that reads no table cannot be returning identity from one."
    )

    with acting_as(db_session, CARE_ROLE):
        for table in named:
            columns = ", ".join(
                f'"{name}" {declared}' for name, declared in public_table_columns(db_session, table)
            )
            assert columns, (
                f"`public.{table}` reports no columns, so the shadow would be an empty-shaped "
                "table and a vulnerable function would fail on the column list rather than read "
                "the shadow."
            )
            refusal = refused(db_session, f'CREATE TEMPORARY TABLE "{table}" ({columns})')
            assert refusal is None, (
                f"`{CARE_ROLE}` could not create a temporary table called `{table}`: {refusal}. "
                "The `TEMPORARY` privilege is granted to `PUBLIC` by default, which is what makes "
                "this attack available to any authenticated role — so if this deployment revokes "
                "it deliberately, that is a second control worth saying out loud in the pull "
                "request, and this test then has to stand the shadow up as the bootstrap identity "
                "the way E0-09's did, with the weaker claim stated."
            )

    for table in named:
        bare, qualified = db_session.execute(
            RESOLVE_BOTH, {"bare": f'"{table}"', "qualified": f'public."{table}"'}
        ).one()
        assert bare is not None and qualified is not None and bare != qualified, (
            f'After `pulse_care` created a temporary table called "{table}", the bare name '
            f"resolves to {bare} and `public.{table}` to {qualified}. They have to differ, and "
            "neither may be null: if the bare name has not moved, the shadow is not on this "
            "session and the call below is the ordinary call the baseline already made."
        )

    shadowed = call_the_reveal(
        db_session,
        function,
        context,
        refusal_means=(
            f"The shadow tables {named} are the only thing that changed between this call and the "
            "baseline one, which succeeded. So the function resolved at least one relation name "
            "into `pg_temp` — the assignment check finding an empty `role_assignment` and refusing "
            "a Care actor is the likeliest shape. That is the hijack, and it is a refusal here "
            "rather than a wrong answer only by luck."
        ),
    )
    after = {str(value) for row in shadowed for value in row.values() if value is not None}
    assert after & subject["identity_values"], (
        f"With an empty `pg_temp` copy of {named} in the session, the reveal returned {shadowed} "
        f"instead of the identity it returned a moment ago ({sorted(subject['identity_values'])}). "
        "The function is reading tables the caller created: Postgres searches the temporary schema "
        "first for relation names, and `pulse_care` needs only the `TEMPORARY` privilege — granted "
        "to `PUBLIC` by default — to put one there. ADR 0027's fix is both halves, and this "
        "function needs both more than the trigger did, because it runs as its owner: "
        "schema-qualify every relation it names, and set "
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
        "nothing and would report success. E0-10 ships exactly one, for the Care reveal; "
        "`test_the_care_role_obtains_identity_through_the_one_function_it_may_execute` diagnoses "
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
    """Exactly three, because a fourth is what there is to catch.

    The owner exists to be small. Once it is not a superuser
    (`test_no_security_definer_function_is_owned_by_a_superuser`), what the door
    opens is precisely the set of grants that role holds — so the interesting
    assertion is not "it can do its job" but "it can do nothing else". **Exactly,
    not at least**: a `UPDATE` on `user_identity` added to make some later
    migration convenient is invisible to every other gate in this build, because
    `alembic check` reads no grants at all and no test but this one enumerates
    them.

    The expected set is derived from three sentences of the ticket rather than
    from the migration, and `REVEAL_DEFINER_PRIVILEGES` at the top of this file
    shows the derivation: the function returns identity, checks the actor's `CARE`
    assignment itself, and writes the audit row. The middle one is the half of the
    design that has to hold when the service is bypassed, which is why
    `role_assignment` is in the set and why two would have been the wrong number.

    **What this cannot see, stated rather than implied** (`docs/MISTAKES.md` entry
    14): a change *within* those three. The function may come to read a different
    column of `user_identity`, or every row of `role_assignment` rather than the
    actor's, and nothing here moves — the audit row records that an access
    happened, not what was read. The grant is the outer bound on the blast radius,
    not a description of the body.

    Vacuity has no route in: the expected set is non-empty, so a
    `has_table_privilege` that answered `false` to everything fails this rather
    than passing it, and one that answered `true` to everything fails it too.
    """
    function = the_reveal_function(db_session)
    owner = function["owner"]
    relations = [row[0] for row in db_session.execute(text(PUBLIC_RELATIONS))]
    assert relations, (
        "There is no table or view in `public`, so this sweep has nothing to ask about and the "
        "comparison below would be between an empty set and three expected members — failing for "
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
        f"`{owner}` owns `{function['signature']}`, so what it holds is what that function can "
        f"reach. Beyond what its job needs: {unexpected}. Missing from what its job needs: "
        f"{missing}.\n\n"
        "The first list is the one to read first. A `SECURITY DEFINER` function spends its "
        "owner's privileges on behalf of a caller who does not have them, so every grant this "
        "role holds is reachable through the one door `pulse_care` may open — and nothing else in "
        "this build would notice a new one, because `alembic check` compares schema and not "
        "grants. If the owner has come to own a relation rather than to be granted on it, that "
        "shows up here as every privilege on that relation at once.\n\n"
        "The second list means the reveal cannot do its job and some other test is about to fail "
        "for a reason that reads as unrelated: without `role_assignment:SELECT` the function "
        "cannot check the actor's `CARE` assignment, and without `audit_log:INSERT` it cannot "
        "leave the record that makes the read legitimate."
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
        "tests from `tests/conftest.py`; on a managed Postgres from the operator. The migration "
        "is the one mechanism that runs everywhere, so it is the one that has to end with the "
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
# privileges with none of the blast radius: `tests/conftest.py` has already
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
# `the_reveal_function` requires there to be exactly one `SECURITY DEFINER`
# function, which is a fact about E0-10 rather than about head.
#
# **Only one identifier is written down**, and that is deliberate. Alembic
# resolves `<revision>-1` against the chain, so the parent is derived rather than
# spelled: a revision inserted between E0-09's and this one changes what gets
# undone on its own, where a second constant here would quietly keep naming the
# wrong parent.
IDENTITY_REVISION = "446183e8cc5f"
BELOW_THE_IDENTITY_REVISION = f"{IDENTITY_REVISION}-1"

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
        definer = the_reveal_function(connection)["owner"]
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
        definer = the_reveal_function(connection)["owner"]
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
