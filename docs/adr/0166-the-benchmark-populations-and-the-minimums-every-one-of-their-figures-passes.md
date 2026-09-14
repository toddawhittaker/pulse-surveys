# 0166 — The benchmark populations, the minimums every one of their figures passes, and why the figures are computed over resolved section ids

**Status:** Accepted — E5-04.

## Context

[SPEC §5.1](../SPEC.md) settles what a benchmark *is* — "to be comparable,
sections must match on both length and level", the default comparison set is
"the same Lead Faculty's courses", there is a university-wide line, leadership
can define named sets, and benchmarks are past-referencing: "week N of a 12-week
section is compared against week N of 12-week sections of the same level in the
current *and prior* terms, regardless of start date".

It does not settle four construction questions that `app.services.benchmarks`
cannot avoid answering, and a reasonable engineer could take each of them the
other way.

1. **Does the university-wide line pass the same two minimums as the comparison
   line?** §4.1 item 7 is written about "a figure computed from a comparison
   set", and whether an institution-wide aggregate is one of those is a reading
   rather than a sentence.
2. **Is the hero section in its own default set, and in the university line?**
   §5.1 says which *courses* the default set is drawn from and says nothing
   about the section being reported on.
3. **How far back does past-referencing reach?** §5.1 says "current and prior
   terms" and names no horizon; §4 has a retention rule and it is about data
   rather than about benchmarks.
4. **Where is a figure over a set that is not a cohort actually computed?**
   E5-03 shipped both per-term cohort views and two `SECURITY DEFINER` set
   functions over an arbitrary section-id array (ADR 0165), and either could in
   principle serve.

## Decision

**One: every figure, on both lines, passes both configured minimums.** The
university line is suppressed by `benchmark_min_sections_default` and
`benchmark_min_respondents_default` exactly as the comparison line is, and the
test is applied per figure — each week of a trend, and a workload mean and its
median separately — never once per report. There is one place in the codebase
where a comparison figure is built, `comparison_after_suppression`, and this
service reaches it once per figure with that figure's own counts.

**Two: the hero section is excluded from its own default set and included in the
university line.** A section compared against a set it belongs to is compared
partly against itself, and the thinner the set the larger the share of the
comparison that is the section's own answers — which runs in the direction that
flatters a section on a quiet week and damns it on a loud one. The university
line is a statement about what the institution looks like, and one drawn with a
single section deliberately removed is not that statement.

**Three: there is no second horizon.** Every term whose rows §4's retention rule
still keeps is counted. Nothing in the resolution names a term at all, which is
what makes past-referencing a property of the query rather than a feature added
to it.

**Four: a figure is computed by resolving section ids and handing them to
E5-03's two set functions.** The service resolves a population to a list of
section ids, calls `benchmark_set_week` and `benchmark_set_rating_week` over
that list, and seals each answer. It computes no mean, no median and no count of
its own.

## Alternatives rejected

- **Exempting the university figure from the minimums** on the reading that an
  institution-wide aggregate discloses nobody. Rejected: that is an inference
  from §4.1 item 7 rather than a reading of it, and the population it would
  exempt is not always institution-wide in practice — a 15-week doctoral cohort
  may be two sections and nine people, and the exemption would show that figure
  precisely because the line it sits on has a reassuring name. A rule that
  applies to a figure because of the label on its line is the shape
  `docs/MISTAKES.md` entry 22 records.
- **Including the hero section everywhere**, which is one fewer rule and one
  fewer thing to get wrong. Rejected for decision 2's reason; the cost of
  keeping it is that "the population" means two different things on the two
  lines, which this record and the resolvers' docstrings both state.
- **A benchmark horizon of its own** — two years, or four terms — so that a
  cohort is not compared against a curriculum that has since changed. Rejected
  as a policy nobody has asked for over data nobody has yet: §4's retention rule
  is already a horizon, a second one is a number with no owner, and a benchmark
  that silently stopped counting a term would be very hard to notice. If the
  question becomes real it is a spec change, not a constant.
- **Aggregating the per-term cohort views in Python.** This is the alternative
  that looks cheapest and is wrong on its own terms: **a cross-term median is
  not derivable from per-term medians.** Averaging medians is not a median, and
  there is no weighting that repairs it — the middle value of a combined
  population depends on the values, not on the per-term summaries. A mean could
  be recombined from a mean and a count; the median could not, and §3.2 asks for
  "true means and medians". The same objection applies to the distinct count of
  people, which cannot be summed across terms without counting a student in two
  sections twice (`docs/MISTAKES.md` entry 50). The set functions exist to
  aggregate an arbitrary cross-term set in one pass, and they are used.
- **Narrowing the named set's term axis to its member courses.** Rejected
  because it is not available: the term-axis views are keyed by
  `(length, level, term, start date)` and carry no course, so there is nothing to
  narrow on, and building a per-set term-axis function would be a migration in a
  ticket whose whole diff is policy. `named_set_term_axis` therefore answers the
  *cohort the set declares* rather than its membership, which is what E5-06's
  preview and E9 need and is stated in the function's own docstring.

## Consequences

Every comparison number this product shows is now decided in one place, and
every one of them passes two thresholds rather than one — including the
university line, which is the figure a reader is most likely to assume is safe.
The cost is that a small institution sees both lines suppressed on a cohort
where only the comparison line would have been, and that is the intended
trade.

Excluding the hero from its own set means the comparison line can be thinner
than the university line by exactly one section, so the two can disagree about
suppression on the same report — which is correct and will look like a defect to
somebody. It is worth saying once here that it is not.

Resolving ids and calling the set functions means every population costs one
round trip per figure family rather than a join, and means a benchmark depends
on a role the application cannot become: if `pulse_benchmark_definer` loses a
column grant, every benchmark in the product empties at once. ADR 0165 records
that owner, and its 2026-09-13 amendment now names every column it holds.

`named_set_term_axis` answers a cohort rather than a membership, which is a
limit E5-06 and E9 inherit; it is written in the function's docstring so that the
next reader meets it before a chart does.
