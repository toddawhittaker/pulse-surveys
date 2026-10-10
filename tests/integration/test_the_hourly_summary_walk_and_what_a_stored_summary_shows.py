"""The hourly summary walk after moderation, and what a stored summary may show (ADR 0188).

Three properties:

- the walk summarizes a section-week on the first pass after its last verdict
  lands, and never again;
- the empty-week sentence is the same whether a week had no comment or its only
  comment was withheld, so the sentence cannot say which;
- an ordinary-mode summary stored for a stream that is now held is not served.

The walk is driven with `StreamAwareGateway`, which records what it was sent;
the verdicts are routed by the sweep against the mock provider, never planted
(`docs/MISTAKES.md` entry 30).
"""

from typing import Any

import pytest
from fixtures.clock import DEVELOPMENT, ENVIRONMENT_VARIABLE
from fixtures.mock_ai import (
    MOCK_AI_PROVIDER_BASE_URL_VARIABLE,
    MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE,
    Endpoint,
    MockAiProvider,
)
from fixtures.moderation import CLEAR, UNMODERATED
from fixtures.report_comments import CommentWorld, configured_threshold
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.summary_job import COURSE_STREAM as COURSE_TOKEN
from fixtures.summary_job import INSTRUCTOR_STREAM as INSTRUCTOR_TOKEN
from fixtures.summary_job import StreamAwareGateway, comment_text
from sqlalchemy import text

pytestmark = pytest.mark.integration

EARLY_WEEK = 7
LATE_WEEK = 8
NO_COMMENT_WEEK = 9
WITHHELD_WEEK = 10

# The sentence an empty stream's summary carries, written out so the test does
# not agree with the constant it checks.
EMPTY_SENTENCE = "There are no comments to show for this week."


@pytest.fixture
def mock_gateway(
    monkeypatch: pytest.MonkeyPatch,
    care_service_environment: dict[str, str],
    mock_ai_endpoint: Endpoint,
) -> Any:
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, DEVELOPMENT)
    monkeypatch.setenv(MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE, "mock-moderation-v1")
    monkeypatch.setenv(MOCK_AI_PROVIDER_BASE_URL_VARIABLE, mock_ai_endpoint.base_url)
    from app.ai.gateway import AIGateway
    from app.config import Settings

    return AIGateway(settings=Settings())


def sweep(world: CommentWorld, gateway: Any) -> None:
    from app.services.moderation import sweep_unmoderated_comments

    sweep_unmoderated_comments(world.session, gateway)


def walk(world: CommentWorld, gateway: Any) -> None:
    from app.config import Settings
    from app.services.reporting import generate_missing_summaries

    generate_missing_summaries(world.session, settings=Settings(), gateway=gateway)


def summaries(world: CommentWorld, week: int) -> dict[str, tuple[str, str]]:
    """The stored rows of one section-week, by stream: (text, prompt version)."""
    return {
        str(stream): (str(summary), str(version))
        for stream, summary, version in world.session.execute(
            text(
                "SELECT stream, summary_text, prompt_version FROM public.weekly_summary "
                "WHERE section_id = :section AND week_id = :week"
            ),
            {"section": world.section_id(), "week": world.week_id(week)},
        ).all()
    }


