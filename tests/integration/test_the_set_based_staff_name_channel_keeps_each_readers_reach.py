"""The set-based channel names staff to its readers only — E9-03, done-whens 3 and 4, SPEC §4.1.

> 3. A student of section A gets A's rows and nothing for section B passed in the
>    same call; an instructor of A likewise; a lead of A's course gets A's rows and
>    nothing for a sibling lead's section. Each refused row has its present twin
>    in the same call.
> 4. A dean's, an assistant dean's, a VP's and a chair's call with any section ids
>    is answered; a lead's call is answered only for sections of courses they lead,
>    even when the call passes a sibling lead's section; a person with no live
>    assignment and no enrollment gets nothing; a Care-only and an Admin-only
>    person get nothing. A `pulse_app` session cannot call v001 or v002 with a
>    reader key it chooses to gain more than that key holds.

**Every case calls the definer directly, as `pulse_app`.** The reader keys are
checked inside the function (the ticket, and ADR 0191), so the refusal asserted
here is the database's: no door, no route and no scope sits between the caller and
the answer. That is the last sentence of done-when 4, asserted in every test.

**What a refusal is here.** The definer answers a refused section with no rows,
the same answer as a section with no staff; so every refusal sits beside its
present twin **in the same call** (done-when 3) or in the same world under a
reader who is answered (`docs/MISTAKES.md` entry 3). A refusal is the absence of
one section's rows from an answer that is otherwise non-empty.

**Every reader set is a closed set, attacked one level out** (`docs/MISTAKES.md`
entry 53): a lead who also teaches elsewhere is still only a lead; a lead who also
chairs another department holds `CHAIR`; a dean asked by their user key rather
than their person key; and both reader keys at once.

**Which failure a red is, before E9-03 lands.** Every test fails on `require_v2`,
naming `public.section_staff_names(uuid[],uuid,uuid,date)`.
"""

from typing import Any

import pytest
from fixtures.roster_sync import institution_today
from fixtures.staff_names import Person, StaffNameWorld
from fixtures.staff_names_for_sections import (
    AS_INSTRUCTOR,
    CHAIR_ROLE,
    SetAnswer,
    SetWorld,
    ask_v2,
    prepared,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]


def by_person(names: StaffNameWorld, reader: Person, sections: list[Any]) -> SetAnswer:
    return ask_v2(
        names.application_session,
        section_ids=sections,
        reader_person_id=reader.person_id,
        reader_date=institution_today(),
    )


def by_user(names: StaffNameWorld, reader: Person, sections: list[Any]) -> SetAnswer:
    assert reader.user_id is not None, f"{reader.label} has no user key to be asked by."
    return ask_v2(
        names.application_session,
        section_ids=sections,
        reader_user_id=reader.user_id,
        reader_date=institution_today(),
    )


def refused(reader: Person, where: str, answer: SetAnswer, section: Any) -> str:
    return (
        f"{reader.label} was answered {answer.of(section)} for {where}, in a call that answered "
        f"{len(answer.rows)} rows in all. E9-03 done-whens 3 and 4: a reader keeps exactly v001's "
        "reach per section, and chair and above alone are answered for any section passed."
    )


# ---------------------------------------------------------------------------
# Done-when 3: the existing readers keep their reach, per section, in one call.
# ---------------------------------------------------------------------------


def test_a_student_of_one_section_is_answered_nothing_for_another_passed_in_the_same_call(
    staff_names_for_sections: SetWorld,
) -> None:
    """Enrolled in F1WW, asking for F1WW and Q1WW: F1WW's rows, and none for Q1WW.

    **The mutation this kills:** the student check written over the array ("is
    enrolled in any of `p_section_ids`"), which answers every section passed
    beside the one the student attends. **The near miss:** the check at course
    grain; F1WW and Q1WW share a course.
    """
    names = staff_names_for_sections.names
    prepared(names)
    student = names.a_student("set-student", names.taught)
    answer = by_user(names, student, [names.taught, names.sibling_section])
    assert answer.of(names.taught), f"The twin: the student was answered {answer} for F1WW."
    assert not answer.of(names.sibling_section), refused(
        student, "Q1WW, a section they are not enrolled in", answer, names.sibling_section
    )


def test_an_instructor_of_one_section_is_answered_nothing_for_another_passed_in_the_same_call(
    staff_names_for_sections: SetWorld,
) -> None:
    """Teaching F1WW, asking for F1WW and Q1WW: F1WW's rows, and none for Q1WW.

    **The mutation this kills:** the instructor check over the array ("teaches any
    of `p_section_ids`"). **The near miss:** at course grain.
    """
    names = staff_names_for_sections.names
    prepared(names)
    assert names.teacher is not None
    answer = by_person(names, names.teacher, [names.taught, names.sibling_section])
    assert answer.of(names.taught), "The twin: the instructor was answered nothing for F1WW."
    assert not answer.of(names.sibling_section), refused(
        names.teacher, "Q1WW, a section they do not teach", answer, names.sibling_section
    )


