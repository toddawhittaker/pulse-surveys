# E2-03 — The registration restore refuses with a sentence, and a docstring stops citing a struck precedent

**ID:** E2-03
**Branch:** `e2/migration-restore-refusal`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** low — migrations path, but the change is an error
message and a docstring; no schema shape moves.

## Context

Two low findings from the carried block, named "same file family, one ticket"
there:

- Downgrade below `b8c41f7d2e05`, delete the registration, upgrade back: the
  restore hands the foreign key a dead deployment and the operator gets a raw
  constraint violation instead of the migration's usual actionable refusal.
  It fails closed today (the transaction rolls back, the preserved rows
  survive for a retry) — the defect is the message, not the outcome.
- `tests/integration/test_the_section_binding_survives_a_downgrade.py` cites
  `e2c94b6a1f70` as a preserve/restore precedent that the boundary record
  corrections in the same merge struck as false (MISTAKES entry 1's shape).

Read first: both carried bullets; the migration at `b8c41f7d2e05` and the
test file; the consolidated re-review comment on PR #123 (findings with
file-and-line evidence).

## Scope

- The restore path detects the dead-reference case before the constraint does
  and refuses with a sentence naming the preserved table and what the
  operator should do — matching the actionable-refusal convention the other
  migrations in the family already follow.
- The test docstring names no precedent the record has struck; the test keeps
  asserting what it asserts.
- A test drives the exact sequence (downgrade, delete, upgrade) and asserts
  the refusal text names the preserved table — the raw-violation shape is the
  red case (MISTAKES entry 3: watch it fail).

## Acceptance criteria

1. The downgrade–delete–upgrade sequence refuses with a sentence naming the
   preserved table; the preserved rows still survive for a retry.
2. The docstring correction is in, and a grep for `e2c94b6a1f70` in
   `tests/` finds no claim the record struck.
3. Both carried bullets' done-whens are met.

## Out of scope

- Any behavioral change to what is preserved or restored — the fail-closed
  outcome is correct and stays.
