"""An instructor publishes and edits a week's response through the routes — E7-03, done-when 1 and 2.

> **Publish and edit.** An instructor publishes a response for a published week
> and edits it; each is one appended row naming them and their role. A second
> publish is refused. An edit by anyone but the first publisher is refused,
> including the lead after an on-behalf response the instructor tries to edit,
> and the other way round. Each refusal writes no row.
>
> **An edit never re-holds.** After an edit in a required week, the student state
> (02) stays released.

Work order decision 1: `POST`/`PUT …/sections/{section_id}/weeks/{course_week}/
response`, `{text, ai_seeded}`; 201 and 200; 409 with a fixed sentence for a
second publish, and one sentence for an edit with no response yet or by someone
who is not the first publisher; the report's own 404 for an untaught section or
an unpublished week. Every write here rides the teacher's Bearer session; the
cookie path is `test_the_response_loop_writes_refuse_a_missing_or_foreign_csrf_token.py`'s.

**The rows are read back as the superuser**, never off the route's answer, so a
route that answers 201 and writes nothing is red.

**Which failure a red is, before E7-03 lands.** `find_route` fails naming the
instructor's response routes — a FAILED, never an ERROR.
"""

import pytest
from fixtures.report_api import UNTAUGHT_COHORT
from fixtures.response_loop_doors import (
    CLEAR_PAST,
    CONFLICT,
    CREATED,
    NOT_FOUND,
    OK,
    ON_BEHALF_AFTER,
    ON_BEHALF_EDIT,
    ON_BEHALF_PUBLISH,
    ON_BEHALF_WEEK,
    LoopWorld,
)
from fixtures.staff_names import (
    AI_SEEDED_COLUMN,
    RESPONSE_AUTHOR_COLUMN,
    RESPONSE_BODY_COLUMN,
    RESPONSE_TEXT_MAX,
    ROLE_COLUMN,
)
from fixtures.the_hold import (
    AWAITING,
    INSTRUCTOR,
    LEAD_FACULTY,
    PUBLISHED,
    RESPONSE,
    STATE,
    TEXT,
    report_opens,
    sentences_served,
)

pytestmark = pytest.mark.integration

FIRST = "E7-03 the teacher's first version: the problem set moves to Thursday"
SECOND = "E7-03 the teacher's edit: the problem set moves to Friday instead"
LEADS = "E7-03 the lead's on-behalf response: we heard you about the pacing"


def summary(rows: list[dict]) -> list[tuple[str, str, str, bool]]:
    return [
        (
            str(row[RESPONSE_AUTHOR_COLUMN]),
            row[ROLE_COLUMN],
            row[RESPONSE_BODY_COLUMN],
            row[AI_SEEDED_COLUMN],
        )
        for row in rows
    ]


def test_a_publish_then_an_edit_each_append_one_row_naming_the_teacher(
    response_loop: LoopWorld,
) -> None:
    """Publish (201), edit (200): two rows, each the teacher's, as `INSTRUCTOR`, with its own text.

    **The mutations this kill:** a publish that answers 201 and writes nothing; an
    edit that overwrites the first row (one row afterwards); a row naming anyone
    but the session's person, or a role other than `INSTRUCTOR`; `ai_seeded`
    dropped (the publish sends `True`). **The near miss:** the first read of the
    rows, after the publish alone — exactly one.
    """
    world = response_loop
    world.stand(CLEAR_PAST)
    teacher = str(world.teacher_id)

    url = world.instructor_url("POST")
    published = world.ask(
        "POST", url, token=world.teacher_token, json={"text": FIRST, "ai_seeded": True}
    )
    assert published.status_code == CREATED, (
        f"The teacher's publish answered {published.status_code}, not {CREATED}. Body "
        f"{published.text[:400]!r}."
    )
    after_publish = summary(world.responses_of(world.hold.taught))
    edited = world.instructor("PUT", text=SECOND)
    assert (
        edited.status_code == OK
    ), f"The teacher's edit answered {edited.status_code}, not {OK}. Body {edited.text[:400]!r}."
    after_edit = summary(world.responses_of(world.hold.taught))

    assert after_publish == [(teacher, INSTRUCTOR, FIRST, True)], (
        f"After the publish the section holds {after_publish}; done-when 1: one appended row "
        "naming the teacher and their role."
    )
    assert after_edit == [
        (teacher, INSTRUCTOR, FIRST, True),
        (teacher, INSTRUCTOR, SECOND, False),
    ], (
        f"After the edit the section holds {after_edit}; done-when 1: the edit is one more "
        "appended row, and SPEC §5.3: never overwrites the old one."
    )


