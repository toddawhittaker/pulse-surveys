# E0-22 — Two spec questions E0-05's review surfaced

**ID:** E0-22
**Branch:** `e0/spec-questions-from-e0-05`
**Depends on:** E0-05

## Status — what is left here

**Both questions were answered on 2026-08-18, and both spec edits are still
owed.** The answers are in the README's *Decided* table; the spec change itself
is Todd's and has not been made.

**Question 1 — every comparison-set figure**, not only a drawn line. The minimum
applies to any number computed from a comparison set, it lands in **§4.1 as an
invariant with a test asserting it**, and §5.1's paragraph points at it rather
than restating it. §4.1's preamble is what obliges the automated assertion, and
a confidentiality rule stated where nothing obliges a test is a rule that ships
unenforced.

**Question 2 — one institution per deployment, enforced.** A constraint
permitting at most one `institution` row, which makes global and
institution-scoped uniqueness the same rule and turns a confusing constraint
violation into an error at the row that is actually wrong. ADR 0017 is amended
to say the assumption became a rule.

Nothing here batches with anything. Question 1's test belongs in the same suite
[E0-33](E0-33-catalog-drift-assertions.md) and
[E0-34](E0-34-view-file-identity-guards.md) extend, and **E4 builds the reports
it governs**, so it is the one with a deadline.


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
- The `lms_` marker grain. That is [E0-11](E0-11-authz-skeleton.md)'s decision
  with [E0-21](E0-21-review-debt.md) carrying the residue.

## Acceptance criteria

- [ ] SPEC says which scope the benchmark minimum has, in one place rather than
      two, and if the answer is "every comparison-set figure" it is a §4.1
      invariant with a test asserting it.
- [ ] SPEC says whether a deployment serves exactly one institution. If it does,
      a constraint enforces it and ADR 0017 is amended to say the assumption
      became a rule.
- [ ] Neither answer is recorded only in an ADR. Both are spec questions, and
      `CLAUDE.md` is explicit that an ADR is not the instrument for something the
      spec should decide.

## Definition of done

**Tests apply** for the first question if the answer makes it a §4.1 invariant,
and for the second if a constraint lands.

**Docs apply** — both answers are spec edits.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies but is light** for the first question, which is a
confidentiality rule, and does not apply to the second.
