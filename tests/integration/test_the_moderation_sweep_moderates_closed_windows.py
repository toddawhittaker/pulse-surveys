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

import contextlib
import json
import logging
import threading
from collections.abc import Callable, Iterator
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import import_module
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
    moderation_service,
    moderation_states,
    moderation_verdicts,
    threat_cases,
)
from fixtures.report_comments import CommentWorld, configured_threshold
from fixtures.report_views import INSTRUCTOR_STREAM
from fixtures.summary_job import INSTRUCTOR_STREAM as INSTRUCTOR_TOKEN
from fixtures.summary_job import StreamAwareGateway, comment_text
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

# The smallest step a `timestamptz` holds.
ONE_TICK = timedelta(microseconds=1)

# Where the app clock lives (ADR 0109). E6-01's boundary tests stand it on an
# instant through this module and through `app.services.moderation`, in case that
# module bound the name itself; the same seam is used here.
CLOCK_MODULE = "app.services.clock"


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
    """Done-when 3: harmful and privacy flag, threat and self-harm open a case, the rest publish.

    "Publishes it" is asserted as the comment reaching the comment view, not only
    as the absence of a flag and a case: a sweep that wrote the `clear` or
    `nonsense` verdict but left the comment out of the read would otherwise pass.
    **The mutation it kills:** routing `nonsense` (or `clear`) to a held outcome
    that writes no `moderation_state` row and opens no case, so the comment is
    silently never shown.
    """
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
        assert answer in view_answer_ids(world, CLOSED_WEEK), (
            f"The sweep routed a {stored!r} verdict, which publishes the comment, but the "
            "comment is not in its closed week's comment view."
        )


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
    one `clear` comment and one the mock always answers in the wrong shape (its
    `malformed` marker, `AIResponseInvalidError` once the gateway's one re-ask
    fails too). Only an unusable answer counts toward the cap (PR #293's fix
    round); a refusal or an outage counts nothing and has its own test below.
    Six sweeps each append one attempt row and each asks the provider again; the
    seventh sends nothing. Requests are compared sweep to sweep rather than
    counted, because how many requests one call makes is the gateway's re-ask
    rule (ADR 0053), not this ticket's. The capped comment then has no verdict and no
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
            world,
            CLOSED_WEEK,
            comment_text(INSTRUCTOR_TOKEN, f"E602CAPA{i:02d}Qz"),
            moderation=CLEAR,
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
        comment_text(INSTRUCTOR_TOKEN, f"E602CAPPEDQz {mock_ai.marker_for('malformed')}"),
    )

    caplog.set_level(logging.WARNING, logger="app.services.moderation")
    asked = 0
    for done in range(1, CAP + 1):
        sweep(world, mock_gateway)
        assert attempts_of(world, capped) == done
        now_asked = requests_carrying(mock_ai_endpoint, "E602CAPPEDQz")
        assert now_asked > asked, f"Sweep {done} did not ask the provider about the comment."
        asked = now_asked

    sweep(world, mock_gateway)
    assert attempts_of(world, capped) == CAP
    assert (
        requests_carrying(mock_ai_endpoint, "E602CAPPEDQz") == asked
    ), f"The seventh sweep asked the provider about a comment already at the cap of {CAP}."

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


