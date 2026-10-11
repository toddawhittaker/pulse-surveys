"""Edit is offered only to the first publisher: two instructors of one section — E7-10 done-when 6.

> **Edit is offered only to the first publisher** (code-reviewer LOW).
> `WeekResponseView` carries `can_edit`; the composer shows Edit only when it is
> true; a two-instructor test pins it.

Work-order decision 4: `can_edit` is "reader is the first row's author", on the
instructor's view and the on-behalf view (the on-behalf half is
`test_the_first_on_behalf_publisher_comes_back_to_edit.py`'s). Until E7-10 a
co-instructor was offered Edit and the `PUT` then answered 409 (SPEC §5.3: only
the person who first published may edit). The composer's rendering is UI and is
not asserted here; what the composer reads is.

**Two instructors of `F1WW`.** The teacher is the report world's own launched
instructor; the co-instructor is a named person given a live section-scoped
`INSTRUCTOR` assignment on `F1WW` and an `INSTRUCTOR` session minted the way every
suite here mints one (`LeadReviewWorld.minted`). Both orders of publishing are
driven, so `can_edit` is shown to follow the first publisher and not the section's
first-listed instructor.

**The server agrees with the flag**: in each order the reader offered no edit is
refused the `PUT` (409) and the reader offered one is accepted, in the same world.

**Which failure a red is.** On the epic head `WeekResponseView` has no `can_edit`:
each test FAILS on the assertion naming the member.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.report_api import INSTRUCTOR_ROLE
from fixtures.response_loop_doors import CAN_EDIT, CLEAR_PAST, CONFLICT, CREATED, OK, LoopWorld
from fixtures.student_read import decoded

pytestmark = pytest.mark.integration

CO_INSTRUCTOR_NAME = "Professor Ilsabet Corrowan"
FIRST = "E7-10 the first publisher's response: the quiz moves to Friday"
EDIT = "E7-10 an edit: the quiz moves to Friday afternoon"


def a_co_instructor(world: LoopWorld) -> str:
    """A second named instructor of `F1WW`, with an `INSTRUCTOR` session of their own; the token."""
    review = world.review
    subject = f"e7-10-co-instructor-{uuid4().hex[:8]}"
    person = world.hold.names.a_named_person(CO_INSTRUCTOR_NAME)
    user_id = review.web_identity.user(platform_id=review._platform_id(), subject=subject)
    review.web_identity.link_person_to_user(person_id=person, user_id=user_id)
    world.hold.names.teaches(person, world.hold.taught)
    return review.minted(role=INSTRUCTOR_ROLE, person_id=person, user_id=user_id, subject=subject)


def can_edit_for(world: LoopWorld, token: str, who: str) -> Any:
    """The instructor's `GET …/response` as `token`: required 200; its `can_edit`."""
    answered = world.instructor("GET", token=token)
    assert answered.status_code == OK, (
        f"{who}'s read of the answered week's response answered {answered.status_code}. Body "
        f"{answered.text[:400]!r}."
    )
    body = decoded(answered, f"{who}'s response read")
    assert isinstance(body, dict) and CAN_EDIT in body, (
        f"{who}'s response read answered {str(body)[:400]!r}; done-when 6: `WeekResponseView` "
        f"carries `{CAN_EDIT}`."
    )
    return body[CAN_EDIT]


@pytest.mark.parametrize("first_publisher", ["the teacher", "the co-instructor"])
def test_only_the_first_publisher_is_offered_the_edit_and_the_server_agrees(
    response_loop: LoopWorld, first_publisher: str
) -> None:
    """One publishes; both read: `can_edit` true for the publisher, false for the other; their `PUT`s agree.

    **The mutations this kills:** `can_edit` true for anyone who teaches the
    section (the boundary review's LOW); `can_edit` keyed on the section's
    first-listed instructor rather than the first row's author (the parameter
    that has the co-instructor publish first). **The near miss, in the same world:** the first publisher's own
    edit, accepted — so the other's 409 is the rule and not a broken edit route.
    """
    world = response_loop
    world.stand(CLEAR_PAST)
    co = a_co_instructor(world)
    tokens = {"the teacher": world.teacher_token, "the co-instructor": co}
    other = "the co-instructor" if first_publisher == "the teacher" else "the teacher"

    published = world.instructor("POST", text=FIRST, token=tokens[first_publisher])
    assert published.status_code == CREATED, (
        f"{first_publisher}'s publish answered {published.status_code}. Body "
        f"{published.text[:400]!r}."
    )
    publishers = can_edit_for(world, tokens[first_publisher], first_publisher)
    others = can_edit_for(world, tokens[other], other)
    refused = world.instructor("PUT", text=EDIT, token=tokens[other])
    accepted = world.instructor("PUT", text=EDIT, token=tokens[first_publisher])

    assert (
        publishers is True
    ), f"{first_publisher}, who published first, reads `{CAN_EDIT}` = {publishers!r}."
    assert others is False, (
        f"{other}, who did not publish, reads `{CAN_EDIT}` = {others!r}. Done-when 6: Edit is "
        "offered only to the first publisher."
    )
    assert (
        refused.status_code == CONFLICT
    ), f"{other}'s edit answered {refused.status_code}; the flag says no and the server must too."
    assert (
        accepted.status_code == OK
    ), f"{first_publisher}'s own edit answered {accepted.status_code}. Body {accepted.text[:300]!r}."
