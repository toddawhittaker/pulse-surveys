"""The column grant E3-05 spends comes back off a downgrade — ticket E3-05, decision D6.

E3-05 grants `pulse_app` `UPDATE` on `section(ags_line_item_url)` and on nothing
else, through a new file under `backend/app/views_sql/` executed by a migration of
its own. Decision D6 requires that migration's `downgrade()` to issue the
**column-grain** revoke, and says why in the note it asks to be mirrored from the
revision below it: *a column ACL survives table-level revokes.*

That sentence is the whole of this module. `REVOKE UPDATE ON public.section FROM
pulse_app` is the revoke somebody writes when they are thinking about the table,
and against a privilege that was granted at column grain it does nothing at all —
Postgres keeps the entry in `pg_attribute.attacl`, `has_column_privilege` goes on
answering true, and an operator who rolled a deployment back is left with a
connection that can still write the column the rollback was meant to take away.
Nothing else in this suite would notice: `test_identity_grants.py` pins the
inventory at head, which is where the grant is supposed to be.

**Both directions, and the near miss is the interesting one.** The revoke has to
reach E3-05's column and has to *leave alone* `section(lms_ags_line_items_url)`,
which is E3-02's grant one revision below and which a blanket revoke on the table
— or on the role — would take with it. A downgrade that revoked too much is a
database an operator cannot use afterwards: a launch could no longer store the
gradebook address the platform advertised, and the failure would show up as
sections that stop being discoverable rather than as anything naming this
migration.

**The revision is found by walking rather than named**, exactly as
`test_the_passback_schema_survives_a_downgrade.py` finds E3-02's and for the same
reason: this module is written before the migration exists, so there is no
identifier to pin. The database is stepped down one revision at a time until the
privilege is gone, which is also the assertion that *some* revision revokes it.
The walk is bounded and running past the bound is a failure saying so rather than
a hang.

**Each test migrates a database of its own.** `empty_database` is a second
database in the same container, created for one test and dropped after, so a
downgrade here cannot touch the session database every other integration test
reads (`docs/MISTAKES.md` entry 12).

**Which failure a red here is.** Before E3-05 lands, this fails on the control at
the top — the privilege is not held at head at all — which is a failed assertion
naming the grant, before any migration is run backwards.
"""

from typing import Any

import pytest
from fixtures.migration_journey import MODEL_SCHEMA, columns_the_database_reports, migrate
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

# The connection role the application runs as, spelled as
# `tests/integration/test_identity_grants.py` spells it. A copy rather than an
# import: a test module importing another test module depends on where pytest put
# `tests/` on `sys.path`, and an import error is not a red.
APPLICATION_ROLE = "pulse_app"

SECTION = "section"

# E3-05's column, and E3-02's beside it. The second is the near miss: it is on the
# same table, granted to the same role, at the same grain, one revision below —
# so a revoke that reaches it is a revoke written about the table or the role
# rather than about this ticket's column.
LINE_ITEM_COLUMN = "ags_line_item_url"
CONTAINER_COLUMN = "lms_ags_line_items_url"

# How many revisions the walk down may cross before it is called broken rather
# than long. The same bound `test_the_passback_schema_survives_a_downgrade.py`
# uses, for the same reason: E3 builds several tickets off one head, and anything
# past this is a `downgrade()` that is not undoing what it is supposed to undo.
MOST_STEPS_DOWN = 12

HOLDS_THE_COLUMN = text(
    "SELECT has_column_privilege(:role, 'public.section', :column, 'UPDATE') AS held"
)


def holds_update_on(database: Any, column: str) -> bool:
    """Whether `pulse_app` may update one column of `section` right now.

    `has_column_privilege` answers for the column ACL *and* for a table-wide grant
    that would cover it, which is exactly the reading this test wants: what an
    operator cares about after a rollback is whether the connection can write the
    column, not which catalog row says so. `pulse_app` holds no table-wide
    `UPDATE` on `section` — `test_identity_grants.py` pins that as an equality —
    so at head a true answer here is the column grant and nothing else.
    """
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            return bool(
                connection.execute(HOLDS_THE_COLUMN, {"role": APPLICATION_ROLE, "column": column})
                .mappings()
                .one()["held"]
            )
    finally:
        engine.dispose()


def walk_down_until_the_line_item_grant_is_gone(config: Any, database: Any) -> int:
    """Downgrade one revision at a time until the grant is not there, and say how far."""
    for step in range(1, MOST_STEPS_DOWN + 1):
        migrate(config, "downgrade", "-1", f"stepping one revision below head, step {step}")
        if not holds_update_on(database, LINE_ITEM_COLUMN):
            return step
    pytest.fail(
        f"After {MOST_STEPS_DOWN} downgrade steps `{APPLICATION_ROLE}` can still `UPDATE` "
        f"`public.{SECTION}.{LINE_ITEM_COLUMN}`, so no revision crossed revokes it. E3-05's work "
        "order (D6) requires the downgrade to issue a column-grain `REVOKE`, and the note it asks "
        "to be mirrored says why a table-grain one is not enough: a column ACL survives table-level "
        "revokes, so `REVOKE UPDATE ON public.section FROM pulse_app` leaves this entry exactly "
        "where it was. An operator who rolls back is then running with a privilege the rollback "
        "was meant to remove, and nothing anywhere says so."
    )


