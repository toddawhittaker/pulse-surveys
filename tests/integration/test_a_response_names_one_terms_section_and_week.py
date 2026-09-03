"""A response's section and its week belong to the same term — E2-16 criterion 2.

> A cross-term `(section, week)` response insert is refused by the schema; the
> same-term insert is accepted (both directions).

`survey_window` has had this rule since E2-05 (ADR 0018, and
`tests/integration/test_a_survey_window_names_one_terms_section_and_week.py` is
where it is asserted). `response` does not: the epic-boundary data-model review
wrote a response pairing a section in one term with a week in another **by
insert**, and the database took it. This module is the same criterion on the
table that stores what students actually submitted, and the mechanism the ticket
settles is the same one — `response.term_id`, `NOT NULL`, with the two composite
foreign key limbs mirroring `uq_section_id_term_id` and `uq_week_id_term_id`.

**Why it matters beyond tidiness.** SPEC §2.2 puts the week axis inside a term,
so a response keyed to another term's week 3 records a submission against a week
its own section's calendar does not contain — and §3.4's participation is "valid
weeks completed ÷ weeks elapsed to date", a ratio then counted over two
different calendars. `survey_window` refuses the pairing and `response` accepts
it, so today the two tables can disagree about what a week is.

**Both limbs are attempted separately, and each is isolated by the term the
response itself claims.** A test that only ever writes a row disagreeing on both
references cannot say which of the two limbs refused it, so a schema carrying one
of the two would pass. In both refusal tests below the response claims **term
A**, and exactly one of its two references belongs to term B: the limb whose row
is in the other term is the only thing that can refuse, and dropping that limb
turns exactly one of these two tests red.

**Every insert here names its section, its week and its term explicitly.** The
shared seeding walker can fill a composite key by following it, and does so for
every other caller; doing that here would make these tests depend on how the
walker resolves a column with two foreign keys, and a change there would move
what they measure.

**Nothing here names a constraint.** A name in this schema is produced by
`Base.metadata`'s naming convention rather than chosen, so holding one would
report a rename as a regression. What is asserted is the criterion — the server
refuses the row — and, beside it, that the refusal is an integrity violation
rather than a complaint about the statement, so a red cannot be a typo in this
module reading as a schema rule.
"""

from typing import Any

import pytest
from fixtures.supervision import sqlstate_of
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# E2-05 created this table and SPEC §8 lists it. Not this ticket's name.
RESPONSE = "response"

# The three columns the rule is written over. `section_id` and `week_id` are
# E2-05's; `term_id` is what this ticket adds, spelled as `survey_window` spells
# the column carrying the same rule.
SECTION_COLUMN = "section_id"
WEEK_COLUMN = "week_id"
TERM_COLUMN = "term_id"
RESPONSE_KEY_COLUMNS = (SECTION_COLUMN, WEEK_COLUMN, TERM_COLUMN)

# The SQLSTATE class Postgres answers an integrity violation with — foreign key,
# not null, unique, check. Asserted as the class rather than as `23503`, because
# which of them refuses a row is the schema's business: the criterion is that the
# server refused it *for a reason about the data*, and `42703` (undefined column)
# or `42601` (syntax) would mean this module is broken rather than that the rule
# is there.
INTEGRITY_VIOLATION = "23"


def response_table(tables: dict[str, Any]) -> Any:
    """The declared `response` table, or a failure saying it is not there."""
    table = tables.get(RESPONSE)
    if table is None:
        pytest.fail(
            f"There is no `{RESPONSE}` table (what is there: {sorted(tables)}). E2-05 creates it "
            "in `backend/app/models/survey.py`; `tests/integration/test_survey_schema.py` is where "
            "a missing survey table is diagnosed."
        )
    return table


