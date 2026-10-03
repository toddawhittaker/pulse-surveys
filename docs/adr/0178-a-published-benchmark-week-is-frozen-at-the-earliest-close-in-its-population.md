# 0178 — A published benchmark week is frozen at the earliest close in its population

**Status:** Accepted — E5-14. The freeze is the owner's ruling of 2026-09-22,
which SPEC §5.1 now states. The population-wide cutoff (round 4) is the
orchestrator's ruling while the owner was away; it only ever withholds more,
and it is flagged for the owner's review at the E5 epic pull request. Changes
the signature of the two set functions ADR 0165 built.

## Context

Before E5-14, SPEC §5.1 said nothing about when a comparison figure is
computed, and the epic computed every figure at read time (breakdown decision
1) over every stored response.

The E5 boundary's privacy review found what that allowed. The two set
functions counted responses in survey windows that were still open, and the
report recomputes its figures, unrounded, on every read. Sections of one term
start on different dates, so while a later-starting section's week 3 is open,
an earlier section's published week-3 comparison already exists and changes
with each submission. A reader who reloads sees one student's answer arrive as
a step in the figure; a simulation recovered the student's rating from that
step in 969 of 1000 trials. The owner ruled: freeze at close.

Where the cutoff comes from took three rounds, because any cutoff that depends
on the reader can hand one reader two snapshots of one population, and the
difference between two snapshots is exactly what closed between them.

- **Round 2** cut each report at its own section's close. An instructor with
  two staggered sections of one cohort saw two snapshots (privacy, HIGH).
- **Round 3** cut at the earliest close among the reader group — every section
  taught by anyone who teaches the reported section. Under co-teaching the
  groups of two sections differ, so one reader could still meet two cutoffs
  (privacy re-check on d7b4561, HIGH).
- **Round 4** made the cutoff independent of the reader. The final privacy
  check on b2579f9 found the cutoff sound.

## Decision

**One cutoff per population and week, whoever reads.** For a report of
section A and course week *w*, the cutoff *T(w)* is the **earliest** week-*w*
`survey_window.closes_at` among **all sections in A's term with A's length and
level**, A included (`app.services.reporting._population_cutoffs`). Every report
over that population and week shares one snapshot, and *T(w)* is never later
than A's own close, so a figure is fixed from the moment A's week publishes.
Sections in other terms never move it.

**What counts.** A response counts toward week *w* only if the window it was
submitted in (its own section's window for its `week_id`) has
`closes_at <= T(w)`, and its `last_submitted_at <= T(w)`. Equal is counted; one
microsecond later is not.

**The cutoffs are applied inside the set functions**, as new `_v003` bodies:

    public.benchmark_set_week(section_ids uuid[], course_weeks integer[], closed_by timestamptz[])
    public.benchmark_set_rating_week(section_ids uuid[], course_weeks integer[], closed_by timestamptz[])

`course_weeks[i]` pairs with `closed_by[i]`. Each function returns rows only for
the course weeks asked, each under its own cutoff, with `_v002`'s columns.
Mismatched arrays count nothing. The one-argument signatures are dropped and the
downgrade restores them. Owner, `SECURITY DEFINER`, pinned `search_path` and
`EXECUTE` to `pulse_app` only are exactly `_v002`'s.

**The service takes the cutoffs as a required argument.** `benchmark_trend`,
`benchmark_workload`, `named_set_trend` and `named_set_workload` each take
`cutoffs: Mapping[int, datetime]`, course week to an aware instant; a naive
instant, or a course week with no cutoff, is refused loudly. The report
derives the mapping on the server. What cutoffs a leadership reader of a named
set gets is E9's, with purview (`../tickets/e6/carried-from-e5.md`).

**One call per population per read**, from the boundary's data-model finding:
each population is resolved once, and each set function is called once per
population with every published week's cutoff. The rating function's rows
serve both streams.

## Alternatives rejected

- **The reported section's own close** (round 2) and **the earliest close in
  the reader group** (round 3). Both depend on the reader, and both handed one
  reader two snapshots of one population.
- **Compare only against terms that have ended.** Nothing could move. Rejected
  because it drops the current term, which §5.1's "current *and* prior terms"
  does not allow; an institution's first term would have no comparison at all;
  and it would be a spec change. Round 4's stopping rule held it in reserve as
  the fallback, and it was not needed for timing.
- **Keep live figures and round what is shown.** Rejected because rounding
  narrows the channel and does not close it: a figure that still moves still
  says somebody answered, and a step across a rounding boundary still bounds
  what they answered.
- **Store each week's figure when its window closes.** The same freeze, held in
  a table. Rejected because breakdown decision 1 computes benchmarks at read
  time and names materialization as E13's fallback for speed; a stored copy is
  a second source to keep in step with the functions.

## Consequences

- **The cost: in the current term, a section counts toward week *w* only if
  its own week-*w* window closed by the earliest week-*w* close in its term.**
  A later-starting section of the same length and level joins week *w* only
  once its week *w* has closed before the earliest one did — so in practice the
  current term contributes the earliest-starting cohort and any section that
  closed with it. Prior terms count in full. Figures early in a term rest
  mostly on prior terms and are withheld more often. SPEC §5.1's "regardless of
  start date" is narrowed to say so.
- **The within-term snapshot class is gone.** No reader can obtain two
  different snapshots of one population and week in one term.
- **Residuals, carried:** a reader's prior-term report set against a current
  one (snapshots across terms); membership resolved at read time — a lead
  mapping, a section's length or start date, a teaching assignment, or a
  late-synced, earlier-starting section of the same length and level (which
  moves the population cutoff for weeks already published) — all still move a
  published figure; and the submit-at-close race (`submissions.py` reads the
  clock before its commit).
- **A response last changed after *T(w)* drops out of week *w* entirely**,
  because no response history is kept.
- **The definer reads four more columns**, none of them a person's:
  `response.last_submitted_at`, and `survey_window.section_id`, `week_id` and
  `closes_at` (`benchmark_definer_v002.sql`). Its reach grows from eighteen
  pairs over six tables to twenty-two over seven. ADR 0165's 2026-09-22
  amendment names them, and the equality test moved with them after
  `docs/disputes/E5-14-01.md` was ruled for the code.
- **The signature is pinned.** A marked test compares both functions'
  arguments and result column names with the contract.
- **Proven by:** `test_a_published_benchmark_week_never_moves_after_its_own_close.py`,
  `test_the_benchmark_set_functions_count_only_what_each_weeks_cutoff_had_fixed.py`,
  the cutoff tests in
  `test_a_readers_own_sections_are_one_group_for_every_benchmark_figure.py` —
  a two-section instructor's reports share one snapshot, co-teaching gives one
  reader one snapshot, a prior-term section of the same length and level never
  moves the cutoff (the battery's C3), and sections of another length or level
  never move it while an earlier-closing section alike in the term does — and
  `test_a_benchmark_cutoff_is_aware_and_names_the_week_it_cuts.py` (the
  battery's X1 and X2). Named mutations: the round-3 reader-group cutoff, and
  the term filter deleted. `docs/disputes/E5-14-02.md` records why A's and B's
  default-set members are not byte-identical (two populations by design, whose
  difference is the reader's own sections) while their university figures
  are.
