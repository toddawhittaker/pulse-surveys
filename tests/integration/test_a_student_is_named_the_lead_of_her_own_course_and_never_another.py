"""A student is named the lead of her own course and never another's — E9-08, done-when 5.

> 5. **No other section's lead.** A student enrolled in section A gets A's
>    course's lead only, never the lead of a course they are not in, tested with
>    two courses and two leads.

**The world** is E7-02's `hold` (`tests/fixtures/the_hold.py`): the own course
(section `F1WW`, led by `LEAD_NAME`) and the sibling course in the same prefix
(cohort `Y`, led by `SIBLING_LEAD_NAME`). Two courses, two leads, each name
distinctive and planted on one person.

**Denial, asserted as denial** (SPEC §4.1; the test author's rule). The door is
asked about the other course's section *by this student* and must refuse —
`None`, the interface's refusal — and the results route asked for that section
must answer its one 404 carrying no trace of that lead. **Each refusal has its
present twin in the same test**: the same section's lead read by its own
student, so the refusal is about who asked and not a door or route that answers
nothing to anybody (`docs/MISTAKES.md` entry 3).

**Marked `invariant`**: a staff name reaching a student of another section is a
§4.1 widening, and CI runs this pass isolated and treats a skip as a failure.

**Which failure a red is, before E9-08 lands:** `the_lead_door` fails naming the
missing door, or `lead_name_in` fails naming the missing member, in each test's
present twin.
"""

import pytest
from fixtures.course_page_lead import ask_for_the_lead, lead_name_in
from fixtures.lead_review import SIBLING_COHORT
from fixtures.staff_names import LEAD_NAME, SIBLING_LEAD_NAME
from fixtures.student_read import response_surface
from fixtures.the_hold import REFUSED_STATUS, HoldWorld, payload_of

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

WEEK = 1


def test_each_student_is_named_her_own_courses_lead_by_the_door(hold: HoldWorld) -> None:
    """Two courses, two leads, a student in each: the door answers each her own course's lead.

    **The mutations this kills:** the lead looked up by the prefix or the
    department (both students read one name); the first `LEAD_FACULTY` row of
    any section in the call rather than of the section asked about; and the door
    asking with a key that is not the student's, so both read `None`. **The near
    miss:** the other student's lead, one course over.
    """
    world = hold
    world.stand_after_the_opening(WEEK)
    own = world.a_student("lead-own-course", world.taught)
    other = world.a_student("lead-sibling-course", world.sibling_course_section)
    session = world.application_session

    own_lead = ask_for_the_lead(session, section_id=world.taught, reader_user_id=own.user_id)
    other_lead = ask_for_the_lead(
        session, section_id=world.sibling_course_section, reader_user_id=other.user_id
    )

    assert own_lead == LEAD_NAME, (
        f"The door named {own_lead!r} as the lead of the own course to its student; the lead is "
        f"{LEAD_NAME!r}."
    )
    assert other_lead == SIBLING_LEAD_NAME, (
        f"The door named {other_lead!r} as the lead of the sibling course to its student; the "
        f"lead is {SIBLING_LEAD_NAME!r}."
    )


def test_the_door_refuses_a_student_the_lead_of_a_course_she_is_not_in(hold: HoldWorld) -> None:
    """The own course's student asks about the sibling course's section: `None`.

    **The present twin, in the same test:** the sibling course's own student asks
    about the same section and is answered `SIBLING_LEAD_NAME`, so the name is
    there to be leaked and the refusal is about the reader. And the other
    direction: the sibling course's student asking about `F1WW` is refused while
    `F1WW`'s own student is answered.

    **The mutations this kills:** the lead read by a query of its own, beside
    E9-03's door rather than through it, which carries no reader check (the
    course's lead answered to anybody who names a section); and the door called
    with the reader key dropped. **The near miss:** each present twin.
    """
    world = hold
    world.stand_after_the_opening(WEEK)
    own = world.a_student("lead-asks-across", world.taught)
    other = world.a_student("lead-asked-across", world.sibling_course_section)
    session = world.application_session

    present_there = ask_for_the_lead(
        session, section_id=world.sibling_course_section, reader_user_id=other.user_id
    )
    present_here = ask_for_the_lead(session, section_id=world.taught, reader_user_id=own.user_id)
    assert (present_there, present_here) == (SIBLING_LEAD_NAME, LEAD_NAME), (
        f"The twins read {present_there!r} and {present_here!r}; each course's own student "
        f"must read its lead ({SIBLING_LEAD_NAME!r}, {LEAD_NAME!r}), or the refusals below "
        "prove nothing."
    )

    across = ask_for_the_lead(
        session, section_id=world.sibling_course_section, reader_user_id=own.user_id
    )
    back = ask_for_the_lead(session, section_id=world.taught, reader_user_id=other.user_id)

    assert across is None, (
        f"The door named {across!r} to a student of the own course as the lead of a course "
        "she is not in. Done-when 5: never the lead of a course she is not in."
    )
    assert back is None, (
        f"The door named {back!r} to a student of the sibling course as the lead of the own "
        "course, which she is not in."
    )


