"""E2-14 item 1 — a second student's submit finds its own row and repeats nothing else.

The E2 boundary review's invariant-coverage audit
(`docs/tickets/e2/boundary-review.md`) found that `_existing_response`
(`backend/app/services/submissions.py`) is a second, independent copy of the
`(user_id, section_id, week_id)` key, and that **deleting
`Response.user_id == student_id` from it survives the whole isolated §4.1 pass**
— 188 passed, measured. The only thing that killed it was an outage-floor test
that happens to submit as a second student for reasons of its own
(`test_the_submit_path_follows_adr_0056s_taxonomy.py::test_a_provider_answering_503_floors_and_the_submission_is_stored`),
which is coverage by accident and is not in the isolated pass either.

So this module is what that mutation dies on, inside `pytest -m invariant`.

**Why this is a §4.1 module and not a storage module.** With the predicate gone,
a student submitting into a section-week a classmate has already answered takes
the *revise* branch on the classmate's row: the classmate's answers — their free
text, their ratings, their workload — are overwritten by a person who is not
them, and the response the route hands back is built from the classmate's row.
SPEC §4.1 item 6, "no view may ever widen a student's visibility relative to
these rules", and item 1's own scoping sentence, are both about exactly that: a
student-visible path answering with another person's data. The write half is a
confidentiality failure in the other direction — one student's words are lost
under another's — and the two arrive from one missing predicate.

**Three tests, one lookup, both of its directions.** A lookup keyed too widely
finds a classmate's row (the first two tests); a lookup that finds nothing at all
would pass both of them and break resubmission, so the third test stands on the
other side of the same line — the student's *own* second submission must still
find the one row they already own. Neither direction is evidence about the
predicate without the other (`docs/MISTAKES.md` entry 2: assert the forbidden
state *and* the near miss).

**The classmate's stored values are read and asserted present before the second
student submits.** A comparison against rows nobody has shown to exist is
satisfied by an empty table (`docs/MISTAKES.md` entry 3), and the message on each
of those assertions says which half it is guarding.

**The two submissions differ in every value they can.** If the second student
submitted the classmate's own numbers, a revise-in-place would rewrite the
classmate's answers to the same content and this module would go green over the
defect it exists for. So the second student's workload, ratings and comment are
different numbers and a different sentence, and the classmate's rows are compared
whole.

**The helpers come from `test_the_submit_path_answers_the_validity_matrix.py`
rather than being copied.** That module is the worked example for this world —
`a_student_in_an_open_window`, `accepted` and `marked` are its three — and it
sits in this same directory, so pytest has already put `tests/integration` on
`sys.path` before this module is imported (prepend import mode inserts a test
module's own basedir before importing it). A copy would be a second thing to keep
in step with E2-07's in-band mock selectors (`docs/MISTAKES.md` entry 13).
"""

from typing import Any

import pytest
from fixtures.submit import (
    COURSE_RATING_POSITION,
    RESPONSE_TABLE,
    USER_TABLE,
    WORKLOAD_POSITION,
    SubmitWorld,
    a_valid_submission,
)
from test_the_submit_path_answers_the_validity_matrix import (
    a_student_in_an_open_window,
    accepted,
    marked,
)

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# E2-08's work order settles both columns and settles that "`first_submitted_at`
# never changes"; they are spelled here because this module reads them by name
# and a rename should be one line rather than five. `user_id` is E2-05's own
# column, read the same way `test_the_submit_path_answers_the_validity_matrix.py`
# reads it.
FIRST_SUBMITTED_AT = "first_submitted_at"
LAST_SUBMITTED_AT = "last_submitted_at"
USER_COLUMN = "user_id"
WORKLOAD_COLUMN = "workload_hours"

# The two submissions' values, chosen to differ everywhere they can. A
# revise-in-place under the missing predicate rewrites the classmate's answer
# rows with these, so every one of them is a difference the whole-row comparison
# below can see.
CLASSMATES_WORKLOAD = 6.5
SECOND_STUDENTS_WORKLOAD = 2.0
CLASSMATES_INSTRUCTOR_RATING = 4
SECOND_STUDENTS_INSTRUCTOR_RATING = 3
CLASSMATES_COURSE_RATING = 5
SECOND_STUDENTS_COURSE_RATING = 3

# Two comments over SPEC §3.3's character floor that share no words, so a comment
# row rewritten by the other student's submission is visible as a different
# string rather than as a shorter one. The mock's `substantive` selector is added
# by `marked` at each call site.
CLASSMATES_COMMENT = "the pacing in week 3 was too fast and the reading load doubled"
SECOND_STUDENTS_COMMENT = "office hours on Tuesday cleared up most of my questions about lab four"


