"""A held stream goes to a release batch, and a released comment never comes back under its week.

Ticket E5.1-01, criteria 3 and 4.

**Criterion 3.** The owner's ruling 1 holds a stream's comments when fewer than the
threshold of distinct students commented in that stream that week — and the
holding is **per stream**: in a week whose course stream is shown, a thin
instructor stream is held while its sibling is not. Held comments enter the
cutter's held set (`_held_comments`, through `cut_due_release_batches`), are cut by
ADR 0152's three unchanged legs, and appear only in `released_comments`, with no
week — never in `visible_comments` for their own week.

**Every leg of the gate is evaluated per stream — the ruling of fix round 1.** A
released card carries its stream, and each week's report says which of its streams
were held. So a gate that pooled the two streams could release a stream's comments
from one quiet week and one author: the scenario in
`test_two_streams_each_held_once_are_not_cut_by_pooling_them`. The ruling: leg (a)
volume, leg (b) distinct authors at least the threshold, and leg (c) at least two
distinct weeks are each counted over one (section, term, stream)'s held comments.
A run still writes at most one `release_batch` row per (section, term); its
members are the held comments of exactly the streams whose three legs all opened,
and a stream whose legs did not all open stays held.

**Within one stream, leg (b) subsumes leg (c).** A stream is held in a week only
when it has fewer than the threshold of distinct commenters that week, so one
stream's held comments from a single week carry fewer authors than the threshold
by the definition of held; reaching it takes at least two weeks of that stream.
Leg (c) is kept as a written-out leg, but deleting it alone is an equivalent
mutation under per-stream counting, and no test here claims to kill it. What these
tests pin is the per-stream evaluation: pooling the streams in a leg, and
releasing a stream that is not due beside one that is.

**Criterion 4.** A comment with a `release_batch_member` row is never returned by
`visible_comments` for its own week — including after the threshold setting is
lowered from 5 to 4 **inside the test**, which is the ticket's named near miss: a
test that started at 4 never had a release to protect.

**Every batch here is cut by the cutter** (`docs/MISTAKES.md` entry 30), and every
planted count is read back from the database before anything rests on it.

**Marked `invariant`**: §4.1 item 3, and ADR 0153's floors on what a release may
be.

**Which failure a red is, before E5.1-01 lands.** Assertions throughout: on the
current tree a week of `threshold` responses holds nothing, so the per-stream cut
answers 0, and a lowered threshold shows a released week's comments again.
"""

from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest
from fixtures.report_comments import (
    COMMENT_SERVICE_MODULE,
    N_THRESHOLD_VARIABLE,
    SPEC_DEFAULT_N_THRESHOLD,
    VISIBLE_FUNCTION,
    VISIBLE_IS_OWED,
    CommentWorld,
    ReleaseRows,
    configured_threshold,
)
from fixtures.report_views import DEFAULT_COHORT
from fixtures.submit import COMMENT_TEXT_COLUMN

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# Term weeks inside cohort `F`'s run (7 to 12); cohort `Q` runs 7 to 18, so a
# second section shares them.
FIRST_WEEK = 7
SECOND_WEEK = 8
A_SHOWN_WEEK = 9
ANOTHER_SECTION = "Q"

# Criterion 4's two thresholds, from the ticket's own sentence: "including after
# the threshold setting is lowered from 5 to 4". Written out rather than derived,
# because the criterion names them.
STARTING_THRESHOLD = 5
LOWERED_THRESHOLD = 4

HELD_LABEL = "the lab handout and the lecture used different notation for the same thing"
SHOWN_LABEL = "the weekly quiz matched what the lectures had covered"
LATE_LABEL = "a comment that reached this closed week after its release was cut"
OTHER_LABEL = "a quiet week in a section that never crossed its release gate"


def texts_of(comments: Any) -> set[str]:
    """The texts a read answered with."""
    return {str(comment.text) for comment in comments}


def planted_texts(answers: list[Any]) -> set[str]:
    """The texts of planted `answer` rows."""
    return {str(answer[COMMENT_TEXT_COLUMN]) for answer in answers}


def read(
    world: CommentWorld, contract: Any, *, week: int, stream: str, cohort: str = DEFAULT_COHORT
) -> Any:
    """`visible_comments` for one of this world's section-weeks."""
    return contract.visible()(
        world.session,
        section_id=world.section_id(cohort),
        week_id=world.week_id(week),
        stream=stream,
    )


def released(world: CommentWorld, contract: Any, stream: str) -> Any:
    """`released_comments` for this world's section and term, in one stream."""
    return contract.released()(
        world.session,
        section_id=world.section_id(),
        term_id=world.term_id(),
        stream=stream,
    )


# ---------------------------------------------------------------------------
# Criterion 3 — held per stream, cut by the release rules, shown only in a batch.
# ---------------------------------------------------------------------------


