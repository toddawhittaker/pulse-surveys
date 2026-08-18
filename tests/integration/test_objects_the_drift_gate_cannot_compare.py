"""Generated columns, check constraints and exclusion constraints — ticket E0-33, items 1 and 2.

`alembic check` compares `Base.metadata` against the database, and
`Base.metadata` holds tables and columns. Everything a *rule on a table* is made
of sits outside that comparison. E0-20 item 3a measured the boundary against a
freshly upgraded container on the pinned Alembic 1.19, mutating the model only,
with a dropped column last as the canary so that "clean" is distinguishable from
a comparison that has gone blind:

| Mutation | `alembic check` |
|---|---|
| exclusion constraint removed | **clean** |
| check-constraint expression changed | **clean** |
| check constraint renamed | detected (1.19's `checkconstraint_byname`) |
| column dropped | detected — the canary |

Item 3 of E0-20 adds the fourth object in the same class: a *generated* column.
Alembic has no `ALTER` to emit for one, so `_compare_computed_default`
normalises both expressions, emits a `UserWarning` when they differ, and
`alembic check` still exits zero. E0-05 spells `course.level`'s expression the
way Postgres deparses it, so the warning fires only on real drift — but a
warning is not a gate, and a changed generation expression with no migration
behind it still passes CI.

**The trap, and it is the reason this file exists.** An object written into the
migration that creates it reads like coverage and is not: nothing re-reads it, in
either direction. E0-06 is the incident rather than the hypothesis — it shipped
`start_letter_map` with `CheckConstraint("letter ~ '^[A-Z]$'")`, which refused six
of the twenty positions in SPEC §2.2's own Fall 2026 seed map, and nobody found
out until E0-07 wrote code that needed one. Every gate was green throughout.

**How both sides are normalised: Postgres does it.** The hard part of comparing a
model's `Computed` text with a stored generation expression is that the two are
different spellings of the same thing — `(a / 100)` and `a / 100` and `A / 100`
deparse identically and are not drift. So this module does not normalise text at
all. It builds a second copy of `Base.metadata` in a throwaway schema, lets
Postgres parse and store *the model's* spelling there, and then compares what
`pg_get_expr` and `pg_get_constraintdef` report for the two schemas. Both sides
come back through the same deparser, so cosmetic differences are gone before the
comparison and semantic ones survive it. The two self-tests at the top of the
file are that claim executed rather than asserted — `docs/MISTAKES.md` entry 3's
rule for a comparison, which is the same rule it states for a pattern: run it
against the thing it must catch *and* the thing it must allow.

**These tests are green the day they land, and that is what they are for.** There
is no behaviour to build here: the database is believed to be correct today. The
deliverable is that it stops being possible for it to drift silently, so the
verification is by mutation — the mutation each test survives is named in its own
docstring, in E0-20's vocabulary, together with the near miss it must tolerate. A
test that goes red on any change to the schema is a tripwire on the file rather
than an assertion.

**What this module does not cover**, said plainly so nobody reads it as wider
than it is (`docs/MISTAKES.md` entry 14):

  - **Triggers, row-level security policies, sequences and functions.** None is
    on `Base.metadata`, so a probe built from the model carries none of them and
    there is nothing here to compare. E0-11's climbing rule is a trigger and is
    asserted behaviourally in
    `test_the_upgrade_refuses_a_stored_edge_that_does_not_climb.py`.
  - **Indexes.** `alembic check` does compare them, which is why they are absent
    here rather than forgotten.
  - **Roles, grants, views and function owners** — E0-33 item 3, which extends
    `test_identity_grants.py` (the grant and role half) and
    `test_identity_separated_views.py` (the view set), because both already hold
    the machinery those halves need and a second copy of it would be
    `docs/MISTAKES.md` entry 13.
  - **A model table outside `public`.** Every table in this schema is in
    `public`; one declared elsewhere would be built into the probe and then
    compared against nothing.
"""

from typing import Any, NamedTuple
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, MetaData, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint

