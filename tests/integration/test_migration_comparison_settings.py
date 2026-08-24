"""Autogenerate compares types *and* server defaults — tickets E0-05 and E0-20.

E0-05's scope, first item: "`backend/migrations/env.py` sets `compare_type=True`
but not `compare_server_default`, which defaults to `False`, so `alembic check`
cannot see a server default that changed without a migration. This ticket is
where the first server defaults land, so it is where that blind spot starts to
cost something." E0-20 item 3 is the same finding in full.

**Why this is a test and not a line in a migration review.** Without it the flag
can be dropped again later with every gate green, which is `docs/MISTAKES.md`
entry 2 — behaviour shipped with nothing asserting it — and is the exact class
E0-20 exists to close. A setting that only a human reading `env.py` can vouch
for is a convention.

**Why it runs Alembic instead of reading the file.** `env.py` is a script that
configures a context, and what matters is the configuration the context ends up
holding, not the spelling of a keyword argument in a file. Searching the text
would also be the shape `docs/MISTAKES.md` entry 3 records — a pattern that goes
blind and reports green. So the real `EnvironmentContext.configure` is wrapped,
the real `alembic upgrade` is run through both paths, and what env.py actually
passed is read off the call.

**Both paths, though only one of them uses the answer.** Offline mode emits SQL
without a connection, so nothing there compares anything and
`compare_server_default` is inert on that path. E0-20 names both anyway, and the
reason is that the two paths are two copies of the same `context.configure` call:
the failure worth preventing is the pair drifting apart, so that a later reader
of the offline branch learns the wrong rule.
"""

from collections.abc import Callable
from typing import Any

import pytest
from alembic import command
from alembic.runtime.environment import EnvironmentContext

pytestmark = pytest.mark.integration

# The two autogenerate comparisons `env.py` has to turn on. `compare_type` is
# already there and is asserted alongside the new one deliberately: an edit that
# reorganises `context.configure` and drops both is the likelier accident, and a
# test that only knew about one of them would report half of it.
REQUIRED_COMPARISONS = ("compare_type", "compare_server_default")


@pytest.mark.parametrize("offline", [False, True], ids=["online", "offline"])
def test_the_migration_environment_compares_types_and_server_defaults(
    empty_database: Any,
    alembic_config_pointed_at: Callable[[Any], Any],
    monkeypatch: pytest.MonkeyPatch,
    offline: bool,
) -> None:
    """Both paths through `env.py` configure both comparisons.

    Every route into the context funnels through `EnvironmentContext.configure`:
    `alembic.context` is a module of proxy functions that call the method on the
    live instance, so wrapping the method catches `from alembic import context`
    and `from alembic.context import configure` alike, and does not care which
    one `env.py` was written with.

    The wrapper calls through rather than standing in, so the migration really
    runs — an `env.py` that could not connect, or a chain that does not apply,
    fails here rather than being reported as a missing setting.
    """
    calls: list[dict[str, Any]] = []
    original = EnvironmentContext.configure

    def recording_configure(self: Any, *args: Any, **kwargs: Any) -> Any:
        calls.append(dict(kwargs))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(EnvironmentContext, "configure", recording_configure)

    config = alembic_config_pointed_at(empty_database)
    command.upgrade(config, "head", sql=offline)

    assert calls, (
        "`env.py` never called `context.configure` on the "
        f"{'offline' if offline else 'online'} path, so the migration environment configured "
        "nothing at all and the comparisons below have nowhere to be set. That is a broken "
        "migration environment rather than a missing flag."
    )

    for configured in calls:
        missing = [name for name in REQUIRED_COMPARISONS if configured.get(name) is not True]
        assert not missing, (
            f"On the {'offline' if offline else 'online'} path `env.py` configures "
            f"{sorted(configured)} and leaves {missing} unset or false. `alembic check` "
            "compares only what it is told to: with `compare_server_default` at its default "
            "of False, editing a model's `server_default` without writing a migration reports "
            "no drift, and E0-04's whole criterion — a model change with no migration behind "
            "it is a build failure — stops holding for that class of change. E0-05 is where "
            "the first server defaults land. If leaving it off is deliberate — Postgres "
            "normalising `text()` defaults into false positives is the real reason to — then "
            "E0-20 item 3 says that goes in `env.py`'s docstring, and this test changes with "
            "it in the same pull request."
        )
