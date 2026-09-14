"""E5-03 criterion 1 — the shape of the four benchmark views, and what is absent from it.

Three questions, none of them about a number:

  - **What each view returns**, asserted as an equality against the set the
    ruling on `docs/disputes/E5-03-01.md` settles. The criterion asks for
    exactly this: "a test asserts each view's column list against an expected
    set". Every column one of these views returns is a column the application
    connection may put in front of an instructor, and a column that arrives
    without a decision is the whole failure §4.1 exists to prevent.
  - **That none of them names a person.** This is the half the dispute was
    about. The work order asked for a fifth view keyed `(section_id,
    course_week, stream, user_id)`; the ruling withdrew it, on the ticket's own
    "section id and numbers, never a person" and on §8's *structural*
    separation. These four are what remain, and a person key arriving on one of
    them later is the same defect wearing this ticket's name.
  - **What a cohort week has a row for**, which is three states rather than two
    and the third was ruled after this suite's first red run:

    | the week | the row |
    |---|---|
    | nobody answered | no row — absence, not zeros |
    | answered, no workload figures | a row, with its counts and **null** workload figures |
    | answered with hours | a row, with figures |

    The first is the contract E5-04's service is written against, and the
    direction that would otherwise be discovered by a chart drawing a zero
    somebody meant as a gap. The third row of that table is the one that
    departs from E4-03's `report_workload`, and
    `test_a_cohort_week_answered_without_workload_still_has_a_row_with_its_counts`
    carries the reasoning: this view holds three counts beside the two figures,
    so the row has to exist to carry them.

**The identity sweeps next door need nothing added here.**
`tests/integration/test_identity_column_marker.py` discovers every view in
`public` out of the catalog and holds all of them to the marked-column rule, the
whole-row rule and the person-table join-key rule, and
`test_identity_separated_views.py` sweeps the `views_sql/` files for the same
thing. Four new views are covered by those the moment the migration creates
them. What is *not* automatic is the equality below and the grant enumeration in
`test_identity_grants.py`'s `SANCTIONED_VIEW_COLUMNS`, which this ticket's four
entries were added to.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.benchmark_views import (
    BENCHMARK_VIEWS,
    COHORT_RATING_WEEK_VIEW,
    COHORT_WEEK_VIEW,
    COURSE_WEEK_VIEWS,
    UG,
    BenchmarkWorld,
    benchmark_view_columns,
    require_benchmark_view,
)

pytestmark = pytest.mark.integration

# Every spelling this schema has for a person, and the whole of the list. Read
# as substrings of a column name, so `respondent_user_id` and `member_person_id`
# are caught as well as the bare keys.
#
# **`respondent_count` is deliberately not one of them**, and the near miss is
# the point: a *count* of people is a number, and it is the number the ruling
# requires these views to carry. The rule is about a column that names one
# person, which is what makes a cohort row joinable back to a student.
#
# Written out rather than imported from `test_identity_column_marker.py`'s
# vocabulary, for the reason that module's own comment gives about its three
# copies: a test module importing a sibling test module resolves only because of
# where pytest puts `tests/` on `sys.path`. These are keys rather than identity
# names, so they are a different list in any case — the identity vocabulary
# never saw `user_id`, which is exactly why E1-01 wrote `JOIN_KEY_COLUMNS`.
PERSON_KEY_FRAGMENTS = ("user_id", "person_id", "respondent_id", "student_id", "lms_user")

# The cohort this module's world plants: one 12-week undergraduate section,
# answering in its second course week and nothing else.
THE_COHORT_LENGTH = 12
THE_COURSE_WEEK = 2
AN_UNANSWERED_COURSE_WEEK = 4
A_WORKLOAD = Decimal("3.5")
A_RATING = Decimal("4")

# The third state, ruled after the first red run: a course week whose responses
# carry ratings and no workload answer. Two respondents in one week and one in
# another, so the week with no hours has counts worth carrying and the week with
# hours is the contrast that makes a null mean mean something.
RATING_ONLY_COURSE_WEEK = 3
RATING_ONLY_RESPONDENTS = 2
A_LATER_WORKLOAD = Decimal("4.0")


@pytest.mark.invariant
@pytest.mark.parametrize("view", sorted(BENCHMARK_VIEWS), ids=sorted(BENCHMARK_VIEWS))
def test_each_benchmark_view_returns_exactly_the_columns_its_contract_names(
    db_session: Any, view: str
) -> None:
    """Criterion 1: the column list is an equality, so a widening is a decision.

    A view is read with its **owner's** privileges, so what one of these returns
    is what the application connection may put on a page whatever the grants on
    the tables underneath say. Nothing else in this repository would notice a
    column arriving here: `alembic check` reads no `pg_class` entry for a view,
    the marked-column sweeps ask what a view *reads* rather than what it
    *returns*, and the grant rules are about relations.

    **The non-vacuity guard is the view's own existence**, checked first rather
    than as a niceness: an absent view returns an empty column list, and "no
    column beyond the expected set" is perfectly true of nothing at all
    (`docs/MISTAKES.md` entry 3). `require_benchmark_view` fails naming the file
    the migration should have executed.

    **The mutation it exists to survive**: a column added to one of the four —
    the shape that arrives is a `section_id` or a `user_id` "so the service can
    join" — and a column dropped by a `_v002.sql`, which fails the same equality
    from the other side.
    **The near miss it tolerates**: a column *reordered*. The ruling gives an
    order and this compares sets, because nothing in the ticket promises an
    order and a caller reads by name; a reordering that mattered would be caught
    by the figures, not by this.
    """
    require_benchmark_view(db_session, view)

    expected = set(BENCHMARK_VIEWS[view])
    present = set(benchmark_view_columns(db_session, view))

    surplus = sorted(present - expected)
    absent = sorted(expected - present)
    assert not surplus and not absent, (
        f"`public.{view}` returns {sorted(present)}. The ruling on "
        f"`docs/disputes/E5-03-01.md` settles it as {sorted(expected)}.\n\n"
        f"Returned and not in the contract: {surplus}. In the contract and not returned: "
        f"{absent}.\n\nThe first list is the one to read first: every column one of these views "
        "returns is a column `pulse_app` may read, and criterion 1 makes a widened view a red "
        "test rather than a quiet diff. If the column is genuinely needed it is a decision — "
        "`BENCHMARK_VIEWS` in tests/fixtures/benchmark_views.py records it with the sentence that "
        "admits it, `SANCTIONED_VIEW_COLUMNS` in tests/integration/test_identity_grants.py records "
        "the grant, and the pull request says which surface needs it. The second list means a "
        "column E5-04 reads is not there, which shuts a read path rather than opening one."
    )


@pytest.mark.invariant
@pytest.mark.parametrize("view", sorted(BENCHMARK_VIEWS), ids=sorted(BENCHMARK_VIEWS))
def test_no_benchmark_view_names_a_person_in_any_currency(db_session: Any, view: str) -> None:
    """The dispute's outcome, asserted where it can be broken.

    The ticket's scope allows this ticket's building block "section id and
    numbers, never a person", and the ruling on `docs/disputes/E5-03-01.md`
    withdrew the view that would have carried `user_id`: "no view keyed to a
    student crosses a grant to `pulse_app` in this ticket or any other". A
    cohort row spanning every section of a length and level, in the current and
    every retained prior term, is the widest read in the system — a person key
    on one of them is a de-anonymization primitive rather than a join key.

    **This is asserted over the catalog and not over the contract constant.**
    Comparing `BENCHMARK_VIEWS` against itself would pass for as long as nobody
    edited the constant, and the constant is in the same pull request as the
    view. The columns come out of `pg_attribute`.

    **The non-vacuity guard is the view's existence and its contract columns**,
    both checked by `require_benchmark_view` before the sweep: "no person key
    here" is true of a view that returns nothing (`docs/MISTAKES.md` entry 3).

    **The mutation it exists to survive**: `user_id` added to a cohort view, and
    the withdrawn `benchmark_respondent_week` re-introduced under a new name
    with its person key intact. **The near miss it tolerates**:
    `respondent_count`, a count of people rather than a person, which every one
    of these views is required to carry.
    """
    require_benchmark_view(db_session, view)

    present = benchmark_view_columns(db_session, view)
    named = sorted(
        column
        for column in present
        if any(fragment in column.lower() for fragment in PERSON_KEY_FRAGMENTS)
    )
    assert not named, (
        f"`public.{view}` returns {named}, which names a person. It returns {list(present)}.\n\n"
        "E5-03's scope allows this ticket's building block 'section id and numbers, never a "
        "person', and the ruling on `docs/disputes/E5-03-01.md` withdrew the person-keyed view the "
        "work order asked for on exactly that sentence and on SPEC §8's 'enforced in the database, "
        "not just the application'. A distinct-respondent figure is computed inside the view with "
        "`COUNT(DISTINCT ...)` and leaves it as a number; the key it counts over never does. If a "
        "caller needs figures over an arbitrary section set, that is what "
        "`benchmark_set_week` and `benchmark_set_rating_week` exist for."
    )


def test_the_four_benchmark_views_are_the_four_this_ticket_ships(db_session: Any) -> None:
    """All four named views exist — an existence check, and deliberately nothing more.

    The parametrised tests above are written over `BENCHMARK_VIEWS`, so deleting
    an entry from that constant deletes its own cases and the module passes at
    the smaller size — the shape `test_identity_grants.py`'s controls carry a
    comment about, and the reason this one names the four outright rather than
    iterating the constant.

    **It does not catch a fifth view, and an earlier version of this docstring
    claimed it did.** The mutation battery planted one and this file stayed
    green, correctly: the body asks whether four names are present, and a fifth
    name is not a thing it looks at. Nothing in this module is a closed set.

    **The closed set lives in `tests/integration/test_identity_grants.py`**, in
    `SANCTIONED_VIEW_COLUMNS`, read as a two-directional equality by
    `test_the_columns_the_application_role_may_read_from_a_view_are_exactly_the_enumerated_set`
    — `invariant`-marked, and red on a fifth *granted* view as well as on a
    column added to any of these four. That is where a new view's admitting
    sentence has to be written. `test_identity_separated_views.py` owns the
    other half of the inventory question, comparing the whole catalog against
    the `views_sql/` files. This test and those two are separate facts: "the
    deliverables are here" and "nothing else is", and a module that tried to own
    both would own neither well.

    **The mutation it exists to survive**: three views shipped instead of four —
    the rating pair folded into the workload pair, or the term axis dropped as
    "nothing renders it in E5" (breakdown decision 7 says it is proven by test
    here precisely so E9 consumes a proven read).
    """
    for view in sorted(BENCHMARK_VIEWS):
        assert benchmark_view_columns(db_session, view), (
            f"There is no view `public.{view}`. E5-03 ships four, from "
            f"`backend/app/views_sql/{view}_v001.sql` and its three siblings, created by that "
            "ticket's migration: a rating pair and a workload-and-counts pair, on the course-week "
            "axis and on §2.2's term axis. The ruling on `docs/disputes/E5-03-01.md` settles all "
            "four names and column lists."
        )


@pytest.mark.parametrize("view", sorted(COURSE_WEEK_VIEWS), ids=sorted(COURSE_WEEK_VIEWS))
def test_a_cohort_week_nobody_answered_has_no_row(
    benchmark_world: BenchmarkWorld, view: str
) -> None:
    """Absence, not zeros — the contract E5-04 is written against.

    One section answers in its second course week and in no other. The fourth
    course week, which the section runs, has no row at all: no zero mean, no
    null row, no fabricated respondent count.

    **Both halves are asserted here**, because the absence on its own is
    satisfied by a view that returns nothing ever (`docs/MISTAKES.md` entry 3):
    the answered week is required to have at least one row first, in the same
    test, so the two readings cannot be confused.

    **The mutation it exists to survive**: a `LEFT JOIN` from `week` or from
    `survey_window` that emits a row per week each section runs. That view is
    plausible, renders as a chart with a zero in it, and says something about a
    cohort that no student said — and at E5-04 a zero-respondent row is a row
    that fails the minimum for a reason nobody can see.
    """
    world = benchmark_world.build()
    world.plant_section("hero", cohort="U", level=UG)
    world.respond(
        "hero",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-absence",
        workload=A_WORKLOAD,
        instructor_rating=A_RATING,
        course_rating=A_RATING,
    )

    answered = world.rows(
        view,
        length_weeks=THE_COHORT_LENGTH,
        level=UG,
        term_id=world.term_id(),
        course_week=THE_COURSE_WEEK,
    )
    assert answered, (
        f"`public.{view}` has no row for the cohort week that was answered, so the absence "
        "asserted below would be equally true of a view that returns nothing at all. One student "
        f"submitted both ratings and a workload figure in course week {THE_COURSE_WEEK} of a "
        f"{THE_COHORT_LENGTH}-week {UG} section."
    )

    empty = world.rows(
        view,
        length_weeks=THE_COHORT_LENGTH,
        level=UG,
        term_id=world.term_id(),
        course_week=AN_UNANSWERED_COURSE_WEEK,
    )
    assert empty == [], (
        f"`public.{view}` returns {empty} for course week {AN_UNANSWERED_COURSE_WEEK}, which the "
        "section runs and in which nobody submitted anything. These views return what was "
        "answered; the zero-filling a chart needs is the payload layer's, in one place, and a view "
        "that emitted a zero week here would make E5-04's job ambiguous — a cohort of nobody and a "
        "week nobody answered would arrive looking the same, and one of them suppresses for a "
        "reason the other does not."
    )


def a_week_answered_without_hours(world: BenchmarkWorld) -> BenchmarkWorld:
    """One section: a course week of ratings and no workload, and a later week with hours.

    The third state of a cohort week, beside "nobody answered" above and "a
    figure was submitted" everywhere else. Both weeks are in one world so the
    null and the number are read off the same view in the same test.
    """
    world.build()
    world.plant_section("hero", cohort="U", level=UG)
    for index in range(RATING_ONLY_RESPONDENTS):
        world.respond(
            "hero",
            course_week=RATING_ONLY_COURSE_WEEK,
            subject=f"e5-03-no-hours-{index}",
            instructor_rating=A_RATING,
            course_rating=A_RATING,
        )
    world.respond(
        "hero",
        course_week=THE_COURSE_WEEK,
        subject="e5-03-with-hours",
        workload=A_LATER_WORKLOAD,
        instructor_rating=A_RATING,
    )
    return world


def test_a_cohort_week_answered_without_workload_still_has_a_row_with_its_counts(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The third state, ruled after the first red run: the week exists, so the row does.

    Two students answered both ratings in this course week and neither submitted
    a workload figure. The row is there, carrying the counts that are real —
    two responses, two respondents, one section — because those are facts about
    the week whatever the hours column holds. A gap in one figure is not a gap
    in the week.

    **This is a departure from E4-03's shape and should be recorded as one**, not
    as following it. `report_workload` has no row for a section-week whose
    responses carry no hours, and that is right there: every column of that view
    is a workload figure, so a row with nulls would be a week that looks answered
    and is not. The cohort view is a different shape — it carries
    `response_count`, `respondent_count` and `section_count` beside the two
    workload figures — so withholding the row would withhold three true counts to
    avoid publishing two absent ones, and E5-04 would read a week that had data
    as a week that had none. ADR 0165 is where that reasoning belongs, and citing
    E4-03 as the precedent for it would be citing a rule for its opposite.

    **The non-vacuity guard is the rating view**, taken first: if the two
    responses had not reached the views at all, "the row exists" would be the
    only thing this test could fail on and it would fail for the wrong reason.

    **The mutation it exists to survive**: the cohort row derived from the
    workload answers — an inner join to the hours, or a `FROM answer WHERE
    question is the workload one` — which drops the whole week, counts and all,
    the moment nobody reports hours. That view answers every other test in this
    ticket correctly.
    """
    world = a_week_answered_without_hours(benchmark_world)

    ratings = world.rows(
        COHORT_RATING_WEEK_VIEW,
        length_weeks=THE_COHORT_LENGTH,
        level=UG,
        term_id=world.term_id(),
        course_week=RATING_ONLY_COURSE_WEEK,
    )
    assert ratings, (
        f"`{COHORT_RATING_WEEK_VIEW}` has no row for course week {RATING_ONLY_COURSE_WEEK}, in "
        f"which {RATING_ONLY_RESPONDENTS} students submitted both ratings. The responses have not "
        "reached the views at all, so the assertion below would be about an empty world rather "
        "than about a week with no hours in it."
    )

    row = world.cohort_week(
        length_weeks=THE_COHORT_LENGTH, level=UG, course_week=RATING_ONLY_COURSE_WEEK
    )
    assert row is not None, (
        f"`{COHORT_WEEK_VIEW}` has no row for course week {RATING_ONLY_COURSE_WEEK}, in which "
        f"{RATING_ONLY_RESPONDENTS} students responded and none reported hours. The week exists "
        "and its counts are real; the ruling of this round is that the row exists with null "
        "workload figures rather than being withheld. A view built from the workload answers "
        "drops the week entirely, and E5-04 then reads a week that had data as a week that had "
        "none."
    )
    assert row["response_count"] == RATING_ONLY_RESPONDENTS, (
        f"`response_count` is {row['response_count']!r} where {RATING_ONLY_RESPONDENTS} responses "
        f"were submitted in course week {RATING_ONLY_COURSE_WEEK}. The row is {row}."
    )
    assert row["respondent_count"] == RATING_ONLY_RESPONDENTS, (
        f"`respondent_count` is {row['respondent_count']!r} where {RATING_ONLY_RESPONDENTS} "
        "different students responded. A count of people is what E5-04's minimum is compared "
        "against, and it does not depend on whether they answered the workload question."
    )
    assert (
        row["section_count"] == 1
    ), f"`section_count` is {row['section_count']!r} where one section answered this cohort week."


