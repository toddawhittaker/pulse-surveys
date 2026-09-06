"""A column on an LMS-owned table is marked, structural, or recorded — ticket E0-35.

[ADR 0014](../../docs/adr/0014-lms-owned-columns-are-marked-by-a-name-prefix.md)
marks LMS-owned columns with an `lms_` name prefix and says plainly what the
marker cannot do: "an unprefixed LMS-owned column arriving in a later ticket leaves
no trace in the metadata that distinguishes it from a Pulse-owned one." E0-35 puts
it in one sentence — `course.canvas_id` sails through every test in the suite —
and rules out the obvious repair: asserting that the *prefixed* set matches a list
does not work, because adding `course.canvas_id` leaves the prefixed set unchanged.

**So this module asks the question from the other end, at table grain.** SPEC §2.1
names the tables whose contents the LMS owns, and ADR 0045 adds `user` to them for
a reason of its own. On the tables in that guarded set, a column is acceptable
only if it is one of four things:

1. **Marked** — it carries the `lms_` prefix, and ADR 0014's convention is met.
2. **Structural** — a primary key, or a column carrying a foreign key. Those are
   Pulse's own wiring between rows rather than facts the LMS supplies, and they
   are identified by what they *are* rather than by being named here, so a new one
   arriving needs no edit to this file.
3. **Unwritable** — a stored generated column, which nothing can write by any
   path. `course.level` is the worked example
   ([ADR 0015](../../docs/adr/0015-course-level-is-a-stored-generated-column.md)):
   it derives from `lms_number`, carries no prefix, and the marker exists to stop
   a write that this column already makes impossible.
4. **Recorded** — named in `PULSE_OWNED_COLUMNS` below with the record that says
   why Pulse owns a value on a table the LMS owns.

**There is no fifth category, and a timestamp does not get one.** An earlier draft
of this module exempted `created_at`, `updated_at` and `deleted_at` by name, on
the ground that Pulse writes row bookkeeping whatever the row is about. It excused
nothing — no table in the guarded set carries any of the three — and it opened the
hole this sweep exists to close: an `updated_at` added to `course` to mirror the
platform's last-modified stamp is LMS-supplied, unmarked, unrecorded, and would
have passed. Whether a timestamp is Pulse's or the LMS's is exactly the fact
`Base.metadata` cannot recover, so it costs a `PULSE_OWNED_COLUMNS` entry like
anything else. Found in E0-35's review.

Anything else fails. `course.canvas_id` is none of the four, which is the whole
point: the direction ADR 0014 could not assert is reachable once the question is
asked per *table* instead of per column, and that is the trade this closes at.
**The marker stops being the enforcement mechanism and becomes documentation** —
which retires one of the two reasons ADR 0014 gives for a name prefix over an
`info={}` dict, and that record needs the line saying so.

**What this cannot see, so nothing here is cited as more than it is.**

  - **It only speaks about the tables in the guarded set.** An LMS-owned column
    landing on a table nobody has put there — a new relation from E1's sync, a
    column on `person` — is outside it entirely, and outside ADR 0045's chokepoint
    for the same reason. Ownership is a fact about where data comes from, and no
    walk of `Base.metadata` will ever recover it once the marker is missing; what
    table grain buys is that on the tables in that set, the marker's accuracy stops
    mattering.
  - **A recorded exception is a claim nobody re-checks.** Every entry in
    `PULSE_OWNED_COLUMNS` is a statement that Pulse owns that value, taken from
    the record cited beside it. If one of them is wrong, this file is where the
    wrongness is preserved. The entries are required to name real columns, so an
    exception cannot outlive the column it excuses, but nothing can check that the
    reason is still true.
  - **It reads `Base.metadata` and not the database.** A column that exists only
    in a migration is invisible here, which is the right side to read for a marker
    the authz layer resolves through the ORM — ADR 0014 says so — and is still a
    limit.
"""

from typing import Any

import pytest
from sqlalchemy import Column, Computed, ForeignKey, Integer, MetaData, String, Table

