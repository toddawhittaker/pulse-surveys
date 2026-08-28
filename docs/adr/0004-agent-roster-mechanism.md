# 0004 — Agent roster mechanism

**Status:** Accepted — roster split amended 2026-08-28; the fifteen-agent
mechanism and computed gating are unchanged
**Date:** 2026-08-12
**Intent:** `docs/AGENTS_INTENT.md`

## Context

`docs/AGENTS_INTENT.md` states what each agent is for and deliberately leaves
the mechanism open: "file format, invocation mechanism, whether an agent can be
re-addressed with its context intact, and how warm sessions are managed are all
implementation questions to be answered against what the tooling actually
supports."

The spec does not mention agents at all. Every choice below is therefore
unanswered by `docs/SPEC.md`, and each is one a reasonable engineer would make
differently.

## Decision

**Fifteen agent definitions in `.claude/agents/`** — three construction, eight
per-PR review, four epic-boundary — invoked by three skills: `/build-ticket`,
`/review-pr`, `/review-selftest`.

> **2026-08-28:** Four per-PR reviewers moved to the epic boundary —
> `data-model`, `lti-oidc`, `a11y-copy`, `prompt-eval`. The roster is now
> three construction, four per-PR review (`spec-conformance`, `app-security`,
> `privacy-authz`, `verifier`), eight epic-boundary (`epic-exit`,
> `invariant-coverage`, `adr-docs-completeness`, `threat-model`, plus the
> four moved). Fifteen agents total, unchanged. The mechanism this record
> decides — hooks, computed gating, session-scoped warmth — is unchanged.

**Warmth comes from `SendMessage`, scoped to a session.** The implementer is
spawned once per ticket and re-addressed by name; a send resumes it from its
transcript. Subagent transcripts persist with their session, so **resuming the
session — `claude --resume` — restores the warm implementer even across a
restart of Claude Code.** What loses warmth is starting a *new* session, not
closing the terminal. Backing it up for that case: an append-only attempt log at
`docs/tickets/e0/.attempts/<TICKET>.md` and `memory: project`.

**Gating is computed, not delegated.** `/review-pr` runs `git diff --name-only`
and maps paths to reviewers from a table.

**The two hard rules are hooks, not instructions.** A `PreToolUse` hook scoped
to the implementer denies writes to `tests/**`; another scoped to the test
author denies reads of `backend/app/**` and `frontend/src/**`.

**Findings arrive as one consolidated pull request comment**, with every
reviewer either reporting findings or stating `Nothing found.`, and untriggered
reviewers listed with the reason.

## Alternatives rejected

**Auto-delegation by agent `description`.** The intended mechanism, and it
cannot do what the intent doc asks. Claude decides whether a description matches
the task; it does not compute a diff, so "gated by what the diff touches" would
become "gated by whether Claude thought of it." Non-determinism in *which*
reviewer runs is invisible — a reviewer that silently did not run looks exactly
like one that found nothing.

**Instructing the implementer not to edit tests.** Rejected because the moment
the instruction matters is the moment it is weakest: an implementer one turn
from green, looking at a test it is convinced is wrong. A hook is indifferent to
how persuasive the reasoning is.

**A single security reviewer.** Rejected per the intent doc's own reasoning —
one agent holding both the generic and the confidentiality checklist does the
generic half competently and skims the other. Kept split, with `app-security`
invoking `/security-review` internally rather than reimplementing it.

**One reviewer commenting per finding, inline on the diff.** Better locality,
rejected on volume: eight agents commenting inline produces exactly the skimming
the intent doc warns about. One comment, ordered most-consequential first.

**Running reviewers in the background.** Rejected on capability: background
subagents lose most built-in tools, including structured finding reporting.
Foreground also keeps the user able to interrupt.

**A ninth reviewer for test quality.** Rejected as a merge instead:
`spec-conformance` already holds the acceptance criteria, and "do these tests
check these criteria" is the same question it is already asking. The failure it
exists to catch — an invariant test asserting a column is *absent* rather than
that the query is *denied* — needs the criteria in hand, which no standalone
test reviewer would have.

**Running the epic-boundary agents as a CI job on the epic → `main` pull
request.** Deferred rather than rejected: they run on demand first, so findings
can change the PR body before it opens. Promote once the findings are trusted.
**2026-08-28:** the boundary now holds eight agents rather than four, which
raises what this deferred alternative would move into CI. Still deferred for
the same reason.

## Consequences

- **A ticket spanning two sittings keeps its warm implementer if the session is
  resumed, and loses it if a new session is started.** Resume with
  `claude --resume` rather than opening a fresh session mid-ticket. A new
  session keeps only the conclusions, via the attempt log — the reasoning behind
  a rejected approach is gone, which is the part the intent doc's "continuity
  for construction" is actually about. The attempt log exists for that case and
  is a weaker substitute, not an equivalent.
- **Blinding the test author is correct for E0 and gets harder at E1.**
  Greenfield tickets can be written from acceptance criteria alone; tests
  extending an existing service cannot, unless the ticket states the public
  interface. Several E0 tickets already do. Revisit at E1 rather than
  pre-solving.
- **"A refactor never rides in the same commit as a behavior change" has no
  enforcement.** Intent is not detectable from a diff. Reviewer judgment only —
  recorded so nobody assumes coverage that does not exist.
- **`/review-pr` costs tokens proportional to reviewers triggered.** Measured
  against the eighteen E0 tickets: typically 2–3 reviewers. **2026-08-28:** the
  per-PR roster is three reviewers now (`privacy-authz`, `app-security`,
  `spec-conformance`), so the ceiling is 3 by construction; E0-10's worst case
  of 5 would now split across the per-PR comment and the epic-boundary run.
- **Reviewer prompts are load-bearing and untested by CI.** A prompt edit can
  silently remove the sentence doing the work, which is why
  `/review-selftest` exists and why it should run after any reviewer edit.
- **The hooks depend on `jq`** being present. They fail closed if the payload
  cannot be parsed.
