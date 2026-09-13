# E4-14 — The nonce purge can run

**ID:** E4-14
**Branch:** `e4/nonce-purge-grant`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** entirely — it widens a runtime grant on the launch
replay ledger, and the carried entry says the decision half out loud: what
does a role that can enumerate spent nonces learn?

## Context

The carried defect, found by FIX-04's Celery drive and live since E1-08: the
beat task `app.jobs.tasks.purge_launch_nonces` fails every run with
`InsufficientPrivilege`, because
`backend/app/views_sql/lti_launch_nonce_grants_v001.sql` grants `pulse_app`
`INSERT, DELETE` and deliberately withholds `SELECT` — and Postgres requires
`SELECT` on the columns a `DELETE ... WHERE` reads. The purge deletes on
`expires_at`, so it is refused; the same task's `lti_launch_state` half
never runs because the nonce half raises first; the table grows without
bound while ADR 0089 says the purge exists to reclaim it. The launch path
itself is unaffected.

The carried entry names the shape of the fix and the shape of the decision:
a `GRANT SELECT` — column-scoped on `expires_at` being the narrow candidate
— plus a matching `RUNTIME_BASE_TABLE_PRIVILEGES` entry behind the test
wall, plus a recorded answer to why `SELECT` was withheld and what the
widening concedes.

Read first: the carried entry whole (it holds the measured evidence); ADR
0089; `backend/app/views_sql/lti_launch_nonce_grants_v001.sql` and the
`lti_launch_state` grants beside it; the privilege test that owns
`RUNTIME_BASE_TABLE_PRIVILEGES`.

## Scope

- The grant, as narrow as Postgres makes practical (the column-scoped
  `SELECT (expires_at)` is the recommendation — the purge's `WHERE` reads
  nothing else, and a role that can read expiry timestamps still cannot
  enumerate nonce values), in a v002 grants file and its migration (third
  chain slot; re-point at merge per the standing procedure).
- The privilege record updated to match, through the test wall's own
  process (the test-author owns `tests/**`; the battery proves the
  equality guard still bites).
- The purge driven to completion as `pulse_app` against a table holding
  expired rows — the task, not the SQL — per the entry's done-when.
- The why-withheld reasoning recorded: an ADR, since the spec is silent and
  the original withholding was itself a deliberate choice now being
  half-reversed.

## Acceptance criteria

1. The driven task completes: expired nonce rows gone, unexpired rows
   intact, and the `lti_launch_state` half now also runs — all three
   asserted from one drive.
2. The grant is exactly what the ADR says: the privilege-equality test
   holds the new tuple, and a mutation widening it (full-table `SELECT`, if
   column-scoped wins) is caught by the battery.
3. A negative stands beside the positive: `pulse_app` still cannot read the
   nonce value column — measured as the carried entry measured the refusal,
   with a direct query as the role.
4. The launch path's own behavior is untouched — `claim_nonce`'s tests
   still pass unmodified.
5. The carried entry closes with what closed it; the ADR records why
   `SELECT` was withheld originally and what this widening concedes.

## Known traps

- **Column-scoped grants have sharp edges** — verify the exact `DELETE ...
  WHERE` the task issues is satisfied by the column set granted; measure
  against the real task, not a hand-written approximation of its SQL (the
  entry's own evidence shows how).
- **The beat schedule means CI never sees this run** — the proof is a
  driven task in a test, not a green pipeline.
- **The state-table half hid behind the nonce half** — after the fix, both
  halves need their assertion; a test that only checks nonces would leave
  the second latent failure shape unwatched.

## Out of scope

- The launch `azp`/`aud` validation and the JWKS cache — carried items for
  epics that touch launch validation's logic; this ticket touches only the
  ledger's grant.
- Purge scheduling changes — ADR 0089's daily rhythm stands.
