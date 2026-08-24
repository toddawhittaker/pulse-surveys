# E1-14 — `/healthz` and `/dev` get one verdict about the environment name

**ID:** E1-14
**Branch:** `e1/healthz-dev-verdict`
**Depends on:** nothing
**Security-relevant (⚠, small):** the decision is a disclosure decision; the
diff is a few lines either way.

## Context

The carried entry governs, and it is a decision deliberately not made in E0.
`backend/app/api/health.py` tells any unauthenticated caller
`settings.environment` — the value every environment-keyed guard rests on
(`/docs` per ADR 0074, `/dev` per ADR 0079, the cookie's `Secure` per
ADR 0078, SQL echo, the seed guard per ADR 0063). Publishing it opens none of
them and tells a caller which to try first. Separately, `GET /dev` is gated in
the handler, so `POST /dev` answers `405` where an unregistered path answers
`404` — one request confirms both that the build ships the console and that
the environment is not development (measured against the pinned Starlette;
ADR 0079 records it).

The done-when: **one of the three honest answers is chosen and written down —
drop the field, gate it, or keep it with a record saying why the guard list is
acceptable to publish — and the same verdict reaches `/dev`'s method
mismatch**, because a verdict that the name may be published makes the `405`
acceptable, and a verdict that it may not leaves that route still answering.

Read first: the carried entry in full (it holds the three options and their
honest costs); ADRs 0074, 0078, 0079, 0063 (the guard list at stake);
`app/api/health.py` and the `/dev` registration.

## Scope

- Choose. The carried entry's own analysis leans toward the third option
  being defensible (an orchestrator health check is the only consumer; the
  value is `production` in production), but the choice is made at build time
  by whoever holds the full picture, with the ADR carrying the reasoning —
  this ticket does not pre-decide it.
- Apply the verdict to both routes consistently: the `/healthz` field per the
  choice, and `/dev` either registered for every method / gated at
  registration (if the name is not publishable) or left as measured with the
  ADR saying the `405` is within the accepted disclosure (if it is).
- The ADR updates or supersedes-in-part ADR 0079's decision-section note, so
  the mismatch stops being an open observation.

## Acceptance criteria

1. One ADR records the verdict, its costs, and the guard list considered.
2. Tests pin the chosen behavior on both routes — including the negative
   space (whichever of the field / the 405 the verdict removes is asserted
   absent, so a regression cannot quietly restore it).
3. Whatever an orchestrator's health check consumed keeps working, or the
   operator-facing change is in the README/config docs (§14.2 item 5).

## Out of scope

- Authentication for observability surfaces generally (E11's console has its
  own model).
- Any other field `/healthz` serves.
