"""`grade_sync` and `ags_call` — ticket E3-02, criteria 3, 5 and 6.

> 5. `grade_sync` can express the retry identity ADR 0052 depends on: the latest
>    row for a `(section_id, user_id)` pair gives back what was last sent, exactly
>    as sent, and when.
> 6. A second post for the same student writes a **second row**, and the first row
>    is still readable afterwards with its original value.

SPEC §8 names both tables and settles the first one's grain in a sentence:
"`grade_sync` is **append-only, at the grain of one row per post**: each row
records the score as it was sent, the timestamp sent with it, the outcome, and the
student and section it concerns, and a failed attempt is a row too. The latest row
for a `(section_id, user_id)` pair is what identifies a retry and what the
recompute compares against." ADR 0124 is the argument, and it is not reopened
here: this module asserts the grain rather than debating it.

**Why the grain is a criterion and not a schema detail.** An already-posted score
can be lowered afterwards — E2-08's asynchronous re-classification can flip a
comment weeks after the window shut, which lowers the numerator of a number a
student was already shown — so E3-06 re-posts whenever a recomputation changes the
value. Under a last-value grain that re-post *overwrites* the row, and the number
the platform was previously told is gone from Pulse entirely. The question that
gets asked when a grade is disputed is "what did we send, and when", and only an
append-only log can answer it.

**The trap the ticket names, planted rather than described.** ADR 0124: "Every
reader must ask for the latest row and not for 'the' row" — a query that returns
one row against a fixture holding one post returns the wrong row against a term's
worth of them, which is `docs/MISTAKES.md` entry 3 wearing a green tick. So every
test here that says "latest" plants **two** rows, and **the newer one is inserted
first**: a reader that answers with the last row written, or with whatever the
table happens to return unordered, is wrong on this fixture and right on a fixture
built the obvious way.

**Byte identity is why the score is a string.** ADR 0052 has a platform accept a
score whose timestamp equals the one it holds as a retry of the same delivery, and
E3-04 leans on that after a network timeout: it re-sends the identical body,
because the timestamp names the recomputation rather than the attempt. A value the
poster re-derives is not provably the value it retries — `61.5` and `61.50` are
one number and two deliveries — so the assertions below are about the string that
comes back and not about the quantity it denotes.

**What this module does not decide.** The spelling of the two outcome values is
read off the column rather than written here, and `ags_call`'s columns are asserted
as a requirement rather than as an exact set: the work order leaves open whether it
carries a count column analogous to `nrps_call.members_seen`, and an equality here
would settle that in a test. The exact column set of `grade_sync` is pinned in one
place and one only — `REACHED_TABLES_THAT_CARRY_NOTHING` in
`tests/integration/test_identity_column_marker.py`, where it sits beside the
judgement it was written against, so a column arriving expires that judgement
rather than merely failing a count (`docs/MISTAKES.md` entry 19: not two copies of
one expectation).

**Which failure a red here is.** Before E3-02 lands, everything except the two
controls at the foot is expected red on `passback_table` failing by name — there is
no `grade_sync` and no `ags_call` in `Base.metadata` — which is a failed assertion
naming the deliverable rather than a collection error. The controls must be green
today.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fixtures.indexes import index_key_columns, indexes_leading_with
from fixtures.supervision import (
    foreign_key_columns,
    seed_row,
    single_primary_key,
    sqlstate_of,
    stored_type,
)
from sqlalchemy import select, text
from sqlalchemy.exc import DatabaseError, StatementError

pytestmark = pytest.mark.integration

# The two tables SPEC §8 names, in `backend/app/models/grades.py` and beside
# `NrpsCall` in `backend/app/models/lti.py` respectively (SPEC §13's layout).
GRADE_SYNC = "grade_sync"
AGS_CALL = "ags_call"

# What a `grade_sync` row has to carry, from SPEC §8's sentence: the score as it
# was sent, the timestamp sent with it, the ledger that went with it (§3.4's
# per-week comment), the outcome, the response code where there was one, the
# student and the section, and when the row was written. **A requirement rather
# than an equality** — the exact set is pinned once, in the identity-marker
# module's own inventory, with the judgement it was written against.
GRADE_SYNC_REQUIRED = (
    "score_text",
    "score_timestamp",
    "ledger_text",
    "outcome",
    "response_code",
    "created_at",
)

# What an `ags_call` row has to carry, at the grain SPEC §6.1 gives it — "each at
# the grain of one HTTP call the tool made to a platform service" — modelled on
# `nrps_call`, whose own columns are `url`, `response_code`, `members_seen` and
# `called_at`. `members_seen` has no required analogue here and is deliberately
# absent from this list: the work order leaves that open and a test naming it
# would close it.
AGS_CALL_REQUIRED = ("url", "response_code", "called_at")

# Column-name fragments that would mean a platform's response *body* is stored on
# the row. ADR 0129's decision, asserted as the forbidden state rather than the
# permitted one (`docs/MISTAKES.md` entry 2): a failed attempt records the
# platform's response *code*, never its body, which is an unbounded third-party
# string written once per post.
A_STORED_BODY = ("body", "payload", "content", "response_text", "response_json")

# The two outcome values, matched case-insensitively against whatever the column
# declares. **Fragments rather than spellings**: the ticket settles that there are
# two outcomes and what they mean, and this module has no business deciding
# whether they are written `posted` or `POSTED`.
POSTED_FRAGMENT = "post"
FAILED_FRAGMENT = "fail"

# The two posts every "latest row" test plants, differing in every value that is
# compared. One constant each rather than a shared template, because a restore, a
# reader or an upsert that answered with the wrong row would still agree with
# itself on any field the two happened to share.
#
# **`score_text` carries the trailing zero on purpose.** A `Numeric` or a `float`
# column round-trips `61.50` as `61.5`, and ADR 0052's retry identity is byte
# equality of the body a platform already accepted — so this one character is the
# whole difference between a schema that can express a retry and one that cannot.
#
# **The second post failed and carries no response code**, which is
# `nrps_call`'s own semantics for the same column: NULL means the call never
# reached the platform at all. It is here rather than in a test of its own because
# a pair of rows that differed only in their score would let a comparison pass
# while `outcome` and `response_code` came back from either row.
FIRST_POST: dict[str, Any] = {
    "score_text": "61.50",
    "score_timestamp": datetime(2026, 9, 14, 18, 30, tzinfo=UTC),
    "ledger_text": "Week 1: 4 of 5 items\nWeek 2: 5 of 5 items",
    "response_code": 200,
    "created_at": datetime(2026, 9, 14, 18, 30, 5, tzinfo=UTC),
}
SECOND_POST: dict[str, Any] = {
    "score_text": "48.00",
    "score_timestamp": datetime(2026, 10, 5, 9, 15, tzinfo=UTC),
    "ledger_text": "Week 1: 4 of 5 items\nWeek 2: 5 of 5 items\nWeek 3: 0 of 5 items",
    "response_code": None,
    "created_at": datetime(2026, 10, 5, 9, 15, 2, tzinfo=UTC),
}

# The score spellings criterion 5 is asserted over. Each is a value E3-04 could
# legitimately send and each survives a `Text` column unchanged; none of them
# survives a numeric one, which is the whole point of the criterion.
BYTE_FRAGILE_SCORES = ("61.50", "100", "0.00", "83.333")

# An outcome no design in this ticket names. Distinctive so that a database which
# accepted it can be seen to have accepted this exact string.
AN_UNNAMED_OUTCOME = "e3-02-not-an-outcome"

# `insufficient_privilege` — what Postgres raises when a role attempts something no
# grant covers. Named rather than inferred from the message, because a message is
# localised and a SQLSTATE is not.
INSUFFICIENT_PRIVILEGE = "42501"


# ---------------------------------------------------------------------------
# Reading the two tables. Nothing here asserts a criterion; each helper either
# answers a reading or stops with a message naming what is not there.
# ---------------------------------------------------------------------------


def passback_table(tables: dict[str, Any], name: str) -> Any:
    """The declared table called `name`, or a failure naming what E3-02 is asked to add.

    `require_table`'s own message names the tickets that created the org and
    calendar tables, which is the right message for a caller asking about one of
    those and the wrong one here: on the current tree every test in this module
    stops on this line, and what a reader needs to see is the deliverable that is
    not there rather than a list of the ones that are.
    """
    table = tables.get(name)
    if table is None:
        pytest.fail(
            f"There is no `{name}` table (what is there: {sorted(tables)}). SPEC §8 names both "
            f"`{GRADE_SYNC}` and `{AGS_CALL}` in its table list and §13 puts the first in "
            "`backend/app/models/grades.py`; E3-02 is the ticket that builds them, with the "
            "migration and the grants beside them."
        )
    return table


def link(table: Any, target: str) -> str:
    """The one column on `table` whose foreign key points at `target`.

    Followed rather than guessed, for the reason `ProvisionedRows.link` gives: a
    column name guessed right is a column name that will one day be guessed wrong,
    silently, and a filter on a column that is not there matches nothing — which
    every test here would read as "no row was written".
    """
    found = foreign_key_columns(table, target)
    if len(found) != 1:
        pytest.fail(
            f"`{table.name}` has {len(found)} foreign keys into `{target}` ({found}); it "
            f"references {sorted({key.column.table.name for key in table.foreign_keys})}. E3-02 "
            f"gives `{table.name}` exactly one path to `{target}`, and these tests address rows "
            "through it."
        )
    return found[0]


def outcome_values(table: Any) -> dict[str, str]:
    """The two values `grade_sync.outcome` declares, mapped to what each means.

    Read off the column so this module does not decide the spelling. The two are
    told apart by fragment, and a set that is not exactly two — or in which either
    fragment matches none or both members — stops the test rather than picking,
    because either would leave every row below carrying an outcome nobody chose.
    """
    if "outcome" not in table.c:
        pytest.fail(
            f"`{table.name}` has no `outcome` column — it has "
            f"{[column.name for column in table.columns]}. SPEC §8 has each row record 'the "
            "outcome', and E3-02 makes it a two-valued enum: the post reached the platform, or "
            "it did not."
        )
    declared = list(getattr(stored_type(table.c.outcome), "enums", ()) or ())
    if len(declared) != 2:
        pytest.fail(
            f"`{table.name}.outcome` declares {declared}, which is not the closed set of two this "
            "module reads. E3-02 makes it an enum of two members — a post reached the platform, or "
            "it did not — and a column with an open set is one any string can be written into, "
            "which is what the refusal test below is about. An empty list here means the column "
            "carries no enumerated type at all. If the closed set is expressed some other way, say "
            "so in the pull request; `outcome_values` in this file is the one place that changes."
        )
    found: dict[str, str] = {}
    for meaning, fragment in (("posted", POSTED_FRAGMENT), ("failed", FAILED_FRAGMENT)):
        matching = [value for value in declared if fragment in value.lower()]
        if len(matching) != 1:
            pytest.fail(
                f"`{table.name}.outcome` declares {declared}, of which {matching} carry "
                f"{fragment!r}. This module tells the two outcomes apart by fragment so that the "
                "spelling stays the ticket's choice, and it cannot do that against these two names."
            )
        found[meaning] = matching[0]
    return found


def a_student_in_a_section(session: Any, tables: dict[str, Any]) -> dict[str, Any]:
    """One section and one user, for the posts below to be about.

    Seeded on the superuser session inside the test's own transaction, which is
    rolled back afterwards: what is under test is what the *table* can express, and
    nothing here drives a service that opens a connection of its own. The two rows
    are seeded through separate chains, so the student is not one the section's
    ancestors happened to create.
    """
    chain: dict[str, Any] = {}
    section = seed_row(session, tables, "section", chain)
    user = seed_row(session, tables, "user", {})
    return {"section": section, "user": user}


def plant_post(
    session: Any,
    tables: dict[str, Any],
    rows: dict[str, Any],
    post: dict[str, Any],
    outcome: str,
) -> Any:
    """One `grade_sync` row for `rows`' student and section, carrying `post`."""
    table = passback_table(tables, GRADE_SYNC)
    return seed_row(
        session,
        tables,
        GRADE_SYNC,
        {},
        **{
            link(table, "section"): rows["section"][single_primary_key(tables["section"])],
            link(table, "user"): rows["user"][single_primary_key(tables["user"])],
            "outcome": outcome,
            **post,
        },
    )


