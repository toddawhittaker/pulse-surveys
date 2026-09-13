"""The grant E4-06 spends comes back off its downgrade — ticket E4-06.

E4-06 grants `pulse_app` `SELECT, INSERT` on `weekly_summary` — the rows the Monday
walk writes and the selection that finds the section-weeks still owed one. Revision
`c7f41a9d2b60` issues it, and its `downgrade()` issues the `REVOKE` that gives it
back.

**The walk also reads `moderation_state`** (SPEC §5.1's "exclude flagged-held
content", which ADR 0145 puts in no other table), and that read is granted one
revision below by `d4c1a7e93f26`, E4-04's. Both branches granted it while they were
built in parallel and both downgrades revoked it, which is a rollback of either
taking a privilege the other still spends; at the merge the duplicate came out of
this revision, so the table appears below in the set that has to **survive** this
downgrade rather than in the set it takes back.

**This module exists because the mutation battery found that nothing executed
them.** Deleting the `REVOKE`s from `downgrade()` changed no test's result, while
the revision's own docstring and the grants file under
`backend/app/views_sql/` say the downgrade revokes. That is `docs/MISTAKES.md`
entry 9 exactly — a guard cited as a guarantee and never run — and the citation is
what makes it worse than an omission: a reviewer reading the revision sees a
symmetric migration, and an operator reading the grants file believes a rollback
takes the privilege back.

**What it costs when it is wrong.** An operator who rolls a deployment back below
this revision has a database where the summary table and the moderation record are
gone from the application's *code* — the walk does not exist at that revision — and
still reachable from its *connection*. The moderation record is the one that
matters: SPEC §5.2's lifecycle is the anti-cherry-picking mechanism and §6.2 keeps
the threat and self-harm route away from the instructor entirely, so a runtime role
left holding a read on it after a rollback is a privilege nobody granted at that
revision and no record describes. `test_identity_grants.py` pins the inventory at
**head**, which is where the grants are supposed to be, so nothing else in this
suite has anything to say about the state a downgrade leaves.

**Both currencies are read, in both directions.** `has_table_privilege` is blind to
a column-scoped grant, and a revoke that clears the table entry while leaving a
column ACL behind reads as a clean rollback and leaves the connection able to
select the column (`docs/MISTAKES.md` entry 35; E3-05's sibling module,
`test_the_line_item_grant_is_given_back_by_a_downgrade.py`, is about the same
asymmetry from the grant side). So "holds nothing" here means nothing at table
grain and nothing on any column.

**The scope of the revoke is asserted as well as its effect.** Two grants that
belong to revisions below this one — `pulse_app`'s `SELECT` on `answer` and on
`classification` — have to survive it. They are the near miss: `REVOKE ALL ON ALL
TABLES IN SCHEMA public FROM pulse_app`, or a revoke written about the role, gives
this module's first assertion perfectly and leaves a database the application
cannot run against at all.

**The revision is named and the one below it is read off the migration**, through
`the_revision_below` in `tests/fixtures/migration_journey.py`, so the chain
re-point this ticket's branch takes at merge moves the journey with it rather than
falsifying a second constant here (`docs/MISTAKES.md` entry 1).

**Each test migrates a database of its own.** `empty_database` is a second database
in the same container, created for one test and dropped after, so a downgrade here
cannot touch the session database every other integration test reads
(`docs/MISTAKES.md` entry 12).

**Green today required**, and it is: the shipped `downgrade()` does revoke. What
this module adds is that the claim is executed rather than read.
"""

from typing import Any

import pytest
from fixtures.migration_journey import (
    MODEL_SCHEMA,
    columns_the_database_reports,
    migrate,
    require_revision,
    the_revision_below,
)
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

# The connection role the application runs as, spelled as
# `tests/integration/test_identity_grants.py` spells it. A copy rather than an
# import: a test module importing another test module depends on where pytest put
# `tests/` on `sys.path`, and an import error is not a red.
APPLICATION_ROLE = "pulse_app"

# The revision this module is about. Named rather than walked to, because it
# exists and the ticket settles it; the revision below it is never named here —
# `the_revision_below` reads it off the migration, so a chain re-pointed at merge
# moves this journey rather than breaking it.
SUMMARY_GRANTS_REVISION = "c7f41a9d2b60"
WHAT_THE_REVISION_IS = (
    "E4-06's grants revision: `SELECT, INSERT` on `weekly_summary` for the Monday walk's own rows "
    "and its 'which section-weeks still need one' selection, and `SELECT` on `moderation_state` "
    "for SPEC §5.1's 'exclude flagged-held content'. If the chain was re-pointed or the file "
    "renamed at merge, this constant is the one place to change"
)

# The two tables this revision grants on, and what it grants there. Written out
# rather than read from the grants files, so a file that stopped issuing a verb
# fails here instead of agreeing with itself (`docs/MISTAKES.md` entry 19).
WEEKLY_SUMMARY = "weekly_summary"
MODERATION_STATE = "moderation_state"
GRANTED = {
    WEEKLY_SUMMARY: ("SELECT", "INSERT"),
}

