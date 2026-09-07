"""The three tables E4-02 adds, and the rules the database holds them to.

Criteria 2, 3, 4 and 5 of `docs/tickets/e4/E4-02-report-schema.md`, plus the
ticket's own decision that no grant is spent here. Criterion 1 — the round trip
on a seeded database — is
`tests/integration/test_the_report_migration_round_trips_on_a_seeded_database.py`,
and `question.stream`'s two `CHECK`s are
`tests/integration/test_a_questions_stream_says_which_side_it_asks_about.py`;
three subjects, three modules, so a red names which of them broke without
anybody opening a file. `alembic check` is asserted by
`tests/integration/test_alembic_baseline.py` for every ticket and is not
repeated here (`docs/MISTAKES.md` entry 19).

**Every rule is attempted at the database, through the model layer.** The
ticket says it in as many words for the summary's uniqueness — "a database
constraint, proven by a refused insert, not an application promise" — and the
same reading governs the rest: what is asserted is that the server refused the
row, and beside it that the refusal was an integrity violation rather than a
complaint about the statement, so a red here cannot be a typo in this module
reading as a schema rule.

**Nothing here names a constraint.** A name in this schema is produced by
`Base.metadata`'s naming convention rather than chosen
(`tests/integration/test_generated_constraint_names.py` is where that is the
subject), so holding one would report a rename as a regression.

**Every refusal is preceded by a control that lands.** A schema which refused
every summary would satisfy every refusal in this file perfectly and would also
make E4-06 unable to store a single row — `docs/MISTAKES.md` entry 3, and the
control is what tells the two apart. The pairs go further than that where the
grain of a rule is the thing at risk: a second summary differing only in its
stream is *accepted*, and two comments released in one batch are *accepted*,
because a `UNIQUE` one column too wide passes every refusal here and breaks the
product quietly.

**Which failure a red is, before the ticket lands.** Every test in this module
stops in its own body on `report_table`, which reports the missing table by
name and lists what is there. That is a failed assertion rather than an error in
setup (`docs/MISTAKES.md` entry 44), and it is the intended red: the tables are
the whole of what the ticket adds.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.supervision import sqlstate_of
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# The three tables the ticket adds, and the membership table the release batch is
# recorded through. Named as constants so that a deliberate rename is a one-line
# change here rather than a search through the messages below.
WEEKLY_SUMMARY = "weekly_summary"
MODERATION_STATE = "moderation_state"
RELEASE_BATCH = "release_batch"
RELEASE_BATCH_MEMBER = "release_batch_member"
REPORT_TABLES = (WEEKLY_SUMMARY, MODERATION_STATE, RELEASE_BATCH, RELEASE_BATCH_MEMBER)

# The subset of them nothing has yet spent a privilege on, and which therefore
# still holds none for either runtime role. **Two tables came out of this list at
# E4-06**, which is the change the grant test below predicted in as many words.
#
#   - `weekly_summary`, because that ticket's Monday job writes it, so it grants
#     the `SELECT, INSERT` it spends.
#   - `moderation_state`, because the same job *reads* it. SPEC §5.1 requires the
#     summaries to "exclude flagged-held content" and ADR 0145 puts that fact
#     nowhere else, so the filter is a `SELECT` on the connection the walk runs on.
#     The rule the test below states is "each ticket grants what it **spends**",
#     and this list — narrowed at E4-06 to the three tables `weekly_summary` came
#     out of — first read it as "what it writes". Dispute E4-06-01 settled it the
#     other way. E4-04 spends the same read from a parallel branch, so one `SELECT`
#     there is the merged end state rather than either ticket's widening.
#
# Both entries live in `RUNTIME_BASE_TABLE_PRIVILEGES` in
# `tests/integration/test_identity_grants.py` with the sentence each comes from,
# and the exact shape of each grant — the verbs held, the verbs withheld, at table
# grain and at column grain — is asserted in
# `tests/integration/test_the_summary_writer_is_granted_insert_and_select_and_nothing_wider.py`,
# which also drives a write over the connection the job actually runs on
# (`docs/MISTAKES.md` entry 46).
TABLES_WITH_NO_WRITER_YET = (RELEASE_BATCH, RELEASE_BATCH_MEMBER)

# The tables E4-02 does not create and writes rows into to reach its own.
ANSWER = "answer"
RESPONSE = "response"

# `weekly_summary`: the grain SPEC §5.1 gives a stored summary — one section, one
# course week, one of the two streams — and the provenance SPEC §7.4 requires of
# every model output.
SECTION_COLUMN = "section_id"
WEEK_COLUMN = "week_id"
STREAM_COLUMN = "stream"
SUMMARY_TEXT_COLUMN = "summary_text"
RESPONSE_COUNT_COLUMN = "response_count"
PROMPT_VERSION_COLUMN = "prompt_version"
MODEL_ID_COLUMN = "model_id"
SUMMARY_GRAIN_COLUMNS = (SECTION_COLUMN, WEEK_COLUMN, STREAM_COLUMN)
SUMMARY_PROVENANCE_COLUMNS = (PROMPT_VERSION_COLUMN, MODEL_ID_COLUMN)

# The two streams SPEC §5.1 groups a report by: "About the instructor" / "About
# the course". Written as the values the column stores rather than discovered,
# because the ticket settles them and a summary of some third stream is the row
# the vocabulary rule exists to refuse.
INSTRUCTOR_STREAM = "INSTRUCTOR"
COURSE_STREAM = "COURSE"

# `moderation_state`: the comment it is about, the state, and when it was decided.
ANSWER_COLUMN = "answer_id"
STATE_COLUMN = "state"

# SPEC §5.2's lifecycle, plus the initial state a comment starts in: "`published`
# -> `flagged-collapsed` … -> `excluded` (with Undo) or `kept`". The spelling is
# the one the ticket's breakdown settles — upper case, and the hyphen written as
# an underscore, as `classification.verdict` and `role_assignment.role` are
# already spelled in this schema.
PUBLISHED = "PUBLISHED"
FLAGGED_COLLAPSED = "FLAGGED_COLLAPSED"
EXCLUDED = "EXCLUDED"
KEPT = "KEPT"
MODERATION_VOCABULARY = (PUBLISHED, FLAGGED_COLLAPSED, EXCLUDED, KEPT)

# A token that is not in it. Deliberately one that *reads* like a state rather
# than a nonsense string: a `CHECK` written as "not empty" refuses `''` and
# accepts this, and refusing nonsense is not the property §5.2 asks for.
NOT_A_MODERATION_STATE = "REVIEWED"

# `release_batch` and its membership table.
BATCH_COLUMN = "batch_id"
CUT_AT_COLUMN = "cut_at"
TERM_COLUMN = "term_id"

# What each of the two release tables carries, whole. **The membership row's
# inventory is the assertion**, not a decoration: SPEC §4 releases held comments
# "batched so that timing cannot identify an author", and the batch's `cut_at` is
# the only time in the design. A per-comment timestamp is a leak nobody exposes
# on the day it is added, which is why the rule is an equality over the whole
# column set rather than a search for a name.
RELEASE_BATCH_COLUMNS = ("id", SECTION_COLUMN, TERM_COLUMN, CUT_AT_COLUMN)
RELEASE_BATCH_MEMBER_COLUMNS = ("id", BATCH_COLUMN, ANSWER_COLUMN)

# `weekly_summary`'s inventory, for the same reason one table over: the person
# walk in `tests/integration/test_identity_column_marker.py` never reaches either
# of these two — neither carries a foreign key path to `user`, `user_identity` or
# `person` — so no sweep in this repository has anything to say about a column
# added to them. The two tables the walk *does* reach are recorded there instead,
# with their columns pinned the same way.
WEEKLY_SUMMARY_COLUMNS = (
    "id",
    SECTION_COLUMN,
    WEEK_COLUMN,
    STREAM_COLUMN,
    SUMMARY_TEXT_COLUMN,
    RESPONSE_COUNT_COLUMN,
    "themes",
    PROMPT_VERSION_COLUMN,
    MODEL_ID_COLUMN,
    "generated_at",
)

# This suite's own values. None of them is a claim about anything the system
# decides.
A_SUMMARY = "Two students described the pacing of week three as too fast."
A_COMMENT = "The worked examples in the Thursday session were the useful part."
A_PROMPT_VERSION = "e4-02-test-prompt-v1"
A_MODEL_ID = "e4-02-test-model"

# The two ends of `response_count`'s range that the schema decides between. Zero
# is a real row rather than an edge case for its own sake: SPEC §5.1 generates a
# summary "even in small-N weeks", so a week the model drew on nothing for is a
# week a summary is still written about, and the count it states is the truth
# about it.
NO_RESPONSES = 0
FEWER_THAN_NO_RESPONSES = -1

# The SQLSTATE class Postgres answers an integrity violation with — foreign key,
# not null, unique, check. Asserted as the class rather than as a particular
# code, because which of them refuses a row is the schema's business: the
# criterion is that the server refused it *for a reason about the data*, and
# `42703` (undefined column) or `42601` (syntax) would mean this module is broken
# rather than that the rule is there.
INTEGRITY_VIOLATION = "23"

# The two connection roles ADR 0001 separates, and the privileges a role can hold
# on a table. Both spellings of "hold" are asked, because a privilege reaches a
# role by three mechanisms and a guard that enumerates them is the shape
# `docs/MISTAKES.md` entry 35 is about: `has_table_privilege` sees a table grant
# and a grant reaching the role through a membership, and is blind to a
# column-scoped one, which `has_column_privilege` is what answers for.
APPLICATION_ROLE = "pulse_app"
CARE_ROLE = "pulse_care"
RUNTIME_ROLES = (APPLICATION_ROLE, CARE_ROLE)
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")

HAS_TABLE_PRIVILEGE = "SELECT has_table_privilege(:role, :relation, :privilege)"
HAS_COLUMN_PRIVILEGE = "SELECT has_column_privilege(:role, :relation, :column, :privilege)"
COLUMNS_OF = text(
    """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = :table
    ORDER BY column_name
    """
)

# The table and column a control probe is aimed at, and the privilege it must
# find there. E0-13 granted `pulse_app` `SELECT, INSERT` on `classification` and
# `tests/integration/test_identity_grants.py` records it; a probe that cannot
# find that one is a probe reporting absence because it is blind, which is the
# whole of entry 35's rule.
A_TABLE_THE_ROLE_CERTAINLY_READS = "classification"
A_COLUMN_THE_ROLE_CERTAINLY_READS = "verdict"


def report_table(tables: dict[str, Any], name: str) -> Any:
    """The declared table called `name`, or a failure saying it is not there.

    Called as the first statement of every test in this module rather than out of
    a fixture, so that a tree without E4-02 in it produces a wall of failed
    assertions naming the table instead of a wall of setup errors
    (`docs/MISTAKES.md` entry 44).
    """
    table = tables.get(name)
    if table is None:
        pytest.fail(
            f"There is no `{name}` table (what is there: {sorted(tables)}). E4-02 creates "
            f"{list(REPORT_TABLES)} in `backend/app/models/report.py` and SPEC §8 lists the "
            "reporting tables. Until the migration lands this is the red every test in this "
            "module reports, and it is the intended one."
        )
    return table


def require_columns(table: Any, names: tuple[str, ...]) -> None:
    """Stop unless `table` has every one of `names`, listing what it does have.

    A message naming the missing column is more use than an insert failing on an
    unknown keyword inside the seeding walker. Each name is a constant at the top
    of this file, so a deliberate rename is a one-line change here.
    """
    absent = [name for name in names if name not in table.c]
    if absent:
        pytest.fail(
            f"`{table.name}` has none of {absent} — it has "
            f"{[column.name for column in table.columns]}. E4-02's breakdown spells every column "
            "of the three tables it adds; a column named some other way is a one-line change at "
            "the top of this file, and a column that is not there at all is the ticket unbuilt."
        )


def refusal_of(session: Any, write: Any) -> DatabaseError | None:
    """Run `write` inside a savepoint; answer the database error it provoked, or `None`.

    A savepoint rather than the surrounding transaction, so a refused write leaves
    the session usable for the next assertion, and `SET CONSTRAINTS ALL IMMEDIATE`
    because a rule written as a deferrable constraint does not fire until commit
    and nothing in this suite commits.
    """
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


def assert_accepted(refused: DatabaseError | None, what: str, why: str) -> None:
    """The control landed. Until it does, the refusal beside it is evidence of nothing."""
    assert refused is None, f"{what} was refused: {refused}. {why}"


def a_section_and_a_week(seed: Any) -> dict[str, Any]:
    """A section and a course week of one term, with the chain that built them.

    Built through one chain, which is what puts them in one term: the walker
    creates the term while building the section's ancestors and the week then
    finds it already there. SPEC §2.2 numbers weeks inside a term, so a summary
    written over a section and a week of two different terms would be a summary
    of a week its own section's calendar does not contain.
    """
    chain: dict[str, Any] = {}
    section = seed("section", chain)
    week = seed("week", chain)
    return {"section": section, "week": week, "term": chain["term"], "chain": chain}


def write_summary(seed: Any, *, where: dict[str, Any], stream: str, **overrides: Any) -> Any:
    """Insert one `weekly_summary` over that section and week, in that stream.

    The text, the count and the provenance are named here rather than left to the
    walker, because two of them are the subject of a test below and a value the
    fixture chose would be a second thing a red could be about.
    """
    values = {
        SECTION_COLUMN: where["section"]["id"],
        WEEK_COLUMN: where["week"]["id"],
        STREAM_COLUMN: stream,
        SUMMARY_TEXT_COLUMN: A_SUMMARY,
        RESPONSE_COUNT_COLUMN: NO_RESPONSES + 1,
        PROMPT_VERSION_COLUMN: A_PROMPT_VERSION,
        MODEL_ID_COLUMN: A_MODEL_ID,
    }
    values.update(overrides)
    return seed(WEEKLY_SUMMARY, {}, **values)


def a_comment(seed: Any) -> Any:
    """One `answer` holding a student's comment, with the response and section behind it.

    The whole chain is built by the walker from one `response`, so the answer's
    response, its section, its week and its term agree with each other without
    this module naming any of them. `comment_text` is supplied because an answer
    holds exactly one of three values (E2-05) and a row holding none is refused —
    which would be a refusal inside this helper rather than a measurement.
    """
    chain: dict[str, Any] = {}
    seed(RESPONSE, chain)
    return seed(ANSWER, chain, comment_text=A_COMMENT)


def columns_of(session: Any, table: str) -> tuple[str, ...]:
    """Every column the database reports on one table, sorted.

    Read from the catalog rather than from `Base.metadata`, because what a
    migration created is the subject and the declaration is the thing it is
    compared against.
    """
    return tuple(session.execute(COLUMNS_OF, {"table": table}).scalars())


# ---------------------------------------------------------------------------
# The tables themselves.
# ---------------------------------------------------------------------------


def test_the_three_report_tables_and_the_membership_table_are_all_there(
    metadata_tables: dict[str, Any],
) -> None:
    """The diagnosis test: which of the four is missing, said once and by name.

    Every other test in this module needs one of these tables before it can
    attempt anything, so without this one a tree with three of the four in it
    reports the same failure from a dozen places and names the ticket from none.

    **The mutation it kills:** a migration that creates the summary and the
    moderation record and leaves the release batch to E4-04 — which is the
    tempting split, since E4-04 is the ticket that releases anything, and it is
    the one E4-02 exists to prevent: the schema E4 shares is reviewed once,
    whole, rather than accreted.
    """
    absent = [name for name in REPORT_TABLES if name not in metadata_tables]
    assert not absent, (
        f"{absent} are not declared. E4-02 adds `weekly_summary` (the stored summary, one row per "
        "section, course week and stream), `moderation_state` (§5.2's lifecycle as an append-only "
        "record) and the release batch as a batch row plus a membership table, all in "
        f"`backend/app/models/report.py`. What is declared: {sorted(metadata_tables)}."
    )


# ---------------------------------------------------------------------------
# Criterion 2 — one summary per section, course week and stream.
# ---------------------------------------------------------------------------


def test_a_summary_of_one_section_week_and_stream_is_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The ordinary summary, and the control every refusal below depends on.

    A test of its own as well as a guard inside each refusal: a schema that
    refused every summary would satisfy criteria 2 and 3 perfectly and would also
    make E4-06 unable to store the thing the epic is about
    (`docs/MISTAKES.md` entry 3). This is the failure that would name that.

    **The mutation it kills:** a `UNIQUE` written over the wrong columns, or a
    `CHECK` on `stream` that admits neither of §5.1's two streams — either leaves
    the honest row refused, and this half catches it.
    """
    summaries = report_table(metadata_tables, WEEKLY_SUMMARY)
    require_columns(summaries, SUMMARY_GRAIN_COLUMNS + SUMMARY_PROVENANCE_COLUMNS)

    where = a_section_and_a_week(seed_rows)
    refused = refusal_of(
        db_session, lambda: write_summary(seed_rows, where=where, stream=INSTRUCTOR_STREAM)
    )

    assert_accepted(
        refused,
        "A summary of one section's course week, in the instructor stream",
        "That is every row E4-06 writes — SPEC §5.1 gives the instructor report one AI summary per "
        "stream per week — so a schema that refuses it refuses the epic, and every refusal in this "
        "module would then be evidence of nothing.",
    )


