"""M1's downgrade refuses to destroy the response records — E7-01, done-when 1.

> The downgrade refuses while a row exists, and runs clean on an empty table.

The ticket: "Its downgrade refuses while either table holds a row, as E6-09 made
the moderation downgrades do." So the precedent's shape is the assertion
(`test_the_moderation_downgrades_refuse_to_destroy_what_they_hold.py`): the
downgrade raises, the error is the precedent's `RuntimeError` (so a SQL error a
half-built downgrade trips over does not pass for a refusal), and the row is still
there afterwards (a guard that raised after dropping the table satisfies the first
two). **One row in one table at a time**, so a guard that counts only one of the
two tables is red on the other.

**M1 is found, not named**: the one revision whose `down_revision` is
`b7d2e94c1a05` (the work order's "Migration M1"). Its id is the implementer's.

**The empty round trip is the control**: head, below M1, head again, over no rows,
completes — with both tables shown gone in the middle, so a downgrade that did
nothing is not mistaken for one that passed.

Each test migrates a throwaway database (`empty_database`), never the session one
(`docs/MISTAKES.md` entry 12).

**Which failure a red is, before E7-01 lands.** `the_m1_revision` fails: no
revision chains from `b7d2e94c1a05`.
"""

from typing import Any

import pytest
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    columns_the_database_reports,
    migrate,
    session_on,
)
from fixtures.staff_names import (
    AI_SEEDED_COLUMN,
    INSTRUCTOR_RESPONSE,
    M1_DOWN_REVISION,
    MODE_COLUMN,
    PERSON_TABLE,
    PREFIX_TABLE,
    RESPONSE_POLICY,
    ROLE_COLUMN,
    SECTION_TABLE,
    only_reference,
    require_the_tables,
)
from fixtures.supervision import seed_row
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration


