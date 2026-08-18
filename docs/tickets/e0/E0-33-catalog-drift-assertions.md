# E0-33 — Assert the database objects `alembic check` never looks at

**ID:** E0-33
**Branch:** `e0/catalog-drift-assertions`
**Depends on:** E0-08, E0-10

## Context

This is the first of the batch tickets. It carries three items that were written
as [E0-20](E0-20-gate-fidelity.md) items 3, 3a and 3b, and it exists because those
three have one fix and were being tracked as three.

`alembic check` compares `Base.metadata` against the database. `Base.metadata`
holds tables and columns. Everything else the schema depends on — a generated
column's expression, a check constraint's expression, an exclusion constraint,
a role, a grant, a view, a function and its owner — is outside the comparison in
both directions, and the gate reports clean while any of it drifts.

**The measurements are in E0-20 and are not repeated here.** Item 3's generated
column, item 3a's constraint table from E0-08, and item 3b's six-row mutation
table from E0-10 each record what was run, on which pinned version, with a
dropped column as the canary so that "clean" is distinguishable from a comparison
that has gone blind. Read them there.

**Why this batch is first.** Item 3b is not hardening. Two of its rows —
`GRANT SELECT ON public.user_identity TO pulse_app` and `ALTER ROLE pulse_care
SUPERUSER` — are each a single statement that voids the whole of SPEC §4.1's
confidentiality model, and `alembic check` calls both clean. Nothing in E0 issues
either one; the point is that nothing would notice if something did.

Read first: SPEC §4.1, [ADR 0001](../../adr/0001-identity-separation-by-database-role.md),
[ADR 0043](../../adr/0043-the-reveal-function-has-an-owner-of-its-own.md),
`docs/MISTAKES.md` entries 2 and 3, and `tests/integration/test_identity_grants.py`,
which is the pattern all three items generalise.

## Scope

The three items are one mechanism: **read the object out of the catalog and
compare it with what the migrations wrote.** Build it once.

### 1. Generated column expressions — E0-20 item 3's residue

Alembic has no `ALTER` to emit for a generated column, so `_compare_computed_default`
warns and `alembic check` exits zero. `course.level` is the only one today and
E0-05 spells its expression the way Postgres deparses it, so the warning fires
only on real drift — but a warning is not a gate.

Read `pg_get_expr` off the migrated database and compare it, normalised, with the
model's `Computed` text. One assertion, and it is the only drift signal a
generated column has.

### 2. Check-constraint expressions and exclusion constraints — E0-20 item 3a

Neither is compared. Both rules exist in the schema now: E0-08's enrollment
overlap rule *is* an exclusion constraint and its window-ordering rule *is* a
check constraint, and E0-06 shipped a check constraint that refused six of the
twenty positions in the spec's own seed map with every gate green.

`get_check_constraints`, and `pg_constraint` filtered to `contype = 'x'`.

### 3. Roles, grants, views and functions — E0-20 item 3b

The widest of the three. Two properties have no assertion anywhere today, and
they are the two this item owes:

- **The owner of every `SECURITY DEFINER` function in `public` is not a
  superuser.** E0-10 routed one; nothing re-reads it. Setting the reveal
  function's owner back to the migration superuser re-opens the escalation ADR
  0043 closes, and `alembic check` calls it clean.
- **The grant set is *exactly* what the migrations wrote, not a superset.** That
  is the shape a later ticket's convenience grant takes. Asserting a refusal
  proves the refusal; it does not prove that nothing else was granted.

The rest of E0-10's grant model is genuinely asserted by
`tests/integration/test_identity_grants.py`, three of whose tests are
`invariant`-marked. Extend that suite rather than replacing it.

## The trap, stated once for all three

**An object written into the migration that creates it reads like coverage and is
not.** Nothing re-reads it, in either direction. E0-20 names this under items 3a
and 3b separately; it is one rule and it is the reason this ticket cannot be
closed by pointing at a migration.

## Out of scope

- **The aggregate `CI` check and the drift job's own shape.** Those are E0-20
  items 1 and 2, now [E0-36](E0-36-ci-gate-fidelity.md). This ticket is about what
  the comparison can see, not about whether its result is reported.
- **View *files* that name an identity column.** That is
  [E0-34](E0-34-view-file-identity-guards.md), which reads the `views_sql/`
  directory rather than the catalog. The two are adjacent and should be built
  together; they are separate tickets because they read different things.
- Changing what any gate checks for. This ticket changes whether it can detect
  drift, not what counts as drift.

## Acceptance criteria

- [ ] A model whose *generated* column expression changed without a migration
      fails something.
- [ ] A model whose *check-constraint expression* changed without a migration
      fails something, and a *removed exclusion constraint* fails something.
- [ ] A database whose roles, grants, view set or function set drift from what
      the migrations wrote fails something — including the two properties named
      in item 3 that have no assertion today.
- [ ] Every one verified by mutation: reintroduce the defect, watch the named
      test fail, restore. Say in the pull request which mutation was run for
      each, and confirm the mutation landed before believing the red — a string
      edit that matches nothing exits zero.
- [ ] "It is in the creating migration" is not accepted as coverage for any of
      the three.
- [ ] No existing gate is weakened to make room for these.

## Definition of done

**Tests apply**, and they are the whole ticket.

**Docs apply** only if an item is answered with "deliberately not", in which case
the reason goes in the module docstring.

**AI evals do not apply. Accessibility does not apply.**

**Security review applies and is not light.** Item 3 is the assertion layer over
the confidentiality model itself.
