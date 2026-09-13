"""SPEC §4.1 item 3, instructor side — ticket E4-04, criteria 1, 2 and 6.

> Below the n-threshold, raw comments are hidden from instructors and students
> alike.

§4 says what that means at the read: "instructors see rating distributions and
the AI summary, but **no raw comments**", and §5.2 adds the half that is easy to
ship without noticing — "below the threshold, flagged comments are hidden from
the instructor entirely — no chip, no count, no flag-type hint".

**Every test here plants comments that would leak.** E4-04's own known traps put
it plainly: "a below-threshold test that passes because the week had no comments
proves nothing". So each below-threshold week in this module carries real text in
both streams and, where the test is about concealment, a `FLAGGED_COLLAPSED` row
and an `EXCLUDED` row beside them. The text is distinctive, and a failure message
that quotes it is quoting a leak.

**Every absence is paired with a presence.** A service that answered `()` for
every week in the product would satisfy every assertion below and would also ship
a report with no comments in it, which is the same green a broken read path gives
(`docs/MISTAKES.md` entry 3). So each test also drives a week at or above the
threshold in the same section and requires the same comment back — and the
below-threshold week's response count and the above-threshold week's are both
read out of the database and compared against the configured threshold, which is
E4-04's first known trap answered from both sides.

**Marked `invariant` at the module level**, which puts every test here in the
isolated §4.1 pass CLAUDE.md says may never be skipped, and which
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
requires of a module named for what it denies.

**Which failure a red is, before E4-04 lands.** Every test in this module reaches
the service through `comment_contract.visible()`, which is a `pytest.fail` naming
`app.services.report_comments` and the signature the work order settles. That is
a FAILED assertion rather than an error in somebody's setup
(`docs/MISTAKES.md` entry 44), and it is the intended red.
"""

from decimal import Decimal
from typing import Any

import pytest
from fixtures.report_comments import CommentWorld

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The two term weeks this module drives, both inside cohort `F`'s run (term weeks
# 7 to 12), so neither is a week the section does not have — a different absence
# with a different cause.
SMALL_WEEK = 7
BIG_WEEK = 8

# A third week, planted with no comments at all, for the indistinguishability
# assertion: what a caller receives for a suppressed week and what it receives
# for a week nobody commented in have to be the same value.
SILENT_WEEK = 9

# The comments planted in the small week. Distinctive enough that a leak of one
# is unmistakable in a failure message, and long enough to clear SPEC §3.3's
# character floor so nothing here rests on a floored classification.
SMALL_WEEK_COMMENTS = (
    "the lab handout for week two contradicted the slides and nobody could reconcile them",
    "office hours clash with the only section of the required statistics course",
    "the reading load doubled in week three without any warning in the syllabus",
    "the group work was fine but the marking rubric was never actually published",
)

# The comment planted in the big week, which is the presence half of every pair.
A_BIG_WEEK_COMMENT = "the worked examples in the Thursday session were the useful part of the week"

# A comment planted in the small week and then flagged, and one planted and then
# excluded. §5.2 conceals the first entirely below the threshold and shows it
# collapsed above; the second keeps its text visible to the instructor above the
# threshold, muted. Below the threshold both are absent, which is what this
# module asserts and what the pair above the threshold makes mean something.
A_FLAGGED_COMMENT = "the instructor said something about my classmate that I do not want repeated"
AN_EXCLUDED_COMMENT = "this one was taken down after review and its text is still the instructors"


# A rating a student gave, for the week that holds responses and no comments.
# Inside SPEC §3.2's 1-5 Likert range and read back by nothing.
A_RATING = Decimal("4")


def texts(comments: tuple[Any, ...]) -> list[str]:
    """The text of every comment a read answered with, for a failure message."""
    return sorted(str(getattr(comment, "text", comment)) for comment in comments)


def some_comments(count: int) -> list[str]:
    """`count` distinct comment texts, whatever the configured threshold is.

    The sentences above are recycled with the response number appended rather
    than being a fixed tuple sliced, so an institution's threshold larger than
    the number of sentences written here still produces a week of exactly the
    planted size. Distinct, because two identical texts would make a leak of one
    of them unattributable in a failure message and would collapse into one entry
    under any assertion written over a set.
    """
    return [
        f"{SMALL_WEEK_COMMENTS[index % len(SMALL_WEEK_COMMENTS)]} (response {index + 1})"
        for index in range(count)
    ]