def test_a_lead_is_answered_nothing_for_a_sibling_leads_section_passed_in_the_same_call(
    staff_names_for_sections: SetWorld,
) -> None:
    """The own course's lead, asking for F1WW and the sibling course's section: F1WW only.

    SPEC §4.1 item 2, and README decision 16: a lead keeps v001's per-section
    check whatever the door passes.

    **The mutations this kill:** ruling 3's broad answer given to `LEAD_FACULTY`
    (decision 16 un-narrowed); the lead check over the array ("leads the course
    of any section passed"); the lead check at prefix grain (both courses share
    one prefix).
    """
    names = staff_names_for_sections.names
    prepared(names)
    assert names.lead is not None
    answer = by_person(names, names.lead, [names.taught, names.sibling_course_section])
    assert answer.of(names.taught), "The twin: the lead was answered nothing for their own F1WW."
    assert not answer.of(names.sibling_course_section), refused(
        names.lead, "the sibling lead's section", answer, names.sibling_course_section
    )


# ---------------------------------------------------------------------------
# Done-when 4: chair and above for any section; a lead per section; nobody else.
# ---------------------------------------------------------------------------

BROAD_READERS = ("the dean", "the assistant dean", "the vice president", "the chair")


def a_broad_reader(world: SetWorld, which: str) -> Person:
    if which == "the dean":
        return world.a_dean()
    if which == "the assistant dean":
        return world.an_assistant_dean()
    if which == "the vice president":
        return world.a_vice_president()
    assert world.names.chair is not None
    return world.names.chair


@pytest.mark.parametrize("which", BROAD_READERS)
def test_chair_and_above_are_answered_for_every_section_passed(
    staff_names_for_sections: SetWorld, which: str
) -> None:
    """Five sections, in two departments and four courses: every one answered its instructor.

    The four sections of E7-01's world (two in a led course, one in a sibling
    lead's course, one in an unled course) and a section in a second, chairless
    department of the same college. Ruling 3: a reader holding a live `CHAIR`,
    `ASSISTANT_DEAN`, `DEAN` or `VP_ACADEMICS` assignment is answered for any
    section passed; the purview is the door's to apply, not the definer's.

    **The mutations this kill:** one of the four roles left out of the broad
    answer (the assistant dean is the likeliest: it is not in v001's vocabulary);
    the role spelled differently from the assignment's own value; the chair's
    broad answer confined to their own department (the chairless department's
    section goes missing) or to unled courses (v001's chair limb).
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    reader = a_broad_reader(world, which)
    world.a_section_in_a_department_with_no_chair()
    teachers = {
        names.taught: names.teacher,
        names.sibling_section: names.sibling_section_teacher,
        names.sibling_course_section: names.sibling_course_teacher,
        names.unmapped_section: names.unmapped_teacher,
        world.chairless_section: world.chairless_teacher,
    }
    expected = set()
    for section, teacher in teachers.items():
        assert teacher is not None
        expected.add((str(section), AS_INSTRUCTOR, str(teacher.person_id)))

    answer = by_person(names, reader, list(teachers))
    instructors = {row.triple for row in answer.rows if row.role == AS_INSTRUCTOR}
    assert instructors == expected, (
        f"{reader.label} asked for five sections and was answered instructor rows "
        f"{sorted(instructors)}, not {sorted(expected)}. Ruling 3: chair and above are answered for "
        "any section passed."
    )


def test_a_lead_who_also_chairs_another_department_is_answered_for_a_sibling_leads_section(
    staff_names_for_sections: SetWorld,
) -> None:
    """The boundary of decision 16, as a pair: lead only, refused; lead and a chair, answered.

    The own course's lead asks for the sibling course's section and is answered
    nothing (their only leadership is `LEAD_FACULTY`). The same person is then
    given `CHAIR` of a bare new department and asks again: answered, because a
    reader holding a live `CHAIR` is answered for any section passed.

    **The mutations this kill:** the per-section check applied to anyone holding
    `LEAD_FACULTY` at all (the second half stays empty), and the broad answer
    given to anyone holding any leadership assignment (the first half is
    answered).
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    assert names.lead is not None
    sections = [names.taught, names.sibling_course_section]

    before = by_person(names, names.lead, sections)
    assert before.of(names.taught), "The twin: the lead was answered nothing for their own F1WW."
    assert not before.of(names.sibling_course_section), refused(
        names.lead,
        "the sibling lead's section, holding only LEAD_FACULTY",
        before,
        names.sibling_course_section,
    )

    department = world.a_new_department()
    world.review.graph.assign(CHAIR_ROLE, scope=department, person=names.lead.person_id)
    world.review.rows.commit()
    after = by_person(names, names.lead, sections)
    assert after.of(names.sibling_course_section), (
        f"The lead, now also chair of another department, asked for the sibling lead's section "
        f"and was answered {after.of(names.sibling_course_section)}. Ruling 3: a reader holding a "
        "live CHAIR assignment is answered for any section passed."
    )


