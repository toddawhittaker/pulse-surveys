"""The demo institution `scripts/seed.py` loads — ticket E0-17.

Every acceptance criterion the database can answer for. What is asserted
elsewhere, or not at all: `make seed` losing its tolerance for an absent script
is `tests/unit/test_seed_target_is_enforcing.py`, which needs no database; and
the half of the last criterion about names — "no name resembles a real person at
a real institution" — is not machine-checkable and is deliberately not asserted
under a weaker reading. What *is* checkable about that criterion is the address:
an email that could be delivered to is the one way a demo seed becomes somebody's
mail, and that is asserted below.

**Why this runs a process instead of calling a function.** The criteria are about
`make seed`, which runs the file as a program. `tests/conftest.py`'s `DemoSeed`
runs it the same way, against a database created and migrated for this module and
dropped afterwards, and hands back the exit status. Nothing in this file names a
callable inside the script, because E0-17 names none — a test that imported one
would be requiring an interface the ticket leaves open, and a script whose work
happens under `if __name__ == "__main__":` would import as a no-op and be reported
green for having done nothing.

**The seed commits, which is why the database is its own.** Every other database
test in this suite writes inside `db_session` and rolls back. A script that opens
its own connection sees none of that and is seen by none of it, so rows it left in
the session database would surface as somebody else's failed non-vacuity guard
three tickets from now.

**Not every criterion here is about the database.** Two sections towards the end
assert the guard ADR 0063 put in front of the script — it refuses to run unless
`ENVIRONMENT` is `development` — and they ask it in two different ways, because
two different questions are being asked. What the script *does* with a value is
asked by running the process, which is how anyone meets it. Which of two sources
supplied that value is asked in-process, against the resolution the script
exposes as a function, because a subprocess started from here inherits one source
from a fixture and the other from whatever untracked file the developer has:
`docs/MISTAKES.md` entry 30 is a case that measured exactly that and passed in CI
while failing on every workstation.

**Order in this file is deliberate.** Everything above the idempotency section
measures the state *one* run produces, which is the state every criterion
describes. The second run happens last, so a script that duplicates rows produces
one failure naming duplication rather than six failures about shapes. The guard
sections are harmless to what is around them: the refused runs open no
connection, the in-process ones open no process at all, and the one run that is
admitted is a run of an idempotent seed against the database that already holds
it.

**What this file does not decide.** The role spellings, the parent edge and what a
scope node is made of are read off the schema through `SupervisionGraph`, which
`tests/conftest.py` built for E0-09 and which answers those questions from
`Base.metadata` alone. It is requested here **only as a reader**: nothing is
written through it, and the session it holds belongs to a different database
entirely. That is cheaper than a fourth copy of the scope-shape logic, which
`docs/MISTAKES.md` entry 13 is about — and a copy is what nobody updates.

**The small schema helpers and the constant lists are copied rather than
imported.** A test module importing the conftest module by name works only
because of where pytest puts `tests/` on `sys.path`, and a collection error is
not a failing test; `test_identity_schema.py` and `test_role_assignment_graph.py`
copy theirs for the same reason. Each copy is marked where it sits, and one of
them — `UNROUTABLE_EMAIL_DOMAINS` — has a twin in
`tests/integration/test_mock_lms_seed_data.py`. Change one, change both.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import date
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Uuid, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.types import TypeDecorator

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Names this file needs. Almost every one is spelled by a ticket, by the spec, or
# by a schema that has already shipped; the ones that are this file's own choice
# say so where they sit.
# ---------------------------------------------------------------------------

ASSIGNMENTS = "role_assignment"
MAPPINGS = "lead_faculty_mapping"
PLATFORMS = "lti_platform"

# SPEC §2.1's containment hierarchy, outermost first. A copy of the tuple in
# `tests/conftest.py`; see the module docstring on copies.
CONTAINMENT_ORDER = ("institution", "college", "department", "prefix", "course", "section")

# Not this file's choice: E0-05 created these columns under these names and
# E0-06/E0-07 added the derived four.
COURSE_NUMBER_COLUMN = "lms_number"
COURSE_TITLE_COLUMN = "lms_title"
COURSE_LEVEL_COLUMN = "level"
SECTION_CODE_COLUMN = "lms_section_code"
DERIVED_LENGTH = "length_weeks"
DERIVED_START = "start_date"
DERIVED_END = "end_date"
DERIVED_MODALITY = "modality"

# E0-06 spells the letter column — "**The letter column is named `letter`**" — and
# leaves the other two to candidates, exactly as
# `tests/integration/test_section_date_derivation.py` records.
LETTER_COLUMN = "letter"
LETTER_LENGTH_COLUMNS = ("length_weeks", "length")
LETTER_START_COLUMNS = ("start_date", "starts_on", "start")
TERM_START_COLUMNS = ("start_date", "starts_on", "start")
TERM_END_COLUMNS = ("end_date", "ends_on", "end")

# SPEC §8's five levels, which E0-05 derives from the course number. E0-17's
# scope: "courses across all five levels".
COURSE_LEVELS = ("DEV", "UG", "UGGR", "GR", "DR")

# SPEC §2.2's Fall 2026 seed map — "12-week U/R/Q starting 8/17, 9/7, 9/28; 6-week
# E/F/H; 8-week X/Y/Z; 10-week S/T; 15-week V/D; 16-week K; 3-week sections
# numbered 2-7" — as `{start position: length in weeks}`. The lengths are the
# spec's; nothing here is this file's invention.
FALL_2026_MAP_LENGTHS = {
    "U": 12,
    "R": 12,
    "Q": 12,
    "E": 6,
    "F": 6,
    "H": 6,
    "X": 8,
    "Y": 8,
    "Z": 8,
    "S": 10,
    "T": 10,
    "V": 15,
    "D": 15,
    "K": 16,
    "2": 3,
    "3": 3,
    "4": 3,
    "5": 3,
    "6": 3,
    "7": 3,
}

# The three start dates §2.2 documents, and the term start they imply: `U` runs
# the full twelve weeks from the term's own first day, which is how
# `tests/integration/test_section_date_derivation.py` reads the same sentence.
FALL_2026_START = date(2026, 8, 17)
DOCUMENTED_START_DATES = {"U": date(2026, 8, 17), "R": date(2026, 9, 7), "Q": date(2026, 9, 28)}

# §2.2: "Modality: `WW` online, `FF` face-to-face." E0-17's scope asks for
# sections in both.
MODALITY_SUFFIXES = ("WW", "FF")

# E0-17's scope: sections spanning "at least three different lengths".
DISTINCT_SECTION_LENGTHS = 3

# Domains that cannot receive mail from anywhere. RFC 2606 and RFC 6761 reserve
# `.invalid`, `.test`, `.example` and the `example.*` second-level names for
# exactly this, and `.local` is reserved by RFC 6762. **There are two copies of
# this tuple in `tests/`**: here and in `test_mock_lms_seed_data.py`, which asks
# the same question of the mock platform's seed. Change one, change both.
UNROUTABLE_EMAIL_DOMAINS = (
    ".invalid",
    ".test",
    ".example",
    ".local",
    ".localhost",
    "example.com",
    "example.net",
    "example.org",
    "example.edu",
)

# How a column is recognised as holding an address. Fragments rather than names,
# because no ticket says which table carries one — `person`, `user_identity` and
# `lti_platform` are all plausible and the sweep should reach whichever it is.
EMAIL_COLUMN_FRAGMENTS = ("email", "mail")

# **Settled by the implementation, and no longer this file's guess.** These two
# were written here as a choice — E0-17 leaves the mechanism open, and
# `.env.example` documents `ENVIRONMENT` as the deployment name — and
# `docs/adr/0063-the-demo-seed-runs-only-in-a-development-environment.md` is what
# made them the mechanism: the seed "refuses to run unless `ENVIRONMENT` is
# exactly `development`", checked "before it builds a database URL, so a refused
# run opens no connection at all".
DEPLOYED_ENVIRONMENT_VARIABLE = "ENVIRONMENT"
DEPLOYED_ENVIRONMENT_VALUE = "production"

# The one value the guard admits. ADR 0063's check is an equality against this
# string and deliberately not a deny-list, "because the set of names a deployment
# might use is open" — an equality after stripping surrounding whitespace, and
# case-sensitive. Its "What the comparison actually is" subsection states the
# whole shape; the cases further down are what would catch it changing.
DEVELOPMENT_ENVIRONMENT = "development"

# An address nothing can connect to, used to prove *when* the guard runs rather
# than only that it does. Not a credential and not copied from one: port 1 is
# reserved, nothing listens on it, and a connection there is refused at once
# rather than waiting on a name lookup. A run that prints the guard's refusal
# while pointed here cannot have opened a connection first, which is ADR 0063's
# ordering claim; a run that gets past the guard fails on this address instead.
UNREACHABLE_DATABASE_URL = "postgresql+psycopg://nobody:nothing@127.0.0.1:1/nowhere"

# Every variable `seed_environment` in tests/conftest.py sets to a database URL,
# so that unreachability can be said in all of them at once. E0-17 does not say
# which one a seed reads — supplying every spelling is that fixture's whole
# design — so pointing only one at the address above would let a script that
# prefers another quietly reach the real database, and the refusals below would
# then be evidence of nothing.
DATABASE_URL_VARIABLES = ("DATABASE_URL", "ALEMBIC_DATABASE_URL", "CARE_DATABASE_URL")

# How deep a row label follows foreign keys before it stops. Bounded so that a
# seed which stored a loop produces a failed assertion in the test that asked
# rather than a recursion error inside this file, and set clear of the longest
# chain the schema has: an assignment scoped to a section reaches the institution
# in seven steps down SPEC §2.1's containment hierarchy.
LABEL_DEPTH = 8


# ---------------------------------------------------------------------------
# Reading the schema. Copies; see the module docstring.
# ---------------------------------------------------------------------------


def stored_type(column: Any) -> Any:
    """The type a column stores, with any `TypeDecorator` resolved away. A copy."""
    kind = column.type
    while isinstance(kind, TypeDecorator):
        kind = kind.impl_instance
    return kind


def foreign_key_columns(table: Any, target: str) -> list[str]:
    """Every column on `table` whose foreign key points at `target`'s primary key.

    **The primary key half is not tidiness.** ADR 0018 gives `week` and
    `start_letter_map` a *composite* key into `term` — `(term_id,
    term_length_weeks) → term (id, length_weeks)` — so both of those columns
    reference `term`, and a helper that counted references would find two links
    where there is one relationship and stop. Filtering on the referenced column
    being a primary key leaves the link this module means to follow.
    """
    return sorted(
        {
            key.parent.name
            for key in table.foreign_keys
            if key.column.table.name == target and key.column.primary_key
        }
    )


def enum_text(value: Any) -> str:
    """One stored value as comparable upper-case text, member or string alike.

    Both sides of every comparison against an enum go through this, so the
    assertion is about the two agreeing rather than about which representation the
    schema chose — `Base.metadata`'s `Enum` hands back a Python member when the
    column was declared with an enum class and a plain string when it was not, and
    no ticket decides which. `modality_text` in
    `tests/integration/test_section_date_derivation.py` is the same helper for the
    same reason; this one prefers the member's *name*, because that is what
    SQLAlchemy puts in the type's `enums` and therefore what
    `SupervisionGraph.role_value` answers with.
    """
    return str(getattr(value, "name", None) or getattr(value, "value", value)).upper()


def require_table(tables: dict[str, Any], name: str) -> Any:
    """The declared table called `name`, or a failure saying it is not there."""
    table = tables.get(name)
    if table is None:
        pytest.fail(
            f"There is no `{name}` table (what is there: {sorted(tables)}). E0-05, E0-06, E0-08 "
            "and E0-09 create every table this module reads; a missing one is diagnosed by those "
            "tickets' own modules, and nothing here can mean anything without it."
        )
    return table


def require_column(table: Any, candidates: tuple[str, ...]) -> str:
    """The first of `candidates` that `table` has, or a failure listing both sides."""
    for candidate in candidates:
        if candidate in table.c:
            return candidate
    present = [column.name for column in table.columns]
    pytest.fail(
        f"`{table.name}` has none of the columns {list(candidates)} — it has {present}. The "
        "candidate list is a constant at the top of this file, so a deliberate rename is a "
        "one-line change here."
    )


def single_primary_key(table: Any) -> str | None:
    """The name of `table`'s one primary key column, or `None` where it has several."""
    columns = list(table.primary_key.columns)
    return columns[0].name if len(columns) == 1 else None


def require_columns(table: Any, names: tuple[str, ...]) -> None:
    """Stop unless `table` has every one of `names`, listing what it does have.

    Used where a test reads several columns off a row by name. Without it a
    missing column ends the test in a `KeyError` from inside a comprehension,
    which is a broken test rather than a red one — and the two are fixed by
    different people.
    """
    absent = [name for name in names if name not in table.c]
    if absent:
        pytest.fail(
            f"`{table.name}` has none of {absent} — it has "
            f"{[column.name for column in table.columns]}. E0-05 named `lms_number`, `lms_title` "
            "and `lms_section_code`, E0-07 added the four derived section columns, and each is a "
            "constant at the top of this file, so a deliberate rename is a one-line change here."
        )