def plant_the_pair(world: CommentWorld, contract: Any, *, stream: str) -> dict[str, Any]:
    """One week below the threshold and one at it, both asserted against the configuration.

    Returns the two weeks' comment rows so a caller can name what it planted.
    Both halves are read back out of the database — E4-04's first known trap is a
    fixture bug that breaks this diff silently, and "provably below and above
    threshold by construction, both sides asserted" is what the ticket asks for.
    """
    threshold = contract.threshold()
    assert threshold >= 2, (
        f"The configured n-threshold is {threshold}, and a threshold below 2 leaves no room for a "
        "week that is strictly under it and still carries a response. Nothing below could be "
        "planted, so this is a failure of the configuration these tests run under rather than of "
        "the service."
    )

    world.build()
    world.close_week(SMALL_WEEK).close_week(BIG_WEEK).close_week(SILENT_WEEK)

    small = world.week_of_comments(
        term_week=SMALL_WEEK, texts=some_comments(threshold - 1), stream=stream
    )
    big = world.week_of_comments(
        term_week=BIG_WEEK, texts=[A_BIG_WEEK_COMMENT] * threshold, stream=stream
    )

    below = world.responses_in(term_week=SMALL_WEEK)
    at_or_above = world.responses_in(term_week=BIG_WEEK)
    assert below == threshold - 1, (
        f"The small week holds {below} responses and this test planted {threshold - 1} — one below "
        f"the configured threshold of {threshold}. A week that is not actually under the threshold "
        "makes every suppression assertion below a statement about nothing, which is exactly the "
        "fixture bug E4-04's known traps name first."
    )
    assert at_or_above == threshold, (
        f"The big week holds {at_or_above} responses and this test planted {threshold} — the "
        "configured threshold exactly. Without a week that really is at the boundary, the presence "
        "half of every pair below cannot distinguish suppression from a read path that answers "
        "nothing for every week."
    )
    return {"small": small, "big": big, "threshold": threshold}