# Three grants that belong to revisions below this one and must survive its
# downgrade. `answer` is E2-08's and is the table the gather reads the comment
# text from; `classification` is E0-13's; `moderation_state` is E4-04's, granted by
# the revision directly below this one. All three are held by `pulse_app` at head
# as an equality in `test_identity_grants.py`, and all three are on the path a
# blanket revoke takes.
#
# **`moderation_state` moved into this set at the merge of the two branches.** Both
# tickets' revisions granted that read while they were built in parallel, and both
# downgrades revoked it — so rolling either one back took a privilege the other
# still spent. `d4c1a7e93f26` is now the only grantor and the only revoker, and
# what this module asserts about the table is the opposite of what it used to: the
# read has to still be there after this revision goes away.
ANSWER = "answer"
CLASSIFICATION = "classification"
SURVIVES = {ANSWER: "SELECT", CLASSIFICATION: "SELECT", MODERATION_STATE: "SELECT"}

# Every privilege a role can hold on a table, and on a column of one. The absence
# assertion is over the whole set rather than over the verbs this revision
# granted: what a rollback should leave is *nothing*, and a downgrade that revoked
# `SELECT` and forgot `INSERT` would satisfy a narrower reading.
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")

HAS_TABLE_PRIVILEGE = text("SELECT has_table_privilege(:role, :relation, :privilege) AS held")
HAS_COLUMN_PRIVILEGE = text(
    "SELECT has_column_privilege(:role, :relation, :column, :privilege) AS held"
)


def holds_on_table(database: Any, table: str, privilege: str) -> bool:
    """Whether `pulse_app` holds `privilege` on `table` by any mechanism the catalog reports.

    Both currencies in one reading, because what an operator cares about after a
    rollback is whether the connection can still reach the table — not which
    catalog row says so. `has_table_privilege` sees a table grant and one arriving
    through a role membership; `has_column_privilege` sees the column-scoped grant
    the first is blind to, and a revoke that clears the table entry and leaves a
    column ACL behind is a rollback that reads as clean and is not
    (`docs/MISTAKES.md` entry 35).
    """
    engine = create_engine(database.superuser_url)
    try:
        with engine.connect() as connection:
            at_table = connection.execute(
                HAS_TABLE_PRIVILEGE,
                {"role": APPLICATION_ROLE, "relation": f"public.{table}", "privilege": privilege},
            ).scalar_one()
            if at_table:
                return True
            if privilege not in COLUMN_PRIVILEGES:
                return False
            for column in columns_the_database_reports(database, table):
                if connection.execute(
                    HAS_COLUMN_PRIVILEGE,
                    {
                        "role": APPLICATION_ROLE,
                        "relation": f"public.{table}",
                        "column": column,
                        "privilege": privilege,
                    },
                ).scalar_one():
                    return True
            return False
    finally:
        engine.dispose()


def everything_held_on(database: Any, table: str) -> list[str]:
    """Every privilege `pulse_app` holds on `table` right now, in either currency."""
    return [
        privilege for privilege in TABLE_PRIVILEGES if holds_on_table(database, table, privilege)
    ]


def require_table_present(database: Any, table: str) -> None:
    """Stop unless `table` is still in the database, before anything asks about privileges.

    `has_table_privilege` on a relation that does not exist raises rather than
    answering false, so a downgrade that dropped the table would turn every reading
    below into an error in the test body instead of an assertion about a revoke.
    It would also be a different defect: these tables are E4-02's, one revision
    further down, and this revision has no business removing them.
    """
    if not columns_the_database_reports(database, table):
        pytest.fail(
            f"After the downgrade there is no `public.{table}` at all. E4-02's revision creates it, "
            f"one step below {SUMMARY_GRANTS_REVISION}, and this revision grants on it and revokes "
            "again — it does not own the table. A downgrade that drops it is undoing another "
            "ticket's work, and every privilege reading below would raise rather than answer."
        )


