"""Who a participation score belongs to — E3-08's boundary round, ruling R7.

> The sweep delivers scores only for members holding a student-shaped role in that
> section. The two-hat rule holds: a person who is instructor elsewhere and
> student here is scored here.

**SPEC §3.4 makes the score a student's.** It is "completed items ÷ total items
across the student's elapsed weeks", posted into that student's gradebook column
with a per-week ledger of what they answered. There is no reading of that section
under which a section's teacher has a participation percentage, and the ledger a
teacher would receive is a list of the weeks they did not fill in their own
survey.

**What the boundary round found.** The sweep chose who to deliver for by
enrollment dates alone — a member is delivered for while `started_on <=
clock.today AND (ended_on IS NULL OR ended_on >= clock.today)` — and an
instructor's enrollment row satisfies that exactly as a student's does. E1-11's
roster sync writes an `enrollment` row for **every** member of a membership
container, instructors included (that is how a section's teaching staff is known
at all), so the running stack posts a participation score, ordinarily `0.0` with a
full ledger, into the instructor's own column of the gradebook they are grading.

**Dates are the wrong instrument and that is the whole subject here.** Both
members in the first test below hold enrollments that differ in nothing a date
can see — same `started_on`, both `ended_on` NULL — and both answered every item
of every elapsed week, so `participation_scores` computes the same score for each.
The only difference between them is the pair of rows that says one of them teaches
the section: ADR 0024's `person`-to-`user` link, and E0-09's `INSTRUCTOR`
`role_assignment` scoped to that section at §2.1's grain. A sweep that cannot see
those rows cannot tell these two members apart, and that is exactly the state the
ruling corrects.

**The two-hat control is the other half, and it is why the first test is not a
licence to exclude anybody with a role.** A person is scored where they are the
student, whatever they are elsewhere: the seeded dean holds a learner-shaped
membership in one section and leadership over others, and that membership keeps
its score. So the second test poses one person who teaches section B and takes
section A, and requires the score in section A. It is green today and has to stay
green, which makes it the control on every over-broad reading of the first test —
"anybody who holds an instructor assignment", "anybody who has a `person` row",
"anybody who appears in the people graph".

**Which failure a red here is.** The sweep exists, so neither test can fail on a
missing symbol. The first is expected red on its assertion that `grade_sync` holds
no row for the instructor-shaped member — today it holds one, and the platform
holds a score body beside it. The second is expected green before and after. Every
premise below is a plain call in the test body, never a fixture, so a world that
could not be built says so as a FAILED naming the row it wanted
(`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebooks`, `grade_sync_rows` and `sweep_contract` come from
# `tests/fixtures/grade_sweep.py`; `window_settings` from
# `tests/fixtures/survey_windows.py`; `committed_clock_overrides` from
# `tests/fixtures/clock.py`.

# How many course weeks have elapsed when the sweep runs. One: the smallest world
# in which anybody in the section has a score to post at all, and therefore the
# smallest one in which "this member was not posted for" is a claim about them
# rather than about a section with nothing to say.
ELAPSED_WEEKS = 1

# The subject the two-hat person carries. **This module's own rather than one of
# the section's launch subjects**, for the reason
# `test_a_sections_record_is_durable_before_the_next_section_starts.py` gives: the
# two sections in that test are two launch contexts of one registered platform,
# `user` is unique on `(lti_platform_id, lms_user_id)`, and a student built from a
# second context's subjects can be a row that already exists. Here it costs
# nothing — the mock platform records a score against whatever `userId` it is
# sent, and what is read back is this subject.
A_PERSON_WHO_TEACHES_ELSEWHERE = "e3-08-two-hat-member"


def outcome_of(row: dict[str, Any], sweep_contract: Any) -> str:
    """One `grade_sync` row's outcome as text, whatever the enum spells it."""
    value = row[sweep_contract.outcome_column]
    return str(getattr(value, "value", value))


