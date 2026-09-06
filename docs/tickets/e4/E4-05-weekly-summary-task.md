# E4-05 — The weekly summary task

**ID:** E4-05
**Branch:** `e4/weekly-summary-task`
**Depends on:** nothing
**Lane:** heavy — `backend/app/ai/` matches no lane row and sits under
`backend/app/`, so the fail-closed rule applies. Named out loud because the
lane table's closing paragraph also says `backend/app/ai/` belongs in no
heavy-lane row (it is a review trigger, not a lane row): the fail-closed
paragraph still governs the lane, and doubt means heavy — a mid-build
re-lane argument is settled here, not at the PR.
**Security-relevant:** comment text leaves the database and goes to the AI
provider — the same boundary the validity task already crosses, with the
same rules: no identity accompanies it, and the output is a typed contract,
never trusted prose. `app-security` fires on the diff per `review-pr`'s
table, and `prompt-eval` runs per-PR on this ticket by the exception the
epic README declares at breakdown.

## Context

§7.4's third task: **Weekly summary** — "per-stream, per-node themed
summaries under the §5.1 contracts." The §5.1 contracts, spelled out:
criticism is preserved, never sanded off; the summary states the response
count it draws from; flagged-held content is excluded, and above small-N the
summary may note "one comment is held for review" with type only; and a
summary is generated even in small-N weeks, where it is the only comment
signal an instructor gets.

This ticket is the task alone — prompt, typed contract, gateway wiring, eval
cases — with no job and no schedule, for the reason E3 split the formula
from the sweep: the prompt is where a wrong answer is invisible. A fluent
summary that quietly drops the week's sharpest criticism passes every shape
check and defeats the product's purpose; only eval cases catch it.

The single-shot boundary (§7.4) governs: one call in, one validated object
out, no tool use, no loop. Prompts are versioned in-repo; every stored
summary records prompt version and model id (E4-02's columns).

Read first: SPEC §5.1, §7.4, §9.3; `backend/app/ai/gateway.py`,
`contracts.py`, `tasks.py` and `prompts/validity.v2.md` (the existing task's
shape end to end); `tests/evals/` layout; ADR 0002 on gate tolerances.

## Scope

- `prompts/summary.v1.md`, versioned like validity's.
- The typed contract in `contracts.py`: the summary text, the themes it
  found, and room for the held-note (type only) that E6's moderation will
  make real. The stated response count is injected by the caller from data,
  never trusted from the model — the contract carries what the model must
  produce, and the ADR draws that line explicitly.
- The gateway task in `tasks.py`, per-stream: the input is the week's
  comments for one stream (under-threshold ones included — §4 says they feed
  the summary), with no identity, no section code, no user id in the prompt.
- Eval cases in `tests/evals/`: the §5.1 contract as typed cases —
  criticism preserved through paraphrase, a small-N week's two comments
  still summarized, an empty week producing the contract's empty shape, a
  mixed week where both praise and a specific complaint survive. The
  validity set's fluent-off-topic family (ten cases, FIX-02, 2026-09-03,
  `tests/evals/validity/cases.py`) is prior art for case design here — it
  already exists and nothing in this ticket re-adds it.

## Acceptance criteria

1. The task round-trips against the mock AI service in CI: typed contract
   validated, shape violations retried, persistent failure surfacing as the
   gateway's error, never as prose passed through.
2. No identity crosses the boundary: a test asserts the rendered prompt for
   a planted week contains no user id, no name-shaped seed data, and no
   section code.
3. The criticism-preservation eval cases fail against a deliberately
   sycophantic prompt variant — proven once by running them against one, so
   the cases are known capable of failing (`docs/MISTAKES.md` entry 3's
   spirit, applied to evals).
4. The empty-week and small-N cases hold: two comments in, a summary out;
   zero comments in, the contract's stated empty shape out, never an
   invented theme.
5. The gate question is settled, not dodged: either this ticket sets an
   enforcing floor for the summary task's eval metrics, or the ADR records
   why the floor waits (and for what measurement), the way E2 staged the
   validity floors. Silence is not an option; `prompt-eval` runs on this PR
   by the README's declared exception and checks for exactly this.
6. Prompt version and model id flow through the task's return so E4-06 can
   store them without re-deriving.

## Decisions this ticket settles

- **What the contract's themes are for.** E7's draft check wants "the week's
  main comment themes with counts"; if this contract's theme list is that
  input, its shape should say so now — or the ADR should say E7 re-derives
  and why. Recommendation: carry themes with per-theme comment counts now;
  it costs one field and spares E7 a second model call over the same text.
- **The floor question** (criterion 5). Recommendation: ship the cases
  enforcing shape and content properties now, set numeric floors after the
  first real-provider measurement run, dated and owned — the E2 pattern.
- **One call per stream or one call for both.** Two calls match "per-stream"
  and keep each prompt small; one call halves spend. Recommendation: two —
  the streams are §5.1's structure, and a cross-stream bleed (course
  complaint summarized into the instructor stream) is a real failure the
  split prevents structurally.

## Known traps

- **A summary eval that a keyword match satisfies** is the green that hides
  the defect — the memory about tests whose outcome a second mechanism also
  produces applies to eval design too. Cases should assert the criticism's
  *substance* survives, at whatever grain the typed contract makes checkable.
- **Comment text in a failure log** — the gateway's error paths must not
  interpolate the input; E3's decision 10 (no student content in worker
  logs) extends here and E4-06 relies on it.
- **The mock AI service needs the new task** — check what the mock answers
  for an unknown task before assuming; teaching it the summary shape may be
  part of this diff (`mock-ai/`, a heavy path via the Dockerfile row's
  reasoning — it stays behind the development guard regardless).

## Out of scope

- The beat job, storage, and when generation happens — E4-06.
- Rendering — E4-10's AiPanel.
- The held-note becoming real — E6, which writes the moderation states that
  populate it.
- The response draft and draft check tasks — E7.
