# 0165 — The benchmark set figures are computed behind a definer of their own, the term axis is keyed by a start date, and a cohort week keeps its row when nobody reports hours

**Status:** Accepted — E5-03.

## Context

E5-03 ships the cohort arithmetic every benchmark figure rests on: per-stream
rating means, workload mean and median, and three counts, keyed by SPEC §5.1's
comparison set (a length, a level, a term) on both of SPEC §2.2's week axes.
Three construction questions were not answered by the spec, and a reasonable
engineer could take each the other way.

**One: how a caller gets those figures for a set of sections that is not a
cohort.** E5-04 resolves a default set (one lead's courses, the hero section
taken out), a university line and a named set. None of those is a key the
database holds, so a view keyed by a cohort cannot answer them. The work order
for this ticket asked for a fifth view exposing `(section_id, course_week,
stream, user_id)` — a person-week index spanning a cohort — granted to
`pulse_app` and "consumed ONLY for aggregate computation". The test author
disputed it (`docs/disputes/E5-03-01.md`) and the dispute was **sustained on
both halves**: E5-03's own scope allows this building block "section id and
numbers, never a person", and SPEC §8 requires identity separation to be
"enforced in the database, not just the application" — a convention about
callers is the thing that sentence replaces.

**Two: what identifies a start cohort on the term axis.** §2.2 draws "one line
per start cohort" with a selector reading "U sections · started 8/17", and the
letter map is admin-configured per term.

**Three: what a cohort week has when its responses carry no workload figure.**
`report_workload` (E4-03) withholds the row.

## Decision

**The building block is a pair of `SECURITY DEFINER` functions**,
`benchmark_set_week(section_ids uuid[])` and
`benchmark_set_rating_week(section_ids uuid[])`, in the versioned `views_sql/`
shape ADR 0041 sets and following ADR 0139's precedent: the section set goes in,
numbers come out, and no row keyed to a student is selectable by `pulse_app`.
Typed wrappers of the same names live in `views_sql/queries.py`, so E5-04 has no
reason to spell a statement of its own. ADR 0150 prefers a plain grant wherever
one would do, and this is the case where one cannot: counting **distinct
students** across an arbitrary set requires reading rows that say which student
answered where, and any relation wide enough for the application to do that
arithmetic itself is the person-week index the dispute withdrew.

**The functions are owned by `pulse_benchmark_definer`**, a new NOLOGIN role
created by this ticket's migration, holding column-grain `SELECT` on the six
relations the two bodies name and nothing else. Reusing `pulse_resolve_definer`
was refused: its column grants on `user` and `person` would give a body whose
job is to count students an owner that can read their names.

**The term-axis cohort key is `section_start_date`.** A start letter is per-term
admin data, so a key on the letter compares two unrelated cohorts across two
terms whenever an administrator reuses one; a date is the same cohort in
whatever term has one.

**A cohort week answered without hours keeps its row, with null workload figures
and its three real counts.** This is a **departure from `report_workload`'s
rule, not an application of it.** Every column of that view is a workload
figure, so a row of nulls there would be a section week that looks answered and
is not. These views carry `response_count`, `respondent_count` and
`section_count` beside the two figures, so withholding the row would withhold
three true counts to avoid publishing two absent ones, and E5-04 would read a
week that had data as a week that had none. Null, never nought: a zero mean is a
statement about how long a cohort's students worked that none of them made, and
E5-05 renders that figure beside an instructor's own.

## Alternatives rejected

- **A per-section pre-aggregate the caller sums.** Rejected because sums of
  distincts are not distinct sums: a student in two sections of a set is counted
  twice, and the over-count runs in the direction that lets a thin set past a
  threshold that exists to protect people (`docs/MISTAKES.md` entry 50).
- **Deferring the building block to E5-04 with its service.** Rejected because
  E5-04 is deliberately a policy-only diff, and moving a migration into it
  couples policy review with SQL review and breaks the wave's migration
  partition.
- **The person-keyed view the work order asked for.** Rejected by the ruling on
  `docs/disputes/E5-03-01.md`; the analogy with `section_roster` fails because
  that view is one section's key handed to a reader already inside it, while a
  cohort-spanning person-week key is a de-anonymization primitive.
- **A key on the start letter** for the term axis, and **table-wide `SELECT`**
  for the definer owner: each is the cheaper spelling of a decision above and
  each gives up the property that decision was taken for.
- **Following E4-03 and withholding the hours-less row.** Rejected for the
  reason above; recording it as "following E4-03" would have cited a rule for
  its opposite, and the next reader would find two views disagreeing with
  nothing to explain it.

## Consequences

`SANCTIONED_APPLICATION_EXECUTE` grows from six entries to eight, each with the
sentence the ruling wrote for it, and a fourth definer owner joins
`IDENTITY_DEFINER_ROLES`. What that owner may reach has no pinned equality of
its own yet, unlike the other three — recorded in `docs/tickets/e5/deferred.md`.
The two functions and the two course-week views compute the same figures by two
routes, so a test sets them side by side; a change to one arithmetic that misses
the other is a red rather than a divergence in production. E9 inherits a term
axis nothing in E5 draws, proven by test here so that it consumes a read
somebody has exercised. And a benchmark figure now depends on a role the
application cannot become: if `pulse_benchmark_definer` loses a column grant,
every benchmark in the product empties at once, which is why the grants are
listed in one file against the two bodies that spend them.
