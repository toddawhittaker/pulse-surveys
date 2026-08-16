# 0020 — A section's end date is its last day, inclusive

**Status:** Accepted
**Date:** 2026-08-15
**Tickets:** E0-07

## Context

[SPEC §2.2](../SPEC.md) says a section's start and end dates derive from its
start letter and the term calendar, and [§8](../SPEC.md) says the same in the
data model. Neither says whether the end date is the section's **last day** or
the day *after* it, and the two readings differ by one day everywhere the date
is used.

E0-06 met the same question on `term` and declined to answer it: it stores a
term's length beside its two dates with no constraint tying them, precisely so
that a `CHECK` would not decide the inclusive question on a schema ticket's
authority. E0-07 cannot decline, because it computes the end date.

The evidence is in §2.2's own seed map rather than in any sentence about
conventions. Fall 2026 runs 18 calendar weeks from Monday 8/17, and `Q` is a
12-week start letter beginning 9/28.

## Decision

`end_date = start_date + 7 × length_weeks − 1`: the section's last day. A
section that starts on a Monday ends on a Sunday.

A term's `end_date` is read the same way — its last day — so "the section runs
past its term" is `section.end_date > term.end_date`, and a section may end on
the term's last day.

## Alternatives rejected

**The exclusive (half-open) reading, `start_date + 7 × length_weeks`.** The
usual choice for a range, and it makes "next section starts where this one
ends" arithmetic trivial. Rejected by §2.2's seed map: under it, `Q` ends
12/21, one day outside the 18-week term it is seeded in, and E0-07's fifth
acceptance criterion then requires the service to reject `Q` — a start letter
the spec seeds by name — for every section in that cohort. A convention that
makes the spec's own example unusable is the wrong convention.

The weekday agrees. §3.1 closes a week's survey window on Sunday 23:59:59, so
under the inclusive reading a section's last window closes on its last day;
under the exclusive one the section is "over" on a Monday whose week has no
window in it.

**Storing no end date and deriving it on read.** Rejected by §8, which gives
`section` start and end dates, and by every reader that filters sections by date
in SQL.

## Consequences

A whole-term section is exactly `term.length_weeks` weeks long and ends on the
term's last day. `Q1WW` in Fall 2026 runs 9/28 to 12/20, and that is the
boundary case with no slack in it — an off-by-one in either direction is a
section outside its term or a section a week short.

The comparison that rejects an overrunning section is against `term.end_date`
as stored, not against `term.start_date + 7 × term.length_weeks − 1`. E0-06
stores a term's length and its two dates independently and constrains only that
the end follows the start, so a term whose dates and length disagree makes
itself known here, as a section refused for leaving a term that is shorter than
its length claims. That is a term to fix rather than a derivation to loosen.

Everything downstream that counts weeks between the two dates counts them
inclusively: §3.1's window per active week, §3.4's participation denominator,
and the course-week axis in §2.2. A reader who assumes a half-open range gets
`length_weeks − 1` weeks and will not notice until the last week of a term.
