"""The privileges this ticket spends, and the ones it withholds — ticket E4-06.

E4-02 created the four report tables and granted nothing on any of them,
deliberately: "the writers grant what they spend — E4-06 for the summary, E4-04
for the release, E6 for every moderation state", and
`tests/integration/test_report_schema.py`'s no-grant walk says in as many words
when it expects to go red for a good reason — "the entry moves into
`RUNTIME_BASE_TABLE_PRIVILEGES` in `test_identity_grants.py` with the sentence it
comes from, and the table's name comes out of the list here". This is that
change, asserted from this side.

**Three verbs over two tables, and the sentence each comes from.**

  - `INSERT` on `weekly_summary` is the row the Monday walk writes: SPEC §5.1 puts
    one AI summary at the head of each of a week's two comment groups, and this job
    is the only writer §5.1 admits (ADR 0145's third decision rests on that being
    true).
  - `SELECT` on `weekly_summary` is the walk's own selection. Its scope is
    "sections with closed weeks **lacking** summary rows", and there is no way to
    ask that question without reading the table — which is also what makes the
    second run of a pair a no-op (criterion 1) rather than a duplicate insert
    refused by a constraint.
  - `SELECT` on `moderation_state` is SPEC §5.1's own sentence: the summaries
    "exclude flagged-held content". ADR 0145 settles that a comment's moderation
    state lives in `public.moderation_state` as an append-only record whose latest
    row governs and whose initial state is the absence of a row, so that is the one
    place the question can be asked, and the filter asks it inside this walk on
    this connection.

**What is withheld is the assertion**, exactly as it is on `classification`, on
`grade_sync` and on `ags_call`. On `weekly_summary`, no `UPDATE`: breakdown
decision 2 rules out regeneration in v1, so a connection able to rewrite a stored
summary is a connection able to change what an instructor already read, with no
Python rule making that structural. No `DELETE`, no `TRUNCATE`: a summary is the
epic's only generated artifact and §4's retention purge is E13's, run under a
different identity. On `moderation_state`, **every** write verb: E4 writes zero
moderation rows by design (ADR 0145) and every writer is E6's, and a connection
able to write one could publish a comment an instructor excluded — which is the
anti-cherry-picking mechanism §5.2 exists for. No `REFERENCES`, no `TRIGGER`, on
either.

**This module first asserted that `pulse_app` held nothing at all on
`moderation_state`, and that assertion was wrong.** It was written from this
ticket's work-order sentence — "`weekly_summary` and nothing wider" — which SPEC
§5.1 overrides: a ticket that must execute the flagged-held filter *spends* a read
there, and the rule the record states is "each ticket grants what it spends", not
"what it writes". Dispute E4-06-01 measured both directions — with the grant, this
module's inventory failed and the two moderation tests passed; without it, the walk
raised `InsufficientPrivilege` — and the ruling moved three assertions together:
this one, `RUNTIME_BASE_TABLE_PRIVILEGES` in
`tests/integration/test_identity_grants.py`, and `test_report_schema.py`'s
narrowed walk. E4-04 grants the same `SELECT` for its own read path from a
parallel branch, so one `SELECT` on that table is the merged end state rather
than a widening either ticket introduces alone — and at the merge the duplicate
came out of *this* revision rather than E4-04's, because two revisions issuing one
grant is invisible while two `downgrade()`s revoking it are not. What this module
asserts is unchanged: the role holds that read, and holds no verb beside it. Which
revision executed the `GRANT` is deliberately not asked here.

**Both currencies are asked, because a privilege reaches a role three ways.**
`has_table_privilege` answers for a table grant and for one arriving through a
role membership and is blind to a column-scoped grant; `has_column_privilege` is
what sees that one. A guard that enumerated mechanisms and missed the one the
design uses is `docs/MISTAKES.md` entry 35, and it is why both are here.

**And the grant is driven, not only read out of the catalog.** A suite that
proved the privilege from `pg_catalog` and then wrote every row through the
migrating engine has not tested the grant at all (`docs/MISTAKES.md` entry 46).
So one test here inserts a summary over `application_engine` — the connection
`app.db` builds and the job therefore runs on — and requires the two refusals
beside it. Every test in this ticket's other modules reaches the same connection
through the task itself.

**Which failure a red here is.** Before E4-06's migration lands, expected red on
an assertion: `pulse_app` holds nothing on `weekly_summary`, so that equality
reports its missing grants by name and the driven insert is refused with
`permission denied`. The `moderation_state` and release-table equalities are
E4-04's revision's to satisfy and are green from one revision lower. Before E4-02's, expected red on `pytest.fail` naming the
absent table (`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest
from fixtures.summary_job import (
    A_CLOSED_TERM_WEEK,
    MODERATION_STATE_TABLE,
    SUMMARY_GENERATED_AT_COLUMN,
    SUMMARY_MODEL_ID_COLUMN,
    SUMMARY_PROMPT_VERSION_COLUMN,
    SUMMARY_RESPONSE_COUNT_COLUMN,
    SUMMARY_SECTION_COLUMN,
    SUMMARY_STREAM_COLUMN,
    SUMMARY_TEXT_COLUMN,
    SUMMARY_WEEK_COLUMN,
    WEEKLY_SUMMARY_TABLE,
    SummaryWorld,
)
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# The two connection roles ADR 0001 separates, and every privilege a role can
# hold on a table or on a column of one.
APPLICATION_ROLE = "pulse_app"
CARE_ROLE = "pulse_care"
RUNTIME_ROLES = (APPLICATION_ROLE, CARE_ROLE)
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")

# What this ticket spends on the table it writes, and the whole of it.
GRANTED_ON_THE_SUMMARY = ("SELECT", "INSERT")

# What it spends on the table it only reads. One verb: SPEC §5.1's summaries
# "exclude flagged-held content", and ADR 0145 puts that fact nowhere else. The
# table's name comes from `tests/fixtures/summary_job.py`, where the moderation
# suite already transcribes it, rather than being written a second time here.
GRANTED_ON_THE_MODERATION_RECORD = ("SELECT",)

# The two tables E4-02 created that this ticket neither reads nor writes. **Their
# entry was nothing until E4-04 merged, and it is that ticket's two verbs now.**
# The rule is unchanged — a privilege lands in the change that spends it — and the
# release path is what spends these: `d4c1a7e93f26` grants `pulse_app`
# `SELECT, INSERT` on both, argued in `report_comment_grants_v001.sql` and pinned
# as an equality in `RUNTIME_BASE_TABLE_PRIVILEGES`. What this module still has to
# say about them is that **E4-06 adds nothing here**, so the assertion below is an
# equality against E4-04's grant rather than against an empty set.
GRANTED_BY_E4_04 = ("release_batch", "release_batch_member")
GRANTED_ON_THE_RELEASE_TABLES = ("SELECT", "INSERT")

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
# find there. E0-13 granted `pulse_app` `SELECT` on `classification` and
# `tests/integration/test_identity_grants.py` records it; a probe that cannot see
# that one reports absence because it is blind, which is entry 35's whole rule.
A_TABLE_THE_ROLE_CERTAINLY_READS = "classification"
A_COLUMN_THE_ROLE_CERTAINLY_READS = "verdict"

# This test's own row. Nothing about it is a claim about anything the system
# decides; it exists so a write can be attempted through the production
# connection and refused or accepted.
A_STREAM = "INSTRUCTOR"
A_SUMMARY = "Written by the grant test over the application connection."
ANOTHER_SUMMARY = "Rewritten by the grant test, which must not be possible."
A_RESPONSE_COUNT = 4
A_PROMPT_VERSION = "e4-06-grant-test-prompt"
A_MODEL_ID = "e4-06-grant-test-model"


def columns_of(session: Any, table: str) -> tuple[str, ...]:
    """Every column the database reports on one table, sorted."""
    return tuple(session.execute(COLUMNS_OF, {"table": table}).scalars())


def probes_can_see_a_grant_they_are_pointed_at(session: Any) -> None:
    """Both readings must find the privilege `pulse_app` certainly holds.

    Called as the first statement of each test that reports an absence. A probe
    that cannot see a grant it is aimed straight at reports absence everywhere,
    and the assertions below would then be facts about a blind reading rather than
    about this table (`docs/MISTAKES.md` entry 35).
    """
    at_table = session.execute(
        text(HAS_TABLE_PRIVILEGE),
        {
            "role": APPLICATION_ROLE,
            "relation": f"public.{A_TABLE_THE_ROLE_CERTAINLY_READS}",
            "privilege": "SELECT",
        },
    ).scalar_one()
    assert at_table, (
        f"`{APPLICATION_ROLE}` does not hold `SELECT` on `{A_TABLE_THE_ROLE_CERTAINLY_READS}` "
        "according to `has_table_privilege`, and E0-13 granted exactly that. So this reading "
        "reports absence whatever is granted."
    )
    at_column = session.execute(
        text(HAS_COLUMN_PRIVILEGE),
        {
            "role": APPLICATION_ROLE,
            "relation": f"public.{A_TABLE_THE_ROLE_CERTAINLY_READS}",
            "column": A_COLUMN_THE_ROLE_CERTAINLY_READS,
            "privilege": "SELECT",
        },
    ).scalar_one()
    assert at_column, (
        f"`{APPLICATION_ROLE}` does not hold `SELECT` on "
        f"`{A_TABLE_THE_ROLE_CERTAINLY_READS}.{A_COLUMN_THE_ROLE_CERTAINLY_READS}` according to "
        "`has_column_privilege`, and a table-wide grant covers every column. The column-grain "
        "half of these tests is therefore blind — and that is the half that sees a grant "
        "`has_table_privilege` cannot report at all."
    )


def held_on_table(session: Any, table: str) -> set[tuple[str, str]]:
    """Every `(role, privilege)` either runtime role holds on one table.

    One reader for the two tables this ticket grants on, rather than a copy per
    test (`docs/MISTAKES.md` entry 13). It answers the whole set rather than the
    verbs a caller had in mind, so the assertion built on it is an equality and a
    verb nobody thought of shows up rather than going unasked.
    """
    return {
        (role, privilege)
        for role in RUNTIME_ROLES
        for privilege in TABLE_PRIVILEGES
        if session.execute(
            text(HAS_TABLE_PRIVILEGE),
            {"role": role, "relation": f"public.{table}", "privilege": privilege},
        ).scalar_one()
    }


def held_on_columns(session: Any, table: str) -> set[tuple[str, str, str]]:
    """Every `(role, column, privilege)` either runtime role holds on one table's columns.

    The currency `has_table_privilege` is blind to. A table-wide grant shows here
    on every column, so the expected set is a product — and anything outside it is
    a column-scoped grant nothing else in this repository reports.
    """
    return {
        (role, column, privilege)
        for role in RUNTIME_ROLES
        for column in columns_of(session, table)
        for privilege in COLUMN_PRIVILEGES
        if session.execute(
            text(HAS_COLUMN_PRIVILEGE),
            {"role": role, "relation": f"public.{table}", "column": column, "privilege": privilege},
        ).scalar_one()
    }


def test_the_application_role_may_read_and_insert_a_summary_and_nothing_else(
    db_session: Any, metadata_tables: dict[str, Any], summary_job_contract: Any
) -> None:
    """The grant this ticket adds, asserted as an equality in both currencies.

    An equality rather than a floor, for the reason `RUNTIME_BASE_TABLE_PRIVILEGES`
    in `tests/integration/test_identity_grants.py` gives: on a table whose whole
    safety is which verbs are withheld, "at least these" is not a guarantee. Two
    verbs in and five out, plus the Care role at nothing — it has no business on
    an instructor's report at all (§6.2 isolates it to the safety path).

    **`UPDATE` is the one worth naming.** Breakdown decision 2 rules out
    regeneration in v1: "a summary that silently changes under a reader is worse
    than one that is a week honest." A connection holding `UPDATE` here can change
    what an instructor read this morning, and criterion 1's idempotence is then a
    property of the walk's code rather than of what the database will permit. The
    same argument E3-02 makes for `grade_sync` and E0-13 for `classification`.

    **The mutation this kills:** `GRANT ALL ON public.weekly_summary TO pulse_app`
    in this ticket's migration, which is the shortest line that makes the job work
    and passes every other test in this ticket; and a column-scoped `UPDATE` added
    to `summary_text` "so a correction is possible", which `has_table_privilege`
    cannot report at all.
    """
    summary_job_contract.require_table(metadata_tables)
    probes_can_see_a_grant_they_are_pointed_at(db_session)

    at_table = held_on_table(db_session, WEEKLY_SUMMARY_TABLE)
    assert at_table == {(APPLICATION_ROLE, privilege) for privilege in GRANTED_ON_THE_SUMMARY}, (
        f"`{WEEKLY_SUMMARY_TABLE}` is held as {sorted(at_table)} and this ticket spends "
        f"exactly {[(APPLICATION_ROLE, p) for p in GRANTED_ON_THE_SUMMARY]}. `INSERT` is the row "
        "the Monday walk writes and `SELECT` is how it finds the section-weeks that have none. "
        "`UPDATE` is refused because there is no regeneration in v1 (breakdown decision 2) — a "
        "connection that can rewrite a stored summary can change what an instructor already read. "
        f"`{CARE_ROLE}` holds nothing here at all: §6.2 isolates it to the safety path, and an "
        "instructor's report is not on it."
    )

    columns = columns_of(db_session, WEEKLY_SUMMARY_TABLE)
    assert columns, (
        f"the catalog reports no columns for `public.{WEEKLY_SUMMARY_TABLE}`, so the column-grain "
        "equality below is over an empty set and holds of anything."
    )
    at_columns = held_on_columns(db_session, WEEKLY_SUMMARY_TABLE)
    assert at_columns == {
        (APPLICATION_ROLE, column, privilege)
        for column in columns
        for privilege in GRANTED_ON_THE_SUMMARY
    }, (
        f"at column grain `{WEEKLY_SUMMARY_TABLE}` is held as {sorted(at_columns)}. A "
        "table-wide grant of the two verbs covers every column and nothing more; an entry here "
        "that is not in that set is a column-scoped grant, which `has_table_privilege` does not "
        "report at all and which nothing else in this repository would find."
    )


def test_the_application_role_may_read_a_moderation_state_and_never_write_one(
    db_session: Any, metadata_tables: dict[str, Any], summary_job_contract: Any
) -> None:
    """The read SPEC §5.1's flagged-held filter spends, and the writes it must not.

    "AI summaries per stream: … **exclude flagged-held content**." ADR 0145 makes
    `moderation_state` an append-only record whose latest row governs and whose
    initial state is the absence of a row, so a walk asking "may this comment be
    sent to a provider" reads that table and there is nowhere else to ask. The walk
    runs on `pulse_app`, so `pulse_app` reads it. Dispute E4-06-01 is the record of
    that being settled, and the measurement behind it: without the grant, the
    filter raises `InsufficientPrivilege` out of the walk and both tests in
    `test_the_summary_job_feeds_no_moderation_held_comment_to_the_model.py` fail.

    **One verb, and the withheld ones are the assertion.** E4 writes zero
    moderation rows by design and every writer is E6's, so `INSERT`, `UPDATE` and
    `DELETE` are all refused. That is not tidiness: §5.2's exclusion log is the
    anti-cherry-picking mechanism, and a connection able to append a `KEPT` row
    could publish a comment an instructor excluded — from the summary job, which
    has no business deciding anything about moderation at all.

    **The Care role holds nothing here either.** §6.2 isolates it to the safety
    path; a comment's moderation state is the instructor's lifecycle, not Care's.

    **Both currencies, and a control on each.** A column-scoped `UPDATE` on
    `state` is invisible to `has_table_privilege` and is exactly the shape a "let
    E6 start early" grant would take (`docs/MISTAKES.md` entry 35).

    **The mutation this kills:** `GRANT SELECT, INSERT ON public.moderation_state`
    — the copy-paste of the summary's own grant block onto the table beside it,
    which makes every test in this ticket pass and hands the Monday job the ability
    to overturn a moderator.

    **What this does not assert** is which ticket issued the grant. E4-04 grants
    the same `SELECT` for its own suppression read from a parallel branch, so after
    the merge one `SELECT` here is the end state whichever revision executed it —
    an equality over the privileges rather than over their provenance is what keeps
    that from reading as a widening.
    """
    assert MODERATION_STATE_TABLE in metadata_tables, (
        f"there is no `{MODERATION_STATE_TABLE}` table (there are {sorted(metadata_tables)}). "
        "E4-02 creates it as SPEC §5.2's lifecycle in append-only form, and this ticket's "
        "flagged-held filter reads it."
    )
    probes_can_see_a_grant_they_are_pointed_at(db_session)

    at_table = held_on_table(db_session, MODERATION_STATE_TABLE)
    assert at_table == {
        (APPLICATION_ROLE, privilege) for privilege in GRANTED_ON_THE_MODERATION_RECORD
    }, (
        f"`{MODERATION_STATE_TABLE}` is held as {sorted(at_table)} and the summary job spends "
        f"exactly {[(APPLICATION_ROLE, p) for p in GRANTED_ON_THE_MODERATION_RECORD]}. SPEC §5.1 "
        "has the summaries exclude flagged-held content and ADR 0145 puts that fact nowhere but "
        "this table, so the read is required; every write verb is refused because E4 writes no "
        "moderation state at all and a connection that could append one could publish a comment "
        f"an instructor excluded (§5.2's anti-cherry-picking mechanism). `{CARE_ROLE}` holds "
        "nothing: §6.2 isolates it to the safety path."
    )

    columns = columns_of(db_session, MODERATION_STATE_TABLE)
    assert columns, (
        f"the catalog reports no columns for `public.{MODERATION_STATE_TABLE}`, so the column-grain "
        "equality below is over an empty set and holds of anything."
    )
    at_columns = held_on_columns(db_session, MODERATION_STATE_TABLE)
    assert at_columns == {
        (APPLICATION_ROLE, column, privilege)
        for column in columns
        for privilege in GRANTED_ON_THE_MODERATION_RECORD
    }, (
        f"at column grain `{MODERATION_STATE_TABLE}` is held as {sorted(at_columns)}. A table-wide "
        "`SELECT` covers every column and nothing more; an entry outside that set is a "
        "column-scoped grant, which `has_table_privilege` does not report at all — and an "
        "`UPDATE` on `state` alone is the narrowest way to give this connection the power §5.2 "
        "reserves for an instructor."
    )


def test_the_two_tables_this_ticket_neither_reads_nor_writes_carry_e4_04s_grants_alone(
    db_session: Any, metadata_tables: dict[str, Any], summary_job_contract: Any
) -> None:
    """The pair to the two tests above: the grant is exactly as wide as what is spent.

    E4-02 created four tables and spent nothing on any of them. This ticket writes
    one and reads a second. The other two are the release path's, and E4-04 spends
    them: `SELECT, INSERT` on each, because SPEC §4's weekly cutter writes a batch
    and its membership rows and reads back what it has already released.

    **This test asserted "nothing at all" until the two branches merged**, and the
    change is a repoint rather than a retreat. The question it exists to ask is
    whether *this* ticket's migration widened a table it does not spend, and with
    E4-04's grant now below it in the chain the true form of that question is an
    equality against E4-04's two verbs. An empty-set assertion would be false, and a
    dropped test would leave nothing here asking it at all.

    **This is still the half that catches the plausible over-grant.** A migration
    written as `GRANT ALL ON ALL TABLES IN SCHEMA public TO pulse_app` passes both
    tests above perfectly, gives the job exactly the verbs it needs on the tables it
    needs them on, and quietly opens every other table in the database — and it
    fails here, on `UPDATE`, `DELETE` and `TRUNCATE` arriving on two tables whose
    whole design is that a release cannot be taken back (ADR 0146). The narrower
    `GRANT SELECT, INSERT ON ALL TABLES` is invisible to this module and is caught
    where it has to be: `RUNTIME_BASE_TABLE_PRIVILEGES` in
    `tests/integration/test_identity_grants.py` is an equality over every base table
    in the schema, so a grant reaching a table nobody argued for reds it.

    **Both currencies, as everywhere in this module.** A table-wide grant shows on
    every column, so the expected column set is a product; anything outside it is a
    column-scoped grant `has_table_privilege` does not report at all.
    """
    for name in GRANTED_BY_E4_04:
        assert name in metadata_tables, (
            f"there is no `{name}` table (there are {sorted(metadata_tables)}). E4-02 creates all "
            "four of the report tables together, and this test is about the two of them this "
            "ticket neither reads nor writes."
        )
    probes_can_see_a_grant_they_are_pointed_at(db_session)

    for name in GRANTED_BY_E4_04:
        expected_at_table = {
            (APPLICATION_ROLE, privilege) for privilege in GRANTED_ON_THE_RELEASE_TABLES
        }
        at_table = held_on_table(db_session, name)
        assert at_table == expected_at_table, (
            f"`{name}` carries {sorted(at_table)}, not {sorted(expected_at_table)}. E4-04's "
            "revision `d4c1a7e93f26` grants `SELECT, INSERT` there and nothing else — a release "
            "cannot be un-released (ADR 0146), so no `UPDATE` and no `DELETE` may reach either "
            "table, and `pulse_care` holds nothing on them at all. E4-06 spends nothing here: it "
            "writes `weekly_summary` and reads `moderation_state`. A verb arriving from this "
            "ticket's migration is a widening for a writer that is not this one, and if it is "
            "deliberate it belongs in the ticket that spends it, recorded in "
            "`RUNTIME_BASE_TABLE_PRIVILEGES` in `tests/integration/test_identity_grants.py` with "
            "the sentence it comes from."
        )

        expected_at_columns = {
            (APPLICATION_ROLE, column, privilege)
            for column in columns_of(db_session, name)
            for privilege in GRANTED_ON_THE_RELEASE_TABLES
        }
        at_columns = held_on_columns(db_session, name)
        assert at_columns == expected_at_columns, (
            f"On `{name}`'s columns the roles hold "
            f"{sorted(at_columns - expected_at_columns)} beyond E4-04's table-wide grant, and are "
            f"missing {sorted(expected_at_columns - at_columns)}. A column-scoped grant is the "
            "currency `has_table_privilege` is blind to (`docs/MISTAKES.md` entry 35), and a "
            "column-scoped `UPDATE` on `release_batch_member.batch_id` is the narrowest way to "
            "move a comment into another batch and give it a second release time."
        )


def test_the_write_lands_over_the_connection_the_job_actually_runs_on(
    summary_world: SummaryWorld,
    summary_job_contract: Any,
    application_engine: Any,
) -> None:
    """`docs/MISTAKES.md` entry 46's second half, driven rather than read.

    "A suite that drives a service through the migrating engine has not tested the
    grant at all — where behaviour depends on one, at least one test reaches the
    code through the connection production uses." `app.db` builds its engine as
    `pulse_app` (`tests/fixtures/database.py`), so this is the connection the
    Monday task opens for itself, and this test writes over it directly.

    **Three statements, and the two refusals are what make the acceptance mean
    something.** An insert that lands says the grant is there. An update and a
    delete refused with `permission denied` say it is no wider — and asserted as
    *refusals* rather than as "the row is unchanged afterwards", because an
    unchanged row is equally the result of a statement that was never sent, of a
    `WHERE` that matched nothing, and of a database in recovery.

    **The row is inserted as `pulse_app` and read back as `pulse_app`**, which
    exercises the `SELECT` half over the same connection: the walk's own
    "lacking summary rows" question is a read on this connection, and a grant of
    `INSERT` alone would let a first run write and every later run insert again
    until a unique constraint refused it.

    **The mutation this kills:** the grant issued to the wrong role — the
    bootstrap identity, or `pulse_care` — which reads identically in a migration
    diff, passes anything that writes through `migrated_engine`, and fails only
    when a worker runs. That is the incident entry 46 is about, and this is the
    statement that would have caught it.
    """
    summaries = summary_job_contract.require_table(summary_world.world.tables)
    # A section and the term's weeks, and no responses at all: what this test needs
    # is two rows a foreign key can point at, and a week nobody answered is the
    # cheapest world that has them.
    summary_world.build(summary_job_contract.a_cohort)
    summary_world.commit()

    values = {
        SUMMARY_SECTION_COLUMN: summary_world.section_id(summary_job_contract.a_cohort),
        SUMMARY_WEEK_COLUMN: summary_world.week_id(A_CLOSED_TERM_WEEK),
        SUMMARY_STREAM_COLUMN: A_STREAM,
        SUMMARY_TEXT_COLUMN: A_SUMMARY,
        SUMMARY_RESPONSE_COUNT_COLUMN: A_RESPONSE_COUNT,
        SUMMARY_PROMPT_VERSION_COLUMN: A_PROMPT_VERSION,
        SUMMARY_MODEL_ID_COLUMN: A_MODEL_ID,
        SUMMARY_GENERATED_AT_COLUMN: summary_world.closes_at(A_CLOSED_TERM_WEEK),
    }

    with application_engine.begin() as connection:
        connection.execute(summaries.insert().values(**values))

    with application_engine.connect() as connection:
        stored = [
            dict(row)
            for row in connection.execute(
                summaries.select().where(
                    summaries.c[SUMMARY_SECTION_COLUMN] == values[SUMMARY_SECTION_COLUMN]
                )
            ).mappings()
        ]
    assert len(stored) == 1 and stored[0][SUMMARY_TEXT_COLUMN] == A_SUMMARY, (
        f"the application connection wrote a summary and read back {stored}. Both halves of the "
        "grant are on this path: the walk inserts the row and reads the table to find which "
        "section-weeks still need one."
    )

    with pytest.raises(DatabaseError) as refused_update, application_engine.begin() as connection:
        connection.execute(
            summaries.update()
            .where(summaries.c[SUMMARY_SECTION_COLUMN] == values[SUMMARY_SECTION_COLUMN])
            .values(**{SUMMARY_TEXT_COLUMN: ANOTHER_SUMMARY})
        )
    assert "permission denied" in str(refused_update.value).lower(), (
        f"the update failed, but not for want of a privilege: {refused_update.value}. A syntax "
        "error or a missing column would satisfy `raises` while saying nothing about what the role "
        "may do — and what is being asserted is that this connection *cannot* rewrite a summary an "
        "instructor has read, rather than that it happens not to."
    )

    with pytest.raises(DatabaseError) as refused_delete, application_engine.begin() as connection:
        connection.execute(
            summaries.delete().where(
                summaries.c[SUMMARY_SECTION_COLUMN] == values[SUMMARY_SECTION_COLUMN]
            )
        )
    assert "permission denied" in str(refused_delete.value).lower(), (
        f"the delete failed, but not for want of a privilege: {refused_delete.value}. §4's "
        "retention purge is E13's and runs under a different identity; nothing on the runtime "
        "connection removes a generated summary."
    )
