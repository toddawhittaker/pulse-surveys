"""The set-name index migration renames near-duplicates; its downgrade drops only the index.

> 13. … The migration renames existing near-duplicates and its downgrade drops
>     only the index.

E9-05's interface, for migration `e9a7c9e1b807`:

> - Group rows by `lower(btrim(regexp_replace(name, '\\s+', ' ', 'g')))`, ordered
>   by `(created_at, id)`.
> - The first row in each group keeps its name. The others get ` (2)`, ` (3)`
>   and so on, using the smallest number whose normalized form is free.
> - Then run `CREATE UNIQUE INDEX uq_comparison_set_normalized_name …`.
> - **Downgrade:** drops the index only. Renamed rows stay renamed.

**The journey.** A database of its own (`empty_database`, `docs/MISTAKES.md`
entry 12) is upgraded to the revision below `e9a7c9e1b807` — read off the
migration's own `down_revision`, so a re-point moves this test with it — and
four sets are planted there that the old schema allows:

  - "nursing  core", created first;
  - "Nursing core", created second, a near-duplicate of the first;
  - "NURSING CORE", created third, another;
  - "Nursing core (2)", created before all three — a different name whose
    normalized form is exactly the first rename a naive numbering would choose;
  - "Biology", unrelated, the control.

Then the database is upgraded through `e9a7c9e1b807` and down again.

**What is expected, worked out by hand from the rule.** The group is ordered by
creation, so "nursing  core" (the earliest, and *last* in byte order — an order
by name would choose another) keeps its name. "Nursing core" takes the smallest
free suffix: " (2)" normalizes to "nursing core (2)", which the fourth row
holds, so it is " (3)". "NURSING CORE" then finds " (2)" and " (3)" taken and
takes " (4)". "Nursing core (2)" and "Biology" are untouched. A numbering that
ignored what is free makes the index creation fail, which `migrate` reports as
the step that did not complete.

**Which failure a red is, before E9-05 lands:** FAILED naming the missing
revision `e9a7c9e1b807`.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.comparison_sets import (
    COMPARISON_SET_TABLE,
    LENGTH_COLUMN,
    LEVEL_COLUMN,
    NAME_COLUMN,
    assert_refused_for_the_data,
    refusal_of,
)
from fixtures.migration_journey import (
    migrate,
    require_revision,
    session_on,
    the_revision_below,
)
from fixtures.supervision import seed_row
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

THE_REVISION = "e9a7c9e1b807"
THE_INDEX = "uq_comparison_set_normalized_name"
CREATED_AT_COLUMN = "created_at"

# (name, created at) — planted at the revision below, in this order of creation.
PLANTED = (
    ("Nursing core (2)", datetime(2026, 1, 5, 9, 0, tzinfo=UTC)),
    ("nursing  core", datetime(2026, 1, 6, 9, 0, tzinfo=UTC)),
    ("Nursing core", datetime(2026, 1, 7, 9, 0, tzinfo=UTC)),
    ("NURSING CORE", datetime(2026, 1, 8, 9, 0, tzinfo=UTC)),
    ("Biology", datetime(2026, 1, 9, 9, 0, tzinfo=UTC)),
)

# What each planted row is called after the upgrade, by the rule, by hand.
EXPECTED_AFTER = {
    "Nursing core (2)": "Nursing core (2)",
    "nursing  core": "nursing  core",
    "Nursing core": "Nursing core (3)",
    "NURSING CORE": "NURSING CORE (4)",
    "Biology": "Biology",
}

INDEX_PRESENT = text(
    "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public' AND indexname = :name"
)


def names_by_creation(database: Any) -> dict[datetime, str]:
    """Every set's name, keyed by the creation instant this module planted it with."""
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(f"SELECT {CREATED_AT_COLUMN}, {NAME_COLUMN} FROM {COMPARISON_SET_TABLE}")  # noqa: S608
            )
            return {row[0]: row[1] for row in rows}
    finally:
        engine.dispose()


def index_is_there(database: Any) -> bool:
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return bool(connection.execute(INDEX_PRESENT, {"name": THE_INDEX}).scalar())
    finally:
        engine.dispose()


def plant_the_sets(database: Any, metadata_tables: dict[str, Any]) -> None:
    with session_on(database) as session:
        chain: dict[str, Any] = {}
        for name, created_at in PLANTED:
            seed_row(
                session,
                metadata_tables,
                COMPARISON_SET_TABLE,
                chain,
                **{
                    NAME_COLUMN: name,
                    LENGTH_COLUMN: 6,
                    LEVEL_COLUMN: "UG",
                    CREATED_AT_COLUMN: created_at,
                },
            )
            chain.pop(COMPARISON_SET_TABLE, None)


