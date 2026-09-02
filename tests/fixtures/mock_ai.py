"""E2-07 — the in-repo mock AI provider, driven the way the gateway drives one.

SPEC §9.2 makes an e2e run self-contained in Compose, and E2-07 adds the third
external dependency's stand-in: an OpenAI-compatible endpoint the stack can point
`MOCK_AI_PROVIDER_BASE_URL` at. This module is how the suite reaches it, and it
holds three separate things because three different kinds of test need them.

**Two triples, since the configuration split ruled on 2026-09-02.** The real
provider is described by `AI_PROVIDER_{API_KEY,BASE_URL,MODEL_NAME}` and the mock
by `MOCK_AI_PROVIDER_{API_KEY,BASE_URL,MODEL_NAME}`; `AI_MODEL_NAME` is a
spelling that ruling struck, because it said which model without saying whose and
there are two providers configured now. This file names both sides rather than
one, and that is not bookkeeping: `deployed_ai_provider` below describes a
provider that is deliberately **not** the mock and therefore takes the real
names, while everything that points a development stack at this service takes the
mock's. A file that held one pair would have to lend it to both, which is how a
model name from one provider ends up beside a base URL from the other.

**The application, in process.** `mock_ai` builds the mock's FastAPI application
through `import_mock_application` — the same machinery both other mocks use, and
for the same reason: `mock-lms/`, `mock-idp/`, `mock-ai/` and `backend/` all
declare a package called `app` (SPEC §13), so an import of one is a decision
about which program is under test (ADR 0039). Everything about the mock's own
behaviour — the rules, the wire shape, the served vocabulary — is asserted
against this client.

**The application on a real socket.** `mock_ai_endpoint` runs the same
application behind a loopback HTTP server, because the gateway is a real HTTP
client and cannot reach an in-process ASGI app. `docs/MISTAKES.md` entry 37 asks
what a harness reproduces and what it does not, so: the bridge reproduces the
mock's routing, its handlers, its status codes, its response bodies and its
delays, over a real TCP connection the gateway opens itself. It does not
reproduce uvicorn's HTTP parsing, the container, or any concurrency limit — the
handler thread forwards one request and blocks. Where a property of *uvicorn* is
the subject, this is the wrong instrument and the Compose health gate is the
right one.

**Nothing here states a rule.** The markers, the threshold, the stall and the
marker line are read from `GET /mock/rules`, which E2-07's third acceptance
criterion makes the mock's own published statement of them ("the tests that aim
at them read the served statement"). The one deliberate hand-copy this ticket
allows lives in `tests/unit/test_mock_ai_rules.py`, next to the test that diffs
it against the served document — the `ALL_SELECTORS` pair
`tests/integration/test_mock_lms_wrong_launches.py` already uses.

**`deployed_ai_provider` is the other half of this file and is about the
backend.** E2-07 pointed `.env.example`'s single provider base URL at the mock —
`MOCK_AI_PROVIDER_BASE_URL` since the split — and the same ticket refuses that
value outside development, so every test that
builds `Settings` under a deployment's `ENVIRONMENT` now has to move the AI
provider as well as the identity provider, or it stops in its own setup on a rule
that is not its subject. That is `docs/MISTAKES.md` entry 22 exactly, and the
repair is E0-39's: one fixture that configures a provider which is not the mock.
`deployed_identity_provider` in `tests/fixtures/doors.py` requests it, so a test
that already says "I am a deployment" gets both without a second declaration.
"""

import contextlib
import json
import threading
from collections.abc import Iterator, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from fixtures.app_imports import import_mock_application
from fixtures.lti_platform import APPLICATION_FACTORY_NAMES

REPO_ROOT = Path(__file__).resolve().parents[2]

# SPEC §13's layout for a mock, and E2-07's work order: `mock-ai/` holding a
# `Dockerfile` and an `app/`, added to Compose under the directory's own name.
# The service name is held against `docker-compose.yml` by
# `tests/unit/test_mock_ai_service.py` rather than trusted here.
MOCK_AI_DIR = REPO_ROOT / "mock-ai"
MOCK_AI_SERVICE = "mock-ai"

