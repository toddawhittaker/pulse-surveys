"""The two response records are append-only, as production runs them — E7-01, done-when 1.

> Through the production connection, `pulse_app` can insert the listed columns of
> each table and read them, and cannot update or delete a row (MISTAKES entry 46).

And the rules the ticket and work order put on the rows themselves: `role` and
`mode` hold their vocabularies (decision 4), the text is non-blank and bounded by
one constant, `RESPONSE_TEXT_MAX = 4000`, checked in a `CHECK` that mirrors it,
`ai_seeded` is `NOT NULL`, `sequence` is the database's ("so that 'latest' is
insert order", ADR 0187), and the author is a `person` key with `RESTRICT`.

**The listed columns are found, not spelled.** The ticket lists each table's
columns by meaning; it spells `role`, `mode`, `ai_seeded`, `week_id` and
`sequence` and no other. So "every listed column" is every column but the primary
key and `sequence` — the two the database assigns — and each reference is filled
from the table its key points at. A column of a type this module cannot fill is a
failure naming it, not a guess.

**Privileges are asked twice**: of the catalog (`has_column_privilege`), and of a
real statement on `pulse_app`'s own connection (`application_session`), whose
refusal is read by SQLSTATE — 42501 — so a missing table or column (42P01, 42703)
is never mistaken for a refused one. Each catalog absence has a control finding a
privilege `pulse_app` certainly holds (`docs/MISTAKES.md` entry 35).

**Which failure a red is, before E7-01 lands.** `require_the_tables` fails naming
`instructor_response` and `response_policy`.
"""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from fixtures.staff_names import (
    AI_SEEDED_COLUMN,
    CHECK_VIOLATION,
    FOREIGN_KEY_VIOLATION,
    INSTRUCTOR_RESPONSE,
    INSUFFICIENT_PRIVILEGE,
    MODE_COLUMN,
    NOT_NULL_VIOLATION,
    PERSON_TABLE,
    POLICY_MODES,
    POLICY_ROLES,
    RESPONSE_POLICY,
    RESPONSE_ROLES,
    RESPONSE_TEXT_MAX,
    ROLE_COLUMN,
    SEQUENCE_COLUMN,
    require_the_application_role,
    require_the_tables,
    sqlstate,
    the_text_bound,
)
from fixtures.supervision import foreign_key_columns, seed_row, stored_type
from sqlalchemy import Boolean, Date, DateTime, Integer, String, text

pytestmark = pytest.mark.integration

RECORDS = (INSTRUCTOR_RESPONSE, RESPONSE_POLICY)
VOCABULARY = {
    INSTRUCTOR_RESPONSE: {ROLE_COLUMN: RESPONSE_ROLES},
    RESPONSE_POLICY: {ROLE_COLUMN: POLICY_ROLES, MODE_COLUMN: POLICY_MODES},
}
# Tokens outside each vocabulary, one level out: a real role the other table
# admits, or a near spelling.
OUTSIDE = {
    (INSTRUCTOR_RESPONSE, ROLE_COLUMN): ("DEAN", "STUDENT", "lead_faculty"),
    (RESPONSE_POLICY, ROLE_COLUMN): ("INSTRUCTOR", "DEAN"),
    (RESPONSE_POLICY, MODE_COLUMN): ("OPTIONAL", "required"),
}
# The only identity-like failure an INSERT naming a database-assigned column may
# answer besides 42501: "cannot insert a non-DEFAULT value into column", raised
# for `GENERATED ALWAYS` before any privilege is checked. Either means the caller
# cannot choose the value.
GENERATED_ALWAYS = "428C9"

HAS_COLUMN_PRIVILEGE = "SELECT has_column_privilege(:relation, :column, :privilege)"
HAS_TABLE_PRIVILEGE = "SELECT has_table_privilege(:relation, :privilege)"


# ---------------------------------------------------------------------------
# Building a whole row without spelling a column the ticket did not.
# ---------------------------------------------------------------------------


def assigned_by_the_database(table: Any) -> set[str]:
    return {column.name for column in table.primary_key.columns} | {SEQUENCE_COLUMN}


