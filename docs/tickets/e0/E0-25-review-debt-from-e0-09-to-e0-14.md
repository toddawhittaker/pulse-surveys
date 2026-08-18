# E0-25 — Review debt from E0-09, E0-12 and E0-14

**ID:** E0-25
**Branch:** `e0/review-debt-e0-09-to-e0-14`
**Depends on:** E0-09, E0-12, E0-14

## Status — what is left here

**Mostly moved or closed.** Two items are batch items, one is closed, one is a
decision for Todd, and one is carried to E1.

| Item | Now |
|---|---|
| 1 — nothing asserts `.dockerignore`'s contents | [E0-36](E0-36-ci-gate-fidelity.md) item 4 |
| 2 — the `"150"` course-number literal in three test modules | [E0-37](E0-37-small-corrections.md) item 4 |
| 3 — `fresh_scope`'s docstring overclaims | [E0-37](E0-37-small-corrections.md) item 5 |
| 4 — `MISTAKES` entry 16 wants its database-shaped variant | **Closed** |
| 5 — the mock LMS cannot mint a deliberately wrong launch | **Carried to E1** |
| 6 — two spec lines describe things that no longer exist | **Decided 2026-08-18: correct both.** Spec edits, still owed — see the README's Decided table. |

On item 4: `docs/mistakes/16-a-mutation-harness-reported-kills-it-had-not-made.md`
now carries the clause — a mutation that lives in the database is read from the
source that installs it and never from `pg_proc`, because a downgrade that
reinstates whatever the database holds reinstates the mutation.

The *Filed elsewhere in this round* table at the bottom is unchanged and is still
the complete index of what the three reviews produced.


## Context

What those three tickets' reviews found and could not close in place, collected
the way E0-21 collects E0-05's and E0-24 collects E0-07's and E0-08's. Nothing
here blocks anything.

Findings that had a natural owner went to that ticket rather than here, and are
listed at the bottom so this file is a complete index of the round even where it
is not the place the work happens.

Three of the six items below are the same shape: **a guarantee that holds today
because of something nobody wrote down.** A packaging rule enforced by a glob, a
concurrency guarantee conditional on an isolation level, a safety distinction
resting on one assertion. That shape is the reason this file exists.

## Scope

### 1. Nothing asserts `.dockerignore`'s contents

E0-12 added four re-exclusions (`backend/**/*~`, `*.orig`, `*.rej`, `*.bak`)
because `pyproject.toml` now ships `app/ai/prompts/**/*` as package data, which
made the prompts directory a path by which **arbitrary file content reaches the
runtime image**. Measured: `scratch-notes.txt` and `validity.v1.md~` are both
carried into the wheel; `.env` is not, because Python's glob skips dotfiles.

The fix is unguarded. Deleting any of those four lines leaves every gate green,
and the failure it prevents — a key parked beside a prompt while debugging,
baked into an image layer — is invisible in review because the file is untracked.

`.dockerignore`'s own header says listing what to exclude fails open, and this is
that pattern applied in the direction that fails open. The check wants to build
the image and inspect what reached it, which makes it a Docker-gate concern
rather than a unit test.

### 2. The `"150"` course-number literal is still latent in three test modules

E0-09's dispute `E0-09-01` was a fixture pinning every seeded course to `"150"`
while the containment helper kept the shared `prefix`, so the second course a
test built violated E0-05's `uq_course_prefix_id_lms_number`. Fixed there with a
per-call generator that counts 100–799 and fails loudly on exhaustion.

The same literal is still present in `tests/integration/test_identity_schema.py`,
`tests/integration/test_section_date_derivation.py`, and
`tests/integration/test_term_calendar_schema.py`. None of them builds two courses
today, so none is broken — they are the same trap set and not yet sprung. The
arbitrator ruled this out of scope for that dispute, correctly, and flagged it.

### 3. `fresh_scope`'s docstring overclaims

It says the fixture never writes a second institution. True of that method, false
of the builder — `seed_row` on an empty chain creates one freely, which is how the
canonical-chain test already produces several. Its author noticed and left it,
since it was outside the fix in hand. `docs/MISTAKES.md` entry 1's shape.

### 4. `MISTAKES` entry 16 wants its database-shaped variant

