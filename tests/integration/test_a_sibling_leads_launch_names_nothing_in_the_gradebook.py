"""A Lead Faculty launching from a sibling lead's course creates no gradebook column — §4.1 invariant 2.

E3-08's boundary round, IC-M2. `tests/integration/test_a_staff_launch_binds_
only_inside_the_launchers_purview.py` holds the **roster** half of this actor's
refusal — nothing bound, no address stored, a `context_outside_purview` defect —
and marks it `invariant`. The **gradebook** half had no test at all: whether that
same launch writes a graded column into somebody else's course.

**Why it is a §4.1 invariant and not a tidiness rule.** §2.1 is unambiguous at
this grain — "a Lead Faculty's grant is only the courses they lead (never sibling
leads' courses, at any point in the union)" — and §4.1 invariant 2 states it as a
hard one: "A Lead Faculty assignment never grants sibling leads' courses, at any
point in the purview union computation." A line item is not a read, but creating
one is this tool acting inside a course the launcher has no grant over, and what
it creates is a **graded column carrying every student's participation
percentage** with §3.4's per-week ledger in each score's comment (ADR 0125). A
sibling lead who can cause that column to exist has caused this tool to publish
per-week completion detail about a class they may not see, into a gradebook they
share with the lead who does. The disclosure is the column, and the person it
discloses to is the colleague — which is exactly the shape §4.1 invariant 2 exists
to refuse.

**The actor is the carried entry's own, verbatim**: "a Lead Faculty enrolled as a
Learner in a sibling lead's course can launch from it". So the launch itself is a
*learner* launch — the lead is a student in the sibling's course — and the
question is what their leadership hat causes.

**Two things are asserted and they fail differently.** No `pulse-participation`
line item in the launched context's container, and no call on the outbound
transport at all. A call that was made and refused is still a call this tool had
no authorization to make: the launching person's role is what authorizes the
trigger, and there is no trigger here to authorize.

**Emptiness is proved to be a real emptiness before it is believed**
(`docs/MISTAKES.md` entry 3). The container read is run again after planting a
line item out of band, and the planted item has to come back — the non-vacuity
control `test_a_staff_launch_creates_the_participation_line_item.py`'s student
test uses, for the same reason: a reader that answered `[]` for any reason at all
would make this test unfalsifiable, and a refusal test that cannot fail is worse
than none.

**The launcher's assignment is read back before the launch**, which is this test's
premise rather than ceremony. The actor is "a Lead Faculty enrolled as a Learner
in a sibling lead's course", so a launcher who ended up holding *no* assignment is
a stranger, and the refusal below would be the refusal of a launch by a person
with no leadership row at all — a different test passing for a different reason.
It is written as an equality rather than a membership because "their only
leadership assignment" is what the grain argument rests on, and because
`scripts/ci/check_invariant_assertions.py` refuses a marked test whose own body
asserts nothing.

**The near miss is the instructor pair next door.** Without
`test_an_instructor_launch_creates_the_participation_line_item_and_stores_its_id`,
this test is equally satisfied by a build where the whole hook is missing. The two
modules are a pair and each is worth reading beside the other.

**Which failure a red here is.** Expected **green** on a tree where the purview
condition is already correct — the roster half is asserted next door and passes,
and the same one decision point governs both. It is here because nothing was
asserting it: E3-05's hook keys on the section `provision_from_launch` resolved,
and a change that moved the trigger off that answer would open this silently.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.invariant, pytest.mark.integration, pytest.mark.lti]

# `gradebook_door`, `line_item_contract` and `celery_application_in` come from
# `tests/fixtures/line_item_creation.py`; `provisioning_contract`, `launch_ground`
# and `provisioned_rows` from `tests/fixtures/provisioning.py`; `web_identity`
# from `tests/fixtures/web_identity.py`. Reached as fixtures rather than
# imported: an import of a fixtures module by name depends on where pytest put
# `tests/` on `sys.path`, and an import error is not a red.

# §2.1's course-grain leadership role, by the spelling
# `tests/fixtures/supervision.py` resolves against the column's own enumeration.
# The carried entry's own actor.
LEAD_FACULTY = "LEAD_FACULTY"

SUBJECT_CLAIM = "sub"

# A label for a line item that is not Pulse's, for the container control below.
# Any string will do; what it must not be is `pulse-participation`.
A_FOREIGN_RESOURCE_ID = "e3-08-somebody-elses-column"


def a_linked_person(web_identity: Any, door: Any, subject: str) -> Any:
    """One `person`, one `user` row for `subject` at this platform, and the ADR 0024 link.

    This module's own copy of the helper in the two modules named above, for the
    reason each of them gives about importing across test modules. No assignment:
    which assignment the person holds is the whole subject here, so it is written
    in the open where the assertion can see it.
    """
    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=door.registration.platform_row[web_identity.key_of("lti_platform")],
        subject=subject,
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    return person_id


def line_item_id(item: Any) -> str:
    """One AGS line item's own address, which is its `id` member."""
    identifier = item.get("id")
    assert isinstance(identifier, str) and identifier, (
        f"The platform served the line item {item!r}, whose `id` is not an address. AGS 2.0 makes "
        "a line item's `id` its own URL."
    )
    return identifier


