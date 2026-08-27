"""The three definer doors E1-11 opens for `pulse_app` — ADR 0094, decisions D6 and D7.

The roster sync has to turn a roster member into row ids and store an address, and
the connection it runs on is the one every screen in the product runs on. Two of
the columns involved are the ones the confidentiality model is built around:

  - `user.lms_user_id` is the `sub` claim verbatim (ADR 0045), and E1-10's round-3
    security review revoked `pulse_app`'s read of it because "a connection able to
    read it can enumerate every subject that ever launched and join a response back
    to the person who gave it".
  - `user_identity.identity_email` is an address, which §4.1 keeps away from every
    role but Care, and `pulse_app` holds "no grant of any kind" on that table
    (E0-10).

ADR 0094's answer is the identity-grant scheme's third mechanism: a `SECURITY
DEFINER` function answers the point query — *this* subject, *this* id — while the
calling connection holds no read on the column at all. `record_roster_email` is
D7's writing counterpart, owned by a second NOLOGIN role holding two columns and
one row's worth of privilege.

**Every refusal here is asserted as a refusal, never as an absence** (SPEC §4.1,
and the rule this project's test author works to): a query that answers nothing
and a query the database refuses look identical in a result set, and only one of
them is a guarantee. The `invariant`-marked tests below run in CI's isolated pass,
where a skip is a failure.

**What is asserted elsewhere.** That `pulse_app` may execute *exactly* these three
functions and neither half of the Care door is
`tests/integration/test_identity_grants.py`'s inventory, which is where every
mechanism-level grant assertion in this project lives; this module is about what
the doors do when they are opened.
"""

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

APPLICATION_ROLE = "pulse_app"
CARE_ROLE = "pulse_care"

# The two owners ADR 0094 and D7 create, each a NOLOGIN role that exists for
# nothing else, so "the definer's privileges" is a list you can read in one file
# against one body (ADR 0043's pattern).
RESOLVE_DEFINER = "pulse_resolve_definer"
ROSTER_DEFINER = "pulse_roster_definer"

# The three functions, spelled as `identity_resolution_v001.sql` and
# `roster_email_v001.sql` spell them. Named rather than discovered: unlike E0-10's
# reveal, whose signature that ticket deliberately left open, these are settled
# byte for byte in the shared file E1-11 and E1-12 both ship.
#
# Every argument is written as a `CAST(:name AS type)` rather than as
# `:name::type`, and the types are named rather than left to inference. Both are
# forced: SQLAlchemy's `text()` stops reading `:name` as a bind parameter when a
# colon follows it (the same trap `test_identity_grants.py` records for
# `regprocedure`), and psycopg sends a Python `None` with no type at all — so an
# uncast NULL argument makes Postgres answer "function does not exist" (42883)
# where this module is asking whether the caller may execute one (42501), and a
# refusal test would pass against a function that is simply missing.
RESOLVE_PLATFORM_USER = (
    "public.resolve_platform_user(CAST(:platform AS uuid), CAST(:subject AS text))"
)
RESOLVE_PERSON_FOR_USER = "public.resolve_person_for_user(CAST(:user_id AS uuid))"
RECORD_ROSTER_EMAIL = "public.record_roster_email(CAST(:user_id AS uuid), CAST(:email AS text))"

# What the roster definer may do, and the whole of it — **derived from D7's
# sentence rather than copied from the migration**, so this constant can be
# checked against what was asked for instead of against the SQL it polices
# (`docs/MISTAKES.md` entry 19). D7: "owner is a new NOLOGIN role
# `pulse_roster_definer` holding exactly `INSERT (user_id, identity_email)`,
# `UPDATE (identity_email)`, `SELECT (user_id, identity_email)` on
# `public.user_identity`".
#
# The `SELECT` is the entry to read twice: an `INSERT … ON CONFLICT (user_id) DO
# UPDATE` needs to see the conflicting row, and the two columns it may see are the
# two it may write. `identity_name` is in none of the three lists, which is what
# makes "the sync never writes a name" a property of the grant rather than of the
# function body.
ROSTER_DEFINER_PRIVILEGES = frozenset(
    {
        ("user_identity", "user_id", "INSERT"),
        ("user_identity", "identity_email", "INSERT"),
        ("user_identity", "identity_email", "UPDATE"),
        ("user_identity", "user_id", "SELECT"),
        ("user_identity", "identity_email", "SELECT"),
    }
)

