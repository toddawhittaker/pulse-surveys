# E9-05 — Named-set figures under the reader's purview

**ID:** E9-05
**Branch:** `e9/named-set-figures-under-the-readers-purview`
**Depends on:** 01
**Lane:** heavy
**Why this lane:** it adds `invariant`-marked tests for §4.1 items 2 and 7
(the generated isolation properties over named sets, and the seal for a
leadership reader). Its code is in `services/benchmarks.py`,
`services/comparison_sets.py` and `api/leadership.py`, which are light paths,
and its migration is on `comparison_set`, which is none of the four heavy
kinds; if the build finds it needs a new view or function under
`views_sql/`, that is heavy too.
**Size:** L
**Security-relevant:** the first read that shows a leader a figure computed
over a set someone else chose. A defect here shows a Lead Faculty member a
sibling lead's courses through a set, or a figure thin enough to subtract.

## Context

Ruling 5: named-set figures are shown on roll-ups, scoped to the reader's
purview, sealed against the reader, and proven by generated properties. SPEC
§5.1 and §5.5 now say so. Today `named_set_trend` and `named_set_workload`
take a set and cutoffs and nothing about the reader, `named_set_term_axis`
answers the set's declared length and level institution-wide, and nothing
calls any of them (ADR 0173 lets every leader list every set).

