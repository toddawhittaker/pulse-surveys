"""`id` is the first column of every table that mixes in `UuidPrimaryKey`.

`UuidPrimaryKey` declares the primary-key column every model shares, and it pins
that column to the front of the DDL with `sort_order=-1`. The mixin's own
docstring says the pin "is what actually keeps `id` first, and it is not
decoration" — this module is what makes that sentence a guarantee rather than a
comment, because until it existed the pin could be deleted without anything
anywhere going red.

**Why nothing else catches it.** Column *order* is invisible to every gate this
project runs. `alembic check` compares a model's columns against the database's
by name and never by position, so a schema in which every `id` has dropped to
last reports no drift at all; the migration that would reorder them is never
written and never missed. The integration suite reads columns by name too — a
row is seeded by keyword and read back by key, so a table whose columns arrived
in a different order behaves identically. That combination is
`docs/MISTAKES.md` entry 2 in its ordinary form: behaviour shipped, and nothing
asserting it.

**The mutation this survives:** delete `sort_order=-1` from the mixin's
`mapped_column`. Without the pin a mixin's columns are appended *after* the ones
the model declares itself, so every table using `UuidPrimaryKey` moves its `id`
from first to last, and the sweep below goes red naming each of them. This was
measured before this file was written: with the pin removed the whole suite
passed and `alembic check` reported no drift.

**The near miss that must stay green:** a table that does not use the mixin and
orders its columns however it likes. Nothing here says a primary key must come
first in general — only that a model which asked for this mixin got what the
mixin promises. A model with a hand-declared `id`, a composite key, or no `id`
at all is outside the swept set by construction, and adding one must not turn
this red.

**Where it can go blind.** The set is derived from the registry rather than
listed here, so it grows with the schema and cannot fall out of date — and a
derived set can also become empty, which would report a clean sweep over a
repository that had lost the mixin entirely. The canary below is what tells
those two apart, and it is the reason the sweep's silence can be believed
(`docs/MISTAKES.md` entry 3).
"""

from typing import Any

import pytest

# Reached through the package rather than through one model module, for the
# reason `tests/unit/test_org_models_registered.py` gives at length:
# `migrations/env.py` imports the package, and a model module nobody imported is
# on no registry — so a sweep that imported one module by name would report a
# clean answer about a schema it had only seen part of.
MODELS_PACKAGE = "app.models"
BASE_MODULE = "app.models.base"

# The mixin, and where it may be reached from. `app.models.base` is where the
# declarative base lives (E0-04, SPEC §13) and is the likeliest home; the package
# is read first in case it re-exports. Both are tried so that this file does not
# pin which of the two a model imports it from — the name is what matters here,
# not the path to it.
MIXIN_NAME = "UuidPrimaryKey"
MIXIN_MODULES = (MODELS_PACKAGE, BASE_MODULE)

# The column the mixin declares, and the keyword that puts it first. Named
# constants rather than literals in a message, because both are quoted several
# times below and a deliberate rename should be a one-line change here.
PRIMARY_KEY_COLUMN = "id"
SORT_ORDER_PIN = "sort_order=-1"


def models_registry(import_app_module: Any) -> Any:
    """`Base.registry`, or a failed assertion naming what is missing.

    Every absence on the way is turned into a failure with a name in it rather
    than an exception from inside a lookup: a missing package, a missing base
    module and a base with no registry are three different repairs, and a test
    that reported them as one would send the reader to the wrong file.
    """
    package = import_app_module(MODELS_PACKAGE)
    assert package is not None, (
        f"There is no `{MODELS_PACKAGE}` package, so no mapped class can be discovered and this "
        "sweep would recognise nothing. `tests/unit/test_org_models_registered.py` is where that "
        "absence is diagnosed."
    )

    base_module = import_app_module(BASE_MODULE)
    assert base_module is not None, (
        f"There is no `{BASE_MODULE}`. E0-04 ships the declarative base there, and every model "
        "module imports `Base` from it rather than from `app.db`."
    )

    registry = getattr(getattr(base_module, "Base", None), "registry", None)
    assert registry is not None, (
        f"`{BASE_MODULE}` exposes no `Base` with a `registry`, so there is nothing to discover "
        "mapped classes from — and nothing for `migrations/env.py` to autogenerate against "
        "either."
    )
    return registry


def primary_key_mixin(import_app_module: Any) -> Any:
    """The `UuidPrimaryKey` class itself, or a failure saying where it was looked for.

    The class rather than its name, so membership is decided by `issubclass`
    against the real object. Matching on the *name* in an MRO would also match a
    second class that happened to be spelled the same way in another module,
    which is the kind of coincidence a sweep should not be able to mistake for
    coverage.
    """
    for name in MIXIN_MODULES:
        module = import_app_module(name)
        if module is None:
            continue
        found = getattr(module, MIXIN_NAME, None)
        if isinstance(found, type):
            return found

    pytest.fail(
        f"Neither {list(MIXIN_MODULES)} exposes a class called `{MIXIN_NAME}`, so this module "
        "cannot tell which models were supposed to inherit a uuid primary key and its sweep "
        "would be over nothing at all.\n"
        "\n"
        f"That is either a rename — in which case `{MIXIN_NAME}` in this file is the one line "
        "that changes — or the mixin has been removed, in which case the column-order rule it "
        "carried has gone with it and this file should go too, deliberately and in a change that "
        "says so."
    )


