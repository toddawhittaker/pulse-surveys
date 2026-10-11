"""The survey payload names the student's section's instructors — E7-01, done-when 2.

> A student with a live enrollment in a section gets that section's instructor's
> name, through the survey payload.

Work order decision 3: "The survey payload's section entry gains `instructors:
list[str]` (names only, sorted; empty when none)", read through the channel.

**The reader is a real launched student**, the one E2-09's door lands
(`tests/fixtures/student_read.py`) — a `user` row and no `person` (ADR 0028) —
reading `GET /student/survey` with the session that launch issued, on the
application's own connection (`docs/MISTAKES.md` entry 46). The ruling on B1 is
what lets the payload ask the channel for this student: by user key. The world holds a sibling section of the same course with a student
and a submission of its own; here it is also given an instructor whose name must
never reach this student (SPEC §4.1 item 1: students never see other sections).

**Where the entry is found.** By walking the answer for the one object carrying
`instructors` (`objects_carrying`), not by indexing a path the ticket does not
settle. The reader has one live enrollment, so there must be exactly one.

**Which failure a red is, before E7-01 lands.** Every test fails on that walk:
no object carries `instructors`.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fixtures.report_api import INSTRUCTOR_ROLE
from fixtures.staff_names import (
    AI_SEEDED_COLUMN,
    IDENTITY_NAME_COLUMN,
    INSTRUCTOR_RESPONSE,
    INSTRUCTORS_FIELD,
    PERSON_TABLE,
    RESPONSE_AUTHOR_COLUMN,
    RESPONSE_BODY_COLUMN,
    RESPONSE_SECTION_COLUMN,
    RESPONSE_TIME_COLUMN,
    ROLE_COLUMN,
    WEEK_COLUMN,
)
from fixtures.student_read import (
    StudentReadDoor,
    decoded,
    objects_carrying,
    response_surface,
)
from fixtures.supervision import require_table, single_primary_key

pytestmark = pytest.mark.integration

ENROLLED_TEACHER = "Aurelio Zabriskie-Teaches-You"
SECOND_ENROLLED_TEACHER = "Zephyrine Abbott-Also-Teaches-You"
OTHER_SECTION_TEACHER = "Thaddeus Wimbleton-Teaches-Elsewhere"
ON_BEHALF_AUTHOR = "Leocadia Pemberton-Wrote-On-Behalf"


def a_teacher(
    door: StudentReadDoor, web_identity: Any, section_id: Any, name: str, **key: Any
) -> Any:
    """A named person holding a live `INSTRUCTOR` assignment on `section_id`, committed."""
    person = web_identity.person(**{IDENTITY_NAME_COLUMN: name}, **key)
    door.world.rows.graph.assign(INSTRUCTOR_ROLE, scope=section_id, person=person)
    door.world.rows.commit()
    return person


def the_entry(door: StudentReadDoor) -> tuple[dict[str, Any], Any]:
    """The one section entry of this student's read, and the response it came in."""
    answered = door.get()
    assert answered.status_code == 200, (
        f"The student's own read answered {answered.status_code}. Body begins "
        f"{answered.text[:400]!r}."
    )
    body = decoded(answered, "The student's survey read")
    entries = objects_carrying(body, INSTRUCTORS_FIELD)
    assert len(entries) == 1, (
        f"{len(entries)} objects in the student's answer carry `{INSTRUCTORS_FIELD}`, and the "
        f"student has one live enrollment. Body begins {answered.text[:400]!r}.\n\n"
        f"E7-01 work order decision 3: the section entry gains `{INSTRUCTORS_FIELD}: list[str]` "
        "(names only, sorted; empty when none)."
    )
    return entries[0], answered


def test_a_section_with_no_instructor_answers_an_empty_list(
    student_read_door: StudentReadDoor,
) -> None:
    """Nobody teaches the enrolled section: the member is present and is `[]`.

    **The mutation this kills:** the member optional and `null` (or absent) when
    there is nobody, which a page reads as a missing field rather than as "no
    instructor yet". **The near miss:** any non-empty list, which would be a name
    from somewhere else.
    """
    entry, answered = the_entry(student_read_door)
    assert entry[INSTRUCTORS_FIELD] == [], (
        f"The enrolled section has no instructor, and its entry carries "
        f"`{INSTRUCTORS_FIELD}` = {entry[INSTRUCTORS_FIELD]!r}. Decision 3: empty when none."
    )


