"""Which of the two provider triples a gateway actually reads — ticket E2-12.

The configuration split ruled on 2026-09-02 describes two providers —
`AI_PROVIDER_{API_KEY,BASE_URL,MODEL_NAME}` for the real one and
`MOCK_AI_PROVIDER_{API_KEY,BASE_URL,MODEL_NAME}` for the in-repo mock — and
settles selection with one construction flag:

- `AIGateway(live=True)` reads the **real** triple in every environment;
- `AIGateway(live=False)` reads the **mock** triple in development and test, and
  the **real** triple in a deployment.

`tests/unit/test_ai_provider_configuration.py` can see the *rules* that hang off
those names — which base URL the catalog refuses, which keys are masked — and it
says in its own docstring that it cannot see the selection, because nothing there
builds a gateway. This module is that missing half, and the whole of it is one
question asked five ways: **the request came out somewhere, and where?**

**Two endpoints, both on the loopback interface, and the answer is which of them
was called.** Each is an OpenAI-compatible stub that records what it received; one
stands for the real provider and one for the mock. Nothing here reads an attribute
off a `Settings` or a gateway, because the property is behavioural and an
attribute is a spelling: a gateway holding `ai_provider_base_url` and posting to
the other endpoint would satisfy an attribute check perfectly.

**Three facts per case, not one, and that is the near miss.** Asserting only which
endpoint received the request passes a gateway that took the base URL from one
triple and the key and model from the other — which is worse than reading the
wrong triple outright: the request lands at the paid provider carrying the mock's
model identifier, gets refused or answers as some other model, and ADR 0031's
audit pair records a model that never ran. So each case asserts the endpoint, the
model name in the request body, and the credential in the `Authorization` header,
and every one of those three differs between the sides.

**Red until the split lands.** `AIGateway` takes no `live` parameter today, so
these fail on a missing keyword rather than on a wrong endpoint.

**On "test" as an environment.** The ruling says the mock triple is read "in
development and test". `app.config` defines exactly one non-deployment
environment constant today, and this module parametrises over that one rather
than inventing a second name. If a `test` value lands, it belongs in
`NON_DEPLOYMENT_ENVIRONMENTS` below, beside the control that holds the literal
against `app.config`.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import ModuleType
from typing import Any

import pytest

GATEWAY_MODULE = "app.ai.gateway"
TASKS_MODULE = "app.ai.tasks"
GATEWAY_CLASS = "AIGateway"
LIVE_FLAG = "live"

# The task the eval runner calls, and the one call in this repository that takes a
# gateway as an argument. It writes no row and needs no session, which is why this
# module is a unit test with no database behind it.
VALIDITY_TASK = "verdict_for_comment"

# The two triples, spelled out because this module's whole subject is which of
# them is read. Nothing is discovered here — a test that found the variables would
# agree with a gateway that had collapsed the two triples into one.
REAL_BASE_URL_VARIABLE = "AI_PROVIDER_BASE_URL"
REAL_MODEL_NAME_VARIABLE = "AI_PROVIDER_MODEL_NAME"
REAL_KEY_VARIABLE = "AI_PROVIDER_API_KEY"

MOCK_BASE_URL_VARIABLE = "MOCK_AI_PROVIDER_BASE_URL"
MOCK_MODEL_NAME_VARIABLE = "MOCK_AI_PROVIDER_MODEL_NAME"
MOCK_KEY_VARIABLE = "MOCK_AI_PROVIDER_API_KEY"

REAL_SIDE = "the real provider"
MOCK_SIDE = "the in-repo mock"

# Distinctive per side, and distinct in all three positions. The model names and
# the credentials differ as well as the addresses, because a gateway that mixed
# the triples would still reach one of the two endpoints and only the other two
# facts would say so.
#
# Nothing here resembles a real credential and nothing was copied from a working
# `.env` (CLAUDE.md, secrets). Named `...CREDENTIAL` rather than `...KEY` so
# ruff's S105 keeps flagging the real thing, exactly as
# `tests/unit/test_config_settings.py` does.
REAL_MODEL_NAME = "e2-12-real-triple-model-Qv7Zm"
MOCK_MODEL_NAME = "e2-12-mock-triple-model-Tf2Yc"
REAL_CREDENTIAL = "e2-12-real-triple-Kj3PxE8mZt5UwGh"
MOCK_CREDENTIAL = "e2-12-mock-triple-Rb9NsWqvZmXt4Ld"

ENVIRONMENT_VARIABLE = "ENVIRONMENT"

# Spelled as literals because parametrisation needs its values at collection time,
# and importing `app.config` there turns a missing module into a collection error
# rather than a red. `test_the_development_literal_is_the_one_app_config_names`
# below is what holds the first against its one definition site — the same control,
# for the same reason, as `tests/unit/test_ai_provider_configuration.py`'s.
DEVELOPMENT = "development"
NON_DEPLOYMENT_ENVIRONMENTS = (DEVELOPMENT,)
DEPLOYMENT_ENVIRONMENTS = ("production", "staging")

# A comment with nothing marker-like in it. ADR 0113 makes `mock-ai:` a selector
# the real mock reads out of the comment; these stubs read nothing, but a comment
# carrying one would make this module's fixtures depend on which stub answered.
A_COMMENT = "The pacing in week three was too fast for the lab work."

# What the stubs answer. The task's own output alone: ADR 0031 has the gateway
# supply the prompt version and the model id and reject a payload that carries
# either, so a stub volunteering them would produce a shape violation on every
# case here.
ANSWER = json.dumps({"verdict": "substantive"})


# ---------------------------------------------------------------------------
# Two OpenAI-compatible endpoints on the loopback interface.
#
# The shape is `tests/integration/test_ai_gateway_validity_roundtrip.py`'s,
# deliberately copied rather than imported: importing one test module from another
# depends on where pytest put `tests/` on `sys.path` for test modules, and turns a
# rename over there into a collection error here. What is copied is the harness
# and not an expectation — neither file asserts anything about the other.
#
# It answers whatever the request asked for: the payload goes in the assistant
# message's content and, when the request declares tools, in a tool call named
# after the tool it declared. So a gateway using native JSON output and one using
# an output tool both get a well-formed answer, and neither mode is chosen from
# the test side.
# ---------------------------------------------------------------------------


@dataclass
class Received:
    """One request a stub was sent."""

    path: str
    headers: dict[str, str]
    payload: Any

    @property
    def model(self) -> str:
        """The model the request asked for, or the empty string."""
        asked = self.payload.get("model") if isinstance(self.payload, dict) else None
        return asked if isinstance(asked, str) else ""

    @property
    def authorization(self) -> str:
        """The `Authorization` header, however it was capitalised."""
        for name, value in self.headers.items():
            if name.lower() == "authorization":
                return value
        return ""


class Handler(BaseHTTPRequestHandler):
    """Records the request, then answers it well."""

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence. The default writes every request to stderr."""

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        payload: Any = None
        if raw:
            with contextlib.suppress(ValueError):
                payload = json.loads(raw)
        provider: RecordingProvider = self.server.provider  # type: ignore[attr-defined]
        provider.received.append(
            Received(path=self.path, headers=dict(self.headers.items()), payload=payload)
        )
        self._send(json.dumps(completion(ANSWER, payload)))

    def do_GET(self) -> None:  # noqa: N802
        self._send(json.dumps({"object": "list", "data": []}))

    def _send(self, body: str) -> None:
        encoded = body.encode("utf-8")
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)


