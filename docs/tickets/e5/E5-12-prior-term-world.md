# E5-12 — The prior-term benchmark world

**ID:** E5-12
**Branch:** `e5/prior-term-world`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** `mock-lms/` and `scripts/` — heavy rows both. Ships
no production behavior; stays behind the development-environment guard
(ADR 0063, 0064).

## Context

The exit line says "benchmarked against prior terms", and nothing seeded
today lives in a prior term. This ticket builds the world the exit drive
(E5-14) and the e2e slices (E5-10, E5-11) read: sections in one or more
prior terms, same lead, matched length+level with the demo section, with
enough seeded responses that the default set and the university line pass
both minimums at the current defaults — and **one deliberately thin
cohort** that must suppress, so suppression is demonstrated by the world
and not only by unit fixtures.

E4-20 is the direct precedent (a fourth mock section and a second seeder,
its ADR 0163 records the machinery); this extends that machinery
backwards in time rather than inventing a third.

Read first: E4-20's ticket and ADR 0163; `scripts/seed_demo_story.py`;
SPEC §2.2 (prior-term start-letter maps are per-term configuration — a
prior term needs its own map rows), §3.4 (enrollment windows);
`docs/MISTAKES.md` entry 48 (a platform holding a section is not the tool
provisioning it — the seed must reach Pulse's own database the way E4-20's
does); the E4-22 anchor rule (no wall-clock-dependent dates).

## Scope

- Mock-LMS sections in at least one prior term: the same lead's courses,
  matched length+level with `BIOL-310-R7FF`'s cohort, plus the thin
  cohort (a length+level pair with fewer than the minimum sections).
- The prior term itself as configuration: term rows, its start-letter map,
  windows — derived per §2.2, hand-entered nowhere.
- Seeded responses across the prior term's weeks at realistic rates
  (E4-20's rotating-commenter machinery reused), no tests asserting the
  generated data's statistics (the E4-20 ruling's rule).
- The demo-drive runbook grows the benchmark steps (the recovery sequence
  memory/file that documents the demo world).

## Acceptance criteria

1. After the full seed sequence on a fresh dev database, the cohort counts
   are stated and reproducible: N sections and M distinct respondents per
   cohort-week for the passing cohort (both above the defaults), and the
   thin cohort below the section minimum — asserted by a seed self-check
   that prints the counts, not by hoping.
2. Every seeded date derives from the term calendar and section codes;
   nothing reads the wall clock (E4-22's rule, applied at write time).
3. Running the seeder twice is safe, proven against a database the loader
   did not fill (MISTAKES entry 31 verbatim).
4. The guard: the seeder refuses outside the development environment,
   same mechanism as E4-20.
5. The exit story world (`seed_exit_story.py`) is untouched — its e2e
   asserts exact numbers; this world must not reach into it.

## Known traps

- **The calendar bomb class** — pinned dates plus real-clock stamps red
  the suite on a schedule; every date in this world is derived
  (`e2e-world-building-traps` is the incident family).
- **A prior term's map is not this term's** — §2.2's letters are per-term
  data; copying Fall 2026's map into Spring is a silent policy.
- **Counting respondents** — the self-check counts distinct students per
  cohort-week, the unit the minimums compare (entry 50), or its printed
  reassurance is in the wrong currency.

## Out of scope

- Any production code path.
- The exit drive itself — E5-14.
- Tests over the generated data's statistics — ruled out by E4-20's
  precedent.
