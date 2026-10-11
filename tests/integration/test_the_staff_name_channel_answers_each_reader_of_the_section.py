"""The name reaches its readers — E7-01, done-when 2.

> A student with a live enrollment in a section gets that section's instructor's
> name, through the survey payload. The section's instructor, and the lead
> responsible for its course, get it through the service. Once a response is
> published to the section, its author's name is answered too.

The survey-payload half is
`test_the_survey_payload_names_the_sections_instructors.py`; this module is the
service half for staff readers (asked by person key), and the student half at the
definer, asked by the student's `user` key — a launched student has no `person`
(ADR 0028), and the ruling on B1 runs the student check on `p_reader_user_id`.

**Every answer is compared whole**, never searched for one name: a channel that
answered the whole course's instructors, or the whole department's, contains the
right name too. The world puts a distinctively named instructor on the sibling
section of the same course, on a sibling course and on an unmapped course
(`tests/fixtures/staff_names.py`), so each widening has a name to leak.

**Every call is made on `pulse_app`'s connection** (`docs/MISTAKES.md` entry 46).

**Which failure a red is, before E7-01 lands.** Each test fails first on the
missing deliverable, by name: `app.services.response_loop` does not exist, or
`public.section_staff_names(uuid,uuid,uuid)` does not, or `instructor_response` is not
declared.
"""

import pytest
from fixtures.staff_names import (
    LEAD_NAME,
    SIBLING_LEAD_NAME,
    SIBLING_SECTION_TEACHER_NAME,
    TEACHER_NAME,
    UNMAPPED_TEACHER_NAME,
    StaffNameWorld,
    ask_the_definer,
    ask_the_service,
    require_the_application_role,
    require_the_definer,
    require_the_tables,
)

pytestmark = pytest.mark.integration


def test_the_sections_instructor_is_answered_their_own_name_through_the_service(
    staff_names: StaffNameWorld,
) -> None:
    """The instructor of `F1WW` asks about `F1WW` and is answered exactly their own name.

    **The mutation this kills:** the instructor dropped from the reader set (the
    channel answering students only), which answers `[]`. **The near miss:** the
    instructor set read at course grain, which adds the sibling section's
    instructor, and the whole department's, which adds two more.
    """
    world = staff_names
    require_the_application_role(world.application_session)
    assert world.teacher is not None
    answered = ask_the_service(
        world.application_session, section_id=world.taught, reader_person_id=world.teacher.person_id
    )
    assert answered == [TEACHER_NAME], (
        f"The taught section's instructor asked the service about their own section and was "
        f"answered {answered}; done-when 2 answers them {[TEACHER_NAME]}, the section's one live "
        "teaching instructor, and nothing beside it."
    )


def test_the_lead_responsible_for_the_course_is_answered_the_instructors_name(
    staff_names: StaffNameWorld,
) -> None:
    """The course's Lead Faculty asks about `F1WW` and is answered its instructor's name.

    **The mutation this kills:** the reader set closed at students and the
    section's own instructors, which refuses the lead. **The near miss:** the
    lead's grant widened to the department, which still answers this case and is
    killed by the sibling-lead refusal in
    `test_the_staff_name_channel_answers_no_other_reader.py`.
    """
    world = staff_names
    require_the_application_role(world.application_session)
    assert world.lead is not None
    answered = ask_the_service(
        world.application_session, section_id=world.taught, reader_person_id=world.lead.person_id
    )
    assert answered == [TEACHER_NAME], (
        f"The lead of the own course asked about its section F1WW and was answered {answered}, "
        f"not {[TEACHER_NAME]}. Done-when 2: the lead responsible for the course gets the "
        "instructor's name through the service (`authz.lead_review_courses`' rule)."
    )


def test_the_chair_of_a_course_with_no_lead_is_answered_its_instructors_name(
    staff_names: StaffNameWorld,
) -> None:
    """The department chair asks about the unmapped course's section and is answered.

    SPEC §2.1: "A course with no mapping falls to its department chair", and the
    work order's reader rule is `lead_review_courses`' (the chair for a course
    with no lead).

    **The mutation this kills:** the responsible-person check written over
    `LEAD_FACULTY` mappings only, which refuses every chair.
    """
    world = staff_names
    require_the_application_role(world.application_session)
    assert world.chair is not None
    answered = ask_the_service(
        world.application_session,
        section_id=world.unmapped_section,
        reader_person_id=world.chair.person_id,
    )
    assert answered == [UNMAPPED_TEACHER_NAME], (
        f"The chair asked about the unmapped course's section and was answered {answered}, not "
        f"{[UNMAPPED_TEACHER_NAME]}. The course has no lead, so it falls to the chair."
    )


def test_a_student_with_a_live_enrollment_is_answered_the_instructors_name_by_the_definer(
    staff_names: StaffNameWorld,
) -> None:
    """A student enrolled in `F1WW` asks the definer directly and is answered its instructor.

    The student check sits inside the definer (the ticket: "the student is the
    reader the channel widens"), so the definer answers a student itself.

    **The mutation this kills:** the enrollment check joined on the wrong user
    (or not at all), which answers nothing to a real student. **The near miss:**
    an answer at course grain, which adds the sibling section's instructor.
    """
    world = staff_names
    require_the_application_role(world.application_session)
    require_the_definer(world.application_session)
    student = world.a_student("live-in-the-taught-section", world.taught)
    answered = ask_the_definer(
        world.application_session, section_id=world.taught, reader_user_id=student.user_id
    )
    assert answered.names == [TEACHER_NAME], (
        f"A student with a live enrollment in F1WW asked the definer about F1WW and was answered "
        f"{answered.names}, not {[TEACHER_NAME]}."
    )


