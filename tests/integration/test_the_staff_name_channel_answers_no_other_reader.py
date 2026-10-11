"""The name reaches nobody else — E7-01, done-when 3, and SPEC §4.1.

> The same call answers nothing for a student of another section, a student whose
> enrollment has ended, an instructor of a sibling section, a lead of a sibling
> course, and a chair of another department. Each test sits beside its passing
> twin in one world (entry 3). Each refused-reader case also calls the database
> function directly as `pulse_app`. … including a two-hat person who is a student
> in section A and an instructor in section B, asking for section C. These tests
> are marked `invariant`.

**What a refusal is here.** The ticket defines it: "Every other reader gets an
empty answer, the same as a section with no instructor." So the refused half of
each pair is an empty answer, and it means something only because **the twin, in
the same world and the same test, is answered a name first** (`docs/MISTAKES.md`
entry 3: an empty answer is also what a channel that answers nobody gives).

**Two reader keys** (the ruling on B1): the definer takes `p_reader_user_id` and
`p_reader_person_id`, exactly one non-null. A student is asked about by user key
— a launched student has no `person` (ADR 0028) — and a member of staff by person
key. So a student is asked at the definer only (the service's keywords are
decision 3's, which name a person key), and a member of staff at both the service
and the definer. Two pairs pin the key rule itself: both keys null and both keys
set answer nothing beside each key alone answering; and each check runs on its
own key only (a student's person key and a teacher's user key reach nothing).

**Every reader set is a closed set, attacked one level out**
(`docs/MISTAKES.md` entry 53): a student enrolled in the same course's other
section, an enrollment that has ended, a teaching grant the roster ended, a lead
of a sibling course under the same prefix, the department's own chair for a
course that has a lead, a chair of another department under the same college,
and the two-hat person whose two real readings bracket the section they may not
read. The last test writes the whole reader rule out by hand over every reader
and every section (`docs/MISTAKES.md` entry 19: the expectation is the spec's
rule written out, not a call to the code under test).

**Which failure a red is, before E7-01 lands.** The definer guard fails naming
`public.section_staff_names(uuid,uuid,uuid)`; the service guard names
`app.services.response_loop`.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.staff_names import (
    SIBLING_COURSE_TEACHER_NAME,
    SIBLING_SECTION_TEACHER_NAME,
    TEACHER_NAME,
    TWO_HAT_NAME,
    UNMAPPED_TEACHER_NAME,
    Person,
    StaffNameWorld,
    ask_the_definer,
    ask_the_service,
    require_the_application_role,
    require_the_definer,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


def staff_answers(world: StaffNameWorld, section_id: Any, reader: Person) -> tuple[list, list]:
    """A member of staff, by person key: the service's names and the definer's names."""
    by_service = ask_the_service(
        world.application_session, section_id=section_id, reader_person_id=reader.person_id
    )
    by_definer = ask_the_definer(
        world.application_session, section_id=section_id, reader_person_id=reader.person_id
    ).names
    return by_service, by_definer


def student_answer(world: StaffNameWorld, section_id: Any, reader: Person) -> list[str]:
    """A student, by user key: the definer's names."""
    assert reader.user_id is not None, f"{reader.label} has no user key to be asked by."
    return ask_the_definer(
        world.application_session, section_id=section_id, reader_user_id=reader.user_id
    ).names


def prepared(world: StaffNameWorld) -> None:
    require_the_application_role(world.application_session)
    require_the_definer(world.application_session)


REFUSAL = (
    "E7-01 done-when 3: the channel answers nothing to a reader who is not enrolled in the "
    "section, does not teach it, and is not responsible for its course — the same empty answer "
    "as a section with no instructor."
)


def staff_refused(reader: Person, where: str, service: list, definer: list) -> str:
    return (
        f"{reader.label} asked about {where} and was answered {service} by the service and "
        f"{definer} by the definer called directly as `pulse_app`. {REFUSAL}"
    )


def student_refused(reader: Person, where: str, definer: list) -> str:
    return (
        f"{reader.label} asked about {where} and was answered {definer} by the definer called "
        f"directly as `pulse_app`. {REFUSAL}"
    )


