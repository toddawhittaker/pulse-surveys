"""The leadership drill-down: one section's Monday report, inside the purview, read-only.

SPEC §5.5: "Drill-down terminates at a section, rendering the Instructor Monday
Report wholesale, read-only, with a context bar." The ticket's done-when 1 to 4
and 7, read through the built application over HTTP (`docs/MISTAKES.md` entry
47), in the lead-review world: one department holding the report world's own
course (led by `lead`, sections `F` taught and `Q` untaught), a sibling course
(cohort `Y`, led by `sibling_lead`) and an unmapped course (cohort `4`), all in
one college.

**Every absence has its present twin** (`docs/MISTAKES.md` entry 3): a refusal
beside the same reader's admitted read, a held stream beside a shown one, a
`decided_by_you` that is false on the drill-down beside the same comment's true
on its decider's own report.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.instructor_decisions import EXCLUDE, KEEP
from fixtures.lead_review import Reader
from fixtures.moderation import CLEAR, HARMFUL
from fixtures.report_api import (
    COMMENT_TEXT_FIELD,
    COMMENTS_FIELD,
    DECIDED_BY_YOU_FIELD,
    FIRST_HELD_WEEK,
    FULL_WEEK,
    PAYLOAD_STREAM_KEY,
    RELEASED_MEMBER,
    SILENT_WEEK,
    SMALL_N_MEMBER,
    STREAMS_MEMBER,
    SUPPRESSED_FIELD,
    TAUGHT_COHORT,
    UNTAUGHT_COHORT,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from sqlalchemy import text

pytestmark = pytest.mark.integration

SIBLING_COHORT = "Y"
DEAN_ROLE = "DEAN"
NOT_FOUND = 404
FORBIDDEN = 403

FLAGGED_TEXT = "E9 drill-down: a harmful comment nobody has decided on yet"
KEPT_TEXT = "E9 drill-down: a harmful comment the lead kept from the review queue"
EXCLUDED_TEXT = "E9 drill-down: a clear comment the teaching instructor excluded"


def drill_down_url(section_id: Any, course_week: int) -> str:
    return f"/leadership/sections/{section_id}/weeks/{course_week}/report"


def drill_down(review: Any, reader: Reader, section_id: Any, course_week: int) -> Any:
    return review.ask("GET", drill_down_url(section_id, course_week), token=reader.token)


def a_dean(review: Any) -> Reader:
    return review.a_leader("the-dean", grants=((DEAN_ROLE, review.college),))


def a_week_in(review: Any, cohort: str) -> None:
    """One comment in the cohort's section in the full week, so the section has that week's window.

    The report world writes survey windows for a section as it plants its
    responses, so a section nothing was planted in has no published week.
    """
    review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=f"E9 drill-down: a clear comment in the cohort-{cohort} section",
        verdict=CLEAR,
        cohort=cohort,
    )


def body_of(answered: Any, what: str) -> Any:
    assert (
        answered.status_code == 200
    ), f"{what} answered {answered.status_code}. Body begins {answered.text[:400]!r}."
    return answered.json()


def comment_sets(body: Any) -> dict[str, Any]:
    """Each stream's comments, its small-N state and the release, without `decided_by_you`.

    `decided_by_you` is the reader's own relation to a comment, so it is the one
    member two readers of one report legitimately differ in; it is asserted on
    its own below.
    """

    def described(cards: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
        return sorted(
            (str(card.get(COMMENT_TEXT_FIELD)), str(card.get("status")), str(card.get("flag")))
            for card in cards
        )

    streams = body[STREAMS_MEMBER]
    found: dict[str, Any] = {}
    for stream in (INSTRUCTOR_STREAM, COURSE_STREAM):
        entry = streams[PAYLOAD_STREAM_KEY[stream]]
        found[stream] = {
            "comments": described(entry[COMMENTS_FIELD]),
            "suppressed": entry[SMALL_N_MEMBER][SUPPRESSED_FIELD],
        }
    found["released"] = described(body[RELEASED_MEMBER])
    return found


def every_card(body: Any) -> list[dict[str, Any]]:
    streams = body[STREAMS_MEMBER]
    cards = [
        card
        for stream in (INSTRUCTOR_STREAM, COURSE_STREAM)
        for card in streams[PAYLOAD_STREAM_KEY[stream]][COMMENTS_FIELD]
    ]
    return cards + list(body[RELEASED_MEMBER])


def card_with(body: Any, comment: str) -> dict[str, Any]:
    found = [card for card in every_card(body) if card.get(COMMENT_TEXT_FIELD) == comment]
    assert len(found) == 1, f"The report carries {len(found)} cards with the text {comment!r}."
    return found[0]


# ---------------------------------------------------------------------------
# Done-when 1: inside the purview only, and one refusal for the rest.
# ---------------------------------------------------------------------------


def test_a_dean_opens_a_section_of_their_college(lead_review: Any) -> None:
    """A dean reads the taught section's report, and the untaught section's, in their college."""
    review = lead_review
    dean = a_dean(review)
    for cohort in (UNTAUGHT_COHORT, SIBLING_COHORT):
        a_week_in(review, cohort)
    for cohort in (TAUGHT_COHORT, UNTAUGHT_COHORT, SIBLING_COHORT):
        section = review.world.section_id(cohort)
        body = body_of(
            drill_down(review, dean, section, FULL_WEEK),
            f"The dean's drill-down into the cohort-{cohort} section",
        )
        assert body["week"]["course_week"] == FULL_WEEK


def test_a_section_outside_the_purview_and_one_that_does_not_exist_get_one_refusal(
    lead_review: Any,
) -> None:
    """A lead opening a sibling lead's section, and a section id nothing holds: one 404, one body.

    The control is the same lead opening a section of their own course, and the
    sibling lead opening their own section.
    """
    from app.copy.instructor_report import SECTION_UNAVAILABLE

    review = lead_review
    own = review.world.section_id(TAUGHT_COHORT)
    sibling = review.world.section_id(SIBLING_COHORT)
    a_week_in(review, SIBLING_COHORT)

    body_of(drill_down(review, review.lead, own, FULL_WEEK), "The lead's own section")
    body_of(
        drill_down(review, review.sibling_lead, sibling, FULL_WEEK),
        "The sibling lead's own section",
    )

    refusals = {
        "the lead, the sibling's section": drill_down(review, review.lead, sibling, FULL_WEEK),
        "the sibling lead, the lead's section": drill_down(
            review, review.sibling_lead, own, FULL_WEEK
        ),
        "the lead, a section id nothing holds": drill_down(review, review.lead, uuid4(), FULL_WEEK),
    }
    for what, answered in refusals.items():
        assert answered.status_code == NOT_FOUND, (
            f"{what} answered {answered.status_code}; a section outside the purview and one that "
            f"does not exist are both a 404. Body {answered.text[:300]!r}."
        )
    bodies = {answered.content for answered in refusals.values()}
    assert len(bodies) == 1, f"The three refusals carry different bodies: {bodies}."
    assert refusals["the lead, a section id nothing holds"].json() == {
        "detail": SECTION_UNAVAILABLE.text
    }


def test_a_week_with_no_published_report_is_refused_with_the_weeks_sentence(
    lead_review: Any,
) -> None:
    """A course week the section never runs, inside the purview: the report's week refusal."""
    from app.copy.instructor_report import WEEK_UNAVAILABLE

    review = lead_review
    dean = a_dean(review)
    answered = drill_down(review, dean, review.world.section_id(TAUGHT_COHORT), 40)
    assert answered.status_code == NOT_FOUND
    assert answered.json() == {"detail": WEEK_UNAVAILABLE.text}