def test_the_line_item_grant_is_revoked_by_the_downgrade_and_the_container_grant_is_not(
    empty_database: Any, alembic_config_pointed_at: Any
) -> None:
    """D6's column-grain revoke, in both directions, on a database of its own.

    **The control comes first**: at head, `pulse_app` may update E3-05's column.
    Without that, every step below is about a privilege that was never granted and
    the walk would stop at the first downgrade having proved nothing
    (`docs/MISTAKES.md` entry 3 — a check satisfied by emptiness). This is also
    the assertion that goes red on today's tree, before any migration runs
    backwards.

    **The revoke is asserted, and so is its scope.** After the walk, the column
    privilege is gone and E3-02's `lms_ags_line_items_url` grant is still there —
    on the same table, to the same role, at the same grain. A downgrade written as
    a revoke on the table, or on the role, takes both, and the database it leaves
    is one where a launch can no longer store the gradebook address a platform
    advertised.

    **The column itself is required to survive the downgrade**, because the
    privilege check is meaningless without it: `has_column_privilege` on a column
    that is not there raises, and a downgrade that dropped E3-02's column would be
    undoing a revision this ticket does not own.

    **The re-upgrade closes the round trip.** A revoke an upgrade cannot undo is a
    one-way door: the operator who rolled back to diagnose something cannot roll
    forward again without editing grants by hand, which is the state
    `docs/MISTAKES.md` entry 12's neighbours are about — a database nobody has
    described.

    **The mutation this kills**: `downgrade()` left empty, which is the single most
    likely way this is met without being satisfied; and a table-grain `REVOKE`,
    which reads as correct and does nothing.
    """
    config = alembic_config_pointed_at(empty_database)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")

    assert holds_update_on(empty_database, LINE_ITEM_COLUMN), (
        f"At head, `{APPLICATION_ROLE}` cannot `UPDATE` `public.{SECTION}.{LINE_ITEM_COLUMN}`. "
        "E3-05's work order (D6) grants exactly that, in a new file under "
        "`backend/app/views_sql/` executed by a migration of its own, because "
        "`app.services.grading` writes the id of the line item this tool creates (SPEC §3.4, ADR "
        "0128) — and the alternative is `UPDATE` on `section` table-wide, which would hand this "
        "connection the section code and ADR 0021's derived calendar columns. Until the grant "
        "exists there is nothing for a downgrade to revoke and this test asserts nothing."
    )
    assert holds_update_on(empty_database, CONTAINER_COLUMN), (
        f"At head, `{APPLICATION_ROLE}` cannot `UPDATE` `public.{SECTION}.{CONTAINER_COLUMN}`, "
        "which is E3-02's grant and not this ticket's. The scope assertion below is that a "
        "downgrade leaves it alone, and with it already absent that assertion is about nothing."
    )

    walk_down_until_the_line_item_grant_is_gone(config, empty_database)

    assert LINE_ITEM_COLUMN in columns_the_database_reports(empty_database, SECTION), (
        f"The walk down took `{LINE_ITEM_COLUMN}` off `{SECTION}` altogether. That column is "
        "E3-02's and the revision that creates it sits below this one, so a downgrade of E3-05 "
        "that drops it is undoing another ticket's work — and the privilege reading above stops "
        "meaning what this test says it means."
    )
    assert holds_update_on(empty_database, CONTAINER_COLUMN), (
        f"The downgrade also took `{APPLICATION_ROLE}`'s `UPDATE` on "
        f"`public.{SECTION}.{CONTAINER_COLUMN}`, which belongs to E3-02 and to the revision below. "
        "A revoke written about the table — or about the role — takes every column grant on it, "
        "and the database that leaves is one where a staff launch can no longer store the AGS "
        "container address its platform advertised (SPEC §3.4). Revoke the column this revision "
        "granted, by name."
    )

    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying every revision the walk undid")

    assert holds_update_on(empty_database, LINE_ITEM_COLUMN), (
        f"After going down and coming back up, `{APPLICATION_ROLE}` still cannot `UPDATE` "
        f"`public.{SECTION}.{LINE_ITEM_COLUMN}`. The revoke is not reversible, so an operator who "
        "rolled back to diagnose something cannot roll forward again without editing grants by "
        "hand — and the application comes up with a passback path the database silently refuses."
    )
    assert holds_update_on(empty_database, CONTAINER_COLUMN), (
        f"After the round trip `{APPLICATION_ROLE}` cannot `UPDATE` "
        f"`public.{SECTION}.{CONTAINER_COLUMN}` either, so the trip lost a grant that was there "
        "when it started."
    )