def one_foreign_key_column(table: Any, target: str) -> str:
    """The single column on `table` keyed to `target`'s primary key, or a failure."""
    found = foreign_key_columns(table, target)
    if len(found) != 1:
        pytest.fail(
            f"`{table.name}` has {len(found)} foreign keys to `{target}`'s primary key ({found}). "
            "This module "
            "walks the containment hierarchy and the people graph by following keys rather than "
            "by guessing column names, and a fork in that walk is a schema question rather than "
            "something to pick a side of here."
        )
    return found[0]


def model_for(table_name: str) -> Any:
    """The mapped class behind one table, found through the registry. A copy.

    Found and not named, for the reason `test_section_date_derivation.py` gives:
    no ticket spells an ORM class name, and importing one by a guessed name would
    be this file deciding it.
    """
    base_module = import_module("app.models.base")
    base = getattr(base_module, "Base", None)
    registry = getattr(base, "registry", None)
    if registry is None:
        pytest.fail("`app.models.base.Base` exposes no `registry`, so no mapped class is findable.")

    found = [
        mapper.class_
        for mapper in registry.mappers
        if getattr(mapper.local_table, "name", None) == table_name
    ]
    if len(found) != 1:
        pytest.fail(
            f"{len(found)} mapped classes stand behind the `{table_name}` table ({found}). This "
            "module needs exactly one so it can hand the derivation a real instance."
        )
    return found[0]


# ---------------------------------------------------------------------------
# Reading the seeded database.
# ---------------------------------------------------------------------------


def seeded_tables(tables: dict[str, Any]) -> list[Any]:
    """Every declared table with exactly one primary key column, parents first.

    Sorted by dependency, so a label that follows a foreign key finds the row it
    points at already read. `MetaData.sorted_tables` does the sorting.
    """
    if not tables:
        return []
    ordered = next(iter(tables.values())).metadata.sorted_tables
    return [table for table in ordered if single_primary_key(table) is not None]


def read_rows(connection: Any, tables: dict[str, Any]) -> dict[str, dict[Any, dict[str, Any]]]:
    """Every row of every declared table, keyed by table name and primary key."""
    found: dict[str, dict[Any, dict[str, Any]]] = {}
    for table in seeded_tables(tables):
        key = single_primary_key(table)
        rows = connection.execute(select(table)).mappings().all()
        found[table.name] = {row[key]: dict(row) for row in rows}
    return found


def rows_of(rows: dict[str, dict[Any, dict[str, Any]]], name: str) -> list[dict[str, Any]]:
    """Every row of one table as a list, or an empty list where the table was not read."""
    return list(rows.get(name, {}).values())


@contextmanager
def reading(demo: Any, tables: dict[str, Any]) -> Iterator[dict[str, dict[Any, dict[str, Any]]]]:
    """Open a connection to the seeded database and read the whole of it."""
    with demo.connect() as connection:
        yield read_rows(connection, tables)


@contextmanager
def demo_session(demo: Any) -> Iterator[Any]:
    """A mapped session on the seeded database, for the one test that needs the ORM."""
    engine = create_engine(demo.database.superuser_url)
    try:
        with Session(bind=engine) as session:
            yield session
    finally:
        engine.dispose()


def seeded(run: Any) -> None:
    """Stop the test unless the first seed run succeeded, naming the test that owns it.

    Every assertion in this module is about what the script *wrote*, and over a
    database it failed to write to each one is satisfied by emptiness or fails for
    a reason it is not about (`docs/MISTAKES.md` entry 3). This makes that one
    failure, in one place, pointing at the criterion that owns it.
    """
    if not run.succeeded:
        pytest.fail(
            "The seed run this module is built on did not succeed, so nothing below it can mean "
            "anything. E0-17's third criterion — '`make seed` on a freshly migrated database "
            "completes without error' — is asserted by "
            "`test_seeding_a_freshly_migrated_database_completes_without_error`, and that is the "
            f"failure to read first.\n{run.report()}"
        )


# ---------------------------------------------------------------------------
# What "the same database state" means, for the idempotency criterion.
# ---------------------------------------------------------------------------


def row_label(
    tables: dict[str, Any],
    rows: dict[str, dict[Any, dict[str, Any]]],
    table_name: str,
    key: Any,
    depth: int = LABEL_DEPTH,
    seen: tuple[tuple[str, Any], ...] = (),
) -> str:
    """One row rendered as text, with its uuid keys resolved into the rows they name.

    **Why not just compare the rows.** Every primary key here is a server-generated
    uuid (ADR 0016), and E0-17 does not say whether a second run re-uses the rows
    it finds or reloads the table — both are idempotent in the sense the criterion
    means, and only one of them keeps the same uuids. Comparing raw rows would pin
    that choice; dropping the uuids and comparing what is left would lose the
    *links*, so a second run that re-parented every assignment would compare equal.
    Resolving each key into the label of the row it points at keeps the links and
    pins nothing: two runs agree when they built the same shape out of the same
    values, whatever ids they gave it.

    Bounded by `depth` and by the rows already on the path, so a graph holding a
    loop renders as text rather than recursing forever — the cycle criterion is
    asserted by its own test, and this one must not fail in its place.
    """
    if (table_name, key) in seen or depth <= 0:
        return f"{table_name}(…)"
    row = rows.get(table_name, {}).get(key)
    if row is None:
        # The key itself is deliberately left out: it is a uuid, and putting one
        # into a label would make two runs differ here for the one reason this
        # comparison is not about. Every table in this schema has a single uuid
        # primary key (ADR 0016), so the only way here is a row a foreign key
        # names and the database does not hold — which cannot happen while the
        # key is enforced, and would be worth its own failure if it did.
        return f"{table_name}(<row not read>)"

    table = require_table(tables, table_name)
    parts: list[str] = []
    for column in table.columns:
        value = row.get(column.name)
        if not isinstance(stored_type(column), Uuid):
            parts.append(f"{column.name}={value!r}")
            continue
        if value is None:
            parts.append(f"{column.name}=None")
            continue
        targets = sorted(column.foreign_keys, key=lambda fk: str(fk.target_fullname))
        if not targets:
            # A uuid that names nothing outside its own row: this row's own
            # identity, which is exactly what must not be compared.
            continue
        target = targets[0].column
        parts.append(
            f"{column.name}->"
            + row_label(
                tables,
                rows,
                target.table.name,
                value,
                depth - 1,
                (*seen, (table_name, key)),
            )
        )
    return f"{table_name}({', '.join(parts)})"


def labelled(
    tables: dict[str, Any], rows: dict[str, dict[Any, dict[str, Any]]]
) -> dict[str, list[str]]:
    """Every row of every table as a sorted list of labels, per table."""
    return {
        name: sorted(row_label(tables, rows, name, key) for key in table_rows)
        for name, table_rows in rows.items()
    }


def counted(rows: dict[str, dict[Any, dict[str, Any]]]) -> dict[str, int]:
    """How many rows each table holds."""
    return {name: len(table_rows) for name, table_rows in rows.items()}


class SecondSeed:
    """The state around a second run of the script, captured once for the module."""

    def __init__(self, before: dict[str, Any], run: Any, after: dict[str, Any]) -> None:
        self.before = before
        self.run = run
        self.after = after


@pytest.fixture(scope="module")
def second_seed(
    demo_database: Any, seeded_demo: Any, metadata_tables: dict[str, Any]
) -> SecondSeed:
    """Run the seed a second time against the same database, reading it either side.

    `seeded_demo` is requested so the first run has certainly happened. Nothing
    here asserts: a second run that fails is E0-17's fourth criterion failing, and
    the test that owns it says so with the script's own output in hand.
    """
    with demo_database.connect() as connection:
        before = read_rows(connection, metadata_tables)
    run = demo_database.run()
    with demo_database.connect() as connection:
        after = read_rows(connection, metadata_tables)
    return SecondSeed(before, run, after)


# ---------------------------------------------------------------------------
# Reading the supervision graph and the containment hierarchy out of what was
# seeded. `graph` below is `SupervisionGraph` used as a reader; see the module
# docstring.
# ---------------------------------------------------------------------------


def scope_node(graph: Any, row: dict[str, Any], kind: str) -> Any:
    """The id of the node of `kind` an assignment is scoped to, or `None`.

    Asks `SupervisionGraph` which of the three shapes E0-09 left open this schema
    took, rather than deciding here. Under the shape where the kind is implied by
    the role there is one id and it is returned whatever `kind` was asked for,
    which is that shape's own meaning rather than a guess.
    """
    shape, detail = graph.scope_shape()
    if shape == "per_kind":
        column = detail.get(kind)
        return None if column is None else row.get(column)
    if shape == "kind_and_id":
        kind_column, id_column = detail
        wanted = enum_text(graph.scope_kind_value(kind))
        return row.get(id_column) if enum_text(row.get(kind_column)) == wanted else None
    return row.get(detail)


def assignments_by_role(graph: Any, rows: dict[str, Any], role: str) -> list[dict[str, Any]]:
    """Every seeded assignment holding `role`, spelled the way the column spells it."""
    wanted = enum_text(graph.role_value(role))
    return [
        row for row in rows_of(rows, ASSIGNMENTS) if enum_text(row[graph.role_column]) == wanted
    ]


def department_of_course(tables: dict[str, Any], rows: dict[str, Any], course_id: Any) -> Any:
    """The department a course belongs to, walked course → prefix → department."""
    course = rows.get("course", {}).get(course_id)
    if course is None:
        return None
    prefix_column = one_foreign_key_column(require_table(tables, "course"), "prefix")
    prefix = rows.get("prefix", {}).get(course[prefix_column])
    if prefix is None:
        return None
    department_column = one_foreign_key_column(require_table(tables, "prefix"), "department")
    return prefix[department_column]


def led_courses(tables: dict[str, Any], rows: dict[str, Any]) -> dict[Any, set[Any]]:
    """Which courses each person leads, out of `lead_faculty_mapping`."""
    mappings = require_table(tables, MAPPINGS)
    person_column = one_foreign_key_column(mappings, "person")
    course_column = one_foreign_key_column(mappings, "course")
    found: dict[Any, set[Any]] = {}
    for row in rows_of(rows, MAPPINGS):
        found.setdefault(row[person_column], set()).add(row[course_column])
    return found


# ---------------------------------------------------------------------------
# Criterion 3 — the run itself.
# ---------------------------------------------------------------------------