def require_columns(table: Any, names: tuple[str, ...]) -> None:
    """Stop unless `table` has every one of `names`, listing what it does have.

    `term_id` is the one this will report while E2-16 is unbuilt, and that is the
    intended red: the column is the whole of what the ticket adds here, and a
    message naming it is more use than an insert failing on an unknown keyword
    inside the seeding walker.
    """
    absent = [name for name in names if name not in table.c]
    if absent:
        pytest.fail(
            f"`{table.name}` has none of {absent} — it has "
            f"{[column.name for column in table.columns]}. E2-16 adds `{TERM_COLUMN}` to "
            f"`{RESPONSE}`, non-nullable and backfilled from `section.term_id`, and gives the "
            "table the two composite foreign key limbs `survey_window` already carries. Each name "
            "is a constant at the top of this file, so a deliberate rename is a one-line change "
            "here."
        )


def one_terms_section_and_week(seed: Any) -> dict[str, Any]:
    """A section and a week that certainly sit in the same term, with that term.

    Built through one chain, which is what puts them in one term: the walker
    creates the term while building the section's ancestors and the week then
    finds it already there. The term row is returned beside them so a caller can
    name it in a response rather than reading it back off either.
    """
    chain: dict[str, Any] = {}
    section = seed("section", chain)
    week = seed("week", chain)
    return {"section": section, "week": week, "term": chain["term"]}


def write_response(seed: Any, *, section: Any, week: Any, term: Any) -> Any:
    """Insert one `response` naming exactly these three rows.

    The student, the timestamps and the validity are left to the walker: none of
    them is what this module is about, and a value chosen here would be a second
    thing a red could be about.
    """
    return seed(
        RESPONSE,
        {},
        **{
            SECTION_COLUMN: section["id"],
            WEEK_COLUMN: week["id"],
            TERM_COLUMN: term["id"],
        },
    )


def refusal_of(session: Any, write: Any) -> DatabaseError | None:
    """Run `write` inside a savepoint; answer the database error it provoked, or `None`.

    A savepoint rather than the surrounding transaction, so a refused write leaves
    the session usable for the next assertion, and `SET CONSTRAINTS ALL IMMEDIATE`
    for `SupervisionGraph.refusal`'s reason: a rule written as a deferrable
    constraint does not fire until commit, and nothing in this suite commits.
    """
    from sqlalchemy import text

    savepoint = session.begin_nested()
    try:
        write()
        session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    except DatabaseError as refused:
        savepoint.rollback()
        return refused
    savepoint.commit()
    return None


def assert_refused_for_the_data(refused: DatabaseError | None, what: str, why: str) -> None:
    """The write was refused, and refused by a rule about the row rather than about the SQL."""
    assert refused is not None, f"{what} was accepted by the database. {why}"
    state = sqlstate_of(refused)
    assert state is not None and state.startswith(INTEGRITY_VIOLATION), (
        f"{what} was refused with SQLSTATE {state!r}: {refused}. An integrity violation is class "
        f"{INTEGRITY_VIOLATION}; anything else means this module built a statement the server "
        "could not run, so the refusal says nothing about the rule under test."
    )


def test_the_helper_builds_a_section_and_a_week_that_really_share_a_term(seed_rows: Any) -> None:
    """The control on this module's own machinery, and it is green today.

    Every test below rests on `one_terms_section_and_week` producing a section and
    a week of **one** term: the accepted case is only meaningful if they agree,
    and each refused case is only isolated to one limb if the other limb is
    satisfied. The helper gets that by sharing a chain, which is a property of the
    seeding walker rather than of anything this file wrote — so it is asserted
    rather than assumed, and asserted here where the failure says "the helper"
    instead of surfacing as a refused control three tests later.

    Green before E2-16 lands and green after: it names `section.term_id` and
    `week.term_id`, both of which E0-06 built, and no column this ticket adds.
    """
    rows = one_terms_section_and_week(seed_rows)

    term = rows["term"]["id"]
    assert rows["section"][TERM_COLUMN] == term, (
        f"The seeded section belongs to term {rows['section'][TERM_COLUMN]} and the helper reports "
        f"{term}. Every response written in this module names that term, so a mismatch here would "
        "make the accepted case a cross-term response and both refusals ambiguous."
    )
    assert rows["week"][TERM_COLUMN] == term, (
        f"The seeded week belongs to term {rows['week'][TERM_COLUMN]} and the helper reports "
        f"{term}. The two rows are seeded through one chain precisely so they land in one term; if "
        "they do not, this module is measuring two cross-term responses and calling one of them "
        "the control."
    )