LMS_PREFIX = "lms_"

# The floor the swept set may not fall below. **Read out of the records, not out
# of the module under test** (`docs/MISTAKES.md` entry 19), and the four entries do
# not all come from the same one. Three are SPEC §2.1's ownership sentence:
# courses, sections, section codes, enrollments, teaching instructors. The fourth
# is **ADR 0045's and not the spec's** — §2.1 names no user record, and ADR 0045
# puts `user` in the guarded set because `user.lms_user_id` is the `sub` claim
# verbatim and SPEC §4 keys every response to it.
#
# It is a floor rather than the whole set: the swept set is this unioned with the
# guard's own `LMS_OWNED_TABLES`, so the sweep grows when ADR 0045's grain grows
# and cannot be shrunk below these four by an edit to the module it is holding up.
# Removing one of the four from `LMS_OWNED_TABLES` fails
# `test_the_guard_names_every_table_in_the_floor_this_sweep_may_not_fall_below` in
# `tests/unit/test_every_writer_of_an_lms_owned_relation_names_the_guard.py`, which
# is where a shrinking guard is diagnosed; the union here is only what stops this
# sweep going quiet about it. Removing a table the guard holds *above* the floor
# fails nothing anywhere — that test states the gap, and ADR 0069 carries it with
# a "done when".
GUARDED_TABLE_FLOOR = ("course", "section", "enrollment", "user")

# Unprefixed columns on an LMS-owned table that Pulse genuinely owns, each with the
# record that says so. Adding to this dict is a decision about ownership and
# belongs in a pull request that says which record it rests on — it is not the
# place to quiet a failure.
PULSE_OWNED_COLUMNS: dict[str, dict[str, str]] = {
    "course": {
        "title_is_fallback": (
            "ADR 0091 (E1-10): `course.lms_title` is the LMS's, and this flag is Pulse's record "
            "of whether that column currently holds a platform-supplied title or the "
            "'PREFIX NUMBER' fallback provisioning wrote when a launch carried a context label "
            "and no title. The platform never sends it and no sync can overwrite it — it is what "
            "lets a later real title replace a fallback while a titleless launch never overwrites "
            "a real title, which is E1-10's own scope: 'the fallback value is distinguishable "
            "from a platform-supplied title (the ADR says how, so a later sync does not "
            '"correct" a real title into a fallback or vice versa)\'.'
        )
    },
    "section": {
        "length_weeks": (
            "ADR 0021: the four derived calendar columns are computed in Pulse by "
            "`apply_section_code` from the LMS's section code and the term's start-letter map. "
            "SPEC §2.2: 'Section start/end dates derive from the letter + term calendar; nothing "
            "is hand-entered per section.' The LMS supplies the code, not the calendar."
        ),
        "start_date": "ADR 0021, with `length_weeks` above.",
        "end_date": "ADR 0021, with `length_weeks` above.",
        "modality": (
            "ADR 0021 and SPEC §2.2: the modality is parsed out of the section code rather than "
            "supplied as a field, so it is derived in Pulse like the three dates."
        ),
        "ags_line_item_url": (
            "ADR 0128 (E3-02): SPEC §3.4 gives every section one AGS line item, 'Pulse "
            "Participation', and this tool is what creates it in the container the platform "
            "advertises. The platform mints the identifier, and that is not what decides "
            "ownership here: the value records which artifact Pulse created and posts to. "
            "Nothing in the LMS's data model instructs Pulse to hold it, no sync mirrors it, "
            "and an LMS-side rename or deletion makes it stale rather than wrong — E3-04's "
            "re-find rule is the reconciliation. The `lms_` prefix is refused deliberately: ADR "
            "0014's prefix means 'the platform publishes it and Pulse only keeps what it was "
            "handed', which describes the claim-supplied `lms_ags_line_items_url` beside it and "
            "not this receipt. E3-02 adds the column and writes nothing to it; E3-05 is its "
            "writer, and the application role holds no `UPDATE` on it until that ticket grants "
            "one."
        ),
    },
    "enrollment": {
        "started_on": (
            "ADR 0045, quoted rather than decided here: `app/models/identity.py` records that "
            "these are 'most likely Pulse's record of when a student was first and last seen, "
            "which is why they carry no `lms_` prefix'. That record leaves it open — 'if E1's "
            "roster sync turns out to own them, they are already inside the refusal for the right "
            "reason' — and this entry is where that changes if it does."
        ),
        "ended_on": "ADR 0045, with `started_on` above.",
    },
}


