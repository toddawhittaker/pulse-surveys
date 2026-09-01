"""E2-04 — the development clock override row, and the settings a clock is read under.

Three suites need the same two things: a `clock_override` row they chose the
values of, and a `Settings` built under an environment they named. A copy of
either in each module is `docs/MISTAKES.md` entry 13 — one question answered in
three places — so both live here.

**The values are never this file's.** `set` takes `pretend_now` and `anchored_at`
as required keyword arguments with no defaults, and `settings_in` takes the
environment name. Every one of those is the thing some test is about: what the
service answers under an override, and whether the override applies at all
(`docs/MISTAKES.md` entry 30 — a fixture that supplied the value under test makes
neither the green nor the red mean anything).

**Two writers, because the readers are two kinds.** `clock_overrides` writes
inside `db_session`'s transaction, for a test that calls the service with that
same session and wants the row gone when it ends. `committed_clock_overrides`
commits, for a test whose subject — the tool over HTTP, a Celery worker, the
roster sync — opens its own connection and sees nothing that has not been. The
committed one deletes every row in the table at teardown rather than trusting a
diff, because a `clock_override` row left behind moves the clock for every test
that runs after it in the same worker, and that failure would surface as somebody
else's date assertion three modules away.

**Nothing here asserts what the service answers.** These fixtures put a row in a
table and read it back; the meaning of that row is
`tests/integration/test_the_clock_service_reads_a_development_override.py`'s
subject, and a fixture that encoded it would be a second implementation for the
tests to agree with.
"""

from collections.abc import Callable, Iterator
from datetime import datetime
from types import ModuleType
from typing import Any

import pytest

# The table, the model and the two columns, spelled exactly as E2-04's work order
# settles them. A deliberate rename is these four lines.
CLOCK_OVERRIDE_TABLE = "clock_override"
CLOCK_MODEL_MODULE = "app.models.clock"
PRETEND_NOW_COLUMN = "pretend_now"
ANCHORED_AT_COLUMN = "anchored_at"

# The service and its two functions, likewise settled by the work order.
CLOCK_SERVICE_MODULE = "app.services.clock"
NOW_FUNCTION = "now"
TODAY_FUNCTION = "today"

# The two variables every clock reading depends on. `ENVIRONMENT` decides whether
# an override applies at all (the service applies it only where
# `is_development(settings)`), and `INSTITUTION_TIMEZONE` is the zone `today`
# resolves in (SPEC §3.1, default `America/New_York`).
ENVIRONMENT_VARIABLE = "ENVIRONMENT"
INSTITUTION_TIMEZONE_VARIABLE = "INSTITUTION_TIMEZONE"

# `app.config`'s own name for the one environment where the override applies.
# Quoted rather than imported so that a suite asserting the *refusal* direction
# does not take its expectation from the module it is checking
# (`docs/MISTAKES.md` entry 19); `tests/unit/
# test_development_environment_has_one_definition.py` owns the one-definition rule.
DEVELOPMENT = "development"


class ClockOverrides:
    """The `clock_override` table, written and read with the values a test chose.

    `commit` decides which of the two kinds of reader this serves. Committed, a
    read rolls the session's transaction back first so that what another
    connection wrote since is visible — the same reason
    `tests/fixtures/provisioning.py`'s `ProvisionedRows` refreshes. Uncommitted, it
    must not, because a rollback inside `db_session` is a rollback to the savepoint
    the fixture opened and would take the seeded row with it.
    """

    def __init__(self, session: Any, table: Any, *, commit: bool) -> None:
        self.session = session
        self.table = table
        self._commit = commit

    def set(self, *, pretend_now: datetime, anchored_at: datetime) -> None:
        """Replace the single override row with this pair of instants.

        Delete-then-insert rather than an upsert, because the table holds at most
        one row by a unique index over `(true)` and a second insert would be
        refused by it. Both arguments are required: which instant is pretended and
        which real instant it was anchored at are the whole of what the offset
        means, and a default for either would answer a question some test is asking.
        """
        from sqlalchemy import delete, insert

        self.session.execute(delete(self.table))
        self.session.execute(
            insert(self.table).values(
                **{PRETEND_NOW_COLUMN: pretend_now, ANCHORED_AT_COLUMN: anchored_at}
            )
        )
        if self._commit:
            self.session.commit()

    def clear(self) -> None:
        """Remove the override, as `POST /dev/clock/clear` does."""
        from sqlalchemy import delete

        self.session.execute(delete(self.table))
        if self._commit:
            self.session.commit()

    def rows(self) -> list[dict[str, Any]]:
        """Every row in `clock_override` right now, as plain mappings."""
        from sqlalchemy import select

        if self._commit:
            # End this session's transaction so a row another connection committed
            # since — the tool's own, a worker's — is visible to the select below.
            self.session.rollback()
        return [dict(row) for row in self.session.execute(select(self.table)).mappings()]


