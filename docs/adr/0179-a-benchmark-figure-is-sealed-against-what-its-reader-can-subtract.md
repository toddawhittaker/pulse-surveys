# 0179 — A benchmark figure is sealed against what its reader can subtract

**Status:** Accepted — E5-14. Amends decision 1 of
[ADR 0166](0166-the-benchmark-populations-and-the-minimums-every-one-of-their-figures-passes.md);
its decision 2 (the default set leaves out the reported section, the university
line keeps it) stands. The seal in its final form (rounds 4 to 6) is the
orchestrator's ruling while the owner was away; it only ever withholds more,
and it is flagged for the owner's review at the E5 epic pull request.

## Context

ADR 0166 sealed each figure against the counts of its whole population. SPEC
§5.1 and §4.1 item 7 say a figure computed from fewer sections or people than
the minimums is not shown; before E5-14 they did not say which population is
measured when the reader already knows part of it.

She does. An instructor knows her own sections' figures and response counts
exactly, and the report shows her several populations at one cutoff: the
default set of each section she teaches, and the university line. Any of those
she can add and subtract. The seal took five rounds:

- **Round 2**, from the boundary's spec-conformance HIGH: the university line
  keeps the reported section, so subtracting it (her section of fourteen, two
  one-student sections elsewhere) left a mean over two students. The seal
  became "everyone but the reported section, and the complement after the
  default set".
- **Round 3**, from the privacy pass over round 2 (MEDIUM): a reader teaches
  more than one section. The seal moved to the *reader group*, every section
  taught by anyone who teaches the reported one. A draft that removed the
  group from the populations was withdrawn before it was built: in the seeded
  world one person teaches the hero's whole default set, which would have
  emptied the comparison.
- **Round 4**, from the re-check on d7b4561 (HIGH, verified): co-teachers do
  not share knowledge. Instructor Y knows only Y's sections, so a remainder that
  was "empty" after removing the whole group could be two sections and six
  people after removing Y's alone. The seal became per person.
- **Round 5**, from the final check on b2579f9 (HIGH, verified through the
  report route): a reader teaching sections under two leads sees both leads'
  default sets and the university line at one cutoff. Removing her own sections
  and only this report's default set left the other lead's set inside the
  remainder, and university minus both sets minus her own sections was one
  unled section with one student, whose rating the arithmetic recovered.
- **Round 6**, from the check aimed at the closure argument on 0361fb3 (HIGH,
  verified through the report route): the university seal never checked the
  lead atoms themselves. With the rest of the university empty, the university
  minus her own sections minus the default set she is shown was a second, thin
  lead's set — one student, whose hours the arithmetic recovered exactly
  (152 − 83 − 28 = 41).

Two declared fallbacks were not used. After round 4 it was prior terms only;
it fixes when a snapshot is taken, and round 5's finding was set algebra
between populations shown at one cutoff, which happens with prior-term data
too. After round 5 it was withholding the university line entirely; that would
have broken the exit clause's three lines per panel, and round 6's fix is
exactly what the closure argument below requires. No further review round ran;
the owner reviews the whole seal at the epic pull request.

## Decision

The populations are unchanged: the default set leaves out the reported section
A, and the university line includes it. A figure for a week is shown only if:

- **(a)** its population meets both minimums; and, for **each person *p***
  holding an instructor grant on A (`authz.teaching_instructors_of`), with
  *T(p)* every section *p* teaches in any term (`taught_section_ids`):
- **(b_p)** the population minus *T(p)* is empty or meets both minimums; and
- **(c_p)**, for the university line only, **every atom *p* could isolate** is
  empty or meets both minimums: each lead atom *D(S)* − *T(p)*, where *D(S)* is
  the default set, as resolved today, of a section *S* of *p*'s in A's term at
  A's length and level; and the rest of the university, the university minus
  *T(p)* minus the union of every such *D(S)*.