def posts_for(session: Any, tables: dict[str, Any], rows: dict[str, Any]) -> list[Any]:
    """Every `grade_sync` row for one student and section, newest first.

    Ordered by `created_at` descending, which is the lookup ADR 0124 makes every
    reader perform and the one E3-02's index exists to serve. The whole list rather
    than the first row, so a test can assert both what the latest row is *and* that
    the older one is still there — two questions a `LIMIT 1` cannot answer together.
    """
    table = passback_table(tables, GRADE_SYNC)
    section_column = link(table, "section")
    user_column = link(table, "user")
    if "created_at" not in table.c:
        pytest.fail(
            f"`{GRADE_SYNC}` has no `created_at` column — it has "
            f"{[column.name for column in table.columns]}. ADR 0124 makes every reader ask for the "
            "latest row for a student and section, and without the column the row was written at "
            "there is nothing for 'latest' to mean."
        )
    statement = (
        select(table)
        .where(
            table.c[section_column] == rows["section"][single_primary_key(tables["section"])],
            table.c[user_column] == rows["user"][single_primary_key(tables["user"])],
        )
        .order_by(table.c["created_at"].desc())
    )
    return list(session.execute(statement).mappings())


def refused_by_the_server(
    session: Any, statement: str, parameters: dict[str, Any], what: str
) -> None:
    """Require Postgres to refuse `statement` for want of a privilege, and nothing else.

    A second copy of `tests/integration/test_the_application_role_writes_only_the_
    granted_columns.py`'s helper, which is `docs/MISTAKES.md` entry 13's shape and
    is left as one deliberately: that module is E1-10's, its failure messages name
    that ticket, and re-pointing a merged module at a shared home is a change to
    tests this ticket does not otherwise touch. Said out loud so the next module
    that needs this makes the shared home rather than a third copy.

    Run inside a savepoint so a refusal does not leave the transaction aborted for
    whatever follows it. The SQLSTATE is required, not merely a raise: a `NOT NULL`
    violation, a `CHECK` and a foreign key are all `DatabaseError`s, and a test that
    accepted any of them would report a table this role can rewrite freely as one
    the database protects (`docs/MISTAKES.md` entry 3).
    """
    savepoint = session.begin_nested()
    try:
        session.execute(text(statement), parameters)
    except DatabaseError as refusal:
        savepoint.rollback()
        code = sqlstate_of(refusal)
        assert code == INSUFFICIENT_PRIVILEGE, (
            f"{what} raised SQLSTATE {code!r} rather than {INSUFFICIENT_PRIVILEGE!r} "
            f"(`insufficient_privilege`): {refusal}. The statement failed for a reason that is not "
            "the grant, so this says nothing about whether the table is append-only."
        )
        return
    savepoint.rollback()
    pytest.fail(
        f"{what} succeeded. SPEC §8 makes this an append-only record and E3-02 grants the "
        "application role `SELECT` and `INSERT` and nothing else — the verbs withheld are the "
        "assertion, exactly as they are on `classification` and on `nrps_call`. A connection that "
        "can rewrite a row here can rewrite what a student was told their participation was, on "
        "the connection every screen in the product runs on."
    )


