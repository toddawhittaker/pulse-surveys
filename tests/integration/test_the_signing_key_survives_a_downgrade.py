"""E3-01's schema change goes down and comes back up without losing the tool's key.

The rotation rule is a migration: `uq_tool_signing_key_one_row` is dropped,
`created_at` and `retired_at` are added. A revision that cannot be undone is one
an operator cannot back out of, and the thing at risk here is not a survey answer
— it is the private half of the tool's LTI identity, which nothing regenerates
and no platform will accept a replacement for without a re-registration.

**The shape is `test_the_survey_schema_survives_a_downgrade.py`'s**, and
deliberately so: resolve the revision to walk back to, seed at head, walk down,
assert in the middle that the downgrade really undid something, walk back up, and
compare whole rows keyed by their own primary key. E2-16 put those five moves in
`tests/fixtures/migration_journey.py` so that the fourth module needing them
imports rather than copies (`docs/MISTAKES.md` entry 13).

**Two of the three journeys seed one key, and the third seeds two.** At the
revision below, the one-row rule is back on the table, so a database holding a
rotation cannot be represented there at all. This module's first two tests said
nothing about that state and this paragraph used to say why: the choice between
refusing loudly and keeping the newest was open, and a test that picked one would
have made the decision from the test side. **It is no longer open**, and ADR 0127
records both halves: the downgrade counts the **live** keys and refuses while more
than one is live, naming retirement as the way forward; with at most one live key
it deletes the retired rows itself and proceeds, since the one-row schema cannot
hold them and nothing signs with them.
`test_a_downgrade_refuses_a_stored_rotation_rather_than_discarding_a_key` holds
both halves — written after the fact and saying so in its own docstring — and its
second half is what tells a live-key count from a stored-row count. The first two
tests still seed one key, which is the state a downgrade must always be able to
handle.

**The comparison is over the columns that exist at both ends.** `created_at` and
`retired_at` do not exist below the revision under test, so requiring their values
to survive would be requiring a preserve-and-restore step the ticket never asked
for. The `id` and the key itself are what a deployment cannot lose.

**The middle of the journey is where the control is.** A downgrade that quietly
did nothing would preserve everything perfectly and prove nothing at all
(`docs/MISTAKES.md` entry 3), so the two new columns are required to be gone at
the older revision and the one-row index is required to be back.

**Each test migrates a database of its own.** `empty_database` is a second
database in the same container, created for one test and dropped after, so a
downgrade here cannot reach the session database every other integration test
reads.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    columns_the_database_reports,
    migrate,
    require_revision,
    rows_by_key,
    session_on,
)
from fixtures.signing_key_tool import (
    CREATED_AT_COLUMN,
    ONE_ROW_INDEX,
    PRIVATE_KEY_COLUMN,
    RETIRED_AT_COLUMN,
    SIGNING_KEYS,
    generated_pem,
    require_rotation_columns,
)
from fixtures.supervision import seed_row

pytestmark = pytest.mark.integration

# The revision this ticket's migration chains from — the chain head when the
# branch was cut. Walked to by name rather than by a relative step, so that a
# rebase which re-points the new revision is a one-line change here and a loud
# `require_revision` failure until somebody makes it. If another E3 ticket's
# migration lands between the two, the walk undoes that one as well, which is
# still a valid journey for the only thing asserted below: the stored key.
THE_REVISION_BELOW = "b1e7d4a90c26"
WHAT_IT_IS = "the migration chain's head when E3-01 was cut, below the rotation revision"

# The columns compared at either end: the ones that exist at both revisions.
CARRIED_ACROSS = ("id", PRIVATE_KEY_COLUMN)

# Three instants, aware as ADR 0019 requires, so the seeded rows carry values this
# module chose rather than ones the server default invented. The second and third
# belong to the refusal test, where two keys have to be told apart and one of them
# is then retired.
SUPPLIED_AT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)
REPLACED_AT = datetime(2026, 9, 3, 9, 0, tzinfo=UTC)
RETIRED_ON = datetime(2026, 9, 4, 9, 0, tzinfo=UTC)

# How a refusal to downgrade a stored rotation has to tell an operator what to do.
# **A candidate list, because the ticket fixes no wording** — the same device
# `tests/fixtures/supervision.py::require_column` uses where a spelling is the
# implementer's. What is asserted is that the refusal names a way back to one key
# rather than only reporting that there are too many.
WAYS_BACK_TO_ONE_KEY = ("retire", "retirement")


def indexes_the_database_reports(database: Any, table: str) -> set[str]:
    """Every index on `table` by name, read from the catalog at whatever revision.

    Named indexes rather than a `unique` flag, because the object being asserted
    about is a specific one: `uq_tool_signing_key_one_row` is the unique index on
    a constant expression that E1-05 used to hold the one-row rule, and a
    downgrade that recreated *some* unique index would satisfy anything weaker.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            found = connection.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = :table"
                ),
                {"table": table},
            ).scalars()
            return set(found)
    finally:
        engine.dispose()


