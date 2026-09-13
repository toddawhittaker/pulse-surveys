"""The one view this path selects comment text through — ticket E4-04.

E4-04's work order ships `backend/app/views_sql/report_comment_v001.sql`,
returning `(section_id, week_id, stream, answer_id, comment_text)` over the
comment-kind answers that carry text. Three questions about it, and none is
answered by anything already in the suite:

  - **What it returns**, as an equality against the contract. Every column a view
    an instructor's connection can read returns is a column an instructor can be
    shown, and SPEC §4.1 forbids identity in any of them. `alembic check` reads no
    `pg_class` entry for a view at all, and the marked-column sweeps ask what a
    view *reads* rather than what it *returns* — so a column arriving here is
    caught by this and by `SANCTIONED_VIEW_COLUMNS` in
    `tests/integration/test_identity_grants.py`, and by nothing else.
  - **What rows it holds.** "Comment-kind answers with non-empty text only" is two
    filters, and each has a test. Without the text filter the view hands the read
    path a NULL for every question nobody answered, which renders as blank comment
    cards. Without the **kind** filter it hands over any row that happens to carry
    `comment_text`, whatever question it answers — and E2-05's `CHECK` counts
    non-null values without ever asking which value belongs under which kind, so
    that row is one the database accepts and only `app.services.submissions`
    declines to write.
  - **Whether the rule survives one layer up.** A predicate in the view is only
    the report's answer if the report reads through the view, so the forbidden row
    is asserted absent from `visible_comments` as well — a read path that reached
    past the view to `answer` would satisfy every assertion about the view and
    still put a number somebody typed as text under §5.1's comment heading.

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

# Text stored on an `answer` whose question asks for a number. E2-05's `CHECK` is
# `num_nonnulls(rating, comment_text, workload_hours) = 1` and says nothing about
# which value belongs under which *kind* of question, so the database accepts this
# row; `app.services.submissions` is what never writes it, and ADR 0110 puts that
# validation on the write path deliberately. It is planted directly, which
# `CommentWorld.comment_text_under_another_kind` explains at length.
#
# **It reads like a rating that has gone wrong rather than like a comment**, so a
# failure message quoting it says which row leaked and how it got there.
TEXT_UNDER_A_RATING_QUESTION = "4 out of 5, stored as text on an answer to the rating question"


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
    """The row filter: the answers to comment questions, and nothing else at all.

    One student answers both comment questions and both rating questions. A second
    student answers one rating and leaves the other question unanswered, and it is
    on *their* response that the forbidden row is planted: an `answer` carrying
    `comment_text` under a **rating** question. The view is asserted to hold
    exactly the two real comments, by the answers' own keys, so the equality runs
    in every direction at once — a rating leaking in is caught, a comment missing
    is caught, and so is the planted row.

    **The second respondent is not decoration.** E2-05 holds
    `UNIQUE (response_id, question_id)`, so the forbidden row cannot go on a
    response that already gave that question a number: the insert is refused
    before the view is reached, and the red is about this test rather than about
    the predicate. `comment_text_under_another_kind` now says so in words rather
    than letting a `UniqueViolation` say it.

    **The planted row is the point, and it is why this test exists at this
    strength.** E2-05's `answer` carries `CHECK (num_nonnulls(rating,
    comment_text, workload_hours) = 1)` — one value per row — and nothing in the
    schema says which value belongs under which *kind* of question. So a comment
    stored under a rating question is a row the database accepts, and what keeps
    it out of a deployment is `app.services.submissions` writing the column the
    kind calls for (ADR 0110 puts value validation on the write path deliberately).
    The view's kind predicate is the second line, and until something is thrown at
    it the predicate can be deleted with every test in this epic still green — it
    was, and this is the repair.

    **What such a row would do if it got through** is not cosmetic. It enters the
    view, so `visible_comments` returns it as a student's comment; it counts toward
    the cumulative volume SPEC §4 releases a term's held comments on, so it can
    push a section across the threshold; and it can be written into a release
    batch, where it surfaces with its week stripped and cannot be un-released
    (ADR 0146). The next test in this module asserts the read path's half.

    **Why the ratings still matter beside it.** A view written as "every answer
    for the section-week" returns a row per rating with a NULL `comment_text`, and
    the read path hands the report a blank comment card per rating per response —
    not a confidentiality failure, and the failure this filter also prevents.

    **The planted row is classified like a real comment**, so the only thing that
    distinguishes it from the comment beside it is the kind of question it answers.
    Without that, a read path or a view that joined `classification` would exclude
    it for a reason having nothing to do with the kind predicate, and this test
    would be green while naming the wrong layer.

    **The mutation it kills:** `WHERE asked.kind = 'comment'` deleted from
    `report_comment_v001.sql` — the survivor this test was rewritten for — and
    with it any join to `question` that served only that predicate.
    **The near miss it leaves to its neighbour:** the `comment_text` predicate
    dropped, which `test_a_comment_answer_holding_no_text_never_reaches_the_view`
    is the test for. This one cannot see it: every row it plants either carries
    text or is a rating whose `comment_text` is NULL, so the two predicates are
    not both exercised here and this docstring does not claim they are.
    """
    contract = comment_contract
    world = comment_world
    world.build()
    world.close_week(THE_WEEK)

    _answered_everything, comments = world.submit(
        term_week=THE_WEEK,
        comments={
            contract.instructor_stream: AN_INSTRUCTOR_COMMENT,
            contract.course_stream: A_COURSE_COMMENT,
        },
        ratings={contract.rating_position: A_RATING, THE_OTHER_RATING_POSITION: A_RATING},
    )
    # **A second respondent, and the forbidden row goes on theirs**, because E2-05
    # holds `UNIQUE (response_id, question_id)`: the submission above answered the
    # rating question with a number, so it has no room for a second row under it
    # and the insert would be refused before the view was reached at all. This one
    # leaves that position unanswered — `submit` writes an `answer` only for the
    # positions it is given — and rates the other stream instead, so it is a real
    # submission rather than an empty one.
    left_the_rating_unanswered, _no_comments = world.submit(
        term_week=THE_WEEK, ratings={THE_OTHER_RATING_POSITION: A_RATING}
    )
    planted = world.comment_text_under_another_kind(
        left_the_rating_unanswered,
        term_week=THE_WEEK,
        position=contract.rating_position,
        body=TEXT_UNDER_A_RATING_QUESTION,
    )

    rows = world.view_rows(term_week=THE_WEEK)
    held = {row["answer_id"] for row in rows}
    expected = {world.answer_key(answer) for answer in comments.values()}
    forbidden = world.answer_key(planted)

    assert expected, (
        "This test planted no comment answers, so the equality below is between two empty sets. "
        "The submission answers both comment questions, so a miss here is the fixture rather than "
        "the view."
    )
    assert forbidden not in expected, (
        "The row planted under the rating question came back with the key of one of the real "
        "comments, so the assertion below could not tell them apart. That is this test's own "
        "fixture rather than the view."
    )
    assert forbidden not in held, (
        f"`public.{COMMENT_VIEW}` returns the answer carrying "
        f"{TEXT_UNDER_A_RATING_QUESTION!r}, which was stored under SPEC §3.2's rating question at "
        f"position {contract.rating_position} and is not a comment.\n\n"
        "E2-05's `CHECK` counts non-null values and says nothing about which value belongs under "
        "which kind of question, so the database accepts this row; `app.services.submissions` is "
        "the only thing that does not write it, and this view's kind predicate is what stands "
        "between that promise and the report. Once such a row is in the view it is a comment to "
        "everything downstream: `visible_comments` returns it, the cumulative volume counts it "
        "toward SPEC §4's crossing, and a release batch can carry it out with its week stripped "
        "and no way to un-release it (ADR 0146)."
    )
    assert held == expected, (
        f"`public.{COMMENT_VIEW}` holds {len(held)} rows for the week and the student wrote "
        f"{len(expected)} comments.\n\nIn the view and not a comment: {sorted(held - expected)}\n"
        f"A comment and not in the view: {sorted(expected - held)}\n\n"
        "The first list is a rating, a workload figure or the planted text-under-a-rating row "
        "arriving as a comment. The second is a comment the instructor will never be shown."
    )

    streams = {row["stream"] for row in rows}
    assert streams == {contract.instructor_stream, contract.course_stream}, (
        f"The view reports streams {sorted(streams)} for a week holding one comment in each of "
        "SPEC §5.1's two groups. The stream comes from `question.stream` (E4-02) and never from a "
        "question's ordinal, which is what makes a re-ordered question set still group correctly."
    )


def test_text_stored_under_a_rating_question_never_reaches_the_instructors_report(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The same forbidden row, one layer up: what the instructor is actually handed.

    The test above asserts the view does not return it. This one asserts the
    consequence that matters — that no such row reaches an instructor as a
    comment — through `visible_comments`, over a week at the configured threshold
    where every real comment *is* returned.

    **Two layers, two tests, and neither implies the other.** The view is one
    place the predicate could live and the service is another: a read path that
    selected from `answer` directly, or that widened its own predicate, would
    satisfy the view's row equality perfectly and still hand the report a number
    somebody stored as text. Asserting only the view would be asserting a
    mechanism; this is the criterion.

    **The pair is inside the test**: the week's real comments must all come back.
    Below the threshold `visible_comments` returns nothing at all, so an absence
    on its own here would be suppression rather than filtering
    (`docs/MISTAKES.md` entry 3), and the count is read back from the database
    before the read is made.

    **The planted row is classified like a real comment**, so a read path that
    joins `classification` cannot be what excludes it, and a green here names the
    kind predicate rather than some second defence that happens to agree.

    **The mutation it kills:** the kind predicate deleted from
    `report_comment_v001.sql`, seen from the surface that renders the result; and
    a read path that reached past the view to `answer`, which no assertion about
    the view can see.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()

    world.build()
    world.close_week(THE_WEEK)
    real: list[Any] = []
    responses: list[Any] = []
    for index in range(threshold):
        # **No rating is answered**, and that is what leaves room for the plant:
        # E2-05 holds `UNIQUE (response_id, question_id)`, so a response that gave
        # the rating question a number refuses a second row under it and the
        # insert fails before the read path is reached. `submit` writes an
        # `answer` only for the positions it is given, so omitting the rating is
        # all it takes; the ratings are not what this test is about, and the week
        # that renders them is the test above's.
        response, comments = world.submit(
            term_week=THE_WEEK,
            comments={contract.instructor_stream: f"{AN_INSTRUCTOR_COMMENT} ({index + 1})"},
        )
        responses.append(response)
        real.append(comments[contract.instructor_stream])
    world.comment_text_under_another_kind(
        responses[0],
        term_week=THE_WEEK,
        position=contract.rating_position,
        body=TEXT_UNDER_A_RATING_QUESTION,
    )

    count = world.responses_in(term_week=THE_WEEK)
    assert count == threshold, (
        f"The week holds {count} responses and the configured threshold is {threshold}. Below it "
        "`visible_comments` returns nothing whatever is stored, and the absence asserted here "
        "would be small-N suppression rather than the kind filter. The forbidden row is planted on "
        "one of these responses rather than on a response of its own, so it adds no count — but a "
        "planter who adds a respondent to make room for it moves this number, which is what this "
        "guard is here to say."
    )

    shown = contract.visible()(
        world.session,
        section_id=world.section_id(),
        week_id=world.week_id(THE_WEEK),
        stream=contract.instructor_stream,
    )
    texts = [str(comment.text) for comment in shown]

    assert len(shown) == len(real), (
        f"The week returned {len(shown)} comments and {len(real)} were written as answers to SPEC "
        f"§3.2's comment question: {texts}. Until every real comment comes back, the absence "
        "asserted below is satisfied by a read that answers nothing."
    )
    assert TEXT_UNDER_A_RATING_QUESTION not in texts, (
        f"The instructor's report carries {TEXT_UNDER_A_RATING_QUESTION!r}, which is stored on an "
        f"`answer` to the rating question at position {contract.rating_position} rather than to a "
        "comment question.\n\n"
        "E2-05's `CHECK` counts non-null values and never asks which value belongs under which "
        "kind of question, so this row is one the database accepts and only "
        "`app.services.submissions` declines to write. Whatever reaches the report as a comment is "
        "read as a student's words: it is rendered under §5.1's headings, it feeds the summary, it "
        "counts toward the cumulative volume SPEC §4 releases a term's held comments on, and once "
        "a release batch carries it there is no way to un-release it (ADR 0146)."
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
