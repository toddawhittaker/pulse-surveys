"""The comment-validity task, end to end against a stubbed provider — ticket E0-13.

E0-13's exit criterion is one working AI round trip: "a comment goes in, a
validated Pydantic object comes back, and the prompt version and model ID are
recorded". This module is that round trip, plus the three things the ticket says
must happen when the provider misbehaves — retry on a shape violation, an error
on a persistent one, and **fail open** on a timeout — plus the append-only
`classification` row SPEC §8 requires.

**Nothing here names a function inside `app.ai.tasks` or `app.ai.gateway`.** The
ticket spells the two files and spells no callable, no signature and no return
shape, so the validity task is *found* — one public callable whose name carries
the task's own word — and it is called by filling its parameters from the values
this module has, by parameter name. That is the mechanism `SectionCodeService` in
`tests/conftest.py` uses and it is here for the same reason: pinning a name would
make the implementer build to this file instead of to the ticket. A parameter no
offered role matches stops the test with a message naming it, which is an
interface question for the ticket rather than something to guess at.

**The provider is a real HTTP server on the loopback interface, and that is the
one seam the ticket does name.** Its scope says "provider-agnostic client against
an OpenAI-compatible base URL" and "Provider configuration from `Settings`: base
URL, model, and a masked key", so a test drives the provider by pointing
`AI_PROVIDER_BASE_URL` at a server it controls. What the stub deliberately does
*not* decide is how the gateway asks for structured output: it answers whatever
the request asked for, putting the task's JSON in the assistant message's content
**and**, when the request carries tools, in a tool call named after the tool the
request declared. A gateway using native JSON output and one using an output tool
both get a well-formed answer, so neither mode is chosen from the test side.

**These are integration tests rather than the unit tests E0-13's definition of
done asks for**, and the reason is a signature the ticket leaves open. The task
persists a `classification` row, so it may well take a session; a module that
offered none would die inside its own binder for every implementation that does
(`docs/MISTAKES.md` entry 13, the hazard met at one call site and not the other).
Offering `db_session` costs an implementation that does not want one nothing —
the binder simply does not pass it — and the append-only criterion needs the
database in any case.

**Where a criterion is asserted against an absence, it carries a control.**
`docs/MISTAKES.md` entry 3: the retry test would pass against a gateway that
always sends two requests, so `test_a_well_formed_first_answer_is_not_followed_by
_a_second_call` pins the single-shot boundary from the other side; the loopback
guard is run against an address it must refuse *and* one it must permit, because
a guard that has gone blind reports the same silence as a gateway that never left
the machine; and the credential-leak test asserts the stub actually *received* the
key before asserting the error does not carry it, since an error cannot leak a
value that was never sent.

**The needle that credential rule searches with is itself asserted**, and that is
a repair rather than a flourish. The value first used here contained the ordinary
word `provider`; in the unit module that made a leak assertion false for every
implementation, and here it would have done something quieter and worse, since the
same value is used as a *positive* detector to prove the key was sent at all.
`test_the_needle_matches_nothing_a_request_carries_without_it` removes the key,
makes the same call, and requires zero matches anywhere in it.

**Three subjects were added after a review, and each closes a gap this module had
rather than a criterion it had missed.** The fail-open tests asserted a property
of two returned objects while claiming one about the stored record, so moving the
`classification` write inside the gateway's `try` — the fail-open path returning a
verdict and storing nothing — left the whole suite green; they read the row now.
Nothing asserted that the student's comment or the versioned prompt reached the
provider at all, so an empty prompt or an unsubstituted placeholder also passed.
And two failure modes a reviewer found in the gateway have regression tests here:
one client shared across per-thread event loops, whose reused connections raised
and were misread as an outage, so a healthy provider's answer was fetched and
discarded; and a shape-violation message built by interpolating the keys of the
payload that violated it, which reassembles a student's comment in a log when a
model returns the comment as field names.

**What is deliberately not asserted here.** Whether the validity prompt produces
good classifications is a distribution, not an assertion — SPEC §9.3 answers that
with versioned eval sets and per-task precision and recall floors, and nothing in
this file can make that gate easier to pass. Prompt *content* is read only to the
extent of checking that it was sent. The synchronous submit path, its p95 budget,
and what a student sees when the floor applies are E2's (§3.3), and this module
asserts only what the gateway does.
"""

import asyncio
import contextlib
import enum
import inspect
import ipaddress
import json
import socket
import threading
import time
import types
import typing
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]

# E0-13's scope spells both files, and SPEC §13 places them: "`ai/gateway.py` —
# provider-agnostic client (OpenAI-compatible base_url)" and "`ai/tasks.py` —
# validity / moderation / summary / draft / draft-check calls". The package root
# is `backend/`, so the import paths are these.
TASKS_MODULE = "app.ai.tasks"
CONTRACTS_MODULE = "app.ai.contracts"

# The exceptions that mean the gateway fell over rather than reported. E0-13 names
# no error type, so requiring one would pin an interface the ticket leaves open;
# what is required is that a failure is *surfaced* — something a caller on §3.3's
# submit path can catch on purpose. `raised_by_the_service` in `tests/conftest.py`
# draws the same line for E0-07 and gives the reason: an unguarded parse failure
# is not an error anybody can handle.
FELL_OVER = (AttributeError, TypeError, NameError)

# E0-12 shipped the prompts here and `pyproject.toml` packages the directory.
# ADR 0031 makes the recorded `prompt_version` "the prompt file's path stem", so
# this is what a recorded version is checked against.
PROMPTS_DIR = REPO_ROOT / "backend" / "app" / "ai" / "prompts"
NON_PROMPT_NAMES = ("readme.md", "readme", "__init__.py", ".gitkeep", ".gitignore")

# **This suite's choice**, and the only place a callable inside `app.ai.tasks` is
# guessed at. The ticket names the task — "the comment-validity task implemented
# end to end against the E0-12 contract and prompt" — and names no function, so a
# callable is matched by a word from the task's own name. If it is there under a
# name none of these reaches, that is a one-line change here and a sentence in the
# pull request.
VALIDITY_FRAGMENTS = ("validity", "valid", "classify_comment")

# What a value this module can supply is *for*, matched against a parameter's
# name. E0-13 says the task takes a comment and says nothing about whether a
# session is passed or what any of it is called, so the tests offer what they have
# and let the signature take what it wants. Matching is by exact name or by
# `_`-suffix, longest alias first, exactly as `SERVICE_ROLES` in
# `tests/conftest.py` does.
CALL_ROLES: dict[str, tuple[str, ...]] = {
    "session": ("session", "db", "database"),
    "comment": ("comment", "text", "body", "content", "answer", "comment_text"),
}

# §7.4's Output column for the comment-validity task, **deliberately transcribed
# rather than derived**, and this is the one constant in this file that is not
# free to move (`docs/MISTAKES.md` entry 19). The tokens are needed twice: to
# write a well-formed provider answer, and to say which verdict the character
# heuristic must reach. Reading them off the contract under test would make both
# uses a comparison of the code against itself.
# `tests/unit/test_ai_contracts.py` holds the derived version, which is what keeps
# the enum and §7.4's table in step; this is the copy that lets a payload be
# built.
SUBSTANTIVE_VERDICT = "substantive"
INSUFFICIENT_VERDICT = "insufficient"

# SPEC §3.3: "The prototype's ≥25-character heuristic is a placeholder only;
# production substantiveness is the classifier's call, with the character
# heuristic retained solely as the fail-open floor below." So this number is the
# floor's whole rule, and it is the spec's rather than this file's.
HEURISTIC_MINIMUM_CHARACTERS = 25

# Two comments well clear of that boundary in each direction, and one on it. The
# boundary strings are checked for their own length inside the test that uses
# them, so a typo here fails as a fixture problem rather than as a criterion.
SUBSTANTIVE_COMMENT = "The pacing in week three was too fast for the lab work."
INSUFFICIENT_COMMENT = "it was okay"
BOUNDARY_COMMENT = "the lab work was hard ok!"

# The same comment carrying a nonce, for the two tests that ask whether the
# student's words reached the provider. The nonce is what makes a match evidence:
# an ordinary English sentence could in principle turn up in a prompt template,
# and then "the comment was sent" would be satisfied by a request that carried the
# prompt and dropped the comment.
TRACEABLE_COMMENT = "The pacing in week three was too fast for the lab work [Kj3PxE8mZt5UwGh]."

# A comment made of tokens that appear nowhere else in this repository, and long
# enough per token that an eight-character window of one is unambiguous. It is the
# needle for the two tests asking whether a shape violation quotes a student back
# into an error message, and the chunks are sent as the *keys* of the payload
# because that is the shape the reviewer found: a message built by interpolating
# the names a model invented reassembles the comment in order.
NEEDLE_COMMENT = "Rb9NsWqvZm Xt4LdKj3Px E8mZt5UwGh Tf2YcRbVn8"
NEEDLE_COMMENT_CHUNKS = tuple(NEEDLE_COMMENT.split())

# How many submissions the concurrency regression makes, and over how many
# threads. **This suite's choice.** The defect it is written against floored every
# other call — measured at 1, 3 and 5 of six — so a dozen over four workers is
# comfortably more than one round of it, and each call is a loopback round trip
# costing milliseconds.
CONCURRENT_SUBMISSIONS = 12
CONCURRENT_WORKERS = 4

# The model the stub answers as. Distinctive so that a `model_id` recorded from
# the configuration and one recorded from the provider's response are the same
# string, and neither route has to be chosen from the test side — what is asserted
# is that the value identifies the model that answered.
STUB_MODEL_ID = "e0-13-stub-model-7c1f"

# The value the provider key is configured with, and the needle
# `leaked_fragments` searches for in **both** directions below.
#
# **The property it has to have is that it shares no run of
# `LEAK_FRAGMENT_LENGTH` characters with anything a request or an error
# legitimately carries.** The first version was
# `fake-ai-provider-Qv7ZmXt4Ld9RbNsW`, and `provider` is an eight-character window
# of it. In `tests/unit/test_ai_provider_configuration.py` that made a leak
# assertion false for every possible implementation, which is how the collision
# was found and ruled on. **Here it is worse, because this module also uses the
# needle as a *positive* detector.**
# `test_a_provider_error_does_not_carry_the_provider_key_into_the_failure` proves
# the key was really sent by looking for it in the request headers, so a header
# value containing the ordinary word `provider` satisfies that non-vacuity guard —
# after which the leak assertions underneath it report a guarantee they never
# tested. That is `docs/MISTAKES.md` entry 3 in the direction the unit module
# cannot produce: a green test rather than a red one.
#
# The exception-chain half was surviving on capitalisation alone: the gateway
# writes `AI_PROVIDER_BASE_URL` and `AIProviderRefusedError`, both of which miss a
# lowercase needle, and one lowercased error message would have turned it red for
# a reason that has nothing to do with a credential.
#
# `test_the_needle_matches_nothing_a_request_carries_without_it` below is what
# makes this an asserted property rather than a value chosen carefully once.
# Nothing here resembles a real credential and nothing was copied from a working
# `.env` (CLAUDE.md, secrets); the readable label lives in the constant's name,
# and the failure messages name it.
FAKE_PROVIDER_CREDENTIAL = "Qv7ZmXt4Ld9RbNsW-Kj3PxE8mZt5UwGh"

# How much of a credential has to appear contiguously to count as leaked.
# Checking for the whole value is not enough — a truncated repr can print all but
# one character and still not contain it. Same length and same reason as
# `tests/unit/test_config_settings.py`.
#
# **Raising it is not a way to fix a colliding needle.** It is a threshold shared
# with `test_config_settings.py` and `test_db_engine_configuration.py`, where a
# larger value would let a rendering that truncated a real database password to
# nine characters pass. Tune the needle instead.
LEAK_FRAGMENT_LENGTH = 8

# **This suite's choice**, and how a `.env.example` entry for the provider key is
# recognised without the ticket having spelled its name. `.env.example` already
# says of it: "the provider key is not read yet — the gateway and its masked key
# land in E0-13."
PROVIDER_KEY_WORDS = ("KEY", "TOKEN", "SECRET", "CREDENTIAL")
PROVIDER_KEY_QUALIFIERS = ("AI", "PROVIDER", "MODEL", "LLM")

# What the provider's own answer may never contain. ADR 0031: "The gateway must
# reject a provider payload that contains either key, *before* merging anything
# into it, and treat that as the shape violation §7.4 has it retry on." The values
# are invented here so that one landing in a returned object is unambiguous.
LIAR_PROMPT_VERSION = "i-was-never-loaded.v99"
LIAR_MODEL_ID = "i-am-a-liar-3000"

# How a prompt version and a model ID might be spelled on a contract. Both lists
# are `tests/unit/test_ai_contracts.py`'s, because E0-12 spells "prompt version
# and model ID" and spells no field name. Compared with case, underscores and
# hyphens removed.
PROMPT_VERSION_NAMES = ("promptversion", "promptrevision", "promptid")
MODEL_ID_NAMES = ("modelid", "model", "modelname", "modelversion")

# Used only to break a tie when a contract carries more than one enum-typed field.
# A model with a single enum field never consults this list.
VERDICT_FIELD_NAMES = (
    "verdict",
    "label",
    "classification",
    "status",
    "result",
    "category",
    "outcome",
    "decision",
)

# How long the stub holds a request before answering, in the timeout tests, and
# the margin below it that counts as "did not wait for the provider". The number
# is not a claim about what the gateway's per-task timeout should be — E0-13 does
# not set one and neither does this file. It is only long enough that a gateway
# which waits for the answer cannot be mistaken for one that gave up.
PROVIDER_DELAY_SECONDS = 20.0
FAIL_OPEN_MARGIN_SECONDS = 2.0

# The table SPEC §8 names and E0-13 creates.
CLASSIFICATION_TABLE = "classification"

# The role the API and the worker connect as (ADR 0001, ADR 0009). A
# classification row is written by application code, so this is the role that has
# to be able to write one.
APPLICATION_ROLE = "pulse_app"

# An address that is certainly not this machine. RFC 5737 TEST-NET-3, reserved for
# documentation and routed nowhere — so a guard that lets a connection through
# leaks no packet anywhere real, and a guard that stops it stops it before any
# name is resolved.
OFF_MACHINE_ADDRESS = ("203.0.113.7", 443)


# ---------------------------------------------------------------------------
# A provider on the loopback interface
# ---------------------------------------------------------------------------


