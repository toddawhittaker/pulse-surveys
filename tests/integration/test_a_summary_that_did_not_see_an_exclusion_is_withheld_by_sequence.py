"""A stored summary is withheld from up-chain readers when it did not see the week's latest removal.

The carried race: the on-behalf filter compared transaction-start instants, so an
exclusion whose transaction began before the summary walk and committed after the
walk's read passed as earlier, and the summary carrying the excluded comment was
served. `weekly_summary.moderation_sequence_seen` now records the highest
moderation sequence the walk could read before it gathered the comments, and the
filter compares that with the latest removal's sequence (ADR 0206).

**The interleaving is planted with two connections, not by sleeping.** The
exclusion is inserted on one connection and left open; the walk summarizes the
section-week on another and commits; then the exclusion commits. The walk's own
gather is recorded, so the test asserts that the summary was written over the
comment the exclusion removes, which is what makes it the race and not merely a
summary older than a decision.

The model is replaced at `_summary_of`, the one place the walk asks it, by a
record written here: what the summary says is not the subject, only which
comments the walk gathered and what it recorded.

Read through the leadership drill-down (over HTTP, as a dean of the college) and
through the on-behalf read's service (`on_behalf_streams`), the two up-chain
readers of a stored summary. The instructor's own report keeps the summary,
unchanged (ADR 0195), which is the present twin of each withheld read.
"""

from collections.abc import Sequence
from typing import Any

import pytest
from fixtures.instructor_decisions import AS_INSTRUCTOR, STORED_EXCLUDED
from fixtures.lead_review import Reader
from fixtures.moderation import CLEAR
from fixtures.report_api import (
    FULL_WEEK,
    PAYLOAD_STREAM_KEY,
    STREAMS_MEMBER,
    SUMMARY_FIELD,
    TAUGHT_COHORT,
    TERM_WEEK_OF_COURSE_WEEK,
)
from fixtures.report_views import INSTRUCTOR_STREAM
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

DEAN_ROLE = "DEAN"
RACED_TEXT = "E9 sequence filter: a clear comment the instructor excludes while the walk runs"
SUMMARY_TEXT = "E9 sequence filter: the week's instructor-stream summary"
REASON = "E9 sequence filter: an unflagged exclusion needs a stated reason."


