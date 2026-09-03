"""The mock provider's HTTP surface — an OpenAI-compatible endpoint that decides nothing.

Run it with `uvicorn app.main:create_app --factory`, the same way the backend and
the other two mocks are run. There is no module-level application object, which
is the shape this repository already uses; unlike the other two mocks there is no
per-process key behind that choice, because this service holds no key and no
state at all.

**It is stateless on purpose, and that is load-bearing rather than tidy.** ADR
0053 gives the gateway one bounded re-ask for a shape violation, and §7.4 has it
"surface persistent failures as errors rather than letting a malformed
classification propagate". A mock that answered malformedly once and correctly
the second time would make that error unreachable: the retry would succeed and
the path E2-07's second criterion names would never run. So every request is
decided by its own comment and by nothing this process remembers.

**Nothing is logged.** SPEC §10 forbids personally identifiable information in
logs, and the prompt this service is sent ends with a student's comment. Stated
precisely, because "nothing is logged" is a claim this file cannot make on its
own: uvicorn's access log is on, and it records the method, the path and the
status of every request. The comment arrives in a `POST` body and reaches none of
that. No handler here writes the prompt, the comment or the answer anywhere.

**The verdicts it gives are not judgements.** `app.rules` has the whole of the
reasoning; the short version is that this service reads a character count and a
handful of markers, so a stack pointed at it is a stack that is not classifying.
`docs/adr/0113-the-mock-model-provider-is-development-only-and-selects-in-band.md`
is why nothing outside development may point at it.
"""

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import (
    CHAT_COMPLETIONS_PATH,
    DEFAULT_MODEL_NAME,
    HEALTH_PATH,
    MODELS_PATH,
    RULES_PATH,
    SERVICE_NAME,
    SUMMARY,
)
from app.rules import ExtractionError, classify, extract_comment, served_rules

# What a completion envelope reports as its identity and its creation time. Both
# are fixed: a client reads neither for anything this service is used for, and a
# mock that reached for a clock or a random number would be one more thing that
# differs between two otherwise identical runs.
COMPLETION_ID = "chatcmpl-mock-ai"
COMPLETION_CREATED = 1_750_000_000

# A body this service could not read at all — not JSON, or JSON that is not an
# object. Answered as a 400 rather than allowed to become an unhandled exception
# and a 500, because a 500 here is a status this mock hands out on purpose
# (`mock-ai:500`) and a second source of it would make that selector ambiguous.
UNREADABLE_REQUEST = 400

# Words that mark a declared tool as the one an answer is meant to come back
# through. The same heuristic, for the same reason, as the stub in
# `tests/integration/test_ai_gateway_validity_roundtrip.py`: the gateway declares
# no tool at all (ADR 0053 — `NativeOutput`, so the request carries
# `response_format`), and answering under whatever name a client *did* declare is
# what keeps this mock from being the thing that decides which mode is used.
OUTPUT_TOOL_WORDS = ("result", "final", "output")


def prompt_text(body: Mapping[str, Any]) -> str:
    """Every message's text out of one chat-completions request, in order.

    Joined rather than reduced to the last message, because the boundary
    `app.rules.extract_comment` reads is the marker's *last* occurrence — so a
    client that split its instructions across a system message and a user message
    reaches the same answer as one that sent a single message, and neither can
    move the boundary by adding a message before it.

    A content part carrying `text` is read as well as a plain string content,
    which is the multimodal spelling of the same field. Anything else is skipped:
    this service classifies writing.
    """
    messages = body.get("messages")
    if not isinstance(messages, list):
        return ""
    parts: list[str] = []
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(
                str(piece["text"])
                for piece in content
                if isinstance(piece, Mapping) and isinstance(piece.get("text"), str)
            )
    return "\n".join(parts)


def output_tool_name(body: Mapping[str, Any]) -> str | None:
    """The tool a request wants its answer in, if it declared one.

    Where several are declared the one whose name reads like an output tool is
    preferred and otherwise the last is taken — a heuristic, written down here
    rather than hidden, and the same one the roundtrip stub uses.
    """
    tools = body.get("tools")
    if not isinstance(tools, list):
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
        if any(word in name.lower() for word in OUTPUT_TOOL_WORDS):
            return name
    return names[-1]


