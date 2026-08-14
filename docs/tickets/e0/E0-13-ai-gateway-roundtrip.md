# E0-13 — AIGateway shell and one working round-trip

**ID:** E0-13
**Branch:** `e0/ai-gateway-roundtrip`
**Depends on:** E0-04, E0-12

## Context

E0's exit criterion includes one working AI task round-trip: a comment goes in,
a validated Pydantic object comes back, and the prompt version and model ID are
recorded. The gateway is deliberately thin — `pydantic-ai` is young and
fast-moving, so the interface must stay replaceable in about a day's work
(§7.4).

Read first: SPEC §7.4 (single-shot boundary, typed contracts, the note on
pinning `pydantic-ai`), §3.3 (validity gating and fail-open), §6.3 (AI provider
configuration), the AI boundary section of `CLAUDE.md`, and **"What the built
tickets settled" in [the epic README](README.md)**.

Two of those rules reach this ticket. The `classification` table means a model
module, so it needs registering in `app/models/__init__.py` and must import
`Base` from `app.models.base`. And the AI provider variables need `Settings`
fields to resolve them before `.env.example` can document them — which this
ticket is adding anyway, so the order is what matters, not the work.

## Scope

- `backend/app/ai/gateway.py` — provider-agnostic client against an
  OpenAI-compatible base URL, with per-task timeout and retry, returning a
  validated contract object.
- One call in, one validated object out. No tool use, no planning loop, no
  iterative retrieval — the single-shot boundary is a hard constraint, not a
  starting point.
- `backend/app/ai/tasks.py` with the comment-validity task implemented end to
  end against the E0-12 contract and prompt.
- Retry on shape violation, surfacing persistent failure as an error rather than
  letting a malformed classification propagate.
- **Fail-open on provider timeout**: the character-heuristic floor applies, the
  submission is accepted, and classification runs async. Never block a student
  on a provider outage. E2 wires this into the real submit path; E0 proves the
  gateway behaves this way.
- A minimal `classification` table storing the verdict with prompt version and
  model ID, append-only (re-runs create new rows, per §8).
- Provider configuration from `Settings`: base URL, model, and a masked key.
  **The key is a secret** — follow `CLAUDE.md`: do not add a `secrets.*`
  reference to any workflow without asking first.
- A recorded or stubbed provider for tests so the suite never makes a live call.

## Out of scope

- The four other tasks — moderation, summary, draft, draft check (E2, E4, E6,
  E7). Their contracts exist; their prompts and calls do not.
- Eval sets, the eval runner, and precision/recall floors (E2 onward). The CI
  eval job stays tolerant.
- The synchronous submit path and the p95 budget it must meet (E2).
- Admin console AI metrics and the drift panel (E11).

## Acceptance criteria

- [ ] A validity call against the stub provider returns a validated contract
      object with prompt version and model ID populated.
- [ ] A malformed provider response triggers a retry, and a persistently
      malformed one raises rather than returning a partial object.
- [ ] A simulated provider timeout returns the heuristic-floor result and does
      not raise — the fail-open path, asserted by test.
- [ ] Re-running classification for the same comment creates a second row rather
      than updating the first.
- [ ] No test makes a live network call; the suite passes with no provider key
      set.
- [ ] The gateway interface is small enough that swapping the provider library
      touches one file — state the file count in the pull request.
- [ ] No `secrets.*` reference was added to a workflow without prior agreement.

## Definition of done

**Tests apply.** Unit tests for validation, retry, and the fail-open timeout
path against a stubbed provider. One integration test persisting a
classification row.

**AI evals apply in a limited sense.** No eval set ships here, but the contract
must be usable as an eval fixture — assert that in a test, since §7.4 makes that
a design requirement rather than a convenience.

**Docs apply.** `.env.example` gains the AI provider variables with placeholder
values. `README.md` notes how to run without a provider key.

**Accessibility does not apply.**

**Security review applies and matters here.** Review for the provider key
reaching a log or an error message, for student text being sent with identity
attached, and for the fail-open path failing *open* in the intended sense —
accepting the submission — rather than open in the sense of skipping a safety
classification silently.
