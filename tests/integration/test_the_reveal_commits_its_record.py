"""The record of a reveal is not the caller's to discard — ticket E0-26, item 1.

SPEC §4 states the guarantee: "Re-identification is possible only through the Care
queue (§6.2), only by the Care role, and **every identity access is automatically
audit-logged** with actor, timestamp, and case." E0-10 built a single
`SECURITY DEFINER` function that returned identity and wrote the `audit_log` row
in one transaction — the caller's — and E0-10's review measured what that leaves
open, twice, on the pinned image:

    BEGIN;
    SELECT * FROM public.reveal_student_identity(<a real CARE person>, <a user>, NULL);
    ROLLBACK;

returns the student's name and email address and leaves `audit_log` empty.
Postgres has already streamed the result rows to the client by the time the caller
decides what to do with the transaction, so the read and the record come apart,
and the party who can separate them is the one holding the Care credential. That
is a live gap in a guarantee the spec states, not a missing assertion, and E0-26
item 1 closes it.

**The shape the ticket settles**, and the interface every test here is written
against — the ticket spells it because a test cannot be written against an
interface that does not exist:

    public.record_identity_reveal(
        in_actor_person_id uuid, in_subject_user_id uuid, in_case_id uuid
    ) RETURNS uuid                       -- the audit_log row's id

    public.reveal_student_identity(in_reveal_id uuid)
        RETURNS TABLE (identity_name text, identity_email text)

The three-argument `reveal_student_identity` is **dropped**, not kept alongside:
a door that still opens the old way is not closed.

**Why the counts here are read from a second connection.** The ticket's "done
when" says so in as many words, and the reason is `docs/MISTAKES.md` entry 3. A
count taken on the connection that rolled back is a statement about what that
connection can see — it is not evidence about what survived, and it is exactly the
shape of the test this ticket replaces. E0-10's own acceptance criterion asked for
a test that "rolling back the transaction discards both the read and the audit
row, so the two cannot come apart"; the test asserted precisely that and passed,
because the rollback does discard both *inside the database*, after the identity
has reached the client. So every surviving-row count below is taken on a fresh
connection from `migrated_engine`, and every one of them is paired with a count
that must come back **non-zero**, so that a reader which has gone blind fails here
rather than reporting that nothing survived.

**Denial, not absence.** Every refusal here is asserted as a `DatabaseError`
having arrived, never as a name being missing from a result set — an absence is
satisfied by a query that returned nothing for an unrelated reason. That includes
the record whose actor has since lost `CARE`: the ticket did not originally say
what happens there, this module first accepted either a raise or an empty result
and said so, and Todd settled it as a raise on 2026-08-20 for the reason the ticket
already gives elsewhere — an empty result is the value the service turns into
`None`, so a refusal would reach §6.2's queue as "no identity on file".

**Three different students, and the answers about them must not collapse.** A
student with a name and an address; a student with a name and **no** address,
because `RevealedIdentity.identity_email` is legitimately optional and NRPS
releases an address only where the platform is configured to; and a user with **no
`user_identity` row at all**. The reveal answers one row, one row with a null
address, and zero rows. The constant block below names the three, and each test
says which it is about.

**Every test names the mutation it exists to survive**, because a red suite that
cannot say which edit turns it green is a description rather than a guarantee.
Two of them are aimed at implementations that look correct:
`test_a_record_written_inside_a_savepoint_does_not_count_as_committed` is aimed at
comparing the audit row's `xmin` against the current transaction, and
`test_the_honest_path_returns_the_identity_and_leaves_exactly_one_audit_row` is
aimed at a reveal that keeps E0-10's own `INSERT` beside the new record.

**What this module does not cover**, stated rather than implied
(`docs/MISTAKES.md` entry 14). Item 2 of the same ticket — the conflict-of-interest
marking §6.2 requires — is carried to E10 and nothing here asserts it. Item 3, the
acting person being a parameter rather than a property of the connection, is
carried too: every test below hands the actor in, exactly as a caller holding the
Care credential would, so a borrowed `person_id` is as accepted here as it is in
production. `services/safety.py`'s half of the door is
`tests/integration/test_care_service_reveal.py`; nothing in this file goes near
the service.

**`test_identity_grants.py` has moved onto this interface, and where the line
between the two modules runs is worth knowing before adding a test to either.**
That module's helper became `the_care_door`, and the count of halves moved out of
it into `test_pulse_care_may_execute_exactly_the_two_halves_of_the_care_door` —
a count is a fact about a revision, and two tests there inspect a downgraded one.
Its four tests that go through the door now take a `pulse_care` login and
record, commit and reveal, because none of them could be driven inside
`db_session`; and `test_the_reveal_writes_its_audit_row_in_the_callers_own_
transaction`, which asserted the row does *not* survive a rollback, is gone — its
own docstring had named this ticket as the one that would invert it, and the
inversion lives here, in
`test_a_caller_that_rolls_back_keeps_no_name_it_is_not_recorded_as_having_taken`.

**That module asks whether the grants let the door work and stop everything else;
this one asks what the door does.** A behavioural rule about an uncommitted record,
a savepoint, a revoked actor or a substituted subject belongs here. A rule about
who holds `EXECUTE`, what the definer may reach, or what `pulse_care` may do to
`audit_log` directly belongs there.
"""

from typing import Any, NamedTuple
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# The two calls the ticket settles, named because the ticket names them. E0-10's
# tests discover their function from the catalog — "E10 replaces the function and
# a rule spelled with its name would retire with it" — and that reading does not
# apply here: this ticket's subject *is* the split into two calls, and a test that
# discovered them would have to decide which of the two it had found by looking at
# a property that half this module is asserting.
RECORD_FUNCTION = "record_identity_reveal"
REVEAL_FUNCTION = "reveal_student_identity"

# SPEC §8's table, and the ticket's own words for what the first call returns:
# "the audit_log row's id".
AUDIT_TABLE = "audit_log"

# The columns the ticket gives the reveal's result. Asserted by name rather than
# by "some string came back", because a reveal that answers the student's key
# twice, or a row of nulls, satisfies "it returned something" and reveals nobody.
IDENTITY_COLUMNS = ("identity_name", "identity_email")

# **Three students, and they are three different cases that must not collapse into
# each other.** Every seeding helper below builds exactly one of them, and every
# test says in its docstring which it uses:
#
#   1. a name *and* an address — the ordinary case, and the one the honest path and
#      the rollback tests use;
#   2. a name and **no** address — `RevealedIdentity.identity_email` is legitimately
#      optional, because NRPS releases an address only where the platform is
#      configured to. The reveal answers one row with a null email, not zero rows;
#   3. **no `user_identity` row at all** — no identity has ever been stored for this
#      user. The reveal answers zero rows, and the service turns that into `None`.
#
# The address is seeded explicitly, and that is a repair rather than a detail. The
# seeding helper in `tests/conftest.py` fills only what the schema requires, and
# `identity_email` is nullable — so before `an_address` below existed, every
# identity row the suite had ever made carried a null address. Two assertions were
# satisfied by that null and by nothing else: `returned["identity_email"] ==
# revealable.identity_email` was `None == None`, and asking whether a *second*
# student's address had leaked into the result is true of any result at all when
# that address is `None` (`docs/MISTAKES.md` entry 3). Cases 1 and 2 are each
# somebody's subject on purpose now.


def an_address() -> str:
    """One address that belongs to exactly one seeded student.

    Unique per call, because two students sharing an address would make
    `test_the_reveal_returns_the_student_named_in_the_committed_record` unable to
    tell a correct reveal from a leak, and because nothing here should depend on
    whether the column carries a uniqueness constraint.
    """
    return f"e0-26-{uuid4().hex[:12]}@example.invalid"


RECORD_CALL = (
    f"SELECT public.{RECORD_FUNCTION}("
    "CAST(:actor AS uuid), CAST(:subject AS uuid), CAST(:case_id AS uuid))"
)
REVEAL_CALL = f"SELECT * FROM public.{REVEAL_FUNCTION}(CAST(:reveal_id AS uuid))"  # noqa: S608

