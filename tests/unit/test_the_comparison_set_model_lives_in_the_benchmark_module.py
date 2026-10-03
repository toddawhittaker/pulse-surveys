"""The comparison-set model is declared in `app/models/benchmark.py` — SPEC §13.

E5-01's scope names the module and SPEC §13's repository layout is what it names
it from: `benchmark.py` is listed there as the home of the comparison-set model,
and `CLAUDE.md` sends every "where does a module go" question to that section.
The ticket's context sentence repeats it — "SPEC §13 names `benchmark.py` for
`comparison_set`".

**Why this is worth a test rather than a review note.** A model declared in the
nearest module that already imports what it needs — `org.py`, beside `course` —
works perfectly, passes every schema test in this epic, and is invisible to
`alembic check`, which compares tables and knows nothing about which Python file
declared one. The layout is a decision the spec makes and nothing else in the
repository asserts it for this table.

**It asserts the module and not the class name**, which the ticket does not spell
and this file must not decide. What is looked up is the mapper for the
`comparison_set` table, whichever class carries it.

**Which failure a red here is, before E5-01 lands**: a failed assertion saying no
mapped class carries a `comparison_set` table, listing the tables that are mapped.
"""

from typing import Any

# SPEC §8's table list spells the table and SPEC §13 the module.
COMPARISON_SET_TABLE = "comparison_set"
BENCHMARK_MODULE = "app.models.benchmark"

# Where the registry is reached from, as `tests/unit/test_uuid_primary_key_is_the_
# first_column.py` reaches it: through the package, because `migrations/env.py`
# imports the package and a module nobody imported is on no metadata, and through
# `app.models.base` rather than `app.db`, which builds an engine out of `Settings`
# at import.
MODELS_PACKAGE = "app.models"
BASE_MODULE = "app.models.base"


def models_registry(import_app_module: Any) -> Any:
    """`Base.registry`, or a failed assertion naming what is missing."""
    package = import_app_module(MODELS_PACKAGE)
    assert package is not None, (
        f"There is no `{MODELS_PACKAGE}` package, so no mapped class can be discovered. "
        "`tests/unit/test_org_models_registered.py` is where that absence is diagnosed."
    )
    base_module = import_app_module(BASE_MODULE)
    assert base_module is not None, (
        f"There is no `{BASE_MODULE}`. E0-04 ships the declarative base there, and every model "
        "module imports `Base` from it rather than from `app.db`."
    )
    registry = getattr(getattr(base_module, "Base", None), "registry", None)
    assert registry is not None, (
        f"`{BASE_MODULE}` exposes no `Base` with a `registry`, so there is nothing to discover "
        "mapped classes from."
    )
    return registry


def mapped_modules_by_table(registry: Any) -> dict[str, tuple[str, str]]:
    """Every mapped table, against the class that maps it and the module it is declared in."""
    found: dict[str, tuple[str, str]] = {}
    for mapper in registry.mappers:
        table = getattr(mapper, "local_table", None)
        if table is None:
            continue
        found[table.name] = (mapper.class_.__name__, mapper.class_.__module__)
    return found


def test_at_least_one_model_module_is_registered(
    configured_env: dict[str, str], import_app_module: Any
) -> None:
    """CONTROL — must be green today.

    The assertion below is about one entry in a mapping, and an empty mapping
    would fail it for a reason that has nothing to do with E5-01: a package that
    does not import, a registry that is not reached, a walk that recognises
    nothing. This is the failure that says which of those happened
    (`docs/MISTAKES.md` entry 3).
    """
    mapped = mapped_modules_by_table(models_registry(import_app_module))

    assert mapped, (
        "No mapped class was discovered at all, so the assertion below is about an empty "
        "mapping and would report a missing table whatever `app/models/` contains."
    )


def test_the_comparison_set_table_is_declared_in_the_benchmark_module(
    configured_env: dict[str, str], import_app_module: Any
) -> None:
    """SPEC §13: the comparison-set model's home is `app/models/benchmark.py`.

    **The mutation it kills:** the model declared in `app/models/org.py` beside
    `course`, which is where it is convenient to put it — the level enumeration
    and the course relationship are both already there — and where §13 does not
    put it. Every other test in this ticket passes against that placement.
    """
    mapped = mapped_modules_by_table(models_registry(import_app_module))

    assert COMPARISON_SET_TABLE in mapped, (
        f"No mapped class carries a `{COMPARISON_SET_TABLE}` table. The tables that are mapped "
        f"are {sorted(mapped)}. SPEC §8 lists this one in its inventory and E5-01 builds it."
    )

    class_name, module = mapped[COMPARISON_SET_TABLE]
    assert module == BENCHMARK_MODULE, (
        f"`{class_name}` maps `{COMPARISON_SET_TABLE}` and is declared in `{module}` rather than "
        f"in `{BENCHMARK_MODULE}`. SPEC §13's repository layout names the module, E5-01's scope "
        "repeats it, and nothing else in this repository asserts it: `alembic check` compares "
        "tables and columns and has no opinion about which file declared one."
    )