pytestmark = pytest.mark.integration

# Every generated column in one schema, with the expression the server stored for
# it. `attgenerated` is the empty string on an ordinary column and `s` on a stored
# generated one, so the filter is the property rather than a list of names.
# `pg_get_expr` deparses the parse tree Postgres kept, which is the only record of
# a generation expression there is — `CREATE TABLE`'s own text is not retained.
GENERATED_COLUMNS = """
    SELECT c.relname AS table_name,
           a.attname AS column_name,
           pg_get_expr(d.adbin, d.adrelid) AS expression
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
    WHERE n.nspname = :schema
      AND c.relkind IN ('r', 'p')
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND a.attgenerated <> ''
    ORDER BY 1, 2
"""

# Every constraint of one kind in one schema, as the server renders it back.
# `pg_get_constraintdef` prints the definition without the constraint's name,
# which is deliberate here: 1.19's `checkconstraint_byname` already fails
# `alembic check` on a rename, so a rename is not this file's job and a comparison
# that included the name would go red on one.
CONSTRAINT_DEFINITIONS = """
    SELECT c.relname AS table_name,
           con.conname AS constraint_name,
           pg_get_constraintdef(con.oid) AS definition
    FROM pg_constraint con
    JOIN pg_class c ON c.oid = con.conrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = :schema AND con.contype = :contype
    ORDER BY 1, 2
"""

# The schema the migrations built. Named rather than discovered because SPEC §13
# and every migration in the tree put this project's tables in `public`, and
# because the probe schema below has to be told which one it is a copy of.
MIGRATED_SCHEMA = "public"


class ConstraintKind(NamedTuple):
    """One kind of constraint `alembic check` does not compare, from both sides.

    `contype` is what `pg_constraint` calls it and `declared_as` is the class the
    model declares it with, so the two halves of each test — "the model declares
    at least one" and "the catalog reports at least one" — are asked about the
    same thing rather than about two things that happen to be true together.
    """

    contype: str
    declared_as: type
    label: str
    why_one_exists: str


# Both kinds E0-20 item 3a names, and the reason each is known to exist rather
# than assumed. Both entries carry their own vacuity guard's message, because a
# comparison between two empty sets passes and says nothing (`docs/MISTAKES.md`
# entry 3), and because the two kinds fail that guard for different reasons.
CONSTRAINT_KINDS = (
    ConstraintKind(
        contype="c",
        declared_as=CheckConstraint,
        label="check",
        why_one_exists=(
            "E0-06 ships `start_letter_map` with a check constraint on its letter column, and "
            "E0-08's enrollment window-ordering rule *is* a check constraint — E0-20 item 3a "
            "names both. A model that declares none is either a model that has lost them or a "
            "reflection here that has stopped seeing them; the first is the drift this test "
            "exists for and the second would make it pass against anything."
        ),
    ),
    ConstraintKind(
        contype="x",
        declared_as=ExcludeConstraint,
        label="exclusion",
        why_one_exists=(
            "E0-08's enrollment overlap rule *is* an exclusion constraint — E0-20 item 3a says "
            "so, and its measurement was taken by removing that constraint from the model and "
            "watching `alembic check` report clean, which is only possible if the model is where "
            "it is declared. A model that declares none is therefore the very mutation this test "
            "is here to catch, and it is caught here rather than by the comparison below, which "
            "an empty model side satisfies."
        ),
    ),
)


def public_tables(tables: dict[str, Any]) -> list[Any]:
    """Every `Base.metadata` table that lives in the schema the migrations built."""
    return [table for table in tables.values() if table.schema in (None, MIGRATED_SCHEMA)]


def declared_generated_columns(tables: dict[str, Any]) -> dict[tuple[str, str], Any]:
    """Every `(table, column)` the model declares as generated, and its `Computed`.

    Discovered by reflection over `Base.metadata` rather than by naming
    `course.level`, which is the only one today. A rule spelled with that name
    would retire with the column and would cover no generated column added after
    it — and one added without a migration behind it is precisely the change
    `alembic check` answers with a warning and a zero exit.
    """
    return {
        (table.name, column.name): column.computed
        for table in public_tables(tables)
        for column in table.columns
        if column.computed is not None
    }


