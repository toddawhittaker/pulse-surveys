"""The hourly moderation sweep: what it asks, what it routes, and when it gives up.

SPEC §7.4 runs moderation at window close; ADR 0188 makes that an hourly sweep
over every comment in a closed window that holds no verdict. These tests drive
the sweep against the mock provider, whose markers pick the verdict or the
failure, and read the rows it leaves (`docs/MISTAKES.md` entries 30 and 49):
never the sweep's return value.

The worlds are rolled back at the end of each test, but the sweep walks every
comment it can see, including committed rows of a test running beside this one.
So every assertion is about this test's own answers, and a request is counted as
this test's only when it carries this test's text.
"""

import json
import logging
from collections.abc import Callable
from typing import Any

import pytest
from fixtures.clock import DEVELOPMENT, ENVIRONMENT_VARIABLE
from fixtures.mock_ai import (
    MOCK_AI_PROVIDER_BASE_URL_VARIABLE,
    MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE,
    Endpoint,
    MockAiProvider,
)
from fixtures.moderation import (
    CLEAR,
    FLAGGED_COLLAPSED,
    UNMODERATED,
    moderation_states,
    moderation_verdicts,
    threat_cases,
)
from fixtures.report_comments import CommentWorld, configured_threshold
from fixtures.report_views import INSTRUCTOR_STREAM
from fixtures.summary_job import StreamAwareGateway, comment_text
from fixtures.summary_job import INSTRUCTOR_STREAM as INSTRUCTOR_TOKEN
from sqlalchemy import text

pytestmark = pytest.mark.integration

CLOSED_WEEK = 7
SECOND_CLOSED_WEEK = 8
OPEN_WEEK = 9

# Nothing listens on the discard port, so a gateway pointed here gets a refused
# connection: `AIProviderUnreachableError`, an outage.
NOWHERE = "http://127.0.0.1:9/v1"

# The ADR 0188 cap, written out so the test does not agree with the constant it checks.
CAP = 6


@pytest.fixture
def gateways(
    monkeypatch: pytest.MonkeyPatch,
    care_service_environment: dict[str, str],
    mock_ai_endpoint: Endpoint,
) -> Callable[[str], Any]:
    """Build an `AIGateway` pointed at a base URL, in a development environment."""
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, DEVELOPMENT)
    monkeypatch.setenv(MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE, "mock-moderation-v1")

    def build(base_url: str) -> Any:
        from app.ai.gateway import AIGateway
        from app.config import Settings

        monkeypatch.setenv(MOCK_AI_PROVIDER_BASE_URL_VARIABLE, base_url)
        return AIGateway(settings=Settings())

    return build


@pytest.fixture
def mock_gateway(gateways: Callable[[str], Any], mock_ai_endpoint: Endpoint) -> Any:
    return gateways(mock_ai_endpoint.base_url)


def sweep(world: CommentWorld, gateway: Any) -> None:
    from app.services.moderation import sweep_unmoderated_comments

    sweep_unmoderated_comments(world.session, gateway)


def a_comment(world: CommentWorld, week: int, body: str, *, moderation: Any = UNMODERATED) -> Any:
    """One student's instructor-stream comment, and its answer id."""
    _, written = world.submit(
        term_week=week,
        comments={INSTRUCTOR_STREAM: body},
        moderation={INSTRUCTOR_STREAM: moderation},
    )
    return world.answer_key(written[INSTRUCTOR_STREAM])


def verdicts_of(world: CommentWorld, answer_id: Any) -> list[str]:
    return [row["verdict"] for row in moderation_verdicts(world.session, answer_id)]


def attempts_of(world: CommentWorld, answer_id: Any) -> int:
    return int(
        world.session.execute(
            text("SELECT count(*) FROM public.moderation_attempt WHERE answer_id = :answer"),
            {"answer": answer_id},
        ).scalar_one()
    )


def requests_carrying(endpoint: Endpoint, nonce: str) -> int:
    return sum(1 for body in endpoint.completions if nonce in json.dumps(body))


def view_answer_ids(world: CommentWorld, week: int) -> set[Any]:
    return {row["answer_id"] for row in world.view_rows(term_week=week)}