def test_a_second_summary_of_the_same_section_week_and_stream_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 2: the summary table cannot hold two rows for one section, week and stream.

    The ticket says which mechanism proves it: "a database constraint, proven by a
    refused insert, not an application promise". So the second row is written
    through the model layer and the assertion is that the server would not take
    it.

    **Why it matters beyond tidiness.** A second row for one grain is two answers
    to "what did the model say about this section's instructor stream in week 3",
    and nothing in the design says which of them the report renders — SPEC §5.1
    puts one summary at the head of each comment group. A re-run that appended
    instead of replacing would leave the older text on the screen for as long as
    the reader's query happened to order it first.

    **The mutation it kills:** the `UNIQUE` left off entirely, which is what a
    table created from a plain column list has.
    """
    summaries = report_table(metadata_tables, WEEKLY_SUMMARY)
    require_columns(summaries, SUMMARY_GRAIN_COLUMNS)

    where = a_section_and_a_week(seed_rows)
    control = refusal_of(
        db_session, lambda: write_summary(seed_rows, where=where, stream=INSTRUCTOR_STREAM)
    )
    assert_accepted(
        control,
        "The first summary of this section's week",
        "Until one summary inserts, the refusal below says nothing about a second.",
    )

    again = refusal_of(
        db_session, lambda: write_summary(seed_rows, where=where, stream=INSTRUCTOR_STREAM)
    )
    assert_refused_for_the_data(
        again,
        "A second summary of the same section, course week and stream",
        "Criterion 2: the summary table may hold one row per section, course week and stream, and "
        f"the constraint is over `({SECTION_COLUMN}, {WEEK_COLUMN}, {STREAM_COLUMN})`. Two rows at "
        "one grain are two answers to one question, and §5.1 renders one.",
    )


def test_a_summary_of_the_same_section_and_week_in_the_other_stream_is_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The near miss the refusal above cannot see: the grain includes the stream.

    **This is the pair, and it is the half that catches the likelier defect.** A
    `UNIQUE` over `(section_id, week_id)` alone refuses the second row exactly as
    the test above requires and also refuses the row SPEC §5.1 demands — the
    report carries *two* summaries a week, one for the instructor stream and one
    for the course stream, each leading its own comment group. A schema one
    column short passes the refusal and breaks the product, and nothing else in
    this repository would say so.

    **The mutation it kills:** `UNIQUE (section_id, week_id)`.
    """
    summaries = report_table(metadata_tables, WEEKLY_SUMMARY)
    require_columns(summaries, SUMMARY_GRAIN_COLUMNS)

    where = a_section_and_a_week(seed_rows)
    control = refusal_of(
        db_session, lambda: write_summary(seed_rows, where=where, stream=INSTRUCTOR_STREAM)
    )
    assert_accepted(
        control,
        "The instructor-stream summary of this section's week",
        "Until one summary inserts, accepting a second says nothing about the stream.",
    )

    other = refusal_of(
        db_session, lambda: write_summary(seed_rows, where=where, stream=COURSE_STREAM)
    )
    assert_accepted(
        other,
        "The course-stream summary of the same section and course week",
        "SPEC §5.1 puts two summaries on one week's report — one per stream, each leading its own "
        "comment group — so both rows are ordinary. A uniqueness rule that refuses this one is "
        f"written over `({SECTION_COLUMN}, {WEEK_COLUMN})` rather than over the three columns "
        "criterion 2 names, and it would pass every refusal in this module.",
    )