def test_a_comment_below_the_cap_still_holds_its_weeks_summary(
    comment_world: CommentWorld,
    mock_ai: MockAiProvider,
    mock_gateway: Any,
    summary_contracts: Any,
) -> None:
    """Done-when 4's other half: the walk waits until the sixth failure, not before.

    One closed week holds a planted `clear` comment (the control the walk must
    eventually summarize) and one comment the mock always answers in the wrong
    shape (`malformed`, the unusable answer that counts toward the cap). After each of
    the first five sweeps a summary walk writes no row for the week, because the
    refused comment is neither verdicted nor at the cap. After the sixth sweep
    the walk summarizes the week, with the control and without the refused one.

    The test above checks only the state after the cap, so it cannot tell where
    the gate draws its line. **The mutations it kills:** the gate counting a
    comment as resolved below six attempt rows (`>= 1`, or the off-by-one
    `>= 5`); and the gather not waiting on an unverdicted comment at all.
    """
    from app.config import Settings
    from app.services.reporting import generate_missing_summaries

    world = comment_world
    world.build()
    world.close_week(CLOSED_WEEK)
    a_comment(
        world,
        CLOSED_WEEK,
        comment_text(INSTRUCTOR_TOKEN, "E602WAITBESIDEQz"),
        moderation=CLEAR,
    )
    refused = a_comment(
        world,
        CLOSED_WEEK,
        comment_text(INSTRUCTOR_TOKEN, f"E602WAITREFUSEDQz {mock_ai.marker_for('malformed')}"),
    )

    def walk() -> str:
        gateway = StreamAwareGateway(summary_contracts)
        generate_missing_summaries(world.session, settings=Settings(), gateway=gateway)
        return "\n".join(gateway.prompts)

    def stored_rows() -> int:
        return int(
            world.session.execute(
                text(
                    "SELECT count(*) FROM public.weekly_summary "
                    "WHERE section_id = :section AND week_id = :week"
                ),
                {"section": world.section_id(), "week": world.week_id(CLOSED_WEEK)},
            ).scalar_one()
        )

    for done in range(1, CAP):
        sweep(world, mock_gateway)
        assert attempts_of(world, refused) == done
        sent = walk()
        assert stored_rows() == 0, (
            f"The week was summarized after {done} failed moderation call(s) on one of its "
            f"comments. The walk waits until every comment holds a verdict or has reached the "
            f"cap of {CAP} failed calls; below the cap the comment may still be moderated."
        )
        assert "E602WAITBESIDEQz" not in sent

    sweep(world, mock_gateway)
    assert attempts_of(world, refused) == CAP
    sent = walk()
    assert stored_rows() > 0, (
        f"The refused comment reached the cap of {CAP} failed calls, but the walk still did not "
        "summarize its week. At the cap the gather stops waiting on it."
    )
    assert "E602WAITBESIDEQz" in sent
    assert "E602WAITREFUSEDQz" not in sent


# ---------------------------------------------------------------------------
# PR #293's fix round: what counts toward the cap, overlapping sweeps, a commit
# per comment, and the instant a window counts as closed for the sweep.
# ---------------------------------------------------------------------------


class StubProvider:
    """A provider on a local port that answers every request with one HTTP status.

    The mock's markers live in the comment text, so a comment marked to be refused
    is refused for ever and a test cannot then watch the provider recover. This
    stub answers whatever it is asked with `status`, so a gateway pointed at it
    and then at the mock is the same comment meeting a refusing provider and then
    a healthy one. With `hold`, each request waits until `release` is set, which is
    how a test keeps one sweep inside its provider call while another starts.

    It records each request body, so a test counts only the requests carrying
    its own text.
    """

    def __init__(self, status: int, *, hold: bool = False) -> None:
        self.status = status
        self.bodies: list[str] = []
        self.arrived = threading.Event()
        self.release = threading.Event()
        if not hold:
            self.release.set()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - the name `http.server` dispatches to
                length = int(self.headers.get("Content-Length") or 0)
                stub.bodies.append(self.rfile.read(length).decode("utf-8", "replace"))
                stub.arrived.set()
                stub.release.wait(timeout=60)
                payload = json.dumps(
                    {"error": {"message": "stub provider", "type": "stub", "code": None}}
                ).encode()
                # A client that gave up waiting has closed the socket; nothing is left to answer.
                with contextlib.suppress(OSError):
                    self.send_response(stub.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)

            def log_message(self, *_args: Any) -> None:
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def carrying(self, nonce: str) -> int:
        return sum(1 for body in self.bodies if nonce in body)

    def close(self) -> None:
        self.release.set()
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub_providers() -> Iterator[Callable[..., StubProvider]]:
    made: list[StubProvider] = []

    def make(status: int, *, hold: bool = False) -> StubProvider:
        stub = StubProvider(status, hold=hold)
        made.append(stub)
        return stub

    yield make
    for stub in made:
        stub.close()