def test_seeding_a_freshly_migrated_database_completes_without_error(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 3: "`make seed` on a freshly migrated database completes without error."

    **The second half is not decoration.** "Completes without error" is satisfied
    perfectly by a script that connects, prints a line and exits — and by one that
    catches its own exception and returns zero, which is the shape a loader
    acquires while somebody is making it idempotent. So the exit status and the
    rows are asserted together: the six containment tables, the term and the
    people graph all have to hold something afterwards.

    The database this runs against was created and migrated for this module, so
    "freshly migrated" is literal rather than incidental — nothing else has ever
    written to it.
    """
    assert seeded_demo.succeeded, (
        "The demo seed did not run to completion against a database freshly at head.\n"
        f"{seeded_demo.report()}\n"
        "E0-17's third criterion is this run. The environment it was given supplies the "
        "container's coordinates under every spelling `backend/migrations/env.py` and "
        "`app.config.Settings` read — see `seed_environment` in tests/conftest.py — so a "
        "failure naming a missing variable is a variable no other part of this repository "
        "documents, which is worth saying in the pull request."
    )

    with reading(demo_database, metadata_tables) as rows:
        counts = counted(rows)
    empty = [
        name
        for name in (*CONTAINMENT_ORDER, "term", "start_letter_map", "person", ASSIGNMENTS)
        if not counts.get(name)
    ]
    assert not empty, (
        f"The seed exited zero and left {empty} empty (the whole count: {counts}). E0-17's scope "
        "is a demo institution — 'at least two colleges, several departments, a department "
        "grouping more than one prefix… a Fall 2026 term… a people graph' — and every later epic "
        "develops against it. A script that exits zero having written nothing satisfies "
        "'completes without error' and satisfies the idempotency criterion below perfectly, "
        "which is why the two halves are asserted in one test."
    )


# ---------------------------------------------------------------------------
# Criterion 1 — what the triggers would have refused, re-checked afterwards.
#
# **These two do not care whether the loader disabled anything**, and that is the
# point. ADR 0027 measured that `SET session_replication_role = replica` turns off
# E0-09's supervision trigger with no `ALTER TABLE` and no ownership check, and
# that a two-row cycle stores cleanly under it — a path this script's identity has
# and `pulse_app` does not. The criterion asks the loader to re-check what the
# trigger would have refused if it took that path. A test of the seeded *graph*
# holds whichever way the implementation goes: if the trigger ran, these pass
# because it refused the bad rows; if it was bypassed and the loader re-checked,
# they pass because the check held; if it was bypassed and nothing looked, they
# are the only thing that notices.
# ---------------------------------------------------------------------------


def test_the_seeded_supervision_graph_holds_no_cycle(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any], supervision_graph: Any
) -> None:
    """Criterion 1: no cycle in the graph the seed left behind.

    Walked here rather than trusted to the trigger, because the whole subject of
    this criterion is a write path that can turn the trigger off. SPEC §2.1
    defines purview as "own grant union purviews of all assignments transitively
    reporting to it", and over a loop that union has no fixed point: E9's roll-up
    does not return a wrong answer, it does not return.

    **That quotation is a transcription**, verbatim but for one character: §2.1
    writes the union as the set symbol, which ruff reads as a confusable, so it is
    spelled out here. Every other §2.1 quotation in this file is transcribed the
    same way and for the same reason — the wording is the spec's, not a paraphrase
    of it.

    **The edge count is asserted first**, and it is not ceremony: a graph with no
    edges at all is acyclic, and so is one where every `reports_to` was quietly
    dropped. E0-17 seeds chairs under an assistant dean under a dean, so there are
    edges to walk or the shape criteria below have already failed.
    """
    seeded(seeded_demo)
    graph = supervision_graph
    parent_column = graph.reports_to_column
    key_column = graph.assignment_key

    with reading(demo_database, metadata_tables) as rows:
        assignments = {row[key_column]: row[parent_column] for row in rows_of(rows, ASSIGNMENTS)}

    edges = {child: parent for child, parent in assignments.items() if parent is not None}
    assert edges, (
        f"The seed wrote {len(assignments)} assignments and not one `{parent_column}` edge, so "
        "there is no supervision graph here to be acyclic. E0-17's people graph is 'an assistant "
        "dean between chairs and a dean', which is two edges at the least, and a graph with no "
        "edges passes every cycle check ever written."
    )

    for start in edges:
        seen = [start]
        current = edges.get(start)
        while current is not None:
            if current in seen:
                loop = [*seen[seen.index(current) :], current]
                pytest.fail(
                    f"The seeded supervision graph holds a cycle: {loop}. E0-17's first "
                    "criterion: 'If the loader disables triggers, it re-checks what they would "
                    "have refused — no cycle… and fails loudly if the seeded graph violates "
                    "either.' ADR 0027 measured the path that gets here: `SET "
                    "session_replication_role = replica` disables E0-09's trigger entirely, with "
                    "no `ALTER TABLE` and no ownership check, and a two-row cycle stores cleanly "
                    "under it. Nothing else in this schema will ever look."
                )
            seen.append(current)
            current = edges.get(current)


def test_no_seeded_supervision_edge_touches_a_care_assignment(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any], supervision_graph: Any
) -> None:
    """Criterion 1's other half: no edge into or out of a `CARE` assignment.

    SPEC §2.1 puts Care outside the supervision graph entirely, and §6.2 spends a
    paragraph on why: an edge into a Care assignment hands the one role that can
    re-identify a student a reporting purview, and an edge out of one puts Care
    inside somebody's oversight. E0-09 states both directions and enforces them in
    the same trigger the loader can switch off.

    **This one cannot require a Care assignment to exist**, and says so rather than
    implying more: E0-17's scope does not ask for one, so a seed with no Care row
    satisfies this vacuously. What makes that acceptable is that the count is
    reported in the failure and that the cycle test above is non-vacuous on the
    same rows — if the graph is empty, that test is what says so.
    """
    seeded(seeded_demo)
    graph = supervision_graph
    parent_column = graph.reports_to_column
    key_column = graph.assignment_key
    care = enum_text(graph.role_value("CARE"))

    with reading(demo_database, metadata_tables) as rows:
        assignments = rows_of(rows, ASSIGNMENTS)

    care_keys = {
        row[key_column] for row in assignments if enum_text(row[graph.role_column]) == care
    }
    outbound = [
        row[key_column]
        for row in assignments
        if enum_text(row[graph.role_column]) == care and row[parent_column] is not None
    ]
    inbound = [
        row[key_column]
        for row in assignments
        if row[parent_column] is not None and row[parent_column] in care_keys
    ]

    assert not outbound and not inbound, (
        f"The seeded graph holds {len(outbound)} edges out of a `CARE` assignment ({outbound}) "
        f"and {len(inbound)} edges into one ({inbound}); it holds {len(care_keys)} Care "
        "assignments in total. SPEC §2.1 keeps Care out of the supervision graph in both "
        "directions and §6.2 says why — Care's 'sole power is the threat queue, kept isolated so "
        "safety re-identification never rides alongside routine oversight access'. E0-09's "
        "trigger refuses these rows; ADR 0027 records that a session running as this script's "
        "identity can turn that trigger off without touching the schema, which is what E0-17's "
        "first criterion is about."
    )


# ---------------------------------------------------------------------------
# Criterion 2 — the mock platform's registration.
# ---------------------------------------------------------------------------


def mock_platform_addresses(base_compose: dict[str, Any], service_name: str) -> set[str]:
    """Every address the base Compose file gives the mock platform *for itself*.

    Read out of the file rather than written here, for the reason
    `postgres_container` reads the Postgres image out of it: the issuer a tool
    would trust is the one the running service signs with, and a constant in a
    test is a second copy of it.

    **Only the addresses whose host is that service.** The same environment block
    also carries the *tool's* login and launch URLs, which name `api` and have
    nothing to do with identifying the platform — matching on those would read a
    row naming this application as a mock registration.
    """
    services = base_compose.get("services") or {}
    service = services.get(service_name) or {}
    environment = service.get("environment") if isinstance(service, dict) else None
    values: set[str] = set()
    if isinstance(environment, dict):
        values |= {str(value).strip().lower() for value in environment.values() if value}
    elif isinstance(environment, list):
        values |= {
            str(entry).partition("=")[2].strip().lower()
            for entry in environment
            if "=" in str(entry)
        }
    host = f"//{service_name.lower()}"
    return {value for value in values if value.startswith("http") and host in value}


def names_the_mock_platform(value: Any, addresses: set[str], service_name: str) -> bool:
    """Whether one stored value identifies the in-repo mock platform.

    Two ways, because a registration could name the platform by the issuer it
    signs with or by the Compose service it runs as. The second is the looser and
    is anchored on the service name rather than on the word "mock" alone, so an
    institution running a real platform at `lms.example.edu` is not caught by it.
    Both halves of that claim are run in the test below this one.
    """
    if not isinstance(value, str):
        return False
    lowered = value.strip().lower()
    if not lowered:
        return False
    if any(address.rstrip("/") in lowered for address in addresses):
        return True
    return service_name.lower() in lowered


def test_the_mock_platform_matcher_catches_the_compose_issuer_and_allows_a_real_one(
    base_compose: dict[str, Any], mock_lms_service: str
) -> None:
    """The matcher below is run against what it must catch and what it must allow.

    A pattern searched against text is a test in its own right and looks like
    none: `docs/MISTAKES.md` entry 3's third case is a pattern that matched
    nothing and turned the test using it green against the exact thing it existed
    to catch. So the samples are here, beside it, and the must-allow half includes
    the near miss that matters — a real platform whose host begins `lms.`, which
    a matcher anchored on the word "lms" rather than on the service name would
    wrongly catch and would then report a compliant seed as a violation.
    """
    addresses = mock_platform_addresses(base_compose, mock_lms_service)
    assert addresses, (
        f"`docker-compose.yml` configures the `{mock_lms_service}` service with no `http` address, "
        "so this matcher has nothing to recognise the mock platform by and every assertion built "
        "on it would pass vacuously. ADR 0037 puts those addresses in the Compose file as "
        "literals, and ADR 0038 makes the issuer the thing a tool trusts."
    )

    must_catch = (
        *addresses,
        *(f"{address}/" for address in addresses),
        f"http://{mock_lms_service}:8000/jwks",
    )
    missed = [
        value
        for value in must_catch
        if not names_the_mock_platform(value, addresses, mock_lms_service)
    ]
    assert not missed, (
        f"These name the in-repo mock platform and the matcher did not recognise them: {missed}. "
        "Every assertion about a seeded registration is only as good as this."
    )

    must_allow = (
        "https://canvas.example.edu",
        "https://lms.example.edu",
        "https://moodle.university.example.com/lti",
        "https://blackboard.example.org",
    )
    caught = [
        value for value in must_allow if names_the_mock_platform(value, addresses, mock_lms_service)
    ]
    assert not caught, (
        f"The matcher reads these as the in-repo mock platform: {caught}. They are the platforms a "
        "real deployment registers, so a matcher this wide would report a compliant seed as a "
        "violation — and the next person would widen the assertion rather than the matcher."
    )


def test_the_seed_registers_no_mock_platform_unless_a_deployed_run_is_refused(
    seeded_demo: Any,
    demo_database: Any,
    metadata_tables: dict[str, Any],
    base_compose: dict[str, Any],
    mock_lms_service: str,
) -> None:
    """Criterion 2, both branches, with the branch that was taken named in the failure.

    E0-17 permits either answer and asks for evidence of whichever one is given:
    "Any `lti_platform` row naming the mock LMS is unreachable from a deployed
    environment… If this script seeds no registration, say so and leave ADR 0038
    alone."

    So this looks first, and then asserts the thing the answer obliges. **No
    registration** — nothing more to prove, and the test says which rows it read
    so that a database with no `lti_platform` table at all cannot pass as one.
    **A registration** — then running the same script with the deployment named as
    production has to be refused, because ADR 0038's whole argument that the mock
    is safe rests on "a tool only trusts it if a registration says so… A production
    Pulse with no such row rejects every launch it signs, and that is the boundary
    that actually matters." A seed that writes the row on a path a deployment also
    runs closes that boundary in the wrong direction.

    **This test's `ENVIRONMENT=production` branch does not run, and must not be
    read as covering the guard.** The seed registers a fictional platform rather
    than the mock (ADR 0065), so the condition above is false and the run below
    never happens — which is exactly how a guard ships with nothing asserting it.
    The guard itself is asserted unconditionally in the section further down;
    ADR 0063's own consequences named this gap before there was a test for it.
    """
    seeded(seeded_demo)
    addresses = mock_platform_addresses(base_compose, mock_lms_service)
    platforms = require_table(metadata_tables, PLATFORMS)

    with reading(demo_database, metadata_tables) as rows:
        read_the_table = PLATFORMS in rows
        registrations = rows_of(rows, PLATFORMS)

    assert read_the_table, (
        f"`{PLATFORMS}` is declared on `Base.metadata` and this test read no rows from it at all, "
        "so 'the seed registered no mock platform' would be a statement about a query that never "
        "ran. Every table here is read by its single uuid primary key (ADR 0016); a table without "
        "one is skipped, which is the only way to get here."
    )

    naming_the_mock = [
        row
        for row in registrations
        if any(
            names_the_mock_platform(value, addresses, mock_lms_service)
            for column, value in row.items()
            if column in platforms.c
        )
    ]

    if not naming_the_mock:
        return

    refused = demo_database.run(**{DEPLOYED_ENVIRONMENT_VARIABLE: DEPLOYED_ENVIRONMENT_VALUE})
    assert not refused.succeeded, (
        f"The seed registers the mock platform — {len(naming_the_mock)} of {len(registrations)} "
        f"`{PLATFORMS}` rows name it — and it ran to completion with "
        f"`{DEPLOYED_ENVIRONMENT_VARIABLE}={DEPLOYED_ENVIRONMENT_VALUE}` set.\n"
        f"{refused.report()}\n"
        "E0-17: 'Seeding an `lti_platform` row for the mock LMS is what would make ADR 0038 "
        "wrong.' That record argues the mock is safe in the base Compose file because it holds "
        "nothing, reaches nothing, publishes no port outside the development override, and is "
        "trusted only by a row in `lti_platform` — and because no such row exists anywhere in "
        "this repository. The mock authenticates nobody: it signs a launch as either seeded user "
        "for whoever can reach the container. If this script is to write that row, something has "
        "to stop a deployment running the path that writes it, and ADR 0038 has to be amended to "
        "say what."
    )


# ---------------------------------------------------------------------------
# Criterion 5 — every seeded section code parses, and lands inside its term.
# ---------------------------------------------------------------------------


def test_every_seeded_section_code_derives_the_calendar_the_section_stores(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any], section_codes: Any
) -> None:
    """Criterion 5, first half: every code parses through E0-07 and agrees with the row.

    Two things at once, and they are one behaviour: the derivation has to accept
    the code, and what it derives has to be what the section stores. A seed that
    wrote its own arithmetic into `length_weeks`, `start_date` and `end_date`
    would satisfy "parses" while shipping a demo institution whose sections
    disagree with the term's own letter map — and E0-07's scope says there is
    "exactly one path that sets them".

    The derivation is called against the *seeded* database, so it reads the
    `start_letter_map` rows this script wrote rather than a fixture's.
    """
    seeded(seeded_demo)
    sections_table = require_table(metadata_tables, "section")
    require_columns(
        sections_table,
        (SECTION_CODE_COLUMN, DERIVED_LENGTH, DERIVED_START, DERIVED_END, DERIVED_MODALITY),
    )
    term_column = one_foreign_key_column(sections_table, "term")
    term_key = single_primary_key(require_table(metadata_tables, "term"))

    with reading(demo_database, metadata_tables) as rows:
        sections = rows_of(rows, "section")

    assert sections, (
        "The seed wrote no sections, so there is no code here to parse. E0-17's scope asks for "
        "'sections spanning several start letters, both modalities, and at least three different "
        "lengths', and every assertion in this section is satisfied by a database with none."
    )

    wrong: dict[str, Any] = {}
    with demo_session(demo_database) as session:
        term_model = model_for("term")
        for section in sections:
            code = section[SECTION_CODE_COLUMN]
            term = session.get(term_model, section[term_column])
            if term is None:
                wrong[code] = "its term could not be loaded through its mapped class"
                continue
            try:
                derived = section_codes.call(
                    section_codes.derive,
                    session=session,
                    code=code,
                    term=term,
                    term_id=section[term_column],
                )
            except Exception as refused:
                # Every exception, not a chosen few: E0-07's definition of done
                # asks that nothing "escapes as a 500", so a code the service
                # cannot parse and one it parses into a `KeyError` are the same
                # finding here — a seeded section nobody can load.
                wrong[code] = f"deriving it raised {refused!r}"
                continue
            found = (
                int(section_codes.part(derived, (DERIVED_LENGTH,), "derived length in weeks")),
                section_codes.part(derived, (DERIVED_START,), "derived start date"),
                section_codes.part(derived, (DERIVED_END,), "derived end date"),
                enum_text(section_codes.part(derived, (DERIVED_MODALITY,), "derived modality")),
            )
            stored = (
                int(section[DERIVED_LENGTH]),
                section[DERIVED_START],
                section[DERIVED_END],
                enum_text(section[DERIVED_MODALITY]),
            )
            if found != stored:
                wrong[code] = f"derived {found} and the row stores {stored}"

    assert not wrong, (
        f"These seeded section codes did not derive the calendar their row holds: {wrong}. E0-17: "
        "'Every seeded section code parses through E0-07 and yields dates inside its term.' A "
        "code the parser rejects is a section every later epic's fixtures inherit and nobody can "
        "load; a code that parses to something other than what the row stores is worse, because "
        "the row looks right on every screen and the two answers only meet when E4 plots a week "
        f"axis. The term key column is `{term_key}` and the section's link to it is "
        f"`{term_column}`."
    )


def test_every_seeded_section_runs_inside_the_term_it_belongs_to(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 5, second half: the dates land inside the term.

    Its own test because it fails for a different reason and reads differently. A
    section that starts before its term or ends after it is exactly what E0-07's
    fifth criterion refuses at derivation time, so a seeded one means the seed
    wrote the columns itself — and §2.2's own `Q` cohort ends on the term's last
    day, so the boundary here has no slack to hide in.
    """
    seeded(seeded_demo)
    term_table = require_table(metadata_tables, "term")
    term_start = require_column(term_table, TERM_START_COLUMNS)
    term_end = require_column(term_table, TERM_END_COLUMNS)
    section_table = require_table(metadata_tables, "section")
    require_columns(section_table, (SECTION_CODE_COLUMN, DERIVED_START, DERIVED_END))
    term_column = one_foreign_key_column(section_table, "term")

    with reading(demo_database, metadata_tables) as rows:
        sections = rows_of(rows, "section")
        terms = rows.get("term", {})

    assert sections, "The seed wrote no sections, so there is nothing here to be inside a term."

    outside: dict[str, Any] = {}
    for section in sections:
        term = terms.get(section[term_column])
        if term is None:
            outside[section[SECTION_CODE_COLUMN]] = "belongs to no term this database holds"
            continue
        if section[DERIVED_START] < term[term_start] or section[DERIVED_END] > term[term_end]:
            outside[section[SECTION_CODE_COLUMN]] = (
                f"runs {section[DERIVED_START]} to {section[DERIVED_END]} in a term running "
                f"{term[term_start]} to {term[term_end]}"
            )

    assert not outside, (
        f"These seeded sections run outside their own term: {outside}. E0-17's fifth criterion, "
        "and E0-07's own: 'a code whose section would end after the term is rejected'. A section "
        "that runs past its term has reporting weeks the term calendar has no week rows for, and "
        "one that starts before it has a course week that maps to no term week — §2.2's two axes "
        "stop lining up, silently, in the demo data every later epic builds against."
    )


def test_the_seeded_fall_2026_term_carries_the_start_letter_map_the_spec_seeds(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any]
) -> None:
    """Scope: "a Fall 2026 term with the §2.2 start-letter map seeded as data".

    §2.2 gives the map by name — "12-week U/R/Q starting 8/17, 9/7, 9/28; 6-week
    E/F/H; 8-week X/Y/Z; 10-week S/T; 15-week V/D; 16-week K; 3-week sections
    numbered 2-7" — so the letters and their lengths are the spec's rather than
    this file's, and so are the three start dates.

    The term is found by its start date, which §2.2 fixes at 8/17/2026 through the
    `U` cohort running the full twelve weeks from the term's first day. A seed with
    no term starting there fails here rather than silently asserting nothing.
    """
    seeded(seeded_demo)
    term_table = require_table(metadata_tables, "term")
    term_start = require_column(term_table, TERM_START_COLUMNS)
    term_key = single_primary_key(term_table)
    letters_table = require_table(metadata_tables, "start_letter_map")
    letter_length = require_column(letters_table, LETTER_LENGTH_COLUMNS)
    letter_start = require_column(letters_table, LETTER_START_COLUMNS)
    letter_term = one_foreign_key_column(letters_table, "term")

    with reading(demo_database, metadata_tables) as rows:
        all_terms = rows_of(rows, "term")
        terms = [row for row in all_terms if row[term_start] == FALL_2026_START]
        letters = rows_of(rows, "start_letter_map")

    assert len(terms) == 1, (
        f"{len(terms)} seeded terms start on {FALL_2026_START}; the seeded terms start on "
        f"{sorted(str(row[term_start]) for row in all_terms)}. SPEC §2.2's Fall 2026 reference "
        "calendar starts there — its `U` cohort runs twelve weeks from the term's first day — and "
        "E0-17's scope seeds that term by name. Two terms sharing that start date would make the "
        "map below ambiguous."
    )
    seeded_map = {
        row[LETTER_COLUMN]: row for row in letters if row[letter_term] == terms[0][term_key]
    }

    missing = sorted(set(FALL_2026_MAP_LENGTHS) - set(seeded_map))
    assert not missing, (
        f"The Fall 2026 map is missing these start positions: {missing}. It holds "
        f"{sorted(seeded_map)}. SPEC §2.2 seeds all twenty by name, and §6.3 makes the map "
        "admin-configured data rather than code — so a letter absent here is a letter no section "
        "in the demo institution can use, and E11's editor has nothing to show for it."
    )
    wrong_length = {
        letter: (seeded_map[letter][letter_length], length)
        for letter, length in FALL_2026_MAP_LENGTHS.items()
        if seeded_map[letter][letter_length] != length
    }
    assert not wrong_length, (
        f"These start positions carry a length §2.2 does not give them (seeded, documented): "
        f"{wrong_length}. §5.1 compares a section only against others of the same length and "
        "level, so a cohort seeded at the wrong length is benchmarked against a population it is "
        "not in."
    )
    wrong_start = {
        letter: (seeded_map[letter][letter_start], start)
        for letter, start in DOCUMENTED_START_DATES.items()
        if seeded_map[letter][letter_start] != start
    }
    assert not wrong_start, (
        f"These start positions begin on a date §2.2 does not document (seeded, documented): "
        f"{wrong_start}. Those three are the only dates the spec spells for this map, and they "
        "are what ties the seeded calendar to a real one."
    )