def output_tool_name(request: Any) -> str | None:
    """The tool a request wants its answer in, if it declared one."""
    tools = request.get("tools") if isinstance(request, dict) else None
    if not isinstance(tools, list) or not tools:
        return None
    names: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        name = function.get("name") if isinstance(function, dict) else tool.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    if not names:
        return None
    for name in names:
        if any(word in name.lower() for word in ("result", "final", "output")):
            return name
    return names[-1]


def completion(content: str, request: Any) -> dict[str, Any]:
    """An OpenAI-compatible chat completion carrying `content` however it was asked for."""
    message: dict[str, Any] = {"role": "assistant", "content": content}
    finish_reason = "stop"
    tool = output_tool_name(request)
    if tool is not None:
        message["tool_calls"] = [
            {
                "id": "call_e2_12",
                "type": "function",
                "function": {"name": tool, "arguments": content},
            }
        ]
        finish_reason = "tool_calls"
    asked = request.get("model") if isinstance(request, dict) else None
    return {
        "id": "chatcmpl-e2-12",
        "object": "chat.completion",
        "created": 1_750_000_000,
        "model": asked if isinstance(asked, str) and asked else "e2-12-stub",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class Server(ThreadingHTTPServer):
    """A threading server carrying the provider it answers for."""

    daemon_threads = True
    provider: RecordingProvider


@dataclass
class RecordingProvider:
    """One endpoint, bound to 127.0.0.1, that remembers what reached it."""

    label: str
    received: list[Received] = field(default_factory=list)
    _server: Server | None = None

    def start(self) -> None:
        server = Server(("127.0.0.1", 0), Handler)
        server.provider = self
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self._server = server

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def base_url(self) -> str:
        if self._server is None:  # pragma: no cover - the fixture always starts it
            raise RuntimeError("this endpoint was not started")
        host, port = self._server.server_address[0], self._server.server_address[1]
        return f"http://{host}:{port}/v1"


@pytest.fixture
def real_endpoint() -> Iterator[RecordingProvider]:
    """The endpoint the `AI_PROVIDER_*` triple names."""
    provider = RecordingProvider(REAL_SIDE)
    provider.start()
    try:
        yield provider
    finally:
        provider.stop()


@pytest.fixture
def mock_endpoint() -> Iterator[RecordingProvider]:
    """The endpoint the `MOCK_AI_PROVIDER_*` triple names."""
    provider = RecordingProvider(MOCK_SIDE)
    provider.start()
    try:
        yield provider
    finally:
        provider.stop()


@pytest.fixture
def classify_through(
    monkeypatch: pytest.MonkeyPatch,
    configured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    real_endpoint: RecordingProvider,
    mock_endpoint: RecordingProvider,
) -> Callable[[str, bool], None]:
    """Configure both triples, then run one classification with a chosen `live` flag.

    Both triples are configured every time, which is the whole design: a case that
    set only the side it expected to be used would pass against a gateway that read
    the other one and found it empty.

    `import_app_module` drops every `app.*` module first, so a gateway that builds
    something out of `Settings` at import time builds it out of what this fixture
    just set (`docs/MISTAKES.md` entry 3). `ENVIRONMENT` is stated by the caller
    rather than inherited, because it is half of what selection turns on
    (`docs/MISTAKES.md` entry 40).
    """

    def run(environment: str, live: bool) -> None:
        for name, value in (
            (ENVIRONMENT_VARIABLE, environment),
            (REAL_BASE_URL_VARIABLE, real_endpoint.base_url),
            (REAL_MODEL_NAME_VARIABLE, REAL_MODEL_NAME),
            (REAL_KEY_VARIABLE, REAL_CREDENTIAL),
            (MOCK_BASE_URL_VARIABLE, mock_endpoint.base_url),
            (MOCK_MODEL_NAME_VARIABLE, MOCK_MODEL_NAME),
            (MOCK_KEY_VARIABLE, MOCK_CREDENTIAL),
        ):
            monkeypatch.setenv(name, value)

        gateway_module = import_app_module(GATEWAY_MODULE)
        if gateway_module is None:
            pytest.fail(f"There is no `{GATEWAY_MODULE}` module. SPEC §13 places it.")
        gateway_class = getattr(gateway_module, GATEWAY_CLASS, None)
        if gateway_class is None:
            pytest.fail(
                f"`{GATEWAY_MODULE}` exposes no `{GATEWAY_CLASS}`. SPEC §7.4: 'All model "
                f"calls go through one internal `{GATEWAY_CLASS}`'."
            )

        tasks_module = import_app_module(TASKS_MODULE)
        if tasks_module is None:
            pytest.fail(f"There is no `{TASKS_MODULE}` module. SPEC §13 places it.")
        task = getattr(tasks_module, VALIDITY_TASK, None)
        if task is None:
            pytest.fail(
                f"`{TASKS_MODULE}` exposes no `{VALIDITY_TASK}`. It is the one call that "
                "takes a supplied gateway, and this module has no other way to choose the "
                "flag under test."
            )

        try:
            gateway = gateway_class(**{LIVE_FLAG: live})
        except TypeError as failure:
            pytest.fail(
                f"`{GATEWAY_CLASS}` does not accept a `{LIVE_FLAG}` construction flag "
                f"({failure}).\n"
                "\n"
                "That flag is the whole of selection: without it a caller cannot say which "
                "of the two configured providers it means, and the eval runner — which must "
                "always reach the real one, on a developer's machine as much as in CI — has "
                "no way to ask."
            )

        task(A_COMMENT, gateway=gateway)

    return run


def expected_and_other(
    side: str, real_endpoint: RecordingProvider, mock_endpoint: RecordingProvider
) -> tuple[RecordingProvider, RecordingProvider, str, str]:
    """The endpoint that must have been called, the one that must not, and the pair's values."""
    if side == REAL_SIDE:
        return real_endpoint, mock_endpoint, REAL_MODEL_NAME, REAL_CREDENTIAL
    return mock_endpoint, real_endpoint, MOCK_MODEL_NAME, MOCK_CREDENTIAL


def assert_reached(
    side: str,
    real_endpoint: RecordingProvider,
    mock_endpoint: RecordingProvider,
    environment: str,
    live: bool,
) -> None:
    """The three facts, together, about one classification.

    Which endpoint, which model name, which credential — and the other endpoint
    untouched. Split into a helper rather than repeated, because the near miss this
    exists for is a gateway that gets one of the three from the other triple, and a
    case that checked two of them would be exactly that mistake in a test.
    """
    expected, other, model, credential = expected_and_other(side, real_endpoint, mock_endpoint)
    described = f"live={live} in {environment!r}"

    assert expected.received, (
        f"{described} sent nothing to {side}, which is the triple the ruling selects.\n"
        f"  {REAL_SIDE} received {len(real_endpoint.received)} request(s)\n"
        f"  {MOCK_SIDE} received {len(mock_endpoint.received)} request(s)\n"
        "\n"
        "Both triples were configured, and each names a different loopback endpoint. A "
        "gateway reading the wrong one reaches a live provider where it meant the mock, "
        "or measures SPEC §9.3's floor against a character counter where it meant a model."
    )
    assert not other.received, (
        f"{described} sent {len(other.received)} request(s) to {other.label}, which the "
        f"ruling says it must not read. Selection is the whole of what the `{LIVE_FLAG}` "
        "flag and the environment decide between."
    )

    request = expected.received[0]
    assert request.model == model, (
        f"{described} reached {side} asking for model {request.model!r}, and that triple "
        f"names {model!r}.\n"
        "\n"
        "This is the near miss the endpoint check alone cannot see: a base URL from one "
        "triple and a model name from the other. The request lands at the right provider "
        "asking for a model it does not serve — and ADR 0031 stores that name as the "
        "`model_id` of the classification, so the audit record names a model that never ran."
    )
    assert credential in request.authorization, (
        f"{described} reached {side} with the `Authorization` header "
        f"{request.authorization!r}, which does not carry that triple's credential.\n"
        "\n"
        "The third of the three facts, and the one with a cost attached: a real key sent to "
        "the mock is a paid credential handed to a container the base Compose file starts "
        "in every deployment (ADR 0038), and the mock's key sent to a real provider is a "
        "request that is refused for a reason nobody will read as a configuration error."
    )


def test_the_two_endpoints_are_distinguishable() -> None:
    """A control, and every case below is vacuous without it.

    Each side is told apart by three values, and if any pair of them were equal the
    corresponding assertion would pass whichever triple the gateway read. This runs
    first so that a failure says "these tests cannot tell the sides apart" rather
    than reporting a selection defect that is not there (`docs/MISTAKES.md`
    entry 3).

    The addresses are not compared here because the fixtures allocate them at run
    time on separate ephemeral ports; `assert_reached` compares the endpoints as
    objects rather than by address, so two servers are two servers whatever ports
    they landed on.
    """
    assert (
        REAL_MODEL_NAME != MOCK_MODEL_NAME
    ), "the two triples name the same model, so no case below can tell which one was read"
    assert REAL_CREDENTIAL != MOCK_CREDENTIAL, (
        "the two triples carry the same credential, so the `Authorization` assertion cannot "
        "tell the sides apart"
    )
    assert REAL_CREDENTIAL not in MOCK_CREDENTIAL and MOCK_CREDENTIAL not in REAL_CREDENTIAL, (
        "one credential contains the other, so the substring assertion in `assert_reached` "
        "is satisfied by the wrong side"
    )


def test_the_development_literal_is_the_one_app_config_names(
    configured_env: dict[str, str],
) -> None:
    """A control on the `"development"` literal the parametrisations below spell.

    **A red here means these tests are broken, not the code.** Parametrisation
    needs its values at collection time and importing `app.config` there would turn
    a missing module into a collection error, so the rows spell the literal and this
    holds it against `app.config.DEVELOPMENT_ENVIRONMENT`, which E0-37 item 2 makes
    its one definition site.

    Without it, every "reads the mock triple in development" row below would be
    running under a *deployment* name and asserting the opposite of what it claims,
    with nothing saying so — the row would simply expect the real side and get it.
    """
    from app.config import DEVELOPMENT_ENVIRONMENT

    assert DEVELOPMENT_ENVIRONMENT == DEVELOPMENT, (
        f"`app.config.DEVELOPMENT_ENVIRONMENT` is {DEVELOPMENT_ENVIRONMENT!r} and this module "
        f"spells {DEVELOPMENT!r}. They have to be the same string, or half the rows below are "
        "running in an environment nobody chose."
    )


@pytest.mark.parametrize("environment", NON_DEPLOYMENT_ENVIRONMENTS)
def test_a_live_gateway_reads_the_real_triple_in_development(
    classify_through: Callable[[str, bool], None],
    real_endpoint: RecordingProvider,
    mock_endpoint: RecordingProvider,
    environment: str,
) -> None:
    """Invariant C: `live=True` reads the real triple regardless of environment.

    This is the row the eval gate rests on. `tests/evals/runner.py` builds its
    gateway `live=True` and `make evals` runs on a developer's machine, where the
    environment is `development` and where a gateway that consulted the environment
    instead of the flag would reach `mock-ai`. What comes back then is E2-07's
    twenty-five-character rule, and the runner writes that score down as SPEC
    §9.3's precision and recall floor — a floor a character counter clears forever,
    recorded against a real prompt version and a real model id.

    Nothing about the returned object says which endpoint answered, which is why
    this is asserted from the endpoints' side.

    **The mutation this kills:** selection written as "development means the mock",
    ignoring the flag — which is the natural reading of ADR 0113 as it stood and is
    correct for every caller except this one. **The near miss the endpoint check
    alone would pass:** the real base URL with the mock's model name or the mock's
    key, which is why `assert_reached` checks all three.
    """
    classify_through(environment, True)
    assert_reached(REAL_SIDE, real_endpoint, mock_endpoint, environment, live=True)


@pytest.mark.parametrize("environment", NON_DEPLOYMENT_ENVIRONMENTS)
def test_a_gateway_that_is_not_live_reads_the_mock_triple_in_development(
    classify_through: Callable[[str, bool], None],
    real_endpoint: RecordingProvider,
    mock_endpoint: RecordingProvider,
    environment: str,
) -> None:
    """The direction the development stack depends on, and the pair for the row above.

    Every ordinary caller is `live=False`: the submit path in §3.3 classifies a
    comment on a development machine through the mock, which is what lets
    `docker compose up` on a clean checkout work without a paid credential (SPEC
    §14.3). If this read the real triple, a clean checkout would send student
    comments to whatever `.env.example` names as the real provider, with whatever
    key happened to be lying in the environment.

    The pairing is what makes either row mean anything: one flag, one environment,
    two different endpoints. A gateway that always read the real triple passes the
    test above and fails this one; a gateway that always read the mock's does the
    reverse.

    **The mutation this kills:** ignoring the flag and always reading one triple,
    in either direction.
    """
    classify_through(environment, False)
    assert_reached(MOCK_SIDE, real_endpoint, mock_endpoint, environment, live=False)


@pytest.mark.parametrize("environment", DEPLOYMENT_ENVIRONMENTS)
def test_a_gateway_that_is_not_live_reads_the_real_triple_in_a_deployment(
    classify_through: Callable[[str, bool], None],
    real_endpoint: RecordingProvider,
    mock_endpoint: RecordingProvider,
    environment: str,
) -> None:
    """Invariant B: outside development and test, the mock triple is not read at all.

    ADR 0038 puts the mock in the Compose file every deployment runs, so
    `mock-ai` is a service that starts, resolves and answers in production. ADR
    0113 refuses a *base URL* that names it; this is the other half, and it is the
    half that survives an operator who copies `.env.example` forward without
    editing it. Both triples are configured here exactly as that copy would leave
    them, and the deployment must read the real one.

    What it costs to get wrong is not an outage. The mock answers, plausibly, in
    milliseconds: every comment over twenty-five characters comes back
    `substantive`, stored with a real prompt version and a real model id against a
    student's participation grade under §3.3, and every dashboard looks healthy.

    `tests/unit/test_ai_provider_configuration.py::test_the_mock_triple_may_still_
    name_the_mock_in_a_deployment` is the companion to this, and the division is
    worth stating: that one says a deployment does not *refuse* the mock's
    configured address, because nothing reads it; this one says nothing reads it.
    Neither is sufficient alone — the first passes over a gateway that reads the
    mock triple happily, and the second would pass over a `Settings` that refused
    every deployment at startup.

    **The mutation this kills:** selection written on the flag alone —
    `live=False` means the mock, everywhere — which passes both development rows
    above and points production at the character counter.
    """
    classify_through(environment, False)
    assert_reached(REAL_SIDE, real_endpoint, mock_endpoint, environment, live=False)


@pytest.mark.parametrize("environment", DEPLOYMENT_ENVIRONMENTS)
def test_a_live_gateway_reads_the_real_triple_in_a_deployment(
    classify_through: Callable[[str, bool], None],
    real_endpoint: RecordingProvider,
    mock_endpoint: RecordingProvider,
    environment: str,
) -> None:
    """Invariant C's other half: "in every environment" includes the ones that agree.

    The flag and the environment select the same triple here, so this row cannot
    fail while the three above pass — which is exactly why it is worth having. A
    selection rule that reads the flag *or* the environment and takes whichever it
    meets first is correct on three of the four combinations, and this is the
    fourth: it says the two agreeing produces the same answer as either alone,
    which is the sentence "regardless of environment" actually makes.

    **The mutation this kills:** a rule that returns the mock triple whenever the
    two inputs disagree in some particular order — cheap to write, and invisible
    without the completing row.
    """
    classify_through(environment, True)
    assert_reached(REAL_SIDE, real_endpoint, mock_endpoint, environment, live=True)