def test_a_student_of_the_same_courses_other_section_is_answered_nothing(
    staff_names: StaffNameWorld,
) -> None:
    """Enrolled in `Q1WW`: answered `Q1WW`'s instructor, and nothing for `F1WW`.

    **The mutation this kills:** the enrollment check joined at course grain.
    **The twin:** the same student asking about their own section.
    """
    world = staff_names
    prepared(world)
    student = world.a_student("in-the-sibling-section", world.sibling_section)

    twin = student_answer(world, world.sibling_section, student)
    assert twin == [
        SIBLING_SECTION_TEACHER_NAME
    ], f"The twin: a student of Q1WW asking about Q1WW was answered {twin}."
    definer = student_answer(world, world.taught, student)
    assert definer == [], student_refused(
        student, "F1WW, the other section of their course", definer
    )


def test_a_student_whose_enrollment_has_ended_is_answered_nothing(
    staff_names: StaffNameWorld,
) -> None:
    """Enrolled in `F1WW` until twenty days ago: nothing; a live classmate is answered.

    **The mutation this kills:** the enrollment check without its window.
    """
    world = staff_names
    prepared(world)
    live = world.a_student("live-classmate", world.taught)
    ended = world.a_student("dropped", world.taught, ended=True)

    twin = student_answer(world, world.taught, live)
    assert twin == [TEACHER_NAME], f"The twin: a live student of F1WW was answered {twin}."
    definer = student_answer(world, world.taught, ended)
    assert definer == [], student_refused(ended, "F1WW, whose enrollment in it has ended", definer)


def test_an_instructor_of_a_sibling_section_is_answered_nothing(
    staff_names: StaffNameWorld,
) -> None:
    """Teaches `Q1WW`: answered for `Q1WW`, nothing for `F1WW`.

    **The mutation this kills:** the instructor check at course grain.
    """
    world = staff_names
    prepared(world)
    reader = world.sibling_section_teacher
    assert reader is not None

    twin = staff_answers(world, world.sibling_section, reader)
    assert twin == (
        [SIBLING_SECTION_TEACHER_NAME],
        [SIBLING_SECTION_TEACHER_NAME],
    ), f"The twin: the instructor of Q1WW asking about Q1WW was answered {twin}."
    service, definer = staff_answers(world, world.taught, reader)
    assert service == [] and definer == [], staff_refused(
        reader, "F1WW, a sibling section of the one they teach", service, definer
    )


def test_a_lead_of_a_sibling_course_is_answered_nothing(staff_names: StaffNameWorld) -> None:
    """Leads the sibling course: answered for its section, nothing for `F1WW`. SPEC §4.1 item 2.

    **The mutation this kills:** the responsible-person check at prefix or
    department grain.
    """
    world = staff_names
    prepared(world)
    reader = world.sibling_lead
    assert reader is not None

    twin = staff_answers(world, world.sibling_course_section, reader)
    assert twin == (
        [SIBLING_COURSE_TEACHER_NAME],
        [SIBLING_COURSE_TEACHER_NAME],
    ), f"The twin: the sibling lead asking about their own course's section was answered {twin}."
    service, definer = staff_answers(world, world.taught, reader)
    assert service == [] and definer == [], staff_refused(
        reader, "F1WW, in a sibling lead's course", service, definer
    )


def test_a_chair_of_another_department_is_answered_nothing(staff_names: StaffNameWorld) -> None:
    """Chairs a second department: nothing for the unmapped course; its own chair is answered.

    **The mutation this kills:** "holds `CHAIR` somewhere", or `CHAIR` at college
    grain (both departments share a college here).
    """
    world = staff_names
    prepared(world)
    assert world.chair is not None and world.other_chair is not None

    twin = staff_answers(world, world.unmapped_section, world.chair)
    assert twin == ([UNMAPPED_TEACHER_NAME], [UNMAPPED_TEACHER_NAME]), (
        f"The twin: the department's chair asking about its unmapped course's section was "
        f"answered {twin}."
    )
    service, definer = staff_answers(world, world.unmapped_section, world.other_chair)
    assert service == [] and definer == [], staff_refused(
        world.other_chair, "the unmapped course's section, in another department", service, definer
    )


def test_the_departments_chair_is_answered_nothing_for_a_course_that_has_a_lead(
    staff_names: StaffNameWorld,
) -> None:
    """The chair, one level out: answered for the unmapped course, nothing for the led one.

    Work order decision 1 (c) is `lead_review_courses`' rule: the chair is
    responsible for a course in their department **with no lead**.

    **The mutation this kills:** the chair branch over the whole department.
    """
    world = staff_names
    prepared(world)
    assert world.chair is not None

    twin = staff_answers(world, world.unmapped_section, world.chair)
    assert twin == (
        [UNMAPPED_TEACHER_NAME],
        [UNMAPPED_TEACHER_NAME],
    ), f"The twin: the chair asking about the unmapped course's section was answered {twin}."
    service, definer = staff_answers(world, world.taught, world.chair)
    assert service == [] and definer == [], staff_refused(
        world.chair, "F1WW, whose course has a lead", service, definer
    )


