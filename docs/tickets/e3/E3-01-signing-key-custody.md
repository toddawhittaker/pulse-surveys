# E3-01 — A deployment can supply and rotate the tool's signing key

**ID:** E3-01
**Branch:** `e3/signing-key-custody`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** yes, directly. This is private key custody. The key
signs every client-credentials assertion the tool sends to a platform, and
the published key set is what a platform verifies those assertions against.
The paths are heavy-lane rows in their own right — `scripts/db-init/`,
`scripts/seed.py`, `backend/app/models/lti.py`, and the tool signing key's
grant SQL under `backend/app/views_sql/`.

## Context

Carried from E2: "A non-development deployment has no way to supply the
tool's signing key" (`carried-from-e2.md`), which came in turn from
`docs/tickets/e1/deferred.md`, E1-05 item 1. ADR 0082 records the custody
decision as it stands: the key lives in a database row, and the only writer
of that row is the development seed. A deployment that holds no row answers
503 at `/lti/jwks`, which is loud and correct as far as it goes — it just
leaves no path to a key that is not the seed's.

Rotation is the second half and the harder one. A key rotation needs a period
in which the published key set carries both the retiring key and its
replacement, so that assertions signed before the switch still verify while
assertions signed after it verify too. The current one-row rule structurally
forbids that overlap: there is nowhere to put the second key.

This ticket is first in the epic for a reason that is not dependency —
E3 is the first epic that registers a real platform, which is what makes the
carried entry E3's, and the work is entirely orthogonal to grades. It can
land at any point in the epic without blocking anything.

Read first: ADR 0082; `carried-from-e2.md`, the signing-key entry;
`docs/tickets/e1/deferred.md` E1-05 item 1 for the done-when that governs;
the tool signing key model and its grant SQL; SPEC §7.3.

## Scope

- A supply path for a deployment that is not development. Whatever the shape,
  it is a path an operator can execute without a seed script and without a
  hand-written `psql`, and it does not weaken the rule that the application
  role cannot write the table.
- The rotation shape: a published key set carrying more than one key, `kid`
  selection at signing time so a verifier can tell which key signed what, and
  a retirement step that removes a key from the set once nothing signs with
  it. The one-row constraint changes or an ADR says why it should not.
- The refusal stays loud. A deployment holding no usable key still fails at
  `/lti/jwks` with a sentence rather than serving an empty key set, and a
  test drives that case.
- **Or a written ruling that moves the item to E13's deployment pass.** The
  carried entry names E3 as owner, so a ruling is owed either way; if the
  supply path genuinely belongs with the rest of the deployment work, this
  ticket produces the ADR that says so and the entry that hands it on, and
  nothing else. *Not taken*: the supply path and the rotation rule were both
  built here, so the carried entry is closed rather than passed on.

## Acceptance criteria

1. A key can be supplied to a deployment by a documented operator path that
   the development seed does not participate in, or an ADR rules the item to
   E13 and this ticket ships that ADR and the carried entry instead.
2. The published key set can carry two keys at once, and a signature made
   with either verifies against it — both directions asserted, not one.
3. `kid` is present on signed assertions and selects the key at verification;
   a signature made with a retired key is refused after retirement, and the
   test plants that case rather than reasoning about it.
4. A deployment with no usable key still answers 503 at `/lti/jwks` with an
   actionable sentence, and the application role still holds no write on the
   key table.
5. ADR 0082 is amended or superseded in this pull request, and the carried
   entry is closed with what closed it, on the entry where it lives —
   `carried-from-e2.md`, which is where this epic's inherited work is recorded.
   *Corrected at build time*: this criterion said `carried-from-e3.md`, which is
   the hand-off note E3's exit ticket writes for E4 (E3-08) and does not exist
   while this ticket is being built. A closure belongs beside the entry it
   closes, and writing it into a file a later ticket creates would have hidden it
   from anyone reading the entry.

## Decisions this ticket settles

- **Where a non-development key comes from.** ADR 0082 decided the storage;
  this decides the supply. The alternatives worth naming in the ADR are an
  environment-supplied key read at startup, an operator command that writes
  the row under a privileged role, and an external key service — the last of
  which is almost certainly out of proportion for the pilot and should be
  rejected in one line rather than surveyed.
- **The rotation overlap rule**, as a new ADR: how many keys the set may
  carry, what selects the signing key, and what retires one.

## Known traps

- **The one-row rule is what makes today's guarantees provable**, so widening
  it widens whatever rests on it. Before changing the constraint, grep for
  what asserts the single row — a test, a grant, an ADR sentence — and move
  every one of them in the same change (`docs/MISTAKES.md` entry 1).
- **A key set with two keys is a place for a stale key to live forever.**
  Retirement has to be executable, not merely describable, or rotation ships
  as a way to accumulate keys.
- **Do not print, echo, or commit a key.** The development key is a
  development key and still nothing is pasted into a pull request body, a
  fixture, or a log line.

## Out of scope

- The deployment environment itself, its secret store, and its TLS — E13.
- Registering a real platform. E3 meets the mock; the carried entry's
  reasoning is that E3 is the epic where a real registration *becomes*
  possible, not that one happens here.