# ---------------------------------------------------------------------------
# Criterion 3 — a summary with no provenance is a refused insert.
# ---------------------------------------------------------------------------


def test_a_summary_with_no_prompt_version_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 3, half one: `prompt_version` is required of every stored summary.

    SPEC §7.4 requires every model output to store the prompt version and the
    model id, and §6.1's classifier drift panel is the surface that spends them:
    a summary nobody can attribute to a prompt is a summary nobody can re-judge
    when the prompt changes.

    **A separate test from the model id below**, and deliberately so: a schema
    that made one of the two `NOT NULL` and forgot the other would pass a test
    that left both out at once, and the two are written by different halves of the
    same call.

    **The refused row is written in the other stream**, so criterion 2's
    uniqueness rule cannot be what refuses it: the control has already taken the
    instructor stream for this section and week, and a second row in that stream
    would be refused whatever its provenance said.

    **The mutation it kills:** `prompt_version` declared nullable — which is also
    the shape "the writer always sets it anyway" takes, and the whole of what
    criterion 3 refuses to accept as an answer.
    """
    summaries = report_table(metadata_tables, WEEKLY_SUMMARY)
    require_columns(summaries, SUMMARY_GRAIN_COLUMNS + SUMMARY_PROVENANCE_COLUMNS)

    where = a_section_and_a_week(seed_rows)
    control = refusal_of(
        db_session, lambda: write_summary(seed_rows, where=where, stream=INSTRUCTOR_STREAM)
    )
    assert_accepted(
        control,
        "A summary carrying both halves of its provenance",
        "Until a provenanced summary inserts, the refusal below says nothing about the missing "
        "half.",
    )

    without = refusal_of(
        db_session,
        lambda: write_summary(
            seed_rows,
            where=where,
            stream=COURSE_STREAM,
            **{PROMPT_VERSION_COLUMN: None},
        ),
    )
    assert_refused_for_the_data(
        without,
        f"A summary written with `{PROMPT_VERSION_COLUMN}` null",
        "Criterion 3: a summary with no provenance is a refused insert. SPEC §7.4 requires both "
        "halves of every model output's provenance to be stored, and `classification` beside it "
        "carries the same pair for the same reason.",
    )


def test_a_summary_with_no_model_id_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 3, half two: `model_id` is required of every stored summary.

    The mirror of the test above, and the reason the criterion names two columns.
    A stored summary is the one place a reader can ask which model wrote a
    sentence an instructor is reading about their own teaching; SPEC §6.1 prices
    per-task spend from the same field, and §9.3's eval sets are scoped by it.

    **The mutation it kills:** `model_id` declared nullable while
    `prompt_version` is not — the asymmetry a single combined test would miss.

    **The refused row is written in the other stream**, so criterion 2's
    uniqueness rule cannot be what refuses it.
    """
    summaries = report_table(metadata_tables, WEEKLY_SUMMARY)
    require_columns(summaries, SUMMARY_GRAIN_COLUMNS + SUMMARY_PROVENANCE_COLUMNS)

    where = a_section_and_a_week(seed_rows)
    control = refusal_of(
        db_session, lambda: write_summary(seed_rows, where=where, stream=INSTRUCTOR_STREAM)
    )
    assert_accepted(
        control,
        "A summary carrying both halves of its provenance",
        "Until a provenanced summary inserts, the refusal below says nothing about the missing "
        "half.",
    )

    without = refusal_of(
        db_session,
        lambda: write_summary(
            seed_rows,
            where=where,
            stream=COURSE_STREAM,
            **{MODEL_ID_COLUMN: None},
        ),
    )
    assert_refused_for_the_data(
        without,
        f"A summary written with `{MODEL_ID_COLUMN}` null",
        "Criterion 3: a summary with no provenance is a refused insert, and the criterion names "
        "both columns because SPEC §7.4 requires both.",
    )