# And the resolver's, from ADR 0094's own sentence: "a NOLOGIN role holding SELECT
# on exactly five columns (`user.id`, `user.lti_platform_id`, `user.lms_user_id`,
# `person.id`, `person.user_id`) and nothing else".
RESOLVE_DEFINER_PRIVILEGES = frozenset(
    {
        ("user", "id", "SELECT"),
        ("user", "lti_platform_id", "SELECT"),
        ("user", "lms_user_id", "SELECT"),
        ("person", "id", "SELECT"),
        ("person", "user_id", "SELECT"),
    }
)

# Every privilege a column can carry, so "exactly" above is checked against all of
# them rather than against `SELECT` alone: `INSERT` and `UPDATE` on a name column
# read nothing and let one be written, and `REFERENCES` lets a foreign key probe
# for a value's existence.
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")

# The statement `pulse_app` must still be refused. Read `*` rather than the email
# column, because that is the shape E0-10's own refusals take and the one a reader
# recognises; the column-grain question is asked by the privilege sweep below.
READ_IDENTITY = 'SELECT * FROM public."user_identity" LIMIT 1'

# The column E1-10's round-3 review revoked, and the enumeration it stops.
ENUMERATE_SUBJECTS = 'SELECT lms_user_id FROM public."user" LIMIT 1'

# Postgres reports an insufficient privilege as SQLSTATE 42501. Asserted on the
# code rather than on the message, because a missing table (42P01) would satisfy
# "it failed" and would mean something else entirely.
INSUFFICIENT_PRIVILEGE = "42501"

COLUMN_PRIVILEGE_SWEEP = """
    SELECT c.relname, a.attname, p.privilege
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'REFERENCES']) AS p(privilege)
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p')
      AND has_column_privilege(:role, c.oid, a.attnum, p.privilege)
    ORDER BY 1, 2, 3
"""

ROLE_EXISTS = "SELECT 1 FROM pg_roles WHERE rolname = :role"
CURRENT_ROLE = "SELECT current_user"


class acting_as:  # noqa: N801 — a context manager used as a statement, not a type
    """Run the block as `role`, then hand the session back as it was found.

    A copy of the helper in `tests/integration/test_identity_grants.py` rather than
    an import of it: a test module that imports another test module depends on
    where pytest put `tests/` on `sys.path`, and an import error is not a red. The
    hazard it works around — `SET ROLE` to a non-superuser drops superuser, and
    `RESET ROLE` fails on an aborted transaction, so every statement expected to
    fail goes through `refused` — is written down in both places.
    """

    def __init__(self, session: Any, role: str) -> None:
        self.session = session
        self.role = role

    def __enter__(self) -> "acting_as":
        present = self.session.execute(text(ROLE_EXISTS), {"role": self.role}).scalar_one_or_none()
        assert present is not None, (
            f"There is no `{self.role}` role in this cluster. ADR 0094 creates "
            f"`{RESOLVE_DEFINER}` and E1-11's D7 creates `{ROSTER_DEFINER}`, each guarded by a "
            "`pg_roles` lookup so the second ticket's migration replays harmlessly; `pulse_app` "
            "and `pulse_care` are E0-10's."
        )
        self.session.execute(text(f'SET ROLE "{self.role}"'))
        current = self.session.execute(text(CURRENT_ROLE)).scalar_one()
        assert current == self.role, (
            f'`SET ROLE "{self.role}"` left `current_user` as {current!r}. Every assertion in this '
            "module is about what that role may do, and a session that did not switch measures the "
            "bootstrap superuser — which passes every control and every refusal at once."
        )
        return self

    def __exit__(self, *exception: Any) -> None:
        self.session.execute(text("RESET ROLE"))


def refused(session: Any, statement: str, parameters: dict[str, Any] | None = None) -> Any:
    """Run `statement` inside a savepoint; answer the error it provoked, or `None`."""
    from sqlalchemy.exc import DatabaseError

    savepoint = session.begin_nested()
    try:
        session.execute(text(statement), parameters or {})
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.commit()
    return None


