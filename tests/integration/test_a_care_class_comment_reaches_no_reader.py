"""A threat or self-harm comment reaches no reader but Care — E6-01, criteria 2, 3 and 7.

SPEC §6.2: comments classified threat-of-harm or self-harm risk "are routed here
immediately and suppressed from all instructor and leadership views", and §5.2's
last bullet: they "bypass this flow entirely … and are never shown to the
instructor". E6-01 writes the first verdicts this system holds, so it is the
ticket that makes this true below the read path:

  - **criterion 2** — a comment with a threat or self-harm verdict, in a
    section-week at the threshold, is absent from the comment service's return
    and from every release batch; and this holds when a later verdict on the same
    comment is `clear`. (The gather's leg is
    `test_the_summary_job_feeds_no_moderation_held_comment_to_the_model.py`.)
  - **criterion 3** — the exit's three-response week: the routing definer opens a
    `threat_case`, and the instructor's report payload carries nothing of the
    comment. (The summary's leg is in the same module as above.)
  - **criterion 7** — the reveal door narrows: `reveal_subject_for_answer`
    refuses an answer with no Care-class verdict and still answers for one with a
    threat or self-harm verdict.

**Every absence has a present control in the same world** (`docs/MISTAKES.md`
entry 3): the comments beside the Care-class one, verdicted `clear`, are asserted
present in the same reader first.

**One case per verdict sequence**: each Care-class verdict alone, and each
followed by a later `clear` — the near miss, because "the latest verdict governs"
is the rule one table over and would publish a self-harm disclosure the moment a
re-run said `clear`.

**Marked `invariant`.** §6.2's suppression is the general form of §4.1 item 3's
read-path rule, and the reveal refusal is a refusal on the Care door.
"""

from typing import Any

import pytest
from fixtures.care_subject import (
    ACTOR_PARAMETER,
    ANSWER_PARAMETER,
    REVEAL,
    audit_rows_for,
    identity_values,
    plant_a_comment_answer,
    require_the_reveal_interface,
    the_two_hat_actor,
)
from fixtures.moderation import (
    CLEAR,
    HARMFUL,
    NONSENSE,
    PRIVACY,
    SELF_HARM,
    THREAT,
    UNMODERATED,
    plant_verdict,
    threat_cases,
)
from fixtures.report_api import (
    FIRST_HELD_WEEK,
    HELD_COMMENTS,
    INSTRUCTOR_ROLE,
    RATING_POSITION,
    SECOND_HELD_WEEK,
    SILENT_WEEK,
    TAUGHT_COHORT,
    TERM_WEEK_OF_COURSE_WEEK,
)
from fixtures.report_comments import CommentWorld, ReleaseRows
from fixtures.report_views import INSTRUCTOR_STREAM
from fixtures.submit import COMMENT_TEXT_COLUMN

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

CARE_SEQUENCES = {
    "threat": (THREAT,),
    "self-harm": (SELF_HARM,),
    "threat-then-clear": (THREAT, CLEAR),
    "self-harm-then-clear": (SELF_HARM, CLEAR),
}

THE_WEEK = 7
ANOTHER_WEEK = 8

CARE_COMMENT = "e6-01 a comment the moderator routed to Care rather than to anyone else"
BESIDE_IT = "e6-01 an ordinary comment in the same week as one routed to Care"

# Every course week of the report world, so the payload sweep walks all of them.
EVERY_COURSE_WEEK = tuple(sorted(TERM_WEEK_OF_COURSE_WEEK))

# The comment the exit's three-response week routes to Care, and the respondent the
# payload test adds so that the held set still opens all three of ADR 0152's legs
# without it — which is what gives the payload a released list to search at all.
THE_DISCLOSURE = HELD_COMMENTS[FIRST_HELD_WEEK][0]
A_LATE_HELD_COMMENT = "e6-01 held week B3: the lab notes for this week were never posted"


def texts_of(comments: Any) -> set[str]:
    return {str(comment.text) for comment in comments}