def test_the_seeded_sections_span_both_modalities(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any]
) -> None:
    """Scope: sections in "both modalities".

    §2.2: "`WW` online, `FF` face-to-face." Read off the section code's suffix
    rather than off the derived column, because the code is what the LMS supplies
    and the column is derived from it — and asserting the derived column here
    would be a second copy of the derivation test above.
    """
    seeded(seeded_demo)
    require_columns(require_table(metadata_tables, "section"), (SECTION_CODE_COLUMN,))
    with reading(demo_database, metadata_tables) as rows:
        codes = [str(row[SECTION_CODE_COLUMN]) for row in rows_of(rows, "section")]

    found = {
        suffix
        for suffix in MODALITY_SUFFIXES
        if any(code.upper().endswith(suffix) for code in codes)
    }
    assert found == set(MODALITY_SUFFIXES), (
        f"The seeded sections use {sorted(found) or 'no modality suffix at all'} out of "
        f"{list(MODALITY_SUFFIXES)}; their codes are {sorted(codes)}. E0-17's scope asks for both, "
        "and a demo institution with one modality is one where nothing exercises the other — "
        "including E4's report header and E13's load fixtures."
    )


def test_the_seeded_sections_span_several_start_letters_and_three_lengths(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any]
) -> None:
    """Scope: sections "spanning several start letters… and at least three different lengths".

    The two go together and are asserted together because one implies the other in
    the direction that matters: three lengths need three letters, and three letters
    that all map to the same length are not the awkward case the scope is asking
    for. §2.2's whole reason for the term axis is cohorts that "began five weeks
    apart", and a demo institution with one cohort cannot show it.
    """
    seeded(seeded_demo)
    require_columns(
        require_table(metadata_tables, "section"), (SECTION_CODE_COLUMN, DERIVED_LENGTH)
    )
    with reading(demo_database, metadata_tables) as rows:
        sections = rows_of(rows, "section")

    letters = {str(row[SECTION_CODE_COLUMN])[:1] for row in sections}
    lengths = {int(row[DERIVED_LENGTH]) for row in sections}
    assert len(lengths) >= DISTINCT_SECTION_LENGTHS and len(letters) >= DISTINCT_SECTION_LENGTHS, (
        f"The seeded sections use {sorted(letters)} as start positions and run {sorted(lengths)} "
        f"weeks. E0-17's scope asks for at least {DISTINCT_SECTION_LENGTHS} different lengths "
        "across several start letters. SPEC §2.2 plots aggregate pages on the term axis 'with one "
        "line per start cohort and a cohort selector', and a seed with one cohort leaves that "
        "screen with nothing to select between."
    )


# ---------------------------------------------------------------------------
# The demo institution's shape — E0-17's scope, which is what makes it worth
# developing against.
# ---------------------------------------------------------------------------


def test_the_demo_institution_holds_more_than_one_college(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any]
) -> None:
    """Scope: "at least two colleges".

    A single-college institution makes a dean's purview and the VP's the same set,
    so E9's roll-up cannot tell a correct answer from one that ignores the scope
    entirely.
    """
    seeded(seeded_demo)
    with reading(demo_database, metadata_tables) as rows:
        colleges = rows_of(rows, "college")

    assert len(colleges) >= 2, (
        f"The seed wrote {len(colleges)} colleges. E0-17's scope: 'at least two colleges, several "
        "departments'. With one, a dean's purview and the VP's are the same rows, and every "
        "scoping bug in E9 looks like a correct answer."
    )


def test_a_seeded_department_groups_more_than_one_prefix(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any]
) -> None:
    """Scope: "a department grouping more than one prefix (the Math / MATH-STAT-MIS case)".

    SPEC §2.1 puts it in the hierarchy itself — "Department (groups one or more
    prefixes: Math may hold MATH, STAT, MIS)" — and it is the case that separates a
    chair's purview from a prefix's. A seed where every department holds exactly
    one prefix lets an implementation conflate the two levels and pass.
    """
    seeded(seeded_demo)
    prefix_table = require_table(metadata_tables, "prefix")
    department_column = one_foreign_key_column(prefix_table, "department")

    with reading(demo_database, metadata_tables) as rows:
        prefixes = rows_of(rows, "prefix")

    grouped: dict[Any, int] = {}
    for prefix in prefixes:
        grouped[prefix[department_column]] = grouped.get(prefix[department_column], 0) + 1

    assert grouped and max(grouped.values()) > 1, (
        f"No seeded department holds more than one prefix ({len(prefixes)} prefixes across "
        f"{len(grouped)} departments). SPEC §2.1: 'Department (groups one or more prefixes: Math "
        "may hold MATH, STAT, MIS)', and E0-17 names that case in its scope. Where every "
        "department has exactly one prefix, a roll-up that aggregates by prefix and one that "
        "aggregates by department agree on every row, and the first is wrong."
    )


def test_the_seeded_courses_cover_every_level_band(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any]
) -> None:
    """Scope: "courses across all five levels".

    §8 derives `level` from the course number and bands it DEV/UG/UGGR/GR/DR. All
    five matter downstream: §5.1 compares a section only against others of the
    same length *and level*, so a level with no seeded course is a comparison set
    nobody can build a fixture for.

    The numbers are not asserted here — that is E0-05's own module — but the
    ticket's warning is worth repeating in the failure, because the obvious source
    for demo numbers is `design/` and every number there fails these bands.
    """
    seeded(seeded_demo)
    require_columns(
        require_table(metadata_tables, "course"), (COURSE_LEVEL_COLUMN, COURSE_NUMBER_COLUMN)
    )
    with reading(demo_database, metadata_tables) as rows:
        courses = rows_of(rows, "course")

    levels = {enum_text(row[COURSE_LEVEL_COLUMN]) for row in courses}
    missing = [level for level in COURSE_LEVELS if level not in levels]
    assert not missing, (
        f"The seeded courses cover {sorted(levels)} and not {missing}. E0-17's scope: 'courses "
        "across all five levels'. SPEC §8 bands them by number — `000`-`099` DEV, `100`-`499` UG, "
        "`500`-`599` UGGR, `600`-`799` GR, `8000`-`9999` DR — and the ticket warns that all 27 "
        "distinct course numbers in `design/` fail those bands, every one being four digits below "
        "8000, which is the gap between the two. Pick the seed numbers against §8; do not "
        f"reconcile either side to the other. The numbers seeded so far: "
        f"{sorted(str(row[COURSE_NUMBER_COLUMN]) for row in courses)}."
    )


