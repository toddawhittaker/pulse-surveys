"""The course a student is looking at, named on the read answer — ticket E2-17 item 5.

E2-17's fifth criterion: "the read answer carries the course label, pinned by an
integration test; the headings render it". The heading is `tests/e2e`'s; this
module is the wire.

**What the ticket settles, and what it leaves open.** The member is
`course_label` and its value is `"<prefix code> <lms_number> — <lms_title>"` —
both settled in E2-17's work order, and both transcribed once in
`tests/fixtures/student_read.py` rather than spelled here. Everything else is the
implementer's: where in the answer the member sits, whether the answer is one
object or a list of them, and how the label is assembled. So the field is found
by walking the answer the way E2-09's own week-number test walks it, and never by
indexing a shape.

**The expectation is built out of the rows, not out of the code.** Each label is
composed from the `prefix`, `course` and `section` rows this world seeded, read
back through their own foreign keys, and joined with the spelling the ticket
settles. An expectation derived from the service under test agrees with an
implementation that made the same mistake (`docs/MISTAKES.md` entry 19), and one
written as a literal here would go stale the first time the seeding walker
changed what it invents for a course title.

**The second test is the one a single-section world cannot ask.** A label read
from *a* course rather than from *this section's* course satisfies the first test
completely: the world has one enrolled section, so any lookup that finds any
course finds the right one. So the reader is enrolled in a second section, of a
course that shares nothing with the first, and each entry has to carry its own.

**What is not here** is SPEC §4.1: a course the student is not enrolled in must
not be named at all, and that denial lives in
`tests/integration/test_the_course_label_names_nothing_outside_the_students_enrollment.py`
inside the isolated invariant pass, beside the refusal pair. The two are
different kinds of claim and CI runs one of them twice.
"""

from typing import Any

import pytest
from fixtures.student_read import (
    COURSE_LABEL_FIELD,
    COURSE_NUMBER_COLUMN,
    COURSE_TABLE,
    COURSE_TITLE_COLUMN,
    ENROLLED_SINCE,
    FOREIGN_SECTION_CODE,
    PREFIX_TABLE,
    SECTION_TABLE,
    STUDENT_READ_PATH,
    ForeignCourse,
    StudentReadDoor,
    decoded,
    key_of,
    objects_carrying,
)
from fixtures.survey_windows import SECTION_CODE_COLUMN

pytestmark = [pytest.mark.integration, pytest.mark.lti]


def entries_with_a_label(body: Any) -> list[dict[str, Any]]:
    """Every object anywhere in the answer that carries the label member."""
    return objects_carrying(body, COURSE_LABEL_FIELD)


def named_by(entry: dict[str, Any]) -> set[str]:
    """The scalars one entry carries, as strings, one level deep.

    Used to say *which section* an entry is about without naming the member the
    section rides in. E2-09 settles the two week fields and no others, so a test
    that indexed `entry["section_id"]` would be pinning a schema member no ticket
    settles; a search over the entry's own values finds it however it is spelled
    and fails saying what the entry did carry.
    """
    return {str(value) for value in entry.values() if isinstance(value, str | int | float)}


def entry_for(entries: list[dict[str, Any]], *names: str) -> dict[str, Any]:
    """The one entry that names this section, or a failure saying how many did."""
    matching = [entry for entry in entries if any(name in named_by(entry) for name in names)]
    assert len(matching) == 1, (
        f"{len(matching)} of the {len(entries)} entries carrying `{COURSE_LABEL_FIELD}` name "
        f"{list(names)}. The entries carry {[sorted(named_by(entry))[:6] for entry in entries]}.\n\n"
        "Each entry the read path answers with is about one live enrollment, so exactly one of "
        "them is about this section. None means the answer does not identify its sections at all "
        "— by identifier or by §2.2 code — and two means one enrollment is reported twice."
    )
    return matching[0]


@pytest.fixture
def a_second_course(student_read_door: StudentReadDoor, enrol: Any) -> ForeignCourse:
    """A second live enrollment for this reader, in a section of another course.

    A fixture rather than four lines in a test, because the pairing test and its
    own guard both need the same rows and neither is about how they got there.
    Nothing here decides anything a test reads back as an answer: the label is
    composed from these rows *by the world*, and what the read path answers is the
    subject (`docs/MISTAKES.md` entry 30).
    """
    world = student_read_door.world
    foreign = world.seed_a_course_this_student_is_not_in()
    enrol.enrol(
        user_id=world.user_id,
        section_id=key_of(world.tables, SECTION_TABLE, foreign.section),
        started_on=ENROLLED_SINCE,
        ended_on=None,
    )
    return foreign