def test_a_second_publish_is_refused_with_one_sentence_and_writes_no_row(
    response_loop: LoopWorld,
) -> None:
    """Publish, publish again: 409 carrying one `copy/response_loop` sentence; still one row.

    **The mutations this kill:** a second publish treated as an edit (two rows); a
    second publish that replaces the first; a 409 carrying no registered sentence.
    **The near miss:** the first publish, 201.
    """
    world = response_loop
    world.stand(CLEAR_PAST)
    assert world.instructor("POST", text=FIRST).status_code == CREATED

    again = world.instructor("POST", text=SECOND)

    assert again.status_code == CONFLICT, (
        f"A second publish for one section-week answered {again.status_code}, not {CONFLICT}. "
        "Ruling 3: one response per section-week."
    )
    assert len(sentences_served(again)) == 1, (
        f"The 409 served {again.text[:300]!r}; decision 1: one fixed sentence from "
        "`app/copy/response_loop.py`."
    )
    bodies = [row[RESPONSE_BODY_COLUMN] for row in world.responses_of(world.hold.taught)]
    assert bodies == [FIRST], f"The refused publish left the section holding {bodies}."


def test_an_edit_with_no_response_yet_is_refused_and_writes_no_row(
    response_loop: LoopWorld,
) -> None:
    """`PUT` before any publish: 409, no row.

    **The mutation this kills:** an edit route that publishes when there is
    nothing to edit — a back door around the publish route's rules.
    """
    world = response_loop
    world.stand(CLEAR_PAST)

    refused = world.instructor("PUT", text=SECOND)

    assert (
        refused.status_code == CONFLICT
    ), f"An edit with no response yet answered {refused.status_code}, not {CONFLICT}."
    assert world.responses_of(world.hold.taught) == [], "The refused edit wrote a row."


def test_the_teacher_cannot_edit_the_leads_on_behalf_response(response_loop: LoopWorld) -> None:
    """The lead publishes on behalf past +96h; the teacher's `PUT`: 409, the same sentence, no row.

    **The mutations this kill:** "first publisher" read as "anyone who teaches the
    section"; an edit check keyed on the role rather than the person. **The near
    miss:** the lead's own on-behalf publish, which must land as `LEAD_FACULTY`.
    """
    world = response_loop
    world.own_course_required()
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)
    # The same edit, the same week, before anybody published: the other cause of the 409.
    no_response_yet = world.instructor("PUT", text=SECOND)
    published = world.on_behalf(
        ON_BEHALF_PUBLISH, world.lead, section_id=world.hold.taught, text=LEADS
    )
    assert 200 <= published.status_code < 300, (
        f"The lead's on-behalf publish past +96h answered {published.status_code}. Body "
        f"{published.text[:400]!r}."
    )
    before = summary(world.responses_of(world.hold.taught))
    assert before == [(str(world.lead.person_id), LEAD_FACULTY, LEADS, False)], before

    refused = world.instructor("PUT", text=SECOND)

    assert refused.status_code == CONFLICT, (
        f"The teacher's edit of the lead's response answered {refused.status_code}, not "
        f"{CONFLICT}. SPEC §5.3: only the person who first published may edit."
    )
    assert no_response_yet.status_code == CONFLICT and refused.content == no_response_yet.content, (
        f"The not-the-first-publisher refusal ({refused.text[:200]!r}) and the no-response-yet "
        f"refusal ({no_response_yet.status_code}, {no_response_yet.text[:200]!r}) differ; decision "
        "1: one sentence for both, so the refusal reveals nothing about who published."
    )
    assert summary(world.responses_of(world.hold.taught)) == before, "The refused edit wrote a row."


def test_the_lead_cannot_edit_the_teachers_response_through_on_behalf(
    response_loop: LoopWorld,
) -> None:
    """The teacher publishes; past +96h the lead's on-behalf `POST` and `PUT` are both 404; no row.

    The other way round of done-when 1. Decision 5: once published the on-behalf
    door is closed (already answered), and the edit is the first publisher's only.

    **The mutations this kill:** an on-behalf edit that appends to whatever
    response the week holds; an on-behalf publish that ignores an existing
    response (a second author in one week). **The near miss:** the teacher's own
    publish, 201.
    """
    world = response_loop
    world.own_course_required()
    world.stand(CLEAR_PAST)
    assert world.instructor("POST", text=FIRST).status_code == CREATED
    world.stand(ON_BEHALF_AFTER + CLEAR_PAST)
    before = summary(world.responses_of(world.hold.taught))

    edit = world.on_behalf(ON_BEHALF_EDIT, world.lead, section_id=world.hold.taught, text=LEADS)
    publish = world.on_behalf(
        ON_BEHALF_PUBLISH, world.lead, section_id=world.hold.taught, text=LEADS
    )

    assert (edit.status_code, publish.status_code) == (NOT_FOUND, NOT_FOUND), (
        f"The lead's on-behalf edit and publish of the teacher's week answered "
        f"{edit.status_code} and {publish.status_code}; decision 5: both 404."
    )
    assert summary(world.responses_of(world.hold.taught)) == before, "A refused write left a row."


