"""The binding migration's downgrade keeps what it takes away — E1 boundary fix, H2.

E1-10's round-3 security review gave `section` an identity a copied course
cannot reproduce: `(lti_deployment_id, lms_context_id)`, unique. The migration
that adds it is `20260826_b8c41f7d2e05`, and its downgrade drops both columns.
The boundary review proved on a scratch database what that costs: run that
revision down and back up, and every bound section comes back reading
`lms_context_id = 'pre-binding-section-<uuid>'` — the identifier the upgrade
invents for rows that were never bound. The section is then bound to a context
no platform ever issued, so every staff launch from the real context takes the
`context_collision` branch and is refused, permanently: the application holds no
UPDATE on that column, and nothing in the failure says a downgrade caused it.
Launch-triggered ingestion and refresh die; the hourly sync survives, because
the roster address column round-trips intact.

**The fix shape is inside the revision itself** — `b8c41f7d2e05`'s downgrade
preserves the pair it is about to drop and its upgrade restores it — and this
module is what says the round trip is the identity the docstring claims. The
sentence here used to offer an earlier revision as the precedent for that shape,
and the E1 boundary record corrections struck that claim in the same merge that
made it: the revision it named does no data migration at all, and its own
docstring says so. It names no precedent now, and
`tests/unit/test_no_test_cites_the_struck_preserve_precedent.py` is what keeps
every module here from acquiring one again (E2-03, `docs/MISTAKES.md` entry 1).

**Everything is asserted per row, keyed by the section's own primary key.** Two
sections are seeded, carrying distinct values in *both* columns, and the
comparison is a mapping rather than a set: a restore that puts the values back
in the wrong order — by insertion order, by a `LIMIT`, by a join that lost its
key — leaves the set of stored bindings exactly right and points each section at
the other one's context. That is the same failure the binding was added to
prevent, arriving through the migration instead of through a launch.

**Both revisions are reached by name and neither end is a step.** The subject is
`b8c41f7d2e05` and the revision below it, and that parent is *resolved from the
script directory* rather than written down: `down_revision` is the migration's
own statement of what it chains from, so a rebase that re-points it moves this
test with it, while `-1` would silently become whichever revision happened to
land on top (`docs/disputes/E0-11-02.md`, `docs/MISTAKES.md` entry 3).

**Seeding happens at head and the database is walked back down afterwards**, for
the reason `seed_row`'s own docstring gives at length: the insert and its
`RETURNING` clause are built from `Base.metadata`, so seeding into a database
standing before any revision that added a column fails inside the fixture
(`docs/disputes/E1-10-01.md`). `head` appears here only as the name of the
schema today's models describe, and is the subject of nothing.

**Each test migrates a database of its own.** `empty_database` is a second
database in the same container, created for one test and dropped after, so a
downgrade here cannot touch the session database every other integration test
reads (`docs/MISTAKES.md` entry 12).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fixtures.supervision import require_table, seed_row, single_primary_key

pytestmark = pytest.mark.integration

# The revision under test — the file is `backend/migrations/versions/
# 20260826_b8c41f7d2e05_*.py`, and Alembic knows it by the bare identifier.
BINDING_REVISION = "b8c41f7d2e05"

# Where the seeding happens, and **it is not a subject**. Every assertion below
# is about `BINDING_REVISION` and the revision it chains from; this name appears
# only in the upgrade calls that put the database into the shape
# `Base.metadata` describes, so that `seed_row` can write to it at all.
MODEL_SCHEMA = "head"

# The two columns the revision adds, spelled as `tests/fixtures/provisioning.py`
# spells the first (`SECTION_CONTEXT_ID_COLUMN`) and as the plan and
# `boundary-review.md` spell the second. Not this module's invention: they are
# the pair the round-3 ruling makes unique together.
SECTION_TABLE = "section"
CONTEXT_ID_COLUMN = "lms_context_id"
DEPLOYMENT_COLUMN = "lti_deployment_id"

# The two context identifiers seeded, one per section. Written by this module
# rather than invented by the seeder, because the whole subject is whether a
# *particular* value comes back on a *particular* row: values that differ in
# every character make a swapped restore visible, and values nothing else could
# produce make "it came back" mean it was kept rather than re-derived.
FIRST_CONTEXT_ID = "e1-boundary-b-context-alpha-8f21"
SECOND_CONTEXT_ID = "e1-boundary-b-context-omega-3c7d"

# What the upgrade writes into `lms_context_id` for a section it finds unbound.
# Quoted from the E1-10 deferred item that measured it (`deferred.md`, item 3:
# `select count(*) from section where lms_context_id like 'pre-binding-section-%'`).
# A section that comes back carrying this shape is the finding itself, so it is
# worth naming in the failure rather than only reporting a mismatch.
PRE_BINDING_PREFIX = "pre-binding-section-"


def require_revision(config: Any, revision: str) -> str:
    """`revision`, after asking the script directory whether it still exists.

    Resolved rather than handed straight to `command.upgrade`, so a constant
    left behind by a squash, a rebase or a renamed file fails with a message
    naming the ticket instead of with Alembic's own `Can't locate revision`,
    which reads like a broken environment. The idiom is
    `tests/integration/test_the_upgrade_refuses_a_stored_edge_that_does_not_climb.py`'s.
    """
    from alembic.script import ScriptDirectory

    try:
        ScriptDirectory.from_config(config).get_revision(revision)
    except Exception as failure:
        pytest.fail(
            f"`{revision}` is not a revision in this tree: {failure!r}. That is E1-10's round-3 "
            "revision — the one that adds `section`'s `(lti_deployment_id, lms_context_id)` "
            "binding — and this module pins its work to a named revision rather than to `head` and "
            "a relative step. If it has been renumbered or squashed, the constant at the top of "
            "this file is the one place to change."
        )
    return revision


def the_revision_below(config: Any, revision: str) -> str:
    """What `revision` chains from, read off the migration itself.

    The migration's own `down_revision` rather than a second constant here: it
    is the statement of what this revision undoes back to, so a rebase that
    re-points it moves this test with it, and a copy in this file would be a
    record that goes on asserting something the change made false
    (`docs/MISTAKES.md` entry 1).
    """
    from alembic.script import ScriptDirectory

    parent = ScriptDirectory.from_config(config).get_revision(revision).down_revision
    if not isinstance(parent, str) or not parent:
        pytest.fail(
            f"Revision {revision} reports `down_revision = {parent!r}`, so this module cannot say "
            "what 'the revision below it' is. A tuple means a merge point and `None` means it is "
            "the base; either way the round trip this file drives has to be re-expressed against "
            "whatever the history now looks like, deliberately, rather than guessed at here."
        )
    return parent


def migrate(config: Any, direction: str, revision: str, what: str) -> None:
    """Run one Alembic command to `revision`, failing the test if it does not complete.

    A migration that stops part-way is worse than one that refuses to start: the
    statements before the failure have run, the ones after have not, and the
    version is still stamped — so everything read afterwards is a database
    nobody has described.
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


@contextmanager
def session_on(database: Any) -> Iterator[Any]:
    """A committed session on `database`, opened and closed around one step.

    Opened and closed around each migration step rather than held across one: an
    Alembic upgrade that alters a table takes locks a session idle inside a
    transaction can block, and a migration waiting on this test's own connection
    is a hang rather than a failure. `test_the_upgrade_refuses_a_stored_edge_
    that_does_not_climb.py` opens its connections the same way for the same
    reason.
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

    A mapping rather than a list, because the whole question is which values are
    on which row: a restore that preserved both pairs and put them back on the
    wrong sections leaves any set comparison satisfied.
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


def columns_the_database_reports(database: Any, table: str) -> set[str]:
    """What `table` actually has right now, read from the catalog rather than the models.

    `Base.metadata` describes head and says nothing about the database in front
    of it, and the point of this read is to stand at an older revision and ask
    what is there.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            found = connection.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :table"
                ),
                {"table": table},
            ).scalars()
            return set(found)
    finally:
        engine.dispose()


def two_bound_sections(database: Any, tables: dict[str, Any]) -> dict[Any, tuple[Any, Any]]:
    """Seed two sections whose bindings differ in both halves, and answer them.

    Each section is built on a chain of its own, so each one's
    `lti_deployment_id` is a different `lti_deployment` row — the containment
    ancestors are seeded per chain and only the institution is shared, which is
    the schema's own rule (`uq_institution_one_row`).

    The context identifiers are this module's, for the reason the constants say.
    The deployment half cannot be: it is a foreign key, so the value has to be a
    row that exists, and it is read back off the insert rather than predicted.
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
    contexts = [context for context, _ in seeded.values()]
    deployments = [deployment for _, deployment in seeded.values()]
    assert len(set(contexts)) == 2 and all(contexts), (
        f"The two sections carry the context identifiers {contexts}. They have to differ, and "
        "neither may be empty: a swapped restore is invisible when both rows say the same thing, "
        "and a NULL means the column is nullable here and this module has to seed it explicitly "
        "(it seeds `lms_context_id` and lets the foreign key half be built by the chain)."
    )
    assert len(set(deployments)) == 2 and all(deployments), (
        f"The two sections are bound to the deployments {deployments}. They have to differ, and "
        "neither may be NULL, or half of the pair under test is a constant — a restore that "
        "re-derived every section's deployment from the only registration in the database would "
        "pass, which is exactly the mutation this file exists to catch."
    )
    return seeded


def stored_pairs_for(
    after: dict[Any, tuple[Any, Any]], seeded: dict[Any, tuple[Any, Any]]
) -> dict[Any, Any]:
    """The stored pairs for the seeded keys, for a failure message to print."""
    return {key: after.get(key) for key in seeded}


def assert_bindings_are_unchanged(
    after: dict[Any, tuple[Any, Any]], seeded: dict[Any, tuple[Any, Any]], what: str
) -> None:
    """Every seeded section still carries its own pair, byte for byte.

    Three failures are separated, because they need different fixes: rows that
    are gone, rows whose values were invented by the backfill, and rows whose
    values belong to the other section.
    """
    missing = sorted(str(key) for key in seeded if key not in after)
    assert not missing, (
        f"After {what}, the sections {missing} are no longer in the database at all. The revision "
        "under test adds columns; it does not own the rows, and a downgrade that takes rows with "
        "it is a worse version of the finding this file is about."
    )
    invented = sorted(
        str(key) for key in seeded if str(after[key][0] or "").startswith(PRE_BINDING_PREFIX)
    )
    assert not invented, (
        f"After {what}, the sections {invented} carry a `{CONTEXT_ID_COLUMN}` beginning "
        f"{PRE_BINDING_PREFIX!r} — the identifier the upgrade invents for a section it finds "
        "unbound. Their real bindings were dropped on the way down and were not there to restore "
        "on the way up. Nothing a platform issues looks like this value, so every staff launch "
        "from the real context is now refused as a `context_collision`, permanently: the "
        f"application holds no UPDATE on that column. Stored now: {dict(after)}"
    )
    assert {key: after[key] for key in seeded} == seeded, (
        f"After {what}, the sections do not carry the bindings they were seeded with.\n"
        f"  seeded: {seeded}\n"
        f"  stored: {stored_pairs_for(after, seeded)}\n"
        "The comparison is per row and by key, deliberately: two sections whose preserved values "
        "came back on each other's rows hold exactly the right *set* of bindings and each point "
        "at the other's context — which is the repointing the binding was added to prevent, "
        "arriving through a migration rather than through a launch."
    )


def test_a_downgrade_and_re_upgrade_gives_every_section_its_own_binding_back(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """The round trip is the identity `b8c41f7d2e05`'s docstring says it is.

    Two sections are seeded at head with distinct context identifiers and
    distinct deployments; the database is walked down to the revision below the
    binding one and back up; and each section has to come back carrying its own
    pair, unchanged.

    **The mutation this must kill, and it is the state of the code today:** a
    downgrade that drops the two columns and keeps nothing. The upgrade then
    treats every section as unbound and invents `pre-binding-section-<uuid>`,
    which reads as a successful migration and refuses every subsequent staff
    launch from the real context.

    **The near miss it must survive:** a preserve-and-restore that keeps both
    pairs and puts them back on the wrong rows — restoring by insertion order,
    by a `LIMIT`, or by a join that lost the section key. Set equality is
    satisfied by that and it is strictly worse than losing the values, because
    each section is then bound to the *other* context and no error is raised
    anywhere. Hence the assertion on the keyed mapping and the two seeded
    sections differing in both halves.

    **The control that makes the round trip mean anything** is asserted in the
    middle: at the revision below, the database really has no binding columns. A
    downgrade that quietly did nothing would preserve the values perfectly and
    prove nothing at all (`docs/MISTAKES.md` entry 3).
    """
    config = alembic_config_pointed_at(empty_database)
    binding = require_revision(config, BINDING_REVISION)
    below = the_revision_below(config, binding)

    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    seeded = two_bound_sections(empty_database, metadata_tables)

    migrate(config, "downgrade", below, f"undoing revision {binding}")

    standing = columns_the_database_reports(empty_database, SECTION_TABLE)
    still_there = sorted({CONTEXT_ID_COLUMN, DEPLOYMENT_COLUMN} & standing)
    assert not still_there, (
        f"After downgrading to {below} — the revision below {binding} — `{SECTION_TABLE}` still "
        f"carries {still_there}. The revision under test adds those columns, so a downgrade that "
        "leaves them is not undoing it, and 'the values survived the round trip' would be true of "
        "a migration pair that did nothing in either direction. If the downgrade deliberately "
        "keeps a column now, that is a change to what a downgrade means and belongs in the pull "
        f"request. The table reports: {sorted(standing)}"
    )

    migrate(config, "upgrade", MODEL_SCHEMA, f"re-applying revision {binding} and what follows it")

    assert_bindings_are_unchanged(
        bindings_on(empty_database, metadata_tables),
        seeded,
        f"a downgrade to {below} and an upgrade back to the models' schema",
    )


def test_the_binding_survives_the_round_trip_being_made_twice(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """Preserving is not a one-shot: an operator who goes down and up twice keeps the binding.

    The same journey as the test above, made a second time from the state the
    first one left. Its pair is that test — one trip has to work before two can
    mean anything — and it is here because the scratch-table shape has a failure
    mode the single trip cannot see.

    **The mutation this must kill:** a preserve step that assumes it is starting
    from nothing. A `CREATE TABLE` that raises because the scratch table is
    still there from last time; a restore that leaves stale rows behind so the
    second preserve writes a second copy per section and the restore matches the
    wrong one; a preserve that skips because it found the table already
    populated. None of them is visible on a first round trip, and a downgrade is
    exactly the operation somebody repeats — that is what it is for.

    **The near miss it must survive:** the second trip preserving values from
    the *first* trip's leftovers. The values are the same either way, so this is
    asserted as the same keyed mapping rather than as "some binding is present";
    a stale row carrying the other section's pair fails here for the same reason
    a swap does above.
    """
    config = alembic_config_pointed_at(empty_database)
    binding = require_revision(config, BINDING_REVISION)
    below = the_revision_below(config, binding)

    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    seeded = two_bound_sections(empty_database, metadata_tables)

    for attempt in (1, 2):
        migrate(config, "downgrade", below, f"undoing revision {binding}, trip {attempt}")
        migrate(config, "upgrade", MODEL_SCHEMA, f"re-applying revision {binding}, trip {attempt}")

    assert_bindings_are_unchanged(
        bindings_on(empty_database, metadata_tables),
        seeded,
        f"two downgrades to {below} and two upgrades back",
    )
