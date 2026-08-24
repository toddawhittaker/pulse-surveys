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
timezone-bound (§3.1), so they carry server defaults or generated columns.
E0-05 settled the server-default half — `env.py` sets
`compare_server_default=True` on both paths, so a changed default with no
migration behind it now fails `alembic check`. The *generated column* half is
still open and is E0-05's finding: Alembic emits a warning and exits zero when a
generation expression drifts, so a `week` or `survey_window` column computed in
the database has no drift gate. See [E0-20](E0-20-gate-fidelity.md) item 3.

## Scope

- Models in `backend/app/models/term.py`: `term`, `week`, `survey_window`,
  `start_letter_map`.
- `term` carries name, start and end dates, **length in weeks**, and institution
  timezone reference. The length is stored rather than derived from the two
  dates: §2.2 states term lengths as institution configuration — 18 for fall and
  spring, 12 for summer — which is a value someone sets, and the spec never says
  whether `end_date` is inclusive or what a span that is not a whole number of
  weeks would mean. Both of the cross-row rules below compare against it, so
  deriving it would put two acceptance criteria on arithmetic the spec does not
  specify. If you want the length and the dates held consistent, a check
  constraint between them is the place; that is a judgment call, not a
  requirement of this ticket.
- `week` rows enumerate term weeks 1..N so the term axis (§2.2) is data, not
  arithmetic scattered through queries. **This ticket ships the function that
  produces those rows for a term**, because nothing else in E0 does and a
  contiguity rule with no producer has nothing to assert against. The database
  covers uniqueness over `(term_id, number)` and the range; contiguity — the set
  is exactly 1..N with no gaps — is not expressible as a row-level constraint in
  Postgres and is a tested invariant over the producer instead, which is the
  second of the two options the acceptance criterion already allows.
- `start_letter_map` is per-term: letter, length in weeks, start date. **The
  letter column is named `letter`.** It takes no `lms_` prefix — the marker E0-05
  established is for LMS-owned columns, and the letter map is admin-configured
  Pulse-owned configuration under §6.3. A letter is unique within a term. The
  Fall 2026 seed values from §2.2 are fixture data for tests, not hardcoded rows
  in a migration.
- `survey_window` models the weekly open and close, keyed to a section and a
  week, with timezone-aware timestamps. Columns exist and are constrained; the
  scheduling logic that fills them is E2.
- **`section.term_id` lands here**, non-nullable and referencing `term`, along
  with the uniqueness rule that needs it: a section code identifies a section
  within a course *and* term, so the constraint is over
  `(course_id, term_id, lms_section_code)` and could not be written before this
  ticket without forbidding the same code recurring next term. E0-05 chose this
  of the two orderings its scope offered — it created `section` with the course
  foreign key alone rather than ordering its own migration behind a `term` stub.
  SPEC §8's "sections belong to exactly one course and one term" is only half
  enforced until this lands.

  **Drop `ix_section_course_id` in the same migration, if — and only if — that
  constraint lands leading with `course_id`.** E0-05's review added that index
  because `section.course_id` was an unindexed foreign key. A composite unique
  index over `(course_id, term_id, lms_section_code)` already serves an equality
  lookup on `course_id` alone, measured, which is the same reasoning that leaves
  `college.institution_id`, `department.college_id` and `course.prefix_id`
  deliberately unindexed. Keeping both would cost a write on every section
  insert for no read benefit. If you order the constraint's columns differently,
  the index stays and this bullet is wrong rather than the index being
  redundant — check before deleting.
- All timestamps timezone-aware. The `DTZ` ruff rules are already on; do not
  suppress them.

**How the cross-table rule is enforced is yours to choose.** A letter's length
has to be compared against its term's, and a `CHECK` constraint cannot reach
another table, so this needs a trigger, a composite foreign key carrying the
term's length alongside `term_id` so the check becomes local, or something else.
That is a construction decision the spec does not answer and a reasonable
engineer might make differently, which is exactly the test `CLAUDE.md` sets for
an architecture decision record — write one in the same pull request. The
acceptance criterion above constrains the behaviour, not the mechanism.

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
- [ ] `week` rows for a term are contiguous from 1 to the term length. The
      database enforces uniqueness over `(term_id, number)` and the range; the
      no-gaps half is a tested invariant over the producer function this ticket
      ships, exercised across generated term lengths rather than one example.
- [ ] A naive datetime cannot be written to any timestamp column — verify with a
      test that attempts it.
- [ ] A start-letter map row whose length exceeds its term's length is rejected.
      A length that is invalid in general — 500 weeks — must not be what the test
      relies on, because a plain range check over §2.2's lengths would pass that
      test against a schema that never compares the row to its term. The case
      that isolates the rule is a length valid in general and too long for *this*
      term, such as a 15-week letter in a 12-week summer term.
- [ ] A section cannot be written without a term; a duplicate section code within
      one course and term is rejected; the same code recurs in a later term and
      in a sibling course of the same term without complaint.

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