# The two counts every surviving-row assertion here is made of. Templates rather
# than f-strings at the call site so the table and key names are interpolated in
# one place; the values interpolated are read out of `Base.metadata`, never out of
# anything a test was handed.
COUNT_AUDIT_ROWS = 'SELECT count(*) FROM public."{table}"'
COUNT_ONE_AUDIT_ROW = 'SELECT count(*) FROM public."{table}" WHERE "{key}" = CAST(:id AS uuid)'

# Everything a test here needs to know about one function in `public`, for the two
# assertions that are about the door's *shape* rather than about what it does.
#
# **`argument_types` carries types and no names, and that is the repair for dispute
# E0-26-01.** It was `pg_get_function_identity_arguments`, which renders
# `in_reveal_id uuid` — the parameter's name as well as its type — so comparing it
# against `'uuid'` refused the exact signature the ticket settles and could only
# have been satisfied by an anonymous parameter. Three spellings were measured
# during the ruling and two of them are traps:
#
#   - `p.proargtypes::regtype[]::text` renders `[0:0]={uuid}` rather than `{uuid}`,
#     because `oidvector` is zero-based. A literal comparison there is the same
#     false red one layer down;
#   - `p.oid::regprocedure::text` is `search_path`-dependent — it schema-qualifies
#     when the function is not visible on the current path — which makes it right
#     for a failure message and wrong for a predicate. It stays as `signature`, and
#     it is printed and never compared.
#
# `array_to_string(p.proargtypes::regtype[], ',')` gives `uuid` cleanly, and the
# column is named for what it holds so that the next reader does not repeat this.
FUNCTIONS = """
    SELECT p.oid::regprocedure::text AS signature,
           array_to_string(p.proargtypes::regtype[], ',') AS argument_types,
           pg_get_function_result(p.oid) AS result,
           p.pronargs AS argument_count,
           p.proretset AS returns_a_set,
           p.prosecdef AS security_definer,
           coalesce(array_to_string(p.proargmodes, ','), '') AS argument_modes
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = :name
    ORDER BY 1
"""

THE_INTERFACE = (
    "E0-26 item 1 settles the door's shape before any test was written:\n\n"
    "    public.record_identity_reveal(\n"
    "        in_actor_person_id uuid, in_subject_user_id uuid, in_case_id uuid\n"
    "    ) RETURNS uuid\n\n"
    "    public.reveal_student_identity(in_reveal_id uuid)\n"
    "        RETURNS TABLE (identity_name text, identity_email text)\n\n"
    "The first records that a reveal is about to happen and the caller must `COMMIT` it; the "
    "second returns identity, and only against a record that is already committed. The "
    "three-argument `reveal_student_identity` is dropped rather than kept alongside."
)


class Revealable(NamedTuple):
    """One student with an identity on file, and two people who might ask about them."""

    subject_user_id: Any
    identity_name: str
    identity_email: str
    care_person: Any
    care_assignment_id: Any
    reporting_person: Any
    audit_key: str


def attempt(connection: Any, statement: str, parameters: dict[str, Any]) -> tuple[list[Any], Any]:
    """Run `statement` on `connection`; answer its rows and the error it raised, if any.

    **It does not roll anything back**, unlike the `refused` helper in
    `test_identity_grants.py`, and the difference is the subject of this module:
    what the caller does with its transaction after a refusal is a thing the tests
    here decide statement by statement. A caller that has provoked an error is
    inside an aborted transaction until it says otherwise.

    **`returns_rows` is checked though every statement this module sends is a
    `SELECT`**, and the reason is `docs/MISTAKES.md` entry 13: its twin in
    `test_identity_grants.py` is handed `CREATE TEMPORARY TABLE`, `INSERT` and
    `DELETE`, and without this check `.mappings().all()` raises
    `ResourceClosedError` — which is not a `DatabaseError`, so it escapes the
    `except` and reaches the test as an error rather than as an answer. That was a
    measured failure there and a latent one in a test that passed. The quirk is
    faced in two places, so both places carry the same one-line answer rather than
    one of them carrying a comment about it.
    """
    try:
        result = connection.execute(text(statement), parameters)
        rows = result.mappings().all() if result.returns_rows else []
    except DatabaseError as failure:
        return [], failure
    return rows, None


def record(connection: Any, *, actor: Any, subject: Any) -> tuple[Any, Any]:
    """Ask for a reveal to be recorded; answer the record's id, and the error if refused.

    The case id is null: there is no case model until E10, and E0-10 shipped its
    reveal the same way. `in_case_id` exists in the signature because §6.2's audit
    entry carries one, and this is the value the queue will supply.
    """
    rows, failure = attempt(
        connection, RECORD_CALL, {"actor": actor, "subject": subject, "case_id": None}
    )
    if failure is not None:
        return None, failure
    assert rows, (
        f"`public.{RECORD_FUNCTION}` returned no row at all. It is declared `RETURNS uuid`, so a "
        "call that is not refused answers exactly one value — the id of the `audit_log` row it "
        "wrote — and every test here addresses the record by that id."
    )
    return next(iter(rows[0].values())), None


def reveal(connection: Any, reveal_id: Any) -> tuple[list[Any], Any]:
    """Call the reveal against one record's id; answer its rows and the error, if any."""
    return attempt(connection, REVEAL_CALL, {"reveal_id": reveal_id})


def identity_in(rows: list[Any]) -> set[str]:
    """Every non-null string the reveal handed back, whatever column it arrived in."""
    return {str(value) for row in rows for value in row.values() if value is not None}


def audit_rows_with_id(engine: Any, key: str, reveal_id: Any) -> int:
    """How many `audit_log` rows carry `reveal_id`, read on a connection of this test's own.

    A fresh connection per call, so the answer is never a value cached in a
    snapshot taken before the transaction under test did anything. This is the
    "second connection" the ticket's "done when" requires, and it is the bootstrap
    identity rather than `pulse_care` because Care holds no `SELECT` on
    `audit_log` — the record it writes is not one it may read back, which is
    itself part of E0-10's grant model.
    """
    statement = COUNT_ONE_AUDIT_ROW.format(table=AUDIT_TABLE, key=key)
    with engine.connect() as connection:
        return connection.execute(text(statement), {"id": reveal_id}).scalar_one()


def audit_row_total(engine: Any) -> int:
    """How many `audit_log` rows exist right now, on a fresh connection."""
    statement = COUNT_AUDIT_ROWS.format(table=AUDIT_TABLE)
    with engine.connect() as connection:
        return connection.execute(text(statement)).scalar_one()


@pytest.fixture
def reveal_interface(migrated_engine: Any) -> dict[str, list[Any]]:
    """Both halves of the door, as `pg_proc` reports them, or a failure naming what is absent.

    **Its whole job is to keep a missing deliverable a failed assertion rather
    than a `ProgrammingError` from inside a query.** A call to a function that does
    not exist raises SQLSTATE 42883 with a message about argument types, which
    reads as a test that is broken rather than as a criterion nobody has met yet —
    and the two are fixed by different people. `AuthzModule` in `tests/conftest.py`
    draws the same line for the same reason.

    It asserts only that each name resolves to at least one function. **What their
    shape has to be is asserted in tests and not here**: two tests below are about
    exactly that, and a fixture that had already checked the arity would be
    supplying the value those tests measure.
    """
    found: dict[str, list[Any]] = {}
    with migrated_engine.connect() as connection:
        for name in (RECORD_FUNCTION, REVEAL_FUNCTION):
            found[name] = connection.execute(text(FUNCTIONS), {"name": name}).mappings().all()

    missing = [name for name in (RECORD_FUNCTION, REVEAL_FUNCTION) if not found[name]]
    present = sorted(row["signature"] for rows in found.values() for row in rows)
    assert not missing, (
        f"`public` has no function called {missing}. {THE_INTERFACE}\n\n"
        f"What it does have under those two names: {present}."
    )
    return found