@dataclass
class Answer:
    """One reply the stub is scripted to make.

    `content` is what the assistant says, verbatim — the tests use it both for a
    well-formed payload and for a malformed one, since "malformed" here means
    "text the contract refuses" and that is a property of the string.

    `body` replaces the whole HTTP body, for the case where the envelope itself is
    wrong. `delay` is how long the request is held before answering, which is the
    timeout simulation.
    """

    content: str | None = None
    status: int = 200
    delay: float = 0.0
    body: str | None = None


@dataclass
class Received:
    """One request the stub was sent, kept so a test can say what was asked."""

    method: str
    path: str
    headers: dict[str, str]
    body: str
    payload: Any = None


def output_tool_name(request: Any) -> str | None:
    """The name of the tool a request wants its answer in, if it declared one.

    A client asking for structured output through a tool call names the tool it
    wants back, so the stub answers under that name rather than under one this
    file invents. Where several tools are declared, the one whose name reads like
    an output tool is preferred and otherwise the last is taken — a heuristic,
    stated here rather than hidden, and it exists so that the stub does not
    decide whether the gateway uses tool calls or native JSON output.
    """
    if not isinstance(request, Mapping):
        return None
    tools = request.get("tools")
    if not isinstance(tools, list) or not tools:
        return None
    names: list[str] = []
    for tool in tools:
        if not isinstance(tool, Mapping):
            continue
        function = tool.get("function")
        name = function.get("name") if isinstance(function, Mapping) else tool.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    if not names:
        return None
    for name in names:
        if any(word in name.lower() for word in ("result", "final", "output")):
            return name
    return names[-1]


def chat_completion(content: str | None, request: Any, model: str) -> dict[str, Any]:
    """An OpenAI-compatible chat completion carrying `content` however it was asked for."""
    message: dict[str, Any] = {"role": "assistant", "content": content}
    finish_reason = "stop"

    tool_name = output_tool_name(request)
    if tool_name is not None and content is not None:
        message["tool_calls"] = [
            {
                "id": "call_e0_13_stub",
                "type": "function",
                "function": {"name": tool_name, "arguments": content},
            }
        ]
        finish_reason = "tool_calls"

    requested_model = request.get("model") if isinstance(request, Mapping) else None
    return {
        "id": "chatcmpl-e0-13-stub",
        "object": "chat.completion",
        "created": 1_750_000_000,
        "model": requested_model if isinstance(requested_model, str) and requested_model else model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class StubHandler(BaseHTTPRequestHandler):
    """The request handler. Every reply comes from the server's script."""

    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence. The default writes every request to stderr."""

    def _record(self, method: str) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        payload: Any = None
        if raw:
            with contextlib.suppress(ValueError):
                payload = json.loads(raw)
        received = Received(
            method=method,
            path=self.path,
            headers=dict(self.headers.items()),
            body=raw,
            payload=payload,
        )
        self.server.provider.received.append(received)  # type: ignore[attr-defined]
        return received

    def _send(self, status: int, body: str) -> None:
        encoded = body.encode("utf-8")
        # A client that has already given up leaves nothing to write to. That is
        # the normal end of a timed-out request rather than a failure.
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        received = self._record("POST")
        provider: StubProvider = self.server.provider  # type: ignore[attr-defined]
        answer = provider.next_answer()
        if answer.delay:
            time.sleep(answer.delay)
        if answer.body is not None:
            self._send(answer.status, answer.body)
            return
        self._send(
            answer.status,
            json.dumps(chat_completion(answer.content, received.payload, provider.model)),
        )

    def do_GET(self) -> None:  # noqa: N802
        self._record("GET")
        provider: StubProvider = self.server.provider  # type: ignore[attr-defined]
        self._send(
            200,
            json.dumps({"object": "list", "data": [{"id": provider.model, "object": "model"}]}),
        )


class StubServer(ThreadingHTTPServer):
    """A threading server carrying the provider it answers for."""

    daemon_threads = True
    provider: "StubProvider"


@dataclass
class StubProvider:
    """An OpenAI-compatible endpoint the tests control, bound to 127.0.0.1.

    It answers from a script. `answers` is consumed in order and the last entry
    repeats once the script runs out, so "always malformed" and "malformed once,
    then fine" are one mechanism.
    """

    model: str = STUB_MODEL_ID
    answers: list[Answer] = field(default_factory=list)
    received: list[Received] = field(default_factory=list)
    _server: StubServer | None = None
    _index: int = 0

    def start(self) -> None:
        server = StubServer(("127.0.0.1", 0), StubHandler)
        server.provider = self
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._server = server

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def base_url(self) -> str:
        if self._server is None:  # pragma: no cover - the fixture always starts it
            raise RuntimeError("the stub provider was not started")
        host, port = self._server.server_address[0], self._server.server_address[1]
        return f"http://{host}:{port}/v1"

    def script(self, *answers: Answer) -> None:
        """Set what the stub will answer, in order. The last answer repeats.

        **A script of more than one answer is not safe to use concurrently.**
        `next_answer` advances a plain counter and the server handles each request
        on its own thread, so two overlapping requests can take the same entry or
        skip one. The concurrency test below scripts exactly one answer, where the
        counter cannot change which answer is given; anything that needs an
        ordered script under load needs a lock here first.
        """
        self.answers = list(answers)
        self._index = 0

    def next_answer(self) -> Answer:
        if not self.answers:
            return Answer(content="{}")
        index = min(self._index, len(self.answers) - 1)
        self._index += 1
        return self.answers[index]

    @property
    def calls(self) -> list[Received]:
        """The POSTs — the completion requests, rather than a model listing."""
        return [entry for entry in self.received if entry.method == "POST"]


@pytest.fixture
def stub_provider() -> Iterator[StubProvider]:
    """A provider endpoint on the loopback interface, torn down with the test."""
    provider = StubProvider()
    provider.start()
    try:
        yield provider
    finally:
        provider.stop()


@pytest.fixture
def ai_environment(
    monkeypatch: pytest.MonkeyPatch,
    care_service_environment: dict[str, str],
    documented_env: dict[str, str],
    stub_provider: StubProvider,
) -> dict[str, str]:
    """An environment pointing an `app.*` import at the stub and at this container.

    `care_service_environment` is depended on for what it does rather than for
    what it is named: it is the one fixture that applies `.env.example`'s whole
    surface and then overwrites the database variables with the test container's,
    which is what any `app.*` module reaching `app.db` needs (`docs/MISTAKES.md`
    entry 13 — the alternative was a fourth copy of that assembly).

    Every documented variable whose name reads as the provider key is then set to
    one obvious fake, so a test asserting the key does not leak has a value to
    look for.
    """
    values = {
        "AI_PROVIDER_BASE_URL": stub_provider.base_url,
        "AI_MODEL_NAME": STUB_MODEL_ID,
    }
    for name in provider_key_variables(documented_env):
        values[name] = FAKE_PROVIDER_CREDENTIAL
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return {**care_service_environment, **values}


def provider_key_variables(documented_env: Mapping[str, str]) -> list[str]:
    """Every `.env.example` entry that reads as the provider key.

    Found rather than named, because E0-13 does not spell the variable — it says
    only "Provider configuration from `Settings`: base URL, model, and a masked
    key", and `.env.example` says "the provider key is not read yet — the gateway
    and its masked key land in E0-13".
    """
    return sorted(
        name
        for name in documented_env
        if any(word in name.upper() for word in PROVIDER_KEY_WORDS)
        and any(word in name.upper() for word in PROVIDER_KEY_QUALIFIERS)
    )


# ---------------------------------------------------------------------------
# Finding the task and the contract without naming them
# ---------------------------------------------------------------------------


def normalised(name: str) -> str:
    """A field or member name with case, underscores and hyphens removed."""
    return name.lower().replace("_", "").replace("-", "").replace(" ", "")


def require_module(
    import_app_module: Callable[[str], ModuleType | None], name: str, quoting: str
) -> ModuleType:
    """Import an `app.*` module, or fail naming the deliverable that is missing."""
    module = import_app_module(name)
    if module is None:
        pytest.fail(f"There is no `{name}` module. E0-13's scope: {quoting}")
    return module


def defined_callables(module: ModuleType) -> dict[str, Any]:
    """Every public callable the module defines itself.

    Defines *itself*: a function imported from somewhere else is not part of this
    module's surface, and counting one would let an import answer for the ticket's
    deliverable. Module-level functions and the `classmethod`/`staticmethod`
    members of module-level classes both count, because `ValidityTask.run` and
    `classify_validity` are equally reasonable and the ticket rules out neither.
    """
    found: dict[str, Any] = {}
    for name, value in vars(module).items():
        if name.startswith("_"):
            continue
        if getattr(value, "__module__", None) != module.__name__:
            continue
        if inspect.isfunction(value):
            found[name] = value
        elif inspect.isclass(value):
            for attribute, member in vars(value).items():
                if attribute.startswith("_") or not isinstance(member, classmethod | staticmethod):
                    continue
                bound = getattr(value, attribute, None)
                if callable(bound):
                    found[f"{name}.{attribute}"] = bound
    return found


def validity_task(import_app_module: Callable[[str], ModuleType | None]) -> Any:
    """The one callable in `app.ai.tasks` that runs the comment-validity task."""
    module = require_module(
        import_app_module,
        TASKS_MODULE,
        "'`backend/app/ai/tasks.py` with the comment-validity task implemented end to end "
        "against the E0-12 contract and prompt'.",
    )
    defined = defined_callables(module)
    for fragment in VALIDITY_FRAGMENTS:
        matches = {
            name: value
            for name, value in defined.items()
            if fragment in name.rsplit(".", maxsplit=1)[-1].lower()
        }
        if len(matches) > 1:
            unqualified = {name: value for name, value in matches.items() if "." not in name}
            if len(unqualified) == 1:
                return next(iter(unqualified.values()))
            pytest.fail(
                f"`{TASKS_MODULE}` defines more than one callable whose name carries "
                f"{fragment!r} ({sorted(matches)}), so this cannot tell which one is the "
                "comment-validity task. Naming one here would pin an interface E0-13 leaves "
                "open: say in the pull request which it is, and `VALIDITY_FRAGMENTS` in this "
                "file is the one line that changes."
            )
        if matches:
            return next(iter(matches.values()))
    pytest.fail(
        f"`{TASKS_MODULE}` defines no callable whose name carries any of "
        f"{list(VALIDITY_FRAGMENTS)} — it defines {sorted(defined)}. E0-13's scope: "
        "'`backend/app/ai/tasks.py` with the comment-validity task implemented end to end "
        "against the E0-12 contract and prompt.' The callable is looked for by name rather than "
        "imported under an agreed one because no ticket spells it."
    )


def contract_models(module: ModuleType) -> dict[str, type[BaseModel]]:
    """Every Pydantic model the contracts module defines itself."""
    return {
        name: value
        for name, value in vars(module).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and issubclass(value, BaseModel)
        and value.__module__ == CONTRACTS_MODULE
    }


def validity_contract(import_app_module: Callable[[str], ModuleType | None]) -> type[BaseModel]:
    """E0-12's comment-validity contract, matched by a word from the task's name.

    Imported through the same `import_app_module` call the task is, so the class
    this compares against is the class the task's own module imported. Two
    imports of `app.ai.contracts` produce two different class objects, and an
    `isinstance` across them is false for a reason that has nothing to do with the
    criterion.
    """
    module = require_module(
        import_app_module,
        CONTRACTS_MODULE,
        "'the comment-validity task implemented end to end against the E0-12 contract' — "
        "E0-12 ships `backend/app/ai/contracts.py` and it must still be there.",
    )
    models = contract_models(module)
    matches = {
        name: model
        for name, model in models.items()
        if any(fragment in normalised(name) for fragment in ("validity", "valid"))
    }
    if len(matches) != 1:
        pytest.fail(
            f"`{CONTRACTS_MODULE}` has {len(matches)} models for the comment-validity task "
            f"({sorted(matches)}); it defines {sorted(models)}. "
            "`tests/unit/test_ai_contracts.py` owns that criterion — this file needs exactly one "
            "so it has something to compare a returned object against."
        )
    return next(iter(matches.values()))


def bare(annotation: Any) -> Any:
    """An annotation with `Annotated[...]` metadata and an optional `None` removed."""
    while hasattr(annotation, "__metadata__"):
        annotation = annotation.__origin__
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        arguments = [
            argument for argument in typing.get_args(annotation) if argument is not type(None)
        ]
        if len(arguments) == 1:
            return bare(arguments[0])
    return annotation


def verdict_field(contract: type[BaseModel]) -> tuple[str, type[enum.Enum]]:
    """The name of the field carrying the verdict, and the enum it is drawn from."""
    candidates: list[tuple[str, type[enum.Enum]]] = []
    for name, model_field in contract.model_fields.items():
        annotation = bare(model_field.annotation)
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            candidates.append((name, annotation))
    if not candidates:
        pytest.fail(
            f"No field on `{contract.__name__}` is annotated with an enum, so this file cannot "
            "write a verdict into a provider payload or read one out of a result. E0-12's "
            "criterion 1 owns that; `tests/unit/test_ai_contracts.py` is where it fails."
        )
    if len(candidates) > 1:
        named = [entry for entry in candidates if normalised(entry[0]) in VERDICT_FIELD_NAMES]
        if len(named) == 1:
            return named[0]
        pytest.fail(
            f"`{contract.__name__}` has more than one enum-typed field "
            f"({[name for name, _ in candidates]}) and this cannot tell which carries the "
            "verdict. `VERDICT_FIELD_NAMES` in this file is the one line that changes."
        )
    return candidates[0]


def spellings(member: enum.Enum) -> set[str]:
    """The ways one enum member could be spelling a verdict from §7.4's table."""
    found = {member.name.lower().replace("_", "-")}
    if isinstance(member.value, str):
        found.add(member.value.lower().replace("_", "-"))
    return found


def verdict_member(verdicts: type[enum.Enum], token: str) -> enum.Enum:
    """The member of `verdicts` that spells `token`, or a failure saying it has none."""
    matches = [member for member in verdicts if token in spellings(member)]
    if len(matches) != 1:
        pytest.fail(
            f"`{verdicts.__name__}` offers {[member.name for member in verdicts]} with values "
            f"{[member.value for member in verdicts]}, which does not carry exactly one "
            f"{token!r}. §7.4 gives comment validity the output "
            "`substantive / insufficient / nonsense`, and this file needs those members to write "
            "a provider answer and to say what the fail-open floor should have decided."
        )
    return matches[0]


def wire_value(member: enum.Enum) -> Any:
    """The token a verdict is spelled as outside Python (ADR 0030)."""
    return member.value if isinstance(member.value, str | int | float | bool) else member.name


def stored_text(value: Any) -> str:
    """One column value as text, with an enum read as the token it stores.

    A verdict column typed `Enum(ValidityVerdict)` hands SQLAlchemy Core the
    member rather than the string, and `str()` of a member is
    `ValidityVerdict.SUBSTANTIVE` — which matches nothing and would report a row
    correctly carrying `substantive` as a row missing its verdict. ADR 0030 makes
    the member's value "the token stored, serialised and compared everywhere
    outside Python", so that is what is compared.
    """
    if isinstance(value, enum.Enum):
        return str(wire_value(value))
    return str(value)


def audit_names(kind: str) -> tuple[str, ...]:
    return PROMPT_VERSION_NAMES if kind == "prompt_version" else MODEL_ID_NAMES


def audit_field_names(contract: type[BaseModel]) -> set[str]:
    """Field names on the contract that carry one of the two audit values."""
    wanted = set(PROMPT_VERSION_NAMES) | set(MODEL_ID_NAMES)
    return {name for name in contract.model_fields if normalised(name) in wanted}


def provider_payload(contract: type[BaseModel], verdict: enum.Enum) -> dict[str, Any]:
    """A JSON-ready object holding the task's own output and nothing else.

    ADR 0031: "The gateway supplies both values; the model never reports them",
    and "the prompt tells the provider to return the task's output alone". So the
    audit fields are deliberately absent from what the stub answers — a gateway
    that expected the model to supply them would fail validation here, which is
    the ADR's decision asserted rather than assumed.

    A required field this cannot build a value for stops the test saying so, so a
    fixture that cannot construct its subject is never read as a gateway that
    refused a valid answer (`docs/MISTAKES.md` entry 13).
    """
    verdict_name, _ = verdict_field(contract)
    audit = audit_field_names(contract)
    payload: dict[str, Any] = {verdict_name: wire_value(verdict)}

    for name, model_field in contract.model_fields.items():
        if name in payload or name in audit:
            continue
        if not model_field.is_required():
            continue
        annotation = bare(model_field.annotation)
        if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
            member = next(iter(annotation), None)
            if member is None:
                pytest.fail(f"`{contract.__name__}.{name}` is an empty enum.")
            payload[name] = wire_value(member)
        elif annotation is str:
            payload[name] = "e0-13 stub provider answer"
        elif annotation is bool:
            payload[name] = True
        elif annotation is int:
            payload[name] = 1
        elif annotation is float:
            payload[name] = 0.5
        elif typing.get_origin(annotation) in (list, tuple, set):
            payload[name] = []
        else:
            pytest.fail(
                f"This file could not build a provider answer for `{contract.__name__}.{name}`, "
                f"annotated {model_field.annotation!r}. That is a gap in this module rather than "
                "a failed criterion — teach `provider_payload` the type and the assertion below "
                "runs again."
            )
    return payload


def value_at(subject: Any, names: tuple[str, ...], depth: int = 3) -> tuple[str, Any] | None:
    """One named value on a returned object, however it is carried or nested.

    A path rather than a name, because E0-12 asks for composition: the two audit
    values may legitimately sit on a shared sub-model every contract embeds.
    """
    if depth <= 0 or subject is None:
        return None
    fields = getattr(type(subject), "model_fields", None)
    if not isinstance(fields, dict):
        return None
    for name in fields:
        if normalised(name) in names:
            return name, getattr(subject, name)
    for name in fields:
        below = value_at(getattr(subject, name, None), names, depth - 1)
        if below is not None:
            return f"{name}.{below[0]}", below[1]
    return None


def require_audit_value(result: Any, kind: str, label: str) -> tuple[str, Any]:
    """The prompt version or model ID a result carries, or a failure saying it has none."""
    found = value_at(result, audit_names(kind))
    if found is None:
        pytest.fail(
            f"The object the validity task returned carries no {label}: it is {result!r}. "
            "E0-13's first acceptance criterion is 'a validated contract object with prompt "
            "version and model ID populated', and SPEC §7.4 rests the single-shot boundary on "
            "exactly that — 'a specific prompt version and model ID produced a specific "
            "classification for a specific comment'. If it is carried under a word this file's "
            "name lists do not reach, those lists are the one line that changes."
        )
    return found


# ---------------------------------------------------------------------------
# Calling the task
# ---------------------------------------------------------------------------


def role_of(parameter_name: str) -> str | None:
    """Which of `CALL_ROLES` a parameter called `parameter_name` wants."""
    best: tuple[int, str] | None = None
    for role, aliases in CALL_ROLES.items():
        for alias in aliases:
            if (parameter_name == alias or parameter_name.endswith(f"_{alias}")) and (
                best is None or len(alias) > best[0]
            ):
                best = (len(alias), role)
    return None if best is None else best[1]


def call_task(task: Any, **available: Any) -> Any:
    """Call `task`, filling each parameter from the values offered, by name.

    Binding by parameter name and never by `try: ... except TypeError:` is
    deliberate, and `tests/conftest.py` gives the reason at length: a helper that
    retried call shapes until one stopped raising would swallow a `TypeError`
    raised *inside* the task and report a design the ticket never chose as
    working. A parameter no offered role matches stops the test with a message
    naming it, which is an interface question for the ticket.

    A coroutine function is awaited, because ADR 0013 makes the session
    synchronous but says nothing about the gateway, and choosing here would decide
    it from the test side.

    One narrow accommodation, the same one `SectionCodeService.call` makes: a
    task with a single parameter is handed the comment whatever that parameter is
    called. `classify(raw)` and `classify(comment)` are the same deliverable, and
    the parameter's name is not something E0-13 decides.
    """
    signature = inspect.signature(task)
    parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]

    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    if len(parameters) == 1 and role_of(parameters[0].name) is None:
        only = available["comment"]
        if parameters[0].kind is parameters[0].POSITIONAL_ONLY:
            positional.append(only)
        else:
            keyword[parameters[0].name] = only
    else:
        for parameter in parameters:
            role = role_of(parameter.name)
            if role is None or role not in available:
                if parameter.default is not parameter.empty:
                    continue
                pytest.fail(
                    f"`{getattr(task, '__qualname__', task)}` requires a parameter "
                    f"`{parameter.name}` that this test has nothing to fill from. It is offering "
                    f"{sorted(available)}. E0-13 says the task takes a comment and spells no "
                    "signature, so a parameter outside that is an interface question for the "
                    "ticket — add the role to `CALL_ROLES` in this file once the pull request "
                    "says what it is for."
                )
            if parameter.kind is parameter.POSITIONAL_ONLY:
                positional.append(available[role])
            else:
                keyword[parameter.name] = available[role]

    outcome = task(*positional, **keyword)
    if inspect.isawaitable(outcome):
        return asyncio.run(_awaited(outcome))
    return outcome