def a_submission(
    *, comment: str, instructor_rating: int, course_rating: int, workload: float
) -> dict[int, Any]:
    """One complete submission with every value the caller chose.

    `a_valid_submission` fixes the course rating and the workload, and this
    module's whole point is that the two students' stored values differ, so the
    two it does not take are set here rather than left at their defaults.
    """
    submission = a_valid_submission(comment=comment, instructor_rating=instructor_rating)
    submission[COURSE_RATING_POSITION] = course_rating
    submission[WORKLOAD_POSITION] = workload
    return submission


def response_of(world: SubmitWorld, student_row: Any) -> dict[str, Any]:
    """The one `response` row belonging to one student, or a failure naming the count."""
    key = world.key_of(USER_TABLE)
    mine = [row for row in world.responses() if row[USER_COLUMN] == student_row[key]]
    assert len(mine) == 1, (
        f"There are {len(mine)} `{RESPONSE_TABLE}` rows for the student {student_row[key]!r}: "
        f"{mine}. Every `{RESPONSE_TABLE}` row there is: {world.responses()}. SPEC §8 makes one "
        "response per (student, section, week), so zero means their submission was not stored — "
        "or was stored against somebody else — and more than one means the uniqueness rule is not "
        "holding."
    )
    return mine[0]


def renderings_of(value: Any) -> list[str]:
    """Every way one stored value plausibly reaches a JSON body, as strings to search for.

    A timestamp is the case this exists for: `str()` on a `datetime` puts a space
    where `isoformat()` puts a `T`, and a serializer may write either, or write
    the offset as `Z`. Searching for one spelling and reporting the body clean is
    the shape of a sweep that has gone blind (`docs/MISTAKES.md` entry 3), so all
    of them are searched.
    """
    found = {str(value)}
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        rendered = str(isoformat())
        found.add(rendered)
        found.add(rendered.replace("+00:00", "Z"))
    return sorted(part for part in found if part)


