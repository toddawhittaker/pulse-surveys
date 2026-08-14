# E0-21 — Review debt from E0-05

**ID:** E0-21
**Branch:** `e0/review-debt`
**Depends on:** E0-05

## Context

PR #19 drew four independent passes — `privacy-authz`, `spec-conformance`,
`data-model`, and an independent `/security-review` — producing two HIGH, five
MED and four LOW findings. Everything that was a slip, a wrong record, or a
missing index was fixed in that pull request. Two findings were not, because
neither can be closed by editing E0-05: each needs machinery that does not exist
yet.

They are collected here so that "deferred" means "written down with the reason"
rather than "mentioned once in a pull request nobody re-reads". That distinction
is `docs/MISTAKES.md` entry 1.

Neither blocks anything. Both are small once the thing they depend on exists,
and both are the kind of item that is cheapest to do while passing through for
another reason — hence the ticket rather than a `TODO`.

Read first: [ADR
0014](../../adr/0014-lms-owned-columns-are-marked-by-a-name-prefix.md), the
E0-05 marker criterion, and `docs/MISTAKES.md` entries 2 and 3.

## Scope

### 1. Detect an LMS-owned column that was never marked

**The gap.** LMS-owned columns carry an `lms_` name prefix (ADR 0014). Walking
`Base.metadata` can assert two things: every column E0-05 named is prefixed, and
no Pulse-owned table carries the prefix. It cannot assert the direction that
matters — that a *new* LMS-owned column has its marker — because once the prefix
is missing, nothing in the metadata distinguishes an LMS-owned column from a
Pulse-owned one. `course.canvas_id` or `section.instructor_external_id` would
sail through every test in the suite today.

**Why E0-11 does not close it, despite an earlier draft saying so.** The
authorization chokepoint's only way to know a column is LMS-owned is the same
prefix. So E0-11 enforces the marker where it is present and is blind to one
that is absent, exactly as the metadata tests are. Relocating the check does not
close it, and E0-11's criterion has been reworded to stop claiming otherwise.

**What can close it.** The sync path that writes LMS data is the only thing that
knows which fields it received from the platform. A roster sync or a launch
ingestion that writes a field it got from NRPS or from the `id_token` into a
column with no `lms_` prefix is detectable at that seam, because both halves are
in view at once. That code arrives with tool-side roster sync in **E1**, so this
item is most cheaply done there — a check at the point of assignment, plus a
test that adds an unmarked column and watches it fail.

If E1 passes without picking it up, the fallback is weaker but real: assert that
the set of `lms_`-prefixed columns matches an explicit list in the test suite, so
adding an LMS-owned column forces a deliberate edit to that list. That is a
second source of truth, which is what ADR 0014 chose the name prefix to avoid —
take it only if the seam-based check does not happen.

### 2. Assert that a prefix belongs to a department

E0-05's scope says "a department groups one or more prefixes … enforce each as a
database constraint, not an application convention." `prefix.department_id` is
non-nullable and does enforce it, but nothing asserts the non-nullability. Only
the course-to-prefix half of that sentence is tested.

`ON DELETE RESTRICT` does not cover it: the delete-restrict test passes whether
or not the column is nullable, so a later change making `department_id` nullable
turns nothing red and a prefix belonging to no department becomes writable.

One assertion against `Base.metadata` or the reflected table, in the module that
already holds the containment tests.

## Out of scope

- **The generated-column drift gap.** `alembic check` exits zero on a changed
  generation expression because Alembic cannot `ALTER` one. That is
  [E0-20](E0-20-gate-fidelity.md)'s fourth item, not this ticket's.
- **The `design/` course numbers.** 22 numbers across the prototype fail the
  SPEC §8 bands. [E0-17](E0-17-seed-script.md) carries it.

## Considered and deliberately not carried

**Removing `course.lms_title`.** `spec-conformance` rated it MED and argued it
should land with the ticket that has a value to put in it. Todd decided to keep
it. It is recorded here so the decision is visible rather than looking like an
oversight — the column stays, and [E0-14](E0-14-mock-lms-launch.md) carries the
consequence that the LTI context claim's `title` is optional while the column is
`NOT NULL`, so ingestion needs a fallback.

## Acceptance criteria

- [ ] Adding an LMS-owned column with no `lms_` prefix fails something. The test
      demonstrates it by adding one and watching it go red, not by asserting
      against a list of columns that already exist.
- [ ] `prefix.department_id` being made nullable turns a test red.
- [ ] Both verified by mutation — reintroduce the defect and watch it fail.

## Definition of done

**Tests apply**, and they are the whole ticket.

**Docs apply** only if item 1 takes the fallback rather than the seam check, in
which case ADR 0014 gains a line saying the second source of truth was accepted
and why.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies but is light** — item 1 is a guard on a write path
over LMS-owned data, which is the surface SPEC §2.1's "read-only in Pulse"
protects.
