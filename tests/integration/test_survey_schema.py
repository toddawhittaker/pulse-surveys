"""The survey tables are enforced by Postgres — ticket E2-05.

Acceptance criteria 1 and 5, and the constraints the ticket's Scope carries into
criterion 1's "with the constraints above". Criterion 2 — the survey window's
term rule — is a module of its own,
`test_a_survey_window_names_one_terms_section_and_week.py`, because it is about
a table E0-06 built rather than about the four this ticket creates. Criterion 3
is the seed, and it extends `test_demo_seed_script.py`, which already runs the
script twice. Criterion 4 is `make ci` and rides CI.

**Every refusal here is attempted, and every one of them is attempted beside a
row that has to be accepted** (`docs/MISTAKES.md` entry 3). A `pytest.raises`
around an insert says only that the database refused something; the row before
it is what says the refusal was about the thing the test names. Where the
control is interesting on its own — a single value in an `answer`, a response
for the same student in a later week — it is a test of its own rather than only
a guard, because the schema refusing it would be a defect worth its own failure.

**Nothing here names a constraint**, which is the rule
`test_term_calendar_schema.py` sets out at length and for the same two reasons:
a name in this schema is produced by `Base.metadata`'s naming convention from a
name in the model rather than chosen, so a test holding one reports a rename as
a regression; and the criteria are about outcomes. What each test does name, in
its docstring, is the mutation it exists to kill.

**Writes go through `Base.metadata`, never through a reflected table.** ADR 0019
puts the naive-datetime guard on the column *type*, and a write through a
reflected table never meets it — so a suite that seeded through reflection would
be unable to ask criterion-4-of-E0-06's question of the two new timestamps at
all. The declared tables and the row-seeding walker both come from
`tests/fixtures/supervision.py` (`metadata_tables`, `seed_rows`): this module
deliberately carries no copy of either, since four already exist and
`docs/MISTAKES.md` entry 13 is about the fifth.

**Criterion 5 is asked of the live migrated table and not of the model**, which
is what the criterion itself requires — "asserted by a test that inspects the
live table, not by review". A model may declare no default while a hand-written
migration adds one, and that is exactly the drift the criterion is written
against. `information_schema.columns` is what a deployment would be asked.

**The column names below are this ticket's settled design.** SPEC §3.2 and §8
name the tables and the rules and spell almost no columns, so each name is a
constant here and a deliberate rename is a one-line change — the precedent
`test_term_calendar_schema.py` sets with `TERM_LENGTH_COLUMNS`. Where a value
rather than a name is the spec's, the docstring says so.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DatabaseError, StatementError

pytestmark = pytest.mark.integration

# The four tables E2-05's scope names. SPEC §8 lists all four among the core
# tables. Table names, not ORM class names — the ticket names the tables and
# nothing anywhere names the classes.
SURVEY_TABLES = ("question_set", "question", "response", "answer")

QUESTION_SET = "question_set"
QUESTION = "question"
RESPONSE = "response"
ANSWER = "answer"

# `question_set`: the version SPEC §3.2 says the set is stored under.
VERSION_COLUMN = "version"

# `question`: the ordinal, the kind, and the two pairs that carry §3.2's rules
# as data rather than as prose the form has to know.
POSITION_COLUMN = "position"
REQUIRED_IF_POSITION_COLUMN = "required_if_position"
REQUIRED_IF_AT_MOST_COLUMN = "required_if_at_most"
MINIMUM_VALUE_COLUMN = "minimum_value"
MAXIMUM_VALUE_COLUMN = "maximum_value"
STEP_COLUMN = "step"

# `response`: the three columns SPEC §8's uniqueness rule is written over. The
# student key is spelled the way `enrollment` spells it — E2-05's scope: "the
# student key is the same identity spelling `enrollment` uses".
RESPONSE_KEY_COLUMNS = ("user_id", "section_id", "week_id")

# `response`: the two submission timestamps criterion 5 is about.
FIRST_SUBMITTED_COLUMN = "first_submitted_at"
LAST_SUBMITTED_COLUMN = "last_submitted_at"
SUBMISSION_TIMESTAMPS = (FIRST_SUBMITTED_COLUMN, LAST_SUBMITTED_COLUMN)

# `answer`: the two keys SPEC §8's "`answer` rows link to versioned `question`
# rows" is written over.
ANSWER_KEY_COLUMNS = ("response_id", "question_id")

# `answer`: the three value columns, exactly one of which a row may hold.
RATING_COLUMN = "rating"
COMMENT_TEXT_COLUMN = "comment_text"
WORKLOAD_HOURS_COLUMN = "workload_hours"
ANSWER_VALUE_COLUMNS = (RATING_COLUMN, COMMENT_TEXT_COLUMN, WORKLOAD_HOURS_COLUMN)

# One value of each kind, all three legal against SPEC §3.2's own ranges — a
# Likert 3 out of 1-5, a sentence, and 3.5 hours out of 0-40 in half-hour steps.
# (§3.2 writes both ranges with an en dash, which ruff reads as a confusable, so
# every range quoted in this file is transcribed with a hyphen.)
# Legal on purpose: this ticket deliberately puts **no** range check on
# `answer`, so a value outside the range is not what any of these tests is
# about, and using one would make a refusal ambiguous.
ANSWER_VALUES = {
    RATING_COLUMN: 3,
    COMMENT_TEXT_COLUMN: "the pacing in week 3 was too fast",
    WORKLOAD_HOURS_COLUMN: Decimal("3.5"),
}

# SPEC §3.2's Likert range and the workload slider's, used where a test needs
# bounds that are ordinary rather than contrived.
LIKERT_BOUNDS = (Decimal("1"), Decimal("5"), Decimal("1"))
WORKLOAD_BOUNDS = (Decimal("0"), Decimal("40"), Decimal("0.5"))

# An aware instant to write into a submission timestamp. Aware because ADR 0019
# refuses anything else, and in UTC because nothing here is about the offset
# except the one test that says it is.
SUBMITTED_AT = datetime(2026, 8, 23, 22, 30, tzinfo=UTC)

# The same submission, revised an hour later. A resubmission, which is the only
# way the two timestamps come to differ (E2-08 owns the semantics; this ticket
# owns the columns).
RESUBMITTED_AT = SUBMITTED_AT + timedelta(hours=1)


def survey_table(tables: dict[str, Any], name: str) -> Any:
    """The declared table called `name`, or a failure saying E2-05 has not built it.

    A message of this module's own rather than the one the shared walker prints,
    because that one names E0-05 and E0-09 and would send a reader to the wrong
    ticket while these four tables do not exist.
    """
    table = tables.get(name)
    if table is None:
        pytest.fail(
            f"There is no `{name}` table (what is there: {sorted(tables)}). E2-05 creates "
            f"{list(SURVEY_TABLES)} in `backend/app/models/survey.py` and registers the module "
            "in `app/models/__init__.py`; `test_upgrade_head_creates_the_four_survey_tables` "
            "below and `tests/unit/test_survey_models_registered.py` are the two assertions for "
            "that, and nothing else here can mean anything without them."
        )
    return table


def require_columns(table: Any, names: tuple[str, ...]) -> None:
    """Stop unless `table` has every one of `names`, listing what it does have.

    Without it a missing column ends the test inside the seeding walker with a
    message about an unknown keyword, which reads as a broken test rather than
    as a red one — and the two are fixed by different people.
    """
    absent = [name for name in names if name not in table.c]
    if absent:
        pytest.fail(
            f"`{table.name}` has none of {absent} — it has "
            f"{[column.name for column in table.columns]}. Each name is a constant at the top "
            "of this file, so a deliberate rename is a one-line change here."
        )


def refused(session: Any, write: Any) -> bool:
    """Attempt `write` inside a savepoint and say whether the database refused it.

    A savepoint rather than a bare try, because a failed statement poisons the
    transaction and every later write in the test would then fail for a reason
    the test is not about.
    """
    try:
        with session.begin_nested():
            write()
    except DatabaseError:
        return True
    return False


# ---------------------------------------------------------------------------
# The control on this module's own machinery. Green today and green while E2-05
# is unbuilt, deliberately: `refused` is the helper every assertion below is
# phrased through, and a version of it that answered `True` unconditionally
# would turn eleven refusals green against a schema with no constraints at all.
# So it is run against a write the database certainly refuses and against one it
# certainly accepts, neither of them E2-05's (`docs/MISTAKES.md` entry 3 — a
# pattern, or a predicate, searched against text is a test in its own right and
# looks like none).
# ---------------------------------------------------------------------------


def test_the_refusal_helper_tells_a_refused_write_from_an_accepted_one(
    db_session: Any, seed_rows: Any
) -> None:
    """`refused` answers `False` for a write that lands and `True` for one that does not.

    Both cases are E0-06's, not this ticket's, so this control stands whether or
    not E2-05 exists: a second week in a term is accepted, and a second week
    with the same number in the same term is refused by the uniqueness rule
    E0-06's criterion 3 landed and
    `tests/integration/test_term_calendar_schema.py` asserts.

    **The must-not-answer-True half is the one that matters.** A helper that
    reported every write as refused — a bare `except Exception`, a savepoint
    that rolled back on its own — makes every refusal in this module pass
    against a schema that constrains nothing, and no other test here could tell.
    The must-answer-True half guards the mirror image: a helper that swallowed
    the error and returned `False` would make every refusal here a red nobody
    could fix.
    """
    chain: dict[str, Any] = {}
    seed_rows("week", chain, number=1)

    accepted = refused(db_session, lambda: seed_rows("week", {"term": chain["term"]}, number=2))
    assert not accepted, (
        "`refused` reported that week 2 of a term was refused. A term holds twelve or eighteen "
        "weeks (SPEC §2.2), so that write lands — and a helper that answers `True` for a write "
        "the database accepted makes every refusal in this module pass against a schema with no "
        "constraints in it at all."
    )

    duplicated = refused(db_session, lambda: seed_rows("week", {"term": chain["term"]}, number=1))
    assert duplicated, (
        "`refused` reported that a second week 1 in one term was accepted. E0-06's criterion 3 "
        "makes `(term_id, number)` unique and "
        "`tests/integration/test_term_calendar_schema.py` asserts it, so either that rule has "
        "gone or this helper is swallowing the refusal — and if it swallows one, every "
        "assertion in this module that expects a refusal is a red nobody can fix by changing the "
        "schema."
    )


# ---------------------------------------------------------------------------
# Criterion 1, first half — the four tables exist.
# ---------------------------------------------------------------------------


def test_upgrade_head_creates_the_four_survey_tables(migrated_engine: Any) -> None:
    """Criterion 1: `alembic upgrade head` creates all four of the survey tables.

    Asserted against the server rather than against `Base.metadata`, because a
    table that is on the metadata and in no migration exists nowhere a
    deployment can reach — and `alembic check` is silent about a *model module*
    nobody imported, which is the other half and is asserted in
    `tests/unit/test_survey_models_registered.py`.

    **The mutation it kills:** declaring the models and shipping no revision, or
    shipping a revision that creates three of the four. **The near miss it
    tolerates:** a table spelled differently is the same failure as one never
    created, because SPEC §8 names these four and E2-06, E2-08 and E2-09 all
    join to them, so the message prints what is there.
    """
    present = sorted(inspect(migrated_engine).get_table_names())

    missing = [name for name in SURVEY_TABLES if name not in present]
    assert not missing, (
        f"`alembic upgrade head` left no {missing} table. The migrated database holds {present}. "
        "E2-05 creates question_set, question, response and answer (SPEC §3.2, §8); E2-08's "
        "write path and E2-09's read path are both built on them."
    )


# ---------------------------------------------------------------------------
# Criterion 1 — one response per (student, section, week). SPEC §8: "`response`
# is unique per (student, section, week)". Three tests, because the constraint
# has three columns and leaving any one of them out is a different defect.
# ---------------------------------------------------------------------------


def test_a_second_response_for_the_same_student_section_and_week_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 1: "a second response for the same (student, section, week) is refused".

    **A differing third response goes in before the one that must not.** A
    second student's response in the same section and week has to be accepted —
    that is what a section's weekly survey *is* — so until it inserts, the
    refusal below would be equally well explained by a table that permits one
    row per section and week, and would say nothing about the student.

    **The mutation it kills:** the unique constraint left off altogether, which
    lets a student submit twice in a week and doubles their weight in every
    aggregate SPEC §5 computes while the participation denominator stays at one.
    """
    require_columns(survey_table(metadata_tables, RESPONSE), RESPONSE_KEY_COLUMNS)

    chain: dict[str, Any] = {}
    first = seed_rows(RESPONSE, chain)

    other_student = seed_rows("user", {})
    try:
        with db_session.begin_nested():
            seed_rows(
                RESPONSE,
                {},
                user_id=other_student["id"],
                section_id=first["section_id"],
                week_id=first["week_id"],
            )
    except DatabaseError as rejected:
        pytest.fail(
            f"A second student's response in the same section and week was refused: {rejected}. "
            "A weekly survey is answered by every student in the section, so until this inserts "
            "the refusal below says nothing about the student key."
        )

    duplicated = refused(
        db_session,
        lambda: seed_rows(
            RESPONSE,
            {},
            user_id=first["user_id"],
            section_id=first["section_id"],
            week_id=first["week_id"],
        ),
    )
    assert duplicated, (
        "One student wrote two responses for one section in one week. SPEC §8: '`response` is "
        "unique per (student, section, week)', and E2-05's first criterion makes the database "
        "the thing that refuses it. Two rows are two votes: §3.3's validity rate and §3.4's "
        "participation score both count responses, and the denominator is weeks, not rows."
    )


