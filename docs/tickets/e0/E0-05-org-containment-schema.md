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
(selected constraints), `CLAUDE.md` (roles and purview).

## Scope

- Models in `backend/app/models/org.py`: `institution`, `college`, `department`,
  `prefix`, `course`, `section`.
- A department groups one or more prefixes; a course belongs to exactly one
  prefix; a section belongs to exactly one course and one term. Enforce each as
  a database constraint, not an application convention.
- Course `level` (UG / GR / DR) **derived from the course number**, stored as a
  generated or trigger-maintained column so it cannot drift from the number.
  Document the number-to-level rule in the model docstring.
- Mark LMS-owned columns explicitly (courses, sections, section codes) so a
  later ticket cannot casually add an edit path. A comment is not enough — add a
  model-level marker or a naming convention the authz layer can read.
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
- [ ] Inserting a course under a prefix in a different department's subtree
      fails at the database level.
- [ ] Course level derives correctly for a table of representative course
      numbers spanning UG, GR, and DR, including boundary numbers.
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
