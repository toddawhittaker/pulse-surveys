"""The results route answers only the student's own section — E7-02, done-when 6.

> **Only the student's own section.** The route refuses a section the student is
> not enrolled in, an ended enrollment, and a week whose report has not opened,
> each with one refusal that names nothing of the section, its instructor or its
> response. Each refusal sits beside a passing twin in one world. These tests are
> marked `invariant`.

Work order decision 5: every refused case — not enrolled, ended enrollment,
unopened week, nonexistent week or section — is one 404 carrying one fixed
sentence from `app/copy/response_loop.py`, byte-identical across all of them.

**Denial, not absence** (SPEC §4.1, the test author's rule). Each refusal is
asserted *refused*: the 404, the one sentence, and then that nothing of the
section rides in it. And each sits beside a twin in the same world that is
answered: the refused section's own student reads it, the refused student's
classmate reads the same section-week, the week before the unopened one reads.
Without the twin a refusal could be a route that answers nobody.

**What a refusal must not name**, planted so that it has something to name: the
section's identifier (both spellings) and its code, its teaching instructor's
name, and a published response's text and author for that very section-week.

**The unopened week has a response planted in it**, written before its report
opens — the writer does not refuse that (decision 6), so a gate that read the
response before checking the week has something to leak.

**Every test asserts in its own body** (`scripts/ci/check_invariant_assertions.py`)
and the marker sits at module level: this module's name carries `names_nothing`,
a denial shape `tests/unit/test_every_confidentiality_denial_module_sits_inside_
the_invariant_pass.py` requires to be marked there.

**Which failure a red is, before E7-02 lands.** Every test fails naming the
missing route (`results_route`).
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.lead_review import UNMAPPED_COHORT
from fixtures.report_api import TAUGHT_COHORT, UNTAUGHT_COHORT
from fixtures.routing import paths_of, student_visible_routes
from fixtures.staff_names import SIBLING_SECTION_TEACHER_NAME, TEACHER_NAME
from fixtures.student_read import REFUSED_STATUS as NOT_A_STUDENT_STATUS
from fixtures.student_read import response_surface
from fixtures.the_hold import (
    FIRST_ROW_AFTER_OPENING,
    HELD_WEEK,
    INSTRUCTOR,
    REFUSED_STATUS,
    STATE,
    WEEK_BEFORE,
    HoldWorld,
    latest_results_route,
    report_opens,
    response_loop_copy,
    results_route,
    results_url,
    sentences_served,
    spellings_of,
)

pytestmark = [pytest.mark.invariant, pytest.mark.integration]

OWN_TEXT = "E7-02 F1WW's reply for course week two, which only its students read"
SIBLING_TEXT = "E7-02 Q1WW's reply for course week two, which only its students read"
EARLY_TEXT = "E7-02 a reply written before the week's report opened"

# One past the taught section's six weeks.
A_WEEK_THE_SECTION_DOES_NOT_HAVE = 7


def plant_the_replies(world: HoldWorld) -> None:
    """Each sibling section's teacher answers course week 2 of their own section."""
    opens = report_opens(HELD_WEEK)
    world.a_response(
        section_id=world.taught,
        course_week=HELD_WEEK,
        author=world.person(world.names.teacher).person_id,
        role=INSTRUCTOR,
        body=OWN_TEXT,
        published_at=opens + FIRST_ROW_AFTER_OPENING,
    )
    world.a_response(
        section_id=world.sibling_section,
        course_week=HELD_WEEK,
        author=world.person(world.names.sibling_section_teacher).person_id,
        role=INSTRUCTOR,
        body=SIBLING_TEXT,
        published_at=opens + FIRST_ROW_AFTER_OPENING,
    )


def named_in(answered: Any, needles: set[str]) -> list[str]:
    surface = response_surface(answered)
    return sorted(needle for needle in needles if needle in surface)