def test_a_response_whose_section_and_week_share_a_term_is_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The ordinary submission, and the control both refusals below depend on.

    A test of its own as well as a guard inside each refusal, because a schema
    that refused every response would satisfy both refusals perfectly and would
    also make E2-08's submit path unable to store a single row
    (`docs/MISTAKES.md` entry 3). This is the failure that would name that.

    **The mutation it kills:** a composite key written against the wrong
    referenced columns, or a `term_id` that references `term` directly while
    `section_id` and `week_id` go on referencing `section (id)` and `week (id)` —
    either leaves the honest row refused or the dishonest row accepted, and this
    half catches the first.
    """
    require_columns(response_table(metadata_tables), RESPONSE_KEY_COLUMNS)

    rows = one_terms_section_and_week(seed_rows)
    refused = refusal_of(
        db_session,
        lambda: write_response(
            seed_rows, section=rows["section"], week=rows["week"], term=rows["term"]
        ),
    )

    assert refused is None, (
        f"A response naming a section and a week of one term, and claiming that term, was "
        f"refused: {refused}. That is every submission E2-08 stores — SPEC §8 gives one response "
        "per student per section per week — so a schema that refuses it refuses the weekly survey, "
        "and the two refusals in this module would then be evidence of nothing."
    )


def test_a_response_whose_week_belongs_to_another_term_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 2, the week limb: `(week_id, term_id) → week (id, term_id)`.

    The response claims term A and names a section of term A, so the section limb
    is satisfied; its week belongs to term B, so no `week` row carries that id
    with term A and the week limb is the only thing that can refuse it. **The
    section limb being satisfied is the whole design of the case**: a response
    disagreeing with its term on both references would be refused by either limb
    alone, and a schema carrying only one of the two would pass it.

    **The control is a response over term A's own week**, so a refusal here
    cannot be about responses being unwritable.

    **The mutation it kills:** shipping the section limb and leaving `week_id` a
    plain foreign key — which is also what the table has today, with neither
    limb: the boundary review wrote exactly this row and the database took it.
    """
    require_columns(response_table(metadata_tables), RESPONSE_KEY_COLUMNS)

    home = one_terms_section_and_week(seed_rows)
    elsewhere = one_terms_section_and_week(seed_rows)
    assert elsewhere["term"]["id"] != home["term"]["id"], (
        "The second chain was seeded into the same term as the first, so its week is not from "
        "another term and this test would attempt an ordinary response. The walker shares only the "
        "single institution row between chains; a shared term means that has changed."
    )

    control = refusal_of(
        db_session,
        lambda: write_response(
            seed_rows, section=home["section"], week=home["week"], term=home["term"]
        ),
    )
    assert control is None, (
        f"The control response — a section and a week of one term — was refused: {control}. Until "
        "an ordinary response inserts, the refusal below says nothing about the week's term."
    )

    crossed = refusal_of(
        db_session,
        lambda: write_response(
            seed_rows, section=home["section"], week=elsewhere["week"], term=home["term"]
        ),
    )
    assert_refused_for_the_data(
        crossed,
        "A response pairing a section of one term with a week of another",
        f"E2-16's criterion 2: the composite key `({WEEK_COLUMN}, {TERM_COLUMN})` finds no week of "
        "this response's term with that id. The response's section is in the term it claims, so "
        "the section limb accepts this row — only the week limb can refuse it, which is why a "
        "schema carrying one composite key and one plain foreign key fails here and passes "
        "everywhere else. `survey_window` has refused this pairing since E2-05; the table holding "
        "what students submitted does not.",
    )