@pytest.fixture
def revealable(committed_rows: Any) -> Revealable:
    """A student with an identity on file, a Care staffer, and a lead who is not one.

    Committed, because every call below is made on a `pulse_care` connection of the
    test's own and would otherwise be asked about a student that, from where it is
    standing, does not exist. `committed_rows` removes whatever *appeared* when the
    test ends, which is what takes away the `audit_log` rows these tests deliberately
    commit on a connection nothing here tracks by key.

    **This is case 1**: a student with a name *and* an address. The address is
    passed as an override rather than left to the seeding helper, which fills only
    what the schema requires and leaves this nullable column null — so without it,
    every assertion here comparing a returned address against a seeded one would be
    comparing `None` with `None`. Case 2, a student with a name and no address, is
    `seed_a_student_with_no_email` and has a test of its own.

    The Care staffer is E0-09's two-hat person — a `CARE` assignment and a teaching
    assignment on one person, which §2.1 permits and §6.2 spends a paragraph on — so
    the permitted case here is the awkward one rather than the easy one. Their `CARE`
    assignment's key comes back too, because one test revokes it.
    """
    graph = committed_rows.graph
    hats = graph.care_and_instructor_person()
    chain: dict[str, Any] = {}
    identity = committed_rows.seed("user_identity", chain, identity_email=an_address())
    committed_rows.commit()

    user = chain.get("user")
    assert user is not None, (
        "Seeding `user_identity` did not seed a `user` with it, so there is no student to ask "
        "about. ADR 0001 splits the key onto `user` and the name and email onto `user_identity`, "
        "one row per user, which makes the link a NOT NULL foreign key the seeding helper follows."
    )
    for column in IDENTITY_COLUMNS:
        assert identity.get(column), (
            f"The seeded `user_identity` row carries no `{column}`: {dict(identity)}. The reveal's "
            f"result columns are `{IDENTITY_COLUMNS}` by the ticket's own signature, and the tests "
            "using this fixture compare what came back against what was seeded — against a null "
            "they would be asserting that a call returned nothing and calling it a match.\n\n"
            "`identity_email` is nullable and the seeding helper leaves nullable columns alone, so "
            "this fixture passes an address in explicitly. A failure naming that column means the "
            "override did not land — a renamed column, or a helper that stopped honouring "
            "overrides — rather than that a student legitimately has no address on file. That case "
            "is deliberate and it is somebody else's subject: "
            "`test_a_student_whose_identity_carries_no_address_still_comes_back_with_the_name`."
        )

    reporting_person = hats["lead"][graph.person_column]
    assert reporting_person != hats["person"], (
        "The graph fixture handed back one person for both the Care actor and the lead-faculty "
        "actor, so the refusal test below would be making the same call twice and proving nothing."
    )

    return Revealable(
        subject_user_id=user[user_key(committed_rows)],
        identity_name=identity[IDENTITY_COLUMNS[0]],
        identity_email=identity[IDENTITY_COLUMNS[1]],
        care_person=hats["person"],
        care_assignment_id=hats["care"][graph.assignment_key],
        reporting_person=reporting_person,
        audit_key=audit_key(committed_rows),
    )


def user_key(committed_rows: Any) -> str:
    """The name of `user`'s primary key column, from the metadata rather than guessed."""
    return next(iter(committed_rows.tables["user"].primary_key.columns)).name


def audit_key(committed_rows: Any) -> str:
    """The name of `audit_log`'s primary key column."""
    table = committed_rows.tables.get(AUDIT_TABLE)
    assert table is not None, (
        f"There is no `{AUDIT_TABLE}` table in the metadata — it holds {sorted(committed_rows.tables)}. "
        f"SPEC §8 names it, it is append-only and 'includes all re-identifications', and the "
        f"ticket's `public.{RECORD_FUNCTION}` returns the id of the row it writes there."
    )
    return next(iter(table.primary_key.columns)).name


def seed_a_student_with_no_identity_row(committed_rows: Any) -> Any:
    """Case 3: one `user`, and no `user_identity` row for them at all. Committed.

    Distinct from case 2 next door, and the difference is the whole subject of the
    two tests that use them: this student has no identity row, so there is nothing
    for the reveal to return and it answers zero rows. Case 2's student *has* an
    identity row and it carries a name, so the reveal answers one row whose address
    is null.
    """
    row = committed_rows.seed("user", {})
    committed_rows.commit()
    return row[user_key(committed_rows)]


def seed_a_student_with_no_address(committed_rows: Any) -> tuple[Any, str]:
    """Case 2: a student with a name on file and no address. Their key and name.

    The null is written **explicitly**, not left to the seeding helper's default.
    `seed_row` honours an override even when it is `None`, and saying so here is
    what makes this student's missing address a decision this test made rather than
    a property the helper happens to have today — which is exactly what the null
    was before, when it was every seeded student's and nobody's subject.
    """
    chain: dict[str, Any] = {}
    identity = committed_rows.seed("user_identity", chain, identity_email=None)
    committed_rows.commit()
    assert identity[IDENTITY_COLUMNS[1]] is None, (
        f"This helper asked for a student with no address and the row came back carrying "
        f"{identity[IDENTITY_COLUMNS[1]]!r}. `seed_row` in `tests/conftest.py` states that 'an "
        "override is honoured even when it is `None`, so a test can write a null and let the "
        "database accept or refuse it', so either that has stopped being true or the column is no "
        "longer nullable — and the test using this would be asserting a null the reveal was never "
        "given the chance to return."
    )
    return chain["user"][user_key(committed_rows)], identity[IDENTITY_COLUMNS[0]]


def seed_a_second_student(committed_rows: Any) -> tuple[Any, str, str]:
    """Case 1 again, for a second student: key, name and address, committed.

    The address is an override for the reason `revealable` uses one. Without it,
    `other_email` is `None`, and the half of
    `test_the_reveal_returns_the_student_named_in_the_committed_record` that checks
    the other student's address did not leak would be asking whether `None` is in a
    set of strings — true whatever the reveal returned.
    """
    chain: dict[str, Any] = {}
    identity = committed_rows.seed("user_identity", chain, identity_email=an_address())
    committed_rows.commit()
    return (
        chain["user"][user_key(committed_rows)],
        identity[IDENTITY_COLUMNS[0]],
        identity[IDENTITY_COLUMNS[1]],
    )


