# 0053 — The gateway reaches an OpenAI-compatible endpoint through `pydantic-ai-slim[openai]`

**Status:** Accepted — Todd's decision, 2026-08-18. SPEC §7.4's sentence stands:
`pydantic-ai` is what ships.
**Date:** 2026-08-18
**Tickets:** E0-13

## Context

SPEC §7.4 puts every model call behind one internal gateway and then names an
implementation for it:

> `pydantic-ai` is the intended implementation (model-agnostic across
> OpenAI-compatible endpoints, typed outputs, instrumentation that feeds the
> admin console's per-task metrics); it is young and fast-moving, so pin it and
> keep the gateway interface thin enough that replacing it is a day's work.

What that sentence does not weigh is what the package brings with it.
`pydantic-ai` is a metapackage: it depends on `pydantic-ai-slim` with the
`anthropic`, `cli`, `evals`, `google`, `logfire`, `mcp`, `openai`, `retries` and
`web` extras all turned on. Resolved against PyPI with
`pip install --dry-run --report`, three candidates:

| candidate | packages in the resolved closure |
|---|---|
| `pydantic-ai` | 100 |
| `pydantic-ai-slim[openai]` | 30 |
| the `openai` SDK alone | 16 |

The seventy the metapackage adds over the slim distribution include two other
model SDKs (`anthropic`, `google-genai`), an MCP client stack, a telemetry client
(`logfire`, with five OpenTelemetry packages under it), a terminal UI
(`prompt_toolkit`, `rich`, `pyperclip`, `argcomplete`) and a credential store
(`keyring`, `SecretStorage`, `jeepney` — a D-Bus client).

The process that would carry them is the one that ships student comment text to a
third party. §4 makes that text confidential, §10 puts this project's secrets in
its environment, and `docker-compose.yml` deliberately withholds the Care
credential from `worker` for exactly that reason.

**This record was first written for a different decision.** The implementer built
against the `openai` SDK, argued the footprint above, and — since that
contradicts §7.4's sentence — raised it rather than editing the spec, as
`CLAUDE.md` requires. Todd's answer was that the middle option existed and is the
right one. The measurement survives because it is what produced the decision; the
decision is his.

## Decision

**`backend/app/ai/gateway.py` uses `pydantic-ai`, installed as
`pydantic-ai-slim[openai]` and pinned exactly.** It is the only module under
`backend/app/` that imports a provider library, which the confinement sweep in
`tests/unit/` enforces. Nothing in this project imports `openai`, although the
extra installs it: the SDK is what the library talks to, not what this project
writes against.

Three consequences of that choice are decisions in their own right, and they are
recorded here because a reasonable engineer would make them differently:

**The model is never asked for the contract; it is asked for the contract minus
the audit pair.** `CommentValidityOutput` *requires* `prompt_version` and
`model_id`, and [ADR 0031](0031-every-task-contract-carries-the-prompt-version-and-model-id.md)
forbids a model supplying either — so handing the contract to the library as its
output type would put both fields in the JSON schema the endpoint is asked to
fill. `_payload_model` derives the payload shape from the contract instead,
carrying the contract's own `extra="forbid"`, so a model that reports an audit
field fails validation before anything is merged. That is ADR 0031's "reject the
payload before merging anything into it", enforced by the type rather than by a
check somebody has to remember to write.

**Output mode is `NativeOutput`, not the library's default tool output.** §7.4:
"one call in, one validated object out — **no tool use**, no planning loop, no
iterative retrieval." Native output asks for a JSON object against the payload's
schema, so the request carries `response_format` and declares no tool at all. It
also keeps the wire agreeing with the prompt, which tells the model to "return
only this JSON object".

**The library's feedback retry is off; the gateway re-asks instead.**
`pydantic-ai` can send a failed answer back to the model with the validation
error attached. That appends a message *after* the one ending in the student's
comment, and `app/ai/prompts/README.md` rests the whole injection boundary on
there being nothing after it: "'To the end of the message' cannot be forged, and
it means the gateway must append nothing after the comment." So `retries=0` on
the agent, and one bounded re-ask in `run_task`.

## Alternatives rejected

**`pydantic-ai`, the metapackage, as §7.4 spells it.** Rejected on the closure
above. It is the same library and the same import root, so no code changes with
it — which is precisely why the other eight extras are not worth carrying.

**The `openai` SDK directly**, which is what this record first held. Sixteen
packages, and every one of §7.4's three reasons for the library would then be
this project's to build: the typed-output plumbing (a hand-written JSON parse and
merge), the model-agnosticism (only as far as the OpenAI wire protocol reaches),
and the instrumentation. It also contradicts a spec sentence to save fourteen
packages, which is not a trade worth making in a foundations epic.

