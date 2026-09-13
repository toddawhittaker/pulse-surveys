"""E4-03 criterion 1, and the row contract the payload layer is built on.

Two questions, both about the *shape* of the three report views rather than about
any number in them:

  - **What each view returns**, asserted as an equality against a set written
    down in `tests/fixtures/report_views.py`. The criterion asks for exactly
    this — "a test asserts the view's column list against an expected set — a
    widened view is a red test, not a quiet diff" — because every column one of
    these views returns is a column an instructor reads, and a column that
    arrives without a decision is the whole failure §4.1 exists to prevent.
  - **Whether a week nobody answered has a row.** The work order settles it:
    absence, not zeros. "Zero-filling is the payload layer's (one place)", and
    E4-07 is where a week the chart needs is given back to it. Asserting it here
    pins the contract that layer is written against, in the direction that would
    otherwise be discovered by a chart drawing a zero somebody meant as a gap.

**The identity half of criterion 1 is asserted next door and needs nothing
here.** `tests/integration/test_identity_column_marker.py` discovers every view
in `public` out of the catalog and holds all of them to the marked-column rule,
the whole-row rule and the person-table join-key rule; `test_identity_separated_
views.py` sweeps the `views_sql/` files for the same thing. Three new views are
covered by those the moment the migration creates them, so a fourth copy of that
sweep here would be `docs/MISTAKES.md` entry 13 rather than coverage. What is
*not* automatic is the equality above and the grant enumeration in
`test_identity_grants.py`'s `SANCTIONED_VIEW_COLUMNS`, which this ticket's three
entries were added to.

**The mutations these are written to survive.** For the column equality: a fourth
column added to any of the three views in its `views_sql/` file — `user_id`
carried along "so the payload can join", a `submitted_at`, a comment count — and
a column removed from one, which is the same test failing from the other side.
For the empty-week rule: a `LEFT JOIN` from `survey_window` or from `week` that
emits a row per week the section runs rather than per week it has answers for,
which is the shape that produces zeros nobody asked for.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.report_views import (
    RATING_DISTRIBUTION_VIEW,
    REPORT_VIEWS,
    RESPONSE_COUNTS_VIEW,
    WORKLOAD_VIEW,
    ReportWorld,
    report_view_columns,
    require_report_view,
)

pytestmark = pytest.mark.integration

# The term weeks this module answers and leaves empty. Cohort `F` runs term weeks
# 7 to 12, so both are weeks the section really has — an unanswered week rather
# than a week outside the section's calendar, which is a different absence with a
# different cause.
ANSWERED_WEEK = 7
UNANSWERED_WEEK = 9

# One ordinary submission: both ratings, both comments and the workload figure.
# The values are this test's and are read back by nothing here; what they are for
# is that all three views have something to return for the answered week, so the
# absence asserted below is about the *unanswered* one.
A_WHOLE_SUBMISSION = {
    1: Decimal("4"),
    2: "the pacing in week 3 was too fast and the reading load doubled",
    3: Decimal("5"),
    4: "the reading list was well chosen and the workload was steady",
    5: Decimal("6.5"),
}


@pytest.mark.invariant
@pytest.mark.parametrize("view", sorted(REPORT_VIEWS), ids=sorted(REPORT_VIEWS))
def test_each_report_view_returns_exactly_the_columns_its_contract_names(
    db_session: Any, view: str
) -> None:
    """Criterion 1: the column list is an equality, so a widening is a decision.

    A view is read with its **owner's** privileges, so what one of these returns
    is what the application connection may put on an instructor's page whatever
    the grants on the tables underneath say. There is no other rule in this
    repository that would notice a column arriving here: `alembic check` reads no
    `pg_class` entry for a view at all, the marked-column sweeps ask what a view
    *reads* rather than what it *returns*, and the grant rules are about
    relations.

    **The non-vacuity guard is the view's own existence**, and it is the first
    thing checked rather than a niceness: an absent view returns an empty column
    list, and "no column beyond the expected set" is perfectly true of nothing at
    all (`docs/MISTAKES.md` entry 3). `require_report_view` fails naming the file
    the migration should have executed.

    **The mutation it exists to survive**: a column added to one of the three
    views — the shape that arrives is a key "for the payload to join on" — and a
    column dropped by a `_v002.sql`, which fails the same equality from the other
    side.
    **The near miss it tolerates**: a column *reordered*, which is a set
    comparison and not a sequence one, because nothing in this ticket promises an
    order and a payload reads by name.
    """
    require_report_view(db_session, view)

    expected = set(REPORT_VIEWS[view])
    present = set(report_view_columns(db_session, view))

    surplus = sorted(present - expected)
    absent = sorted(expected - present)
    agrees = not surplus and not absent
    assert agrees, (
        f"`public.{view}` returns {sorted(present)}. E4-03 settles it as {sorted(expected)}.\n\n"
        f"Returned and not in the contract: {surplus}. In the contract and not returned: {absent}."
        "\n\nThe first list is the one to read first: every column one of these views returns is a "
        "column an instructor's connection may read, and E4-03's first criterion makes a widened "
        "view a red test rather than a quiet diff. If the column is genuinely needed, it is a "
        "decision — `REPORT_VIEWS` in tests/fixtures/report_views.py records it with the sentence "
        "that admits it, `SANCTIONED_VIEW_COLUMNS` in tests/integration/test_identity_grants.py "
        "records the grant, and the pull request says which surface needs it. The second list "
        "means a column the report reads is not there, which shuts a read path rather than opening "
        "one."
    )


@pytest.mark.parametrize("view", sorted(REPORT_VIEWS), ids=sorted(REPORT_VIEWS))
def test_a_week_nobody_answered_has_no_row_in_any_report_view(
    report_world: ReportWorld, view: str
) -> None:
    """Absence, not zeros — the contract E4-07's payload layer is written against.

    The ticket's own "Decisions this ticket settles" asked whether the trend
    should expose a row for a zero-response week, and the work order settles it
    the other way: these views return only weeks that have rows, and the payload
    layer zero-fills in one place. Both halves are asserted here, because the
    absence on its own is satisfied by a view that returns nothing ever
    (`docs/MISTAKES.md` entry 3): the answered week is required to have at least
    one row first, in the same test, so the two readings cannot be confused.

    **The mutation it exists to survive**: a `LEFT JOIN` from `week` or from
    `survey_window` that emits a row per week the section runs. That view is
    plausible, renders as a chart with a zero in it, and says something about a
    section that no student said.
    """
    world = report_world.build()
    student = world.student("e4-03-one-answered-week")
    world.respond(student, term_week=ANSWERED_WEEK, answers=A_WHOLE_SUBMISSION)

    answered = world.rows(view, term_week=ANSWERED_WEEK)
    assert answered, (
        f"`public.{view}` has no row for the section-week that was answered, so the absence "
        "asserted below would be equally true of a view that returns nothing at all. One student "
        f"submitted both ratings, both comments and a workload figure in term week {ANSWERED_WEEK}."
    )

    empty = world.rows(view, term_week=UNANSWERED_WEEK)
    assert empty == [], (
        f"`public.{view}` returns {empty} for term week {UNANSWERED_WEEK}, which the section runs "
        "and in which nobody submitted anything. E4-03's work order settles this as absence rather "
        "than a zero row: the enrolled denominator, the rates and the zero-filling the chart needs "
        "all live at E4-07's payload layer, in one place, and a view that emitted a zero week here "
        "would make that layer's job ambiguous — a stored zero and a missing week would arrive "
        "looking the same. A `LEFT JOIN` from `week` or `survey_window` is the usual way this "
        "happens."
    )


def test_the_three_views_the_report_reads_are_the_three_this_ticket_ships(db_session: Any) -> None:
    """The set of views, so a fourth is a decision and a missing one is not a silent skip.

    The parametrised tests above are written over `REPORT_VIEWS`, so deleting an
    entry from that constant deletes its own cases and the suite passes at the
    smaller size — the shape `test_identity_grants.py`'s controls carry a comment
    about, and the reason this one names the three outright rather than iterating
    the constant.

    It is not an inventory of every view in `public`: `test_identity_separated_
    views.py` compares the whole catalog against the `views_sql/` files, and this
    one asks only that E4-03's three exist under the names its work order settles.
    """
    for view in (RATING_DISTRIBUTION_VIEW, WORKLOAD_VIEW, RESPONSE_COUNTS_VIEW):
        assert report_view_columns(db_session, view), (
            f"There is no view `public.{view}`. E4-03 ships three, from "
            f"`backend/app/views_sql/{view}_v001.sql` and its two siblings, created by that "
            "ticket's migration: the per-stream rating distribution, the workload mean and median, "
            "and the response and valid-response counts. Each is keyed by `(section_id, week_id)`."
        )