def test_a_week_is_summarized_on_the_first_walk_after_its_last_verdict_and_never_again(
    comment_world: CommentWorld,
    mock_ai: MockAiProvider,
    mock_gateway: Any,
    summary_contracts: Any,
) -> None:
    """Done-when 5, both weeks ADR 0184's 06:00 opening asks about.

    The early week's comment is moderated before the first walk (an ordinary
    Sunday close: the 00:10 sweep, then the 00:50 walk), and that walk
    summarizes it. The late week's comment is still unmoderated at the first
    walk, so the walk leaves it; once a sweep lands its verdict, the next walk
    summarizes it. A third walk sends nothing about either week and the stored
    rows do not change.
    """
    world = comment_world
    world.build()
    world.close_week(EARLY_WEEK)
    world.close_week(LATE_WEEK)
    world.submit(
        term_week=EARLY_WEEK,
        comments={INSTRUCTOR_STREAM: comment_text(INSTRUCTOR_TOKEN, "E602EARLYQz")},
        moderation={INSTRUCTOR_STREAM: UNMODERATED},
    )
    sweep(world, mock_gateway)
    world.submit(
        term_week=LATE_WEEK,
        comments={INSTRUCTOR_STREAM: comment_text(INSTRUCTOR_TOKEN, "E602LATEQz")},
        moderation={INSTRUCTOR_STREAM: UNMODERATED},
    )

    first = StreamAwareGateway(summary_contracts)
    walk(world, first)
    assert "E602EARLYQz" in "\n".join(first.prompts)
    assert set(summaries(world, EARLY_WEEK)) == {"INSTRUCTOR", "COURSE"}
    assert summaries(world, LATE_WEEK) == {}

    sweep(world, mock_gateway)
    second = StreamAwareGateway(summary_contracts)
    walk(world, second)
    sent = "\n".join(second.prompts)
    assert "E602LATEQz" in sent and "E602EARLYQz" not in sent
    stored = {week: summaries(world, week) for week in (EARLY_WEEK, LATE_WEEK)}
    assert set(stored[LATE_WEEK]) == {"INSTRUCTOR", "COURSE"}

    third = StreamAwareGateway(summary_contracts)
    walk(world, third)
    assert not any(nonce in "\n".join(third.prompts) for nonce in ("E602EARLYQz", "E602LATEQz"))
    assert {week: summaries(world, week) for week in (EARLY_WEEK, LATE_WEEK)} == stored


def test_the_empty_week_sentence_is_the_same_for_no_comment_and_a_withheld_comment(
    comment_world: CommentWorld,
    mock_ai: MockAiProvider,
    mock_gateway: Any,
    summary_contracts: Any,
) -> None:
    """Done-when 6, side by side.

    One week whose only respondent wrote no comment; one whose only respondent
    wrote a self-harm disclosure, which the sweep routes to Care and the view
    withholds from everyone. Each stream's stored summary is the same sentence
    under the same prompt version in both weeks, and the disclosure reached no
    summary call.
    """
    world = comment_world
    world.build()
    world.close_week(NO_COMMENT_WEEK)
    world.close_week(WITHHELD_WEEK)
    world.submit(term_week=NO_COMMENT_WEEK, comments={})
    world.submit(
        term_week=WITHHELD_WEEK,
        comments={
            INSTRUCTOR_STREAM: comment_text(
                INSTRUCTOR_TOKEN, f"E602WITHHELDQz {mock_ai.marker_for('self-harm')}"
            )
        },
        moderation={INSTRUCTOR_STREAM: UNMODERATED},
    )
    sweep(world, mock_gateway)

    gateway = StreamAwareGateway(summary_contracts)
    walk(world, gateway)

    assert "E602WITHHELDQz" not in "\n".join(gateway.prompts)
    no_comment = summaries(world, NO_COMMENT_WEEK)
    withheld = summaries(world, WITHHELD_WEEK)
    assert no_comment == withheld
    assert no_comment["INSTRUCTOR"] == (EMPTY_SENTENCE, "empty-week")


