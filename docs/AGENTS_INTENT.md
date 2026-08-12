# Agent Roster — Intent

This document states *what I want from each agent and why*. It does not
specify how Claude Code should implement them — file format, invocation
mechanism, whether an agent can be re-addressed with its context intact,
and how warm sessions are managed are all implementation questions to be
answered against what the tooling actually supports.

Read `docs/SPEC.md` (especially §2.1, §4.1, §5, §7.3, §7.4, §9, §13, §14),
`docs/DESIGN_BRIEF.md`, and `CLAUDE.md` before designing the roster.

---

## Governing principles

**Fresh eyes for review, continuity for construction.** Anyone reviewing
work must not have watched it being written — a reviewer that saw the
reasoning has already been persuaded by it. The implementer, by contrast,
benefits from remembering the approaches it already tried.

**The test author must be blind to implementation.** If it can see
implementation attempts, it writes tests the implementation passes, and
red-green becomes theater.

**A reviewer that always says "looks good" is worse than no reviewer.**
Every review agent reports findings ranked by severity and states plainly
when it found nothing. I will spot-check early runs against diffs I know
are broken.

**Volume kills review.** If every agent comments on every PR, I skim, and
skimming is worse than not reviewing. Some agents run per-PR, gated by
what the diff touches; others run once at an epic boundary, because they
ask questions a single diff cannot answer.

**Opinionated, but opinionated toward *this* architecture.** Generic best
practice applied enthusiastically will damage this codebase in two specific
ways: an enterprise-patterns reviewer will request abstraction layers
(repository over SQLAlchemy, DTOs separate from the Pydantic contracts, a
wrapper over the LTI library) that add distance from the two things that
actually cost time — protocol debugging and confidentiality correctness —
and aggressive DRY will merge the identity-separated read paths into one
clever parameterized query, which is exactly what §8 exists to prevent.
Duplication in confidentiality-critical paths is sometimes correct.

---

## Construction agents

### Implementer
Writes the code. Holds its context across attempts within a ticket so it
remembers what it already tried and why.

Opinions it should hold:
- DRY, SOLID, KISS, YAGNI — with the caveat above about confidentiality
  paths.
- Idiomatic for the language. Modern Python (3.13+, typed, async where the
  stack is async); idiomatic React 19 + TypeScript.
- Boring, obvious code over clever code. Optimize for whoever is debugging
  it at 11pm.
- Make illegal states unrepresentable — types and DB constraints over
  runtime checks. This is the same instinct that put identity separation
  in views rather than application logic.
- Fail loudly and early. The validity classifier's fail-open (§3.3) is the
  only sanctioned exception; that pattern appears nowhere else.
- Every AI call is an untrusted dependency: timeout, validate, define the
  failure behavior.
- Keep audit-log writes and grade posting in one obvious place each, not
  scattered.
- No configuration knob for something with one correct answer.
- Leave the code better than it found it.

Hard rules:
- **Never modify, skip, xfail, or delete a test to make it pass.** If it
  believes a test is wrong, it escalates (see arbitration below) and stops.
- Refactor freely within files the ticket already touches. Anything
  crossing a module boundary, changing a shared signature, or touching a
  confidentiality-critical path is *proposed*, not done.
- A refactor never rides in the same commit as a behavior change.
- Re-read any file that changed outside its own edits before acting on it.

### Test author
Reads the ticket's acceptance criteria and the relevant spec sections,
writes failing tests, stops. Never sees implementation.

TDD scope — state this boundary explicitly rather than letting it drift:
- **Red-green applies to:** services, the participation formula, purview
  computation over the assignment DAG, section-code parsing, authz scoping,
  the moderation lifecycle state machine.
- **Red-green does not apply to:** UI layout, and the AI tasks, where
  "correct" is a distribution rather than an assertion. Those get eval sets
  (§9.3) and visual review instead.

