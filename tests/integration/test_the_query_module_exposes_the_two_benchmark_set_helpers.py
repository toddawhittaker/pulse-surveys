"""E5-03's typed wrappers — the two names `views_sql/queries.py` gains.

The ruling on `docs/disputes/E5-03-01.md`: "Typed wrappers in
`views_sql/queries.py` carry the same two names." That module is where this
repository already keeps the statements a read path issues — the org-views sweep
excuses it by name for exactly that reason, and
`tests/unit/test_the_org_views_are_read_only_through_the_grant.py` polices the
excuse — so E5-04 reaches these functions through it rather than writing SQL in
a service.

**The signature is not settled and this module does not settle one.** The ruling
names the wrappers and the SQL arguments and stops. So the call below binds
parameters by name out of a candidate list, and a required parameter it cannot
fill stops with a message naming it: an interface question for the ticket rather
than a guess written into a fixture. `tests/fixtures/report_views.py` takes the
same approach to `recompute_response_validity` and says why at length.

**What is asserted is that the wrapper answers what the SQL function answers.**
Not its return type, not whether it hands back rows or a dataclass — those are
the implementer's, and a test that pinned one would be building to a shape
nobody agreed. The figures have to match, because a wrapper that quietly
computed something else would be a third implementation of this ticket's
arithmetic.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    SET_FUNCTION,
    SET_RATING_FUNCTION,
    UG,
    BenchmarkWorld,
    call_wrapper,
    query_module,
    query_wrapper,
    require_benchmark_function,
    set_function_rows,
)

pytestmark = pytest.mark.integration

THE_COURSE_WEEK = 2
FIRST_HOURS = Decimal("2.0")
SECOND_HOURS = Decimal("5.0")
A_RATING = Decimal("3")


def a_two_section_set(world: BenchmarkWorld) -> BenchmarkWorld:
    """Two answered sections, which is enough for a wrapper to have something to return."""
    world.build()
    for label, hours in (("first", FIRST_HOURS), ("second", SECOND_HOURS)):
        world.plant_section(label, cohort="U", level=UG)
        world.respond(
            label,
            course_week=THE_COURSE_WEEK,
            subject=f"e5-03-wrapper-{label}",
            workload=hours,
            instructor_rating=A_RATING,
        )
    return world


def figures_of(answered: Any) -> list[dict[str, Any]]:
    """Whatever a wrapper returned, as a list of mappings this test can compare.

    Three shapes are accepted, because the ruling settles none of them and each
    is an ordinary way to type a read: rows the driver produced, mappings, or
    objects with attributes. What is *not* accepted is a shape this cannot read
    at all, which stops with a message rather than an attribute error — the
    difference between an interface question and a broken test.
    """
    rows = list(answered)
    if not rows:
        return []
    first = rows[0]
    if isinstance(first, dict):
        return [dict(row) for row in rows]
    if hasattr(first, "_mapping"):
        return [dict(row._mapping) for row in rows]
    if hasattr(first, "__dict__") or hasattr(first, "__slots__"):
        return [
            {
                name: getattr(row, name)
                for name in dir(row)
                if not name.startswith("_") and not callable(getattr(row, name))
            }
            for row in rows
        ]
    pytest.fail(
        f"The wrapper answered {type(first)!r} values, which this test cannot read as rows of "
        "named figures. Rows, mappings and objects with attributes are all handled; if the wrapper "
        "returns something else, `figures_of` in this module is the one place that changes — the "
        "return shape is the implementer's decision and this test is about the numbers in it."
    )


@pytest.mark.parametrize("name", sorted((SET_FUNCTION, SET_RATING_FUNCTION)))
def test_the_query_module_exposes_a_typed_wrapper_for_each_set_function(name: str) -> None:
    """The names, and a failure that says which deliverable is missing.

    The import happens inside the test body rather than at the top of the file,
    so a tree without the module is a **failed** test naming it rather than a
    collection error — `docs/MISTAKES.md` entry 44, and the same reason
    `tests/fixtures/authz_data.py` reaches `app.services.authz` that way.

    **The mutation it exists to survive**: the SQL functions shipped and the
    wrappers not, which leaves E5-04 to write its own statement in a service —
    the state the org-views sweep exists to prevent, because a statement outside
    `queries.py` is a read nothing polices.
    """
    module = query_module()
    wrapper = query_wrapper(name)
    assert callable(wrapper), (
        f"`{module.__name__}.{name}` is not callable. The ruling on "
        "`docs/disputes/E5-03-01.md` puts a typed wrapper here under the same name as the SQL "
        "function."
    )


@pytest.mark.parametrize("name", sorted((SET_FUNCTION, SET_RATING_FUNCTION)))
def test_each_typed_wrapper_answers_what_its_sql_function_answers(
    benchmark_world: BenchmarkWorld, name: str
) -> None:
    """One arithmetic, reached two ways, and the two must agree.

    The wrapper is called over the same two sections the SQL function is called
    over, and every figure the ruling names has to match. What the wrapper does
    with the rows afterwards — a dataclass, a mapping, a domain object — is the
    implementer's; that the numbers are the function's is not.

    **The non-vacuity guard is the SQL side**, taken first: a wrapper returning
    nothing would agree perfectly with a function returning nothing
    (`docs/MISTAKES.md` entry 3), so the direct call is required to produce rows
    before the comparison happens.

    **The mutation it exists to survive**: a wrapper that issues its own
    `SELECT` over the base tables instead of calling the function — which is
    what makes it a third implementation, and which would also be a read of
    person-keyed rows from the application connection, the thing the ruling
    withdrew a whole view to prevent.
    """
    world = a_two_section_set(benchmark_world)
    require_benchmark_function(world.session, name)
    world.session.flush()

    section_ids = world.section_ids("first", "second")
    from_sql = set_function_rows(world.session, name, section_ids)
    assert from_sql, (
        f"`{name}` answered nothing over two sections that were both answered, so a wrapper "
        "answering nothing would agree with it and this comparison would be vacuous. The function's "
        "own behaviour is "
        "`test_the_benchmark_set_functions_answer_over_a_section_set.py`'s subject."
    )

    from_wrapper = figures_of(call_wrapper(name, world.session, section_ids))
    assert from_wrapper, (
        f"`queries.{name}` answered nothing over the same two sections the SQL function answered "
        f"{len(from_sql)} rows for. A wrapper that returns nothing is a read path that is present "
        "and does not work, which E5-04 would meet as an empty benchmark."
    )

    def keyed(rows: list[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
        return {
            (row.get("course_week"), row.get("stream")): {
                figure: row.get(figure) for figure in sorted(from_sql[0])
            }
            for row in rows
        }

    expected = keyed(from_sql)
    answered = keyed(from_wrapper)
    assert answered == expected, (
        f"`queries.{name}` and `public.{name}` disagree over the same two sections.\n\n"
        f"Through the wrapper: {answered}\nThrough the function: {expected}\n\n"
        "The wrapper is a typed way to reach one arithmetic, not a second one. A wrapper that "
        "issues its own statement over the base tables would produce exactly this failure — and "
        "would also be reading person-keyed rows on the application connection, which is what the "
        "ruling on `docs/disputes/E5-03-01.md` withdrew a view to prevent."
    )