def permitted_by_the_server(
    session: Any, statement: str, parameters: dict[str, Any], what: str
) -> None:
    """Require Postgres to allow `statement`, saying what a refusal would cost."""
    savepoint = session.begin_nested()
    try:
        session.execute(text(statement), parameters)
    except DatabaseError as refusal:
        savepoint.rollback()
        pytest.fail(
            f"{what} was refused: {refusal} (SQLSTATE {sqlstate_of(refusal)!r}). Refusing too much "
            "is this scheme's other failure mode and the one no denial test can see: E3-06 posts "
            "and records on the application connection, so a grant that withholds the append "
            "leaves the epic unable to write the account of what it sent."
        )
    savepoint.rollback()


# ---------------------------------------------------------------------------
# The two tables exist and record what a post is accounted for by — criterion 3's
# first clause, and ADR 0129's decision about what an outcome is made of.
# ---------------------------------------------------------------------------


def test_grade_sync_records_the_score_the_timestamp_the_ledger_and_the_outcome(
    metadata_tables: dict[str, Any],
) -> None:
    """SPEC §8's sentence, column by column, plus the student and the section.

    "Each row records the score as it was sent, the timestamp sent with it, the
    outcome, and the student and section it concerns" — with §3.4's per-week ledger
    beside them, because since the 2026-09-04 ruling every posted score carries one
    in its AGS comment and that comment is the only place the arithmetic behind a
    percentage is visible to anyone.

    **The mutation this kills:** the table built without `score_timestamp`, which
    is the column ADR 0052's retry identity turns on and the one an implementation
    that stamped its own clock would leave out; and the table built without
    `ledger_text`, which would leave E3-04 composing the comment and storing no
    record of what it composed.

    **What this deliberately does not assert** is that the set is exactly these:
    the exact column list is pinned in `REACHED_TABLES_THAT_CARRY_NOTHING`, beside
    the reason a column arriving has to be re-read against.
    """
    table = passback_table(metadata_tables, GRADE_SYNC)
    present = {column.name for column in table.columns}

    missing = sorted(set(GRADE_SYNC_REQUIRED) - present)
    assert not missing, (
        f"`{GRADE_SYNC}` carries {sorted(present)} and does not carry {missing}. SPEC §8 makes "
        "each row the account of one post: the score as sent, the timestamp sent with it, the "
        "per-week ledger that went in the comment, the outcome, the response code where the call "
        "reached the platform, and when the row was written."
    )
    for target in ("section", "user"):
        assert foreign_key_columns(table, target), (
            f"`{GRADE_SYNC}` has no foreign key into `{target}` — it references "
            f"{sorted({key.column.table.name for key in table.foreign_keys})}. §8: each row "
            "records 'the student and section it concerns', and a row that names neither is an "
            "account of a post about nobody."
        )