# Where the ASGI application might sit inside that package, most likely first —
# the same list, for the same reason, as `MOCK_LMS_MODULES`: the ticket names a
# FastAPI service and names no module, so the application is found rather than
# imported under a spelling this file chose.
MOCK_AI_MODULES = ("app.main", "app", "app.server", "app.api")

# The four routes E2-07 settles. The first three are the platform side of ADR
# 0053's OpenAI-compatible surface; the fourth is the mock's published rules,
# which acceptance criterion 3 makes the source every test aims at.
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
MODELS_PATH = "/v1/models"
HEALTH_PATH = "/healthz"
RULES_PATH = "/mock/rules"

# The port the container listens on, and the one the development override
# publishes it to on the loopback interface. 8080 and 8081 are the other two
# mocks'; 8082 is this one's, settled at the work order.
CONTAINER_PORT = "8000"
PUBLISHED_HOST_PORT = "8082"

# How the served rules document's four members are recognised. **This suite's
# choice**, and the same device `tests/integration/test_ai_gateway_validity_
# roundtrip.py` uses for the contract's field names: E2-07 settles that
# `/mock/rules` serves the whole vocabulary and settles no key names, so a member
# is matched by a normalised name from a short list and a document that carries
# none of them fails with a message naming the criterion rather than passing
# against a shape this file invented.
MARKERS_NAMES = ("markers", "selectors", "wronganswermarkers", "vocabulary")
THRESHOLD_NAMES = (
    "threshold",
    "minimumcharacters",
    "substantiveminimumcharacters",
    "insufficientbelow",
    "charactersthreshold",
)
STALL_SECONDS_NAMES = ("stallseconds", "stall", "stallsecs", "delayseconds")
MARKER_LINE_NAMES = ("markerline", "commentmarker", "commentmarkerline", "promptmarker")

# §7.4's Output column for the comment-validity task: "substantive / insufficient
# / nonsense". **Transcribed rather than derived**, and held here rather than in
# either test module because both the mock and the tool speak this vocabulary and
# a copy on each side would be two things to keep in step. Reading it off
# `app.ai.contracts` would make every assertion a comparison of one
# implementation against another; `tests/unit/test_ai_contracts.py` owns the
# derived direction, which is what keeps the enum and §7.4's table in step.
SUBSTANTIVE = "substantive"
INSUFFICIENT = "insufficient"
NONSENSE = "nonsense"
ALL_VERDICTS = (SUBSTANTIVE, INSUFFICIENT, NONSENSE)

# The member the mock's payload spells the verdict under: the contract payload
# minus the audit pair is one field, and E2-07's work order settles its name.
VERDICT_KEY = "verdict"

# A model name the request asks for, so that what the envelope reports can be
# compared against something the test chose. Distinctive on purpose.
REQUESTED_MODEL = "mock-validity-v1-e2-07-probe"

# The name a request declares when it asks for its answer in a tool call. The
# gateway itself uses `NativeOutput` and declares no tool (ADR 0053), so this is
# only ever this suite's own request — it exists because the work order keeps the
# mock honest to the stub the roundtrip test already models.
OUTPUT_TOOL_NAME = "final_result"

# The two triples, since the configuration split ruled on 2026-09-02. The real
# provider's names and the mock's, kept apart here so that no caller has to lend
# one side's constant to the other.
#
# `AI_MODEL_NAME_VARIABLE` is gone rather than aliased: it named a spelling the
# ruling struck, and leaving an alias behind would let a call site go on
# configuring "the model" without saying whose — which is the ambiguity the split
# exists to remove, surviving under a name that reads as harmless.
AI_PROVIDER_BASE_URL_VARIABLE = "AI_PROVIDER_BASE_URL"
AI_PROVIDER_MODEL_NAME_VARIABLE = "AI_PROVIDER_MODEL_NAME"
AI_PROVIDER_API_KEY_VARIABLE = "AI_PROVIDER_API_KEY"