def test_the_empty_week_sentence_is_the_same_for_no_comment_and_a_capped_comment(
    comment_world: CommentWorld,
    mock_ai: MockAiProvider,
    mock_gateway: Any,
    summary_contracts: Any,
) -> None:
    """Done-when 6, for the other way a week's only comment is withheld: the attempt cap.

    One week whose only respondent wrote no comment; one whose only respondent
    wrote a comment the mock always answers in the wrong shape (`malformed`, the
    unusable answer that counts toward the cap), swept six times until it reaches
    the cap and stays held with no verdict (ADR 0188). Each stream's stored
    summary is the same in both weeks, and the capped comment reached no summary
    call. The self-harm test above covers a Care-class withholding; this covers
    the held-at-the-cap one, which takes a different path through the gather.

    **The mutation it kills:** the gather counting a capped comment as a comment
    of the week, so its stream is summarized from nothing or under a sentence
    that differs from the no-comment week's (for example one saying comments are
    being held), which tells the reader that someone wrote something.
    """
    world = comment_world
    world.build()
    world.close_week(NO_COMMENT_WEEK)
    world.close_week(WITHHELD_WEEK)
    world.submit(term_week=NO_COMMENT_WEEK, comments={})
    world.submit(
        term_week=WITHHELD_WEEK,
        comments={
            INSTRUCTOR_STREAM: comment_text(
                INSTRUCTOR_TOKEN, f"E602CAPPEDONLYQz {mock_ai.marker_for('malformed')}"
            )
        },
        moderation={INSTRUCTOR_STREAM: UNMODERATED},
    )
    # Six counted failures, the ADR 0188 cap, written out rather than imported.
    for _ in range(6):
        sweep(world, mock_gateway)

    gateway = StreamAwareGateway(summary_contracts)
    walk(world, gateway)

    assert "E602CAPPEDONLYQz" not in "\n".join(gateway.prompts)
    no_comment = summaries(world, NO_COMMENT_WEEK)
    capped = summaries(world, WITHHELD_WEEK)
    assert "INSTRUCTOR" in no_comment, (
        f"The no-comment week has no stored instructor summary (it has {sorted(no_comment)}), "
        "so the comparison below would be between two empty results and prove nothing."
    )
    assert no_comment == capped
    assert no_comment["INSTRUCTOR"][0] == EMPTY_SENTENCE


def test_an_ordinary_summary_stored_for_a_stream_now_held_is_not_served(
    comment_world: CommentWorld,
) -> None:
    """Done-when 8: an old ordinary-mode row for a thin stream is withheld.

    One week: the instructor stream has one commenter (held below the
    threshold), the course stream a threshold of commenters. Both carry an
    ordinary-mode (`summary.v1`) row, as summaries written before the per-stream
    rule may. The thin stream's row is not served and the full stream's is. A
    second week's thin stream carries a small-N (`summary.v3`) row, which is
    served: the withholding is about the mode, not about thinness.
    """
    from app.models.report import WeeklySummary
    from app.services.reporting import _stored_summaries

    world = comment_world
    threshold = configured_threshold()
    world.build()
    world.close_week(EARLY_WEEK)
    world.close_week(LATE_WEEK)
    world.submit(
        term_week=EARLY_WEEK,
        comments={
            INSTRUCTOR_STREAM: comment_text(INSTRUCTOR_TOKEN, "E602THINQz"),
            COURSE_STREAM: comment_text(COURSE_TOKEN, "E602FULL00Qz"),
        },
        moderation={INSTRUCTOR_STREAM: CLEAR, COURSE_STREAM: CLEAR},
    )
    for index in range(1, threshold):
        world.submit(
            term_week=EARLY_WEEK,
            comments={COURSE_STREAM: comment_text(COURSE_TOKEN, f"E602FULL{index:02d}Qz")},
        )
    world.submit(
        term_week=LATE_WEEK,
        comments={INSTRUCTOR_STREAM: comment_text(INSTRUCTOR_TOKEN, "E602THINLATEQz")},
    )

    def stored(week: int, stream: str, version: str) -> None:
        world.session.add(
            WeeklySummary(
                section_id=world.section_id(),
                week_id=world.week_id(week),
                stream=stream,
                summary_text=f"a {version} summary of the {stream} stream",
                response_count=1,
                themes=[],
                prompt_version=version,
                model_id="a-model",
            )
        )

    stored(EARLY_WEEK, "INSTRUCTOR", "summary.v1")
    stored(EARLY_WEEK, "COURSE", "summary.v1")
    stored(LATE_WEEK, "INSTRUCTOR", "summary.v3")
    world.session.flush()

    early = _stored_summaries(
        world.session, section_id=world.section_id(), week_id=world.week_id(EARLY_WEEK)
    )
    late = _stored_summaries(
        world.session, section_id=world.section_id(), week_id=world.week_id(LATE_WEEK)
    )
    assert set(early) == {"COURSE"}
    assert set(late) == {"INSTRUCTOR"}