def test_each_students_results_carry_her_own_courses_lead_and_no_other(hold: HoldWorld) -> None:
    """Both students read course week 1 through the route: each her own lead, the other nowhere.

    The other lead's name is searched for in the whole answer, headers and body,
    not only in `lead_name`: a payload that carried both leads somewhere would
    pass a check of the one member.

    **The mutations this kills:** the lead read for the course of the section the
    route was asked about but through a key that is not the student's (both read
    `null`); the lead of the prefix's first course; and a list of leads. **The
    near miss:** each student's own lead, present in the same read.
    """
    world = hold
    own = world.a_student("results-own-course", world.taught)
    other = world.a_student("results-sibling-course", world.sibling_course_section)
    world.windows_for(SIBLING_COHORT, WEEK)
    world.stand_after_the_opening(WEEK)

    own_answer = world.results(own, course_week=WEEK)
    other_answer = world.results(other, course_week=WEEK)
    own_body = payload_of(own_answer, "The own course's student's results")
    other_body = payload_of(other_answer, "The sibling course's student's results")

    own_name = lead_name_in(own_body, "The own course's student's results")
    other_name = lead_name_in(other_body, "The sibling course's student's results")
    assert own_name == LEAD_NAME, f"The own course's student reads `lead_name` = {own_name!r}."
    assert (
        other_name == SIBLING_LEAD_NAME
    ), f"The sibling course's student reads `lead_name` = {other_name!r}."
    assert SIBLING_LEAD_NAME not in response_surface(own_answer), (
        f"The own course's student's results name the sibling course's lead "
        f"({SIBLING_LEAD_NAME!r}). Done-when 5."
    )
    assert LEAD_NAME not in response_surface(other_answer), (
        f"The sibling course's student's results name the own course's lead ({LEAD_NAME!r}). "
        "Done-when 5."
    )


def test_a_results_read_of_another_courses_section_is_refused_and_names_its_lead_nowhere(
    hold: HoldWorld,
) -> None:
    """The own course's student asks the route for the sibling course's section: the one 404.

    **The present twin, in the same test:** the sibling course's own student reads
    that section's week and is answered 200 carrying `SIBLING_LEAD_NAME`, so the
    week is published, the route answers it, and the name exists to leak.

    **The mutations this kill:** the lead's name read before the enrollment check
    and served on the refusal (an error body that says whose course it is); and
    the refusal answered with a body that varies by section. **The near miss:**
    the twin.
    """
    world = hold
    own = world.a_student("refused-own-course", world.taught)
    other = world.a_student("refused-sibling-course", world.sibling_course_section)
    world.windows_for(SIBLING_COHORT, WEEK)
    world.stand_after_the_opening(WEEK)

    what = "The sibling course's own student's results"
    twin = world.results(other, course_week=WEEK)
    twin_name = lead_name_in(payload_of(twin, what), what)
    assert twin_name == SIBLING_LEAD_NAME, (
        f"The sibling course's own student reads `lead_name` = {twin_name!r}, not "
        f"{SIBLING_LEAD_NAME!r}, so the refusal below would prove nothing."
    )

    refused = world.results(own, course_week=WEEK, section_id=world.sibling_course_section)

    assert refused.status_code == REFUSED_STATUS, (
        f"A student of the own course asking for the sibling course's section was answered "
        f"{refused.status_code}, not the one {REFUSED_STATUS}."
    )
    assert SIBLING_LEAD_NAME not in response_surface(refused), (
        f"The refusal names the sibling course's lead ({SIBLING_LEAD_NAME!r}). Done-when 5, and "
        "SPEC §4.1: a refused read names nothing of the section."
    )