async def _awaited(outcome: Any) -> Any:
    return await outcome


def run_validity(
    import_app_module: Callable[[str], ModuleType | None],
    session: Any,
    comment: str,
) -> Any:
    """Run the comment-validity task over `comment` and hand back what it returned."""
    task = validity_task(import_app_module)
    return call_task(task, session=session, comment=comment)


# ---------------------------------------------------------------------------
# The loopback guard
# ---------------------------------------------------------------------------


class OffMachineConnectionError(Exception):
    """Raised in place of a socket connection to anything but this machine."""


@contextlib.contextmanager
def only_loopback(monkeypatch: pytest.MonkeyPatch, *permitted: str) -> Iterator[list[Any]]:
    """Refuse every socket connection to an address off this machine.

    Patched at `socket.socket`, which is below every HTTP client in the closure:
    `httpx` reaches the network through `httpcore`, which calls
    `socket.create_connection`, which calls `sock.connect`. A `AF_UNIX` address is
    a string rather than a tuple and is permitted — it reaches no network.

    `permitted` carries the addresses a test legitimately needs off the loopback
    interface, and there is exactly one: the Postgres container, whose host is
    normally `127.0.0.1` and need not be. Naming it here rather than widening the
    rule keeps the guard about the thing it is for.
    """
    attempted: list[Any] = []
    allowed = {"localhost", *permitted}
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def permitted_address(address: Any) -> bool:
        if not isinstance(address, tuple) or not address:
            return True
        host = address[0]
        if not isinstance(host, str):
            return False
        if host in allowed:
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def guard(name: str, original: Any) -> Any:
        def wrapper(self: Any, address: Any) -> Any:
            attempted.append(address)
            if not permitted_address(address):
                raise OffMachineConnectionError(
                    f"socket.{name} to {address!r}, which is not this machine. E0-13's fifth "
                    "acceptance criterion: 'No test makes a live network call.'"
                )
            return original(self, address)

        return wrapper

    monkeypatch.setattr(socket.socket, "connect", guard("connect", original_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guard("connect_ex", original_connect_ex))
    yield attempted


def leaked_fragments(text_value: str, secret: str, size: int = LEAK_FRAGMENT_LENGTH) -> list[str]:
    """Every contiguous run of `secret` of length `size` that appears in `text_value`.

    Searching for the whole secret is the check that misses: a rendering that
    elides the middle of a value can print all but one character and still not
    contain it as a substring. The same helper, for the same reason, as
    `tests/unit/test_config_settings.py`.
    """
    windows = (secret[start : start + size] for start in range(len(secret) - size + 1))
    return sorted({window for window in windows if window in text_value})


def json_strings(document: Any) -> list[str]:
    """Every string in a parsed JSON document, keys included.

    Keys as well as values, because a provider request carries text in both and
    because the shape-violation tests below send a comment *as* a set of keys.
    """
    if isinstance(document, Mapping):
        found: list[str] = []
        for key, value in document.items():
            if isinstance(key, str):
                found.append(key)
            found.extend(json_strings(value))
        return found
    if isinstance(document, list):
        return [text_value for item in document for text_value in json_strings(item)]
    return [document] if isinstance(document, str) else []


def sent_text(call: Received) -> str:
    """Everything one request said, read out of the parsed body rather than the raw text.

    Parsed, because the body is JSON: a prompt line containing an apostrophe or a
    quotation mark reaches the wire escaped, and a search over the raw text would
    report it missing. The raw body is the fallback for a request that is not JSON
    at all, so a search never silently has nothing to look at.
    """
    strings = json_strings(call.payload)
    return "\n".join(strings) if strings else call.body


def all_sent_text(provider: StubProvider) -> str:
    """Everything every request said, for a search that does not care which call carried it."""
    return "\n".join(sent_text(call) for call in provider.calls)


def columns_holding(row: Mapping[str, Any], value: str) -> list[str]:
    """The columns of `row` whose stored value reads as `value`.

    Used to find where a row keeps the two audit values without naming the
    columns: E0-13 spells the table and none of its columns, so the way to read a
    stored prompt version is to look for the one the returned object carried.
    """
    return sorted(name for name, held in row.items() if stored_text(held) == value)


def exception_chain(failure: BaseException) -> list[BaseException]:
    """`failure` and everything it was raised from, `__cause__` and `__context__` alike."""
    chain: list[BaseException] = []
    current: BaseException | None = failure
    while current is not None and not any(link is current for link in chain):
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


# ---------------------------------------------------------------------------
# The classification table
# ---------------------------------------------------------------------------


def classification_table(metadata_tables: dict[str, Any]) -> Any:
    """The `classification` table, or a failure naming the deliverable."""
    table = metadata_tables.get(CLASSIFICATION_TABLE)
    if table is None:
        pytest.fail(
            f"There is no `{CLASSIFICATION_TABLE}` table on the metadata `migrations/env.py` "
            f"autogenerates against (it holds {sorted(metadata_tables)}). E0-13's scope: 'A "
            "minimal `classification` table storing the verdict with prompt version and model "
            "ID, append-only (re-runs create new rows, per §8).' "
            "`tests/unit/test_ai_models_registered.py` owns the registration half of this."
        )
    return table


def primary_key_of(table: Any) -> Any:
    """The one primary key column (ADR 0016 makes every primary key a single uuid)."""
    columns = list(table.primary_key.columns)
    if len(columns) != 1:
        pytest.fail(
            f"`{table.name}` has {len(columns)} primary key columns "
            f"({[column.name for column in columns]}). ADR 0016 makes every primary key one uuid "
            "with a server default, and these tests address rows by it."
        )
    return columns[0]


@dataclass
class ClassificationRows:
    """Whatever is in `classification`, read on both connections a write could land on.

    The task may take the session it is handed or open one of its own through
    `app.db` — E0-13 does not say which, and a reader that consulted only one
    would report an empty table for the other. So both are read and the results
    unioned, and the teardown removes whatever was *committed*, which is the only
    half a rollback does not already undo.
    """

    session: Any
    engine: Any
    table: Any

    def keys(self) -> set[Any]:
        column = primary_key_of(self.table)
        statement = select(column)
        seen = set(self.session.execute(statement).scalars())
        with self.engine.connect() as probe:
            seen |= set(probe.execute(statement).scalars())
        return seen

    def row(self, key: Any) -> Mapping[str, Any] | None:
        column = primary_key_of(self.table)
        statement = select(self.table).where(column == key)
        found = self.session.execute(statement).mappings().first()
        if found is not None:
            return dict(found)
        with self.engine.connect() as probe:
            found = probe.execute(statement).mappings().first()
        return dict(found) if found is not None else None


@pytest.fixture
def classification_rows(
    db_session: Any, migrated_engine: Any, metadata_tables: dict[str, Any]
) -> Iterator[ClassificationRows]:
    """A reader over `classification`, with the database left as it was found."""
    table = classification_table(metadata_tables)
    rows = ClassificationRows(session=db_session, engine=migrated_engine, table=table)
    before = rows.keys()
    try:
        yield rows
    finally:
        column = primary_key_of(table)
        with migrated_engine.connect() as connection:
            committed = set(connection.execute(select(column)).scalars())
            added = committed - before
            if added:
                connection.execute(table.delete().where(column.in_(added)))
                connection.commit()


# ---------------------------------------------------------------------------
# The round trip
# ---------------------------------------------------------------------------


def well_formed(contract: type[BaseModel], token: str) -> Answer:
    """A provider answer carrying the task's output for `token` and nothing else."""
    _, verdicts = verdict_field(contract)
    member = verdict_member(verdicts, token)
    return Answer(content=json.dumps(provider_payload(contract, member)))


def test_a_validity_call_against_the_stub_returns_the_validity_contract(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """Criterion 1, first half: one call in, one validated contract object out.

    The type is asserted rather than the shape, because §7.4 makes that one class
    the runtime contract, the API response schema and the eval fixture at once —
    a task returning a dict, a bare enum member or a second model of its own
    satisfies "something came back" and satisfies none of the three uses the spec
    puts the object to. E0-12's scope forbids the fork in the same words: "Do not
    fork these models for API or eval use. If an API response needs a different
    shape, compose rather than copy."

    The stub is scripted with the *verdict the model chose*, not with the one the
    character heuristic would reach, so a gateway that never called the provider
    at all cannot pass this by falling straight through to the floor.
    """
    contract = validity_contract(import_app_module)
    stub_provider.script(well_formed(contract, INSUFFICIENT_VERDICT))

    result = run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)

    assert stub_provider.calls, (
        "The validity task returned without sending the stub provider anything. E0-13's first "
        f"criterion is a round trip: `AI_PROVIDER_BASE_URL` was {stub_provider.base_url}, and a "
        "task that answers without asking is not the thing this ticket exists to build."
    )
    assert isinstance(result, contract), (
        f"The validity task returned {result!r}, which is not a `{contract.__name__}`. E0-13's "
        "first criterion: 'A validity call against the stub provider returns a validated "
        "contract object.' §7.4 makes that one model the runtime contract, the API response "
        "schema and the eval fixture, so a dict or a second shape is not the same deliverable."
    )

    name, verdicts = verdict_field(contract)
    expected = verdict_member(verdicts, INSUFFICIENT_VERDICT)
    assert getattr(result, name) is expected, (
        f"The provider answered {INSUFFICIENT_VERDICT!r} and the task returned "
        f"{getattr(result, name)!r}. The verdict the model produced is the verdict the round "
        "trip has to carry — §3.3 makes substantiveness 'the classifier's call'."
    )


def test_the_returned_object_carries_the_prompt_version_and_the_model_that_produced_it(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """Criterion 1, second half: prompt version and model ID populated.

    Both are asserted against something outside the object rather than merely for
    being non-empty, because "populated" is satisfied by two strings nobody can
    resolve. §7.4: "the threat/self-harm classifier must be auditable, meaning a
    specific prompt version and model ID produced a specific classification for a
    specific comment", and a version naming no file and a model ID naming no model
    reproduce nothing.

    The prompt version is checked against the prompts on disk because
    [ADR 0031](../../docs/adr/0031-every-task-contract-carries-the-prompt-version-and-model-id.md)
    decides what it is: "`prompt_version` is the prompt file's path stem —
    `validity.v1` — so the stored value names exactly one immutable file with no
    lookup table between them."

    The model ID is checked against the configured model, which the stub also
    answers as, so a gateway taking it from its configuration and one taking it
    from the provider's response are both correct here and neither is chosen from
    the test side.
    """
    contract = validity_contract(import_app_module)
    stub_provider.script(well_formed(contract, SUBSTANTIVE_VERDICT))

    result = run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)

    prompt_path, prompt_version = require_audit_value(result, "prompt_version", "prompt version")
    _, model_id = require_audit_value(result, "model_id", "model ID")

    stems = prompt_stems()
    assert stems, (
        f"There are no prompt files under {PROMPTS_DIR}, so this test would report any recorded "
        "prompt version as unresolvable whatever the truth is. "
        "`tests/unit/test_prompt_directory_layout.py` owns that failure."
    )
    assert str(prompt_version) in stems, (
        f"The task recorded a prompt version of {prompt_version!r} (on `{prompt_path}`), and no "
        f"file under {PROMPTS_DIR} has that path stem — the stems there are {sorted(stems)}. "
        "ADR 0031: the recorded value is the prompt file's path stem, so it names exactly one "
        "immutable file. A version naming no file cannot reproduce the classification it is "
        "attached to, which is the whole of what §7.4 asks the value for."
    )
    assert STUB_MODEL_ID in str(model_id), (
        f"The task recorded a model ID of {model_id!r}, which does not name the model that "
        f"answered — `AI_MODEL_NAME` was {STUB_MODEL_ID!r} and the stub answered as it. §9.3's "
        "eval floors compare runs of different models, so a model ID that does not identify one "
        "makes the comparison meaningless."
    )


def prompt_stems() -> set[str]:
    """The path stems of every prompt file on disk, as ADR 0031 spells a version."""
    if not PROMPTS_DIR.is_dir():
        return set()
    stems: set[str] = set()
    for path in PROMPTS_DIR.rglob("*"):
        if not path.is_file() or path.name.lower() in NON_PROMPT_NAMES:
            continue
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(PROMPTS_DIR)
        stems.add(path.name.removesuffix(path.suffix))
        stems.add(relative.as_posix().removesuffix(path.suffix))
    return stems


def test_the_returned_object_is_usable_as_an_eval_fixture(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """E0-13's definition of done: "the contract must be usable as an eval fixture".

    E0-12 asserts that each contract round-trips a payload this suite builds.
    What is new here, and what §7.4 actually asks for, is that the object *a task
    returned* is one: "The same models serve three purposes without duplication:
    the runtime contract, the API response schema, and the eval fixture in §9.3 —
    so an eval case is a typed object, not a string comparison."

    An eval set is JSON on disk before it is anything else, and §6.1's drift panel
    grows it from admin overrides, so the case has to survive being written out
    and read back. The near miss is a field whose validation alias serialisation
    does not use: the model then refuses its own output, and every fixture in the
    set has to be written in whichever spelling happens to work.
    """
    contract = validity_contract(import_app_module)
    stub_provider.script(well_formed(contract, SUBSTANTIVE_VERDICT))

    result = run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)
    assert isinstance(result, contract), (
        f"The validity task returned {result!r} rather than a `{contract.__name__}`, so there is "
        "no eval case to round-trip. The first test in this module owns that failure."
    )

    emitted = result.model_dump_json()
    again = contract.model_validate_json(emitted)

    assert again == result, (
        f"What the validity task returned did not survive a round trip through JSON. Out: "
        f"{emitted}. Back: {again!r}. §9.3 builds every eval case out of exactly this — 'Cases "
        "are typed objects built from the same Pydantic contracts the tasks return (§7.4), so a "
        "contract change breaks its evals at type-check time rather than silently passing' — and "
        "a case that loads to a different object compares two things that were never the same."
    )


def prompt_file_named(version: str) -> Path | None:
    """The prompt file whose path stem is `version` (ADR 0031), if there is one."""
    if not PROMPTS_DIR.is_dir():
        return None
    for path in sorted(PROMPTS_DIR.rglob("*")):
        if not path.is_file() or path.name.lower() in NON_PROMPT_NAMES:
            continue
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(PROMPTS_DIR).as_posix()
        if version in (path.name.removesuffix(path.suffix), relative.removesuffix(path.suffix)):
            return path
    return None


# The shortest line of a prompt this file will treat as evidence that the prompt
# was sent, and the marks that say a line is a template rather than text. A line
# carrying a placeholder is rewritten on substitution, so requiring it verbatim
# would fail against a correct gateway; a short line is too likely to appear in a
# request for some other reason. **This suite's choice**, both of them.
MINIMUM_QUOTABLE_LINE = 24
PLACEHOLDER_MARKS = ("{", "}", "$", "<", ">", "%")


def quotable_lines(text_value: str) -> list[str]:
    """The lines of a prompt that a request carrying that prompt should hold verbatim."""
    return sorted(
        (
            line.strip()
            for line in text_value.splitlines()
            if len(line.strip()) >= MINIMUM_QUOTABLE_LINE
            and not any(mark in line for mark in PLACEHOLDER_MARKS)
        ),
        key=len,
        reverse=True,
    )


def test_the_students_comment_reaches_the_provider(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """ "A comment goes in" — the half of the round trip nothing here was asserting.

    E0-13's context states the exit criterion in one sentence: "a comment goes in,
    a validated Pydantic object comes back, and the prompt version and model ID
    are recorded". Every test in this module covered the second and third clauses.
    None covered the first, and the stub answers from its script whatever it is
    sent — so setting the prompt to the empty string, or leaving the placeholder
    unsubstituted so the marker ships in place of the comment, passed the whole
    suite. The classification then describes a comment the model never saw, which
    §7.4's audit sentence — "a specific prompt version and model ID produced a
    specific classification for **a specific comment**" — makes a false record
    rather than a wrong answer.

    The comment carries a nonce so that a match is evidence. An ordinary English
    sentence could plausibly appear in a prompt template, and then "the comment
    was sent" would be satisfied by a request that carried the prompt and dropped
    the comment.

    The search is over the parsed request body rather than its raw text, because
    the body is JSON and a comment containing a quotation mark reaches the wire
    escaped.
    """
    contract = validity_contract(import_app_module)
    stub_provider.script(well_formed(contract, INSUFFICIENT_VERDICT))

    run_validity(import_app_module, db_session, TRACEABLE_COMMENT)

    assert stub_provider.calls, (
        "The validity task sent the stub no request at all, so this test could not look at what "
        "was in one. The first test in this module owns that failure."
    )
    assert TRACEABLE_COMMENT in all_sent_text(stub_provider), (
        f"The comment the task was given does not appear in anything it sent the provider. It "
        f"asked for {TRACEABLE_COMMENT!r}; the requests carried "
        f"{all_sent_text(stub_provider)!r}. A classification produced without the comment in the "
        "request is a verdict about nothing, and §7.4's audit record — 'a specific prompt version "
        "and model ID produced a specific classification for a specific comment' — then names a "
        "comment that was never sent."
    )


def test_the_versioned_prompt_reaches_the_provider(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """The prompt whose version gets recorded is the text that was actually sent.

    The sibling of the test above, and the one that catches an empty prompt: with
    the comment appended to nothing, the comment still reaches the provider, the
    contract still validates, and the recorded `prompt_version` still names a file
    on disk. Everything about that is green and the file's contents played no part
    in the classification — which makes the stored version a citation of a
    document that was never used, and §9.3's eval sets incomparable across a
    prompt change for the same reason ADR 0032 makes a prompt file immutable.

    The prompt is found from the version the call itself recorded rather than
    named here, so this follows whichever prompt the task chose. The longest line
    carrying no template marker is what must appear verbatim: a line with a
    placeholder in it is rewritten on substitution, and requiring it would fail
    against a correct gateway.

    **What it does not cover**, since it reads stronger than it is: it asserts the
    prompt's text was sent, not that it was sent as a system instruction, and not
    that it was sent unmodified. A gateway that reflows the prompt's whitespace
    would fail this for a reason that is not a defect; that is a fixture question
    and the docstring is where it gets raised rather than the assertion where it
    gets weakened.
    """
    contract = validity_contract(import_app_module)
    stub_provider.script(well_formed(contract, INSUFFICIENT_VERDICT))

    result = run_validity(import_app_module, db_session, TRACEABLE_COMMENT)
    _, prompt_version = require_audit_value(result, "prompt_version", "prompt version")

    prompt_path = prompt_file_named(str(prompt_version))
    assert prompt_path is not None, (
        f"The task recorded a prompt version of {prompt_version!r} and no file under "
        f"{PROMPTS_DIR} has that path stem, so this test has no text to look for. "
        "`test_the_returned_object_carries_the_prompt_version_and_the_model_that_produced_it` "
        "owns that failure."
    )

    lines = quotable_lines(prompt_path.read_text(encoding="utf-8"))
    assert lines, (
        f"{prompt_path} holds no line of at least {MINIMUM_QUOTABLE_LINE} characters free of "
        f"{list(PLACEHOLDER_MARKS)}, so this test has nothing it can require verbatim. That is a "
        "gap in this file — or a prompt that is entirely template — rather than a failed "
        "criterion."
    )

    assert lines[0] in all_sent_text(stub_provider), (
        f"The prompt the task recorded as {prompt_version!r} was not sent: its longest plain line, "
        f"{lines[0]!r}, appears nowhere in what the provider received "
        f"({all_sent_text(stub_provider)!r}). §7.4: 'Prompts are versioned in-repo; every "
        "classification stores prompt version and model ID for reproducibility.' A version "
        "recorded against text that took no part in the classification reproduces nothing, and "
        "ADR 0032's immutable prompt file is then a document nobody read."
    )


def test_a_well_formed_first_answer_is_not_followed_by_a_second_call(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """§7.4's single-shot boundary, and the control the retry test below needs.

    "Every task in the table above is one call in, one validated object out — no
    tool use, no planning loop, no iterative retrieval." E0-13's scope repeats it
    as "a hard constraint, not a starting point".

    It is also what stops the retry assertion passing for the wrong reason. That
    test asserts the stub was called more than once, which a gateway sending two
    requests every time satisfies without retrying anything (`docs/MISTAKES.md`
    entry 3). One call for one well-formed answer is the other half of the claim,
    and §3.3's p95 under two seconds is the reason it matters beyond tidiness.
    """
    contract = validity_contract(import_app_module)
    stub_provider.script(well_formed(contract, SUBSTANTIVE_VERDICT))

    run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)

    assert len(stub_provider.calls) == 1, (
        f"One comment produced {len(stub_provider.calls)} requests to the provider "
        f"({[call.path for call in stub_provider.calls]}), and the first answer was well formed. "
        "SPEC §7.4: 'Every task in the table above is one call in, one validated object out — no "
        "tool use, no planning loop, no iterative retrieval. This is deliberate: the validity "
        "check has a p95 < 2s budget that loop variance would break.'"
    )


def test_a_malformed_provider_answer_is_retried_and_the_next_answer_is_returned(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """Criterion 2, first half: a malformed response triggers a retry.

    The stub answers with prose the first time — the most likely thing a model
    does wrong, a sentence where an object was asked for — and with the contract's
    own shape the second. §7.4: "The gateway validates against that model, retries
    on shape violations, and surfaces persistent failures as errors rather than
    letting a malformed classification propagate."

    Two assertions, and the second is the one that says a retry happened rather
    than a first answer having been accepted: the object returned carries the
    verdict from the *second* answer, and the stub saw more than one request. The
    control that a well-formed answer produces exactly one request is the test
    above.
    """
    contract = validity_contract(import_app_module)
    stub_provider.script(
        Answer(content="I think this comment is reasonably substantive, on balance."),
        well_formed(contract, INSUFFICIENT_VERDICT),
    )

    result = run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)

    assert len(stub_provider.calls) > 1, (
        f"The provider answered with prose rather than the contract's shape and the gateway sent "
        f"{len(stub_provider.calls)} request(s) in total, so nothing was retried. E0-13's second "
        "criterion: 'A malformed provider response triggers a retry.'"
    )
    assert isinstance(result, contract), (
        f"After a retry the task returned {result!r} rather than a `{contract.__name__}`. The "
        "retry exists so that a recoverable shape violation still ends in a validated object."
    )
    name, verdicts = verdict_field(contract)
    assert getattr(result, name) is verdict_member(verdicts, INSUFFICIENT_VERDICT), (
        f"The second answer carried {INSUFFICIENT_VERDICT!r} and the task returned "
        f"{getattr(result, name)!r}. A retry that discards the answer it retried for is not a "
        "retry."
    )


def test_a_persistently_malformed_provider_answer_raises_rather_than_returning_a_partial_object(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """Criterion 2, second half: a persistent shape violation is an error.

    The stub never answers correctly, so whatever the retry budget is, it runs
    out. §7.4 is explicit about the alternative and why it is refused: the gateway
    "surfaces persistent failures as errors rather than letting a malformed
    classification propagate". A partially-populated object here is a stored
    verdict nobody produced.

    **Which exception is not asserted, and what is.** E0-13 names no error type,
    so requiring one would pin an interface the ticket leaves open. What is
    required is that the failure is a *surfaced* one — a project error or the
    `ValidationError` the contract raised — rather than a `TypeError` or an
    `AttributeError`, which is the gateway falling over rather than reporting.
    `tests/conftest.py`'s `raised_by_the_service` draws the same line for E0-07,
    for the same reason: an unguarded parse failure is not something a caller can
    catch on purpose.
    """
    stub_provider.script(Answer(content='{"verdict": "spicy-take"}'))

    try:
        result = run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)
    except FELL_OVER as failure:
        pytest.fail(
            f"A persistently malformed provider answer raised {failure!r}, which is the gateway "
            "falling over rather than surfacing a failure. §7.4 asks it to surface persistent "
            "failures as errors — a caller on §3.3's submit path has to be able to catch this "
            "one deliberately in order to fall open."
        )
    except Exception:
        return

    pytest.fail(
        f"The provider answered with a verdict outside the closed set on every attempt and the "
        f"task returned {result!r} rather than raising. E0-13's second criterion: 'a "
        "persistently malformed one raises rather than returning a partial object'. §7.4: the "
        "gateway 'surfaces persistent failures as errors rather than letting a malformed "
        f"classification propagate'. The stub was asked {len(stub_provider.calls)} time(s)."
    )


def test_a_provider_that_supplies_its_own_audit_fields_is_refused_rather_than_believed(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """ADR 0031's instruction to this ticket, and the sharpest edge in it.

    The record is explicit, and it was corrected once already for claiming the
    contract closed this: "`extra='forbid'` refuses keys the model does not
    *declare*. `prompt_version` and `model_id` are declared fields, so a
    provider-supplied value is not extra — it is the field, filled in by the wrong
    party, and it validates and round-trips cleanly." So the check has to be in
    the gateway: "The gateway must reject a provider payload that contains either
    key, *before* merging anything into it, and treat that as the shape violation
    §7.4 has it retry on. Not overwrite quietly: a model returning an audit field
    is a model doing something it was told not to do, and on the moderation path
    the value it invented would otherwise land in a §6.2 audit record."

    Quiet overwriting is the near miss, and it is why this test does not stop at
    "the liar's values are not in the result". A gateway that merges its own
    values over the provider's produces a clean-looking object every time, and
    which value survives then depends on a merge order nothing constrains — so
    the same payload with the keys in the other order is a fiction that ships.
    """
    contract = validity_contract(import_app_module)
    _, verdicts = verdict_field(contract)
    payload = provider_payload(contract, verdict_member(verdicts, SUBSTANTIVE_VERDICT))
    liar = dict(payload)
    for name in contract.model_fields:
        if normalised(name) in PROMPT_VERSION_NAMES:
            liar[name] = LIAR_PROMPT_VERSION
        if normalised(name) in MODEL_ID_NAMES:
            liar[name] = LIAR_MODEL_ID

    assert liar != payload, (
        f"`{contract.__name__}` declares neither a prompt version nor a model ID under any name "
        "this file knows, so there is no audit field for a provider to usurp and this test would "
        "pass without having sent one. E0-12's criterion 2 owns that."
    )

    stub_provider.script(Answer(content=json.dumps(liar)))

    try:
        result = run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)
    except FELL_OVER as failure:
        pytest.fail(
            f"A provider payload carrying its own audit fields raised {failure!r}, which is the "
            "gateway falling over rather than refusing the payload. ADR 0031 asks for the shape "
            "violation §7.4 has it retry on, which is something a caller can catch."
        )
    except Exception:
        return

    _, prompt_version = require_audit_value(result, "prompt_version", "prompt version")
    _, model_id = require_audit_value(result, "model_id", "model ID")
    pytest.fail(
        f"The provider returned its own audit fields — prompt version {LIAR_PROMPT_VERSION!r} and "
        f"model ID {LIAR_MODEL_ID!r} — and the gateway returned {result!r} instead of refusing "
        f"the payload (its recorded pair is {prompt_version!r} / {model_id!r}). ADR 0031: 'The "
        "gateway must reject a provider payload that contains either key, before merging anything "
        "into it, and treat that as the shape violation §7.4 has it retry on.' Overwriting them "
        "quietly is not enough: it leaves which value survives depending on a merge order nothing "
        "asserts, and on the moderation path the value the model invented would land in a §6.2 "
        "audit record."
    )


# ---------------------------------------------------------------------------
# Failing open
# ---------------------------------------------------------------------------


def timed_out(delay: float = PROVIDER_DELAY_SECONDS) -> Answer:
    """A provider that holds the request far longer than any per-task timeout."""
    return Answer(content='{"verdict": "nonsense"}', delay=delay)


def test_a_provider_timeout_does_not_raise_so_the_submission_can_be_accepted(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """Criterion 3: a simulated timeout returns a result and does not raise.

    SPEC §3.3: "Classifier latency budget: p95 < 2s; on provider timeout, the
    heuristic floor applies and the submission is accepted, then classified async
    (fail open, never block a student on an outage)." E0-13's scope says the same
    in the imperative — "Never block a student on a provider outage" — and adds
    that E2 wires it into the submit path while E0 proves the gateway behaves this
    way.

    Two assertions, because "it returned" on its own is satisfied by a gateway
    that waited twenty seconds for the provider and then used its answer, which is
    precisely the blocked student this rule exists to prevent. So the call must
    also come back **before** the provider would have answered.
    """
    contract = validity_contract(import_app_module)
    stub_provider.script(timed_out())

    started = time.monotonic()
    try:
        result = run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)
    except Exception as failure:
        pytest.fail(
            f"A provider that did not answer made the validity task raise {failure!r}. E0-13's "
            "third criterion: 'A simulated provider timeout returns the heuristic-floor result "
            "and does not raise — the fail-open path, asserted by test.' §3.3: the submission is "
            "accepted and classified async; a raise here is a student blocked by somebody else's "
            "outage."
        )
    elapsed = time.monotonic() - started

    assert isinstance(result, contract), (
        f"On a provider timeout the task returned {result!r} rather than a "
        f"`{contract.__name__}`. The floor still has to produce the contract: §3.3 gates "
        "participation on the verdict, and E2's submit path has one shape to read."
    )
    assert elapsed < PROVIDER_DELAY_SECONDS - FAIL_OPEN_MARGIN_SECONDS, (
        f"The validity task took {elapsed:.1f}s against a provider scripted to answer only after "
        f"{PROVIDER_DELAY_SECONDS:.0f}s, so it waited for the answer rather than timing out. "
        "E0-13's scope: 'per-task timeout and retry'. §3.3 gives the synchronous check a p95 "
        "under two seconds, and a fail-open path that fires after the student has already given "
        "up has failed closed."
    )


@pytest.mark.parametrize(
    ("comment", "token"),
    [
        (SUBSTANTIVE_COMMENT, SUBSTANTIVE_VERDICT),
        (INSUFFICIENT_COMMENT, INSUFFICIENT_VERDICT),
    ],
    ids=["long-enough", "too-short"],
)
def test_a_provider_timeout_falls_back_to_the_character_heuristic(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
    comment: str,
    token: str,
) -> None:
    """Criterion 3: the timeout returns *the heuristic-floor result*, not just a result.

    Both directions, and the second is the one that makes the first mean
    something: a floor that answers `substantive` to everything satisfies the long
    case and is not a heuristic — it is participation credit for "adfasdfa"
    whenever the provider is down. §3.3 names the rule the floor uses: "The
    prototype's ≥25-character heuristic is a placeholder only; production
    substantiveness is the classifier's call, with the character heuristic
    retained solely as the fail-open floor below."

    The stub is scripted to answer `nonsense` after its delay, so a gateway that
    waited for the provider fails both cases rather than passing the short one by
    coincidence.
    """
    contract = validity_contract(import_app_module)
    stub_provider.script(timed_out())

    result = run_validity(import_app_module, db_session, comment)

    name, verdicts = verdict_field(contract)
    expected = verdict_member(verdicts, token)
    assert getattr(result, name) is expected, (
        f"With the provider unreachable, a {len(comment)}-character comment was classified "
        f"{getattr(result, name)!r} rather than {expected!r}. §3.3 keeps the ≥"
        f"{HEURISTIC_MINIMUM_CHARACTERS}-character heuristic 'solely as the fail-open floor', so "
        "the floor's answer is decided by the length of the comment and by nothing else. A floor "
        "that always says substantive hands participation credit to every comment during an "
        "outage; one that always says insufficient penalises every student for it."
    )


def test_the_character_floor_takes_effect_at_the_length_the_spec_names(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """§3.3's floor is "≥25 characters", and this is the boundary asserted as written.

    Separated from the two clear-cut cases above because the boundary is where a
    placeholder rule is most likely to have been transcribed as `>` — and the
    direction of that error matters: it withholds credit from the shortest comment
    the spec says counts, during an outage the student did not cause.
    """
    assert len(BOUNDARY_COMMENT) == HEURISTIC_MINIMUM_CHARACTERS, (
        f"The boundary comment in this file is {len(BOUNDARY_COMMENT)} characters rather than "
        f"{HEURISTIC_MINIMUM_CHARACTERS}, so this test would be checking the wrong boundary. That "
        "is a defect in this file rather than a failed criterion."
    )

    contract = validity_contract(import_app_module)
    name, verdicts = verdict_field(contract)
    stub_provider.script(timed_out())

    at_the_boundary = run_validity(import_app_module, db_session, BOUNDARY_COMMENT)
    below = run_validity(import_app_module, db_session, BOUNDARY_COMMENT[:-1])

    assert getattr(at_the_boundary, name) is verdict_member(verdicts, SUBSTANTIVE_VERDICT), (
        f"A comment of exactly {HEURISTIC_MINIMUM_CHARACTERS} characters was classified "
        f"{getattr(at_the_boundary, name)!r} by the fail-open floor. §3.3 writes the rule as "
        f"'the ≥{HEURISTIC_MINIMUM_CHARACTERS}-character heuristic', so the boundary counts."
    )
    assert getattr(below, name) is verdict_member(verdicts, INSUFFICIENT_VERDICT), (
        f"A comment one character below {HEURISTIC_MINIMUM_CHARACTERS} was classified "
        f"{getattr(below, name)!r} by the fail-open floor, so the floor is not the rule §3.3 "
        "names — or it is not looking at the comment at all."
    )


def test_a_floored_classification_is_recorded_rather_than_skipped(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
    classification_rows: ClassificationRows,
) -> None:
    """A provider timeout still leaves a row. This is the half nothing here asserted.

    E0-13's definition of done sends the security review after one distinction:
    the fail-open path must fail open "in the intended sense — accepting the
    submission — rather than open in the sense of skipping a safety classification
    silently". A floored submission that writes nothing at all is the second of
    those exactly, and until this test existed the whole suite passed against it:
    moving the classification write inside the gateway's `try` was run as a
    mutation and every test stayed green, because every timeout test asserted on
    the object returned and only the answered-path tests read a row.

    That silence is the expensive kind. §3.3 has the submission accepted and "then
    classified async", and the thing that finds it later is the record saying a
    model was never asked. No row means nothing to find, and the comment is
    counted as validated on a character count nobody revisits.
    """
    stub_provider.script(timed_out())
    before = classification_rows.keys()

    run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)

    added = classification_rows.keys() - before
    assert len(added) == 1, (
        f"A validity call the provider never answered added {len(added)} "
        f"`{CLASSIFICATION_TABLE}` row(s). §3.3: on a provider timeout 'the heuristic floor "
        "applies and the submission is accepted, then classified async'. The async pass has "
        "nothing to look for unless the floored classification is on record, and E0-13's "
        "definition of done calls a submission accepted with no record of the classification "
        "being skipped the failure mode the security review exists to catch."
    )


def test_a_timed_out_classification_is_not_recorded_as_one_the_model_produced(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
    classification_rows: ClassificationRows,
) -> None:
    """Failing open must mean accepting the submission, not pretending a model answered.

    The test above requires the floored classification to be recorded; this one
    requires the record to say so. The two are separate because the ways they fail
    are separate: one is a row that is not there, the other is a row that is there
    and lies.

    §7.4 is what makes it checkable: "every classification stores prompt version
    and model ID for reproducibility", and the single-shot boundary exists so that
    "a specific prompt version and model ID produced a specific classification for
    a specific comment". A floor row carrying the same pair as a real one asserts
    that a model produced a verdict no model was asked for — and E2's async
    re-classification has nothing to select, because every row already looks
    classified.

    **This reads the stored rows, not the returned objects**, and that is the
    repair a review asked for. It used to compare the two objects the calls
    returned, which is a claim about what a caller sees rather than about what the
    record says, and the two come apart in exactly the case that matters: a
    gateway that marks the object and writes the answered pair to the table.
    ADR 0054 names the stored distinction as what makes a floored verdict
    identifiable.

    **What is asserted is a difference, not a particular value.** How the floor is
    marked is E0-13's to choose; that a reader can tell the two apart is not
    optional. The answered row, written seconds earlier under the same
    configuration, is the control that stops this passing on some unrelated
    variation — and the columns compared are found by looking for the answered
    object's own values, since the ticket spells the table and none of its columns.
    """
    contract = validity_contract(import_app_module)
    before = classification_rows.keys()

    stub_provider.script(well_formed(contract, SUBSTANTIVE_VERDICT))
    answered = run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)
    after_answered = classification_rows.keys()

    stub_provider.script(timed_out())
    run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)
    after_floored = classification_rows.keys()

    answered_keys = after_answered - before
    floored_keys = after_floored - after_answered
    assert len(answered_keys) == 1 and len(floored_keys) == 1, (
        f"The answered call added {len(answered_keys)} row(s) and the floored call added "
        f"{len(floored_keys)}, so there is no pair of rows to compare. The two tests that own "
        "those failures are the one above and "
        "`test_a_validity_call_writes_a_classification_row_carrying_its_audit_pair`."
    )

    answered_row = classification_rows.row(next(iter(answered_keys)))
    floored_row = classification_rows.row(next(iter(floored_keys)))
    assert (
        answered_row is not None and floored_row is not None
    ), "One of the two rows could not be read back after being written."

    _, answered_prompt = require_audit_value(answered, "prompt_version", "prompt version")
    _, answered_model = require_audit_value(answered, "model_id", "model ID")

    prompt_columns = columns_holding(answered_row, str(answered_prompt))
    model_columns = columns_holding(answered_row, str(answered_model))
    assert prompt_columns and model_columns, (
        f"The `{CLASSIFICATION_TABLE}` row written for an answered call holds neither the prompt "
        f"version {answered_prompt!r} nor the model ID {answered_model!r} that the returned object "
        f"carried — the row is {answered_row!r}. This test cannot then say which columns the "
        "floored row should differ in. "
        "`test_a_validity_call_writes_a_classification_row_carrying_its_audit_pair` owns that."
    )

    audit_columns = sorted(set(prompt_columns) | set(model_columns))
    answered_pair = {name: stored_text(answered_row[name]) for name in audit_columns}
    floored_pair = {name: stored_text(floored_row[name]) for name in audit_columns}

    assert floored_pair != answered_pair, (
        f"The row stored for a classification the provider never made carries the same audit "
        f"values as the row stored for one it did: both read {answered_pair}. Nothing reading "
        f"`{CLASSIFICATION_TABLE}` can then tell a verdict a model produced from one the "
        "character floor produced during an outage — SPEC §7.4 requires a stored classification "
        "to say which prompt version and which model produced it, and this row says a model "
        "produced something it was never asked. E0-13's definition of done: failing open means "
        "accepting the submission, not silently skipping a classification, and the row is the "
        "only place that distinction survives."
    )


def test_a_provider_that_cannot_be_reached_raises_rather_than_flooring(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """The edge of the sanctioned fail-open: a timeout floors, a connection failure does not.

    §3.3 sanctions exactly one fail-open and names its cause: "Classifier latency
    budget: p95 < 2s; **on provider timeout**, the heuristic floor applies and the
    submission is accepted". A review found the gateway catching the library's
    whole error hierarchy and treating everything in it as an outage, so a refused
    connection, a failed TLS handshake and a misconfigured base URL all produced a
    verdict based on a character count with no sign anything was wrong. That is
    the fail-open widened from "the provider was slow" to "anything at all went
    wrong", and every one of those causes is permanent rather than transient: the
    async re-classification it defers to would fail the same way.

    The provider is made unreachable rather than slow by stopping the stub, so the
    port in `AI_PROVIDER_BASE_URL` refuses the connection immediately. **The
    timeout tests above are this test's control**: they are what says the
    sanctioned case still floors, so a gateway that simply stopped flooring
    everything would fail there rather than pass here.

    **This is a behaviour change rather than a criterion**, recorded in ADR 0056:
    an unreachable provider now blocks where it used to floor, and whether E2's
    submit path catches it there is E2's to decide. It is asserted here because
    the alternative is silent — a permanently misconfigured provider handing out
    participation credit on a character count, with nothing red anywhere.
    """
    contract = validity_contract(import_app_module)
    unreachable = stub_provider.base_url
    stub_provider.script(well_formed(contract, INSUFFICIENT_VERDICT))
    stub_provider.stop()

    try:
        result = run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)
    except FELL_OVER as failure:
        pytest.fail(
            f"An unreachable provider made the validity task raise {failure!r}, which is the "
            "gateway falling over rather than surfacing a failure. A caller on §3.3's submit path "
            "has to be able to catch this one deliberately."
        )
    except Exception:
        return

    name, _ = verdict_field(contract)
    pytest.fail(
        f"The provider at {unreachable} was not listening, and the validity task returned "
        f"{getattr(result, name)!r} instead of raising. §3.3 sanctions the heuristic floor on a "
        "provider **timeout** and on nothing else, and a connection that is refused is not a "
        "provider that was slow — it is one that is not there, which no amount of waiting fixes "
        "and which the async re-classification will meet again. A gateway that floors it hands "
        "out participation credit on a character count for as long as the misconfiguration lasts, "
        "with nothing anywhere reporting a problem. ADR 0056 records the choice; the timeout "
        "tests above are what say the sanctioned case still floors."
    )


# ---------------------------------------------------------------------------
# One gateway, many threads
# ---------------------------------------------------------------------------


def test_concurrent_submissions_all_carry_the_verdict_the_provider_gave(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    migrated_engine: Any,
    classification_rows: ClassificationRows,
) -> None:
    """One gateway across threads keeps classifying, rather than quietly flooring alternate calls.

    The defect this is written against: a single HTTP client shared across
    per-thread event loops. A connection created under one loop and reused under
    another raised, the gateway read the raise as an outage, and §3.3's sanctioned
    fail-open turned it into a verdict from the character floor. Measured before
    the fix at six submissions against a healthy provider — three real answers and
    three floored, alternating.

    **The stub saw all six.** The comment was sent to the third party, the model
    answered, and the answer was discarded — so the cost is a wrong verdict *and* a
    disclosure of a student's words that bought nothing. That is why the request
    count is asserted here as well: it is not the discriminator, it is what makes
    the failure's price legible.

    **"Nothing raised" would pass against the defect**, which is the whole trap:
    the floor never raises. So the stub is scripted with a verdict the character
    floor *cannot* produce — the comments are all comfortably over §3.3's
    ≥25-character threshold, so the floor says `substantive` and the model says
    `insufficient` — and every result has to carry the model's. A floored call is
    then visible as a verdict rather than as an error.

    Each thread gets its own `Session`, because a SQLAlchemy session is not
    thread-safe and sharing `db_session` across a pool would be this module
    breaking in its own fixture rather than the gateway breaking (`docs/MISTAKES.md`
    entry 13).
    """
    contract = validity_contract(import_app_module)
    task = validity_task(import_app_module)
    stub_provider.script(well_formed(contract, INSUFFICIENT_VERDICT))

    name, verdicts = verdict_field(contract)
    from_the_model = verdict_member(verdicts, INSUFFICIENT_VERDICT)
    from_the_floor = verdict_member(verdicts, SUBSTANTIVE_VERDICT)

    def submit(index: int) -> Any:
        session = Session(bind=migrated_engine)
        try:
            return call_task(
                task, session=session, comment=f"{SUBSTANTIVE_COMMENT} (submission {index})"
            )
        except Exception as failure:  # returned rather than raised, so all of them are reported
            return failure
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as pool:
        results = list(pool.map(submit, range(CONCURRENT_SUBMISSIONS)))

    raised = {index: item for index, item in enumerate(results) if isinstance(item, BaseException)}
    assert not raised, (
        f"{len(raised)} of {CONCURRENT_SUBMISSIONS} concurrent submissions raised: {raised}. A "
        "gateway serving one request at a time and failing on the second is not a gateway E2 can "
        "put behind a submit path."
    )

    assert len(stub_provider.calls) == CONCURRENT_SUBMISSIONS, (
        f"{CONCURRENT_SUBMISSIONS} submissions produced {len(stub_provider.calls)} requests to a "
        "healthy provider. §7.4's single-shot boundary makes it one call per submission, and this "
        "count is also what says whether a floored verdict below cost a disclosure: a request the "
        "provider answered and the gateway discarded sent the student's comment to a third party "
        "for nothing."
    )

    floored = {
        index: getattr(item, name, None)
        for index, item in enumerate(results)
        if getattr(item, name, None) is not from_the_model
    }
    assert not floored, (
        f"{len(floored)} of {CONCURRENT_SUBMISSIONS} concurrent submissions came back with a "
        f"verdict the provider did not give: {floored}, against {from_the_model!r} from the stub. "
        f"A verdict of {from_the_floor!r} is the character floor — every comment here is over "
        f"§3.3's {HEURISTIC_MINIMUM_CHARACTERS}-character threshold — so this is the sanctioned "
        "fail-open firing against a provider that was healthy and answered. One HTTP client "
        "shared across per-thread event loops is what produced it: the reused connection raises, "
        "the raise reads as an outage, and the student is graded on a character count. Nothing "
        "raises, nothing is logged as an error, and the stub still saw every request."
    )

    stems = prompt_stems()
    assert stems, (
        f"There are no prompt files under {PROMPTS_DIR}, so the check below would accept any "
        "recorded version. `tests/unit/test_prompt_directory_layout.py` owns that failure."
    )
    unresolvable = {
        index: require_audit_value(item, "prompt_version", "prompt version")[1]
        for index, item in enumerate(results)
        if str(require_audit_value(item, "prompt_version", "prompt version")[1]) not in stems
    }
    assert not unresolvable, (
        f"These concurrent submissions recorded a prompt version naming no file under "
        f"{PROMPTS_DIR}: {unresolvable}. ADR 0031 makes the recorded value a prompt file's path "
        "stem, so a result carrying anything else was produced without loading a prompt — which "
        "is what a floored verdict looks like from the audit side."
    )


# ---------------------------------------------------------------------------
# What must never leave the machine, and what must never leave in a message
# ---------------------------------------------------------------------------


def test_a_validity_call_reaches_nothing_off_this_machine(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
    migrated_database: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 5, first half: no test makes a live network call.

    Asserted rather than arranged. Pointing `AI_PROVIDER_BASE_URL` at a stub is
    the arrangement; what this adds is a guard under the call, so that a gateway
    reaching a hosted provider — a default base URL, a discovery request, a
    hardcoded host — fails here instead of billing somebody and leaking a
    student's comment to a third party in a CI run.

    The one address permitted off the loopback interface is the Postgres
    container's, because the task may open a database connection while it runs
    and the container's host is not guaranteed to be `127.0.0.1`. Naming it keeps
    the guard about the thing it is for.
    """
    from urllib.parse import urlsplit

    contract = validity_contract(import_app_module)
    stub_provider.script(well_formed(contract, SUBSTANTIVE_VERDICT))
    database_host = urlsplit(migrated_database.application_url).hostname or "127.0.0.1"

    with only_loopback(monkeypatch, database_host) as attempted:
        try:
            run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)
        except OffMachineConnectionError as failure:
            pytest.fail(
                f"The validity task tried to connect off this machine: {failure}. E0-13's fifth "
                "criterion: 'No test makes a live network call.' §10 and §4 make a comment sent "
                "to an unintended host a confidentiality failure rather than a billing one."
            )

    assert attempted, (
        "No socket connection was attempted at all during the call, so this test observed "
        "nothing. Either the guard is not reaching the client the gateway uses — in which case "
        "the control test below is what says so — or the gateway answered without a round trip, "
        "which the first test in this module owns."
    )


def test_the_loopback_guard_refuses_an_address_off_this_machine_and_permits_one_on_it(
    monkeypatch: pytest.MonkeyPatch,
    stub_provider: StubProvider,
) -> None:
    """The guard above, run against what it must stop and what it must allow.

    Not a test of the ticket — a test of the guard the test above depends on.
    `docs/MISTAKES.md` entry 3's rule for anything that reports by silence: run it
    against the case you claim it catches *and* the case you claim it allows,
    because a guard that has gone blind reports exactly what a gateway that never
    left the machine reports. Entry 9 is the same rule for a guard cited rather
    than executed.

    The refused address is RFC 5737 TEST-NET-3, which is routed nowhere, so the
    permitted branch of this test cannot itself become the live call the guard
    exists to prevent.
    """
    from urllib.parse import urlsplit

    stub = urlsplit(stub_provider.base_url)

    refused = pytest.raises(OffMachineConnectionError)

    with only_loopback(monkeypatch):
        with refused, socket.socket() as probe:
            probe.settimeout(1.0)
            probe.connect(OFF_MACHINE_ADDRESS)

        with socket.socket() as permitted:
            permitted.settimeout(5.0)
            permitted.connect((stub.hostname or "127.0.0.1", stub.port or 0))


def test_a_validity_call_succeeds_with_no_provider_key_configured(
    ai_environment: dict[str, str],
    documented_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 5, second half: the suite passes with no provider key set.

    A key is not something an OpenAI-compatible endpoint necessarily wants —
    `.env.example` says the base URL may be "a hosted provider, a proxy, or a
    local server such as vLLM or Ollama", and the last two commonly need none. So
    "the suite passes with no provider key set" is a property of the gateway
    rather than an accident of what CI happens to export, and E0-13's definition
    of done makes it a documented one: "`README.md` notes how to run without a
    provider key."

    The variables are found in `.env.example` rather than named, since E0-13 does
    not spell the key's variable. An empty set fails here rather than passing
    vacuously: with nothing removed, this test would report a gateway working
    without a key while the key was in fact set.
    """
    variables = provider_key_variables(documented_env)
    assert variables, (
        "`.env.example` documents no variable that reads as the AI provider key, so this test "
        "removed nothing and would pass with the key set. E0-13's scope: 'Provider configuration "
        "from `Settings`: base URL, model, and a masked key', and `.env.example` already says "
        "'the provider key is not read yet — the gateway and its masked key land in E0-13'. If "
        "it is documented under a word `PROVIDER_KEY_WORDS` in this file does not reach, that "
        "constant is the one line that changes."
    )

    # Removed before anything under `app.` is imported, because a module that
    # builds its client out of `Settings()` at import time reads the environment
    # once. `import_app_module` is what makes that observable rather than a matter
    # of which test ran first.
    for name in variables:
        monkeypatch.delenv(name, raising=False)

    contract = validity_contract(import_app_module)
    stub_provider.script(well_formed(contract, SUBSTANTIVE_VERDICT))

    try:
        result = run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)
    except Exception as failure:
        pytest.fail(
            f"With {variables} unset, the validity task raised {failure!r}. E0-13's fifth "
            "criterion: 'the suite passes with no provider key set', and a local OpenAI-compatible "
            "server needs no key at all."
        )

    assert isinstance(result, contract), (
        f"With no provider key configured the task returned {result!r} rather than a "
        f"`{contract.__name__}`."
    )


def test_a_provider_error_does_not_carry_the_provider_key_into_the_failure(
    ai_environment: dict[str, str],
    documented_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """E0-13's security review, first item: the key must not reach a log or an error message.

    A provider rejecting the credential is the error most likely to be logged with
    the request that caused it, and an HTTP client that renders the request in its
    exception renders the `Authorization` header with it. SPEC §10 keeps secrets
    in the environment or the secret store; a startup or runtime error that prints
    one puts it in the log aggregator instead.

    **The non-vacuity guard is the first assertion, and it is not ceremony.** An
    error cannot leak a value that was never sent, so a gateway that ignores the
    configured key would pass the leak check while failing to authenticate to
    every real provider — `docs/MISTAKES.md` entry 23, a field validated and read
    by nothing, arriving from the other direction. Every header the stub received
    is searched, not the `Authorization` header alone, because how a key is sent
    is the gateway's choice.

    **That guard is only as good as the needle**, which is why
    `test_the_needle_matches_nothing_a_request_carries_without_it` sits below it.
    A needle sharing an ordinary word with a header value satisfies the guard
    without the key having been sent at all, and then every assertion after it is
    green about nothing.
    """
    variables = provider_key_variables(documented_env)
    assert variables, (
        "`.env.example` documents no provider key variable, so nothing was configured and this "
        "test would report no leak whatever the truth is. The criterion-5 test above says what "
        "that entry is for."
    )

    stub_provider.script(
        Answer(status=401, body=json.dumps({"error": {"message": "invalid api key"}}))
    )

    raised: BaseException | None = None
    try:
        run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)
    except Exception as failure:
        raised = failure

    sent = [
        name
        for call in stub_provider.calls
        for name, value in call.headers.items()
        if leaked_fragments(value, FAKE_PROVIDER_CREDENTIAL)
    ]
    assert sent, (
        f"The provider key was configured in {variables} and no request the gateway sent carried "
        f"it in any header — the stub saw {len(stub_provider.calls)} request(s) with headers "
        f"{[sorted(call.headers) for call in stub_provider.calls]}. Either the key is configured "
        "and read by nothing, which makes every hosted provider unreachable, or it is sent "
        "somewhere this test does not look. Until it is sent, the leak assertion below cannot "
        "fail and would report a guarantee it never tested."
    )
    assert raised is not None, (
        "The provider answered 401 on every attempt and the validity task returned without "
        "raising. A rejected credential is not a shape violation the floor should absorb: §3.3's "
        "fail-open is for a *timeout*, and a silently-accepted authentication failure is the "
        "safety classification skipped rather than the submission accepted."
    )

    for link in exception_chain(raised):
        for rendering, where in ((str(link), "str"), (repr(link), "repr")):
            fragments = leaked_fragments(rendering, FAKE_PROVIDER_CREDENTIAL)
            assert not fragments, (
                f"{where}() of the raised {type(link).__name__} contains fragments of "
                f"`FAKE_PROVIDER_CREDENTIAL`, the value the provider key was configured with: "
                f"{fragments}. The full text was:\n{rendering}\n"
                "E0-13's definition of done: 'Review for the provider key reaching a log or an "
                "error message.' A gateway error is printed to the container log, so this is a "
                "credential in a log (SPEC §10). If these fragments read as ordinary words rather "
                "than as the key, suspect the needle first — "
                "`test_the_needle_matches_nothing_a_request_carries_without_it` is the test that "
                "answers that, and it should be red beside this one."
            )


def test_the_needle_matches_nothing_a_request_carries_without_it(
    ai_environment: dict[str, str],
    documented_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`FAKE_PROVIDER_CREDENTIAL` shares no fragment with a call that was never given it.

    Not a test of the ticket — a test of the needle the two rules above are driven
    by, and the control whose absence cost a dispute round in the unit module. The
    original needle contained the word `provider`, and this module searches with
    it in **both** directions: once to prove the key was sent, once to prove it did
    not leak. A collision breaks the first silently — the guard passes on a header
    that merely says "provider", and the leak assertions beneath it then report a
    guarantee they never tested.

    So the key is removed and the same call made. Everything the request carries
    is searched, and so is every value this module configures apart from the key
    itself: anything found is a collision between the needle and the vocabulary of
    a request, not a credential.

    Whether the call raises is not this test's subject — the criterion-5 test owns
    that — but a call that reached the stub with no request at all would make this
    control vacuous, so that is asserted first.
    """
    variables = provider_key_variables(documented_env)
    assert variables, (
        "`.env.example` documents no provider key variable, so nothing was removed and this "
        "control is not testing what it says. The criterion-5 test above owns that failure."
    )
    for name in variables:
        monkeypatch.delenv(name, raising=False)

    contract = validity_contract(import_app_module)
    stub_provider.script(well_formed(contract, SUBSTANTIVE_VERDICT))

    with contextlib.suppress(Exception):
        run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)

    assert stub_provider.calls, (
        "The gateway sent the stub no request, so this control searched nothing and would report "
        "the needle as clean whatever it collides with. The first test in this module owns the "
        "failure that no round trip happened."
    )

    searched: list[tuple[str, str]] = [
        (f"the {name} header of a request", value)
        for call in stub_provider.calls
        for name, value in call.headers.items()
    ]
    searched += [
        (f"the path of a request ({call.path})", call.path) for call in stub_provider.calls
    ]
    searched += [("the body of a request", call.body) for call in stub_provider.calls]
    searched += [
        (f"the configured value of {name}", value)
        for name, value in ai_environment.items()
        if name not in variables
    ]

    collisions = {
        where: leaked_fragments(text, FAKE_PROVIDER_CREDENTIAL)
        for where, text in searched
        if leaked_fragments(text, FAKE_PROVIDER_CREDENTIAL)
    }

    assert not collisions, (
        f"`FAKE_PROVIDER_CREDENTIAL` shares fragments with things this module renders while the "
        f"key was not configured at all: {collisions}. Both rules above are then broken, and in "
        "opposite ways — the guard that proves the key was sent passes on a request that never "
        "carried it, and the assertion that no error leaks it fails on ordinary words. The repair "
        f"is the needle: choose a value sharing no run of {LEAK_FRAGMENT_LENGTH} characters with "
        "what is searched here. Leave `LEAK_FRAGMENT_LENGTH` alone — it is shared with "
        "`test_config_settings.py` and `test_db_engine_configuration.py`, where raising it would "
        "let a truncated database password through."
    )


def raised_by_a_persistent_shape_violation(
    import_app_module: Callable[[str], ModuleType | None],
    session: Any,
    comment: str,
) -> BaseException:
    """Run the validity task against a provider that never answers correctly, and return the error.

    A failure that is the gateway falling over rather than reporting is refused
    here rather than searched, for the reason
    `test_a_persistently_malformed_provider_answer_raises_rather_than_returning_a_partial_object`
    gives at length: a `TypeError` is not a surfaced failure, and searching one
    for a comment would be reading whatever Python happened to say.
    """
    try:
        result = run_validity(import_app_module, session, comment)
    except FELL_OVER as failure:
        pytest.fail(
            f"A persistently malformed provider answer raised {failure!r}, which is the gateway "
            "falling over rather than surfacing a failure. The test named above owns that."
        )
    except Exception as failure:
        return failure
    pytest.fail(
        f"The provider answered malformed on every attempt and the task returned {result!r} "
        "rather than raising, so there is no failure message to search. "
        "`test_a_persistently_malformed_provider_answer_raises_rather_than_returning_a_partial_"
        "object` owns that."
    )


def rendered_chain(failure: BaseException) -> dict[str, str]:
    """Every rendering of every link in an exception chain, labelled by where it came from.

    Three surfaces per link, because a fix can address one and miss the others:
    the message a traceback prints, the repr a structured logger reaches for, and
    the payload a JSON error handler would serialise. The chain rather than the
    outermost exception, because `raise X() from exc` leaves the original holding
    whatever it held and Python prints a cause's message too.
    """
    surfaces: dict[str, str] = {}
    for index, link in enumerate(exception_chain(failure)):
        label = f"{type(link).__name__}[{index}]"
        surfaces[f"str() of {label}"] = str(link)
        surfaces[f"repr() of {label}"] = repr(link)
        errors = getattr(link, "errors", None)
        if callable(errors):
            surfaces[f"errors() of {label}"] = json.dumps(errors(), default=str)
    return surfaces


def assert_the_failure_describes_the_shape(surfaces: dict[str, str], field_name: str) -> None:
    """The message says something about the payload's shape, so an absence below means something.

    The non-vacuity guard for the two tests beneath, and not ceremony: "no part of
    the comment appears in the failure" is satisfied completely by a gateway whose
    message is the empty string, and a message that cannot say which field was
    wrong is a message nobody can act on. A field the *contract* declares is the
    thing a shape violation is entitled to name — it is the project's own
    vocabulary rather than the model's.
    """
    assert any(field_name in rendering for rendering in surfaces.values()), (
        f"No rendering of the raised failure mentions `{field_name}`, a field the contract "
        f"declares — the renderings were {surfaces}. The assertions below say that no part of the "
        "student's comment appears in this failure, and a failure that says nothing at all "
        "satisfies them without the guarantee holding. §7.4 has the gateway surface persistent "
        "failures as errors, and an error that cannot name the field that was wrong leaves an "
        "operator with a comment they may not read and nothing else."
    )


def test_a_shape_violation_message_does_not_carry_the_students_comment(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """A comment must not reach a log through the error a bad answer produced.

    §4 keeps a student's words out of every surface that is not the ones it names,
    and §10 keeps them out of logs; a gateway error is printed to the container
    log with its whole chain. This is the general case: the provider answers
    malformed, the gateway gives up, and whatever it says must describe the
    *shape* it refused rather than the text it was asked about.

    It is also the control for the test below. The comment here is made of tokens
    that appear nowhere else in this repository, so this test passing is what says
    those tokens do not collide with the gateway's own vocabulary — without it, a
    green result there would be as consistent with a needle that matches nothing
    as with a message that leaks nothing (`docs/MISTAKES.md` entry 3).
    """
    contract = validity_contract(import_app_module)
    field_name, _ = verdict_field(contract)
    stub_provider.script(Answer(content='{"' + field_name + '": "spicy-take"}'))

    failure = raised_by_a_persistent_shape_violation(import_app_module, db_session, NEEDLE_COMMENT)
    surfaces = rendered_chain(failure)
    assert_the_failure_describes_the_shape(surfaces, field_name)

    leaked = {
        where: leaked_fragments(rendering, NEEDLE_COMMENT)
        for where, rendering in surfaces.items()
        if leaked_fragments(rendering, NEEDLE_COMMENT)
    }
    assert not leaked, (
        f"The failure a malformed provider answer produced carries fragments of the student's "
        f"comment: {leaked}. The renderings were {surfaces}. SPEC §4 permits a comment on the "
        "surfaces it names and no others, and §10 keeps it out of logs — a gateway error is "
        "printed to the container log with its whole chain, so a comment quoted into one is a "
        "comment in the log aggregator."
    )


def test_a_shape_violation_does_not_reassemble_the_comment_out_of_the_answers_keys(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
) -> None:
    """The route a review found, and the reason a message may not interpolate what it refused.

    A message that names the offending field by interpolating the key it came from
    is quoting the *model's* invention, and a model asked to classify a comment
    can return that comment as its field names. With the number of details
    unbounded, the keys arrive in order and the comment reassembles itself inside
    the error — in a log, from a gateway that has done nothing else wrong.

    So the stub answers with a payload whose keys are the chunks of the comment,
    in order. What must survive is the distinction between vocabularies: a name
    the *contract* declares may be named, and a name the model invented may not be
    echoed. The fix sanitises every element of the location against the payload's
    own schema and caps how many are reported; this asserts the property rather
    than either mechanism.

    Its non-vacuity guard is `assert_the_failure_describes_the_shape` — a message
    that says nothing leaks nothing — and its needle control is the test above,
    which sends the same comment with ordinary keys and requires the same silence.
    """
    contract = validity_contract(import_app_module)
    field_name, _ = verdict_field(contract)
    invented = {chunk: "..." for chunk in NEEDLE_COMMENT_CHUNKS}
    assert field_name not in invented, (
        f"The comment this test chops into keys happens to contain `{field_name}`, the "
        "contract's own field name, so a message that legitimately names the field would read as "
        "a leak. `NEEDLE_COMMENT` in this file is the one line that changes."
    )
    stub_provider.script(Answer(content=json.dumps(invented)))

    failure = raised_by_a_persistent_shape_violation(import_app_module, db_session, NEEDLE_COMMENT)
    surfaces = rendered_chain(failure)
    assert_the_failure_describes_the_shape(surfaces, field_name)

    leaked: dict[str, list[str]] = {}
    for where, rendering in surfaces.items():
        found = sorted(
            fragment
            for needle in (NEEDLE_COMMENT, *NEEDLE_COMMENT_CHUNKS)
            for fragment in leaked_fragments(rendering, needle)
        )
        if found:
            leaked[where] = found

    assert not leaked, (
        f"A provider answered with the student's comment as its field names, and the failure the "
        f"gateway raised quotes those names back: {leaked}. The renderings were {surfaces}. The "
        "comment was "
        f"{NEEDLE_COMMENT!r}, chopped into {list(NEEDLE_COMMENT_CHUNKS)} and sent as the payload's "
        "keys. A message built by interpolating the keys of the payload it refused reassembles "
        "the comment in a container log, and the number of them reported is what decides how much "
        "of it. A name the contract declares may be named; a name the model invented may not be "
        "echoed."
    )


# ---------------------------------------------------------------------------
# The classification row (SPEC §8: append-only)
# ---------------------------------------------------------------------------


def test_a_validity_call_writes_a_classification_row_carrying_its_audit_pair(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
    classification_rows: ClassificationRows,
) -> None:
    """E0-13's scope: a `classification` table "storing the verdict with prompt version and model ID".

    The row is what §7.4's reproducibility sentence is actually about — "every
    classification stores prompt version and model ID" — and it is the thing an
    audit conversation reaches for when a participation grade or a safety flag is
    questioned. A returned object that satisfies the contract and is never
    persisted leaves that conversation with nothing.

    The three values are read out of the row and compared against the object the
    call returned, rather than against constants, so a row written with defaults
    or with somebody else's classification fails here.
    """
    contract = validity_contract(import_app_module)
    stub_provider.script(well_formed(contract, INSUFFICIENT_VERDICT))
    before = classification_rows.keys()

    result = run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)

    added = classification_rows.keys() - before
    assert len(added) == 1, (
        f"One validity call added {len(added)} `{CLASSIFICATION_TABLE}` row(s). E0-13's scope: 'A "
        "minimal `classification` table storing the verdict with prompt version and model ID, "
        "append-only (re-runs create new rows, per §8).' A classification that is returned and "
        "not stored cannot be reproduced, re-reviewed in §6.1's drift panel, or fed to §9.3's "
        "eval sets."
    )

    row = classification_rows.row(next(iter(added)))
    assert row is not None, "The row that was just added could not be read back."
    stored = {stored_text(value) for value in row.values() if value is not None}

    name, _ = verdict_field(contract)
    _, prompt_version = require_audit_value(result, "prompt_version", "prompt version")
    _, model_id = require_audit_value(result, "model_id", "model ID")
    expected = {
        "the verdict": str(wire_value(getattr(result, name))),
        "the prompt version": str(prompt_version),
        "the model ID": str(model_id),
    }

    missing = {label: value for label, value in expected.items() if value not in stored}
    assert not missing, (
        f"The `{CLASSIFICATION_TABLE}` row does not carry {sorted(missing)}: it holds {row!r}, "
        f"and the object returned carried {expected}. SPEC §8: '`classification` is append-only "
        "(re-runs create new rows) with prompt/model versioning.' §7.4: the classifier 'must be "
        "auditable, meaning a specific prompt version and model ID produced a specific "
        "classification for a specific comment' — all three values, in the row, or the record "
        "answers none of that."
    )


def test_re_running_classification_for_the_same_comment_adds_a_second_row(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
    classification_rows: ClassificationRows,
) -> None:
    """Criterion 4: a re-run creates a second row rather than updating the first.

    SPEC §8 makes `classification` append-only, and the reason is §6.1's drift
    panel and §9.3's eval sets: a re-run under a new prompt version is the
    measurement, and an `UPDATE` deletes the earlier answer that the new one is
    being compared against. It is also what makes a disputed participation grade
    answerable — the verdict that decided it is still there after the prompt has
    moved on.

    The two runs answer *differently*, which is the case an upsert handles by
    overwriting: a re-run producing an identical row would be satisfied by an
    `ON CONFLICT DO NOTHING` that wrote nothing at all.
    """
    contract = validity_contract(import_app_module)
    before = classification_rows.keys()

    stub_provider.script(well_formed(contract, INSUFFICIENT_VERDICT))
    run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)
    after_first = classification_rows.keys()

    stub_provider.script(well_formed(contract, SUBSTANTIVE_VERDICT))
    run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)
    after_second = classification_rows.keys()

    first = after_first - before
    second = after_second - after_first

    assert len(first) == 1, (
        f"The first classification of the comment added {len(first)} rows, so this test has no "
        "baseline to compare a re-run against. The test above owns that failure."
    )
    assert len(second) == 1, (
        f"Classifying the same comment a second time added {len(second)} `{CLASSIFICATION_TABLE}` "
        f"row(s) rather than one. E0-13's fourth criterion: 'Re-running classification for the "
        "same comment creates a second row rather than updating the first.' SPEC §8: "
        "'`classification` is append-only (re-runs create new rows) with prompt/model "
        "versioning.'"
    )
    assert first.isdisjoint(second), (
        f"The re-run reused the row key {sorted(first & second)}, so the second classification is "
        "the first one rewritten. Append-only means a new row, not a new value."
    )


def test_the_first_classification_survives_the_re_run_unchanged(
    ai_environment: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
    stub_provider: StubProvider,
    db_session: Any,
    classification_rows: ClassificationRows,
) -> None:
    """The other half of append-only: the earlier verdict is still readable afterwards.

    Two rows existing does not mean the first still says what it said. A gateway
    that inserts a new row *and* stamps the old one — with a "superseded" verdict,
    a cleared prompt version, a null — passes the count assertion above and leaves
    §9.3 comparing a new answer against a row that has been edited to agree with
    it. `audit_log` is append-only for the same reason (§8), and there the
    consequence is a record of a re-identification that no longer says who did it.
    """
    contract = validity_contract(import_app_module)
    before = classification_rows.keys()

    stub_provider.script(well_formed(contract, INSUFFICIENT_VERDICT))
    run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)

    added = classification_rows.keys() - before
    assert len(added) == 1, (
        f"The first classification added {len(added)} rows, so there is nothing here to watch for "
        "changes. The two tests above own that failure."
    )
    key = next(iter(added))
    original = classification_rows.row(key)
    assert original is not None, "The first classification row could not be read back."

    stub_provider.script(well_formed(contract, SUBSTANTIVE_VERDICT))
    run_validity(import_app_module, db_session, SUBSTANTIVE_COMMENT)

    afterwards = classification_rows.row(key)
    assert afterwards is not None, (
        f"The first `{CLASSIFICATION_TABLE}` row was deleted by the re-run. SPEC §8 makes the "
        "table append-only: the earlier verdict is the record a disputed participation grade is "
        "answered from."
    )
    assert afterwards == original, (
        f"The first classification row changed when the comment was classified again.\n"
        f"Before: {original!r}\nAfter:  {afterwards!r}\n"
        "SPEC §8: '`classification` is append-only (re-runs create new rows).' A second row "
        "beside an edited first one is not append-only — §9.3 would be comparing a new answer "
        "against a row that had been rewritten to agree with it."
    )


def test_the_application_role_may_write_a_classification_row(
    migrated_engine: Any,
    metadata_tables: dict[str, Any],
) -> None:
    """The role production runs as can insert one, which no test above can see.

    Every behavioural test in this module hands the task a session on the
    bootstrap connection, because that is what `tests/conftest.py` provides and
    because the ticket does not say whether the task opens its own. So all of them
    would pass against a schema in which `pulse_app` — the role the API and the
    worker actually connect as (ADR 0001, ADR 0009) — holds no `INSERT` on this
    table, and the first classification in a deployment would fail with a
    permission error. `tests/conftest.py` states the general form of this: "a test
    that passes under privileges production lacks is a test that fails."

    Asserted out of the catalog rather than by writing a row, because the two
    answer different questions and `docs/MISTAKES.md` entry 3 asks for both where
    it can get them: a behavioural insert cannot see whether the *grant* is what
    permitted it, and this cannot see whether an insert works. The behavioural
    half is every test above.
    """
    table = classification_table(metadata_tables)
    with migrated_engine.connect() as connection:
        present = connection.execute(
            text("SELECT to_regclass(:name)"), {"name": f"public.{table.name}"}
        ).scalar()
        assert present is not None, (
            f"There is no `public.{table.name}` relation in the migrated database, although the "
            "table is on `Base.metadata`. That is a migration nobody wrote — "
            "`alembic check` and `tests/unit/test_ai_models_registered.py` are where it shows."
        )
        granted = connection.execute(
            text("SELECT has_table_privilege(:role, :name, 'INSERT')"),
            {"role": APPLICATION_ROLE, "name": f"public.{table.name}"},
        ).scalar()

    assert granted, (
        f"`{APPLICATION_ROLE}` holds no INSERT on `public.{table.name}`. That is the role the API "
        "and the Celery worker connect as (ADR 0001, ADR 0009, `.env.example`), and E0-13 has "
        "them writing a classification for every comment — so the first one in a real deployment "
        "fails with a permission error while every test in this module, which writes on the "
        "bootstrap connection, stays green."
    )


# The privileges that would let a stored classification be changed or removed.
# SPEC §8's "append-only (re-runs create new rows)" is enforced by their absence
# and by nothing else: no constraint, no trigger and no application code stops an
# `UPDATE` that the grant permits.
FORBIDDEN_APPEND_ONLY_PRIVILEGES = ("UPDATE", "DELETE", "TRUNCATE")


@pytest.mark.parametrize("privilege", FORBIDDEN_APPEND_ONLY_PRIVILEGES)
def test_the_application_role_may_not_change_or_remove_a_classification_row(
    migrated_engine: Any,
    metadata_tables: dict[str, Any],
    privilege: str,
) -> None:
    """Append-only, asserted as the absence that actually enforces it.

    The test above asserts `INSERT` is present. Nothing asserted these were
    absent, and they are the whole of the enforcement: §8 says "`classification`
    is append-only (re-runs create new rows) with prompt/model versioning", and no
    constraint, trigger or line of application code holds that — the grant does.
    A later migration adding `UPDATE` would pass every other test in this module,
    and ADR 0055 names the temptation by name: E2's re-classification pass will
    have a row it would rather amend than supersede.

    **The two append-only behaviour tests cannot see this**, which is why it is
    separate rather than folded into them. They run on the bootstrap connection,
    which holds every privilege in the cluster whatever `pulse_app` holds, so they
    would stay green against a role that could rewrite every verdict ever stored.
    `tests/integration/test_identity_grants.py` sets this repository's bar for the
    shape — a catalog assertion paired with a behavioural one — and the
    behavioural half is the test below.

    `TRUNCATE` is in the set for completeness: it removes every row without being
    a `DELETE`, and a grant of it is the same guarantee lost by a different verb.
    """
    table = classification_table(metadata_tables)
    with migrated_engine.connect() as connection:
        readable = connection.execute(
            text("SELECT has_table_privilege(:role, :name, 'SELECT')"),
            {"role": APPLICATION_ROLE, "name": f"public.{table.name}"},
        ).scalar()
        held = connection.execute(
            text("SELECT has_table_privilege(:role, :name, :privilege)"),
            {"role": APPLICATION_ROLE, "name": f"public.{table.name}", "privilege": privilege},
        ).scalar()

    assert readable, (
        f"`{APPLICATION_ROLE}` cannot even SELECT `public.{table.name}`, so this test is asking "
        "about a table the role has no relationship with at all and its answer says nothing about "
        "append-only. E0-13 has the application reading its own classifications back."
    )
    assert not held, (
        f"`{APPLICATION_ROLE}` holds {privilege} on `public.{table.name}`. SPEC §8: "
        "'`classification` is append-only (re-runs create new rows) with prompt/model "
        "versioning' — and the grant is the only thing enforcing it, since no constraint or "
        "trigger refuses an amendment. With this privilege held, a re-classification can rewrite "
        "the verdict that decided a participation grade, §9.3 compares a new answer against a row "
        "edited to agree with it, and §6.1's drift panel samples a history that has been "
        "rewritten. ADR 0055 records that E2 will want exactly this; the answer is a second row."
    )


@pytest.mark.parametrize("statement", ("UPDATE", "DELETE"))
def test_the_application_role_is_refused_a_write_that_would_amend_a_classification(
    application_engine: Any,
    metadata_tables: dict[str, Any],
    statement: str,
) -> None:
    """The behavioural half: the statement itself is refused on the connection production uses.

    The catalog test above says the privilege is not in `relacl`; this says the
    database acts on that. `docs/MISTAKES.md` entry 3's rule for a guarantee two
    mechanisms could produce: "the catalog test cannot see whether the rule works
    and the behavioural test cannot see whether it exists. Both, not either."

    `application_engine` is the connection that matters — `pulse_app`, holding
    only what the migrations grant it — and the epic README is explicit that from
    E0-10 on, which role a fixture authenticates as is the difference between a
    test that can detect a missing grant and one that cannot.

    **The control comes first.** A `SELECT` on the same table over the same
    connection has to succeed, because "the statement was refused" is equally
    satisfied by a table that is not there, a role that cannot connect and a
    schema nobody migrated — and all three would read as append-only holding.

    No row is seeded and none is needed: Postgres checks the privilege before it
    looks for rows, so the refusal is the same on an empty table and is a
    statement about the grant rather than about what happens to be stored.
    """
    from sqlalchemy.exc import ProgrammingError

    table = classification_table(metadata_tables)
    key = primary_key_of(table)
    # Built through SQLAlchemy Core rather than as text, so the statement is
    # rendered from the table this test was handed rather than from a name spliced
    # into a string. Neither is a `commit()`, and a connection closed without one
    # rolls back — so a grant that should not be there fails this test rather than
    # emptying the table on its way through.
    amendments = {
        "UPDATE": table.update().values({key.name: key}),
        "DELETE": table.delete(),
    }

    with application_engine.connect() as connection:
        current = connection.execute(text("SELECT current_user")).scalar()
        assert current == APPLICATION_ROLE, (
            f"This test connected as {current!r} rather than as `{APPLICATION_ROLE}`, so a "
            "refusal here would be about some other role's privileges. `tests/conftest.py` "
            "carries the reasoning beside `TEST_APP_USER`, and "
            "`test_the_suites_application_connection_authenticates_as_the_granted_role` in "
            "`tests/integration/test_identity_grants.py` is what keeps the two names in step."
        )
        try:
            connection.execute(select(key)).first()
        except ProgrammingError as refusal:
            pytest.fail(
                f"`{APPLICATION_ROLE}` could not read `public.{table.name}`: {refusal}. The "
                "refusal asserted below would then be indistinguishable from a table this role "
                "cannot reach at all."
            )

    with application_engine.connect() as connection, pytest.raises(ProgrammingError) as refused:
        connection.execute(amendments[statement])

    assert "permission denied" in str(refused.value).lower(), (
        f"`{APPLICATION_ROLE}` was refused `{statement}` on `public.{table.name}`, but not for "
        f"want of a privilege: {refused.value}. A syntax error or a missing relation refuses the "
        "same statement and says nothing about append-only, which is the distinction this "
        "assertion exists to keep."
    )