**A plain `httpx` client speaking the chat-completions protocol.** Zero new
dependencies, and about forty lines for one request. Rejected because it puts
this project in the business of tracking a protocol it does not own — retry
semantics, streaming, error shapes, the `Authorization` header, and every
endpoint's variation on all four.

**`litellm`.** Broader endpoint coverage than any of the above, and a much larger
surface than a project with one configured endpoint needs. Nothing in the spec
asks for routing across providers at runtime.

**Letting the library's retry argue with the model**, rather than re-asking.
Genuinely better at recovering: a model told what was wrong with its answer often
fixes it, while a model that made its mistake deterministically will make it
again on an identical re-ask. Rejected on the prompt layout above. The cost is
real, and is written into `run_task`'s docstring rather than left for somebody to
discover.

## Consequences

**Nineteen new runtime packages**, against four for the `openai` SDK alone and
about eighty-five for the metapackage. `pip-audit` reports no known vulnerability
in the closure. The license gate passes and reports two new `unknown`
classifications, neither of which fails it: `regex` declares `Apache-2.0 AND
CNRI-Python`, whose second half no rule names, and `tiktoken` ships the full MIT
licence *text*, whose all-caps disclaimer contains the word "AND" — so the
checker reads it as a conjunction and cannot classify every part. Both are
permissive in fact. Widening `scripts/ci/check_licenses.py` to say so is a change
to a gate, and is not made here.

**`Agent.run_sync` is unusable in this project, and the gateway drives a loop
itself.** It calls `asyncio.get_event_loop()`, which emits a `DeprecationWarning`
on a thread with no loop set; `pyproject.toml` turns a `DeprecationWarning` into
an error on purpose, so every model call failed under the suite the first time
this was wired. `asyncio.run` per call is not the fix either — the client's
connection pool binds to the loop that first used it, so the second call would
reach into a closed one.

**And the loop cannot be separated from the client**, which the first fix got
wrong and E0-13's review measured: one shared client across per-thread loops
answered every *second* submission from the character floor while the provider was
healthy, because a pooled connection raises when it is reused from another loop
and the layers above report that as "could not be reached". `_ThreadBound` now
holds the loop, the client and the agents together, one per thread, and
`app.ai.tasks` shares a single gateway so the count is bounded by threads rather
than by comments. Measured after the fix: 100 calls over a four-thread pool, 100
real verdicts, and file descriptors flat at a ceiling reached during the first
batch. This is the one piece of machinery in the gateway that exists because of
the library rather than because of the spec, and it goes when `run_sync` stops
calling a deprecated API.

**The client's own retry has to be turned off, and the only way in is the
provider's client object.** Left at its default of two, `openai` retries a
timeout twice *inside* one call: measured against a stub that never answers, a
four-second per-task timeout took 13.3 seconds and three requests to fail open —
against §3.3's p95 budget of two seconds. `OpenAIProvider` takes no retry
argument, so `provider.client.max_retries = 0` reaches for the object it built.
The alternative is constructing the client here, which means importing `openai`
in this file and making it the second provider-library importer.

**Diagnostics are thinner than they were.** The `openai`-SDK version parsed the
answer itself and could name each failing field with its pydantic error code. The
library validates internally and raises `UnexpectedModelBehavior`, whose detail
sits on a chained `ToolRetryError` — reachable, and read by `_describe` for the
field paths and error codes only, because the same structure carries the model's
own text in `input`, and that text may quote a student's comment.

**§6.1's per-task metrics now have a library that can feed them**, which is the
half of §7.4's parenthetical the `openai` SDK would have given up: `pydantic-ai`
carries OpenTelemetry instrumentation, off by default, and E11 can turn it on
rather than writing counters at the call site.

**Replacing the library is still one file.** `run_task` takes prompt text, a
contract and a timeout, and returns a validated instance; nothing else in
`backend/app/` knows what is underneath it. That property is what made this
reversal cheap, and it is now measured rather than asserted: swapping the
`openai` SDK for `pydantic-ai` touched `gateway.py`, one line of `pyproject.toml`,
the two lockfiles — and no other module, no caller, and no test.
