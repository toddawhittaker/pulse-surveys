# E0-12 — AI output contracts and prompt layout

**ID:** E0-12
**Branch:** `e0/ai-contracts`
**Depends on:** E0-01

## Context

`ai/contracts.py` serves three roles at once: runtime contract, API response
schema, and eval fixture (§7.4). Because an eval case is a typed object rather
than a string comparison, a contract change breaks its evals at type-check time
instead of passing silently. This ticket defines those models before any of them
has a caller, so the shape is decided deliberately rather than falling out of
the first implementation.

Read first: SPEC §7.4 in full (the task table, typed contracts, the single-shot
boundary), §9.3 (evals), §5.1 and §5.2 for what summaries and moderation must
carry, and the AI boundary section of `CLAUDE.md`.

## Scope

- `backend/app/ai/contracts.py` — a Pydantic output model per §7.4 task:
  comment validity, moderation, weekly summary, response draft, draft check.
- Validity returns substantive / insufficient / nonsense. Moderation returns
  clear / harmful / privacy / nonsense / threat / self-harm. Model both as
  enums, not free strings.
- Every model carries the fields needed for auditability: prompt version and
  model ID, per §7.4's requirement that a specific prompt version and model ID
  produced a specific classification.
- `backend/app/ai/prompts/` directory structure, one file per task and version,
  with the version-naming scheme documented.
- Do **not** fork these models for API or eval use — `CLAUDE.md` forbids it. If
  an API response needs a different shape, compose rather than copy.

## Out of scope

- The gateway itself, provider configuration, and any live call (E0-13).
- Prompt *content* beyond a first draft for the validity task — moderation,
  summary, draft, and draft-check prompts belong to E2, E4, E6, and E7.
- Eval sets and the eval runner (E2 onward; the CI job stays tolerant).
- The `classification` and `summary` tables (E0-13 adds what the round-trip
  needs; the rest arrive with their epics).

## Acceptance criteria

- [ ] One Pydantic model per task in §7.4's table, with enum-typed verdicts.
- [ ] Every model requires prompt version and model ID; constructing one without
      them fails validation.
- [ ] A test imports each contract and asserts it round-trips through
      `model_validate_json` for a representative payload.
- [ ] A malformed payload — wrong enum value, missing field — raises
      `ValidationError` rather than coercing.
- [ ] The prompt directory contains a versioned validity prompt and a README
      stating the naming scheme.
- [ ] mypy strict passes on `app/ai/contracts.py`, which is in the strict
      profile.

## Definition of done

**Tests apply.** Unit tests for validation and round-tripping of each contract.
These double as the first eval fixtures, which is the point of the shared model.

**AI evals do not apply yet** — no model task runs. The contracts are what
future eval cases are built from, and the CI eval job stays tolerant.

**Docs apply, briefly.** The prompt-directory README documenting the versioning
scheme.

**Accessibility does not apply.**

**Security review applies but is light.** Nothing executes. Worth confirming no
contract field would carry raw student identity into an AI payload.