def test_a_summary_that_drew_on_no_responses_is_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Zero is a count a summary may state, and the lower half of the range pair.

    SPEC §5.1 generates the AI summaries "even in small-N weeks — there, the
    summary is the only comment signal", and a week nobody answered is the
    smallest of those. A schema that refused a zero would force the writer either
    to skip the week or to lie about it, and the count the summary "states the
    response count they draw from" would then be a number that cannot be zero.

    **The mutation it kills:** `CHECK (response_count > 0)`, which is the natural
    typo for the rule the breakdown settles and which no test asserting the
    refusal of a negative count can see.
    """
    summaries = report_table(metadata_tables, WEEKLY_SUMMARY)
    require_columns(summaries, (RESPONSE_COUNT_COLUMN,))

    where = a_section_and_a_week(seed_rows)
    refused = refusal_of(
        db_session,
        lambda: write_summary(
            seed_rows,
            where=where,
            stream=INSTRUCTOR_STREAM,
            **{RESPONSE_COUNT_COLUMN: NO_RESPONSES},
        ),
    )

    assert_accepted(
        refused,
        f"A summary stating `{RESPONSE_COUNT_COLUMN}` = {NO_RESPONSES}",
        "SPEC §5.1 writes a summary even in a small-N week, and a week with no responses at all is "
        "the smallest one. Zero is the honest count for it.",
    )


def test_a_summary_claiming_a_negative_response_count_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The upper half of the same pair: a count below zero is not a count.

    `response_count` is what SPEC §5.1 requires a summary to state — "state the
    response count they draw from" — and it is read straight onto the instructor's
    report. A negative value is not a small number, it is a writer that has
    subtracted something, and a stored one would be rendered.

    **The mutation it kills:** the `CHECK` left off, so the column is a plain
    integer.

    **The refused row is written in the other stream**, so criterion 2's
    uniqueness rule cannot be what refuses it — the control has already taken the
    instructor stream for this section and week.
    """
    summaries = report_table(metadata_tables, WEEKLY_SUMMARY)
    require_columns(summaries, (RESPONSE_COUNT_COLUMN,))

    where = a_section_and_a_week(seed_rows)
    control = refusal_of(
        db_session,
        lambda: write_summary(
            seed_rows,
            where=where,
            stream=INSTRUCTOR_STREAM,
            **{RESPONSE_COUNT_COLUMN: NO_RESPONSES},
        ),
    )
    assert_accepted(
        control,
        f"A summary stating `{RESPONSE_COUNT_COLUMN}` = {NO_RESPONSES}",
        "Until the boundary value inserts, the refusal below could be about the column refusing "
        "every value.",
    )

    negative = refusal_of(
        db_session,
        lambda: write_summary(
            seed_rows,
            where=where,
            stream=COURSE_STREAM,
            **{RESPONSE_COUNT_COLUMN: FEWER_THAN_NO_RESPONSES},
        ),
    )
    assert_refused_for_the_data(
        negative,
        f"A summary stating `{RESPONSE_COUNT_COLUMN}` = {FEWER_THAN_NO_RESPONSES}",
        "The breakdown settles the column as a non-negative count, and §5.1 renders it on the "
        "instructor's report as the number of responses the summary drew on.",
    )


