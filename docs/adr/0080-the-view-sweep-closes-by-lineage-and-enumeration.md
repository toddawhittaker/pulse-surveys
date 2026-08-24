# 0080 — The view sweep closes by table lineage and a hand-written column enumeration

**Status:** accepted (E1-01)

## Context

The reviewer self-test measured two blind spots in the §4.1 view sweep, recorded
in `docs/tickets/e1/carried-from-e0.md`: an identity column reaches a view under
an alias the marker convention cannot see, and `user.lms_user_id` — a stable
per-person key an instructor can resolve in the LMS in one step — is flagged by
nothing, because `lms_` is ADR 0014's ownership marker rather than an identity
marker. The carried entry fixes the direction (lineage and enumeration, not a
longer fragment list) but not the mechanism. SPEC §4.1 and §8 require the
guarantee and are silent on how a test detects a breach.

## Decision

Three closures, all in the existing identity test modules, none in production
code:

1. **Strict table rule.** A view may not read any column of a person table
   (`user`, `user_identity`, `person`) except the join keys `id`, `user_id`,
   `lti_platform_id` — whatever the column is called, and whether or not it
   carries the identity marker. Applied twice: as a fourth file-side sweep
   mechanism that resolves table aliases before reading column references, and
   as a widened catalog-side check over `pg_depend`.
2. **Chains resolve coarsely.** A view depending on any column of another view
   inherits that view's flagged findings, to a fixed point. A view reading only
   the safe columns of a partly-flagged view is still flagged; failing closed is
   the chosen direction, and no legitimate view-on-view exists to be wrongly
   refused.
3. **The `pulse_app` column enumeration is hand-written in the test.** The
   candidate set — every view column the role can actually read — comes from the
   catalog (`aclexplode` over `relacl` and `attacl`), which the guarded
   structure cannot shrink. The expected set is written out by hand from the
   record, following `RUNTIME_BASE_TABLE_PRIVILEGES`'s precedent, and compared
   for exact equality in both directions. Base tables stay under the existing
   table-grain equality test; this enumeration covers views only.

## Alternatives rejected

- **A longer `IDENTITY_NAME_FRAGMENTS` list.** The carried entry forbids it by
  name: the label is the view author's choice, so a label-matching guard can
  always be aliased around.
- **Column-level `GRANT SELECT (…)` in the database.** Stronger in principle —
  the database itself would refuse the read — but it moves the enumeration into
  the grant files, which is exactly where `docs/MISTAKES.md` entry 19 says an
  expectation goes blind (the test would read its answer from the thing it
  checks), and it makes every future view column a migration. The test-level
  enumeration keeps the review moment without the churn.
- **A SQL parser for precise file-side lineage.** Column-precise chain tracing
  through view definitions needs a real parser; a dependency for it buys
  precision the coarse rule does not need, since the base view in any chain is
  always flagged directly.

## Consequences

- A future view that legitimately needs a person-table column (say
  `person.category`) goes red until the allowed set is widened in a reviewed
  one-line change. That is the intended review moment.
- Every future ticket that grants `pulse_app` a view, or adds a column to a
  granted view, must extend the hand-written enumeration in the same change —
  the failure message says so.
- The catalog-side chain rule can over-flag a view reading only safe columns of
  a flagged view. The repair for a false positive is restructuring the view to
  read base tables, not weakening the fold.