def sqlstate(failure: Any) -> str | None:
    return getattr(getattr(failure, "orig", None), "sqlstate", None)


def held_columns(session: Any, role: str) -> set[tuple[str, str, str]]:
    """Every `(relation, column, privilege)` `role` holds anywhere in `public`.

    Asked through `has_column_privilege` rather than by reading `attacl`, so a
    privilege reaching the role by membership in another role counts — the hole
    `GRANT pulse_reveal_definer TO pulse_app` opens, which writes no ACL entry
    anywhere.
    """
    return {
        (row[0], row[1], row[2])
        for row in session.execute(text(COLUMN_PRIVILEGE_SWEEP), {"role": role}).tuples()
    }


@pytest.fixture
def a_subject_row(committed_rows: Any, metadata_tables: dict[str, Any]) -> Any:
    """Two platforms, and one `user` row on each carrying the *same* subject key.

    The same key on purpose: `lms_user_id` is the platform's own identifier for a
    person and means nothing outside the registration that issued it, so two
    platforms using one string is the ordinary case rather than a contrived one —
    and it is the case a resolver that forgot its platform argument gets wrong.
    """
    subject = f"e1-11-subject-{uuid4().hex[:12]}"
    rows = []
    for _ in range(2):
        platform = committed_rows.seed("lti_platform", {})
        rows.append(
            committed_rows.seed(
                "user",
                {"lti_platform": platform},
                lms_user_id=subject,
            )
        )
    committed_rows.commit()
    return {"subject": subject, "users": rows}


@pytest.mark.invariant
def test_the_application_role_resolves_a_subject_it_holds_and_is_still_refused_the_column(
    committed_rows: Any, a_subject_row: Any, metadata_tables: dict[str, Any]
) -> None:
    """ADR 0094's whole claim, and it is a pair rather than a permission.

    "`pulse_app` can resolve a subject it already holds from a verified token or a
    roster document, and can never enumerate subjects it does not."

    **The refusing half is `invariant`-marked and is the reason this ticket needs a
    definer at all.** Re-granting `SELECT (lms_user_id)` would make the sync a
    two-line change and would reverse E1-10's round-3 fix: every screen's
    connection could again list every subject that ever launched and join a
    response back to the person who gave it. So the refusal is asserted as a
    *refused statement* with its SQLSTATE, not as an empty result — an absence
    passes against a table that happens to be empty, against a typo in a column
    name, and against a query that failed for some other reason entirely.

    **The permitting half is what stops the fix being a wall.** A schema that
    refused both would satisfy every denial test in this repository and leave the
    sync unable to match a single roster member.
    """
    subject = a_subject_row["subject"]
    known = a_subject_row["users"][0]
    key = next(iter(metadata_tables["user"].primary_key.columns)).name
    platform_column = sorted(
        {
            item.parent.name
            for item in metadata_tables["user"].foreign_keys
            if item.column.table.name == "lti_platform"
        }
    )
    assert len(platform_column) == 1, (
        f"`user` has {platform_column} foreign keys to `lti_platform`, and the resolver is keyed "
        "on exactly one of them."
    )

    with acting_as(committed_rows.session, APPLICATION_ROLE):
        resolved = committed_rows.session.execute(
            text(f"SELECT {RESOLVE_PLATFORM_USER}"),
            {"platform": known[platform_column[0]], "subject": subject},
        ).scalar_one()
        enumeration = refused(committed_rows.session, ENUMERATE_SUBJECTS)
        identity = refused(committed_rows.session, READ_IDENTITY)

    assert resolved == known[key], (
        f"`resolve_platform_user` answered {resolved!r} for a subject this deployment holds; the "
        f"row is {known[key]!r}. A function that cannot resolve leaves the sync unable to match a "
        "roster member to a user at all, which is the wall ADR 0094 rejects as the alternative to "
        "the door."
    )
    assert enumeration is not None and sqlstate(enumeration) == INSUFFICIENT_PRIVILEGE, (
        f"`{APPLICATION_ROLE}` read `user.lms_user_id` (the statement answered "
        f"{enumeration!r}). E1-10's round-3 review revoked exactly that read: the column is the "
        "`sub` claim verbatim, so a connection holding it can enumerate every subject that has "
        "ever launched and join a response back to a person — on the connection every screen in "
        "the product runs on. The definer function exists so that this stays refused while a "
        "point lookup still answers."
    )
    assert identity is not None and sqlstate(identity) == INSUFFICIENT_PRIVILEGE, (
        f"`{APPLICATION_ROLE}` read `user_identity` (the statement answered {identity!r}). E1-11 "
        "gives that role `EXECUTE` on a function that *writes* an email; holding a read as well "
        "would make every address in the deployment visible to the connection every instructor "
        "screen runs on."
    )


