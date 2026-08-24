"""The calendar models are on `Base.metadata`, and cost nothing to import — ticket E0-06.

Not an acceptance criterion of its own. Both assertions here are rules E0-06's
Context pulls in by reference from **"What the built tickets settled"** in
`docs/tickets/e0/README.md` — "this ticket adds a model module, so its rules on
registering that module, importing `Base`, constraint naming, and the existing
database fixtures all apply". They are here for the same reason
`tests/unit/test_org_models_registered.py` exists for E0-05: these are the two
rules that fail without failing anything.

  - **A model module nobody imported is not on `Base.metadata`.**
    `migrations/env.py` autogenerates against that metadata, so an unregistered
    `term.py` means `alembic check` reports no drift, the migration nobody wrote
    is never missed, and the four tables exist in no deployed database. Nothing
    goes red at the time — `docs/MISTAKES.md` entry 2, and E0-20's whole subject.
  - **A model module that reaches `Base` through `app.db` builds an engine out of
    `Settings()` at import.** That needs `AI_PROVIDER_BASE_URL` and four other
    variables which have nothing to do with a schema, so it works on a machine
    with a full `.env` and breaks in CI, where the `migration-drift` job supplies
    the database variables alone.

The integration suite cannot see either one: by the time it reflects the migrated
database, a table is either there or it is not.
"""

from pathlib import Path
from typing import Any

import pytest

# The four tables E0-06's scope names. SPEC §8 lists all four among the core
# tables. Table names, not ORM class names — the ticket names the tables, and
# nothing anywhere names the classes.
CALENDAR_TABLES = ("term", "week", "survey_window", "start_letter_map")

# Where the ticket puts the module, and where SPEC §13 puts the package.
TERM_MODULE = "app.models.term"
MODELS_PACKAGE = "app.models"
BASE_MODULE = "app.models.base"


def test_every_calendar_table_is_registered_on_base_metadata(
    configured_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """Importing `app.models` is enough to put all four tables on the metadata.

    Asserted through the package rather than through `app.models.term` directly,
    and that is the whole point: `env.py` imports the package, so a module that
    exists and is not imported there is invisible to autogenerate. Importing
    `term` by name here would pass against exactly the defect this exists to
    catch.
    """
    package = import_app_module(MODELS_PACKAGE)
    assert package is not None, (
        f"There is no `{MODELS_PACKAGE}` package. E0-04 ships it with `base.py` and E0-05 added "
        "`org.py`; E0-06 adds `term.py` to it and imports the module in `__init__.py` in the "
        "same change."
    )

    base_module = import_app_module(BASE_MODULE)
    assert base_module is not None, (
        f"There is no `{BASE_MODULE}`. E0-04 ships the declarative base there, and every model "
        "module imports `Base` from it rather than from `app.db`."
    )

    metadata = getattr(getattr(base_module, "Base", None), "metadata", None)
    assert metadata is not None, (
        f"`{BASE_MODULE}` exposes no `Base` with `metadata`, so there is nothing for "
        "`migrations/env.py` to autogenerate against."
    )

    registered = sorted(metadata.tables)
    missing = [name for name in CALENDAR_TABLES if name not in registered]
    assert not missing, (
        f"Importing `{MODELS_PACKAGE}` registers {registered}, so {missing} is on no metadata "
        f"`env.py` can see. The table may well exist in `{TERM_MODULE}`: a module nobody imports "
        "is not on `Base.metadata`, `alembic check` then reports no drift, and the migration "
        "that was never written is never missed. Import the module in `app/models/__init__.py` "
        "in the same change that adds it."
    )


def test_importing_the_calendar_models_needs_no_application_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    documented_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """`app.models.term` imports with the environment empty.

    The environment is emptied of everything `.env.example` documents and the
    working directory moved somewhere with no `.env`, because the failure this
    describes is invisible on a developer's machine: with a full `.env`, a model
    module that reaches `Base` through `app.db` imports perfectly and builds an
    engine on the way. CI is where it breaks, and by then the message is about a
    missing AI provider URL in a schema ticket.

    Asserting the documented set is non-empty first is not ceremony: an
    `.env.example` that failed to parse would empty the environment of nothing
    and leave this passing against the defect (`docs/MISTAKES.md` entry 3).
    """
    assert documented_env, (
        "`.env.example` documented no variables, so nothing was cleared and this test would "
        "pass whatever `app.models.term` imports. `tests/unit/test_env_example_sync.py` says "
        "what that file is supposed to hold."
    )

    monkeypatch.chdir(tmp_path)
    for name in documented_env:
        monkeypatch.delenv(name, raising=False)

    try:
        module = import_app_module(TERM_MODULE)
    except Exception as failure:
        pytest.fail(
            f"Importing `{TERM_MODULE}` with no configuration in the environment raised "
            f"{failure!r}. A model module needs `Base` and nothing else: import it from "
            "`app.models.base`, never from `app.db`, which builds an engine out of `Settings()` "
            "at import time. CI's `migration-drift` job and the testcontainers fixture both "
            "supply the database variables alone, so a module that needs more than that works "
            "here and fails there."
        )

    assert module is not None, (
        f"There is no `{TERM_MODULE}` module. E0-06 puts term, week, survey_window and "
        "start_letter_map there (SPEC §13 gives `models/` that job, and the ticket names the "
        "file)."
    )