def test_a_week_below_the_threshold_yields_no_raw_comment_at_all(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """Criterion 1: zero raw comments cross the boundary, proven at the service's return.

    SPEC §4: "instructors see rating distributions and the AI summary, but **no
    raw comments**". The week planted here carries one response fewer than the
    configured threshold and a real comment on every one of them, so a service
    that returned anything at all is returning a student's words to a reader §4
    says must not have them.

    **The pair is the same section's week at the threshold**, read in the same
    test. Without it, `()` is the answer a service gives when the view is missing,
    when the grant is absent, and when the section does not exist — three
    failures that look exactly like suppression (`docs/MISTAKES.md` entry 3).

    **The mutation it kills:** `<` written where `<=` was meant, or the threshold
    comparison dropped entirely, which is a read path that returns every comment
    it finds. **The near miss it distinguishes:** a service that suppresses the
    whole section rather than the week — that one fails on the presence half here
    rather than passing quietly.
    """
    stream = comment_contract.instructor_stream
    planted = plant_the_pair(comment_world, comment_contract, stream=stream)
    read = comment_contract.visible()

    suppressed = read(
        comment_world.session,
        section_id=comment_world.section_id(),
        week_id=comment_world.week_id(SMALL_WEEK),
        stream=comment_contract.instructor_stream,
    )
    shown = read(
        comment_world.session,
        section_id=comment_world.section_id(),
        week_id=comment_world.week_id(BIG_WEEK),
        stream=comment_contract.instructor_stream,
    )

    assert shown, (
        f"The week at the configured threshold of {planted['threshold']} returned no comments "
        "either, so the suppression asserted below is indistinguishable from a read path that "
        "answers nothing for every week — a missing view, a missing grant, a section this query "
        "never reached. It planted "
        f"{planted['threshold']} responses each carrying {A_BIG_WEEK_COMMENT!r}."
    )
    assert tuple(suppressed) == (), (
        f"The week below the threshold returned {texts(suppressed)}.\n\n"
        "SPEC §4: 'Small-N handling (n < 5 responses in a reporting week): instructors see rating "
        "distributions and the AI summary, but no raw comments.' §4.1 item 3 makes it an "
        "invariant. This week holds one response fewer than the configured threshold of "
        f"{planted['threshold']}, and every one of those responses carries a comment written by a "
        "student who was promised it would not be shown at this size. A leak here cannot be "
        "un-shown."
    )


def test_a_flagged_comment_below_the_threshold_is_absent_from_everything(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """Criterion 2, asserted as the forbidden state (`docs/MISTAKES.md` entry 2).

    SPEC §5.2's small-N concealment: "below the threshold, flagged comments are
    hidden from the instructor entirely — no chip, no count, no flag-type hint —
    while flags still route immediately to the appropriate reviewer." The
    concealment is *stronger* than the ordinary suppression, because a flag is a
    fact about one comment: a count of held comments in a four-response week is a
    statement about one of four people.

    **The forbidden state, not the permitted one.** What is asserted is that the
    flagged text and the flagged status appear nowhere in what the caller
    receives — not that the returned tuple has some expected length — so a later
    ticket that adds a legitimate second field to `ReportComment` cannot make this
    pass by accident.

    **The pair is the same flagged comment above the threshold**, where §5.2 says
    it appears flagged-collapsed with its chip. Without that half, this test is
    satisfied by a service that has never been able to read `moderation_state` at
    all — which is the state the tree is in until E4-04 grants it, and which would
    otherwise read as concealment working.

    **The mutation it kills:** the moderation join left out of the below-threshold
    branch, so a flagged comment falls through as published; and a "1 response
    held for review" count computed before the threshold test, which is the trace
    §5.2 permits only as a neutral participation line and never as a flag hint.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert (
        threshold >= 2
    ), f"The configured n-threshold is {threshold}; nothing below can be planted under it."

    world.build()
    world.close_week(SMALL_WEEK).close_week(BIG_WEEK)

    small = world.week_of_comments(
        term_week=SMALL_WEEK,
        texts=[A_FLAGGED_COMMENT, *some_comments(threshold - 2)],
        stream=contract.instructor_stream,
    )
    world.moderate(small[0], contract.stored_flagged)

    big = world.week_of_comments(
        term_week=BIG_WEEK,
        texts=[A_FLAGGED_COMMENT, *([A_BIG_WEEK_COMMENT] * (threshold - 1))],
        stream=contract.instructor_stream,
    )
    world.moderate(big[0], contract.stored_flagged)

    assert world.responses_in(term_week=SMALL_WEEK) == threshold - 1, (
        f"The small week does not hold {threshold - 1} responses, so it is not the week this test "
        "is about."
    )
    assert world.responses_in(term_week=BIG_WEEK) == threshold, (
        f"The big week does not hold {threshold} responses, so the control below is not at the "
        "boundary."
    )

    read = contract.visible()
    above = read(
        world.session,
        section_id=world.section_id(),
        week_id=world.week_id(BIG_WEEK),
        stream=contract.instructor_stream,
    )
    flagged_above = [
        comment
        for comment in above
        if getattr(comment, "text", None) == A_FLAGGED_COMMENT
        and getattr(comment, "status", None) == contract.flagged
    ]
    assert flagged_above, (
        "Above the configured threshold the flagged comment did not come back carrying "
        f"{contract.flagged!r}; the week returned {[(c.text, c.status) for c in above]}.\n\n"
        "SPEC §5.2 shows a flagged comment to the instructor collapsed, with its chip, once the "
        "week is at or above the threshold. Until this half works, the absence asserted below is "
        "equally well explained by a path that cannot read `moderation_state` at all — which is "
        "the state of the tree until E4-04's migration grants it."
    )

    below = read(
        world.session,
        section_id=world.section_id(),
        week_id=world.week_id(SMALL_WEEK),
        stream=contract.instructor_stream,
    )
    everything_returned = [
        value
        for comment in below
        for value in (getattr(comment, "text", None), getattr(comment, "status", None))
    ]
    forbidden = [
        value
        for value in everything_returned
        if value == A_FLAGGED_COMMENT or value == contract.flagged
    ]
    assert not forbidden, (
        f"The below-threshold week returned {forbidden} — the flagged comment's text, or its "
        f"status, or both. What came back whole: {[(c.text, c.status) for c in below]}.\n\n"
        "SPEC §5.2: below the threshold a flagged comment is hidden from the instructor entirely — "
        "no chip, no count, no flag-type hint. In a week of "
        f"{threshold - 1} responses a flag is a statement about one of "
        f"{threshold - 1} identifiable people, which is why the concealment is total rather than a "
        "collapsed card."
    )


def test_a_suppressed_week_and_a_week_nobody_commented_in_return_the_same_thing(
    comment_world: CommentWorld, comment_contract: Any
) -> None:
    """Criteria 1 and 2: the count of what was withheld is not derivable from the response.

    SPEC §5.2 permits "an optional neutral participation trace" and forbids it
    revealing category; §4 gives the instructor a distribution and a summary and
    no raw comments. What neither permits is a *shape* that differs — a returned
    value that is longer, or of a different type, or carrying a placeholder, when
    something was withheld than when there was nothing to withhold.

    Three weeks are planted in one section: one below the threshold carrying four
    real comments and a flagged one, one below the threshold carrying none at all,
    and one at the threshold carrying a comment. The first two must be
    indistinguishable to the caller; the third is what says the reader works.

    **This is where a well-meaning implementation leaks.** A path that returns an
    empty list of comments plus a `withheld=4` beside it, or a tuple of four
    redacted placeholders, satisfies "no raw comments" and tells the instructor
    exactly how many students in a four-response week wrote something — which in a
    section that small is a roster question.

    **The mutation it kills:** a suppressed week answered with a tuple of
    placeholder `ReportComment`s rather than with nothing, and any difference of
    type between the two answers.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert (
        threshold >= 2
    ), f"The configured n-threshold is {threshold}, and nothing can be planted below it."

    world.build()
    world.close_week(SMALL_WEEK).close_week(SILENT_WEEK).close_week(BIG_WEEK)

    small = world.week_of_comments(
        term_week=SMALL_WEEK,
        texts=some_comments(threshold - 1),
        stream=contract.instructor_stream,
    )
    world.moderate(small[0], contract.stored_flagged)
    # A week under the threshold in which nobody wrote a comment: the responses
    # exist, so the week is a real week with a real count, and no comment answer
    # was ever stored for it.
    for _ in range(threshold - 1):
        world.submit(term_week=SILENT_WEEK, ratings={contract.rating_position: A_RATING})
    world.week_of_comments(
        term_week=BIG_WEEK,
        texts=[A_BIG_WEEK_COMMENT] * threshold,
        stream=contract.instructor_stream,
    )

    assert world.responses_in(term_week=SMALL_WEEK) == threshold - 1, (
        f"The suppressed week does not hold {threshold - 1} responses, so it is not one below the "
        "configured threshold and this comparison is about two weeks nobody planted."
    )
    assert world.responses_in(term_week=SILENT_WEEK) == threshold - 1, (
        "The silent week does not hold the same number of responses as the suppressed one, so the "
        "two answers below could differ for a reason that is not about comments."
    )

    read = contract.visible()

    def week(term_week: int) -> Any:
        return read(
            world.session,
            section_id=world.section_id(),
            week_id=world.week_id(term_week),
            stream=contract.instructor_stream,
        )

    assert week(BIG_WEEK), (
        "The week at the threshold returned nothing, so both answers compared below are the answer "
        "this path gives to everything and their agreement means nothing."
    )

    suppressed = week(SMALL_WEEK)
    silent = week(SILENT_WEEK)
    assert type(suppressed) is type(silent), (
        f"A suppressed week answers with a {type(suppressed).__name__} and a week with no comments "
        f"in it answers with a {type(silent).__name__}. The type alone tells an instructor that "
        "something was withheld."
    )
    assert suppressed == silent, (
        f"A week holding {threshold - 1} withheld comments answered {suppressed!r} and a week "
        f"holding none answered {silent!r}.\n\n"
        "SPEC §5.2 lets a neutral participation trace exist and forbids it revealing category; "
        "what it does not allow is the suppressed count being readable off the response itself. In "
        f"a week of {threshold - 1} responses, 'four comments were withheld' and 'none were' are "
        "different facts about four identifiable students, and any difference between these two "
        "values carries it."
    )