@pytest.fixture
def own_connections(migrated_engine: Any) -> Iterator[Any]:
    """An engine whose connections really close, for sessions the sweep runs on by itself.

    `NullPool`, because a Postgres session-level advisory lock belongs to the
    server connection: a pooled connection handed back and out again would carry
    a lock its last user never released, and a re-entrant `pg_try_advisory_lock`
    on the same connection succeeds, which would hide exactly that.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    engine = create_engine(migrated_engine.url, poolclass=NullPool)
    yield engine
    engine.dispose()


def a_sweep_session(engine: Any) -> Any:
    """A session on its own server connection, stating the environment as `db_session` does."""
    from sqlalchemy.orm import Session

    from app.config import DEVELOPMENT_ENVIRONMENT

    return Session(bind=engine.connect(), info={"environment": DEVELOPMENT_ENVIRONMENT})


def close_sweep_session(session: Any) -> None:
    connection = session.get_bind()
    session.close()
    connection.close()


def committed_state(engine: Any, answer_ids: list[Any]) -> dict[str, Any]:
    """Verdicts, attempt rows and Care cases for `answer_ids`, read on a fresh connection.

    Only what was committed is visible here, which is the point: a row written and
    then rolled back is not in this answer.
    """
    from sqlalchemy.orm import Session

    with Session(engine) as fresh:
        return {
            str(answer): {
                "verdicts": [row["verdict"] for row in moderation_verdicts(fresh, answer)],
                "attempts": int(
                    fresh.execute(
                        text(
                            "SELECT count(*) FROM public.moderation_attempt "
                            "WHERE answer_id = :answer"
                        ),
                        {"answer": answer},
                    ).scalar_one()
                ),
                "cases": len(threat_cases(fresh, answer)),
            }
            for answer in answer_ids
        }


def stand_the_clock_at(monkeypatch: pytest.MonkeyPatch, instant: Any) -> None:
    """Make the app clock answer `instant`, the way E6-01's boundary tests do."""

    def fixed(*_args: Any, **_kwargs: Any) -> Any:
        return instant

    monkeypatch.setattr(import_module(CLOCK_MODULE), "now", fixed)
    monkeypatch.setattr(moderation_service(), "now", fixed, raising=False)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422, 429, 500])
def test_a_refusing_provider_writes_no_attempt_and_strands_no_comment(
    status: int,
    comment_world: CommentWorld,
    mock_ai: MockAiProvider,
    gateways: Callable[[str], Any],
    mock_gateway: Any,
    stub_providers: Callable[..., StubProvider],
) -> None:
    """No HTTP status counts toward the cap: every refusal is retried like an outage.

    PR #293's fix round: `AIProviderRefusedError` (HTTP 401, 429, 500) writes no
    `moderation_attempt` row. E6-05 then counted 413 and 422; E6-08 (done-when 2)
    takes that back, because either can come back on every request (a self-hosted
    endpoint answers 422 to a parameter it rejects, a proxy with a low body limit
    answers 413 to most prompts), and counting them would cap every comment within
    six sweeps and release every week with no threat or self-harm check. Only an
    answer that came back and was unusable counts (the cap test above). 400 was
    moved here by PR #296's fix round for the same reason, and 403 and 404 because
    a fix that counted "every 4xx" is the natural near miss. Seven sweeps against
    a provider answering `status` to everything, one more than the cap, each ask
    about both comments and leave neither an attempt row nor a verdict. One sweep
    against the healthy mock then gives each its verdict, and the self-harm
    disclosure its Care case.

    **The mutation it kills:** a refusal counted toward the cap, which after six
    sweeps parks the comment for good, and a self-harm disclosure parked that way
    reaches nobody. In particular, 413 or 422 still in a counting set reds that
    case, and so does a gateway that turns either status into the unusable-answer
    error. **Near misses:** counting only some refusal statuses (one case per
    status, so a fix that dropped 422 alone still reds on 413); and a sweep that
    stops asking after some refusals without writing a row (the request count must
    rise on every sweep, and the last sweep must verdict both).
    """
    world = comment_world
    world.build()
    world.close_week(CLOSED_WEEK)
    ordinary = a_comment(world, CLOSED_WEEK, "E602REFUSEDAQz the lab ran long")
    disclosure = a_comment(world, CLOSED_WEEK, f"E602REFUSEDBQz {mock_ai.marker_for('self-harm')}")
    refusing = stub_providers(status)
    refused = gateways(refusing.base_url)

    asked = {"E602REFUSEDAQz": 0, "E602REFUSEDBQz": 0}
    for number in range(1, CAP + 2):
        sweep(world, refused)
        for nonce, before in asked.items():
            now_asked = refusing.carrying(nonce)
            assert now_asked > before, (
                f"Sweep {number} did not ask the refusing provider about {nonce}. A refused "
                "comment is retried by the next sweep, however many refusals came before."
            )
            asked[nonce] = now_asked
        for answer in (ordinary, disclosure):
            assert attempts_of(world, answer) == 0, (
                f"After {number} sweep(s) against a provider answering HTTP {status}, the comment "
                f"has {attempts_of(world, answer)} attempt row(s). Only an unusable answer "
                "counts toward the cap; a refusal is retried next hour and counts nothing."
            )
    for answer in (ordinary, disclosure):
        assert verdicts_of(world, answer) == []

    sweep(world, mock_gateway)

    assert verdicts_of(world, ordinary) == [CLEAR]
    assert verdicts_of(world, disclosure) == ["self_harm"], (
        f"After {CAP + 1} refused sweeps the provider recovered, and the self-harm disclosure "
        "still holds no verdict. A refusal must never park a comment."
    )
    assert len(threat_cases(world.session, disclosure)) == 1