def reported_model(body: Mapping[str, Any]) -> str:
    """The model the envelope says answered: the one asked for, or this mock's own.

    Echoed rather than invented, which is what a real provider does — and
    `app.ai.gateway` records this value as half of every classification's audit
    pair (ADR 0031), so an envelope naming nothing would leave that pair with
    nowhere to come from.
    """
    asked = body.get("model")
    return asked if isinstance(asked, str) and asked.strip() else DEFAULT_MODEL_NAME


def chat_completion(payload: dict[str, Any], body: Mapping[str, Any]) -> dict[str, Any]:
    """One OpenAI-compatible chat completion carrying `payload`, however it was asked for.

    The payload travels as the *text* of the assistant's message, which is the
    route native JSON output reads (ADR 0053), and additionally as a tool call
    when the request declared a tool. Both, rather than one or the other, because
    a client reads the answer back through the channel it asked on and this
    service does not get to choose which.
    """
    content = json.dumps(payload)
    message: dict[str, Any] = {"role": "assistant", "content": content}
    finish_reason = "stop"

    tool = output_tool_name(body)
    if tool is not None:
        message["tool_calls"] = [
            {
                "id": "call_mock_ai",
                "type": "function",
                "function": {"name": tool, "arguments": content},
            }
        ]
        finish_reason = "tool_calls"

    return {
        "id": COMPLETION_ID,
        "object": "chat.completion",
        "created": COMPLETION_CREATED,
        "model": reported_model(body),
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def create_app() -> FastAPI:
    """Build the mock provider. It reads nothing and holds nothing."""
    app = FastAPI(
        title="Pulse Surveys — mock AI provider",
        summary=SUMMARY,
        # No OpenAPI schema, and so no `/docs` and no `/redoc`, exactly as the
        # other two mocks. This service's contract is the OpenAI chat-completions
        # surface, and `GET /mock/rules` is what describes the part of its
        # behaviour a caller actually has to know.
        openapi_url=None,
    )

    @app.get(HEALTH_PATH, summary="Liveness, for the Compose health check")
    def healthz() -> dict[str, str]:
        """Answer from nothing but this process. No downstream, no state."""
        return {"service": SERVICE_NAME, "status": "ok"}

    @app.get(RULES_PATH, summary="Everything this mock decides, and how")
    def rules() -> dict[str, Any]:
        """The published vocabulary (E2-07 criterion 3). See `app.rules`."""
        return served_rules()

    @app.get(MODELS_PATH, summary="The models this endpoint serves")
    def models() -> dict[str, Any]:
        """One model, because an OpenAI-compatible client may probe before it asks.

        A provider library is free to list models before its first completion, and
        a 404 here is a client that never connects — a difference from a real
        endpoint in the one place it stops everything.
        """
        return {
            "object": "list",
            "data": [{"id": DEFAULT_MODEL_NAME, "object": "model", "owned_by": SERVICE_NAME}],
        }

    @app.post(CHAT_COMPLETIONS_PATH, summary="Classify the comment this prompt ends with")
    async def chat_completions(request: Request) -> JSONResponse:
        """The whole of what this service does, in the order `app.rules` publishes.

        Read the prompt, find the student's comment behind the marker, apply the
        rules, and answer. A prompt with no marker is a 500 naming the line it
        looked for, because every quiet answer to "which part of this is the
        comment" is wrong for every request.
        """
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse(
                {
                    "error": {
                        "type": "invalid_request_error",
                        "message": "The request body is not JSON.",
                    }
                },
                status_code=UNREADABLE_REQUEST,
            )
        if not isinstance(body, Mapping):
            return JSONResponse(
                {
                    "error": {
                        "type": "invalid_request_error",
                        "message": "The request body is not a chat-completions object.",
                    }
                },
                status_code=UNREADABLE_REQUEST,
            )

        try:
            comment = extract_comment(prompt_text(body))
        except ExtractionError as failure:
            return JSONResponse(
                {"error": {"type": "extraction_failed", "message": str(failure)}},
                status_code=500,
            )

        answer = classify(comment)
        if answer.stall_seconds:
            # `asyncio.sleep`, never `time.sleep`: this handler runs on the event
            # loop, and blocking it would stall every other request as well —
            # which would make a stalled classification look like a stalled
            # service and take the health check down with it.
            await asyncio.sleep(answer.stall_seconds)
        if answer.status != 200:
            return JSONResponse(answer.payload, status_code=answer.status)
        return JSONResponse(chat_completion(answer.payload, body))

    return app
