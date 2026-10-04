"""E5.1-02's migration round-trips — E5.1-12, Part B item 6.

Revision `c5e8a1f3b9d4` creates `ended_teaching_grant`, the append-only record of
every ended teaching grant, and runs `teaching_grant_end_v001.sql`, which creates
the NOLOGIN owner `pulse_grant_end_definer` and the `SECURITY DEFINER` function
`public.end_teaching_instructor`. ADR 0183 gives that owner `SELECT, DELETE` on
`role_assignment`, `SELECT (id, section_id, response_code)` on `nrps_call` and
`INSERT` on `ended_teaching_grant`, and nothing else. Its `downgrade()` says it
drops the function and the table and empties the owner.

**Nothing executed that downgrade until this module.** The shape is
`test_the_summary_job_grants_are_given_back_by_a_downgrade.py`'s, and so is the
reason: a downgrade the revision's docstring describes and no test runs is a
guard cited and never executed (`docs/MISTAKES.md` entry 9).

**What it costs when it is wrong.** The owner holds `DELETE` on `role_assignment`.
A rollback below this revision that left that grant in place, or left the
function callable, leaves a door that deletes teaching grants on a database whose
code does not know the door exists. The owner role is NOLOGIN, so the grant is
reachable only through a function owned by it — which is exactly what the
function-gone assertion is about, and why both are asserted.

**Both currencies are read**, table grain and column grain, for the reason the
model module gives (`docs/MISTAKES.md` entry 35): the owner's read of `nrps_call`
is column-scoped, and `has_table_privilege` is blind to it.

**The scope is asserted as well as the effect.** Two grants that belong to
revisions below this one must survive: `pulse_app`'s `INSERT` on `nrps_call`
(the roster sync's write since E1-11) and `pulse_instructor_definer`'s `INSERT`
on `role_assignment` (the sibling door, E5.1-02's precedent). A revoke written
about a table rather than a role — `REVOKE ALL ON public.role_assignment FROM
PUBLIC, pulse_instructor_definer, …` — or about the application role takes them.

**Whether the owner role itself survives is not asserted.** The migration keeps
it, empty (E0-10's decision for `pulse_reveal_definer`), but the ticket asks only
that it hold nothing; a downgrade that dropped the role would also hold nothing,
and choosing between the two is not this module's to do.

**The revision is named; the one below it is read off the migration**
(`the_revision_below`), and the database is a throwaway (`empty_database`), as in
the model module.
"""

from typing import Any

import pytest
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    columns_the_database_reports,
    migrate,
    require_revision,
    the_revision_below,
)
from fixtures.roster_sync import (
    END_TEACHING_INSTRUCTOR,
    ENDED_TEACHING_GRANT_TABLE,
    GRANT_END_DEFINER_ROLE,
)
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

GRANT_END_REVISION = "c5e8a1f3b9d4"
WHAT_THE_REVISION_IS = (
    "E5.1-02's revision: the `ended_teaching_grant` table and `teaching_grant_end_v001.sql`'s "
    "`pulse_grant_end_definer` and `public.end_teaching_instructor`. If the chain was re-pointed "
    "or the file renamed at merge, this constant is the one place to change"
)

APPLICATION_ROLE = "pulse_app"
INSTRUCTOR_DEFINER = "pulse_instructor_definer"

# What the owner holds at head that the downgrade has to take back, from ADR 0183
# rather than from the SQL file (`docs/MISTAKES.md` entry 19). The table grant on
# `ended_teaching_grant` goes with the table, so it is the head control only.
OWNER_AT_HEAD_WHOLE = {
    ("role_assignment", "SELECT"),
    ("role_assignment", "DELETE"),
    (ENDED_TEACHING_GRANT_TABLE, "INSERT"),
}
OWNER_AT_HEAD_COLUMNS = {
    ("nrps_call", "id", "SELECT"),
    ("nrps_call", "section_id", "SELECT"),
    ("nrps_call", "response_code", "SELECT"),
}

