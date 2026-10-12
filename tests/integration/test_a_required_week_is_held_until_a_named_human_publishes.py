"""A required week is held until a named human publishes — E7-02, done-when 1, 2 and 3.

> 1. **Required holds.** In a required-mode section-week with no response, the
>    student reads `awaiting`, and the payload carries no response, no name and
>    no count.
> 2. **A publish releases.** After one response row, the student reads
>    `published` with the text, the instructor's name and the role.
> 3. **On behalf is honest.** A first response written under the Lead Faculty
>    role (or the chair acting as lead) reads `on-behalf`, with that person's
>    name and role, never the instructor's.

And the fourth state the ticket names: `unanswered`, an encouraged week with no
response. Every read is the student's own, through the route decision 4 settles,
on the built application.

**The sequence, not one payload** (`docs/MISTAKES.md` entry 51). The hold is a
property of what a student sees from one read to the next, so the publish is
asserted as a pair of reads either side of it, through decision 6's writer: the
read before carries nothing, the read after carries the response.

**Every week here is course week 2**, read an hour after its report opens
(2026-10-12 11:00 UTC). A required policy is recorded a day before the opening,
far from the boundary, which is `test_the_policy_in_force_at_report_open_governs_
the_week.py`'s subject rather than this module's.

**Which failure a red is, before E7-02 lands.** Every test fails naming the
missing route (`results_route`), or naming M2's `course_id` where it plants a
policy row first.
"""

import json
from datetime import timedelta

import pytest
from fixtures.course_page_lead import LEAD_NAME_MEMBER
from fixtures.lead_review import UNMAPPED_COHORT
from fixtures.staff_names import (
    CHAIR_NAME,
    LEAD_NAME,
    SIBLING_SECTION_TEACHER_NAME,
    TEACHER_NAME,
    UNMAPPED_TEACHER_NAME,
)
from fixtures.student_read import decoded, response_surface
from fixtures.the_hold import (
    AUTHOR_NAME,
    AUTHOR_ROLE,
    AWAITING,
    CHAIR,
    FIRST_ROW_AFTER_OPENING,
    HELD_WEEK,
    INSTRUCTOR,
    LEAD_FACULTY,
    ON_BEHALF,
    PUBLISHED,
    PUBLISHED_AT,
    REQUIRED,
    RESPONSE,
    SECOND_ROW_AFTER_OPENING,
    STATE,
    TEXT,
    UNANSWERED,
    WEEK_AFTER,
    WEEK_BEFORE,
    HoldWorld,
    instant,
    numbers_in,
    outside_the_week_list,
    report_opens,
)

pytestmark = pytest.mark.integration

# Distinctive texts, so a body found in an answer says which row it came from.
TEACHER_TEXT = "E7-02 the teacher's reply: we will slow the pacing in week three"
LEAD_TEXT = "E7-02 the lead's reply on behalf: the reading list is being reissued"
CHAIR_TEXT = "E7-02 the chair's reply on behalf: the lab clash is fixed from Monday"
SIBLING_TEXT = "E7-02 the sibling section's reply, which this section never shows"
OTHER_WEEK_TEXT = "E7-02 a reply to another week of the same section"
FIRST_TEXT = "E7-02 the two-hat author's first row"
SECOND_TEXT = "E7-02 the two-hat author's second row"


def required(world: HoldWorld) -> None:
    """The own course required by its lead, a day before course week 2's report opens."""
    world.a_policy(
        course=world.own_course,
        setter=world.person(world.names.lead).person_id,
        role=LEAD_FACULTY,
        mode=REQUIRED,
        set_at=report_opens(HELD_WEEK) - timedelta(days=1),
    )


# ---------------------------------------------------------------------------
# Done-when 1: required holds.
# ---------------------------------------------------------------------------