# ---------------------------------------------------------------------------
# The ticket's "done when": a caller that rolls back keeps no name it is not
# recorded as having taken, and the surviving count is read from somewhere else.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_a_caller_that_rolls_back_keeps_no_name_it_is_not_recorded_as_having_taken(
    care_connections: Any, migrated_engine: Any, revealable: Revealable, reveal_interface: Any
) -> None:
    """SPEC §4: every identity access is audit-logged — including the ones that are undone.

    This is E0-26 item 1's "done when", spelled as the ticket spells it: a caller
    that rolls back keeps no name it is not recorded as having taken, **or** the
    audit row survives the rollback. The assertion is written as that disjunction
    rather than as one of its halves, because the ticket leaves the direction to
    the implementation and a test that demanded a surviving row would settle it.
    Under the shape the ticket settles, the left half is what holds: with no
    committed record there is no identity to keep.

    **The count comes from a second connection**, which is the requirement in the
    ticket's own words, and `docs/MISTAKES.md` entry 3 is why. The connection that
    rolled back can be asked what it can see and will answer honestly about its own
    snapshot; that answer is not evidence about what survived. E0-10's criterion
    asked for exactly the reading this replaces — "rolling back the transaction
    discards both the read and the audit row" — the test asserted it, and it passed
    while the defect was live.

    **Two controls, in order, and neither is ceremony.** The honest path runs
    first on the same connection with the same actor and the same student, so a
    refusal below is attributable to the record not being committed rather than to
    a call this test has bound wrongly, a role that may do nothing, or a database
    that has stopped working. And the reader is required to *find* that honest
    record: a second connection which answers zero for everything — a stale
    snapshot, the wrong table, a `count` over a filter that matches nothing —
    reports the attacker's record as having vanished just as convincingly as a
    rollback does.

    **The mutation it exists to survive**: deleting the guard in
    `reveal_student_identity` that refuses a record which is not yet committed, so
    that the function reads the record out of its own transaction's snapshot. That
    is one `RAISE` and its condition, it restores E0-10's behaviour exactly, and
    every other test in this file that does not name the guard stays green.
    """
    caller = care_connections()

    honest_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, (
        f"The control failed: `public.{RECORD_FUNCTION}` refused a person holding a live `CARE` "
        f"assignment — {refused}. §4 and §6.2 keep this door open on purpose, and until it opens "
        "the rollback below says nothing about what a caller keeps. "
        "`test_the_honest_path_returns_the_identity_and_leaves_exactly_one_audit_row` is where "
        "that is diagnosed."
    )
    caller.commit()
    honest_rows, honest_failure = reveal(caller, honest_id)
    caller.commit()
    assert honest_failure is None and revealable.identity_name in identity_in(honest_rows), (
        f"The control failed: against a committed record the reveal answered {honest_rows} "
        f"(error: {honest_failure}) rather than the seeded {revealable.identity_name!r}. A door "
        "that is shut to everybody passes the assertion below perfectly."
    )
    assert audit_rows_with_id(migrated_engine, revealable.audit_key, honest_id) == 1, (
        "The second connection cannot see the `audit_log` row of a reveal that was committed on "
        "the Care connection a moment ago. It is therefore not in a position to tell a row that "
        "survived a rollback from a row it cannot see for some unrelated reason, and the count "
        "below would report a vanished record whatever the implementation did."
    )

    rolled_back_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, (
        f"The recording call was refused on its second use in the same test: {refused}. Nothing "
        "about the actor or the student changed between the two, so this is a call that succeeds "
        "once — which the ticket says nothing about and which would make the rollback below a "
        "test of single use rather than of the record."
    )
    rows, failure = reveal(caller, rolled_back_id)
    kept = identity_in(rows)
    caller.rollback()

    surviving = audit_rows_with_id(migrated_engine, revealable.audit_key, rolled_back_id)
    took_a_name = revealable.identity_name in kept or revealable.identity_email in kept

    assert surviving == 1 or not took_a_name, (
        f"A `pulse_care` caller opened a transaction, recorded a reveal, obtained "
        f"{sorted(kept)} — the seeded student's name and email address — and rolled back. From a "
        f"second connection, `{AUDIT_TABLE}` holds {surviving} row(s) for that record.\n\n"
        "So the caller kept a name it is not recorded as having taken, which is the finding E0-26 "
        "item 1 exists to close and the thing SPEC §4 says cannot happen: 'every identity access "
        "is automatically audit-logged with actor, timestamp, and case'. The identical call "
        "without the rollback worked in this same test, on this same connection, so the rollback "
        "alone is the difference.\n\n"
        "Either half of the disjunction closes it. Under the shape the ticket settles, the reveal "
        "returns nothing until a separately committed record exists, so the left half holds and "
        f"the reveal above should have raised rather than answering {rows}. An implementation "
        "that instead writes the record over a connection of its own satisfies the right half, "
        "and then this count is 1."
    )


@pytest.mark.invariant
def test_a_record_written_inside_a_savepoint_does_not_count_as_committed(
    care_connections: Any, migrated_engine: Any, revealable: Revealable, reveal_interface: Any
) -> None:
    """The near miss the ticket names: an implementation that looks correct and is not.

    **This test is aimed at comparing the audit row's `xmin` against the current
    transaction.** It is the obvious way to write "the caller has not committed
    this record yet", it passes every other test in this file, and the ticket says
    why it is wrong: "a caller that wraps the first call in a `SAVEPOINT` gives the
    row a subtransaction id, which differs from the top-level id, and the check
    would pass on a record that still vanishes on `ROLLBACK`. Whatever is compared
    has to be a value that a savepoint cannot change."

    So the recording call below runs inside a savepoint which is then released, and
    everything else is the attack in
    `test_a_caller_that_rolls_back_keeps_no_name_it_is_not_recorded_as_having_taken`
    unchanged. Against an `xmin`-comparing implementation that test is green and
    this one is red; against an implementation that compares something a savepoint
    cannot change, both are green. Neither test is redundant: the savepoint is what
    tells the two apart, and the plain rollback is what says the guard exists at
    all.

    **The inversion is `test_the_honest_path_returns_the_identity_and_leaves_
    exactly_one_audit_row`**, which records and commits and reveals **on this same
    connection**. An implementation that refuses everything, or that refuses any
    record written by the connection now asking, passes this test and fails that
    one. Read as a pair they say: the record has to be committed, and committing it
    is enough.

    **The controls** are the same two as next door and for the same reasons — the
    honest path first on the same connection, and a reader required to find that
    honest record before its silence about this one is believed.

    **The mutation it exists to survive**: writing the committed-record guard as a
    comparison between the record's `xmin` and `pg_current_xact_id()`, which
    answers "not my transaction" for a row a savepoint wrote and opens the door.
    """
    caller = care_connections()

    honest_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, f"The control failed: the recording call was refused — {refused}."
    caller.commit()
    honest_rows, honest_failure = reveal(caller, honest_id)
    caller.commit()
    assert honest_failure is None and revealable.identity_name in identity_in(honest_rows), (
        f"The control failed: against a committed record the reveal answered {honest_rows} "
        f"(error: {honest_failure}). A door that is shut to everybody passes the assertion below "
        "perfectly, and this test would then be reporting a savepoint guard that does not exist."
    )
    assert audit_rows_with_id(migrated_engine, revealable.audit_key, honest_id) == 1, (
        "The second connection cannot see the `audit_log` row of a reveal committed on the Care "
        "connection a moment ago, so its silence about the savepoint record below would mean "
        "nothing."
    )

    savepoint = caller.begin_nested()
    inside_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, (
        f"The recording call was refused inside a savepoint: {refused}. The ticket asks for the "
        "*reveal* to refuse a record that is not committed; refusing to record inside a savepoint "
        "would be a different design, and one that a caller defeats by not opening a savepoint. "
        "If that refusal is deliberate, it is an interface question for the ticket."
    )
    savepoint.commit()

    rows, failure = reveal(caller, inside_id)
    kept = identity_in(rows)
    caller.rollback()

    surviving = audit_rows_with_id(migrated_engine, revealable.audit_key, inside_id)
    took_a_name = revealable.identity_name in kept or revealable.identity_email in kept

    assert surviving == 1 or not took_a_name, (
        f"A `pulse_care` caller wrapped the recording call in a `SAVEPOINT`, released it, obtained "
        f"{sorted(kept)}, and rolled the top-level transaction back. From a second connection, "
        f"`{AUDIT_TABLE}` holds {surviving} row(s) for that record.\n\n"
        "This is the near miss E0-26 names. A guard comparing the audit row's `xmin` against the "
        "current transaction reads the subtransaction id a savepoint gave the row, decides it "
        "belongs to somebody else, and opens the door — while the same guard correctly refuses the "
        "plain, savepoint-free case that "
        "`test_a_caller_that_rolls_back_keeps_no_name_it_is_not_recorded_as_having_taken` makes. "
        "The ticket: 'whatever is compared has to be a value that a savepoint cannot change.'\n\n"
        "A savepoint is not an exotic thing for a caller to open: SQLAlchemy's `begin_nested`, "
        "`plpgsql`'s own `BEGIN … EXCEPTION` block and psql's `\\set ON_ERROR_ROLLBACK` all open "
        "one, so this is reachable without anybody intending it."
    )


