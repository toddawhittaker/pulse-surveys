"""The identity models are on `Base.metadata`, and cost nothing to import — ticket E0-08.

Not an acceptance criterion of its own. Both assertions here are rules E0-08's
Context pulls in by reference from **"What the built tickets settled"** in
`docs/tickets/e0/README.md` — "this ticket adds two model modules, so the
registration, `Base` import, constraint-naming and fixture rules all apply". They
are here for the same reason `tests/unit/test_org_models_registered.py` exists
for E0-05 and `test_term_models_registered.py` for E0-06: these are the two rules
that fail without failing anything.

  - **A model module nobody imported is not on `Base.metadata`.**
    `migrations/env.py` autogenerates against that metadata, so an unregistered
    `identity.py` means `alembic check` reports no drift, the migration nobody
    wrote is never missed, and the tables exist in no deployed database. Nothing
    goes red at the time — `docs/MISTAKES.md` entry 2, and E0-20's whole subject.
  - **A model module that reaches `Base` through `app.db` builds an engine out of
    `Settings()` at import.** That needs `AI_PROVIDER_BASE_URL` and four other
    variables which have nothing to do with a schema, so it works on a machine
    with a full `.env` and breaks in CI, where the `migration-drift` job supplies
    the database variables alone.

**Only one module name is asserted here, and it is the one the ticket spells.**
E0-08's scope puts `user`, `user_identity`, `person` and `enrollment` in
`backend/app/models/identity.py`, and leaves the LTI registration tables in
"`backend/app/models/org.py` or a new `lti.py`". So the registration test names
tables and not modules, which is true whichever of the two the implementer picks,
and the import test reaches the LTI module the same way `env.py` does — through
the package.
"""

from pathlib import Path
from typing import Any

import pytest

# The six tables E0-08's scope names. SPEC §8 lists all six among the core
# tables. Table names, not ORM class names — the ticket names the tables, and
# nothing anywhere names the classes.
IDENTITY_TABLES = ("user", "user_identity", "person", "enrollment")
LTI_TABLES = ("lti_platform", "lti_deployment")
E0_08_TABLES = IDENTITY_TABLES + LTI_TABLES

# Where the ticket puts the identity module, and where SPEC §13 puts the package.
IDENTITY_MODULE = "app.models.identity"
MODELS_PACKAGE = "app.models"
BASE_MODULE = "app.models.base"


def test_every_identity_and_lti_table_is_registered_on_base_metadata(
    configured_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """Importing `app.models` is enough to put all six tables on the metadata.

    Asserted through the package rather than through `app.models.identity`
    directly, and that is the whole point: `env.py` imports the package, so a
    module that exists and is not imported there is invisible to autogenerate.
    Importing `identity` by name here would pass against exactly the defect this
    exists to catch — and it would say nothing at all about the LTI tables, which
    the ticket allows to live in either of two modules.
    """
    package = import_app_module(MODELS_PACKAGE)
    assert package is not None, (
        f"There is no `{MODELS_PACKAGE}` package. E0-04 ships it with `base.py`, E0-05 added "
        "`org.py` and E0-06 `term.py`; E0-08 adds `identity.py` (and either extends `org.py` or "
        "adds `lti.py`) and imports each module in `__init__.py` in the same change."
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
    missing = [name for name in E0_08_TABLES if name not in registered]
    assert not missing, (
        f"Importing `{MODELS_PACKAGE}` registers {registered}, so {missing} is on no metadata "
        f"`env.py` can see. The table may well exist in `{IDENTITY_MODULE}` or in the module "
        "holding the LTI registration tables: a module nobody imports is not on `Base.metadata`, "
        "`alembic check` then reports no drift, and the migration that was never written is "
        "never missed. Import the module in `app/models/__init__.py` in the same change that "
        "adds it."
    )


def test_importing_the_model_package_needs_no_application_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    documented_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """`app.models` — and so `app.models.identity` — imports with the environment empty.

    The environment is emptied of everything `.env.example` documents and the
    working directory moved somewhere with no `.env`, because the failure this
    describes is invisible on a developer's machine: with a full `.env`, a model
    module that reaches `Base` through `app.db` imports perfectly and builds an
    engine on the way. CI is where it breaks, and by then the message is about a
    missing AI provider URL in a schema ticket.

    The **package** is imported rather than one module, because E0-08 adds two
    modules and names only one of them. Importing the package is what `env.py`
    does, and it reaches whichever module the implementer put `lti_platform` in.
    `app.models.identity` is then asked for separately, because the ticket does
    spell that one and a missing file should say so in words.

    Asserting the documented set is non-empty first is not ceremony: an
    `.env.example` that failed to parse would empty the environment of nothing
    and leave this passing against the defect (`docs/MISTAKES.md` entry 3).
    """
    assert documented_env, (
        "`.env.example` documented no variables, so nothing was cleared and this test would "
        "pass whatever the model package imports. `tests/unit/test_env_example_sync.py` says "
        "what that file is supposed to hold."
    )

    monkeypatch.chdir(tmp_path)
    for name in documented_env:
        monkeypatch.delenv(name, raising=False)

    try:
        package = import_app_module(MODELS_PACKAGE)
        module = import_app_module(IDENTITY_MODULE)
    except Exception as failure:
        pytest.fail(
            "Importing the model package with no configuration in the environment raised "
            f"{failure!r}. A model module needs `Base` and nothing else: import it from "
            "`app.models.base`, never from `app.db`, which builds an engine out of `Settings()` "
            "at import time. CI's `migration-drift` job and the testcontainers fixture both "
            "supply the database variables alone, so a module that needs more than that works "
            "here and fails there."
        )

    assert (
        package is not None
    ), f"There is no `{MODELS_PACKAGE}` package to import. E0-04 ships it with `base.py`."
    assert module is not None, (
        f"There is no `{IDENTITY_MODULE}` module. E0-08 puts user, user_identity, person and "
        "enrollment there (SPEC §13 gives `models/` that job, and the ticket names the file)."
    )