def a_recorded_model(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the walk's model call with a fixed record; answer every comment it was sent."""
    from app.ai.contracts import WeeklySummaryOutput, WeeklySummaryRecord
    from app.ai.tasks import SUMMARY_PROMPT_VERSION
    from app.services import reporting

    gathered: list[str] = []

    def summary_of(
        *,
        comments: Sequence[str],
        token: str,
        response_count: int,
        small_n: bool,
        gateway: Any,
    ) -> Any:
        gathered.extend(comments)
        return WeeklySummaryRecord(
            summary=WeeklySummaryOutput(
                stream=reporting.STREAM_ASKED_ABOUT[token],
                summary=SUMMARY_TEXT,
                themes=(),
                prompt_version=SUMMARY_PROMPT_VERSION,
                model_id="e9-sequence-filter-model",
            ),
            response_count=response_count,
        )

    monkeypatch.setattr(reporting, "_summary_of", summary_of)
    return gathered


def the_week(review: Any) -> tuple[Any, Any]:
    world = review.world
    return world.section_id(TAUGHT_COHORT), world.week_id(TERM_WEEK_OF_COURSE_WEEK[FULL_WEEK])


def no_summary_yet(engine: Any, section_id: Any, week_id: Any) -> None:
    from app.models.report import WeeklySummary

    with engine.connect() as probe:
        stored = probe.execute(
            select(func.count())
            .select_from(WeeklySummary)
            .where(WeeklySummary.section_id == section_id, WeeklySummary.week_id == week_id)
        ).scalar_one()
    assert stored == 0, "The section-week already holds a summary, so the walk cannot write one."


def an_exclusion(connection: Any, review: Any, answer_id: Any) -> None:
    from app.models.report import ModerationState

    connection.execute(
        insert(ModerationState).values(
            answer_id=answer_id,
            state=STORED_EXCLUDED,
            decided_by_person_id=review.door.person_id,
            decided_as=AS_INSTRUCTOR,
            reason=REASON,
        )
    )


def the_walk(engine: Any, section_id: Any, week_id: Any) -> None:
    from app.services import reporting

    with Session(bind=engine) as walk:
        reporting._summarize_section_week(
            walk, section_id=section_id, week_id=week_id, gateway=None
        )
        walk.commit()


def instructor_summary(body: Any) -> Any:
    return body[STREAMS_MEMBER][PAYLOAD_STREAM_KEY[INSTRUCTOR_STREAM]][SUMMARY_FIELD]


def where_the_summary_reached(
    review: Any, dean: Reader, section_id: Any, week_id: Any
) -> dict[str, Any]:
    """The instructor-stream summary as the dean's drill-down, on-behalf and the instructor read it."""
    from app.services.reporting import on_behalf_streams

    drilled = review.ask(
        "GET", f"/leadership/sections/{section_id}/weeks/{FULL_WEEK}/report", token=dean.token
    )
    assert drilled.status_code == 200, f"The dean's drill-down answered {drilled.status_code}."
    review.door.door.refresh()
    on_behalf = {
        stream.stream: stream.summary_text
        for stream in on_behalf_streams(review.session, section_id=section_id, week_id=week_id)
    }
    return {
        "drill-down": instructor_summary(drilled.json()),
        "drill-down body": SUMMARY_TEXT in drilled.text,
        "on-behalf": on_behalf["instructor"],
        "instructor": instructor_summary(review.door.payload(FULL_WEEK)),
    }


def test_a_summary_written_inside_an_exclusions_transaction_is_withheld_up_chain(
    lead_review: Any, migrated_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exclusion inserts, the walk summarizes and commits, the exclusion commits: withheld.

    **The mutations this kills:** the filter left on transaction-start instants
    (the exclusion's `decided_at` is earlier than the summary's `generated_at`,
    so the summary is served); the walk recording its sequence after the commit
    or not at all; the drill-down reading the instructor's unfiltered summaries.
    """
    review = lead_review
    gathered = a_recorded_model(monkeypatch)
    comment = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=RACED_TEXT,
        verdict=CLEAR,
        cohort=TAUGHT_COHORT,
    )
    dean = review.a_leader("the-dean", grants=((DEAN_ROLE, review.college),))
    section_id, week_id = the_week(review)
    no_summary_yet(migrated_engine, section_id, week_id)

    with migrated_engine.connect() as racing:
        excluding = racing.begin()
        an_exclusion(racing, review, comment)
        the_walk(migrated_engine, section_id, week_id)
        excluding.commit()

    assert RACED_TEXT in gathered, (
        "The walk did not gather the comment being excluded, so its summary cannot carry it and "
        "this is not the race."
    )
    reached = where_the_summary_reached(review, dean, section_id, week_id)
    assert (
        reached["instructor"] is not None and reached["instructor"]["text"] == SUMMARY_TEXT
    ), f"The instructor's own report does not carry the summary: {reached['instructor']!r}."
    assert reached["drill-down"] is None and not reached["drill-down body"], (
        f"The dean's drill-down carries a summary written over a comment excluded in a racing "
        f"transaction: {reached['drill-down']!r}."
    )
    assert (
        reached["on-behalf"] is None
    ), f"The on-behalf read carries the raced summary: {reached['on-behalf']!r}."


def test_a_summary_written_after_the_exclusion_committed_is_served_up_chain(
    lead_review: Any, migrated_engine: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exclusion commits, then the walk runs: the summary saw it, left it out, and is served.

    **The mutation this kills:** a filter that withholds any summary in a week
    holding any removal, which passes the withheld case above.
    """
    review = lead_review
    gathered = a_recorded_model(monkeypatch)
    comment = review.plant(
        course_week=FULL_WEEK,
        stream=INSTRUCTOR_STREAM,
        text=RACED_TEXT,
        verdict=CLEAR,
        cohort=TAUGHT_COHORT,
    )
    dean = review.a_leader("the-dean", grants=((DEAN_ROLE, review.college),))
    section_id, week_id = the_week(review)
    no_summary_yet(migrated_engine, section_id, week_id)

    with migrated_engine.connect() as excluding, excluding.begin():
        an_exclusion(excluding, review, comment)
    the_walk(migrated_engine, section_id, week_id)

    assert (
        gathered and RACED_TEXT not in gathered
    ), "The walk gathered the excluded comment after the exclusion committed."
    reached = where_the_summary_reached(review, dean, section_id, week_id)
    assert (
        reached["drill-down"] is not None and reached["drill-down"]["text"] == SUMMARY_TEXT
    ), f"The dean's drill-down withholds a summary written after the exclusion: {reached!r}."
    assert (
        reached["on-behalf"] == SUMMARY_TEXT
    ), f"The on-behalf read withholds a summary written after the exclusion: {reached!r}."
