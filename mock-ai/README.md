# The mock AI provider

A development-only OpenAI-compatible endpoint, so that the stack can classify a
comment without calling a model anybody pays for. SPEC §9.2 makes an end-to-end
run self-contained in Compose; `mock-lms/` stands in for the LMS and `mock-idp/`
for the identity provider, and this stands in for the third external dependency.

It runs as the Compose service `mock-ai`, on port 8000 inside the network, and
the development override publishes it at <http://localhost:8082> so you can read
its rules in a browser. `.env.example` points `MOCK_AI_PROVIDER_BASE_URL` at
`http://mock-ai:8000/v1`, which is what makes `make up` produce a stack that
classifies and summarizes. (That variable was `AI_PROVIDER_BASE_URL` until the
configuration split of 2026-09-02 gave the real provider and the mock a triple
each; ADR 0118 is the split.)

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

**Two tasks, told apart by a line.** A prompt carrying the summary prompt's
marker line is asking for SPEC §7.4's weekly summary; anything else is a
comment-validity request, which is what this service answered to everything
before E4-05.

For **comment validity**, the student's comment is everything after the last
occurrence of the line the validity prompt's instructions end with, with
surrounding whitespace removed. A comment carrying a copy of that line moves this
boundary to the right, and it stays that way deliberately: the move truncates the
student's own comment before their own verdict, so what it reaches is a wrong
answer about themselves, while taking the *first* occurrence would hand back the
prompt's own instructions whenever the template quoted its marker.
`extract_comment` in `mock-ai/app/rules.py` carries the trade in full.

For the **weekly summary**, the week is the blank-line-separated blocks after the
*first* occurrence of the summary prompt's marker line, and the stream is the
token following the last `Stream under review:` line before it — so no comment can
move that boundary or choose which stream the answer is about. This one is read
*before* the marker rather than after it, which is why it wants the opposite end:
a comment that moved it would put its own text into the instructions the service
reads the stream and the small-N mode out of.

All three strings are copied into `mock-ai/app/rules.py`, because this package
cannot import `backend/app/` — both are called `app` — and unit tests hold the
two marker lines against whichever prompt version `app.ai.tasks` says it renders,
so that an edit to one goes red rather than quiet.

A prompt this service cannot read — no marker line, or a summary prompt naming no
stream — is answered with **HTTP 500 naming what it looked for**. Loudly, because
every quiet answer to "which part of this is the input" is wrong for every
request and looks like a working stack.

## The rules, in the order they are applied

**1. A wrong-answer marker anywhere in the input** — the comment, or any of the
week's comments. First, so that input long enough to be classified normally can
still drive a failure. Each reaches one row of
[ADR 0056](../docs/adr/0056-only-a-timeout-fails-open.md)'s taxonomy from the
tool side:

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
nothing. The summary task's timeout is sixty, so the same stall drives a *late
summary* there rather than a timeout — deliberately: a stall long enough to time
a summary out would hold a test for a minute to reach a row this table already
reaches through the validity task.

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

**4. The summary.** Rules 2 and 3 are the validity task's — a summary has no
closed set of answers to force and no length rule to apply — so a week carrying
no wrong-answer marker is answered here. The payload names the stream the prompt
asked about, its prose says how many comments arrived and how each one opened,
and it carries one theme per comment up to three, each claiming exactly one
comment. Two different weeks are answered differently and the same week twice is
answered identically: the first is what makes a stack prove the week's text
actually left the tool, and the second is what lets the gateway's one bounded
re-ask reach the same answer twice.

## What it is not

- **It is not a model.** It reads a character count, and for a summary it reads
  how many comments there are and how each one begins — never what any of them
  says. A stack pointed here is a stack that is not classifying and not
  summarizing, which is why the eval suite (SPEC §9.3, E2-12) measures the real
  provider and never this — a mock that passed evals would be measuring itself.
- **It authenticates nobody**, holds no credential, and takes no `env_file`.
- **It has no configuration.** Every value it uses has one correct answer, so
  there is nothing to set and no `.env.example` entry to earn (ADR 0037, ADR
  0058).
- **It has no reload.** Like the other two mocks, the development override mounts
  your checkout into the three application containers and not into this one, so
  editing `mock-ai/` means `docker compose up -d --build mock-ai`.
