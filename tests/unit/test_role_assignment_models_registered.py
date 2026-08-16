"""The assignment models are on `Base.metadata` — ticket E0-09.

Not an acceptance criterion of its own. It is the rule E0-09's Context pulls in
by reference from **"What the built tickets settled"** in
`docs/tickets/e0/README.md` — "this ticket adds a model module and the
registration rule, the `Base`-import rule, constraint naming and the existing
fixtures all apply" — and it is the one that fails without failing anything:

  **A model module nobody imported is not on `Base.metadata`.**
  `migrations/env.py` autogenerates against that metadata, so an unregistered
  module means `alembic check` reports no drift, the migration nobody wrote is
  never missed, and the tables exist in no deployed database. Nothing goes red
  at the time — `docs/MISTAKES.md` entry 2, and E0-20's whole subject.

**The `Base`-import rule is not asserted again here.**
`tests/unit/test_identity_models_registered.py` already imports the whole
`app.models` package with the environment emptied, and E0-09's module is inside
that package whichever file it lands in. A second copy would give two failures
for one defect, and the copy that drifted would be this one.

**No module name is asserted either.** E0-09's scope says
"`backend/app/models/identity.py` (or a sibling module)", so the table names are
what this test knows: they are what SPEC §8 lists, what the migration creates,
and what E0-10, E0-11 and E0-17 all join to.
"""

from typing import Any

MODELS_PACKAGE = "app.models"
BASE_MODULE = "app.models.base"

# The two tables E0-09's scope names. SPEC §8 lists both among the core tables.
E0_09_TABLES = ("role_assignment", "lead_faculty_mapping")


def test_the_role_assignment_and_lead_faculty_tables_are_registered_on_base_metadata(
    configured_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """Importing `app.models` is enough to put both tables on the metadata.

    Asserted through the package rather than through the module the ticket names,
    and that is the whole point: `env.py` imports the package, so a module that
    exists and is not imported there is invisible to autogenerate. Importing the
    module by name here would pass against exactly the defect this exists to
    catch — and it would say nothing about which of the two files the implementer
    chose.
    """
    package = import_app_module(MODELS_PACKAGE)
    assert package is not None, (
        f"There is no `{MODELS_PACKAGE}` package. E0-04 ships it with `base.py`, and E0-05, E0-06 "
        "and E0-08 each added a module and imported it in `__init__.py` in the same change."
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
    missing = [name for name in E0_09_TABLES if name not in registered]
    assert not missing, (
        f"Importing `{MODELS_PACKAGE}` registers {registered}, so {missing} is on no metadata "
        "`env.py` can see. The table may well exist in the module E0-09 added: a module nobody "
        "imports is not on `Base.metadata`, `alembic check` then reports no drift, and the "
        "migration that was never written is never missed. Import the module in "
        "`app/models/__init__.py` in the same change that adds it — and note that this is the "
        "table every authorization decision in the product is computed from, so a deployment "
        "without it is a deployment where nobody has any purview at all."
    )
