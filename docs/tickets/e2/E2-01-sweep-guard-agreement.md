# E2-01 — The `views_sql` exemption and the import guard name the same object

**ID:** E2-01
**Branch:** `e2/sweep-guard-agreement`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** the two sweeps guarded by this ticket are what keeps a
raw org read out of API handlers. Their disagreement is the carried finding.

## Context

The carried entry governs (`carried-from-e1.md`, "The `views_sql` package
exemption and the import guard disagree on their object"). The org-view SQL
sweep excuses any module under `backend/app/views_sql/` by containment, while
the one-importer sweep pins the literal name `app.views_sql.queries`. A second
module added to the package, holding a raw org read and imported from an API
handler, passes both halves in two individually legal steps. The re-review
reproduced this with a planted module.

**Deadline (Todd, 2026-08-31):** fixed before any second module lands under
`backend/app/views_sql/` and before E2's first read path behind the sweep —
which makes this ticket first in the build order, the same way E1-01 was.

Read first: the carried entry; ADR 0107 (its stated reason describes a guard
that does not exist as described); the sweep tests in
`tests/unit/test_the_org_views_are_read_only_through_the_grant.py` (the
exemption test, the org sweep at
`test_no_module_outside_the_sanctioned_locations_runs_sql_naming_a_policed_relation`,
and the one-importer sweep at
`test_no_module_outside_the_grant_chokepoint_imports_the_view_query_module`).

## Scope

- Make the exemption and the import guard name the same object. Two honest
  shapes; the builder picks one and the ADR-0107 correction records why:
  - narrow the containment exemption to the one module the import guard
    watches (`app/views_sql/queries.py`), so a second module in the package
    gets no exemption and fails the org sweep — the fail-closed shape;
  - or widen the import guard to the whole package.
  The first is the lean, because it fails closed on the module nobody has
  written yet (MISTAKES entry 35's lesson: a closed set must not be
  extendable by the thing it guards).
- Prove it with the re-review's own offender: the two-step planted module
  (new module under `views_sql/` with a raw org read, imported from a
  handler) goes red. Keep the plant as the test's negative control.
- Correct ADR 0107's sentence in the same PR (MISTAKES entry 1).
- The record fixes the carried low-findings block assigns to "whichever E2
  ticket next touches the org sweep" — this one:
  - the exempt files' statement pin compares relation names, not statements;
    make the pin match its docstring or the docstrings match the pin, and fix
    the count-only-plant docstring that claims a location assertion the
    assertion does not make;
  - `backend/app/services/authz.py`'s comment still says the sweep polices
    "the three org views" — make it count what the sweep polices (fourteen
    relations at the re-review).

## Acceptance criteria

1. The exemption and the import guard name the same object, and the choice is
   recorded in the corrected ADR 0107 text.
2. The planted two-step offender is red under the new rule and green when
   removed — both directions run, not argued (MISTAKES entries 3 and 9).
3. The statement-pin docstrings and the pin agree; the `authz.py` comment
   counts the policed relations.
4. The carried entry's done-when is met in full.

## Out of scope

- Any new view or student read path — E2-09's, and blocked on this ticket by
  the deadline.
- The `PERSON_TABLES` structural source (E13's; the standing per-epic review
  question applies to the tables E2-05 adds and is asked there).
