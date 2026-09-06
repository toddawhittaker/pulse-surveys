# 0131 — A week counts if its window closed after the student arrived

## Context

SPEC §3.4 decides which weeks form a student's denominator in three sentences:
the denominator starts at the student's first enrolled week from NRPS enrollment
data; where the platform supplies no dates a student counts from the section's
start; except that a student who first appears in a roster sync later than their
section's first sync counts from the week of that sync. It also says one thing
about a student who leaves — "scores stop updating; the LMS owns what happens to
the column" — which is a rule about posting and leaves open what the formula
computes for them.

Three things in those sentences are underspecified, and each of them moves real
numbers in a real gradebook.

The **comparison** is between values of different kinds. `enrollment.lms_window_start`
is an instant, `enrollment.started_on` is a date, and a window has two instants of
its own. Which pair is compared, and whether the comparison is strict, decides
whether a whole week joins or leaves a denominator.

The **third tier's other side** has two candidates. `started_on` is Pulse's own
first-sighting date, written by the roster sync (ADR 0095); the section's `nrps_call`
rows are the log of when those syncs happened. They disagree, and the disagreement
is what the tier is about — "later than their section's first sync" is a claim
about the section's history, not about the student's.

The **drop** has to be answered by this module even though §3.4's sentence is
about a different module.

## Decision

**One boundary rule, in one sentence: a week counts if the student could still
have answered it — that is, if its window closes at or after the instant they
were enrolled from.** The first credited course week is the earliest week whose
`closes_at` is at or after that instant, and a student every window closed before
has no score at all rather than a zero.

The instant they were enrolled from is chosen by §3.4's tiers, in the spec's own
order:

1. `lms_window_start` where the platform supplied one.
2. Otherwise, where the section has at least one `nrps_call` row **and**
   `started_on` is strictly later than the institution-timezone day of that
   section's **earliest** `called_at`: the start of the `started_on` day, in the
   institution timezone.
3. Otherwise the section's start — every course week.

Tier 3's comparison is against the section's earliest roster-sync row, and a
section with no such row is tier 2 outright.

**A dropped student is computed exactly like an enrolled one.** `ended_on` is not
read by the formula at all. E3-06 is what stops posting.

## Alternatives rejected

- **Treat `started_on` alone as the late-add date.** It is one column and needs no
  second read, and it is what "the date they were added" sounds like. It cannot
  answer the question §3.4 actually asks: "later than their section's first sync"
  needs to know what that first sync was, and a first-sighting date on its own
  cannot say. It also fires on seeded data, where nothing has ever been synced and
  every `started_on` is an invented value.
- **Compare dates rather than instants in tier 3.** Simpler, and wrong by up to a
  day at the only place it matters: a window closes at 23:59:59 on a Sunday, and a
  student first seen on the Monday could not have answered it although both days
  fall inside the same course week.
- **A strict `>` on the window's close, so that a student arriving at the closing
  instant misses the week.** The window is open up to and including that instant
  (E2-06 treats both ends as inclusive), so a student dated to it could still have
  answered.
- **`>=` on the sync day in tier 3**, making every member of the first sync a late
  add dated by it. That deletes most of the term from most denominators, because
  the first sync is where a section's whole roster arrives.
- **Truncating a dropped student's denominator at `ended_on`, or leaving them out
  of the answer.** Both read "scores stop updating" as a rule about arithmetic. It
  is a rule about posting, and putting it here would hide it from E3-06 — which is
  where somebody would look for it — and would give the same student two different
  scores depending on which module was asked.

## Consequences

A late add the platform never dated and the section's first sync already contained
cannot be told from a day-one student, and is credited with weeks that closed
before anyone had synced the section. SPEC §3.4 accepts that under-credit in as
many words: no rule can recover data the platform never supplied.

Tier 3 depends on the roster-sync log being retained. A retention policy that
deleted old `nrps_call` rows would silently move every tier-3 student to tier 2 and
widen their denominators, so that log is now load-bearing for a grade and not only
for operations. The retention epic has to know this.

Every boundary here is one comparison and each is asserted from both sides —
tier 1 a microsecond either side of a close and exactly on it, tier 3 on the day a
window closes and the day after, and tier 3's own selection on the sync day and the
day after. Those pairs are the guarantee; a single-sided assertion cannot tell `>`
from `>=`, and the two differ by a whole week of a student's grade.

Because `ended_on` is never read, a dropped student's computed score keeps moving
as their comments are re-classified. Nothing posts it — that is E3-06's — but any
future reader of this module gets a live number for a student who has left, which
is the correct answer to "what would their score be" and not an answer to "what
does their gradebook say".