# ---------------------------------------------------------------------------
# Criterion 2 — the comment service and the release batch.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sequence", list(CARE_SEQUENCES.values()), ids=list(CARE_SEQUENCES))
def test_a_care_class_comment_is_absent_from_a_shown_week(
    sequence: tuple[str, ...], comment_world: CommentWorld, comment_contract: Any
) -> None:
    """Criterion 2, the service's return: a week at the threshold shows everything but it.

    `threshold + 1` students comment about the instructor in one closed week; one
    comment holds this case's Care-class sequence, the others `clear`. With the
    Care-class comment's author out of the count — the conservative side,
    `docs/MISTAKES.md` entry 50 — the stream still has a threshold of commenters,
    so it is shown: every `clear` comment is returned (the control), and the
    Care-class one is not.

    **The mutations this kills:** v004 without its Care-class condition (every
    case); the condition over the latest verdict only (the `-then-clear` cases);
    and a section-week rule that treated a Care-class verdict as "not moderated"
    and hid the whole week (the control fails).
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    world.build()
    world.close_week(THE_WEEK)
    beside = [f"{BESIDE_IT} ({index + 1})" for index in range(threshold)]
    for text in beside:
        world.submit(term_week=THE_WEEK, comments={INSTRUCTOR_STREAM: text})
    world.submit(
        term_week=THE_WEEK,
        comments={INSTRUCTOR_STREAM: CARE_COMMENT},
        moderation={INSTRUCTOR_STREAM: sequence},
    )
    assert world.commenters_in(term_week=THE_WEEK, stream=INSTRUCTOR_STREAM) == threshold + 1

    returned = texts_of(
        contract.visible()(
            world.session,
            section_id=world.section_id(),
            week_id=world.week_id(THE_WEEK),
            stream=INSTRUCTOR_STREAM,
        )
    )
    assert set(beside) <= returned, (
        f"The week returned {sorted(returned)}; its {threshold} `clear` comments come from "
        f"{threshold} distinct students and are shown. Until they are, the absence below is what "
        "this read gives every week."
    )
    assert CARE_COMMENT not in returned, (
        f"`{contract.visible_name}` returned a comment holding the moderation verdicts "
        f"{list(sequence)}. SPEC §6.2: suppressed from all instructor and leadership views. "
        "E6-01: never when any of its verdicts, ever, is threat or self-harm."
    )


@pytest.mark.parametrize("sequence", list(CARE_SEQUENCES.values()), ids=list(CARE_SEQUENCES))
def test_a_care_class_comment_is_never_a_release_batch_member(
    sequence: tuple[str, ...],
    comment_world: CommentWorld,
    comment_contract: Any,
    release_rows: ReleaseRows,
) -> None:
    """Criterion 2, the release batch: the held set is cut, and the Care-class comment is not in it.

    Two closed held weeks. The first holds `threshold - 1` comments, one of them
    Care-class; the second holds two `clear` ones. Without the Care-class comment
    the held set is `threshold` distinct authors over two weeks — every leg of ADR
    0152's gate open — so the cutter cuts a batch (the control), and its members
    and `released_comments` are those comments and not the Care-class one.

    **The mutations this kills:** the cutter reading held comments from `answer`
    rather than the view (the Care-class comment is a member, and a batch is never
    un-released — ADR 0146); the view's Care-class condition over the latest
    verdict only (the `-then-clear` cases).
    """
    contract = comment_contract
    world = comment_world
    threshold = contract.threshold()
    assert threshold >= 3, (
        f"The configured n-threshold is {threshold}; the first held week carries a Care-class "
        "comment beside at least one `clear` one, which needs 3 or more."
    )
    world.build()
    world.close_week(THE_WEEK)
    world.close_week(ANOTHER_WEEK)

    first = [
        world.submit(term_week=THE_WEEK, comments={INSTRUCTOR_STREAM: f"{BESIDE_IT} A{index}"})[1][
            INSTRUCTOR_STREAM
        ]
        for index in range(threshold - 2)
    ]
    _, care = world.submit(
        term_week=THE_WEEK,
        comments={INSTRUCTOR_STREAM: CARE_COMMENT},
        moderation={INSTRUCTOR_STREAM: sequence},
    )
    second = [
        world.submit(term_week=ANOTHER_WEEK, comments={INSTRUCTOR_STREAM: f"{BESIDE_IT} B{index}"})[
            1
        ][INSTRUCTOR_STREAM]
        for index in range(2)
    ]

    cut = contract.cut()(world.session)
    assert cut == 1, (
        f"`{contract.cut_name}` cut {cut} batches. Leaving the Care-class comment out, the held "
        f"comments carry {threshold} distinct authors over two closed weeks, so the gate is open "
        "and there is a batch for it to be absent from."
    )
    members = release_rows.released_answers()
    expected = {world.answer_key(answer) for answer in first + second}
    assert (
        expected <= members
    ), f"The batch is missing held `clear` comments: {sorted(expected - members)}."
    care_key = world.answer_key(care[INSTRUCTOR_STREAM])
    assert care_key not in members, (
        f"A comment holding the moderation verdicts {list(sequence)} is a release batch member. "
        "A released comment is shown in the latest published week's report for the rest of the "
        "term and cannot be un-released (ADR 0146)."
    )
    released_texts = texts_of(
        contract.released()(
            world.session,
            section_id=world.section_id(),
            term_id=world.term_id(),
            stream=INSTRUCTOR_STREAM,
        )
    )
    assert released_texts and CARE_COMMENT not in released_texts, (
        f"`{contract.released_name}` answers {sorted(released_texts)}: it must answer the released "
        "`clear` comments and never the Care-class one."
    )


# ---------------------------------------------------------------------------
# Criterion 3 — the exit's three-response week, at the payload.
# ---------------------------------------------------------------------------


def test_the_exits_three_response_week_opens_a_case_and_its_payloads_carry_nothing_of_it(
    report_door_as: Any, report_api_contract: Any, comment_contract: Any
) -> None:
    """Criterion 3: a self-harm comment in a 3-response week opens a case and reaches no payload.

    E4-07's canonical world (`tests/fixtures/report_api.py`): course week 3 holds
    three responses, each with an instructor comment — the exit's own shape. One of
    those comments is routed `self_harm` through the definer. A fourth student is
    added to the second held week, so that the held comments *without* the
    disclosure still carry a threshold of distinct authors over two weeks and the
    cutter has a release to cut.

      - **The route.** One `threat_case` row names the self-harm comment.
      - **The release (the control).** The cutter cuts one batch, and the latest
        published week's payload carries released comments — so this world's
        payloads do carry comment text, and the search below can find one.
      - **The payloads.** In every published week's report — its two streams and
        its released list, at every depth — no string contains the disclosure.

    **Built in the test body**, through the `report_door_as` factory rather than
    the `report_door` fixture, so that a red before E6-01 lands is a FAILED naming
    `route_verdict` rather than a setup ERROR (`docs/MISTAKES.md` entry 44).

    **What this does not assert, stated rather than implied.** The criterion's
    "no count" — that the week report carries no held count of any kind is
    asserted in `test_the_week_report_carries_no_held_count.py` (E6-03), and the
    empty-week sentence is E6-02's; the payload's
    `responses` figure counts the week's three *responses*, which SPEC §5.1 makes a
    count of responses rather than of comments, and this test does not pin it. The
    summary's leg is the service-side test in
    `test_the_summary_job_feeds_no_moderation_held_comment_to_the_model.py`, because
    this world runs no summary job.

    **The mutations this kills:** the cutter releasing a Care-class comment (the
    disclosure is in the released list); the report assembling comments from
    `report_comment` rather than from the service; and a definer that opens no case.
    """
    door = report_door_as(INSTRUCTOR_ROLE)
    world = door.world
    threshold = comment_contract.threshold()
    assert threshold == 5, (
        f"The configured n-threshold is {threshold}. E4-07's canonical world is built for 5: five "
        "distinct respondents behind its two held weeks, which this test brings back to five after "
        "routing one of them to Care."
    )
    assert door.rows.responses_in(FIRST_HELD_WEEK) == 3, (
        f"Course week {FIRST_HELD_WEEK} holds {door.rows.responses_in(FIRST_HELD_WEEK)} responses; "
        "the exit's week has three."
    )

    from sqlalchemy import select

    answers = world.tables["answer"]
    door.refresh()
    disclosure_key = world.session.execute(
        select(answers.c[world.key_of("answer")]).where(
            answers.c[COMMENT_TEXT_COLUMN] == THE_DISCLOSURE
        )
    ).scalar_one()
    plant_verdict(world.session, disclosure_key, SELF_HARM)
    world.submit(
        term_week=TERM_WEEK_OF_COURSE_WEEK[SECOND_HELD_WEEK],
        comments={INSTRUCTOR_STREAM: A_LATE_HELD_COMMENT},
        ratings={RATING_POSITION[INSTRUCTOR_STREAM]: 3},
        cohort=TAUGHT_COHORT,
    )
    door.commit()

    assert len(threat_cases(world.session, disclosure_key)) == 1, (
        "Routing a `self_harm` verdict opened no `threat_case` — or more than one. The definer "
        "opens exactly one, in the same call (work order decision 2)."
    )

    door.refresh()
    cut = comment_contract.cut()(world.session)
    world.session.commit()
    assert cut == 1, (
        f"The cutter cut {cut} batches. Without the disclosure, the two held weeks carry five "
        "distinct authors (two and three) — every leg open — so a release exists to search."
    )

    found_anywhere: list[tuple[int, str]] = []
    for course_week in EVERY_COURSE_WEEK:
        body, _answered = door.payload(course_week=course_week)
        for value in report_api_contract.strings_in(body):
            if THE_DISCLOSURE in value:
                found_anywhere.append((course_week, value))
        if course_week == SILENT_WEEK:
            carried = report_api_contract.member(
                body, report_api_contract.released_member, answered=_answered
            )
            assert carried, (
                "The latest published week's payload carries no released comment after a batch "
                "was cut, so this world's payloads carry no comment text and the search above "
                "proves nothing."
            )
    assert not found_anywhere, (
        f"The self-harm comment of the exit's three-response week is in the instructor's report: "
        f"{found_anywhere}. SPEC §6.2: suppressed from all instructor and leadership views."
    )


# ---------------------------------------------------------------------------
# Criterion 7 — the reveal door narrows to Care-class answers.
# ---------------------------------------------------------------------------

REFUSED_SEQUENCES = {
    "no-verdict": UNMODERATED,
    "clear": CLEAR,
    "harmful": HARMFUL,
    "privacy": PRIVACY,
    "nonsense": NONSENSE,
}
ANSWERED_SEQUENCES = {
    "threat": THREAT,
    "self-harm": SELF_HARM,
    "threat-then-clear": (THREAT, CLEAR),
}


@pytest.mark.parametrize(
    "refused_verdict", list(REFUSED_SEQUENCES.values()), ids=list(REFUSED_SEQUENCES)
)
def test_the_reveal_refuses_an_answer_with_no_care_class_verdict_and_answers_one_with(
    refused_verdict: Any,
    care_service: Any,
    committed_rows: Any,
    migrated_engine: Any,
) -> None:
    """Criterion 7, both sides with planted verdicts: no Care-class verdict, no subject.

    One Care actor, two comments: one holding a `threat` verdict (the accepted half,
    and the control — the same actor, the same call), one holding this case's
    non-Care verdict, or none. The reveal answers the first comment's author and
    refuses the second — it raises, returns no identity, and writes no audit row
    for the refused call.

    **Why it matters before E10.** The door took any answer id before E6-01, so a
    Care officer — or anybody holding the Care role's connection — could name the
    author of any comment in the system: an instructor's ordinary feedback, a
    `harmful` comment about a lecture. §6.2's reveal exists for threat and self-harm
    cases; E6-03's comment handle is safe to give an instructor because the door
    will not answer for it.

    **Whether the definer answers `NULL` or raises is not settled by the work
    order** ("refuses", same signature as v001), so the refusal is asserted at the
    service as any exception, no identity, and no audit row — which every reading of
    "refuses" produces and an answer does not.

    **The mutations this kills:** v002 not shipped (every case is answered); the
    narrowing written over flagging verdicts too (`harmful` answered); the
    narrowing over the latest verdict only (see the answered `threat-then-clear`
    case in the test below for the other side).
    """
    require_the_reveal_interface(care_service)
    reveal = getattr(care_service, REVEAL)
    actor = the_two_hat_actor(committed_rows)
    cased = plant_a_comment_answer(committed_rows, verdict=THREAT)
    uncased = plant_a_comment_answer(committed_rows, verdict=refused_verdict)

    allowed = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: cased.answer_id})
    assert identity_values(allowed) & cased.identity_values, (
        "The control failed: the Care actor could not reveal the author of a comment holding a "
        "`threat` verdict, so the refusal below is not attributable to the verdict."
    )
    audited_before = len(audit_rows_for(migrated_engine, committed_rows, actor.person))

    # Any exception, deliberately: which refusal class the door's "refuses" becomes
    # at the service — the settled `UnknownRevealSubjectError` for a NULL, or a
    # database error for a raise — is not settled by the work order. What is
    # settled is that no identity comes back, which a raise guarantees.
    with pytest.raises(Exception):  # noqa: B017
        reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: uncased.answer_id})
    audited_after = len(audit_rows_for(migrated_engine, committed_rows, actor.person))
    assert audited_after == audited_before, (
        f"A refused reveal wrote {audited_after - audited_before} audit row(s). A record of an "
        "access that did not happen is a false record."
    )


@pytest.mark.parametrize(
    "answered_verdict", list(ANSWERED_SEQUENCES.values()), ids=list(ANSWERED_SEQUENCES)
)
def test_the_reveal_still_answers_for_a_care_class_verdict(
    answered_verdict: Any, care_service: Any, committed_rows: Any
) -> None:
    """Criterion 7's other side: a threat or self-harm verdict is still a case Care can act on.

    Including `threat` followed by a later `clear`: v004 never shows that comment
    (its verdicts, ever, include `threat`), so Care is the only reader it has, and
    a door that refused it would leave a student at risk read by nobody.

    **The mutations this kills:** v002 refusing everything (a wall satisfies every
    refusal above); `self_harm` left out of the Care-class set; the narrowing over
    the latest verdict only (the `threat-then-clear` case is refused).
    """
    require_the_reveal_interface(care_service)
    reveal = getattr(care_service, REVEAL)
    actor = the_two_hat_actor(committed_rows)
    planted = plant_a_comment_answer(committed_rows, verdict=answered_verdict)

    revealed = reveal(**{ACTOR_PARAMETER: actor.person, ANSWER_PARAMETER: planted.answer_id})
    assert planted.identity_name in identity_values(revealed), (
        f"The reveal answered {revealed!r} for a comment holding {answered_verdict!r}; its author "
        f"was seeded as {sorted(planted.identity_values)}. §6.2's door exists for exactly this "
        "comment."
    )
