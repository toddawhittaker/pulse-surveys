# 0165 — The benchmark set figures are computed behind a definer of their own, the term axis is keyed by a start date, and a cohort week keeps its row when nobody reports hours

**Status:** Accepted — E5-03; amended 2026-09-13 (E5-04).

> **Amendment, 2026-09-13.** The decision below is unchanged. What it left
> unstated is the thing this record was the only place to state: **exactly which
> `(relation, column)` pairs `pulse_benchmark_definer` holds `SELECT` on.** The
> consequences section says the owner "has no pinned equality of its own yet",
> and `docs/tickets/e5/deferred.md` gave E5-04 the job of closing that. A test
> could not close it alone: an expected set transcribed from
> `benchmark_definer_v001.sql` would assert that the SQL equals itself, which is
> `docs/MISTAKES.md` entry 19, and the sibling equality test refuses it in its
> own docstring — "the expected sets are derived from the records' own sentences
> rather than copied from the migration". So the sentence goes here, where a
> reviewer weighs it as a claim about what the owner may reach, and the equality
> is derived from it.
>
> `pulse_benchmark_definer` holds `SELECT` on these eighteen columns of these six
> relations, and on nothing else — no seventh relation, no other verb, and no
> privilege at the grain of a whole relation:
>
> - `public.response` — `id`, `user_id`, `section_id`, `week_id`
> - `public.answer` — `response_id`, `question_id`, `rating`, `workload_hours`
> - `public.question` — `id`, `kind`, `stream`
> - `public.section` — `id`, `term_id`, `start_date`
> - `public.term` — `id`, `start_date`
> - `public.week` — `id`, `number`
>
> **Not one of them is a column of `user`, `user_identity` or `person`**, which
> is the property the deferral was about. `response.user_id` is the only column
> in the list that reaches a person at all; it is the key the distinct count of
> people is computed over, it is grouped away inside both function bodies, and it
> never leaves either function's row. The columns are exactly the ones those two
> bodies name — a length and a level reach the cohort views through the section
> and its course rather than through this owner, and a course week is derived
> from `section.start_date`, `term.start_date` and `week.number`.
>
> **What changes if this list moves.** A column added to the owner widens what a
> `SECURITY DEFINER` body may read past what any reviewer of this record agreed
> to, and the widening is invisible in a diff of the two function bodies. So the
> list above is the reviewable claim and the equality derived from it is the
> gate; moving either without the other is the failure both exist to prevent.
> `docs/tickets/e5/deferred.md`'s entry closes on this amendment.

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
shape ADR 0041 sets and following ADR 0139's precedent: the section set goes in
and numbers come out. Typed wrappers of the same names live in
`views_sql/queries.py`, so E5-04 has no reason to spell a statement of its own.

**What that buys, stated accurately.** The ruling's own first answer — that
`pulse_app` "may not select the rows they aggregate" — was false, and the
amendment on `docs/disputes/E5-03-01.md` records it: that connection has held
table-wide `SELECT` on `response` and `answer` since the E2 submission path, so
it can already read which student answered where. What it cannot read is a
**person**; its `SELECT` on `public."user"` is `(id)` only, so `response.user_id`
joins to nothing nameable. Three things survive, and each is checkable. The
functions add **no new reach** to `pulse_app` — an `EXECUTE` grant on two bodies
is the only new privilege:
that answer in aggregates and have nowhere to put a row. They answer in numbers
**by construction** rather than by a convention about callers, which is the
difference SPEC §8's "enforced in the database, not just the application" is
asking for. And they keep a person-keyed relation off the sanctioned read
surface, where the withdrawn view would have put one — with the precedent for
the next one behind it. ADR 0150 prefers a plain grant wherever one would do,
and what a plain grant cannot do here is that third thing: the grant *is* the
person-keyed relation.

**The functions are owned by `pulse_benchmark_definer`**, a new NOLOGIN role
created by this ticket's migration, holding column-grain `SELECT` on the six
relations the two bodies name and nothing else. Reusing `pulse_resolve_definer`
was refused, and the reason is blast radius rather than names: that role cannot
read a name either — it holds `user(id, lti_platform_id, lms_user_id)`,
`person(id, user_id)` and `web_login_subject`, which are cross-platform
identifier columns — but it exists to resolve one identifier to another, and a
body whose whole job is counting has no use for that reach. Disjoint owners are
what keep each function family's reach readable against the bodies that spend
it, and a later widening of either then widens one family rather than two.

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
  `docs/disputes/E5-03-01.md`. Its cost is a standing granted relation keyed to
  a student on the surface `SANCTIONED_VIEW_COLUMNS` enumerates, and the
  precedent for the next one — rather than a new capability, since the
  connection can already read the rows underneath. The analogy with
  `section_roster` fails for a second reason: that view is one section's key
  handed to a reader already inside it, while this one spans every section of a
  cohort across terms.
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