@pytest.mark.invariant
def test_the_reveal_raises_for_an_uncommitted_record_rather_than_returning_no_rows(
    care_connections: Any, revealable: Revealable, reveal_interface: Any
) -> None:
    """Two different answers must not arrive looking the same.

    The ticket is explicit, and it is a criterion rather than a preference: the
    reveal "**raises** where the record is not committed, rather than returning
    zero rows. Zero rows already means 'this student has no identity row', which is
    a legitimate answer the service returns as `None`, and the two must not arrive
    looking the same."

    So this asserts the refusal is a raise. Its pair is
    `test_a_student_with_no_identity_row_gets_no_rows_and_no_refusal`, which asserts
    the other answer is not one — and the two together are the whole of the
    distinction. Either alone is satisfied by an implementation that gives both
    cases the same answer.

    **The control is the same call one commit later**, on the same connection with
    the same record id, which is what tells "this record is not committed" apart
    from "this function raises for everything". It runs second on purpose: the
    thing under test is a record that has *never* been committed, and committing
    first would leave nothing to assert.

    **The mutation it exists to survive**: writing the uncommitted-record branch as
    `RETURN;` instead of `RAISE EXCEPTION`. The caller then obtains no identity, so
    `test_a_caller_that_rolls_back_keeps_no_name_it_is_not_recorded_as_having_taken`
    stays green — and §6.2's queue reports "this student has no identity on file"
    for a reveal that was actually refused, which is a wrong answer rather than a
    refusal.
    """
    caller = care_connections()

    reveal_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, f"The recording call was refused for a Care actor: {refused}."

    rows, failure = reveal(caller, reveal_id)

    assert failure is not None, (
        f"`public.{REVEAL_FUNCTION}` answered {rows} for a record its caller has not committed, "
        "rather than raising. The ticket asks for a raise here in as many words, because zero rows "
        "is already the answer for a student with no `user_identity` row — a legitimate result the "
        "service hands back as `None` — and §6.2's queue would show 'no identity on file' for a "
        "call that was in fact refused. A refusal that is indistinguishable from an absence is a "
        "wrong answer wearing the right one's clothes."
    )

    caller.rollback()
    committed_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, f"The control's recording call was refused: {refused}."
    caller.commit()
    rows, failure = reveal(caller, committed_id)
    caller.commit()
    assert failure is None and revealable.identity_name in identity_in(rows), (
        f"The control failed: with the record committed, the reveal answered {rows} (error: "
        f"{failure}) rather than the seeded {revealable.identity_name!r}. So the raise above is "
        "not attributable to the record being uncommitted — a function that raises for every "
        "record satisfies that assertion and closes the Care door, which §4 and §6.2 require to "
        "stay open."
    )


def test_a_student_with_no_identity_row_gets_no_rows_and_no_refusal(
    care_connections: Any, committed_rows: Any, revealable: Revealable, reveal_interface: Any
) -> None:
    """The legitimate empty answer, which must not be dressed up as a refusal.

    The other half of the distinction the ticket draws: zero rows means "this
    student has no identity row", and `services/safety.py` hands that back as
    `None`. It is not an error and the Care queue has to be able to tell it from
    one — a student who launched the tool but whose identity was never stored is an
    ordinary state, not a failure.

    **The control is the same call for a student who does have an identity row**,
    made on the same connection, which is what tells "this student has no identity"
    apart from "this reveal returns nothing for anybody".

    **The mutation it exists to survive**: reading the identity with `INTO STRICT`,
    or adding `IF NOT FOUND THEN RAISE`. Both are the natural way to write the
    lookup, both leave every other test in this file green, and both collapse the
    two answers `test_the_reveal_raises_for_an_uncommitted_record_rather_than_
    returning_no_rows` exists to keep apart.
    """
    nameless_user = seed_a_student_with_no_identity_row(committed_rows)
    caller = care_connections()

    control_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, f"The control's recording call was refused: {refused}."
    caller.commit()
    control_rows, control_failure = reveal(caller, control_id)
    caller.commit()
    assert control_failure is None and revealable.identity_name in identity_in(control_rows), (
        f"The control failed: a student who does have a `user_identity` row came back as "
        f"{control_rows} (error: {control_failure}). The empty answer asserted below would then be "
        "this function returning nothing for everybody."
    )

    reveal_id, refused = record(caller, actor=revealable.care_person, subject=nameless_user)
    assert refused is None, (
        f"`public.{RECORD_FUNCTION}` refused to record a reveal of a student who has no "
        f"`user_identity` row: {refused}. The ticket has the reveal answer zero rows for that "
        "student, which it cannot do unless the record exists — so recording has to succeed here. "
        "A record that validated the subject's identity row would also be a second read of "
        "`user_identity` outside the audited call."
    )
    caller.commit()
    rows, failure = reveal(caller, reveal_id)
    caller.commit()

    assert failure is None, (
        f"`public.{REVEAL_FUNCTION}` raised for a student with no `user_identity` row: {failure}. "
        "That is a legitimate empty answer, which the service returns as `None`, and the ticket "
        "reserves the raise for a record that is not committed. Collapsing the two makes a missing "
        "identity indistinguishable from a refused call at exactly the moment §6.2's queue needs "
        "to tell them apart."
    )
    assert rows == [], (
        f"`public.{REVEAL_FUNCTION}` answered {rows} for a student with no `user_identity` row. "
        "There is no name on file to return, so anything here is invented, borrowed from another "
        "student, or the student's own key handed back as though it were an identity."
    )


def test_a_student_whose_identity_carries_no_address_still_comes_back_with_the_name(
    care_connections: Any, committed_rows: Any, revealable: Revealable, reveal_interface: Any
) -> None:
    """Case 2: an identity row with a name and no address is a whole answer.

    `RevealedIdentity.identity_email` is legitimately optional — NRPS releases an
    address only where the platform is configured to — so a student with a name and
    no address is an ordinary state of the data, and §6.2's queue has a name to act
    on. The reveal answers **one row whose address is null**, and that is a third
    answer, distinct from both of the two the ticket separates:

      - zero rows means no `user_identity` row exists at all, which
        `test_a_student_with_no_identity_row_gets_no_rows_and_no_refusal` holds;
      - a raise means the record is not committed, which
        `test_the_reveal_raises_for_an_uncommitted_record_rather_than_returning_no_rows`
        holds.

    Collapsing this one into the first loses a name Care staff are entitled to and
    would have acted on.

    **This test exists because seeding an address took its coverage away.** Until
    the address became an explicit override, every seeded row carried a null one,
    and the honest path's `identity_email` assertion was `None == None` — case 2 was
    covered by accident and asserted by nothing (`docs/MISTAKES.md` entry 3). It is
    somebody's subject on purpose now.

    **The control is the same call for the student who does have an address**, made
    first on the same connection, so the null below is attributable to this
    student's data rather than to a reveal that nulls the column for everybody.

    **The mutation it exists to survive**: adding `AND identity_email IS NOT NULL`
    to the identity read — the shape that arrives when somebody makes the reveal
    answer only "complete" identities. It turns a student with a name and no address
    into the same zero rows as a student with no identity row at all, and every
    other test in this file stays green.
    """
    addressless_user, addressless_name = seed_a_student_with_no_address(committed_rows)
    caller = care_connections()

    control_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, f"The control's recording call was refused: {refused}."
    caller.commit()
    control_rows, control_failure = reveal(caller, control_id)
    caller.commit()
    assert control_failure is None and len(control_rows) == 1, (
        f"The control failed: the student who does have an address came back as {control_rows} "
        f"(error: {control_failure}). The null asserted below would then be this reveal answering "
        "nothing useful for anybody."
    )
    assert dict(control_rows[0])["identity_email"] == revealable.identity_email, (
        f"The control failed: the student seeded with {revealable.identity_email!r} came back "
        f"carrying {dict(control_rows[0])['identity_email']!r}. A reveal that nulls this column "
        "for every student satisfies the assertion below perfectly."
    )

    reveal_id, refused = record(caller, actor=revealable.care_person, subject=addressless_user)
    assert refused is None, (
        f"`public.{RECORD_FUNCTION}` refused to record a reveal of a student whose identity row "
        f"carries no address: {refused}. Whether an address was released by the platform is not a "
        "question about whether a reveal may be recorded."
    )
    caller.commit()
    rows, failure = reveal(caller, reveal_id)
    caller.commit()

    assert failure is None, (
        f"`public.{REVEAL_FUNCTION}` raised for a student whose identity row carries a name and no "
        f"address: {failure}. The ticket reserves the raise for a record that is not committed, "
        "and this record was committed one transaction ago. An optional column being absent is not "
        "an error."
    )
    assert len(rows) == 1, (
        f"`public.{REVEAL_FUNCTION}` answered {len(rows)} rows for a student who has an identity "
        f"row carrying the name {addressless_name!r}. Zero rows is the answer for a student with "
        "no identity row at all, and answering it here loses a name §6.2's queue is entitled to "
        "act on — the likeliest cause is the identity read requiring an address to be present."
    )

    returned = dict(rows[0])
    assert returned["identity_name"] == addressless_name, (
        f"The reveal answered `identity_name` = {returned['identity_name']!r} for a student seeded "
        f"as {addressless_name!r}."
    )
    assert returned["identity_email"] is None, (
        f"The reveal answered `identity_email` = {returned['identity_email']!r} for a student "
        "whose `user_identity` row carries no address. An invented value, an empty string standing "
        "in for a null, or another student's address are each worse than the null: §6.2's Care "
        "staff would act on it."
    )