MOCK_AI_PROVIDER_BASE_URL_VARIABLE = "MOCK_AI_PROVIDER_BASE_URL"
MOCK_AI_PROVIDER_MODEL_NAME_VARIABLE = "MOCK_AI_PROVIDER_MODEL_NAME"
MOCK_AI_PROVIDER_API_KEY_VARIABLE = "MOCK_AI_PROVIDER_API_KEY"

# An AI provider that is not the mock, for a test that runs as a deployment and
# is about something else. `.example.edu` resolves nowhere and nothing here
# fetches it; `https` because E0-37 item 12 refuses cleartext off this machine.
#
# **The real triple's names, and that is the point of the fixture.** It exists to
# say "this process is a deployment and is not pointed at the in-repo mock", so
# describing it under the mock's own variables would be the fixture asserting the
# opposite of its name.
DEPLOYED_AI_PROVIDER = {
    AI_PROVIDER_BASE_URL_VARIABLE: "https://ai.example.edu/v1",
    AI_PROVIDER_MODEL_NAME_VARIABLE: "a-real-deployments-model",
}


def normalised(name: str) -> str:
    """A member name with case, underscores, hyphens and spaces removed."""
    return name.lower().replace("_", "").replace("-", "").replace(" ", "")


def served_member(document: Mapping[str, Any], names: tuple[str, ...], purpose: str) -> Any:
    """One member of the served rules document, matched by a normalised name.

    Fails naming acceptance criterion 3 rather than returning `None`, so a
    document that does not publish what the criterion says it publishes is a red
    with an explanation instead of a `None` that flows into an assertion and
    reads as a wrong value.
    """
    for key, value in document.items():
        if isinstance(key, str) and normalised(key) in names:
            return value
    pytest.fail(
        f"`GET {RULES_PATH}` publishes no member for {purpose} — it carries {sorted(document)}. "
        "E2-07's third acceptance criterion: 'The mock's rules are served, not copied: its "
        f"README/route states them, and the tests that aim at them read the served statement.' If "
        f"it is published under a name none of {list(names)} reaches, that tuple in "
        "tests/fixtures/mock_ai.py is the one line that changes."
    )


def import_mock_ai_application(values: Mapping[str, str]) -> Any:
    """The mock provider's ASGI application. See `import_mock_application`."""
    return import_mock_application(
        MOCK_AI_DIR,
        MOCK_AI_MODULES,
        values,
        absent_directory=(
            f"{MOCK_AI_DIR} does not exist. E2-07's scope is 'a small FastAPI service "
            "(`mock-ai/`, following the mock pattern) speaking the OpenAI-compatible "
            "chat-completions surface the gateway uses', added to Compose as `mock-ai`."
        ),
        nothing_found=(
            "Nothing under `mock-ai/app/` exposes a FastAPI application. Looked for a "
            f"module-level instance, then a factory named one of {list(APPLICATION_FACTORY_NAMES)}"
            f", in {list(MOCK_AI_MODULES)}; imported {{imported}}. If it is reachable under a "
            "spelling none of those covers, that is a defect in `MockAiProvider` in "
            "tests/fixtures/mock_ai.py rather than in the mock, and MOCK_AI_MODULES there is the "
            "one line that changes."
        ),
    )