def test_a_closed_window_is_moderated_and_a_held_verdict_is_not_asked_again(
    comment_world: CommentWorld,
    mock_ai: MockAiProvider,
    mock_ai_endpoint: Endpoint,
    mock_gateway: Any,
) -> None:
    """Done-when 1: the sweep verdicts a closed window's comment, not an open one's.

    Three comments: one in a closed week with no verdict, one in an open week, and
    one in the closed week that already holds a planted verdict. After a sweep
    the first holds the mock's `harmful`, the second holds nothing (its text can
    still change), and the third still holds exactly its one planted verdict and
    was never sent. A second sweep sends nothing about any of them.
    """
    world = comment_world
    world.build()
    world.close_week(CLOSED_WEEK)
    world.open_week(OPEN_WEEK)
    harmful = mock_ai.marker_for("harmful")
    closed = a_comment(world, CLOSED_WEEK, f"E602CLOSEDQz the pace was hard {harmful}")
    still_open = a_comment(world, OPEN_WEEK, f"E602OPENQz the pace was hard {harmful}")
    held = a_comment(world, CLOSED_WEEK, "E602HELDQz already moderated", moderation=CLEAR)

    sweep(world, mock_gateway)

    assert verdicts_of(world, closed) == ["harmful"]
    assert verdicts_of(world, still_open) == []
    assert verdicts_of(world, held) == [CLEAR]
    assert requests_carrying(mock_ai_endpoint, "E602HELDQz") == 0
    assert requests_carrying(mock_ai_endpoint, "E602OPENQz") == 0
    assert requests_carrying(mock_ai_endpoint, "E602CLOSEDQz") == 1

    sweep(world, mock_gateway)

    assert requests_carrying(mock_ai_endpoint, "E602CLOSEDQz") == 1
    assert verdicts_of(world, closed) == ["harmful"]


@pytest.mark.parametrize(
    ("marker", "stored", "route"),
    [
        ("harmful", "harmful", "flag"),
        ("privacy", "privacy", "flag"),
        ("threat", "threat", "care"),
        ("self-harm", "self_harm", "care"),
        ("clear", "clear", "none"),
        ("nonsense", "nonsense", "none"),
    ],
)
def test_each_verdict_is_routed_as_its_class_requires(
    marker: str,
    stored: str,
    route: str,
    comment_world: CommentWorld,
    mock_ai: MockAiProvider,
    mock_gateway: Any,
) -> None:
    """Done-when 3: harmful and privacy flag, threat and self-harm open a case, the rest publish."""
    world = comment_world
    world.build()
    world.close_week(CLOSED_WEEK)
    answer = a_comment(world, CLOSED_WEEK, f"E602ROUTEQz {mock_ai.marker_for(marker)}")

    sweep(world, mock_gateway)

    assert verdicts_of(world, answer) == [stored]
    states = [row["state"] for row in moderation_states(world.session, answer)]
    cases = threat_cases(world.session, answer)
    if route == "flag":
        assert states == [FLAGGED_COLLAPSED] and cases == []
    elif route == "care":
        assert states == [] and len(cases) == 1
    else:
        assert states == [] and cases == []


def test_an_outage_writes_no_attempt_and_the_comment_is_moderated_once_the_provider_returns(
    comment_world: CommentWorld,
    mock_ai: MockAiProvider,
    gateways: Callable[[str], Any],
    mock_gateway: Any,
) -> None:
    """Done-when 2 and the outage half of the cap: an outage never parks a comment.

    Eight sweeps against an unreachable provider, more than the cap, leave both
    comments with no verdict, no attempt row, and out of the view; a ninth
    against the mock gives each its verdict. One of them is a self-harm
    disclosure, the comment an outage-counting cap would lose.
    """
    world = comment_world
    world.build()
    world.close_week(CLOSED_WEEK)
    ordinary = a_comment(world, CLOSED_WEEK, "E602OUTAGEAQz the lab ran long")
    disclosure = a_comment(world, CLOSED_WEEK, f"E602OUTAGEBQz {mock_ai.marker_for('self-harm')}")
    down = gateways(NOWHERE)

    for _ in range(CAP + 2):
        sweep(world, down)

    for answer in (ordinary, disclosure):
        assert verdicts_of(world, answer) == []
        assert attempts_of(world, answer) == 0
    assert not view_answer_ids(world, CLOSED_WEEK) & {ordinary, disclosure}

    sweep(world, mock_gateway)

    assert verdicts_of(world, ordinary) == [CLEAR]
    assert verdicts_of(world, disclosure) == ["self_harm"]
    assert len(threat_cases(world.session, disclosure)) == 1
    assert ordinary in view_answer_ids(world, CLOSED_WEEK)