def the_m1_revision(config: Any) -> str:
    """The one revision chaining from `b7d2e94c1a05`, or a failure naming the work order."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(config)
    above = [
        revision.revision
        for revision in script.walk_revisions()
        if M1_DOWN_REVISION
        in (
            revision.down_revision
            if isinstance(revision.down_revision, tuple)
            else (revision.down_revision,)
        )
    ]
    if len(above) != 1:
        pytest.fail(
            f"{len(above)} revisions chain from `{M1_DOWN_REVISION}` ({above}). E7-01 owns M1, "
            f'with `down_revision = "{M1_DOWN_REVISION}"`, and no other E7 ticket adds a migration.'
        )
    return above[0]


def count(database: Any, table: str) -> int:
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return int(
                connection.execute(text(f"SELECT count(*) FROM public.{table}")).scalar_one()  # noqa: S608
            )
    finally:
        engine.dispose()


def refused(config: Any, revision: str) -> BaseException | None:
    from alembic import command

    try:
        command.downgrade(config, revision)
    except Exception as refusal:
        return refusal
    return None


def is_a_runtime_error(failure: BaseException | None) -> bool:
    seen: set[int] = set()
    while failure is not None and id(failure) not in seen:
        if isinstance(failure, RuntimeError):
            return True
        seen.add(id(failure))
        failure = failure.__cause__ or failure.__context__
    return False


def plant(database: Any, tables: dict[str, Any], name: str) -> None:
    """One row of `name` at head, every spelled column named and every reference followed.

    The writer is the chain's course's Lead Faculty — the assignment and the
    mapping — because the fix round's F1 and F3 triggers refuse a `LEAD_FACULTY`
    row from anybody else, on every connection.
    """
    from fixtures.supervision import SupervisionGraph

    with session_on(database) as session:
        chain: dict[str, Any] = {}
        seed_row(session, tables, SECTION_TABLE, chain)
        chain[PERSON_TABLE] = seed_row(session, tables, PERSON_TABLE, {})
        graph = SupervisionGraph(session, tables)
        graph.assign("LEAD_FACULTY", scope=chain["course"]["id"], person=chain[PERSON_TABLE]["id"])
        graph.lead_mapping(person=chain[PERSON_TABLE]["id"], course=chain["course"]["id"])
        table = tables[name]
        values: dict[str, Any] = {ROLE_COLUMN: "LEAD_FACULTY"}
        values[only_reference(table, PERSON_TABLE)] = chain[PERSON_TABLE]["id"]
        if name == INSTRUCTOR_RESPONSE:
            values[only_reference(table, SECTION_TABLE)] = chain[SECTION_TABLE]["id"]
            values[AI_SEEDED_COLUMN] = False
        else:
            values[only_reference(table, PREFIX_TABLE)] = chain[PREFIX_TABLE]["id"]
            values[MODE_COLUMN] = "REQUIRED"
        seed_row(session, tables, name, chain, **values)


def a_lead_in_a_fresh_prefix(session: Any, tables: dict[str, Any]) -> tuple[Any, Any]:
    """A section's whole chain and a person who leads its course; (the prefix key, the lead's key)."""
    from fixtures.supervision import SupervisionGraph

    chain: dict[str, Any] = {}
    seed_row(session, tables, SECTION_TABLE, chain)
    lead = seed_row(session, tables, PERSON_TABLE, {})["id"]
    graph = SupervisionGraph(session, tables)
    graph.assign("LEAD_FACULTY", scope=chain["course"]["id"], person=lead)
    graph.lead_mapping(person=lead, course=chain["course"]["id"])
    return chain[PREFIX_TABLE]["id"], lead


# M1's own `response_policy` columns, written out: `Base.metadata` describes head,
# where E7-02's M2 has added `course_id`, so a row planted at M1 is written in SQL
# naming exactly the columns M1 created (ADR 0192).
POLICY_ROW_AT_M1 = (
    "INSERT INTO public.response_policy (prefix_id, set_by_person_id, role, mode, set_at) "
    "VALUES (CAST(:prefix AS uuid), CAST(:setter AS uuid), 'LEAD_FACULTY', 'REQUIRED', now())"
)


def write_a_policy_row_at_m1(database: Any, *, prefix: Any, setter: Any) -> BaseException | None:
    """One M1-shaped policy row, committed on its own session; the error it raised, or `None`."""
    from sqlalchemy.exc import DatabaseError

    try:
        with session_on(database) as session:
            session.execute(text(POLICY_ROW_AT_M1), {"prefix": str(prefix), "setter": str(setter)})
    except DatabaseError as failure:
        return failure
    return None


def plant_a_policy_row_at_m1(database: Any, tables: dict[str, Any]) -> None:
    """One policy row in a database standing at M1, written by the course's lead.

    For E7-02's fix round (H1): M2's downgrade refuses while `response_policy`
    holds a row, so a policy row planted at head is refused by M2 and never
    reaches M1's own check. The row is planted *after* stepping down to M1, so the
    refusal measured is M1's.
    """
    with session_on(database) as session:
        prefix, lead = a_lead_in_a_fresh_prefix(session, tables)
    failure = write_a_policy_row_at_m1(database, prefix=prefix, setter=lead)
    assert failure is None, f"The lead's policy row at M1 was refused: {failure!r}. A broken world."


@pytest.mark.parametrize(
    ("planted", "other"),
    [(INSTRUCTOR_RESPONSE, RESPONSE_POLICY), (RESPONSE_POLICY, INSTRUCTOR_RESPONSE)],
)
def test_the_m1_downgrade_refuses_while_one_record_holds_a_row(
    planted: str,
    other: str,
    empty_database: Any,
    metadata_tables: dict[str, Any],
    alembic_config_pointed_at: Any,
) -> None:
    """One row in `planted`, none in `other`: `RuntimeError`, and the row is still there.

    **E7-02's fix round (H1) moves where the policy row is planted.** M2 sits on
    top of M1 and its downgrade refuses while `response_policy` holds a row, so a
    policy row planted at head would be refused by M2 — a `RuntimeError` with the
    row intact, green for a reason that is not M1's (`docs/MISTAKES.md` entry 3).
    So the database steps down to M1 over an empty policy table first, and the
    policy row is planted there. The response row is still planted at head: M2's
    downgrade counts no response, so it steps through to M1's check.

    **The mutation this kills:** a downgrade that drops both tables over their
    rows, and a guard that counts only `other` (which this row does not trip).
    """
    require_the_tables(metadata_tables)
    config = alembic_config_pointed_at(empty_database)
    m1 = the_m1_revision(config)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    if planted == RESPONSE_POLICY:
        migrate(config, "downgrade", m1, "stepping below M2 over an empty policy table")
        plant_a_policy_row_at_m1(empty_database, metadata_tables)
    else:
        plant(empty_database, metadata_tables, planted)
    assert count(empty_database, planted) == 1, f"The planted `{planted}` row is not there."
    assert count(empty_database, other) == 0, f"`{other}` holds a row this test did not plant."

    failure = refused(config, M1_DOWN_REVISION)
    assert failure is not None, (
        f"`alembic downgrade {M1_DOWN_REVISION}` completed over a `{planted}` row, dropping the "
        f"record (ruling 7: 'these tables are the record'). E7-01: the downgrade of {m1} refuses "
        "while either table holds a row."
    )
    assert is_a_runtime_error(
        failure
    ), f"The downgrade failed with {failure!r}, not the precedent's `RuntimeError`."
    assert count(empty_database, planted) == 1, f"After the refusal the `{planted}` row is gone."


def test_the_m1_downgrade_round_trips_over_empty_tables(
    empty_database: Any, metadata_tables: dict[str, Any], alembic_config_pointed_at: Any
) -> None:
    """The control: head, below M1, head again, over no rows — both tables gone, then back.

    **The mutation this kills:** a guard that refuses unconditionally, which makes
    the migration impossible to step back.
    """
    require_the_tables(metadata_tables)
    config = alembic_config_pointed_at(empty_database)
    the_m1_revision(config)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")
    for name in (INSTRUCTOR_RESPONSE, RESPONSE_POLICY):
        assert columns_the_database_reports(empty_database, name), f"No `{name}` at head."

    migrate(config, "downgrade", M1_DOWN_REVISION, "walking an empty database below M1")
    for name in (INSTRUCTOR_RESPONSE, RESPONSE_POLICY):
        assert not columns_the_database_reports(
            empty_database, name
        ), f"Below M1 `{name}` is still there, so the downgrade did not run."

    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying M1")
    for name in (INSTRUCTOR_RESPONSE, RESPONSE_POLICY):
        assert columns_the_database_reports(empty_database, name), f"After the trip no `{name}`."