@pytest.mark.parametrize("where", ["a-section-not-taught", "an-unpublished-week"])
def test_a_publish_outside_the_teachers_published_weeks_is_the_reports_404(
    response_loop: LoopWorld, where: str
) -> None:
    """`Q1WW` (not hers), or course week 2 before its report opens: 404, no row anywhere.

    **The mutations this kill:** a publish route that trusts the path's section
    (any instructor publishes anywhere); a publish into a week students cannot yet
    read. **The near miss:** `test_a_publish_then_an_edit_...`, the published week
    of her own section.
    """
    world = response_loop
    if where == "a-section-not-taught":
        world.hold.windows_for(UNTAUGHT_COHORT, ON_BEHALF_WEEK)
        world.stand(CLEAR_PAST)
        refused = world.instructor("POST", text=FIRST, section_id=world.hold.sibling_section)
    else:
        world.hold.stand_at(report_opens(ON_BEHALF_WEEK + 1) - CLEAR_PAST)
        refused = world.instructor("POST", text=FIRST, course_week=ON_BEHALF_WEEK + 1)

    assert (
        refused.status_code == NOT_FOUND
    ), f"A publish to {where} answered {refused.status_code}, not {NOT_FOUND}."
    assert world.response_count() == 0, f"The refused publish to {where} wrote a row."


def test_text_over_the_bound_is_refused_and_never_shortened(response_loop: LoopWorld) -> None:
    """`RESPONSE_TEXT_MAX + 1` characters: a 4xx and no row; exactly the bound: 201.

    `docs/MISTAKES.md` entry 29: a value repaired before the check that should
    refuse it. **The mutations this kill:** a route that truncates to the bound
    and writes. **The near miss:** a text of exactly the bound, accepted — so the
    refusal is the bound and not a route refusing long text.
    """
    world = response_loop
    world.stand(CLEAR_PAST)

    refused = world.instructor("POST", text="x" * (RESPONSE_TEXT_MAX + 1))
    assert (
        400 <= refused.status_code < 500
    ), f"A text one over the bound answered {refused.status_code}."
    assert world.response_count() == 0, "A text over the bound was written (shortened?)."

    accepted = world.instructor("POST", text="y" * RESPONSE_TEXT_MAX)
    assert (
        accepted.status_code == CREATED
    ), f"A text of exactly {RESPONSE_TEXT_MAX} characters answered {accepted.status_code}."


def test_an_edit_in_a_required_week_leaves_the_student_released(response_loop: LoopWorld) -> None:
    """Done-when 2, as a sequence of reads (entry 51): awaiting, publish, published, edit, published.

    A student of `F1WW`, the own course required a day before the week opened.
    Three reads, one either side of each write.

    **The mutations this kill:** an edit route that re-evaluates the hold (a later
    read of `awaiting`); an edit that writes through a path the student read does
    not see (the old text after the edit). **The near miss:** the first read,
    `awaiting` — so `published` afterwards is the publish's doing.
    """
    world = response_loop
    world.own_course_required()
    student = world.hold.a_student("e7-03-edit", world.hold.taught)
    world.stand(CLEAR_PAST)

    held = world.hold.payload(student, course_week=ON_BEHALF_WEEK)
    assert world.instructor("POST", text=FIRST).status_code == CREATED
    released = world.hold.payload(student, course_week=ON_BEHALF_WEEK)
    assert world.instructor("PUT", text=SECOND).status_code == OK
    after_edit = world.hold.payload(student, course_week=ON_BEHALF_WEEK)

    assert held[STATE] == AWAITING, f"Before the publish the student read {held[STATE]!r}."
    assert released[STATE] == PUBLISHED, f"After the publish the student read {released[STATE]!r}."
    assert after_edit[STATE] == PUBLISHED, (
        f"After the edit the student read {after_edit[STATE]!r}. Done-when 2: an edit never "
        "re-holds."
    )
    assert after_edit[RESPONSE][TEXT] == SECOND, (
        f"After the edit the student read {after_edit[RESPONSE][TEXT]!r}; SPEC §5.3: students see "
        "the latest version."
    )
