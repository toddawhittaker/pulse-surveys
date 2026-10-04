# 0184 — A week's report opens at 06:00 on the Monday after its window closes

**Status:** Accepted
**Date:** 2026-10-03
**Ticket:** [E5.1-05](../tickets/e5.1/E5.1-05-small-behaviour-fixes.md)

## Context

SPEC §3.1 said reports are "available after window close Monday morning" and gave
no hour. The code published a week the instant its window closed, so a report
could be read on Sunday night, before the Monday summary walk had written the
summary that leads it. The owner ruled on 2026-10-03 that a week's report opens
at 06:00 on Monday in the institution's time zone. SPEC §3.1 now says so. What
the spec leaves open is how the rule is built.

## Decision

1. **The rule is a pure function.** `app.services.reporting.report_opens_at`
   answers the first Monday 06:00 in the institution's zone that is strictly later
   than `closes_at`. A Sunday 23:59:59 close opens the next morning; a close at
   Monday 05:00 opens that morning; a close at Monday 06:00:00 exactly opens the
   following Monday. The Monday is found on the calendar in the zone and combined
   with 06:00, never reached by adding a fixed offset, so a week that closes
   across a daylight-saving change still opens at 06:00 local.
2. **One predicate.** `week_is_published(closes_at, now=…, zone=…)` is
   `now >= report_opens_at(…)`. `instructor_report` and `published_course_weeks`
   both select their weeks through `_published_weeks`, which calls it with the
   effective clock (ADR 0109) and `ZoneInfo(settings.institution_timezone)`.
3. **The hour is a constant, `REPORT_OPENS_AT = time(6, 0)`**, not a setting.
4. **A closed but unopened week is refused exactly as a week the section never
   runs**, from the same line (`CourseWeekUnavailableError`, ADR 0155).

## Alternatives rejected

- **A setting for the hour.** The owner ruled one hour. A setting would add a
  value to validate and test for a need nobody has.
- **A stored `published_at` column.** It would be a second copy of a fact the
  close and the zone already determine, and it would stop moving when a developer
  moves the clock. E4's breakdown decision 6 ("nothing is stored to make a week
  published") still holds.
- **Publish at the close**, as before. The summary that leads the report does not
  exist yet, and the ruling is 06:00.
- **Publish when the summary exists.** That ties availability to a model call. A
  provider outage would hold the report back indefinitely, and the hour would
  differ from section to section.

## Consequences

- Between the close and 06:00 Monday a week is unavailable, and the latest
  published week is still the one before it. A release batch cut at Monday 02:40
  therefore appears in the prior week's report until 06:00. That is released
  content and carries no week attribution (ADR 0153), so nothing is disclosed.
- Four rules stay on the close, deliberately: the summary walk
  (`generate_missing_summaries`, which must finish before the report opens), the
  comment hold in `report_comments._held_comments` (it is about the count being
  final), grading's elapsed-week rule (SPEC §3.4), and the benchmark cutoffs
  (ADR 0178).
- An institution in another zone gets 06:00 in its own zone, read from
  `institution_timezone`.