def test_every_seeded_course_carries_a_title(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any]
) -> None:
    """`course.lms_title` is `NOT NULL`, and a blank string satisfies that.

    E0-17 names the column because a course inserted without one fails at write
    time — so a seed that got this wrong would fail the run above rather than this
    test. What this adds is the half the constraint cannot state: a title that is
    empty or whitespace passes `NOT NULL` and reaches every screen that shows a
    course. E0-15 made the same distinction for the mock platform's seed, in
    `test_mock_lms_seed_data.py`, and E0-21 carries the question of whether the
    column should exist at all.
    """
    seeded(seeded_demo)
    require_columns(
        require_table(metadata_tables, "course"), (COURSE_TITLE_COLUMN, COURSE_NUMBER_COLUMN)
    )
    with reading(demo_database, metadata_tables) as rows:
        courses = rows_of(rows, "course")

    assert courses, "The seed wrote no courses, so there is no title here to be blank."
    untitled = [
        str(row[COURSE_NUMBER_COLUMN])
        for row in courses
        if not str(row.get(COURSE_TITLE_COLUMN) or "").strip()
    ]
    assert not untitled, (
        f"These seeded courses carry no usable title: {untitled}. `course.lms_title` is `NOT "
        "NULL` (E0-05, kept deliberately), which refuses a null and accepts an empty string — and "
        "a course row with a blank title reaches §2.1's course-level page header and E9's "
        "hierarchy nav as an unlabelled line."
    )


# ---------------------------------------------------------------------------
# Criterion 6 — the assistant-dean shape from SPEC §2.1.
# ---------------------------------------------------------------------------


def test_the_seeded_graph_holds_an_assistant_dean_between_chairs_and_a_dean(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any], supervision_graph: Any
) -> None:
    """Criterion 6: §2.1's insertion, as rows.

    §2.1: "some chairs in a college report through an assistant dean (`CHAIR →
    ASSISTANT_DEAN → DEAN`) while others report straight to the dean", and the
    assistant dean is scoped to the "College (same node as the dean — authority
    comes from the supervision graph, not the scope)".

    Four properties, and each one is load-bearing:

      - an assistant dean exists and reports to a dean;
      - it is scoped to the node that dean is scoped to, so that a purview taken
        from the scope alone would be the *dean's* — which is what makes the
        example an argument for computing purview from the graph;
      - at least one chair reports to it;
      - at least one chair reports to that same dean directly, because a college
        where every chair reports through the assistant dean is a chain rather
        than the insertion §2.1 describes, and a roll-up that ignores the
        assistant dean entirely gets the same answer over it.

    **Computing the purview is E9's**, and this asserts none of it. What it
    asserts is that the rows E9 will compute over are there.
    """
    seeded(seeded_demo)
    graph = supervision_graph
    key_column = graph.assignment_key
    parent_column = graph.reports_to_column

    with reading(demo_database, metadata_tables) as rows:
        assistant_deans = assignments_by_role(graph, rows, "ASSISTANT_DEAN")
        deans = {row[key_column]: row for row in assignments_by_role(graph, rows, "DEAN")}
        chairs = assignments_by_role(graph, rows, "CHAIR")

    assert assistant_deans, (
        "The seed wrote no `ASSISTANT_DEAN` assignment. E0-17's scope asks for 'an assistant dean "
        "between chairs and a dean', and §2.1 calls it the worked example for why purview comes "
        "from the supervision graph rather than from containment: 'own led courses union every "
        f"supervised chair's department — a set no single containment node holds'. There are "
        f"{len(deans)} deans and {len(chairs)} chairs."
    )

    complaints: list[str] = []
    for assistant in assistant_deans:
        dean = deans.get(assistant[parent_column])
        if dean is None:
            complaints.append(
                f"assistant dean {assistant[key_column]} reports to "
                f"{assistant[parent_column]!r}, which is no seeded `DEAN` assignment"
            )
            continue
        supervised = [chair for chair in chairs if chair[parent_column] == assistant[key_column]]
        direct = [chair for chair in chairs if chair[parent_column] == dean[key_column]]
        assistant_college = scope_node(graph, assistant, "college")
        dean_college = scope_node(graph, dean, "college")
        if not supervised:
            complaints.append(f"no chair reports to assistant dean {assistant[key_column]}")
        elif not direct:
            complaints.append(
                f"every chair under dean {dean[key_column]} reports through the assistant dean; "
                "none reports to the dean directly"
            )
        elif assistant_college is None or assistant_college != dean_college:
            complaints.append(
                f"assistant dean {assistant[key_column]} is scoped to {assistant_college!r} and "
                f"its dean to {dean_college!r}"
            )
        else:
            return

    pytest.fail(
        "No seeded assistant dean sits between chairs and a dean the way SPEC §2.1 describes:\n"
        + "\n".join(f"  - {complaint}" for complaint in complaints)
        + "\n\nE0-17 criterion 6: 'The seeded graph contains the assistant-dean shape from §2.1, "
        "and a test asserts its structure — the purview it implies is E9's to compute, but the "
        "shape must be present now.' §2.1: 'some chairs in a college report through an assistant "
        "dean while others report straight to the dean', and the assistant dean sits on the same "
        "node as the dean because 'authority comes from the supervision graph, not the scope'. A "
        "seed without the second kind of chair is a straight chain, and a roll-up that ignored "
        "the assistant dean would produce the same numbers over it."
    )


def test_the_assistant_deans_led_course_sits_outside_the_departments_they_supervise(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any], supervision_graph: Any
) -> None:
    """Criterion 6's other half: the purview §2.1 says no containment node holds.

    §2.1's worked example is not "an extra level in the chain". It is a purview:
    "own led courses union every supervised chair's department — a set no single
    containment node holds" — a transcription with §2.1's set symbol spelled out,
    as everywhere else in this file. That sentence is only true of seeded rows
    where the assistant dean *leads a course* and that course sits outside the
    departments of the chairs they supervise. Seed it the other way and the union
    collapses into one department subtree, E9's development data stops
    distinguishing a correct roll-up from a containment walk, and nothing says so.

    Its own test rather than a fifth clause above, because it fails for a
    different reason: the shape above can be right while this is missing, and the
    fix is a lead-faculty mapping rather than an edge.
    """
    seeded(seeded_demo)
    graph = supervision_graph
    key_column = graph.assignment_key
    parent_column = graph.reports_to_column
    person_column = graph.person_column

    with reading(demo_database, metadata_tables) as rows:
        assistant_deans = assignments_by_role(graph, rows, "ASSISTANT_DEAN")
        chairs = assignments_by_role(graph, rows, "CHAIR")
        leads = led_courses(metadata_tables, rows)
        departments_of = {
            course_id: department_of_course(metadata_tables, rows, course_id)
            for course_id in rows.get("course", {})
        }

    assert assistant_deans, (
        "The seed wrote no `ASSISTANT_DEAN` assignment, which the test above reports as the "
        "missing shape; this one needs it before it can ask what that person leads."
    )

    complaints: list[str] = []
    for assistant in assistant_deans:
        own_courses = leads.get(assistant[person_column], set())
        supervised = [chair for chair in chairs if chair[parent_column] == assistant[key_column]]
        supervised_departments = {scope_node(graph, chair, "department") for chair in supervised}
        if not own_courses:
            complaints.append(
                f"assistant dean {assistant[key_column]} leads no course "
                f"(`{MAPPINGS}` has no row for person {assistant[person_column]})"
            )
            continue
        outside = {
            course
            for course in own_courses
            if departments_of.get(course) not in supervised_departments
        }
        if not outside:
            complaints.append(
                f"assistant dean {assistant[key_column]} leads {sorted(map(str, own_courses))}, "
                "all of them inside the departments of the chairs they supervise"
            )
            continue
        return

    pytest.fail(
        "No seeded assistant dean has the purview SPEC §2.1 uses as its worked example:\n"
        + "\n".join(f"  - {complaint}" for complaint in complaints)
        + "\n\n§2.1: 'The assistant dean is the worked example for why purview comes from the "
        "graph: own led courses union every supervised chair's department — a set no single "
        "containment node holds.' Where the led course sits inside a supervised chair's "
        "department, that union *is* held by a single node, and E9 can pass its own tests with a "
        "containment walk. The shape is cheap to seed and impossible to notice missing."
    )


# ---------------------------------------------------------------------------
# Criteria 7 and 8 — sibling leads, and the course that falls to the chair.
# ---------------------------------------------------------------------------


