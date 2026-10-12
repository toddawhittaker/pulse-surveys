# 0197 — The student's week is read under the hold, as filters over the instructor's reads

**Status:** Accepted
**Date:** 2026-10-11
**Ticket:** [E8-01](../tickets/e8/E8-01-the-students-week-under-the-hold.md)

## Context

SPEC §5.4 puts the trend, the distributions, the workload median and the
published comments on the student's results page, with the `small-N` state, and
the E8 breakdown wrote its rulings into §5.4: the course named in every state,
the trend without `awaiting` weeks, published and kept comments only, the
release group on the latest published week only, and no count of anybody.
[ADR 0193](0193-the-hold-reads-a-per-course-policy-row-fixed-at-report-open.md)
built the hold for the response alone. The SPEC does not say where the student's
comment rule lives, how the release group's instant is read, or how a trend
leaves a held week out. The breakdown's ruling 7 places the read as a filter
over the instructor's reads, with no new view.

## Decision

**The payload.** `StudentWeekResults` gains `course_label` (every state, through
`reporting._course_label`, which composes `section_codes.course_label`),
`streams` (instructor then course), `workload_median` and `released`. While the
page's week is `awaiting` the three figure members are `null`, and the route
returns before it reads any figure or comment. Every new model refuses an
undeclared member. A comment is `{text}` under its stream, a released comment
`{text, stream}`.

**The comment reads** are two functions in `services/report_comments.py`.
`student_comments(section_id, week_id, stream)` is `visible_cards` kept to the
`published` and `kept` statuses; so the threshold (distinct commenters, ADR
0182), the whole-week moderation rule (ADR 0187), the batch anti-join and v004's
Care exclusion all apply unchanged, and the order is the report's shuffle.
`student_released_comments(section_id, term_id, stream, as_of)` is the release
read with `cut_at < as_of`, kept to the same two statuses. Both return text and
stream only. `services/response_loop.py` is the one module that imports them,
and it imports nothing else from `report_comments` or `moderation` (the import
sweep holds it).

**The figures** are `reporting.student_streams`, after `on_behalf_streams`: the
trend over the weeks the caller passes, this week's ratings as shares keyed "1"
to "5", and either the comments the caller read or the small-N state. The
small-N state is `_held_streams`, the instructor report's own answer, so a
stream below the threshold, or a week still waiting on a verdict, carries no
comment whatever the caller passed. The workload median is
from the same count of who answered in `reporting.student_streams`; the mean is
not served. The mean and the median leave the server rounded to one decimal, the
precision the page shows: beside whole-number shares an exact mean such as 30/7
names how many classmates rated (E8's boundary review).

**Ratings as shares, withheld when small** (the README's ruling 8, SPEC §5.4).
The instructor's histogram counts sum to the number of classmates who rated, and
in a week of two or three raters a student who knows her own rating can subtract
it from a mean, a median or a histogram and read a classmate's. So a student
reads whole percentages by largest-remainder rounding, summing to exactly 100,
never counts. And a stream-week with fewer distinct raters than `n_threshold()`
gives no shares and a trend point with a null mean, on its own page and on every
later one (the point stays, so a small week never looks like a held one); a week
with fewer distinct workload answerers gives no median. The unit is people,
counted from `response.user_id` and grouped away (MISTAKES entry 50). The
comment rule and the instructor's figures are unchanged.

**The hold over the sequence of pages.** `response_loop` reads every week's
state set-based, through `_week_clocks` (required and unanswered is
`awaiting`). The trend takes the published weeks up to and including the page's
week that are not `awaiting`: a held week has no point, not a null one. The
release group shows only when the page's week is the latest published week and
no published week is `awaiting`, as of that week's report opening
(`reporting.report_opens_at`), so the 02:40 cut before a 06:00 opening is in it
and a cut after the opening waits for the next week's page.

**The policy-of-record rule is written once**, as `response_loop._mode_in_force`:
the last of a course's rows in `sequence` order set at or before the opening, or
encouraged. `policy_of_record` now reads the course's rows and applies it, and
`_week_clocks` applies it to the rows it reads for many courses at once.

## Alternatives rejected

- **A student view under `views_sql/`** (ruling 7). It would be a second
  statement of v004's rule and the threshold, to keep in step by hand. A view
  later is an additive migration.
- **The status filter in SQL, inside the shared statement.** A second
  `WHERE` beside the instructor's would split one read in two; filtering the
  cards keeps every rule the instructor read applies, by construction.
- **The release instant from the reading clock.** A batch cut between the
  opening and the read would appear on a page that was already published, which
  is a difference a reader can see between two visits to one week.
- **A null trend point for a held week.** It would mark the held week on every
  later page. A null mean is kept for what it already means: a released week
  nobody rated.
- **Two copies of the policy rule**, one in SQL with `LIMIT 1` and one in
  Python. They had already drifted in form; one function closes it, at the cost
  of `policy_of_record` reading all of a course's policy rows (a handful).

## Consequences

- One required week nobody answers hides every batch for the rest of the term
  (the accepted cost of ruling 1).
- The student's comment read reads `answer` in exactly two statements, both
  gates and neither a text read: `_unmoderated_section_weeks` (the whole-week
  moderation check, ADR 0187) and `_commenters_by_stream_week` (the
  distinct-commenter count, ADR 0182). The text comes from `report_comment`
  only. Dispute E8-01-02 ruled that this is what done-when 4 allows: it forbids
  reading comment text from `answer`, not the gates, which stay inside the read
  so it is safe for any caller.
- The student trend point is `StudentTrendPoint`, not `TrendPoint`: two schema
  classes with one name make FastAPI name both OpenAPI components by module,
  which would rename the instructor report's `TrendPoint` under its frontend.