@pytest.fixture
def clock_override_table(metadata_tables: dict[str, Any]) -> Any:
    """The `clock_override` table off `Base.metadata`, or a failure naming what is missing.

    Reached through the metadata rather than by importing the model class, for the
    reason `tests/fixtures/supervision.py` gives about `metadata_tables`: a module
    nobody imported is on no metadata, so this is also the check that E2-04's model
    is registered where `migrations/env.py` can see it.
    """
    table = metadata_tables.get(CLOCK_OVERRIDE_TABLE)
    if table is None:
        pytest.fail(
            f"There is no `{CLOCK_OVERRIDE_TABLE}` table on `Base.metadata` (there are "
            f"{sorted(metadata_tables)}). E2-04 ships `{CLOCK_MODEL_MODULE}` with a "
            f"`ClockOverride` model carrying `{PRETEND_NOW_COLUMN}` and `{ANCHORED_AT_COLUMN}`, "
            "and a migration that creates it. A model in a module `app.models` does not import "
            "is on no metadata and in no migration."
        )
    for column in (PRETEND_NOW_COLUMN, ANCHORED_AT_COLUMN):
        if column not in table.c:
            pytest.fail(
                f"`{CLOCK_OVERRIDE_TABLE}` declares no `{column}` (it declares "
                f"{[c.name for c in table.columns]}). The override is a pretended instant paired "
                "with the real instant it was set at, so that time keeps flowing from the point "
                "it was set rather than freezing there."
            )
    return table


@pytest.fixture
def clock_overrides(db_session: Any, clock_override_table: Any) -> ClockOverrides:
    """An override row inside `db_session`'s transaction, rolled back with it.

    For a test that hands the same session to `app.services.clock`, which is every
    test whose subject is the service itself rather than something that connects
    for itself.
    """
    return ClockOverrides(db_session, clock_override_table, commit=False)


@pytest.fixture
def committed_clock_overrides(
    committed_rows: Any, clock_override_table: Any, migrated_engine: Any
) -> Iterator[ClockOverrides]:
    """An override row every connection can see, and no row at all afterwards.

    The teardown empties the table outright rather than relying on
    `committed_rows`' diff. Two reasons, and the first is enough on its own: a
    `clock_override` row that survives its test moves the clock for every test that
    runs after it in the same worker, and the failures that follow are date
    assertions in modules that never heard of this one. The second is that the diff
    walks tables with exactly one primary key column, and E2-04's work order settles
    the table's columns and its one-row index without settling its key.
    """
    from sqlalchemy import delete

    overrides = ClockOverrides(committed_rows.session, clock_override_table, commit=True)
    try:
        yield overrides
    finally:
        with migrated_engine.begin() as connection:
            connection.execute(delete(clock_override_table))


@pytest.fixture
def clock_service() -> ModuleType:
    """`app.services.clock`, imported here so a missing module fails loudly and once."""
    try:
        import app.services.clock as module
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{CLOCK_SERVICE_MODULE}` does not import ({missing}). E2-04 ships it under "
            f"`backend/app/services/` (SPEC §13) with `{NOW_FUNCTION}(session, *, settings)` and "
            f"`{TODAY_FUNCTION}(session, *, settings)`, and every scheduling read goes through it."
        )
    for name in (NOW_FUNCTION, TODAY_FUNCTION):
        if not callable(getattr(module, name, None)):
            pytest.fail(
                f"`{CLOCK_SERVICE_MODULE}` exposes no callable `{name}`; it exposes "
                f"{sorted(n for n in vars(module) if not n.startswith('_'))}. The service answers "
                "the two questions this codebase asks about time: the current instant in UTC, and "
                "today's date in the institution's timezone."
            )
    return module


@pytest.fixture
def settings_in(
    monkeypatch: pytest.MonkeyPatch,
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
) -> Callable[..., Any]:
    """Build `Settings` under an environment the caller names.

    **The caller names it**, which is `docs/MISTAKES.md` entry 40's rule: a test
    whose subject reads the process environment states the value it runs under, in
    its own fixture chain. `configured_env` lays down every documented variable
    over an empty working directory, so a developer's own `.env` cannot supply one
    this fixture believes it set; `deployed_identity_provider` configures a provider
    that is not the mock, because E0-39 refuses `.env.example`'s `mock-idp`
    addresses anywhere the environment is not `development` and a settings object
    that would not build is not what any of these tests is about.
    """

    def build(environment: str, **overrides: str) -> Any:
        from app.config import Settings

        monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
        for name, value in overrides.items():
            monkeypatch.setenv(name, value)
        return Settings()

    return build