def test_an_instructor_whose_teaching_grant_the_roster_ended_is_answered_nothing(
    staff_names: StaffNameWorld,
) -> None:
    """Taught `F1WW` until the roster ended the grant: nothing; the live teacher is answered.

    **The mutation this kills:** the instructor check reading taught-or-once-taught
    sections (E6-09's helper, which exists for the opposite purpose).
    """
    world = staff_names
    prepared(world)
    assert world.teacher is not None
    former = world.a_former_teacher_of_the_taught_section()

    twin = staff_answers(world, world.taught, world.teacher)
    assert twin == ([TEACHER_NAME], [TEACHER_NAME]), f"The twin was answered {twin}."
    service, definer = staff_answers(world, world.taught, former)
    assert service == [] and definer == [], staff_refused(
        former, "F1WW, whose teaching grant the roster ended", service, definer
    )


def test_a_two_hat_person_is_answered_nothing_for_a_third_section(
    staff_names: StaffNameWorld,
) -> None:
    """Student in `Q1WW` (A), instructor of the sibling course's section (B), asking `F1WW` (C).

    **Both twins are asserted**, each under the key of the session it would come
    in on: their student session (user key) is answered A's instructor, and their
    instructor session (person key) is answered B's instructors. C is asked under
    each key, and under both at once; every answer is empty.

    **The mutation this kills:** the hats OR-ed across sections ("enrolled
    somewhere and teaches somewhere"), and the student hat at course grain (A and
    C share a course).
    """
    world = staff_names
    prepared(world)
    reader = world.a_two_hat_person()

    as_a_student = student_answer(world, world.sibling_section, reader)
    assert as_a_student == [SIBLING_SECTION_TEACHER_NAME], (
        f"The first twin: the two-hat person's student key, asking about Q1WW, was answered "
        f"{as_a_student}."
    )
    expected_b = sorted([SIBLING_COURSE_TEACHER_NAME, TWO_HAT_NAME])
    as_a_teacher = staff_answers(world, world.sibling_course_section, reader)
    assert as_a_teacher == (expected_b, expected_b), (
        f"The second twin: the two-hat person's person key, asking about the section they teach, "
        f"was answered {as_a_teacher}, not {expected_b} from both."
    )

    by_user = student_answer(world, world.taught, reader)
    service, by_person = staff_answers(world, world.taught, reader)
    by_both = ask_the_definer(
        world.application_session,
        section_id=world.taught,
        reader_user_id=reader.user_id,
        reader_person_id=reader.person_id,
    ).names
    assert by_user == [] and service == [] and by_person == [] and by_both == [], (
        f"The two-hat person asked about F1WW, which they neither attend nor teach, and was "
        f"answered {by_user} under the user key, {service} by the service and {by_person} by the "
        f"definer under the person key, and {by_both} under both. {REFUSAL}"
    )


def test_each_check_runs_on_its_own_key_only(staff_names: StaffNameWorld) -> None:
    """A student's person key reaches nothing, and a teacher's user key reaches nothing.

    The ruling on B1: "The student check (live enrollment) runs on
    `p_reader_user_id`; the staff checks … run on `p_reader_person_id`." So a
    two-hat person's **person** key asking about the section they are only a
    student of is answered nothing, and a teacher's **user** key asking about the
    section they teach is answered nothing — beside each key answering where it
    should.

    **The mutations this kill:** the student check also reached from a person key
    (`person.user_id` joined to `enrollment`), and the staff checks also reached
    from a user key (`person.user_id` joined back to a grant). Either lets one
    session borrow the other hat's reading.
    """
    world = staff_names
    prepared(world)
    reader = world.a_two_hat_person()
    # A second teacher of the unmapped course's section, with a `user` row linked to
    # their person — the shape a launching instructor has (E1-12).
    teacher = world.a_teacher_of(world.unmapped_section, "Keyed Byperson-Only", "a keyed teacher")
    teacher_user = world.web_identity.user(
        platform_id=world.review._platform_id(), subject=f"e7-01-teacher-{uuid4().hex[:8]}"
    )
    world.web_identity.link_person_to_user(person_id=teacher.person_id, user_id=teacher_user)
    expected = sorted(["Keyed Byperson-Only", UNMAPPED_TEACHER_NAME])

    twins = (
        student_answer(world, world.sibling_section, reader),
        staff_answers(world, world.unmapped_section, teacher)[1],
    )
    assert twins == ([SIBLING_SECTION_TEACHER_NAME], expected), (
        f"The twins: the two-hat person's user key on Q1WW and the keyed teacher's person key on "
        f"the section they teach were answered {twins}."
    )
    student_hat_by_person = ask_the_definer(
        world.application_session,
        section_id=world.sibling_section,
        reader_person_id=reader.person_id,
    ).names
    teacher_hat_by_user = ask_the_definer(
        world.application_session, section_id=world.unmapped_section, reader_user_id=teacher_user
    ).names
    assert student_hat_by_person == [], (
        f"The two-hat person's person key, asking about Q1WW where they are only a student, was "
        f"answered {student_hat_by_person}. The student check runs on the user key only."
    )
    assert teacher_hat_by_user == [], (
        f"The keyed teacher's user key, asking about the section they teach, was answered "
        f"{teacher_hat_by_user}. The staff checks run on the person key only."
    )


