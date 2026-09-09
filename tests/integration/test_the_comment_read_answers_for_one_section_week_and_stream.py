"""What a comment read is scoped to — ticket E4-04.

`visible_comments` takes a section, a week and a stream; `released_comments` takes
a section, a term and a stream. Each of those is a filter, and each of them
protects something different:

  - **the section**, which is SPEC §4's own boundary and the most expensive of the
    three to get wrong. A read that leaked another section's comments would put
    one class's words on another instructor's report, and the threshold test would
    still pass — the leaking section may be large while the leaked-from one is
    not, which is small-N suppression defeated from outside.
  - **the week**, which is what makes the threshold mean anything at all: SPEC §4's
    rule is "n < 5 responses **in a reporting week**", so a read that pooled two
    weeks would answer a large week's comments under a small week's key.
  - **the stream**, which is SPEC §5.1's two groups — "About the instructor" /
    "About the course" — read from `question.stream` (E4-02) rather than from a
    question's ordinal, so a re-ordered question set still groups correctly.

**Each is asserted as a pair**: the thing asked for comes back, and the thing not
asked for is absent. An absence on its own is what a read that answers nothing
produces, which is `docs/MISTAKES.md` entry 3 in the shape that reads as
suppression working.

**Every week driven here is at or above the configured threshold**, read back from
the database first — below it everything is absent and every assertion in this
module would be true of a path that had never been written.
"""

from typing import Any

import pytest
from fixtures.report_comments import CommentWorld

# **Marked `invariant`, which puts this module in CI's isolated §4.1 pass** where a
# skip or an empty collection is a failure (`scripts/ci/check_invariants.py`).
# §4.1 item 3 and item 6: what this module asserts is the *keying* of the comment
# read — one section, one week, one stream — and a read whose section predicate is
# dropped or widened hands one instructor another section's students' words. That
# is a confidentiality boundary rather than a query-shape preference, so it belongs
# where a silent skip cannot hide it.
pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# Cohort `F` runs term weeks 7 to 12; cohort `Q` runs 7 to 18, so the two sections
# share these weeks and a leak across them is about the section and nothing else.
THIS_WEEK = 7
ANOTHER_WEEK = 8
THIS_SECTION = "F"
ANOTHER_SECTION = "Q"

ABOUT_THE_INSTRUCTOR = "the feedback on the first assignment came back quickly and was specific"
ABOUT_THE_COURSE = "the recommended text is three editions out of date and hard to get hold of"
FROM_ANOTHER_WEEK = "in the following week the workload dropped back to something manageable"
FROM_ANOTHER_SECTION = "this belongs to a different section and no instructor here ever taught it"


def read(world: CommentWorld, contract: Any, *, stream: str, week: int, cohort: str) -> Any:
    """One read, spelled out so each test says which of the three filters it is moving."""
    return contract.visible()(
        world.session,
        section_id=world.section_id(cohort),
        week_id=world.week_id(week),
        stream=stream,
    )


def fill(
    world: CommentWorld, contract: Any, *, week: int, cohort: str, body: str, stream: str
) -> None:
    """A week at the configured threshold, every response carrying the same comment.

    The count is read back: below the threshold the read answers nothing, and the
    absences this module asserts would then be free.
    """
    threshold = contract.threshold()
    world.close_week(week)
    world.week_of_comments(
        term_week=week,
        texts=[f"{body} ({index + 1})" for index in range(threshold)],
        stream=stream,
        cohort=cohort,
    )
    count = world.responses_in(term_week=week, cohort=cohort)
    assert count == threshold, (
        f"Section {cohort}'s term week {week} holds {count} responses and the configured threshold "
        f"is {threshold}. Below it the read answers nothing, and every absence asserted in this "
        "module would be true for a reason that is not the filter under test."
    )


def texts_of(comments: Any) -> list[str]:
    """The texts a read answered with."""
    return sorted(str(comment.text) for comment in comments)


