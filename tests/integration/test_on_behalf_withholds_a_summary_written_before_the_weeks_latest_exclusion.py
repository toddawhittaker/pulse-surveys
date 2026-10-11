"""On behalf withholds a summary written before the week's latest exclusion — E7-03, done-when 10.

> **No summary written before the week's latest exclusion.** A summary is withheld
> when any decision in that section-week that removes a comment from the shown
> set (an exclusion, or the undo of a keep) is not strictly earlier than the
> summary's `generated_at`. The instructor excludes a comment after the week's
> summary was written; the lead's on-behalf read carries no summary for that
> stream, and the draft gather for the lead carries none either. The undo of a
> keep withholds the same way. A tie between the decision and `generated_at`
> withholds, and is tested. A summary written strictly after every such decision
> is served. Marked `invariant`.

**Every decision is the teacher's, made through E6-03's own route**, and its
stored instant is read back off the row; the summary is then planted with a
`generated_at` this suite chooses *relative to that instant* — one second before,
the same instant, one second after. So nothing here depends on which clock the
decision route stamps with.

**Two surfaces per case**: the on-behalf read (`summary_text`, and the planted
text anywhere in the body), and the draft gather — what the on-behalf draft
**sent the provider**. The served case requires the summary in both, so the
withheld cases cannot pass on a read or a prompt that never carries a summary at
all (`docs/MISTAKES.md` entry 3). Themes are planted with the summary and required
absent wherever the summary is withheld; their presence when served is not
asserted, because the ticket does not say the on-behalf draft sends themes.

**Entry 51's pair**: one test reads the on-behalf view either side of an
exclusion made after the summary was written — served, then withheld.

The week is course week 1 of `F1WW`: the instructor stream shown, lead A
responsible, required, unanswered, past +96h.

**Which failure a red is, before E7-03 lands.** `find_route` fails naming the
on-behalf route.
"""

from datetime import datetime, timedelta
from typing import Any

import pytest
from fixtures.instructor_decisions import UNDO
from fixtures.moderation import HARMFUL
from fixtures.response_loop_doors import (
    CLEAR_PAST,
    OK,
    ON_BEHALF_AFTER,
    ON_BEHALF_DRAFT,
    ON_BEHALF_MEMBERS,
    ON_BEHALF_READ,
    ON_BEHALF_WEEK,
    ONE_SECOND,
    STREAM,
    STREAM_MEMBERS,
    STREAMS,
    SUMMARY_TEXT,
    LoopWorld,
)
from fixtures.student_read import decoded
from fixtures.the_hold import report_opens

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

SUMMARY = "E7-03 the stored instructor-stream summary: the proofs went too fast for most"
THEME = "E7-03 proofs in the Tuesday lecture"
THEME_COUNT = 731
EXCLUDED = "E7-03 a comment the instructor excluded: the lecturer mumbled through every proof"
KEPT_THEN_UNDONE = "E7-03 a flagged comment kept and then undone: the lecturer is useless at this"
RESTORED = "E7-03 a comment excluded and then restored: the problem sets are far too long"


def instructor_stream_summary(world: LoopWorld, answered: Any) -> Any:
    """The on-behalf read's instructor-stream `summary_text`, after requiring decision 5's shape."""
    assert answered.status_code == OK, (
        f"Lead A's on-behalf read past +96h answered {answered.status_code}. Body "
        f"{answered.text[:400]!r}."
    )
    body = decoded(answered, "The on-behalf read")
    assert isinstance(body, dict) and set(body) == ON_BEHALF_MEMBERS, (
        f"The on-behalf read answered {str(body)[:400]!r}; decision 5: exactly "
        f"{sorted(ON_BEHALF_MEMBERS)}."
    )
    entries = [s for s in body[STREAMS] if str(s.get(STREAM, "")).lower() == "instructor"]
    assert len(entries) == 1 and set(entries[0]) == STREAM_MEMBERS, (
        f"The on-behalf read's streams are {body[STREAMS]!r}; decision 5: one entry per stream, "
        f"each exactly {sorted(STREAM_MEMBERS)}."
    )
    return entries[0][SUMMARY_TEXT]


