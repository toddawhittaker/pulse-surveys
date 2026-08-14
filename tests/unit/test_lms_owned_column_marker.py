"""LMS-owned columns are marked by an `lms_` name prefix — ticket E0-05.

Acceptance criterion: "Every LMS-owned column carries the `lms_` prefix, asserted
by walking `Base.metadata` rather than by reading the model — so a later ticket
that adds an unprefixed LMS column fails instead of passing silently."

The marker exists so that the authorization layer can tell, from the name alone,
which columns a write path may never touch (SPEC §2.1: courses, sections and
section codes are LMS-owned and read-only in Pulse). E0-05 has no write path, so
what can be asserted here is the marker itself — and a marker with nothing
asserting it is `docs/MISTAKES.md` entry 2, which is how the previous version of
this ticket left it.

**The two directions, and which one is complete.**

*Every prefixed column is one somebody meant.* Asserted, and it is complete for
the tables this ticket creates: the four Pulse-owned containment tables —
institution, college, department, prefix — may carry no prefixed column at all.
Nothing in them comes from the LMS, so a prefix there either marks a column that
is not LMS-owned, which teaches the authz layer to refuse a write Pulse is
entitled to make, or is decoration, which teaches every later reader that the
prefix means nothing in particular.

*Every LMS-owned column is prefixed.* Asserted for the columns that are named —
the two the ticket spells, and the unprefixed spellings of the facts SPEC §2.1
names — and **it stops there, deliberately, because the rest cannot be asserted
from `Base.metadata`**. "LMS-owned" is a fact about where data comes from, and
the metadata records no such fact once the prefix is missing: an unprefixed
`external_id` arriving in a later ticket is indistinguishable, to any test that
walks the metadata, from a column Pulse owns outright. Closing that would mean
either enumerating the implementer's columns here, which decides the schema from
the test suite, or asking the model to declare its LMS-owned set separately,
which is the second source of truth the `lms_` prefix was chosen over. The
enforcing test belongs where the write path is — E0-11's authz chokepoint — and
what this module can do is make the named cases fail loudly and stop the obvious
regression, an unprefixed twin appearing beside a prefixed column.

**Why the metadata and not the migration.** The criterion says `Base.metadata`,
and it is the right side to read: the authz layer will resolve a column through
the ORM, so a prefix that exists only in the migration is not a marker anything
can act on.
"""

from typing import Any

import pytest

LMS_PREFIX = "lms_"

# The two the ticket spells outright, as `(table, column)`.
MARKED_COLUMNS = (
    ("course", "lms_number"),
    ("section", "lms_section_code"),
)

# Tables E0-05 creates that hold nothing the LMS owns (SPEC §2.1: the LMS-owned
# list is courses, sections, section codes, enrollments and teaching instructors,
# and the institution/college/department/prefix hierarchy is Pulse's own).
PULSE_OWNED_TABLES = ("institution", "college", "department", "prefix")

# Unprefixed spellings of facts SPEC §2.1 puts on the LMS's side of the line. A
# **sample and not a closure** — see the module docstring. Each is asserted only
# if the column is present, so none of these decides that a column has to exist;
# what they refuse is an LMS-owned fact stored under a name the marker does not
# reach, including the regression this criterion is really about, an unprefixed
# twin appearing next to `lms_number` or `lms_section_code`.
#
# Deliberately absent: instructor spellings on `section`. Teaching instructors
# are LMS-owned too, but they arrive in E0-08, and that ticket should carry the
# criterion rather than this module reaching forward into a schema nobody has
# designed yet.
UNPREFIXED_SPELLINGS = {
    "course": ("number", "course_number", "catalog_number", "title", "name", "description"),
    "section": ("code", "section_code", "number", "title", "name"),
}


def containment_metadata(import_app_module: Any) -> Any:
    """`Base.metadata` with the org models registered on it.

    Reached through `app.models` rather than through `app.models.org`, for the
    reason `tests/unit/test_org_models_registered.py` gives at length: `env.py`
    imports the package, and a module nobody imported is on no metadata. That
    module is where a missing registration is diagnosed; this one only needs
    something to walk, so it fails by pointing there.
    """
    package = import_app_module("app.models")
    if package is None:
        pytest.fail(
            "There is no `app.models` package to walk. E0-05 adds `org.py` to it and imports "
            "the module in `__init__.py` in the same change; "
            "tests/unit/test_org_models_registered.py says why the import is the load-bearing "
            "half."
        )
    base_module = import_app_module("app.models.base")
    metadata = getattr(getattr(base_module, "Base", None), "metadata", None)
    if metadata is None:
        pytest.fail(
            "`app.models.base` is missing, or exposes no `Base` with `metadata`, so there is "
            "nothing to walk — and nothing for `migrations/env.py` to autogenerate against "
            "either. E0-04 ships the declarative base there."
        )
    return metadata


