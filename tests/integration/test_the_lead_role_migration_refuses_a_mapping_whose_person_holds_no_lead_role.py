"""Migration `e9b8c0d2e417` refuses to upgrade over a mapping whose person holds no lead role — E9-14 fix round, P3.

E9-14 item 2 makes the map definer refuse a person with no live `LEAD_FACULTY`
assignment, and the revoke definer refuse while a lead still has mappings, so
no new write can make "a course led by somebody who is not a lead". A row
written before the migration can still be there, and the definers never look at
it. The fix round: the upgrade raises `RuntimeError` with a clear sentence when
any `lead_faculty_mapping` row's person holds no `LEAD_FACULTY` assignment, so
the gap is surfaced to whoever migrates rather than carried forward.

The shape is `test_the_people_graph_downgrade_refuses_while_an_admin_write_is_
audited.py`'s: a throwaway database (`empty_database`, never the session one,
`docs/MISTAKES.md` entry 12), the refusal found as a `RuntimeError` anywhere in
the exception's chain, and the database read afterwards so a guard that raised
part-way is not mistaken for one that refused.

**Which failure a red is, on e88d4fc8.** The upgrade has no such guard, so the
refusal test FAILS on "the upgrade completed". The twin is green.
"""

from typing import Any

import pytest
from fixtures.migration_journey import MODEL_SCHEMA, migrate, require_revision, session_on
from fixtures.supervision import SupervisionGraph, seed_row
from sqlalchemy import create_engine, text
from test_the_response_records_downgrade_refuses_while_a_row_exists import is_a_runtime_error

pytestmark = pytest.mark.integration

E9_14_REVISION = "e9b8c0d2e417"
BELOW_E9_14 = "e9e5b7d9f605"


def scalar(database: Any, sql: str) -> Any:
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return connection.execute(text(sql)).scalar_one_or_none()
    finally:
        engine.dispose()


def below_e9_14(config: Any) -> None:
    """Head, then down to the revision below E9-14's, over an empty database."""
    require_revision(config, E9_14_REVISION, "E9-14's migration")
    require_revision(config, BELOW_E9_14, "the revision E9-14's migration chains from")
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    migrate(config, "downgrade", BELOW_E9_14, "stepping below E9-14 over an empty database")


def plant_a_mapping(database: Any, tables: dict[str, Any], *, lead_role: bool) -> None:
    """One course mapped to one person, committed; the person holds `LEAD_FACULTY` or nothing.

    With `lead_role`, the assignment is at the same course, which is the shape
    every lead in the seeded world has.
    """
    with session_on(database) as session:
        chain: dict[str, Any] = {}
        seed_row(session, tables, "section", chain)
        person = seed_row(session, tables, "person", {})["id"]
        graph = SupervisionGraph(session, tables)
        if lead_role:
            graph.assign("LEAD_FACULTY", scope=chain["course"]["id"], person=person)
        graph.lead_mapping(person=person, course=chain["course"]["id"])


def upgrade(config: Any) -> BaseException | None:
    from alembic import command

    try:
        command.upgrade(config, E9_14_REVISION)
    except Exception as refusal:
        return refusal
    return None


def test_the_upgrade_refuses_while_a_mapping_names_a_person_with_no_lead_role(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """One mapping below E9-14 whose person holds no assignment: the upgrade raises; nothing moved.

    **The mutations it kills:** no guard, so a course stays "led" by a person
    the review queue does not count as a lead (its harmful comments reach no
    queue); a guard that deletes the mapping silently instead of refusing; a
    guard that raises after the definers were replaced (the version is read
    back). **The near miss it spares:** the same mapping with the role (below).
    """
    config = alembic_config_pointed_at(empty_database)
    below_e9_14(config)
    plant_a_mapping(empty_database, metadata_tables, lead_role=False)

    failure = upgrade(config)

    assert failure is not None, (
        f"`alembic upgrade {E9_14_REVISION}` completed over a lead mapping whose person holds no "
        "`LEAD_FACULTY` assignment. Fix round P3: the upgrade refuses, so the gap is surfaced."
    )
    assert is_a_runtime_error(failure), f"The upgrade failed with {failure!r}, not `RuntimeError`."
    assert (
        scalar(empty_database, "SELECT count(*) FROM public.lead_faculty_mapping") == 1
    ), "The refused upgrade removed the mapping instead of leaving it for someone to resolve."
    assert (
        scalar(empty_database, "SELECT version_num FROM public.alembic_version") == BELOW_E9_14
    ), "The refused upgrade left the database stamped at another revision."


def test_the_upgrade_completes_when_every_mapped_person_holds_the_lead_role(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """The twin: the same mapping, its person holding `LEAD_FACULTY`, upgrades to E9-14.

    **The mutation it kills:** a guard that refuses any mapping at all, or that
    checks the role at the mapped course in a way the seeded leads fail.
    """
    config = alembic_config_pointed_at(empty_database)
    below_e9_14(config)
    plant_a_mapping(empty_database, metadata_tables, lead_role=True)

    failure = upgrade(config)

    assert failure is None, f"The upgrade over a clean mapping failed: {failure!r}."
    assert (
        scalar(empty_database, "SELECT version_num FROM public.alembic_version") == E9_14_REVISION
    )
