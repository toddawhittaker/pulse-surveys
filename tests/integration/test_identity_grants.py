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
from typing import Any

import pytest
from sqlalchemy import text
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
# three doors the application role has. This is the **one** §4.1 item E0-10
# lands: item 1, "no student-visible path exposes another section", is deferred
# to E2 on the record, because there is no student-visible path here and the
# scoping that would make "another section" mean anything is E0-11's. Nothing in
# this file may be read as covering it.
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


def test_a_rollback_discards_the_revealed_identity_and_its_audit_row_together(
    db_session: Any, seed_rows: Any, supervision_graph: Any
) -> None:
    """Criterion: the reveal and its audit row cannot come apart.

    ADR 0001 rejected "logging the reveal as a separate step after reading
    identity … because it makes the audit trail a convention that a future code
    path can skip. Putting the read and the audit write in one transaction means
    they cannot come apart." This asserts both directions of that in one
    transaction:

      - calling the function **adds a row somewhere** while the caller has the
        identity in hand. An implementation that returns identity and leaves the
        logging to its caller adds nothing here, and that is the one this kills;
      - rolling the transaction back **removes it again**. An implementation that
        logs through a second connection — `dblink`, a separate engine, a
        "fire-and-forget" audit writer — leaves the row behind, and that is the
        other. It looks like a safer design and it means the record can exist
        without the read, and the read without the record.

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
        f"counts across {len(before)} tables are unchanged. §4: 'every identity access is "
        "automatically audit-logged with actor, timestamp, and case', and E0-10 puts the write "
        "inside the function so that 'a name cannot be obtained without leaving a record'. An "
        "audit written by the caller afterwards is the design ADR 0001 rejected, and it passes "
        "every other test in this file."
    )

    surviving = {name: after[name] - before[name] for name in before if after[name] != before[name]}
    assert not surviving, (
        f"After rolling the transaction back, {surviving} still differs from the counts before "
        f"the reveal, while the identity read was discarded with the transaction. The audit row "
        "and the read are then in different transactions — an autonomous or second-connection "
        "writer — so a failed reveal can leave a record of an access that did not happen, and a "
        "future refactor can leave an access with no record. E0-10 asks for both to be discarded "
        "together, and this is the shape that proves they are one write."
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