def test_two_sibling_leads_lead_courses_in_one_prefix(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 7: "two sibling leads exist in one prefix with disjoint course sets".

    **Disjointness is asserted and is not the load-bearing half**, which is worth
    saying rather than leaving for somebody to discover: E0-09 enforces one lead
    per course by constraint, so two leads' course sets cannot overlap in a
    database this schema accepts, and an assertion about it passes over any seed at
    all. What the criterion actually asks for is the *existence* of the pair —
    two people leading different courses under one prefix — because that is what
    makes SPEC §4.1 invariant 2 visible in development: "a Lead Faculty assignment
    never grants sibling leads' courses". With one lead per prefix, a purview that
    leaked the whole prefix would look right on every screen.
    """
    seeded(seeded_demo)
    course_table = require_table(metadata_tables, "course")
    prefix_column = one_foreign_key_column(course_table, "prefix")

    with reading(demo_database, metadata_tables) as rows:
        leads = led_courses(metadata_tables, rows)
        courses = rows.get("course", {})

    by_prefix: dict[Any, dict[Any, set[Any]]] = {}
    for person, owned in leads.items():
        for course_id in owned:
            course = courses.get(course_id)
            if course is None:
                continue
            by_prefix.setdefault(course[prefix_column], {}).setdefault(person, set()).add(course_id)

    siblings = {prefix: holders for prefix, holders in by_prefix.items() if len(holders) >= 2}
    leads_per_prefix = sorted(len(holders) for holders in by_prefix.values())
    assert siblings, (
        f"No seeded prefix has two leads. The mapping holds {len(leads)} people across "
        f"{len(by_prefix)} prefixes, with {leads_per_prefix} leads in each. E0-17's scope: "
        "'two sibling leads in the same prefix so isolation is visible in development, not just "
        "in tests'. SPEC §4.1 invariant 2 is that a lead never sees a sibling lead's course, and "
        "with one lead per prefix a purview that hands over the whole prefix produces exactly the "
        "right answer."
    )

    prefix, holders = next(iter(siblings.items()))
    pair = sorted(holders, key=str)[:2]
    first, second = holders[pair[0]], holders[pair[1]]
    assert first and second, (
        f"Two people are mapped as leads under prefix {prefix} and one of them leads no course: "
        f"{first!r} and {second!r}. An empty course set is disjoint from anything, which is what "
        "makes it worth asserting separately (`docs/MISTAKES.md` entry 3)."
    )
    assert not (first & second), (
        f"Two leads under prefix {prefix} share the courses {sorted(map(str, first & second))}. "
        "E0-09 makes one lead per course a database constraint, so this is either that constraint "
        "gone or a mapping table this test has misread — both worth seeing, neither expected."
    )


def test_at_least_one_seeded_course_has_no_lead_faculty_mapping(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 8: "At least one course has no lead-faculty mapping."

    SPEC §2.1: "A course with no mapping falls to its department chair", and E9's
    dry-run diff shows it in as many words — "BIOL 441 unmapped, falls to chair".
    That path has no fixture until a seeded course exercises it.

    **The control is a mapped course**, and it is not ceremony: "some course is
    unmapped" is true of a seed that writes no mappings at all, which would also
    satisfy every other assertion about mappings by being empty.
    """
    seeded(seeded_demo)
    mappings = require_table(metadata_tables, MAPPINGS)
    course_column = one_foreign_key_column(mappings, "course")

    with reading(demo_database, metadata_tables) as rows:
        courses = set(rows.get("course", {}))
        mapped = {row[course_column] for row in rows_of(rows, MAPPINGS)}

    assert mapped, (
        f"The seed wrote no `{MAPPINGS}` rows at all, so every course is unmapped and the "
        "criterion below would be satisfied by a seed with no lead faculty in it. E0-17's scope "
        "asks for the mappings *and* for one course deliberately left out of them."
    )
    unmapped = courses - mapped
    assert unmapped, (
        f"All {len(courses)} seeded courses have a lead-faculty mapping. E0-17: 'Lead-faculty "
        "mappings, including at least one course deliberately left unmapped so the fall-to-chair "
        "path is exercised.' SPEC §2.1 makes that path real — 'a course with no mapping falls to "
        "its department chair' — and with every course mapped, an implementation that never "
        "implements the fallback passes every screen in development."
    )


# ---------------------------------------------------------------------------
# Criterion 9 — the seeded people.
# ---------------------------------------------------------------------------


def test_no_seeded_person_carries_a_routable_email_address(
    seeded_demo: Any, demo_database: Any, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 9, the half a test can check: nothing here could be delivered to.

    E0-17's security review asks that "no seeded person carries a real email
    address or anything resembling real student data". Whether a *name* resembles a
    real person at a real institution is not something this can decide, and the
    module docstring says so rather than asserting a weaker thing under the same
    name. An address is decidable: RFC 2606 and RFC 6761 reserve `.invalid`,
    `.test`, `.example` and the `example.*` second-level names precisely so that a
    fixture cannot reach anybody's mailbox.

    The sweep is over every column in the schema whose name reads as an address,
    not over a named table, because no ticket says which table carries one — and
    the addresses that would matter most sit on `user_identity`, which is the one
    table §4.1 keeps behind a database grant.
    """
    seeded(seeded_demo)
    with reading(demo_database, metadata_tables) as rows:
        addresses: dict[str, list[str]] = {}
        for name, table_rows in rows.items():
            table = metadata_tables.get(name)
            if table is None:
                continue
            columns = [
                column.name
                for column in table.columns
                if any(fragment in column.name.lower() for fragment in EMAIL_COLUMN_FRAGMENTS)
            ]
            for row in table_rows.values():
                for column in columns:
                    value = row.get(column)
                    if isinstance(value, str) and "@" in value:
                        addresses.setdefault(f"{name}.{column}", []).append(value)

    assert addresses, (
        "No seeded row carries anything shaped like an email address, so this assertion has "
        "nothing to be about. E0-17 seeds a people graph and E0-08 gives `user_identity` the "
        "columns §4.1 exists to protect; if the demo institution genuinely stores no address, say "
        "so in the pull request and this test should say so too rather than passing over an "
        "absence."
    )

    routable = {
        where: [
            value
            for value in values
            if not any(
                value.strip().lower().endswith(domain) for domain in UNROUTABLE_EMAIL_DOMAINS
            )
        ]
        for where, values in addresses.items()
    }
    routable = {where: values for where, values in routable.items() if values}
    assert not routable, (
        f"These seeded addresses could be delivered to: {routable}. E0-17's security review: 'no "
        f"seeded person carries a real email address'. Use a domain from "
        f"{list(UNROUTABLE_EMAIL_DOMAINS)} — RFC 2606 and RFC 6761 reserve them for exactly this "
        "— because a demo seed is copied into staging environments, and the address that gets "
        "mail is a real person who never heard of this project."
    )


# ---------------------------------------------------------------------------
# The environment guard — E0-17's security review item, as ADR 0063 implements it:
# "confirm the seed script cannot run against a non-development environment".
#
# **Why this section exists at all.** The implementer shipped the guard and then
# said in ADR 0063's own consequences that nothing in the suite executed it: the
# only run this module made with a deployment name sat behind the mock-platform
# condition, which is false, so the guard was a convention rather than a
# guarantee (`docs/MISTAKES.md` entry 9). What follows is the part the process can
# be asked directly.
#
# **The tests here are one argument and are worth reading in order.** A guard
# that refuses everything passes every refusal case below and is useless, so the
# control that a `development` run is admitted comes first. A guard that runs
# *after* opening a connection would satisfy "the run failed" just as well, so
# every refusal is asked with the database URLs pointed at an address nothing
# answers on: a run that prints the guard's refusal from there cannot have
# connected first, and the second control is what proves this file can tell the
# two failures apart rather than being blind to both.
#
# **What this section can and cannot ask.** Every value it sets is set in the
# *process*, which beats `.env` under ADR 0063's precedence, so these are claims
# about the script wherever it is run. Which of the two sources supplied a value
# is a different question and is not askable from out here — the section after
# this one asks it against the seam instead, and `docs/MISTAKES.md` entry 30 is
# what the attempt to ask it from a subprocess cost.
# ---------------------------------------------------------------------------

# What a failure to reach a database looks like in this project's output,
# whichever shape it takes: an uncaught exception, which is what exit 1 out of a
# Python process means, or a message that names the host it could not reach.
# Asserted absent for every refusal and asserted **present** by
# `test_a_development_run_gets_past_the_guard_and_fails_on_the_address` — because
# a list of fragments that matches nothing would report every run as "no
# connection attempted", including the runs where one was (`docs/MISTAKES.md`
# entry 3, third case).
CONNECTION_FAILURE_FRAGMENTS = ("psycopg", "operationalerror", "traceback", "127.0.0.1")

# The values a deployment might carry, each set **in the process**. ADR 0063 chose
# an equality against `development` rather than a deny-list, so what this list is
# for is the names nobody would have thought to enumerate: the first two are
# `.env.example`'s own conventions, the third is a spelling no record in this
# repository mentions, and the fourth contains the safe name without being it —
# which is the case a guard written as a substring test lets through.
#
# **Every value here is present rather than absent, and that is a repair rather
# than an omission.** A case that removed `ENVIRONMENT` from the child used to sit
# at the end of this list, and it measured the machine instead of the script: the
# child reads `.env` too, so its verdict was decided by whether an untracked file
# exists in the working tree — passing in CI, which never creates one, and failing
# on every checkout that followed README step one. That is `docs/MISTAKES.md`
# entry 30 and `docs/disputes/E0-17-01.md`. Absence is asked of the *resolution*
# instead, in the section below this one, where both sources are arguments. What
# is left here is machine-independent: a value in the process beats `.env` under
# ADR 0063's precedence, whatever the file happens to say.
REFUSED_ENVIRONMENTS = (
    pytest.param(DEPLOYED_ENVIRONMENT_VALUE, id="production"),
    pytest.param("staging", id="staging"),
    pytest.param("prod", id="a-name-no-record-here-enumerates"),
    pytest.param(f"staging-{DEVELOPMENT_ENVIRONMENT}", id="a-name-containing-the-safe-one"),
    pytest.param("", id="set-to-nothing"),
)


def unreachable_overrides(environment_value: str) -> dict[str, str | None]:
    """One `ENVIRONMENT` value, and every database URL pointed at nothing."""
    overrides: dict[str, str | None] = dict.fromkeys(
        DATABASE_URL_VARIABLES, UNREACHABLE_DATABASE_URL
    )
    overrides[DEPLOYED_ENVIRONMENT_VARIABLE] = environment_value
    return overrides


def said_by(run: Any) -> str:
    """Both of a run's streams together, since which one carries a refusal is free."""
    return f"{run.stdout}\n{run.stderr}"


def test_a_development_environment_is_admitted(demo_database: Any) -> None:
    """The control the refusals below are worth nothing without.

    ADR 0063's check is "an equality, not a deny-list", and the failure that
    distinction is about cuts both ways: a guard that enumerated names to refuse
    lets through every name nobody thought of, and a guard that refused *every*
    name would pass all six cases below while making `make seed` impossible.

    So this is the same script, run against the same reachable database as the
    rest of this module, with `ENVIRONMENT` set explicitly rather than inherited —
    and it has to complete. It overlaps
    `test_seeding_a_freshly_migrated_database_completes_without_error` on purpose:
    that test's subject is criterion 3, and the coupling belongs where the
    refusals are, because they are the thing it makes meaningful.

    `seeded_demo` is deliberately not requested. The guard is independent of
    whether an earlier run seeded anything, and a test of the guard should not go
    red because the seed did — though the database it runs against has been seeded
    by the time this executes, so a run that fails here on a *constraint* is the
    idempotency criterion failing rather than the guard, and the message says so.
    """
    admitted = demo_database.run(**{DEPLOYED_ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT})

    assert admitted.succeeded, (
        f"The seed was refused, or failed, with "
        f"`{DEPLOYED_ENVIRONMENT_VARIABLE}={DEVELOPMENT_ENVIRONMENT}` set explicitly.\n"
        f"{admitted.report()}\n"
        "Read the output above before reading this sentence, because there are two failures it "
        "could be. If the script refused, ADR 0063's guard refuses the one value it admits — 'the "
        "one name that is safe is the one this script exists for' — which passes every case in "
        "`test_the_seed_is_refused_wherever_the_environment_is_not_development` while leaving "
        "nobody able to seed a demo institution at all. If it failed on a constraint instead, "
        "this database was already seeded when the run started, so that is the idempotency "
        "criterion and `test_running_the_seed_a_second_time_leaves_the_same_rows` is where it is "
        "asserted."
    )


def test_a_development_run_gets_past_the_guard_and_fails_on_the_address(
    demo_database: Any,
) -> None:
    """The second control: this file can tell a refusal from a connection failure.

    Every refusal below is asked with the database URLs pointed at
    `UNREACHABLE_DATABASE_URL`, and each one asserts that the output carries no
    sign of a connection attempt. That assertion is an absence, and an absence is
    satisfied by a fragment list that matches nothing at all — so this runs the
    one case where a connection attempt certainly happens and requires the list to
    fire on it.

    It is also, in the same breath, ADR 0063's ordering claim from the other side:
    "it checks that **before** it builds a database URL, so a refused run opens no
    connection at all". A `development` run pointed at an address nothing answers
    on has to get past the guard and die on the address; that is the shape a
    refused run must *not* have.
    """
    reached = demo_database.run(**unreachable_overrides(DEVELOPMENT_ENVIRONMENT))
    said = said_by(reached).lower()

    assert not reached.succeeded, (
        f"The seed reported success while every database URL it was given pointed at "
        f"{UNREACHABLE_DATABASE_URL}, where nothing listens.\n{reached.report()}\n"
        "Either it reached a database by some route this test did not redirect — in which case "
        "`DATABASE_URL_VARIABLES` at the top of this file is short of a name and the refusals "
        "below are being asked of a script that can still connect — or it wrote nothing and said "
        "it had."
    )
    found = [fragment for fragment in CONNECTION_FAILURE_FRAGMENTS if fragment in said]
    assert found, (
        f"A `{DEVELOPMENT_ENVIRONMENT}` run against an address nothing answers on failed without "
        f"any of {list(CONNECTION_FAILURE_FRAGMENTS)} appearing in its output.\n"
        f"{reached.report()}\n"
        "That list is what every refusal below uses to say 'no connection was attempted', so a "
        "list matching nothing would make all six of those assertions vacuous. Either the script "
        "now reports a connection failure in words none of these fragments reach — in which case "
        "add one — or it failed before connecting, which would mean the guard refuses "
        f"`{DEVELOPMENT_ENVIRONMENT}` too and the control above should already have said so."
    )


@pytest.mark.parametrize("environment_value", REFUSED_ENVIRONMENTS)
def test_the_seed_is_refused_wherever_the_environment_is_not_development(
    demo_database: Any, environment_value: str
) -> None:
    """E0-17's security review item: the seed cannot run against a non-development environment.

    One case per value, because the values are what the criterion is about. ADR
    0063: "The check is an equality, not a deny-list. The set of names a
    deployment might use is open — `prod`, `production`, `live`, a customer's own
    word, a typo — so a check that enumerated names to refuse would let every name
    nobody thought of through." A test that tried `production` alone would pass
    against exactly the deny-list that record rejects; `staging` and a name no
    record here mentions are what separate the two designs, and a name that
    *contains* `development` separates an equality from a substring test.

    Set to nothing is here because ADR 0063 spells it: "an empty `ENVIRONMENT` is
    refused for the same reason — a value somebody set to nothing is not the one
    name that is safe." **Not set at all is deliberately not here**, and used to
    be: a process started without the variable still reads `.env`, so that case
    measured the working tree rather than the script. It is asked of the
    resolution instead, in the section below, as
    `nothing-sets-it-and-there-is-no-file`.

    **The refusal is the first assertion and the weakest one; what follows is
    what makes it mean something.** The run has to fail. The message has to name
    the variable, the value it found and the value it wants, because a refusal an
    operator cannot act on sends them to the source instead. And no connection may
    have been attempted, which is asked from an address nothing answers on — a
    refusal printed from there happened before the connection, which is ADR 0063's
    ordering claim and the reason the guard is worth anything against a production
    database.

    The exit *status* is deliberately not asserted beyond being non-zero. Nothing
    in the ticket or in ADR 0063 fixes a number, and pinning one here would make
    this file the record of a decision nobody wrote down.
    """
    refused = demo_database.run(**unreachable_overrides(environment_value))
    said = said_by(refused)

    assert not refused.succeeded, (
        f"The seed ran to completion with `{DEPLOYED_ENVIRONMENT_VARIABLE}` set to "
        f"{environment_value!r} in the process.\n"
        f"{refused.report()}\n"
        "E0-17's definition of done asks the security review to 'confirm the seed script cannot "
        "run against a non-development environment', and ADR 0063 is how it does: the script "
        "writes an invented institution, an invented term and invented people into whatever "
        "database `DATABASE_URL` names, connecting as the bootstrap superuser, which bypasses "
        "every grant ADR 0001 puts between a read path and a student's name. The failure this "
        "guard is about is not malice — it is `make seed` typed in a terminal whose `.env` "
        "points at staging."
    )

    assert DEPLOYED_ENVIRONMENT_VARIABLE in said, (
        f"The seed refused, and its output does not name `{DEPLOYED_ENVIRONMENT_VARIABLE}`.\n"
        f"{refused.report()}\n"
        "ADR 0063: 'The message names the variable, the value it found and the value it wants.' A "
        "refusal that says none of those is indistinguishable from the script being broken, and "
        "the person meeting it is a developer whose `.env` is one word wrong."
    )

    if environment_value:
        assert environment_value in said, (
            f"The refusal does not quote the value it found, {environment_value!r}.\n"
            f"{refused.report()}\n"
            "The wording is free and this is not a test of anybody's prose; what the value being "
            "absent costs is the one thing the reader needs, since the whole failure is that "
            f"`{DEPLOYED_ENVIRONMENT_VARIABLE}` says something other than they think it does."
        )

    # Skipped for the one value that contains the safe name: there, the message
    # naming `development` is satisfied by it quoting the offending value back,
    # so the assertion would pass without saying anything (`docs/MISTAKES.md`
    # entry 3). Every other case distinguishes the two.
    if DEVELOPMENT_ENVIRONMENT not in (environment_value or "").lower():
        assert DEVELOPMENT_ENVIRONMENT in said.lower(), (
            f"The refusal does not name `{DEVELOPMENT_ENVIRONMENT}`, the value it wants.\n"
            f"{refused.report()}\n"
            "ADR 0063 makes this an equality against one name, and a refusal that withholds the "
            "name leaves an operator guessing at a value that is not in any error message."
        )

    connected = [fragment for fragment in CONNECTION_FAILURE_FRAGMENTS if fragment in said.lower()]
    assert not connected, (
        f"The refused run's output carries {connected}, so it reached the database layer before "
        f"stopping — it was pointed at {UNREACHABLE_DATABASE_URL}, where nothing listens.\n"
        f"{refused.report()}\n"
        "ADR 0063 puts the check 'before it builds a database URL, so a refused run opens no "
        "connection at all', and that ordering is the guarantee rather than a detail: a guard "
        "that runs after connecting has already opened a superuser session against a production "
        "database, and whether it then writes is a question about the next few lines of the "
        "script rather than about a boundary. `test_a_development_run_gets_past_the_guard_and_"
        "fails_on_the_address` is what proves these fragments are visible when a connection is "
        "genuinely attempted."
    )


# ---------------------------------------------------------------------------
# Which source supplied the permission — ADR 0063's resolution, asked in-process.
#
# **Why these are not subprocess tests, when everything above them is.** The guard
# reads the process environment with `.env` filling in what it does not set, and
# *which of the two supplied a value* is the one question a subprocess cannot be
# asked from here: `seed_environment` in tests/conftest.py lays every documented
# `.env.example` entry into the child, and whether an untracked `.env` sits in the
# working tree decides the rest. A case written that way measures the machine —
# it passed in CI, which never creates that file, and failed on every checkout
# that followed the README. That is `docs/MISTAKES.md` entry 30, and it cost a
# dispute, an arbitration and a decision escalated to Todd
# (`docs/disputes/E0-17-01.md`).
#
# The script now answers it directly: `resolved_configuration(environ,
# dotenv_path)` returns the merge as a value rather than mutating `os.environ`,
# and the guard takes that mapping. So both sources are arguments here, neither is
# inherited, and no test below can be decided by what is or is not on disk in the
# repository — every `.env` they read is one they wrote in `tmp_path`.
#
# **The admitted rows are the ruling and are asserted as such.** Todd chose that
# `.env` may supply the permission; a later change that reinstates the refusal is
# reversing a decision rather than tightening a guard, and the failures below say
# so in those words.
# ---------------------------------------------------------------------------

# The seam ADR 0063 records: "`resolved_configuration(environ, dotenv_path)`
# returns a mapping instead of mutating `os.environ`, and `main` takes both as
# optional arguments defaulting to the real thing." Looked up by name rather than
# discovered, for the reason `AuthzModule` in tests/conftest.py gives: this
# surface was settled in writing before these tests were, so a name that is not
# there is a missing deliverable rather than a rename to accommodate.
RESOLVE_CONFIGURATION = "resolved_configuration"
CHECK_ENVIRONMENT = "check_environment_is_development"

# One `.env` this suite writes, for the cases where the file is meant to say
# nothing about the environment. It carries an unrelated entry rather than being
# empty, so that "the file exists and does not set this" is what is being asked
# rather than "the file is empty" — and so that the three-way message test below
# can hold the file constant while only the process changes.
SILENT_DOTENV = {"DATABASE_URL": UNREACHABLE_DATABASE_URL}

# **Four values the record states, and the rows below are what would catch a
# change to any of them.** ADR 0063's "What the comparison actually is" says the
# guard compares `(raw or "").strip()` against `development`: surrounding
# whitespace of any kind is stripped, internal whitespace is not, there is no
# substring matching, and case is not folded. The padded spellings of the one safe
# name are admitted and nothing else is, which is what makes that a containment
# claim rather than only an admission — and a containment claim with no test under
# it is what `docs/MISTAKES.md` entry 2 is about.
#
# Each row survives a different edit, which is what keeps them from being padding:
# a row that cannot name the change it catches does not earn a place here.
#
#   - a plain `==`, the strip dropped while tidying, fails
#     `the-safe-name-with-surrounding-whitespace` alone;
#   - `.strip(" ")`, the strip narrowed to spaces, fails
#     `the-safe-name-padded-with-a-tab-and-a-newline` alone — and a `.env` line
#     hand-edited into a trailing tab is exactly the case the strip exists for;
#   - `.startswith(...)` in place of the equality fails
#     `the-safe-name-with-something-appended` alone. The other direction —
#     `.endswith(...)`, or a bare `in` — is caught by
#     `a-name-containing-the-safe-one` in the subprocess section above, and the
#     two are separate rows because neither implies the other;
#   - a `.casefold()` added beside the strip fails
#     `the-safe-name-in-the-wrong-case` alone.
#
# **The two halves point in opposite directions on purpose, and only one of them
# is a decision.** ADR 0063 records the strip as deliberate — a trailing space is
# invisible in most editors, and a refusal quoting a padded name reads on screen
# exactly like a refusal quoting the right one, which is the most confusing
# failure this guard could emit — and records case-sensitivity as *inherited*,
# since `==` is case-sensitive and nobody weighed it. It stands on review because
# folding would widen a fail-closed guard, and because a miscased name is
# something a reader can see is wrong. The rule reconciling the two is the
# record's: forgive what the reader cannot see, refuse what they can. If folding
# is ever adopted deliberately, the miscased row changes — and that is a decision
# to record in the ADR rather than a test to repair.
SPACED_DEVELOPMENT = f" {DEVELOPMENT_ENVIRONMENT} "
ODDLY_PADDED_DEVELOPMENT = f"\t{DEVELOPMENT_ENVIRONMENT}\n"
MISCASED_DEVELOPMENT = DEVELOPMENT_ENVIRONMENT.capitalize()
SUFFIXED_DEVELOPMENT = f"{DEVELOPMENT_ENVIRONMENT}1"

# The rows of ADR 0063's resolution table, as `(process environment, .env
# contents)`, plus the comparison rows above. `None` for the file means there is
# no file at all, which is what a deployment looks like; a mapping means this
# suite writes one in `tmp_path`.
REFUSED_CONFIGURATIONS = (
    pytest.param({}, None, id="nothing-sets-it-and-there-is-no-file"),
    pytest.param({}, SILENT_DOTENV, id="the-file-exists-and-sets-no-environment"),
    pytest.param(
        {},
        {DEPLOYED_ENVIRONMENT_VARIABLE: DEPLOYED_ENVIRONMENT_VALUE},
        id="the-file-alone-names-a-deployment",
    ),
    pytest.param(
        {DEPLOYED_ENVIRONMENT_VARIABLE: ""},
        {DEPLOYED_ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT},
        id="the-process-sets-it-to-nothing-over-a-development-file",
    ),
    pytest.param(
        {DEPLOYED_ENVIRONMENT_VARIABLE: "   "},
        {DEPLOYED_ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT},
        id="the-process-sets-it-to-whitespace-over-a-development-file",
    ),
    pytest.param(
        {DEPLOYED_ENVIRONMENT_VARIABLE: DEPLOYED_ENVIRONMENT_VALUE},
        {DEPLOYED_ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT},
        id="the-process-names-a-deployment-over-a-development-file",
    ),
    pytest.param(
        {DEPLOYED_ENVIRONMENT_VARIABLE: MISCASED_DEVELOPMENT},
        SILENT_DOTENV,
        id="the-safe-name-in-the-wrong-case",
    ),
    pytest.param(
        {DEPLOYED_ENVIRONMENT_VARIABLE: SUFFIXED_DEVELOPMENT},
        SILENT_DOTENV,
        id="the-safe-name-with-something-appended",
    ),
)

ADMITTED_CONFIGURATIONS = (
    pytest.param(
        {},
        {DEPLOYED_ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT},
        id="the-file-alone-says-development",
    ),
    pytest.param(
        {DEPLOYED_ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT},
        {DEPLOYED_ENVIRONMENT_VARIABLE: DEPLOYED_ENVIRONMENT_VALUE},
        id="the-process-says-development-over-a-deployment-file",
    ),
    pytest.param(
        {DEPLOYED_ENVIRONMENT_VARIABLE: ODDLY_PADDED_DEVELOPMENT},
        SILENT_DOTENV,
        id="the-safe-name-padded-with-a-tab-and-a-newline",
    ),
    pytest.param(
        {DEPLOYED_ENVIRONMENT_VARIABLE: SPACED_DEVELOPMENT},
        SILENT_DOTENV,
        id="the-safe-name-with-surrounding-whitespace",
    ),
)


def dotenv_at(path: Path, values: Mapping[str, str] | None) -> Path:
    """Write a `.env` holding `values`, or answer a path where no file exists.

    Nothing here interpolates: a `${...}` in one of these would be resolved by
    the script's own reader, which is a behaviour of that reader rather than
    anything these cases are about.
    """
    if values is None:
        return path
    path.write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()), encoding="utf-8"
    )
    return path


