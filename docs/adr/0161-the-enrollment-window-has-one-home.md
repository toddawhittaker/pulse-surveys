# 0161 — SPEC §3.4's enrolment window has one home, and the report's denominator reads it

## Context

Two surfaces divide by "who was enrolled", and until the E4 boundary round only
one of them read SPEC §3.4's rules for it.

§3.4 says when a student's enrolment begins:

> Late adds: denominator starts at the student's first enrolled week (from NRPS
> enrollment data). Where the platform supplies no enrollment dates — most supply
> none — a student counts as enrolled from the section's start date.

E3-04 built that reading as three tiers
([0131](0131-a-late-adds-first-week-is-decided-in-three-tiers.md)): the platform's
own `enrollment.lms_window_start` where it supplied one; otherwise the day the
student was first sighted, if that is after the section's first roster sync; and
otherwise the section's start. They lived in `app/services/grading.py` as private
helpers of the participation formula.

§5.1's response rate divides that week's responses by the students enrolled while
its window was open, and
[0147](0147-the-report-views-return-counts-and-the-payload-layer-divides.md) is
explicit about where that number comes from and why it is not in SQL:

> No view names `enrollment`, and the enrolled denominator is not here. It is
> computed at the payload layer on the clock and enrolment helpers
> `app/services/grading.py` already uses, so §3.4's window rules are read once.

**That sentence was a claim the code did not have.** What
`app.services.reporting._enrolled_students` actually asked was
`started_on <= closed_on`, and `started_on` is the column a roster sync writes
when it *first sights* a member — so a late add the platform dated three weeks
into a section carries the section's start date in it and was counted in every
week before he arrived. The consequence is not an error anybody can see: those
weeks' response rates are divided by one too many and each renders as a plausible
percentage. It was found by the boundary round and is red under
`tests/integration/test_the_report_payload_divides_the_rates.py`.

So the question is not whether to fix it but where the rule goes, and a
reasonable engineer would choose differently: a second, correct reading inside
`reporting.py` is a smaller diff and it is a second reading.

## Decision

**A new module, `app/services/enrollment_windows.py`**, holding three things and
nothing else: `first_sync_day`, the roster-log read tier 3 rests on;
`enrolled_from`, the tier branch itself; and `began_by`, the "had this enrolment
begun by the time that window closed" comparison, which exists because its `None`
case carries a meaning — `None` is tier 2, "from the section's start", so a caller
reading it as "no weeks" would silently drop every member of every section a
platform dates nobody in, which is most of them.

`app.services.grading` calls it, and its whole suite is green **unmodified**,
which is what says the promotion changed nothing on its side.
`app.services.reporting._enrolled_students` calls it too, and its begin test moved
out of SQL along the way — which is ADR 0147's own direction, "so §3.4's window
rules are read once", now true.

**What is deliberately not shared is `ended_on`.** §3.4 has a drop stop a score
from *updating* rather than take away weeks already earned, so grading reads that
column nowhere and says so; §5.1's denominator is the people who could have
answered that week, so the report does read it, in SQL, unchanged. A helper that
folded the end date in would have made one of the two callers wrong.

The E4-07 moderation-state consolidation is the shape and the precedent: one
resolution, shaped to be called from elsewhere, with the ordering stated once.

## Alternatives rejected

**Correct the comparison inside `reporting.py` and leave grading's helpers where
they are.** Four lines instead of a module, and it is the shape that produced the
defect: two readings of one spec sentence, each internally consistent, with
nothing comparing them. The first thing that diverges is a tier nobody adds to
both.

**Put the tiers in `app.services.roster_sync`, which writes the columns.** It is
where the data comes from and it is the wrong direction: the report read would
then import the sync — its NRPS client, its debounce, its write sanction — for
three functions that read two columns and one log table. The boundary was named as
a stop condition before the work started, and this is the answer that avoids it.

**Put them in `app.services.survey_windows`.** Same word, different axis: that
module derives §3.1's *survey* windows from a section's calendar, and an
enrolment window is a fact about a person. One module holding both would make
"window" ambiguous in the two places it is least affordable.

**Have the report ask `app.services.grading` directly**, importing the private
helpers or making them public. It inverts the dependency — a read path importing
the passback module, which pulls the AGS client, Celery and `requests` in behind
it — and `tests/unit/test_the_grading_module_reaches_no_network_ags_or_job.py`
records that exact objection from the other side.

**A denominator counting live enrolments as of today.** Rejected already in ADR
0147 and restated because it is the shape that suggests itself: one query, one
number, and it answers two different weeks with the same wrong value.

## Consequences

- **`NRPS_CALL = Base.metadata.tables["nrps_call"]` moved with the function that
  reads it**, and it is still read off the metadata rather than imported from
  `app.models.lti`, for the reason it was there: the participation formula reaches
  this function, and the formula may not reach a module path holding `lti` — that
  is the rule keeping E3-04's AGS client out of the arithmetic, and the roster-sync
  log happens to share a module with it.
- **The report loads one section's enrollment rows per report instead of counting
  them in the database.** The row set is one section's roster and the read happens
  once per report; what is bought is that §3.4's tiers are read in one language, in
  one place, which is ADR 0147's stated direction.
- **The report's per-week denominator changes for more than the late add.** Tier 2
  now counts a member with no platform date and no later first-sight from the
  section's start, where `started_on <= closed_on` counted them from the day the
  sync first saw them. That is §3.4's rule as grading has applied it since E3-04,
  and the two surfaces agree now where they quietly did not.
- **`app.services.grading` is a little smaller and a little less self-contained.**
  Its docstring says where the tiers went; its purity sweep follows only functions
  defined in that module, so the moved ones leave its reachable set — no property
  is lost, since they reach the database and nothing else, but the sweep no longer
  says so and this record is where that is written down.
- **ADR 0147's sentence about the denominator is now true**, and that record
  carries a dated paragraph saying it was a claim before it was a fact.