def declared_constraints(tables: dict[str, Any], kind: ConstraintKind) -> dict[str, int]:
    """How many constraints of `kind` the model declares, per table.

    The count rather than the objects: what the constraint *says* is compared out
    of the catalog on both sides, so the model side is needed only to tell "the
    model declares none" apart from "the probe schema was not built", which are
    two different failures with the same symptom.
    """
    counted: dict[str, int] = {}
    for table in public_tables(tables):
        found = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, kind.declared_as)
        ]
        if found:
            counted[table.name] = len(found)
    return counted


def generated_expressions(session: Any, schema: str) -> dict[tuple[str, str], str]:
    """What `schema` stores as the generation expression of each of its generated columns."""
    return {
        (row.table_name, row.column_name): row.expression or ""
        for row in session.execute(text(GENERATED_COLUMNS), {"schema": schema})
    }


def constraint_definitions(session: Any, schema: str, contype: str) -> dict[str, set[str]]:
    """Every `contype` constraint in `schema`, as a set of definitions per table.

    A set rather than a list because a constraint's name is not compared: two
    tables' worth of definitions are being asked whether they say the same things,
    and "the same rule under a different name" is the near miss this file has to
    tolerate.
    """
    found: dict[str, set[str]] = {}
    rows = session.execute(text(CONSTRAINT_DEFINITIONS), {"schema": schema, "contype": contype})
    for row in rows:
        found.setdefault(row.table_name, set()).add(row.definition)
    return found


@pytest.fixture
def model_probe_schema(db_session: Any, metadata_tables: dict[str, Any]) -> str:
    """`Base.metadata` built into a schema of its own, for Postgres to deparse.

    This is the mechanism the whole module rests on and it is worth stating in
    full. The question every test below asks is whether the rule the *model*
    declares is the rule the *migrated database* is carrying, and the two are
    written in different languages: one is Python that a SQLAlchemy dialect will
    compile, the other is a parse tree Postgres already stored. Comparing them as
    text means normalising two spellings by hand, and every normaliser of that
    kind is a place where a real difference gets sanded off — strip the
    parentheses and `a - (b - c)` reads like `(a - b) - c`.

    So the model's own DDL is executed, into a schema named after nothing, and the
    comparison is between two things the same server deparsed. Cosmetic
    differences are gone before the comparison; semantic ones are not.
    `test_the_constraint_definition_comparison_normalises_spelling_and_keeps_meaning`
    and its sibling are those two halves executed.

    **It runs inside `db_session`'s transaction**, which is what removes it: the
    fixture rolls back, and Postgres puts DDL inside the transaction, so the schema
    and everything in it is gone whether the test passed or failed. Nothing here
    touches `public`.

    **A failure to build is reported as a broken mechanism, not as drift.** If
    `create_all` cannot run, every comparison below would be between the real
    schema and an empty one — which is a red for a reason that has nothing to do
    with the model, and the message says so rather than sending the reader to look
    for a constraint that moved.
    """
    tables = public_tables(metadata_tables)
    assert tables, (
        "`Base.metadata` holds no table in `public`, so there is nothing to build a probe from "
        "and every comparison in this module would be between two empty sets. "
        "`tests/unit/test_identity_models_registered.py` diagnoses a model package whose modules "
        "were never imported, which is the usual cause and the one that leaves `alembic check` "
        "green as well."
    )

    schema = f"model_probe_{uuid4().hex[:12]}"
    connection = db_session.connection()
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    probe = MetaData(schema=schema)
    for table in tables:
        table.to_metadata(probe, schema=schema)

    try:
        probe.create_all(bind=connection, checkfirst=True)
    except Exception as failure:
        pytest.fail(
            f"Building `Base.metadata` into a schema of its own raised {failure!r}. That is this "
            "module's own mechanism failing rather than a model that has drifted: every test here "
            "compares what Postgres deparses for the migrated schema with what it deparses for "
            "this copy, and without the copy there is nothing on the model side of the "
            "comparison. Read the error first — a type or an extension the copy needs and the "
            "migrated schema already has is the likeliest cause, and it is a fact about this "
            "fixture rather than about the schema under test."
        )
    return schema