class MockAiProvider:
    """The mock, driven the way the gateway drives a provider: over its own routes.

    Nothing here decides a rule. `rules()` fetches the served document and every
    helper that needs a marker, a threshold or the marker line reads it from
    there, so this class cannot be the second copy acceptance criterion 3 forbids.
    """

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        from fastapi.testclient import TestClient

        self.values = dict(values or {})
        self.application = import_mock_ai_application(self.values)
        self.client = TestClient(self.application)
        # Entered so the application's lifespan runs, exactly as the other two
        # mock drivers do: whatever a mock builds at startup has not been built
        # until it does.
        self.client.__enter__()
        self._rules: dict[str, Any] | None = None

    def close(self) -> None:
        self.client.__exit__(None, None, None)

    # -- the published vocabulary -------------------------------------------

    def rules(self) -> dict[str, Any]:
        """The mock's own statement of its rules, fetched from `GET /mock/rules`."""
        if self._rules is None:
            response = self.client.get(RULES_PATH)
            assert response.status_code == 200, (
                f"`GET {RULES_PATH}` answered {response.status_code} rather than 200. E2-07's "
                "third acceptance criterion puts the rules on a route so that no test has to "
                f"hold a copy of them. Body begins {response.text[:200]!r}."
            )
            document = response.json()
            assert isinstance(document, dict) and document, (
                f"`GET {RULES_PATH}` served {document!r}, which is not a rules document. It is "
                "the whole vocabulary as JSON: the markers, the length threshold, the stall, and "
                "the prompt's comment marker."
            )
            self._rules = document
        return self._rules

    def markers(self) -> dict[str, str]:
        """The wrong-answer and forced-verdict markers, keyed by what each selects.

        Served as a mapping — the selector's meaning to the string a comment
        carries — or as a bare list, in which case each entry keys itself. Both
        are read, because E2-07 settles the marker strings and not the shape of
        the document that publishes them.
        """
        served = served_member(self.rules(), MARKERS_NAMES, "the wrong-answer and verdict markers")
        if isinstance(served, Mapping):
            return {str(key): str(value) for key, value in served.items()}
        assert isinstance(served, list) and served, (
            f"`GET {RULES_PATH}` publishes {served!r} as its markers, which is neither a non-empty "
            "list nor an object. A vocabulary nobody can enumerate is not a served vocabulary."
        )
        return {str(entry): str(entry) for entry in served}

    def marker_strings(self) -> list[str]:
        """Every marker string the mock answers to, whatever it is keyed by."""
        return sorted(self.markers().values())

    def marker_for(self, ending: str) -> str:
        """The one served marker that ends with `ending`.

        How a caller outside `tests/unit/test_mock_ai_rules.py` selects a
        behaviour without holding a second copy of the vocabulary: that module
        owns this ticket's single hand-copy and diffs it against the served list,
        and everything else picks its marker out of what the mock published.

        Fails when the match is not unique, which is the loud version of the
        failure a copy produces quietly — a renamed marker selects nothing here
        instead of selecting the unmarked path under an old name.
        """
        matches = [name for name in self.marker_strings() if name.endswith(ending)]
        assert len(matches) == 1, (
            f"The mock serves {matches} markers ending in {ending!r}, out of "
            f"{self.marker_strings()}. A caller selecting a behaviour needs exactly one."
        )
        return matches[0]

    def threshold(self) -> int:
        """The character count below which an unmarked comment is insufficient."""
        value = served_member(self.rules(), THRESHOLD_NAMES, "the length threshold")
        assert isinstance(value, int) and not isinstance(value, bool) and value > 0, (
            f"`GET {RULES_PATH}` publishes {value!r} as its length threshold. It is a count of "
            "characters, so it is a positive integer."
        )
        return value

    def stall_seconds(self) -> float:
        """How long the stall marker holds a request before answering."""
        value = served_member(self.rules(), STALL_SECONDS_NAMES, "the stall")
        assert isinstance(value, int | float) and not isinstance(value, bool) and value > 0, (
            f"`GET {RULES_PATH}` publishes {value!r} as its stall. It is a number of seconds the "
            "stalling answer waits before it replies."
        )
        return float(value)

    def marker_line(self) -> str:
        """The prompt line the student's comment follows."""
        value = served_member(self.rules(), MARKER_LINE_NAMES, "the prompt's comment marker line")
        assert isinstance(value, str) and value.strip(), (
            f"`GET {RULES_PATH}` publishes {value!r} as the comment marker line. It is the line "
            "`backend/app/ai/prompts/validity.v1.md` ends its comment section with, and the mock "
            "reads the student's comment as everything after its last occurrence."
        )
        return value

    # -- the OpenAI-compatible surface --------------------------------------

    def prompt_carrying(self, comment: str, *, marker: str | None = None, before: str = "") -> str:
        """A prompt ending in the marker line and then `comment`.

        `before` is whatever precedes the marker, so a test can put an earlier
        occurrence of it — or a decoy marker — in the part of the prompt the mock
        must ignore.
        """
        line = self.marker_line() if marker is None else marker
        head = before or "You are classifying a student comment. Answer with the JSON object only."
        return f"{head}\n{line}\n{comment}"

    def request_body(self, prompt: str, *, tools: bool = False) -> dict[str, Any]:
        """One OpenAI-compatible chat-completions request carrying `prompt`."""
        body: dict[str, Any] = {
            "model": REQUESTED_MODEL,
            "messages": [{"role": "user", "content": prompt}],
        }
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": OUTPUT_TOOL_NAME,
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]
        return body

    def ask(
        self, comment: str, *, marker: str | None = None, before: str = "", tools: bool = False
    ) -> Any:
        """Post one completion request whose prompt carries `comment`, and answer raw."""
        prompt = self.prompt_carrying(comment, marker=marker, before=before)
        return self.post(prompt, tools=tools)

    def post(self, prompt: str, *, tools: bool = False) -> Any:
        """Post one completion request carrying `prompt` verbatim, and answer raw.

        Raw, so that a test asking about a 503 reads the status itself rather
        than meeting an exception from a helper that assumed 200.
        """
        return self.client.post(CHAT_COMPLETIONS_PATH, json=self.request_body(prompt, tools=tools))


