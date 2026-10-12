"""The four cohort views are retired, with their grants, and the retirement round-trips — E9-12 done-when 10.

> 10. **The four cohort views are retired.** After the migration none exists and
>    `pulse_app` holds no grant on any; nothing under `backend/app/` names them
>    (search with a canary); downgrade and upgrade round-trip; the §4.1 view
>    sweeps and catalog guards are green with the views gone. If E9-05, E9-07 or
>    E9-09 recorded that one of them is read, that view is kept and the pull
>    request says so.

README decision 10 names the four: `benchmark_cohort_week`,
`benchmark_cohort_rating_week`, `benchmark_cohort_term_axis` and
`benchmark_cohort_rating_term_axis`. E9-05 deleted their last reader
(`named_set_term_axis`); none of E9-05, E9-07 or E9-09 recorded a reader in its
pull request (the bodies this ticket's work order names). The migration is
`e9e5b7d9f605` (the ticket's "Owns"), and its downgrade recreates them from their
versioned files.

**Three tests, each a different layer.** At head, on the session database: no
relation of any of the four names exists in **any** schema, of any kind (a view
moved to another schema, or re-created as a table or a materialized view, is the
one-level-out escape — `docs/MISTAKES.md` entry 53); and `pulse_app` holds no
privilege on any, at relation or column grain. Each has its **present twin**: a
view that stays (`report_workload`, E4-03's) exists and is granted to `pulse_app`,
read by the same catalog query. **The round trip** walks a database of its own
(`empty_database`, so no other test's database moves — `docs/MISTAKES.md` entry
12) up to head, down to the revision below `e9e5b7d9f605`, and back up: in the
middle the four exist again with their columns and `pulse_app`'s `SELECT`, at
both ends they do not.

The name sweep is `tests/unit/test_nothing_under_the_application_names_a_retired_
cohort_view.py`; the catalog guard that lists sanctioned view columns
(`tests/integration/test_identity_grants.py`) no longer sanctions the four.

**Which failure a red is, before the migration exists:** the two head tests FAIL
on their assertions (the four views are there, and granted); the round trip FAILS
naming the missing revision `e9e5b7d9f605`. Their twins are green throughout.
"""

from typing import Any

import pytest
from fixtures.database import TEST_APP_USER
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    columns_the_database_reports,
    migrate,
    require_revision,
    session_on,
    the_revision_below,
)
from sqlalchemy import text

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

THE_RETIREMENT = "e9e5b7d9f605"
WHAT_IT_IS = "E9-12's migration, which drops the four cohort views and their grants"

# The four, and the columns each carried when it was last sanctioned for
# `pulse_app` (`tests/integration/test_identity_grants.py` before E9-12; the term
# axis's last two arrived with `benchmark_cohort_term_axis_v002.sql`). The
# downgrade recreates them from their versioned files, so these are what comes
# back.
RETIRED_VIEWS: dict[str, tuple[str, ...]] = {
    "benchmark_cohort_week": (
        "length_weeks",
        "level",
        "term_id",
        "course_week",
        "workload_mean",
        "workload_median",
        "response_count",
        "respondent_count",
        "section_count",
    ),
    "benchmark_cohort_rating_week": (
        "length_weeks",
        "level",
        "term_id",
        "course_week",
        "stream",
        "rating_mean",
        "rating_count",
    ),
    "benchmark_cohort_term_axis": (
        "length_weeks",
        "level",
        "term_id",
        "section_start_date",
        "term_week",
        "workload_mean",
        "workload_median",
        "response_count",
        "respondent_count",
        "section_count",
        "workload_respondent_count",
        "workload_section_count",
    ),
    "benchmark_cohort_rating_term_axis": (
        "length_weeks",
        "level",
        "term_id",
        "section_start_date",
        "term_week",
        "stream",
        "rating_mean",
        "rating_count",
    ),
}

# A view this ticket does not touch, read by the same queries as the twin.
A_VIEW_THAT_STAYS = "report_workload"

RELATIONS_NAMED = text(
    "SELECT n.nspname AS schema_name, c.relname AS relation, c.relkind::text AS kind "
    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE c.relname = ANY(:names)"
)
# Read off the ACLs themselves rather than `information_schema`, whose grant views
# answer only for roles the reading session is a member of: `pg_class.relacl` for a
# grant on the relation, `pg_attribute.attacl` for a grant on one column of it
# (which no `relacl` records — `test_identity_grants.py`'s own measurement).
RELATION_GRANTS = text(
    "SELECT c.relname AS relation, '' AS column_name, a.privilege_type AS privilege "
    "FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a "
    "JOIN pg_roles r ON r.oid = a.grantee "
    "WHERE r.rolname = :grantee AND c.relname = ANY(:names)"
)
COLUMN_GRANTS = text(
    "SELECT c.relname AS relation, att.attname AS column_name, a.privilege_type AS privilege "
    "FROM pg_class c JOIN pg_attribute att ON att.attrelid = c.oid "
    "CROSS JOIN LATERAL aclexplode(att.attacl) a "
    "JOIN pg_roles r ON r.oid = a.grantee "
    "WHERE r.rolname = :grantee AND c.relname = ANY(:names) AND att.attnum > 0"
)