# ---------------------------------------------------------------------------
# The comparison itself, checked before anything is built on it.
# ---------------------------------------------------------------------------


def test_the_stored_expression_comparison_normalises_spelling_and_keeps_meaning(
    db_session: Any,
) -> None:
    """`pg_get_expr` is the normaliser, so it is run against both cases first.

    Every generated-column assertion in this file is "these two deparsed
    expressions are equal", and that assertion is worth exactly what the deparser
    is worth. Two properties are needed and neither is obvious:

      - a **re-spelling** of one expression — different whitespace, different
        capitalisation, redundant parentheses — has to come back *identical*, or
        the test is a tripwire that goes red when somebody tidies a model file;
      - a **changed** expression has to come back *different*, or the test is
        green against the drift it exists to catch.

    Three generated columns on a throwaway table, one plain, one re-spelled, one
    meaning something else. `docs/MISTAKES.md` entry 3: verify by executing it,
    not by reading it. `upper` and `lower` are immutable, which a generation
    expression is required to be.

    **The mutation it exists to survive** is a normaliser being introduced into
    this module — hand-stripped parentheses, a lowercased comparison, a regex —
    that makes `lower(value)` and `upper(value)` compare equal. **The near miss it
    tolerates** is the re-spelling, which must stay green.
    """
    schema = f"drift_selftest_{uuid4().hex[:12]}"
    db_session.execute(text(f'CREATE SCHEMA "{schema}"'))
    db_session.execute(
        text(
            f'CREATE TABLE "{schema}".sample ('
            " value text,"
            " plain text GENERATED ALWAYS AS (upper(value)) STORED,"
            " respelled text GENERATED ALWAYS AS ( UPPER ( ( value ) ) ) STORED,"
            " meaning_changed text GENERATED ALWAYS AS (lower(value)) STORED)"
        )
    )

    stored = generated_expressions(db_session, schema)
    reported = {column: expression for (_, column), expression in stored.items()}

    assert set(reported) == {"plain", "respelled", "meaning_changed"}, (
        f"The generated-column query reports {sorted(reported)} for a table that was just created "
        "with three generated columns. It is not reading what it claims to read, and every "
        "comparison in this module is built on it."
    )
    assert all(reported.values()), (
        f"`pg_get_expr` returned an empty expression for one of {reported}. An empty string on "
        "both sides of a comparison is equal to an empty string, so the tests below would pass "
        "against any pair of generated columns at all."
    )

    assert reported["respelled"] == reported["plain"], (
        f"`upper(value)` deparsed to {reported['plain']!r} and "
        f"`UPPER ( ( value ) )` to {reported['respelled']!r}. Postgres is expected to be the "
        "normaliser for this module: the same expression written two ways has to come back once, "
        "or `test_every_generated_column_stores_the_expression_the_model_declares` goes red when "
        "somebody reformats a model file and nothing has drifted."
    )
    assert reported["meaning_changed"] != reported["plain"], (
        f"`upper(value)` and `lower(value)` both deparse to {reported['plain']!r}. The comparison "
        "cannot then tell two different expressions apart, and the generated-column test in this "
        "file is green against every change to a generation expression — which is the exact state "
        "E0-20 item 3 describes `alembic check` being in."
    )