class RecordsRefusals:
    """The real gateway, recording every `AIProviderRefusedError` it raises on the way out.

    Answers `run_task` and `run_task_with_usage`, the two entry points
    `FailsOnItsSecondCall` above answers; anything else is passed through. The
    error is re-raised untouched, so the sweep sees exactly what it would have.
    """

    def __init__(self, real: Any, refused: type[BaseException]) -> None:
        self.real = real
        self.refused = refused
        self.raised: list[BaseException] = []

    def _call(self, name: str, kwargs: dict[str, Any]) -> Any:
        try:
            return getattr(self.real, name)(**kwargs)
        except self.refused as error:
            self.raised.append(error)
            raise

    def run_task(self, **kwargs: Any) -> Any:
        return self._call("run_task", kwargs)

    def run_task_with_usage(self, **kwargs: Any) -> Any:
        return self._call("run_task_with_usage", kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.real, name)


@pytest.mark.parametrize("status", [422, 429])
def test_a_refusal_carries_the_http_status_the_provider_answered(
    status: int,
    comment_world: CommentWorld,
    gateways: Callable[[str], Any],
    stub_providers: Callable[..., StubProvider],
) -> None:
    """E6-05 decision 5b: `AIProviderRefusedError` carries its HTTP status as `status: int`.

    E6-05 added the status so the sweep could split refusals by it. Since E6-08 no
    status counts toward the cap, so the cap does not depend on it; the error
    still carries it, and this test keeps that contract. **The mutation this
    kills:** the status left off the error, or set to a constant. **The near
    miss:** the status carried as a string, since `"422"` is not `422`.
    """
    from app.ai.gateway import AIProviderRefusedError

    world = comment_world
    world.build()
    world.close_week(CLOSED_WEEK)
    a_comment(world, CLOSED_WEEK, f"E605STATUS{status}Qz the lab ran long")
    gateway = RecordsRefusals(gateways(stub_providers(status).base_url), AIProviderRefusedError)

    sweep(world, gateway)

    assert gateway.raised, (
        f"The gateway raised no `AIProviderRefusedError` against a provider answering HTTP "
        f"{status}, so this test measured nothing."
    )
    carried = [getattr(error, "status", None) for error in gateway.raised]
    assert all(type(value) is int and value == status for value in carried), (
        f"The refusals carried `status` {carried!r} for a provider answering HTTP {status}. "
        "Decision 5b: the error carries its HTTP status as an int."
    )