@pytest.mark.invariant
def test_the_enrolled_sections_instructor_is_named_and_the_other_sections_is_nowhere(
    student_read_door: StudentReadDoor, web_identity: Any
) -> None:
    """One instructor on each sibling section: the student's entry names theirs, and only theirs.

    **The mutation this kills:** the payload asking the channel about the wrong
    section, or about every section of the course, which names the sibling
    section's instructor somewhere in the answer — a §4.1 item 1 leak. **The
    positive half** is what makes the absence mean something: the student's own
    instructor is named, so the channel is answering this reader at all.
    """
    door = student_read_door
    world = door.world
    a_teacher(door, web_identity, world.enrolled_section_id, ENROLLED_TEACHER)
    a_teacher(door, web_identity, world.other_section_id, OTHER_SECTION_TEACHER)

    entry, answered = the_entry(door)
    assert entry[INSTRUCTORS_FIELD] == [ENROLLED_TEACHER], (
        f"The enrolled section's entry carries `{INSTRUCTORS_FIELD}` = "
        f"{entry[INSTRUCTORS_FIELD]!r}; its one instructor is {ENROLLED_TEACHER!r}. Done-when 2: a "
        "student with a live enrollment gets the section's instructor's name through the payload."
    )
    surface = response_surface(answered)
    assert OTHER_SECTION_TEACHER not in surface, (
        f"The student's answer names {OTHER_SECTION_TEACHER!r}, who teaches the sibling section "
        "the student is not enrolled in. SPEC §4.1 item 1: students never see other sections."
    )


def test_a_response_author_who_does_not_teach_the_section_is_not_listed_as_an_instructor(
    student_read_door: StudentReadDoor, web_identity: Any, metadata_tables: dict[str, Any]
) -> None:
    """A lead published a response to the enrolled section: `instructors` still names only its teacher.

    The ruling appended to the work order: "`instructors` in the survey payload
    lists the section's live teaching instructors only. Response authors are
    answered by the channel, but the survey payload does not show them."

    **The mutation this kills:** the payload copying the channel's whole answer
    into `instructors`, which names an on-behalf author as the section's teacher.
    **The near miss:** the teacher, who is named.
    """
    door = student_read_door
    world = door.world
    a_teacher(door, web_identity, world.enrolled_section_id, ENROLLED_TEACHER)
    author = web_identity.person(**{IDENTITY_NAME_COLUMN: ON_BEHALF_AUTHOR})
    if INSTRUCTOR_RESPONSE not in metadata_tables:
        pytest.fail(f"`Base.metadata` declares no `{INSTRUCTOR_RESPONSE}`; E7-01's M1 adds it.")
    world.rows.seed(
        INSTRUCTOR_RESPONSE,
        {},
        **{
            RESPONSE_SECTION_COLUMN: world.enrolled_section_id,
            WEEK_COLUMN: world.week[single_primary_key(require_table(metadata_tables, "week"))],
            RESPONSE_AUTHOR_COLUMN: author,
            ROLE_COLUMN: "LEAD_FACULTY",
            AI_SEEDED_COLUMN: False,
            RESPONSE_BODY_COLUMN: "E7-01 an on-behalf response the payload does not attribute",
            RESPONSE_TIME_COLUMN: datetime.now(UTC),
        },
    )
    world.rows.commit()

    entry, _ = the_entry(door)
    assert entry[INSTRUCTORS_FIELD] == [ENROLLED_TEACHER], (
        f"The enrolled section's entry carries `{INSTRUCTORS_FIELD}` = "
        f"{entry[INSTRUCTORS_FIELD]!r}; it lists the live teaching instructor {ENROLLED_TEACHER!r} "
        f"only, never {ON_BEHALF_AUTHOR!r}, who published a response and does not teach it."
    )


def test_two_instructors_are_named_in_sorted_order(
    student_read_door: StudentReadDoor, web_identity: Any, metadata_tables: dict[str, Any]
) -> None:
    """Two instructors on the enrolled section: both named, alphabetically.

    The `Z…` instructor is assigned first and given the smaller person key, so
    insertion order and key order both put it first; only an order by name puts
    `A…` first.

    **The mutation this kills:** the names left in whatever order the channel
    returned them, which decision 3 rules out ("sorted").
    """
    door = student_read_door
    world = door.world
    key = single_primary_key(require_table(metadata_tables, PERSON_TABLE))
    smaller, larger = sorted([uuid4(), uuid4()])
    a_teacher(
        door, web_identity, world.enrolled_section_id, SECOND_ENROLLED_TEACHER, **{key: smaller}
    )
    a_teacher(door, web_identity, world.enrolled_section_id, ENROLLED_TEACHER, **{key: larger})

    entry, _ = the_entry(door)
    assert entry[INSTRUCTORS_FIELD] == [ENROLLED_TEACHER, SECOND_ENROLLED_TEACHER], (
        f"The enrolled section's entry carries `{INSTRUCTORS_FIELD}` = "
        f"{entry[INSTRUCTORS_FIELD]!r}; decision 3 settles both names, sorted: "
        f"{[ENROLLED_TEACHER, SECOND_ENROLLED_TEACHER]}."
    )
