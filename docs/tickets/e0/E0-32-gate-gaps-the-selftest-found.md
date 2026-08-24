# E0-32 — Three gate gaps the reviewer self-test found

**ID:** E0-32
**Branch:** `e0/gate-gaps-from-selftest`
**Depends on:** E0-10

## Status — where this ticket's items went

**Not built as written. All three items have moved**, and they did not move
together — item 1 is a pipeline script and items 2 and 3 are the same test
surface as a finding from another ticket.

| Item | Now |
|---|---|
| 1 — `check_invariants.py` cannot see a test that asserts nothing | [E0-36](E0-36-ci-gate-fidelity.md) item 3 |
| 2 — the identity-column guard only sees views a migration executed | [E0-34](E0-34-view-file-identity-guards.md) |
| 3 — the sweep that does fire invites a repair that leaves the leak | [E0-34](E0-34-view-file-identity-guards.md) |

E0-34 also carries [E0-27](E0-27-review-debt-from-e0-11.md) item 2, which is the
same directory reached from the grant model rather than from the gate. The two
tickets disagreed about whether building the guard was required or optional;
E0-34 resolves that in favour of building it.


## Context

`/review-selftest` was run over seven fixtures after E0-13, E0-16 and E0-17
merged. Every reviewer caught its planted defect and every declared secondary,
with no false positives — so this ticket is not about the reviewers.

It is about three things the reviewers found **on the way**, each a gate that
reports green while the thing it exists to detect is happening. They are E0-20's
subject arriving from a new direction: E0-20 collects gates blind to what they
claim to check, and these are three more.

None blocks the E0 exit. All three are cheap, and all three protect §4.1.

Read first: `docs/tickets/e0/E0-20-gate-fidelity.md`, SPEC §4 and §4.1,
[ADR 0001](../../adr/0001-identity-separation-by-database-role.md),
[ADR 0041](../../adr/0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md),
and `docs/MISTAKES.md` entries 2 and 3.

## Scope

### 1. `check_invariants.py` cannot see a test that asserts nothing

The §4.1 invariant gate treats a skip, an xfail and an empty collection as
failures, because in a green checkmark those are indistinguishable from a passing
assertion. It does not treat **a test that runs and asserts nothing** as a
failure, and that is indistinguishable too.

Found by `spec-conformance` against a fixture carrying an `invariant`-marked test
whose body ends after a call, with no assertion. It counts toward the "N invariant
test(s) ran, none skipped, none failed" the checker prints.

Done when: an `invariant`-marked test that executes no assertion fails the gate,
and a test asserts that it does.

### 2. The identity-column guard only sees views a migration has executed

`test_no_view_reads_a_column_the_identity_marker_names` reads `pg_depend` out of
the migrated database, so it can only see views that exist. `view_sql_files()` is
consumed by the file-presence check and the schema-qualification sweep, and
neither looks for identity columns.

So a file in `backend/app/views_sql/` that joins `user_identity` and selects a
name can sit in the canonical directory, pass the identity invariant **vacuously**,
and go live the day somebody appends its name to a `SCRIPTS` tuple in an unrelated
ticket. Found by `privacy-authz`, which then measured the second half:

### 3. The sweep that *does* fire invites a repair that leaves the leak

The same file is caught by
`test_every_relation_a_view_sql_file_names_is_schema_qualified` — but the failure
message is about `public.` prefixes. The invited repair is to add four prefixes,
after which the identity join and the `GRANT … TO pulse_app` are untouched and the
pipeline is green.

A red whose message points away from the defect is worse than no red, because it
spends the one moment somebody was looking.

Done when: a `views_sql/*.sql` file naming an identity column fails on that
ground, whether or not a migration has executed it, and the message says so.

## Out of scope

- Small-N suppression and the thresholds (E4).
- §4.1 item 1, which E0-10 defers to E2 on the record.
- The reviewer prompts themselves — they caught all seven fixtures.

## Acceptance criteria

- [ ] An `invariant`-marked test that asserts nothing fails the invariant gate.
- [ ] A `views_sql/*.sql` naming an identity column fails a test whose message
      names the identity column, whether or not the file is in a `SCRIPTS` tuple.
- [ ] Each new guard is verified by mutation: introduce the defect, watch the
      named test fail, restore. Say in the pull request which mutation was run
      for each — a guard added without that is the shape entry 2 records.
- [ ] No existing gate is weakened to make room for these.

## Definition of done

**Tests apply**, and they are the deliverable.

**Docs apply** only if a rule changes; otherwise none.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies.** All three guards protect §4.1, and the second is the
one route ADR 0001's grants cannot close.
