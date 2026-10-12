"""E5-03's grants, after E9-12 — what `pulse_app` may do with the benchmark arithmetic.

The ruling on `docs/disputes/E5-03-01.md`: "Grants: SELECT on the four views;
EXECUTE on the two functions". **E9-12 retires the four views and their `SELECT`
grants** (README decision 10), so the read the application does is now only the
second half: `EXECUTE` on `benchmark_set_week` and `benchmark_set_rating_week`.
This module (it keeps its E5-03 name) asserts that read where it now lives:

  - **The call works, as the role production uses.** Both functions are
    `SECURITY DEFINER`: they run with their *owner's* privileges, so an
    `EXECUTE` grant on the right function still fails, or answers empty, if the
    owner cannot read `answer`, `response` or `section` underneath
    (`docs/MISTAKES.md` entry 46: "a suite that drives a service through the
    migrating engine has not tested the grant at all").
  - **Real rows come back through that connection**, compared with the same
    call made by the migrating identity over a committed world.

**Deleted, and why:** `test_the_runtime_role_holds_no_write_privilege_on_a_
benchmark_view` asked the views' ACLs whether `pulse_app` could write to them;
the views are gone, and `test_the_four_cohort_views_are_retired.py` asserts that
no relation of those names exists and that `pulse_app` holds nothing on one. A
function has no write privilege to ask about; what `pulse_app` may execute is
held as an equality by `SANCTIONED_APPLICATION_EXECUTE` in
`test_identity_grants.py`.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    BENCHMARK_FUNCTIONS,
    SET_FUNCTION,
    UG,
    BenchmarkWorld,
    set_function_rows,
)
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

APPLICATION_ROLE = "pulse_app"

THE_COURSE_WEEK = 2
COMMITTED_HOURS = (Decimal("2.0"), Decimal("3.0"), Decimal("4.0"))
COMMITTED_MEAN = Decimal("3.0")
COMMITTED_SECTIONS = 3
A_RATING = Decimal("4")


def a_committed_world(world: BenchmarkWorld, committed_rows: Any) -> list[Any]:
    """Three sections, each answered once at course week 2, committed; their ids."""
    world.build()
    labels = []
    for index, hours in enumerate(COMMITTED_HOURS):
        label = f"committed-{index}"
        world.plant_section(label, cohort="U", level=UG)
        world.respond(
            label,
            course_week=THE_COURSE_WEEK,
            subject=f"e5-03-as-the-app-{index}",
            workload=hours,
            # Both ratings too, so the rating function has rows to answer: with
            # hours alone `benchmark_set_rating_week` has nothing to count.
            instructor_rating=A_RATING,
            course_rating=A_RATING,
        )
        labels.append(label)
    committed_rows.commit()
    return world.section_ids(*labels)


@pytest.mark.parametrize("function", sorted(BENCHMARK_FUNCTIONS), ids=sorted(BENCHMARK_FUNCTIONS))
def test_the_runtime_role_may_call_each_benchmark_set_function(
    application_engine: Any,
    migrated_engine: Any,
    committed_rows: Any,
    committed_benchmark_world: BenchmarkWorld,
    function: str,
) -> None:
    """The `EXECUTE` grant and the owner's reads, asked of the connection the application opens.

    **The control is `current_user`**: every assertion here is about what a
    restricted role may do, and a superuser connection would pass them all.

    **The mutation it exists to survive**: the `GRANT EXECUTE` left out, and the
    function left owned by a role holding nothing on the survey tables, which
    refuses (or answers nothing) at call time with the grant in place.
    """
    sections = a_committed_world(committed_benchmark_world, committed_rows)
    with migrated_engine.connect() as connection:
        seeded = set_function_rows(connection, function, sections)
    assert seeded, (
        f"The migrating connection's call of `{function}` answers nothing for three committed, "
        "answered sections, so the reading below would compare two empty answers."
    )

    with application_engine.connect() as connection:
        role = connection.execute(text("SELECT current_user")).scalar_one()
        assert (
            role == APPLICATION_ROLE
        ), f"This connection reports itself as {role!r}, not {APPLICATION_ROLE!r}."
        try:
            as_the_application = set_function_rows(connection, function, sections)
        except DatabaseError as refused:
            pytest.fail(
                f"`{APPLICATION_ROLE}` cannot call `public.{function}`: {refused}. The ruling on "
                "`docs/disputes/E5-03-01.md` grants it `EXECUTE`; `42501` naming the function is a "
                "missing grant, `42501` naming a table is the owner short a read underneath."
            )
    assert as_the_application == seeded, (
        f"Called as `{APPLICATION_ROLE}`, `{function}` answers {as_the_application}; called by the "
        f"migrating identity over the same committed sections it answers {seeded}. A definer "
        "function runs with its owner's privileges, so a difference is a policy or an owner that "
        "filters rows for one caller and not the other."
    )


def test_the_runtime_role_reads_the_figures_the_committed_world_holds(
    application_engine: Any,
    committed_rows: Any,
    committed_benchmark_world: BenchmarkWorld,
) -> None:
    """One reading of real figures through the connection production uses.

    **The mutation it exists to survive**: a function whose owner is changed to
    a role without a read on the survey tables — the grant stays, the catalog
    still shows `EXECUTE` for `pulse_app`, and every benchmark in the product is
    empty. **The near miss it tolerates**: nothing about the arithmetic beyond
    three sections and their mean, which the set-function modules assert at
    length.
    """
    sections = a_committed_world(committed_benchmark_world, committed_rows)
    with application_engine.connect() as connection:
        rows = [
            row
            for row in set_function_rows(connection, SET_FUNCTION, sections)
            if row["course_week"] == THE_COURSE_WEEK
        ]
    assert len(rows) == 1, (
        f"Called as `{APPLICATION_ROLE}`, `{SET_FUNCTION}` answers {rows} at course week "
        f"{THE_COURSE_WEEK} over three committed sections that each answered then."
    )
    assert rows[0]["section_count"] == COMMITTED_SECTIONS, (
        f"Called as `{APPLICATION_ROLE}`, `section_count` is {rows[0]['section_count']!r}; three "
        "sections answered."
    )
    assert rows[0]["workload_mean"] == COMMITTED_MEAN, (
        f"Called as `{APPLICATION_ROLE}`, `workload_mean` is {rows[0]['workload_mean']!r}; the "
        f"three sections submitted {[str(value) for value in COMMITTED_HOURS]} hours."
    )