# ---------------------------------------------------------------------------
# Done-when 2: the section's own hold, unchanged.
# ---------------------------------------------------------------------------


def test_the_dean_reads_exactly_the_comments_the_instructor_reads_in_every_week(
    lead_review: Any, comment_contract: Any
) -> None:
    """A shown week, a held week and the latest week carrying a release batch, read by both.

    The same section-week read as its instructor and as the dean gives equal
    comment sets, equal small-N states and an equal release. The premises are
    asserted on the instructor's read: the full week shows comments, the held
    week shows none and says so, and the release is in the latest week only.
    """
    review = lead_review
    door = review.door
    review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=FLAGGED_TEXT,
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    door.door.refresh()
    cut = comment_contract.cut()(door.world.session)
    door.world.session.commit()
    assert int(cut) >= 1, "The cutter cut no batch, so this world has no release to compare."

    dean = a_dean(review)
    taught = review.world.section_id(TAUGHT_COHORT)
    read: dict[int, tuple[Any, Any]] = {}
    for week in (FULL_WEEK, FIRST_HELD_WEEK, SILENT_WEEK):
        mine = comment_sets(door.payload(week))
        theirs = comment_sets(body_of(drill_down(review, dean, taught, week), f"Week {week}"))
        read[week] = (mine, theirs)
        assert theirs == mine, (
            f"In course week {week} the dean's drill-down shows {theirs} and the instructor's "
            f"report shows {mine}; the drill-down renders the instructor's report wholesale."
        )

    full, _ = read[FULL_WEEK]
    held, _ = read[FIRST_HELD_WEEK]
    latest, _ = read[SILENT_WEEK]
    assert full[INSTRUCTOR_STREAM]["comments"] and not full[INSTRUCTOR_STREAM]["suppressed"]
    assert FLAGGED_TEXT in {text for text, _status, _flag in full[INSTRUCTOR_STREAM]["comments"]}
    assert held[INSTRUCTOR_STREAM]["suppressed"] is True
    assert held[INSTRUCTOR_STREAM]["comments"] == []
    assert latest["released"], "The latest published week carries no release batch."
    assert full["released"] == [] and held["released"] == []