def test_the_workload_figures_of_a_week_with_no_hours_are_null_rather_than_zero(
    benchmark_world: BenchmarkWorld,
) -> None:
    """The other half: an absent figure is null, and null is not nought.

    Nobody reported hours in this course week, so there is no mean and no median
    to report. A zero would be a statement about the cohort that no student
    made — "these students spent no time on the course" — and it would travel:
    E5-05 renders the workload comparison beside a section's own figure, so a
    fabricated 0.0 becomes a benchmark an instructor is measured against.

    **The contrast week is the discriminator**, and without it this assertion is
    satisfied by a view whose workload columns are null for everybody. The same
    world's other course week has one submitted figure and must report it.

    **The mutation it exists to survive**: `coalesce(avg(...), 0)` and
    `coalesce(percentile_cont(...), 0)` — the shape somebody writes to keep a
    numeric column non-null, which is exactly the wrong instinct here. Also
    `avg(coalesce(hours, 0))`, which is worse and harder to see: it counts every
    response as zero hours, so a week where one of five students reported four
    hours reads as 0.8 rather than 4.0.
    """
    world = a_week_answered_without_hours(benchmark_world)

    row = world.cohort_week(
        length_weeks=THE_COHORT_LENGTH, level=UG, course_week=RATING_ONLY_COURSE_WEEK
    )
    assert row is not None, (
        f"`{COHORT_WEEK_VIEW}` has no row for course week {RATING_ONLY_COURSE_WEEK}; the test "
        "above is where that is diagnosed."
    )

    with_hours = world.cohort_week(
        length_weeks=THE_COHORT_LENGTH, level=UG, course_week=THE_COURSE_WEEK
    )
    assert with_hours is not None and with_hours["workload_mean"] == A_LATER_WORKLOAD, (
        f"The cohort week that *does* carry hours reads {with_hours}, where one student submitted "
        f"{A_LATER_WORKLOAD}. Until this row is right, a null in the other week says nothing — a "
        "view whose workload columns are null for every week would satisfy the assertion below "
        "perfectly (`docs/MISTAKES.md` entry 3)."
    )

    nulls = {
        figure: row[figure]
        for figure in ("workload_mean", "workload_median")
        if row[figure] is not None
    }
    assert not nulls, (
        f"{nulls} are reported for a cohort week in which nobody submitted a workload figure. "
        f"The whole row is {row}.\n\n"
        "A zero is the answer to look for and the one that must not be here: it is a statement "
        "about how long these students worked, made by nobody, and E5-05 renders the comparison "
        "workload figure beside the section's own — so it arrives on an instructor's page as a "
        "benchmark. `coalesce(avg(...), 0)` is how it gets there. Null is the honest answer, and "
        f"the counts on this same row ({row['respondent_count']!r} respondents) are what tell "
        "E5-04 that the week had data and this particular figure did not."
    )