def table_columns(metadata: Any, name: str) -> set[str]:
    """Every column name on one registered table, or a failure saying it is absent."""
    table = metadata.tables.get(name)
    if table is None:
        pytest.fail(
            f"No `{name}` table is registered on `Base.metadata` (it holds "
            f"{sorted(metadata.tables)}). E0-05 creates institution, college, department, "
            "prefix, course and section."
        )
    return {column.name for column in table.columns}


@pytest.mark.parametrize(("table_name", "column_name"), MARKED_COLUMNS)
def test_the_lms_owned_columns_the_ticket_names_carry_the_prefix(
    configured_env: dict[str, str],
    import_app_module: Any,
    table_name: str,
    column_name: str,
) -> None:
    """The two columns the ticket spells exist under their marked names.

    Narrow on purpose, and it is the half of "every LMS-owned column is
    prefixed" that can be pinned to a name. The course number and the section
    code are LMS-owned in SPEC §2.1 and named in E0-05's scope, so `lms_number`
    and `lms_section_code` are not a reading of the rule — they are the rule's
    two worked examples.
    """
    metadata = containment_metadata(import_app_module)
    present = sorted(table_columns(metadata, table_name))

    assert column_name in present, (
        f"`{table_name}` has no `{column_name}` column — it has {present}. E0-05 marks "
        f"LMS-owned columns with an `{LMS_PREFIX}` name prefix and names this one, so that a "
        "later ticket adding a write path can see from the column alone that Pulse does not "
        "own the value. A marker that is missing on the columns the ticket spells is not a "
        "marker the authz layer can rely on for the ones it does not."
    )


@pytest.mark.parametrize("table_name", sorted(UNPREFIXED_SPELLINGS))
def test_no_lms_owned_fact_is_stored_under_an_unprefixed_name(
    configured_env: dict[str, str],
    import_app_module: Any,
    table_name: str,
) -> None:
    """An LMS-owned fact may not sit beside the marker without wearing it.

    This is the part of the criterion that keeps working after today: the failure
    it describes is a later ticket adding `code` next to `lms_section_code`, or
    restoring `number` beside `lms_number`, and it fails here rather than passing
    silently. It is a sample of the LMS-owned facts and not the whole set — the
    module docstring says why the whole set is not reachable from the metadata.
    """
    metadata = containment_metadata(import_app_module)
    present = table_columns(metadata, table_name)

    unmarked = sorted(present & set(UNPREFIXED_SPELLINGS[table_name]))
    assert not unmarked, (
        f"`{table_name}` carries {unmarked} with no `{LMS_PREFIX}` prefix, and SPEC §2.1 puts "
        f"{table_name}s on the LMS's side of the ownership line — read-only in Pulse, synced "
        "hourly and at launch. An unprefixed name is invisible to a marker that is a name, so "
        f"the column reads as Pulse's to edit. Rename it (`{LMS_PREFIX}...`), or if the value "
        "really is Pulse's own, say so in the pull request and take the spelling out of "
        "`UNPREFIXED_SPELLINGS` in this file with the reason."
    )


def test_no_pulse_owned_table_carries_the_lms_prefix(
    configured_env: dict[str, str],
    import_app_module: Any,
) -> None:
    """The other direction: a prefixed column is a column somebody meant to mark.

    **The non-vacuity guard runs first and is not ceremony.** "No Pulse-owned
    table carries the prefix" is satisfied most thoroughly by a schema where the
    prefix appears nowhere at all — which is the state this criterion exists to
    leave behind, and it would report green (`docs/MISTAKES.md` entry 3). So the
    marker is required to exist on the LMS-owned side before its absence
    elsewhere is allowed to mean anything.
    """
    metadata = containment_metadata(import_app_module)

    marked = {
        f"{table.name}.{column.name}"
        for table in metadata.tables.values()
        for column in table.columns
        if column.name.startswith(LMS_PREFIX)
    }
    assert marked, (
        f"No column anywhere on `Base.metadata` starts with `{LMS_PREFIX}`, so the marker does "
        "not exist yet and this test would pass against a schema with no marking at all. E0-05 "
        "marks the LMS-owned columns on `course` and `section` this way."
    )

    misplaced = sorted(
        f"{name}.{column}"
        for name in PULSE_OWNED_TABLES
        if name in metadata.tables
        for column in table_columns(metadata, name)
        if column.startswith(LMS_PREFIX)
    )
    assert not misplaced, (
        f"{misplaced} carry the `{LMS_PREFIX}` prefix on tables that hold nothing the LMS "
        f"owns. SPEC §2.1's LMS-owned list is courses, sections, section codes, enrollments "
        "and teaching instructors; the institution, college, department and prefix hierarchy "
        "is Pulse's own, built in the admin console. A prefix here either marks a column Pulse "
        "is entitled to write, which the authz layer will then refuse, or marks nothing at "
        "all — and a marker that appears where it does not apply stops being readable as one."
    )
