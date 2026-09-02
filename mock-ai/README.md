# The mock AI provider

A development-only OpenAI-compatible endpoint, so that the stack can classify a
comment without calling a model anybody pays for. SPEC §9.2 makes an end-to-end
run self-contained in Compose; `mock-lms/` stands in for the LMS and `mock-idp/`
for the identity provider, and this stands in for the third external dependency.

It runs as the Compose service `mock-ai`, on port 8000 inside the network, and
the development override publishes it at <http://localhost:8082> so you can read
its rules in a browser. `.env.example` points `AI_PROVIDER_BASE_URL` at
`http://mock-ai:8000/v1`, which is what makes `make up` produce a stack that
classifies.

**Nothing outside development may point at it.** `app.config.Settings` refuses an
`AI_PROVIDER_BASE_URL` whose host is `mock-ai` anywhere `ENVIRONMENT` is not
`development` — see
[ADR 0113](../docs/adr/0113-the-mock-model-provider-is-development-only-and-selects-in-band.md).
A deployment that reached this service would store a character count as a
classification, under a real prompt version and a real model id, with nothing
saying a model was never asked.

## The routes

| Route | What it is |
|---|---|
| `POST /v1/chat/completions` | The completion the gateway asks for (ADR 0053) |
| `GET /v1/models` | The listing a client library may probe before it asks |
| `GET /healthz` | Liveness, for the Compose health check |
| `GET /mock/rules` | Everything below, as JSON |

**`GET /mock/rules` is the statement, and this page is the paraphrase.** The
tests read the route; nothing asserts against this file. If the two ever
disagree, the route is right — it is built from the constants
`mock-ai/app/rules.py` applies.

## What it does with a prompt

The student's comment is **everything after the last occurrence of the line the
validity prompt's instructions end with**, with surrounding whitespace removed.
That line is copied into `mock-ai/app/rules.py` as `MARKER_LINE`, because this
package cannot import `backend/app/` — both are called `app` — and a unit test
holds the copy against `backend/app/ai/prompts/validity.v1.md` so that an edit to
one goes red rather than quiet.

A prompt carrying no copy of that line is answered with **HTTP 500 naming the
line it looked for**. Loudly, because every quiet answer to "which part of this is
the comment" is wrong for every request and looks like a working stack.

## The rules, in the order they are applied

**1. A wrong-answer marker anywhere in the comment.** First, so that a comment
long enough to be classified normally can still drive a failure. Each reaches one
row of [ADR 0056](../docs/adr/0056-only-a-timeout-fails-open.md)'s taxonomy from
the tool side:

| Marker | What this service answers | What the gateway raises |
|---|---|---|
| `mock-ai:503` | HTTP 503 | `AIProviderUnavailableError` — SPEC §3.3's floor applies |
| `mock-ai:500` | HTTP 500 | `AIProviderRefusedError` — nothing floors |
| `mock-ai:malformed` | HTTP 200, a valid envelope, the payload `{"answer": 42}` | `AIResponseInvalidError`, after one re-ask |
| `mock-ai:stall` | `substantive`, six seconds late | `AIProviderUnavailableError` — the read timeout |

The first two are one status code apart on purpose: they are the near miss that
separates ADR 0056's unavailable row from its refused row, which is why 503 and
500 both exist here. The stall is six seconds because the validity task's
per-task timeout is four; a stall inside that budget answers in time and drives
nothing.

**2. A forced verdict**, so an end-to-end run can drive a particular
classification without patching the backend: `mock-ai:substantive`,
`mock-ai:insufficient`, `mock-ai:nonsense`.

**3. The character rule.** A comment of fewer than **25** characters is
`insufficient`; anything else is `substantive`. That is SPEC §3.3's own
heuristic, reused so that the spec's example of a comment that must be bounced —
`"it was okay"` — classifies `insufficient` through a running stack.

**`nonsense` is reachable only by its marker.** Rule 3 has two outcomes and not
three: deciding that a comment is keyboard mashing is a judgement about content,
and this service makes none.

## What it is not

- **It is not a model.** It reads a character count. A stack pointed here is a
  stack that is not classifying, which is why the eval suite (SPEC §9.3, E2-12)
  measures the real one and never this — a mock that passed evals would be
  measuring itself.
- **It authenticates nobody**, holds no credential, and takes no `env_file`.
- **It has no configuration.** Every value it uses has one correct answer, so
  there is nothing to set and no `.env.example` entry to earn (ADR 0037, ADR
  0058).
- **It has no reload.** Like the other two mocks, the development override mounts
  your checkout into the three application containers and not into this one, so
  editing `mock-ai/` means `docker compose up -d --build mock-ai`.