def text_columns(table: Any) -> list[str]:
    """The free-text columns: string-typed, not a reference, not a vocabulary."""
    spelled = set(VOCABULARY.get(table.name, {}))
    return [
        column.name
        for column in table.columns
        if isinstance(stored_type(column), String)
        and not column.foreign_keys
        and column.name not in spelled
        and column.name not in assigned_by_the_database(table)
    ]


def the_text_column(table: Any) -> str:
    found = text_columns(table)
    if len(found) != 1:
        pytest.fail(
            f"`{table.name}` has {len(found)} free-text columns ({found}); the ticket lists one, "
            "the response text."
        )
    return found[0]


def a_whole_row(session: Any, tables: dict[str, Any], table: Any, chain: dict[str, Any]) -> dict:
    """A value for every column but the database's two, references filled from `chain`."""
    values: dict[str, Any] = {}
    for column in table.columns:
        if column.name in assigned_by_the_database(table):
            continue
        vocabulary = VOCABULARY.get(table.name, {}).get(column.name)
        if column.foreign_keys:
            key = sorted(column.foreign_keys, key=lambda fk: str(fk.target_fullname))[0]
            target = key.column.table.name
            if target not in chain:
                chain[target] = seed_row(session, tables, target, chain)
            values[column.name] = chain[target][key.column.name]
        elif vocabulary is not None:
            values[column.name] = vocabulary[0]
        else:
            kind = stored_type(column)
            if isinstance(kind, Boolean):
                values[column.name] = False
            elif isinstance(kind, DateTime):
                values[column.name] = datetime.now(UTC)
            elif isinstance(kind, Date):
                values[column.name] = date.today()
            elif isinstance(kind, String):
                values[column.name] = f"E7-01 {table.name}.{column.name} written as pulse_app"
            elif isinstance(kind, Integer):
                values[column.name] = 1
            else:
                pytest.fail(
                    f"`{table.name}.{column.name}` is a {column.type!r}; this module fills booleans, "
                    "instants, dates, strings, integers and references, and the ticket lists no "
                    "other kind of column."
                )
    return values


def parents(committed_rows: Any, tables: dict[str, Any]) -> dict[str, Any]:
    """A section with its whole chain and a person, committed — what a row references."""
    chain: dict[str, Any] = {}
    committed_rows.seed("section", chain)
    chain[PERSON_TABLE] = committed_rows.seed(PERSON_TABLE, {})
    committed_rows.commit()
    return chain


def attempted(session: Any, statement: Any, parameters: dict | None = None) -> Any:
    """Run `statement` in a savepoint that is always rolled back; its error, or `None`."""
    from sqlalchemy.exc import DatabaseError

    savepoint = session.begin_nested()
    try:
        if isinstance(statement, str):
            session.execute(text(statement), parameters or {})
        else:
            session.execute(statement)
    except DatabaseError as failure:
        savepoint.rollback()
        return failure
    savepoint.rollback()
    return None


def a_committed_row(committed_rows: Any, tables: dict[str, Any], name: str) -> dict[str, Any]:
    """One whole row of `name`, written by the superuser and committed."""
    table = tables[name]
    chain = parents(committed_rows, tables)
    values = a_whole_row(committed_rows.session, tables, table, chain)
    row = (
        committed_rows.session.execute(table.insert().values(**values).returning(*table.columns))
        .mappings()
        .one()
    )
    committed_rows.commit()
    return dict(row)