def test_a_read_of_one_stream_never_returns_the_other_streams_comments(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """SPEC §5.1's two groups, kept apart by `question.stream`.

    One week, one section, one comment about the instructor and one about the
    course from every respondent. Each read returns its own group and neither
    returns the other's.

    **Why this is a confidentiality rule and not a layout one.** §5.1 heads each
    group with its own AI summary, and §5.2's routing differs by group — abuse
    aimed at the instructor goes to the Lead Faculty queue. A course comment
    rendered under "About the instructor" is a complaint about a textbook filed as
    a complaint about a named person.

    **The mutation it kills:** the `stream` predicate dropped from the read, which
    returns everything under both headings; and a stream derived from a question's
    ordinal rather than from `question.stream`, which E4-02 added precisely so a
    re-ordered question set still groups correctly.
    """
    contract = comment_contract
    world = comment_world
    world.build()
    threshold = contract.threshold()
    world.close_week(THIS_WEEK)
    for index in range(threshold):
        world.submit(
            term_week=THIS_WEEK,
            comments={
                contract.instructor_stream: f"{ABOUT_THE_INSTRUCTOR} ({index + 1})",
                contract.course_stream: f"{ABOUT_THE_COURSE} ({index + 1})",
            },
        )
    count = world.responses_in(term_week=THIS_WEEK)
    assert count == threshold, (
        f"The week holds {count} responses and the threshold is {threshold}; below it both reads "
        "answer nothing and neither absence below means anything."
    )

    instructor = texts_of(
        read(
            world,
            contract,
            stream=contract.instructor_stream,
            week=THIS_WEEK,
            cohort=THIS_SECTION,
        )
    )
    course = texts_of(
        read(world, contract, stream=contract.course_stream, week=THIS_WEEK, cohort=THIS_SECTION)
    )

    assert len(instructor) == threshold and len(course) == threshold, (
        f"The two streams returned {len(instructor)} and {len(course)} comments and each was "
        f"written {threshold} times. Until both answer, the separation below is satisfied by a read "
        "that answers nothing for one of them."
    )
    assert not [text for text in instructor if ABOUT_THE_COURSE in text], (
        f"The instructor stream returned {instructor}, which includes comments written in answer to "
        "SPEC §3.2's course question. §5.1 heads each group with its own summary and §5.2 routes "
        "abuse aimed at the instructor to the Lead Faculty queue, so a course comment filed under "
        "'About the instructor' is a complaint about a textbook read as a complaint about a named "
        "person."
    )
    assert not [text for text in course if ABOUT_THE_INSTRUCTOR in text], (
        f"The course stream returned {course}, which includes instructor-stream comments. Both "
        "directions are asserted because a read that ignored `stream` entirely would return "
        "everything under both headings and fail only one of these if only one were written."
    )


def test_a_read_of_one_week_never_returns_another_weeks_comments(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The week filter, which is what makes SPEC §4's threshold mean anything.

    §4's rule is "n < 5 responses **in a reporting week**". A read that pooled a
    section's weeks would answer with a large week's comments under a small week's
    key, so the threshold test would pass on one week's count while returning
    another's text — which is small-N suppression defeated without ever touching
    the comparison.

    **The mutation it kills:** the `week_id` predicate dropped, which is easy to
    do when the read already filters by section and the section usually has one
    interesting week.
    """
    contract = comment_contract
    world = comment_world
    world.build()
    fill(
        world,
        contract,
        week=THIS_WEEK,
        cohort=THIS_SECTION,
        body=ABOUT_THE_INSTRUCTOR,
        stream=contract.instructor_stream,
    )
    fill(
        world,
        contract,
        week=ANOTHER_WEEK,
        cohort=THIS_SECTION,
        body=FROM_ANOTHER_WEEK,
        stream=contract.instructor_stream,
    )

    asked = texts_of(
        read(
            world,
            contract,
            stream=contract.instructor_stream,
            week=THIS_WEEK,
            cohort=THIS_SECTION,
        )
    )
    assert asked, "The asked week returned nothing, so its exclusivity below is free."
    assert not [text for text in asked if FROM_ANOTHER_WEEK in text], (
        f"Reading term week {THIS_WEEK} returned {asked}, which includes comments submitted in term "
        f"week {ANOTHER_WEEK}. SPEC §4's threshold counts responses in a *reporting week*, so a "
        "read that pools a section's weeks tests one week's count and returns another week's text."
    )


def test_a_read_of_one_section_never_returns_another_sections_comments(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The section boundary, which is the most expensive of the three to get wrong.

    Two sections of the same term, sharing the same course weeks and the same
    question set. A read of one must return nothing of the other's — not because
    it is untidy but because §4's whole confidentiality model is per section: an
    instructor sees their own students' words and nobody else's, and a leaked
    comment cannot be un-shown.

    **It defeats small-N suppression from outside.** If a large section's comments
    leaked into a small one's read, the small section's own week could be under the
    threshold and the read would still return text — the threshold comparison
    having been made on a count that was never about the comments returned.

    **The released read is asserted too**, because it takes the section as a
    parameter as well and is written against different tables: a release read that
    walked `release_batch_member` without joining back to the batch's section would
    hand every held comment in the institution to whoever asked first.

    **The mutation it kills:** the `section_id` predicate dropped from either read,
    and — the one only the release half sees — a membership walk that filters on the
    term and not on the section.
    """
    contract = comment_contract
    world = comment_world
    world.build()
    world.section(ANOTHER_SECTION)
    fill(
        world,
        contract,
        week=THIS_WEEK,
        cohort=THIS_SECTION,
        body=ABOUT_THE_INSTRUCTOR,
        stream=contract.instructor_stream,
    )
    fill(
        world,
        contract,
        week=THIS_WEEK,
        cohort=ANOTHER_SECTION,
        body=FROM_ANOTHER_SECTION,
        stream=contract.instructor_stream,
    )

    mine = texts_of(
        read(
            world,
            contract,
            stream=contract.instructor_stream,
            week=THIS_WEEK,
            cohort=THIS_SECTION,
        )
    )
    theirs = texts_of(
        read(
            world,
            contract,
            stream=contract.instructor_stream,
            week=THIS_WEEK,
            cohort=ANOTHER_SECTION,
        )
    )
    assert mine and theirs, (
        f"One of the two sections returned nothing ({len(mine)} and {len(theirs)}), so the "
        "separation below is satisfied by a read that answers nothing for one section."
    )
    assert not [text for text in mine if FROM_ANOTHER_SECTION in text], (
        f"Reading section {THIS_SECTION} returned {mine}, which includes comments submitted to "
        f"section {ANOTHER_SECTION}. SPEC §4's confidentiality model is per section: an instructor "
        "reads their own students' words and nobody else's, and this is the leak that cannot be "
        "un-shown."
    )
    assert not [text for text in theirs if ABOUT_THE_INSTRUCTOR in text], (
        f"Reading section {ANOTHER_SECTION} returned {theirs}, which includes section "
        f"{THIS_SECTION}'s comments. Both directions are asserted because a read ignoring "
        "`section_id` leaks in both and would fail only one of these if only one were written."
    )


def test_a_released_read_of_one_section_never_returns_another_sections_batch(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """The same boundary on the release, which is written against different tables.

    Both sections hold enough held comments to cross, so both have a batch. A
    release read of one must hold none of the other's — and the query that gets
    this wrong is a plausible one: `release_batch_member` carries only a batch and
    a comment (ADR 0146), so the section lives one join away, on the batch row.

    **The pair is that each section's own release is complete**, which is what
    tells a scoping defect from a release read that answers nothing.

    **The mutation it kills:** a membership walk joined to `release_batch` on the
    term alone, which hands every section in the institution its neighbours' held
    comments; and a walk that reaches the section through `answer` and `response`
    instead of through the batch, which is right today and stops being right the
    first time a batch spans anything.
    """
    contract = comment_contract
    world = comment_world
    world.build()
    world.section(ANOTHER_SECTION)
    threshold = contract.threshold()

    sections = (
        (THIS_SECTION, ABOUT_THE_INSTRUCTOR),
        (ANOTHER_SECTION, FROM_ANOTHER_SECTION),
    )
    for cohort, body in sections:
        for index in range(threshold):
            week = THIS_WEEK + (index % 3)
            world.close_week(week)
            world.week_of_comments(
                term_week=week,
                texts=[f"{body} (held {index + 1})"],
                stream=contract.instructor_stream,
                cohort=cohort,
            )
        for week in range(THIS_WEEK, THIS_WEEK + 3):
            count = world.responses_in(term_week=week, cohort=cohort)
            assert 0 < count < threshold, (
                f"Section {cohort}'s term week {week} holds {count} responses and the threshold is "
                f"{threshold}; a week that is not under it holds nothing to release."
            )

    cut = contract.cut()(world.session)
    assert cut == 2, (
        f"`{contract.cut_name}` cut {cut} batches over two sections that each crossed once, so the "
        "separation below would be about one batch or none."
    )

    released = contract.released()
    mine = texts_of(
        released(
            world.session,
            section_id=world.section_id(THIS_SECTION),
            term_id=world.term_id(),
            stream=contract.instructor_stream,
        )
    )
    theirs = texts_of(
        released(
            world.session,
            section_id=world.section_id(ANOTHER_SECTION),
            term_id=world.term_id(),
            stream=contract.instructor_stream,
        )
    )

    assert len(mine) == threshold and len(theirs) == threshold, (
        f"The two sections' releases hold {len(mine)} and {len(theirs)} comments and each section "
        f"held {threshold}. Until both are complete, the separation below is satisfied by a read "
        "that answers nothing for one of them."
    )
    assert not [text for text in mine if FROM_ANOTHER_SECTION in text], (
        f"Section {THIS_SECTION}'s release holds {mine}, which includes section "
        f"{ANOTHER_SECTION}'s comments. `release_batch_member` carries only a batch and a comment "
        "(ADR 0146), so the section is one join away on the batch row — and a walk that joins on "
        "the term alone hands every section in the institution its neighbours' held comments, "
        "stripped of their weeks and impossible to attribute or retract."
    )
    assert not [text for text in theirs if ABOUT_THE_INSTRUCTOR in text], (
        f"Section {ANOTHER_SECTION}'s release holds {theirs}, which includes section "
        f"{THIS_SECTION}'s comments."
    )