def seam(module: Any, name: str) -> Any:
    """One name off the seam ADR 0063 records, or a failure saying it is missing."""
    found = getattr(module, name, None)
    if found is None:
        defined = sorted(attribute for attribute in vars(module) if not attribute.startswith("_"))
        pytest.fail(
            f"`scripts/seed.py` defines no `{name}` — it defines {defined}. ADR 0063 records that "
            "seam by name: '`resolved_configuration(environ, dotenv_path)` returns a mapping "
            "instead of mutating `os.environ`, and `main` takes both as optional arguments'. It is "
            "what makes the question below askable at all; without it the only way to ask is to "
            "start a process in a directory that does or does not hold an untracked file, which "
            "is what `docs/MISTAKES.md` entry 30 is about."
        )
    return found


def resolve(module: Any, environ: Mapping[str, str], dotenv_path: Path) -> Mapping[str, str]:
    """The configuration the script would read from those two sources."""
    return seam(module, RESOLVE_CONFIGURATION)(environ, dotenv_path)


def guard_refusal(module: Any, configuration: Mapping[str, str], capsys: Any) -> tuple[Any, str]:
    """Run the guard over `configuration`; answer what it raised and what it said.

    Both, because ADR 0063 promises a message and does not say where it comes out.
    A guard that raises an error carrying the text and one that prints the text
    and exits are the same refusal to an operator, and pinning either here would
    make this file the record of a decision nobody wrote down. `SystemExit` is
    caught for that reason and `KeyboardInterrupt` is not.
    """
    check = seam(module, CHECK_ENVIRONMENT)
    raised: BaseException | None = None
    try:
        check(configuration)
    except (Exception, SystemExit) as refused:
        raised = refused
    captured = capsys.readouterr()
    return raised, "\n".join(
        part
        for part in (str(raised) if raised is not None else "", captured.out, captured.err)
        if part
    )


@pytest.mark.parametrize(("environ", "dotenv"), REFUSED_CONFIGURATIONS)
def test_the_guard_refuses_these_resolved_configurations(
    seed_module: Any,
    tmp_path: Path,
    capsys: Any,
    environ: dict[str, str],
    dotenv: dict[str, str] | None,
) -> None:
    """ADR 0063's table, row by row, with both sources supplied rather than inherited.

    `nothing-sets-it-and-there-is-no-file` and
    `the-file-exists-and-sets-no-environment` are the cases the subprocess section
    above cannot reach at all, and they are the ones that sent this round back:
    absence in the process is not absence in the resolution.

    `the-file-alone-names-a-deployment` is the mirror of Todd's ruling. If the
    file may grant permission it must equally be able to withhold it, or "reads
    resolved configuration" would mean "reads the file only when it agrees".

    The cases that set a value in the process over a `.env` saying `development`
    assert the precedence in the direction that matters: a developer with a
    development checkout who has exported `ENVIRONMENT=production` for something
    else, and then types `make seed`, must be refused. Whitespace-only is one of
    them because ADR 0063 spells it — "set to anything but `development`, empty
    and whitespace included" — and because it is the value a line holding nothing
    but a space produces.

    `the-safe-name-in-the-wrong-case` and `the-safe-name-with-something-appended`
    are the refusing half of ADR 0063's "What the comparison actually is": the
    guard folds no case and matches no substring, so `Development` and
    `development1` are both refused. The comment on `MISCASED_DEVELOPMENT` above
    says which edit each of those rows survives and why the containment claim
    needs the appended one as well as the two in the subprocess section.
    """
    configuration = resolve(seed_module, environ, dotenv_at(tmp_path / ".env", dotenv))
    found = configuration.get(DEPLOYED_ENVIRONMENT_VARIABLE)
    refused, said = guard_refusal(seed_module, configuration, capsys)

    assert refused is not None, (
        f"The guard admitted a configuration resolving `{DEPLOYED_ENVIRONMENT_VARIABLE}` to "
        f"{found!r}, out of a process holding {environ} and a `.env` holding {dotenv}.\n"
        "ADR 0063: the seed 'refuses to run unless `ENVIRONMENT` is exactly `development`', and "
        "the check is 'an equality, not a deny-list'. What it protects is a superuser connection "
        "to whatever `DATABASE_URL` names, which bypasses every grant ADR 0001 puts between a "
        "read path and a student's name."
    )
    assert DEPLOYED_ENVIRONMENT_VARIABLE in said, (
        f"The refusal names no variable: {said!r}.\n"
        "ADR 0063: 'The message names the variable, the value it found and the value it wants.' "
        "The person meeting this is a developer whose `.env` is one word wrong, and a refusal "
        "they cannot act on sends them to the source."
    )
    if found and found.strip():
        assert found.strip() in said, (
            f"The refusal does not quote the value it resolved, {found!r}: {said!r}.\n"
            "That value is the whole of what is wrong, and where it came from — the process or "
            "the file — is the thing the reader has to work out next."
        )