# ---------------------------------------------------------------------------
# Through the production connection.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", RECORDS)
def test_the_application_connection_inserts_every_listed_column_and_reads_the_row_back(
    name: str, committed_rows: Any, metadata_tables: dict[str, Any], application_session: Any
) -> None:
    """`pulse_app` inserts a row naming every column but the database's two, then reads it back.

    **The mutation this kills:** the grants file withholding a listed column (the
    author, the role, `ai_seeded`) or `SELECT`, which a suite driving the writer
    through the migrating engine never notices (`docs/MISTAKES.md` entry 46).
    """
    require_the_tables(metadata_tables)
    require_the_application_role(application_session)
    table = metadata_tables[name]
    chain = parents(committed_rows, metadata_tables)
    values = a_whole_row(committed_rows.session, metadata_tables, table, chain)
    committed_rows.commit()

    from sqlalchemy.exc import DatabaseError

    try:
        application_session.execute(table.insert().values(**values))
        application_session.commit()
    except DatabaseError as failure:
        application_session.rollback()
        pytest.fail(
            f"`pulse_app` could not insert a `{name}` row naming {sorted(values)} "
            f"(SQLSTATE {sqlstate(failure)}): {failure}\n\nE7-01: '`pulse_app` gets `SELECT` and "
            "column-grain `INSERT` on both' — every listed column."
        )
    person_column = foreign_key_columns(table, PERSON_TABLE)
    assert len(person_column) == 1, f"`{name}` references `person` {len(person_column)} times."
    read = (
        application_session.execute(
            table.select().where(table.c[person_column[0]] == values[person_column[0]])
        )
        .mappings()
        .all()
    )
    application_session.rollback()
    assert len(read) == 1, f"`pulse_app` read back {len(read)} rows of the one it inserted."
    for column, value in values.items():
        if isinstance(value, datetime):
            continue
        assert (
            read[0][column] == value
        ), f"`{name}.{column}` came back {read[0][column]!r}; `pulse_app` wrote {value!r}."


@pytest.mark.parametrize("name", RECORDS)
def test_the_application_connection_may_update_no_column_of_a_record(
    name: str, committed_rows: Any, metadata_tables: dict[str, Any], application_session: Any
) -> None:
    """No `UPDATE` on any column, and a real `UPDATE` is refused with 42501.

    **The control:** the same catalog probe finds `UPDATE` on `enrollment.ended_on`,
    which `pulse_app` holds (E1-11).

    **The mutation this kills:** `UPDATE` granted on the table, or on one column
    (the text, the mode), which turns "every edit is a new row" (ruling 3) and
    "these tables are the record" (ruling 7) into conventions.
    """
    require_the_tables(metadata_tables)
    require_the_application_role(application_session)
    table = metadata_tables[name]
    row = a_committed_row(committed_rows, metadata_tables, name)

    def may(relation: str, column: str, privilege: str) -> bool:
        held = application_session.execute(
            text(HAS_COLUMN_PRIVILEGE),
            {"relation": f"public.{relation}", "column": column, "privilege": privilege},
        ).scalar_one()
        application_session.rollback()
        return bool(held)

    assert may(
        "enrollment", "ended_on", "UPDATE"
    ), "The control: the probe does not find `pulse_app`'s `UPDATE` on `enrollment.ended_on`."
    updatable = [column.name for column in table.columns if may(name, column.name, "UPDATE")]
    assert not updatable, f"`pulse_app` may update `{name}` columns {updatable}."

    key = next(iter(table.primary_key.columns)).name
    vocabulary = VOCABULARY[name][ROLE_COLUMN]
    failure = attempted(
        application_session,
        table.update().where(table.c[key] == row[key]).values(**{ROLE_COLUMN: vocabulary[-1]}),
    )
    application_session.rollback()
    assert failure is not None and sqlstate(failure) == INSUFFICIENT_PRIVILEGE, (
        f"`pulse_app`'s `UPDATE` of a `{name}` row answered "
        f"{'nothing — it succeeded' if failure is None else sqlstate(failure)}, not 42501."
    )


@pytest.mark.parametrize("name", RECORDS)
def test_the_application_connection_may_not_delete_or_truncate_a_record(
    name: str, committed_rows: Any, metadata_tables: dict[str, Any], application_session: Any
) -> None:
    """`DELETE` and `TRUNCATE` are refused with 42501; the row is still there.

    **The control:** the probe finds `pulse_app`'s `DELETE` on `lti_launch_nonce`.

    **The mutation this kills:** `DELETE` granted for a tidy-up, which lets the
    connection every screen runs on erase a published response or a policy change.
    """
    require_the_tables(metadata_tables)
    require_the_application_role(application_session)
    table = metadata_tables[name]
    row = a_committed_row(committed_rows, metadata_tables, name)

    def may(relation: str, privilege: str) -> bool:
        held = application_session.execute(
            text(HAS_TABLE_PRIVILEGE), {"relation": f"public.{relation}", "privilege": privilege}
        ).scalar_one()
        application_session.rollback()
        return bool(held)

    assert may("lti_launch_nonce", "DELETE"), "The control: the probe misses a held `DELETE`."
    assert not may(name, "DELETE") and not may(
        name, "TRUNCATE"
    ), f"`pulse_app` may delete or truncate `{name}`."
    key = next(iter(table.primary_key.columns)).name
    for statement in (
        table.delete().where(table.c[key] == row[key]),
        f"TRUNCATE public.{name}",
    ):
        failure = attempted(application_session, statement)
        application_session.rollback()
        assert failure is not None and sqlstate(failure) == INSUFFICIENT_PRIVILEGE, (
            f"`pulse_app` ran {statement} on `{name}` and was answered "
            f"{'nothing — it succeeded' if failure is None else sqlstate(failure)}, not 42501."
        )


