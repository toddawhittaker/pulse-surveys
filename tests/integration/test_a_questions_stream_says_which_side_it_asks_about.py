"""A question belongs to the instructor stream, the course stream, or neither — E4-02.

SPEC §5.1 renders the instructor report as two groups: de-identified comments
"grouped under 'About the instructor' / 'About the course,' each group led by its
own AI summary", over a stacked pair of trend charts with one panel per stream.
SPEC §3.2 numbers the instrument that feeds them — Q1 and Q2 about the
instructor, Q3 and Q4 about the course, Q5 the workload figure, which belongs to
neither group.

**Nothing in the schema says which of those a question is**, and that is what
this ticket adds: `question.stream`, nullable, under two `CHECK`s — a workload
question carries no stream, every other kind carries one, and the value is one of
the two the report groups by. Every ticket from E4-03 on derives a comment's
group from this column, so it is the source rather than a convenience, and the
report's two groups are only well-defined while the two rules hold.

**Each test drives exactly one of the two `CHECK`s**, which is what makes a red
say which rule is missing:

  - a **workload** question carrying a stream breaks only the first rule (the
    second admits both streams);
  - a **non-workload** question with no stream breaks only the first (the second
    admits a null);
  - a non-workload question carrying a *third* stream breaks only the second (the
    first only asks whether the value is null).

A schema that ships one rule and not the other therefore turns one of these red
and leaves the rest green, rather than being caught or missed as a block.

**The kinds are named, and checked against what the column enumerates.** The
breakdown settles the stored spelling as `likert`, `comment` and `workload` —
lowercase, which is what `values_callable` produces — and a mismatch is reported
by name here rather than surfacing as a refused insert that reads like a `CHECK`
firing.

**Which failure a red is, before the ticket lands.** Every test stops in its own
body on `require_the_stream_column`, naming the column E4-02 adds. That is a
failed assertion rather than an error in setup (`docs/MISTAKES.md` entry 44).
The backfill of the rows that already exist is a different question and is asked
where the migration can be run:
`tests/integration/test_the_report_migration_round_trips_on_a_seeded_database.py`.
"""

from typing import Any

import pytest
from fixtures.supervision import sqlstate_of
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# E2-05 created this table and SPEC §8 lists it. Not this ticket's name.
QUESTION = "question"

KIND_COLUMN = "kind"
STREAM_COLUMN = "stream"

# The three answer shapes SPEC §3.2 gives the instrument, spelled as the database
# stores them. Checked against the column's own enumeration below, so a different
# spelling is a message naming both sides rather than a refusal that reads like a
# rule under test.
LIKERT_KIND = "likert"
COMMENT_KIND = "comment"
WORKLOAD_KIND = "workload"
KINDS_THAT_ASK_ABOUT_A_STREAM = (LIKERT_KIND, COMMENT_KIND)

# The two streams §5.1 groups the report by.
INSTRUCTOR_STREAM = "INSTRUCTOR"
COURSE_STREAM = "COURSE"
STREAMS = (INSTRUCTOR_STREAM, COURSE_STREAM)

# A third stream, planted. Deliberately a word that reads like a stream rather
# than nonsense: a rule written as "not empty" refuses `''` and admits this, and
# a group nobody defined is a comment the instructor report renders under no
# heading at all.
NOT_A_STREAM = "BOTH"

INTEGRITY_VIOLATION = "23"


def question_table(tables: dict[str, Any]) -> Any:
    """The declared `question` table, or a failure saying it is not there."""
    table = tables.get(QUESTION)
    if table is None:
        pytest.fail(
            f"There is no `{QUESTION}` table (what is there: {sorted(tables)}). E2-05 creates it "
            "in `backend/app/models/survey.py`; `tests/integration/test_survey_schema.py` is where "
            "a missing survey table is diagnosed."
        )
    return table