def guarded_tables(registry: Any, mixin: type) -> dict[str, tuple[str, str]]:
    """Every mapped table whose class inherits the mixin, with its first column.

    Keyed by table name and holding the model that mapped it, so a failure can
    name both: a reader repairing this needs the table to look at the DDL and the
    class to look at the declaration.

    A mapper with no local table is skipped rather than failed on — an inherited
    mapper shares its parent's table and would report the same table twice — and
    a skip cannot hide anything here, because the parent is itself in the
    registry and is swept on its own account.
    """
    found: dict[str, tuple[str, str]] = {}
    for mapper in registry.mappers:
        if not issubclass(mapper.class_, mixin):
            continue
        table = getattr(mapper, "local_table", None)
        if table is None:
            continue
        columns = list(getattr(table, "columns", []) or [])
        if not columns:
            continue
        found[table.name] = (mapper.class_.__name__, columns[0].name)
    return found


def test_at_least_one_mapped_model_mixes_in_the_uuid_primary_key(
    configured_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """The canary: the sweep below has something to be a sweep over.

    An empty set passes the ordering assertion perfectly, so without this a
    repository that had renamed the mixin, stopped using it, or a walk that had
    stopped recognising it would all report exactly what a correct schema
    reports (`docs/MISTAKES.md` entry 3). This is the assertion that tells those
    apart, and it is proved against the real registry rather than a hand-written
    imitation of one.
    """
    registry = models_registry(import_app_module)
    mixin = primary_key_mixin(import_app_module)
    guarded = guarded_tables(registry, mixin)

    assert guarded, (
        f"No mapped class on `Base` inherits `{MIXIN_NAME}`, so the column-order sweep in this "
        "module is over an empty set and would report a clean result whatever the models "
        "declare.\n"
        "\n"
        "Three things look like this and only one of them is fine: the mixin was renamed or "
        "removed, every model stopped using it, or this walk has gone blind — it reads "
        f"`{MODELS_PACKAGE}` and matches `issubclass` against the class itself. "
        "`tests/unit/test_uuid_primary_key_is_the_first_column.py` is the one place that changes "
        "for the first and the third; the second is a decision that belongs in a pull request, "
        "and it retires this file rather than leaving it green over nothing."
    )


def test_every_model_that_mixes_in_the_uuid_primary_key_lists_id_first(
    configured_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """The criterion: the mixin's `sort_order=-1` actually put `id` at the front.

    Read off the mapped table's own column collection, which is the order the
    DDL is emitted in, so this is a statement about what `CREATE TABLE` writes
    rather than about what the class body looks like.

    **The mutation this survives:** remove `sort_order=-1` from the mixin's
    `mapped_column`. Every table below then lists its own first column first and
    `id` last, and this fails naming each one.
    **The near miss that must stay green:** a model that does not use the mixin,
    whatever order its columns are in. `issubclass` is what keeps it out, and
    the failure prints only the tables that asked for the guarantee.
    """
    registry = models_registry(import_app_module)
    mixin = primary_key_mixin(import_app_module)
    guarded = guarded_tables(registry, mixin)

    assert guarded, (
        f"No mapped class inherits `{MIXIN_NAME}`, so this assertion would pass over nothing. "
        "`test_at_least_one_mapped_model_mixes_in_the_uuid_primary_key` above is where that is "
        "diagnosed."
    )

    offenders = {
        table: (model, first)
        for table, (model, first) in sorted(guarded.items())
        if first != PRIMARY_KEY_COLUMN
    }

    assert not offenders, "\n".join(
        [
            f"These tables mix in `{MIXIN_NAME}` and do not list `{PRIMARY_KEY_COLUMN}` first:",
            *(
                f"  {table}: first column is `{first}` (mapped by `{model}`)"
                for table, (model, first) in offenders.items()
            ),
            "",
            f"The fix is `{SORT_ORDER_PIN}` on the mixin's `mapped_column`. Without it a mixin's "
            "columns are appended after the ones each model declares itself, so the shared "
            f"`{PRIMARY_KEY_COLUMN}` lands at the end of every table that inherits it.",
            "",
            "Nothing else in the pipeline sees this. `alembic check` compares a model's columns "
            "against the database's **by name and never by position**, so it reports no drift "
            "over a schema whose ids have all moved to last, and the tests that read rows do it "
            "by key. That is why the pin is not decoration, and why this assertion exists.",
        ]
    )