def relations(session: Any, names: list[str]) -> list[tuple[str, str, str]]:
    rows = session.execute(RELATIONS_NAMED, {"names": names}).mappings()
    return sorted((row["schema_name"], row["relation"], row["kind"]) for row in rows)


def grants(session: Any, names: list[str]) -> list[tuple[str, str, str]]:
    """Every `(relation, column or '', privilege)` `pulse_app` holds on a relation so named."""
    found: list[tuple[str, str, str]] = []
    for query in (RELATION_GRANTS, COLUMN_GRANTS):
        rows = session.execute(query, {"grantee": TEST_APP_USER, "names": names}).mappings()
        found += [(row["relation"], row["column_name"], row["privilege"]) for row in rows]
    return sorted(found)


def test_none_of_the_four_cohort_views_exists_at_head(db_session: Any) -> None:
    """No relation named for a retired view, in any schema, of any kind; a staying view is found.

    **The twin:** `report_workload` is found by the same query, so the catalog read
    is not blind.

    **The mutation it kills:** the migration dropping three of the four, or none;
    a view re-created under another schema or as a table. **The near miss it
    spares:** E5-03's two set functions, which stay (they are functions, not
    relations, and the roll-ups read them).
    """
    retired = sorted(RETIRED_VIEWS)
    twin = relations(db_session, [A_VIEW_THAT_STAYS])
    assert twin, f"The twin failed: the catalog read finds no `{A_VIEW_THAT_STAYS}` at all."
    found = relations(db_session, retired)
    assert not found, (
        f"At head the catalog still holds {found}. README decision 10 retires all four cohort "
        "views; E9-12's migration drops them."
    )


def test_pulse_app_holds_no_grant_on_a_retired_cohort_view(db_session: Any) -> None:
    """`pulse_app` holds no relation or column privilege on any of the four; it holds one on a staying view.

    **The mutation it kills:** the grants file still granting a relation of one
    of these names (a view re-created, or a table or materialized view left in
    its place), at relation or at column grain. **The near miss it spares:**
    `pulse_app`'s `EXECUTE` on the two set functions, which are not relations.
    **The twin:** `report_workload`'s `SELECT` is found by the same query.
    """
    twin = grants(db_session, [A_VIEW_THAT_STAYS])
    assert twin, (
        f"The twin failed: `{TEST_APP_USER}` is found holding nothing on `{A_VIEW_THAT_STAYS}`, so "
        "the grant read is blind."
    )
    found = grants(db_session, sorted(RETIRED_VIEWS))
    assert not found, f"`{TEST_APP_USER}` still holds {found} on the retired cohort views."


def test_the_retirement_round_trips_and_the_downgrade_restores_views_and_grants(
    empty_database: Any, alembic_config_pointed_at: Any
) -> None:
    """Up to head, down below `e9e5b7d9f605`, up again: gone, back with columns and grants, gone.

    **The middle of the trip is asserted** (`docs/MISTAKES.md` entry 3): a
    downgrade written as `pass` round-trips perfectly and proves nothing, so
    below the revision each view exists with exactly its last versioned columns
    and `pulse_app` may `SELECT` it.

    **The mutation it kills:** a downgrade that recreates the views without their
    grant (the term axis read by nothing, but the downgrade claims a state it does
    not restore), from a stale versioned file (`benchmark_cohort_term_axis_v001`,
    two columns short), or not at all; an upgrade that drops three. **The near
    miss it spares:** the views coming back with their columns in another
    ordinal order (compared as sets).
    """
    config = alembic_config_pointed_at(empty_database)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    revision = require_revision(config, THE_RETIREMENT, WHAT_IT_IS)
    below = the_revision_below(config, revision)
    retired = sorted(RETIRED_VIEWS)

    with session_on(empty_database) as session:
        at_head = relations(session, retired)
    assert not at_head, f"After the upgrade to head the catalog holds {at_head}."

    migrate(config, "downgrade", below, "undoing the retirement")
    restored = {
        name: sorted(columns_the_database_reports(empty_database, name)) for name in retired
    }
    with session_on(empty_database) as session:
        granted = {
            relation
            for relation, _column, privilege in grants(session, retired)
            if privilege == "SELECT"
        }
    wrong = {
        name: columns
        for name, columns in restored.items()
        if columns != sorted(RETIRED_VIEWS[name])
    }
    assert not wrong, (
        f"Below {THE_RETIREMENT} the views came back as {wrong}; their last versioned files give "
        f"{ {name: sorted(RETIRED_VIEWS[name]) for name in wrong} }."
    )
    assert granted == set(retired), (
        f"Below {THE_RETIREMENT} `{TEST_APP_USER}` may SELECT {sorted(granted)} of the four; the "
        "downgrade restores the grants with the views."
    )

    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying the retirement")
    with session_on(empty_database) as session:
        again = relations(session, retired)
        still = grants(session, retired)
    assert (
        not again and not still
    ), f"After the round trip the catalog holds {again} and `{TEST_APP_USER}` holds {still}."
