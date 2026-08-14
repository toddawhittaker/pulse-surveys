# E0-05 — Org containment schema

**ID:** E0-05
**Branch:** `e0/org-containment-schema`
**Depends on:** E0-04

## Context

Containment — Institution → College → Department → Prefix → Course → Section —
drives navigation and aggregation, and is one of the two decoupled structures in
§2.1. It is deliberately *not* where purview comes from; that is the supervision
graph in E0-09. Getting the separation right in the schema is what keeps the two
from quietly merging later.

Read first: SPEC §2.1 (containment, and the data-source ownership list), §8
(selected constraints), `CLAUDE.md` (roles and purview), and **"What the built
tickets settled" in [the epic README](README.md)** — this is the first ticket to
add a model module, so every rule in that section applies here first: registering
the module in `app/models/__init__.py`, importing `Base` from `app.models.base`
rather than `app.db`, leaving constraint names to the convention, and using the
fixtures `tests/conftest.py` already provides.

## Scope

**Settle one thing from E0-20 first.** `backend/migrations/env.py` sets
`compare_type=True` but not `compare_server_default`, which defaults to `False`,
so `alembic check` cannot see a server default that changed without a migration.
This ticket is where the first server defaults land, so it is where that blind
spot starts to cost something. Turn it on, or accept it knowingly and record why
in `env.py`'s docstring — the usual reason is false positives from Postgres
normalising `text()` defaults, which is real but should be written down rather
than rediscovered. [E0-20](E0-20-gate-fidelity.md) item 3 has the detail.

- Models in `backend/app/models/org.py`: `institution`, `college`, `department`,
  `prefix`, `course`, `section`.
- A department groups one or more prefixes; a course belongs to exactly one
  prefix; a section belongs to exactly one course and one term. Enforce each as
  a database constraint, not an application convention.
- Course `level` **derived from the course number**, stored as a generated or
  trigger-maintained column so it cannot drift from the number. SPEC §8 carries
  the bands and they are not restated here — `DEV`, `UG`, `UGGR`, `GR`, `DR`,
  with `800`–`999` and `1000`–`7999` rejected at write time. Two things about
  them are easy to get wrong: the number is **text**, because `MATH 040`'s
  leading zero is significant and an integer cannot hold it, so the derivation
  casts; and the bands mix widths, so a three-digit `850` is invalid while the
  four-digit `8500` is doctoral. The model docstring cites §8 rather than
  copying the table.
- Mark LMS-owned columns explicitly (courses, sections, section codes) so a
  later ticket cannot casually add an edit path. **The marker is an `lms_` name
  prefix** — `lms_number`, `lms_section_code` — chosen over a model-level
  marker because a name cannot be forgotten the way an `info` dict can, and it
  is visible at every call site rather than only at the definition. The cost is
  accepted: the prefix is noisy in queries, and a column that stops being
  LMS-owned needs a migration to rename it. See [ADR
  0014](../../adr/0014-lms-owned-columns-are-marked-by-a-name-prefix.md).

  Two boundaries of the rule, because both were guessed at once already.
  **`section.lms_section_code` is this ticket's column**, not E0-07's — E0-07
  derives length, dates and modality *from* it and creates nothing. And
  **`level` carries no prefix.** SPEC §2.1 lists course level among the
  LMS-owned facts, which is true of the value but not of the column: the LMS
  supplies the number, Pulse derives the level from it, and a generated column
  cannot be written by anyone at all — which is the thing the marker exists to
  prevent. Marking it would advertise a sync that does not happen.
- Migration with the constraint names from E0-04's convention.

## Out of scope

- `term`, `week`, `survey_window`, `start_letter_map` (E0-06); the section's
  term foreign key lands here but the table it points at arrives there — order
  the migrations accordingly, or introduce the term table stub in E0-06 and add
  the constraint then. Pick one and say which in the pull request.
- Section length, start date, end date, and modality derivation (E0-07).
- `person`, `enrollment`, `role_assignment` (E0-08, E0-09).
- Any API router or service — this is schema only.

## Acceptance criteria

- [ ] `alembic upgrade head` creates all six tables; `alembic check` is clean.
- [ ] A course reaches a department by exactly one path — through its prefix,
      via a non-nullable foreign key. Note that in a strict tree this criterion
      is met by construction and *no row can express* the violation, which is
      the stronger outcome and is what SPEC §8's "courses belong to exactly one
      prefix" asks for. It only becomes a live constraint if the schema names an
      ancestor twice (a `department_id` on `course`, say), and then the
      contradictory row must be refused by the database. Do not add the second
      reference in order to have something to constrain.
- [ ] Course level derives correctly for a table of representative course
      numbers spanning all five levels, and asserts both edges of every band —
      `099`/`100`, `499`/`500`, `599`/`600`, `799`, `8000`, `9999`.
- [ ] A course number in no band fails to insert: `800` and `999` at three
      digits, `1000` and `7999` at four, a four-digit number below `1000` such
      as `0099`, and a number that is not three or four digits at all.
- [ ] Every LMS-owned column this ticket creates carries the `lms_` prefix, and
      no Pulse-owned table carries the prefix, both asserted by walking
      `Base.metadata` rather than by reading the model. **This is narrower than
      "a later ticket that adds an unprefixed LMS column fails", and the wording
      is deliberate** — that property is not assertable from the metadata at
      all. Once a prefix is missing, nothing distinguishes an LMS-owned column
      from a Pulse-owned one, so the suite carries a trap-line of unprefixed
      spellings that must not appear beside the marked ones, which catches the
      regression and not the omission. [ADR
      0014](../../adr/0014-lms-owned-columns-are-marked-by-a-name-prefix.md)
      states the gap and [E0-21](E0-21-review-debt.md) carries what closes it.
- [ ] Course level cannot be set independently of the course number — an attempt
      either fails or is ignored in favor of the derived value.
- [ ] Deleting a department with prefixes attached fails rather than cascading.

## Definition of done

**Tests apply.** Unit tests for level derivation across the number ranges,
including boundaries. Integration tests for the containment constraints, since
they are enforced in Postgres and need a real database.

**Docs do not apply** beyond model docstrings — no operator-visible surface
changes.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies but is light.** Nothing here is user-facing. Worth
confirming that no LMS-owned column has a write path.
