"""The one view this path selects comment text through — ticket E4-04.

E4-04's work order ships `backend/app/views_sql/report_comment_v001.sql`,
returning `(section_id, week_id, stream, answer_id, comment_text)` over the
comment-kind answers that carry text. Two questions about it, and neither is
answered by anything already in the suite:

  - **What it returns**, as an equality against the contract. Every column a view
    an instructor's connection can read returns is a column an instructor can be
    shown, and SPEC §4.1 forbids identity in any of them. `alembic check` reads no
    `pg_class` entry for a view at all, and the marked-column sweeps ask what a
    view *reads* rather than what it *returns* — so a column arriving here is
    caught by this and by `SANCTIONED_VIEW_COLUMNS` in
    `tests/integration/test_identity_grants.py`, and by nothing else.
  - **What rows it holds.** "Comment-kind answers with non-empty text only" is a
    filter, and a view without it hands the read path a rating, a workload figure
    and a NULL for every question nobody answered — which the read path would then
    render as blank comment cards on an instructor's report.

**The identity half needs nothing here.**
`tests/integration/test_identity_column_marker.py` discovers every view in
`public` out of the catalog and holds all of them to the marked-column rule, the
whole-row rule and the person-table join-key rule, and
`test_identity_separated_views.py` sweeps the `views_sql/` files for the same
thing. A fourth copy would be `docs/MISTAKES.md` entry 13 rather than coverage.

**Which failure a red is, before E4-04 lands.** Every test here stops in its own
body on `require_comment_view`, which names the file the migration should have
executed — a FAILED assertion rather than an `UndefinedTable` raised inside a
fixture (`docs/MISTAKES.md` entry 44).
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.report_comments import (
    COMMENT_VIEW,
    COMMENT_VIEW_COLUMNS,
    CommentWorld,
    require_comment_view,
)

pytestmark = pytest.mark.integration

THE_WEEK = 7

# One submission that answers everything: a rating in each stream, a comment in
# each stream, and the workload figure. The view must return the two comments and
# neither of the ratings nor the workload.
AN_INSTRUCTOR_COMMENT = "the explanations in the Tuesday lecture were the clearest part of the term"
A_COURSE_COMMENT = "the recommended textbook was never actually used in any assessed exercise"
A_RATING = Decimal("4")
THE_OTHER_RATING_POSITION = 3


@pytest.mark.invariant
def test_the_report_comment_view_returns_exactly_the_columns_its_contract_names(
    db_session: Any,
) -> None:
    """The column list is an equality, so a widening is a decision rather than a diff.

    A view is read with its **owner's** privileges, so what this one returns is
    what the application connection may put in front of an instructor whatever the
    grants on `answer` and `response` underneath say. SPEC §4 keys responses to
    the LMS user id and §4.1 forbids identity in any instructor-visible view; a
    `user_id` or a `response_id` carried here "so the payload can join" is one hop
    from a person, and a `submitted_at` is the timestamp §4 says is never shown
    with a comment.

    **The non-vacuity guard is the view's own existence**, checked first: an
    absent view returns an empty column list, and "no column beyond the expected
    set" is perfectly true of nothing at all (`docs/MISTAKES.md` entry 3).

    **Marked `invariant`** because the equality is a §4.1 assertion about what an
    instructor's connection can select, in the same currency
    `test_the_report_views_return_the_columns_the_report_reads.py` marks E4-03's
    three.

    **The mutation it kills:** a sixth column added to the view file — `user_id`,
    `response_id`, `submitted_at`, `created_at` — and a column dropped by a
    `_v002.sql`, which fails the same equality from the other side.
    **The near miss it tolerates:** a column reordered, which is a set comparison
    and not a sequence one, because nothing here promises an order and the read
    path selects by name.
    """
    require_comment_view(db_session)

    present = set(require_comment_view(db_session))
    expected = set(COMMENT_VIEW_COLUMNS)
    surplus = sorted(present - expected)
    absent = sorted(expected - present)

    assert not surplus and not absent, (
        f"`public.{COMMENT_VIEW}` returns {sorted(present)} and E4-04 settles it as "
        f"{sorted(expected)}.\n\nReturned and not in the contract: {surplus}\nIn the contract and "
        f"not returned: {absent}\n\n"
        "The first list is the one to read first. Every column this view returns is a column the "
        "application connection may select and put on an instructor's report, and SPEC §4.1 "
        "forbids identity in any of them: `user_id` and `response_id` each reach a person in one "
        "more hop, and `submitted_at` is the timestamp SPEC §4 says is never shown with a comment "
        "— which is also the order key E4-04's known traps warn about. If a column is genuinely "
        "needed it is a decision: `COMMENT_VIEW_COLUMNS` in tests/fixtures/report_comments.py "
        "records it with the sentence that admits it, `SANCTIONED_VIEW_COLUMNS` in "
        "tests/integration/test_identity_grants.py records the grant, and the pull request says "
        "which surface needs it.\n\n"
        "The second list means a column the read path selects is not there, which shuts the path "
        "rather than opening it."
    )


def test_the_view_holds_the_weeks_comment_answers_and_nothing_else(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The row filter: comment-kind answers, and not the ratings beside them.

    One student answers all five of SPEC §3.2's questions. Two of those answers
    are comments and three are numbers, and the view is asserted to hold exactly
    the two — by the answers' own keys, so the assertion runs in both directions
    at once: a rating leaking in is caught, and a comment missing is caught.

    **Why the numbers matter here.** A view written as "every answer for the
    section-week" returns a row per rating with a NULL `comment_text`, and the
    read path above it then hands the report a blank comment card per rating per
    response. That is not a confidentiality failure, and it is the failure this
    filter exists to prevent; the confidentiality half is the column list next
    door.

    **The mutation it kills:** the join to `question` dropped, so every answer of
    every kind is a row; and the `comment_text IS NOT NULL` predicate dropped,
    which is the same defect written the other way.
    """
    contract = comment_contract
    world = comment_world
    world.build()
    world.close_week(THE_WEEK)

    _response, comments = world.submit(
        term_week=THE_WEEK,
        comments={
            contract.instructor_stream: AN_INSTRUCTOR_COMMENT,
            contract.course_stream: A_COURSE_COMMENT,
        },
        ratings={contract.rating_position: A_RATING, THE_OTHER_RATING_POSITION: A_RATING},
    )

    rows = world.view_rows(term_week=THE_WEEK)
    held = {row["answer_id"] for row in rows}
    expected = {world.answer_key(answer) for answer in comments.values()}

    assert expected, (
        "This test planted no comment answers, so the equality below is between two empty sets. "
        "The submission answers both comment questions, so a miss here is the fixture rather than "
        "the view."
    )
    assert held == expected, (
        f"`public.{COMMENT_VIEW}` holds {len(held)} rows for the week and the student wrote "
        f"{len(expected)} comments.\n\nIn the view and not a comment: {sorted(held - expected)}\n"
        f"A comment and not in the view: {sorted(expected - held)}\n\n"
        "The first list is a rating or a workload figure arriving as a comment row, which the read "
        "path renders as an empty comment card. The second is a comment the instructor will never "
        "be shown."
    )

    streams = {row["stream"] for row in rows}
    assert streams == {contract.instructor_stream, contract.course_stream}, (
        f"The view reports streams {sorted(streams)} for a week holding one comment in each of "
        "SPEC §5.1's two groups. The stream comes from `question.stream` (E4-02) and never from a "
        "question's ordinal, which is what makes a re-ordered question set still group correctly."
    )