@pytest.mark.parametrize("name", (GRADE_SYNC, AGS_CALL))
def test_neither_passback_table_stores_a_platforms_response_body(
    metadata_tables: dict[str, Any], name: str
) -> None:
    """ADR 0129's decision, asserted as the forbidden state rather than the permitted one.

    A failed attempt records the platform's response **code** and never its body.
    A body is an unbounded third-party string, written once per post on a table
    that grows all term, and it is the one field on either of these rows that could
    carry text a platform chose — including, on a misconfigured platform, text
    quoting the request that produced it.

    **The mutation this kills:** a `response_body` column added because it would
    have made one afternoon's debugging easier. Nothing else in this suite would
    notice: the column would be nullable, every other test here would stay green,
    and the retention question it creates arrives years later.

    Asserted over name fragments, which is a judgement about names and is stated as
    one: a column called `detail` holding a body walks past this. What it catches
    is the column somebody would actually add.
    """
    table = passback_table(metadata_tables, name)
    bodies = sorted(
        column.name
        for column in table.columns
        if any(fragment in column.name.lower() for fragment in A_STORED_BODY)
    )
    assert not bodies, (
        f"`{name}` carries {bodies}, which read as a platform's response body. ADR 0129: the "
        "outcome is an enum beside a nullable response code, and a body was rejected — an "
        "unbounded third-party string stored per post, on a table nothing purges until E13."
    )


def test_ags_call_records_one_http_call_with_the_code_the_platform_answered(
    metadata_tables: dict[str, Any],
) -> None:
    """SPEC §6.1's second log, at the grain its own sentence gives it.

    "NRPS and AGS call logs with response codes — `nrps_call` and `ags_call`
    respectively, each at the grain of one HTTP call the tool made to a platform
    service." Only the NRPS half was ever built; this is the other, modelled on it:
    which section the call was about, the URL, the code that came back, and when.

    **`response_code` is nullable and that is a meaning, not a convenience** — the
    same meaning `nrps_call` gives it: NULL is a call that never reached the
    platform at all, which is what makes a transport failure distinguishable from a
    `500`. The nullability is asserted here because a `NOT NULL` on this column
    would force the writer to invent a code for a call that got no answer.

    **The mutation this kills:** no second log at all, with AGS calls appended to
    `nrps_call` — which SPEC §6.1 and §8 both now rule out by naming two tables, and
    which would leave E11's console unable to say which service a failing call was
    to.

    **What this does not assert:** that the column set is exactly these. The work
    order leaves open whether a count column analogous to `nrps_call.members_seen`
    is worth carrying, and an equality here would settle it in a test.
    """
    table = passback_table(metadata_tables, AGS_CALL)
    present = {column.name for column in table.columns}

    missing = sorted(set(AGS_CALL_REQUIRED) - present)
    assert not missing, (
        f"`{AGS_CALL}` carries {sorted(present)} and does not carry {missing}. §6.1 puts it at the "
        "grain of one HTTP call with the response code it answered, which is what an operator "
        "reads when a gradebook stops updating."
    )
    assert foreign_key_columns(table, "section"), (
        f"`{AGS_CALL}` has no foreign key into `section` — it references "
        f"{sorted({key.column.table.name for key in table.foreign_keys})}. A call log nobody can "
        "attribute to a section cannot answer §6.1's question, which is always about one course."
    )
    assert table.c["response_code"].nullable, (
        f"`{AGS_CALL}.response_code` is NOT NULL. `nrps_call` makes the same column nullable and "
        "means something by it: NULL is a call that never reached the platform, which is the state "
        "an operator most needs to see and the one a writer would have to invent a number for."
    )


# ---------------------------------------------------------------------------
# Criterion 6 — a second post is a second row, and the first is still there.
# ---------------------------------------------------------------------------


def plant_two_posts(db_session: Any, metadata_tables: dict[str, Any]) -> dict[str, Any]:
    """Two `grade_sync` rows for one student and section, **newer planted first**.

    The order is this helper's whole contribution. A reader that answers with the
    last row inserted, with the highest primary key, or with whatever an unordered
    scan returns first is right on a fixture built the obvious way and wrong here —
    and wrong in production, where a re-post is separated from the post it replaces
    by weeks. ADR 0124 names that failure explicitly as the one this grain
    introduces.

    **A plain function rather than a fixture**, deliberately: on the current tree
    every line of it stops on `grade_sync` not existing, and a `pytest.fail` raised
    during fixture setup is reported as an error where the same failure raised in
    the test body is reported as a failure naming the missing table. The two are
    read by different people.
    """
    outcomes = outcome_values(passback_table(metadata_tables, GRADE_SYNC))
    rows = a_student_in_a_section(db_session, metadata_tables)
    newer = plant_post(db_session, metadata_tables, rows, SECOND_POST, outcomes["failed"])
    older = plant_post(db_session, metadata_tables, rows, FIRST_POST, outcomes["posted"])
    return {"rows": rows, "older": older, "newer": newer, "outcomes": outcomes}