def swept_tables(authz: Any) -> tuple[str, ...]:
    """The tables whose columns this module judges.

    The union of the floor above and the guard's own set. The union is what makes
    this grow when ADR 0045's grain grows; the floor is what stops it narrowing
    below those four when the guard does, and the assertion that the guard still
    names them lives in the sibling sweep cited beside the floor. Above the floor
    the guard may narrow with nothing noticing, which that sweep states as its own
    limit.
    """
    return tuple(sorted(set(GUARDED_TABLE_FLOOR) | set(authz.LMS_OWNED_TABLES)))


def declarative_metadata(import_app_module: Any) -> Any:
    """`Base.metadata` with every model module registered on it.

    Reached through `app.models` rather than through one model module, for the
    reason `tests/unit/test_org_models_registered.py` gives at length: `env.py`
    imports the package, and a module nobody imported is on no metadata.
    """
    package = import_app_module("app.models")
    if package is None:
        pytest.fail(
            "There is no `app.models` package to walk, so this sweep has no columns to judge and "
            "would report success. `tests/unit/test_org_models_registered.py` is where a missing "
            "registration is diagnosed."
        )
    base_module = import_app_module("app.models.base")
    metadata = getattr(getattr(base_module, "Base", None), "metadata", None)
    if metadata is None:
        pytest.fail(
            "`app.models.base` is missing, or exposes no `Base` with `metadata`, so there is "
            "nothing to walk. E0-04 ships the declarative base there."
        )
    return metadata


def accounted_for(column: Any, recorded: dict[str, str]) -> str | None:
    """Why `column` is allowed to sit unmarked on a table the LMS owns, or `None`.

    One function, so that the sweep over the real schema and the control over the
    synthetic one are asking the same question — a control that re-implemented the
    rule would be testing a copy of it (`docs/MISTAKES.md` entry 19).
    """
    if column.name.startswith(LMS_PREFIX):
        return "marked"
    if column.primary_key:
        return "a primary key"
    if column.foreign_keys:
        return "a foreign key"
    if getattr(column, "computed", None) is not None:
        return "a generated column, which nothing can write"
    if column.name in recorded:
        return "recorded as Pulse-owned"
    return None


def unaccounted_columns(table: Any, recorded: dict[str, str]) -> list[str]:
    """Every column on `table` that is neither marked, structural, nor recorded."""
    return sorted(
        column.name for column in table.columns if accounted_for(column, recorded) is None
    )


def synthetic_lms_table(*, marker: str) -> Table:
    """A stand-in for `course`, carrying one column of each shape the rule judges.

    Built here rather than taken from `Base.metadata` so the control asserts what
    the *rule* does rather than what today's schema happens to contain. `marker` is
    the name of the column under test: `canvas_id` is E0-35's own example of the
    thing that must fail, `lms_canvas_id` is the nearest thing to it that must pass
    — one prefix apart, so a rule that fired on both, or on neither, is caught here
    rather than by nobody — and `updated_at` is the shape E0-35's review found
    passing through a fifth category that no longer exists.

    The three columns beside it are one of each thing the rule accounts for: a
    primary key, a foreign key, and a stored generated column.
    """
    metadata = MetaData()
    Table("prefix", metadata, Column("id", Integer, primary_key=True))
    return Table(
        "course",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("prefix_id", Integer, ForeignKey("prefix.id")),
        Column("lms_number", String(16)),
        Column("level", String(8), Computed("'UG'")),
        Column(marker, String(64)),
    )


