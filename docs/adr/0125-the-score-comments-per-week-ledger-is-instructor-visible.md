# 0125 — The score comment's per-week ledger is instructor-visible, and that is accepted

## Context

Ruled 2026-09-04, each posted participation score carries an AGS comment
holding a per-week ledger — one line per elapsed week, of the form
`Week 1: 4 of 5 items`. SPEC §3.4 records the ruling. Since v1 ships no
student-facing and no instructor-facing view of the participation score, that
comment is the only place the arithmetic behind a posted percentage is
visible to anyone.

An AGS score comment is **not** private to the student. It lands in the
platform's gradebook beside the score, where an instructor with ordinary
gradebook access reads it. That makes it a disclosure, and §4 is the
load-bearing wall of this product: responses are keyed to the LMS user id and
identity is never displayed to instructors, in any view.

The concrete risk is a narrowing one rather than a naming one. The ledger
tells an instructor, per student, which weeks that student completed and how
completely. Combined with the comment sets the instructor already sees —
comments are shown without timestamps and in randomized order (§4), and
small-N weeks suppress raw comments entirely — a per-week completion pattern
narrows the set of students who could have written a given week's comment. In
a small section where one student completed a week and others did not, the
set can narrow to one.

## Decision

**The ledger stays as ruled, and the instructor visibility is accepted.**

The reason it is acceptable is that the channel is not new. Any
weekly-updated participation score already leaks the same fact, without a
comment: an instructor who reads the gradebook column in successive weeks
sees each student's percentage move or not move, and a percentage that did
not move is a week not completed. The arithmetic is recoverable from the
deltas by anyone who cares to do it, because the denominator is a public rule
in §3.4 and the week count is the calendar. The ledger makes that convenient;
it does not make it possible.

Accepting a disclosure because an equivalent one already exists is only
honest if the existing one is stated, so it is stated here: **a weekly
participation score posted to a gradebook is itself a per-week completion
signal**, and that is a property of §3.4's design rather than of this
comment.

## Alternatives rejected

**A totals-only comment** — the percentage and the overall fraction, with no
per-week breakdown. It removes the convenience without removing the channel,
since the deltas still carry the same information week over week. What it
does remove is the student's only means of checking the number: with no
per-week lines, a student who disputes a score has nothing to point at, and
Pulse ships no surface where they could look it up. That cost is real and the
benefit is presentational.

**No comment at all.** The strictest option and the one that best matches "no
new disclosure". It leaves a participation grade in a gradebook with no
explanation anywhere in the system, at exactly the moment the formula became
harder to guess: an item-based score means a student can lose credit for
leaving an optional comment blank, and nothing in v1 tells them so. Posting an
unexplained number that penalizes an invisible rule is worse than posting an
explained one.

**Ship the ledger only where the section is above the n-threshold.** Attempts
to borrow §4's small-N machinery for a surface it was not built for. The
threshold governs how many *responses* a reporting week holds, which is a
different question from how many students are enrolled, and a rule that made
the comment appear and disappear across weeks would itself be a signal. It
also puts confidentiality logic on the passback path, where a failure mode is
a wrong grade rather than a suppressed panel.

**Defer the ledger until a student surface exists to explain it.** This is
what E8 will build, and waiting means every pilot term before it posts
unexplained numbers. The disclosure question would return unchanged when the
surface shipped.

## Consequences

**§4's guarantee is unchanged and this is not an exception to it.** Nothing
here displays identity to an instructor. What is accepted is that a
completion pattern the gradebook already carries becomes easier to read. The
distinction matters, because an ADR that reads as "§4 has an exception" would
be cited later as a precedent for one.

**Comment de-anonymization by completion pattern is now a recorded, accepted
risk**, and it belongs to the epics that render comments rather than to E3.
E4's report surfaces and E6's moderation views are where an instructor sees
comments beside a section roster, and this record is the one they read when
deciding whether their own suppression rules are sufficient. E3 adds no
comment-rendering surface.

**A per-platform quirk could widen this.** Some platforms surface a score
comment more prominently than others, and at least one exposes submission
comments in threads students and instructors both post to. The
`PlatformProfile` seam (§7.3) is where such a difference would be handled, and
E3 ships the seam with only the mock's profile — so the first real platform
certification re-reads this record rather than assuming it transfers.

**If the ledger's copy changes, this record is re-read.** The acceptance rests
on the ledger carrying completion counts and nothing else. A line that named a
question, quoted an answer, or said which comment was refused would be a new
channel rather than a convenient one, and would not be covered by the
reasoning above.