def test_a_response_whose_section_belongs_to_another_term_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 2, the section limb: `(section_id, term_id) → section (id, term_id)`.

    The mirror of the test above and the reason the criterion says "both
    directions". The response claims term A and names a week of term A, so the
    week limb is satisfied; its section belongs to term B, so the section limb is
    the only thing that can refuse it.

    **The mutation it kills:** shipping the week limb and leaving `section_id` a
    plain foreign key — and, one step further out, dropping `UNIQUE (id,
    term_id)` from `section`, which is what the section limb references and
    without which it cannot exist at all.

    A section belongs to exactly one term (SPEC §8, and E0-06 landed
    `section.term_id` to say so), so a response naming another term's section is
    a submission for a section that was not running then.
    """
    require_columns(response_table(metadata_tables), RESPONSE_KEY_COLUMNS)

    home = one_terms_section_and_week(seed_rows)
    elsewhere = one_terms_section_and_week(seed_rows)
    assert elsewhere["term"]["id"] != home["term"]["id"], (
        "The second chain was seeded into the same term as the first, so its section is not from "
        "another term and this test would attempt an ordinary response."
    )

    control = refusal_of(
        db_session,
        lambda: write_response(
            seed_rows, section=home["section"], week=home["week"], term=home["term"]
        ),
    )
    assert control is None, (
        f"The control response — a section and a week of one term — was refused: {control}. Until "
        "an ordinary response inserts, the refusal below says nothing about the section's term."
    )

    crossed = refusal_of(
        db_session,
        lambda: write_response(
            seed_rows, section=elsewhere["section"], week=home["week"], term=home["term"]
        ),
    )
    assert_refused_for_the_data(
        crossed,
        "A response naming a section of one term and a week of another",
        f"The composite key `({SECTION_COLUMN}, {TERM_COLUMN})` finds no section of this "
        "response's term with that id. The response's week is in the term it claims, so the week "
        "limb accepts this row — only the section limb can refuse it.",
    )


def test_a_response_cannot_be_written_without_a_term(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """`response.term_id` is NOT NULL, and that is what makes both limbs bite.

    **This is not a tidiness test.** A composite foreign key in Postgres is
    `MATCH SIMPLE` unless it says otherwise, and `MATCH SIMPLE` skips the check
    entirely when *any* column of the key is null. So a nullable `term_id` gives
    every writer a way to store the exact row criterion 2 refuses: leave the term
    out, and neither limb is evaluated. The two refusals above would go on
    passing, because they supply a term; nothing in this repository would say the
    door was open.

    **The control is an ordinary response**, written first through the same
    helper, so the refusal is known to be about the null rather than about
    anything else in the row.

    **The mutation it kills:** declaring `term_id` nullable — which is also the
    shape a "make the migration easier" change takes, since `response` may
    already hold rows and a nullable column needs no backfill.
    """
    require_columns(response_table(metadata_tables), RESPONSE_KEY_COLUMNS)

    rows = one_terms_section_and_week(seed_rows)
    control = refusal_of(
        db_session,
        lambda: write_response(
            seed_rows, section=rows["section"], week=rows["week"], term=rows["term"]
        ),
    )
    assert control is None, (
        f"The control response was refused: {control}. Until an ordinary response inserts, the "
        "refusal below says nothing about the null."
    )

    without_a_term = refusal_of(
        db_session,
        lambda: seed_rows(
            RESPONSE,
            {},
            **{
                SECTION_COLUMN: rows["section"]["id"],
                WEEK_COLUMN: rows["week"]["id"],
                TERM_COLUMN: None,
            },
        ),
    )
    assert_refused_for_the_data(
        without_a_term,
        f"A response written with `{TERM_COLUMN}` null",
        "Postgres evaluates a composite foreign key under `MATCH SIMPLE`, which skips the check "
        "when any column of the key is null — so a nullable term column is a documented way around "
        "both of the rules criterion 2 is about, and the two cross-term tests above would go on "
        "passing while every response written that way escaped them. E2-16 makes the column "
        "non-nullable, backfilled from `section.term_id`.",
    )
