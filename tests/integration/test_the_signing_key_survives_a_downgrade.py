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

**Only one key is seeded, and that is a limit rather than an oversight.** At the
revision below, the one-row rule is back on the table, so a database holding two
keys cannot be represented there at all — and what a downgrade should do about a
second key (refuse loudly, or keep the newest and discard the rest) is a decision
E3-01 does not make and this module must not make for it. What is asserted is the
state a downgrade must always be able to handle: one key, kept.

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

# One instant, aware as ADR 0019 requires, so the seeded row carries a value this
# module chose rather than one the server default invented.
SUPPLIED_AT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


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
