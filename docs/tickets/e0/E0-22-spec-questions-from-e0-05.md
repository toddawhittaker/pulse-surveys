# E0-22 — Two spec questions E0-05's review surfaced

**ID:** E0-22
**Branch:** `e0/spec-questions-from-e0-05`
**Depends on:** E0-05

## Status — what is left here

**Both questions were answered on 2026-08-18 and both spec edits have landed.**
What is left here is **code**, and it is now a build ticket rather than a
question.

| Half | State |
|---|---|
| q1 — the rule | **Landed** as SPEC §4.1 item 7, with §5.1 rewritten to point at it |
| q1 — the test | **Owed, and it is E4's.** §4.1 item 7 is marked *asserted from E4*, because the reports carrying these figures do not exist yet |
| q2 — the rule | **Landed** in SPEC §8, and ADR 0017 is amended to say the assumption became a rule |
| q2 — the constraint | **Owed, and it is this ticket's.** Nothing yet stops a second `institution` row |

**§4.1's preamble now names the two items that carry no assertion** — item 1
(E2's) and item 7 (E4's) — rather than claiming all seven are asserted. Adding
item 7 is what made that necessary: an invariant listed with nothing asserting
it is exactly the rule this ticket exists to stop shipping unenforced.

The remaining work does not batch with anything: it is one migration adding one
constraint, plus the test that a second `institution` row is refused.


## Context

E0-05 settled the course-number-to-level bands, which had never been written
down. Splitting three levels into five, and writing the first schema, exposed two
questions the spec does not answer. Neither was answered in E0-05, deliberately:
both are product decisions, and a schema ticket whose own scope says "this is
schema only" is the wrong place to make them by side effect.

They are collected here so that "open" means "written down with the exposure
stated" rather than "noticed once in a pull request comment". Both are cheap to
answer and neither is cheap to discover twice.

Read first: SPEC §4, §4.1 and §5.1 for the first question; [ADR
0017](../../adr/0017-prefix-codes-are-unique-across-the-deployment.md) and SPEC
§2.1 for the second.

## Scope

### 1. Does the benchmark minimum cover comparison-set *numbers*, or only lines?

**The exposure.** SPEC §5.1 requires a workload mean and median for the section
*against comparison-set and university figures*. It also says "Benchmark **lines**
have their own minimum … the line is suppressed rather than shown thin." Those
are the only two sentences, and the minimum is scoped to the line. A comparison
figure computed from one or two sections is therefore rendered.

A mean over two sections is a number about those two sections. That is the same
inference the small-N comment rule exists to prevent, reached through a benchmark
rather than through a comment — a Lead Faculty reading another instructor's
section-level workload off a comparison figure.

**Why it matters more now.** E0-05 split three levels into five, and §5.1 matches
levels exactly with no folding. Thin comparison sets move from the edge case to
the common one, especially for `DEV` and `UGGR` sections and for the less common
lengths.

**What to decide.** Whether the minimum applies to every figure computed from a
comparison set, or only to a drawn line. The likely answer is every figure, and
if that is the answer it belongs in **§4.1 as an invariant with a test behind
it**, not only as prose in §5.1 — §4.1's preamble is what obliges an automated
assertion, and a confidentiality rule stated where nothing obliges a test is a
rule that ships unenforced. §5.1's paragraph then points at it.

A round of E0-05's review widened the §5.1 sentence on its own judgment and the
next round argued the rule was right but the placement overreached. §5.1 now
states the gap as an open question rather than settling it, which is the state
this ticket resolves.

### 2. Is one institution per deployment enforced, or merely assumed?

**The exposure.** `prefix.code` is unique across the whole table, not scoped to a
parent, while `college.name` is unique per institution and `department.name` per
college. ADR 0017 records why and names the assumption it rests on — a deployment
serves one institution — and is explicit that the assumption is **latent, not
enforced**. Nothing stops a second `institution` row being written. Its `BIOL` is
then refused by `uq_prefix_code`, with an error naming a constraint and no
institution.

**What to decide.** Whether Pulse is single-tenant by construction. If it is, a
constraint permitting at most one `institution` row makes global and
institution-scoped uniqueness the same rule, removes the incoherence, and turns a
confusing constraint violation into an error at the row that is actually wrong.
ADR 0017 records this as the cheapest of its three options and the one it did not
take, because whether the product is single-tenant is a statement about what
Pulse *is* and the spec does not make it.

If it is not single-tenant, `prefix.code` needs rescoping and `INSTITUTION_TIMEZONE`
stops being a deployment-level setting — which is the honest signal that the
change is larger than a schema edit.

## Out of scope

- Anything about the level bands themselves. Those are settled in SPEC §8.
- The `lms_` marker grain. That is [E0-11](E0-11-authz-skeleton.md)'s decision.
  The residue moved from [E0-21](E0-21-review-debt.md) to
  [E0-35](E0-35-the-writer-and-the-marker-nobody-routed.md), which closed it at
  table grain on 2026-08-19.

## Acceptance criteria

- [x] SPEC says which scope the benchmark minimum has, in one place rather than
      two. **Done 2026-08-18:** it is §4.1 item 7, and §5.1 points at it instead
      of restating it.
- [ ] §4.1 item 7 has a test asserting it. **Not done, and it is E4's** — the
      reports carrying comparison-set figures do not exist yet. §4.1's preamble
      names item 7 and item 1 as the two invariants that carry no assertion, so
      the gap is stated rather than implied.
- [x] SPEC says whether a deployment serves exactly one institution, and ADR 0017
      is amended to say the assumption became a rule. **Done 2026-08-18**, in §8.
- [ ] **A constraint enforces it.** Not done, and it is this ticket's remaining
      scope: nothing yet stops a second `institution` row, so §8 currently states
      a rule the database does not hold. One migration, plus a test that the
      second row is refused, verified by mutation.
- [x] Neither answer is recorded only in an ADR. Both are spec questions, and
      `CLAUDE.md` is explicit that an ADR is not the instrument for something the
      spec should decide. **Both landed in SPEC**; ADR 0017's amendment points at
      §8 rather than carrying the decision.

## Definition of done

**Tests apply** for the first question if the answer makes it a §4.1 invariant,
and for the second if a constraint lands.

**Docs apply** — both answers are spec edits.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies but is light** for the first question, which is a
confidentiality rule, and does not apply to the second.