@pytest.mark.parametrize("name", RECORDS)
def test_the_application_connection_cannot_choose_a_rows_sequence(
    name: str, committed_rows: Any, metadata_tables: dict[str, Any], application_session: Any
) -> None:
    """An `INSERT` naming `sequence` is refused; the same row without it is accepted.

    **The mutation this kills:** `INSERT` granted table-wide, so the application
    can write a row "before" another and change which response is the latest.
    **The near miss:** the same insert without `sequence`, which must succeed.
    """
    require_the_tables(metadata_tables)
    require_the_application_role(application_session)
    table = metadata_tables[name]
    assert SEQUENCE_COLUMN in table.c, f"`{name}` has no `{SEQUENCE_COLUMN}` column."
    chain = parents(committed_rows, metadata_tables)
    values = a_whole_row(committed_rows.session, metadata_tables, table, chain)
    committed_rows.commit()

    accepted = attempted(application_session, table.insert().values(**values))
    application_session.rollback()
    assert accepted is None, f"The near miss: `pulse_app`'s plain insert was refused: {accepted}."
    refused = attempted(
        application_session, table.insert().values(**values, **{SEQUENCE_COLUMN: 1})
    )
    application_session.rollback()
    assert refused is not None and sqlstate(refused) in (
        INSUFFICIENT_PRIVILEGE,
        GENERATED_ALWAYS,
    ), (
        f"`pulse_app` inserted a `{name}` row choosing its own `{SEQUENCE_COLUMN}` and was "
        f"answered {'nothing' if refused is None else sqlstate(refused)}. The ticket: 'a "
        "database-assigned `sequence` column so that \"latest\" is insert order'."
    )


@pytest.mark.parametrize("name", RECORDS)
def test_a_later_insert_carries_a_larger_sequence(
    name: str, committed_rows: Any, metadata_tables: dict[str, Any], application_session: Any
) -> None:
    """Two rows written one after the other by `pulse_app`: the second's `sequence` is larger.

    **The mutation this kills:** `sequence` with no default the application can
    rely on, or a default that is not monotonic (a random key named `sequence`).
    """
    require_the_tables(metadata_tables)
    require_the_application_role(application_session)
    table = metadata_tables[name]
    chain = parents(committed_rows, metadata_tables)
    values = a_whole_row(committed_rows.session, metadata_tables, table, chain)
    committed_rows.commit()
    person_column = foreign_key_columns(table, PERSON_TABLE)[0]

    def sequences_so_far() -> set[Any]:
        committed_rows.session.rollback()
        found = {
            row[0]
            for row in committed_rows.session.execute(
                table.select()
                .with_only_columns(table.c[SEQUENCE_COLUMN])
                .where(table.c[person_column] == values[person_column])
            )
        }
        committed_rows.session.rollback()
        return found

    application_session.execute(table.insert().values(**values))
    application_session.commit()
    first = sequences_so_far()
    application_session.execute(table.insert().values(**values))
    application_session.commit()
    second = sequences_so_far() - first
    assert len(first) == 1 and len(second) == 1, (
        f"Two `{name}` rows written one after the other carry `{SEQUENCE_COLUMN}` values {first} "
        f"and {second}; each row carries one, and no two rows share one."
    )
    assert next(iter(second)) > next(iter(first)), (
        f"The later `{name}` row carries `{SEQUENCE_COLUMN}` {second}, the earlier {first}; the "
        "later row's is larger (ADR 0187's insert order)."
    )