def running_inline(
    monkeypatch: pytest.MonkeyPatch,
    celery_application_in: Any,
    line_item_contract: Any,
    door: Any,
) -> None:
    """Both substitutions, in the order this test needs them.

    Deliberately **not** a fixture, for the reason the line-item module gives: both
    import `app.*` modules, which only resolve to the objects the door holds once
    the door has been built, and a fixture would run before the test body chose its
    environment. It is also where the deliverable guards fire, and a guard in a
    fixture turns a module's reds into setup errors (`docs/MISTAKES.md` entry 44).

    **Substituted even though nothing should run**, which is the point: with the
    task runner eager and the transport pointed at the platform, a hook that *did*
    fire would really create the column. A refusal test that left the machinery
    unwired would pass against a hook firing into a broker that was down.
    """
    line_item_contract.run_tasks_inline(monkeypatch, celery_application_in)
    line_item_contract.reaching_the_platform(monkeypatch, door.wire)


def test_a_lead_faculty_launching_from_a_sibling_leads_course_creates_no_column(
    gradebook_door: Any,
    provisioning_contract: Any,
    line_item_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    web_identity: Any,
    committed_rows: Any,
    a_closed_broker: str,
    celery_application_in: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§4.1 invariant 2, at the gradebook: a sibling lead's launch writes no column.

    The carried entry's actor, launching as the learner they are in the sibling's
    course, holding one `LEAD_FACULTY` assignment over a course that is not this
    one. §2.1: "a Lead Faculty's grant is only the courses they lead (never sibling
    leads' courses, at any point in the union)."

    **The mutation this kills:** the line-item trigger moved off the section
    `provision_from_launch` resolved and onto anything else — the launched context
    id, the claims, a section looked up by code. That answer is `None` for a launch
    outside the launcher's purview, and it is the single decision point that makes
    every one of §7.3's three limbs come out right at the gradebook. A trigger
    keyed on anything else creates a graded column in a course the launcher has no
    grant over, and the roster half next door stays green while it happens: nothing
    is bound, no address is stored, the defect is recorded — and a column appears
    anyway.

    **Why the column is a disclosure.** It carries every student's participation
    percentage, and ADR 0125 puts §3.4's per-week ledger in each score's comment
    where the course's instructors read it. A sibling lead who can cause that
    column to exist has caused this tool to publish per-week completion detail
    about a class they may not see, into a gradebook they share with the lead who
    may.

    **Course grain deliberately.** The leadership pair next door is college grain,
    and a condition written only over the college a launcher is scoped to would
    pass that while leaving this open: the lead here is scoped to a *course*, and
    their grant is that course and its sections, not the prefix above it.

    **`accepted` rather than `landed`**, and the reason is E1-13's landing rather
    than anything about this ticket: which of the door's two answers a lead faculty
    holding one course assignment gets is that ticket's rule. What is asserted is
    that the door did not *refuse* the launch, so what the hook did or did not do
    is attributable to the purview condition rather than to a launch that never
    arrived.
    """
    door = gradebook_door(**{line_item_contract.redis_url_variable: a_closed_broker})
    offer = door.student_offer(provisioning_contract)
    claims = door.driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)
    launch_ground(label)
    running_inline(monkeypatch, celery_application_in, line_item_contract, door)

    person_id = a_linked_person(web_identity, door, claims[SUBJECT_CLAIM])
    graph = committed_rows.graph
    lead = graph.assign(LEAD_FACULTY, person=person_id, reports_to=None)
    committed_rows.commit()

    assert graph.assignments_of(person_id) == [lead[graph.assignment_key]], (
        f"This launcher holds the assignments {graph.assignments_of(person_id)} and this test "
        f"wrote one {LEAD_FACULTY} assignment, {lead[graph.assignment_key]!r}. None means the "
        "launcher is a stranger and the refusal below is about a person with no leadership row at "
        "all — which §7.3's leadership limb never admitted in the first place. More than one means "
        "the launcher holds a hat this test did not write, so a refusal is not attributable to the "
        "lead-faculty grain."
    )

    response, signed = door.driver.launch(offer)

    door.driver.accepted(response, "a lead faculty's launch into a sibling lead's course")

    # The premise the whole test rests on: this launch really does advertise a
    # gradebook. "No column was created" over a launch carrying no AGS claim is a
    # statement about the claim rather than about the purview condition.
    advertised = provisioning_contract.line_items_url_in(signed.claims)
    assert advertised, (
        "The launch this test drove advertises no AGS line-item container, so there is nowhere a "
        "column could have been created and the refusal below is about nothing."
    )

    assert not door.pulse_items_in(signed), (
        f"A lead faculty's launch into a sibling lead's course put {door.pulse_items_in(signed)} "
        "into that course's gradebook. §2.1: 'a Lead Faculty's grant is only the courses they lead "
        "(never sibling leads' courses, at any point in the union)', and §4.1 invariant 2 makes it "
        "a hard invariant.\n\n"
        "What was created is a graded column carrying every student's participation percentage, "
        "with §3.4's per-week ledger in each score's comment where the course's own instructors "
        "read it (ADR 0125). The person who caused it has no grant over this course at all."
    )
    assert not door.wire.calls, (
        f"A lead faculty's launch into a sibling lead's course made "
        f"{[str(call) for call in door.wire.calls]} on the outbound transport. A call that was "
        "made and refused is still a call this tool had no authorization to make: the launching "
        "person's role authorizes the trigger, and there is no trigger here to authorize."
    )

    # The non-vacuity control, last, so the item it plants is its own
    # (`docs/MISTAKES.md` entry 3). Without it the two absences above are this
    # reader seeing nothing rather than the gradebook holding nothing.
    planted = door.plant_a_line_item(signed, resource_id=A_FOREIGN_RESOURCE_ID)
    assert line_item_id(planted) in [item.get("id") for item in door.items_in(signed)], (
        "A line item created out of band after the launch does not come back from the container "
        "read this test just used to assert emptiness. So the emptiness above is this reader "
        "seeing nothing rather than the gradebook holding nothing, and the whole test proves "
        "nothing."
    )