def test_the_upgrade_renames_near_duplicates_by_creation_order_and_the_smallest_free_suffix(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """The renames worked out in the module docstring, and the index in place afterwards.

    **The mutations this kills:** near-duplicates deleted rather than renamed
    (four rows become two); the group ordered by name or by id instead of
    creation (the wrong row keeps its name); a numbering by rank that ignores
    which suffixes are free (the index creation fails on "nursing core (2)");
    the index created without the renames (the upgrade fails on the planted
    rows). **The near miss:** "Nursing core (2)" and "Biology" keep their names.
    """
    config = alembic_config_pointed_at(empty_database)
    require_revision(config, THE_REVISION, "E9-05's set-name index migration")
    below = the_revision_below(config, THE_REVISION)
    migrate(config, "upgrade", below, f"standing at {below}, below the set-name index")
    plant_the_sets(empty_database, metadata_tables)
    planted = names_by_creation(empty_database)
    assert sorted(planted.values()) == sorted(
        name for name, _ in PLANTED
    ), f"The planted rows read back as {planted}; a broken world, not a red."

    migrate(config, "upgrade", THE_REVISION, "applying the set-name index")

    after = names_by_creation(empty_database)
    expected = {created_at: EXPECTED_AFTER[name] for name, created_at in PLANTED}
    assert after == expected, (
        f"After the upgrade the sets are named {sorted(after.values())}, not "
        f"{sorted(expected.values())}. The interface: the first row of each normalized group, by "
        "(created_at, id), keeps its name; the others take ' (n)' with the smallest n whose "
        "normalized form is free. Rows are renamed, never deleted."
    )
    assert index_is_there(empty_database), f"`{THE_INDEX}` is not in the catalog after the upgrade."


def test_the_downgrade_drops_the_index_and_nothing_else(
    empty_database: Any, alembic_config_pointed_at: Any, metadata_tables: dict[str, Any]
) -> None:
    """Down one step: the index is gone, the renamed rows stay renamed, `UNIQUE (name)` stays.

    **The controls in the body:** after the downgrade a near-duplicate inserts
    (so the index really is gone, by behaviour as well as by catalog), and an
    exact duplicate is still refused (so the downgrade took nothing else).

    **The mutations this kills:** a downgrade that "restores" the old names
    (it cannot know them, and a guess is a rename nobody asked for); one that
    drops the name's own unique constraint with the index; one that leaves the
    index behind.
    """
    config = alembic_config_pointed_at(empty_database)
    require_revision(config, THE_REVISION, "E9-05's set-name index migration")
    below = the_revision_below(config, THE_REVISION)
    migrate(config, "upgrade", below, f"standing at {below}, below the set-name index")
    plant_the_sets(empty_database, metadata_tables)
    migrate(config, "upgrade", THE_REVISION, "applying the set-name index")
    renamed = names_by_creation(empty_database)

    migrate(config, "downgrade", below, "undoing the set-name index")

    assert not index_is_there(empty_database), f"`{THE_INDEX}` survived the downgrade."
    assert names_by_creation(empty_database) == renamed, (
        f"The downgrade changed the sets' names: {names_by_creation(empty_database)} where the "
        f"upgrade left {renamed}. The interface: 'Renamed rows stay renamed.'"
    )
    with session_on(empty_database) as session:
        near = refusal_of(
            session,
            lambda: seed_row(
                session,
                metadata_tables,
                COMPARISON_SET_TABLE,
                {},
                **{NAME_COLUMN: "BIOLOGY", LENGTH_COLUMN: 6, LEVEL_COLUMN: "UG"},
            ),
        )
        assert near is None, (
            f"After the downgrade, 'BIOLOGY' beside 'Biology' was refused: {near}. The index is "
            "gone, so only an exact duplicate is."
        )
        exact = refusal_of(
            session,
            lambda: seed_row(
                session,
                metadata_tables,
                COMPARISON_SET_TABLE,
                {},
                **{NAME_COLUMN: "Biology", LENGTH_COLUMN: 6, LEVEL_COLUMN: "UG"},
            ),
        )
        assert_refused_for_the_data(
            exact,
            "After the downgrade, a second set named 'Biology'",
            "E5-01's `UNIQUE (name)` is not the index's to drop.",
        )