def test_a_sweep_that_starts_while_another_runs_asks_nothing_and_writes_nothing(
    committed_comment_world: CommentWorld,
    committed_rows: Any,
    own_connections: Any,
    gateways: Callable[[str], Any],
    mock_gateway: Any,
    mock_ai_endpoint: Endpoint,
    stub_providers: Callable[..., StubProvider],
) -> None:
    """Sweeps never overlap: a second run while the first holds the lock does nothing.

    The world is committed, so two sweeps on two server connections both see the
    comment. The first sweep runs in a thread against a provider that holds its
    request open, so it is mid-run, holding whatever it holds. A second sweep
    then runs against the healthy mock: it must send no request about the comment
    and leave no verdict and no attempt row. The held provider is then released,
    the first sweep finishes, and a third sweep, on the second sweep's connection,
    moderates the comment.

    No lock key is named here. The test drives two real runs into each other,
    which is the property, rather than holding a key it would have to copy.

    **The mutations it kills:** no lock (the second sweep asks the mock and routes
    `clear`); a lock taken per transaction rather than per run, released at the
    first per-comment commit (same red, once the first sweep has committed
    anything). **The near miss:** a lock never released, or released only on the
    success path. The third sweep runs on a different server connection from the
    first, so a lock left behind on the first connection refuses it and the
    comment stays unmoderated. A pooled connection would hide this, which is why
    the sessions here sit on `NullPool` connections of their own.
    """
    from app.services.moderation import sweep_unmoderated_comments

    world = committed_comment_world
    world.build()
    world.close_week(CLOSED_WEEK)
    answer = a_comment(world, CLOSED_WEEK, "E602OVERLAPQz the lab ran long")
    committed_rows.commit()

    holding = stub_providers(503, hold=True)
    held = gateways(holding.base_url)
    first = a_sweep_session(own_connections)
    second = a_sweep_session(own_connections)
    failures: list[BaseException] = []

    def run_the_first() -> None:
        try:
            sweep_unmoderated_comments(first, held)
        except BaseException as failure:  # reported by the main thread
            failures.append(failure)

    runner = threading.Thread(target=run_the_first, daemon=True)
    try:
        runner.start()
        try:
            assert holding.arrived.wait(timeout=30), (
                "The first sweep never asked the held provider, so nothing was held while the "
                "second sweep ran and this test measured nothing."
            )
            sweep_unmoderated_comments(second, mock_gateway)
            still_running = runner.is_alive()
            asked = requests_carrying(mock_ai_endpoint, "E602OVERLAPQz")
            during = committed_state(own_connections, [answer])[str(answer)]
        finally:
            holding.release.set()
            runner.join(timeout=60)

        assert still_running, (
            "The first sweep had already finished when the second one returned, so the two did "
            "not overlap and this run measured nothing (the gateway may have timed out first)."
        )
        assert asked == 0 and during == {"verdicts": [], "attempts": 0, "cases": 0}, (
            f"A sweep started while another was running sent {asked} request(s) about the "
            f"comment and left {during}. The second run must find the first one's lock taken and "
            "touch nothing: two runs at once ask twice and route twice."
        )
        assert not runner.is_alive(), "The first sweep did not finish after its provider answered."
        assert failures == [], f"The first sweep raised: {failures!r}"

        sweep_unmoderated_comments(second, mock_gateway)
        after = committed_state(own_connections, [answer])[str(answer)]
        assert after["verdicts"] == [CLEAR], (
            f"Once the first sweep had finished, a new sweep on another connection left {after}. "
            "The first run's lock was not released, so every later run would do nothing."
        )
    finally:
        close_sweep_session(first)
        close_sweep_session(second)


class UnexpectedFailureError(RuntimeError):
    """Not one of the gateway's error classes: what a bug raises, not what a provider does."""


class FailsOnItsSecondCall:
    """The real gateway, except that the second call carrying `nonce` raises `UnexpectedFailureError`.

    Answers `run_task` and `run_task_with_usage`, the two entry points the
    repository's gateway doubles already answer; anything else is passed to the
    real gateway. `raised` says whether the failure fired, so a sweep that never
    reached a second call cannot pass for one that survived it.
    """

    def __init__(self, real: Any, nonce: str) -> None:
        self.real = real
        self.nonce = nonce
        self.carrying = 0
        self.raised = False

    def _count(self, kwargs: dict[str, Any]) -> None:
        if self.nonce in repr(kwargs):
            self.carrying += 1
            if self.carrying == 2:
                self.raised = True
                raise UnexpectedFailureError("an error that is not a gateway error")

    def run_task(self, **kwargs: Any) -> Any:
        self._count(kwargs)
        return self.real.run_task(**kwargs)

    def run_task_with_usage(self, **kwargs: Any) -> Any:
        self._count(kwargs)
        return self.real.run_task_with_usage(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.real, name)