@pytest.mark.parametrize(("environ", "dotenv"), ADMITTED_CONFIGURATIONS)
def test_the_guard_admits_these_resolved_configurations(
    seed_module: Any,
    tmp_path: Path,
    capsys: Any,
    environ: dict[str, str],
    dotenv: dict[str, str],
) -> None:
    """The other half of the equality, and the first case is a ruling rather than a detail.

    **`.env` alone may grant permission.** That was disputed, arbitrated, and
    decided by Todd: "the guard reads resolved configuration", so `make seed`
    works on a stock checkout with nothing exported and `README.md`'s promise
    about that stands. A change that made this refuse would be reversing a
    decision, not tightening a guard.

    `the-process-says-development-over-a-deployment-file` is the precedence in the
    admitting direction: a developer who exports `ENVIRONMENT=development` over a
    `.env` that says something else is admitted, because the process wins.
    Without it, "the file may grant permission" could be implemented as "the file
    decides", which would refuse a developer who did exactly what an operator is
    told to do.

    The two padded rows are the admitting half of ADR 0063's "What the comparison
    actually is": `(raw or "").strip()` admits the one safe name with whitespace
    of any kind around it, which is deliberate — a trailing space is invisible in
    an editor, and a refusal quoting a padded name looks on screen exactly like a
    refusal quoting the right one. One row pads with spaces and one with a tab and
    a newline, because a strip narrowed to spaces would satisfy the first and not
    the second. The comment on `SPACED_DEVELOPMENT` above has the rest.
    """
    configuration = resolve(seed_module, environ, dotenv_at(tmp_path / ".env", dotenv))
    refused, said = guard_refusal(seed_module, configuration, capsys)

    assert refused is None, (
        f"The guard refused a configuration resolving `{DEPLOYED_ENVIRONMENT_VARIABLE}` to "
        f"{configuration.get(DEPLOYED_ENVIRONMENT_VARIABLE)!r}, out of a process holding "
        f"{environ} and a `.env` holding {dotenv}: {said!r}\n"
        "ADR 0063's decision, after `docs/disputes/E0-17-01.md` went to arbitration and then to "
        "Todd: 'the guard reads *resolved* configuration — the process environment with `.env` "
        "filling in only what it does not set'. Refusing here does not tighten that guard, it "
        "reverses the ruling — and it breaks `make seed` on a stock checkout, which is the case "
        "the ruling was about. Reopen the decision rather than the code: the record says the gap "
        "it leaves is accepted, and that 'anyone reaching for this gap later should reopen the "
        "address question, not this one'."
    )


def test_the_address_may_come_from_the_process_while_the_permission_comes_from_the_file(
    seed_module: Any, tmp_path: Path, capsys: Any
) -> None:
    """The residual gap Todd accepted, asserted as the decision it is.

    ADR 0063: "An operator who exports a production `DATABASE_URL` over a
    development checkout, leaving `ENVIRONMENT` to `.env`, is admitted: the
    address comes from the process and the permission from the file, and nothing
    here notices they describe different systems. Todd took that knowingly."

    This is that configuration exactly, and it is a test rather than a comment for
    two reasons. It is the case the dispute was about, so the day somebody changes
    it, the failure should say that a decision is being reversed and where to
    reopen it — which is the address check, not this one. And it is the case the
    parametrized admissions above cannot express: what makes it interesting is
    that the two sources supply *different* values, so the resolution is asserted
    as well as the verdict — without that, a `resolved_configuration` that ignored
    `environ` entirely would satisfy it.

    The address used is unreachable, so nothing here can connect to anything even
    if a later change moves work into the guard.
    """
    dotenv = dotenv_at(tmp_path / ".env", {DEPLOYED_ENVIRONMENT_VARIABLE: DEVELOPMENT_ENVIRONMENT})
    environ = {"DATABASE_URL": UNREACHABLE_DATABASE_URL}
    configuration = resolve(seed_module, environ, dotenv)

    assert configuration.get("DATABASE_URL") == UNREACHABLE_DATABASE_URL, (
        f"The resolved configuration's `DATABASE_URL` is "
        f"{configuration.get('DATABASE_URL')!r} rather than the one the process supplied. This "
        "case is named for two sources reaching the script at once; if the process's value does "
        "not arrive, the verdict below is about one source and says nothing about the gap."
    )
    assert configuration.get(DEPLOYED_ENVIRONMENT_VARIABLE) == DEVELOPMENT_ENVIRONMENT, (
        f"The resolved configuration's `{DEPLOYED_ENVIRONMENT_VARIABLE}` is "
        f"{configuration.get(DEPLOYED_ENVIRONMENT_VARIABLE)!r}, and the `.env` written for this "
        f"test sets it to {DEVELOPMENT_ENVIRONMENT!r}. The permission is supposed to come from "
        "the file here, and it did not."
    )

    refused, said = guard_refusal(seed_module, configuration, capsys)
    assert refused is None, (
        f"The guard refused an address from the process and a permission from the file: {said!r}\n"
        "ADR 0063 records this exact combination as admitted, knowingly, after the dispute: "
        "'Reading B refuses only the slice where the operator forgot to export the name, and "
        "admits the slice where they exported `development` alongside a production address. The "
        "check that would close it properly is a check on the *address*.' So a refusal here is a "
        "reversal of Todd's ruling rather than a fix, and the thing to reopen is the address "
        "question."
    )


def test_the_refusal_says_which_of_the_three_ways_the_environment_was_wrong(
    seed_module: Any, tmp_path: Path, capsys: Any
) -> None:
    """Not set anywhere, set to nothing, and set to something else are three messages.

    ADR 0063: "the refusal names which of the three ways it was wrong — an earlier
    version reported the first and the third identically, which is how the two got
    conflated in the first place." That conflation is the reason a case that
    measured the machine went unnoticed for a round, so the distinction is worth
    holding rather than trusting.

    **The three cases share one `.env` file, and that is what makes the assertion
    mean something.** They differ only in what the process supplies, so three
    messages that differ cannot be differing because the file's path or contents
    changed — which is the shape a "these are distinct" assertion usually passes
    for (`docs/MISTAKES.md` entry 3). The wording is nobody's business here: what
    is asserted is that an operator can tell the three apart.
    """
    dotenv = dotenv_at(tmp_path / ".env", SILENT_DOTENV)
    ways = {
        "not set anywhere": {},
        "set to nothing": {DEPLOYED_ENVIRONMENT_VARIABLE: ""},
        "set to a deployment name": {DEPLOYED_ENVIRONMENT_VARIABLE: DEPLOYED_ENVIRONMENT_VALUE},
    }

    said_by_way: dict[str, str] = {}
    for way, environ in ways.items():
        refused, said = guard_refusal(seed_module, resolve(seed_module, environ, dotenv), capsys)
        assert refused is not None, (
            f"The guard admitted the configuration where `{DEPLOYED_ENVIRONMENT_VARIABLE}` is "
            f"{way}. Every one of these is refused by ADR 0063's table, and the parametrized "
            "cases above are where that is asserted; this test needs all three refused before it "
            "can ask whether they read differently."
        )
        assert (
            DEPLOYED_ENVIRONMENT_VARIABLE in said
        ), f"The refusal for `{DEPLOYED_ENVIRONMENT_VARIABLE}` {way} names no variable: {said!r}."
        said_by_way[way] = said

    identical = [
        (one, other)
        for index, one in enumerate(said_by_way)
        for other in list(said_by_way)[index + 1 :]
        if said_by_way[one] == said_by_way[other]
    ]
    assert not identical, (
        f"These refusals are word for word the same: {identical}.\n"
        + "\n".join(f"  {way}: {text!r}" for way, text in said_by_way.items())
        + "\nADR 0063 asks the refusal to name 'which of the three ways it was wrong', because an "
        "earlier version printed the unset case and the empty case identically — and that "
        "conflation is what hid a defect for a round: a hand measurement ran `ENVIRONMENT=`, read "
        "the message, and reported the unset case as covered when it had never been asked "
        "(`docs/MISTAKES.md` entry 30)."
    )


# ---------------------------------------------------------------------------
# Criterion 4 — running it twice.
#
# Last in the file on purpose: everything above measures the state one run
# produces, which is the state every other criterion describes. Running the seed
# again here means a script that duplicates rows fails as one duplication rather
# than as six shapes.
# ---------------------------------------------------------------------------


def test_running_the_seed_a_second_time_completes_without_a_constraint_violation(
    seeded_demo: Any, second_seed: SecondSeed
) -> None:
    """Criterion 4, first half: "no constraint violation".

    The failure this catches is the ordinary one — a loader that inserts
    unconditionally meets its own unique constraints on the second pass — and the
    script's own output is what says which constraint.
    """
    seeded(seeded_demo)
    assert second_seed.run.succeeded, (
        f"The second seed run failed against the database the first one left.\n"
        f"{second_seed.run.report()}\n"
        "E0-17: 'Running `make seed` twice produces no duplicate rows and no constraint "
        "violation.' This is the half a unique constraint reports; the half nothing reports is "
        "asserted by the test below."
    )


def test_running_the_seed_a_second_time_leaves_the_same_rows(
    seeded_demo: Any, second_seed: SecondSeed, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 4, second half: "no duplicate rows", and the same state.

    **Counts and content, not one or the other.** A count comparison alone passes
    over a run that replaced every row's values while keeping the number; a content
    comparison alone reads oddly when a table gains rows, since the failure would
    be a wall of labels rather than "there are now twice as many sections". Both
    are asserted here because they are one criterion, and the counts are compared
    first so the message says the simple thing when the simple thing is wrong.

    **What a label is, and what it deliberately does not pin**, is written on
    `row_label` above: E0-17 does not say whether a second run re-uses the rows it
    finds or reloads them, and both are idempotent in the sense the criterion
    means. So a row is compared by its values and by the rows its keys point at,
    never by the uuids themselves.

    **The non-vacuity guard is not ceremony.** Two empty databases have the same
    counts and the same labels, so this would pass most convincingly against a
    seed that wrote nothing at all — which is `docs/MISTAKES.md` entry 3 in its
    purest form.
    """
    seeded(seeded_demo)
    before = counted(second_seed.before)
    after = counted(second_seed.after)

    assert sum(before.values()), (
        "The database held no rows before the second run, so 'the same rows afterwards' is a "
        "comparison between two empty databases. The first run is what should have filled it, and "
        "`test_seeding_a_freshly_migrated_database_completes_without_error` is where that is "
        "asserted."
    )

    grew = {
        name: (before.get(name, 0), count)
        for name, count in after.items()
        if count != before.get(name, 0)
    }
    assert not grew, (
        f"These tables hold a different number of rows after a second seed run (before, after): "
        f"{grew}. E0-17: 'idempotent: running it twice leaves the same database state rather than "
        "duplicating rows'. A developer runs `make seed` again after every schema change; a "
        "second copy of the institution is not a visible failure, it is a demo database where "
        "every roll-up count is doubled and every purview test has two answers."
    )

    labels_before = labelled(metadata_tables, second_seed.before)
    labels_after = labelled(metadata_tables, second_seed.after)
    changed = {
        name: (
            sorted(set(labels_before.get(name, [])) - set(rows))[:5],
            sorted(set(rows) - set(labels_before.get(name, [])))[:5],
        )
        for name, rows in labels_after.items()
        if sorted(rows) != sorted(labels_before.get(name, []))
    }
    assert not changed, (
        f"A second seed run left the same number of rows holding different content (gone, "
        f"arrived — up to five of each): {changed}. E0-17's criterion is 'the same database "
        "state', not the same row count: a loader that deletes and rewrites, or that updates a "
        "row it should have matched, keeps the count and moves the data underneath every fixture "
        "built on it. Row identities are deliberately not compared — see `row_label` in this "
        "file for why — so this is a difference in values or in what a row points at."
    )
