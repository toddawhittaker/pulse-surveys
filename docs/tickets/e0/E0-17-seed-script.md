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
  §2.1), and courses across UG, GR, and DR levels.
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

## Acceptance criteria

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