def test_resolving_a_subject_is_scoped_to_the_platform_that_issued_it(
    committed_rows: Any, a_subject_row: Any, metadata_tables: dict[str, Any]
) -> None:
    """The resolver's two arguments are both load-bearing, and only a pair says so.

    A subject key is the platform's own identifier for a person; two registrations
    can use the same string for two different people, which is why the `user` table
    carries a platform reference at all and why `resolve_platform_user` takes one.

    **The mutation this kills**: a body that matches on `lms_user_id` alone. With
    one registration in the database it is indistinguishable from the correct one —
    and this deployment has one registration today, which is exactly how such a
    body would ship. What it does in a second institution's deployment is enroll
    one platform's student into the other platform's section.

    Both directions: the same key resolves to a different row under each platform,
    and neither row is the other's.
    """
    subject = a_subject_row["subject"]
    first, second = a_subject_row["users"]
    key = next(iter(metadata_tables["user"].primary_key.columns)).name
    platform_column = sorted(
        {
            item.parent.name
            for item in metadata_tables["user"].foreign_keys
            if item.column.table.name == "lti_platform"
        }
    )[0]

    with acting_as(committed_rows.session, APPLICATION_ROLE):
        answers = [
            committed_rows.session.execute(
                text(f"SELECT {RESOLVE_PLATFORM_USER}"),
                {"platform": row[platform_column], "subject": subject},
            ).scalar_one()
            for row in (first, second)
        ]

    assert answers == [first[key], second[key]], (
        f"Two registrations carry the subject {subject!r} for two different people, and the "
        f"resolver answered {answers} where the rows are {[first[key], second[key]]}. A body that "
        "matches on `lms_user_id` alone answers whichever row it finds first — and with one "
        "registered platform, which is this deployment today, it is right every time until the "
        "second one arrives."
    )


def test_resolve_person_for_user_answers_for_a_linked_user_and_null_for_an_unlinked_one(
    committed_rows: Any, metadata_tables: dict[str, Any]
) -> None:
    """The second resolver, both ways, because D5's whole rule turns on the null.

    "The sync writes the INSTRUCTOR `role_assignment` … only when the member's
    `user` row resolves to a `person`. No person → no assignment." So the function
    that answers "no person" is what stands between a roster and a purview grant,
    and a body that answered the wrong thing in either direction would be wrong in
    a way the sync's own tests would report as the sync's fault.

    **The mutation this kills**: a body written with an inner join and a `LIMIT 1`
    that answers *some* person's id for a user linked to none — which is a purview
    grant to whoever happens to sort first.
    """
    key = next(iter(metadata_tables["user"].primary_key.columns)).name
    person_key = next(iter(metadata_tables["person"].primary_key.columns)).name
    link = sorted(
        {
            item.parent.name
            for item in metadata_tables["person"].foreign_keys
            if item.column.table.name == "user"
        }
    )[0]

    linked_user = committed_rows.seed("user", {})
    unlinked_user = committed_rows.seed("user", {})
    person = committed_rows.seed("person", {}, **{link: linked_user[key]})
    committed_rows.commit()

    with acting_as(committed_rows.session, APPLICATION_ROLE):
        found = committed_rows.session.execute(
            text(f"SELECT {RESOLVE_PERSON_FOR_USER}"), {"user_id": linked_user[key]}
        ).scalar_one()
        absent = committed_rows.session.execute(
            text(f"SELECT {RESOLVE_PERSON_FOR_USER}"), {"user_id": unlinked_user[key]}
        ).scalar_one()

    assert found == person[person_key], (
        f"`resolve_person_for_user` answered {found!r} for a user linked to person "
        f"{person[person_key]!r}. A resolver that cannot find a person leaves every roster "
        "instructor unassigned, and the section's report goes to nobody."
    )
    assert absent is None, (
        f"`resolve_person_for_user` answered {absent!r} for a user no `person` row points at. That "
        "answer is what D5 refuses an `INSTRUCTOR` assignment on; an id here hands somebody else's "
        "person row a purview grant over a section, which SPEC §2.1 computes the whole oversight "
        "surface from."
    )