# ---------------------------------------------------------------------------
# Who may open the door, checked when the record is written and again when it is
# spent.
# ---------------------------------------------------------------------------


@pytest.mark.invariant
def test_recording_a_reveal_refuses_an_actor_with_no_live_care_assignment(
    care_connections: Any, migrated_engine: Any, revealable: Revealable, reveal_interface: Any
) -> None:
    """The check E0-10 put in the function does not weaken because the door grew a second half.

    E0-10 settled that the acting person is verified in two places: the
    `SECURITY DEFINER` function checks a live `CARE` assignment itself, and
    `services/safety.py` checks independently before calling it. The ticket keeps
    that unchanged — "`record_identity_reveal` refuses an actor with no live `CARE`
    assignment, exactly as the old function did" — and moves it to the first of the
    two calls, which is the one a caller reaches first.

    **The control is the same call with the Care actor**, run first on the same
    connection with the same student, which is what tells "this actor is refused"
    apart from "this function refuses everybody", from a `pulse_care` role that
    holds no `EXECUTE`, and from a database that has stopped working. Its record id
    is then required to name a committed `audit_log` row, which is what says the
    call recorded something rather than answering a uuid it invented.

    **There is deliberately no "the refused call wrote no row" assertion, because
    it could not fail.** A `RAISE` aborts the caller's transaction, so a row
    inserted before the check is discarded by the caller's own `ROLLBACK` whatever
    the implementation did — the count would be equal for a function that checks
    first and for one that checks last, and an assertion that cannot fail reads as
    thoroughness while proving nothing (`docs/MISTAKES.md` entry 3, the fourth
    case). Ordering the check before the insert is worth doing and is not
    observable from here; only a record written over a second connection would
    make it so, and the ticket rejects that mechanism.

    **"Never reaches identity" is structural and is asserted next door**, in
    `test_the_recording_call_hands_back_an_identifier_and_never_identity`: the
    recording call is declared `RETURNS uuid`, so there is no path on which it can
    hand back a name whatever it does internally. This test is the behavioural
    half, and neither stands in for the other (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: deleting the `CARE` assignment check
    from `record_identity_reveal` — one `IF NOT EXISTS … RAISE`. The reveal's own
    re-check is not a substitute, because it reads the actor *out of the record*
    the deleted check would have refused to write.
    """
    caller = care_connections()

    permitted_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, (
        f"The control failed: `public.{RECORD_FUNCTION}` refused a person holding a live `CARE` "
        f"assignment — {refused}. §4 and §6.2 open this door deliberately, and a door shut to "
        "everybody satisfies the refusal below without any check existing."
    )
    caller.commit()

    assert audit_rows_with_id(migrated_engine, revealable.audit_key, permitted_id) == 1, (
        f"`public.{RECORD_FUNCTION}` returned an id that names no committed `{AUDIT_TABLE}` row, "
        "read from a second connection. The ticket has it return 'the audit_log row's id', so a "
        "call that answers a uuid without recording anything would satisfy the control above and "
        "leave the refusal below contrasted with a call that also recorded nothing."
    )

    _, failure = record(
        caller, actor=revealable.reporting_person, subject=revealable.subject_user_id
    )
    caller.rollback()

    assert failure is not None, (
        f"`public.{RECORD_FUNCTION}` accepted a person holding a lead-faculty assignment and no "
        "`CARE` assignment — the same call it accepted a moment ago for somebody who does hold "
        "one. The function is `SECURITY DEFINER`, so the acting person's assignment is the only "
        "thing between a `pulse_care` connection and any student's name: E0-10's design is that "
        "'a caller reaching the function by any other route still gets nothing', and a recording "
        "call that writes the row is the route that then opens the reveal.\n\n"
        "Returning NULL rather than raising fails here too, and deliberately: the reveal reads its "
        "subject and actor out of a record, so a recording call that answers quietly leaves the "
        "caller holding nothing rather than being told it was refused — and §6.2's queue would "
        "show that as a system fault rather than as a person without a `CARE` assignment."
    )


@pytest.mark.invariant
def test_the_reveal_refuses_a_record_whose_actor_no_longer_holds_care(
    care_connections: Any, committed_rows: Any, revealable: Revealable, reveal_interface: Any
) -> None:
    """The second half of the door re-checks the actor; a committed record is not a ticket.

    The ticket: the reveal "re-checks that the record's actor still holds `CARE`…
    The two-places rule E0-10 states does not weaken because the door grew a second
    half." Without it a committed record is a bearer token — recorded while the
    actor held the assignment, spent after it was revoked, and §2.1 has no
    end-dating, so revocation is the deletion of the row.

    **Two records are committed before anything is revoked**, and the control
    spends the first while the assignment is live. Doing it that way keeps this
    test silent on a question the ticket leaves open — whether a record may be
    spent more than once — which spending one record twice would settle here by
    accident.

    **The refusal is a raise, and that is settled rather than assumed.** The
    ticket as first written said the reveal raises for a record that is not
    committed and said nothing about a record whose actor has since lost `CARE`, so
    this test accepted either a raise or an empty result. Todd settled it as a raise
    on 2026-08-20, for the reason the ticket already gives one paragraph earlier: an
    empty result is the value the service turns into `None`, so a revoked actor
    would reach §6.2's queue as "this student has no identity on file" — a wrong
    answer rather than a refusal, and about a student the queue is open on. The
    assertion below is therefore a denial and not an absence, which is also what
    SPEC §4.1 work is held to.

    **The mutation it exists to survive**: deleting the actor re-check from
    `reveal_student_identity` and leaving it only in `record_identity_reveal`. That
    reads as removing a duplicated condition, and every other test in this file
    stays green.
    """
    caller = care_connections()

    control_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, f"The control's recording call was refused: {refused}."
    revoked_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, f"The second recording call was refused: {refused}."
    caller.commit()

    control_rows, control_failure = reveal(caller, control_id)
    caller.commit()
    assert control_failure is None and revealable.identity_name in identity_in(control_rows), (
        f"The control failed: while the `CARE` assignment was live the reveal answered "
        f"{control_rows} (error: {control_failure}) rather than the seeded "
        f"{revealable.identity_name!r}. The refusal below would then be about a door that is shut "
        "to everybody."
    )

    assignments = committed_rows.tables["role_assignment"]
    key = committed_rows.graph.assignment_key
    committed_rows.session.execute(
        assignments.delete().where(assignments.c[key] == revealable.care_assignment_id)
    )
    committed_rows.commit()

    rows, failure = reveal(caller, revoked_id)
    kept = identity_in(rows)
    caller.rollback()

    assert failure is not None, (
        f"`public.{REVEAL_FUNCTION}` answered {sorted(kept)} against a record whose actor no "
        "longer holds a `CARE` assignment — the assignment was deleted between the control call "
        "above, which returned that same identity, and this one. A committed record is then a "
        "bearer token: recorded while the actor was Care staff and spendable afterwards by "
        "whoever holds the `pulse_care` credential. §2.1 has no end-dating on an assignment, so "
        "deleting the row is what revoking it means today, and E0-10's rule that the function "
        "verifies a live assignment itself has to survive the door being split in two.\n\n"
        "**An empty result fails here too, and that is the settled reading rather than this "
        "file's.** Zero rows is the answer for a student with no `user_identity` row, which the "
        "service hands back as `None`, so a revoked actor would reach §6.2's queue as 'no identity "
        "on file' about a student the queue is open on. The ticket refuses that collision for the "
        "uncommitted-record case in as many words, and it holds here for the same reason."
    )