def test_the_answer_names_the_course_of_the_section_the_student_is_enrolled_in(
    student_read_door: StudentReadDoor,
) -> None:
    """Criterion 5: the read answer carries the course label.

    The label is `"<prefix code> <lms_number> — <lms_title>"` for the course above
    this student's own section, composed from the three rows this world seeded.
    Today's answer carries four members per section entry and none of them is a
    course name at all, which is the defect E2-17 item 5 exists for: the heading
    renders `E1FF` and a student has to work out which course that is.

    **The mutations this kills.** The field absent altogether, which is the state
    this test is written red against. A label built from two of the three parts —
    the number and the title with no prefix code, or the prefix code and the
    number with no title — each of which reads perfectly well and is not the
    label the ticket settles. And the parts assembled in some other order, or
    joined with some other separator, which a test asserting containment of each
    part separately would pass.

    **The near miss it must survive**: the answer may carry more than this. Only
    the member the criterion names is asserted, and it is asserted wherever in the
    answer it sits.

    **The guard, first.** The three values are read back out of the seeded rows,
    so a green says the answer carried what those rows hold — not that the answer
    and an empty expectation agreed (`docs/MISTAKES.md` entry 3). A label composed
    of blanks would be a string of two spaces and a dash, and the guard is what
    stops that being the thing this test demands.
    """
    world = student_read_door.world
    course = world.parent_row(SECTION_TABLE, COURSE_TABLE, world.enrolled_section)
    prefix = world.parent_row(COURSE_TABLE, PREFIX_TABLE, course)
    parts = {
        "prefix code": prefix[world.prefix_code_column()],
        "course number": course[COURSE_NUMBER_COLUMN],
        "course title": course[COURSE_TITLE_COLUMN],
    }
    blank = sorted(name for name, value in parts.items() if not str(value or "").strip())
    assert not blank, (
        f"The seeded course carries no {blank}; it carries {parts}. The label below is composed "
        "from these three, so a blank among them makes this test demand a label with a hole in it "
        "and a green would mean the read path agreed with the hole (`docs/MISTAKES.md` entry 3)."
    )
    expected = world.course_label_of(world.enrolled_section)

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} for a student with one live "
        f"enrollment inside an open window. Body begins {answered.text[:300]!r}."
    )
    body = decoded(answered, f"`GET {STUDENT_READ_PATH}`")

    entries = entries_with_a_label(body)
    assert entries, (
        f"Nothing in the answer carries a `{COURSE_LABEL_FIELD}`. Body begins "
        f"{answered.text[:300]!r}.\n\n"
        "E2-17 item 5 adds it to the read answer so the survey's own heading can name the course "
        "beside the section code: today the heading reads `E1FF`, which is a §2.2 section code and "
        "not a course anybody recognises. The member is spelled exactly; where it sits is the "
        "implementer's to choose, and this walk finds it anywhere in the answer."
    )
    carried = [entry[COURSE_LABEL_FIELD] for entry in entries]
    assert carried == [expected], (
        f"The answer carries {carried} as `{COURSE_LABEL_FIELD}`; this student's one live "
        f"enrollment is in a section whose course is {expected!r}.\n\n"
        "The label E2-17 settles is `<prefix code> <lms_number> — <lms_title>`, one space either "
        "side of an em dash. A value missing the prefix code, or the title, or joined with some "
        "other punctuation is a different string and is caught here rather than by three "
        "containment checks that would all pass on a label assembled in any order at all."
    )


def test_each_section_is_labelled_with_its_own_course_and_not_with_another(
    student_read_door: StudentReadDoor, a_second_course: ForeignCourse
) -> None:
    """Criterion 5, the half a one-section world cannot ask: the label is *this* section's.

    The reader is enrolled in two sections now, of two courses that share no
    prefix, no number and no title. Each entry has to carry its own course's
    label, and the two labels are asserted to differ before either is looked for
    — over two sections of one course, every wrong lookup answers correctly.

    **The mutations this kills**, and none of them is reachable with one
    enrollment: a label looked up once and repeated on every entry; a label joined
    from the first course the query reaches rather than from the section's own; a
    join written from `course` down to `section` instead of from the section up,
    which pairs each label with whichever section came back first.

    **The near miss it must survive** is the correct answer with the entries in
    either order — the entries are matched to their sections by what they name,
    not by position, because no ticket settles an order for them.
    """
    world = student_read_door.world
    mine = world.course_label_of(world.enrolled_section)
    theirs = world.course_label_of(a_second_course.section)
    assert mine != theirs, (
        f"Both sections this reader is enrolled in label their course {mine!r}, so this test "
        "cannot tell a per-section label from a single lookup repeated. "
        "`seed_a_course_this_student_is_not_in` seeds its own prefix and course precisely so the "
        "two differ."
    )

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} for a student with two live "
        f"enrollments. Body begins {answered.text[:300]!r}."
    )
    entries = entries_with_a_label(decoded(answered, f"`GET {STUDENT_READ_PATH}`"))
    assert len(entries) == 2, (
        f"{len(entries)} entries carry `{COURSE_LABEL_FIELD}` and this reader has two live "
        f"enrollments. Body begins {answered.text[:300]!r}. One means the second enrollment is "
        "missing from the answer entirely, which is a different defect from the one this test is "
        "about and is E2-09's `_live_enrollments`."
    )

    ours = entry_for(
        entries,
        str(world.enrolled_section_id),
        world.enrolled_section[SECTION_CODE_COLUMN],
    )
    other = entry_for(
        entries,
        str(key_of(world.tables, SECTION_TABLE, a_second_course.section)),
        FOREIGN_SECTION_CODE,
    )
    assert (ours[COURSE_LABEL_FIELD], other[COURSE_LABEL_FIELD]) == (mine, theirs), (
        f"The entry naming the first section is labelled {ours[COURSE_LABEL_FIELD]!r} and the "
        f"entry naming the second {other[COURSE_LABEL_FIELD]!r}; their courses are {mine!r} and "
        f"{theirs!r}.\n\n"
        "Two entries carrying the same label is one lookup repeated. The two swapped is a join "
        "that pairs a label with whichever section the query returned first rather than with the "
        "one it belongs to — which is invisible in a world where every section is under one "
        "course, and is why this test seeds a second."
    )
