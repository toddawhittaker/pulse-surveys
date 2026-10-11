"""On behalf refuses a sibling lead's section identically in every state — E7-03, done-when 9 (SPEC §4.1 item 2).

> **No sibling course.** No route in this ticket reads, sets, lists or publishes
> for a course outside the reader's own `lead_review_courses`. Each refusal is the
> same 404 and names nothing of the section. The refusal for a sibling's section
> is byte-identical whether that week is encouraged or required, before or after
> + 96h, and answered or not. Marked `invariant`.

**The sequence is the subject** (`docs/MISTAKES.md` entry 51). Lead A asks every
on-behalf door about the sibling lead's section while that section's week moves
through five states — encouraged early, encouraged late, required late, required
early, and answered — and each answer is compared with A's answer for a section
that does not exist. A refusal that varies with the sibling's state is an oracle
for it, whatever its status says.

**Denial, not absence**: each answer is required to be the 404, carrying one
sentence of `app/copy/response_loop.py`, and to name neither the section's code
nor its key. **And the door is shown to serve**: in the same world, past +96h,
A's own `Q1WW` is read 200, so a door refusing everything is red.

The policy read, the policy write and the owed read have their own sibling tests
(`test_a_sibling_leads_policy_setting_reaches_nobody_else.py`,
`test_a_policy_switch_through_the_route_holds_only_the_readers_courses.py`,
`test_the_responses_owed_read_lists_only_the_readers_owed_weeks.py`).

**Which failure a red is, before E7-03 lands.** `find_route` fails naming the
on-behalf route.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.lead_review import SIBLING_COHORT
from fixtures.report_api import UNTAUGHT_COHORT
from fixtures.response_loop_doors import (
    CLEAR_PAST,
    NOT_FOUND,
    OK,
    ON_BEHALF_AFTER,
    ON_BEHALF_DOORS,
    ON_BEHALF_READ,
    ON_BEHALF_WEEK,
    LoopWorld,
    OnBehalfDoor,
    same_refusal,
)
from fixtures.the_hold import (
    FIRST_ROW_AFTER_OPENING,
    INSTRUCTOR,
    report_opens,
    sentences_served,
    spellings_of,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

EARLY = CLEAR_PAST
LATE = ON_BEHALF_AFTER + CLEAR_PAST


@pytest.mark.parametrize("door", ON_BEHALF_DOORS, ids=lambda door: door.name)
def test_the_refusal_of_a_sibling_leads_section_never_moves_with_its_state(
    response_loop: LoopWorld, door: OnBehalfDoor
) -> None:
    """Five states of the sibling's week, five answers: each the 404 for a section that does not exist.

    **The mutations this kill:** a door that checks "required, unanswered, past
    +96h" before it checks the reader's grant (the required-late state is served,
    or refused with a different sentence from the encouraged one — done-when 9's
    oracle); a 409 for "already answered" reached before the grant; a refusal
    naming the section; any write or model call on a refused request. **The near
    miss:** A's own `Q1WW`, read 200 in the required-late state.
    """
    world = response_loop
    world.hold.windows_for(SIBLING_COHORT, ON_BEHALF_WEEK)
    world.hold.windows_for(UNTAUGHT_COHORT, ON_BEHALF_WEEK)
    world.own_course_required()
    sibling = world.hold.sibling_course_section
    nowhere = uuid4()
    rows, calls = world.response_count(), world.model_calls()
    answers: dict[str, tuple[Any, Any]] = {}

    def ask(state: str) -> None:
        answers[state] = (
            world.on_behalf(door, world.lead, section_id=sibling),
            world.on_behalf(door, world.lead, section_id=nowhere),
        )

    world.stand(EARLY)
    ask("encouraged, before +96h")
    world.stand(LATE)
    ask("encouraged, past +96h")
    world.sibling_course_required()
    ask("required, past +96h, unanswered")
    own = world.on_behalf(ON_BEHALF_READ, world.lead, section_id=world.hold.sibling_section)
    world.stand(EARLY)
    ask("required, before +96h")
    world.hold.a_response(
        section_id=sibling,
        course_week=ON_BEHALF_WEEK,
        author=world.hold.person(world.hold.names.sibling_course_teacher).person_id,
        role=INSTRUCTOR,
        body="E7-03 the sibling course's own response",
        published_at=report_opens(ON_BEHALF_WEEK) + FIRST_ROW_AFTER_OPENING,
    )
    world.stand(LATE)
    ask("required, past +96h, answered")

    assert own.status_code == OK, (
        f"Lead A's own `Q1WW` past +96h answered {own.status_code}, so the refusals below may be a "
        "door refusing everything."
    )
    first = answers["encouraged, before +96h"][0]
    for state, (theirs, missing) in answers.items():
        assert theirs.status_code == NOT_FOUND, (
            f"Lead A's on-behalf {door.name} for the sibling lead's section ({state}) answered "
            f"{theirs.status_code}. Body {theirs.text[:300]!r}."
        )
        assert same_refusal(theirs, missing), (
            f"({state}) The refusal of the sibling's section {theirs.text[:200]!r} is not the "
            f"refusal of a section that does not exist {missing.text[:200]!r}."
        )
        assert same_refusal(theirs, first), (
            f"The refusal moved with the sibling's week: ({state}) {theirs.text[:200]!r} against "
            f"(encouraged, before +96h) {first.text[:200]!r}. Done-when 9."
        )
        assert len(sentences_served(theirs)) == 1, f"({state}) served {theirs.text[:300]!r}."
        named = [
            token
            for token in (world.hold.code_of(SIBLING_COHORT), *spellings_of(sibling))
            if token in theirs.text
        ]
        assert not named, f"({state}) The refusal names {named}."
    assert world.response_count() - rows == 1, (
        "Rows were written while the sibling's week was refused; the one expected row is the "
        "sibling teacher's own, planted above."
    )
    assert world.model_calls() == calls, "A refused on-behalf request reached the provider."