def test_the_rule_refuses_an_unmarked_lms_column_and_allows_its_nearest_neighbours() -> None:
    """The control, run before the sweep's silence over the real schema counts.

    E0-35's criterion is that adding an LMS-owned column with no `lms_` prefix
    fails something, "demonstrated by adding one and watching it go red". This is
    that demonstration written down: the same table, twice, differing only in
    whether the new column wears the marker.

    The allowed half is what stops the rule being a prohibition on columns. A
    primary key, a foreign key and a generated column are all unprefixed and all
    correct, and a rule that failed on them would be red against the schema E0-05
    already shipped — which is the state that gets a rule deleted rather than met.

    **A timestamp is not one of them, and the case is here because it once was.**
    E0-35's review found a fifth branch exempting `created_at`, `updated_at` and
    `deleted_at` by name: it excused nothing on today's schema and would have let
    an LMS-supplied last-modified stamp onto `course` unmarked. The branch is gone
    and this is the case that stops it coming back quietly.
    """
    caught = unaccounted_columns(synthetic_lms_table(marker="canvas_id"), recorded={})
    assert caught == ["canvas_id"], (
        f"The rule reports {caught} for a `course` table carrying an unprefixed `canvas_id`. It "
        "has to be exactly that one column: anything less and E0-35's own example passes, "
        "anything more and the rule is red against a primary key, a foreign key or a generated "
        "column — all of which E0-05's schema already has."
    )

    timestamped = unaccounted_columns(synthetic_lms_table(marker="updated_at"), recorded={})
    assert timestamped == ["updated_at"], (
        f"The rule reports {timestamped} for a `course` table carrying an unprefixed "
        "`updated_at`. A timestamp on a table the LMS owns is not exempt for being a timestamp: "
        "it is as likely to be the platform's last-modified stamp as Pulse's own row "
        "bookkeeping, and which one it is, is exactly the fact `Base.metadata` cannot recover. "
        "If a Pulse-owned timestamp genuinely lands on one of these tables, it costs a "
        "`PULSE_OWNED_COLUMNS` entry like any other column, not a category of its own."
    )

    allowed = unaccounted_columns(synthetic_lms_table(marker="lms_canvas_id"), recorded={})
    assert not allowed, (
        f"The rule reports {allowed} for the same table with the column marked `lms_canvas_id`. "
        "Marking the column is the fix this sweep exists to ask for, so a marked column that "
        "still fails leaves the failure with no remedy."
    )

    excused = unaccounted_columns(
        synthetic_lms_table(marker="canvas_id"), recorded={"canvas_id": "a reason"}
    )
    assert not excused, (
        f"The rule reports {excused} for a column recorded as Pulse-owned. The recorded set is "
        "the second remedy — rename it, or say in a record why Pulse owns it — and a rule that "
        "ignores the record leaves only the rename."
    )


def test_every_recorded_exception_names_a_column_that_exists(
    configured_env: dict[str, str], import_app_module: Any, authz: Any
) -> None:
    """An excuse may not outlive the column it excuses.

    The failure this prevents is quiet and cumulative: a column is renamed or
    dropped, its entry in `PULSE_OWNED_COLUMNS` stays, and the next column that
    happens to take that name is excused by a record written for something else.
    `tests/unit/test_the_provider_judges_the_value_that_arrived.py` holds the same
    property for the mock provider's permissions, for the same reason.

    It also catches the cheaper mistake in the other direction. Every entry here is
    a claim about the schema, written by someone reading an ADR rather than the
    models, and a misspelt column name would silently excuse nothing while looking
    like it excused something.
    """
    metadata = declarative_metadata(import_app_module)
    swept = swept_tables(authz)

    stale: list[str] = []
    for table_name, recorded in PULSE_OWNED_COLUMNS.items():
        table = metadata.tables.get(table_name)
        if table is None:
            stale.append(f"{table_name} (no such table)")
            continue
        if table_name not in swept:
            stale.append(f"{table_name} (not a table this module sweeps: {list(swept)})")
        present = {column.name for column in table.columns}
        stale.extend(f"{table_name}.{name}" for name in sorted(set(recorded) - present))

    assert not stale, (
        f"`PULSE_OWNED_COLUMNS` records {stale}, which do not exist on `Base.metadata`. An "
        "exception for a column nobody can find is a hole the next column with that name falls "
        "into, and it reads in review as though somebody checked."
    )


