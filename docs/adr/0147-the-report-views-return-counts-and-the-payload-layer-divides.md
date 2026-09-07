# 0147 — The report views return counts over the weeks that were answered, and every division, denominator and label is the payload layer's

## Context

E4-03 ships the numbers SPEC §5.1 asks the instructor's Monday report for,
computed at read time from what E2 stored. The ticket's own "Decisions this
ticket settles" leaves three questions open, and answering them turned out to be
one decision rather than three: **where the line between SQL and Python falls.**

**Where a rate is computed.** §5.1 asks for a "response rate and validity rate";
§3.3 defines the second as valid responses over responses. Either the views
divide, or they expose the counts and the service reading them divides.

**What "enrolled that week" means.** The response rate's denominator is the
enrolment, and §3.4's enrolment-window rules — a student who joins late, one who
drops mid-window — are an institution rule that `app/services/grading.py`
already reads and already applies. A SQL denominator would be a second reading of
it.

**Which week a row is about.** §2.2 gives a section two week axes: the term week
the calendar numbers, and the course week the report prints, which the cohort's
start letter and length decide. A view has to be keyed on one of them.

**Whether a zero-response week has a row.** The ticket recommends that the trend
"yields the week with null mean and zero counts" so the chart has the week to
draw a gap in.

**And whether there is a fourth view.** §5.1 asks for a trend line as well as a
distribution, so a `report_rating_trend` returning a weekly mean per stream was
the obvious fourth file.

Every one of these is a construction choice the spec leaves open, and a
reasonable engineer would settle at least two of them the other way, which is
what puts them here rather than in a comment.

## Decision

**Three views, keyed by `(section_id, week_id)`, returning counts and statistics
over the section-weeks that were answered — and nothing else.**

- `report_rating_distribution` — `(section_id, week_id, stream, rating,
  responses)`: how many submitted ratings of each value each stream holds, with
  the stream read from `question.stream` and never from a question's ordinal.
- `report_workload` — `(section_id, week_id, workload_mean, workload_median)`:
  `avg` over the stored `numeric`, and `percentile_cont(0.5) WITHIN GROUP (…)`
  cast back to `numeric`.
- `report_response_counts` — `(section_id, week_id, responses,
  valid_responses)`: the two numerators §3.3's validity rate is built from,
  the second counting `response.is_valid` as `app/services/validity.py`
  maintains it.

Four things follow, and each is the answer to one of the questions above.

**No rate is divided in SQL.** The views expose counts; E4-07's payload layer
divides. A division needs a rule for a zero denominator, and one reviewable
place for that rule is worth more than the convenience of reading a percentage
out of a view.

**No view names `enrollment`, and the enrolled denominator is not here.** It is
computed at the payload layer on the clock and enrolment helpers
`app/services/grading.py` already uses, so §3.4's window rules are read once.

**The key is the `week` row's id, and the course-week label is applied at the
payload layer**, on the same Python that already derives it. §2.2's start-letter
calendar exists in one place and stays there.

**Only the section-weeks that were answered get a row.** Absence, not a zero
row: the payload layer zero-fills the weeks the chart needs, in one place, so a
stored zero and a missing week never arrive looking the same.

**There is no trend view.** A weekly mean per stream is
`sum(rating × responses) / sum(responses)` over the distribution's own rows —
the same rows, aggregated once more. A second view over them would be a second
implementation of one number.

**Consequently the ticket's acceptance criteria 3 and 5 are re-homed to E4-07**,
named here and in both pull request bodies:

- **Criterion 3, the mean's semantics** — "the weekly mean is the mean of that
  week's submitted ratings; an absent response contributes nothing to the mean
  (it costs the response rate, not the average)". No view returns a mean of
  ratings, so the assertion belongs where the mean is computed. E4-03 asserts the
  half that is in scope: a response that rated one stream and not the other adds
  nothing to the other stream's distribution and is still counted in
  `report_response_counts`.
- **Criterion 5, the enrolment-window boundary** — "a student enrolled for weeks
  1–3 of a 6-week section is in week 2's denominator and not week 5's, driven on
  both sides of the boundary". The denominator is E4-07's, so the boundary pair
  is E4-07's.

## Alternatives rejected

**Rates divided in the view.** Rejected on the zero denominator: a week with no
enrolment or no responses is a real state, and three views each deciding what to
return for it is three places for one rule, one of which will eventually be
`NULL` where the others are `0`. It also fixes the enrolled denominator in SQL,
which is the next alternative and is worse.