def test_a_lead_who_also_teaches_elsewhere_is_still_answered_nothing_for_a_sibling_leads_section(
    staff_names_for_sections: SetWorld,
) -> None:
    """Lead of the own course and instructor of the unled course's section: still only a lead.

    Asking for the unled section and the sibling lead's section: the unled section
    is answered (they teach it) and the sibling lead's is not. A teaching grant is
    not a leadership assignment (README ruling 4).

    **The mutation this kills:** the broad answer given to "anyone holding an
    assignment that is not `LEAD_FACULTY`", which a teaching grant satisfies.
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    assert names.lead is not None
    names.teaches(names.lead.person_id, names.unmapped_section)

    answer = by_person(names, names.lead, [names.unmapped_section, names.sibling_course_section])
    assert answer.of(names.unmapped_section), (
        "The twin: the lead, who also teaches the unled course's section, was answered nothing "
        "for it."
    )
    assert not answer.of(names.sibling_course_section), refused(
        names.lead,
        "the sibling lead's section, while also teaching elsewhere",
        answer,
        names.sibling_course_section,
    )


NOBODIES = (
    "a person holding nothing, by person key",
    "a user with no enrollment, by user key",
    "a Care-only person",
    "an Admin-only person",
    "the dean, by user key",
)


def a_nobody(world: SetWorld, which: str) -> tuple[Person, str]:
    """The reader, and the key the definer is asked by."""
    if which == "a person holding nothing, by person key":
        return world.a_person_holding_nothing(), "person"
    if which == "a user with no enrollment, by user key":
        return world.a_person_holding_nothing(), "user"
    if which == "a Care-only person":
        return world.a_care_holder(), "person"
    if which == "an Admin-only person":
        return world.an_admin(), "person"
    return world.a_dean(), "user"


@pytest.mark.parametrize("which", NOBODIES)
def test_a_reader_with_no_teaching_enrollment_or_leadership_is_answered_nothing(
    staff_names_for_sections: SetWorld, which: str
) -> None:
    """Asking for all four sections: nothing. The twin: the chair, in the same world, is answered.

    Care and Admin assignments are not leadership (SPEC §6.2: Care contributes
    nothing to a purview; ruling 1: Admin runs the system). The dean asked by
    their **user** key is the one-level-out case: the leadership check runs on the
    person key, as v001's staff checks do (ADR 0191), so a user key borrowed from
    a person who holds `DEAN` reaches nothing.

    **The mutations this kill:** the broad answer for "any live assignment"
    (Care, Admin); a check that fails open on a reader it cannot resolve; and
    the leadership check reached from a user key through `person.user_id`.
    """
    world = staff_names_for_sections
    names = world.names
    prepared(names)
    assert names.chair is not None
    sections = list(names.every_section().values())
    reader, key = a_nobody(world, which)

    twin = by_person(names, names.chair, sections)
    assert twin.sections == {str(section) for section in sections}, (
        f"The twin: the chair asked for the four sections and was answered rows for "
        f"{sorted(twin.sections)} only."
    )
    ask = by_user if key == "user" else by_person
    answer = ask(names, reader, sections)
    assert answer.rows == [], (
        f"{reader.label} ({which}) asked for the four sections and was answered {answer.rows}. "
        "E9-03 done-when 4: a person with no live assignment and no enrollment, a Care-only person "
        "and an Admin-only person get nothing."
    )


def test_a_call_naming_both_reader_keys_is_answered_nothing_even_for_a_real_reader(
    staff_names_for_sections: SetWorld,
) -> None:
    """A student's user key and the instructor's person key, each answered alone; together, nothing.

    v001's rule, kept for v002 (the ticket: "v001's reader checks, kept as they
    are"): exactly one reader key is non-null, or the answer is empty.

    **The mutation this kills:** the branches OR-ed with no exactly-one guard,
    which lets a caller pair any person key with a borrowed user key.
    """
    names = staff_names_for_sections.names
    prepared(names)
    assert names.teacher is not None
    student = names.a_student("set-both-keys", names.taught)
    as_student = by_user(names, student, [names.taught])
    as_teacher = by_person(names, names.teacher, [names.taught])
    assert as_student.rows and as_teacher.rows, (
        f"The twins: the student's key alone was answered {as_student.rows} and the instructor's "
        f"alone {as_teacher.rows}."
    )
    both = ask_v2(
        names.application_session,
        section_ids=[names.taught],
        reader_user_id=student.user_id,
        reader_person_id=names.teacher.person_id,
        reader_date=institution_today(),
    )
    assert both.rows == [], (
        f"The overload, called with both reader keys set, answered {both.rows}. Exactly one reader "
        "key is non-null, else zero rows (ADR 0191)."
    )
