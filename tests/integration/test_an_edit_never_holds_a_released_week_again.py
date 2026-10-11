"""An edit never holds a released week again — E7-02, done-when 5.

> **An edit never re-holds.** A second row for a released week changes the text
> the student reads and leaves the week released, including when the policy
> changed in between. The latest row by `sequence` is the one read, including
> two rows written in one transaction.

Ruling 3: "A week is released by the first response row. Later rows change the
text students read, never the release." Work order decision 3: the text is the
latest row's body; the author shown is the first row's.

**The sequence, not one payload** (`docs/MISTAKES.md` entry 51). Each edit is
asserted as a pair of reads either side of it, through decision 6's writer: what
changed between them is the text, and only the text.

**Course week 2** of `F1WW`, required by its lead a day before the report opens,
read an hour after it opens. Rows planted directly are dated minutes after the
opening and before the reading clock.

**Which failure a red is, before E7-02 lands.** Every test fails naming M2's
`course_id` in its first planted row, or the missing route.
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from fixtures.staff_names import LEAD_NAME, TEACHER_NAME
from fixtures.student_read import response_surface
from fixtures.the_hold import (
    AUTHOR_NAME,
    ENCOURAGED,
    FIRST_ROW_AFTER_OPENING,
    HELD_WEEK,
    INSTRUCTOR,
    LEAD_FACULTY,
    ON_BEHALF,
    POLICY_CHANGE_AFTER_OPENING,
    PUBLISHED,
    REQUIRED,
    RESPONSE,
    SECOND_ROW_AFTER_OPENING,
    STATE,
    TEXT,
    HoldWorld,
    report_opens,
)

pytestmark = pytest.mark.integration

FIRST_TEXT = "E7-02 the first version: the quiz moves to Thursday"
SECOND_TEXT = "E7-02 the edited version: the quiz moves to Friday instead"


def required_a_day_early(world: HoldWorld) -> None:
    world.a_policy(
        course=world.own_course,
        setter=world.person(world.names.lead).person_id,
        role=LEAD_FACULTY,
        mode=REQUIRED,
        set_at=report_opens(HELD_WEEK) - timedelta(days=1),
    )


@pytest.mark.parametrize(
    ("author_is", "role", "state", "name"),
    [
        ("the-teacher", INSTRUCTOR, PUBLISHED, TEACHER_NAME),
        ("the-lead", LEAD_FACULTY, ON_BEHALF, LEAD_NAME),
    ],
)
def test_an_edit_changes_the_text_between_two_reads_and_leaves_the_week_released(
    hold: HoldWorld, author_is: str, role: str, state: str, name: str
) -> None:
    """Publish, read, edit through the writer, read: the text moves and nothing else does.

    Entry 51's pair either side of the edit: the state and the author are the
    same in both reads, the text is the first row's and then the second's, and
    the first text is gone from the second read.

    **The mutations this kill:** the text read from the first row (the edit never
    shows); an edit that re-evaluates the hold (any state but the first read's);
    and, for the lead, an on-behalf week that an edit turns into the
    instructor's own. **The near miss:** the first read, which must show the
    first text.
    """
    world = hold
    required_a_day_early(world)
    author = world.person(world.names.teacher if author_is == "the-teacher" else world.names.lead)
    student = world.a_student(f"edit-{author_is}", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    world.publish(
        section_id=world.taught,
        course_week=HELD_WEEK,
        author=author.person_id,
        role=role,
        body=FIRST_TEXT,
    )
    before = world.payload(student, course_week=HELD_WEEK)
    world.publish(
        section_id=world.taught,
        course_week=HELD_WEEK,
        author=author.person_id,
        role=role,
        body=SECOND_TEXT,
    )
    after_answer = world.results(student, course_week=HELD_WEEK)
    after = world.payload(student, course_week=HELD_WEEK)

    assert (before[STATE], before[RESPONSE][TEXT]) == (
        state,
        FIRST_TEXT,
    ), f"After the first row the week read {before!r}; expected {state!r} with the first text."
    assert after[STATE] == state, (
        f"After the edit the week read {after[STATE]!r}, not {state!r}. Ruling 3: an edit never "
        "holds the week again, and the release is the first row's."
    )
    assert (
        after[RESPONSE][TEXT] == SECOND_TEXT
    ), f"After the edit the text read is {after[RESPONSE][TEXT]!r}. Students see the latest row."
    assert after[RESPONSE][AUTHOR_NAME] == before[RESPONSE][AUTHOR_NAME] == name
    assert FIRST_TEXT not in response_surface(
        after_answer
    ), "The edited week still carries the first version's text."


@pytest.mark.parametrize("mode_in_between", [REQUIRED, ENCOURAGED])
def test_an_edit_after_the_policy_changed_leaves_the_week_released(
    hold: HoldWorld, mode_in_between: str
) -> None:
    """Required week; the teacher's first row; a policy row after it; the teacher's edit: released.

    The policy row is the lead's, for the own course, dated after the first
    response and before the edit — a switch the week did not open under, in
    either direction.

    **The mutation this kills:** the hold re-evaluated per row — an edit treated
    as a fresh release that a newer `REQUIRED` row (or any newer row) puts back
    behind the door until somebody "publishes" again. **The near miss:** the
    first read, released before the change.
    """
    world = hold
    required_a_day_early(world)
    teacher = world.person(world.names.teacher)
    opens = report_opens(HELD_WEEK)
    world.a_response(
        section_id=world.taught,
        course_week=HELD_WEEK,
        author=teacher.person_id,
        role=INSTRUCTOR,
        body=FIRST_TEXT,
        published_at=opens + FIRST_ROW_AFTER_OPENING,
    )
    student = world.a_student(f"changed-{mode_in_between}", world.taught)
    world.stand_after_the_opening(HELD_WEEK)
    before = world.payload(student, course_week=HELD_WEEK)

    world.a_policy(
        course=world.own_course,
        setter=world.person(world.names.lead).person_id,
        role=LEAD_FACULTY,
        mode=mode_in_between,
        set_at=opens + POLICY_CHANGE_AFTER_OPENING,
    )
    world.a_response(
        section_id=world.taught,
        course_week=HELD_WEEK,
        author=teacher.person_id,
        role=INSTRUCTOR,
        body=SECOND_TEXT,
        published_at=opens + SECOND_ROW_AFTER_OPENING,
    )
    after = world.payload(student, course_week=HELD_WEEK)

    assert before[STATE] == PUBLISHED, f"After the first row the week read {before[STATE]!r}."
    assert after[STATE] == PUBLISHED, (
        f"A {mode_in_between} switch between the first row and the edit left the week reading "
        f"{after[STATE]!r}. Done-when 5: the week stays released."
    )
    assert after[RESPONSE][TEXT] == SECOND_TEXT


def test_two_rows_written_in_one_transaction_read_the_second(hold: HoldWorld) -> None:
    """Two rows for one section-week, one commit, one `published_at`: the second inserted is read.

    The first row is given the larger primary key, so an order by key disagrees
    with insertion order; the two share a timestamp, as two rows of one
    transaction do (SPEC §8: "two decisions written in one transaction share its
    timestamp").

    **The mutations this kill:** "latest" read by primary key (the first row
    wins); "latest" read by `published_at` alone (a tie the database breaks as it
    likes, which `test_the_latest_row_is_the_latest_by_sequence_even_when_its_
    time_is_earlier` pins deterministically).
    """
    world = hold
    required_a_day_early(world)
    teacher = world.person(world.names.teacher)
    smaller, larger = sorted([uuid4(), uuid4()])
    published_at = report_opens(HELD_WEEK) + FIRST_ROW_AFTER_OPENING
    for key, text in ((larger, FIRST_TEXT), (smaller, SECOND_TEXT)):
        world.rows.seed(
            "instructor_response",
            {},
            **world.response_values(
                section_id=world.taught,
                course_week=HELD_WEEK,
                author=teacher.person_id,
                role=INSTRUCTOR,
                body=text,
                published_at=published_at,
                id=key,
            ),
        )
    world.rows.commit()
    stored = world.rows_of("instructor_response", "section_id", world.taught)
    assert [row["body"] for row in stored] == [FIRST_TEXT, SECOND_TEXT], (
        f"The two rows are stored in `sequence` order as {[row['body'] for row in stored]}; the "
        "premise is that the second inserted carries the larger `sequence`."
    )
    student = world.a_student("one-transaction", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    body = world.payload(student, course_week=HELD_WEEK)

    assert body[RESPONSE][TEXT] == SECOND_TEXT, (
        f"Two rows written in one transaction: the student read {body[RESPONSE][TEXT]!r}. The "
        "latest by `sequence` is the second."
    )


def test_the_latest_row_is_the_latest_by_sequence_even_when_its_time_is_earlier(
    hold: HoldWorld,
) -> None:
    """The edit carries an earlier `published_at` than the first row; the edit's text is read.

    A development clock moved backwards between a publish and its edit writes
    exactly this, and SPEC §8 makes "latest" the sequence, never a time.

    **The mutation this kills:** the latest row chosen by `published_at`.
    """
    world = hold
    required_a_day_early(world)
    teacher = world.person(world.names.teacher)
    opens = report_opens(HELD_WEEK)
    inserted_in_order = (
        (FIRST_TEXT, SECOND_ROW_AFTER_OPENING),
        (SECOND_TEXT, FIRST_ROW_AFTER_OPENING),
    )
    for text, after in inserted_in_order:
        world.a_response(
            section_id=world.taught,
            course_week=HELD_WEEK,
            author=teacher.person_id,
            role=INSTRUCTOR,
            body=text,
            published_at=opens + after,
        )
    student = world.a_student("earlier-edit", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    body = world.payload(student, course_week=HELD_WEEK)

    assert body[RESPONSE][TEXT] == SECOND_TEXT, (
        f"The edit was inserted second with an earlier time, and the student read "
        f"{body[RESPONSE][TEXT]!r}. The latest is by `sequence`."
    )