def test_a_call_naming_no_reader_key_answers_nothing(staff_names: StaffNameWorld) -> None:
    """Both reader keys null: zero rows. The twin: the section's teacher by person key alone.

    **The mutation this kills:** a reader check that fails open when there is no
    reader (`NULL` comparisons read as "no restriction", or the student branch
    written as `p_reader_user_id IS NULL OR …`).
    """
    world = staff_names
    prepared(world)
    assert world.teacher is not None
    twin = ask_the_definer(
        world.application_session, section_id=world.taught, reader_person_id=world.teacher.person_id
    ).names
    assert twin == [TEACHER_NAME], f"The twin was answered {twin}."
    nobody = ask_the_definer(world.application_session, section_id=world.taught).names
    assert nobody == [], (
        f"The definer, called with both reader keys null, answered {nobody}. The ruling on B1: "
        "exactly one reader key is non-null, else zero rows."
    )


def test_a_call_naming_both_reader_keys_answers_nothing_even_for_a_real_reader(
    staff_names: StaffNameWorld,
) -> None:
    """Both keys set — each a real reader of `F1WW` alone — answers zero rows.

    The student's user key alone is answered, the teacher's person key alone is
    answered, and the two together are not: "exactly one reader key is non-null,
    else zero rows".

    **The mutation this kills:** the two branches OR-ed with no exactly-one guard,
    which lets a caller pair any person key with a borrowed user key.
    """
    world = staff_names
    prepared(world)
    assert world.teacher is not None
    student = world.a_student("both-keys", world.taught)
    alone = (
        student_answer(world, world.taught, student),
        ask_the_definer(
            world.application_session,
            section_id=world.taught,
            reader_person_id=world.teacher.person_id,
        ).names,
    )
    assert alone == ([TEACHER_NAME], [TEACHER_NAME]), (
        f"The twins: the student's user key alone and the teacher's person key alone were answered "
        f"{alone}."
    )
    both = ask_the_definer(
        world.application_session,
        section_id=world.taught,
        reader_user_id=student.user_id,
        reader_person_id=world.teacher.person_id,
    ).names
    assert both == [], (
        f"The definer, called with both reader keys set, answered {both}. The ruling on B1: "
        "exactly one reader key is non-null, else zero rows."
    )


def test_a_person_holding_nothing_and_ids_naming_nobody_are_answered_nothing(
    staff_names: StaffNameWorld,
) -> None:
    """A person with no grant; a person key and a user key that name no row.

    **The mutation this kills:** a check that fails open on a reader it cannot
    resolve. **The twin:** the section's instructor, answered.
    """
    world = staff_names
    prepared(world)
    assert world.teacher is not None
    nobody = world.a_named_person("Nobody Inparticular")

    twin = staff_answers(world, world.taught, world.teacher)
    assert twin == ([TEACHER_NAME], [TEACHER_NAME]), f"The twin was answered {twin}."
    holding_nothing = staff_answers(
        world, world.taught, Person(person_id=nobody, name="", label="a person holding nothing")
    )
    no_such_person = ask_the_definer(
        world.application_session, section_id=world.taught, reader_person_id=uuid4()
    ).names
    no_such_user = ask_the_definer(
        world.application_session, section_id=world.taught, reader_user_id=uuid4()
    ).names
    assert holding_nothing == ([], []) and no_such_person == [] and no_such_user == [], (
        f"A person holding nothing was answered {holding_nothing} (service, definer); a person key "
        f"naming nobody {no_such_person}; a user key naming nobody {no_such_user}. {REFUSAL}"
    )