def test_an_unavailable_answer_is_an_outage_and_counts_nothing(
    comment_world: CommentWorld, mock_ai: MockAiProvider, mock_gateway: Any
) -> None:
    """The 503 the mock answers for its unavailable marker writes no attempt, sweep after sweep."""
    world = comment_world
    world.build()
    world.close_week(CLOSED_WEEK)
    answer = a_comment(world, CLOSED_WEEK, f"E602UNAVAILQz {mock_ai.marker_for('503')}")

    for _ in range(CAP + 1):
        sweep(world, mock_gateway)

    assert verdicts_of(world, answer) == []
    assert attempts_of(world, answer) == 0


def test_six_unusable_answers_cap_the_comment_and_its_week_goes_on_without_it(
    comment_world: CommentWorld,
    mock_ai: MockAiProvider,
    mock_ai_endpoint: Endpoint,
    mock_gateway: Any,
    summary_contracts: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Done-when 4: six counted failures, then no call; held for good; the week moves on.

    Two held weeks: the first carries `threshold - 1` `clear` comments, the second
    one `clear` comment and one the mock always refuses (HTTP 500,
    `AIProviderRefusedError`). Six sweeps each append one attempt row; the
    seventh sends nothing. The capped comment then has no verdict and no
    `moderation_state` row and is absent from the view, from the release batch
    and from the summary model's input, while its week's `clear` comment is
    present in all three (entry 3's control). The cap is logged once at error
    level, by answer id, with no comment text.

    Before the cap the second week waits on the refused comment, so the cut and
    the walk skip it; at the cap they stop waiting.
    """
    from app.config import Settings
    from app.services.report_comments import cut_due_release_batches
    from app.services.reporting import generate_missing_summaries

    world = comment_world
    threshold = configured_threshold()
    world.build()
    world.close_week(CLOSED_WEEK)
    world.close_week(SECOND_CLOSED_WEEK)
    first_week = [
        a_comment(
            world, CLOSED_WEEK, comment_text(INSTRUCTOR_TOKEN, f"E602CAPA{i:02d}Qz"), moderation=CLEAR
        )
        for i in range(threshold - 1)
    ]
    beside = a_comment(
        world,
        SECOND_CLOSED_WEEK,
        comment_text(INSTRUCTOR_TOKEN, "E602BESIDEQz"),
        moderation=CLEAR,
    )
    capped = a_comment(
        world,
        SECOND_CLOSED_WEEK,
        comment_text(INSTRUCTOR_TOKEN, f"E602CAPPEDQz {mock_ai.marker_for('500')}"),
    )

    caplog.set_level(logging.WARNING, logger="app.services.moderation")
    for done in range(1, CAP + 1):
        sweep(world, mock_gateway)
        assert attempts_of(world, capped) == done
        assert requests_carrying(mock_ai_endpoint, "E602CAPPEDQz") == done

    sweep(world, mock_gateway)
    assert attempts_of(world, capped) == CAP
    assert requests_carrying(mock_ai_endpoint, "E602CAPPEDQz") == CAP

    assert verdicts_of(world, capped) == []
    assert moderation_states(world.session, capped) == []
    in_view = view_answer_ids(world, SECOND_CLOSED_WEEK)
    assert beside in in_view and capped not in in_view

    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert [str(capped) in record.getMessage() for record in errors] == [True]
    assert not any("E602CAPPEDQz" in record.getMessage() for record in caplog.records)

    assert cut_due_release_batches(world.session) == 1
    members = {
        row[0]
        for row in world.session.execute(
            text("SELECT answer_id FROM public.release_batch_member")
        ).all()
    }
    assert {*first_week, beside} <= members
    assert capped not in members

    gateway = StreamAwareGateway(summary_contracts)
    generate_missing_summaries(world.session, settings=Settings(), gateway=gateway)
    sent = "\n".join(gateway.prompts)
    assert "E602BESIDEQz" in sent
    assert "E602CAPPEDQz" not in sent
    summarized = world.session.execute(
        text("SELECT count(*) FROM public.weekly_summary WHERE week_id = :week"),
        {"week": world.week_id(SECOND_CLOSED_WEEK)},
    ).scalar_one()
    assert summarized == 2