def test_the_workload_and_counts_view_returns_one_row_for_one_cohort_week(
    benchmark_world: BenchmarkWorld,
) -> None:
    """One row per key, which is what makes every figure below readable as a number.

    Two sections of one cohort answer in the same course week. The
    workload-and-counts view is keyed by `(length_weeks, level, term_id,
    course_week)` and carries no stream, so that is **one** row — and a suite
    that read `rows[0]` of two would assert against half a cohort and pass.

    **The mutation it exists to survive**: `section_id` or `stream` left in the
    `GROUP BY` of the workload view, which produces a row per section or per
    stream carrying figures that look right in isolation. `one_benchmark_row`
    fails rather than indexing, so the defect names itself.
    """
    world = benchmark_world.build()
    world.plant_section("one", cohort="U", level=UG)
    world.plant_section("two", cohort="U", level=UG)
    for label in ("one", "two"):
        world.respond(
            label,
            course_week=THE_COURSE_WEEK,
            subject=f"e5-03-one-row-{label}",
            workload=A_WORKLOAD,
            instructor_rating=A_RATING,
            course_rating=A_RATING,
        )

    rows = world.rows(
        COHORT_WEEK_VIEW,
        length_weeks=THE_COHORT_LENGTH,
        level=UG,
        term_id=world.term_id(),
        course_week=THE_COURSE_WEEK,
    )
    assert len(rows) == 1, (
        f"`{COHORT_WEEK_VIEW}` returns {len(rows)} rows for one cohort week: {rows}. The ruling on "
        "`docs/disputes/E5-03-01.md` keys it by `(length_weeks, level, term_id, course_week)` and "
        "puts `stream` only on the rating pair, so two sections of one cohort answering in one "
        "course week are one row carrying one workload mean, one median and three counts."
    )