def bodies_for(book: Any, subject: str, sweep_contract: Any) -> list[dict[str, Any]]:
    """Every score body the platform recorded for one subject against this section.

    A copy of the helper in `test_a_dropped_students_score_stops_updating.py`
    rather than an import of it, for the reason `logged_by` in
    `test_a_sections_record_is_durable_before_the_next_section_starts.py` gives: a
    test module that imports a sibling test module depends on where pytest put
    `tests/` on `sys.path`, and an import error is not a red.
    """
    return [
        sweep_contract.body(entry)
        for entry in book.posted()
        if str(entry.get(sweep_contract.user_member)) == subject
    ]


def one_enrollment(world: Any, member: Any, described: str) -> dict[str, Any]:
    """The single `enrollment` row this member holds in this section, or a failure.

    Read out of the database, because every premise this module states about the
    sweep's delivery selection has to be about stored rows: the selection reads
    the table, not the fixture's memory of what it wrote.
    """
    rows = world.enrollments_of(member)
    assert len(rows) == 1, (
        f"The {described} holds {len(rows)} enrollment rows in this section: {rows}. This module "
        "poses two members whose enrollments differ in nothing a date can see, so a member with "
        "no row is not in the section at all and a member with two has a history the comparison "
        "below was never set up to make."
    )
    return rows[0]


