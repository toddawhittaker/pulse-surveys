# 0107 — The org-view sweep polices a catalog closure, with pinned exemptions

**Status:** Accepted
**Date:** 2026-08-28 (E1 boundary fix batch C; the safety.py ruling and the
scope ruling were made during this batch's review round)

## Context

The E1 boundary review (finding M8, `docs/tickets/e1/boundary-review.md`)
verified that the raw-SQL sweep guarding the §4.1 org views policed a
hand-written three-name list that omitted `section_roster`,
`section_enrollment_count`, and base `enrollment` — the three relations where
`pulse_app` holds table-grain SELECT and `ScopedReader` is the only
narrowing — and that the suite's own allow-list protected the bypassing query
shape. The spec says which reads must be denied (§4.1) but nothing about how
a sweep's inventory is built or what it may exempt. Every choice below is
contestable.

## Decision

- **The policed inventory is a catalog closure.** Parsed at runtime from
  `backend/app/views_sql/*.sql`: every `CREATE VIEW` name, plus every
  relation those view bodies read FROM or JOIN. No hand-written inventory
  exists; `enrollment` is policed because the roster views are built on it.
  As written this closes over fourteen relations, `course` and `section`
  among them, and the count moves with the catalog.
- **The breadth is deliberate.** A raw SQL read of any of the fourteen
  outside a sanctioned location is reported, even where the relation alone
  is not a §4.1 concern. When a legitimate such read appears, the answers
  are: move the read to a sanctioned location, or exempt it in its own
  reviewed commit with a statement pin. **The inventory is never narrowed**
  — the trim that looks smallest under pressure is how the sweep came to
  police three hand-written names in the first place.
- **Exemptions are locations, pinned to statements.** Four locations:
  `services/authz.py` and the `views_sql/` package (the chokepoint and its
  statement store — unpinned, because reading these relations is their whole
  job, and the one-importer sweep guards `views_sql` separately);
  `api/dev.py`, pinned to exactly `["section_enrollment_count"]` (ADR 0100);
  and `services/safety.py`, pinned to exactly `["role_assignment"]`. A
  pinned file's policed reads are asserted as an equality — the read must
  exist (a sweep must be able to see what it excuses) and nothing else may
  join it unseen.
- **The safety.py ruling.** The closed sweep's first real run caught
  `_HOLDS_A_LIVE_CARE_ASSIGNMENT` in `services/safety.py`. Ruled an
  exemption, not a defect: it is one of four deliberately co-named
  statements of the holds-Care rule (safety.py's own comment; MISTAKES
  entry 13), and it runs on the `pulse_care` credential — a grant function
  in `authz.py` would answer on the `pulse_app` connection, which is the
  wrong one for the Care service's revalidation.

## Alternatives rejected

- **Keeping a hand-written inventory** — the finding itself: a list the
  guarded structure can outgrow silently.
- **Deriving the inventory from `GRANT ... TO pulse_app`** — polices every
  ordinary product table the role can read and asserts a rule nobody agreed
  to; attempted in this batch and reversed.
- **Routing safety.py's check through `authz.py`** — puts the Care
  revalidation on the wrong credential, or forces `authz` to hold a second
  engine; the four-copies design already binds the statements together.
- **Whole-file exemptions without pins** — reviewed and rejected in this
  same batch: both pinnable files' stated reasons covered one statement
  each, and an unpinned file exempts whatever is added to it later.

## Consequences

- A new view or a view-body change re-derives the policed set with no edit
  to the sweep; a parse miss fails loud (the six-name premise and the
  planted offenders redden, not silently pass).
- The first legitimate raw read of `section` or `course` outside the four
  locations will red an invariant-marked test against correct code; the
  docstring names the two sanctioned answers so the remedy is not a
  shrunken inventory.
- `authz.py` and `views_sql/` remain unpinned by design; what they may
  contain is guarded by review and by the one-importer sweep, not by this
  file.