def require_the_stream_column(table: Any) -> None:
    """Stop unless `question` carries the column E4-02 adds, listing what it does carry.

    The intended red while the ticket is unbuilt, and a better one than an insert
    failing on an unknown keyword inside the seeding walker: the column is the
    whole of what the ticket adds to this table.
    """
    if STREAM_COLUMN not in table.c:
        pytest.fail(
            f"`{QUESTION}` has no `{STREAM_COLUMN}` column — it has "
            f"{[column.name for column in table.columns]}. E4-02 adds it, nullable, under two "
            "`CHECK`s: a workload question carries no stream and every other kind carries one, "
            f"and the value is one of {list(STREAMS)}. Nothing else in this schema says which of "
            "SPEC §5.1's two groups a question belongs to, and E4-03 onwards read this column to "
            "decide."
        )


def kind_the_column_enumerates(table: Any, wanted: str) -> str:
    """`wanted`, after asking the kind column whether it is one of its members.

    The three spellings are settled by the ticket rather than discovered, and this
    is what keeps a settled spelling from becoming an assumption: a schema whose
    kinds are `LIKERT` and `WORKLOAD` reports both sides here, instead of every
    insert below being refused for a reason that reads like the rules under test.
    """
    if KIND_COLUMN not in table.c:
        pytest.fail(
            f"`{QUESTION}` has no `{KIND_COLUMN}` column — it has "
            f"{[column.name for column in table.columns]}. The first of E4-02's two `CHECK`s is "
            "written over it, so there is no rule to measure without it."
        )
    members = list(getattr(table.c[KIND_COLUMN].type, "enums", ()) or ())
    if members and wanted not in members:
        pytest.fail(
            f"`{QUESTION}.{KIND_COLUMN}` enumerates {members}, which does not include "
            f"`{wanted}`. The breakdown settles the stored spelling as lowercase — `likert`, "
            "`comment`, `workload`, which is what `values_callable` produces — and every rule in "
            "this module is written over it. The three constants at the top of this file are the "
            "one place a deliberate re-spelling changes."
        )
    return wanted


def refusal_of(session: Any, write: Any) -> DatabaseError | None:
    """Run `write` inside a savepoint; answer the database error it provoked, or `None`."""
    savepoint = session.begin_nested()
    try:
        write()
        session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    except DatabaseError as refused:
        savepoint.rollback()
        return refused
    savepoint.commit()
    return None


def write_question(seed: Any, *, kind: str, stream: str | None) -> Any:
    """Insert one question of that kind, in that stream — both named, always.

    `stream` is passed on every call including where it is `None`, which is what
    keeps the shared seeding walker's own fill out of this module: that helper
    gives a question it is not told about a stream that satisfies these rules and
    means nothing (`fill_dependent_columns` in tests/fixtures/supervision.py), and
    a fixture supplying the value under test is `docs/MISTAKES.md` entry 30.
    """
    return seed(QUESTION, {}, **{KIND_COLUMN: kind, STREAM_COLUMN: stream})


@pytest.mark.parametrize("kind", KINDS_THAT_ASK_ABOUT_A_STREAM)
@pytest.mark.parametrize("stream", STREAMS)
def test_a_question_that_asks_about_a_stream_may_name_either_one(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any, kind: str, stream: str
) -> None:
    """The ordinary question, over both kinds and both streams — the control for everything below.

    SPEC §3.2's five are two ratings and two comments, one of each per stream, so
    all four combinations are rows the shipped instrument holds. A schema that
    refused any of them would satisfy every refusal in this module and would also
    make the v1 question set unwritable (`docs/MISTAKES.md` entry 3).

    **A case per combination**, because a rule that admitted `INSTRUCTOR` and not
    `COURSE`, or that was written over the rating kind alone, passes a single
    accepted case and breaks half the report.

    **The mutation it kills:** either `CHECK` written with its sense inverted —
    `(kind = 'workload') != (stream IS NULL)`, or a value list that names one
    stream.
    """
    questions = question_table(metadata_tables)
    require_the_stream_column(questions)
    kind_the_column_enumerates(questions, kind)

    refused = refusal_of(db_session, lambda: write_question(seed_rows, kind=kind, stream=stream))

    assert refused is None, (
        f"A `{kind}` question in the `{stream}` stream was refused: {refused}. SPEC §3.2 ships two "
        "ratings and two comments, one of each per stream, so this is one of the four rows the v1 "
        "question set is made of — a schema that refuses it refuses the instrument, and every "
        "refusal in this module would then be evidence of nothing."
    )