def test_the_constraint_definition_comparison_normalises_spelling_and_keeps_meaning(
    db_session: Any,
) -> None:
    """The same two properties for `pg_get_constraintdef`, which the constraint tests rest on.

    Same argument as the test above, at the other deparser. A check constraint
    re-spelled must compare equal; a check constraint negated must not. `NOT (…)`
    is the mutation used because it is valid for any boolean expression, so this
    self-test does not depend on which constraints the model happens to declare.

    **The mutation it exists to survive**: a comparison that lowercases or strips
    punctuation until `value <> 'x'` and `NOT (value <> 'x')` are the same string.
    **The near miss it tolerates**: the re-spelling, and the constraint's *name*,
    which `pg_get_constraintdef` does not print — a renamed constraint is already
    detected by `alembic check` on the pinned 1.19 and is not this file's subject.
    """
    schema = f"drift_selftest_{uuid4().hex[:12]}"
    db_session.execute(text(f'CREATE SCHEMA "{schema}"'))
    db_session.execute(text(f'CREATE TABLE "{schema}".sample (value text)'))
    for name, expression in (
        ("plain", "value <> 'x'"),
        ("respelled", "( ( value ) <> 'x' )"),
        ("meaning_changed", "NOT (value <> 'x')"),
    ):
        db_session.execute(
            text(f'ALTER TABLE "{schema}".sample ADD CONSTRAINT {name} CHECK ({expression})')
        )

    definitions = {
        row.constraint_name: row.definition
        for row in db_session.execute(
            text(CONSTRAINT_DEFINITIONS), {"schema": schema, "contype": "c"}
        )
    }

    assert set(definitions) == {"plain", "respelled", "meaning_changed"}, (
        f"The constraint query reports {sorted(definitions)} for a table that was just given three "
        "check constraints. It is not reading what it claims to read, and both constraint tests "
        "below are built on it."
    )
    assert definitions["respelled"] == definitions["plain"], (
        f"`value <> 'x'` deparsed to {definitions['plain']!r} and its re-spelling to "
        f"{definitions['respelled']!r}. One rule written two ways has to come back once, or the "
        "constraint tests below go red on a reformatted model."
    )
    assert definitions["meaning_changed"] != definitions["plain"], (
        f"`value <> 'x'` and `NOT (value <> 'x')` both deparse to {definitions['plain']!r}. The "
        "comparison cannot tell a rule from its negation, so the constraint tests below would be "
        "green against E0-20 item 3a's second row — a check-constraint expression changed with no "
        "migration behind it."
    )


# ---------------------------------------------------------------------------
# Item 1 — generated columns. `alembic check` warns and exits zero.
# ---------------------------------------------------------------------------