def test_record_roster_email_writes_the_address_and_never_a_name(
    committed_rows: Any, metadata_tables: dict[str, Any]
) -> None:
    """D7's writer, exercised through the door `pulse_app` actually holds.

    The sync cannot write `user_identity` at all — `pulse_app` holds no privilege on
    that table by any mechanism, which is E0-10's own sentence and an
    `invariant`-marked assertion in `test_identity_grants.py`. So the address goes
    through one function, owned by a role holding two columns, and this test drives
    it exactly as the sync does: as `pulse_app`, by `EXECUTE`.

    **Three properties, and the third is the one no other test can see.** The
    address lands; a second call updates the row rather than raising or
    duplicating (D7's `ON CONFLICT (user_id) DO UPDATE`, which is what makes an
    hourly sync idempotent); and `identity_name` is untouched — set here first, so
    that a body which listed every column in its `DO UPDATE` erases a value this
    test can name and not merely a null it could not tell apart from an absence.
    """
    key = next(iter(metadata_tables["user"].primary_key.columns)).name
    link = sorted(
        {
            item.parent.name
            for item in metadata_tables["user_identity"].foreign_keys
            if item.column.table.name == "user"
        }
    )[0]
    user = committed_rows.seed("user", {})
    committed_rows.seed(
        "user_identity",
        {},
        **{link: user[key], "identity_name": "A Name Only Pulse Knows", "identity_email": None},
    )
    committed_rows.commit()

    with acting_as(committed_rows.session, APPLICATION_ROLE):
        for address in ("first@pulse-tests.invalid", "second@pulse-tests.invalid"):
            committed_rows.session.execute(
                text(f"SELECT {RECORD_ROSTER_EMAIL}"),
                {"user_id": user[key], "email": address},
            )

    identities = metadata_tables["user_identity"]
    stored = [
        row
        for row in committed_rows.session.execute(identities.select()).mappings()
        if row[link] == user[key]
    ]
    assert len(stored) == 1, (
        f"Two calls to `record_roster_email` for one user left {len(stored)} `user_identity` rows: "
        f"{[dict(row) for row in stored]}. D7's body is an `INSERT … ON CONFLICT (user_id) DO "
        "UPDATE`, and a second row per hourly sync is a table that grows with every run."
    )
    assert stored[0]["identity_email"] == "second@pulse-tests.invalid", (
        f"The row carries `identity_email` {stored[0]['identity_email']!r} after two calls; the "
        "second call's address is the one the platform last exposed."
    )
    assert stored[0]["identity_name"] == "A Name Only Pulse Knows", (
        f"The row's `identity_name` is {stored[0]['identity_name']!r} and this test set it to a "
        "name before the writer ran. D7: the function 'never writes `identity_name`' — a name it "
        "overwrote is one somebody entered on purpose, gone on the hour, and NRPS carries no name "
        "to have replaced it with (ADR 0050)."
    )


