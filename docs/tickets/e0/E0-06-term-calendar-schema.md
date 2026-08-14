# E0-06 — Term calendar and start-letter map schema

**ID:** E0-06
**Branch:** `e0/term-calendar-schema`
**Depends on:** E0-04

## Context

The academic calendar is institution configuration, not code (§2.2). Terms run
18 weeks for fall and spring and 12 for summer in the reference model, sections
run 3 to 18 weeks, and a per-term start-letter map encodes which letter means
which length and start date. This ticket stores that configuration; E0-07 reads
it to derive section dates.

Read first: SPEC §2.2 (terms, section codes, the Fall 2026 seed map), §6.3
(configuration surface), §8, and **"What the built tickets settled" in [the epic
README](README.md)** — this ticket adds a model module, so its rules on
registering that module, importing `Base`, constraint naming, and the existing
database fixtures all apply.

One of them bites here specifically: `week` and `survey_window` are
timezone-bound (§3.1), so they carry server defaults or generated columns, and
`alembic check` is currently blind to server-default drift. See
[E0-20](E0-20-gate-fidelity.md) item 3 — if E0-05 has not already settled it,
settle it here.

## Scope

- Models in `backend/app/models/term.py`: `term`, `week`, `survey_window`,
  `start_letter_map`.
- `term` carries name, start and end dates, and institution timezone reference.
  `week` rows enumerate term weeks 1..N so the term axis (§2.2) is data, not
  arithmetic scattered through queries.
- `start_letter_map` is per-term: letter, length in weeks, start date. A letter
  is unique within a term. The Fall 2026 seed values from §2.2 are fixture data
  for tests, not hardcoded rows in a migration.
- `survey_window` models the weekly open and close, keyed to a section and a
  week, with timezone-aware timestamps. Columns exist and are constrained; the
  scheduling logic that fills them is E2.
- All timestamps timezone-aware. The `DTZ` ruff rules are already on; do not
  suppress them.

## Out of scope

- Section-code parsing and the derivation of section length, start, end, and
  modality (E0-07).
- Window scheduling — computing Friday 18:00 ET opens (E2).
- The admin UI for editing the calendar or the letter map (E11).
- Seeding a real Fall 2026 term (E0-17).

## Acceptance criteria

- [ ] `alembic upgrade head` creates the four tables; `alembic check` is clean.
- [ ] A duplicate start letter within one term is rejected by a unique
      constraint; the same letter in two different terms is accepted.
- [ ] `week` rows for a term are contiguous from 1 to the term length, enforced
      by constraint or by a tested invariant.
- [ ] A naive datetime cannot be written to any timestamp column — verify with a
      test that attempts it.
- [ ] A start-letter map row whose length exceeds its term's length is rejected.

## Definition of done

**Tests apply.** Unit tests for the constraints above. Integration tests for the
uniqueness and range rules, which live in Postgres.

**Docs do not apply** beyond model docstrings. The operator-facing calendar
editor is E11 and carries its own documentation.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review does not meaningfully apply** — this is configuration schema
with no read path, no identity, and no user input. Run `/security-review` per
`CLAUDE.md` and expect it to be clean; say so in the pull request rather than
inventing findings.