def test_the_generated_columns_in_the_database_are_exactly_those_the_model_declares(
    db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """A column is generated in both places or in neither.

    The narrower of the two generated-column tests and the one that has to run
    first: before asking whether two expressions agree, there has to *be* an
    expression on both sides. A model column that has lost its `Computed`, and a
    database column that has lost its generation expression, are the same drift
    seen from the two ends, and both leave `alembic check` reporting no
    operations — a generated column is compared through
    `_compare_computed_default`, which warns rather than failing, because Alembic
    has no `ALTER` it could emit for one.

    Asserted as an equality in both directions. The model side going empty is the
    likelier accident — a `Computed` dropped while editing a model — and it is the
    one a subset comparison would call clean.

    **The mutation it exists to survive**: remove `Computed` from a model column,
    or run `ALTER TABLE course ALTER COLUMN level DROP EXPRESSION` against the
    database. Either leaves every other test in this suite green.
    **The near miss it tolerates**: changing the expression itself, which belongs
    to the next test and does not move this one; and renaming the column, which
    moves both sides together and is caught by `alembic check` as a column
    change.
    """
    declared = set(declared_generated_columns(metadata_tables))
    stored = set(generated_expressions(db_session, MIGRATED_SCHEMA))

    assert declared, (
        "`Base.metadata` declares no generated column at all. E0-05 ships `course.level` as one — "
        "E0-20 item 3 and E0-33 item 1 both name it as the only one today — so either it has lost "
        "its `Computed` (which is this test's subject, and `alembic check` calls it clean) or the "
        "model package was never imported, which "
        "`tests/unit/test_identity_models_registered.py` diagnoses. Without a declared generated "
        "column the comparison below is between two empty sets and passes against anything."
    )

    missing = sorted(declared - stored)
    unexpected = sorted(stored - declared)
    assert not missing and not unexpected, (
        f"Generated in the model and not in the database: {missing}. Generated in the database and "
        f"not in the model: {unexpected}.\n\n"
        "A generated column is the one kind of column drift `alembic check` reports and does not "
        "fail on: it has no `ALTER` to emit, so `_compare_computed_default` raises a `UserWarning` "
        "and the command exits zero (E0-20 item 3). So a `Computed` removed from a model, or an "
        "expression dropped from a column with `ALTER TABLE … DROP EXPRESSION`, reaches `main` "
        "with the drift gate green.\n\n"
        "If a column is genuinely meant to stop being generated, the migration that stops "
        "generating it is what makes both lists empty again."
    )


def test_every_generated_column_stores_the_expression_the_model_declares(
    db_session: Any, metadata_tables: dict[str, Any], model_probe_schema: str
) -> None:
    """E0-33 item 1: the only drift signal a generated column has.

    The expression itself, compared through Postgres rather than through a
    normaliser written here — the model's own DDL is executed into
    `model_probe_schema` and both sides are read back with `pg_get_expr`, so the
    comparison is between two deparsings by one server.
    `test_the_stored_expression_comparison_normalises_spelling_and_keeps_meaning`
    is where that mechanism is checked against a re-spelling and against a
    changed meaning.

    E0-05 spells `course.level`'s expression the way Postgres deparses it, which
    is what makes Alembic's warning fire only on real drift. This test is the same
    signal with the exit code attached.

    **The mutation it exists to survive**: change the expression in the model's
    `Computed` without writing a migration — E0-20 item 3's finding, which
    `alembic check` answers with a warning and a zero exit.
    **The near miss it tolerates**: re-spelling the same expression. Extra
    parentheses, different capitalisation and different whitespace all deparse to
    one string and stay green, so reformatting a model file is not a build
    failure.

    **What it does not cover** (`docs/MISTAKES.md` entry 14): whether the
    expression is *right*. It compares the model with the database, and a wrong
    expression written into both is wrong in both. That is what
    `test_section_date_derivation.py` and the behavioural schema tests are for.
    """
    declared = set(declared_generated_columns(metadata_tables))
    stored = generated_expressions(db_session, MIGRATED_SCHEMA)
    from_model = generated_expressions(db_session, model_probe_schema)

    assert declared, (
        "`Base.metadata` declares no generated column, so this test compared nothing. "
        "`test_the_generated_columns_in_the_database_are_exactly_those_the_model_declares` "
        "diagnoses that."
    )

    unbuilt = sorted(key for key in declared if key not in from_model)
    assert not unbuilt, (
        f"{unbuilt} is declared as a generated column in `Base.metadata` and is not generated in "
        f"the copy of that metadata built in `{model_probe_schema}`. That is this module's own "
        "mechanism failing rather than drift — the model side of the comparison is missing, so a "
        "comparison against it would pass whatever the migrated schema holds."
    )
    absent = sorted(key for key in declared if key not in stored)
    assert not absent, (
        f"{absent} is generated in the model and is not a generated column in `{MIGRATED_SCHEMA}`. "
        "`test_the_generated_columns_in_the_database_are_exactly_those_the_model_declares` is "
        "where that is diagnosed; this test is about what the expression says, and there is no "
        "expression on one side."
    )
    blank = sorted(key for key in declared if not stored[key] or not from_model[key])
    assert not blank, (
        f"`pg_get_expr` returned nothing for {blank} on one side or the other, and two empty "
        "strings compare equal. The column is marked generated and has no stored expression, "
        "which is a broken read rather than a passing comparison."
    )

    drifted = {
        key: f"the database stores {stored[key]!r}, the model says {from_model[key]!r}"
        for key in sorted(declared)
        if stored[key] != from_model[key]
    }
    assert not drifted, (
        f"{drifted}.\n\n"
        "Both strings above were deparsed by this same server — the model's spelling was executed "
        "into a throwaway schema for exactly that reason — so the difference is in what the "
        "expressions *mean*, not in how they are written. E0-20 item 3: Alembic has no `ALTER` to "
        "emit for a generated column, so `_compare_computed_default` normalises both expressions, "
        "emits a `UserWarning` when they differ, and `alembic check` still exits zero. This "
        "assertion is the only drift signal a generated column has.\n\n"
        "If the model's expression is the intended one, the migration that changes the column is "
        "what is missing. If the database's is, the model is what is wrong."
    )


# ---------------------------------------------------------------------------
# Item 2 — check-constraint expressions, and exclusion constraints entirely.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", CONSTRAINT_KINDS, ids=[kind.label for kind in CONSTRAINT_KINDS])
def test_every_constraint_the_model_declares_is_stored_with_the_definition_it_declares(
    db_session: Any, metadata_tables: dict[str, Any], model_probe_schema: str, kind: ConstraintKind
) -> None:
    """E0-33 item 2, model to database: what the model says, the database is carrying.

    Both kinds E0-20 item 3a names, in one test parametrised over them rather than
    two tests with one body, because the assertion is identical and the difference
    is one letter of `contype`. Both are run: a check constraint's *expression* is
    not compared by autogenerate, and an exclusion constraint is not compared at
    all.

    The comparison is per table and by definition text, with the constraint's name
    deliberately outside it. `pg_get_constraintdef` prints the rule and not the
    name, and 1.19's `checkconstraint_byname` already fails `alembic check` on a
    rename — so a rename is somebody else's red and not this one's.

    **The mutation it exists to survive**: change a check constraint's expression
    in the model with no migration behind it (E0-20 item 3a, row two — `alembic
    check` clean); or drop either kind of constraint off the migrated database
    with `ALTER TABLE … DROP CONSTRAINT`, which is the same disagreement from the
    other end.
    **The near miss it tolerates**: renaming a constraint; re-spelling its
    expression with different parentheses, casing or whitespace; and a constraint
    that exists in the database and not in the model, which is the other
    direction's subject and has its own test — a rule stated only in SQL is a
    choice a migration is allowed to make, and this direction does not judge it.

    **What it does not cover**: whether the rule is right. E0-06's `letter ~
    '^[A-Z]$'` refused six of §2.2's twenty seed positions and would have been
    written identically into both sides of this comparison.
    """
    declared = declared_constraints(metadata_tables, kind)
    from_model = constraint_definitions(db_session, model_probe_schema, kind.contype)
    stored = constraint_definitions(db_session, MIGRATED_SCHEMA, kind.contype)

    assert declared, (
        f"`Base.metadata` declares no {kind.label} constraint on any table, so this test compared "
        f"nothing and would report success. {kind.why_one_exists}"
    )
    assert from_model, (
        f"The copy of `Base.metadata` built in `{model_probe_schema}` carries no {kind.label} "
        f"constraint, although the model declares {declared}. That is this module's own mechanism "
        "failing rather than drift: with an empty model side, the comparison below is satisfied by "
        "any database at all."
    )

    missing = {
        table: sorted(definitions - stored.get(table, set()))
        for table, definitions in from_model.items()
        if definitions - stored.get(table, set())
    }
    carried = {table: sorted(stored.get(table, set())) for table in missing}
    assert not missing, (
        f"The model declares these {kind.label} constraints and `{MIGRATED_SCHEMA}` is not "
        f"carrying them: {missing}. What it does carry on those tables: {carried}.\n\n"
        "Both sides were deparsed by this server, so a difference here is a difference in what the "
        "rule says. E0-20 item 3a measured this boundary on the pinned Alembic 1.19: a "
        "check-constraint expression changed reports **clean**, and an exclusion constraint is "
        "invisible to the comparison entirely — while a dropped column, the canary in the same "
        "run, was detected. So neither of these reaches CI as a failure.\n\n"
        "E0-06 is why this is worth a test rather than a review note: it shipped a check "
        "constraint that refused six of the twenty positions in SPEC §2.2's own seed map, and "
        "nothing found out until E0-07 needed one. **The constraint being written into the "
        "migration that creates the table is not coverage** — nothing re-reads it, in either "
        "direction, which is the trap E0-33 names once for all three of its items."
    )


@pytest.mark.parametrize("kind", CONSTRAINT_KINDS, ids=[kind.label for kind in CONSTRAINT_KINDS])
def test_the_database_carries_no_constraint_of_this_kind_the_model_does_not_declare(
    db_session: Any, metadata_tables: dict[str, Any], model_probe_schema: str, kind: ConstraintKind
) -> None:
    """E0-33 item 2, database to model — the direction that catches a *removal*.

    The test above is satisfied by a model that declares nothing: an empty set is
    a subset of anything. That is not a hypothetical weakness, it is precisely
    E0-20 item 3a's first row — "exclusion constraint removed", measured by
    removing it *from the model* and finding `alembic check` clean. A comparison
    that only walks from the model outwards reports clean on the same mutation,
    for the same reason.

    So this is the other direction: every rule of this kind the database is
    carrying is one the model declares. Together the two tests are a set equality,
    written as two tests rather than one because the two directions fail for
    different reasons and a reader needs to know which one it was.

    **The mutation it exists to survive**: remove the `ExcludeConstraint` from the
    model — E0-20 item 3a, row one — or remove a `CheckConstraint` from it. In
    both cases the database keeps the rule, no migration is written, `alembic
    check` reports clean, and every behavioural test stays green because the
    database is still refusing what it always refused.
    **The near miss it tolerates**: renaming a constraint, and re-spelling one, for
    the same reason as the test above — the definition is compared and the name is
    not.

    **What this direction pins that the ticket leaves open**, said out loud
    because it is a decision rather than a reading: it requires a constraint of
    these two kinds to be declared on the model and not only written into a
    migration. E0-20's measurement establishes that both of today's are declared —
    it mutated the model to take them away. If a later migration deliberately
    states a rule in SQL alone, this test is where that decision has to be
    recorded, and the pull request that makes it owes the reason. It is not
    something to relax quietly: an undeclared constraint is invisible to
    autogenerate in both directions, so nothing else in the build would ever
    mention it again.
    """
    declared = declared_constraints(metadata_tables, kind)
    from_model = constraint_definitions(db_session, model_probe_schema, kind.contype)
    stored = constraint_definitions(db_session, MIGRATED_SCHEMA, kind.contype)

    assert stored, (
        f"`{MIGRATED_SCHEMA}` carries no {kind.label} constraint on any table, so this test swept "
        f"nothing. {kind.why_one_exists} A migrated database missing them entirely is a larger "
        "failure than the one this test is about, and "
        "`test_every_constraint_the_model_declares_is_stored_with_the_definition_it_declares` "
        "reports it as such."
    )
    carried = {table: sorted(definitions) for table, definitions in stored.items()}
    assert declared, (
        f"`Base.metadata` declares no {kind.label} constraint while `{MIGRATED_SCHEMA}` carries "
        f"{carried}. {kind.why_one_exists}"
    )

    undeclared = {
        table: sorted(definitions - from_model.get(table, set()))
        for table, definitions in stored.items()
        if definitions - from_model.get(table, set())
    }
    assert not undeclared, (
        f"`{MIGRATED_SCHEMA}` carries these {kind.label} constraints and the model declares no "
        f"rule that deparses to them: {undeclared}.\n\n"
        "Either a rule was removed from a model without a migration behind it — the mutation E0-20 "
        "item 3a measured, which `alembic check` calls clean — or a migration wrote a rule the "
        "model has never known about. The two look identical from here and the fix differs: the "
        "first is a model to repair, the second is a decision to record.\n\n"
        "A constraint of this kind that lives only in SQL is outside autogenerate in both "
        "directions, so from the moment it is undeclared, nothing in this build compares it with "
        "anything ever again."
    )
