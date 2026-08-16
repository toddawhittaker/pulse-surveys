# E0-17 — Demo seed script

**ID:** E0-17
**Branch:** `e0/seed-script`
**Depends on:** E0-07, E0-09, E0-15

## Context

`scripts/seed.py` builds the demo institution every later epic develops against:
a hierarchy, a term with its start-letter map, sections whose codes parse, a
people graph with assignments, and lead-faculty mappings. The org shape it
creates decides how useful E9's roll-up work will be to develop against, so it
should include the awkward cases from the start.

Read first: SPEC §2.1 (the assistant-dean worked example — seed it), §2.2 (the
Fall 2026 start-letter map), §13 (`scripts/seed.py`), §6.3.

## Scope

- `scripts/seed.py`, idempotent: running it twice leaves the same database
  state rather than duplicating rows.
- A demo institution with at least two colleges, several departments, a
  department grouping more than one prefix (the Math / MATH-STAT-MIS case from
  §2.1), and courses across all five levels.

  **The design prototype's course numbers cannot be seeded, and this is where
  that lands.** E0-05 settled the number-to-level bands (SPEC §8), and 24 of the
  25 course numbers written across `design/` fail them — every four-digit
  number below `8000`, which is all of `BIOL 2150`, `CHEM 1210`, `MATH 1610`,
  `PSYC 1010` and the rest. Only `MATH 040` survives. SPEC §2.1's own two
  examples were renumbered when the bands landed; the `design/` corpus was
  deliberately not, because it is a design deliverable rather than schema.
  Whoever builds this ticket picks the seed numbers against §8 and should
  expect them to disagree with every screenshot in `design/`. Renumbering that
  corpus, or deciding it stays as illustration, is a separate call — raise it
  rather than quietly reconciling one side to the other.

  **Every seeded course also needs a title.** `course.lms_title` is `NOT NULL`
  (E0-05, kept deliberately — see [E0-21](E0-21-review-debt.md)), so a course
  inserted without one fails.
- A Fall 2026 term with the §2.2 start-letter map seeded as data, and sections
  spanning several start letters, both modalities, and at least three different
  lengths.
- A people graph exercising the cases that break naive implementations: an
  **assistant dean** between chairs and a dean, a **two-hat person** holding
  both a chair assignment and a lead-faculty assignment, and **two sibling
  leads** in the same prefix so isolation is visible in development, not just in
  tests.
- Lead-faculty mappings, including at least one course deliberately left
  unmapped so the fall-to-chair path is exercised.
- `make seed` runs it against the running stack.

## Out of scope

- Responses, comments, classifications, reports — no survey data exists until
  E2 and E4. This seeds structure only.
- The admin console people editor and CSV import (E9, E11).
- Performance-scale data for the 500-section load test (E13).

## Two things this script can switch off without meaning to

Both found by E0-09 and E0-14's security reviews, both about the fact that a
seed script runs as the **superuser identity** (ADR 0009) and a bulk loader is
where people reach for the sharp tools.

**1. `SET session_replication_role = replica` disables E0-09's supervision
trigger entirely** — no `ALTER TABLE`, no ownership check. Measured: a two-row
cycle stored cleanly with it set. The application role is refused the parameter
itself, so this is not a path `pulse_app` can take; it is a path *this script*
can take. If the loader uses it for speed, it owes a check afterwards that the
graph it just wrote is still acyclic and still Care-clean, because nothing else
will have looked. ADR 0027 names this ticket.

**2. Seeding an `lti_platform` row for the mock LMS is what would make ADR 0038
wrong.** E0-14 argues the mock is safe in the base Compose file because it holds
nothing, reaches nothing, publishes no port outside the development override,
and **is trusted only by a row in `lti_platform`** — and no such row exists
anywhere in the repository today. A seed that inserts one into a path a
deployment also runs closes that gap in the wrong direction. If this script
registers the mock, the registration must be unreachable from a deployed
environment, and ADR 0038 needs amending to say how.

## Acceptance criteria

- [ ] **If the loader disables triggers, it re-checks what they would have
      refused** — no cycle, no edge into or out of a `CARE` assignment — and
      fails loudly if the seeded graph violates either. If it does not disable
      them, say so in the pull request so the next person does not add it.
- [ ] **Any `lti_platform` row naming the mock LMS is unreachable from a
      deployed environment**, and ADR 0038 is amended to say what enforces that.
      If this script seeds no registration, say so and leave ADR 0038 alone.
- [ ] `make seed` on a freshly migrated database completes without error.
- [ ] Running `make seed` twice produces no duplicate rows and no constraint
      violation.
- [ ] Every seeded section code parses through E0-07 and yields dates inside its
      term.
- [ ] The seeded graph contains the assistant-dean shape from §2.1, and a test
      asserts its structure — the purview it implies is E9's to compute, but the
      shape must be present now.
- [ ] Two sibling leads exist in one prefix with disjoint course sets.
- [ ] At least one course has no lead-faculty mapping.
- [ ] Seeded people are obviously fictional; no name resembles a real person at
      a real institution.

## Definition of done

**Tests apply.** One integration test that seeds into a testcontainers database
and asserts the structural claims above — idempotency, the assistant-dean shape,
sibling leads, the unmapped course. This is also the fixture E9 will reuse.

**Docs apply.** `README.md` documents `make seed` and describes the demo
institution, including which awkward cases it deliberately contains and why.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies but is light.** Confirm the seed script cannot run
against a non-development environment, and that no seeded person carries a real
email address or anything resembling real student data.