def test_the_results_route_is_a_student_route(
    hold: HoldWorld, require_student_dependency: Any
) -> None:
    """The route's dependency graph holds `require_student`, so every student-route sweep reaches it.

    `docs/MISTAKES.md` entry 53, one level out: the §4.1 item 1 sweeps derive
    their inventory from `require_student`, so a results route that checked the
    student some other way would sit outside every one of them and be swept by
    none. **The mutation this kills:** the route written with its own session
    read instead of the shared dependency.
    """
    template = results_route(hold.door.application)
    latest = latest_results_route(hold.door.application)
    found = paths_of(student_visible_routes(hold.door.application, require_student_dependency))

    assert template in found, (
        f"The results route {template!r} is not among the routes whose dependency graph holds "
        f"`require_student` ({sorted(found)}). The ticket: the route sits behind `require_student`."
    )
    assert latest in found, (
        f"The no-week results route {latest!r} (the amendment's A2) is not among the routes whose "
        f"dependency graph holds `require_student` ({sorted(found)})."
    )


def test_a_section_the_student_is_not_enrolled_in_is_refused_beside_its_own_students_read(
    hold: HoldWorld,
) -> None:
    """A student of `F1WW` asks for `Q1WW`'s course week 2: 404. A student of `Q1WW` reads it.

    Both sections are the same course's, with windows over the same weeks and a
    published reply each; the refused request names a section that exists and has
    something to show.

    **The mutation this kills:** the route reading the section without the
    student's enrollment — or through any enrollment in the course — which serves
    `Q1WW`'s reply and its teacher's name to a student of `F1WW` (SPEC §4.1 item
    1: other sections). **The near miss:** `Q1WW`'s own student, answered.
    """
    world = hold
    world.windows_for(UNTAUGHT_COHORT, WEEK_BEFORE, HELD_WEEK)
    plant_the_replies(world)
    ours = world.a_student("not-enrolled", world.taught)
    theirs = world.a_student("sibling-own", world.sibling_section)
    world.stand_after_the_opening(HELD_WEEK)

    twin = world.results(theirs, course_week=HELD_WEEK)
    refused = world.results(ours, course_week=HELD_WEEK, section_id=world.sibling_section)

    assert twin.status_code == 200 and SIBLING_TEXT in twin.text, (
        f"`Q1WW`'s own student was answered {twin.status_code} {twin.text[:300]!r}; the twin must "
        "read the reply, or the refusal beside it could be a route that answers nobody."
    )
    assert refused.status_code == REFUSED_STATUS, (
        f"A student of `F1WW` asking for `Q1WW` was answered {refused.status_code} "
        f"{refused.text[:300]!r}. Done-when 6: refused, 404 (decision 5)."
    )
    assert len(sentences_served(refused)) == 1, (
        f"The refusal carries {sentences_served(refused)} of `app.copy.response_loop`'s sentences; "
        "decision 5: exactly one."
    )
    leaked = named_in(
        refused,
        spellings_of(world.sibling_section)
        | {world.code_of(UNTAUGHT_COHORT), SIBLING_SECTION_TEACHER_NAME, SIBLING_TEXT},
    )
    assert not leaked, f"The refusal names {leaked} — the section, its instructor or its reply."


def test_an_ended_enrollment_is_refused_beside_a_live_classmates_read(hold: HoldWorld) -> None:
    """A student whose enrollment in `F1WW` ended asks for its course week 2: 404. A classmate reads it.

    The ended enrollment ends before any week this world reads opened its window,
    so it is not live today under either clock and was not live in the week asked
    about.

    **The mutation this kills:** an enrollment check that ignores `ended_on` —
    "was ever enrolled" — which serves a dropped student the section's reply.
    **The near miss:** the live classmate, answered.
    """
    world = hold
    plant_the_replies(world)
    live = world.a_student("live-classmate", world.taught)
    ended = world.a_student("ended", world.taught, ended=True)
    world.stand_after_the_opening(HELD_WEEK)

    twin = world.results(live, course_week=HELD_WEEK)
    refused = world.results(ended, course_week=HELD_WEEK)

    assert (
        twin.status_code == 200 and OWN_TEXT in twin.text
    ), f"The live classmate was answered {twin.status_code} {twin.text[:300]!r}."
    assert refused.status_code == REFUSED_STATUS, (
        f"An ended enrollment was answered {refused.status_code} {refused.text[:300]!r}. "
        "Done-when 6: refused."
    )
    assert len(sentences_served(refused)) == 1, f"The refusal carries {sentences_served(refused)}."
    needles = spellings_of(world.taught) | {world.code_of(TAUGHT_COHORT), TEACHER_NAME, OWN_TEXT}
    leaked = named_in(refused, needles)
    assert not leaked, f"The refusal names {leaked}."


