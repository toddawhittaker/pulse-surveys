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

The widest of the three.

**Corrected 2026-08-18, while building.** This item used to name two properties
as having "no assertion anywhere today" — that no `SECURITY DEFINER` function in
`public` is owned by a superuser, and that the definer's grants are exactly what
its job needs. **Both are asserted**, in the file this item says to extend:
`test_no_security_definer_function_is_owned_by_a_superuser` and
`test_the_reveal_functions_owner_holds_exactly_the_privileges_its_job_needs`, and
ADR 0043's closing paragraph records them landing. The claim was written from
E0-20 item 3b's text, which predates E0-10's later review round; E0-20 is
corrected in the same pull request.

This matters more than a stale sentence usually does. Both tests sit at module
scope, so a second `def` under a similar name **replaces** the first silently:
writing the two tests as this item asked would have deleted a live assertion
while reporting that it had added one. `docs/MISTAKES.md` entry 1 carries it as
an instance — before writing a test a ticket asks for, check what already
asserts it.

What is genuinely unasserted, and what this item therefore owes:

- **Who else is named in an ACL on anything in `public`.** The existing tests ask
  what the three roles in the scheme hold. None asks whether a *fourth* grantee
  exists, and a grant to a new role, or to `PUBLIC`, is invisible to all of them.
- **What the connection roles hold on a base table.** Exactness is asserted for
  the definer role and for `user_identity`; the runtime roles' privileges on
  every other base table are not, and that is the shape a later ticket's
  convenience grant takes. It has to be an equality rather than a lower bound,
  because a withheld verb is often the assertion — `SELECT, INSERT` on
  `classification` with `UPDATE` withheld is what makes SPEC §8's append-only
  rule a property of the database.
- **A role membership granted `WITH INHERIT FALSE`.** `has_table_privilege` and
  `pg_has_role(…, 'USAGE')` both follow the inheritance rule, so a non-inheriting
  membership in the definer role writes no ACL entry, appears in neither, and
  leaves `SELECT` on `user_identity` one `SET ROLE` away from the Care
  connection. Asked in `'MEMBER'` mode, it is visible.
- **The view set and the function set**, which no test compares against the files
  that create them in the file-to-catalog direction. Both are built. Where a
  *function's* SQL belongs is unsettled — SPEC §13 places view SQL under
  `views_sql/` and says nothing about functions — so the function half tolerates
  an empty expectation rather than pinning a decision no ticket has made, and
  says so where it is implemented.
- **A privilege held on a column rather than on a table.** Added 2026-08-18 from
  PR #40's review, and it is the sharpest entry here: a column grant is recorded
  in `pg_attribute.attacl`, which neither `has_table_privilege` nor
  `pg_class.relacl` reads, so `GRANT SELECT (identity_name) ON
  public.user_identity TO pulse_app` left `SELECT *` refused — every behavioural
  refusal green — while the connection behind every instructor screen read every
  student's name.

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
      the migrations wrote fails something — including each of the five
      genuinely-unasserted properties item 3 lists. (This criterion used to say
      "the two properties named in item 3 that have no assertion today"; both of
      those were already asserted. See item 3's correction note.)
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
