"""Nothing identifies a comment or its week — E8-01, done-when 6.

> 6. **Nothing identifies a comment or its week.** No comment in the payload
>    carries an `answer_id`, a status, a time or a week. Comment order is
>    randomized as on the instructor's report.

**The members are the work order's, whole**: a week's comment is
`StudentComment {text}` and a released one `StudentReleasedComment {text,
stream}`. An equality over each served object's keys rather than a search for
`answer_id`, because the leak arrives under whatever name the next author picks
(`docs/MISTAKES.md` entry 53). Beside it, the planted comments' answer ids are
searched for in what was served, in both spellings a uuid can take, so an id
riding some other member is caught too.

**The order** (work order decision 4: "reuse its shuffle"). The instructor's
report draws its order from `app.services.report_comments._make_rng`, a private
hook E4-04's suite replaces (`tests/integration/test_the_comment_order_is_
randomized_rather_than_stored.py`). Eight sources must give more than one order
of the same five comments; one source read twice must give one order. The first
kills a stored order; the second kills a student read that shuffles from some
other source, which is not the instructor's shuffle reused. The replacement
accepts any arguments, for that module's reason: the hook's name is settled and
its signature is not.

**Marked `invariant`**: SPEC §4's "comment display order is randomized;
timestamps are never shown with comments" is a confidentiality rule, and a stored
order is a timestamp by another name.

**Which failure a red is, before E8-01 lands:** `student_week.read` fails naming
the four members the work order adds.
"""

import random
from typing import Any

import pytest
from fixtures.report_api import FULL_WEEK_COMMENTS, HELD_COMMENTS
from fixtures.report_comments import comment_service
from fixtures.student_week import (
    COMMENT_MEMBERS,
    CUT_BEFORE_OPENING,
    INSTRUCTOR_NAME,
    RELEASED,
    RELEASED_MEMBERS,
    STREAM,
    STREAM_ORDER,
    a_batch,
    answer_id_of,
    comment_texts,
    read,
    streams_of,
)
from fixtures.the_hold import HoldWorld, report_opens, spellings_of

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

LATEST = 4
RNG_HOOK = "_make_rng"
SEEDS = (1, 2, 3, 5, 8, 13, 21, 34)
A_SEED = SEEDS[0]


def seeded(monkeypatch: pytest.MonkeyPatch, seed: int) -> None:
    """Replace the report's random source with a freshly seeded one, on every call."""
    module = comment_service()
    if not callable(getattr(module, RNG_HOOK, None)):
        pytest.fail(f"`{module.__name__}` exposes no callable `{RNG_HOOK}` (E4-04's seam).")
    monkeypatch.setattr(module, RNG_HOOK, lambda *args, **kwargs: random.Random(seed))  # noqa: S311 — the seam under test wants determinism, not cryptography


def week_one_order(world: HoldWorld, student: Any) -> tuple[str, ...]:
    body, _ = read(world, student, 1)
    return tuple(comment_texts(streams_of(body, "Course week 1")[INSTRUCTOR_NAME]))


