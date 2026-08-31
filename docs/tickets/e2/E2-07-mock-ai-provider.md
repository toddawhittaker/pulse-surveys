# E2-07 — A mock AI provider joins the Compose stack

**ID:** E2-07
**Branch:** `e2/mock-ai-provider`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** a new container is where a service gets exposed or
hidden — the compose review reads the merged configuration, not one file
(the closed-set lesson from E1's reviews). The mock must not be reachable
beyond what development needs, and nothing may point production at it.

## Context

SPEC §9.2 makes e2e runs fully self-contained in Compose — that is why the
mock LMS and mock IdP exist. The validity classifier is the third external
dependency, and today the running stack has no stand-in for it: the gateway's
stub lives inside one integration test file as a loopback server
(`tests/integration/test_ai_gateway_validity_roundtrip.py`), unreachable from
Compose. Without this ticket, every interactive session and every e2e run
either burns real tokens or exercises only the fail-open timeout path — four
seconds of dead wait per submit, and the "bounced with immediate feedback"
exit clause never actually tested against a verdict.

Todd's constraint, decided 2026-08-31: no live AI calls in ordinary runs.
Live calls happen only in the eval suite (E2-12), path-filtered and manual.
Everything else — dev, e2e, CI — talks to this mock.

Read first: SPEC §7.4 (single-shot boundary, typed contracts); ADR 0053 (the
gateway speaks OpenAI-format chat completions through pydantic-ai — the mock
implements the platform side of exactly that); ADR 0037/0038 (compose
conventions for mocks); the stub classes in the roundtrip test (the wire
format is already worked out there); `mock-lms/` and `mock-idp/` for the
service pattern; ADR 0056 (only a timeout fails open — the mock is what lets
the *non*-timeout paths run in a browser).

## Scope

- A small FastAPI service (`mock-ai/`, following the mock pattern) speaking
  the OpenAI-compatible chat-completions surface the gateway uses, returning
  deterministic `CommentValidityOutput`-shaped verdicts by simple published
  rules — rules a test can aim at on purpose (e.g. marker phrases and a
  length rule; the mock's README states them; `"it was okay"` must classify
  insufficient so the spec's own example works end to end).
- Deliberately wrong answers on request, the `mock-lms` wrong-launches
  precedent: a malformed shape, a delayed answer past the 4s budget, a 500 —
  selectable per request, so e2e can drive the fail-open and shape-retry
  paths without patching the backend.
- Compose wiring: the backend and worker reach it by service name;
  `.env.example` documents pointing `AI_PROVIDER_BASE_URL` at it for
  development. Decide host exposure (the other mocks publish 8080/8081; 8082
  if debugging wants it) and defend it in the PR against the merged compose
  config.
- Nothing in the backend changes: the gateway cannot tell this mock from a
  provider, which is the point.

## Acceptance criteria

1. `make up`, `.env` pointed at the mock: a submit through the real gateway
   classifies deterministically with no external call and no 4s stall.
2. The wrong-answer selectors work: one e2e-reachable path each for timeout
   (fail-open floor applies, ADR 0056) and malformed shape (one retry, then
   the error surface), driven from the mock, asserted from the tool side.
3. The mock's rules are served, not copied: its README/route states them, and
   the tests that aim at them read the served statement (the E1-07
   `ALL_SELECTORS` lesson — no second hand-held copy).
4. CI's e2e job runs against it with no `secrets.*` reference anywhere.

## Out of scope

- Moderation, summary, draft, and draft-check verdicts — each lands with the
  epic that builds its task (E4, E6, E7); the mock grows then.
- Any eval-suite use — evals measure the real model (E2-12); a mock that
  passed evals would be measuring itself.
- Prompt rendering or contract changes in `backend/app/ai/`.
