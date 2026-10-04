# 0185 — The frontend wire types are generated from the OpenAPI schema

**Status:** Accepted, superseding [0117](0117-the-survey-screen-calls-two-endpoints-by-hand.md) in part
**Date:** 2026-10-03
**Ticket:** [E5.1-06](../tickets/e5.1/E5.1-06-generated-wire-types.md)

## Context

ADR 0117 kept the frontend's wire types as a transcription of the backend's
schemas, and named the cost: nothing checked it, so a renamed member went stale
silently. It also said when to revisit: when the surface grew. By E5 three
client modules held more than thirty wire types, and the copies had spread past
them into two components. The owner ruled that the types are generated from OpenAPI, as
types only and not as a client, by a pinned generator, with a check that fails
when they are stale.

## Decision

**Types only.** `openapi-typescript`, exact-pinned at 7.13.0 as a frontend dev
dependency, turns a committed `frontend/src/api/openapi.json` into a committed
`frontend/src/api/wire.gen.ts` (`npm run gen:wire --workspace frontend`, with
`--immutable` so the types stay read-only as the hand-written ones were).
`scripts/export_openapi.py` writes the JSON from `create_app().openapi()`, which
produces the same document whether or not the served route is on (ADR 0074).
The calls stay hand-written, as ADR 0117 decided.

**The generator's peer range is overridden, not relaxed.** It declares
`typescript: ^5.x` and the repository pins 6.0.3, so the root `package.json`
carries `"overrides": {"openapi-typescript": {"typescript": "$typescript"}}`.
That names the one package and points it at the repository's own compiler.

**Two stale checks, each inside a job CI already runs.** A unit test compares
the export script's `render()` with the committed JSON, so a backend change
that was not exported fails the pytest job. A vitest test runs the real
generator command line into a temporary file and compares it with the committed
`wire.gen.ts`, so a JSON change that was not regenerated fails the frontend
unit-test job. No workflow changes.

**A sweep keeps the types generated.** `frontend/src/api/wireTypes.test.ts`
fails on any `interface` in a client module and on any exported type that does
not read `components['schemas']`, except types named `…Read` or `…Outcome`,
which are the frontend's own outcome unions. Where a client type departs from
the generated shape (the report omits a member nothing reads; members added to
a live payload stay optional for older answers), it is built from the generated
type rather than written beside it.

## Alternatives rejected

- **A generated client or query hooks.** The ruling excludes them, and ADR
  0117's reason still holds: each call's interesting part is its status table
  and which server sentence each status carries, and a client would not write
  that.
- **The generator's programmatic API in the stale test.** It would be a second
  way of generating that nobody runs, and could agree with itself while the
  script disagreed. The test runs the same command line as `gen:wire`.
- **`legacy-peer-deps` or an `.npmrc` change.** Either one relaxes peer
  resolution for every package, not just this one.
- **A separate CI step for the checks.** It would mean a workflow change, which
  is a `process/` pull request, and it would buy nothing the two existing jobs
  do not already run.

## Consequences

- A backend schema change now needs two regeneration commands in the same
  pull request: `PYTHONPATH=backend python scripts/export_openapi.py`, then
  `npm run gen:wire --workspace frontend`. The failing test names both.
- `openapi.json` is committed, so a schema change shows up in review as a
  readable diff.
- The `…Read`/`…Outcome` exemption is a naming rule. A hand-written wire type
  given one of those names would pass the sweep, so a review still has to read
  the name.
- The trend chart's own test refuses any import from `api/`, so the chart takes
  the shared figure type through `lib/shownFigure.ts` and keeps its series
  types local.
