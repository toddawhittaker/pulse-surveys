"""The first publisher can come back to edit an on-behalf response — E7-10 done-when 5 (and 6's on-behalf half).

> **The first publisher can come back to edit an on-behalf response**
> (code-reviewer MED). Once a week is answered, its on-behalf read answers the
> first publisher with the response; every other reader still gets the one 404.
> The on-behalf page seeds its composer from that answer. A test covers publish, a
> fresh read, and an edit.
>
> **Edit is offered only to the first publisher.** `WeekResponseView` carries
> `can_edit` […] in both instructor and on-behalf views.

Work-order decision 3 settles the shape: the on-behalf read's payload gains
`response: WeekResponseView | null` — null while the week is unanswered; for a
week already answered whose first author is the reader, the read answers 200
with the streams and the response; for anyone else, the same 404 as before.
Decision 4: `can_edit` is "reader is the first row's author".

**What is not read by name.** `WeekResponseView`'s text member: the work order
lists what the view carries, not how each is spelled, so the published text is
looked for among the strings the `response` member carries. `can_edit` is named,
by decision 4.

**The refusals are compared, not transcribed**: each "other reader" answer is
required to be byte-identical (status, body, content headers) to that reader's
answer for a section that does not exist — the one 404 decision 5 settles.

**Which failure a red is.** On the epic head the read of an answered week is the
404 for everyone and the payload has no `response` member: the served and
unanswered tests FAIL on an assertion (status, or the members). The refusal test
is green on the epic head; it holds the denial while the door is widened.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.response_draft import strings_in
from fixtures.response_loop_doors import (
    CAN_EDIT,
    CLEAR_PAST,
    CREATED,
    NOT_FOUND,
    OK,
    ON_BEHALF_AFTER,
    ON_BEHALF_EDIT,
    ON_BEHALF_MEMBERS,
    ON_BEHALF_PUBLISH,
    ON_BEHALF_READ,
    ON_BEHALF_RESPONSE,
    LoopWorld,
    a_reader_for,
    same_refusal,
)
from fixtures.staff_names import RESPONSE_AUTHOR_COLUMN, RESPONSE_BODY_COLUMN, ROLE_COLUMN
from fixtures.student_read import decoded
from fixtures.the_hold import LEAD_FACULTY, sentences_served, spellings_of

pytestmark = pytest.mark.integration

LEADS = "E7-10 the lead's response: the course will post worked derivations after each lecture"
LEADS_EDIT = "E7-10 the lead's edit: the course will post worked derivations within a day"
TEACHERS = "E7-10 the teacher's own response: the problem set moves to Thursday"


def the_response_member(answered: Any, what: str) -> Any:
    """A 200 on-behalf read's `response` member, after holding the payload to its members."""
    assert (
        answered.status_code == OK
    ), f"{what} answered {answered.status_code}. Body {answered.text[:400]!r}."
    body = decoded(answered, what)
    assert isinstance(body, dict) and set(body) == ON_BEHALF_MEMBERS, (
        f"{what} answered {str(body)[:400]!r}; decision 5 with E7-10's decision 3: exactly "
        f"{sorted(ON_BEHALF_MEMBERS)}."
    )
    return body[ON_BEHALF_RESPONSE]


def lead_publishes(world: LoopWorld) -> None:
    world.own_course_required()
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)
    published = world.on_behalf(
        ON_BEHALF_PUBLISH, world.lead, section_id=world.hold.taught, text=LEADS
    )
    assert 200 <= published.status_code < 300, (
        f"Lead A's on-behalf publish past +96h answered {published.status_code}. Body "
        f"{published.text[:400]!r}."
    )


def test_an_unanswered_weeks_on_behalf_read_carries_a_null_response(
    response_loop: LoopWorld,
) -> None:
    """Required, unanswered, past +96h: the read is 200 and `response` is null.

    **The mutation this kills:** the new member omitted while unanswered (the
    composer then cannot tell "nothing yet" from "not sent"), or filled with
    something — a draft, another section's response — before anybody published.
    """
    world = response_loop
    world.own_course_required()
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)

    response = the_response_member(
        world.on_behalf(ON_BEHALF_READ, world.lead, section_id=world.hold.taught),
        "Lead A's on-behalf read of an unanswered week",
    )

    assert (
        response is None
    ), f"An unanswered week's on-behalf read carries `response` = {response!r}."