def test_a_member_whose_only_role_in_the_section_is_instructor_is_not_scored_there(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """R7's first half: a section's teacher gets no participation score in it.

    Two members of one section, enrolled on the same day with neither enrollment
    ended, each answering every item of every elapsed week. One of them also
    teaches the section — a `person` row linked to their `user` (ADR 0024) and an
    `INSTRUCTOR` `role_assignment` scoped to this section at SPEC §2.1's grain
    (E0-09). Nothing else about them differs, and `participation_scores` answers
    the same score for both, which the premise below requires before anything is
    read back.

    **The mutation this kills — and it is the state the sweep is in today.** The
    role predicate removed from the delivery selection, leaving `_live_enrollments`
    choosing on `started_on` and `ended_on` alone. Under it both members are
    delivered for, and the section's instructor gets a participation percentage
    written into the gradebook column they themselves grade: ordinarily `0.0` with
    a full ledger of the weeks they did not answer their own survey. Every other
    test in these modules is blind to it, because every member they seed is a
    student and no ticket before this one gave the sweep a reason to look at
    `role_assignment` at all.

    **Both directions in one run, which is what makes either mean anything.** The
    refusing half alone is satisfied by a sweep that delivers for nobody — a bound
    that skipped the section, a line item that was never created, a clock in the
    wrong place — so the student's own delivery is asserted in the same sweep, off
    the platform's record as well as out of `grade_sync`. The accepting half alone
    is satisfied by the sweep as it stands.

    **The absence is asserted twice and neither reading is redundant.** No
    `grade_sync` row says Pulse has no record of posting for the instructor; no
    body in the platform's own log says nothing reached the gradebook. A sweep that
    posted and failed to record satisfies the first while writing into a teacher's
    column, and a sweep that recorded and posted nothing satisfies the second while
    claiming a delivery that never happened.
    """
    book = gradebooks()
    teaching, learning = sweep_contract.students(book, 2)
    for member in (teaching, learning):
        sweep_contract.answered_fully(book.world, member, through=ELAPSED_WEEKS)
    who = book.world.person_for(teaching)
    book.world.teaches(who, book.id)
    book.world.rows.commit()
    book.world.elapsed_through(committed_clock_overrides, ELAPSED_WEEKS)

    teacher_row = one_enrollment(book.world, teaching, "member who teaches this section")
    student_row = one_enrollment(book.world, learning, "member who only takes it")
    assert (
        teacher_row[sweep_contract.ended_on_column] is None
        and student_row[sweep_contract.ended_on_column] is None
        and teacher_row[sweep_contract.started_on_column]
        == student_row[sweep_contract.started_on_column]
    ), (
        f"The two enrollments are {teacher_row} and {student_row}. This test's whole instrument is "
        "that they are indistinguishable by date — same `started_on`, neither ended — so that the "
        "instructor assignment is the only thing that can produce two different answers. Where "
        "they differ here, the silence asserted below could be an ordinary drop or a future add "
        "and would say nothing about R7 (`docs/MISTAKES.md` entry 3)."
    )
    assert book.world.persons_linked_to(teaching) == [who], (
        f"`person` rows naming this member's `user` are {book.world.persons_linked_to(teaching)} "
        f"and this test linked {who}. ADR 0024 puts the link on `person`, nullable and unique, and "
        "it is the only path from the member a score would be posted for to the assignment that "
        "says they teach here. Without it the member holds no role in this section at all and this "
        "test is two students."
    )
    assert book.world.instructors_of(book.id) == [who], (
        "The `INSTRUCTOR` assignments scoped to this section name "
        f"{book.world.instructors_of(book.id)} and this test wrote one for {who}. SPEC §2.1 puts an "
        "instructor at section grain (E0-09's `ROLE_SCOPE_GRAIN`, the same grain "
        "`test_the_roster_definers_answer_a_point_query_and_nothing_more.py` pins its own "
        "instructor rows to). With no row here nobody teaches this section and the refusal below "
        "would be about nothing."
    )
    teacher_score = sweep_contract.computed(book.world, teaching, settings=window_settings)
    student_score = sweep_contract.computed(book.world, learning, settings=window_settings)
    assert teacher_score == student_score, (
        f"The formula answers {teacher_score!r} for the member who teaches and {student_score!r} "
        "for the member who only takes the section. They are seeded identically and answered "
        "identically, so the two scores have to be one score. Where they are not, the silence "
        "below belongs to `participation_scores` rather than to the sweep's delivery selection, "
        "and a mutation to that selection would leave this test green."
    )
    book.wire.calls.clear()

    answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r}."
    delivered = grade_sync_rows.for_pair(book.id, learning.user_id)
    assert (
        len(delivered) == 1
        and outcome_of(delivered[0], sweep_contract) == grade_sync_rows.outcomes()["posted"]
    ), (
        f"The member who only takes this section has {delivered}. This is the positive control and "
        "it comes first: without a delivery somebody in this section demonstrably received, "
        '"the instructor was not delivered for" is satisfied by a sweep that did nothing at all '
        "— a term outside the grace bound, a line item never created, a clock that never moved."
    )
    assert bodies_for(book, learning.subject, sweep_contract), (
        "The platform recorded no score for the member who only takes this section, though "
        "`grade_sync` says one was posted. The control has to be a delivery the gradebook can "
        "confirm, or the absence asserted below is measured against Pulse's own bookkeeping "
        "rather than against what reached the platform."
    )
    taught = grade_sync_rows.for_pair(book.id, teaching.user_id)
    assert not taught, (
        f"`grade_sync` holds {taught} for the member who teaches this section. R7: the sweep "
        "delivers only for members holding a student-shaped role in the section, and SPEC §3.4 "
        "makes the score a student's — 'completed items ÷ total items across the student's elapsed "
        "weeks'. A row here is Pulse recording a participation grade for the person doing the "
        "grading, computed from the weeks they did not fill in their own survey."
    )
    assert not bodies_for(book, teaching.subject, sweep_contract), (
        f"The platform recorded {bodies_for(book, teaching.subject, sweep_contract)} for the "
        "member who teaches this section. The absent row above is only half the claim: a sweep "
        "that posted and failed to record would satisfy it while writing a percentage into the "
        "instructor's own column of the gradebook they grade."
    )
    assert answered == {
        sweep_contract.posted_key: 1,
        sweep_contract.failed_key: 0,
    }, (
        f"The sweep answered {answered!r} where one of two members of the section is a student. "
        "Two posted is the instructor being scored; the per-member assertions above say which."
    )