def test_a_care_route_committed_before_a_later_failure_survives_it(
    committed_comment_world: CommentWorld,
    committed_rows: Any,
    own_connections: Any,
    mock_ai: MockAiProvider,
    mock_gateway: Any,
) -> None:
    """A verdict and its route are committed before the next comment is asked about.

    Two comments, both self-harm disclosures, so whichever the sweep asks about
    first is routed to Care. The second call about them raises an error that is
    not a gateway class. Whatever the sweep then does with that error, the first
    comment's verdict and its `threat_case` must be in the database, read on a
    fresh connection after the sweep's session has rolled back what it had not
    committed.

    Both comments carry the same marker so the test does not depend on the order
    the sweep walks them in, which the ticket leaves open.

    **The mutation it kills:** one commit at the end of the sweep (the error
    rolls back the first comment's Care route, and the disclosure is left with
    no case and no verdict, to be asked about again next hour, if the error is
    not there again). **Near miss:** a commit after every *second* comment, or
    after the loop's first full pass only (same red: nothing is committed before
    the second call).
    """
    from app.services.moderation import sweep_unmoderated_comments

    world = committed_comment_world
    world.build()
    world.close_week(CLOSED_WEEK)
    marker = mock_ai.marker_for("self-harm")
    first = a_comment(world, CLOSED_WEEK, f"E602COMMITAQz {marker}")
    second = a_comment(world, CLOSED_WEEK, f"E602COMMITBQz {marker}")
    committed_rows.commit()

    gateway = FailsOnItsSecondCall(mock_gateway, "E602COMMIT")
    session = a_sweep_session(own_connections)
    try:
        # Whether the sweep lets the error out or carries on is not this test's subject.
        with contextlib.suppress(UnexpectedFailureError):
            sweep_unmoderated_comments(session, gateway)
        session.rollback()
    finally:
        close_sweep_session(session)

    assert gateway.raised, (
        f"The sweep made {gateway.carrying} call(s) about this test's two comments through "
        "`run_task` or `run_task_with_usage`, so the injected failure never fired and this test "
        "measured nothing."
    )
    state = committed_state(own_connections, [first, second])
    routed = [row for row in state.values() if row["verdicts"] == ["self_harm"]]
    assert len(routed) == 1 and routed[0]["cases"] == 1, (
        f"After an unexpected error on the second comment, the committed rows are {state}. The "
        "first comment's self-harm verdict and its Care case were routed before the error and "
        "must have been committed then; a sweep that commits once at the end loses them."
    )


def test_a_window_closing_at_the_clocks_instant_is_not_swept_and_one_tick_later_it_is(
    comment_world: CommentWorld,
    mock_gateway: Any,
    mock_ai_endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closed, for the sweep, means `closes_at < now`: the boundary pair.

    Two comments: one in a week whose window closes at instant T, one in a later
    closed week. With the app clock stood at T exactly, a sweep leaves both alone.
    With the clock one microsecond later, a sweep moderates the first and still
    leaves the later week alone.

    **The later week is the seam's control.** Its window closes a week after T,
    so by the stood clock it is open at both readings. If the sweep read some
    clock other than the app clock (the real one says 2026, and this window
    closed in 2020), it would be swept at the first reading, and that assertion
    comes first so a missed seam is named as a broken test, not as a wrong
    boundary.

    **The mutation it kills:** the selection written `closes_at <= now` (the
    first comment is swept at T). **Near miss:** `closes_at < now - something`,
    a grace that waits longer than one tick (the first comment is not swept at
    T plus one tick). The ticket's route check (E6-01) counts `now == closes_at`
    as closed; the sweep deliberately waits one tick more.
    """
    world = comment_world
    world.build()
    world.close_week(CLOSED_WEEK)
    world.close_week(SECOND_CLOSED_WEEK)
    at_close = a_comment(world, CLOSED_WEEK, "E602BOUNDARYQz the lab ran long")
    later = a_comment(world, SECOND_CLOSED_WEEK, "E602LATERWEEKQz the lab ran long")
    closes_at = world.instants[CLOSED_WEEK][1]
    assert world.instants[SECOND_CLOSED_WEEK][1] > closes_at + ONE_TICK

    stand_the_clock_at(monkeypatch, closes_at)
    sweep(world, mock_gateway)

    assert (
        verdicts_of(world, later) == []
        and requests_carrying(mock_ai_endpoint, "E602LATERWEEKQz") == 0
    ), (
        "A window that closes a week after the stood clock was swept, so the sweep is not "
        "reading the app clock this test stood. The test is broken, not red: fix the seam "
        "before reading the boundary assertion below."
    )
    assert (
        verdicts_of(world, at_close) == []
        and requests_carrying(mock_ai_endpoint, "E602BOUNDARYQz") == 0
    ), (
        "With the app clock at the window's `closes_at` exactly, the sweep asked about its "
        "comment. The fix round settles the sweep's selection as `closes_at < now`."
    )

    stand_the_clock_at(monkeypatch, closes_at + ONE_TICK)
    sweep(world, mock_gateway)

    assert verdicts_of(world, at_close) == [
        CLEAR
    ], "One microsecond after the window's `closes_at`, the sweep did not moderate its comment."
    assert verdicts_of(world, later) == []
