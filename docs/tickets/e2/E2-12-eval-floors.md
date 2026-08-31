# E2-12 — The validity eval set, and the eval floors turn enforcing

**ID:** E2-12
**Branch:** `e2/eval-floors`
**Depends on:** nothing (uses the E0-13 task as it stands)
**Lane:** heavy
**Security-relevant:** CI gate machinery, plus the one place this project
ever calls a paid provider from CI. The secrets policy binds hard here.

## Context

The last E0 tolerance. CI's `evals` job is a `::notice::` today; the `detect`
probe already pins `tests/evals/runner.py`, and the job's own notice records
that running it for real "needs a provider API key as a repository secret and
a `secrets.*` reference in this workflow" — Todd's call under the secrets
policy. §14.3 E2: "turns the AI eval floors enforcing, the last CI tolerance
E0 left." §11 question 4: the production "substantive" definition is the
classifier's, and its eval set and threshold need real seeded data **before
E2 exits**.

**Decided with Todd, 2026-08-31 — when live calls happen.** Ordinary test
runs never call a provider (they use the loopback stub and E2-07's mock). The
eval suite is the only live-provider surface, and it runs: (a) in CI only
when the change touches the AI surface — prompts, `backend/app/ai/`,
`tests/evals/` — via the existing `changed`-outputs pattern at **step level**
(ADR 0002's amendment: the aggregate treats a skipped job as failure, so the
job always runs and its steps decide; a job-level `if:` is the shape
`test_the_aggregate_ci_check_sees_an_upstream_failure.py` exists to refuse);
(b) on demand via `workflow_dispatch`; (c) locally via a make target reading
`.env`. Hundreds of live calls per merge is exactly what this design refuses.

Read first: ADR 0002 whole (both amendments); the `evals` and `detect` jobs
and the `changed` job in `.github/workflows/ci.yml`; SPEC §9.3, §7.4 (typed
contracts are the eval fixtures); ADR 0031, 0032 (prompt immutability —
grown eval cases cite prompt versions); `.claude/review-fixtures/eval-floor-lowered.diff`
and the review-selftest that uses it; MISTAKES entries 9 and 36 (a gate that
has never failed is a comment; a probe deciding whether a gate runs is
itself a gate).

## Scope

- `tests/evals/`: the runner (`runner.py`, the path the probe pins), the
  validity eval set as typed `CommentValidityOutput` cases (§7.4 — a contract
  change breaks evals at type-check time), and per-task floor declarations
  living with the sets. Floors for the validity task now; the threat/self-harm
  floor's *slot* exists in the structure with no set and no number — setting
  it is E10's, and the runner refuses to report a task with a floor and no
  set rather than passing it silently.
- The eval set is the operational answer to §11 question 4: seeded synthetic
  comments across substantive / insufficient / nonsense, including the
  boundary cases the heuristic floor gets wrong (a short substantive comment;
  a long vacuous one — the two the 25-character rule misclassifies by
  construction). Size to spend, not to ceremony: on the order of a hundred
  cases, one live model call each, only on AI-touching changes. The chosen
  precision/recall floors are recorded with the set, with a sentence on how
  they were picked against a real run.
- The CI flip: real steps in the `evals` job behind the step-level path
  condition plus `workflow_dispatch`; the tolerant notice steps retire. The
  `secrets.*` reference for the provider key lands **only after Todd creates
  the secret and says go in the PR conversation** — asked, then waited for,
  never provisional. The runner refuses plainly when the key is absent
  (an AI-touching PR without the secret is a red gate naming what is
  missing, not a quiet pass — MISTAKES entry 34's cousin).
- The flip proven by breaking, both ways: a planted floor breach (a case set
  the current prompt fails) runs red through the real runner; the
  lowered-floor review fixture still trips `prompt-eval` in review-selftest;
  the `detect` probe's planted-tree tests still hold for the runner path.
- `make evals` for local runs off `.env`; README documents cost expectations
  and when the gate fires.

## Acceptance criteria

1. `python -m tests.evals.runner --enforce-floors` passes against the live
   provider on the shipped prompt, and fails — demonstrated once, logged in
   the PR — against the planted breach (MISTAKES entry 9).
2. An AI-touching PR runs the live eval steps; a docs-only or unrelated PR
   runs none and the aggregate stays sound (both shapes shown on real CI
   runs of this branch).
3. No `secrets.*` reference exists in the diff until Todd's go is quoted in
   the PR; after it, the Secrets-check box in the PR template says where.
4. §11 question 4 can be marked settled-for-v1 in the spec's terms, or the
   PR says precisely what remains and E2-13 carries it — no silent residue.
5. ADR 0002's "last tolerance" state is recorded: after this flip, a new
   tolerant gate is a smell, per that ADR's own closing line.

## Out of scope

- Moderation/threat/summary eval sets — each epic that builds the task
  builds its set (E4, E6, E10); the structure here must accept them without
  rework.
- The admin-override feed into eval sets (§6.1) — E11.
- Any prompt change to `validity.v1.md` — if a floor cannot be met without
  one, that is a finding for Todd, not a quiet edit (ADR 0032 makes the old
  prompt immutable anyway).
