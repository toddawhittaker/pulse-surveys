# 0203 — Named-set figures are read inside the reader's purview, and the seal counts every hat

**Status:** Accepted. Amends [ADR 0173](0173-a-named-set-is-read-by-every-leader-and-written-by-the-one-who-defined-it.md) (every leader still lists every set; a set's figures are scoped to the reader) and [ADR 0179](0179-a-benchmark-figure-is-sealed-against-what-its-reader-can-subtract.md) (the reader's sections include her leadership purview, and a leadership reader is sealed against).
**Date:** 2026-10-12
**Ticket:** [E9-05](../tickets/e9/E9-05-named-set-figures-under-the-readers-purview.md)

## Context

[SPEC §5.1](../SPEC.md) and [§5.5](../SPEC.md) (E9 ruling 5) show a named set's
figures to a leader over the set's sections inside her purview, at both benchmark
minimums, sealed against her. E9 decision 14 sets the cutoff at the start
cohort's own close. Until now E5's three named-set reads took no reader, and the
term-axis one answered a declared length and level institution-wide from a view
that holds no course. The spec does not say how the read is shaped, where the
cohorts come from, how the seal learns a person's purview, or what happens to
names that differ only in case or spacing that already exist.

## Decision

- **One door.** `benchmarks.named_set_series(session, *, set_id, scope, term_id,
  settings)` replaces `named_set_trend`, `named_set_workload` and
  `named_set_term_axis` (none had a caller). It answers one `NamedSetCohort` per
  start cohort, each with its published weeks on both week axes, every figure
  sealed. One door reads each cohort's population once per set function, as
  `section_benchmarks` does for a report.
- **Cohorts come from the purview, never from the set.** They are the start
  dates of the reader's purview sections in the viewed term at the set's length
  and level. Cohort C's population is the set's resolved sections inside the
  purview that start on C. So a set wholly outside the purview answers the same
  cohorts, every figure suppressed, as a thin set inside it.
- **The cutoff** for course week N is the earliest week-N window close among
  every section of the term with that start date, length and level. It depends
  on no reader. Only weeks whose report has opened (`week_is_published`) are
  answered.
- **The seal counts every hat.** Each reader of a report is one person whose
  known sections are every section she teaches together with every section in her
  leadership purview; `section_benchmarks(…, scope=…)` adds the leadership reader
  as one more such person, and an instructor who also holds a leadership
  assignment is sealed against her purview on her own report. A named-set figure
  is sealed against its population and its population less the reader's known
  sections, which is empty by construction: the purview narrowing keeps a
  sibling's course out, and the seal is the second layer.
  `authz.leadership_section_ids` answers a person's purview sections, because
  only `authz.py` and `deps.leadership_scope` may name `resolve_scope`.
- **The route** `GET /leadership/comparison-sets/{set_id}/series?term_id=` takes
  its scope from `leadership_scope` only. An unknown set is the existing 404; an
  unknown term is a 404 with `leadership_rollup.term_unavailable`. That copy
  module registers the `leadership_rollup` surface (decision 15); the line's
  legend and withheld notice are frontend words, filed by E9-11 under the same
  prefix, because the API serves none.
- **Names are unique ignoring case and spacing.** A unique index on
  `lower(btrim(regexp_replace(name, '\s+', ' ', 'g')))` (migration
  `e9a7c9e1b807`), mapped to the existing duplicate-name sentence, reworded to
  say so. The migration renames existing near-duplicates, in creation order, to
  their name plus the smallest free ` (n)`; its downgrade drops only the index.
- **Residues accepted (ruling 6):** a set's membership is read at read time, so
  an edit moves weeks already published; one week read in two terms can differ;
  two leaders who compare what each sees can pool it.

## Alternatives rejected

- **Changing `named_set_trend` and `named_set_workload` in place**, as the ticket
  first said: three set-function calls per cohort where one door makes two.
- **Cohorts taken from the set's sections**: a set outside the purview would
  answer no cohorts while a thin one inside answers suppressed ones, which tells
  "outside" from "too few".
- **Resolving a co-instructor's purview inside `benchmarks.py`**: it would name
  `resolve_scope` or read `assignment_scope` outside `authz.py`.
- **Keeping the term-axis read**: its view holds no course, so it cannot be
  narrowed to a purview.
- **Deleting near-duplicate sets, or refusing to migrate while any exist**: the
  first destroys a definition and its membership; the second leaves a deployment
  unable to upgrade without an operator renaming rows by hand.

## Consequences

- The four cohort views have no reader under `backend/app/`; E9-12 drops them.
  E9-05's sweep checks Python only, because the view files still name them.
- The seal resolves the default set of every one of a reader's sections that
  matches the reported section's term, length and level in one statement, and
  asks the set functions once per distinct remainder. So the statements a
  report read sends do not grow with the number of sections in the reader's
  purview; they grow only with the number of distinct lead sets among them (two
  aggregates each), and the one default-set statement answers more rows. E9-09's
  drill-down, which passes the reader, carries that cost.
- An instructor with no leadership assignment is sealed exactly as before.
- A renamed set keeps its new name after a downgrade; the old names are not kept.
