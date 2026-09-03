"""SPEC §4.1 item 1, over the field E2-17 item 5 adds — ticket E2-17.

Item 1: "Students never see comparables, benchmarks, university averages, or
**other sections** — in charts, text, tooltips, exports, or aria labels." E2-17
adds a course label to the one student-visible read path, and a label is built by
joining *upward* out of the section — section → course → prefix — which is the
first widening anything has asked of that query since it was written.

**`app.services.survey_read`'s join is deliberately narrow, and its own docstring
says so**: widening it is how another person's sections reach a student's page,
and the two enrollment filters carry the §4.1 rule. This module is what tells a
widening that reached only the section's own course from one that reached
further.

**Why the world's sibling section is no use as a needle here.**
`tests/fixtures/student_read.py` seeds two sections under one containment chain
on purpose, so they share a course — and therefore share a *label*. An answer
that named the other section's course would carry the identical string a correct
answer carries, and a scan for it would be silent whatever the query did
(`docs/MISTAKES.md` entry 3). So this module seeds its own prefix, course and
section: three values nothing else in the database holds, with a window over the
same week and **somebody enrolled in it**, so that every way of losing the
student predicate has a differently-shaped row to leak.

**The near miss every test here must survive** is the one that has caught this
project repeatedly: an answer that returned *nothing* names no other course
either. So each test first requires the answer to carry this student's **own**
course label — the very field under test — before it reports that it did not
carry anybody else's.

**The refusal pair is here rather than next door** because it is the same §4.1
question one layer out: a route that takes no parameters has to answer a request
naming a real section it will not serve exactly as it answers one naming a
section that does not exist, and a new member on the answer is a new way for
those two to differ (ADR 0074/0079). `test_the_student_read_path_names_nothing_
outside_the_enrollment.py` asserts that of the whole body; this asserts it of the
labels, which is the half that stays meaningful if the body ever stops being
byte-stable.

**The marker sits at module level**, in the list form beside `integration` and
`lti`, so this module's next denial test inherits it —
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
pins that spelling.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.student_read import (
    COURSE_LABEL_FIELD,
    FOREIGN_COURSE_TITLE,
    FOREIGN_PREFIX_CODE,
    OTHER_SECTION_ENROLLED_SINCE,
    SECTION_TABLE,
    STUDENT_READ_PATH,
    ForeignCourse,
    StudentReadDoor,
    around,
    decoded,
    key_of,
    objects_carrying,
    response_surface,
)

pytestmark = [pytest.mark.invariant, pytest.mark.integration, pytest.mark.lti]

# The query parameter names a caller could try to reach another section by, as
# `test_the_student_read_path_names_nothing_outside_the_enrollment.py` lists
# them. That module owns the inventory and says why it is a convention rather
# than a closed class; this one runs the same three names against the member
# E2-17 adds, because a field that varies with a parameter is a field that
# answers questions the route does not take.
SECTION_PARAMETERS = ("section_id", "section", "section_code")


@pytest.fixture
def a_course_with_somebody_else_in_it(
    student_read_door: StudentReadDoor, enrol: Any
) -> ForeignCourse:
    """A course this reader is not in, with a live enrollment that is not theirs.

    Both halves matter and they catch different mutations. The rows alone are
    what a join widened past the section reaches — up to the prefix and back down
    to its other courses. The **enrollment** is what a read that kept its joins
    and lost `Enrollment.user_id == user_id` reaches: without somebody else in
    this section, every live enrollment in the database is the reader's own and
    the widened query answers exactly what the correct one answers. That is not a
    hypothesis — it is the state E2-09's mutation battery measured, with the
    suite green and the docstring claiming otherwise.

    The third person the world already seeds is used rather than a fourth: they
    are somebody other than the reader, which is the whole requirement.
    """
    world = student_read_door.world
    foreign = world.seed_a_course_this_student_is_not_in()
    enrol.enrol(
        user_id=world.other_section_student_id,
        section_id=key_of(world.tables, SECTION_TABLE, foreign.section),
        started_on=OTHER_SECTION_ENROLLED_SINCE,
        ended_on=None,
    )
    return foreign


def labels_in(body: Any) -> list[str]:
    """Every `course_label` anywhere in a decoded answer, wherever it sits."""
    return [entry[COURSE_LABEL_FIELD] for entry in objects_carrying(body, COURSE_LABEL_FIELD)]


def test_the_answer_names_no_course_the_student_is_not_enrolled_in(
    student_read_door: StudentReadDoor, a_course_with_somebody_else_in_it: ForeignCourse
) -> None:
    """SPEC §4.1 item 1: the new label names this student's course and no other.

    One course the reader is enrolled in; one they are not, with its own prefix,
    its own number, its own title, a window open at this instant and somebody
    else enrolled in it. The answer must carry the first label and none of the
    second's three strings, anywhere — in the body or in a header.

    **The mutations this kills.** A join written from `prefix` down rather than
    from the section up, which reaches every course under the prefix. A join to
    `course` that lost its `section_id` predicate, which reaches every course
    there is. And `Enrollment.user_id == user_id` deleted from
    `_live_enrollments`, which reaches the *other person's* enrollment and
    therefore the label of the course they are in — the one shape the world's own
    sibling section cannot express, because it shares the reader's course.

    **The near misses it must survive.** An answer carrying the reader's own
    label and nothing else, which is the pass, and which is required before the
    scan runs — a refusal, an empty list or a 500 names no foreign course either.
    And a scan for strings the two courses *share*: there are none, deliberately,
    because the second course is seeded with its own prefix rather than as a
    sibling under the first.

    **The canary.** The three foreign strings are required to be present in the
    database — as a section that exists, a label the world can compose, and an
    enrollment that is not the reader's — before the test reports that they were
    not returned. Without that, a fixture that seeded nothing produces the same
    green as a read path that withheld everything.
    """
    world = student_read_door.world
    foreign = a_course_with_somebody_else_in_it
    forbidden = world.anything_shaped_like_the_foreign_courses_label(foreign)
    mine = world.course_label_of(world.enrolled_section)

    assert mine not in forbidden and not any(needle in mine for needle in forbidden), (
        f"This student's own course label {mine!r} contains, or is, one of the values this test "
        f"searches for ({sorted(forbidden)}). The scan would then report a correct answer as a "
        "leak. The foreign course is seeded under its own prefix precisely so the two share no "
        "string."
    )
    assert {FOREIGN_PREFIX_CODE, FOREIGN_COURSE_TITLE} <= forbidden, (
        f"The needle set is {sorted(forbidden)} and does not hold the foreign prefix code and "
        "title. Those two are what name that course to a person, and a search without them is "
        "looking only for the composed label — which a partially-widened join need not produce."
    )

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} for a student with a live "
        f"enrollment and an open window. Body begins {answered.text[:300]!r}. A refusal names no "
        "foreign course either, so this sweep cannot be allowed to pass over one."
    )
    body = decoded(answered, f"`GET {STUDENT_READ_PATH}`")
    assert labels_in(body) == [mine], (
        f"The answer carries {labels_in(body)} as `{COURSE_LABEL_FIELD}`; this student has one "
        f"live enrollment and its course is {mine!r}. Body begins {answered.text[:300]!r}.\n\n"
        "Asserted before the denial below, and not instead of it: an answer carrying no label at "
        "all names no foreign course either, and every scan under it would be a statement about "
        "an empty surface (`docs/MISTAKES.md` entry 3). Until E2-17 item 5 lands this is the "
        "assertion that reds, and it names the deliverable."
    )

    surface = response_surface(answered)
    leaked = sorted(value for value in forbidden if value in surface)
    assert not leaked, (
        f"`GET {STUDENT_READ_PATH}` named {len(leaked)} value(s) belonging to a course this "
        f"student is not enrolled in: {leaked[:3]}. The first sits in "
        f"{around(surface, leaked[0])!r}.\n\n"
        "SPEC §4.1 item 1: students never see other sections, in any surface — and a course is "
        "how a section names itself to a person.\n\n"
        "**Which mutation, read off what leaked.** The composed label or the title is a join that "
        "reached another course: written from the prefix down, or to `course` without the "
        "section's own key. The prefix code alone is a join that reached the prefix and read it "
        "rather than the course. Either can also be a read that kept its joins and lost "
        "`Enrollment.user_id == user_id`, which reaches the enrollment of the person seeded into "
        "that section — and that is the shape the world's sibling section cannot show, because it "
        "shares this reader's course."
    )


@pytest.mark.parametrize("parameter", SECTION_PARAMETERS)
def test_the_course_label_is_the_same_however_the_read_is_asked(
    student_read_door: StudentReadDoor,
    a_course_with_somebody_else_in_it: ForeignCourse,
    parameter: str,
) -> None:
    """A refusal stays indistinguishable from a nonexistence once the answer names a course.

    E2-09's route takes no parameters and E2-17 does not give it any; what is
    asserted is that the new member changes nothing observable. Three reads —
    plain, one naming the section this student is not in, one naming a section
    that does not exist anywhere — and the last two must be answered identically,
    with the identical labels.

    **The mutation this kills:** a label lookup that honours a section named in
    the query — the natural way to grow "show me that course" out of a field that
    already names one — and then answers a real section it will not serve
    differently from an invented one. A `404` for the invented identifier beside a
    `403` for the real one confirms the real one exists, which is a fact about the
    institution's sections that a student may not learn here (ADR 0074/0079).

    **The near miss it must survive**: a route that ignores unknown query
    parameters answers all three reads the same way, which is the pass.

    **The label comparison is unconditional and the body comparison is not.** The
    body's stability is measured first, exactly as
    `test_the_student_read_path_names_nothing_outside_the_enrollment.py` measures
    it, because an answer that echoed an instant would not be byte-stable and
    demanding equality of it would be a red nobody could fix. The set of labels is
    stable whatever the body does, so it is required to be equal in every case —
    which is the assertion that keeps meaning something if the body ever grows a
    clock.
    """
    world = student_read_door.world
    forbidden = world.anything_shaped_like_the_foreign_courses_label(
        a_course_with_somebody_else_in_it
    )

    first = student_read_door.get()
    second = student_read_door.get()
    named = student_read_door.get(**{parameter: str(world.other_section_id)})
    invented = student_read_door.get(**{parameter: str(uuid4())})

    assert first.status_code == 200, (
        f"The plain read answered {first.status_code}, so there is no ordinary answer for the two "
        f"parametrised reads to be compared against. Body begins {first.text[:300]!r}."
    )
    assert labels_in(decoded(first, "the plain read")) == [
        world.course_label_of(world.enrolled_section)
    ], (
        f"The plain read carries {labels_in(decoded(first, 'the plain read'))} as "
        f"`{COURSE_LABEL_FIELD}`, and this student's one enrollment is in "
        f"{world.course_label_of(world.enrolled_section)!r}. Every comparison below is between "
        "three answers, and three answers carrying no label at all are equal to each other for a "
        "reason that has nothing to do with this test."
    )
    assert named.status_code == invented.status_code == first.status_code, (
        f"`?{parameter}=` naming the section this student is not enrolled in was answered "
        f"{named.status_code}, naming a section that does not exist at all {invented.status_code}, "
        f"and the plain read {first.status_code}. Two different answers tell the caller which "
        "identifier is real, whether or not any data follows (ADR 0074/0079)."
    )

    labels = {
        "the plain read": labels_in(decoded(first, "the plain read")),
        "naming the other section": labels_in(decoded(named, "the read naming another section")),
        "naming a section nobody has": labels_in(decoded(invented, "the read naming nothing")),
    }
    assert len(set(map(tuple, labels.values()))) == 1, (
        f"The three reads carry different course labels: {labels}.\n\n"
        f"A `{COURSE_LABEL_FIELD}` that changes with `?{parameter}=` is a parameter being "
        "honoured, and the first thing anybody would ask this path about is a section they are "
        "not in."
    )

    if first.text == second.text:
        assert named.text == invented.text == first.text, (
            f"Two plain reads of `{STUDENT_READ_PATH}` are byte-identical, so this answer is "
            f"stable — but adding `?{parameter}=` changed it. Naming the other section answered "
            f"{named.text[:200]!r} and naming a section that does not exist answered "
            f"{invented.text[:200]!r}."
        )

    for answered, what in ((named, "the other section"), (invented, "a section nobody has")):
        surface = response_surface(answered)
        leaked = sorted(value for value in forbidden if value in surface)
        assert not leaked, (
            f"Asking `?{parameter}=` for {what} was answered with {leaked[:3]}, which names a "
            f"course this student is not enrolled in. First occurrence: "
            f"{around(surface, leaked[0])!r}."
        )