def test_a_second_students_submission_writes_its_own_row_and_leaves_the_classmates_untouched(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> None:
    """Two students in one section-week are two responses, and the first one does not move.

    **The mutation this kills:** `Response.user_id == student_id` deleted from
    `_existing_response` (`backend/app/services/submissions.py`). With it gone the
    lookup is keyed on `(section_id, week_id)` alone, the second student's submit
    takes the revise branch on the classmate's row, and the classmate's stored
    answers become the second student's — measured by the E2 boundary review as
    surviving the entire isolated §4.1 pass.

    Four things are asserted and each fails differently under that mutation. There
    are two `response` rows rather than one; they are two different rows, keyed
    differently, one per student; the classmate's row is byte-for-byte the row
    that was read before the second submission, `last_submitted_at` included; and
    the classmate's `answer` rows are the ones they submitted, compared whole
    rather than counted. A count alone would pass against a revision that replaced
    five values with five other values.

    **The classmate's rows are asserted present first.** "Their answers are
    unchanged" is true of a student who has no answers, and this world seeds no
    `response` or `answer` row at all — every one of them is written by the path
    under test — so the read-back before the second submission is the guard that
    the comparison after it is about something.
    """
    classmate = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = classmate.world
    second_student_row = world.another_student()
    second = signed_in_student(classmate.client, world, second_student_row)

    accepted(
        classmate.submit(
            a_submission(
                comment=f"{marked(mock_ai, 'substantive')} {CLASSMATES_COMMENT}",
                instructor_rating=CLASSMATES_INSTRUCTOR_RATING,
                course_rating=CLASSMATES_COURSE_RATING,
                workload=CLASSMATES_WORKLOAD,
            )
        ),
        "The classmate's own submission",
    )

    before = response_of(world, world.student)
    classmates_answers = world.answers_of(before)
    assert classmates_answers, (
        f"The classmate's response {before} holds no `answer` rows, so the comparison below is "
        "between two empty lists and would hold however the second student's submission had "
        "rewritten them (`docs/MISTAKES.md` entry 3)."
    )
    assert len(world.responses()) == 1, (
        f"Before the second student submitted there were {len(world.responses())} responses: "
        f"{world.responses()}. The count assertion below counts up from one."
    )

    answered = second.submit(
        a_submission(
            comment=f"{marked(mock_ai, 'substantive')} {SECOND_STUDENTS_COMMENT}",
            instructor_rating=SECOND_STUDENTS_INSTRUCTOR_RATING,
            course_rating=SECOND_STUDENTS_COURSE_RATING,
            workload=SECOND_STUDENTS_WORKLOAD,
        )
    )

    accepted(answered, "A second student's submission into the same section and week")
    stored = world.responses()
    assert len(stored) == 2, (
        f"Two students submitted into one section-week and there are {len(stored)} "
        f"`{RESPONSE_TABLE}` rows: {stored}. One row means the second submission was written over "
        "the first — the classmate's week replaced by somebody else's, with the classmate's own "
        "next resubmission the only thing that could ever discover it."
    )

    key = world.key_of(RESPONSE_TABLE)
    after = response_of(world, world.student)
    mine = response_of(world, second_student_row)
    assert mine[key] != after[key], (
        f"Both students' submissions resolve to the `{RESPONSE_TABLE}` row {after[key]!r}. Two "
        "students in one section-week hold two responses; one row read back for both is the "
        "lookup finding a classmate's row and revising it."
    )
    assert after == before, (
        f"The classmate's `{RESPONSE_TABLE}` row changed when a second student submitted: "
        f"{before} became {after}. `_existing_response` keys the lookup on `(user_id, section_id, "
        "week_id)`; without the `user_id` predicate the second student's submit revises this row "
        f"in place, which moves `{LAST_SUBMITTED_AT}` and can move `{FIRST_SUBMITTED_AT}` under a "
        "person who has not submitted since."
    )
    assert world.answers_of(after) == classmates_answers, (
        f"The classmate's `answer` rows changed when a second student submitted: "
        f"{classmates_answers} became {world.answers_of(after)}. Their free text is what SPEC §5.1 "
        "shows the instructor and what §4 keys to the classmate's LMS user id, so a rewrite here "
        "puts one student's words under another student's name and loses the first student's week."
    )


def test_the_second_students_answer_repeats_nothing_that_identifies_the_classmates_response(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> None:
    """What the route hands back names the second student's row and nothing of the classmate's.

    The ticket's subject, second half: the response "returns neither the
    classmate's `response_id` nor their `first_submitted_at`". Under the same
    mutation the route answers from the classmate's row, so whatever it serves
    about a response — its id, when it was first submitted, the text it holds — is
    somebody else's, handed to a student on their own screen. SPEC §4.1 item 6: no
    view may widen a student's visibility.

    **The three needles are the classmate's response id, their
    `first_submitted_at` in every spelling a serializer plausibly writes, and
    their comment text.** The last is there because it is unambiguously the
    classmate's *content* rather than a key, and because it is what a body
    carrying a whole revised response would trip on.

    **The identifier assertion is written as "the ids this body carries are not
    the classmate's" rather than as a bare absence**, and it prints the second
    student's own id beside it, so a failure says which row was served rather than
    only that a string was found.

    **The disclosed limit, said plainly:** if E2-08's submit path answers with an
    empty body, every assertion here is vacuously true and only the test above is
    load-bearing. There is no needle to find in a body that carries nothing, so
    that is written down rather than papered over with a non-empty-body guard,
    which would go red on a legitimate contract. Each failure message prints the
    body, so the next reader can see which case they are in.
    """
    classmate = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = classmate.world
    second_student_row = world.another_student()
    second = signed_in_student(classmate.client, world, second_student_row)

    accepted(
        classmate.submit(
            a_submission(
                comment=f"{marked(mock_ai, 'substantive')} {CLASSMATES_COMMENT}",
                instructor_rating=CLASSMATES_INSTRUCTOR_RATING,
                course_rating=CLASSMATES_COURSE_RATING,
                workload=CLASSMATES_WORKLOAD,
            )
        ),
        "The classmate's own submission",
    )
    theirs = response_of(world, world.student)
    key = world.key_of(RESPONSE_TABLE)
    assert theirs[FIRST_SUBMITTED_AT] is not None, (
        f"The classmate's response {theirs} carries no `{FIRST_SUBMITTED_AT}`, so one of the two "
        "values this test scans a body for does not exist and its absence would say nothing."
    )

    answered = second.submit(
        a_submission(
            comment=f"{marked(mock_ai, 'substantive')} {SECOND_STUDENTS_COMMENT}",
            instructor_rating=SECOND_STUDENTS_INSTRUCTOR_RATING,
            course_rating=SECOND_STUDENTS_COURSE_RATING,
            workload=SECOND_STUDENTS_WORKLOAD,
        )
    )

    accepted(answered, "A second student's submission into the same section and week")
    body = answered.text
    mine = response_of(world, second_student_row)
    named = sorted(str(row[key]) for row in world.responses() if str(row[key]) in body)

    assert str(theirs[key]) not in named, (
        f"The response served to the second student carries the classmate's `{RESPONSE_TABLE}` id "
        f"{theirs[key]!r}; the ids it carries are {named}. The second student's own row is "
        f"{mine[key]!r}. Body: {body[:400]!r}. A route answering from the classmate's row hands a "
        "student an identifier for a response that is not theirs, which is the first thing any "
        "later surface would resolve."
    )

    stamped = [
        rendering for rendering in renderings_of(theirs[FIRST_SUBMITTED_AT]) if rendering in body
    ]
    assert not stamped, (
        f"The response served to the second student carries the classmate's "
        f"`{FIRST_SUBMITTED_AT}` as {stamped}. Body: {body[:400]!r}. That is the moment another "
        "person first answered this week — a fact about a classmate, on a student's own screen."
    )
    assert CLASSMATES_COMMENT not in body, (
        f"The response served to the second student carries the classmate's comment text. Body: "
        f"{body[:400]!r}. SPEC §4 keys a response to the LMS user id and never shows one student's "
        "words to another; this would be that, on the submit path itself."
    )


def test_a_students_own_resubmission_still_revises_the_one_row_they_already_own(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
) -> None:
    """The other direction of the same lookup: it must still find the student's own row.

    Without this, both tests above are passed by a lookup that finds *nothing* —
    `_existing_response` returning `None` unconditionally, or keyed so narrowly
    that no row ever matches. Every submission would then insert, a student's
    second one would meet E2-05's uniqueness constraint as a 5xx or write a
    duplicate week, and the two tests above would go on reporting that a
    classmate's row was untouched. `docs/MISTAKES.md` entry 2 asks for the
    forbidden state and the near miss; this is the near miss, and it sits in the
    isolated pass beside them deliberately, because a pass that only ever proves
    refusals cannot tell a working lookup from a broken one.

    **The mutation this kills:** the lookup dropped, or narrowed so that a
    student's own row is not found. The resubmission rule itself is E2-08's and is
    asserted in full in `test_the_submit_path_answers_the_validity_matrix.py::
    test_a_resubmission_inside_the_window_replaces_the_prior_answers`; what is
    here is the half that gives the two assertions above their meaning.

    **A classmate submits first**, so the row this student's resubmission has to
    find is not the only row in the table — a lookup that ignores `user_id` and
    happens to be handed a one-row table would pass a test written without them.
    """
    student = a_student_in_an_open_window(
        open_submit_tool, submit_world, signed_in_student, mock_ai_endpoint, open_now
    )
    world = student.world
    other = signed_in_student(student.client, world, world.another_student())

    accepted(
        other.submit(
            a_submission(
                comment=f"{marked(mock_ai, 'substantive')} {SECOND_STUDENTS_COMMENT}",
                instructor_rating=SECOND_STUDENTS_INSTRUCTOR_RATING,
                course_rating=SECOND_STUDENTS_COURSE_RATING,
                workload=SECOND_STUDENTS_WORKLOAD,
            )
        ),
        "A classmate's submission, made before this student's",
    )
    accepted(
        student.submit(
            a_submission(
                comment=f"{marked(mock_ai, 'substantive')} {CLASSMATES_COMMENT}",
                instructor_rating=CLASSMATES_INSTRUCTOR_RATING,
                course_rating=CLASSMATES_COURSE_RATING,
                workload=CLASSMATES_WORKLOAD,
            )
        ),
        "This student's first submission",
    )
    first = response_of(world, world.student)
    key = world.key_of(RESPONSE_TABLE)

    accepted(
        student.submit(
            a_submission(
                comment=f"{marked(mock_ai, 'substantive')} {CLASSMATES_COMMENT}",
                instructor_rating=CLASSMATES_INSTRUCTOR_RATING,
                course_rating=CLASSMATES_COURSE_RATING,
                workload=CLASSMATES_WORKLOAD + 4,
            )
        ),
        "This student's resubmission inside the same open window",
    )

    revised = response_of(world, world.student)
    assert revised[key] == first[key], (
        f"This student's resubmission produced the row {revised[key]!r} where their first "
        f"submission produced {first[key]!r}. The lookup did not find the row they already own, so "
        "every 'the classmate's row was untouched' assertion in this module would be satisfied by "
        "a lookup that finds nothing at all."
    )
    assert len(world.responses()) == 2, (
        f"After two students and one resubmission there are {len(world.responses())} responses: "
        f"{world.responses()}. Two students in one section-week are two rows, and a resubmission "
        "adds none."
    )
    workloads = [
        row[WORKLOAD_COLUMN]
        for row in world.answers_of(revised)
        if row[WORKLOAD_COLUMN] is not None
    ]
    assert len(workloads) == 1 and float(workloads[0]) == CLASSMATES_WORKLOAD + 4, (
        f"The stored workload answers after the resubmission are {workloads}; the resubmission "
        f"said {CLASSMATES_WORKLOAD + 4}. The lookup found a row and then wrote somewhere else."
    )