def test_a_week_whose_report_has_not_opened_is_refused_beside_the_week_before_and_after(
    hold: HoldWorld,
) -> None:
    """An hour before course week 2's report opens: week 2 is 404, week 1 reads; an hour after, week 2 reads.

    A reply is already stored for week 2 (`EARLY_TEXT`, dated before the opening).
    Whole hours either side, because ADR 0109's effective clock drifts while it is
    read; the opening's exact second is `REPORT_OPENS_BY_TERM_WEEK`'s, asserted by
    `test_the_report_opening_rule_is_six_on_the_monday_after_the_close.py`.

    **The mutations this kill:** the route answering any week the section has a
    window for, closed or not (`week_is_published` not consulted); the response
    read before the week is checked (the early reply leaks); and a gate published
    from the window's close rather than the report's opening (six hours early).
    **The near misses:** week 1 at the same instant, and week 2 an hour after.
    """
    world = hold
    student = world.a_student("unopened", world.taught)
    world.a_response(
        section_id=world.taught,
        course_week=HELD_WEEK,
        author=world.person(world.names.teacher).person_id,
        role=INSTRUCTOR,
        body=EARLY_TEXT,
        published_at=report_opens(HELD_WEEK) - FIRST_ROW_AFTER_OPENING,
    )
    world.stand_before_the_opening(HELD_WEEK)

    refused = world.results(student, course_week=HELD_WEEK)
    week_before = world.results(student, course_week=WEEK_BEFORE)
    world.stand_after_the_opening(HELD_WEEK)
    opened = world.results(student, course_week=HELD_WEEK)

    assert (
        week_before.status_code == 200
    ), f"Course week 1, long opened, was answered {week_before.status_code} at the same instant."
    assert opened.status_code == 200 and EARLY_TEXT in opened.text, (
        f"An hour after the opening course week 2 was answered {opened.status_code} "
        f"{opened.text[:300]!r}."
    )
    assert refused.status_code == REFUSED_STATUS, (
        f"Course week 2, an hour before its report opens, was answered {refused.status_code} "
        f"{refused.text[:300]!r}. Done-when 6: a week whose report has not opened is refused."
    )
    assert len(sentences_served(refused)) == 1, f"The refusal carries {sentences_served(refused)}."
    leaked = named_in(refused, {EARLY_TEXT, TEACHER_NAME, world.code_of(TAUGHT_COHORT)})
    assert not leaked, f"The unopened week's refusal names {leaked}."