def test_the_reveal_returns_the_student_named_in_the_committed_record(
    care_connections: Any, committed_rows: Any, revealable: Revealable, reveal_interface: Any
) -> None:
    """The subject comes from the record, and it is the right one.

    The ticket's reason for the reveal taking only a record id is that "the subject
    is read from the committed record and cannot be substituted by the caller".
    `test_the_reveal_takes_the_records_identifier_and_nothing_else` asserts that
    there is no second argument to substitute with; this asserts the other half,
    which is that the subject actually read is the one the record names.

    **Two students, both with identities on file**, because "it returned a name"
    is satisfied by a reveal that returns whichever identity row it finds first. A
    single seeded student cannot tell the two apart, and with one row in the table
    an unfiltered read is indistinguishable from a correct one.

    **The mutation it exists to survive**: dropping the `WHERE` that ties the
    identity read to the record's subject — the shape that returns the newest, the
    first, or every identity row. With one student seeded that mutation passes; the
    second student is what kills it.
    """
    other_user, other_name, other_email = seed_a_second_student(committed_rows)
    assert other_user != revealable.subject_user_id, (
        "The two seeded students are one student, so the reveal cannot return the wrong one and "
        "the assertion below could not fail."
    )
    theirs = {other_name, other_email}
    ours = {revealable.identity_name, revealable.identity_email}
    assert all(theirs) and all(ours), (
        f"One of the four seeded values is empty — this student carries {theirs} and the recorded "
        f"one carries {ours}. The leak assertion below asks whether the other student's values "
        "appear in what came back, and `None` never appears in a set of strings, so a null would "
        "make that half of it true whatever the reveal returned. Both students are seeded with an "
        "address on purpose; the student who legitimately has none is "
        "`test_a_student_whose_identity_carries_no_address_still_comes_back_with_the_name`'s."
    )
    assert theirs.isdisjoint(ours), (
        f"The second student was seeded with an identity that shares a value with the first — "
        f"{other_name!r}/{other_email!r} against {revealable.identity_name!r}/"
        f"{revealable.identity_email!r}. The assertion below distinguishes the two students by "
        "their values, so a collision would make a correct reveal look like a leak. The seeding "
        "helper in `tests/conftest.py` invents a fresh value per row; if this fires, that is where "
        "it is diagnosed rather than here."
    )
    caller = care_connections()

    reveal_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, f"The recording call was refused: {refused}."
    caller.commit()
    rows, failure = reveal(caller, reveal_id)
    caller.commit()

    assert failure is None, f"The reveal raised against a committed record: {failure}."
    returned = identity_in(rows)
    assert revealable.identity_name in returned and revealable.identity_email in returned, (
        f"The record named the student carrying {revealable.identity_name!r} and "
        f"{revealable.identity_email!r}, and the reveal answered {sorted(returned)}. Without the "
        "recorded student's own identity coming back, the assertion below — that the other "
        "student's does not — would be satisfied by a reveal that returns nothing at all."
    )
    assert other_name not in returned and other_email not in returned, (
        f"The reveal answered {sorted(returned)} for a record naming a different student. "
        f"{other_name!r} belongs to the second student seeded by this test, who is the subject of "
        "no record here. §4's audit rule is that the record says who was accessed; a reveal that "
        "returns somebody the record does not name makes the audit row a description of a "
        "different event from the one that happened."
    )


def test_the_honest_path_returns_the_identity_and_leaves_exactly_one_audit_row(
    care_connections: Any, migrated_engine: Any, revealable: Revealable, reveal_interface: Any
) -> None:
    """§6.2's one-click action, end to end, over the shape the ticket settles.

    The Care path is a requirement rather than an oversight — §4 and §6.2 make
    re-identification the one legitimate route to identity, and every refusal in
    this file is silent about a door that has been closed. So this is the criterion
    in its own right, and it is also the **inversion** of
    `test_a_record_written_inside_a_savepoint_does_not_count_as_committed`: it
    records, commits and reveals **on one connection**, which is what
    `services/safety.py` does ("it records, commits, and then reveals in a second
    transaction"). An implementation that refuses any record written by the
    connection now asking passes the savepoint test and fails this one.

    **Exactly one audit row**, counted from a second connection across the whole
    exchange. Over-recording is the direction the ticket accepts and states —
    "a caller that commits a record and then never reveals leaves a row saying an
    access was authorised" — but *two* rows for one access is a different thing:
    §6.2's periodic review counts rows as accesses, and a queue that logged twice
    per reveal would read as twice the traffic.

    **Both values, by the column names the ticket's signature gives them.** A
    reveal that answers the name in both columns, or a row of nulls, satisfies "it
    returned something" and reveals nobody.

    **The mutation it exists to survive**: leaving E0-10's `INSERT INTO audit_log`
    inside `reveal_student_identity` beside the new committed record. That is the
    likeliest edit of all — the old body is being rewritten rather than replaced,
    the caller still gets the right name, and every other test in this file stays
    green while every reveal writes two rows.
    """
    caller = care_connections()
    before = audit_row_total(migrated_engine)

    reveal_id, refused = record(
        caller, actor=revealable.care_person, subject=revealable.subject_user_id
    )
    assert refused is None, (
        f"`public.{RECORD_FUNCTION}` refused a person holding a live `CARE` assignment: {refused}. "
        "§6.2 gives Care staff 'a plain, one-click procedural action', and this is the first half "
        "of it."
    )
    caller.commit()
    rows, failure = reveal(caller, reveal_id)
    caller.commit()
    after = audit_row_total(migrated_engine)

    assert failure is None, (
        f"`public.{REVEAL_FUNCTION}` raised against a record committed on this same connection one "
        f"transaction earlier: {failure}. That is the honest path — `services/safety.py` 'records, "
        "commits, and then reveals in a second transaction' on the Care pool — so a guard that "
        "refuses it has closed the door §4 and §6.2 keep open rather than closing the gap this "
        "ticket is about."
    )
    assert len(rows) == 1, (
        f"`public.{REVEAL_FUNCTION}` answered {len(rows)} rows for one record: {rows}. Its "
        "signature is `RETURNS TABLE (identity_name text, identity_email text)` against a record "
        "naming one student, and `user_identity` holds one row per user."
    )

    returned = dict(rows[0])
    missing = [column for column in IDENTITY_COLUMNS if column not in returned]
    assert not missing, (
        f"The reveal's result has columns {sorted(returned)} and is missing {missing}. The "
        f"ticket's signature names them: {THE_INTERFACE}"
    )
    assert returned["identity_name"] == revealable.identity_name, (
        f"The reveal answered `identity_name` = {returned['identity_name']!r} for a student seeded "
        f"as {revealable.identity_name!r}."
    )
    assert returned["identity_email"] == revealable.identity_email, (
        f"The reveal answered `identity_email` = {returned['identity_email']!r} for a student "
        f"seeded as {revealable.identity_email!r}. Asserted separately from the name because a "
        "reveal that returns the name in both columns satisfies any check that only asks whether "
        "the seeded strings came back."
    )

    assert audit_rows_with_id(migrated_engine, revealable.audit_key, reveal_id) == 1, (
        f"No committed `{AUDIT_TABLE}` row carries the id `public.{RECORD_FUNCTION}` returned, "
        "read from a second connection after the caller committed. §4 requires that every identity "
        "access is audit-logged, and this is the whole of the record."
    )
    assert after - before == 1, (
        f"One reveal moved the committed `{AUDIT_TABLE}` total by {after - before} rows, from "
        f"{before} to {after}. Exactly one is the criterion: §6.2's review outside the Care office "
        "reads each row as an access, so two rows per reveal double what that review sees. The "
        "likeliest cause is E0-10's own `INSERT` still standing inside "
        f"`public.{REVEAL_FUNCTION}` beside the record the caller now commits for itself."
    )