# ---------------------------------------------------------------------------
# Criterion 4 — the moderation lifecycle's vocabulary, and absence as the
# initial state.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", MODERATION_VOCABULARY)
def test_every_state_in_the_lifecycle_vocabulary_is_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any, state: str
) -> None:
    """Criterion 4, the permitted half: each of §5.2's states can be written.

    "`published` -> `flagged-collapsed` … -> `excluded` (with Undo) or `kept`", plus
    the published state a comment starts in. E6 writes the lifecycle and E4 writes
    none of it, so this is the assertion that the vocabulary E6 will need is the
    one the column enumerates — asked now, while the table is being made, rather
    than found by E6 against a `CHECK` two states short.

    **A case per state rather than one test over the set**, because a `CHECK`
    enumerating three of the four passes any test that writes one of the three,
    and the failure output should name the state that cannot be written.

    **The mutation it kills:** any one of the four dropped from the `CHECK` —
    `KEPT` most likely of them, since it is the only state reached by an
    instructor choosing to publish rather than by a classifier.
    """
    states = report_table(metadata_tables, MODERATION_STATE)
    require_columns(states, (ANSWER_COLUMN, STATE_COLUMN))

    comment = a_comment(seed_rows)
    refused = refusal_of(
        db_session,
        lambda: seed_rows(
            MODERATION_STATE, {}, **{ANSWER_COLUMN: comment["id"], STATE_COLUMN: state}
        ),
    )

    assert_accepted(
        refused,
        f"A moderation state of `{state}`",
        "SPEC §5.2's lifecycle is `published` -> `flagged-collapsed` -> `excluded` or `kept`, and "
        f"criterion 4 requires the enforced value set to match it plus the initial state. "
        f"`{state}` is one of the four; a schema that cannot store it is a lifecycle E6 cannot "
        "walk.",
    )


def test_a_state_outside_the_lifecycle_vocabulary_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 4, the refused half: "a planted out-of-vocabulary write is refused".

    The planted token reads like a state rather than like nonsense, which is the
    point: a `CHECK` that only refuses an empty string, or a column with no
    `CHECK` at all, takes `REVIEWED` without complaint and leaves the lifecycle a
    convention. §5.2's flow has exact transitions and an undo in both directions,
    and a fifth state nobody defined is a comment in a state no screen renders.

    **The mutation it kills:** the `CHECK` left off the column, which is what a
    plain `Text` column is — the shape the ticket deliberately chooses over a
    Postgres enum, and the shape whose whole safety is the constraint beside it.
    """
    states = report_table(metadata_tables, MODERATION_STATE)
    require_columns(states, (ANSWER_COLUMN, STATE_COLUMN))

    comment = a_comment(seed_rows)
    control = refusal_of(
        db_session,
        lambda: seed_rows(
            MODERATION_STATE, {}, **{ANSWER_COLUMN: comment["id"], STATE_COLUMN: PUBLISHED}
        ),
    )
    assert_accepted(
        control,
        f"A moderation state of `{PUBLISHED}`",
        "Until an in-vocabulary state inserts, the refusal below could be a table that refuses "
        "every row.",
    )

    planted = refusal_of(
        db_session,
        lambda: seed_rows(
            MODERATION_STATE,
            {},
            **{ANSWER_COLUMN: comment["id"], STATE_COLUMN: NOT_A_MODERATION_STATE},
        ),
    )
    assert_refused_for_the_data(
        planted,
        f"A moderation state of `{NOT_A_MODERATION_STATE}`",
        "Criterion 4: the moderation status has a database-enforced value set matching §5.2's "
        f"lifecycle vocabulary plus the initial state, and {list(MODERATION_VOCABULARY)} is the "
        "whole of it. The ticket chooses `Text` plus a `CHECK` over a Postgres enum deliberately, "
        "so the `CHECK` is the entire enforcement.",
    )


def test_two_moderation_states_for_one_comment_are_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The record is append-only, so one comment may carry a decision trail.

    SPEC §5.2's lifecycle has an undo in both directions — "`excluded` (with Undo)
    or `kept` … Undo returns it to review" — and SPEC §8 records moderation
    transitions as rows with "both directions logged". A record that permitted one
    row per comment could not express any of that: the second decision would have
    to overwrite the first, and the trail the accountability log is built on
    (§5.2's anti-cherry-picking mechanism) would be the current state and nothing
    else.

    **The mutation it kills:** `UNIQUE (answer_id)` on `moderation_state`, which
    is the natural shape for a table whose latest row governs and which turns the
    append-only record into a mutable column with extra steps.
    """
    states = report_table(metadata_tables, MODERATION_STATE)
    require_columns(states, (ANSWER_COLUMN, STATE_COLUMN))

    comment = a_comment(seed_rows)
    first = refusal_of(
        db_session,
        lambda: seed_rows(
            MODERATION_STATE,
            {},
            **{ANSWER_COLUMN: comment["id"], STATE_COLUMN: FLAGGED_COLLAPSED},
        ),
    )
    assert_accepted(
        first,
        "The first moderation state for this comment",
        "Until one state row inserts, a second says nothing.",
    )

    second = refusal_of(
        db_session,
        lambda: seed_rows(
            MODERATION_STATE, {}, **{ANSWER_COLUMN: comment["id"], STATE_COLUMN: KEPT}
        ),
    )
    assert_accepted(
        second,
        "A second moderation state for the same comment",
        "§5.2 moves a comment from `flagged-collapsed` to `kept` after an instructor reviews it, "
        "and §8 requires both directions to be logged. A record that holds one row per comment "
        "cannot hold a decision trail at all.",
    )