def test_the_lead_publishes_reads_afresh_and_edits_their_on_behalf_response(
    response_loop: LoopWorld,
) -> None:
    """Publish; a fresh session's read serves the response with `can_edit` true; an edit lands; the next read serves it.

    The read is made with a session minted afresh for the same person — the lead
    coming back another day — so the answer is about the person and not the
    session that published.

    **The mutations this kills:** the answered week still the 404 for its first
    publisher (the boundary review's MED); the first author compared with the
    session rather than the person; `can_edit` false or missing on the on-behalf
    view; an edit that is accepted and then not what the next read serves. **The
    near miss:** `test_an_unanswered_weeks_on_behalf_read_carries_a_null_response`.
    """
    world = response_loop
    lead_publishes(world)
    returning = a_reader_for(world, world.lead.person_id, "lead-returns")

    first = the_response_member(
        world.on_behalf(ON_BEHALF_READ, returning, section_id=world.hold.taught),
        "Lead A's fresh on-behalf read of the week they answered",
    )
    edited = world.on_behalf(
        ON_BEHALF_EDIT, returning, section_id=world.hold.taught, text=LEADS_EDIT
    )
    second = the_response_member(
        world.on_behalf(ON_BEHALF_READ, returning, section_id=world.hold.taught),
        "Lead A's on-behalf read after their edit",
    )
    rows = [
        (str(row[RESPONSE_AUTHOR_COLUMN]), row[ROLE_COLUMN], row[RESPONSE_BODY_COLUMN])
        for row in world.responses_of(world.hold.taught)
    ]

    assert isinstance(first, dict) and LEADS in strings_in(first), (
        f"Lead A's fresh read of the week they answered carries `response` = {first!r}; done-when "
        f"5: the first publisher is answered with the response ({LEADS!r})."
    )
    assert first.get(CAN_EDIT) is True, (
        f"The first publisher's on-behalf view carries `{CAN_EDIT}` = {first.get(CAN_EDIT)!r}. "
        "Done-when 6: true exactly when the reader is the first row's author."
    )
    assert (
        200 <= edited.status_code < 300
    ), f"Lead A's on-behalf edit answered {edited.status_code}. Body {edited.text[:400]!r}."
    lead = str(world.lead.person_id)
    assert rows == [(lead, LEAD_FACULTY, LEADS), (lead, LEAD_FACULTY, LEADS_EDIT)], (
        f"After the publish and the edit the section holds {rows}; one appended row each, both "
        "the lead's."
    )
    assert isinstance(second, dict) and LEADS_EDIT in strings_in(
        second
    ), f"After the edit the read carries `response` = {second!r}; SPEC §5.3: the latest version."


@pytest.mark.invariant
def test_an_answered_week_is_the_one_404_for_every_reader_but_its_first_publisher(
    response_loop: LoopWorld,
) -> None:
    """Lead A answered `F1WW` on behalf; the sibling lead's read: the 404 for a section that does not exist.

    Lead A's own read of the week they answered is taken in the same world and
    required to be served, so a door that refuses everything is red. The other
    case — the reader responsible for the course, the week answered by somebody
    else — is the next test.

    **The mutations this kills:** the first-publisher branch keyed on "the week is
    answered" rather than on the first row's author; the grant check moved after
    the new branch (the sibling lead served lead A's response); a refusal for an
    answered week that differs from the 404 for a section that does not exist (an
    oracle for "somebody answered"); a refusal naming the section or carrying the
    response text.
    """
    world = response_loop
    lead_publishes(world)
    leads_own = world.on_behalf(ON_BEHALF_READ, world.lead, section_id=world.hold.taught)
    siblings = world.on_behalf(ON_BEHALF_READ, world.sibling_lead, section_id=world.hold.taught)
    siblings_nowhere = world.on_behalf(ON_BEHALF_READ, world.sibling_lead, section_id=uuid4())

    assert leads_own.status_code == OK, (
        f"Lead A's read of the week they answered answered {leads_own.status_code}, so the "
        "refusals below may be a door refusing everything."
    )
    assert siblings.status_code == NOT_FOUND and same_refusal(siblings, siblings_nowhere), (
        f"The sibling lead's on-behalf read of a week lead A answered answered "
        f"{siblings.status_code} {siblings.text[:200]!r}; the refusal of a section that does not "
        f"exist is {siblings_nowhere.status_code} {siblings_nowhere.text[:200]!r}."
    )
    assert len(sentences_served(siblings)) == 1, f"The refusal served {siblings.text[:300]!r}."
    leaked = [t for t in (LEADS, *spellings_of(world.hold.taught)) if t in siblings.text]
    assert not leaked, f"The sibling lead's refusal carries {leaked}."


@pytest.mark.invariant
def test_the_responsible_lead_is_refused_a_week_the_teacher_answered(
    response_loop: LoopWorld,
) -> None:
    """The teacher answers; past +96h lead A — responsible, required week — reads: the 404 for nowhere.

    **The mutation this kills:** the new branch serving anyone who could have
    published on behalf (the responsible lead) rather than the first row's author
    — the teacher's response, and their name, handed up-chain through a door
    built for something else. **The near miss:** the previous test's lead A,
    served the week they answered themselves.
    """
    world = response_loop
    world.own_course_required()
    world.stand(CLEAR_PAST)
    assert world.instructor("POST", text=TEACHERS).status_code == CREATED
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)

    answered = world.on_behalf(ON_BEHALF_READ, world.lead, section_id=world.hold.taught)
    nowhere = world.on_behalf(ON_BEHALF_READ, world.lead, section_id=uuid4())

    assert answered.status_code == NOT_FOUND and same_refusal(answered, nowhere), (
        f"Lead A's on-behalf read of a week the teacher answered answered {answered.status_code} "
        f"{answered.text[:200]!r}; the refusal of a section that does not exist is "
        f"{nowhere.status_code} {nowhere.text[:200]!r}. Done-when 5: every reader but the first "
        "publisher gets the one 404."
    )
    assert TEACHERS not in answered.text, "The refusal carries the teacher's response."