def test_a_students_comments_carry_their_text_and_stream_only_and_no_answer_id(
    hold: HoldWorld,
) -> None:
    """Week 1's shown comments and week 4's release group, read an hour after week 4 opened.

    Every comment object under a stream is exactly `{text}`; every released item
    is exactly `{text, stream}`, its stream one of the two names. No answer id of
    any comment on either page is anywhere in either body.

    **The mutations this kills:** the student read returning the instructor's
    card (`answer_id`, `flag`, `decided_by_you`) or `ReportComment` (`status`);
    a `week`, `course_week` or `submitted_at` put on a released item "so the page
    can group it" (ADR 0153: a release carries no week); and an id carried under
    a member nobody listed. **The near miss:** the text and the stream, which are
    exactly what is carried.
    """
    world = hold
    batched = list(HELD_COMMENTS[3])
    batched_ids = [answer_id_of(world, text) for text in batched]
    a_batch(world, cut_at=report_opens(LATEST) - CUT_BEFORE_OPENING, answer_ids=batched_ids)
    shown_ids = [answer_id_of(world, text) for text in FULL_WEEK_COMMENTS]
    student = world.a_student("no-handle", world.taught)
    world.stand_after_the_opening(LATEST)

    week_one, week_one_answer = read(world, student, 1)
    latest, latest_answer = read(world, student, LATEST)

    streams = streams_of(week_one, "Course week 1")
    cards = [comment for name in STREAM_ORDER for comment in streams[name]["comments"]]
    assert len(cards) == len(FULL_WEEK_COMMENTS), (
        f"Course week 1 carries {len(cards)} comments and its shown stream holds "
        f"{len(FULL_WEEK_COMMENTS)}; the key check below would be over too few."
    )
    wrong = [sorted(card) for card in cards if set(card) != COMMENT_MEMBERS]
    assert wrong == [], f"Week comments carry the members {wrong}; `StudentComment` is `{{text}}`."
    items = latest[RELEASED] or []
    assert sorted(item.get("text") for item in items) == sorted(
        batched
    ), f"Week 4's group is {latest[RELEASED]!r}, so the key check below has nothing to read."
    wrong = [sorted(item) for item in items if set(item) != RELEASED_MEMBERS]
    assert wrong == [], f"Released items carry {wrong}; the work order: `{{text, stream}}`."
    assert {item[STREAM] for item in items} <= set(STREAM_ORDER)

    served = week_one_answer.text + latest_answer.text
    carried = [
        str(answer_id)
        for answer_id in (*shown_ids, *batched_ids)
        if any(spelling in served for spelling in spellings_of(answer_id))
    ]
    assert carried == [], f"The student's pages carry the answer ids {carried}."


def test_the_order_a_student_reads_a_weeks_comments_in_moves_with_the_reports_random_source(
    hold: HoldWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eight seeded sources, eight reads of course week 1: one set, more than one order.

    **The mutation this kills:** a stored order — the view's, the answer key's,
    `submitted_at`'s — which no source moves. **The near miss it tolerates:**
    which order any one source gives.
    """
    world = hold
    student = world.a_student("order-moves", world.taught)
    world.stand_after_the_opening(1)

    orders: dict[int, tuple[str, ...]] = {}
    for seed in SEEDS:
        seeded(monkeypatch, seed)
        orders[seed] = week_one_order(world, student)

    assert {tuple(sorted(order)) for order in orders.values()} == {
        tuple(sorted(FULL_WEEK_COMMENTS))
    }, f"Different sources gave different sets of comments: {orders}."
    assert len(set(orders.values())) > 1, (
        f"All {len(SEEDS)} sources gave the order {orders[A_SEED]}. SPEC §4: comment display order "
        "is randomized, and an order that does not move with the report's random source is a "
        "stored one, which is submission order."
    )


def test_one_random_source_gives_a_student_one_order_so_the_shuffle_is_the_reports(
    hold: HoldWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One seeded source, re-patched between two reads: the same order twice.

    **The mutation this kills:** a student read that shuffles from its own
    source (`random.shuffle` with the module's generator, or `ORDER BY random()`)
    rather than through `_make_rng` — the variation above is satisfied by it, and
    it is not the instructor's shuffle reused (decision 4). **The near miss:** the
    variation test above, which a hook-ignoring shuffle passes.
    """
    world = hold
    student = world.a_student("order-repeats", world.taught)
    world.stand_after_the_opening(1)

    seeded(monkeypatch, A_SEED)
    first = week_one_order(world, student)
    seeded(monkeypatch, A_SEED)
    second = week_one_order(world, student)

    assert first, "Course week 1 carried no comments, so two empty orders agree for nothing."
    assert first == second, (
        f"Two reads under a source seeded {A_SEED} gave {first} and {second}; the student's order "
        f"does not come from `{RNG_HOOK}`, the instructor report's random source."
    )
