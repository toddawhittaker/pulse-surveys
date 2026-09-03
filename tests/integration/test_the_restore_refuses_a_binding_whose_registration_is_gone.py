"""E2-03 — the restore refuses with a sentence when the registration is gone.

`b8c41f7d2e05` preserves `section`'s `(lti_deployment_id, lms_context_id)` pair
across its own downgrade and restores it on the way back up. The carried E1
finding is about the one state that restore cannot honour: an operator
downgrades below the revision, deletes the registration those preserved rows
point at, and upgrades again. The restore hands a dead deployment to the foreign
key, and what the operator gets is Postgres saying a constraint was violated —
not the actionable refusal every other migration in this family writes.

**The outcome is already right and is not what this file is about.** The
transaction rolls back, nothing is stamped, and the preserved rows survive for a
retry. The ticket's first criterion is the *message*: the path "refuses with a
sentence naming the preserved table", and the preserved rows "still survive for
a retry". The first half is asserted on what the failure said; the second half is
not asserted as a phrase at all, it is executed — the registration is put back
and the same upgrade is run again, and every section has to come back carrying
its own pair.

**Three assertions separate a refusal from the raw violation, and each one is
here because the others can be satisfied by the wrong thing.**

  - The failure's SQLSTATE is not `23503`, and its text does not carry Postgres's
    own `violates foreign key constraint` phrase. That is the finding itself,
    stated in the two ways it can be spelled, and it is what is red today.
  - The text names `section_binding_preserved`. On its own that would be the
    weakest of the three: a `DatabaseError` renders the statement that raised it,
    so a guard that read the preserved table and then raised an anonymous
    sentence would print the table's name in the echo and pass
    (`docs/MISTAKES.md` entry 3, and the same trap
    `test_the_upgrade_refuses_a_stored_edge_that_does_not_climb.py` avoids by
    asserting a row's uuid). So nothing here reads the rendered statement:
    `what_the_failure_said` reads the server's *message* fields and nothing
    else, and the two reader controls at the bottom of this file are what say it
    can do that.
  - The text names the ticket and the table whose row is missing, because a
    refusal an operator cannot act on is the defect wearing a different message.

**The pair, and which way each half fails.**
`test_the_same_upgrade_completes_when_every_preserved_binding_still_has_its_registration`
is the identical sequence with one statement removed — the `DELETE` — and it has
to complete. Without it every assertion above is satisfied by a guard that
refuses every upgrade, which is a revision no deployment can apply at all.
`test_the_preserved_bindings_come_back_when_the_registration_is_restored...` is
the third direction: refused, repaired, run again, and the bindings are the ones
that were seeded.

**What a red means, per test, and it is not the same answer for all of them.**
The two reader controls and the healthy round trip are green on the tree as it
stands today, before any guard exists: a red in them *now* means this module's
own machinery is broken rather than the migration. After the guard lands they
mean the opposite — a healthy round trip that refuses is a guard that over-fires,
which is a defect in the code and not in this file.

**Each test migrates a database of its own.** `empty_database` is a second
database in the same container, created for one test and dropped after, so the
downgrades here cannot touch the session database every other integration test
reads (`docs/MISTAKES.md` entry 12).

**Seeding happens at head and the database is walked back down afterwards**, for
the reason `seed_row`'s own docstring gives: its insert and its `RETURNING`
clause are built from `Base.metadata`, so it can only write to a database at
head (`docs/disputes/E1-10-01.md`). `head` appears here only as the name of the
schema today's models describe and is the subject of nothing.

**The helpers below are copies, and they are marked as copies.** `require_revision`,
`the_revision_below`, `migrate`, `session_on`, `bindings_on` and
`two_bound_sections` are `test_the_section_binding_survives_a_downgrade.py`'s;
`attempt_upgrade` and `version_stamped` are
`test_the_upgrade_refuses_a_stored_edge_that_does_not_climb.py`'s. Lifting the
set into `tests/fixtures/` would be the other answer to `docs/MISTAKES.md` entry
13 and it would edit two merged modules' imports for a ticket that is about an
error message, so the copies stay and say where they came from — as the four
copies of `seed_row` and the three of `require_revision` already in this suite
do. What is *not* a copy is everything from `what_the_failure_said` down: that
machinery is new here, and it ships with its own controls.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fixtures.supervision import require_table, seed_row, single_primary_key, sqlstate_of

pytestmark = pytest.mark.integration

# The revision under test — the file is `backend/migrations/versions/
# 20260826_b8c41f7d2e05_*.py`, and Alembic knows it by the bare identifier. Named
# rather than reached by a step from head, for the reason
# `docs/disputes/E0-11-02.md` gives: a position moves when a revision lands on
# top of it, and every assertion here is about this revision's upgrade.
BINDING_REVISION = "b8c41f7d2e05"

# Where the seeding happens, and **it is not a subject**. This name appears only
# in the upgrade call that puts the database into the shape `Base.metadata`
# describes, so that `seed_row` can write to it at all.
MODEL_SCHEMA = "head"

SECTION_TABLE = "section"
CONTEXT_ID_COLUMN = "lms_context_id"
DEPLOYMENT_COLUMN = "lti_deployment_id"

# The table a section's binding points at, and the row this file deletes. It is
# the registration the carried bullet says "no longer exists" in the sequence it
# describes: "downgrade below `b8c41f7d2e05`, delete the registration, upgrade
# back".
DEPLOYMENT_TABLE = "lti_deployment"

# Where the downgrade puts the pair it is about to drop, and the name the ticket
# requires the refusal to carry: criterion 1 is that the path "refuses with a
# sentence naming the preserved table". Spelled here once, so that a rename of
# the scratch table is a one-line change in this file and a visible one in the
# pull request.
PRESERVED_TABLE = "section_binding_preserved"

# The ticket, as the refusal is expected to name it. The other migrations in this
# family open their exceptions with their own ticket id, and an operator reading a
# failure at three in the morning gets the whole record from it.
TICKET = "E2-03"

# Postgres's own foreign-key violation, in the two ways it can be recognised: the
# SQLSTATE, which no wording change can move, and the phrase the server writes,
# which is what the carried finding quotes. Asserted absent, together, because
# that raw shape *is* the defect — the operator is told a constraint was violated
# instead of what to do about it.
FOREIGN_KEY_VIOLATION = "23503"
RAW_VIOLATION_PHRASE = "violates foreign key constraint"

# The two context identifiers seeded, one per section. This module's own, and
# distinct in every character, because a restore that put both pairs back on each
# other's rows holds exactly the right *set* of bindings.
FIRST_CONTEXT_ID = "e2-03-restore-context-alpha-4d19"
SECOND_CONTEXT_ID = "e2-03-restore-context-omega-b703"

# What the upgrade writes into `lms_context_id` for a section it finds unbound.
# Quoted from the E1-10 deferred item that measured it (`deferred.md`, item 3).
# A section carrying this shape after the retry is the strongest statement that
# the preserved rows did *not* survive the refusal — they were consumed, cleared
# or rolled away, and the upgrade then treated the section as one that had never
# been bound.
PRE_BINDING_PREFIX = "pre-binding-section-"

# The fields a server error carries that hold what somebody wrote, as psycopg
# spells them. Deliberately these three and not `str()` of the SQLAlchemy
# wrapper: that renders the statement as well, and a statement echo would satisfy
# every name assertion in this file on a refusal that named nothing
# (`docs/MISTAKES.md` entry 3). HINT is included because `RAISE EXCEPTION ...
# USING HINT` is a reasonable place for an implementer to put the half of the
# sentence that tells the operator what to do, and reading only the primary
# message would fail a correct implementation for where it put its words.
DIAGNOSTIC_FIELDS = ("message_primary", "message_detail", "message_hint")

# How far the exception chain is walked. A bound rather than `while` alone, so a
# self-referential `__context__` is a failed assertion rather than a hang.
CHAIN_LIMIT = 8


# ---------------------------------------------------------------------------
# Copies. Each names the module it came from; see the last paragraph of the
# module docstring for why they are copies.
# ---------------------------------------------------------------------------


def require_revision(config: Any, revision: str) -> str:
    """`revision`, after asking the script directory whether it still exists.

    A copy of `test_the_section_binding_survives_a_downgrade.py`'s. Resolved
    rather than handed straight to `command.upgrade`, so a constant left behind
    by a squash, a rebase or a renamed file fails with a message naming the
    ticket instead of with Alembic's own `Can't locate revision`, which reads
    like a broken environment.
    """
    from alembic.script import ScriptDirectory

    try:
        ScriptDirectory.from_config(config).get_revision(revision)
    except Exception as failure:
        pytest.fail(
            f"`{revision}` is not a revision in this tree: {failure!r}. That is the revision that "
            "adds `section`'s `(lti_deployment_id, lms_context_id)` binding, preserves the pair "
            "across its own downgrade and restores it on the way back up — the restore E2-03 is "
            "about. If it has been renumbered or squashed, the constant at the top of this file "
            "is the one place to change."
        )
    return revision


def the_revision_below(config: Any, revision: str) -> str:
    """What `revision` chains from, read off the migration itself.

    A copy of `test_the_section_binding_survives_a_downgrade.py`'s. The
    migration's own `down_revision` rather than a second constant here: a rebase
    that re-points it moves this test with it, and a copy in this file would be a
    record that goes on asserting something the change made false
    (`docs/MISTAKES.md` entry 1).
    """
    from alembic.script import ScriptDirectory

    parent = ScriptDirectory.from_config(config).get_revision(revision).down_revision
    if not isinstance(parent, str) or not parent:
        pytest.fail(
            f"Revision {revision} reports `down_revision = {parent!r}`, so this module cannot say "
            "what 'the revision below it' is. A tuple means a merge point and `None` means it is "
            "the base; either way the sequence this file drives — down below the binding "
            "revision, delete the registration, up again — has to be re-expressed against "
            "whatever the history now looks like, deliberately, rather than guessed at here."
        )
    return parent


def migrate(config: Any, direction: str, revision: str, what: str) -> None:
    """Run one Alembic command that has to complete, failing the test if it does not.

    A copy of `test_the_section_binding_survives_a_downgrade.py`'s. Used for the
    steps that are machinery. The upgrade under test is never run through this
    one — it goes through `attempt_upgrade` below, because whether it completes
    is the subject rather than a precondition.
    """
    from alembic import command

    run = command.upgrade if direction == "upgrade" else command.downgrade
    try:
        run(config, revision)
    except Exception as failure:
        pytest.fail(
            f"`alembic {direction} {revision}` did not complete ({what}): {failure!r}. Every "
            "assertion in this module is about a database that made the whole trip, so nothing "
            "after this point means anything."
        )


def attempt_upgrade(config: Any, revision: str) -> BaseException | None:
    """Run `alembic upgrade <revision>`; answer the failure it raised, or `None`.

    A copy of `test_the_upgrade_refuses_a_stored_edge_that_does_not_climb.py`'s,
    and it answers rather than asserting for the same reason: both outcomes are
    the subject of a test here. The upgrade must refuse the database whose
    registration was deleted, and must complete over the one where it is still
    there.
    """
    from alembic import command

    try:
        command.upgrade(config, revision)
    except Exception as failure:
        return failure
    return None


def version_stamped(database: Any) -> Any:
    """The revision Alembic records as applied, read on a connection of its own.

    A copy of `test_the_upgrade_refuses_a_stored_edge_that_does_not_climb.py`'s.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
    finally:
        engine.dispose()


@contextmanager
def session_on(database: Any) -> Iterator[Any]:
    """A committed session on `database`, opened and closed around one step.

    A copy of `test_the_section_binding_survives_a_downgrade.py`'s, and the third
    in this suite. Opened and closed around each migration step rather than held
    across one: an Alembic upgrade that alters a table takes locks a session idle
    inside a transaction can block, and a migration waiting on this test's own
    connection is a hang rather than a failure.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(database.superuser_url)
    try:
        session = Session(bind=engine)
        try:
            yield session
            session.commit()
        finally:
            session.close()
    finally:
        engine.dispose()


def bindings_on(database: Any, tables: dict[str, Any]) -> dict[Any, tuple[Any, Any]]:
    """Every section's `(lms_context_id, lti_deployment_id)`, keyed by its primary key.

    A copy of `test_the_section_binding_survives_a_downgrade.py`'s. A mapping
    rather than a list, because the whole question is which values are on which
    row: a restore that preserved both pairs and put them back on the wrong
    sections leaves any set comparison satisfied.
    """
    from sqlalchemy import select

    table = require_table(tables, SECTION_TABLE)
    key = single_primary_key(table)
    for column in (CONTEXT_ID_COLUMN, DEPLOYMENT_COLUMN):
        if column not in table.c:
            pytest.fail(
                f"`{SECTION_TABLE}` declares no `{column}` (it declares "
                f"{[one.name for one in table.columns]}). Revision {BINDING_REVISION} adds both "
                "halves of the binding and the model declares them; a name that has moved is a "
                "constant at the top of this file."
            )
    with session_on(database) as session:
        rows = session.execute(
            select(table.c[key], table.c[CONTEXT_ID_COLUMN], table.c[DEPLOYMENT_COLUMN])
        ).all()
    return {row[0]: (row[1], row[2]) for row in rows}


def two_bound_sections(database: Any, tables: dict[str, Any]) -> dict[Any, tuple[Any, Any]]:
    """Seed two sections whose bindings differ in both halves, and answer them.

    A copy of `test_the_section_binding_survives_a_downgrade.py`'s, and two
    sections rather than one is load-bearing *here* for a reason that module does
    not have. Only one of the two registrations is deleted, so the guard under
    test has to find the preserved rows that point at a deployment which is gone —
    not merely notice that the preserved table has rows in it, which is what a
    single-section fixture would let it get away with.

    Each section is built on a chain of its own, so each one's
    `lti_deployment_id` is a different `lti_deployment` row; only the institution
    is shared, which is the schema's own rule (`uq_institution_one_row`).
    """
    with session_on(database) as session:
        first = seed_row(
            session, tables, SECTION_TABLE, {}, **{CONTEXT_ID_COLUMN: FIRST_CONTEXT_ID}
        )
        second = seed_row(
            session, tables, SECTION_TABLE, {}, **{CONTEXT_ID_COLUMN: SECOND_CONTEXT_ID}
        )

    table = require_table(tables, SECTION_TABLE)
    key = single_primary_key(table)
    seeded = {row[key]: (row[CONTEXT_ID_COLUMN], row[DEPLOYMENT_COLUMN]) for row in (first, second)}

    assert len(seeded) == 2, (
        f"The two seeded sections share a primary key ({seeded}), so 'each row keeps its own "
        "binding' cannot be told from 'the two were swapped'."
    )
    deployments = [deployment for _, deployment in seeded.values()]
    assert len(set(deployments)) == 2 and all(deployments), (
        f"The two sections are bound to the deployments {deployments}. They have to differ and "
        "neither may be NULL: this file deletes one registration and leaves the other standing, "
        "so a fixture that pointed both sections at one deployment would make 'the guard found "
        "the dead reference' indistinguishable from 'the guard refuses whenever anything is "
        "preserved'."
    )
    return seeded


def assert_bindings_are_unchanged(
    after: dict[Any, tuple[Any, Any]], seeded: dict[Any, tuple[Any, Any]], what: str
) -> None:
    """Every seeded section still carries its own pair, byte for byte.

    Adapted from `test_the_section_binding_survives_a_downgrade.py`'s, with the
    messages rewritten for this file's sequence. Three failures are separated
    because they need different fixes: rows that are gone, rows whose values were
    invented by the backfill, and rows carrying the other section's pair.
    """
    missing = sorted(str(key) for key in seeded if key not in after)
    assert not missing, (
        f"After {what}, the sections {missing} are no longer in the database at all. The revision "
        "under test adds columns; it does not own the rows, and a guard that made the restore "
        "safe by removing what it could not restore is a worse defect than the message this "
        "ticket is about."
    )
    invented = sorted(
        str(key) for key in seeded if str(after[key][0] or "").startswith(PRE_BINDING_PREFIX)
    )
    assert not invented, (
        f"After {what}, the sections {invented} carry a `{CONTEXT_ID_COLUMN}` beginning "
        f"{PRE_BINDING_PREFIX!r} — the identifier the upgrade invents for a section it finds "
        "unbound. So the preserved rows did not survive: the refused attempt consumed, cleared or "
        "rolled them away, and the retry found nothing to restore from. That is the half of the "
        "carried finding this ticket is not allowed to break — 'the transaction rolls back and "
        "the preserved rows survive for a retry' — and it is worse than the raw message the "
        "ticket exists to replace, because the section is now bound to a context no platform ever "
        f"issued and every staff launch from the real one is refused. Stored now: {dict(after)}"
    )
    stored = {key: after.get(key) for key in seeded}
    assert {key: after[key] for key in seeded} == seeded, (
        f"After {what}, the sections do not carry the bindings they were seeded with.\n"
        f"  seeded: {seeded}\n"
        f"  stored: {stored}\n"
        "The comparison is per row and by key, deliberately: two sections whose preserved values "
        "came back on each other's rows hold exactly the right *set* of bindings and each point "
        "at the other's context — which is the repointing the binding was added to prevent, "
        "arriving through a migration rather than through a launch."
    )


# ---------------------------------------------------------------------------
# New machinery. Everything below this line is this ticket's, and the two reader
# controls at the bottom of the file are what execute it before anything trusts
# it (`docs/MISTAKES.md` entry 9).
# ---------------------------------------------------------------------------


def chain_of(failure: BaseException) -> list[BaseException]:
    """`failure` and everything it was raised from, nearest first."""
    found: list[BaseException] = []
    current: BaseException | None = failure
    while current is not None and len(found) < CHAIN_LIMIT:
        found.append(current)
        current = current.__cause__ or current.__context__
    return found


def spoken_by(error: BaseException) -> str | None:
    """What the server *said* in `error`, with the statement that raised it left out.

    The distinction is the whole reason this function exists. `str()` of a
    SQLAlchemy `DatabaseError` appends the SQL it ran, so a test that matched a
    table name against it would be satisfied by a migration that read the
    preserved table and then raised a sentence naming nothing — the statement
    echo would carry the name (`docs/MISTAKES.md` entry 3). A driver error
    carries the server's own message fields separately, and those are what an
    operator is shown; so those are what is read.

    Three answers, in order. A driver error with diagnostics answers with its
    message, detail and hint. A wrapper — anything still holding an `orig` —
    answers `None`, because its text is the echo. Anything else answers its own
    `str()`, which is how a migration that refuses by raising an ordinary Python
    exception is read: nothing in this ticket says the guard has to be written in
    SQL, and a test that could only see a `RAISE EXCEPTION` would be deciding
    that for the implementer.
    """
    diagnostics = getattr(error, "diag", None)
    if diagnostics is not None:
        fields = [
            value
            for name in DIAGNOSTIC_FIELDS
            if isinstance(value := getattr(diagnostics, name, None), str) and value
        ]
        if fields:
            return "\n".join(fields)
    if getattr(error, "orig", None) is not None:
        return None
    return f"{type(error).__name__}: {error}"


def what_the_failure_said(failure: BaseException) -> str:
    """Everything `failure` and its causes said, and nothing they merely ran.

    Each exception in the chain contributes, and each one's `orig` with it, since
    a wrapper's driver error is not always separately chained. Deduplicated by
    identity so one error read from two directions is not counted twice.
    """
    parts: list[str] = []
    seen: set[int] = set()
    for exception in chain_of(failure):
        for candidate in (exception, getattr(exception, "orig", None)):
            if candidate is None or id(candidate) in seen:
                continue
            seen.add(id(candidate))
            said = spoken_by(candidate)
            if said:
                parts.append(said)
    return "\n".join(parts)


def sqlstates_in(failure: BaseException) -> set[str]:
    """Every SQLSTATE the chain carries, under either driver's spelling.

    `sqlstate_of` is `tests/fixtures/supervision.py`'s and reads both psycopg 3's
    `sqlstate` and psycopg 2's `pgcode`; this walks the chain with it, because
    the code that matters can be on an error the wrapper is holding rather than
    on the exception Alembic raised.
    """
    found: set[str] = set()
    for exception in chain_of(failure):
        for candidate in (exception, getattr(exception, "orig", None)):
            if candidate is None:
                continue
            code = sqlstate_of(candidate)
            if code:
                found.add(code)
    return found


def reflected(database: Any, name: str) -> Any:
    """`name` as the database in front of us actually has it, right now.

    Reflected rather than taken from `Base.metadata`, and that is the difference
    that makes the delete-and-restore below honest. Metadata describes head; this
    runs at the revision *below* the binding one, and the row it round-trips has
    to be written back exactly as it was read — every column the database has,
    under the types the database gave them. A write through the declared table
    would silently drop a column a later revision added and would apply a
    `TypeDecorator` to a value that has already been through one.
    """
    from sqlalchemy import MetaData, Table, create_engine

    engine = create_engine(database.superuser_url)
    try:
        try:
            return Table(name, MetaData(), autoload_with=engine, schema="public")
        except Exception as failure:
            pytest.fail(
                f"`public.{name}` could not be reflected from the database standing below "
                f"{BINDING_REVISION}: {failure!r}. This file deletes one row of that table and "
                "puts it back, which is the sequence the carried finding describes; a table that "
                "is not there under that name at that revision means the constant at the top of "
                "this file has to move, and this is a broken test rather than a broken migration."
            )
    finally:
        engine.dispose()


def registration_row(database: Any, table: Any, key: Any) -> dict[str, Any]:
    """One whole `lti_deployment` row, read back as a mapping of column to value."""
    from sqlalchemy import select

    identifier = single_primary_key(table)
    with session_on(database) as session:
        found = session.execute(select(table).where(table.c[identifier] == key)).mappings().first()
    assert found is not None, (
        f"There is no `{DEPLOYMENT_TABLE}` row with {identifier} {key}, so there is nothing for "
        "this test to delete and nothing to put back. The seeded sections were bound to it one "
        "step ago, at head; a row that has gone missing between there and here means the walk "
        "down took it, and this is a broken test rather than a broken migration."
    )
    return dict(found)


def delete_the_registration(database: Any, table: Any, key: Any) -> None:
    """Delete one `lti_deployment` row, and require that exactly one went.

    The row count is asserted rather than assumed, because everything after this
    point is about a database that no longer holds that registration: a delete
    that quietly matched nothing would leave the upgrade below completing for the
    ordinary reason and the test reading it as the guard working
    (`docs/MISTAKES.md` entry 3, and the note about checking the mutation landed
    before believing it).
    """
    from sqlalchemy import select

    identifier = single_primary_key(table)
    with session_on(database) as session:
        removed = session.execute(table.delete().where(table.c[identifier] == key)).rowcount
    assert removed == 1, (
        f"Deleting the `{DEPLOYMENT_TABLE}` row {key} removed {removed} rows rather than one. "
        "That is this test's plant failing to land, not the migration: the whole sequence below "
        "is about preserved bindings pointing at a registration that no longer exists."
    )
    with session_on(database) as session:
        still_there = session.execute(
            select(table.c[identifier]).where(table.c[identifier] == key)
        ).first()
    assert still_there is None, (
        f"The `{DEPLOYMENT_TABLE}` row {key} is still in the database after being deleted and "
        "committed. Nothing below this line means anything: the state the carried finding "
        "describes was never reached."
    )


def restore_the_registration(database: Any, table: Any, row: dict[str, Any]) -> None:
    """Put a captured `lti_deployment` row back, primary key and all.

    The same row rather than a fresh one, and the primary key is the reason: the
    preserved bindings point at that particular deployment, so only a row
    carrying that id makes the retry the operator's retry — "restore the deleted
    registration and run the upgrade again" rather than "register a second
    platform and hope".

    Generated and identity columns are left to the database, since a value cannot
    be written into one; every other column is written back exactly as it was
    read.
    """
    from sqlalchemy import select

    writable = {
        name: value
        for name, value in row.items()
        if name in table.c and table.c[name].computed is None and table.c[name].identity is None
    }
    identifier = single_primary_key(table)
    assert identifier in writable, (
        f"The captured `{DEPLOYMENT_TABLE}` row cannot be written back with its own primary key "
        f"(`{identifier}` is generated or is not among {sorted(row)}). The preserved bindings "
        "point at that id, so a row written under a new one restores nothing and this file has to "
        "reach the retry some other way. Broken test, not broken migration."
    )
    with session_on(database) as session:
        try:
            session.execute(table.insert().values(**writable))
        except Exception as failure:
            pytest.fail(
                f"Putting the `{DEPLOYMENT_TABLE}` row back failed: {failure!r}. The values are "
                "the ones read out of that same table one step earlier, so this is this module's "
                "round-trip machinery rather than anything the migration did — a column type "
                "reflection and re-insertion cannot round-trip is the likely cause, and the fix "
                "is here."
            )
    with session_on(database) as session:
        found = session.execute(
            select(table.c[identifier]).where(table.c[identifier] == writable[identifier])
        ).first()
    assert found is not None, (
        f"The `{DEPLOYMENT_TABLE}` row {writable[identifier]} is not in the database after being "
        "restored and committed, so the retry below would be a second run of the refused upgrade "
        "rather than the repaired one (`docs/MISTAKES.md` entry 3)."
    )


def walked_below_the_binding(
    config: Any, database: Any, tables: dict[str, Any]
) -> tuple[str, str, dict[Any, tuple[Any, Any]], Any]:
    """The state all three migration tests start from, built once.

    Head, two bound sections, then down to the revision below the binding one —
    which is where `section` no longer carries the binding at all, and therefore
    where a registration can be deleted without the foreign key having anything
    to say about it. That is the operator's sequence from the carried bullet, and
    the three tests differ only in what they do next.

    Written as one function so the refusal and its healthy-path pair cannot drift
    apart: the difference between them has to stay the `DELETE` and nothing else.
    """
    binding = require_revision(config, BINDING_REVISION)
    below = the_revision_below(config, binding)

    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    seeded = two_bound_sections(database, tables)
    migrate(config, "downgrade", below, f"undoing revision {binding}")

    return binding, below, seeded, reflected(database, DEPLOYMENT_TABLE)


def the_doomed_registration(seeded: dict[Any, tuple[Any, Any]]) -> Any:
    """Which of the two seeded registrations this file deletes.

    Chosen by sorting rather than by insertion order, so the two tests that
    delete one delete the same one on every run and a failure is reproducible.
    """
    return sorted({deployment for _, deployment in seeded.values()}, key=str)[0]


# ---------------------------------------------------------------------------
# The tests.
# ---------------------------------------------------------------------------


def test_the_restore_refuses_by_name_when_a_preserved_bindings_registration_is_gone(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """The operator gets a sentence, not `violates foreign key constraint`.

    The carried bullet's sequence exactly: downgrade below `b8c41f7d2e05`, delete
    the registration, upgrade back. Two sections are bound to two different
    deployments and only one deployment is deleted, so a guard has to find the
    preserved rows whose reference is dead rather than notice that anything was
    preserved at all.

    **The mutation this must kill, and it is the state of the code today:** no
    guard. The restore repoints the section at a deployment that is not there,
    the foreign key throws, and the operator is handed Postgres's own
    `violates foreign key constraint` with a `23503` behind it — a message that
    names a constraint, says nothing about `section_binding_preserved`, and gives
    no hint that the fix is to put the registration back and run the upgrade
    again. The outcome is already right (nothing is stamped, and the preserved
    rows survive), so the message is the whole of the defect.

    **The near misses it must survive.**

      - *A guard whose message loses the preserved table's name.* Killed by
        reading the server's message fields rather than the rendered statement:
        the guard's own SQL mentions the table, so an assertion over
        `str(DatabaseError)` would match the echo and pass against an anonymous
        refusal (`docs/MISTAKES.md` entry 3).
      - *A guard that checks the wrong table, or inverts its condition.* It then
        either lets the raw violation through here, or refuses the healthy path
        in this test's pair.
      - *A refusal an operator cannot act on.* The ticket and the family
        convention both ask for a sentence that says what to do, so the failure
        has to name the missing registration's table as well as the preserved
        one.

    **Its pair** is
    `test_the_same_upgrade_completes_when_every_preserved_binding_still_has_its_registration`,
    which is this sequence with the `DELETE` removed. Without it every assertion
    here is satisfied by a migration that refuses every upgrade.
    """
    config = alembic_config_pointed_at(empty_database)
    binding, below, seeded, deployments = walked_below_the_binding(
        config, empty_database, metadata_tables
    )

    doomed = the_doomed_registration(seeded)
    delete_the_registration(empty_database, deployments, doomed)

    failure = attempt_upgrade(config, binding)
    assert failure is not None, (
        f"`alembic upgrade {binding}` completed over a database whose preserved bindings point at "
        f"the deployment {doomed}, which is no longer there. Either the restore silently skipped "
        "those rows — which would leave the sections carrying whatever the backfill invented, and "
        "is a data outcome the ticket puts out of scope — or the foreign key was never applied. "
        "The carried finding says this path fails closed today; if it does not, that is a larger "
        "finding than the message this ticket is about and belongs in the pull request."
    )

    said = what_the_failure_said(failure)
    assert said.strip(), (
        f"The upgrade refused and this module could read nothing that anybody said: {failure!r}. "
        "Every assertion below is about the text of the refusal, and over an empty string each "
        "one of them would be measuring this file's reader rather than the migration "
        "(`docs/MISTAKES.md` entry 3). "
        "`test_the_failure_reader_reports_a_raised_sentence_and_not_the_statement_that_raised_it` "
        "and its sibling are where a blind reader is diagnosed."
    )

    assert FOREIGN_KEY_VIOLATION not in sqlstates_in(failure), (
        f"The upgrade failed with SQLSTATE {FOREIGN_KEY_VIOLATION} — Postgres's foreign key "
        f"violation — so the constraint refused this database and the migration did not. That is "
        "the carried finding itself: the restore hands a dead deployment to the foreign key, and "
        "the operator is told a constraint was violated instead of being told that "
        f"`{PRESERVED_TABLE}` holds bindings pointing at a registration that no longer exists and "
        f"what to do about it. What was said:\n\n{said}"
    )
    assert RAW_VIOLATION_PHRASE not in said.lower(), (
        f"The refusal carries Postgres's own {RAW_VIOLATION_PHRASE!r} phrase, so it is the raw "
        f"constraint violation rather than the migration's refusal. What was said:\n\n{said}"
    )

    assert PRESERVED_TABLE in said, (
        f"The upgrade refused and what it said does not name `{PRESERVED_TABLE}`. That is the "
        "ticket's first criterion in one word: the path 'refuses with a sentence naming the "
        "preserved table', because the preserved rows are the thing the operator has to know "
        "survived — they are what makes a retry possible, and an operator who cannot see them "
        "will assume the downgrade lost the bindings and go looking for a backup. This is read "
        "from the server's message fields and not from the statement Alembic ran, so a guard that "
        "queries the table and then raises a sentence naming nothing does not satisfy it "
        f"(`docs/MISTAKES.md` entry 3). What was said:\n\n{said}"
    )
    assert TICKET in said, (
        f"The refusal does not name {TICKET}. Every other refusal this family of migrations "
        "writes opens with its own ticket, which is how an operator holding a failed upgrade "
        f"reaches the record that explains it. What was said:\n\n{said}"
    )
    assert DEPLOYMENT_TABLE in said, (
        f"The refusal names `{PRESERVED_TABLE}` but never `{DEPLOYMENT_TABLE}`, so it says what is "
        "in the way and not what is missing. The repair is to restore the deleted registration — "
        "re-register the platform, or put the row back — and run the upgrade again; a refusal "
        "that does not name the table whose row is gone leaves the operator with a message they "
        f"cannot act on, which is the defect wearing different words. What was said:\n\n{said}"
    )

    assert version_stamped(empty_database) == below, (
        f"After the refused upgrade, `alembic_version` records "
        f"{version_stamped(empty_database)!r} rather than {below}. The revision was stamped over a "
        "database it refused to migrate: the next run finds nothing left to do, the sections keep "
        "whatever the half-finished restore left on them, and the failure has been reported while "
        "the database has been marked as though it had not. The carried bullet's 'fail-closed' "
        "half is exactly this, and the ticket puts it out of scope to change."
    )


def test_the_preserved_bindings_come_back_when_the_registration_is_restored(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """ "The preserved rows survive for a retry", executed rather than stated.

    The second half of the ticket's first criterion. The same sequence as the
    refusal test, and then the repair the refusal is supposed to be telling the
    operator to make: put the deleted registration back, run the same upgrade
    again, and every section comes back carrying the pair it was seeded with.

    **The mutation this must kill:** a guard that makes the refusal true by
    spending the preserved rows — deleting the dead-referenced ones so the next
    run "works", or clearing the scratch table on its way out. Both produce a
    clean refusal, and both leave the retry restoring nothing: the sections come
    back carrying `pre-binding-section-<uuid>`, bound to a context no platform
    ever issued, and every staff launch from the real one is refused permanently.
    That is a strictly worse outcome than the raw message this ticket exists to
    replace, and nothing in the refusal test can see it.

    **The near miss it must survive:** a retry that restores *a* binding rather
    than the right one. The assertion is a keyed mapping over two sections whose
    pairs differ in both halves, so preserved values put back on each other's
    rows fail here — set equality would not.

    **It also kills a guard that refuses unconditionally**, from the other side
    to the healthy-path pair: the upgrade after the repair has to complete.

    **What a red means depends on when.** This is green on today's tree — the
    transaction rolls back, the preserved rows survive, and the retry already
    works, which is the carried bullet's own account of the fail-closed
    behaviour. So a red here now is this module's machinery, and a red here after
    the guard lands is the guard taking the retry away.
    """
    config = alembic_config_pointed_at(empty_database)
    binding, below, seeded, deployments = walked_below_the_binding(
        config, empty_database, metadata_tables
    )

    doomed = the_doomed_registration(seeded)
    captured = registration_row(empty_database, deployments, doomed)
    delete_the_registration(empty_database, deployments, doomed)

    refused = attempt_upgrade(config, binding)
    assert refused is not None, (
        f"`alembic upgrade {binding}` completed over a database whose preserved bindings point at "
        f"the deleted deployment {doomed}. This test is about what survives a refusal, so there "
        "is nothing here to measure; the refusal itself is "
        "`test_the_restore_refuses_by_name_when_a_preserved_bindings_registration_is_gone`'s "
        "subject and that is where this is diagnosed."
    )
    assert version_stamped(empty_database) == below, (
        f"After the refused upgrade, `alembic_version` records "
        f"{version_stamped(empty_database)!r} rather than {below}, so the retry below would be "
        "starting from a database that has been stamped with a revision it never applied — and "
        "'the upgrade succeeded on the second run' would be true of a command with nothing left "
        "to do."
    )

    restore_the_registration(empty_database, deployments, captured)

    migrate(
        config,
        "upgrade",
        binding,
        "the operator's retry: the registration restored, the same upgrade run again",
    )
    assert version_stamped(empty_database) == binding, (
        f"The retry raised nothing and `alembic_version` records "
        f"{version_stamped(empty_database)!r}. 'It completed' is then true of a command that did "
        "nothing, and the bindings asserted below would be whatever the database already held."
    )

    assert_bindings_are_unchanged(
        bindings_on(empty_database, metadata_tables),
        seeded,
        f"a refused upgrade to {binding}, the deleted registration restored, and the same upgrade "
        "run again",
    )


def test_the_same_upgrade_completes_when_every_preserved_binding_still_has_its_registration(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """The healthy path, which differs from the refusal by one statement.

    Identical to
    `test_the_restore_refuses_by_name_when_a_preserved_bindings_registration_is_gone`
    down to the last call, except that no registration is deleted — the two run
    the same walk through the same helper so that the difference between them
    cannot drift into being something else. The upgrade has to complete, the
    revision has to be stamped, and every section has to carry the pair it was
    seeded with.

    **The mutation this must kill:** a guard that refuses more than the dead
    reference — one whose condition is inverted, one that fires on any row in the
    preserved table, one that joins the wrong way and finds every preserved
    binding unmatched. Each of those satisfies every assertion in the refusal
    test and produces a revision no deployment can apply at all, which is the
    half of a validating migration that is easiest to get wrong.

    **The near miss it must survive:** a guard that lets the upgrade through by
    doing nothing to the sections. Hence the third assertion — the bindings are
    still the seeded ones afterwards, per row and by key, so a restore that was
    made to "pass" by clearing what it could not place is not read as a healthy
    round trip.

    **What a red means depends on when.** This test passes on today's tree, where
    there is no guard at all: a red here *now* means this module's machinery is
    broken rather than the migration, and the walk is what changes. A red here
    *after* the guard lands means the guard refuses a database it has no business
    refusing, and that is a defect in the code.
    """
    config = alembic_config_pointed_at(empty_database)
    binding, _, seeded, deployments = walked_below_the_binding(
        config, empty_database, metadata_tables
    )

    # The same registration the refusal test deletes, chosen through the same
    # function and then left alone — read rather than deleted, so that this test
    # and its pair differ by one statement and the read asserts the row is there.
    # "The upgrade completed" over a database with no registration in it would
    # say nothing about a guard that looks for dead references.
    intact = the_doomed_registration(seeded)
    registration_row(empty_database, deployments, intact)

    failure = attempt_upgrade(config, binding)
    assert failure is None, (
        f"`alembic upgrade {binding}` refused a database whose every preserved binding points at "
        f"a registration that is still there: {failure!r}. That is the ordinary case — it is what "
        "the round trip does on every deployment that has not deleted anything — so a revision "
        "that will not run over it cannot be applied at all, and the refusal this ticket adds has "
        "been written to fire on the wrong condition. "
        "`test_the_restore_refuses_by_name_when_a_preserved_bindings_registration_is_gone` is the "
        "half this one is the control for; the two differ by one `DELETE`."
    )
    assert version_stamped(empty_database) == binding, (
        f"`alembic upgrade {binding}` raised nothing and `alembic_version` records "
        f"{version_stamped(empty_database)!r}. The upgrade did not run, so 'it completed' is true "
        "of a command that did nothing and the assertion above is satisfied by a migration "
        "nothing reaches."
    )

    assert_bindings_are_unchanged(
        bindings_on(empty_database, metadata_tables),
        seeded,
        f"a downgrade below {binding} and an upgrade back with every registration left in place",
    )


# ---------------------------------------------------------------------------
# The reader's own controls. `what_the_failure_said` decides what every message
# assertion above can see, so it is executed against a failure of each kind
# before anything trusts what it reports (`docs/MISTAKES.md` entry 9, and entry
# 35's rule: a reader that only ever reports absence cannot tell you what it can
# see). Both are green on today's tree and must stay green: a red in either one
# means this module's machinery is broken, not the migration.
# ---------------------------------------------------------------------------

# A sentence raised the way a migration raises one, and a token that is in the
# statement and in nothing the server says. The whole point of the reader is that
# it reports the first and never the second. Kept as one statement rather than
# assembled per test, so the message, the hint and the comment cannot drift apart.
CANARY_MESSAGE = "E2-03 reader control: a migration raised this sentence"
CANARY_HINT = "E2-03 reader control: and this hint is beside it"
CANARY_ECHO_ONLY = "canary_echo_only_7c3f91d0"
A_RAISED_SENTENCE = f"""
DO $$
BEGIN
    -- {CANARY_ECHO_ONLY} — in the statement, and in no message the server sends.
    RAISE EXCEPTION '{CANARY_MESSAGE}' USING HINT = '{CANARY_HINT}';
END
$$;
"""

# A real foreign key violation, built out of two tables of this test's own so that
# it needs no schema and cannot be confused with anything the migrations create.
A_PARENT_TABLE = "CREATE TABLE e2_03_reader_control_parent (id uuid PRIMARY KEY)"
A_CHILD_TABLE = (
    "CREATE TABLE e2_03_reader_control_child ("
    " id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
    " parent_id uuid NOT NULL REFERENCES e2_03_reader_control_parent (id))"
)
AN_ORPHANED_CHILD = "INSERT INTO e2_03_reader_control_child (parent_id) VALUES (gen_random_uuid())"


def failure_from(database: Any, prepare: tuple[str, ...], statement: str) -> BaseException:
    """Run `prepare`, then `statement`, and answer the failure `statement` raised.

    The failing statement gets a transaction of its own that is rolled back, so
    that a caught error is not carried into a commit.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import DatabaseError

    engine = create_engine(database.superuser_url)
    try:
        with engine.begin() as connection:
            for one in prepare:
                connection.execute(text(one))
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text(statement))
                transaction.commit()
            except DatabaseError as refused:
                transaction.rollback()
                return refused
    finally:
        engine.dispose()
    pytest.fail(
        f"This statement was expected to fail and did not:\n\n{statement}\n\nThe reader controls "
        "exist to execute `what_the_failure_said` against a real failure of each kind; without "
        "one there is nothing to read and the assertions in this file are measuring nothing."
    )


def test_the_failure_reader_reports_a_raised_sentence_and_not_the_statement_that_raised_it(
    empty_database: Any,
) -> None:
    """The reader can see a refusal, hint and all, and cannot see the SQL echo.

    Every name assertion in this file is made against `what_the_failure_said`,
    and it is worth exactly as much as this test. A raised sentence is provoked
    the way a migration raises one — `RAISE EXCEPTION ... USING HINT` inside a
    `DO` block — and the statement carries a token that appears nowhere in what
    the server says.

    **The mutation this must kill:** a reader that falls back to `str()` of the
    SQLAlchemy wrapper. That renders the statement, so `CANARY_ECHO_ONLY` turns
    up in the text and, in the tests above, so does every table name the guard's
    own SQL mentions — which would let a refusal that names nothing satisfy the
    assertion that it names `section_binding_preserved` (`docs/MISTAKES.md`
    entry 3).

    **The near miss it must survive:** a reader that takes the primary message
    only. The hint is where an implementer may reasonably put the half of the
    refusal that says what to do, and a reader blind to it would fail a correct
    implementation for where it put its words.
    """
    failure = failure_from(empty_database, (), A_RAISED_SENTENCE)
    said = what_the_failure_said(failure)

    assert CANARY_MESSAGE in said, (
        f"The reader did not report a sentence the server certainly raised. It said:\n\n{said}\n\n"
        "Every message assertion in this module reads through this function, so all of them are "
        "measuring nothing until this passes."
    )
    assert CANARY_HINT in said, (
        f"The reader reported the message and not the hint beside it. It said:\n\n{said}\n\n"
        "A refusal is allowed to carry its instruction in a `HINT`, and a reader that cannot see "
        "one would fail an implementation for where it put its words rather than for what it "
        "said."
    )
    assert CANARY_ECHO_ONLY not in said, (
        f"The reader reported {CANARY_ECHO_ONLY!r}, which appears only in the statement and in "
        f"nothing the server said. It is reading the rendered SQL. It said:\n\n{said}\n\nThat is "
        "the failure mode the tests above are written around: a guard's own query mentions "
        f"`{PRESERVED_TABLE}`, so an echo makes 'the refusal names the preserved table' true of a "
        "refusal that names nothing (`docs/MISTAKES.md` entry 3)."
    )


def test_the_failure_reader_finds_a_real_foreign_key_violation_by_phrase_and_by_sqlstate(
    empty_database: Any,
) -> None:
    """The reader can find the shape the tests above assert is absent.

    A row is inserted against a foreign key with nothing behind it, which is the
    same violation the restore provokes today. Both of the ways the refusal test
    says "this must not be the failure mode" are asserted here in the positive,
    against a failure that certainly is one.

    **The mutation this must kill:** a reader, or a `sqlstates_in`, that reports
    nothing. Absence is what the refusal test asserts, so a blind reader makes
    both of those assertions pass against the raw violation the ticket exists to
    replace — the test would go green the moment its machinery broke, which is
    the worst direction for a failure to point. `docs/MISTAKES.md` entry 35 is
    the rule: require the thing to *find* each mechanism on a subject that
    certainly has it, or it can only ever tell you it saw nothing.
    """
    failure = failure_from(empty_database, (A_PARENT_TABLE, A_CHILD_TABLE), AN_ORPHANED_CHILD)
    said = what_the_failure_said(failure)

    assert RAW_VIOLATION_PHRASE in said.lower(), (
        f"A row was inserted against a foreign key with nothing behind it and the reader did not "
        f"report {RAW_VIOLATION_PHRASE!r}. It said:\n\n{said}\n\nThe refusal test asserts that "
        "phrase is *absent* from the migration's failure; if the reader cannot see it when it is "
        "there, that assertion passes against the raw violation itself."
    )
    assert FOREIGN_KEY_VIOLATION in sqlstates_in(failure), (
        f"The same insert carried no {FOREIGN_KEY_VIOLATION} SQLSTATE through `sqlstates_in` "
        f"(it found {sorted(sqlstates_in(failure))}). That is the spelling-independent half of "
        "the refusal test's 'not the raw violation' assertion, and an empty answer satisfies it "
        "for free."
    )