def seed_one_signing_key(database: Any, tables: dict[str, Any]) -> None:
    """One `tool_signing_key` row at head, with a `created_at` this module chose.

    Seeded at head and the database walked down afterwards, for the reason
    `seed_row`'s own docstring gives: its insert and its `RETURNING` clause are
    built from `Base.metadata`, so seeding into a database standing before the
    revision that added a column fails inside the fixture rather than in a test
    (`docs/disputes/E1-10-01.md`).
    """
    with session_on(database) as session:
        seed_row(
            session,
            tables,
            SIGNING_KEYS,
            {},
            **{
                PRIVATE_KEY_COLUMN: generated_pem(),
                CREATED_AT_COLUMN: SUPPLIED_AT,
                RETIRED_AT_COLUMN: None,
            },
        )


def plant_a_signing_key(database: Any, tables: dict[str, Any], created_at: datetime) -> str:
    """One more `tool_signing_key` row at head, created at an instant the caller chose.

    `seed_one_signing_key` above is the one-key case two tests share; this is the
    same write with the instant as an argument, so a rotation — two live keys with
    different `created_at` — can be planted without either test guessing at the
    other's constant.

    The PEM comes back so the caller can name *this* row afterwards without
    comparing timestamps across a database round trip. The key is what tells the
    two rows apart everywhere below.
    """
    pem = generated_pem()
    with session_on(database) as session:
        seed_row(
            session,
            tables,
            SIGNING_KEYS,
            {},
            **{
                PRIVATE_KEY_COLUMN: pem,
                CREATED_AT_COLUMN: created_at,
                RETIRED_AT_COLUMN: None,
            },
        )
    return pem


def the_stamped_revision(database: Any) -> str:
    """What Alembic believes this database is standing at, right now.

    Read because a refusal is only a refusal if the database did not move: a
    downgrade that raised *after* stamping would look like a refusal here and be a
    database standing at a revision whose statements never ran.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            found = connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
            return "".join(sorted(found))
    finally:
        engine.dispose()


def stored_signing_keys(database: Any) -> list[dict[str, Any]]:
    """Every `tool_signing_key` row, read through raw SQL at whatever revision.

    Raw SQL rather than the declared table, so a reading taken while the database
    is standing below the rotation revision reports the columns that are *there*
    instead of failing on a `RETURNING` clause the models built.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            result = connection.execute(text(f"SELECT * FROM public.{SIGNING_KEYS}"))  # noqa: S608
            return [dict(row) for row in result.mappings().all()]
    finally:
        engine.dispose()


