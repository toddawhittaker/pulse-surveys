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
  - **Only the read works.** `SELECT` and nothing else means an `INSERT`, an
    `UPDATE` and a `DELETE` are refused, and refused *for want of privilege*.
    That distinction is the point of asserting the SQLSTATE rather than the
    exception: an aggregate view is not auto-updatable, so Postgres would refuse
    a write to it with `55000` even if the grant were `ALL` — a second defence
    layer producing the same visible outcome, which is what turns a green guard
    into a guard nobody has actually run.
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
from fixtures.supervision import sqlstate_of
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# The role `.env.example` gives `DB_APP_USER` and the one every grant in this
# schema belongs to. Spelled here rather than imported from a sibling test module
# for the reason `test_identity_grants.py` gives about its own copies: a test
# module importing another test module resolves only because of where pytest puts
# `tests/` on `sys.path`.
APPLICATION_ROLE = "pulse_app"

# `insufficient_privilege`. The class of refusal this ticket's grants are about,
# and the one that has to be told apart from `55000` (`object_not_in_prerequisite
# _state`), which is what Postgres answers for a write to a view it cannot make
# auto-updatable — an aggregate view, which all three of these are.
INSUFFICIENT_PRIVILEGE = "42501"
NOT_UPDATABLE = "55000"

# The three verbs the grants file must not confer, each written so that the only
# thing standing in its way is a privilege. No row is named and no value has to be
# valid: the ACL is checked before any of that matters.
WRITE_STATEMENTS = {
    "insert": "INSERT INTO public.{view} ({column}) VALUES (NULL)",
    "update": "UPDATE public.{view} SET {column} = {column}",
    "delete": "DELETE FROM public.{view}",
}

WRITE_CASES = [(view, verb) for view in sorted(REPORT_VIEWS) for verb in sorted(WRITE_STATEMENTS)]

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
    ("view", "verb"), WRITE_CASES, ids=[f"{view}-{verb}" for view, verb in WRITE_CASES]
)
def test_the_runtime_role_may_not_write_to_a_report_view(
    migrated_engine: Any, application_engine: Any, view: str, verb: str
) -> None:
    """`SELECT` "and nothing else" — the other three verbs, refused for want of privilege.

    **The SQLSTATE is asserted rather than the exception**, and that is the whole
    design of this test. Two layers refuse a write here: the ACL, because the
    grants file confers only `SELECT`; and the rewriter, because a view with a
    `GROUP BY` is not auto-updatable. The second answers `55000` and would produce
    an identically green test against a grants file that had handed this role
    `ALL PRIVILEGES` — so a test that merely required "something raised" would be
    satisfied by the layer this ticket does not own, and a widened grant would
    ship green.

    **The mutation it exists to survive**: `GRANT SELECT` widened to `GRANT ALL`
    or to `GRANT SELECT, INSERT, UPDATE, DELETE` in
    `report_read_grants_v001.sql`, which flips the SQLSTATE from `42501` to
    `55000` — a difference nothing else in this suite reads.
    """
    with migrated_engine.connect() as connection:
        columns = require_report_view(connection, view)

    statement = WRITE_STATEMENTS[verb].format(view=view, column=columns[0])
    refused: DatabaseError | None = None
    with application_engine.connect() as connection:
        role = connection.execute(text("SELECT current_user")).scalar_one()
        assert (
            role == APPLICATION_ROLE
        ), f"This connection reports itself as {role!r} rather than as {APPLICATION_ROLE!r}."
        try:
            connection.execute(text(statement))
        except DatabaseError as failure:
            refused = failure
        finally:
            connection.rollback()

    assert refused is not None, (
        f"`{APPLICATION_ROLE}` was allowed to run `{statement}`. The work order settles this "
        "ticket's grants as `SELECT` on the three views and nothing else, and these are read views "
        "over the responses students submitted: a runtime role that can write to one can rewrite a "
        "week's report."
    )
    code = sqlstate_of(refused)
    assert code == INSUFFICIENT_PRIVILEGE, (
        f"`{statement}` was refused with SQLSTATE {code!r}, not {INSUFFICIENT_PRIVILEGE!r}: "
        f"{refused}\n\n"
        f"{NOT_UPDATABLE!r} is Postgres refusing a write to a view it cannot make "
        "auto-updatable, which every aggregate view is — so it is the answer this statement gets "
        "whatever the grants say, including from a role holding `ALL PRIVILEGES`. This test is "
        "about the grant, so it requires the refusal to come from the ACL: that is the layer "
        "E4-03 owns and the only one that would notice a widened `GRANT`."
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