def test_the_same_student_may_respond_to_the_same_section_in_a_later_week(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 1, the other direction: the key includes the week.

    The half that fails when the constraint is written over `(user_id,
    section_id)` alone — which is the natural mistake, reads correctly, and
    would let a student answer a section's survey exactly once per term. SPEC
    §3.1 makes the survey weekly and §3.4 scores "valid weeks completed ÷ weeks
    elapsed", so a rule that permits one response per section is a rule that
    caps every student's participation at a single week.

    **The mutation it kills:** dropping `week_id` from the unique constraint.
    """
    require_columns(survey_table(metadata_tables, RESPONSE), RESPONSE_KEY_COLUMNS)

    chain: dict[str, Any] = {}
    first = seed_rows(RESPONSE, chain)
    later = seed_rows("week", {"term": chain["term"]})
    assert later["id"] != first["week_id"], (
        "Seeding a second week reused the first one, so there is no later week to respond in and "
        "the assertion below would be about nothing."
    )

    try:
        with db_session.begin_nested():
            seed_rows(
                RESPONSE,
                {},
                user_id=first["user_id"],
                section_id=first["section_id"],
                week_id=later["id"],
            )
    except DatabaseError as rejected:
        pytest.fail(
            f"A student was refused a response in a second week of the same section: {rejected}. "
            "The survey runs every week (SPEC §3.1) and participation is scored over weeks "
            "elapsed (§3.4), so a uniqueness rule without the week makes every student's second "
            "week unwritable."
        )


def test_the_same_student_may_respond_to_another_section_in_the_same_week(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 1, the third direction: the key includes the section.

    The half that fails when the constraint is written over `(user_id,
    week_id)`. A student takes several courses; SPEC §3.1 says they "see exactly
    one open survey at a time **per section**", so one response per student per
    week across the whole institution is a rule that silently drops every course
    after the first one they answer in.

    **The mutation it kills:** dropping `section_id` from the unique constraint.
    """
    require_columns(survey_table(metadata_tables, RESPONSE), RESPONSE_KEY_COLUMNS)

    chain: dict[str, Any] = {}
    first = seed_rows(RESPONSE, chain)
    other_section = seed_rows("section", {"term": chain["term"]})
    assert other_section["id"] != first["section_id"], (
        "Seeding a second section reused the first one, so there is no other section to respond "
        "in and the assertion below would be about nothing."
    )

    try:
        with db_session.begin_nested():
            seed_rows(
                RESPONSE,
                {},
                user_id=first["user_id"],
                section_id=other_section["id"],
                week_id=first["week_id"],
            )
    except DatabaseError as rejected:
        pytest.fail(
            f"A student was refused a response in a second section in the same week: {rejected}. "
            "SPEC §3.1 gives a student one open survey per section, not one in total, and a "
            "student taking four courses answers four surveys a week."
        )


# ---------------------------------------------------------------------------
# Criterion 1 — `response`'s submission timestamps. Criterion 5 owns the absence
# of a server default; these two own what the columns are.
# ---------------------------------------------------------------------------


def test_a_response_whose_last_submission_precedes_its_first_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The two timestamps are ordered, and the equal case is the ordinary one.

    E2-05's scope gives `response` "whatever state the resubmission rule needs";
    a `last_submitted_at` before `first_submitted_at` is a row no resubmission
    can produce and one that would make every "edited since" query answer
    backwards.

    **Two rows go in before the one that must not**, and the first of them is
    the boundary: a response never resubmitted has the two timestamps equal, so
    an implementation writing `>` where the rule is `>=` refuses the common case
    and this test fails there rather than at the end. The second is a later
    resubmission, which has to be accepted or the column pair means nothing.

    **The mutation it kills:** the check left off, or written with the operands
    the other way round. **The near miss it tolerates:** none — equal and later
    are both required to insert, so a check that refuses everything fails here.
    """
    response = survey_table(metadata_tables, RESPONSE)
    require_columns(response, SUBMISSION_TIMESTAMPS)

    later = RESUBMITTED_AT

    try:
        with db_session.begin_nested():
            seed_rows(
                RESPONSE,
                {},
                **{
                    FIRST_SUBMITTED_COLUMN: SUBMITTED_AT,
                    LAST_SUBMITTED_COLUMN: SUBMITTED_AT,
                },
            )
    except DatabaseError as rejected:
        pytest.fail(
            f"A response whose two submission timestamps are equal was refused: {rejected}. That "
            "is a response submitted once and never revised, which is the ordinary case — a rule "
            "written as a strict inequality refuses every first submission there will ever be."
        )

    try:
        with db_session.begin_nested():
            seed_rows(
                RESPONSE,
                {},
                **{FIRST_SUBMITTED_COLUMN: SUBMITTED_AT, LAST_SUBMITTED_COLUMN: later},
            )
    except DatabaseError as rejected:
        pytest.fail(
            f"A response resubmitted an hour after it was first submitted was refused: "
            f"{rejected}. Until a resubmitted response inserts, the refusal below says nothing "
            "about the order of the two columns."
        )

    backwards = refused(
        db_session,
        lambda: seed_rows(
            RESPONSE,
            {},
            **{FIRST_SUBMITTED_COLUMN: later, LAST_SUBMITTED_COLUMN: SUBMITTED_AT},
        ),
    )
    assert backwards, (
        "A response was written whose last submission is an hour before its first. Nothing E2-08 "
        "does can produce that row, so it is a defect stored rather than a state to support, and "
        "every query that asks whether a response was revised gets a negative interval back."
    )


def test_a_naive_datetime_cannot_be_written_to_either_submission_timestamp(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """ADR 0019 reaches the two new timestamp columns: "every timestamp column in the schema".

    Not an acceptance criterion of its own, and here for `docs/MISTAKES.md`
    entry 2: E0-06's criterion 4 is asserted over the four *calendar* tables, so
    a `response` declared with a bare `DateTime(timezone=True)` would ship with
    nothing in this repository saying so. Postgres accepts a naive value into a
    `timestamptz` column and resolves it against the session `TimeZone`, which
    means the same value means two moments on two connections — and a
    submission timestamp is exactly what SPEC §3.1's window close is compared
    against.

    **The control and the mutation differ in one thing: `tzinfo`.** The naive
    value is the aware one with its offset stripped and the session is pinned to
    UTC first, so an unguarded write stores the very same instant the control
    stored, and a refusal can only be about the missing offset.

    **The mutation it kills:** declaring either column as
    `DateTime(timezone=True)` rather than through the decorated type ADR 0019
    puts the guard on.
    """
    response = survey_table(metadata_tables, RESPONSE)
    require_columns(response, SUBMISSION_TIMESTAMPS)

    db_session.execute(text("SET TIME ZONE 'UTC'"))

    for column_name in SUBMISSION_TIMESTAMPS:
        try:
            with db_session.begin_nested():
                seed_rows(RESPONSE, {}, **{column_name: SUBMITTED_AT})
        except DatabaseError as rejected:
            pytest.fail(
                f"An aware datetime was refused by `{RESPONSE}.{column_name}`: {rejected}. Until "
                "the ordinary row inserts, a refusal below says nothing about naivety."
            )

        naive = SUBMITTED_AT.replace(tzinfo=None)
        refused_naive = False
        try:
            with db_session.begin_nested():
                seed_rows(RESPONSE, {}, **{column_name: naive})
        except (StatementError, ValueError, TypeError):
            refused_naive = True

        assert refused_naive, (
            f"`{RESPONSE}.{column_name}` accepted the naive datetime {naive!r}. Postgres does not "
            "refuse this on its own — it reads the value in the session timezone and stores "
            "whatever instant that names — so ADR 0019 puts the guard on the column type, where "
            "the ORM, a Core insert, Alembic and the seed script all meet it. E2-08 writes these "
            "two columns through the E2-04 clock service, and a column that accepts a naive "
            "value accepts a clock that has forgotten which zone it is in."
        )


# ---------------------------------------------------------------------------
# Criterion 5 — no server default on either submission timestamp, read off the
# live migrated table.
# ---------------------------------------------------------------------------


def test_neither_submission_timestamp_declares_a_server_default(migrated_engine: Any) -> None:
    """Criterion 5, exactly as it is written: asked of the live table, not of the model.

    "`response`'s submission timestamp columns declare **no server default** —
    asserted by a test that inspects the live table, not by review, because
    E2-08 writes them through the clock service and a `func.now()` default would
    silently win." A model declaring none and a hand-written migration adding
    one is precisely the drift the criterion is phrased against, so the question
    goes to `information_schema.columns`, which is what a deployment would be
    asked.

    **Three guards run before the assertion and none is ceremony**
    (`docs/MISTAKES.md` entry 3). The query has to return rows at all — over a
    table that does not exist it returns none, and "no column has a default" is
    then true of nothing. Both timestamp columns have to be among them, or the
    absence is the absence of the column rather than of its default. And one
    column of the same table, read by the same query, has to come back *with* a
    default: `id` carries `gen_random_uuid()` by ADR 0016, so a query that had
    gone blind — a wrong schema, a wrong catalog column, a driver handing back
    `None` for everything — says so here instead of reporting a clean pass
    (`docs/MISTAKES.md` entry 35: a guard that only ever reports absence cannot
    tell you what it can see).

    **The mutation it kills:** `server_default=func.now()` on either column,
    which makes a clock nobody chose the writer of record and makes E2-04's
    injectable clock unobservable in every test that follows.
    """
    with migrated_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT column_name, column_default FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table"
            ),
            {"table": RESPONSE},
        ).all()

    defaults = dict(rows)
    assert defaults, (
        f"`information_schema.columns` reports no column at all on `public.{RESPONSE}`, so this "
        "test would pass against a database with no such table. E2-05 creates it; "
        "`test_upgrade_head_creates_the_four_survey_tables` is where that is diagnosed."
    )

    missing = [name for name in SUBMISSION_TIMESTAMPS if name not in defaults]
    assert not missing, (
        f"`{RESPONSE}` has no {missing} column — the migrated table holds {sorted(defaults)}. "
        "Criterion 5 is about the defaults on those two columns, and over a table without them "
        "it is satisfied by their absence rather than by their shape."
    )

    with_a_default = sorted(name for name, default in defaults.items() if default is not None)
    assert with_a_default, (
        f"No column on `{RESPONSE}` reports a default of any kind, so this query cannot tell a "
        "column that has none from a reading that sees none. Every primary key in this schema is "
        "a server-defaulted `gen_random_uuid()` (ADR 0016), so at least one default has to come "
        "back or the assertion below is measuring the query rather than the schema."
    )

    defaulted = {
        name: defaults[name] for name in SUBMISSION_TIMESTAMPS if defaults[name] is not None
    }
    assert not defaulted, (
        f"These `{RESPONSE}` columns carry a server default: {defaulted}. Criterion 5 forbids "
        "one. E2-08 writes both through the E2-04 clock service, and a database-side default "
        "wins silently on any insert that omits the column — so the submission time recorded "
        "would be the server's wall clock rather than the injectable clock every test and every "
        "window-close comparison is written against, and nothing would go red."
    )


# ---------------------------------------------------------------------------
# Criterion 1 — an `answer` holds exactly one value. SPEC §8: "`answer` rows
# link to versioned `question` rows; workload is stored as a decimal."
#
# Five cases: each single value accepted, no value refused, two values refused.
# Three greens and two reds, and the greens are what make the reds mean
# anything — a table that refused every insert would satisfy both refusals.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("column_name", ANSWER_VALUE_COLUMNS)
def test_an_answer_holding_exactly_one_value_is_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any, column_name: str
) -> None:
    """Each of the three value columns is usable on its own.

    §3.2 has three answer shapes and this schema has one row shape for them: a
    Likert rating, a free-text comment, and workload as a **decimal** rather
    than a band, which is §3.2's own sentence — "stored as a decimal so
    reporting can show true means and medians rather than band midpoints".

    **The mutation it kills:** a check written as `num_nonnulls(...) <= 1` is
    not caught here (the no-value test below is what catches it), but a check
    naming only two of the three columns is — the third value then arrives with
    a count of zero and is refused, and it is `workload_hours` that a
    two-column check would most naturally omit, since it is the one that is
    neither a rating nor a comment.

    Every value used is legal against §3.2's own ranges, deliberately: this
    ticket puts no range check on `answer` (the ranges are data on `question`,
    and a `CHECK` cannot read another table — ADR 0018's opening problem), so a
    refusal here can never be about the value being out of range.
    """
    answer = survey_table(metadata_tables, ANSWER)
    require_columns(answer, ANSWER_VALUE_COLUMNS)

    try:
        with db_session.begin_nested():
            seed_rows(ANSWER, {}, **{column_name: ANSWER_VALUES[column_name]})
    except DatabaseError as rejected:
        pytest.fail(
            f"An answer holding only `{column_name}` = {ANSWER_VALUES[column_name]!r} was "
            f"refused: {rejected}. §3.2 has three answer shapes and each is stored in one of "
            "these three columns, so every one of them has to be writable on its own — and until "
            "they are, the two refusals beside this test say nothing about how many values a row "
            "may hold."
        )


def test_an_answer_holding_no_value_at_all_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """An answer row that answers nothing is refused.

    The row is `response_id` and `question_id` and three nulls: it says a
    student answered a question and records no answer. Nothing downstream can
    read it — §3.3 counts required fields answered, §5.1 plots the distribution
    — and it is indistinguishable from a question the student skipped, which is
    the absence of a row.

    **The mutation it kills:** a check written as `num_nonnulls(...) <= 1`,
    which permits every combination this test and the two-value test are about
    except one, and reads exactly like the right rule.
    """
    answer = survey_table(metadata_tables, ANSWER)
    require_columns(answer, ANSWER_VALUE_COLUMNS)

    empty = refused(db_session, lambda: seed_rows(ANSWER, {}))
    assert empty, (
        "An answer was written holding no rating, no comment and no workload. E2-05 makes an "
        "answer hold exactly one value; a row holding none records that a question was answered "
        "and stores no answer, so §3.3's completeness check counts it and §5.1's distribution "
        "cannot plot it. `<= 1` is the check that permits it and `= 1` is the check that does "
        "not."
    )


@pytest.mark.parametrize(
    "pair",
    [
        (RATING_COLUMN, COMMENT_TEXT_COLUMN),
        (RATING_COLUMN, WORKLOAD_HOURS_COLUMN),
        (COMMENT_TEXT_COLUMN, WORKLOAD_HOURS_COLUMN),
    ],
)
def test_an_answer_holding_two_values_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any, pair: tuple[str, str]
) -> None:
    """An answer row may not hold two of the three values.

    All three pairs, because a check naming two columns rather than three
    refuses one pair and accepts the other two, and a reader cannot tell which
    from a single case. Each of the two values here is one that
    `test_an_answer_holding_exactly_one_value_is_accepted` has already shown to
    be writable on its own, so the refusal is about the pairing.

    **The mutation it kills:** `num_nonnulls(...) >= 1`, and any check written
    over a subset of the three columns. **What it deliberately does not
    assert:** which of the two values would have been kept — the row is refused
    outright, and a schema that silently dropped one would fail here rather than
    be described.
    """
    answer = survey_table(metadata_tables, ANSWER)
    require_columns(answer, ANSWER_VALUE_COLUMNS)

    values = {name: ANSWER_VALUES[name] for name in pair}
    both = refused(db_session, lambda: seed_rows(ANSWER, {}, **values))
    assert both, (
        f"An answer was written holding both {list(pair)}. E2-05 makes an answer hold exactly "
        "one value; a row holding two belongs to two of §3.2's questions at once, and every "
        "aggregate that reads it counts one submission twice — once in a rating distribution and "
        "once as a comment. The value each column holds is legal on its own, so this cannot be a "
        "refusal about the values."
    )


# ---------------------------------------------------------------------------
# Criterion 1 — an answer belongs to one question of one response.
# ---------------------------------------------------------------------------


def test_a_second_answer_to_the_same_question_in_one_response_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """One answer per question per response.

    **A second answer to a different question goes in first**, because a
    response answers five questions (§3.2) and a table that permitted one answer
    per response would satisfy the refusal below for a reason that has nothing
    to do with the question.

    **The mutation it kills:** the unique constraint left off. Two answers to
    one question is a student's rating counted twice in the same week's
    distribution, with the response count unchanged — the shape §4.1 item 3's
    n-threshold is computed against.
    """
    require_columns(survey_table(metadata_tables, ANSWER), ANSWER_KEY_COLUMNS)

    chain: dict[str, Any] = {}
    first = seed_rows(ANSWER, chain, **{RATING_COLUMN: ANSWER_VALUES[RATING_COLUMN]})
    second_question = seed_rows(
        QUESTION, {QUESTION_SET: chain[QUESTION_SET]}, **{POSITION_COLUMN: 2}
    )
    assert second_question["id"] != first["question_id"], (
        "Seeding a second question reused the first one, so there is no other question to answer "
        "and the assertion below would be about nothing."
    )

    try:
        with db_session.begin_nested():
            seed_rows(
                ANSWER,
                {},
                response_id=first["response_id"],
                question_id=second_question["id"],
                **{COMMENT_TEXT_COLUMN: ANSWER_VALUES[COMMENT_TEXT_COLUMN]},
            )
    except DatabaseError as rejected:
        pytest.fail(
            f"A second answer, to a different question of the same response, was refused: "
            f"{rejected}. A response answers five questions (SPEC §3.2), so until this inserts "
            "the refusal below says nothing about the question key."
        )

    duplicated = refused(
        db_session,
        lambda: seed_rows(
            ANSWER,
            {},
            response_id=first["response_id"],
            question_id=first["question_id"],
            **{RATING_COLUMN: 5},
        ),
    )
    assert duplicated, (
        "One response holds two answers to the same question. E2-05 keys an answer to its "
        "response and its versioned question row, and two rows for one question give every read "
        "path two values and no rule for choosing — a rating distribution that double-counts one "
        "student, and a comment list that shows one student twice under §4's de-identification."
    )


def test_the_same_question_may_be_answered_by_two_responses(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The other direction: the answer key includes the response.

    The half that fails when the constraint is written over `question_id` alone
    — which would permit exactly one answer to each of §3.2's five questions
    across the whole deployment, for all time.

    **The mutation it kills:** dropping `response_id` from the unique
    constraint.
    """
    require_columns(survey_table(metadata_tables, ANSWER), ANSWER_KEY_COLUMNS)

    chain: dict[str, Any] = {}
    first = seed_rows(ANSWER, chain, **{RATING_COLUMN: ANSWER_VALUES[RATING_COLUMN]})
    other_response = seed_rows(RESPONSE, {})
    assert other_response["id"] != first["response_id"], (
        "Seeding a second response reused the first one, so there is no other response to answer "
        "from and the assertion below would be about nothing."
    )

    try:
        with db_session.begin_nested():
            seed_rows(
                ANSWER,
                {},
                response_id=other_response["id"],
                question_id=first["question_id"],
                **{RATING_COLUMN: 4},
            )
    except DatabaseError as rejected:
        pytest.fail(
            f"A second response's answer to the same question was refused: {rejected}. Every "
            "student in a section answers the same five questions (SPEC §3.2), so a uniqueness "
            "rule over the question alone leaves the whole institution one answer each."
        )


# ---------------------------------------------------------------------------
# Criterion 1 — the versioned question set. SPEC §3.2: "Question text is stored
# in a versioned `question_set` table even though v1 ships one fixed set."
# ---------------------------------------------------------------------------


def test_two_question_sets_with_the_same_version_are_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """A version identifies one set.

    **A second, differing version goes in first**, because the table exists to
    hold more than one — §3.2 calls it "the extension point for the future
    feature where each oversight level can append its own questions" — so a
    table permitting one row would satisfy the refusal below for the wrong
    reason.

    **The mutation it kills:** the unique constraint left off `version`. Two
    sets claiming to be v1 make "the v1 question set" ambiguous, and an `answer`
    keyed to a question row cannot say which set the reader should render.
    """
    question_set = survey_table(metadata_tables, QUESTION_SET)
    require_columns(question_set, (VERSION_COLUMN,))

    seed_rows(QUESTION_SET, {}, **{VERSION_COLUMN: 1})

    try:
        with db_session.begin_nested():
            seed_rows(QUESTION_SET, {}, **{VERSION_COLUMN: 2})
    except DatabaseError as rejected:
        pytest.fail(
            f"A second question set at version 2 was refused: {rejected}. SPEC §3.2 versions the "
            "table precisely so a second set can exist, and until one inserts the refusal below "
            "says nothing about duplication."
        )

    duplicated = refused(db_session, lambda: seed_rows(QUESTION_SET, {}, **{VERSION_COLUMN: 1}))
    assert duplicated, (
        "Two question sets were written at version 1. A version is what names a set — E2-05's "
        "seed matches on it, and every `answer` resolves its text through the question row's set "
        "— so two rows sharing one leave 'the v1 set' with two answers."
    )


def test_a_question_set_version_below_one_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Versions start at 1, which is the version SPEC §3.2 ships.

    Version 1 goes in first, because it is the boundary: a check written as
    `> 1` refuses the only set that exists today, and the failure would then be
    at the control rather than at the assertion.

    **The mutation it kills:** the check left off, which lets a set be written
    at 0 or at -1 and makes "the latest version" an ordering over numbers that
    do not mean anything.
    """
    question_set = survey_table(metadata_tables, QUESTION_SET)
    require_columns(question_set, (VERSION_COLUMN,))

    try:
        with db_session.begin_nested():
            seed_rows(QUESTION_SET, {}, **{VERSION_COLUMN: 1})
    except DatabaseError as rejected:
        pytest.fail(
            f"Version 1 was refused: {rejected}. SPEC §3.2 ships v1 as the one fixed set, so it "
            "has to be writable — and until it is, the refusal below says nothing about where "
            "the range starts."
        )

    below = refused(db_session, lambda: seed_rows(QUESTION_SET, {}, **{VERSION_COLUMN: 0}))
    assert below, (
        "A question set was written at version 0. E2-05 starts versions at 1, and SPEC §3.2 "
        "calls the shipped set v1; a set at 0 or below sorts ahead of it in every 'latest "
        "version' query written afterwards."
    )


def test_two_questions_at_the_same_position_in_one_set_are_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """A position identifies a question within its set.

    **Position 2 goes in between the two position 1s**, so the refusal is known
    to be about the repeated ordinal and not about a set being allowed one
    question — SPEC §3.2 gives v1 five of them.

    **The mutation it kills:** the unique constraint left off. §3.2's rules are
    written by position — "Required if Q1 ≤ 2" — and E2-05 carries them as data
    that names a position, so two questions sharing one make the conditional
    rule point at two questions at once.
    """
    survey_table(metadata_tables, QUESTION)

    chain: dict[str, Any] = {}
    seed_rows(QUESTION, chain, **{POSITION_COLUMN: 1})

    try:
        with db_session.begin_nested():
            seed_rows(QUESTION, {QUESTION_SET: chain[QUESTION_SET]}, **{POSITION_COLUMN: 2})
    except DatabaseError as rejected:
        pytest.fail(
            f"A second question at position 2 in the same set was refused: {rejected}. SPEC §3.2 "
            "gives the v1 set five questions, so until a second one inserts the refusal below "
            "proves nothing."
        )

    duplicated = refused(
        db_session,
        lambda: seed_rows(QUESTION, {QUESTION_SET: chain[QUESTION_SET]}, **{POSITION_COLUMN: 1}),
    )
    assert duplicated, (
        "Two questions were written at position 1 of one set. SPEC §3.2 numbers its five "
        "questions and E2-05 carries the conditional-required rule as a position — 'required if "
        "Q1 ≤ 2' — so two rows at one position leave the rule naming two questions and the form "
        "rendering them in an order nothing decides."
    )


def test_the_same_position_may_recur_in_another_question_set(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The position is unique *within* a set, not across the table.

    The half that fails when the constraint is written over `position` alone —
    which would let the whole deployment hold five questions ever, and make
    §3.2's versioning ("no schema migration will be needed to add it")
    unusable at the first added set.

    **The mutation it kills:** dropping `question_set_id` from the unique
    constraint.
    """
    survey_table(metadata_tables, QUESTION)

    chain: dict[str, Any] = {}
    seed_rows(QUESTION, chain, **{POSITION_COLUMN: 1})
    other_set = seed_rows(QUESTION_SET, {})
    assert other_set["id"] != chain[QUESTION_SET]["id"], (
        "Seeding a second question set reused the first one, so there is no other set to put a "
        "question in and the assertion below would be about nothing."
    )

    try:
        with db_session.begin_nested():
            seed_rows(QUESTION, {QUESTION_SET: other_set}, **{POSITION_COLUMN: 1})
    except DatabaseError as rejected:
        pytest.fail(
            f"Position 1 was refused in a second question set: {rejected}. Every set starts at "
            "position 1, and SPEC §3.2 versions the table so a second set can exist at all — a "
            "uniqueness rule spanning sets makes the second one unwritable."
        )


def test_a_question_position_below_one_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Positions start at 1, which is how SPEC §3.2 numbers them.

    Its own test rather than folded into the uniqueness one, because the two
    fail for different reasons and a position 0 becomes an off-by-one everywhere
    §3.2's rules are read by ordinal.

    **The mutation it kills:** the check left off.
    """
    question = survey_table(metadata_tables, QUESTION)
    require_columns(question, (POSITION_COLUMN,))

    chain: dict[str, Any] = {}
    try:
        with db_session.begin_nested():
            seed_rows(QUESTION, chain, **{POSITION_COLUMN: 1})
    except DatabaseError as rejected:
        pytest.fail(
            f"Position 1 was refused: {rejected}. Until the first question of a set inserts, the "
            "refusal below says nothing about where the range starts."
        )

    below = refused(
        db_session,
        lambda: seed_rows(QUESTION, {QUESTION_SET: chain[QUESTION_SET]}, **{POSITION_COLUMN: 0}),
    )
    assert below, (
        "A question was written at position 0. SPEC §3.2 numbers its questions from 1 and E2-05 "
        "carries 'required if Q1 ≤ 2' as that number, so a question at 0 is one the conditional "
        "rule can never name and one the form renders before the first."
    )


# ---------------------------------------------------------------------------
# Criterion 1 — §3.2's two rules carried as data. Each is a pair of columns that
# only means something whole: half a conditional rule points at a question with
# no threshold, and half a range has a minimum and no maximum.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("half", [REQUIRED_IF_POSITION_COLUMN, REQUIRED_IF_AT_MOST_COLUMN])
def test_a_question_carrying_half_a_conditional_rule_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any, half: str
) -> None:
    """§3.2's "Required if Q1 ≤ 2" is a question *and* a threshold, or neither.

    Both halves are parametrised because leaving either one null is a different
    row and a check naming only one of the two columns catches only one of them.

    **Two controls run first**, and both are states §3.2 requires: a question
    with no conditional rule at all (Q1, Q3 and Q5 are three of the five), and a
    question with the whole rule (Q2 is required if Q1 ≤ 2). A check that
    refused either would make three of §3.2's questions or two of them
    unwritable, and the failure would then be at a control rather than at the
    assertion.

    **The mutation it kills:** the check left off, which stores a rule pointing
    at a question with no threshold — a form that knows a field is conditional
    on Q1 and not on what.
    """
    question = survey_table(metadata_tables, QUESTION)
    require_columns(question, (REQUIRED_IF_POSITION_COLUMN, REQUIRED_IF_AT_MOST_COLUMN))

    chain: dict[str, Any] = {}
    try:
        with db_session.begin_nested():
            seed_rows(QUESTION, chain, **{POSITION_COLUMN: 1})
    except DatabaseError as rejected:
        pytest.fail(
            f"A question carrying no conditional rule was refused: {rejected}. Three of SPEC "
            "§3.2's five questions carry none, so this is the ordinary row."
        )

    whole = {
        POSITION_COLUMN: 2,
        REQUIRED_IF_POSITION_COLUMN: 1,
        REQUIRED_IF_AT_MOST_COLUMN: 2,
    }
    try:
        with db_session.begin_nested():
            seed_rows(QUESTION, {QUESTION_SET: chain[QUESTION_SET]}, **whole)
    except DatabaseError as rejected:
        pytest.fail(
            f"A question carrying the whole conditional rule was refused: {rejected}. That is "
            "SPEC §3.2's Q2 — 'Required if Q1 ≤ 2' — so it has to be writable, and until it is "
            "the refusal below says nothing about the rule being half present."
        )

    partial = {POSITION_COLUMN: 3, **{name: None for name in whole if name != POSITION_COLUMN}}
    partial[half] = whole[half]
    halved = refused(
        db_session,
        lambda: seed_rows(QUESTION, {QUESTION_SET: chain[QUESTION_SET]}, **partial),
    )
    assert halved, (
        f"A question was written carrying `{half}` and not the other half of the rule. SPEC "
        "§3.2's conditional requirement is a question and a threshold together; half of it is a "
        "rule E2-10's form cannot evaluate and §3.3's completeness check cannot apply, and it "
        "reads as a configured rule rather than as a missing one."
    )


@pytest.mark.parametrize(
    "present",
    [
        (MINIMUM_VALUE_COLUMN,),
        (MAXIMUM_VALUE_COLUMN,),
        (STEP_COLUMN,),
        (MINIMUM_VALUE_COLUMN, MAXIMUM_VALUE_COLUMN),
        (MINIMUM_VALUE_COLUMN, STEP_COLUMN),
        (MAXIMUM_VALUE_COLUMN, STEP_COLUMN),
    ],
)
def test_a_question_carrying_only_some_of_its_numeric_bounds_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any, present: tuple[str, ...]
) -> None:
    """A numeric range is a minimum, a maximum and a step, or none of the three.

    Every proper subset is parametrised, because a check naming two of the three
    columns accepts the subsets that leave the third out and a single case
    cannot distinguish them.

    **Two controls run first**, and both are §3.2's own rows: a comment question
    with no bounds at all, and the workload slider's whole range — "range 0-40,
    0.5-hour steps".

    **The mutation it kills:** the check left off, which stores a slider with a
    minimum and no maximum, or a range with no step. E2-10 reads these three to
    render the control, and a partial range renders as a slider with one end.
    """
    question = survey_table(metadata_tables, QUESTION)
    require_columns(question, (MINIMUM_VALUE_COLUMN, MAXIMUM_VALUE_COLUMN, STEP_COLUMN))

    minimum, maximum, step = WORKLOAD_BOUNDS
    whole = {
        MINIMUM_VALUE_COLUMN: minimum,
        MAXIMUM_VALUE_COLUMN: maximum,
        STEP_COLUMN: step,
    }

    chain: dict[str, Any] = {}
    try:
        with db_session.begin_nested():
            seed_rows(QUESTION, chain, **{POSITION_COLUMN: 1})
    except DatabaseError as rejected:
        pytest.fail(
            f"A question carrying no numeric bounds was refused: {rejected}. SPEC §3.2's two "
            "comment questions are free text and carry none, so this is an ordinary row."
        )

    try:
        with db_session.begin_nested():
            seed_rows(
                QUESTION, {QUESTION_SET: chain[QUESTION_SET]}, **{POSITION_COLUMN: 2, **whole}
            )
    except DatabaseError as rejected:
        pytest.fail(
            f"A question carrying SPEC §3.2's workload range — {minimum} to {maximum} in steps "
            f"of {step} — was refused: {rejected}. Until the whole range inserts, the refusal "
            "below says nothing about a partial one."
        )

    partial = {POSITION_COLUMN: 3, **dict.fromkeys(whole)}
    for name in present:
        partial[name] = whole[name]
    incomplete = refused(
        db_session,
        lambda: seed_rows(QUESTION, {QUESTION_SET: chain[QUESTION_SET]}, **partial),
    )
    assert incomplete, (
        f"A question was written carrying only {list(present)} of its three numeric bounds. A "
        "range is a minimum, a maximum and a step together — SPEC §3.2 gives the Likert scale "
        "1-5 and the workload slider 0-40 in 0.5-hour steps — and a partial one is a control "
        "E2-10 cannot render and a validation E2-08 cannot apply, stored in a shape that reads "
        "as configured rather than as absent."
    )


def test_a_question_whose_maximum_does_not_exceed_its_minimum_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """A range runs upward.

    The Likert range goes in first — 1 to 5 in steps of 1, SPEC §3.2's own — so
    the refusal below is known to be about the ordering rather than about
    bounds being unwritable.

    **The mutation it kills:** the ordering check left off. A maximum equal to
    or below the minimum is a slider with no travel and a validation nothing can
    satisfy, and it is the shape a transposed pair of arguments produces.
    """
    question = survey_table(metadata_tables, QUESTION)
    require_columns(question, (MINIMUM_VALUE_COLUMN, MAXIMUM_VALUE_COLUMN, STEP_COLUMN))

    minimum, maximum, step = LIKERT_BOUNDS

    chain: dict[str, Any] = {}
    try:
        with db_session.begin_nested():
            seed_rows(
                QUESTION,
                chain,
                **{
                    POSITION_COLUMN: 1,
                    MINIMUM_VALUE_COLUMN: minimum,
                    MAXIMUM_VALUE_COLUMN: maximum,
                    STEP_COLUMN: step,
                },
            )
    except DatabaseError as rejected:
        pytest.fail(
            f"SPEC §3.2's Likert range, {minimum} to {maximum} in steps of {step}, was refused: "
            f"{rejected}. Until an ordinary range inserts, the refusal below says nothing about "
            "the order of its two ends."
        )

    inverted = refused(
        db_session,
        lambda: seed_rows(
            QUESTION,
            {QUESTION_SET: chain[QUESTION_SET]},
            **{
                POSITION_COLUMN: 2,
                MINIMUM_VALUE_COLUMN: maximum,
                MAXIMUM_VALUE_COLUMN: minimum,
                STEP_COLUMN: step,
            },
        ),
    )
    assert inverted, (
        f"A question was written with a minimum of {maximum} and a maximum of {minimum}. Every "
        "range in SPEC §3.2 runs upward — 1-5, 0-40 — and an inverted one is a slider whose ends "
        "are the wrong way round and a validation no answer can satisfy."
    )


def test_a_question_whose_step_is_not_positive_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """A step moves the value.

    Its own test rather than folded into the ordering one, because a missing
    ordering check and a missing step check are separate mistakes: a step of
    zero yields a slider that cannot move and, wherever a step is divided by,
    a division by zero.

    The workload range goes in first, with §3.2's own 0.5-hour step, so a
    fractional step is known to be acceptable before zero is refused.

    **The mutation it kills:** the positivity check left off, or written as
    `>= 0`, which is the near miss that permits exactly the row this refuses.
    """
    question = survey_table(metadata_tables, QUESTION)
    require_columns(question, (MINIMUM_VALUE_COLUMN, MAXIMUM_VALUE_COLUMN, STEP_COLUMN))

    minimum, maximum, step = WORKLOAD_BOUNDS

    chain: dict[str, Any] = {}
    try:
        with db_session.begin_nested():
            seed_rows(
                QUESTION,
                chain,
                **{
                    POSITION_COLUMN: 1,
                    MINIMUM_VALUE_COLUMN: minimum,
                    MAXIMUM_VALUE_COLUMN: maximum,
                    STEP_COLUMN: step,
                },
            )
    except DatabaseError as rejected:
        pytest.fail(
            f"SPEC §3.2's workload step of {step} hours was refused: {rejected}. The slider moves "
            "in half hours, so a fractional step has to be writable — and until it is, the "
            "refusal below says nothing about zero."
        )

    zero = refused(
        db_session,
        lambda: seed_rows(
            QUESTION,
            {QUESTION_SET: chain[QUESTION_SET]},
            **{
                POSITION_COLUMN: 2,
                MINIMUM_VALUE_COLUMN: minimum,
                MAXIMUM_VALUE_COLUMN: maximum,
                STEP_COLUMN: Decimal("0"),
            },
        ),
    )
    assert zero, (
        "A question was written with a step of 0. SPEC §3.2's slider moves in 0.5-hour steps and "
        "its Likert scale in whole ones; a step of zero is a control that cannot move, and any "
        "code that divides a range by its step divides by zero. A check written `>= 0` accepts "
        "this row, which is why zero rather than a negative step is what is attempted."
    )