# Grants that belong to revisions below this one and must survive its downgrade.
SURVIVES = {
    (APPLICATION_ROLE, "nrps_call", "INSERT"),
    (INSTRUCTOR_DEFINER, "role_assignment", "INSERT"),
}

ROLE_EXISTS = text("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = :role")
FUNCTION_EXISTS = text(
    "SELECT count(*) FROM pg_catalog.pg_proc p "
    "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
    "WHERE n.nspname = 'public' AND p.proname = :name"
)
HAS_TABLE_PRIVILEGE = text("SELECT has_table_privilege(:role, :relation, :privilege)")

# Everything a role holds on any relation in `public`, at table grain and at column
# grain. Read over the whole schema rather than over the tables this revision
# touched, so "holds nothing" means nothing anywhere.
WHOLE_RELATION_PRIVILEGES = text(
    """
    SELECT c.relname, p.privilege
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE',
                            'REFERENCES', 'TRIGGER']) AS p(privilege)
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm')
      AND has_table_privilege(:role, c.oid, p.privilege)
    """
)
COLUMN_PRIVILEGES = text(
    """
    SELECT c.relname, a.attname, p.privilege
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    CROSS JOIN unnest(ARRAY['SELECT', 'INSERT', 'UPDATE', 'REFERENCES']) AS p(privilege)
    WHERE n.nspname = 'public'
      AND c.relkind IN ('r', 'p', 'v', 'm')
      AND has_column_privilege(:role, c.oid, a.attnum, p.privilege)
    """
)


def read(database: Any, statement: Any, parameters: dict[str, Any]) -> list[Any]:
    """Every row `statement` answers on the superuser connection, as tuples."""
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return [tuple(row) for row in connection.execute(statement, parameters)]
    finally:
        engine.dispose()


def owner_holds(database: Any) -> tuple[set[Any], set[Any]]:
    """What the definer owner holds in `public`, whole and by column; nothing if it is gone."""
    if not read(database, ROLE_EXISTS, {"role": GRANT_END_DEFINER_ROLE}):
        return set(), set()
    whole = set(read(database, WHOLE_RELATION_PRIVILEGES, {"role": GRANT_END_DEFINER_ROLE}))
    columns = set(read(database, COLUMN_PRIVILEGES, {"role": GRANT_END_DEFINER_ROLE}))
    return whole, columns


def function_count(database: Any) -> int:
    return int(read(database, FUNCTION_EXISTS, {"name": END_TEACHING_INSTRUCTOR})[0][0])


def missing_survivors(database: Any) -> list[Any]:
    return [
        (role, table, privilege)
        for role, table, privilege in sorted(SURVIVES)
        if not read(
            database,
            HAS_TABLE_PRIVILEGE,
            {"role": role, "relation": f"public.{table}", "privilege": privilege},
        )[0][0]
    ]


def require_the_head_state(database: Any, when: str) -> None:
    """The function, the table and the owner's grants are all present — the control."""
    assert function_count(database) == 1, (
        f"{when}, `public` declares {function_count(database)} functions named "
        f"`{END_TEACHING_INSTRUCTOR}`; revision {GRANT_END_REVISION} creates exactly one."
    )
    assert columns_the_database_reports(database, ENDED_TEACHING_GRANT_TABLE), (
        f"{when}, there is no `public.{ENDED_TEACHING_GRANT_TABLE}`; revision "
        f"{GRANT_END_REVISION} creates it."
    )
    whole, columns = owner_holds(database)
    assert OWNER_AT_HEAD_WHOLE <= whole and OWNER_AT_HEAD_COLUMNS <= columns, (
        f"{when}, `{GRANT_END_DEFINER_ROLE}` holds {sorted(whole)} on whole relations and "
        f"{sorted(columns)} by column; ADR 0183 gives it {sorted(OWNER_AT_HEAD_WHOLE)} and "
        f"{sorted(OWNER_AT_HEAD_COLUMNS)}. Until the reader finds those, its empty answer after "
        "the downgrade says nothing about a revoke."
    )
    assert not missing_survivors(database), (
        f"{when}, these grants that belong to earlier revisions are absent: "
        f"{missing_survivors(database)}. The scope assertion after the downgrade is that they "
        "survive it, which means nothing if they were never there."
    )