def content_of(response: Any) -> str:
    """The assistant's message content out of one chat completion, or a failure.

    The route ADR 0053 makes the gateway read: native JSON output, so the task's
    object arrives as the text of the assistant's message.
    """
    assert response.status_code == 200, (
        f"The completion answered {response.status_code} rather than 200, so it carries no "
        f"assistant message to read. Body begins {response.text[:300]!r}."
    )
    document = response.json()
    assert isinstance(document, dict), f"The completion served {document!r}, not an object."
    choices = document.get("choices")
    assert isinstance(choices, list) and choices, (
        f"The completion carries {choices!r} as its `choices`. An OpenAI-compatible chat "
        "completion carries a non-empty array, and the gateway reads the first entry."
    )
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    assert isinstance(message, dict), f"The first choice carries {message!r} as its `message`."
    content = message.get("content")
    assert isinstance(content, str) and content, (
        f"The assistant message carries {content!r} as its `content`. ADR 0053 puts the task's "
        "JSON object there: the gateway asks for native JSON output and declares no tool."
    )
    return content


def payload_of(response: Any) -> Any:
    """The contract payload the completion's content spells, parsed."""
    content = content_of(response)
    try:
        return json.loads(content)
    except ValueError as failure:
        pytest.fail(
            f"The assistant message content is not JSON ({failure}): {content!r}. The mock answers "
            "with the comment-validity payload as a JSON string, which is what the gateway "
            "validates against the contract."
        )


# ---------------------------------------------------------------------------
# The same application, on a socket the gateway can open.
# ---------------------------------------------------------------------------