def test_every_refusal_is_the_same_404_with_the_same_sentence(hold: HoldWorld) -> None:
    """Nine refused reads over both routes, one world, one clock: byte-identical, one sentence.

    The week route: not enrolled, ended, unopened, a course week the section does
    not have, and a section that does not exist. The no-week route (the
    amendment's A2): not enrolled, ended, a section that does not exist, and a
    section with no published week (the unled course's section, whose only window
    is course week 2's, not yet opened). Decision 5 and A2: one 404, one fixed
    sentence, for every one — so no refusal tells a student which of the nine it
    was, and none confirms that a section they are not in exists (ADR 0074/0079's
    rule, at this door).

    **The mutations this kill:** a 403 for another student's section beside a 404
    for a missing one; a refusal sentence per reason; a framework 404 for a week
    the section lacks (FastAPI's own "Not Found") beside the module's sentence; a
    no-week route with refusals of its own (an empty 200, or "no weeks yet" for a
    section with none published). **The near misses:** the student's own week and
    own latest week, both answered 200 in the same world.
    """
    world = hold
    world.windows_for(UNTAUGHT_COHORT, WEEK_BEFORE, HELD_WEEK)
    world.windows_for(UNMAPPED_COHORT, HELD_WEEK)
    plant_the_replies(world)
    student = world.a_student("five-refusals", world.taught)
    ended = world.a_student("five-refusals-ended", world.taught, ended=True)
    unpublished = world.a_student("nothing-published", world.unmapped_section)
    world.stand_after_the_opening(WEEK_BEFORE)

    own = world.results(student, course_week=WEEK_BEFORE)
    own_latest = world.latest(student)
    assert own_latest.status_code == 200 and STATE in own_latest.text, (
        f"The student's own latest week was answered {own_latest.status_code} "
        f"{own_latest.text[:300]!r}; the no-week refusals beside it need a passing twin."
    )
    refusals = {
        "latest: another section": world.latest(student, section_id=world.sibling_section),
        "latest: an ended enrollment": world.latest(ended),
        "latest: a section that does not exist": world.latest(student, section_id=uuid4()),
        "latest: a section with no published week": world.latest(unpublished),
        "another section": world.results(
            student, course_week=WEEK_BEFORE, section_id=world.sibling_section
        ),
        "an ended enrollment": world.results(ended, course_week=WEEK_BEFORE),
        "an unopened week": world.results(student, course_week=HELD_WEEK),
        "a week the section does not have": world.results(
            student, course_week=A_WEEK_THE_SECTION_DOES_NOT_HAVE
        ),
        "a section that does not exist": world.results(
            student, course_week=WEEK_BEFORE, section_id=uuid4()
        ),
    }

    assert (
        own.status_code == 200 and STATE in own.text
    ), f"The student's own week was answered {own.status_code} {own.text[:300]!r}."
    shapes = {what: (answered.status_code, answered.text) for what, answered in refusals.items()}
    assert {status for status, _ in shapes.values()} == {REFUSED_STATUS}, (
        f"The refusals were answered {[(what, s[0]) for what, s in shapes.items()]}. "
        "Decision 5 and A2: one 404 for every refused case, on either route."
    )
    bodies = {what: text[:200] for what, (_, text) in shapes.items()}
    assert len(set(shapes.values())) == 1, f"The refusals are not byte-identical: {bodies}."
    served = sentences_served(refusals["another section"])
    assert (
        len(served) == 1 and served[0] in response_loop_copy()
    ), f"The refusal carries {served} of `app.copy.response_loop`'s sentences; decision 5: one."


def test_the_latest_route_refuses_another_section_beside_its_own_students_read(
    hold: HoldWorld,
) -> None:
    """The no-week route: a student of `F1WW` asks for `Q1WW`: 404 naming nothing. `Q1WW`'s student reads it.

    The amendment's A2: "the same single 404 … for every case the week route
    refuses". **The mutation this kills:** the no-week route resolving the latest
    week from the section alone and only then checking the enrollment through the
    week route's path — or not at all — which serves `Q1WW`'s latest reply to a
    student of `F1WW`. **The near miss:** `Q1WW`'s own student, answered with it.
    """
    world = hold
    world.windows_for(UNTAUGHT_COHORT, WEEK_BEFORE, HELD_WEEK)
    plant_the_replies(world)
    ours = world.a_student("latest-not-enrolled", world.taught)
    theirs = world.a_student("latest-sibling-own", world.sibling_section)
    world.stand_after_the_opening(HELD_WEEK)

    twin = world.latest(theirs)
    refused = world.latest(ours, section_id=world.sibling_section)

    assert twin.status_code == 200 and SIBLING_TEXT in twin.text, (
        f"`Q1WW`'s own student's no-week read was answered {twin.status_code} "
        f"{twin.text[:300]!r}; it must carry `Q1WW`'s latest reply."
    )
    assert refused.status_code == REFUSED_STATUS, (
        f"A student of `F1WW` asking the no-week route for `Q1WW` was answered "
        f"{refused.status_code} {refused.text[:300]!r}. A2: the same 404."
    )
    assert len(sentences_served(refused)) == 1, f"The refusal carries {sentences_served(refused)}."
    leaked = named_in(
        refused,
        spellings_of(world.sibling_section)
        | {world.code_of(UNTAUGHT_COHORT), SIBLING_SECTION_TEACHER_NAME, SIBLING_TEXT},
    )
    assert not leaked, f"The no-week refusal names {leaked}."