Entry 16 tells you to assert a revert restored the file byte for byte. E0-09's
implementer then hit the same class with no file involved: a crashed harness left
a mutated function in `pg_proc`, the next run read its baseline out of the
database, and three variants came back identical. The clause it wants: *if the
thing you are mutating lives in the database rather than in a file, read the
baseline from the source that installs it and assert it does not already contain
the mutation.* It could not be added at the time because three branches were
editing that file.

### 5. The mock LMS cannot mint a deliberately wrong launch

E1 will need expired tokens, foreign signatures and replayed nonces to test its
own launch validation. E0-14 builds the platform side and defines no interface
for producing a bad launch, deliberately — tool-side validation is E1's. Recorded
now so E1 does not discover it after starting. Belongs in E1's ticket or an E0-14
amendment; it is not work for this ticket.

### 6. Two spec lines describe things that no longer exist

**Decided 2026-08-18: correct both.** Both changes were deliberate and both are
already explained in an ADR, so this is transcription rather than a decision —
but it is a spec edit, so it is Todd's to make. It is tracked in the README's
*Decided* table until it lands.

Both raised by implementers who declined to edit the spec themselves, correctly:

- **§8 says an assignment carries `scope_node_id`.** E0-09 shipped five nullable
  foreign keys, one per containment level, because E0-05 built six containment
  tables and no unified node table. ADR 0025 records it.
- **§8's core-table list does not name `user_identity`**, and §13's `identity.py`
  comment still reads `user, enrollment, role_assignment`. ADR 0001 already noted
  the split does not match §8 literally.

**Spec edits are Todd's**, per `CLAUDE.md`. This item is a pointer, not a task.

## Out of scope

- Everything already filed against the ticket that owns it — see below.
- Anything requiring a spec change, beyond recording that one is wanted.

## Acceptance criteria

- [ ] A gate fails when a file matching one of `.dockerignore`'s prompt-directory
      re-exclusions reaches the built image. Building the image and inspecting it
      is acceptable and probably necessary; a test asserting the `.dockerignore`
      *text* is not, because it would pass against a typo'd pattern.
- [ ] The three modules holding a literal course number either draw distinct
      numbers per call or carry a comment saying why a constant is safe there.
      Copying E0-09's generator wholesale is fine; copying the *section-code*
      pattern is not, because `graph_letters(1)` repeats every 26 calls.
- [ ] `fresh_scope`'s docstring says what is true of the builder, not only of the
      method.
- [ ] `MISTAKES` entry 16 carries the database-shaped clause.
- [ ] E1's ticket names the deliberately-wrong-launch interface, or E0-14 is
      amended to add it. Either, not neither.

## Definition of done

**Tests apply** to items 1 and 2. Items 3, 4 and 6 are records.

**Docs apply** — item 4 is a `MISTAKES` edit and item 6 is a pointer at a spec
edit Todd owns.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies but is light.** Item 1 is the only one with a security
consequence, and it is about build hygiene rather than a reachable path.

## Filed elsewhere in this round

Recorded here so this is a complete index of what the three reviews found:

| Finding | Owner |
|---|---|
| Schema-qualify relations in views and functions; `search_path` must name `pg_temp` **last** — the conventional `pg_catalog, public` is the version that fails | **E0-10** |
| The marker sweep's one-hop walk and its `("name", "email")` fragments | **E0-10** |
| Edge direction unconstrained by role — sibling-lead isolation is edge data, not schema | **E0-11** |
| One lead per course enforced on `lead_faculty_mapping` only | **E0-11** |
| `session_replication_role = replica` disables the supervision trigger | **E0-17** |
| Seeding an `lti_platform` row for the mock is what would make ADR 0038 wrong | **E0-17** |
| The advisory lock is one global mutex held to commit; the walk is O(depth), uncapped | **E1** |
| Quadratic bulk-import cost — check the graph once, not per row | **E1** |
| A behavioural backstop for threat versus self-harm reaching Care as distinct cases | **E6** |
| The threat-recall floor must report recall **per verdict**, not over a merged label | **E10** |
| The prompt-immutability CI check | **E2**, per ADR 0032 |
| `jwks_url` is credential-equivalent and unconstrained | **E0-24**, then E1 |
