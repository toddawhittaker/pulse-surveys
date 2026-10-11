"""Only published and kept comments reach a student — E8-01, done-when 4.

> 4. **Only published and kept comments reach a student.** In one shown stream,
>    a flagged-collapsed comment, an excluded comment and a comment with a Care
>    verdict (threat or self-harm) are absent, and a kept comment and a
>    published comment are present. The same holds in a release batch. The read
>    goes through v004, and no student read queries `answer` itself.

The last sentence is
`test_the_students_comment_reads_go_through_the_comment_view_and_never_the_answer_table.py`'s.

**Each comment is put in its state through the product's own paths**: a new
respondent's submission with the routed verdict the test names (`harmful`
collapses a comment, `threat` and `self_harm` route it to Care), and every
exclude and keep through E6-03's decision route — the exclusion, of a comment
the AI did not flag, with a stated reason.

**The instructor's report is the control** (`docs/MISTAKES.md` entry 58). It
shows the published, kept, flagged and excluded comments, each with that status,
so the student's page omitting three of them is a filter and not a world in which
they never existed. The two Care-class comments are hidden from the instructor
too (SPEC §5.2), so their control is the Care record instead: each has a
`threat_case`, which is the reader they were routed to.

**Which failure a red is, before E8-01 lands:** `student_week.read` fails naming
the four members the work order adds.
"""

import pytest
from fixtures.moderation import CLEAR, HARMFUL, SELF_HARM, THREAT, threat_cases
from fixtures.report_api import FULL_WEEK_COMMENTS, HELD_COMMENTS
from fixtures.report_views import INSTRUCTOR_STREAM
from fixtures.student_week import (
    CUT_BEFORE_OPENING,
    EXCLUDE,
    INSTRUCTOR_NAME,
    KEEP,
    SHOWN_EXCLUDED,
    SHOWN_FLAGGED,
    SHOWN_KEPT,
    SHOWN_PUBLISHED,
    a_batch,
    answer_id_of,
    comment_texts,
    decide,
    instructor_released_statuses,
    instructor_report,
    instructor_statuses,
    plant_comment,
    read,
    released_texts,
    route_owed_verdicts,
    streams_of,
)
from fixtures.the_hold import HoldWorld, report_opens

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

SHOWN_WEEK = 1
HELD_WEEK = 3
LATEST = 4


def texts_for(where: str) -> dict[str, str]:
    """One distinctive text per state, for one world. Long enough to clear SPEC §3.3's floor."""
    return {
        "published": f"E8-01 {where} published: the worked examples made the proofs readable",
        "kept": f"E8-01 {where} kept: the lecturer talks over every question people ask",
        "flagged": f"E8-01 {where} flagged: the lecturer is useless and should be replaced",
        "excluded": f"E8-01 {where} excluded: the lab handout contradicts the marking rubric",
        "threat": f"E8-01 {where} threat: somebody in this class is going to get hurt",
        "self_harm": f"E8-01 {where} self harm: I do not think I can keep going this term",
    }


VERDICT_OF = {
    "published": CLEAR,
    "kept": HARMFUL,
    "flagged": HARMFUL,
    "excluded": CLEAR,
    "threat": THREAT,
    "self_harm": SELF_HARM,
}


def plant_every_state(world: HoldWorld, week: int, texts: dict[str, str]) -> dict[str, object]:
    """One comment per state's verdict, in the instructor stream of one week; their ids."""
    return {
        state: plant_comment(
            world,
            course_week=week,
            stream=INSTRUCTOR_STREAM,
            text=texts[state],
            verdict=verdict,
        )
        for state, verdict in VERDICT_OF.items()
    }


def assert_the_care_record_holds(world: HoldWorld, ids: dict[str, object]) -> None:
    """Both Care-class comments opened a case: they exist, and Care is the reader they went to."""
    session = world.rows.session
    session.rollback()
    for state in ("threat", "self_harm"):
        assert threat_cases(session, ids[state]), (
            f"The {state} comment opened no `threat_case`, so its absence from the student's page "
            "would be explained by a comment the routing never saw. A broken world, not a red."
        )
    session.rollback()


