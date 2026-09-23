"""E5-03's grants — what `pulse_app` may do with the four benchmark views.

The ruling on `docs/disputes/E5-03-01.md`: "Grants: SELECT on the four views;
EXECUTE on the two functions". Three questions follow from the first half and
each has a test here; the second half is next door, in
`test_the_benchmark_set_functions_answer_over_a_section_set.py`.

  - **The read works, as the role production uses.** A view is executed with its
    *owner's* privileges, so a `GRANT SELECT` naming the right view still fails
    at query time if the owner cannot read `answer`, `response`, `section` or
    `course` underneath. Nothing in a suite that reads these views through the
    migrating connection would notice: `docs/MISTAKES.md` entry 46 is that exact
    failure — "a suite that drives a service through the migrating engine has
    not tested the grant at all" — so two of the tests below open the
    application connection and one of them reads real rows through it.
  - **Only the read works.** `SELECT` and nothing else, asked of the **ACL**
    rather than of a statement. Attempting the write cannot answer it: all four
    views are aggregates, and PostgreSQL refuses a write to a view it cannot
    make auto-updatable during *rewriting*, before the privilege check — so the
    refusal is `55000` from a role holding nothing and from a role holding `ALL
    PRIVILEGES` alike. That was measured on the pinned server in
    `docs/disputes/E4-03-01.md`, whose ruling this module follows rather than
    re-litigates.
  - **Nothing wider than the read.** That half is asserted in
    `tests/integration/test_identity_grants.py`, whose `SANCTIONED_VIEW_COLUMNS`
    now carries an entry per benchmark view: the columns `pulse_app` may select
    are compared against that record in both directions, so a grant on a fifth
    view or a column added to one of these is a red there. It is not restated
    here, because that enumeration's inventory comes from the catalog and a copy
    of it would be an inventory the guarded structure could shrink.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    BENCHMARK_VIEWS,
    COHORT_WEEK_VIEW,
    UG,
    BenchmarkWorld,
    benchmark_view_columns,
    one_benchmark_row,
    require_benchmark_view,
)
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

# The role `.env.example` gives `DB_APP_USER` and the one every grant in this
# schema belongs to. Spelled here rather than imported from a sibling test
# module for the reason `test_identity_grants.py` gives about its own copies: a
# test module importing another test module resolves only because of where
# pytest puts `tests/` on `sys.path`.
APPLICATION_ROLE = "pulse_app"

HAS_TABLE_PRIVILEGE = "SELECT has_table_privilege(:role, :relation, :privilege)"

READ_PRIVILEGE = "SELECT"
WRITE_PRIVILEGES = ("INSERT", "UPDATE", "DELETE")
WRITE_CASES = [
    (view, privilege) for view in sorted(BENCHMARK_VIEWS) for privilege in WRITE_PRIVILEGES
]

# The committed world the third test reads through the application connection.
TWELVE_WEEKS = 12
THE_COURSE_WEEK = 2
COMMITTED_HOURS = (Decimal("2.0"), Decimal("3.0"), Decimal("4.0"))
COMMITTED_MEAN = Decimal("3.0")
COMMITTED_SECTIONS = 3


@pytest.mark.parametrize("view", sorted(BENCHMARK_VIEWS), ids=sorted(BENCHMARK_VIEWS))
def test_the_runtime_role_may_read_each_benchmark_view(
    migrated_engine: Any, application_engine: Any, view: str
) -> None:
    """The grant, asked of the connection the application really opens.

    The view's existence is checked through the migrating connection first, so
    that "there is no such view" and "the role may not read it" are two
    different reds with two different repairs.

    **The control is `current_user`**, and it is not ceremony: every assertion
    in this module is about what a *restricted* role may do, and a fixture that
    quietly handed back a superuser connection would make all of them pass while
    measuring nothing (`docs/MISTAKES.md` entry 35 — a guard that only ever
    reports absence cannot say what it can see).

    **The mutation it exists to survive**: the `GRANT SELECT` for this view left
    out of the grants file, and — the one a grant-shaped test on the migrating
    connection cannot see — the view left owned by a role holding nothing on
    `response`, `answer`, `section` or `course`, which refuses at execution time
    with the grant on the view itself perfectly in place. These views read wider
    than E4's did: a cohort key needs `section` and `course` as well as the
    survey tables, so there are more ways for the owner to be short one read.
    """
    with migrated_engine.connect() as connection:
        require_benchmark_view(connection, view)

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
        "The ruling on `docs/disputes/E5-03-01.md` grants this role `SELECT` on the four benchmark "
        "views. Two ways this fails and the SQLSTATE tells them apart: `42501` naming the view "
        "itself is a missing `GRANT`; `42501` naming a *table* is the view's owner lacking a read "
        "on what the view selects from, which no grant on the view can repair and which a test "
        "running as the migrating identity would never see."
    )


@pytest.mark.parametrize(
    ("view", "privilege"),
    WRITE_CASES,
    ids=[f"{view}-{privilege.lower()}" for view, privilege in WRITE_CASES],
)
def test_the_runtime_role_holds_no_write_privilege_on_a_benchmark_view(
    db_session: Any, view: str, privilege: str
) -> None:
    """`SELECT` "and nothing else" — asked of the ACL, which is where the answer lives.

    **This asks the catalog rather than attempting the write, and that is a
    ruling rather than a preference** (`docs/disputes/E4-03-01.md`). An
    aggregate view refuses every write with `55000` during rewriting whatever
    the ACL says, so the statement is refused either way and the grant is the
    only place the difference is visible. The two constructions that would make
    a statement-level test observable — an `INSTEAD OF` trigger, a `DO INSTEAD
    NOTHING` rule — were rejected in that ruling as machinery built to make a
    wrong assertion satisfiable, at the cost of the defence the assertion was
    reaching past.

    **The control is the read.** The same probe, the same role and the same
    relation must answer `true` for `SELECT`, so a case that passes because the
    function was answering about something else — a role that exists and is not
    this one, a relation resolved elsewhere on the search path — fails here
    instead of passing silently.

    **The mutation it exists to survive**: `GRANT ALL ON public.<view> TO
    pulse_app`, which flips this probe to `true` for all three verbs at once.
    **The near miss it distinguishes**: `GRANT INSERT` alone, which reds only
    the `-insert` case — which is what the parametrisation buys over one
    assertion covering three verbs and naming neither.
    """
    require_benchmark_view(db_session, view)

    relation = f"public.{view}"
    reads = db_session.execute(
        text(HAS_TABLE_PRIVILEGE),
        {"role": APPLICATION_ROLE, "relation": relation, "privilege": READ_PRIVILEGE},
    ).scalar_one()
    assert reads is True, (
        f"`has_table_privilege` says `{APPLICATION_ROLE}` holds no `{READ_PRIVILEGE}` on "
        f"`{relation}`, so this probe cannot see a privilege the role certainly has and its answer "
        "about the write verbs says nothing (`docs/MISTAKES.md` entry 35). Either the grants file "
        "is missing — `test_the_runtime_role_may_read_each_benchmark_view` in this module is where "
        "that is diagnosed — or this probe is asking about the wrong role or the wrong relation."
    )

    holds = db_session.execute(
        text(HAS_TABLE_PRIVILEGE),
        {"role": APPLICATION_ROLE, "relation": relation, "privilege": privilege},
    ).scalar_one()
    assert holds is False, (
        f"`{APPLICATION_ROLE}` holds `{privilege}` on `{relation}`. The ruling settles this "
        "ticket's grants as `SELECT` on the four views and `EXECUTE` on the two functions; these "
        "are read views over the responses students submitted, and a runtime role that can write "
        "to one can rewrite what every instructor in the institution is benchmarked against.\n\n"
        "The privilege is read from the ACL rather than inferred from a refused statement, because "
        "an aggregate view refuses every write with `55000` during rewriting whatever the ACL says "
        "(`docs/disputes/E4-03-01.md` carries the measurement)."
    )


def test_the_runtime_role_reads_the_cohort_figures_the_committed_world_holds(
    migrated_engine: Any,
    application_engine: Any,
    committed_rows: Any,
    committed_benchmark_world: BenchmarkWorld,
) -> None:
    """One reading of real rows through the connection production uses.

    `docs/MISTAKES.md` entry 46's second sentence: "a suite that drives a
    service through the migrating engine has not tested the grant at all —
    where behaviour depends on one, at least one test reaches the code through
    the connection production uses, or the grant-shaped failure passes review as
    a green suite." Every other test of these views reads them through the
    migrating identity, because that is the only connection that can see rows
    inside a rolled-back transaction. This one commits its world and reads it as
    `pulse_app`.

    **Both readings are taken and compared**, rather than the application's
    alone: an empty answer here with rows there is the grant-shaped failure, and
    an empty answer in both is a world that did not commit.

    **The mutation it exists to survive**: a view whose owner is changed to a
    role without a read on the survey tables — the grant stays, the catalog
    still shows `SELECT` for `pulse_app`, `SANCTIONED_VIEW_COLUMNS` is still
    satisfied, and every benchmark in the product is empty.
    **The near miss it tolerates**: nothing about the arithmetic, which the
    cohort modules assert at greater length; three sections are enough to tell
    "the rows arrived" from "the view answered nothing".
    """
    world = committed_benchmark_world.build()
    for index, hours in enumerate(COMMITTED_HOURS):
        label = f"committed-{index}"
        world.plant_section(label, cohort="U", level=UG)
        world.respond(
            label,
            course_week=THE_COURSE_WEEK,
            subject=f"e5-03-as-the-app-{index}",
            workload=hours,
        )
    committed_rows.commit()

    key = {
        "length_weeks": TWELVE_WEEKS,
        "level": UG,
        "term_id": world.term_id(),
        "course_week": THE_COURSE_WEEK,
    }

    with migrated_engine.connect() as connection:
        seeded = one_benchmark_row(connection, COHORT_WEEK_VIEW, **key)
    assert seeded is not None, (
        "The migrating connection sees no cohort row for the committed week, so this test would "
        "compare two empty readings and report success. Three sections submitted a workload figure "
        "in their second course week; the arithmetic is the cohort modules' subject, not this "
        "test's."
    )

    with application_engine.connect() as connection:
        assert benchmark_view_columns(connection, COHORT_WEEK_VIEW), (
            "The application connection cannot see the view in `pg_catalog` at all, which is a "
            "different failure from a missing grant."
        )
        try:
            as_the_application = one_benchmark_row(connection, COHORT_WEEK_VIEW, **key)
        except DatabaseError as refused:  # pragma: no cover - a red, not a branch
            pytest.fail(
                f"Reading `{COHORT_WEEK_VIEW}` as `{APPLICATION_ROLE}` was refused: {refused}\n\n"
                "The grant itself is the subject of "
                "`test_the_runtime_role_may_read_each_benchmark_view` in this module; this test is "
                "about the rows that come back through that connection, and it cannot ask its own "
                "question until the read succeeds."
            )

    assert as_the_application is not None, (
        f"Read as `{APPLICATION_ROLE}`, `{COHORT_WEEK_VIEW}` has no row for the cohort week the "
        f"migrating connection reads as {seeded}. A view executes with its owner's privileges, so "
        "an owner that cannot read the survey tables — or a row-level policy that applies to this "
        "role and not to the migrating one — empties the benchmark without emptying the database."
    )
    assert as_the_application["section_count"] == COMMITTED_SECTIONS, (
        f"Read as `{APPLICATION_ROLE}`, the cohort's `section_count` is "
        f"{as_the_application['section_count']!r}; three sections answered, and the migrating "
        f"connection reads {seeded['section_count']!r}. A smaller number through this connection "
        "and not the other is a policy or a grant that filters rows rather than refusing the read."
    )
    assert as_the_application["workload_mean"] == COMMITTED_MEAN, (
        f"Read as `{APPLICATION_ROLE}`, the cohort's `workload_mean` is "
        f"{as_the_application['workload_mean']!r}; the three sections submitted "
        f"{[str(value) for value in COMMITTED_HOURS]} hours, a mean of {COMMITTED_MEAN}."
    )