def test_a_comment_answer_holding_no_text_never_reaches_the_view(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """ "Non-empty text only" — asserted as the outcome, whichever layer produces it.

    E4-04's work order settles the view as comment-kind answers **with non-empty
    text**. There are two ways that can be true and this test accepts either: the
    schema refuses an `answer` holding an empty comment (E2-05 refuses an answer
    with no value at all, and ADR 0110 puts value validation on the write path),
    or the view's predicate excludes it. What must not happen is an empty row
    reaching the read path, where it renders as a comment card with nothing in it
    under a heading that says a student wrote something.

    **The disjunction is the criterion rather than a hedge**, and it is written
    out so the next reader does not tighten it into an assertion about a layer
    this ticket does not own. The near miss it still catches is the one that
    matters: a view with no text predicate over a schema with no text constraint.

    **The pair is the ordinary comment in the same week**, required to be present,
    so the absence below is not a view that returns nothing.

    **The mutation it kills:** `comment_text IS NOT NULL` written where
    `comment_text <> ''` was also needed, on a schema that admits the empty
    string.
    """
    from sqlalchemy.exc import DatabaseError

    contract = comment_contract
    world = comment_world
    world.build()
    world.close_week(THE_WEEK)

    _response, comments = world.submit(
        term_week=THE_WEEK, comments={contract.instructor_stream: AN_INSTRUCTOR_COMMENT}
    )
    present = {row["answer_id"] for row in world.view_rows(term_week=THE_WEEK)}
    assert present == {world.answer_key(comment) for comment in comments.values()}, (
        f"The ordinary comment is not in `public.{COMMENT_VIEW}` (it holds {sorted(present)}), so "
        "the absence asserted below is what this view does to everything."
    )

    # Written inside a savepoint so a refusal leaves the session usable, and so a
    # schema that refuses the row is an answer rather than an error.
    savepoint = world.session.begin_nested()
    refused: DatabaseError | None = None
    empty: Any = None
    try:
        empty = world.submit(term_week=THE_WEEK, comments={contract.course_stream: ""})[1][
            contract.course_stream
        ]
    except DatabaseError as failure:
        savepoint.rollback()
        refused = failure
    else:
        savepoint.commit()

    if refused is not None:
        return

    in_the_view = {row["answer_id"] for row in world.view_rows(term_week=THE_WEEK)}
    assert world.answer_key(empty) not in in_the_view, (
        f"An `answer` holding an empty comment was accepted by the database and `public."
        f"{COMMENT_VIEW}` returns it: the view holds {sorted(in_the_view)}.\n\n"
        "E4-04's work order settles this view as comment-kind answers with non-empty text only. An "
        "empty row here renders on the instructor's report as a comment card with nothing in it, "
        "under a heading that says a student wrote something — and it counts toward the cumulative "
        "volume that releases a term's held comments, so an empty string can cross the threshold."
    )