def test_a_published_responses_author_is_answered_beside_the_instructor(
    staff_names: StaffNameWorld,
) -> None:
    """Before a response, the lead's name is not answered for `F1WW`; after the lead publishes, it is.

    Both readers who are answered at all — the section's instructor (service) and a
    student of it (definer) — read the author's name once it exists. A response the
    sibling lead published to the sibling course's section is planted as well, and
    its author must not be answered for `F1WW`.

    **The mutation this kills:** the author union missing, so an on-behalf
    response is attributed to nobody a student can read. **The near miss:** the
    author union keyed on the course or the department rather than the section,
    which answers the sibling lead too.
    """
    world = staff_names
    require_the_application_role(world.application_session)
    require_the_definer(world.application_session)
    require_the_tables(world.tables)
    assert world.teacher is not None and world.lead is not None and world.sibling_lead is not None
    student = world.a_student("reads-the-response", world.taught)

    before = ask_the_service(
        world.application_session, section_id=world.taught, reader_person_id=world.teacher.person_id
    )
    assert before == [TEACHER_NAME], (
        f"Before any response the instructor's answer for F1WW is {before}, not {[TEACHER_NAME]}; "
        "the lead's name must not be answered for a section they have published nothing to."
    )

    world.a_response(world.taught, author=world.lead.person_id, role="LEAD_FACULTY")
    world.a_response(
        world.sibling_course_section, author=world.sibling_lead.person_id, role="LEAD_FACULTY"
    )

    expected = sorted([TEACHER_NAME, LEAD_NAME])
    by_service = ask_the_service(
        world.application_session, section_id=world.taught, reader_person_id=world.teacher.person_id
    )
    assert by_service == expected, (
        f"After the lead published a response to F1WW the instructor's answer is {by_service}, "
        f"not {expected}. Done-when 2: 'Once a response is published to the section, its author's "
        f"name is answered too.' {SIBLING_LEAD_NAME!r} published only to another course's section."
    )
    by_definer = ask_the_definer(
        world.application_session, section_id=world.taught, reader_user_id=student.user_id
    )
    assert by_definer.names == expected, (
        f"After the lead published a response to F1WW, a student of F1WW is answered "
        f"{by_definer.names}, not {expected}. SPEC §5.3: an on-behalf response is 'attributed "
        "honestly to the Lead Faculty', so the student is the reader this name is for."
    )


def test_each_person_is_answered_once_however_many_times_they_published(
    staff_names: StaffNameWorld,
) -> None:
    """The instructor publishes twice (an edit is a second row): one row for them, not three.

    **The mutation this kills:** the instructors and the authors unioned with
    `UNION ALL`, or the author rows read without collapsing to people, so a
    published-then-edited week names its instructor three times.
    """
    world = staff_names
    require_the_application_role(world.application_session)
    require_the_definer(world.application_session)
    require_the_tables(world.tables)
    assert world.teacher is not None
    world.a_response(world.taught, author=world.teacher.person_id, role="INSTRUCTOR")
    world.a_response(world.taught, author=world.teacher.person_id, role="INSTRUCTOR")
    answered = ask_the_definer(
        world.application_session, section_id=world.taught, reader_person_id=world.teacher.person_id
    )
    assert answered.names == [TEACHER_NAME], (
        f"The instructor, who teaches F1WW and published two response rows to it, is answered "
        f"{answered.names}. The channel answers people's names, so each person once."
    )


def test_an_instructor_whose_grant_the_roster_ended_is_no_longer_named(
    staff_names: StaffNameWorld,
) -> None:
    """A former teacher of `F1WW` is not among its names; the live teacher still is.

    Work order decision 2: "the section's **live** teaching instructors' names".

    **The mutation this kills:** the instructor set read from teaching grants
    past and present (`ended_teaching_grant` unioned in, as E6-09's taught-section
    rule does for a different purpose).
    """
    world = staff_names
    require_the_application_role(world.application_session)
    require_the_definer(world.application_session)
    assert world.teacher is not None
    world.a_former_teacher_of_the_taught_section()
    answered = ask_the_definer(
        world.application_session, section_id=world.taught, reader_person_id=world.teacher.person_id
    )
    assert answered.names == [TEACHER_NAME], (
        f"F1WW's names, after another person's teaching grant on it was ended by the roster, are "
        f"{answered.names}; only the live instructor {TEACHER_NAME!r} is answered."
    )


def test_the_sibling_sections_instructor_is_answered_for_their_own_section(
    staff_names: StaffNameWorld,
) -> None:
    """The control for the sibling-section refusal: that teacher is a reader of `Q1WW`.

    **The mutation this kills:** a reader check that refuses every instructor
    but the one a fixture happened to launch, which would make the refusal in
    the denial module pass for the wrong reason (`docs/MISTAKES.md` entry 3).
    """
    world = staff_names
    require_the_application_role(world.application_session)
    assert world.sibling_section_teacher is not None
    answered = ask_the_service(
        world.application_session,
        section_id=world.sibling_section,
        reader_person_id=world.sibling_section_teacher.person_id,
    )
    assert answered == [SIBLING_SECTION_TEACHER_NAME], (
        f"The sibling section's instructor asked about their own section and was answered "
        f"{answered}, not {[SIBLING_SECTION_TEACHER_NAME]}."
    )