**The seal counts a leadership reader (§5.1).** `_section_populations` seals
each figure against each instructor of the reported section, using the
sections that instructor teaches (ADR 0179's `taught` list). The seal must
cover what one **person** can subtract, across every hat they wear (§5.1):

- A leadership reader's known set is every section in the person's
  leadership purview together with every section the person teaches.
- An instructor of the reported section who also holds a leadership
  assignment has every section in their leadership purview added to the
  sections they teach. So the instructor's own report changes for a two-hat
  instructor, and stays as it is for an instructor with no leadership
  assignment.

The reader enters the seal exactly as an instructor does, including the
university line's two extra pieces. E9-09's drill-down passes the reader.

**Named-set figures (decision 10).** A named set's figure for a reader is
computed over the set's resolved sections (`resolve_named_set`) that lie
inside the reader's purview, in the term being viewed, per start cohort, on
the term axis. It is computed through the set functions `benchmark_set_week`
and `benchmark_set_rating_week`, meets both benchmark minimums (3 sections
and 10 distinct respondents, §4.1 item 7), and passes the seal with the
reader. A set with no section inside the purview answers suppressed figures,
the same as a thin one, so a reader cannot tell "outside my purview" from
"too few".

**The cutoff (decision 14).** For start cohort C and course week N in the
viewed term, the cutoff is C's week-N window close. Every section of one
start cohort shares its window closes, so this is ADR 0178's earliest close
within the population.

**`named_set_term_axis` is deleted.** It answers the declared cohort
institution-wide and its view holds no course to narrow by, so it cannot be
scoped. That leaves the four cohort views unread; E9-12 retires them.

**Set names that differ only in case or spacing** become one set. A unique
index on the normalized name (trimmed, inner spaces collapsed, case-folded)
refuses the near-duplicate, and the route answers it with a governed refusal
sentence. Existing near-duplicates in a database are renamed by the migration
with a suffix rather than deleted, and the migration says so.

**The route.** `GET` on a leadership route answers one named set's series for
the viewed term and the reader's scope, from `leadership_scope` (E9-01). The
reader never passes a purview. E9-11 draws it beside a node's own line.

**Residues (ruling 6)** are recorded in ADR 0203, not built: membership read
after publication, one week read in two terms, and two readers pooling.

Read first: SPEC §4.1 items 2 and 7, §5.1 (comparison sets, the freeze, the
seal) and §5.5; ADRs 0164, 0166, 0173, 0178, 0179 and 0180;
`services/benchmarks.py` whole; `services/comparison_sets.py`;
`schemas/` for the named-set API; the carried entries in
`../e6/carried-from-e5.md` named below.

## Owns

- `backend/app/services/benchmarks.py`: the reader in the seal;
  `named_set_trend` and `named_set_workload` take the reader's scope and the
  viewed term and return per-cohort series; `named_set_term_axis` deleted.
- `backend/app/services/comparison_sets.py` and the named-set routes'
  refusal: the normalized-name refusal.
- `backend/app/services/authz.py`: the one helper `leadership_section_ids`,
  because only `authz.py` may resolve a person's purview for the seal.
- `backend/app/models/benchmark.py`: the normalized-name index, so
  `alembic check` agrees with the migration.
- SPEC §5.1: the seal sentences, so "her sections" means taught plus purview
  in every clause.
- `backend/app/api/leadership.py`: the named-set series route.
- `backend/app/schemas/` for the series payload; the near-duplicate refusal
  under the existing `leadership_comparison_sets` prefix.
- `backend/app/copy/leadership_rollup.py` (new) and its frontend twin, with
  the named-set line's words, and the `leadership_rollup` surface placed in
  the copy inventory's `SURFACES_WITH_NO_CONFIDENTIALITY_LINE` with its reason
  (roll-ups show figures over sections, never a student's words). README
  decision 15; E9-07 and E9-11 file their strings under it.
- Migration **`e9a7c9e1b807`**, planned `down_revision = "e9c3f5a7b403"`
  (re-pointed to the head it finds): the unique index on the normalized name.
- The `invariant`-marked tests below, and the generators they need (reusing
  E9-01's forest generators).
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated.
- ADR **0203** (named-set figures under the purview, the reader in the seal,
  the cutoffs, the residues, the name index). It amends ADR 0173 (sets are
  listed by every leader; figures are scoped) and ADR 0179 (the reader), each
  with a line.

## Reuse, do not rewrite

`resolve_named_set`, `_answered`, `_sealed_through`, `_section_populations`,
`_trend`, `_workload` and the two set functions in `services/benchmarks.py`;
E9-01's `Purview` and `leadership_scope`; the E5-14 sweep that allows only
`benchmarks.py` to name the benchmark relations.

## Done when

1. **A sibling lead's set shows nothing of the sibling.** Lead A reads a set
   made of A's course and sibling lead B's course: every figure equals the
   figure over A's course alone (or both are suppressed), and B's
   contribution is absent. Adding B's second course to the set changes no
   figure A reads. Marked `invariant`.
2. **No course outside the purview, generated.** Over generated forests,
   mappings and named sets drawn from random course lists, for every reader
   and every set, every section contributing to a served named-set figure is
   inside the reader's purview. Marked `invariant`. The generator draws sets
   that straddle a purview boundary, and a test asserts it does (MISTAKES
   entry 15).
3. **The minimums hold.** A named-set figure over fewer than 3 sections or 10
   distinct respondents inside the purview is suppressed, a mean, a median
   and a drawn point alike; at exactly 3 and 10 it is shown. Marked
   `invariant`.
4. **No subtraction isolates a section outside the purview.** With S = {own
   course, sibling course X} and S' = {own course}, no pair of figures the
   reader can be served by this ticket's reads (the named-set figures over S
   and S', and `section_benchmarks` for the own course's section read with
   the reader in the seal) differs by a figure over X alone. E9-12 repeats
   this through the routes once the tree and the drill-down exist. Editing a
   set between two reads to add or drop X changes nothing the reader is
   served. Marked `invariant`.
5. **The seal counts a leadership reader.** For a reported section read with
   a leadership reader, a comparison or university figure is suppressed when
   what is left after removing the reader's known set (purview and taught
   sections) is non-empty and below either minimum, and shown when that
   remainder is empty or meets both; tested one respondent either side of
   the minimum. For an instructor with no leadership assignment, the existing
   seal tests stay green, unchanged. Marked `invariant`.
6. **The seal covers both hats.** A Math chair teaches Biology section T. The
   university line U for a report the chair reads, as chair or as T's
   instructor, is suppressed when U less Math less T is non-empty and one
   respondent below a minimum, and shown at the minimum. The twin: the same
   world with the chair not teaching T, where U less Math meets both minimums
   and U is shown. Marked `invariant`.
7. **The university line's first extra piece, for a leader.** U less the
   reader's known set meets both minimums, but one default comparison set of
   a section in the purview, less the known set, is non-empty and thin; U is
   suppressed. The shown twin: that piece meets both minimums (or is empty)
   and U is shown. One respondent either side. Marked `invariant`.
8. **The university line's second extra piece, for a leader.** U less the
   known set meets both minimums, but U less the known set and less every
   such default set is non-empty and thin; U is suppressed. The shown twin:
   that remainder meets both minimums (or is empty) and U is shown. One
   respondent either side. Marked `invariant`.
9. **"Outside" and "thin" look the same.** A set wholly outside the reader's
   purview answers the same payload shape and suppression marker as a thin
   set inside it.
10. **The cutoff is the cohort's own close.** A response submitted after start
   cohort C's week-N close and before another cohort's does not count in C's
   week-N figure; one submitted before it does. Tested one second either side
   (ADR 0178's rule).
11. **The route takes no purview.** The series route resolves the scope from
   the session through `leadership_scope`; a request carrying another
   person's id is answered from the session's own scope. A non-leadership
   session gets ADR 0196's 403.
12. **`named_set_term_axis` is gone,** and nothing under `backend/app/` names
   `benchmark_cohort_week`, `benchmark_cohort_rating_week`,
   `benchmark_cohort_term_axis` or `benchmark_cohort_rating_term_axis`,
   checked by a search with a canary (MISTAKES entry 3).
13. **Near-duplicate names are refused.** Creating "nursing  core" when
    "Nursing core" exists answers the governed refusal sentence (a route
    test); renaming a set to a near-duplicate is refused the same way; a
    name that differs in a letter is accepted. The migration renames existing
    near-duplicates and its downgrade drops only the index.
14. **The surface is placed.** The copy inventory places `leadership_rollup`
    in `SURFACES_WITH_NO_CONFIDENTIALITY_LINE` and collects this ticket's keys
    under it.
15. **The records match.** ADR 0203 is written and indexed; ADR 0173 and 0179
    gain their lines; the docstrings in `benchmarks.py` that say E9 decides
    the cutoffs or that a named set has no reader are rewritten. SPEC §13
    reflects any file added or removed.
16. **The two extra pieces count a two-hat instructor's purview.** The
    instructor of the reported section also chairs department D, and a section
    in D belongs to a course whose lead also leads a course outside D, of the
    same term, length and level. She reads her own report with no leadership
    reader passed. (a) U less her sections (taught and purview) meets both
    minimums, but that lead's default set less her sections is non-empty and
    one respondent below a minimum: U is suppressed, and at the minimum it is
    shown. (b) U less her sections and every such default set is non-empty and
    one respondent below a minimum: U is suppressed, and at the minimum it is
    shown. A twin with the chair assignment removed shows U, which proves the
    piece came from the purview. Marked `invariant`. (Added by the build
    interface; a chair is chosen because a lead's default sets lie inside her
    own purview, so for a lead both pieces are empty.)

## Shares files with

- `services/benchmarks.py`: 07 (node series through the set functions) and
  09 (calls the reader-aware seal).
- `api/leadership.py`: 07 and 09.
- `openapi.json`, `wire.gen.ts`: 04, 06 to 09.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 14, 15, 19, 50, 51 and 53.

## Known traps

- **Entry 51.** Subtraction across the sequence of reads (this week, next
  week, after a set edit) is the attack; done-when 4 drives it in order.
- **Entry 50.** The minimum counts distinct respondents and sections, not
  rows.
- **Entry 19.** The generated property computes the expected contributor set
  from the purview and the set's members independently, never by calling the
  function under test.
- **The level is not re-checked** in `resolve_named_set`, by design (ADR
  0164); do not add a second statement of it.

## Not in this ticket

- Drawing the named-set line (11).
- The drill-down route (09).
- Dropping the cohort views (12).
- Freezing set membership (ruling 6).