**The enrolled denominator computed in SQL, from `enrollment` and the week's
window close.** This is the tempting one: it is a join, and the answer would come
back with the counts. Rejected because §3.4's enrolment tiers and window rules
are an institution rule already implemented in Python and already tested there.
A SQL copy is a second implementation that agrees today, drifts on the first
amendment, and disagrees invisibly — a wrong denominator renders as a plausible
percentage. `docs/MISTAKES.md` entry 19 is a test holding its expectation in a
copy of the thing it was checking; this is the same shape in production code.

**Keying the views by course-week number.** Rejected for the same reason, one
level down: the number is derived from the cohort's start letter and length
(§2.2), so a view computing it re-derives the calendar. It would also make the
views depend on `section` and `term` rows they otherwise never name, and a
cohort whose calendar is corrected would silently re-key rows already read.

**A row per week the section runs, with zeros — the ticket's own
recommendation.** Rejected, and this is the one that reverses a recommendation
rather than choosing between open options. Two reasons. A zero row asserts
something the data does not say: "nobody answered" and "this section does not run
that week" and "the window has not opened yet" are three different states, and a
zero row renders all three as a plotted zero. And it puts the calendar back in
the view — a row per week the section runs is exactly the outer join to `week` or
`survey_window` that the previous alternative was rejected for. The chart's need
is real and is met: E4-07 knows which weeks the section runs, because it is the
layer that already derives the course-week axis, and zero-filling there is one
loop in one place.

**A fourth `report_rating_trend` view.** Rejected as a duplicate: the weekly mean
is a weighted average of the distribution's own counts, and the distribution is
already the finer-grained answer. A second aggregate over the same rows is a
second thing to keep in step, and the two would eventually disagree at exactly
the boundary — a stream with no ratings — where one returns no row and the other
returns `NULL`.

**Reading `classification` directly for `valid_responses`.** Rejected because
`classification` is append-only (ADR 0055), so "the current verdict" is an
ordering question, and an aggregate written without that ordering reports the
*first* verdict and never moves. §3.3's fail-open makes that the common case
rather than an edge: every floored comment starts out accepted. `response.is_valid`
is the column the validity service maintains for exactly this, and the report
reads it.

## Consequences

**E4-07 owns more than the ticket breakdown implied.** It divides both rates,
supplies the enrolled denominator, labels the course-week axis, zero-fills the
weeks the chart needs, and derives the trend mean from the distribution counts.
It also inherits criteria 3 and 5 with their boundary-pair obligations. That is a
larger payload ticket than a thin serializer, and it is deliberate: it is the one
place all of it can be read at once.

**The views are a stable contract and the tests treat it as one.** Each column
list is asserted as an equality, so a column added to one of these views is a red
test rather than a quiet diff (E4-03 criterion 1), and each is enumerated in
`SANCTIONED_VIEW_COLUMNS` in `tests/integration/test_identity_grants.py` with the
sentence that admits it. None of the three returns a column that names a person
in any currency, which is what §4.1 asks of a view an instructor reads.

**The workload median carries a cast that is easy to lose.** `percentile_cont`
answers in `double precision` whatever it is handed and has no numeric form, so
`::numeric` is what keeps §3.2's "true means and medians rather than band
midpoints" true. No *value* of a median over §3.2's half-hour steps can expose
its loss — every one is a multiple of 0.25 and exact in binary — so the suite
asserts the returned type rather than a number.

**A widened grant on a report view is caught by one test, and that test is
disputed.** `docs/disputes/E4-03-01.md` records it: the three views are
aggregates, and PostgreSQL refuses a write to a non-auto-updatable view during
rewriting, before any privilege check, so the `42501` the suite requires is
unreachable at every point on the ACL scale. Until that is arbitrated, nothing in
the suite distinguishes `GRANT SELECT` from `GRANT ALL` on these three — the
sanctioned-column enumeration filters on `SELECT`, and the base-table privilege
record does not cover views.

**Nothing here suppresses anything.** Small-N suppression, flags and comment text
are E4-04's, and E5 owns comparison-set figures. These views expose numbers about
a section-week and no threshold is applied to them, which is the same stance
`section_enrollment_count_v001.sql` takes and states for the same reason.
