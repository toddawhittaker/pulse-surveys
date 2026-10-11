"""A draft is written in its author's role: the instructor's, the lead's, the chair's — E7-10 done-when 4.

> **An on-behalf draft is written in the lead's voice** (prompt-eval MED).
> `response_draft.v3.md` takes the author's role and frames the draft as a named
> leadership role writing to the class; for on-behalf it never promises an action
> in the instructor's voice. The instructor path uses v3 too, with the instructor
> role.

Work-order decision 2 settles the mechanism and its three values: one template
with an `{{AUTHOR_ROLE}}` slot, filled "the course's instructor", "the course's
Lead Faculty" or "the department chair". Until E7-10 the on-behalf draft was sent
`response_draft.v2`, which tells the model to "write as the instructor, first
person" — so a lead's draft promised, in the instructor's voice, what only the
instructor can do (SPEC §5.3).

**Measured on the wire**: what the application's gateway sent the provider this
suite runs, case-insensitively, so the assertion is about the role the model was
told and not about where in the template the slot sits. Whether a real model then
keeps to that voice is a distribution, answered by the eval set's on-behalf
family (`tests/evals/response_draft/cases.py`), not here.

**What is deliberately not asserted.** That the lead's prompt never mentions "the
course's instructor": decision 2 has the on-behalf prompt say the writer is *not*
the instructor, which may well name the instructor. Only the instructor's own
prompt is held to carrying neither leadership role.

**Which failure a red is.** On the epic head every path sends v2, which names no
role phrase: each test FAILS on an assertion naming the missing role.
"""

from typing import Any

import pytest
from fixtures.lead_review import UNMAPPED_COHORT
from fixtures.response_draft import A_PLAIN_DRAFT, draft_answer
from fixtures.response_loop_doors import (
    CLEAR_PAST,
    ON_BEHALF_AFTER,
    ON_BEHALF_DRAFT,
    ON_BEHALF_WEEK,
    LoopWorld,
)

pytestmark = pytest.mark.integration

# Work-order decision 2's three role phrases, transcribed.
THE_INSTRUCTOR = "the course's instructor"
THE_LEAD = "the course's Lead Faculty"
THE_CHAIR = "the department chair"


def sent_by(world: LoopWorld, ask: Any, what: str) -> str:
    """Script a plain draft, run `ask`, require a 2xx and a model call; what the request carried, lower-cased."""
    world.provider.script(draft_answer(A_PLAIN_DRAFT))
    before = world.model_calls()
    answered = ask()
    assert 200 <= answered.status_code < 300, (
        f"{what} answered {answered.status_code} to a usable model answer. Body "
        f"{answered.text[:400]!r}."
    )
    sent = world.provider.text_since(before)
    assert sent.strip(), f"{what} answered {answered.status_code} and sent the provider nothing."
    return sent.lower()


def on_behalf_draft(world: LoopWorld, reader: Any, section_id: Any) -> Any:
    url = world.on_behalf_url(ON_BEHALF_DRAFT, section_id=section_id, course_week=ON_BEHALF_WEEK)
    return world.ask("POST", url, token=reader.token, json={})


def test_the_instructors_draft_is_framed_as_the_courses_instructor(
    response_loop: LoopWorld,
) -> None:
    """The teacher's own draft: the prompt names "the course's instructor" and neither leadership role.

    **The mutations this kills:** the instructor path left on v2 (no role phrase);
    the slot filled from the reader's landing role or a constant, so the
    instructor is framed as a lead or a chair.
    """
    world = response_loop
    world.stand(CLEAR_PAST)

    sent = sent_by(world, lambda: world.draft.draft(), "The teacher's draft")

    assert THE_INSTRUCTOR.lower() in sent, (
        f"The teacher's draft prompt does not frame its author as {THE_INSTRUCTOR!r}. Done-when 4: "
        "the instructor path uses v3 too, with the instructor role."
    )
    named = [role for role in (THE_LEAD, THE_CHAIR) if role.lower() in sent]
    assert not named, f"The teacher's draft prompt frames its author as {named}."


def test_a_leads_on_behalf_draft_is_framed_as_the_courses_lead_faculty(
    response_loop: LoopWorld,
) -> None:
    """Lead A's on-behalf draft past +96h: the prompt names "the course's Lead Faculty".

    **The mutations this kills:** the on-behalf path still sending v2 ("write as
    the instructor"); v3 with the slot filled "the course's instructor" on every
    path. **The twin:** the teacher's prompt above, which does not carry it.
    """
    world = response_loop
    world.own_course_required()
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)

    sent = sent_by(
        world,
        lambda: on_behalf_draft(world, world.lead, world.hold.taught),
        "Lead A's on-behalf draft",
    )

    assert THE_LEAD.lower() in sent, (
        f"Lead A's on-behalf draft prompt does not frame its author as {THE_LEAD!r}. Done-when 4: "
        "an on-behalf draft is written in the lead's voice, never the instructor's."
    )
    assert THE_CHAIR.lower() not in sent, "Lead A's prompt frames her as the department chair."


def test_a_chairs_on_behalf_draft_is_framed_as_the_department_chair(
    response_loop: LoopWorld,
) -> None:
    """The chair's on-behalf draft for the unled course's section: the prompt names "the department chair".

    **The mutations this kill:** a slot filled "Lead Faculty" for every on-behalf
    draft (the role read from the door rather than from the role the reader holds
    the course by). **The twin:** lead A's prompt above.
    """
    world = response_loop
    world.hold.windows_for(UNMAPPED_COHORT, ON_BEHALF_WEEK)
    world.unmapped_course_required()
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)

    sent = sent_by(
        world,
        lambda: on_behalf_draft(world, world.chair, world.hold.unmapped_section),
        "The chair's on-behalf draft",
    )

    assert THE_CHAIR.lower() in sent, (
        f"The chair's on-behalf draft prompt does not frame its author as {THE_CHAIR!r}. "
        "Done-when 4 and work-order decision 2."
    )
    assert THE_LEAD.lower() not in sent, "The chair's prompt frames them as the course's lead."