def test_a_required_week_with_no_response_reads_awaiting_with_no_response_name_or_count(
    hold: HoldWorld,
) -> None:
    """Required, no row: `awaiting`, `response` is `None`, and nothing else rides along.

    The section is named and taught (`TEACHER_NAME`), and its sibling section has a
    published response for the same week (`SIBLING_TEXT` by
    `SIBLING_SECTION_TEACHER_NAME`), so a payload that looked a name or a response
    up for the wrong section, or for the course, has one to carry.

    **The mutations this kills:** a held payload carrying the section's instructor
    (a name the closed door does not show), a count of anything (responses,
    respondents, days held — done-when 1's "no count"), or the sibling section's
    response (a lookup keyed on the course and week rather than the section).
    **The near miss:** the state string itself, which is the one thing it carries.
    """
    world = hold
    required(world)
    world.a_response(
        section_id=world.sibling_section,
        course_week=HELD_WEEK,
        author=world.person(world.names.sibling_section_teacher).person_id,
        role=INSTRUCTOR,
        body=SIBLING_TEXT,
        published_at=report_opens(HELD_WEEK) + FIRST_ROW_AFTER_OPENING,
    )
    student = world.a_student("held", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    answered = world.results(student, course_week=HELD_WEEK)
    body = world.payload(student, course_week=HELD_WEEK)

    assert (
        body[STATE] == AWAITING
    ), f"A required week with no response read {body[STATE]!r}. Done-when 1: `awaiting`."
    assert body[RESPONSE] is None, f"The held week carries a response: {body[RESPONSE]!r}."
    # The amendment's A1 puts the published course weeks on every payload; they are
    # week numbers, not a count, and every other number is still forbidden.
    rest = outside_the_week_list(body)
    assert (
        numbers_in(rest) == []
    ), f"The held week carries the number(s) {numbers_in(rest)}. Done-when 1: no count."
    surface = response_surface(answered)
    named = [name for name in (TEACHER_NAME, SIBLING_SECTION_TEACHER_NAME) if name in surface]
    assert not named, f"The held week names {named}. Done-when 1: no name."
    assert SIBLING_TEXT not in surface, "The held week carries the sibling section's response."


def test_an_encouraged_week_with_no_response_reads_unanswered(hold: HoldWorld) -> None:
    """No policy row at all: the week is encouraged (decision 2), and with no row reads `unanswered`.

    **The mutation this kills:** no policy read as required — every unanswered
    week of every course held — and `awaiting` returned whenever no response
    exists. **The near miss:** the required twin above, one policy row apart.
    """
    world = hold
    student = world.a_student("encouraged", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    body = world.payload(student, course_week=HELD_WEEK)

    assert (
        body[STATE] == UNANSWERED
    ), f"An encouraged week with no response read {body[STATE]!r}; the ticket: `unanswered`."
    assert body[RESPONSE] is None, f"An unanswered week carries {body[RESPONSE]!r}."


# ---------------------------------------------------------------------------
# Done-when 2: a publish releases, read either side of the publish.
# ---------------------------------------------------------------------------


def test_a_publish_through_the_writer_releases_the_week_between_two_reads(
    hold: HoldWorld,
) -> None:
    """Read, publish through decision 6's writer, read again: `awaiting`, then `published`.

    Entry 51's pair: the read before carries no text and no name, and the read
    after carries the text, the instructor's name and the role.

    **The mutations this kill:** a writer that does not append (the second read
    still `awaiting`); a state cached from the first read; and a hold that
    releases on anything but a response row — the first read would already be
    released. **The near miss:** the first read, which must stay closed.
    """
    world = hold
    required(world)
    teacher = world.person(world.names.teacher)
    student = world.a_student("pair", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    before_answer = world.results(student, course_week=HELD_WEEK)
    before = world.payload(student, course_week=HELD_WEEK)
    world.publish(
        section_id=world.taught,
        course_week=HELD_WEEK,
        author=teacher.person_id,
        role=INSTRUCTOR,
        body=TEACHER_TEXT,
    )
    after = world.payload(student, course_week=HELD_WEEK)

    assert (
        before[STATE] == AWAITING and before[RESPONSE] is None
    ), f"Before the publish the week read {before!r}; it is required and has no response."
    assert TEACHER_TEXT not in response_surface(before_answer)
    assert after[STATE] == PUBLISHED, f"After the publish the week read {after[STATE]!r}."
    assert after[RESPONSE] is not None, "After the publish the week carries no response."
    assert after[RESPONSE][TEXT] == TEACHER_TEXT, f"The text read is {after[RESPONSE][TEXT]!r}."
    assert (
        after[RESPONSE][AUTHOR_NAME] == TEACHER_NAME
    ), f"The author read is {after[RESPONSE][AUTHOR_NAME]!r}; the teacher is {TEACHER_NAME!r}."
    assert after[RESPONSE][AUTHOR_ROLE] == INSTRUCTOR, f"The role read is {after[RESPONSE]!r}."


def test_one_instructor_row_reads_published_with_its_text_name_role_and_time(
    hold: HoldWorld,
) -> None:
    """One row, planted at a chosen instant: every member of the response is that row's.

    **The mutations this kill:** the name read from somewhere other than the row's
    author (the section's sibling teacher, or the course's lead, both of whom the
    staff-name channel could answer); the role hard-coded; the time taken from the
    reading clock rather than the row. **The near miss:** the payload's members
    exactly, held by `payload_of`.
    """
    world = hold
    required(world)
    teacher = world.person(world.names.teacher)
    published_at = report_opens(HELD_WEEK) + FIRST_ROW_AFTER_OPENING
    world.a_response(
        section_id=world.taught,
        course_week=HELD_WEEK,
        author=teacher.person_id,
        role=INSTRUCTOR,
        body=TEACHER_TEXT,
        published_at=published_at,
    )
    student = world.a_student("published", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    answered = world.results(student, course_week=HELD_WEEK)
    body = world.payload(student, course_week=HELD_WEEK)

    assert body[STATE] == PUBLISHED, f"A week with one instructor row read {body[STATE]!r}."
    response = body[RESPONSE]
    assert response[TEXT] == TEACHER_TEXT
    assert response[AUTHOR_NAME] == TEACHER_NAME, f"The author read is {response[AUTHOR_NAME]!r}."
    assert response[AUTHOR_ROLE] == INSTRUCTOR
    assert (
        instant(response[PUBLISHED_AT], "`published_at`") == published_at
    ), f"`published_at` is {response[PUBLISHED_AT]!r}; the row was published at {published_at}."
    # Since E9-08 the payload carries the course's Lead Faculty name in `lead_name`,
    # in every state (SPEC §2.1: course-level pages carry it in the header), so the
    # lead may be named there and only there. Everywhere else in the answer, the
    # published week names nobody beside its author.
    served = decoded(answered, "The published week's read")
    assert isinstance(served, dict), f"The published week's read decoded to {served!r}."
    beside_the_header = {key: value for key, value in served.items() if key != LEAD_NAME_MEMBER}
    headers = " ".join(f"{name}: {value}" for name, value in answered.headers.items())
    surface = f"{headers} {json.dumps(beside_the_header, ensure_ascii=False)}"
    others = [name for name in (LEAD_NAME, SIBLING_SECTION_TEACHER_NAME) if name in surface]
    assert not others, f"The published week names {others} beside its author."


def test_a_response_releases_an_encouraged_week_as_well(hold: HoldWorld) -> None:
    """No policy, one row: `published`, not `unanswered`.

    **The mutation this kills:** `published` reachable only from a required week
    (an encouraged week with a response read as `unanswered`). **The near miss:**
    `test_an_encouraged_week_with_no_response_reads_unanswered`, one row apart.
    """
    world = hold
    world.a_response(
        section_id=world.taught,
        course_week=HELD_WEEK,
        author=world.person(world.names.teacher).person_id,
        role=INSTRUCTOR,
        body=TEACHER_TEXT,
        published_at=report_opens(HELD_WEEK) + FIRST_ROW_AFTER_OPENING,
    )
    student = world.a_student("encouraged-published", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    body = world.payload(student, course_week=HELD_WEEK)

    assert body[STATE] == PUBLISHED, f"An encouraged week with a response read {body[STATE]!r}."
    assert body[RESPONSE][TEXT] == TEACHER_TEXT


@pytest.mark.parametrize(
    "other_week", [WEEK_BEFORE, WEEK_AFTER], ids=["the-week-before", "the-week-after"]
)
def test_a_response_to_another_week_of_the_section_does_not_release_this_one(
    hold: HoldWorld, other_week: int
) -> None:
    """The teacher answered course week 1 (or 3); course week 2 is required and still `awaiting`.

    **The mutation this kills:** the latest response looked up by section alone,
    without the week — the section's newest reply released every week of it.
    Both neighbours, because a lookup ordered by time and limited to one row
    finds whichever is newer.
    """
    world = hold
    required(world)
    world.a_response(
        section_id=world.taught,
        course_week=other_week,
        author=world.person(world.names.teacher).person_id,
        role=INSTRUCTOR,
        body=OTHER_WEEK_TEXT,
        published_at=report_opens(HELD_WEEK) + FIRST_ROW_AFTER_OPENING,
    )
    student = world.a_student("other-week", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    answered = world.results(student, course_week=HELD_WEEK)
    body = world.payload(student, course_week=HELD_WEEK)

    assert body[STATE] == AWAITING, (
        f"Course week {HELD_WEEK} read {body[STATE]!r} after a response to course week "
        f"{other_week}. A response releases its own section-week only."
    )
    assert OTHER_WEEK_TEXT not in response_surface(answered)


def test_a_response_to_the_sibling_section_does_not_release_this_one(hold: HoldWorld) -> None:
    """`Q1WW`'s teacher answered course week 2 of `Q1WW`; `F1WW`'s week 2 is still `awaiting`.

    **The mutation this kills:** the response looked up by course and week rather
    than section and week — the two sections share both.
    """
    world = hold
    required(world)
    world.a_response(
        section_id=world.sibling_section,
        course_week=HELD_WEEK,
        author=world.person(world.names.sibling_section_teacher).person_id,
        role=INSTRUCTOR,
        body=SIBLING_TEXT,
        published_at=report_opens(HELD_WEEK) + FIRST_ROW_AFTER_OPENING,
    )
    student = world.a_student("sibling-released", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    body = world.payload(student, course_week=HELD_WEEK)

    assert (
        body[STATE] == AWAITING
    ), f"`F1WW` read {body[STATE]!r} after `Q1WW`'s teacher answered the same course week."


# ---------------------------------------------------------------------------
# Done-when 3: on behalf is honest.
# ---------------------------------------------------------------------------


def test_a_first_response_by_the_lead_reads_on_behalf_under_the_leads_name_and_role(
    hold: HoldWorld,
) -> None:
    """The course's lead writes the week's first row as `LEAD_FACULTY`: `on-behalf`, the lead's name.

    The section has a teacher, whose name the staff-name channel also answers to
    this student; the payload must carry the lead's and never the teacher's.

    **The mutations this kill:** `on-behalf` never produced (every response read as
    `published`); the author name taken from the section's teaching instructor
    (the impersonation SPEC §5.3 forbids); the role shown as `INSTRUCTOR`.
    """
    world = hold
    required(world)
    lead = world.person(world.names.lead)
    world.a_response(
        section_id=world.taught,
        course_week=HELD_WEEK,
        author=lead.person_id,
        role=LEAD_FACULTY,
        body=LEAD_TEXT,
        published_at=report_opens(HELD_WEEK) + FIRST_ROW_AFTER_OPENING,
    )
    student = world.a_student("on-behalf", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    answered = world.results(student, course_week=HELD_WEEK)
    body = world.payload(student, course_week=HELD_WEEK)

    assert body[STATE] == ON_BEHALF, f"A first row written as LEAD_FACULTY read {body[STATE]!r}."
    assert body[RESPONSE][AUTHOR_NAME] == LEAD_NAME, (
        f"The on-behalf response is attributed to {body[RESPONSE][AUTHOR_NAME]!r}; the lead wrote "
        f"it ({LEAD_NAME!r})."
    )
    assert body[RESPONSE][AUTHOR_ROLE] == LEAD_FACULTY
    assert body[RESPONSE][TEXT] == LEAD_TEXT
    assert TEACHER_NAME not in response_surface(
        answered
    ), "The on-behalf payload names the section's instructor. Done-when 3: never the instructor's."


def test_a_first_response_by_the_chair_of_an_unled_course_reads_on_behalf_under_the_chair(
    hold: HoldWorld,
) -> None:
    """The chair writes as `CHAIR` for the unmapped course's section: `on-behalf`, the chair's name.

    **The mutations this kill:** `on-behalf` reached only from `LEAD_FACULTY`
    (the chair's response read as `published`); the name taken from the section's
    teacher (`UNMAPPED_TEACHER_NAME`); the role shown as anything but `CHAIR`.
    """
    world = hold
    chair = world.person(world.names.chair)
    world.windows_for(UNMAPPED_COHORT, WEEK_BEFORE, HELD_WEEK)
    world.a_response(
        section_id=world.unmapped_section,
        course_week=HELD_WEEK,
        author=chair.person_id,
        role=CHAIR,
        body=CHAIR_TEXT,
        published_at=report_opens(HELD_WEEK) + FIRST_ROW_AFTER_OPENING,
    )
    student = world.a_student("chair-on-behalf", world.unmapped_section)
    world.stand_after_the_opening(HELD_WEEK)

    answered = world.results(student, course_week=HELD_WEEK)
    body = world.payload(student, course_week=HELD_WEEK)

    assert body[STATE] == ON_BEHALF, f"A first row written as CHAIR read {body[STATE]!r}."
    assert body[RESPONSE][AUTHOR_NAME] == CHAIR_NAME
    assert body[RESPONSE][AUTHOR_ROLE] == CHAIR
    assert UNMAPPED_TEACHER_NAME not in response_surface(
        answered
    ), "The chair's on-behalf payload names the section's instructor."


@pytest.mark.parametrize(
    ("first_role", "second_role", "expected"),
    [(LEAD_FACULTY, INSTRUCTOR, ON_BEHALF), (INSTRUCTOR, LEAD_FACULTY, PUBLISHED)],
    ids=["lead-first", "instructor-first"],
)
def test_the_state_follows_the_first_rows_role_when_a_two_hat_author_switches(
    hold: HoldWorld, first_role: str, second_role: str, expected: str
) -> None:
    """The lead also teaches `F1WW`, writes the first row under one role and the edit under the other.

    Decision 3: "`on-behalf` iff the FIRST row's role is LEAD_FACULTY or CHAIR".
    Both rows are one author's (E7-01's one-author rule holds), each under a role
    the author holds for the section. The text read is the second row's.

    **The mutation this kills:** the state read off the latest row's role, which
    turns an on-behalf week into the instructor's own after an edit, or the
    reverse. Both orders, so neither "always on-behalf" nor "always published"
    survives. `author_role` is not asserted here: the work order does not say
    which row's role the payload shows across an edit.
    """
    world = hold
    lead = world.person(world.names.lead)
    world.review.graph.assign(INSTRUCTOR, scope=world.taught, person=lead.person_id)
    world.rows.commit()
    opens = report_opens(HELD_WEEK)
    for role, text, after in (
        (first_role, FIRST_TEXT, FIRST_ROW_AFTER_OPENING),
        (second_role, SECOND_TEXT, SECOND_ROW_AFTER_OPENING),
    ):
        world.a_response(
            section_id=world.taught,
            course_week=HELD_WEEK,
            author=lead.person_id,
            role=role,
            body=text,
            published_at=opens + after,
        )
    student = world.a_student("two-hat", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    body = world.payload(student, course_week=HELD_WEEK)

    assert body[STATE] == expected, (
        f"A first row as {first_role} and an edit as {second_role} read {body[STATE]!r}; decision "
        f"3 reads the first row's role, so {expected!r}."
    )
    assert body[RESPONSE][TEXT] == SECOND_TEXT, "The text read is not the latest row's."