def test_the_latest_route_refuses_a_section_with_no_published_week_until_one_opens(
    hold: HoldWorld,
) -> None:
    """An hour before `F1WW`'s first report opens: the no-week read is 404; an hour after, week 1.

    Every one of `F1WW`'s six weeks has a window, so a "latest" computed from the
    windows has six candidates; none has opened. The reply planted in week 1 is
    already stored, so a refusal that read it first would have it to leak.

    **The mutations this kill:** the latest week taken as the last window
    (course week 6, before any report opened); an empty or `null` 200 for a
    section with nothing published, which A2 makes the one 404. **The near miss:**
    the same student an hour after the first opening, answered with week 1.
    """
    world = hold
    world.a_response(
        section_id=world.taught,
        course_week=WEEK_BEFORE,
        author=world.person(world.names.teacher).person_id,
        role=INSTRUCTOR,
        body=EARLY_TEXT,
        published_at=report_opens(WEEK_BEFORE) - FIRST_ROW_AFTER_OPENING,
    )
    student = world.a_student("latest-nothing-yet", world.taught)

    world.stand_before_the_opening(WEEK_BEFORE)
    refused = world.latest(student)
    world.stand_after_the_opening(WEEK_BEFORE)
    opened = world.latest(student)

    assert opened.status_code == 200 and EARLY_TEXT in opened.text, (
        f"An hour after course week 1 opened the no-week read answered {opened.status_code} "
        f"{opened.text[:300]!r}."
    )
    assert refused.status_code == REFUSED_STATUS, (
        f"With no week published the no-week read answered {refused.status_code} "
        f"{refused.text[:300]!r}. A2: the same single 404."
    )
    assert len(sentences_served(refused)) == 1, f"The refusal carries {sentences_served(refused)}."
    leaked = named_in(refused, {EARLY_TEXT, TEACHER_NAME, world.code_of(TAUGHT_COHORT)})
    assert not leaked, f"The no-week refusal names {leaked}."


def test_a_session_that_is_not_a_students_is_refused(hold: HoldWorld) -> None:
    """The section's own teacher, with their launched instructor session: refused, never answered.

    `require_student` refuses every role that is not `STUDENT` (E2-09). The
    teacher of `F1WW` can read their own report; this route is the student's.

    **The mutation this kills:** the route behind a dependency that accepts any
    session, which answers an instructor with the student page's state. **The
    near miss:** a student of the same section, answered.
    """
    world = hold
    plant_the_replies(world)
    student = world.a_student("beside-the-teacher", world.taught)
    world.stand_after_the_opening(HELD_WEEK)

    answered = world.results(student, course_week=HELD_WEEK)
    url = results_url(world.route(), section_id=world.taught, course_week=HELD_WEEK)
    refused = world.review.ask("GET", url, token=world.review.instructor_token)

    assert answered.status_code == 200, f"The student was answered {answered.status_code}."
    assert refused.status_code == NOT_A_STUDENT_STATUS, (
        f"The section's teacher, with an instructor session, was answered {refused.status_code} "
        f"{refused.text[:300]!r} by the student results route; `require_student` refuses every "
        f"other role with {NOT_A_STUDENT_STATUS} (E2-09)."
    )
    assert OWN_TEXT not in refused.text, "The instructor's refusal carries the reply."
    latest_url = results_url(latest_results_route(world.door.application), section_id=world.taught)
    latest_refused = world.review.ask("GET", latest_url, token=world.review.instructor_token)
    assert latest_refused.status_code == NOT_A_STUDENT_STATUS, (
        f"The section's teacher was answered {latest_refused.status_code} "
        f"{latest_refused.text[:300]!r} by the no-week results route (A2)."
    )
    assert OWN_TEXT not in latest_refused.text, "The no-week refusal carries the reply."
