# 0053 — The gateway reaches an OpenAI-compatible endpoint through the `openai` SDK

**Status:** Accepted, and it contradicts a sentence in SPEC §7.4 — raised in
E0-13's pull request rather than settled here.
**Date:** 2026-08-17
**Tickets:** E0-13

## Context

SPEC §7.4 puts every model call behind one internal gateway and then names an
implementation for it:

> `pydantic-ai` is the intended implementation (model-agnostic across
> OpenAI-compatible endpoints, typed outputs, instrumentation that feeds the
> admin console's per-task metrics); it is young and fast-moving, so pin it and
> keep the gateway interface thin enough that replacing it is a day's work.

Two of that sentence's three reasons are already satisfied elsewhere in this
codebase. E0-12 shipped the typed outputs as Pydantic contracts that are
simultaneously the runtime contract, the API response schema and §9.3's eval
fixtures, and the gateway validates against them itself. Model-agnosticism is a
property of speaking the OpenAI wire protocol against a configured base URL,
which every candidate here does. The third — instrumentation feeding §6.1's
per-task metrics — is real and is E11's.

What the sentence does not weigh is what the package brings with it. Measured on
the day, with `pip install --dry-run --report`:

| candidate | packages in the resolved closure |
|---|---|
| `pydantic-ai==2.31.0` | 100 |
| `openai==2.54.0` | 16, of which 4 are new to this project |

`pydantic-ai` is a metapackage: it depends on `pydantic-ai-slim` with the
`anthropic`, `cli`, `evals`, `google`, `logfire`, `mcp`, `openai`, `retries` and
`web` extras all turned on. So the hundred include two other model SDKs
(`anthropic`, `google-genai`), an MCP client stack, a telemetry client
(`logfire`, with five OpenTelemetry packages under it), a terminal UI
(`prompt_toolkit`, `rich`, `pyperclip`, `argcomplete`) and a credential store
(`keyring`, `SecretStorage`, `jeepney` — a D-Bus client).

`pydantic-ai-slim[openai]` would be a fair fraction of that, and it is not
available: E0-13's suite asserts that whichever provider library the gateway
imports is pinned in `pyproject.toml` under the distribution that supplies it,
and the mapping it holds is `pydantic_ai → pydantic-ai`. A `pydantic-ai-slim==`
line does not satisfy it.

The process that would carry those hundred packages is the one that ships student
comment text to a third party — §4 makes that text confidential, §10 puts the
project's secrets in its environment, and `worker` is deliberately the container
that holds no route to a student's name.

## Decision

**`backend/app/ai/gateway.py` uses the official `openai` SDK, pinned at
`openai==2.54.0`, against `AI_PROVIDER_BASE_URL`.** It is the only module under
`backend/app/` that imports a provider library, which
`tests/unit/test_provider_library_is_confined_to_the_gateway.py` enforces.

The 2.x line rather than 3.x: `openai>=3` depends on `httpx2`, and this project
already pins `httpx` for the mock platform and the health checks. Two HTTP client
stacks in one image buy nothing.

Everything §7.4 asks the gateway to do is done in that one file and is not
delegated to the library: the contract validation, the retry on a shape
violation, the refusal of a payload that supplies its own audit fields (ADR
0031), the per-task timeout, and the failure classes a caller branches on.

**This contradicts SPEC §7.4's sentence, so the sentence is raised rather than
edited.** `CLAUDE.md`: "If a decision contradicts the spec, an ADR is not
sufficient. Raise it, and update the spec." The proposed replacement is in E0-13's
pull request body, and it is Todd's to accept or reject. If he rejects it, the
change is this file plus one line of `pyproject.toml` — which is the criterion
this ticket was measured against anyway.

## Alternatives rejected

**`pydantic-ai`, as §7.4 names it.** Rejected on the closure above, and on a
second thing the measurement made visible: the library's structured-output modes
want to validate the model's answer *directly* into the output type, and
`CommentValidityOutput` cannot be that type. It requires `prompt_version` and
`model_id`, and ADR 0031 forbids the model supplying either — so the payload the
model returns is a strictly smaller shape, and the merge is the gateway's work
whichever library carries the request. The library's own retry-with-feedback loop
is also more than §7.4 permits: it sends the validation error back to the model
and asks again, which is a two-turn conversation inside a boundary the spec
writes as "one call in, one validated object out".

**A plain `httpx` client speaking the chat-completions protocol.** Genuinely
attractive: zero new dependencies, and the wire format for one request is about
forty lines. Rejected because it puts this project in the business of tracking a
protocol it does not own — retry semantics, streaming, error shapes, the
`Authorization` header, and every endpoint's variation on all four — and because
E0-13's own suite treats "no module imports a provider library" as the state
before this ticket lands rather than as a design. It would also want its own ADR
and its own change to that test, for a saving of four packages.

**`litellm`.** Broader endpoint coverage than either, and a much larger surface
than a project with one hosted endpoint needs. Nothing in the spec asks for
routing across providers at runtime.

## Consequences

**Four new runtime packages**: `openai`, and `distro`, `jiter` and `tqdm` under
it. `pip-audit` reports no known vulnerability in the closure and the license gate
classifies all four as permissive.

**§6.1's per-task metrics get no instrumentation for free.** §7.4's parenthetical
counted `pydantic-ai`'s hooks as a reason for choosing it, and this trades them
away. What E11 needs — task, prompt version, model ID, latency, outcome — is
available at the one call site in `gateway.py`, and the first three are already
stored on every `classification` row. The cost is that somebody writes the timing
and the counter there rather than switching on a library's exporter.

**The single-shot boundary is enforced by this file rather than by a library's
defaults.** `SHAPE_VIOLATION_ATTEMPTS = 2` and a request that declares no tools
are the whole of it, and
`test_a_well_formed_first_answer_is_not_followed_by_a_second_call` is what keeps
it from drifting.

**Replacing the library is still one file.** That is the property §7.4 asks for
and the reason this decision is cheap to reverse: `run_task` takes prompt text, a
contract and a timeout, and returns a validated instance. Nothing else in
`backend/app/` knows what is underneath it.