# The whole reader rule, written out by hand for this world (SPEC §2.1, §5.3, work
# order decision 1 and the ruling on B1): who is answered for which section, under
# which key. Every pair not listed is answered nothing.
TAUGHT = "the taught section"
SIBLING = "the sibling section"
SIBLING_COURSE = "the sibling course's section"
UNMAPPED = "the unmapped course's section"
EVERY_SECTION = (TAUGHT, SIBLING, SIBLING_COURSE, UNMAPPED)
BY_PERSON = "person"
BY_USER = "user"
READS: dict[str, tuple[str, set[str]]] = {
    "teacher": (BY_PERSON, {TAUGHT}),
    "sibling_section_teacher": (BY_PERSON, {SIBLING}),
    "sibling_course_teacher": (BY_PERSON, {SIBLING_COURSE}),
    "unmapped_teacher": (BY_PERSON, {UNMAPPED}),
    # The own course holds F1WW and Q1WW, and its lead reads both.
    "lead": (BY_PERSON, {TAUGHT, SIBLING}),
    "sibling_lead": (BY_PERSON, {SIBLING_COURSE}),
    # Both other courses of the department have leads; the chair reads only the unled one.
    "chair": (BY_PERSON, {UNMAPPED}),
    "other_chair": (BY_PERSON, set()),
    "former_teacher": (BY_PERSON, set()),
    "live_student": (BY_USER, {TAUGHT}),
    "ended_student": (BY_USER, set()),
    "sibling_student": (BY_USER, {SIBLING}),
    "two_hat_as_a_student": (BY_USER, {SIBLING}),
    "two_hat_as_a_teacher": (BY_PERSON, {SIBLING_COURSE}),
}


def test_the_definer_answers_exactly_the_reader_rule_over_every_reader_and_section(
    staff_names: StaffNameWorld,
) -> None:
    """Fourteen readings by four sections: non-empty exactly where the rule says, empty elsewhere.

    The work order asks for one world holding each reader kind and each
    one-level-out non-reader, with the SQL rule pinned against the Python rules it
    copies (`survey_read._live_enrollments`, `teaching_instructor_assigned`,
    `lead_review_courses`). Those functions' signatures are not settled anywhere
    this suite may read, so the rule is written out above from the spec instead.

    **The mutations this kill:** any one branch of the reader check widened or
    narrowed by one grain, or answered on the wrong key.
    """
    world = staff_names
    prepared(world)
    two_hat = world.a_two_hat_person()
    readers: dict[str, Any] = {
        "teacher": world.teacher,
        "sibling_section_teacher": world.sibling_section_teacher,
        "sibling_course_teacher": world.sibling_course_teacher,
        "unmapped_teacher": world.unmapped_teacher,
        "lead": world.lead,
        "sibling_lead": world.sibling_lead,
        "chair": world.chair,
        "other_chair": world.other_chair,
        "former_teacher": world.a_former_teacher_of_the_taught_section(),
        "live_student": world.a_student("matrix-live", world.taught),
        "ended_student": world.a_student("matrix-ended", world.taught, ended=True),
        "sibling_student": world.a_student("matrix-sibling", world.sibling_section),
        "two_hat_as_a_student": two_hat,
        "two_hat_as_a_teacher": two_hat,
    }
    assert set(readers) == set(READS), "The table and the world name different readers."
    sections = world.every_section()
    assert set(sections) == set(EVERY_SECTION), "The table and the world name different sections."

    wrong: list[str] = []
    for key, reader in readers.items():
        assert reader is not None, f"The world has no {key}."
        kind, reads = READS[key]
        for label, section_id in sections.items():
            if kind == BY_USER:
                answered = ask_the_definer(
                    world.application_session, section_id=section_id, reader_user_id=reader.user_id
                )
            else:
                answered = ask_the_definer(
                    world.application_session,
                    section_id=section_id,
                    reader_person_id=reader.person_id,
                )
            should = label in reads
            if bool(answered.rows) != should:
                wrong.append(
                    f"{key} (by {kind} key) asking about {label}: answered {answered.names}, "
                    f"{'should be answered' if should else 'should be answered nothing'}"
                )
    assert any(reads for _, reads in READS.values()), "The table expects nothing anywhere."
    assert not wrong, "The definer's reader set is not the rule:\n  " + "\n  ".join(wrong)