def test_no_column_on_an_lms_owned_table_is_unmarked_and_unaccounted_for(
    configured_env: dict[str, str], import_app_module: Any, authz: Any
) -> None:
    """The criterion: an LMS-owned column with no `lms_` prefix fails something.

    SPEC §2.1 puts courses, sections, section codes, enrollments and teaching
    instructors on the LMS's side — read-only in Pulse, synced hourly and at
    launch — and §8 restates it as a constraint. ADR 0045's chokepoint refuses
    writes to these tables whatever a column is called, so an unprefixed LMS-owned
    column landing here is not an open edit path today. What it is, is a column the
    schema no longer says anything about: the next reader cannot tell whether Pulse
    may compute it, an export may show it, or a sync will overwrite it, and ADR
    0014's whole argument for a name over an `info={}` dict is that the name is in
    front of whoever writes the query.

    **The mutation this exists to survive** is `course.canvas_id` — an LMS
    identifier added to a table the LMS owns, spelled the way every integration
    spells it, by somebody who has no reason to think a prefix is load-bearing.
    Before this module, it passed every test in the suite.

    A failure here has two honest answers and no third: rename the column with the
    `lms_` prefix, or add it to `PULSE_OWNED_COLUMNS` above with the record that
    says why Pulse owns a value on a table the LMS owns.
    """
    metadata = declarative_metadata(import_app_module)
    swept = swept_tables(authz)

    tables = {name: metadata.tables.get(name) for name in swept}
    absent = sorted(name for name, table in tables.items() if table is None)
    assert not absent, (
        f"{absent} are in the guarded set and are not registered on `Base.metadata` (it holds "
        f"{sorted(metadata.tables)}), so this sweep judged no column on them and its silence "
        "about them means nothing. `test_the_refusal_set_names_the_tables_the_spec_puts_on_the_"
        "lms_side` is where a name in `LMS_OWNED_TABLES` that matches no table is diagnosed."
    )

    marked = {
        f"{table.name}.{column.name}"
        for table in tables.values()
        if table is not None
        for column in table.columns
        if column.name.startswith(LMS_PREFIX)
    }
    assert marked, (
        f"No column on any of {list(swept)} starts with `{LMS_PREFIX}`, so either the marker does "
        "not exist yet or this sweep is reading a schema that is not the one E0-05 shipped — and "
        "a rule about unmarked columns asserts nothing against a schema with no marking at all."
    )

    unaccounted = {
        name: unaccounted_columns(table, PULSE_OWNED_COLUMNS.get(name, {}))
        for name, table in tables.items()
        if table is not None
    }
    failing = {name: found for name, found in unaccounted.items() if found}

    assert not failing, "\n".join(
        [
            f"These columns sit on a table the LMS owns, carry no `{LMS_PREFIX}` marker, and are "
            "not structural or recorded:",
            *(f"  {name}: {found}" for name, found in sorted(failing.items())),
            "",
            "SPEC §2.1 makes courses, sections, section codes, enrollments and teaching "
            "instructors LMS-owned and read-only in Pulse. ADR 0014 marks an LMS-owned column "
            "with an `lms_` name prefix so that the name is in front of whoever writes the "
            "query, and records that the marker cannot catch its own omission — this is the "
            "sweep E0-35 built to catch it, asked at table grain because ownership is not "
            "recoverable from an unprefixed column name.",
            "",
            "Two answers, and no third. Rename it with the prefix if the LMS supplies the value. "
            "If Pulse genuinely owns it, add it to `PULSE_OWNED_COLUMNS` in this file with the "
            "record that says so — a decision about ownership, made in a pull request, not a way "
            "to quiet a failure.",
        ]
    )