def test_a_second_post_for_one_student_leaves_the_first_row_carrying_what_it_was_sent_with(
    db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 6, and the whole reason ADR 0124 rejected a last-value row.

    Two posts for one `(section_id, user_id)` pair are two rows, and the earlier
    one still carries the value it was written with. That is the account of what
    Pulse told a platform about a student's standing, and under a row updated in
    place the earlier number is gone the moment a re-classification lowers a score
    — which is exactly the case E3 is built around and exactly the number somebody
    asks about.

    **The mutation this kills, and it is the design the breakdown first recorded:**
    one row per `(section_id, user_id)`, updated in place. It satisfies every other
    test in this module — the retry identity works perfectly well against it — and
    it fails here, because there is one row where there should be two and its score
    is the newer one.

    **The near miss it must survive:** an insert that writes a second row and
    rewrites the first, which a count-based check cannot see. The comparison is
    over the values, per row, so it fails on that too.
    """
    two_posts = plant_two_posts(db_session, metadata_tables)

    found = posts_for(db_session, metadata_tables, two_posts["rows"])

    assert len(found) == 2, (
        f"There are {len(found)} `{GRADE_SYNC}` rows for one student and section after two posts: "
        f"{found}. SPEC §8 puts this table at the grain of one row per post and ADR 0124 says why: "
        "a re-post that overwrote the row would destroy the number the platform was previously "
        "told, which is the one thing this record exists to be able to answer for."
    )
    older = next(row for row in found if row["created_at"] == FIRST_POST["created_at"])
    for column, sent in FIRST_POST.items():
        assert older[column] == sent, (
            f"The first post's `{column}` came back as {older[column]!r} and it was written as "
            f"{sent!r}. A later post rewrote a row it does not own; the value a student was shown "
            "in a gradebook is now whatever the most recent recomputation happened to produce."
        )
    assert older["outcome"] != two_posts["newer"]["outcome"], (
        f"Both rows carry outcome {older['outcome']!r}. The two posts were planted with different "
        "outcomes precisely so that a comparison cannot pass by reading the same row twice."
    )


def test_the_latest_row_for_a_student_and_section_is_the_newer_post_and_not_the_last_written(
    db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 6's second half: the newer row is the answer, and "newer" is by time.

    ADR 0124 makes "the latest row for a `(section_id, user_id)` pair" the thing
    that serves ADR 0052's retry identity and the thing E3-06 compares a
    recomputation against. This is that lookup, run against a fixture where the
    newer row was **written first** — so an implementation whose "latest" means the
    last row inserted, or the highest key, or an unordered `LIMIT 1`, answers with
    the older post here and would have answered correctly against any fixture that
    planted them in order.

    **The mutation this kills:** `created_at` left out of the ordering. **The near
    miss:** ordering on `score_timestamp` instead, which is the timestamp *sent to
    the platform* rather than when the row was written — the two agree here, which
    is deliberate, because they agree in production too and this test is not the
    place that decides which one a reader keys on. What it does decide is that the
    older row does not win.
    """
    two_posts = plant_two_posts(db_session, metadata_tables)

    found = posts_for(db_session, metadata_tables, two_posts["rows"])

    assert found, (
        f"There is no `{GRADE_SYNC}` row for this student and section at all, so the ordering "
        "below is about an empty result and the assertion would be satisfied by a table nothing "
        "can be written into."
    )
    latest = found[0]
    assert latest["created_at"] == SECOND_POST["created_at"], (
        f"The latest row was written at {latest['created_at']!r} and the newer of the two posts "
        f"was written at {SECOND_POST['created_at']!r}. The newer post was inserted *first* here, "
        "so a reader that answers with the last row written, the highest key, or an unordered "
        "first row picks the older post — and in production the two are weeks apart."
    )
    assert latest["score_text"] == SECOND_POST["score_text"], (
        f"The latest row's score is {latest['score_text']!r} and the newer post sent "
        f"{SECOND_POST['score_text']!r}. E3-06 compares a fresh recomputation against this value "
        "to decide whether to post at all, so answering with the older row re-posts a number the "
        "platform already holds and, after a re-classification, re-posts the wrong one."
    )


# ---------------------------------------------------------------------------
# Criterion 5 — the retry identity: what was last sent, exactly as sent, and when.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("score", BYTE_FRAGILE_SCORES)
def test_the_latest_row_gives_back_the_score_string_byte_for_byte(
    db_session: Any, metadata_tables: dict[str, Any], score: str
) -> None:
    """ADR 0052's retry, and why the score is a string rather than a number.

    A platform accepts a score whose timestamp equals the one it holds as a retry
    of the same delivery. E3-04 leans on that after a network timeout: it re-sends
    the identical body, because the timestamp names the recomputation rather than
    the attempt. SPEC §8: "a re-sent value has to be byte-identical to the one it
    retries, and a value the poster re-derives is not provably that."

    **The mutation this kills:** `score_text` declared `Numeric`, or `Float`, or
    anything that stores the quantity instead of the characters. `61.50` comes back
    as `61.5` or as `Decimal('61.50')`, both of which are the same *number* and
    neither of which is the same *body* — and a retry composed from either is a new
    delivery that the platform may accept twice or refuse.

    **The four spellings are the near misses**, and each is a value E3-04 could
    legitimately send: a trailing zero, an integer with no point at all, a zero
    that is not absent, and a repeating fraction that a re-derivation would round.

    Both halves are asserted — that it is a string, and that it is *this* string —
    because a `Decimal` compares unequal to the text and would fail with a message
    about a value rather than about a type.
    """
    rows = a_student_in_a_section(db_session, metadata_tables)
    outcomes = outcome_values(passback_table(metadata_tables, GRADE_SYNC))
    plant_post(
        db_session,
        metadata_tables,
        rows,
        {**FIRST_POST, "score_text": score},
        outcomes["posted"],
    )

    latest = posts_for(db_session, metadata_tables, rows)[0]

    assert isinstance(latest["score_text"], str), (
        f"`{GRADE_SYNC}.score_text` came back as {latest['score_text']!r}, a "
        f"{type(latest['score_text']).__name__}. ADR 0124 stores 'the exact string, not a number "
        "to be re-rendered', because the retry identity is byte equality of a body the platform "
        "already accepted."
    )
    assert latest["score_text"] == score, (
        f"The score came back as {latest['score_text']!r} and was sent as {score!r}. A retry "
        "composed from what came back is a different body from the one it retries, so the platform "
        "sees a new delivery rather than the repeat ADR 0052 has it accept."
    )


def test_the_latest_row_gives_back_the_timestamp_that_was_sent_with_the_score(
    db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """Criterion 5's "and when": the instant that went to the platform, not the row's own.

    ADR 0052 compares instants, and the timestamp a retry carries has to be the one
    the delivery it retries carried — "the timestamp names the recomputation rather
    than the attempt". So the row keeps two different moments and they are not
    interchangeable: `score_timestamp` is what was sent, `created_at` is when the
    row was written, and a schema with only one of them cannot express a retry at
    all.

    **The mutation this kills:** `score_timestamp` dropped and `created_at` read in
    its place. The two posts here are planted five and two seconds apart
    respectively, so a row answering with its own write time is wrong by a
    measurable amount rather than coincidentally right.

    **And the timezone survives**, which ADR 0019 requires of everything stored in
    these columns: a value that came back naive would be compared against an aware
    one by a reader and would raise, or worse, be normalised into a different
    instant.
    """
    two_posts = plant_two_posts(db_session, metadata_tables)

    latest = posts_for(db_session, metadata_tables, two_posts["rows"])[0]

    assert latest["score_timestamp"] == SECOND_POST["score_timestamp"], (
        f"The latest row's `score_timestamp` is {latest['score_timestamp']!r} and the post carried "
        f"{SECOND_POST['score_timestamp']!r}. ADR 0052 has a platform accept a score whose "
        "timestamp equals the one it holds as a retry of the same delivery, so a stored timestamp "
        "that is not the one that was sent makes every retry a new delivery."
    )
    assert latest["score_timestamp"] != latest["created_at"], (
        f"`score_timestamp` and `created_at` are both {latest['score_timestamp']!r}. They were "
        "planted two seconds apart, so one of them is being read out of the other — and a row that "
        "cannot tell the instant it sent from the instant it was written cannot express a retry."
    )
    assert latest["score_timestamp"].tzinfo is not None, (
        f"`score_timestamp` came back naive: {latest['score_timestamp']!r}. ADR 0019 puts an "
        "aware-datetime guard on the column type for exactly this, and a naive instant compared "
        "against an aware one is an error at the reader rather than here."
    )


def test_a_post_that_never_reached_the_platform_is_a_row_with_no_response_code(
    db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """SPEC §8: "a failed attempt is a row too", and NULL is what a transport failure looks like.

    ADR 0124: "An attempt that never reached the platform is part of the account of
    what Pulse tried to do to a gradebook", and it is what lets E3-06 leave a
    section in a state an operator can act on rather than silently retrying. The
    NULL response code is `nrps_call`'s own semantics for the same column, and
    carrying the same meaning in both logs is what stops E11's console needing two
    readings of one idea.

    **The mutation this kills:** `response_code` declared `NOT NULL`, which forces
    the writer to invent a number — a `0`, or a `599` — for a call that got no
    answer, after which "the platform refused it" and "we never reached the
    platform" are the same row.

    **Its pair** is the older post in the same fixture, which succeeded and carries
    a real code: without it, this would be equally true of a table that stores no
    response code at all.
    """
    two_posts = plant_two_posts(db_session, metadata_tables)

    found = posts_for(db_session, metadata_tables, two_posts["rows"])
    latest, earlier = found[0], found[-1]

    assert latest["response_code"] is None, (
        f"The failed post's `response_code` is {latest['response_code']!r} and it was written as "
        "NULL. NULL means the call never reached the platform, which is the state an operator most "
        "needs to see; a number here is one somebody had to invent."
    )
    assert latest["outcome"] == two_posts["outcomes"]["failed"], (
        f"The failed post's outcome came back as {latest['outcome']!r} rather than "
        f"{two_posts['outcomes']['failed']!r}. A failed attempt that reads as posted is a gradebook "
        "Pulse believes it has written to."
    )
    assert earlier["response_code"] == FIRST_POST["response_code"], (
        f"The succeeded post's `response_code` is {earlier['response_code']!r} and it was written "
        f"as {FIRST_POST['response_code']!r}. Without a row that carries a code, the assertion "
        "above is equally true of a table that stores none."
    )


def test_an_outcome_the_ticket_does_not_name_is_refused(
    db_session: Any, metadata_tables: dict[str, Any]
) -> None:
    """The outcome is a closed set of two, and a write outside it does not land.

    A post either reached the platform or it did not, and E11's job dashboard and
    E3-06's retry decision both branch on exactly that. An open column is one a
    later writer can put a third state into — `pending`, `skipped`, `unknown` — and
    every reader then has a case it was never written against, with no red anywhere.

    **The mutation this kills:** `outcome` declared as plain text with no
    constraint. Every other test in this module stays green: they write values from
    the column's own vocabulary, and a text column accepts those too.

    **A refusal from either side counts, and the difference is stated rather than
    hidden** (`docs/MISTAKES.md` entry 14). A native enum type or a `CHECK` refuses
    this in the server; a SQLAlchemy `Enum` over a Python class refuses it in the
    type, before a statement is sent. Both close the set for every writer that goes
    through the models, which is every writer this project has; only the first also
    closes it for raw SQL. Which of the two E3-02 uses is its choice — the ticket
    settles that the set is two, not how it is spelled — so what is required here is
    that the value does not land, and `StatementError` is the base both refusals
    arrive as.

    **The near miss it must survive** is the row planted immediately afterwards:
    the two named values are accepted, which is what stops this being satisfied by
    a column that refuses everything.
    """
    rows = a_student_in_a_section(db_session, metadata_tables)
    table = passback_table(metadata_tables, GRADE_SYNC)
    outcomes = outcome_values(table)

    savepoint = db_session.begin_nested()
    try:
        plant_post(db_session, metadata_tables, rows, FIRST_POST, AN_UNNAMED_OUTCOME)
    except StatementError:
        savepoint.rollback()
    else:
        savepoint.rollback()
        pytest.fail(
            f"`{GRADE_SYNC}` accepted an `outcome` of {AN_UNNAMED_OUTCOME!r}. The column declares "
            f"{sorted(outcomes.values())} and the ticket makes it two-valued: a post reached the "
            "platform or it did not. A third state would reach E11's dashboard and E3-06's retry "
            "branch as a case neither was written against."
        )

    plant_post(db_session, metadata_tables, rows, FIRST_POST, outcomes["posted"])
    assert posts_for(db_session, metadata_tables, rows), (
        f"`{GRADE_SYNC}` refused a row carrying {outcomes['posted']!r}, one of the two values its "
        "own column declares. A column that refuses everything passes the refusal above and stops "
        "the epic writing anything at all."
    )


# ---------------------------------------------------------------------------
# The index the latest-row lookup runs on, and the append-only grant.
# ---------------------------------------------------------------------------


def test_grade_sync_is_indexed_for_the_latest_row_lookup(
    migrated_engine: Any, metadata_tables: dict[str, Any]
) -> None:
    """The scope item: "the index that makes 'the latest row for this student in this section' cheap".

    That lookup is on the recompute's hot path once a term's worth of rows exists —
    E3-06 runs it per student per section on every sweep — and ADR 0124 hands E3-02
    the index by name: "E3-02 owes an index that makes the lookup cheap and a test
    that plants a second row and requires the newer one to win."

    **The mutation this kills:** an index on `section_id` alone, which is what
    `nrps_call` carried until the E1 boundary review measured it at 2,006 buffers
    per probe against 5 for the composite — and this table grows faster, because it
    takes a row per post rather than per sync.

    **Ascending, and the reason is not performance.** Postgres serves `ORDER BY
    created_at DESC LIMIT 1` from an ascending index by a backward scan at the same
    cost. What a `DESC` costs is visibility: a text-expression index is not
    comparable, so `alembic check` cannot see the declaration at all and the drift
    gate is blind to the index for as long as it is written that way. E2-02
    reversed `nrps_call`'s for exactly this, and the lesson is in that model's own
    docstring.

    **Asserted by columns rather than by name**, because the ticket settles no
    index name and pinning one here would make this file the place that choice was
    made. The leading pair may be in either order — both spellings answer an
    equality lookup on both columns — and `created_at` has to follow them, because
    that is the column the ordering runs on.

    Read from the catalog, because an index a migration never created exists
    nowhere a deployment can reach. The reader's own control is
    `test_the_index_reader_reports_column_order_and_the_descending_flag` in
    `tests/integration/test_the_nrps_call_log_is_indexed_for_the_debounce_probe.py`;
    a red there means this assertion is measuring nothing.
    """
    table = passback_table(metadata_tables, GRADE_SYNC)
    leading = (link(table, "section"), link(table, "user"))

    with migrated_engine.connect() as connection:
        read = index_key_columns(connection, GRADE_SYNC)

    assert read, (
        f"The catalog reports no index at all on `{GRADE_SYNC}`, not even a primary key's. Either "
        "no migration created the table — which the tests above diagnose — or this reader is "
        "looking somewhere the migrated schema is not, and the assertion below would be about "
        "nothing."
    )
    candidates = indexes_leading_with(read, leading)
    serving = {
        name: keys
        for name, keys in candidates.items()
        if len(keys) >= 3 and keys[2] == ("created_at", False)
    }
    assert serving, (
        f"No index on `{GRADE_SYNC}` leads with {list(leading)} and then `created_at` ascending. "
        f"The indexes it carries are {read!r}, each as `(column, descending)` in key order.\n\n"
        "The lookup every reader of this table performs is the newest row for one student in one "
        "section (ADR 0124), on the recompute's hot path, against a table that takes a row per "
        f"post all term. An index on {leading[0]!r} alone does not answer it, and neither does one "
        "that leads with `created_at`. A descending `created_at` would perform identically and is "
        "refused for a different reason: a text-expression index is invisible to `alembic check`, "
        "so the drift gate could not see this declaration at all."
    )
    descending = {
        name: keys for name, keys in read.items() if any(is_descending for _, is_descending in keys)
    }
    assert not descending, (
        f"`{GRADE_SYNC}` carries descending indexes {descending!r}. The composite this criterion "
        "asks for is ascending; a descending one beside it is maintained on every insert and is "
        "the half `alembic check` cannot compare."
    )


def commit_a_post_and_a_call(
    committed_rows: Any, metadata_tables: dict[str, Any]
) -> dict[str, Any]:
    """One committed `grade_sync` row and one committed `ags_call` row, to aim statements at.

    Committed, because `application_session` is a second connection and sees
    nothing else. Seeded through the superuser connection deliberately: what is
    under test is what `pulse_app` may do to a row that exists, not whether it could
    create one to test against.

    A plain function rather than a fixture, for the reason `plant_two_posts` above
    gives: on the current tree every line of it stops on a table that is not there,
    and that failure belongs in the test body where it reads as a missing
    deliverable rather than as a broken fixture.
    """
    grade_table = passback_table(metadata_tables, GRADE_SYNC)
    call_table = passback_table(metadata_tables, AGS_CALL)
    outcome = outcome_values(grade_table)["posted"]
    chain: dict[str, Any] = {}
    section = committed_rows.seed("section", chain)
    user = committed_rows.seed("user", {})
    section_key = section[single_primary_key(metadata_tables["section"])]
    post = committed_rows.seed(
        GRADE_SYNC,
        {},
        **{
            link(grade_table, "section"): section_key,
            link(grade_table, "user"): user[single_primary_key(metadata_tables["user"])],
            "outcome": outcome,
            **FIRST_POST,
        },
    )
    call = committed_rows.seed(AGS_CALL, {}, **{link(call_table, "section"): section_key})
    committed_rows.commit()
    return {GRADE_SYNC: post, AGS_CALL: call, "tables": metadata_tables}


def copy_of(seeded: dict[str, Any], name: str) -> tuple[str, dict[str, Any]]:
    """A textual `INSERT` copying one seeded row, key omitted so the server makes a new one.

    Copying is what keeps the statement about the grant: every value is one the
    schema already accepted, so a refusal cannot be a constraint this test happened
    to trip.
    """
    table = seeded["tables"][name]
    row = seeded[name]
    key = single_primary_key(table)
    values = {
        column.name: row[column.name]
        for column in table.columns
        if column.name != key and column.computed is None
    }
    columns = ", ".join(f'"{column}"' for column in values)
    binds = ", ".join(f":{column}" for column in values)
    # S608 is for SQL assembled out of a variable; every name here comes from
    # `Base.metadata` and every value travels as a bind parameter.
    statement = f'INSERT INTO public."{name}" ({columns}) VALUES ({binds})'  # noqa: S608
    return statement, values


@pytest.mark.parametrize("name", (GRADE_SYNC, AGS_CALL))
@pytest.mark.parametrize("verb", ("UPDATE", "DELETE"))
def test_the_application_role_cannot_rewrite_or_remove_a_passback_row(
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    application_session: Any,
    name: str,
    verb: str,
) -> None:
    """Append-only by grant: the verbs withheld are the assertion.

    Both tables get `SELECT` and `INSERT` and nothing else, which is how
    `classification` and `nrps_call` are already held. That is what makes
    append-only a property of the database rather than a rule the next writer has
    to remember — and both writers here run on the connection every screen in the
    product runs on, so anything the grant permits is reachable by a bug in an
    unrelated service module.

    **`grade_sync` is the one that matters.** A connection able to rewrite a row
    here can rewrite the account of what a student was told their participation
    was, which is the record ADR 0124 exists to keep. `ags_call` is an operational
    log and the argument is `nrps_call`'s, unchanged.

    **The mutation this kills:** `GRANT UPDATE` or `GRANT ALL` on either table —
    written because a writer wanted to "fix up" a row after the fact. The
    catalog-side half of the same fact is
    `tests/integration/test_identity_grants.py`, which compares the whole grant set
    as an equality; this half says what the server actually does, and a grant
    recorded in that file which no migration issues is invisible there and fails
    here.

    **Its pair** is the insert below, without which this is equally true of a role
    that holds nothing at all.
    """
    committed = commit_a_post_and_a_call(committed_rows, metadata_tables)
    table = committed["tables"][name]
    key = single_primary_key(table)
    parameters = {"identifier": committed[name][key]}
    if verb == "DELETE":
        statement = f'DELETE FROM public."{name}" WHERE "{key}" = :identifier'  # noqa: S608  # noqa: S608
    else:
        column = "score_text" if name == GRADE_SYNC else "url"
        statement = (
            f'UPDATE public."{name}" SET "{column}" = \'rewritten\' WHERE "{key}" = :identifier'  # noqa: S608
        )

    refused_by_the_server(
        application_session,
        statement,
        parameters,
        f"`{verb}` on `{name}` as the application role",
    )


@pytest.mark.parametrize("name", (GRADE_SYNC, AGS_CALL))
def test_the_application_role_may_append_a_passback_row_and_read_it_back(
    committed_rows: Any, metadata_tables: dict[str, Any], application_session: Any, name: str
) -> None:
    """The permitted half, and it is not ceremony.

    A grant scheme that refused everything satisfies both refusals above and leaves
    E3-06 unable to record anything it posted. `INSERT` is what the poster spends;
    `SELECT` is what the recompute spends when it asks for the latest row to
    compare against, which is a read this table exists to serve — ADR 0124 makes
    the sweep's comparison a lookup rather than a stored answer.

    **The mutation this kills:** the grant written as `INSERT` alone, which passes
    every refusal and every schema test here and leaves the sweep unable to tell a
    changed value from an unchanged one, so every run re-posts every student.
    """
    committed = commit_a_post_and_a_call(committed_rows, metadata_tables)
    statement, values = copy_of(committed, name)

    permitted_by_the_server(
        application_session,
        statement,
        values,
        f"Appending a row to `{name}` as the application role",
    )
    permitted_by_the_server(
        application_session,
        f'SELECT * FROM public."{name}"',  # noqa: S608
        {},
        f"Reading `{name}` as the application role",
    )


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the code.**
# ---------------------------------------------------------------------------


def test_the_two_planted_posts_differ_in_every_value_that_is_compared() -> None:
    """A control: the pair this module plants can tell one row from the other.

    Every assertion about "the latest row" and about the first row surviving is a
    comparison between two rows. If the two posts shared a value in any position,
    an implementation that answered with the wrong row would agree in that position
    and the test would be measuring the fields that happened to differ
    (`docs/MISTAKES.md` entry 3, and the same argument
    `test_the_survey_schema_survives_a_downgrade.py` makes for seeding values that
    differ in every position).

    Arithmetic on this module's own constants. Green today and after the ticket
    lands.
    """
    assert set(FIRST_POST) == set(SECOND_POST), (
        f"The two planted posts carry {sorted(FIRST_POST)} and {sorted(SECOND_POST)}. They have to "
        "describe the same columns, or a comparison over one of them says nothing about the other."
    )
    shared = sorted(column for column in FIRST_POST if FIRST_POST[column] == SECOND_POST[column])
    assert not shared, (
        f"The two planted posts agree on {shared}. A reader that answered with the older row would "
        "still be right about those fields, so the tests resting on this pair would be green "
        "against the failure they exist to catch."
    )


def test_the_newer_planted_post_is_written_later_and_inserted_first() -> None:
    """A control: the fixture's ordering trap is actually a trap.

    The whole force of the latest-row tests is that the newer post is planted
    first, so that "the last row inserted" and "the newest row" are different
    answers. Two things have to hold for that: the second post's `created_at` has to
    be later than the first's, and the fixture has to insert it before the other. A
    pair that drifted so the newer one was also inserted second would leave every
    latest-row assertion green against the reader ADR 0124 warns about.

    The insertion order is `plant_two_posts`' own line and cannot be asserted here;
    what this pins is the half a constant edit could break silently.

    Arithmetic on this module's own constants. Green today.
    """
    assert SECOND_POST["created_at"] > FIRST_POST["created_at"], (
        f"`SECOND_POST` was written at {SECOND_POST['created_at']!r} and `FIRST_POST` at "
        f"{FIRST_POST['created_at']!r}, so the post this module calls newer is not newer and every "
        "latest-row assertion is asking for the wrong row."
    )
    assert SECOND_POST["score_timestamp"] > FIRST_POST["score_timestamp"], (
        "The newer post's `score_timestamp` is not later than the older one's. §3.4 re-posts after "
        "each week closes, so a later delivery carries a later recomputation instant — and ADR "
        "0052's ordering rule has a platform refuse a score whose timestamp is strictly earlier "
        "than the one it holds."
    )
    for post in (FIRST_POST, SECOND_POST):
        assert post["score_timestamp"] != post["created_at"], (
            f"A planted post carries {post['score_timestamp']!r} in both `score_timestamp` and "
            "`created_at`, so the test that requires the two to differ would be asserting about a "
            "fixture that cannot tell them apart either."
        )
