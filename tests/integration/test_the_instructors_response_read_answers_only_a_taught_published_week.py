"""The instructor's response read answers only her own taught, published week — E7-10 done-when 7.

> The instructor's `GET …/response` has a marked test: own week served, and the
> sibling section, a nonexistent section and an unpublished week each get the
> report's own 404, byte for byte, naming nothing.

E7-03's work order (decision 1) mounts `GET …/sections/{section_id}/weeks/
{course_week}/response` in `app.api.instructor` beside the publish and the edit,
and gives a section the reader does not teach, or a week not yet published, the
report's own 404. The publish and the edit were driven against those refusals;
the read was not (invariant-coverage MED). SPEC §4.1 item 2: an instructor sees
no other section — and the sibling section here has a response of its own,
planted, so a read that resolved the section without the teaching scope would
hand it over.

**Each refusal is compared with the report route's answer** for the same
section-week at the same clock, never transcribed (`docs/MISTAKES.md` entry 19),
and is required to carry neither the section's key nor its code nor the planted
response. **The served twin runs in every test**: the teacher's own answered
week, read 200 carrying her text, in the same world and at the same clock as the
refusal beside it.

**Which failure a red is.** E7-03 built the route and, by its work order, its
refusals; on the epic head these are expected green unless the read skips the
scope. They are the marked coverage the boundary review found missing.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.report_api import UNTAUGHT_COHORT
from fixtures.response_draft import strings_in
from fixtures.response_loop_doors import (
    CLEAR_PAST,
    CREATED,
    NOT_FOUND,
    OK,
    ON_BEHALF_WEEK,
    LoopWorld,
)
from fixtures.the_hold import FIRST_ROW_AFTER_OPENING, INSTRUCTOR, report_opens, spellings_of

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

HERS = "E7-10 the teacher's response: the lab report deadline moves to Monday"
SIBLINGS = "E7-10 the sibling section's response: Quentaro Vell will rerun the tutorial"

SIBLING = "the sibling section"
NOWHERE = "a section that does not exist"
UNPUBLISHED = "a week not yet published"


def her_week_is_answered(world: LoopWorld) -> None:
    world.stand(CLEAR_PAST)
    published = world.instructor("POST", text=HERS)
    assert published.status_code == CREATED, (
        f"The teacher's publish of her own week answered {published.status_code}. Body "
        f"{published.text[:300]!r}."
    )


def the_sibling_section_is_answered(world: LoopWorld) -> None:
    """`Q1WW` (the own course's other section) with a window and a response of its own teacher's."""
    world.hold.windows_for(UNTAUGHT_COHORT, ON_BEHALF_WEEK)
    world.hold.a_response(
        section_id=world.hold.sibling_section,
        course_week=ON_BEHALF_WEEK,
        author=world.hold.person(world.hold.names.sibling_section_teacher).person_id,
        role=INSTRUCTOR,
        body=SIBLINGS,
        published_at=report_opens(ON_BEHALF_WEEK) + FIRST_ROW_AFTER_OPENING,
    )


def asked_and_reported(world: LoopWorld, where: str) -> tuple[Any, Any, list[str]]:
    """The response read for `where`, the report's answer for the same section-week, and what may not appear."""
    if where == SIBLING:
        the_sibling_section_is_answered(world)
        section, week = world.hold.sibling_section, ON_BEHALF_WEEK
        forbidden = [SIBLINGS, world.hold.code_of(UNTAUGHT_COHORT), *spellings_of(section)]
    elif where == NOWHERE:
        section, week = uuid4(), ON_BEHALF_WEEK
        forbidden = list(spellings_of(section))
    else:
        world.hold.stand_at(report_opens(ON_BEHALF_WEEK + 1) - CLEAR_PAST)
        section, week = world.hold.taught, ON_BEHALF_WEEK + 1
        forbidden = [HERS]
    asked = world.instructor("GET", section_id=section, course_week=week)
    reported = world.draft.report(course_week=week, section_id=section)
    return asked, reported, forbidden


@pytest.mark.parametrize("where", [SIBLING, NOWHERE, UNPUBLISHED])
def test_the_response_read_refuses_with_the_reports_own_404_and_serves_her_own_week(
    response_loop: LoopWorld, where: str
) -> None:
    """Her own answered week: 200 with her text. `where`: the report's 404, byte for byte, naming nothing.

    **The mutations this kills, one per parameter:** the read resolving the
    section by its key without the teaching scope (the sibling's response served
    — SPEC §4.1 item 2); a distinct answer for an unknown key (a 422, another
    sentence — an existence oracle); the publication check absent from the read
    (a week students cannot yet read answered before its report opens, and the
    one place a response could be read before it is published). And for each, a
    refusal worded apart from the report's. **The near miss, in the same world at
    the same clock:** her own published, answered week, served.
    """
    world = response_loop
    her_week_is_answered(world)

    asked, reported, forbidden = asked_and_reported(world, where)
    own = world.instructor("GET")

    assert own.status_code == OK and HERS in strings_in(own.json()), (
        f"The teacher's read of her own answered week answered {own.status_code} "
        f"{own.text[:300]!r}, so the refusal below may be a route refusing everything."
    )
    assert reported.status_code == NOT_FOUND, (
        f"The report itself answers {reported.status_code} for {where}; the comparison rests on "
        "its 404. A broken world, not a red."
    )
    assert asked.status_code == NOT_FOUND, (
        f"The teacher's response read for {where} answered {asked.status_code}. Body "
        f"{asked.text[:300]!r}."
    )
    assert asked.content == reported.content, (
        f"The response read's refusal for {where} is {asked.text[:300]!r}; the report's is "
        f"{reported.text[:300]!r}. E7-03 decision 1: the report's own 404, byte for byte."
    )
    named = [token for token in forbidden if token in asked.text]
    assert not named, f"The refusal for {where} names {named}."