def test_the_summary_job_grants_are_revoked_by_the_downgrade_and_its_neighbours_are_not(
    empty_database: Any, alembic_config_pointed_at: Any
) -> None:
    """The two `REVOKE`s in `downgrade()`, executed rather than read.

    **The control comes first**, and it is `docs/MISTAKES.md` entry 35's rule as
    much as entry 3's: every privilege this test reasons about — the two granted
    here and the three that must survive — is required to be *found* at head before
    anything said about it below means anything. A reading that answered false for
    everything — a role name that does not exist in this cluster, a relation
    spelled wrong — would report a perfect rollback against a database where
    nothing had been revoked at all. The exact shape of the grants at head is an
    equality in
    `tests/integration/test_the_summary_writer_is_granted_insert_and_select_and_nothing_wider.py`
    and is deliberately not repeated here; what this needs is that they are
    present, so the walk down has something to take away.

    **Then the database is stepped down to whatever `c7f41a9d2b60` chains from**,
    read off the migration rather than named a second time — and afterwards
    `pulse_app` holds **nothing at all** on either table, in either currency. The
    absence is asserted over the whole privilege set rather than over the two verbs
    this revision granted, because a downgrade that revoked `SELECT` and forgot
    `INSERT` passes the narrower reading and leaves the connection able to write
    rows into a table the code at that revision does not know about.

    **The scope is the near miss.** `pulse_app`'s `SELECT` on `answer` and on
    `classification` belong to revisions below this one and have to survive. A
    downgrade written as `REVOKE ALL ON ALL TABLES IN SCHEMA public FROM pulse_app`
    — or about the role rather than about the two tables — satisfies the assertion
    above perfectly and leaves a database the application cannot serve a single
    request against. That failure would surface as every read path refusing at once,
    naming nothing about this migration.

    **The re-upgrade closes the round trip.** A revoke an upgrade cannot undo is a
    one-way door: an operator who rolled back to diagnose something cannot roll
    forward again without editing grants by hand, and the Monday job would come up
    against a database that silently refuses its first insert.

    **The mutation this kills:** `downgrade()`'s body emptied — which is the state
    the mutation battery found, because deleting the `REVOKE`s changed no test's
    result while the revision's docstring and its grants file went on saying the
    downgrade revokes. That is a guard cited and never executed
    (`docs/MISTAKES.md` entry 9), and it is why this module is one test rather than
    a sentence in a pull request.

    **The near miss it must survive:** a revoke that names the one table and
    nothing else. That is the shipped shape, and the two neighbour assertions are
    what tell it apart from the blanket one.
    """
    config = alembic_config_pointed_at(empty_database)
    require_revision(config, SUMMARY_GRANTS_REVISION, WHAT_THE_REVISION_IS)
    migrate(config, "upgrade", MODEL_SCHEMA, "putting an empty database into the models' shape")

    for table, privileges in GRANTED.items():
        for privilege in privileges:
            assert holds_on_table(empty_database, table, privilege), (
                f"At head, `{APPLICATION_ROLE}` does not hold `{privilege}` on `public.{table}`. "
                f"Revision {SUMMARY_GRANTS_REVISION} grants it — `INSERT` on `{WEEKLY_SUMMARY}` is "
                "the row the Monday walk writes and `SELECT` there is how it finds the "
                "section-weeks still owed one. Until the grant is there, there is nothing for a "
                "downgrade to revoke and every assertion below is about a privilege that never "
                "existed."
            )
    for table, privilege in SURVIVES.items():
        assert holds_on_table(empty_database, table, privilege), (
            f"At head, `{APPLICATION_ROLE}` does not hold `{privilege}` on `public.{table}`, which "
            "belongs to a revision below this one. The scope assertion below is that the downgrade "
            "leaves it alone, and with it already absent that assertion is about nothing."
        )

    below = the_revision_below(config, SUMMARY_GRANTS_REVISION)
    migrate(
        config,
        "downgrade",
        below,
        f"stepping from head to {below}, the revision {SUMMARY_GRANTS_REVISION} chains from",
    )

    for table in GRANTED:
        require_table_present(empty_database, table)
        held = everything_held_on(empty_database, table)
        assert not held, (
            f"After the downgrade `{APPLICATION_ROLE}` still holds {held} on `public.{table}`. "
            f"Revision {SUMMARY_GRANTS_REVISION}'s `downgrade()` issues the `REVOKE`s that give "
            "these back, and its own docstring and the grants files under "
            "`backend/app/views_sql/` both say so — a claim a mutation battery found nothing "
            "executed. An operator who rolls back below this revision would otherwise have a "
            "database where the Monday walk does not exist in the code and the privilege to store "
            "its rows is still on the connection, held by a role no record at that revision "
            "describes.\n\n"
            "The reading covers both currencies, so an entry here can also be a column-scoped "
            "grant a table-grain `REVOKE` left behind."
        )

    for table, privilege in SURVIVES.items():
        assert holds_on_table(empty_database, table, privilege), (
            f"The downgrade also took `{APPLICATION_ROLE}`'s `{privilege}` on `public.{table}`, "
            "which belongs to a revision below this one. A revoke written about the role — or "
            "`ON ALL TABLES IN SCHEMA public` — takes every grant the application has, and the "
            "database it leaves cannot serve a request at all: every read path refuses at once, "
            f"naming nothing about this migration. For `{MODERATION_STATE}` the failure is "
            "narrower and just as invisible — E4-04's suppression path loses the record it "
            "conceals a flag with. Revoke the one table this revision granted on, by name."
        )

    migrate(config, "upgrade", MODEL_SCHEMA, "re-applying the revision the downgrade undid")

    for table, privileges in GRANTED.items():
        for privilege in privileges:
            assert holds_on_table(empty_database, table, privilege), (
                f"After going down and coming back up, `{APPLICATION_ROLE}` still does not hold "
                f"`{privilege}` on `public.{table}`. The revoke is not reversible, so an operator "
                "who rolled back to diagnose something cannot roll forward again without editing "
                "grants by hand — and the Monday job comes up against a database that refuses its "
                "first statement."
            )
    for table, privilege in SURVIVES.items():
        assert holds_on_table(empty_database, table, privilege), (
            f"After the round trip `{APPLICATION_ROLE}` does not hold `{privilege}` on "
            f"`public.{table}` either, so the trip lost a grant that was there when it started."
        )