class Endpoint:
    """The mock's address on a real socket, and what the gateway sent to it.

    `completions` is why this is an object rather than a string: E2-07's malformed
    selector is about the gateway asking *twice* — ADR 0053's one bounded re-ask —
    and a test that could only see the final error would pass against a gateway
    that never retried and against one that retried forever.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.completions: list[Any] = []


class _BridgeHandler(BaseHTTPRequestHandler):
    """Forward one HTTP request into the mock's in-process client and back out.

    Deliberately thin. It does not interpret a status, a body or a delay — it
    passes each through — so what a test asserts about the gateway's reaction is
    a reaction to what the mock actually answered.
    """

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence. The default writes every request to stderr."""

    def _forward(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if method == "POST" and self.path.endswith(CHAT_COMPLETIONS_PATH):
            with contextlib.suppress(ValueError):
                self.server.endpoint.completions.append(  # type: ignore[attr-defined]
                    json.loads(body.decode("utf-8"))
                )
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in {"host", "content-length", "connection", "accept-encoding"}
        }
        client = self.server.bridged_client  # type: ignore[attr-defined]
        answered = client.request(method, self.path, content=body, headers=headers)
        payload = answered.content
        # A client that has already given up leaves nothing to write to, which is
        # the normal end of a request the gateway timed out on rather than a
        # failure of this bridge.
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.send_response(answered.status_code)
            self.send_header(
                "Content-Type", answered.headers.get("content-type", "application/json")
            )
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        self._forward("POST")

    def do_GET(self) -> None:  # noqa: N802
        self._forward("GET")


class _BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    bridged_client: Any
    endpoint: Endpoint


@pytest.fixture
def mock_ai_dir() -> Path:
    """Where the mock provider must live. Asserted by the test, not here."""
    return MOCK_AI_DIR


@pytest.fixture
def mock_ai_service() -> str:
    """The Compose service name E2-07 gives the mock provider.

    One answer to "what is this service called", so that the compose-shape tests,
    the `.env.example` test and `app.config`'s catalog are all held against the
    same string rather than against three literals that can drift apart
    (`docs/MISTAKES.md` entry 35 — a stale catalog refuses nothing and reports
    exactly what a fresh one reports).
    """
    return MOCK_AI_SERVICE


@pytest.fixture
def mock_ai() -> Iterator[MockAiProvider]:
    """The mock provider in process, torn down with the test."""
    provider = MockAiProvider()
    try:
        yield provider
    finally:
        provider.close()


@pytest.fixture
def mock_ai_rules(mock_ai: MockAiProvider) -> dict[str, Any]:
    """The served rules document, for a test whose subject is what it publishes."""
    return mock_ai.rules()


@pytest.fixture
def mock_ai_endpoint(mock_ai: MockAiProvider) -> Iterator[Endpoint]:
    """The mock on a loopback socket, with a `MOCK_AI_PROVIDER_BASE_URL` to point at it.

    For the tests whose subject is the *gateway's* reaction to what the mock
    answers: the gateway is a real HTTP client and cannot reach an ASGI
    application in process. What this reproduces and what it does not is in this
    module's docstring (`docs/MISTAKES.md` entry 37).
    """
    server = _BridgeServer(("127.0.0.1", 0), _BridgeHandler)
    host, port = server.server_address[0], server.server_address[1]
    endpoint = Endpoint(f"http://{host}:{port}/v1")
    server.bridged_client = mock_ai.client
    server.endpoint = endpoint
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield endpoint
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def deployed_ai_provider(
    monkeypatch: pytest.MonkeyPatch,
    configured_env: dict[str, str],
) -> dict[str, str]:
    """Configure an AI provider that is not the mock, and answer what it set.

    The twin of `deployed_identity_provider` in `tests/fixtures/doors.py`, and it
    exists for the identical reason one ticket later. `configured_env` lays down
    `.env.example`, whose provider is `http://mock-ai:8000/v1` from E2-07 onwards;
    that value is refused outside development twice over — once for naming the
    mock and once for being cleartext off this machine — so a test that sets
    `ENVIRONMENT` to a deployment's value and is about something else stops in its
    own setup on a rule that is not its subject (`docs/MISTAKES.md` entry 22).

    Requested rather than applied globally, because the combination is legal — and
    required — in development, and `tests/unit/test_config_settings.py` asserts
    that the documented file is a working configuration.
    """
    for name, value in DEPLOYED_AI_PROVIDER.items():
        monkeypatch.setenv(name, value)
    return dict(DEPLOYED_AI_PROVIDER)