### Arbitrator
Resolves implementer-vs-test disputes. Cannot be the implementer's own
session. Reads the test, the written objection, and the disputed spec
section, and reaches one of three outcomes:
1. The test is wrong → test author is re-invoked with the ruling.
2. The implementer is wrong → it resumes with an explanation, not an order.
3. **The spec is ambiguous** → this is not an implementation decision. It
   comes to me, and produces a spec edit or an ADR.

Outcome 3 is the reason the loop exists. Most genuine disputes are spec
ambiguities surfacing; without arbitration, whichever side is more stubborn
quietly wins.

The objection is always *written to a file* even when the implementer's
context survives — the arbitrator reads it, the PR record needs it, and a
spec ambiguity needs to become an ADR.

---

## Review agents — per PR

Gated by what the diff touches, so PR review stays readable.

**Spec conformance** (always). Does this diff do what the ticket and spec
say, or something adjacent that seemed reasonable? Spec drift is the most
likely failure mode in a long agent-driven build, because every individual
change looks fine.

**Privacy / authorization** (read paths, purview, identity, audit). The
domain-specific one, and the strongest mandate in the roster: §4.1
invariants, purview computation, sibling-lead isolation, n-thresholds,
identity separation, audit completeness. Deliberately separate from
application security, because one agent holding both checklists does the
generic half competently and skims this half.

**Application security** (endpoints, auth, external input, dependencies).
Generic and pattern-driven: injection, SSRF, secrets in logs, token
validation, CSRF on state-changing endpoints, dependency risk.

**Architecture** (structural changes, new modules, new abstractions).
Opinionated toward §13's layering: thin routers, logic in `services/`, one
authz chokepoint, single-shot AI, platform quirks isolated in adapters. Its
default answer to a proposed abstraction is **no** unless the abstraction
names the duplication it removes.

**Data model** (any migration). Reversibility, constraint correctness,
whether identity-separated views still hold after a schema change, and
**index coverage against the queries the report jobs actually run** — N+1
aggregation across the purview DAG is the likeliest way the
500-sections-in-30-minutes target is missed.

**LTI / OIDC conformance** (`lti/`, auth, session). Narrow specialist:
launch validation, nonce/state, clock skew, AGS score semantics, NRPS
paging, cookieless iframe behavior. This is where the real bugs will live,
and general review won't catch protocol-level mistakes.

**Accessibility + copy register** (frontend components and screens). WCAG
2.2 AA against *rendered* output, not just source: keyboard operability of
the workload slider, chart data-table equivalents, focus rings,
reduced-motion. Same agent checks copy against the register rules — "needs
attention" never "underperforming," confidentiality copy once per screen,
coaching rather than shaming on the validity bounce.

**Prompt / eval** (`ai/prompts/`, `ai/contracts.py`, eval floors). Were
eval cases added for changed behavior? Were floors quietly lowered? This
guards the one gate where the tempting fix is the wrong one.

All reviewers: **prefer deleting to adding.** The most valuable finding is
often "this doesn't need to exist," and agents rarely say it unless told to.

---

## Review agents — epic boundary (before merge to main)

These ask questions a diff-scoped reviewer structurally cannot.

**Threat model** (⚠ epics always). Given everything now merged, what can a
Lead Faculty — or an instructor, or an agent acting for either — see that
they shouldn't? Exposure that emerges from the *combination* of merged
work, where no individual PR granted anything wrong.

**Invariant coverage audit** (always). The §4.1 tests only cover read paths
someone thought to test. Did new read paths appear that the invariant suite
never touches?

**Epic exit criteria** (always). Every ticket can pass while the epic still
fails to deliver what §14.3 says it should.

**ADR + docs completeness** (always). Were construction decisions that
diverge from or aren't covered by the spec recorded? Does `CLAUDE.md` still
contain only process (per its own policy)?

---

## Open questions for me

Ask rather than assume:
- Whether warm/re-addressable agents are actually available in this setup,
  and if so, how handoffs across turns should work.
- Which agents I want on by default vs. invoked explicitly.
- How findings are surfaced — PR comments, files, or session output.
- Whether any of this roster is redundant or missing something you can see
  from the tooling side that I can't.