@pytest.mark.invariant
def test_the_care_role_may_not_execute_either_of_the_roster_definers(committed_rows: Any) -> None:
    """The doors this ticket opens are `pulse_app`'s alone, and the count matters.

    E0-10's central criterion is that `pulse_care` "gets `EXECUTE` on a **single**
    `SECURITY DEFINER` function", split into two halves by E0-26 item 1, "so a name
    cannot be obtained without leaving a record". Every additional door reachable
    by that role is another way to obtain identity, and `record_roster_email` runs
    as an owner that can read `user_identity.identity_email` — so a stray `GRANT
    EXECUTE … TO PUBLIC`, which is the state a migration reaches by *not* revoking,
    hands the Care role an unlogged read of every address in the deployment.

    Asserted as a refused call rather than as an absent grant, and both functions
    are named: a sweep that counted doors would be satisfied by two grants that
    happened to be the right number.

    **The control is `pulse_app` next door**, which must be able to call the same
    function — otherwise this test is satisfied by a function nobody may execute,
    which is a different defect wearing the same green.
    """
    reachable = []
    with acting_as(committed_rows.session, CARE_ROLE):
        for call in (RESOLVE_PLATFORM_USER, RESOLVE_PERSON_FOR_USER, RECORD_ROSTER_EMAIL):
            statement = f"SELECT {call}"
            failure = refused(
                committed_rows.session,
                statement,
                {"platform": None, "subject": None, "user_id": None, "email": None},
            )
            if failure is None or sqlstate(failure) != INSUFFICIENT_PRIVILEGE:
                reachable.append((call, failure))

    assert not reachable, (
        # The S608 suppression: an assertion message that quotes SQL vocabulary, not a query.
        f"`{CARE_ROLE}` may execute {[call for call, _ in reachable]}. E0-10 gives that role "  # noqa: S608
        "`EXECUTE` on the Care door and nothing else, because 'every additional door is a way to "
        "obtain a name without leaving a record' — and `record_roster_email` runs as an owner "
        "holding `SELECT (identity_email)` on `user_identity`. `REVOKE ALL ON FUNCTION … FROM "
        "PUBLIC` is the line whose absence produces exactly this, and Postgres grants `EXECUTE` to "
        f"`PUBLIC` by default. What the failures were: {reachable}."
    )


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        pytest.param(RESOLVE_DEFINER, RESOLVE_DEFINER_PRIVILEGES, id="resolve-definer"),
        pytest.param(ROSTER_DEFINER, ROSTER_DEFINER_PRIVILEGES, id="roster-definer"),
    ],
)
def test_each_definer_holds_exactly_the_column_privileges_its_job_needs(
    db_session: Any, role: str, expected: frozenset[tuple[str, str, str]]
) -> None:
    """ADR 0043's pattern, applied to the two owners this ticket adds.

    A `SECURITY DEFINER` function spends its **owner's** privileges, so the owner's
    grant list is the real blast radius of the door — not the function body, which
    a later revision can change without anybody re-reading the grants. Both owners
    exist for nothing else, which is what makes an equality possible at all:
    "'the definer's privileges' is a list you can read in this file against these
    bodies".

    **An equality rather than a ceiling**, for the reason
    `REVEAL_DEFINER_PRIVILEGES` next door is one. A `>=` is satisfied by an owner
    that also holds `SELECT (identity_name)` — which would make
    `record_roster_email` a function that *could* return a name, one revision away,
    with every behavioural test in this repository still green.

    **The expected sets are derived from the records' own sentences** rather than
    copied from the migration (`docs/MISTAKES.md` entry 19): ADR 0094 names the
    resolver's five columns and D7 names the roster definer's three grants. A
    constant copied from the SQL it polices asserts that the SQL equals itself.

    **The near miss it must not fire on**: a privilege the role holds by owning
    something, which `has_column_privilege` reports and a `pg_attribute.attacl`
    read would not — that is the point of asking through the function.
    """
    held = held_columns(db_session, role)
    assert held == expected, (
        f"`{role}` holds {sorted(held)} and the record says {sorted(expected)}.\n\n"
        "A `SECURITY DEFINER` function runs as its owner, so every column in that set is a column "
        "the function's callers can be made to reach — `pulse_app`, which is the connection every "
        "screen in this product runs on. ADR 0094 gives the resolver's owner five columns and no "
        "identity-bearing one among them; E1-11's D7 gives the roster definer two columns of "
        "`user_identity` and never `identity_name`.\n\n"
        "If a grant here is legitimate, it is recorded in the pull request that makes it, in this "
        "constant, with the sentence it rests on — the shape "
        "`tests/integration/test_identity_grants.py` uses for every other grant in this schema."
    )