def retire_the_key(database: Any, pem: str, at: datetime) -> None:
    """Mark one stored key retired, the way an operator's `retire <kid>` does.

    **Retired rather than deleted**, and that is the whole strength of the pair
    that uses it. An earlier version of this module deleted the row, because
    whether the guard counted every row or only the unretired ones was unsettled
    and a reduction by retirement would have passed under one reading and failed
    under the other. The ruling settled it — the guard counts **live** keys, and
    with at most one live key the downgrade clears the retired rows itself — so
    the reduction is now the very thing the refusal's message advises, and the
    pair proves that advice end to end instead of proving a way round it.

    The row is addressed by its key rather than by its timestamp: a value this
    test generated and holds, with no round trip through a column whose type or
    timezone rendering could make the comparison the subject.
    """
    from sqlalchemy import create_engine, text

    engine = create_engine(database.superuser_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"UPDATE public.{SIGNING_KEYS} SET {RETIRED_AT_COLUMN} = :at "  # noqa: S608
                    f"WHERE {PRIVATE_KEY_COLUMN} = :pem"
                ),
                {"at": at, "pem": pem},
            )
    finally:
        engine.dispose()


def refused_downgrade(config: Any, revision: str) -> Exception:
    """Run a downgrade that is expected to refuse, and hand back what it raised.

    `migrate` from `tests/fixtures/migration_journey.py` cannot be used here: it
    turns any incomplete step into a `pytest.fail`, which is exactly right for
    every other journey in this module and exactly wrong for the one case where
    not completing is the behaviour under test.

    **`Exception` rather than a named type**, deliberately. The type a migration
    raises to refuse is the implementer's, and pinning one from the test side
    would settle an interface the ticket leaves open. What keeps that breadth
    honest is everything the caller asserts afterwards: the message names a way
    forward, the database did not move, and both keys are still there — a genuine
    SQL error satisfies none of those.
    """
    from alembic import command

    try:
        command.downgrade(config, revision)
    except Exception as refusal:
        return refusal
    pytest.fail(
        f"`alembic downgrade {revision}` completed against a database holding two signing keys. "
        "The revision below restores `uq_tool_signing_key_one_row`, so the only ways to complete "
        "are to discard a key or to leave the index off — the first destroys half of a rotation "
        "in progress, and it destroys the half a platform may already have fetched. ADR 0127 makes "
        "this a refusal."
    )