def what_the_draft_sent(world: LoopWorld) -> str:
    before = world.model_calls()
    drafted = world.on_behalf(ON_BEHALF_DRAFT, world.lead, section_id=world.hold.taught)
    assert (
        200 <= drafted.status_code < 300
    ), f"Lead A's on-behalf draft answered {drafted.status_code}. Body {drafted.text[:400]!r}."
    sent = world.provider.text_since(before)
    assert sent.strip(), "The on-behalf draft answered 2xx and sent the provider nothing."
    return sent


def stand_in_the_week(world: LoopWorld) -> None:
    world.own_course_required()
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)


def plant(world: LoopWorld, generated_at: datetime) -> None:
    world.plant_summary(text=SUMMARY, themes=((THEME, THEME_COUNT),), generated_at=generated_at)


def where_the_summary_reached(world: LoopWorld) -> list[str]:
    """Each surface that carries the stored summary or its theme; empty when it is withheld.

    Returned rather than asserted here, so each `invariant` test asserts in its own
    body (`scripts/ci/check_invariant_assertions.py`).
    """
    read = world.on_behalf(ON_BEHALF_READ, world.lead, section_id=world.hold.taught)
    summary_text = instructor_stream_summary(world, read)
    sent = what_the_draft_sent(world)
    reached: list[str] = []
    if summary_text is not None:
        reached.append(f"the read's instructor-stream summary_text ({summary_text!r})")
    if SUMMARY in read.text or THEME in read.text:
        reached.append("the read's body")
    if SUMMARY in sent or THEME in sent:
        reached.append("what the on-behalf draft sent the provider (the gather)")
    return reached


@pytest.mark.parametrize(
    ("offset", "why"),
    [
        (-ONE_SECOND, "written one second before the exclusion"),
        (timedelta(0), "written at the same instant as the exclusion (the tie)"),
    ],
)
def test_a_summary_not_strictly_after_an_exclusion_is_withheld_from_the_read_and_the_draft(
    response_loop: LoopWorld, offset: timedelta, why: str
) -> None:
    """The teacher excludes a comment; a summary dated one second before it, or at it: withheld twice over.

    **The mutations this kill:** no filter (the stored summary served to the lead
    and sent in the draft); a filter on the read and not in the gather, or the
    other way round; `>` where the ticket says "not strictly earlier" (the tie
    served); the comparison against the earliest decision rather than the latest.
    **The near miss:** `test_a_summary_written_one_second_after_every_removal_is_served`.
    """
    world = response_loop
    stand_in_the_week(world)
    world.a_comment(EXCLUDED)
    decided = world.exclude(EXCLUDED)
    plant(world, decided + offset)

    reached = where_the_summary_reached(world)

    assert not reached, f"A summary {why} reached {reached}. Done-when 10: withheld from both."


def test_a_summary_written_before_the_undo_of_a_keep_is_withheld(response_loop: LoopWorld) -> None:
    """A flagged comment kept, then the keep undone; the summary dated one second before the undo: withheld.

    The undo returns the comment to review — out of the shown set — so it removes
    a comment the summary may carry.

    **The mutations this kill:** only `EXCLUDED` rows counted as removals (the undo
    of a keep missed); the undo's restored state read as shown. **The near miss:**
    the keep itself, earlier, which removes nothing.
    """
    world = response_loop
    stand_in_the_week(world)
    world.a_comment(KEPT_THEN_UNDONE, verdict=HARMFUL)
    undone = world.keep_then_undo(KEPT_THEN_UNDONE)
    plant(world, undone - ONE_SECOND)

    reached = where_the_summary_reached(world)

    assert (
        not reached
    ), f"A summary written one second before the undo of a keep reached {reached}. Done-when 10."


