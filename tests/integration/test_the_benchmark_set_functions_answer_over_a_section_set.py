"""E5-03's building block — figures over an arbitrary section set, computed where the rows live.

The ruling on `docs/disputes/E5-03-01.md` replaced the work order's person-keyed
view with two `SECURITY DEFINER` functions:

> **Shape 2 is ruled in.** The building block is a pair of `SECURITY DEFINER`
> functions in the `views_sql/` versioned shape, the `resolve_subject_for_user`
> precedent (ADR 0139): the section-id set goes in, numbers come out, and no row
> keyed to a student is ever selectable by `pulse_app`. ADR 0150's plain-grant
> preference is answered head-on: a plain grant *cannot* do this — any grant wide
> enough to let the application count distinct respondents across an arbitrary
> section set is a grant on person-keyed rows, which is the thing being refused.

E5-04 is the caller (default set, university line, named set — none of which is
a cohort key, because each is a list of sections chosen by a rule the database
does not hold). Nothing in E5-03 calls them, which the ticket's boundary says
outright, so this module is where their behaviour is pinned.

**The respondent rule is the reason these are functions and not a pre-aggregate.**
A per-section figure summed across a set counts a student in two of its sections
twice, and the number that comes out is compared against
`benchmark_min_respondents_default` — a threshold about people. `docs/MISTAKES.md`
entry 50 in one sentence, and the first test below plants it.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    BENCHMARK_FUNCTIONS,
    COHORT_WEEK_VIEW,
    INSTRUCTOR_STREAM,
    SET_FUNCTION,
    SET_RATING_FUNCTION,
    UG,
    BenchmarkWorld,
    empty_set_call,
    function_shape,
    require_benchmark_function,
    set_function_rows,
)
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration

APPLICATION_ROLE = "pulse_app"
TWELVE_WEEKS = 12
THE_COURSE_WEEK = 2

# The relation the work order asked for and the ruling withdrew. Named here so
# that "it was built anyway" is a red rather than a thing nobody looks for.
WITHDRAWN_VIEW = "benchmark_respondent_week"

# Postgres reports an insufficient privilege as 42501 and an undefined relation
# as 42P01. Both are refusals of the withdrawn read and either satisfies the
# test below; what must not happen is rows coming back.
INSUFFICIENT_PRIVILEGE = "42501"
UNDEFINED_RELATION = "42P01"

# The set world. Three sections of one cohort and a fourth the caller does not
# pass in, so "only the sections it was given" has an out side as well as an in
# side. One student is enrolled in two of the three and answers in both, which
# is the distinct-respondent plant.
SHARED_HOURS_IN_FIRST = Decimal("1.0")
SHARED_HOURS_IN_SECOND = Decimal("3.0")
THIRD_HOURS = Decimal("5.0")
OUTSIDER_HOURS = Decimal("20.0")

# Four responses inside the set, from three people.
SET_RESPONSES = 4
SET_RESPONDENTS = 3
SET_SECTIONS = 3
# (1.0 + 3.0 + 5.0 + 5.0) / 4 — the third section carries two respondents.
SET_WORKLOAD_MEAN = Decimal("3.5")
SET_WORKLOAD_MEDIAN = Decimal("4.0")
MEAN_IF_THE_OUTSIDER_IS_COUNTED = Decimal("6.8")

# The four figures inside the set, as a failure message prints them.
HOURS_INSIDE_THE_SET = [
    str(value)
    for value in (SHARED_HOURS_IN_FIRST, SHARED_HOURS_IN_SECOND, THIRD_HOURS, THIRD_HOURS)
]

A_RATING = Decimal("4")


def a_section_set_and_one_section_outside_it(world: BenchmarkWorld) -> BenchmarkWorld:
    """Three sections a caller passes in, one it does not, and a student in two of the three."""
    world.build()
    for label in ("in-one", "in-two", "in-three", "outside"):
        world.plant_section(label, cohort="U", level=UG)

    shared = world.student("e5-03-set-shared", enrolled_in=("in-one", "in-two"))
    world.respond(
        "in-one",
        course_week=THE_COURSE_WEEK,
        student=shared,
        workload=SHARED_HOURS_IN_FIRST,
        instructor_rating=A_RATING,
    )
    world.respond(
        "in-two",
        course_week=THE_COURSE_WEEK,
        student=shared,
        workload=SHARED_HOURS_IN_SECOND,
        instructor_rating=A_RATING,
    )
    world.respond(
        "in-three",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-set-third-a",
        workload=THIRD_HOURS,
        instructor_rating=A_RATING,
    )
    world.respond(
        "in-three",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-set-third-b",
        workload=THIRD_HOURS,
        instructor_rating=A_RATING,
    )
    world.respond(
        "outside",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-set-outsider",
        workload=OUTSIDER_HOURS,
        instructor_rating=A_RATING,
    )
    return world


def the_set_row(world: BenchmarkWorld, *labels: str) -> dict[str, Any]:
    """The one row `benchmark_set_week` answers for this course week over `labels`."""
    rows = [row for row in world.set_week(*labels) if row["course_week"] == THE_COURSE_WEEK]
    assert rows, (
        f"`{SET_FUNCTION}` answered no row at course week {THE_COURSE_WEEK} for sections "
        f"{list(labels)}, in which every one of them was answered. Every assertion below would be "
        "vacuous against an empty answer (`docs/MISTAKES.md` entry 3)."
    )
    assert len(rows) == 1, (
        f"`{SET_FUNCTION}` answered {len(rows)} rows for one course week over one section set: "
        f"{rows}. The ruling settles its rows as {list(BENCHMARK_FUNCTIONS[SET_FUNCTION])}, keyed "
        "by the course week alone — the set is the argument, so a row per section is the "
        "pre-aggregate the ruling rejected."
    )
    return rows[0]


# `invariant`-marked for the reason its twin on the cohort view carries at
# length (`test_a_benchmark_cohort_counts_each_respondent_once.py`): this is the
# number §4.1 item 7's minimum is compared against, so an over-count shows a
# comparison figure computed from fewer people than the rule requires. It is
# marked on both sides because E5-04 reads the views behind one line and these
# functions behind another, and a guard that covers one currency of a figure and
# not the other is `docs/MISTAKES.md` entry 35's shape.
@pytest.mark.invariant
def test_the_set_function_counts_a_repeat_respondent_once_across_the_whole_set(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The ruling's own reason for this shape, and `docs/MISTAKES.md` entry 50 again.

    Three sections, four responses, three people — one student answered in two
    of the three. The distinct-respondent figure over the *set* is three.

    **This is the arithmetic a pre-aggregate cannot do**, which is why the
    building block is a function taking the whole set rather than a per-section
    view the caller sums: "sums of distincts are not distinct sums". A summed
    per-section count answers four, and four is what E5-04 would compare against
    `benchmark_min_respondents_default` — over-counting people in the direction
    that lets a thin set through a threshold that exists to protect them.

    **The response count is asserted beside it**, because three is also what a
    view that lost one of the shared student's responses would answer, and the
    two defects want different fixes.

    **The mutation it exists to survive**: `count(DISTINCT <person key>)`
    computed per section and summed; `count(*)`; and a `GROUP BY section_id`
    left in the function's body, which turns one row into three and is caught by
    `the_set_row`'s own check.
    """
    world = a_section_set_and_one_section_outside_it(benchmark_world)
    row = the_set_row(world, "in-one", "in-two", "in-three")

    assert row["response_count"] == SET_RESPONSES, (
        f"`response_count` is {row['response_count']!r} where four responses were submitted across "
        "the three sections in the set. This is the premise of the assertion below rather than its "
        "subject: with it wrong, a respondent count of 3 could be three responses."
    )
    assert row["respondent_count"] == SET_RESPONDENTS, (
        f"`respondent_count` is {row['respondent_count']!r} over a section set three people "
        "answered — one of them in two of its sections.\n\n"
        "A 4 is a count of responses, or a per-section distinct count summed across the set. The "
        "ruling on `docs/disputes/E5-03-01.md` chose this shape over a per-section pre-aggregate "
        "for exactly that arithmetic, and `docs/MISTAKES.md` entry 50 is what it costs: E5-04 "
        "compares this number against `benchmark_min_respondents_default`, so an over-count shows "
        "a comparison figure computed from fewer people than the threshold requires."
    )
    assert row["section_count"] == SET_SECTIONS, (
        f"`section_count` is {row['section_count']!r} where three sections were passed in and all "
        "three were answered. E5-04 compares this against `benchmark_min_sections_default`."
    )