def test_a_thin_stream_beside_a_shown_stream_is_held_cut_and_shown_only_in_the_release(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """Criterion 3: a stream is held on its own commenters, whatever its sibling does.

    Two closed weeks. In each, `threshold` students comment about the course —
    so each week holds `threshold` responses and its course stream is shown —
    and a few of them also comment about the instructor: `threshold // 2` in the
    first week and the rest of a threshold's worth in the second. Each instructor
    stream is below the threshold; between them they carry a threshold's worth of
    distinct authors across two weeks, which opens all three of ADR 0152's legs.

    So the cutter must cut exactly one batch holding exactly the instructor-stream
    comments; `released_comments` must answer them for the instructor stream and
    nothing for the course stream; and each week's own read must show its course
    stream and none of its instructor stream.

    **The mutation it kills:** holding decided by the week's response count — each
    week has `threshold` responses, so nothing is held and nothing is cut. **The
    near misses it kills:** a held set that takes the whole week once one stream is
    thin (the course comments would be in the batch); and a shown stream counted
    into the held stream's commenters, which shows the instructor stream under its
    week.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 4, (
        f"The configured n-threshold is {threshold}; this world splits a threshold's worth of "
        "instructor commenters over two weeks, each still under it, which needs 4 or more."
    )
    world.build()

    first_size = threshold // 2
    split = ((FIRST_WEEK, first_size), (SECOND_WEEK, threshold - first_size))
    held: list[Any] = []
    shown: dict[int, list[Any]] = {}
    for week, thin in split:
        world.close_week(week)
        planted = world.week_by_stream(
            term_week=week, both=thin, course_only=threshold - thin, label=HELD_LABEL
        )
        held.extend(planted[contract.instructor_stream])
        shown[week] = planted[contract.course_stream]
        counts = (
            world.responses_in(term_week=week),
            world.commenters_in(term_week=week, stream=contract.instructor_stream),
            world.commenters_in(term_week=week, stream=contract.course_stream),
        )
        assert counts == (threshold, thin, threshold), (
            f"Term week {week} holds (responses, instructor commenters, course commenters) = "
            f"{counts}; this test planted {(threshold, thin, threshold)}. The week's responses "
            "must reach the threshold while its instructor stream's commenters do not, or a gate "
            "counting responses holds the same set this one does."
        )

    cut = contract.cut()(world.session)
    assert cut == 1, (
        f"`{contract.cut_name}` cut {cut} batch(es). Two closed weeks each hold a thin instructor "
        f"stream ({first_size} and {threshold - first_size} distinct commenters, under the "
        f"threshold of {threshold}) beside a course stream of {threshold}. Held per stream, the "
        f"instructor comments are {threshold} distinct authors over two weeks — every leg of ADR "
        "0152's gate open. Nothing cut is holding decided by the week's response count, which is "
        "at the threshold in both weeks."
    )

    released_answers = release_rows.released_answers()
    expected = {world.answer_key(answer) for answer in held}
    assert released_answers == expected, (
        f"In a batch and not a held instructor comment: {sorted(released_answers - expected)}\n"
        f"Held and not in a batch: {sorted(expected - released_answers)}\n\n"
        "The batch holds the thin streams' comments and nothing else. A course comment in it was "
        "on its own week's report already, and is now shown twice — once with its week stripped."
    )

    instructor_release = released(world, contract, contract.instructor_stream)
    assert texts_of(instructor_release) == planted_texts(held), (
        f"`{contract.released_name}` answers {sorted(texts_of(instructor_release))} for the "
        f"instructor stream; the batch holds {sorted(planted_texts(held))}."
    )
    course_release = released(world, contract, contract.course_stream)
    assert tuple(course_release) == (), (
        f"`{contract.released_name}` answers {sorted(texts_of(course_release))} for the course "
        "stream, which was never held: both its weeks had a threshold's worth of commenters."
    )

    for week, _thin in split:
        course = read(world, contract, week=week, stream=contract.course_stream)
        assert texts_of(course) == planted_texts(shown[week]), (
            f"Term week {week}'s course stream answered {sorted(texts_of(course))}; it holds "
            f"{threshold} distinct commenters and is shown in full. Until it answers, the "
            "instructor stream's emptiness below is what this read gives every stream."
        )
        instructor = read(world, contract, week=week, stream=contract.instructor_stream)
        assert tuple(instructor) == (), (
            f"Term week {week}'s instructor stream answered {sorted(texts_of(instructor))} under "
            "its own week. Those comments are below the commenter threshold and in a release "
            "batch; criterion 3 puts them in the batch with no week, and nowhere else."
        )


def test_two_held_streams_of_one_week_are_not_cut_and_only_the_stream_that_opens_is_cut_later(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """One week's two held streams are never a batch; later only the stream that opens is cut.

    One closed week: `threshold - 1` students comment about the instructor only and
    `threshold - 1` others about the course only. Both streams are held. Pooled,
    the held set carries `2 x (threshold - 1)` distinct authors; per stream, each
    carries `threshold - 1` in one week. Nothing may be cut.

    Then one student comments about the instructor in a second closed week. The
    instructor stream's held comments now carry `threshold` authors across two
    weeks — all three legs open — and it is cut. The course stream's held comments
    are still one week's `threshold - 1` and **stay held**: absent from
    `released_comments`, absent from their week's read, in one batch row.

    **Changed in fix round 1, and why.** This test first expected the course
    stream's comments in the batch too, because the gate pooled the two streams.
    The ruling makes every leg per stream, so a stream held in one week only is not
    due whatever its sibling does — releasing it would put a course card in a batch
    whose course comments all come from one quiet week.

    **The mutations it kills:** releasing a non-due stream's comments in a due
    batch (the second half: the course comments go out with the instructor ones);
    and leg (b) pooled across streams with leg (c) deleted (the first half:
    `2 x (threshold - 1)` pooled authors cut one week). Deleting leg (c) alone,
    with the legs per stream, is an equivalent mutation and survives; the first half
    pins leg (b) per stream. **Its pair is the second half's cut**, so a cutter
    that never cuts is red too.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 3, (
        f"The configured n-threshold is {threshold}; two held streams of one week must together "
        "reach it while each stays under it, which needs 3 or more."
    )
    world.build()
    world.close_week(FIRST_WEEK)
    one_week = world.week_by_stream(
        term_week=FIRST_WEEK,
        instructor_only=threshold - 1,
        course_only=threshold - 1,
        label=HELD_LABEL,
    )
    counts = (
        world.responses_in(term_week=FIRST_WEEK),
        world.commenters_in(term_week=FIRST_WEEK, stream=contract.instructor_stream),
        world.commenters_in(term_week=FIRST_WEEK, stream=contract.course_stream),
    )
    assert counts == (2 * (threshold - 1), threshold - 1, threshold - 1), (
        f"The week holds (responses, instructor commenters, course commenters) = {counts}; this "
        f"test planted {(2 * (threshold - 1), threshold - 1, threshold - 1)}."
    )
    authors = 2 * (threshold - 1)
    assert authors >= threshold, (
        f"The two held streams carry {authors} distinct authors pooled, which does not reach the "
        f"threshold of {threshold}; a pooled leg (b) would then refuse too and this half would say "
        "nothing about pooling."
    )

    alone = contract.cut()(world.session)
    assert alone == 0, (
        f"`{contract.cut_name}` cut {alone} batch(es) from one closed week whose two held streams "
        f"carry {authors} distinct authors between them and {threshold - 1} each.\n\n"
        "Every leg is per stream (fix round 1's ruling), and each stream here is one week of "
        f"{threshold - 1} authors. A batch from one week is also the week attribution ADR 0153 "
        "removes, arriving through next Monday's report."
    )
    assert release_rows.members() == [], f"Comments were released: {release_rows.members()}."

    world.close_week(SECOND_WEEK)
    second = world.week_by_stream(term_week=SECOND_WEEK, instructor_only=1, label=HELD_LABEL)
    assert world.commenters_in(term_week=SECOND_WEEK, stream=contract.instructor_stream) == 1

    together = contract.cut()(world.session)
    assert together == 1, (
        f"With a second closed week holding one more instructor comment, `{contract.cut_name}` cut "
        f"{together} batch(es). The instructor stream's held comments now carry {threshold} "
        "distinct authors across two weeks: its three legs are open."
    )
    expected = {
        world.answer_key(answer)
        for answer in [*one_week[contract.instructor_stream], *second[contract.instructor_stream]]
    }
    released_answers = release_rows.released_answers()
    assert released_answers == expected, (
        f"In the batch and not a due instructor comment: {sorted(released_answers - expected)}\n"
        f"Due and not in the batch: {sorted(expected - released_answers)}\n\n"
        "The batch's members are the held comments of exactly the streams whose three legs all "
        f"opened. The course stream is one week of {threshold - 1} authors and is not due; its "
        "comments in the batch would be released course cards that all come from one quiet week."
    )
    assert len(release_rows.batches()) == 1, f"Batches: {release_rows.batches()}."
    course_release = released(world, contract, contract.course_stream)
    assert tuple(course_release) == (), (
        f"`{contract.released_name}` answers {sorted(texts_of(course_release))} for the course "
        "stream, which is not due and stays held."
    )
    still_held = read(world, contract, week=FIRST_WEEK, stream=contract.course_stream)
    assert tuple(still_held) == (), (
        f"The course stream's held comments came back under their week: "
        f"{sorted(texts_of(still_held))}."
    )


def test_two_streams_each_held_once_are_not_cut_by_pooling_them(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """The privacy review's scenario: each stream held in one week, never pooled into a batch.

    Week 1: `threshold` students comment about the instructor (shown) and
    `threshold - 1` others about the course (held). Week 2: `threshold` students
    comment about the course (shown) and one other about the instructor (held).
    Pooled, the held set is `threshold` authors across two weeks and the gate
    opens. Per stream, the course stream's held comments are one week's
    `threshold - 1` authors and the instructor stream's are one author: neither
    stream's legs open, so nothing is cut.

    **What pooling would release.** One released card marked "instructor", and the
    week-2 report says that week's instructor stream was held — so the card is the
    lone week-2 instructor commenter's, named by the ledger beside it (ADR 0153).

    **The control is in the same world**: both shown streams return their comments,
    so the emptiness below is not a read or a cutter that answers nothing everywhere
    (`docs/MISTAKES.md` entry 3).

    **The mutations it kills:** pooling the streams in leg (b) (authors counted
    across both streams' held comments) together with pooling in leg (c) (weeks
    counted across both streams). Either pooled alone still fails here on the other
    leg per stream; the pair is `test_leg_b_counts_authors_within_one_stream`, which
    separates leg (b).
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 2, f"The configured n-threshold is {threshold}; nothing is below it."
    world.build()

    world.close_week(FIRST_WEEK)
    first = world.week_by_stream(
        term_week=FIRST_WEEK,
        instructor_only=threshold,
        course_only=threshold - 1,
        label=HELD_LABEL,
    )
    world.close_week(SECOND_WEEK)
    second = world.week_by_stream(
        term_week=SECOND_WEEK, course_only=threshold, instructor_only=1, label=HELD_LABEL
    )
    counts = tuple(
        world.commenters_in(term_week=week, stream=stream)
        for week in (FIRST_WEEK, SECOND_WEEK)
        for stream in (contract.instructor_stream, contract.course_stream)
    )
    assert counts == (threshold, threshold - 1, 1, threshold), (
        f"The commenters per (week, stream) are {counts}; this test planted "
        f"{(threshold, threshold - 1, 1, threshold)}."
    )

    shown_instructor = read(world, contract, week=FIRST_WEEK, stream=contract.instructor_stream)
    shown_course = read(world, contract, week=SECOND_WEEK, stream=contract.course_stream)
    assert texts_of(shown_instructor) == planted_texts(first[contract.instructor_stream]) and (
        texts_of(shown_course) == planted_texts(second[contract.course_stream])
    ), (
        "A shown stream did not return its comments, so the emptiness asserted below is what this "
        "world answers everywhere."
    )

    cut = contract.cut()(world.session)
    assert cut == 0, (
        f"`{contract.cut_name}` cut {cut} batch(es). The course stream's held comments are one "
        f"week of {threshold - 1} authors and the instructor stream's are one author in one week. "
        f"Pooled they make {threshold} authors over two weeks, but every leg is per stream: a "
        "released card carries its stream, and the week-2 report says its instructor stream was "
        "held, so the one released instructor card would be that week's lone commenter's."
    )
    assert release_rows.members() == [], f"Comments were released: {release_rows.members()}."
    for stream in (contract.instructor_stream, contract.course_stream):
        found = released(world, contract, stream)
        assert (
            tuple(found) == ()
        ), f"`{contract.released_name}` answers {sorted(texts_of(found))} for the {stream} stream."


def test_leg_b_counts_authors_within_one_stream(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """Leg (b) per stream: two streams one author short are not cut; one more author opens one.

    Two closed weeks. The instructor stream's held comments carry `threshold - 1`
    distinct authors split across both weeks; the course stream's carry
    `threshold - 1` different authors across the same two weeks. Pooled, that is
    `2 x (threshold - 1)` authors over two weeks; per stream, each stream spans two
    weeks (leg c open) and is one author short (leg b closed). Nothing is cut.

    Then one more student comments about the instructor in the second week. The
    instructor stream reaches `threshold` authors and is cut, in one batch row; the
    course stream stays held.

    **What it does not isolate, corrected after the verifier's battery.** It was
    written to pin leg (b) per stream, and it does not: each stream's volume here
    is its `threshold - 1` comments, so leg (a) refuses per stream as well, and a
    gate pooling only leg (b) (mutation j) still refuses this world on leg (a).
    That mutation survived the whole suite. It kills pooling legs (a) and (b)
    together. The test that isolates leg (b) is
    `test_leg_b_alone_refuses_a_stream_whose_authors_repeat_across_weeks`.
    **And in the second half:** releasing a non-due stream's comments in a due
    batch — the course comments would go out beside the instructor ones.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 3, (
        f"The configured n-threshold is {threshold}; each stream's `threshold - 1` authors must "
        "split across two weeks with at least one in each, which needs 3 or more."
    )
    world.build()

    short = threshold - 1
    first_size = short // 2
    split = ((FIRST_WEEK, first_size), (SECOND_WEEK, short - first_size))
    held: dict[str, list[Any]] = {contract.instructor_stream: [], contract.course_stream: []}
    for week, size in split:
        world.close_week(week)
        planted = world.week_by_stream(
            term_week=week, instructor_only=size, course_only=size, label=HELD_LABEL
        )
        for stream in held:
            held[stream].extend(planted[stream])
    per_stream = {
        stream: sum(world.commenters_in(term_week=week, stream=stream) for week, _ in split)
        for stream in held
    }
    assert per_stream == {stream: short for stream in held}, (
        f"Distinct commenters per stream across the two weeks: {per_stream}; this test planted "
        f"{short} in each (disjoint people throughout)."
    )

    refused = contract.cut()(world.session)
    assert refused == 0, (
        f"`{contract.cut_name}` cut {refused} batch(es). Each stream's held comments span two "
        f"weeks and carry {short} distinct authors — one short of {threshold}. Pooled across "
        f"streams they carry {2 * short}, which is the count a pooled leg (b) reads."
    )
    assert release_rows.members() == [], f"Comments were released: {release_rows.members()}."

    extra = world.week_by_stream(term_week=SECOND_WEEK, instructor_only=1, label=HELD_LABEL)
    cut = contract.cut()(world.session)
    assert cut == 1, (
        f"With one more instructor commenter the instructor stream's held comments carry "
        f"{threshold} authors across two weeks, and `{contract.cut_name}` cut {cut} batch(es)."
    )
    expected = {
        world.answer_key(answer)
        for answer in [*held[contract.instructor_stream], *extra[contract.instructor_stream]]
    }
    released_answers = release_rows.released_answers()
    assert released_answers == expected, (
        f"In the batch and not a due instructor comment: {sorted(released_answers - expected)}\n"
        f"Due and not in the batch: {sorted(expected - released_answers)}\n\n"
        f"The course stream still has {short} authors and is not due; it stays held."
    )
    assert len(release_rows.batches()) == 1, f"Batches: {release_rows.batches()}."
    course_release = released(world, contract, contract.course_stream)
    assert tuple(course_release) == (), (
        f"`{contract.released_name}` answers {sorted(texts_of(course_release))} for the course "
        "stream, which is not due."
    )


THIRD_HELD_WEEK = 10


def test_leg_b_alone_refuses_a_stream_whose_authors_repeat_across_weeks(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """Leg (b) is the only leg that refuses: the same few people, in both weeks, in each stream.

    Two closed weeks. The instructor stream is written by the same
    `threshold - 1` students in both weeks; the course stream by `threshold - 1`
    other students, also the same in both weeks. No stream-week reaches the
    threshold of commenters, so all four stream-weeks are held. **Per stream, legs
    (a) and (c) are open by construction**: each stream's held volume is
    `2 x (threshold - 1)` comments, at or past the threshold, across two weeks.
    Only leg (b) is closed — `threshold - 1` distinct authors per stream. Pooled
    across streams the authors are `2 x (threshold - 1)`. Nothing may be cut.

    Then one new student comments about the instructor in a third closed week. The
    instructor stream now has `threshold` distinct authors over three weeks and is
    cut; the course stream still has `threshold - 1` and stays held. The new author
    goes in a third week rather than one of the first two because either of those
    weeks would then hold `threshold` instructor commenters, and that stream-week
    would be shown rather than held.

    **The mutation it kills: mutation j**, leg (b) pooled across both streams while
    legs (a) and (c) stay per stream. That mutation cuts the first half. It survived
    the whole suite before this test, because every other world that refuses on
    leg (b) also has each stream's volume under the threshold, so leg (a) refused
    first. **The second half kills** releasing a stream that is not due beside one
    that is, and is the pair: a cutter that never cuts is red there.

    **The readable control** is a shown week in the same world: a stream of
    `threshold` commenters returns its comments, so the empty releases below are
    not a read that answers nothing (`docs/MISTAKES.md` entry 3).
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 3, (
        f"The configured n-threshold is {threshold}; each stream needs `threshold - 1` repeat "
        "authors whose two weeks of comments reach the threshold in volume, which needs 3 or more."
    )
    world.build()

    short = threshold - 1
    instructor_people = [world.respondent() for _ in range(short)]
    course_people = [world.respondent() for _ in range(short)]
    held: dict[str, list[Any]] = {contract.instructor_stream: [], contract.course_stream: []}
    for week in (FIRST_WEEK, SECOND_WEEK):
        world.close_week(week)
        for stream, people in (
            (contract.instructor_stream, instructor_people),
            (contract.course_stream, course_people),
        ):
            for index, person in enumerate(people):
                _response, written = world.submit(
                    term_week=week,
                    student=person,
                    comments={stream: f"{HELD_LABEL} (week {week}, {stream.lower()} {index + 1})"},
                )
                held[stream].append(written[stream])

    counts = {
        (week, stream): world.commenters_in(term_week=week, stream=stream)
        for week in (FIRST_WEEK, SECOND_WEEK)
        for stream in held
    }
    assert set(counts.values()) == {short}, (
        f"Commenters per (week, stream) are {counts}; this test planted {short} in each, so "
        "every stream-week is under the threshold and held."
    )
    volume = {stream: len(answers) for stream, answers in held.items()}
    assert all(found >= threshold for found in volume.values()), (
        f"Each stream's held volume is {volume}; leg (a) must be open per stream ({threshold} or "
        "more) or the refusal below could be leg (a)'s, which is how mutation j survived."
    )

    world.close_week(A_SHOWN_WEEK)
    shown = world.week_by_stream(
        term_week=A_SHOWN_WEEK, instructor_only=threshold, label=SHOWN_LABEL
    )[contract.instructor_stream]
    control = read(world, contract, week=A_SHOWN_WEEK, stream=contract.instructor_stream)
    assert texts_of(control) == planted_texts(
        shown
    ), f"A week of {threshold} instructor commenters answered {sorted(texts_of(control))}."

    refused = contract.cut()(world.session)
    assert refused == 0, (
        f"`{contract.cut_name}` cut {refused} batch(es). Each stream's held comments are "
        f"{volume} comments over two weeks — legs (a) and (c) open — written by {short} distinct "
        f"people, one short of {threshold}. Pooled across streams the authors are {2 * short}: "
        "a cut here is leg (b) counted over both streams."
    )
    assert release_rows.members() == [], f"Comments were released: {release_rows.members()}."
    for stream in held:
        found = released(world, contract, stream)
        assert (
            tuple(found) == ()
        ), f"`{contract.released_name}` answers {sorted(texts_of(found))} for the {stream} stream."

    world.close_week(THIRD_HELD_WEEK)
    fifth = world.week_by_stream(term_week=THIRD_HELD_WEEK, instructor_only=1, label=HELD_LABEL)[
        contract.instructor_stream
    ]
    cut = contract.cut()(world.session)
    assert cut == 1, (
        f"With a fifth distinct instructor author in a third closed week, the instructor stream's "
        f"held comments carry {threshold} authors, and `{contract.cut_name}` cut {cut} batch(es)."
    )
    expected = {world.answer_key(answer) for answer in [*held[contract.instructor_stream], *fifth]}
    released_answers = release_rows.released_answers()
    assert released_answers == expected, (
        f"In the batch and not a due instructor comment: {sorted(released_answers - expected)}\n"
        f"Due and not in the batch: {sorted(expected - released_answers)}\n\n"
        f"The course stream still has {short} distinct authors and is not due; it stays held."
    )
    assert len(release_rows.batches()) == 1, f"Batches: {release_rows.batches()}."
    course_release = released(world, contract, contract.course_stream)
    assert tuple(course_release) == (), (
        f"`{contract.released_name}` answers {sorted(texts_of(course_release))} for the course "
        "stream, which is not due."
    )


# ---------------------------------------------------------------------------
# Criterion 4 — a released comment never comes back under its week.
# ---------------------------------------------------------------------------


def cut_two_held_weeks(
    world: CommentWorld, contract: Any, release_rows: ReleaseRows, *, per_week: int
) -> list[Any]:
    """Two closed weeks of `per_week` instructor-only commenters, cut into one batch.

    Answers the released answers. Called from a test body; every guard it raises
    is a FAILED in that test (`docs/MISTAKES.md` entry 44).
    """
    held: list[Any] = []
    for week in (FIRST_WEEK, SECOND_WEEK):
        world.close_week(week)
        planted = world.week_by_stream(term_week=week, instructor_only=per_week, label=HELD_LABEL)
        held.extend(planted[contract.instructor_stream])
        found = world.commenters_in(term_week=week, stream=contract.instructor_stream)
        assert found == per_week, f"Term week {week} holds {found} instructor commenters."
    cut = contract.cut()(world.session)
    assert cut == 1, (
        f"`{contract.cut_name}` cut {cut} batch(es) over two closed weeks of {per_week} instructor "
        f"commenters each — {2 * per_week} distinct authors across two weeks. Until a release "
        "exists there is nothing for criterion 4 to keep out of its week."
    )
    released_answers = release_rows.released_answers()
    assert released_answers == {
        world.answer_key(answer) for answer in held
    }, f"The batch holds {sorted(released_answers)}, which is not the two weeks' held comments."
    return held


def test_a_released_comment_stays_out_of_its_week_after_the_threshold_drops_to_four(
    comment_world: CommentWorld,
    comment_contract: Any,
    release_rows: ReleaseRows,
    monkeypatch: pytest.MonkeyPatch,
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """Criterion 4 with its named near miss: start at 5, cut, then lower to 4 inside the test.

    At a threshold of 5, two closed weeks of four instructor commenters each are
    held and cut into one batch. The setting is then lowered to 4. Each of those
    weeks now has as many commenters as the threshold — and its comments are in a
    batch, so they must not come back under their week.

    **The pair is in the same world**: a second section's closed week of four
    instructor commenters that was never released (its own gate fails: four
    authors, one week). Lowering the threshold to 4 **does** make it visible, so a
    read that answers nothing after the lowering is red, and the emptiness
    asserted for the released weeks is about the release (`docs/MISTAKES.md`
    entry 3). A week of five commenters in the released section is shown at 5,
    before the lowering, for the same reason.

    **Why the module is re-imported after the lowering**: a service may build its
    threshold from `Settings` at import; re-importing makes this true of one that
    reads per call and of one that reads once, which is the device the module
    beside it uses for the same setting.

    **The mutation it kills:** the week read with no anti-join against
    `release_batch_member` and a count that includes released comments — four
    released commenters reach a threshold of 4, and the released comments are shown
    under their week, beside the batch that already showed them with no week. That
    re-attaches the week ADR 0153 removed. **The near miss it names:** a test that
    began at 4 never cut this release, so the protection was never exercised.
    """
    contract = comment_contract
    world = comment_world
    starting = configured_threshold()
    assert starting == STARTING_THRESHOLD == SPEC_DEFAULT_N_THRESHOLD, (
        f"This test starts at a configured threshold of {starting}, and criterion 4 starts at "
        f"{STARTING_THRESHOLD} — the documented default — and lowers it to {LOWERED_THRESHOLD}. A "
        "different starting value is a failure of the environment this test runs under."
    )
    world.build()
    world.section(ANOTHER_SECTION)

    # The control section's quiet week is planted before the cut, so the cutter
    # meets it and declines it on its own gate (four authors, one week) rather
    # than never seeing it.
    world.close_week(FIRST_WEEK)
    never_released = world.week_by_stream(
        term_week=FIRST_WEEK,
        instructor_only=LOWERED_THRESHOLD,
        label=OTHER_LABEL,
        cohort=ANOTHER_SECTION,
    )[contract.instructor_stream]

    held = cut_two_held_weeks(world, contract, release_rows, per_week=LOWERED_THRESHOLD)

    world.close_week(A_SHOWN_WEEK)
    shown = world.week_by_stream(
        term_week=A_SHOWN_WEEK, instructor_only=STARTING_THRESHOLD, label=SHOWN_LABEL
    )[contract.instructor_stream]
    other_count = world.commenters_in(
        term_week=FIRST_WEEK, stream=contract.instructor_stream, cohort=ANOTHER_SECTION
    )
    assert other_count == LOWERED_THRESHOLD, (
        f"The second section's week holds {other_count} instructor commenters, not "
        f"{LOWERED_THRESHOLD}."
    )
    assert not release_rows.released_answers() & {
        world.answer_key(answer) for answer in never_released
    }, "The second section's comments are in a batch, so they cannot be this test's control."

    # At 5: the shown week answers, and the released weeks do not.
    at_five_shown = read(world, contract, week=A_SHOWN_WEEK, stream=contract.instructor_stream)
    assert texts_of(at_five_shown) == planted_texts(shown), (
        f"At a threshold of {STARTING_THRESHOLD}, a week of {STARTING_THRESHOLD} instructor "
        f"commenters answered {sorted(texts_of(at_five_shown))}."
    )
    for week in (FIRST_WEEK, SECOND_WEEK):
        at_five = read(world, contract, week=week, stream=contract.instructor_stream)
        assert tuple(at_five) == (), (
            f"At a threshold of {STARTING_THRESHOLD}, released term week {week} answered "
            f"{sorted(texts_of(at_five))} under its own week."
        )

    # Lower the setting to 4, inside the test.
    monkeypatch.setenv(N_THRESHOLD_VARIABLE, str(LOWERED_THRESHOLD))
    lowered = configured_threshold()
    assert lowered == LOWERED_THRESHOLD, (
        f"`Settings.n_threshold_default` reads {lowered} after `{N_THRESHOLD_VARIABLE}` was set to "
        f"{LOWERED_THRESHOLD}, so the lowering never reached configuration."
    )
    module = import_app_module(COMMENT_SERVICE_MODULE)
    assert module is not None, f"There is no `{COMMENT_SERVICE_MODULE}` module. {VISIBLE_IS_OWED}"
    lowered_read = getattr(module, VISIBLE_FUNCTION, None)
    assert callable(lowered_read), f"No callable `{VISIBLE_FUNCTION}`. {VISIBLE_IS_OWED}"

    def read_lowered(week: int, cohort: str = DEFAULT_COHORT) -> Any:
        return lowered_read(
            world.session,
            section_id=world.section_id(cohort),
            week_id=world.week_id(week),
            stream=contract.instructor_stream,
        )

    control = read_lowered(FIRST_WEEK, ANOTHER_SECTION)
    assert texts_of(control) == planted_texts(never_released), (
        f"At a lowered threshold of {LOWERED_THRESHOLD}, the second section's never-released week "
        f"of {LOWERED_THRESHOLD} commenters answered {sorted(texts_of(control))}. The lowering is "
        "supposed to make it visible; until it does, the emptiness asserted below is what this "
        "read gives every week."
    )

    held_texts = planted_texts(held)
    for week in (FIRST_WEEK, SECOND_WEEK):
        after = read_lowered(week)
        assert not texts_of(after) & held_texts and tuple(after) == (), (
            f"After the threshold was lowered from {STARTING_THRESHOLD} to {LOWERED_THRESHOLD}, "
            f"released term week {week} answered {sorted(texts_of(after))} under its own week.\n\n"
            "Criterion 4: a comment with a `release_batch_member` row is never returned for its "
            "own week. These comments already appear in a batch with no week; showing them under "
            "the week too re-attaches the week ADR 0153 removed, to a reader who can put this "
            "report beside the gradebook's per-week completion ledger."
        )


def test_a_released_comment_stays_out_of_its_week_when_the_stream_later_reaches_the_threshold(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """The anti-join on its own: a stream reaching the threshold shows only unreleased comments.

    Two weeks of `threshold - 1` instructor commenters are cut into one batch. Then
    a full threshold of new students' instructor comments arrives in the first of
    those weeks. That stream now has the threshold of **unreleased** commenters and
    is shown — and it must show exactly the new comments, none of the released ones.

    **How this world is planted, said plainly.** The product's write path takes no
    response into a closed window, so this is planted directly: it is the one way
    to stand a released comment in a stream that is then shown, which is the state
    the work order's D2 anti-join exists for. Whatever route brings a comment into
    a released stream-week later, the rule is the same.

    **The mutation it kills:** the anti-join against `release_batch_member` dropped
    from the comment read while the count is right — the stream is shown and the
    released comments come back under their week. **The near miss it must
    survive:** suppressing the whole stream because some of it was released, which
    would withhold the new comments; the equality below requires them.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 3, f"The configured n-threshold is {threshold}; this world needs 3 or more."
    world.build()

    held = cut_two_held_weeks(world, contract, release_rows, per_week=threshold - 1)

    late = world.week_by_stream(term_week=FIRST_WEEK, instructor_only=threshold, label=LATE_LABEL)[
        contract.instructor_stream
    ]
    total = world.commenters_in(term_week=FIRST_WEEK, stream=contract.instructor_stream)
    assert total == 2 * threshold - 1, (
        f"The first week's instructor stream holds {total} commenters; this test planted "
        f"{threshold - 1} released and {threshold} new."
    )

    shown = read(world, contract, week=FIRST_WEEK, stream=contract.instructor_stream)
    assert texts_of(shown) == planted_texts(late), (
        f"The first week's instructor stream answered {sorted(texts_of(shown))}.\n\n"
        f"Released and shown under the week: {sorted(texts_of(shown) & planted_texts(held))}\n"
        f"New and missing: {sorted(planted_texts(late) - texts_of(shown))}\n\n"
        "Criterion 4: a comment in a release batch is never returned for its own week. The work "
        "order's D2 excludes every released comment from the read, so a stream shown on its "
        f"{threshold} unreleased commenters shows those {threshold} comments and no others."
    )


def test_released_commenters_do_not_count_toward_their_weeks_threshold(
    comment_world: CommentWorld, comment_contract: Any, release_rows: ReleaseRows
) -> None:
    """The count's half of criterion 4: released authors are not the week's commenters any more.

    Two weeks of `threshold - 1` instructor commenters are cut into one batch. Then
    one new student's instructor comment arrives in the first of those weeks. The
    stream now holds `threshold` commenters in all — `threshold - 1` released and
    one not — and must show nothing: the work order's D1 counts only comments in no
    batch, so one unreleased commenter is below the threshold.

    **The shown stream beside it** is a week of `threshold` instructor commenters in
    the same section, asserted first (`docs/MISTAKES.md` entry 3).

    **The mutation it kills:** released comments counted toward the threshold while
    the read excludes them — the count reaches the threshold, the anti-join leaves
    one comment, and one student's words are shown alone under a week heading. That
    is the defect criterion 1 exists to close, arriving through the release.
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 3, f"The configured n-threshold is {threshold}; this world needs 3 or more."
    world.build()

    cut_two_held_weeks(world, contract, release_rows, per_week=threshold - 1)

    world.close_week(A_SHOWN_WEEK)
    shown_planted = world.week_by_stream(
        term_week=A_SHOWN_WEEK, instructor_only=threshold, label=SHOWN_LABEL
    )[contract.instructor_stream]
    lone = world.week_by_stream(term_week=FIRST_WEEK, instructor_only=1, label=LATE_LABEL)[
        contract.instructor_stream
    ]
    total = world.commenters_in(term_week=FIRST_WEEK, stream=contract.instructor_stream)
    assert total == threshold, (
        f"The first week's instructor stream holds {total} commenters; this test planted "
        f"{threshold - 1} released and one new."
    )

    shown = read(world, contract, week=A_SHOWN_WEEK, stream=contract.instructor_stream)
    assert texts_of(shown) == planted_texts(shown_planted), (
        f"A week of {threshold} instructor commenters answered {sorted(texts_of(shown))}. Until it "
        "answers, the emptiness asserted below is what this read gives every week."
    )

    after = read(world, contract, week=FIRST_WEEK, stream=contract.instructor_stream)
    assert tuple(after) == (), (
        f"The first week's instructor stream answered {sorted(texts_of(after))}. It holds one "
        f"unreleased commenter ({sorted(planted_texts(lone))}) beside {threshold - 1} whose comments "
        "are in a batch.\n\n"
        "The work order's D1 counts only comments with no `release_batch_member` row: released "
        "authors already surfaced in a batch with no week, and counting them here lifts one "
        "student's comment over the threshold to stand alone under its week."
    )
