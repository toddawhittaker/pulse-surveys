"""E4-03's grants — what `pulse_app` may do with the three report views.

The work order settles the file and its contents: "`report_read_grants_v001.sql`
grants `pulse_app` SELECT on the three views and nothing else." Three questions
follow from that sentence and each has a test here.

  - **The read works, as the role production uses.** A view is executed with its
    *owner's* privileges, so a `GRANT SELECT` that names the right view still
    fails at query time if the owner cannot read `answer` or `response`
    underneath. Nothing in a suite that reads these views through the migrating
    connection would notice: `docs/MISTAKES.md` entry 46 is that exact failure —
    "a suite that drives a service through the migrating engine has not tested
    the grant at all" — so two of the three tests below open the application
    connection and one of them reads real rows through it.
  - **Only the read works.** `SELECT` and nothing else means the role holds no
    `INSERT`, `UPDATE` or `DELETE` on any of the three, and that is asked of the
    **ACL** rather than of a statement. Attempting the write cannot answer it on
    this platform: all three views are aggregates, and PostgreSQL refuses a write
    to a view it cannot make auto-updatable during *rewriting*, before the
    privilege check the executor would make — so the refusal is `55000` from a
    role holding nothing and `55000` from a role holding `ALL PRIVILEGES` alike,
    and a statement-level test cannot tell the two apart. That was measured on
    the pinned server, in both directions and against a plain-view canary, in
    `docs/disputes/E4-03-01.md`, which is also where the two ways of *making* the
    statement observable — an `INSTEAD OF` trigger, a `DO INSTEAD NOTHING` rule —
    are rejected: both remove the second line of defence in order to watch the
    first, on a confidentiality-critical read path.
  - **Nothing wider than the read.** That half is asserted next door, in
    `tests/integration/test_identity_grants.py`, whose `SANCTIONED_VIEW_COLUMNS`
    now carries an entry per report view: the columns `pulse_app` may select are
    compared against that record in both directions, so a grant on a fourth view
    or a column added to one of these is a red there. It is not restated here,
    because that enumeration's inventory comes from the catalog and a copy of it
    would be an inventory the guarded structure could shrink.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.report_views import (
    COURSE_STREAM,
    INSTRUCTOR_STREAM,
    RATING_DISTRIBUTION_VIEW,
    REPORT_VIEWS,
    ReportWorld,
    distribution_rows,
    report_view_columns,
    require_report_view,
)
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# The role `.env.example` gives `DB_APP_USER` and the one every grant in this
# schema belongs to. Spelled here rather than imported from a sibling test module
# for the reason `test_identity_grants.py` gives about its own copies: a test
# module importing another test module resolves only because of where pytest puts
# `tests/` on `sys.path`.
APPLICATION_ROLE = "pulse_app"

# The ACL asked directly, with every name bound rather than interpolated. It is
# the question `test_identity_grants.py` already asks of a base table, spelled the
# same way, and `docs/disputes/E4-03-01.md` is why the difference between asking
# the ACL and attempting the write decides this test.
HAS_TABLE_PRIVILEGE = "SELECT has_table_privilege(:role, :relation, :privilege)"

# The privilege `report_read_grants_v001.sql` does confer, used as this probe's
# control: the same role, the same relation, an answer that must be `true`.
# Without it, a probe answering `false` to everything — a role that exists and is
# not this one, a relation the function resolved somewhere else — would satisfy
# every case below while reading nothing (`docs/MISTAKES.md` entry 35: require a
# guard to *find* a privilege on a subject that certainly has one).
READ_PRIVILEGE = "SELECT"

# The three verbs the grants file must not confer. `TRUNCATE`, `REFERENCES` and
# `TRIGGER` are the other table privileges Postgres knows and are deliberately not
# probed: the ruling on E4-03-01 names these three, and each of them is a way to
# change what a week's report says. `GRANT ALL` confers all six at once, so the
# mutation this is written against is caught whichever three are asked.
WRITE_PRIVILEGES = ("INSERT", "UPDATE", "DELETE")

WRITE_CASES = [(view, privilege) for view in sorted(REPORT_VIEWS) for privilege in WRITE_PRIVILEGES]

# The committed world the third test reads through the application connection.
INSTRUCTOR_RATING = 1
COURSE_RATING = 3
THE_WEEK = 7
RATINGS = (Decimal("5"), Decimal("5"), Decimal("2"))


@pytest.mark.parametrize("view", sorted(REPORT_VIEWS), ids=sorted(REPORT_VIEWS))
def test_the_runtime_role_may_read_each_report_view(
    migrated_engine: Any, application_engine: Any, view: str
) -> None:
    """The grant, asked of the connection the application really opens.

    The view's existence is checked through the migrating connection first, so
    that "there is no such view" and "the role may not read it" are two different
    reds with two different repairs.

    **The control is `current_user`**, and it is not ceremony: every assertion in
    this module is about what a *restricted* role may do, and a fixture that
    quietly handed back a superuser connection would make all of them pass while
    measuring nothing (`docs/MISTAKES.md` entry 35 — a guard that only ever
    reports absence cannot say what it can see).

    **The mutation it exists to survive**: the `GRANT SELECT` for this view
    deleted from `report_read_grants_v001.sql`, and — the one a grant-shaped test
    on the migrating connection cannot see — the view left owned by a role that
    holds nothing on `answer` or `response`, which refuses at execution time with
    the grant on the view itself perfectly in place.
    """
    with migrated_engine.connect() as connection:
        require_report_view(connection, view)

    with application_engine.connect() as connection:
        role = connection.execute(text("SELECT current_user")).scalar_one()
        assert role == APPLICATION_ROLE, (
            f"This connection reports itself as {role!r} rather than as {APPLICATION_ROLE!r}, so "
            "it is not the connection the application opens and nothing below is a statement "
            "about a grant."
        )

        refused: DatabaseError | None = None
        try:
            connection.execute(text(f"SELECT * FROM public.{view}"))  # noqa: S608
        except DatabaseError as failure:
            refused = failure

    assert refused is None, (
        f"`{APPLICATION_ROLE}` cannot read `public.{view}`: {refused}\n\n"
        "E4-03 ships `report_read_grants_v001.sql`, which grants this role `SELECT` on the three "
        "report views. Two ways this fails and they are told apart by the SQLSTATE: `42501` on the "
        "view itself is a missing `GRANT`; `42501` naming a *table* is the view's owner lacking a "
        "read on what the view selects from, which no grant on the view can repair and which a "
        "test running as the migrating identity would never see."
    )


@pytest.mark.parametrize(
    ("view", "privilege"),
    WRITE_CASES,
    ids=[f"{view}-{privilege.lower()}" for view, privilege in WRITE_CASES],
)
def test_the_runtime_role_holds_no_write_privilege_on_a_report_view(
    db_session: Any, view: str, privilege: str
) -> None:
    """`SELECT` "and nothing else" — asked of the ACL, which is where the answer lives.

    **This asks the catalog rather than attempting the write, and that is a
    ruling rather than a preference** (`docs/disputes/E4-03-01.md`). The first
    version of this test ran an `INSERT`, an `UPDATE` and a `DELETE` as
    `pulse_app` and required SQLSTATE `42501`, on the reasoning that a bare
    "something raised" would also be satisfied by the rewriter refusing a
    non-auto-updatable view. The measurement went the other way: PostgreSQL
    rewrites before it executes, so the not-auto-updatable refusal — `55000` —
    comes back *before* the privilege check, from a role holding nothing and from
    a role holding `ALL PRIVILEGES` alike. `42501` was therefore not merely the
    answer this grants file does not produce; it is an answer no grants file can
    produce for an aggregate view, so the assertion could not pass and could not
    discriminate. The two constructions that would make it observable — an
    `INSTEAD OF` trigger, a `DO INSTEAD NOTHING` rule — were rejected in the same
    ruling as machinery built to make a wrong assertion satisfiable, at the cost
    of the very defence the wrong assertion was reaching past.

    `has_table_privilege` reads the grant itself, which is what the work order's
    "SELECT on the three views and nothing else" is a sentence about, and what
    `report_read_grants_v001.sql` is a file about.

    **The control is the read.** The same probe, the same role and the same
    relation must answer `true` for `SELECT`, so a case that passes because the
    function was answering about something else — a role that exists and is not
    this one, a relation resolved elsewhere on the search path — fails here
    instead of passing silently.

    **The mutation it exists to survive**: `GRANT ALL ON public.<view> TO
    pulse_app` in `report_read_grants_v001.sql`. That flips this probe to `true`
    for every write verb, so all three cases of the widened view go red —
    `<view>-insert`, `<view>-update` and `<view>-delete` together — and nothing
    else in the suite reads it: `test_identity_grants.py`'s column enumeration
    filters on `privilege_type = 'SELECT'`, and its base-table equality is about
    tables.
    **The near miss it distinguishes**: `GRANT INSERT` alone. Only
    `<view>-insert` goes red for that one; `<view>-update` and `<view>-delete`
    stay green, and correctly — they are separate privileges and each case
    asserts its own. That is what the parametrisation buys over one assertion
    covering all three verbs at once, which would name neither the verb nor the
    view in its failure.
    """
    require_report_view(db_session, view)

    relation = f"public.{view}"
    reads = db_session.execute(
        text(HAS_TABLE_PRIVILEGE),
        {"role": APPLICATION_ROLE, "relation": relation, "privilege": READ_PRIVILEGE},
    ).scalar_one()
    assert reads is True, (
        f"`has_table_privilege` says `{APPLICATION_ROLE}` holds no `{READ_PRIVILEGE}` on "
        f"`{relation}`, so this probe cannot see a privilege the role certainly has and its answer "
        "about the write verbs says nothing (`docs/MISTAKES.md` entry 35). Either the grants file "
        "is missing — `test_the_runtime_role_may_read_each_report_view` in this module is where "
        "that is diagnosed — or this probe is asking about the wrong role or the wrong relation."
    )

    holds = db_session.execute(
        text(HAS_TABLE_PRIVILEGE),
        {"role": APPLICATION_ROLE, "relation": relation, "privilege": privilege},
    ).scalar_one()
    assert holds is False, (
        f"`{APPLICATION_ROLE}` holds `{privilege}` on `{relation}`. E4-03's work order settles this "
        "ticket's grants as `SELECT` on the three views and nothing else, and these are read views "
        "over the responses students submitted: a runtime role that can write to one can rewrite a "
        "week's report.\n\n"
        "The privilege is read from the ACL rather than inferred from a refused statement, because "
        "an aggregate view refuses every write with `55000` during rewriting whatever the ACL says "
        "— so the statement is refused either way and the grant is the only place the difference "
        "is visible (`docs/disputes/E4-03-01.md` carries the measurement, at every point on the "
        "ACL scale and with a plain-view canary)."
    )


def test_the_runtime_role_reads_the_same_counts_the_seeded_week_holds(
    migrated_engine: Any,
    application_engine: Any,
    committed_rows: Any,
    committed_report_world: ReportWorld,
) -> None:
    """One reading of real rows through the connection production uses.

    `docs/MISTAKES.md` entry 46's second sentence: "a suite that drives a service
    through the migrating engine has not tested the grant at all — where behaviour
    depends on one, at least one test reaches the code through the connection
    production uses, or the grant-shaped failure passes review as a green suite."
    Every other test of these views in this ticket reads them through the
    migrating identity, because that is the only connection that can see rows
    inside a rolled-back transaction. This one commits its world and reads it as
    `pulse_app`.

    **The mutation it exists to survive**: a view whose owner is changed to a role
    without a read on the survey tables — the grant on the view stays, the catalog
    still shows `SELECT` for `pulse_app`, `SANCTIONED_VIEW_COLUMNS` is still
    satisfied, and the report is empty or refused for every instructor in the
    product.
    **The near miss it tolerates**: nothing about the arithmetic, which the
    distribution's own module asserts at greater length; three ratings are enough
    to tell "the rows arrived" from "the view answered nothing".
    """
    world = committed_report_world.build()
    for index, rating in enumerate(RATINGS):
        student = world.student(f"e4-03-as-the-app-{index}")
        world.respond(
            student,
            term_week=THE_WEEK,
            answers={INSTRUCTOR_RATING: rating, COURSE_RATING: Decimal("3")},
        )
    committed_rows.commit()

    section_id = world.section_id()
    week_id = world.week_id(THE_WEEK)

    with migrated_engine.connect() as connection:
        seeded = distribution_rows(connection, section_id=section_id, week_id=week_id)
    assert seeded, (
        "The migrating connection sees no distribution row for the committed week, so this test "
        "would compare two empty readings and report success. The three submissions are the "
        "subject of the assertion below, not the grant."
    )

    with application_engine.connect() as connection:
        assert report_view_columns(connection, RATING_DISTRIBUTION_VIEW), (
            "The application connection cannot see the view in `pg_catalog` at all, which is a "
            "different failure from a missing grant."
        )
        try:
            as_the_application = distribution_rows(
                connection, section_id=section_id, week_id=week_id
            )
        except DatabaseError as refused:  # pragma: no cover - a red, not a branch
            pytest.fail(
                f"Reading `{RATING_DISTRIBUTION_VIEW}` as `{APPLICATION_ROLE}` was refused: "
                f"{refused}\n\nThe grant itself is the subject of "
                "`test_the_runtime_role_may_read_each_report_view` in this module; this test is "
                "about the rows that come back through that connection, and it cannot ask its own "
                "question until the read succeeds."
            )

    expected = sorted(
        [
            (INSTRUCTOR_STREAM, Decimal("5"), 2),
            (INSTRUCTOR_STREAM, Decimal("2"), 1),
            (COURSE_STREAM, Decimal("3"), 3),
        ]
    )
    assert as_the_application == expected, (
        f"Read as `{APPLICATION_ROLE}`, the week's distribution is {as_the_application}; the same "
        f"read as the migrating identity gives {seeded}, and the three students submitted "
        f"instructor ratings {[str(value) for value in RATINGS]} and a course rating of 3 each.\n\n"
        "An empty answer here with rows there is the grant-shaped failure: a view executes with "
        "its owner's privileges, so an owner that cannot read the survey tables — or a row-level "
        "policy that applies to this role and not to the migrating one — empties the report "
        "without emptying the database."
    )