def test_a_workload_question_with_no_stream_is_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The other half of the first rule's control: the workload question belongs to neither group.

    SPEC §5.1 has two comment groups and no third, and §3.2's fifth question is a
    number of hours rather than a judgement about the instructor or about the
    course. So a null here is the correct value rather than missing data, and a
    column made `NOT NULL` would have no honest value to hold for it.

    **The mutation it kills:** `stream` declared `NOT NULL`, which is the shape a
    column "every question has" takes and which refuses the workload question
    outright.
    """
    questions = question_table(metadata_tables)
    require_the_stream_column(questions)
    kind_the_column_enumerates(questions, WORKLOAD_KIND)

    refused = refusal_of(
        db_session, lambda: write_question(seed_rows, kind=WORKLOAD_KIND, stream=None)
    )

    assert refused is None, (
        f"A `{WORKLOAD_KIND}` question with no stream was refused: {refused}. §3.2's fifth "
        "question is hours spent, and §5.1 groups comments under two headings neither of which it "
        "belongs to — so a null is what this row means and the column is nullable to hold it."
    )


@pytest.mark.parametrize("kind", KINDS_THAT_ASK_ABOUT_A_STREAM)
def test_a_question_that_asks_about_a_stream_may_not_leave_it_null(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any, kind: str
) -> None:
    """The first rule, one direction: a question that belongs to a group says which.

    A rating with no stream is a value the trend charts cannot plot — SPEC §5.1
    draws one panel per stream — and a comment with no stream is a comment the
    report has no heading for. The whole reason the column exists is that nothing
    else in the schema carries that fact, so a null on a non-workload question is
    the fact missing.

    **Only the first rule can refuse this row.** The second admits a null (a
    workload question is one), so a schema carrying the value list and not the
    agreement rule fails here and passes the third test below. That is what makes
    a red name the missing rule.

    **The control is the same kind carrying a stream**, written first, so the
    refusal cannot be about questions of this kind being unwritable.

    **The mutation it kills:** the agreement `CHECK` left off, so `stream` is a
    plain nullable column and every question the writer forgets is a question in
    no group.
    """
    questions = question_table(metadata_tables)
    require_the_stream_column(questions)
    kind_the_column_enumerates(questions, kind)

    control = refusal_of(
        db_session, lambda: write_question(seed_rows, kind=kind, stream=INSTRUCTOR_STREAM)
    )
    assert control is None, (
        f"The control — a `{kind}` question in the `{INSTRUCTOR_STREAM}` stream — was refused: "
        f"{control}. Until an ordinary question of this kind inserts, the refusal below says "
        "nothing about the null."
    )

    without = refusal_of(db_session, lambda: write_question(seed_rows, kind=kind, stream=None))
    assert without is not None, (
        f"A `{kind}` question was written with `{STREAM_COLUMN}` null. E4-02's first rule is that "
        "a stream is absent exactly when the question is the workload one; this row is a question "
        "SPEC §5.1 renders under one of two headings, and nothing on it says which. The column is "
        "the only source of that fact in the schema, so a row without it is a comment E4-03 cannot "
        "group and a rating E4-05 cannot plot."
    )
    state = sqlstate_of(without)
    assert state is not None and state.startswith(INTEGRITY_VIOLATION), (
        f"The row was refused with SQLSTATE {state!r}: {without}. An integrity violation is class "
        f"{INTEGRITY_VIOLATION}; anything else means this module built a statement the server "
        "could not run, so the refusal says nothing about the rule under test."
    )


@pytest.mark.parametrize("stream", STREAMS)
def test_a_workload_question_may_not_claim_a_stream(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any, stream: str
) -> None:
    """The first rule, the other direction: the workload question belongs to no group.

    The pair of the test above, and the reason the rule is written as an
    equivalence rather than as "a stream is required". A workload question
    carrying `INSTRUCTOR` would put a number of hours inside the instructor's
    comment group and into the instructor panel of §5.1's stacked pair, where §3.2
    puts a 0-40 hours figure on a shared 1-5 scale.

    **Only the first rule can refuse this row**: the value list admits both
    streams, so a schema carrying the list and not the agreement rule passes here
    and this test names it.

    **The control is the same question with no stream**, so the refusal is known
    to be about the value rather than about workload questions being unwritable.

    **The mutation it kills:** the agreement `CHECK` written one-sided — `stream
    IS NOT NULL OR kind = 'workload'` — which requires a stream where one is due
    and permits one where none is.
    """
    questions = question_table(metadata_tables)
    require_the_stream_column(questions)
    kind_the_column_enumerates(questions, WORKLOAD_KIND)

    control = refusal_of(
        db_session, lambda: write_question(seed_rows, kind=WORKLOAD_KIND, stream=None)
    )
    assert control is None, (
        f"The control — a `{WORKLOAD_KIND}` question with no stream — was refused: {control}. "
        "Until that row inserts, the refusal below says nothing about the stream it carries."
    )

    claimed = refusal_of(
        db_session, lambda: write_question(seed_rows, kind=WORKLOAD_KIND, stream=stream)
    )
    assert claimed is not None, (
        f"A `{WORKLOAD_KIND}` question was written in the `{stream}` stream. §3.2's fifth question "
        "is hours spent on the course, and §5.1's two groups are about the instructor and about "
        "the course materials — a workload figure in either of them is a number rendered as though "
        "it were a judgement, on a chart whose y-scale is 1 to 5."
    )
    state = sqlstate_of(claimed)
    assert state is not None and state.startswith(INTEGRITY_VIOLATION), (
        f"The row was refused with SQLSTATE {state!r}: {claimed}. An integrity violation is class "
        f"{INTEGRITY_VIOLATION}; anything else means this module built a statement the server "
        "could not run, so the refusal says nothing about the rule under test."
    )


def test_a_question_may_not_name_a_stream_the_report_does_not_group_by(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The second rule: the value is one of the two, or nothing.

    SPEC §5.1's report has exactly two comment groups and a two-panel chart, and
    §5.4 shows students "the published comments grouped under the same two
    headings as everywhere else". A third value is a comment that appears under no
    heading on every surface in the product, and the row that produces it is
    written by whichever writer mis-spells the constant.

    **Only the second rule can refuse this row.** The question is a comment
    carrying a non-null stream, so the agreement rule is satisfied and a schema
    with the agreement rule and no value list fails here alone.

    **The control is the same question in a real stream**, so the refusal is about
    the value rather than about the row.

    **The mutation it kills:** the value `CHECK` left off — which is exactly what
    a plain `Text` column is, and the ticket chooses `Text` plus a `CHECK` over a
    Postgres enum deliberately, so the `CHECK` is the whole of the enforcement.
    """
    questions = question_table(metadata_tables)
    require_the_stream_column(questions)
    kind_the_column_enumerates(questions, COMMENT_KIND)

    control = refusal_of(
        db_session, lambda: write_question(seed_rows, kind=COMMENT_KIND, stream=COURSE_STREAM)
    )
    assert control is None, (
        f"The control — a `{COMMENT_KIND}` question in the `{COURSE_STREAM}` stream — was "
        f"refused: {control}. Until it inserts, the refusal below says nothing about the value."
    )

    third = refusal_of(
        db_session, lambda: write_question(seed_rows, kind=COMMENT_KIND, stream=NOT_A_STREAM)
    )
    assert third is not None, (
        f"A question was written in the `{NOT_A_STREAM}` stream. E4-02's second rule is that the "
        f"value is one of {list(STREAMS)} or nothing at all. The report groups comments under two "
        "headings and plots two panels; a third value is a comment with no group on the "
        "instructor's report, on the student's results page and in every roll-up above them."
    )
    state = sqlstate_of(third)
    assert state is not None and state.startswith(INTEGRITY_VIOLATION), (
        f"The row was refused with SQLSTATE {state!r}: {third}. An integrity violation is class "
        f"{INTEGRITY_VIOLATION}; anything else means this module built a statement the server "
        "could not run, so the refusal says nothing about the rule under test."
    )
