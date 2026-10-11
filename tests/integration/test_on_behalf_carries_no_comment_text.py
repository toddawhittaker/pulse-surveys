"""On behalf carries no comment text, at any threshold — E7-03, done-when 11 (SPEC §5.5).

> **No comment text up-chain.** The on-behalf payload carries no comment text at
> any threshold; a planted distinctive comment is absent from every on-behalf
> response body. Marked `invariant`.

Two distinctive comments are planted in course week 1 of `F1WW`: one in the
instructor stream, which is shown (the canonical five commenters and more), and
one in the course stream, which is held (one commenter). Lead A then reads,
drafts, checks and publishes on behalf past +96h, and **every** response body,
headers included, is searched for both.

**Absence means something only beside presence** (`docs/MISTAKES.md` entry 3), so
two controls run in the same world: the teacher's own report for the week carries
the shown comment (it is a real, visible comment, not a planting that failed), and
each on-behalf request is required to succeed — a refusal carries no comment text
for the wrong reason. The on-behalf read is also held to decision 5's members
exactly, so a `comments` member cannot ride in empty today and full tomorrow.

What the draft *sent the provider* is not this criterion's subject (the ticket
names response bodies); the summary-filter module reads the prompt.

**Which failure a red is, before E7-03 lands.** `find_route` fails naming the
on-behalf route.
"""

import pytest
from fixtures.report_views import COURSE_STREAM
from fixtures.response_loop_doors import (
    CLEAR_PAST,
    OK,
    ON_BEHALF_AFTER,
    ON_BEHALF_DOORS,
    ON_BEHALF_MEMBERS,
    ON_BEHALF_READ,
    ON_BEHALF_WEEK,
    STREAM_MEMBERS,
    STREAMS,
    LoopWorld,
)
from fixtures.student_read import decoded, response_surface

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

SHOWN = "E7-03 shown-stream comment: Quillmore Tessaract said the marking felt arbitrary"
HELD = "E7-03 held-stream comment: the Vexborough reading pack never reached me at all"
# A run of each that a paraphrase would not reproduce, searched as well as the whole text.
SHOWN_RUN = "Quillmore Tessaract"
HELD_RUN = "Vexborough reading pack"


def test_no_on_behalf_response_body_carries_a_comment_at_either_threshold(
    response_loop: LoopWorld,
) -> None:
    """Read, draft, check, publish and edit past +96h: neither planted comment in any body.

    **The mutations this kill:** the on-behalf read built from the report payload
    with its comments (the shown comment served to the lead); a held stream's
    comment let through because "the lead is above the instructor"; a draft or
    check answer echoing the gather back; a publish answer carrying the week's
    view. **The near misses:** every request succeeds, and the teacher's own
    report carries the shown comment.
    """
    world = response_loop
    world.own_course_required()
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)
    world.a_comment(SHOWN)
    world.a_comment(HELD, stream=COURSE_STREAM)

    teachers = world.draft.report(course_week=ON_BEHALF_WEEK)
    assert teachers.status_code == OK and SHOWN in teachers.text, (
        f"The teacher's own report for the week answered {teachers.status_code} and does not carry "
        "the shown comment, so its absence below would prove nothing."
    )

    bodies: dict[str, str] = {}
    for door in ON_BEHALF_DOORS:
        answered = world.on_behalf(door, world.lead, section_id=world.hold.taught)
        assert 200 <= answered.status_code < 300, (
            f"Lead A's on-behalf {door.name} answered {answered.status_code}; a refusal carries no "
            f"comment for the wrong reason. Body {answered.text[:300]!r}."
        )
        bodies[door.name] = response_surface(answered)

    carried = {
        name: [text for text in (SHOWN, HELD, SHOWN_RUN, HELD_RUN) if text in body]
        for name, body in bodies.items()
    }
    assert not any(
        carried.values()
    ), f"On-behalf responses carry comment text: {carried}. Done-when 11."


def test_the_on_behalf_read_has_no_member_a_comment_could_ride_in(response_loop: LoopWorld) -> None:
    """The read's members are decision 5's exactly, top level and per stream.

    **The mutation this kills:** a `comments` (or `released`, or `excerpts`) member
    added to the payload, empty in this world and full in the next.
    """
    world = response_loop
    world.own_course_required()
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)

    answered = world.on_behalf(ON_BEHALF_READ, world.lead, section_id=world.hold.taught)

    assert answered.status_code == OK, f"The on-behalf read answered {answered.status_code}."
    body = decoded(answered, "The on-behalf read")
    assert isinstance(body, dict) and set(body) == ON_BEHALF_MEMBERS, (
        f"The on-behalf read carries {sorted(body) if isinstance(body, dict) else body!r}; "
        f"decision 5: exactly {sorted(ON_BEHALF_MEMBERS)}."
    )
    extra = [sorted(set(s) - STREAM_MEMBERS) for s in body[STREAMS] if set(s) != STREAM_MEMBERS]
    assert body[STREAMS] and not extra, (
        f"The on-behalf read's stream entries carry members {extra} beyond decision 5's "
        f"{sorted(STREAM_MEMBERS)} (or there are none: {body[STREAMS]!r})."
    )