def test_the_set_function_answers_over_only_the_sections_it_was_given(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The out half of the set boundary: a section outside the argument is outside the figure.

    A fourth section of the same cohort answered the same course week with 20
    hours and is not in the array. The mean over the set is 3.5; with the
    outsider it is 6.8, and the section count is 4.

    This is the boundary that makes the function a *set* function rather than a
    cohort view with extra steps. E5-04's three resolutions — the default set
    (one lead's courses), the university line, a named set — are three different
    subsets of one cohort, and decision 5 has the hero section excluded from its
    own comparison set. Every one of those depends on the argument being
    honoured exactly.

    **The mutation it exists to survive**: the argument ignored and the cohort
    of the first section computed instead — which answers correctly whenever the
    caller happens to pass a whole cohort, and is wrong for every default set
    E5-04 builds, because a default set never contains the hero.
    """
    world = a_section_set_and_one_section_outside_it(benchmark_world)
    row = the_set_row(world, "in-one", "in-two", "in-three")

    assert row["section_count"] == SET_SECTIONS, (
        f"`section_count` is {row['section_count']!r}. Three sections were passed in; a fourth "
        "section of the same length, level, term and course week answered too and was not. A 4 is "
        "the argument ignored in favour of the cohort."
    )
    assert row["workload_mean"] == SET_WORKLOAD_MEAN, (
        f"`workload_mean` is {row['workload_mean']!r}. The four responses inside the set carry "
        f"{HOURS_INSIDE_THE_SET} hours, a mean of {SET_WORKLOAD_MEAN}. "
        f"{MEAN_IF_THE_OUTSIDER_IS_COUNTED} is the fifth response — {OUTSIDER_HOURS} hours, from "
        "the section outside the argument — folded in."
    )
    assert row["workload_median"] == SET_WORKLOAD_MEDIAN, (
        f"`workload_median` is {row['workload_median']!r}; the middle pair of 1.0, 3.0, 5.0 and "
        f"5.0 is 3.0 and 5.0, whose midpoint is {SET_WORKLOAD_MEDIAN}. An answer of 3.0 is "
        "`percentile_disc` rather than `percentile_cont`, which SPEC §5.1's 'true numeric "
        "statistics' rules out."
    )


def test_the_set_function_takes_the_outsider_in_when_it_is_passed_in(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The in half of the same boundary, on the same world.

    The fourth section is passed in and the figures move: four sections, five
    responses, and a mean of 6.8. Without this, the test above is satisfied by a
    function that ignores its argument in the other direction — one that only
    ever answers over three sections, or that silently drops any section id it
    was not expecting.

    **The mutation it exists to survive**: an argument truncated, deduplicated
    against a cohort, or intersected with something; and the whole function
    hard-wired to the first section's cohort, which would answer the same
    numbers for both of these tests and be caught by neither alone.
    """
    world = a_section_set_and_one_section_outside_it(benchmark_world)
    row = the_set_row(world, "in-one", "in-two", "in-three", "outside")

    assert row["section_count"] == SET_SECTIONS + 1, (
        f"`section_count` is {row['section_count']!r} where four sections were passed in and all "
        "four answered this course week."
    )
    assert row["response_count"] == SET_RESPONSES + 1, (
        f"`response_count` is {row['response_count']!r} where five responses were submitted across "
        "the four sections."
    )
    assert row["workload_mean"] == MEAN_IF_THE_OUTSIDER_IS_COUNTED, (
        f"`workload_mean` is {row['workload_mean']!r} over four sections. The five responses carry "
        f"1.0, 3.0, 5.0, 5.0 and {OUTSIDER_HOURS} hours, a mean of "
        f"{MEAN_IF_THE_OUTSIDER_IS_COUNTED}. A mean of {SET_WORKLOAD_MEAN} is the fourth section's "
        "id accepted and then not used."
    )


def test_the_set_rating_function_answers_per_stream(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The rating function's key: a course week and a stream, as the ruling settles it.

    Every response in the set rated the instructor and left the course rating
    unanswered, so the instructor stream has a mean over four ratings and the
    course stream has no row at all — absence rather than a null, the same
    contract the views carry.

    **The mutation it exists to survive**: `stream` dropped from the function's
    output, which collapses SPEC §5.1's two panels into one series; and a
    `LEFT JOIN` that emits a course-stream row with a null mean, which E5-04
    would carry into the payload as a suppressed-looking figure that was never
    computed from anything.
    """
    world = a_section_set_and_one_section_outside_it(benchmark_world)
    rows = [
        row
        for row in world.set_rating_week("in-one", "in-two", "in-three")
        if row["course_week"] == THE_COURSE_WEEK
    ]
    assert rows, (
        f"`{SET_RATING_FUNCTION}` answered nothing at course week {THE_COURSE_WEEK}, in which four "
        "instructor ratings were submitted across the three sections in the set."
    )

    streams = sorted(str(row["stream"]) for row in rows)
    assert streams == [INSTRUCTOR_STREAM], (
        f"`{SET_RATING_FUNCTION}` answered the streams {streams} at course week "
        f"{THE_COURSE_WEEK}. Every response in this set carries an instructor rating and no course "
        "rating, so one stream is the whole answer: a second row is a stream fabricated from "
        "nothing, and an empty list is `stream` missing from the output altogether."
    )
    assert rows[0]["rating_count"] == SET_RESPONSES, (
        f"`rating_count` is {rows[0]['rating_count']!r}; four instructor ratings were submitted in "
        "the set, two of them by one student. It is a count of ratings, not of people — the count "
        f"of people is `respondent_count` on `{SET_FUNCTION}`."
    )
    assert (
        rows[0]["rating_mean"] == A_RATING
    ), f"`rating_mean` is {rows[0]['rating_mean']!r}; all four ratings were {A_RATING}."


def test_the_set_functions_agree_with_the_cohort_view_over_the_same_sections(
    benchmark_world: BenchmarkWorld,
) -> None:
    """One arithmetic, two callers — the figures must not diverge.

    Handed exactly the sections a cohort contains, the function answers what the
    cohort view answers. Two implementations of one set of figures is the defect
    this catches: E5-04 reads the views for the university line and the
    functions for a named set, and a report showing a section against two
    benchmarks computed by two different rules is worse than one showing
    neither.

    **The world is the four sections of one cohort week** — the set world's
    three plus the outsider, which together are the whole cohort — so the two
    answers are over the same rows by construction rather than by coincidence.

    **The mutation it exists to survive**: the function written with its own
    `avg` and its own `percentile_cont` that disagree with the view's in a
    detail — a cast dropped, a null handled differently, `count(*)` where the
    view has `count(DISTINCT ...)`. Each of those passes its own module's tests
    and is visible only when the two are set side by side.
    """
    world = a_section_set_and_one_section_outside_it(benchmark_world)

    from_the_view = world.cohort_week(
        length_weeks=TWELVE_WEEKS, level=UG, course_week=THE_COURSE_WEEK
    )
    assert from_the_view is not None, (
        f"`{COHORT_WEEK_VIEW}` has no row for the cohort these four sections make up, so there is "
        "nothing to compare the function against. The cohort modules diagnose that."
    )

    from_the_function = the_set_row(world, "in-one", "in-two", "in-three", "outside")

    shared = [
        "workload_mean",
        "workload_median",
        "response_count",
        "respondent_count",
        "section_count",
    ]
    disagreements = {
        name: (from_the_view[name], from_the_function[name])
        for name in shared
        if from_the_view[name] != from_the_function[name]
    }
    assert not disagreements, (
        f"The cohort view and `{SET_FUNCTION}` disagree over the same four sections, as "
        f"`{{figure: (view, function)}}`: {disagreements}.\n\n"
        "The set passed to the function is every section of the cohort the view keys, so the two "
        "are computing the same figures over the same rows. A divergence is two implementations of "
        "one arithmetic — and E5-04 puts both on one report, the view behind the university line "
        "and the function behind a named set."
    )


def test_an_empty_section_set_answers_no_rows(benchmark_world: BenchmarkWorld) -> None:
    """The degenerate argument: no rows, not an error and not a row of nulls.

    E5-04 resolves a named set that may have no members and a default set that
    may be empty once the hero section is excluded from it (decision 5), so an
    empty array is an ordinary input rather than a programming error. E5-01's
    empty-set decision makes the service answer a suppressed figure for it, and
    it can only do that if the read below it comes back empty rather than
    raising.

    **The non-vacuity guard is the same call with real ids**, in the same test:
    "no rows" is what a function that always answers nothing gives too.

    **The mutation it exists to survive**: a body that raises on an empty array
    — a `strict` unnest, a division by the section count — and one that answers
    a single row of nulls with a zero section count, which E5-04 would read as a
    cohort of nobody rather than as no cohort at all.
    """
    world = a_section_set_and_one_section_outside_it(benchmark_world)
    require_benchmark_function(world.session, SET_FUNCTION)

    populated = set_function_rows(
        world.session, SET_FUNCTION, world.section_ids("in-one", "in-two", "in-three")
    )
    assert populated, (
        f"`{SET_FUNCTION}` answered nothing for three sections that were all answered, so the "
        "emptiness asserted below says nothing about the empty argument."
    )

    try:
        rows = [dict(row) for row in world.session.execute(empty_set_call(SET_FUNCTION)).mappings()]
    except DatabaseError as failure:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{SET_FUNCTION}(ARRAY[]::uuid[])` raised {failure}.\n\nAn empty section set is an "
            "ordinary input: E5-04 resolves named sets that may have no members, and a default set "
            "can be empty once the hero section is excluded from it (the E5 breakdown's decision "
            "5). The service answers a suppressed figure for that case and needs a read that comes "
            "back empty rather than one that fails."
        )

    assert rows == [], (
        f"`{SET_FUNCTION}(ARRAY[]::uuid[])` answered {rows}. No section means no responses, so no "
        "row: a row of nulls with a zero count is a cohort of nobody, which is a different thing "
        "from no cohort and suppresses for a different reason."
    )


def test_both_set_functions_are_security_definer(db_session: Any) -> None:
    """The mechanism, not just the answer — a definer is the whole of the ruling.

    "The section-id set goes in, numbers come out, and no row keyed to a student
    is ever selectable by `pulse_app`." That property is bought by the function
    running as its **owner** rather than as its caller: a `SECURITY INVOKER`
    function is a view with parentheses, and whatever the application role may
    not read inside it, it may not read through it either.

    ADR 0139's `resolve_subject_for_user` is the precedent this follows, and
    `test_identity_grants.py` already sweeps every definer in `public` for an
    owner that is not a superuser. What that sweep cannot ask is whether *these
    two* are definers at all — a plain function passes it by not being in the
    set.

    **The mutation it exists to survive**: `SECURITY DEFINER` left off either
    file. On a tree where the application role happens to hold the reads the
    body needs, that mutation changes no answer in this module and no answer in
    E5-04 — it changes only what happens when a later ticket narrows a base-table
    grant, at which point every benchmark in the product fails at once, for a
    reason nobody will connect to this file.
    """
    for name in sorted(BENCHMARK_FUNCTIONS):
        shape = require_benchmark_function(db_session, name)
        assert shape["security_definer"] is True, (
            f"`public.{name}` is not `SECURITY DEFINER` — the catalog reports "
            f"{shape['security_definer']!r} for `prosecdef`, and its signature is "
            f"{shape['signature']}. The ruling on `docs/disputes/E5-03-01.md` makes these two "
            "definers on purpose: 'a plain grant *cannot* do this — any grant wide enough to let "
            "the application count distinct respondents across an arbitrary section set is a grant "
            "on person-keyed rows, which is the thing being refused'. A `SECURITY INVOKER` "
            "function answers with the caller's own reach and buys none of that."
        )
        assert shape["owner"] != APPLICATION_ROLE, (
            f"`public.{name}` is owned by `{shape['owner']}`, which is the application role "
            "itself. A definer owned by its own caller runs with exactly the caller's privileges "
            "and is a `SECURITY DEFINER` in name only.\n\n"
            "**Which role owns these two is not settled anywhere**, and this assertion is "
            "deliberately the weakest true thing rather than a name this test invented. If the "
            "implementation adds a new NOLOGIN owner, `IDENTITY_DEFINER_ROLES` in "
            "tests/integration/test_identity_grants.py is a closed set that has to gain it with "
            "the sentence that admits it, and "
            "`test_no_role_outside_this_scheme_is_granted_anything_in_public` is the test that "
            "will say so. Reusing an existing definer owner is the other answer, and it is a "
            "different one: `pulse_resolve_definer` holds column grants on `user` and `person`, "
            "which is a wider surface than these two functions need and would widen what an "
            "`EXECUTE` on them could reach if a body ever changed."
        )


@pytest.mark.invariant
def test_the_person_keyed_benchmark_view_the_dispute_withdrew_is_not_readable(
    application_engine: Any,
) -> None:
    """The withdrawn deliverable, asserted as a refusal rather than as an absence.

    The work order for this ticket instructed a view
    `benchmark_respondent_week_v001` "exposing (section_id, course_week, stream,
    user_id) response keys — an identity-CARRYING view … granted SELECT". The
    ruling on `docs/disputes/E5-03-01.md` withdrew it: "no view keyed to a
    student crosses a grant to `pulse_app` in this ticket or any other".

    A written instruction to build something is the strongest reason to check it
    was not built. This is the one relation in this ticket whose name is already
    written down in a work order, and a later reader finding that sentence
    without the ruling beside it would build it.

    **The read is required to be refused, not merely empty.** An empty result is
    what an unpopulated view returns, what a view over an empty world returns,
    and what a mis-typed relation name returns from a `to_regclass` check — so
    this drives the read as `pulse_app` and requires the driver to raise, with
    an undefined relation (`42P01`) and a denied privilege (`42501`) both
    counting as the refusal. Rows coming back is the failure whatever they hold.

    **The control is `current_user`**, so a fixture handing back a superuser
    connection cannot satisfy this by refusing for the wrong reason — or, worse,
    by reading it successfully and being counted as a refusal because something
    else raised.
    """
    with application_engine.connect() as connection:
        role = connection.execute(text("SELECT current_user")).scalar_one()
        assert role == APPLICATION_ROLE, (
            f"This connection reports itself as {role!r} rather than as {APPLICATION_ROLE!r}, so a "
            "refusal below would be a statement about the wrong role."
        )

        refused: DatabaseError | None = None
        rows: list[Any] = []
        try:
            rows = list(connection.execute(text(f"SELECT * FROM public.{WITHDRAWN_VIEW}")))  # noqa: S608
        except DatabaseError as failure:
            refused = failure
        connection.rollback()

    assert refused is not None, (
        f"`{APPLICATION_ROLE}` read `public.{WITHDRAWN_VIEW}` and got {len(rows)} rows back. That "
        "relation is the person-keyed view this ticket's work order asked for and the ruling on "
        "`docs/disputes/E5-03-01.md` withdrew, on E5-03's own 'section id and numbers, never a "
        "person' and on SPEC §8's 'enforced in the database, not just the application'. It spans "
        "every section of a cohort across terms and keys each row to a student, which is a "
        "de-anonymization primitive rather than a join key. The figures it was meant to feed are "
        f"`{SET_FUNCTION}` and `{SET_RATING_FUNCTION}`, which compute them where the person rows "
        "live and return numbers."
    )
    state = getattr(getattr(refused, "orig", None), "sqlstate", None)
    assert state in (UNDEFINED_RELATION, INSUFFICIENT_PRIVILEGE, None), (
        f"Reading `public.{WITHDRAWN_VIEW}` as `{APPLICATION_ROLE}` failed with SQLSTATE {state!r}: "
        f"{refused}. A refusal is what this test wants, but not any refusal: `42P01` is the "
        "relation not existing and `42501` is the grant withheld, and anything else means the "
        "statement failed for a reason that says nothing about either."
    )


def test_the_two_set_functions_are_the_two_this_ticket_ships(db_session: Any) -> None:
    """The inventory, so a third function is a decision and a missing one is not a silent skip.

    Every other test here iterates `BENCHMARK_FUNCTIONS`, so deleting an entry
    deletes its own cases and the suite passes at the smaller size. This names
    both outright.

    A third definer arriving in this ticket's name would also be a seventh entry
    in `SANCTIONED_APPLICATION_EXECUTE`, whose comment says what that means: "a
    new door into identity that some later ticket opened without arguing for
    it". Two is what the ruling admits and two is what the sentence in that
    constant covers.
    """
    for name in (SET_FUNCTION, SET_RATING_FUNCTION):
        assert function_shape(db_session, name), (
            f"There is no function `public.{name}`. E5-03 ships two, from "
            f"`backend/app/views_sql/{name}_v001.sql` and its sibling, created by this ticket's "
            "migration: the workload-and-counts figures over a section set, and the per-stream "
            "rating figures over the same set."
        )