# ---------------------------------------------------------------------------
# Done-when 3: read-only.
# ---------------------------------------------------------------------------


def test_no_comment_on_the_drill_down_is_the_readers_decision(lead_review: Any) -> None:
    """The lead keeps a queued comment; on the lead's drill-down it is not `decided_by_you`.

    The present twin: the instructor's own exclusion is `decided_by_you` on the
    instructor's report, so the member is live in this world.
    """
    review = lead_review
    door = review.door
    kept = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=KEPT_TEXT,
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    excluded = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=EXCLUDED_TEXT,
        verdict=CLEAR,
        cohort=TAUGHT_COHORT,
    )
    assert review.decide(review.lead, kept, KEEP).status_code == 204
    assert door.decide(excluded, EXCLUDE, "An unflagged exclusion needs a reason.").status_code in (
        200,
        201,
        204,
    )

    instructors = door.payload(FULL_WEEK)
    assert card_with(instructors, EXCLUDED_TEXT)[DECIDED_BY_YOU_FIELD] is True

    leads = body_of(
        drill_down(review, review.lead, review.world.section_id(TAUGHT_COHORT), FULL_WEEK),
        "The lead's drill-down",
    )
    assert card_with(leads, KEPT_TEXT), "The kept comment is not on the lead's drill-down."
    marked = [card for card in every_card(leads) if card.get(DECIDED_BY_YOU_FIELD) is not False]
    assert marked == [], f"The drill-down marks {marked} as the reader's decision."


def test_the_write_routes_refuse_the_dean_for_a_section_they_may_read(lead_review: Any) -> None:
    """The dean reads the section, and its decision, on-behalf and policy writes refuse them."""
    from app.copy.leadership_moderation import NO_REVIEW_GRANT
    from app.copy.response_loop import NO_POLICY_TO_SET, ON_BEHALF_UNAVAILABLE

    review = lead_review
    dean = a_dean(review)
    taught = review.world.section_id(TAUGHT_COHORT)
    comment = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=FLAGGED_TEXT,
        verdict=HARMFUL,
        cohort=TAUGHT_COHORT,
    )
    body_of(drill_down(review, dean, taught, FULL_WEEK), "The dean's drill-down")
    before = review.rows_of(comment)

    decided = review.decide(dean, comment, EXCLUDE)
    assert decided.status_code == FORBIDDEN
    assert decided.json() == {"detail": NO_REVIEW_GRANT.text}
    assert review.rows_of(comment) == before

    published = review.ask(
        "POST",
        f"/leadership/sections/{taught}/weeks/{FULL_WEEK}/on-behalf/response",
        token=dean.token,
        json={"text": "A response the dean may not publish.", "ai_seeded": False},
    )
    assert published.status_code == NOT_FOUND
    assert published.json() == {"detail": ON_BEHALF_UNAVAILABLE.text}

    prefix = review.session.execute(
        text("SELECT prefix_id FROM course WHERE id = :course"), {"course": review.own_course}
    ).scalar_one()
    switched = review.ask(
        "PUT", f"/leadership/response-policy/{prefix}", token=dean.token, json={"mode": "REQUIRED"}
    )
    assert switched.status_code == NOT_FOUND
    assert switched.json() == {"detail": NO_POLICY_TO_SET.text}


# ---------------------------------------------------------------------------
# Done-when 4: the seal is handed the reader.
# ---------------------------------------------------------------------------


def test_the_drill_down_hands_the_benchmark_seal_the_readers_scope(
    lead_review: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`section_benchmarks` is called with the dean's own scope, and with none for the instructor.

    What the seal does with a reader is E9-05's and tested there
    (`test_the_benchmark_seal_counts_a_leadership_reader.py`); this pins that
    the drill-down passes the reader in, and passes the instructor's report none.
    """
    from app.services import benchmarks

    review = lead_review
    dean = a_dean(review)
    real = benchmarks.section_benchmarks
    scopes: list[Any] = []

    def recording(*args: Any, **kwargs: Any) -> Any:
        scopes.append(kwargs.get("scope"))
        return real(*args, **kwargs)

    monkeypatch.setattr(benchmarks, "section_benchmarks", recording)

    review.door.payload(FULL_WEEK)
    body_of(
        drill_down(review, dean, review.world.section_id(TAUGHT_COHORT), FULL_WEEK),
        "The dean's drill-down",
    )

    assert len(scopes) == 2, f"`section_benchmarks` was called {len(scopes)} times for two reads."
    instructors, deans = scopes
    assert instructors is None, f"The instructor's report handed the seal {instructors!r}."
    assert deans is not None and str(deans.person_id) == str(
        dean.person_id
    ), f"The drill-down handed the seal {deans!r}, not the dean's scope."
    assert (
        review.world.section_id(SIBLING_COHORT) in deans.purview.section_ids
    ), "The scope handed to the seal does not hold the dean's college."
