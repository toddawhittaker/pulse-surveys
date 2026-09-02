# The eval sets and the floors that gate on them

SPEC §9.3, made executable. This directory holds the only code in the repository
that deliberately calls a paid model provider.

```
python -m tests.evals.runner --enforce-floors
```

Run it from the repository root, with `AI_PROVIDER_API_KEY` set. `make evals`
does the same thing from `.env`.

## When it runs

Three situations, and no others.

1. **On a pull request whose diff touches the AI surface.** `scripts/ci/classify_
   changed_paths.py` answers `ai_surface` for a diff touching `backend/app/ai/`,
   `tests/evals/`, `backend/app/config.py` or `.env.example`, and the `evals`
   job's live steps are conditioned on that answer *and* on the diff not being
   inert documentation. The path set is what SPEC §9.3's gate names — prompt or
   model — plus the two files that carry the model identifier.
2. **On demand**, through `workflow_dispatch` on the CI workflow.
3. **Locally**, through `make evals`.

Ordinary test runs never call a provider. They reach the loopback stub in
`tests/integration/test_ai_gateway_validity_roundtrip.py` or E2-07's `mock-ai`
service, and neither costs anything or leaves the machine.

## What it costs

One model call per case, per graded task. The comment-validity set is 98 cases,
so a full run is 98 calls — cents, not dollars, at any provider this project
would use. The design that keeps it that way is the firing condition above:
hundreds of live calls on every merge is exactly what this arrangement refuses.

**The run reports its own figures, so this does not have to be estimated.** Each
answered case comes back with the gateway's `TaskUsage` beside the verdict, and
the report prints the totals: input tokens with the cache-read share shown inside
them rather than added to them, output tokens, and the number of provider
requests. Two things about that line matter before anyone compares it with an
invoice — a cache read is a *part* of the input count, and a call the gateway
retried contributes only the request that answered, so the figures are a floor on
what the run cost rather than a complete account of it. The line says so itself.

A run is not free of wall clock either. The calls are sequential, and the eval
timeout is sixty seconds rather than §3.3's four: that budget is a student's, and
using it here let a merely slow answer be replaced by a character count. Two full
runs were voided that way before the two timeouts were separated
(`docs/disputes/E2-12-06.md`). Expect a few minutes.

## The layout

- `declarations.py` — the case, floor and task types, and the usage totals a run
  accumulates. Three floor states, and the module docstring argues why three
  rather than two.
- `measure.py` — precision and recall over one task's answers.
- `live.py` — the gateway built `live=True`, and the one call the run makes into
  it, at the eval timeout rather than the submit path's.
- `registry.py` — every task the runner walks.
- `runner.py` — the command line, the refusals, the comparison, and the cost.
- `validity/` — SPEC §3.3's comment-validity set and its floor.
- `threat/` — SPEC §9.3's strictest floor, as a slot with no set and no number.
  E10 sets it.

## The floors

Each task's floor lives beside its own set, so lowering one is a diff in the
directory of the cases it governs. `CLAUDE.md`: floors move only in a deliberate
pull request whose subject is moving them, and the threat and self-harm recall
floor is a hard gate whose lowering is the repository owner's call.

The comment-validity floor is **not set yet**. It ships as a placeholder and the
runner refuses on it, because a floor picked before anything was measured is a
number chosen to make the first run pass. `tests/evals/validity/floors.py` says
what filling it in looks like.

## What a refusal means

The runner exits non-zero and names what is missing. It never reports a pass over
a task it did not grade — a missing credential, a floor with no set, an unfilled
placeholder and an answer produced under the wrong prompt version are all
refusals, not skips. An AI-touching pull request that cannot reach a provider is
a red gate saying so.