def test_a_person_who_teaches_one_section_is_still_scored_as_a_student_in_another(
    gradebooks: Any,
    grade_sync_rows: Any,
    sweep_contract: Any,
    window_settings: Any,
    committed_clock_overrides: Any,
) -> None:
    """R7's two-hat rule: the hat is per section, never per person.

    One person, two sections of one institution. They hold an `INSTRUCTOR`
    assignment scoped to the second and a live enrollment — with answers — in the
    first, and nothing at all in the second. SPEC §2.1's whole design is that
    authority is held at a node rather than by an individual, and staff take
    courses: the seeded dean's learner-shaped membership is the case this is drawn
    from, and it has to keep its score.

    **The mutations this kills, and both are readings of R7's first half that pass
    every assertion in the test above.**

      - *The predicate widened from "holds an instructor's assignment in **this**
        section" to "holds one anywhere."* Under it every member of teaching staff
        who is also taking a course silently stops receiving a participation grade,
        in a section they are an ordinary student of.
      - *The predicate written as "has no `person` row."* Absence from the people
        graph is not the same claim as being a student here, and it withdraws the
        score of everybody Pulse has ever entered — every dean, chair, lead and
        Care officer taking a course, and anybody a roster sync happened to link.

    **Green before this ruling and green after**, which is what makes it a control
    rather than a second criterion: the sweep as it stands delivers for this person
    because their enrollment is live, and the sweep as R7 leaves it delivers for
    them because they are the student here. A red here after the fix is the fix
    reaching past the section it was scoped to.

    **The premises say where each hat is**, in both directions and before the
    sweep runs. An assignment that landed on the wrong section, or on no section,
    would make this an ordinary one-student sweep wearing this test's name.
    """
    book = gradebooks()
    elsewhere = gradebooks.beside(book)
    student = book.world.student(A_PERSON_WHO_TEACHES_ELSEWHERE)
    sweep_contract.answered_fully(book.world, student, through=ELAPSED_WEEKS)
    who = book.world.person_for(student)
    book.world.teaches(who, elsewhere.id)
    book.world.rows.commit()
    book.world.elapsed_through(committed_clock_overrides, ELAPSED_WEEKS)

    assert book.id != elsewhere.id, (
        f"Both halves of this person's two hats are on section {book.id}. The rule under test is "
        "that the hat is per section, and with one section there are no two sections to tell "
        "apart."
    )
    assert book.world.instructors_of(elsewhere.id) == [who], (
        "The `INSTRUCTOR` assignments scoped to the other section name "
        f"{book.world.instructors_of(elsewhere.id)} and this test wrote one for {who}. Without it "
        "this person wears one hat, and a sweep that scored them here would prove nothing about "
        "the two-hat rule."
    )
    assert book.world.instructors_of(book.id) == [], (
        "The section under test has `INSTRUCTOR` assignments naming "
        f"{book.world.instructors_of(book.id)}. This person must hold no teaching role *here*, or "
        "the delivery asserted below is the case the first test in this module refuses rather than "
        "the case this one requires."
    )
    enrolled = one_enrollment(book.world, student, "person who teaches the other section")
    assert enrolled[sweep_contract.ended_on_column] is None, (
        f"This person's enrollment in the section under test is {enrolled}, and its `ended_on` is "
        "set. SPEC §3.4 stops updating a dropped student's score, so a delivery here would be "
        "refused for that reason and this test would report the two-hat rule holding while "
        "measuring a drop."
    )
    book.wire.calls.clear()

    answered, raised = sweep_contract.run(
        book.session, settings=window_settings, http=book.wire.session()
    )

    assert raised is None, f"The sweep raised {raised!r}."
    rows = grade_sync_rows.for_pair(book.id, student.user_id)
    assert (
        len(rows) == 1
        and outcome_of(rows[0], sweep_contract) == grade_sync_rows.outcomes()["posted"]
    ), (
        f"`grade_sync` holds {rows} for a person who teaches another section and is an ordinary "
        "student of this one. R7: 'a person who is instructor elsewhere and student here is scored "
        "here.' SPEC §2.1 attaches authority to a node rather than to an individual, and staff "
        "take courses — the seeded dean's learner-shaped membership is this case. Silence here is "
        "a role test that has escaped the section it was scoped to."
    )
    assert bodies_for(book, student.subject, sweep_contract), (
        f"The platform recorded {bodies_for(book, student.subject, sweep_contract)} for this "
        "person against the section they are a student of. The row above says Pulse believes it "
        "posted; this says the gradebook column they are entitled to actually has the value in it."
    )
    assert answered == {
        sweep_contract.posted_key: 1,
        sweep_contract.failed_key: 0,
    }, (
        f"The sweep answered {answered!r}. One of the two sections has one student in it and the "
        "other has none, so one post is the whole of this run."
    )
