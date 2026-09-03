"""Walking one database down through a revision and back up, and reading what survived.

A round-trip test is the same five moves every time: resolve the revision under
test and the one below it, run each step and stop loudly if a step did not
complete, read the catalog while standing at the older revision, and read the
stored rows at either end. `tests/integration/test_the_section_binding_survives_a_downgrade.py`
wrote them for E2-03 and `test_the_upgrade_refuses_a_stored_edge_that_does_not_climb.py`
holds a third copy of two of them; E2-16 needs the same five for the survey
schema, so they are here rather than copied a third time (`docs/MISTAKES.md`
entry 13).

**The two existing copies are deliberately left where they are**, and that is a
gap rather than a decision: their failure messages name the tickets they were
written for, and re-pointing merged tickets' modules at these generic ones is a
change to tests this ticket does not touch. Said out loud so the next module
that needs a journey imports from here instead of copying a fourth time.

**Everything here seeds and reads at head.** `seed_row` writes through
`Base.metadata` and reads back every column it declares, so a database standing
before any revision that added one is a database it cannot write to
(`docs/disputes/E1-10-01.md`). A test whose subject is an older revision seeds
while the database is at head, walks it down, and walks it back up — `head`
appears in such a module as the name of the schema today's models describe and
is the subject of nothing.

**Nothing here asserts anything.** Each function either answers a reading or
stops with a message saying the journey did not happen, so a broken step and a
failed criterion are never reported as the same thing.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

# The schema today's models describe, reached by name so that a module walking a
# database back up does not have to know what has landed on top of its subject.
MODEL_SCHEMA = "head"


def require_revision(config: Any, revision: str, what: str) -> str:
    """`revision`, after asking the script directory whether it still exists.

    Resolved rather than handed straight to `command.upgrade`, so a constant left
    behind by a squash, a rebase or a renamed file fails with a message naming
    what the revision is *for* instead of with Alembic's own `Can't locate
    revision`, which reads like a broken environment.
    """
    from alembic.script import ScriptDirectory

    try:
        ScriptDirectory.from_config(config).get_revision(revision)
    except Exception as failure:
        pytest.fail(
            f"`{revision}` is not a revision in this tree: {failure!r}. That is {what}, and the "
            "module asking for it pins its journey to a named revision rather than to `head` and a "
            "relative step. If it has been renumbered or squashed, the constant at the top of that "
            "file is the one place to change."
        )
    return revision


def the_revision_below(config: Any, revision: str) -> str:
    """What `revision` chains from, read off the migration itself.

    The migration's own `down_revision` rather than a second constant in the test:
    it is the statement of what this revision undoes back to, so a rebase that
    re-points it moves the test with it, and a copy would be a record that goes on
    asserting something the change made false (`docs/MISTAKES.md` entry 1).
    """
    from alembic.script import ScriptDirectory

    parent = ScriptDirectory.from_config(config).get_revision(revision).down_revision
    if not isinstance(parent, str) or not parent:
        pytest.fail(
            f"Revision {revision} reports `down_revision = {parent!r}`, so a test cannot say what "
            "'the revision below it' is. A tuple means a merge point and `None` means it is the "
            "base; either way the round trip has to be re-expressed against whatever the history "
            "now looks like, deliberately, rather than guessed at."
        )
    return parent


def migrate(config: Any, direction: str, revision: str, what: str) -> None:
    """Run one Alembic command to `revision`, failing the test if it does not complete.

    A migration that stops part-way is worse than one that refuses to start: the
    statements before the failure have run, the ones after have not, and the
    version is still stamped — so everything read afterwards is a database nobody
    has described.
    """
    from alembic import command

    run = command.upgrade if direction == "upgrade" else command.downgrade
    try:
        run(config, revision)
    except Exception as failure:
        pytest.fail(
            f"`alembic {direction} {revision}` did not complete ({what}): {failure!r}. Every "
            "assertion resting on this journey is about a database that made the whole trip, so "
            "nothing after this point means anything."
        )


@contextmanager
def session_on(database: Any) -> Iterator[Any]:
    """A committed session on `database`, opened and closed around one step.

    Opened and closed around each migration step rather than held across one: an
    Alembic upgrade that alters a table takes locks a session idle inside a
    transaction can block, and a migration waiting on the test's own connection is
    a hang rather than a failure.
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


def columns_the_database_reports(database: Any, table: str) -> set[str]:
    """What `table` actually has right now, read from the catalog rather than the models.

    `Base.metadata` describes head and says nothing about the database in front of
    it, and the point of this read is to stand at an older revision and ask what is
    there. A table that does not exist reports no columns, which is the answer a
    caller asking about a dropped table wants.
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


def rows_by_key(database: Any, tables: dict[str, Any], name: str) -> dict[Any, dict[str, Any]]:
    """Every row of one declared table, whole, keyed by its primary key.

    Keyed rather than listed, because the question a round trip asks is which
    values are on which row: a restore that kept every value and put them back on
    the wrong rows leaves any set comparison satisfied and is strictly worse than
    losing them.
    """
    from sqlalchemy import select

    from fixtures.supervision import require_table, single_primary_key

    table = require_table(tables, name)
    key = single_primary_key(table)
    with session_on(database) as session:
        rows = session.execute(select(table)).mappings().all()
    return {row[key]: dict(row) for row in rows}
