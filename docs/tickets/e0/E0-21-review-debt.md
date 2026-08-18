# E0-21 — Review debt from E0-05

**ID:** E0-21
**Branch:** `e0/review-debt`
**Depends on:** E0-05

## Status — where this ticket's items went

**Not built as written. Both items have moved**, and the reasoning stays here
because the batch tickets link to it.

| Item | Now |
|---|---|
| 1 — detect an LMS-owned column that was never marked | [E0-35](E0-35-the-writer-and-the-marker-nobody-routed.md) |
| 2 — assert that a prefix belongs to a department | [E0-37](E0-37-small-corrections.md) item 3 |

The section below headed *Considered and deliberately not carried* is a record of
Todd's decision on `course.lms_title` and its three-part cost. It moves nowhere
and stays readable here.


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

**Two ways to close it, and the choice belongs to E0-11.**

*Table grain.* SPEC §2.1's ownership list is *courses, sections, section codes,
enrollments, teaching instructors*. Four of the five live on `course`, `section`
or `enrollment`, so a chokepoint refusing application writes to those **tables**
answers most of §2.1 without reading a column name, and catches the unprefixed
`canvas_id` that no name-based check can. Two things it does not catch. The day a
Pulse-owned writable column lands on one of those tables, a table-grain rule
refuses a write that should be allowed — `course.level` is already a non-LMS
column on an LMS-owned table, saved only by being unwritable. And the
teaching-instructor link may not be on those tables at all: §2.1's chain runs
over role assignments and §8 puts those on `role_assignment`, so if the link is
an assignment row, table grain leaves it writable — which is a purview grant
rather than a stale attribute, since purview is computed from those rows.

*The write seam.* The sync path is the only thing that sees both halves at once —
which field came from the platform, and which column it went into. A write of an
`id_token` or NRPS field into a column with no `lms_` prefix is detectable
there. The limit is that the sync is **not the only writer of platform-sourced
data**: launch-time ingestion, AGS, and the seed script all write it too, so a
check at one seam covers one seam.

An earlier draft of this ticket offered a third option — assert that the set of
`lms_`-prefixed columns matches an explicit list. **That does not work and is not
on the table.** Adding `course.canvas_id` leaves the prefixed set unchanged, so
the assertion stays green while the gap opens; it also contradicts this ticket's
own first acceptance criterion, which forbids asserting against a list of
columns that already exist. It is recorded here only so it is not re-proposed.

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
  generation expression because Alembic cannot `ALTER` one. That belongs to
  [E0-20](E0-20-gate-fidelity.md), under its item 3, not to this ticket.
- **The `design/` course numbers.** All 27 distinct numbers across the prototype
  fail the SPEC §8 bands. [E0-17](E0-17-seed-script.md) carries it.

## Considered and deliberately not carried

**Removing `course.lms_title`.** `spec-conformance` rated it MED and argued it
should land with the ticket that has a value to put in it. Todd decided to keep
it. Recorded here so the decision is visible rather than looking like an
oversight — and recorded with its full cost, because the first draft of this
paragraph named one third of it:

1. The LTI context claim's `title` is optional while the column is `NOT NULL`,
   so ingestion needs a fallback. [E0-14](E0-14-mock-lms-launch.md) carries it.
2. **E0-15's NRPS sync and E0-17's seed must supply a title for every course
   they insert**, or the write fails. Neither ticket says so yet.
3. **The fallback and the marker contradict each other.** E0-14 tells the
   ingestion path to invent a title — `label`, or the prefix and number — when
   the platform sends none, and write it into a column whose `lms_` name asserts
   that Pulse does not own the value ([ADR
   0014](../../adr/0014-lms-owned-columns-are-marked-by-a-name-prefix.md)). That
   is the distinction E0-05 drew when it refused to mark `level`: a value Pulse
   computes carries no prefix. So keeping `NOT NULL` costs either a nullable
   column later or a marker that lies about one row in every course the platform
   under-describes.

None of that reverses the decision, which is Todd's. It is here so that whoever
hits item 3 finds it already named rather than discovering it as a
contradiction.

## Acceptance criteria

- [ ] Adding an LMS-owned column with no `lms_` prefix fails something. The test
      demonstrates it by adding one and watching it go red, not by asserting
      against a list of columns that already exist.
- [ ] `prefix.department_id` being made nullable turns a test red.
- [ ] Both verified by mutation — reintroduce the defect and watch it fail.

## Definition of done

**Tests apply**, and they are the whole ticket.

**Docs apply if item 1 is closed by table grain**, in which case ADR 0014 gains
a line: the marker stops being the enforcement mechanism and becomes
documentation, which retires one of the two reasons that ADR gives for choosing
a name prefix over an `info={}` dict. (An earlier version of this line made the
docs conditional on taking an explicit-list fallback, which is no longer on the
table at all.)

**AI evals do not apply. Accessibility does not apply.**

**Security review applies but is light** — item 1 is a guard on a write path
over LMS-owned data, which is the surface SPEC §2.1's "read-only in Pulse"
protects.