def test_a_summary_written_one_second_after_every_removal_is_served(
    response_loop: LoopWorld,
) -> None:
    """An exclusion and the undo of a keep; the summary dated one second after the later: served twice over.

    The control every withheld case leans on: the read's `summary_text` is the
    summary, and the draft sent it.

    **The mutations this kill:** a filter that withholds any summary in a week
    with any decision; a filter keyed on the summary's age rather than on the
    decisions.
    """
    world = response_loop
    stand_in_the_week(world)
    world.a_comment(EXCLUDED)
    world.a_comment(KEPT_THEN_UNDONE, verdict=HARMFUL)
    first = world.exclude(EXCLUDED)
    second = world.keep_then_undo(KEPT_THEN_UNDONE)
    plant(world, max(first, second) + ONE_SECOND)

    read = world.on_behalf(ON_BEHALF_READ, world.lead, section_id=world.hold.taught)
    summary_text = instructor_stream_summary(world, read)
    sent = what_the_draft_sent(world)

    assert summary_text == SUMMARY, (
        f"The on-behalf read carries {summary_text!r} for a summary written after every removal. "
        "Done-when 10: served."
    )
    assert SUMMARY in sent, "The on-behalf draft did not send the provider a summary it may carry."


def test_a_summary_between_two_removals_is_withheld_by_the_later(response_loop: LoopWorld) -> None:
    """An exclusion, then the undo of a keep; the summary dated between them: withheld.

    **The mutation this kills:** the summary compared with the week's first
    removal rather than its latest. **The near miss:** the served case above.
    """
    world = response_loop
    stand_in_the_week(world)
    world.a_comment(EXCLUDED)
    world.a_comment(KEPT_THEN_UNDONE, verdict=HARMFUL)
    first = world.exclude(EXCLUDED)
    second = world.keep_then_undo(KEPT_THEN_UNDONE)
    assert second > first, (
        f"The undo is stored at {second} and the exclusion at {first}; this case needs the undo "
        "strictly later. A broken world, not a red."
    )
    plant(world, first + (second - first) / 2)

    reached = where_the_summary_reached(world)

    assert not reached, (
        f"A summary written after the exclusion and before the later undo of a keep reached "
        f"{reached}. Done-when 10: the latest removal decides."
    )


def test_a_decision_that_restores_a_comment_withholds_nothing(response_loop: LoopWorld) -> None:
    """An exclusion, the summary one second after it, then the exclusion undone: served.

    The undo of an exclusion returns the comment to the shown set; it removes
    nothing, so a summary written before it carries nothing the reader may not see.

    **The mutation this kills:** any decision after `generated_at` withholding,
    whatever it does. **The near miss:** the undo of a keep, which does withhold.
    """
    world = response_loop
    stand_in_the_week(world)
    world.a_comment(RESTORED)
    excluded = world.exclude(RESTORED)
    plant(world, excluded + ONE_SECOND)
    world.decide(RESTORED, UNDO)

    read = world.on_behalf(ON_BEHALF_READ, world.lead, section_id=world.hold.taught)
    assert (
        instructor_stream_summary(world, read) == SUMMARY
    ), f"An exclusion undone after the summary was written withheld it: {read.text[:300]!r}."


def test_two_reads_either_side_of_an_exclusion_serve_then_withhold(
    response_loop: LoopWorld,
) -> None:
    """Entry 51: the summary written an hour before; read; the teacher excludes; read again.

    **The mutations this kill:** a filter computed once (cached) per summary;
    a filter that reads the decisions only when the summary is generated. **The
    near miss:** the first read, served.
    """
    world = response_loop
    stand_in_the_week(world)
    world.a_comment(EXCLUDED)
    generated_at = report_opens(ON_BEHALF_WEEK) + ON_BEHALF_AFTER
    plant(world, generated_at)

    first = world.on_behalf(ON_BEHALF_READ, world.lead, section_id=world.hold.taught)
    first_summary = instructor_stream_summary(world, first)
    decided = world.exclude(EXCLUDED)
    second = world.on_behalf(ON_BEHALF_READ, world.lead, section_id=world.hold.taught)
    second_summary = instructor_stream_summary(world, second)

    assert (
        decided >= generated_at
    ), f"The exclusion is stored at {decided}, before the summary; this pair needs it after."
    assert first_summary == SUMMARY, f"Before the exclusion the read carried {first_summary!r}."
    assert (
        second_summary is None and SUMMARY not in second.text
    ), f"After the exclusion the read still carries {second_summary!r}. Done-when 10."