# ---------------------------------------------------------------------------
# What the rows themselves may hold. Written as the superuser, inside a
# transaction that is rolled back: these are the table's rules, not a grant's.
# ---------------------------------------------------------------------------


def a_row_in(db_session: Any, tables: dict[str, Any], name: str, **overrides: Any) -> Any:
    """Insert one row of `name` with `overrides`; the error it raised, or `None`."""
    table = tables[name]
    chain: dict[str, Any] = {}
    seed_row(db_session, tables, "section", chain)
    chain[PERSON_TABLE] = seed_row(db_session, tables, PERSON_TABLE, {})
    values = a_whole_row(db_session, tables, table, chain)
    values.update(overrides)
    return attempted(db_session, table.insert().values(**values))


SETTLED_TOKENS = [
    (name, column, token)
    for name, columns in VOCABULARY.items()
    for column, tokens in columns.items()
    for token in tokens
]


@pytest.mark.parametrize(("name", "column", "token"), SETTLED_TOKENS)
def test_every_token_of_a_vocabulary_is_accepted(
    name: str, column: str, token: str, db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """Each settled token is a legal row (work order decision 4).

    **The mutation this kills:** a vocabulary `CHECK` missing a token — `CHAIR` on
    a response, which SPEC §5.3's chair-acting-as-lead needs.
    """
    require_the_tables(metadata_tables)
    failure = a_row_in(db_session, metadata_tables, name, **{column: token})
    assert failure is None, f"A `{name}` row with `{column}` = {token!r} was refused: {failure}"


@pytest.mark.parametrize(
    ("name", "column", "token"),
    [(name, column, token) for (name, column), tokens in OUTSIDE.items() for token in tokens],
)
def test_a_token_outside_a_vocabulary_is_refused_by_a_check(
    name: str, column: str, token: str, db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """One level out: a real role the other table admits, or a lowercase spelling — 23514.

    **The mutation this kills:** no `CHECK` (any text accepted), and a policy
    `role` vocabulary copied from the response's, which admits `INSTRUCTOR` — an
    instructor sets no policy (SPEC §5.3).
    """
    require_the_tables(metadata_tables)
    failure = a_row_in(db_session, metadata_tables, name, **{column: token})
    assert failure is not None and sqlstate(failure) == CHECK_VIOLATION, (
        f"A `{name}` row with `{column}` = {token!r} was answered "
        f"{'nothing — accepted' if failure is None else sqlstate(failure)}, not 23514."
    )


def test_the_text_bound_is_one_constant_of_four_thousand(metadata_tables: dict[str, Any]) -> None:
    """`RESPONSE_TEXT_MAX` exists, is 4000, and has one value (the ticket: 'one constant').

    **The mutation this kills:** the bound written as a literal in the `CHECK`
    and a different literal in a schema, with no constant to tie them.
    """
    require_the_tables(metadata_tables)
    assert the_text_bound() == RESPONSE_TEXT_MAX


def test_text_at_the_bound_is_accepted(db_session: Any, metadata_tables: dict[str, Any]) -> None:
    """Exactly `RESPONSE_TEXT_MAX` characters: accepted. The permitted half of the boundary pair.

    **The mutation this kills:** an off-by-one bound (`< 4000`).
    """
    require_the_tables(metadata_tables)
    column = the_text_column(metadata_tables[INSTRUCTOR_RESPONSE])
    failure = a_row_in(
        db_session, metadata_tables, INSTRUCTOR_RESPONSE, **{column: "a" * RESPONSE_TEXT_MAX}
    )
    assert failure is None, f"A response of exactly {RESPONSE_TEXT_MAX} characters was refused."


def test_text_one_past_the_bound_is_refused_by_the_check(
    db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """`RESPONSE_TEXT_MAX + 1` characters: refused with 23514. The refused half of the pair.

    **The mutation this kills:** no bound in the database (the bound only in a
    request schema), and a bound off by one the other way (`<= 4001`).
    """
    require_the_tables(metadata_tables)
    column = the_text_column(metadata_tables[INSTRUCTOR_RESPONSE])
    failure = a_row_in(
        db_session, metadata_tables, INSTRUCTOR_RESPONSE, **{column: "a" * (RESPONSE_TEXT_MAX + 1)}
    )
    assert failure is not None and sqlstate(failure) == CHECK_VIOLATION, (
        f"A response of {RESPONSE_TEXT_MAX + 1} characters was answered "
        f"{'nothing — accepted' if failure is None else sqlstate(failure)}, not the `CHECK`'s 23514."
    )


@pytest.mark.parametrize("blank", ["", "   "], ids=["empty", "spaces"])
def test_blank_text_is_refused_by_the_check(
    blank: str, db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """Empty, or nothing but spaces: 23514 (the ticket: 'The text is non-blank').

    **The mutation this kills:** `length(text) > 0` alone, which admits spaces.
    """
    require_the_tables(metadata_tables)
    column = the_text_column(metadata_tables[INSTRUCTOR_RESPONSE])
    failure = a_row_in(db_session, metadata_tables, INSTRUCTOR_RESPONSE, **{column: blank})
    assert failure is not None and sqlstate(failure) == CHECK_VIOLATION, (
        f"A response of {blank!r} was answered "
        f"{'nothing — accepted' if failure is None else sqlstate(failure)}, not 23514."
    )


def test_one_visible_character_is_enough_text(
    db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """The near miss for the blank rule: `' x '` is accepted.

    **The mutation this kills:** a blank rule written as a minimum length above
    one, or as "no surrounding spaces".
    """
    require_the_tables(metadata_tables)
    column = the_text_column(metadata_tables[INSTRUCTOR_RESPONSE])
    failure = a_row_in(db_session, metadata_tables, INSTRUCTOR_RESPONSE, **{column: " x "})
    assert failure is None, f"A response of ' x ' was refused: {failure}"


def test_ai_seeded_may_not_be_null(db_session: Any, metadata_tables: dict[str, Any]) -> None:
    """`ai_seeded` is `NOT NULL` (work order decision 4): a null is refused with 23502.

    **The mutation this kills:** a nullable flag, under which "was this seeded
    from an AI draft?" has a third answer nobody chose.
    """
    require_the_tables(metadata_tables)
    failure = a_row_in(db_session, metadata_tables, INSTRUCTOR_RESPONSE, **{AI_SEEDED_COLUMN: None})
    assert failure is not None and sqlstate(failure) == NOT_NULL_VIOLATION, (
        f"A response with a null `{AI_SEEDED_COLUMN}` was answered "
        f"{'nothing — accepted' if failure is None else sqlstate(failure)}, not 23502."
    )


def test_a_person_who_wrote_a_response_cannot_be_deleted(
    db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """The author key is `RESTRICT`: deleting the author is refused (23503); a stranger deletes.

    **The mutation this kills:** `ON DELETE CASCADE` (the response vanishes with
    its author) or `SET NULL` (it stays, attributed to nobody — SPEC §5.3 never
    publishes without a named human).
    """
    require_the_tables(metadata_tables)
    table = metadata_tables[INSTRUCTOR_RESPONSE]
    person = metadata_tables[PERSON_TABLE]
    person_key = next(iter(person.primary_key.columns)).name
    chain: dict[str, Any] = {}
    seed_row(db_session, metadata_tables, "section", chain)
    chain[PERSON_TABLE] = seed_row(db_session, metadata_tables, PERSON_TABLE, {})
    author = chain[PERSON_TABLE][person_key]
    row = a_whole_row(db_session, metadata_tables, table, chain)
    db_session.execute(table.insert().values(**row))
    stranger = seed_row(db_session, metadata_tables, PERSON_TABLE, {})[person_key]

    near_miss = attempted(db_session, person.delete().where(person.c[person_key] == stranger))
    assert near_miss is None, f"The near miss: deleting a person who wrote nothing: {near_miss}"
    failure = attempted(db_session, person.delete().where(person.c[person_key] == author))
    assert failure is not None and sqlstate(failure) == FOREIGN_KEY_VIOLATION, (
        "Deleting the author of a response was answered "
        f"{'nothing — it succeeded' if failure is None else sqlstate(failure)}, not 23503."
    )
