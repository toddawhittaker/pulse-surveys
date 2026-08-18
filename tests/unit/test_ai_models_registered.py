"""The `classification` model is on `Base.metadata`, and costs nothing to import — ticket E0-13.

Not one of E0-13's seven acceptance criteria. Both assertions here are the two
rules the ticket pulls in by reference from **"What the built tickets settled"**
in `docs/tickets/e0/README.md` — it names them itself: "The `classification`
table means a model module, so it needs registering in `app/models/__init__.py`
and must import `Base` from `app.models.base`." They are here because they are
the two that fail without failing anything:

  - **A model module nobody imported is not on `Base.metadata`.**
    `migrations/env.py` autogenerates against that metadata, so an unregistered
    `ai.py` means `alembic check` reports no drift, the migration nobody wrote is
    never missed, and `classification` exists in no deployed database. Every
    behavioural test in `tests/integration/test_ai_gateway_validity_roundtrip.py`
    would then fail on a missing relation, pointing at the gateway rather than at
    the import that is actually absent. That is `docs/MISTAKES.md` entry 2, and
    E0-20's whole subject.
  - **A model module that reaches `Base` through `app.db` builds an engine out of
    `Settings()` at import.** That needs `AI_PROVIDER_BASE_URL` and four other
    variables which have nothing to do with a schema, so it works on a machine
    with a full `.env` and breaks in CI, where the `migration-drift` job supplies
    the database variables alone.

The integration suite cannot see either one: it reflects the migrated database,
and by then a table is either there or it is not.
"""

from pathlib import Path
from typing import Any

import pytest

# SPEC §8 names the table and E0-13's scope creates it: "A minimal
# `classification` table storing the verdict with prompt version and model ID,
# append-only (re-runs create new rows, per §8)." A table name, not an ORM class
# name — the ticket names the table and nothing names the class.
CLASSIFICATION_TABLE = "classification"

# SPEC §13 puts it here: "`models/ai.py` — classification, summary". The summary
# table belongs to E4; only the classification half of that line is E0-13's.
AI_MODEL_MODULE = "app.models.ai"
MODELS_PACKAGE = "app.models"
BASE_MODULE = "app.models.base"


def test_the_classification_table_is_registered_on_base_metadata(
    configured_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """Importing `app.models` is enough to put `classification` on the metadata.

    Asserted through the package rather than through `app.models.ai` directly,
    and that is the whole point: `env.py` imports the package, so a module that
    exists and is not imported there is invisible to autogenerate. Importing the
    module by name here would pass against exactly the defect this exists to
    catch.
    """
    package = import_app_module(MODELS_PACKAGE)
    assert package is not None, (
        f"There is no `{MODELS_PACKAGE}` package. E0-04 ships it with `base.py`; E0-13 adds the "
        "classification model to it and imports the module in `__init__.py` in the same change."
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
    assert CLASSIFICATION_TABLE in registered, (
        f"Importing `{MODELS_PACKAGE}` registers {registered}, so `{CLASSIFICATION_TABLE}` is on "
        f"no metadata `env.py` can see. The table may well exist in `{AI_MODEL_MODULE}`: a module "
        "nobody imports is not on `Base.metadata`, `alembic check` then reports no drift, and the "
        "migration that was never written is never missed. Import the module in "
        "`app/models/__init__.py` in the same change that adds it — the epic README names this "
        "ticket as one of the two it reaches."
    )


def test_importing_the_ai_models_needs_no_application_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    documented_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """`app.models.ai` imports with the environment empty.

    The environment is emptied of everything `.env.example` documents and the
    working directory moved somewhere with no `.env`, because the failure this
    describes is invisible on a developer's machine: with a full `.env`, a model
    module that reaches `Base` through `app.db` imports perfectly and builds an
    engine on the way. CI is where it breaks.

    It is worth stating for this ticket in particular. E0-13 is the first one to
    put a model module next to code that legitimately *does* need
    `AI_PROVIDER_BASE_URL`, so the pull toward importing the gateway's
    configuration from a schema module is stronger here than anywhere it has been
    before — and the failure lands in the `migration-drift` job, in a message
    about an AI provider URL.

    Asserting the documented set is non-empty first is not ceremony: an
    `.env.example` that failed to parse would empty the environment of nothing
    and leave this passing against the defect (`docs/MISTAKES.md` entry 3).
    """
    assert documented_env, (
        "`.env.example` documented no variables, so nothing was cleared and this test would pass "
        "whatever `app.models.ai` imports. `tests/unit/test_env_example_sync.py` says what that "
        "file is supposed to hold."
    )

    monkeypatch.chdir(tmp_path)
    for name in documented_env:
        monkeypatch.delenv(name, raising=False)

    try:
        module = import_app_module(AI_MODEL_MODULE)
    except Exception as failure:
        pytest.fail(
            f"Importing `{AI_MODEL_MODULE}` with no configuration in the environment raised "
            f"{failure!r}. A model module needs `Base` and nothing else: import it from "
            "`app.models.base`, never from `app.db`, which builds an engine out of `Settings()` "
            "at import time. It must not reach `app.ai.gateway` either — the gateway reads the "
            "provider configuration, and a schema module that pulls it in cannot be "
            "autogenerated against in CI."
        )

    assert module is not None, (
        f"There is no `{AI_MODEL_MODULE}` module. SPEC §13 gives `models/ai.py` the "
        "classification and summary tables, and E0-13's scope creates the first of them: 'A "
        "minimal `classification` table storing the verdict with prompt version and model ID.'"
    )