# ---------------------------------------------------------------------------
# The door's shape, out of the catalog. Where two mechanisms could produce the
# same behaviour, a behavioural test cannot say which one did
# (`docs/MISTAKES.md` entry 3), and the old three-argument door is invisible to
# every test above.
# ---------------------------------------------------------------------------


def test_the_reveal_takes_the_records_identifier_and_nothing_else(
    reveal_interface: dict[str, list[Any]],
) -> None:
    """A door that still opens the old way is not closed.

    Two criteria in one shape, both spelled by the ticket. The reveal "takes only
    the record's id, so the subject is read from the committed record and cannot be
    substituted by the caller"; and "the three-argument `reveal_student_identity`
    is **dropped**, not kept alongside".

    The second is the one nothing else here can see. Postgres overloads on
    argument types, so a migration that creates the new one-argument function and
    forgets to `DROP` the old three-argument one leaves both callable — every
    behavioural test in this file passes, because every one of them calls the new
    signature, and the exact `BEGIN; SELECT …; ROLLBACK;` that E0-10's review
    measured still works against the old one.

    **Vacuity has no route in**: `reveal_interface` has already failed if no
    function of this name exists, so "there is exactly one overload" cannot be true
    here of a schema that has no reveal at all.

    **Two faults reach this test and they get two messages**, because they are
    repaired differently. A *second* overload means the migration created the new
    function and did not `DROP` the old one, and both doors are open. A *single*
    overload of the wrong shape means there is one door and it is not the one the
    ticket settles — most usefully `reveal_student_identity(text)`, which takes the
    record's id as a string and which `pronargs` alone would wave through.

    **The type is compared and the parameter's name is not**, which is the repair
    ruled in `docs/disputes/E0-26-01.md`. This assertion read
    `pg_get_function_identity_arguments`, which renders `in_reveal_id uuid`, so it
    refused the exact signature the ticket writes and could only ever have been
    satisfied by an anonymous parameter — a workaround the implementer was right to
    decline. `argument_types` in the `FUNCTIONS` query carries types and nothing
    else; the comment above it holds the two spellings that look equivalent and are
    not. **Do not respell this predicate against `signature`**: `regprocedure`
    schema-qualifies depending on `search_path`, which makes it right for the
    message below and wrong for the condition.

    **The mutation it exists to survive**: a migration whose `upgrade()` creates
    the one-argument function without dropping the three-argument one. `pronargs`
    counts input arguments only — it is 1 for the reveal despite its `RETURNS
    TABLE` columns, and 3 for the old door — so the old function fails the arity
    half on its own. The `downgrade()` half of the round trip is deliberately *not*
    claimed here: this test reads post-`upgrade` catalog state and never runs a
    downgrade, and a docstring naming a mutation it does not exercise reads as
    coverage. `test_identity_grants.py` is where downgrade round trips live.
    """
    overloads = reveal_interface[REVEAL_FUNCTION]

    assert len(overloads) == 1, (
        f"`public` carries {len(overloads)} functions called `{REVEAL_FUNCTION}`: "
        f"{[row['signature'] for row in overloads]}. Every one of them is a door, and the "
        "three-argument form is the one E0-26 item 1 exists to close: it takes the subject from "
        "its caller, so the caller chooses whose name comes back, and the record it writes is the "
        "caller's to roll back. Postgres overloads on argument types, so creating the new function "
        "does not replace the old one — the migration has to `DROP` it by its full signature.\n\n"
        "Every behavioural test in this file passes with both doors standing, because every one of "
        "them calls the new signature. This is the only assertion that looks at what else is "
        f"there.\n\n{THE_INTERFACE}"
    )

    misshapen = [
        f"{row['signature']} takes {row['argument_count']} argument(s) of type "
        f"({row['argument_types'] or 'none'})"
        for row in overloads
        if row["argument_count"] != 1 or row["argument_types"].strip().lower() != "uuid"
    ]
    assert not misshapen, (
        f"The one function called `{REVEAL_FUNCTION}` is not the door the ticket settles: "
        f"{misshapen}. It takes exactly one argument and that argument is a `uuid` — the id of a "
        "committed record, which is what makes the subject something the caller cannot "
        "substitute.\n\n"
        "The type is asserted and not only the count, because `reveal_student_identity(text)` has "
        "one argument too. That is the shape that arrives when somebody later takes the record's "
        "id as a string, and it widens what a caller may hand in from 'a uuid this database "
        f"generated' to 'any text at all'.\n\n{THE_INTERFACE}"
    )

    not_definer = [row["signature"] for row in overloads if not row["security_definer"]]
    assert not not_definer, (
        f"{not_definer} is not `SECURITY DEFINER`. `pulse_care` holds no grant of any kind on "
        "`user_identity` (E0-10, ADR 0001), so a reveal that runs with the caller's privileges "
        "cannot read a name at all — and a door that returns nothing to everybody would satisfy "
        "several of the refusals in this file."
    )


def test_the_recording_call_hands_back_an_identifier_and_never_identity(
    reveal_interface: dict[str, list[Any]],
) -> None:
    """The first call returns the record's id "and nothing else — no identity, on any path".

    The ticket's words, and they are a structural claim rather than a behavioural
    one: a function declared `RETURNS uuid` cannot hand back a name whatever its
    body does. Asserting it out of the catalog is what makes it hold on paths no
    test exercises — the refused path, the path where the student has no identity
    row, and whatever E10 adds.

    It matters because the split is what closes the gap. If the recording call
    could also return identity, a caller would have no reason to make the second
    call at all, and the whole exchange would be back inside one transaction the
    caller can roll back.

    `OUT` and `INOUT` parameters are checked with the return type because they are
    the other way a function hands a value back, and `pg_get_function_result` on a
    function with `OUT` parameters describes them rather than saying `uuid` — so a
    single equality against `'uuid'` would already catch it, and the mode check is
    what makes the failure message say which of the two happened.

    **Vacuity has no route in**: `reveal_interface` has already failed if no
    function of this name exists.

    **The mutation it exists to survive**: widening the recording call to
    `RETURNS TABLE (reveal_id uuid, identity_name text, identity_email text)` so
    the queue can make one round trip instead of two. Every behavioural test in
    this file still passes, because they all call the reveal afterwards anyway.
    """
    overloads = reveal_interface[RECORD_FUNCTION]

    handing_back_more = [
        f"{row['signature']} -> {row['result']}"
        for row in overloads
        if row["result"].strip().lower() != "uuid" or row["returns_a_set"]
    ]
    assert not handing_back_more, (
        f"`public.{RECORD_FUNCTION}` is declared {handing_back_more}. The ticket has it return the "
        "`audit_log` row's id 'and nothing else — no identity, on any path'. A recording call that "
        "also returns the name removes the caller's reason to make the second call, and the whole "
        f"exchange is back inside one transaction the caller can roll back.\n\n{THE_INTERFACE}"
    )

    output_parameters = [
        f"{row['signature']} (argument modes {row['argument_modes']})"
        for row in overloads
        if any(mode in {"o", "b", "t"} for mode in row["argument_modes"].split(","))
    ]
    assert not output_parameters, (
        f"`public.{RECORD_FUNCTION}` declares {output_parameters}. An `OUT`, `INOUT` or `TABLE` "
        "parameter is the other way a function hands a value back, and it is how a name would "
        "arrive from a call whose declared return type still reads as `uuid`."
    )
