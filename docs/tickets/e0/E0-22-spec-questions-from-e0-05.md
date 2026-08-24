# E0-22 — Two spec questions E0-05's review surfaced

**ID:** E0-22
**Branch:** `e0/single-institution-constraint` (the questions half needed no branch)
**Depends on:** E0-05

## Status — what is left here

**Both questions were answered on 2026-08-18, both spec edits landed, and the
constraint was built on 2026-08-20.** One thing is still owed and it is not this
ticket's: the test behind SPEC §4.1 item 7.

| Half | State |
|---|---|
| q1 — the rule | **Landed** as SPEC §4.1 item 7, with §5.1 rewritten to point at it |
| q1 — the test | **Owed, and it is E4's.** §4.1 item 7 is marked *asserted from E4*, because the reports carrying these figures do not exist yet |
| q2 — the rule | **Landed** in SPEC §8, and ADR 0017 is amended to say the assumption became a rule |
| q2 — the constraint | **Built 2026-08-20** as `uq_institution_one_row`, a unique index on `(true)`; [ADR 0072](../../adr/0072-one-institution-is-a-unique-index-on-a-constant.md) |

**§4.1's preamble now names the two items that carry no assertion** — item 1
(E2's) and item 7 (E4's) — rather than claiming all seven are asserted. Adding
item 7 is what made that necessary: an invariant listed with nothing asserting
it is exactly the rule this ticket exists to stop shipping unenforced.

The remaining work did not batch with anything: one migration adding one
constraint, plus the test that a second `institution` row is refused. Folding it
into [E0-37](E0-37-small-corrections.md) was considered and declined — Batch H is
text corrections and test guards, and a migration riding along with those is the
one item in it that could break something. It ran on its own branch,
`e0/single-institution-constraint`, after E0-26 item 1 and before E0-18.

**It reached further than a migration and a test**, and the declining was worth
it. Two things the ticket did not predict:

  - **The seeding fixtures build a containment chain per test, and every chain
    ends at an institution.** 41 tests about survey windows, supervision edges
    and identity columns failed inside their own seeding, none of them about
    tenancy. `chain_row` in `tests/conftest.py` hands back the institution that
    is already there; the four modules carrying their own copy of `seed_row` got
    the same rule. `SupervisionGraph.fresh_scope` had already refused to write a
    second institution *because* this question was open, and named this ticket.
  - **`scripts/seed.py` can no longer run beside a real institution at all.**
    Two of its tests planted a foreign institution to check ADR 0064's prefix
    guard, and that database is not one Postgres will hold now. The collision
    they plant moved inside the one institution, where the guard still applies,
    and the scenario they used to cover became its own test: a database holding
    another institution refuses the seed, and the refusal names
    `uq_institution_one_row`.

**What the security review found, 2026-08-21.** It ran on PR #54 in a session
with no prior context, both passes, against the right diff. **No security
vulnerability and no blocker**, and four findings, all from the project-specific
pass:

  - **MEDIUM: the seed crashed rather than refusing.** The constraint refused the
    row as designed — as an `IntegrityError`, which is not a `SeedError`, so it
    escaped `main` and printed a forty-line traceback with exit 1 where every
    other deliberate refusal prints a sentence and exits 2. Nothing was written
    (row-count deltas measured zero across every table) and nothing leaked, but
    the error arrived in the form this rule exists to replace. Fixed:
    `seed_containment` checks for a standing institution before it writes.
  - **LOW: `SeedError`'s docstring** claimed every deliberate refusal is a
    `SeedError`. True again with the fix, and the docstring now states the general
    rule — a rule the database enforces usually needs a guard in the script too.
  - **LOW: the new seed test could not tell a refusal from a crash**, and was
    green against the traceback. It now asserts exit 2 and no traceback, and a
    second test asserts the refused run wrote nothing.
  - **LOW, deferred with a done-when: `SINGLE_ROW_TABLES`** is a hand-maintained
    list nothing checks against the schema, and the four inline copies of the rule
    do not read it. Left while it has one correct entry; the done-when is at the
    list and in ADR 0072.

It also cleared four of the five risks named in the brief — including that
sharing the institution node made no assertion vacuous, measured both ways — and
reproduced the 41-test figure exactly.

**What `alembic check` does with the drop, measured before the shape was
chosen.** The ticket's last criterion anticipated an object the drift gate cannot
compare, and asked for it to be named in [E0-33](E0-33-catalog-drift-assertions.md)'s
catalog assertions if so. It is not one: the gate detects the index dropped, the
`unique` flag removed and the expression changed, and reports clean when database
and model agree. **So nothing was added to E0-33**, and ADR 0072 carries the
measurement table.


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

**Answered: enforced.** The subsection below is the question as it was asked, in
the tense it was asked in, and every present-tense claim in it stopped being true
on 2026-08-20 — SPEC §8 states the rule and `uq_institution_one_row` holds it.

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
- [x] **A constraint enforces it. Done 2026-08-20.** `uq_institution_one_row`, a
      unique index on `(true)`, because a check constraint sees one row at a time
      and cannot count its own table (ADR 0072). Verified by mutation: dropping
      it turns `test_a_second_institution_row_is_refused` red, as does making it
      non-unique or moving it to the `name` column, and a rule permitting no rows
      at all turns the near-miss test red. `alembic check` catches all three
      mutations, so nothing was named in E0-33.
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