def carried_values(rows: dict[Any, dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    """Each row reduced to the columns that exist on both sides of the journey."""
    return {key: {name: row[name] for name in CARRIED_ACROSS} for key, row in rows.items()}


def assert_the_key_is_unchanged(after: dict[Any, Any], before: dict[Any, Any], what: str) -> None:
    """The stored key came back, on its own row, holding what it was seeded with."""
    missing = sorted(str(key) for key in before if key not in after)
    assert not missing, (
        f"After {what}, {len(missing)} `{SIGNING_KEYS}` row(s) are gone: {missing}. The revision "
        "under test adds two columns and drops an index; it does not own these rows. A downgrade "
        "that discards the tool's private key discards an identity a platform has already been "
        "registered against, and nothing regenerates it."
    )
    changed = {
        key: {
            column: (before[key][column], after[key][column])
            for column in before[key]
            if after[key][column] != before[key][column]
        }
        for key in before
    }
    changed = {key: difference for key, difference in changed.items() if difference}
    assert not changed, (
        f"After {what}, the stored signing key came back holding values it was not seeded with — "
        f"as `column: (seeded, stored)`:\n  {changed}\nA key the upgrade invented signs perfectly "
        "and verifies against nothing any platform holds, which is the failure ADR 0082 calls "
        "invisible at the moment it happens."
    )
    appeared = sorted(str(key) for key in after if key not in before)
    assert not appeared, (
        f"After {what}, `{SIGNING_KEYS}` holds {len(appeared)} row(s) nothing seeded: {appeared}. "
        "A restore that inserted rather than restored leaves a second identity for one tool, and "
        "whichever row a process reads first decides whether its assertions verify."
    )


def test_a_downgrade_and_re_upgrade_keeps_the_stored_signing_key(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """The tool's key survives being walked below E3-01's revision and back up.

    **The mutation this kills:** a downgrade written as "drop the two columns and
    put the index back", which is the obvious one and is fine, beside an upgrade
    that recreates the table or clears it to make the index drop safe — which is
    the shape that loses the key. It also kills a downgrade that cannot run at all
    against a database holding a key, which is every database that has one.

    **The control is in the middle**, and without it a downgrade that did nothing
    would pass every comparison here: the two new columns must really be gone, and
    the one-row index must really be back, at the older revision.

    **The near miss it must survive:** an upgrade that re-adds `created_at` as
    `NOT NULL` with no default. That aborts on a table with a row in it and leaves
    the database stranded below the revision — which is exactly how E2-05's
    revision failed, and it shows up here as the upgrade step failing rather than
    as a comparison.
    """
    require_rotation_columns(metadata_tables[SIGNING_KEYS].c.keys(), "the declared table")
    config = alembic_config_pointed_at(empty_database)
    below = require_revision(config, THE_REVISION_BELOW, WHAT_IT_IS)

    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    seed_one_signing_key(empty_database, metadata_tables)
    before = carried_values(rows_by_key(empty_database, metadata_tables, SIGNING_KEYS))
    assert len(before) == 1, (
        f"This journey seeds one `{SIGNING_KEYS}` row and the database holds {len(before)}. With "
        "none, every comparison below is an equality between two empty mappings and a downgrade "
        "that took the key with it reads as a perfect round trip."
    )

    migrate(config, "downgrade", below, f"undoing the rotation revision, back to {below}")

    standing = columns_the_database_reports(empty_database, SIGNING_KEYS)
    assert standing, (
        f"After downgrading to {below}, `{SIGNING_KEYS}` does not exist at all. E1-05 creates that "
        "table well below this revision, so a downgrade that drops it has undone somebody else's "
        "migration — and taken the deployment's only signing key with it."
    )
    left_behind = sorted({CREATED_AT_COLUMN, RETIRED_AT_COLUMN} & standing)
    assert not left_behind, (
        f"After downgrading to {below}, `{SIGNING_KEYS}` still carries {left_behind}. E3-01's "
        "revision is what adds them, so a downgrade that leaves them behind is not undoing it, and "
        "'the key survived the round trip' would be true of a migration pair that did nothing in "
        f"either direction. The table reports: {sorted(standing)}"
    )
    assert ONE_ROW_INDEX in indexes_the_database_reports(empty_database, SIGNING_KEYS), (
        f"After downgrading to {below}, `{ONE_ROW_INDEX}` is not on `{SIGNING_KEYS}`. That index "
        "is the one-row rule E1-05 built and E3-01 drops, so a downgrade that does not restore it "
        "leaves the database in neither revision's shape — and the next upgrade's attempt to drop "
        "it again is where an operator finds out."
    )

    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying the rotation revision and what follows")

    after = carried_values(rows_by_key(empty_database, metadata_tables, SIGNING_KEYS))
    assert_the_key_is_unchanged(after, before, f"a downgrade to {below} and an upgrade back")


def test_the_signing_key_survives_the_round_trip_being_made_twice(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """A downgrade is an operation somebody repeats — that is what it is for.

    Its pair is the test above: one trip has to work before two can mean anything.
    It is here because dropping and recreating a *named* index has a failure mode
    a single trip cannot see.

    **The mutation this kills:** an upgrade whose index drop assumes the index is
    there, or a downgrade whose `CREATE UNIQUE INDEX` assumes it is not. Either
    raises on the second trip and never on the first, and the database is left
    stranded part-way through a revision with the version stamped.

    **The near miss it must survive:** a second trip that appears to work because
    the first one left the schema in a state the second one did not have to change.
    The row comparison is the same keyed equality as above, so a key that came back
    on a different row, or a second row that appeared, fails here too.
    """
    require_rotation_columns(metadata_tables[SIGNING_KEYS].c.keys(), "the declared table")
    config = alembic_config_pointed_at(empty_database)
    below = require_revision(config, THE_REVISION_BELOW, WHAT_IT_IS)

    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    seed_one_signing_key(empty_database, metadata_tables)
    before = carried_values(rows_by_key(empty_database, metadata_tables, SIGNING_KEYS))
    assert len(before) == 1, (
        f"This journey seeds one `{SIGNING_KEYS}` row and the database holds {len(before)}, so the "
        "comparison after two trips would be satisfied by a database that lost the key on the "
        "first one."
    )

    for attempt in (1, 2):
        migrate(config, "downgrade", below, f"undoing the rotation revision, trip {attempt}")
        migrate(config, "upgrade", MODEL_SCHEMA, f"re-applying it, trip {attempt}")

    after = carried_values(rows_by_key(empty_database, metadata_tables, SIGNING_KEYS))
    assert_the_key_is_unchanged(after, before, f"two downgrades to {below} and two upgrades back")


def test_a_downgrade_refuses_a_stored_rotation_rather_than_discarding_a_key(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """A rotation in progress cannot be walked back down, and the refusal says why.

    **Written after the implementation, and this docstring says so.** The manifest
    for this ticket flagged the question as open — "what a downgrade does with more
    than one stored key is unanswered… refusing loudly and keeping-the-newest are
    both defensible and the ticket picks neither" — and the answer landed as a
    refusal, recorded in ADR 0127. So this test carries no credit for having
    predicted the behaviour. What it is worth is that the decision cannot now be
    reversed silently, which is exactly what the mutation battery measured: with
    the guard removed from `downgrade()`, the whole suite stayed green.

    **The state is one the one-row rule cannot represent.** The revision below
    restores `uq_tool_signing_key_one_row`, so a database holding a rotation has
    only two ways to get there — discard a key, or leave the index off. Discarding
    is the dangerous one and it is silent: the key that goes is the private half of
    something a platform may already have fetched, nothing regenerates it, and the
    failure surfaces at that platform as a refused assertion naming no key.

    **The first mutation this kills:** the row-count guard removed from
    `downgrade()`, so the migration proceeds and the index creation decides what
    happens to the second key. Every other test in this module seeds exactly one
    key and stays green against that change; this is the only place in the suite
    that puts two there and asks. That is the survivor the E3-01 mutation battery
    found.

    **The second mutation this kills, and it is why the reduction below is a
    retirement:** a guard that counts **stored** rows rather than live ones. The
    ruling is that it counts live keys, and that with at most one live key the
    downgrade clears the retired rows itself — so retiring a key is the whole of
    what an operator has to do, which is exactly what the refusal's message tells
    them. Under the stored-row count that same retirement changes nothing, the
    second attempt refuses too, and the operator is left following advice that
    does not work. The two counts are indistinguishable on the refusal alone and
    are told apart only here, by taking the advice and requiring it to succeed.

    **Four assertions, because "it refused" is the weakest of them.** It raised;
    the message names a way back to one key rather than only reporting that there
    are too many; the database did not move, so this is a refusal rather than a
    half-applied revision with the version stamped past it; and both keys are
    still stored, which is the thing actually being protected.

    **The near miss, and it is the second half of this test:** a guard that refuses
    every downgrade. That takes a deployment's ability to back out a bad release
    away entirely, and it would pass every assertion above. So one key is retired
    and the same walk has to succeed — and to have really run, which is why the
    rotation columns are required to be gone at the end and the one-row index to
    be back, rather than the exit status being taken as the answer.

    **The retired row is required to be gone, and the live one to remain.** That
    is the other half of the ruling: the one-row schema cannot hold two rows at
    all, so the downgrade deletes what it can no longer represent, and which row
    it deletes is the whole question. A downgrade that kept the retired key and
    dropped the live one would complete, restore the index, and leave the
    deployment signing with nothing — every earlier assertion here green.
    """
    require_rotation_columns(metadata_tables[SIGNING_KEYS].c.keys(), "the declared table")
    config = alembic_config_pointed_at(empty_database)
    below = require_revision(config, THE_REVISION_BELOW, WHAT_IT_IS)

    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    seed_one_signing_key(empty_database, metadata_tables)
    retiring = plant_a_signing_key(empty_database, metadata_tables, REPLACED_AT)
    before = {row["id"]: row[PRIVATE_KEY_COLUMN] for row in stored_signing_keys(empty_database)}
    standing_at = the_stamped_revision(empty_database)
    assert len(before) == 2, (
        f"This test needs two stored keys and the database holds {len(before)}. With one, the "
        "downgrade below is the ordinary case the first test in this module owns, and every "
        "assertion here would be about a refusal that never had a reason to happen."
    )
    staying = [pem for pem in before.values() if pem != retiring]
    assert len(staying) == 1, (
        "The two planted rows do not hold two different keys, so 'the live key is the one that "
        "survived' cannot be told from 'the retired key is'. That is a defect in this test's "
        "planting rather than a finding about the migration."
    )

    refusal = refused_downgrade(config, below)

    named = [word for word in WAYS_BACK_TO_ONE_KEY if word in str(refusal).lower()]
    assert named, (
        f"The downgrade refused and said {str(refusal)!r}, which names no way back to one key. An "
        "operator holding a rotation and a release they need to back out is then stuck between two "
        "commands that both refuse, and the tempting next move is to delete a row by hand — which "
        "is the outcome the refusal exists to prevent. Naming retirement is what makes the refusal "
        "actionable rather than merely correct."
    )
    stamped = the_stamped_revision(empty_database)
    assert stamped != below, (
        f"The database is stamped at {below} after a downgrade that raised; it was at "
        f"{standing_at}. A revision that refuses *after* moving the version is worse than one that "
        "completes: the schema and the stamp disagree, and the next `alembic upgrade head` runs "
        "statements against a database that is not where it says it is. Asserted as 'did not "
        "reach the target' rather than 'did not move at all', because a second E3 migration "
        "landing between the two would legitimately come off first."
    )
    still_there = {
        row["id"]: row[PRIVATE_KEY_COLUMN] for row in stored_signing_keys(empty_database)
    }
    assert still_there == before, (
        f"The refused downgrade left {len(still_there)} of the 2 stored keys, or changed one. A "
        "refusal that costs a key is not a refusal — and the key it costs is the private half of "
        "an identity a platform may already have fetched, which nothing regenerates."
    )
    reported = columns_the_database_reports(empty_database, SIGNING_KEYS)
    lost = sorted({CREATED_AT_COLUMN, RETIRED_AT_COLUMN} - reported)
    assert not lost, (
        f"After the refusal the table has lost {lost}. Then the downgrade did part of its "
        "work before deciding not to do the rest, which is the half-applied state the stamp "
        "assertion above is meant to be evidence against."
    )

    retire_the_key(empty_database, retiring, RETIRED_ON)
    migrate(config, "downgrade", below, "the same walk, with one live key and one retired")

    standing = columns_the_database_reports(empty_database, SIGNING_KEYS)
    assert not {CREATED_AT_COLUMN, RETIRED_AT_COLUMN} & standing, (
        f"After retiring one key the downgrade reported success and `{SIGNING_KEYS}` still carries "
        f"the rotation columns: {sorted(standing)}. Then the near miss is unproven — a guard that "
        "refuses every downgrade and one that refuses only a live rotation are indistinguishable "
        "if the permitted case never actually runs."
    )
    assert ONE_ROW_INDEX in indexes_the_database_reports(empty_database, SIGNING_KEYS), (
        f"The permitted downgrade completed and `{ONE_ROW_INDEX}` is not on `{SIGNING_KEYS}`. The "
        "index is the reason two rows cannot be walked down at all, so a downgrade that clears the "
        "retired rows and then does not restore it has paid the whole price of the refusal and "
        "bought none of it."
    )
    kept = stored_signing_keys(empty_database)
    assert [row[PRIVATE_KEY_COLUMN] for row in kept] == staying, (
        f"After retiring one of two keys the downgrade left {len(kept)} row(s), and not the live "
        "one alone. Two rows means it did not clear what the one-row schema cannot hold — the "
        "ruling has the downgrade delete the retired rows itself, which is what makes retirement "
        "sufficient advice. Zero, or the retired key in place of the live one, is worse than the "
        "refusal this test starts with: it completes, it restores the index, and it leaves the "
        "deployment signing with nothing."
    )