def test_the_grant_ending_door_is_given_back_by_the_downgrade_and_restored_by_the_upgrade(
    empty_database: Any, alembic_config_pointed_at: Any
) -> None:
    """Down: the function and the table are gone and the owner holds nothing. Up: all three return.

    **The control comes first:** at head the function exists, the table exists,
    the owner holds ADR 0183's grants in both currencies, and the two neighbouring
    grants are present. A reader that answered nothing for everything would
    otherwise report a perfect rollback.

    **The mutations that must turn this red**, each in
    `backend/migrations/versions/20261003_c5e8a1f3b9d4_a_teaching_grant_ends_when_the_roster_drops_it.py`:

      - line 119, `op.execute(EMPTY_THE_DEFINER_ROLE)` deleted: the owner keeps
        `SELECT, DELETE` on `role_assignment` and its column read of `nrps_call`;
      - line 115, the `DROP FUNCTION` deleted: a PL/pgSQL body records no
        dependency on the table it names, so the function outlives the table;
      - inside `EMPTY_THE_DEFINER_ROLE`, lines 60-62 (both `nrps_call` revokes)
        deleted: the owner keeps its column read of `nrps_call`, which only the
        column reading sees, because `has_table_privilege` is blind to it.

    **An equivalent mutation, said so it is not mistaken for a gap:** deleting
    only the column-scoped revoke on lines 60-61 leaves this green, because Postgres
    revokes a table's column privileges along with a table-level `REVOKE ALL`
    (line 62). The column revoke is belt and braces, not load-bearing.

    **The near miss it must survive:** the shipped revokes, which name the owner
    role; and the scope assertion is what tells them apart from `REVOKE ALL …
    FROM pulse_app` or a revoke from every grantee of the table.
    """
    config = alembic_config_pointed_at(empty_database)
    require_revision(config, GRANT_END_REVISION, WHAT_THE_REVISION_IS)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    require_the_head_state(empty_database, "At head")

    below = the_revision_below(config, GRANT_END_REVISION)
    migrate(
        config,
        "downgrade",
        below,
        f"stepping from head to {below}, the revision {GRANT_END_REVISION} chains from",
    )

    assert function_count(empty_database) == 0, (
        f"After the downgrade `public.{END_TEACHING_INSTRUCTOR}` is still declared. It is a "
        "`SECURITY DEFINER` door that deletes `role_assignment` rows, left on a database whose code "
        "does not know it exists."
    )
    assert not columns_the_database_reports(empty_database, ENDED_TEACHING_GRANT_TABLE), (
        f"After the downgrade `public.{ENDED_TEACHING_GRANT_TABLE}` is still there; revision "
        f"{GRANT_END_REVISION} created it and its downgrade drops it."
    )
    whole, columns = owner_holds(empty_database)
    assert not whole and not columns, (
        f"After the downgrade `{GRANT_END_DEFINER_ROLE}` still holds {sorted(whole)} on whole "
        f"relations and {sorted(columns)} by column. The revision's docstring says its downgrade "
        "empties the owner; an owner left holding `DELETE` on `role_assignment` is a privilege no "
        "record at the older revision describes."
    )
    gone = missing_survivors(empty_database)
    assert not gone, (
        f"The downgrade also took {gone}, which belong to revisions below this one. Revoke from "
        f"`{GRANT_END_DEFINER_ROLE}`, by name, and nothing else."
    )

    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying the revision the downgrade undid")
    require_the_head_state(empty_database, "After going down and back up")