def test_a_shown_stream_carries_its_published_and_kept_comments_and_none_of_the_others(
    hold: HoldWorld,
) -> None:
    """Course week 1's instructor stream, shown, with one comment in each state beside the five.

    **The mutations this kills:** the student read taken from `visible_cards`
    unfiltered (the flagged and excluded comments, which an instructor sees,
    reach the student); a filter on `published` alone (the kept comment
    disappears — SPEC §5.2's "Keep for students" publishes it); a filter
    excluding `flagged_collapsed` but not `excluded`, or the reverse; and a read
    of `answer` beside the view, which would carry the two Care-class comments
    the view leaves out. **The near misses:** the published and kept comments,
    and the five canonical ones, which must all be there.
    """
    world = hold
    texts = texts_for("week one")
    ids = plant_every_state(world, SHOWN_WEEK, texts)
    decide(world, ids["kept"], KEEP)
    decide(world, ids["excluded"], EXCLUDE)
    student = world.a_student("statuses-shown", world.taught)
    world.stand_after_the_opening(SHOWN_WEEK)

    statuses = instructor_statuses(instructor_report(world, SHOWN_WEEK), INSTRUCTOR_STREAM)
    expected = {
        texts["published"]: SHOWN_PUBLISHED,
        texts["kept"]: SHOWN_KEPT,
        texts["flagged"]: SHOWN_FLAGGED,
        texts["excluded"]: SHOWN_EXCLUDED,
    }
    assert {text: statuses.get(text) for text in expected} == expected, (
        f"The instructor's report shows {statuses}; this world needs each planted comment there in "
        "the state it was put in. A broken world, not a red."
    )
    assert_the_care_record_holds(world, ids)

    body, answered = read(world, student, SHOWN_WEEK)
    shown = comment_texts(streams_of(body, "Course week 1")[INSTRUCTOR_NAME])

    assert sorted(shown) == sorted((*FULL_WEEK_COMMENTS, texts["published"], texts["kept"])), (
        f"Course week 1's instructor stream carries {shown}. Done-when 4: the published and the "
        "kept comment, beside the five canonical ones, and nothing else."
    )
    leaked = [
        state
        for state in ("flagged", "excluded", "threat", "self_harm")
        if texts[state] in answered.text
    ]
    assert leaked == [], f"The student's page serves the {leaked} comment(s)."


def test_a_release_batch_carries_its_published_and_kept_comments_and_none_of_the_others(
    hold: HoldWorld,
) -> None:
    """The same six states in held week 3, released in a batch with its three canonical comments.

    The batch is cut before week 4 opened and read on week 4's page, where ruling
    1 shows it. Week 3's verdicts are owed when the comments are planted (the
    hold world's clock has closed week 1 only), so the clock is stood after week
    4's opening and the owed verdicts routed before anything decides on them
    (dispute E8-01-01). The exclude and keep are then made through the route,
    which accepts a decision on a comment in the instructor's release.

    **The mutations this kills:** the released read taken from `released_cards`
    unfiltered — the instructor's release carries flagged and excluded comments
    with their chips, and the student's must not; and a filter applied to the
    week's comments and forgotten on the release. **The near misses:** the
    published and kept comments, and the three canonical held ones.
    """
    world = hold
    texts = texts_for("week three")
    ids = plant_every_state(world, HELD_WEEK, texts)
    canonical = [answer_id_of(world, text) for text in HELD_COMMENTS[HELD_WEEK]]
    a_batch(
        world,
        cut_at=report_opens(LATEST) - CUT_BEFORE_OPENING,
        answer_ids=[*canonical, *ids.values()],
    )
    route_owed_verdicts(world, standing_after=LATEST)
    decide(world, ids["kept"], KEEP)
    decide(world, ids["excluded"], EXCLUDE)
    student = world.a_student("statuses-released", world.taught)

    statuses = instructor_released_statuses(instructor_report(world, LATEST))
    expected = {
        texts["published"]: SHOWN_PUBLISHED,
        texts["kept"]: SHOWN_KEPT,
        texts["flagged"]: SHOWN_FLAGGED,
        texts["excluded"]: SHOWN_EXCLUDED,
    }
    assert {text: statuses.get(text) for text in expected} == expected, (
        f"The instructor's release shows {statuses}; this world needs each planted comment there "
        "in the state it was put in. A broken world, not a red."
    )
    assert_the_care_record_holds(world, ids)

    body, answered = read(world, student, LATEST)
    released = released_texts(body)

    assert sorted(released) == sorted(
        (*HELD_COMMENTS[HELD_WEEK], texts["published"], texts["kept"])
    ), (
        f"Week 4's group carries {released}. Done-when 4: the published and the kept comment, "
        "beside the three canonical held ones, and nothing else."
    )
    leaked = [
        state
        for state in ("flagged", "excluded", "threat", "self_harm")
        if texts[state] in answered.text
    ]
    assert leaked == [], f"The student's page serves the {leaked} comment(s) from the batch."