def test_a_comment_with_no_moderation_state_row_is_a_comment_in_the_initial_state(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """Criterion 4's other half: the initial state is the absence of a row.

    The breakdown settles it — a comment with no `moderation_state` row is
    published, which is what makes "exactly one value ever written during E4" a
    count of zero writes and leaves every writer to E6. This is the assertion that
    the schema really is shaped that way, and it has two halves that are both
    load-bearing:

      - **`answer` carries no moderation column.** If the state lived on the
        answer row as well, the absence of a record row would mean nothing and
        two places would answer the same question — the mutable-column design the
        ticket's own decision weighs and rejects.
      - **A comment can exist with no state row at all.** Written and counted,
        rather than assumed: a foreign key pointing the other way, or a `NOT
        NULL` reference from `answer`, would make a comment without a decision
        unwritable, and every comment E4-04 conceals is exactly that.

    **The mutation it kills:** a `state` column added to `answer` "so the read
    path has somewhere to look", which leaves this schema with two sources of
    truth and E6's log hanging off neither.

    **Not a §4.1 confidentiality assertion, and it is not marked as one.** What is
    counted here is a row this test wrote the parent of; the concealment rules
    that rest on the state are E4-04's, and they are asserted as refusals on a
    read path rather than as an absence in a table.
    """
    states = report_table(metadata_tables, MODERATION_STATE)
    require_columns(states, (ANSWER_COLUMN,))
    answers = metadata_tables.get(ANSWER)
    assert answers is not None, (
        f"There is no `{ANSWER}` table (what is there: {sorted(metadata_tables)}). E2-05 creates "
        "it, and both halves of this test are about where a comment's moderation status is and is "
        "not."
    )

    moderation_columns = sorted(
        column.name
        for column in answers.columns
        if STATE_COLUMN in column.name or "moderation" in column.name
    )
    assert not moderation_columns, (
        f"`{ANSWER}` carries {moderation_columns}. E4-02 settles the moderation status as its own "
        f"append-only record beside `classification`, with the latest `{MODERATION_STATE}` row "
        "governing and the absence of one meaning published. A column on the answer row beside it "
        "is a second answer to the same question, and the two disagree the first time either is "
        "written alone."
    )

    comment = a_comment(seed_rows)
    assert comment["id"] is not None, (
        "The helper did not produce a comment, so what is counted below is the state of nothing "
        "and would be zero however this schema was shaped."
    )

    # S608: both names are constants at the top of this file, and the answer's key
    # is bound rather than interpolated.
    count_states = f"SELECT count(*) FROM public.{MODERATION_STATE} WHERE {ANSWER_COLUMN} = :answer"  # noqa: S608
    held = db_session.execute(text(count_states), {"answer": comment["id"]}).scalar_one()
    assert held == 0, (
        f"A comment that has just been written already carries {held} moderation state row(s). The "
        "initial state is the absence of a row — E4 writes none at all — so something is writing "
        "one on insert, and E4-04's concealment queries would then be built against a table whose "
        "rows nobody in this epic put there."
    )


# ---------------------------------------------------------------------------
# The release batch: a set released together, and no time of its own.
# ---------------------------------------------------------------------------


def test_a_comment_released_in_a_batch_is_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The ordinary release, and the control the two refusals below depend on.

    SPEC §4 holds comments from under-threshold weeks and surfaces them "once the
    section's cumulative comment volume for the term crosses the threshold,
    batched so that timing cannot identify an author". A membership row is one
    comment in one such batch, and E4-04 writes a set of them at once.

    **The mutation it kills:** a foreign key written against the wrong table or
    the wrong column, which leaves the honest row refused.
    """
    members = report_table(metadata_tables, RELEASE_BATCH_MEMBER)
    require_columns(members, (BATCH_COLUMN, ANSWER_COLUMN))
    report_table(metadata_tables, RELEASE_BATCH)

    batch = seed_rows(RELEASE_BATCH, {})
    comment = a_comment(seed_rows)
    refused = refusal_of(
        db_session,
        lambda: seed_rows(
            RELEASE_BATCH_MEMBER, {}, **{BATCH_COLUMN: batch["id"], ANSWER_COLUMN: comment["id"]}
        ),
    )

    assert_accepted(
        refused,
        "One comment released in one batch",
        "That is every row E4-04 writes when a section crosses the threshold, so a schema that "
        "refuses it refuses the release and the two refusals below would be evidence of nothing.",
    )


def test_a_comment_released_a_second_time_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """A comment belongs to at most one batch, and the database is what says so.

    The breakdown settles it — a comment is released at most once — and SPEC §4 is
    why it matters rather than being tidy. The batch is what stands between a
    released comment and its author: the only time in the design is the batch's
    `cut_at`, so a comment in two batches has two release times, and the
    difference between them is a signal about one comment that the batching exists
    to remove.

    **The mutation it kills:** the `UNIQUE` on the membership's `answer_id` left
    off, so a second release is an ordinary insert and E4-04 re-releasing after a
    failure silently doubles a comment.
    """
    members = report_table(metadata_tables, RELEASE_BATCH_MEMBER)
    require_columns(members, (BATCH_COLUMN, ANSWER_COLUMN))

    first_batch = seed_rows(RELEASE_BATCH, {})
    second_batch = seed_rows(RELEASE_BATCH, {})
    comment = a_comment(seed_rows)

    control = refusal_of(
        db_session,
        lambda: seed_rows(
            RELEASE_BATCH_MEMBER,
            {},
            **{BATCH_COLUMN: first_batch["id"], ANSWER_COLUMN: comment["id"]},
        ),
    )
    assert_accepted(
        control,
        "The first release of this comment",
        "Until one membership inserts, the refusal below says nothing about a second.",
    )

    again = refusal_of(
        db_session,
        lambda: seed_rows(
            RELEASE_BATCH_MEMBER,
            {},
            **{BATCH_COLUMN: second_batch["id"], ANSWER_COLUMN: comment["id"]},
        ),
    )
    assert_refused_for_the_data(
        again,
        "A second release of a comment that is already in a batch",
        "A comment is released at most once. Two memberships give one comment two release times, "
        "and SPEC §4 batches the release precisely so that timing cannot identify an author.",
    )


def test_two_comments_released_in_one_batch_are_accepted(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """The near miss the refusal above cannot see: the batch holds a set.

    **This is the pair.** A `UNIQUE` on the membership's `batch_id` — or on the
    pair `(batch_id, answer_id)` written where `answer_id` alone was meant —
    refuses the second release above just as required, and also refuses the only
    thing a batch is for: E4-04 must be able to release a *set* atomically, which
    is the constraint the ticket states for either shape of this decision. A
    schema one column wrong passes the refusal and makes the epic's release
    impossible, one comment at a time.

    **The mutation it kills:** `UNIQUE (batch_id)` on the membership table.
    """
    members = report_table(metadata_tables, RELEASE_BATCH_MEMBER)
    require_columns(members, (BATCH_COLUMN, ANSWER_COLUMN))

    batch = seed_rows(RELEASE_BATCH, {})
    first = a_comment(seed_rows)
    second = a_comment(seed_rows)
    assert first["id"] != second["id"], (
        "The helper produced one comment twice, so the second membership below is a second release "
        "of one comment and this test is measuring the rule the test above measures."
    )

    control = refusal_of(
        db_session,
        lambda: seed_rows(
            RELEASE_BATCH_MEMBER, {}, **{BATCH_COLUMN: batch["id"], ANSWER_COLUMN: first["id"]}
        ),
    )
    assert_accepted(
        control,
        "The first comment in this batch",
        "Until one membership inserts, accepting a second says nothing about the batch.",
    )

    beside_it = refusal_of(
        db_session,
        lambda: seed_rows(
            RELEASE_BATCH_MEMBER, {}, **{BATCH_COLUMN: batch["id"], ANSWER_COLUMN: second["id"]}
        ),
    )
    assert_accepted(
        beside_it,
        "A second comment in the same batch",
        "A batch is a set of comments released together — that is the whole of what batching means "
        "in SPEC §4 — so a membership table that holds one comment per batch makes every batch a "
        "single comment and restores the per-comment timing the batching removes.",
    )


def test_a_release_naming_a_batch_that_does_not_exist_is_refused(
    db_session: Any, metadata_tables: dict[str, Any], seed_rows: Any
) -> None:
    """A membership hangs off a real batch, and the database is what checks it.

    A membership whose batch does not exist is a released comment with no release
    time at all — the batch row is where `cut_at` lives, so the reference is the
    only thing that dates the release. E4-04 reads the batch to decide what is
    visible; a dangling membership is a comment that is released according to one
    table and unreleased according to the other.

    **The mutation it kills:** the foreign key left off the membership's
    `batch_id`, so the column is a plain uuid — which is exactly what a batch
    label stamped onto a comment would be, the alternative shape the ticket names
    and rejects.
    """
    members = report_table(metadata_tables, RELEASE_BATCH_MEMBER)
    require_columns(members, (BATCH_COLUMN, ANSWER_COLUMN))

    batch = seed_rows(RELEASE_BATCH, {})
    comment = a_comment(seed_rows)
    control = refusal_of(
        db_session,
        lambda: seed_rows(
            RELEASE_BATCH_MEMBER, {}, **{BATCH_COLUMN: batch["id"], ANSWER_COLUMN: comment["id"]}
        ),
    )
    assert_accepted(
        control,
        "A release naming a batch that exists",
        "Until an ordinary membership inserts, the refusal below could be about anything on the "
        "row.",
    )

    # A second comment, and not the one already in a batch: reusing that one would
    # leave the unique rule from the test above able to refuse this row, and the
    # refusal would say nothing about the batch reference. Built here rather than
    # inside the write below, so that a failure to build it is not read as the
    # database refusing the membership.
    unreleased = a_comment(seed_rows)
    nowhere = uuid4()
    dangling = refusal_of(
        db_session,
        lambda: seed_rows(
            RELEASE_BATCH_MEMBER,
            {},
            **{BATCH_COLUMN: nowhere, ANSWER_COLUMN: unreleased["id"]},
        ),
    )
    assert_refused_for_the_data(
        dangling,
        f"A release naming batch {nowhere}, which no row is",
        "The comment in it has never been released, so the membership's unique rule cannot be what "
        "refused this row. The batch row carries `cut_at`, the only release time in the design, so "
        "a membership with no batch behind it is a released comment nothing can date and nothing "
        "can un-release.",
    )


@pytest.mark.invariant
def test_a_released_comment_carries_no_time_of_its_own(
    db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """SPEC §4's batching, made structural: the batch's `cut_at` is the only time.

    "Comments from under-threshold weeks … surface as raw text once the section's
    cumulative comment volume for the term crosses the threshold, **batched so
    that timing cannot identify an author**", and §4 one line down: "timestamps
    are never shown with comments". The ticket puts the consequence plainly — a
    stored timestamp nobody exposes today is a leak someone ships tomorrow — so
    the rule is that no per-comment release time exists anywhere, not that no view
    selects one.

    **Asserted as an equality over the whole column set rather than as a search
    for a name.** A test that looked for `released_at` would pass against
    `surfaced_on`, `first_shown`, or a `created_at` added by a later ticket's
    convention; the inventory cannot be widened without this going red, whatever
    the column is called. That is the same shape as the column pins in
    `tests/integration/test_identity_column_marker.py`, and this table is one the
    person walk there *does* reach, so its entry pins the same list from the other
    side.

    **The control is the batch's own `cut_at`**, required to be found. Without it
    this test reports the absence of a timestamp column equally well against a
    reading that cannot see a timestamp column at all, and a guard that only ever
    reports absence cannot say which mechanisms it can see (`docs/MISTAKES.md`
    entry 35).

    **The mutation it kills:** `released_at` added to the membership row "for
    debugging", which no other test in this repository would notice and which
    makes the ordering of a term's held comments recoverable one row at a time.
    """
    report_table(metadata_tables, RELEASE_BATCH_MEMBER)
    report_table(metadata_tables, RELEASE_BATCH)

    on_the_batch = columns_of(db_session, RELEASE_BATCH)
    assert CUT_AT_COLUMN in on_the_batch, (
        f"`{RELEASE_BATCH}` carries {list(on_the_batch)} and none of them is `{CUT_AT_COLUMN}`. "
        "The batch's cut time is the one time the design has, and until this reading can find it "
        "on the table that certainly has it, its silence about the membership row means nothing."
    )

    on_the_membership = columns_of(db_session, RELEASE_BATCH_MEMBER)
    assert sorted(on_the_membership) == sorted(RELEASE_BATCH_MEMBER_COLUMNS), (
        f"`{RELEASE_BATCH_MEMBER}` carries {list(on_the_membership)}; it was designed to carry "
        f"{list(RELEASE_BATCH_MEMBER_COLUMNS)} and nothing else. A membership row is a comment and "
        "the batch it went out in — SPEC §4 batches the release so that timing cannot identify an "
        "author, and the batch's `cut_at` is the only time in the design. A column added here is "
        "either a per-comment time, which is the leak, or something the design has not weighed; "
        "either way it is a deliberate change to what this table is, and it belongs in the pull "
        "request that argues for it."
    )


def test_the_report_tables_the_person_walk_never_reaches_carry_only_their_declared_columns(
    db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 5, for the two tables no sweep in this repository can see.

    `tests/integration/test_identity_column_marker.py` walks foreign keys from
    `user`, `user_identity` and `person` to a fixed point and asks its questions
    of everything it reaches. `moderation_state` and `release_batch_member` are
    reached — both reference `answer` — and each has an entry there recording what
    it carries and why the sweeps' silence about it is correct. **These two are
    not reached at all**: `weekly_summary` references a section and a week, and
    `release_batch` a section and a term, so no path leads from either to a
    person and no rule in that module has anything to say about a column added to
    them. That blind spot is named in E1-01's deferred item — "any identity column
    on a table with no foreign-key path to `user`, `user_identity` or `person`" —
    and an inventory is the only answer available to a test.

    **What this is not.** It is not a claim that these tables are harmless; it is
    the record of the columns a reviewer read when they judged them so, and the
    first column added to either expires it. `weekly_summary` holds an aggregate —
    a section, a week, a stream, generated text, a count and the provenance §7.4
    requires — and `release_batch` holds a section, a term and the cut time.
    Neither references a person, and this is what says so tomorrow.

    **The mutation it kills:** `author_user_id`, `first_responder`, or any other
    reference added to `weekly_summary` to make some later query easier — which
    would put a person one hop from a table the identity sweeps do not visit, and
    which nothing else in this repository would report.
    """
    report_table(metadata_tables, WEEKLY_SUMMARY)
    report_table(metadata_tables, RELEASE_BATCH)

    pinned = {
        WEEKLY_SUMMARY: sorted(WEEKLY_SUMMARY_COLUMNS),
        RELEASE_BATCH: sorted(RELEASE_BATCH_COLUMNS),
    }
    live = {name: sorted(columns_of(db_session, name)) for name in pinned}
    assert live == pinned, (
        f"Pinned against live: {pinned} versus {live}. Each of these two tables is outside the "
        "person walk in `tests/integration/test_identity_column_marker.py`, so nothing else in "
        "this repository looks at what they carry. A column that arrived here is either a "
        "reference to a person on a table nothing sweeps, or a deliberate addition whose pull "
        "request updates this list and says what it read."
    )


# ---------------------------------------------------------------------------
# The grants this ticket does not spend.
# ---------------------------------------------------------------------------


def test_neither_runtime_role_holds_any_privilege_on_a_table_with_no_writer_yet(
    db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """The ticket's own boundary: a privilege lands in the change that uses it.

    E4-02 creates four tables and writes to none of them. The writers are other
    tickets — E4-06 for the summary, E4-04 for the release, E6 for the moderation
    lifecycle — and each grants what it spends, which is the rule every grants
    file in `backend/app/views_sql/` states and the ticket's own known trap: "a
    grant added 'for later' is scope … granting it now widens the runtime role for
    a writer that does not exist."

    **Two of the four have since been spent on, exactly as the last paragraph of
    this docstring predicted, and the second one corrected a misreading of the rule
    above.** E4-06's Monday job writes `weekly_summary` — and it *reads*
    `moderation_state`, because SPEC §5.1 has the AI summaries "exclude
    flagged-held content" and ADR 0145 puts that fact in no other table. Neither is
    in the list this test walks any more. The verbs each holds and the verbs each
    does not are asserted in
    `tests/integration/test_the_summary_writer_is_granted_insert_and_select_and_nothing_wider.py`
    and recorded in `RUNTIME_BASE_TABLE_PRIVILEGES` with the sentence they come
    from. The rule is "grants what it **spends**", not "what it writes"; this list
    briefly read it the second way, and dispute E4-06-01 is where that was settled.
    What is left here is the two tables nothing has spent anything on, and the
    boundary is unchanged for them.

    **Both currencies are asked, because a privilege reaches a role three ways.**
    `has_table_privilege` answers for a table grant and for one arriving through a
    role membership, and is blind to a column-scoped grant;
    `has_column_privilege` is what sees that one. A guard that enumerated
    mechanisms and missed the one the design uses is `docs/MISTAKES.md` entry 35,
    and the reason both are here rather than the first alone.

    **Two controls, and neither is ceremony.** Each probe has to *find* the
    privilege `pulse_app` certainly holds on `classification` — `SELECT`, granted
    by E0-13 and recorded in `tests/integration/test_identity_grants.py`. A probe
    that cannot see a grant it is pointed straight at reports absence everywhere,
    and this test would then be green against a database with every privilege in
    it.

    **When this goes red for a good reason**, which has now happened twice and will
    happen again: E4-06 granted the summary writer its `SELECT, INSERT` and its
    read of `moderation_state`, and E4-04 grants the release path what it needs.
    That is a widening of the runtime role recorded deliberately, in the pull
    request that makes it — the entry moves into
    `RUNTIME_BASE_TABLE_PRIVILEGES` in `test_identity_grants.py` with the sentence
    it comes from, and the table's name comes out of the list here.

    **The mutation it kills:** `GRANT SELECT, INSERT ON public.release_batch TO
    pulse_app` written into a migration because the writer will need it
    eventually.
    """
    for name in TABLES_WITH_NO_WRITER_YET:
        report_table(metadata_tables, name)

    control_table = db_session.execute(
        text(HAS_TABLE_PRIVILEGE),
        {
            "role": APPLICATION_ROLE,
            "relation": f"public.{A_TABLE_THE_ROLE_CERTAINLY_READS}",
            "privilege": "SELECT",
        },
    ).scalar_one()
    assert control_table, (
        f"`{APPLICATION_ROLE}` does not hold `SELECT` on "
        f"`{A_TABLE_THE_ROLE_CERTAINLY_READS}` according to `has_table_privilege`, and E0-13 "
        "granted exactly that. So this reading reports absence whatever is granted, and everything "
        "below is a fact about a blind probe rather than about the new tables."
    )
    control_column = db_session.execute(
        text(HAS_COLUMN_PRIVILEGE),
        {
            "role": APPLICATION_ROLE,
            "relation": f"public.{A_TABLE_THE_ROLE_CERTAINLY_READS}",
            "column": A_COLUMN_THE_ROLE_CERTAINLY_READS,
            "privilege": "SELECT",
        },
    ).scalar_one()
    assert control_column, (
        f"`{APPLICATION_ROLE}` does not hold `SELECT` on "
        f"`{A_TABLE_THE_ROLE_CERTAINLY_READS}.{A_COLUMN_THE_ROLE_CERTAINLY_READS}` according to "
        "`has_column_privilege`, and a table-wide grant covers every column of the table. The "
        "column-grain half of this test is therefore blind, which is the half that sees the "
        "grant `has_table_privilege` cannot report at all."
    )

    held = []
    for role in RUNTIME_ROLES:
        for name in TABLES_WITH_NO_WRITER_YET:
            for privilege in TABLE_PRIVILEGES:
                if db_session.execute(
                    text(HAS_TABLE_PRIVILEGE),
                    {"role": role, "relation": f"public.{name}", "privilege": privilege},
                ).scalar_one():
                    held.append(f"{role} holds {privilege} on public.{name}")
            for column in columns_of(db_session, name):
                for privilege in COLUMN_PRIVILEGES:
                    if db_session.execute(
                        text(HAS_COLUMN_PRIVILEGE),
                        {
                            "role": role,
                            "relation": f"public.{name}",
                            "column": column,
                            "privilege": privilege,
                        },
                    ).scalar_one():
                        held.append(f"{role} holds {privilege} on public.{name}.{column}")

    assert not held, (
        f"{sorted(held)}. E4-02 adds no grant, and nothing has yet spent a privilege on these two "
        "tables: the release path is E4-04's, and a privilege lands in the change that uses it — "
        "as `weekly_summary`'s write and `moderation_state`'s read both did at E4-06, which is why "
        "neither is walked here any more. An entry naming a column is a grant "
        "`has_table_privilege` does not report at all. If "
        "one of these is a deliberate grant, it belongs in the ticket that spends it, recorded in "
        "`RUNTIME_BASE_TABLE_PRIVILEGES` in `tests/integration/test_identity_grants.py` with the "
        "sentence it comes from — and this list shortens in the same pull request."
    )