"Empty" means zero contributors to the figure being sealed at that week and
cutoff; a workload remainder whose week row exists but whose hour-reporters are
zero counts as empty. A section with no instructor has no *p*, so only (a)
applies; nobody can read that report, because the route requires a teaching
grant. Counts come from the same set functions, over those section-id lists,
with the population-wide cutoffs of ADR 0178. The instructors come from
`authz.teaching_instructors_of` and their sections from `taught_section_ids`;
`authz.reader_group_section_ids`, round 3's helper, is removed.

**How the seal reaches the chokepoint.** "Every pair meets both minimums" is
the same statement as "the smallest count of sections and the smallest count
of people among them meet both". So `_tightest` in `app/services/benchmarks.py`
takes the component-wise minimum over the population's own contributors and
each non-empty remainder's, and hands that one pair to
`comparison_after_suppression`, which still makes the decision. Every figure
still passes through the chokepoint, and the provenance invariants hold
unchanged.

**Why this is enough: the closure argument.** Fix one reader *p*, one length
and level, one term, and one course week at one cutoff. Every population *p*
can see a figure for is a union of disjoint atoms:

1. *p*'s own sections, which *p* already knows;
2. for each lead L of a course of one of *p*'s sections there, L's sections
   minus *p*'s own — the default sets of *p*'s sections, less *p*'s sections;
3. the rest: the university minus atom 1 minus every atom 2.

Every figure *p* can see is a combination of atom aggregates. A default-set
figure is shown only if its own lead atom is empty or meets both minimums
((b_p)), and the university figure only if every atom other than *p*'s own
sections does ((c_p)). So every combination *p* can compute is over atoms that
meet the minimums, and none isolates fewer people or sections than they
protect. The argument covers one reader, one term and one cutoff; what lies
outside it is carried (below).

## Alternatives rejected

- **Removing the reader's sections from the populations** (round 3's draft).
  It empties the comparison where the reader teaches the whole cohort, and
  hides nothing from her that (b_p) does not.
- **Sealing on the reported section alone** (round 2), **on the reader group**
  (round 3), or **against this report's default set only** (round 4's (c_p)).
  Each left an atom the reader could isolate, as above.
- **Prior terms only.** Addresses snapshot timing, not set algebra.
- **Rounding the shown figures**, or **a higher university minimum.** The
  subtraction needs neither the unrounded value nor a small threshold.

## Consequences

- Figures are withheld more often, most of all the university line in thin
  length-and-level cohorts and for readers who teach under several leads.
  In the seeded world the hero's whole default set is taught by the hero's own
  instructor, so (b_p) passes on an empty remainder and the exit story's three
  lines hold; that instructor also teaches `BIOL-215-R3WW`, so E4's exit story
  there does not withhold the hero's university line. A current-term 12-week
  undergraduate section outside the instructor's own sections that holds a few
  answers does withhold it, and the exit drive states that as its premise.
- The argument covers one reader. Two readers who pool what they know can
  combine atoms neither could isolate alone. That is out of scope: §4.1's
  threat model is one reader, and no per-person rule can stop collusion.
- Snapshots across terms and membership resolved at read time are outside the
  argument, which fixes one term and one cutoff; both are carried.
- Each report read counts more populations — for each instructor, one
  remainder per population, one lead atom per default set she sees, and one
  rest of the university — each read once; default sets are resolved once per
  read and shared between instructors.
- **Proven by:** `test_the_university_line_is_sealed_on_everyone_but_the_reported_section.py`;
  the per-person tests, including the reviewer's co-teaching world (Y's
  set, X's two sets, a default set of all three: withheld for both streams, and
  shown in its twin with an outside remainder at both minimums) and the
  single-instructor "made only of her own sections: shown" case; the empty
  workload remainder in both directions (battery B7); and
  `test_the_university_remainder_removes_every_default_set_its_reader_sees.py`,
  marked invariant — the two-lead world with an unled one-student section Z is
  withheld for both of the reader's sections, and shown in its twins without Z
  and with Z's course at both minimums; and, in the same module, round 6's
  thin lead atom, which withholds the university line on both reports and
  leaves it shown when the atom is empty. Named mutations: (c_p) subtracting
  only this report's default set, and the lead atoms not checked as university
  remainders. Round 4's per-person tests are in
  `test_a_readers_own_sections_are_one_group_for_every_benchmark_figure.py`.
