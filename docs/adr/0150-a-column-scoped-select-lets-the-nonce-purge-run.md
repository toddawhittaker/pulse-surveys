# 0150 — A column-scoped `SELECT` lets the nonce purge run

**Status:** Accepted
**Date:** 2026-09-06
**Tickets:** [E4-14](../tickets/e4/E4-14-nonce-purge-grant.md)

## Context

`docs/tickets/e4/carried-from-e3.md` carries a defect found by FIX-04's Celery
drive on 2026-09-06 and live since E1-08 shipped `lti_launch_nonce` on
2026-08-26. `app.jobs.tasks.purge_launch_nonces` — the daily beat task ADR
0089 gives the ledger in place of a TTL Redis would have supplied — raises
`psycopg.errors.InsufficientPrivilege` on every run. The cause is a deliberate
choice, not a bug: `lti_launch_nonce_grants_v001.sql` grants `pulse_app`
`INSERT` and `DELETE` on the table and withholds `SELECT` outright, because
ADR 0089 reasoned that nothing needs to read the ledger back — `claim_nonce`
spends a nonce with a plain `INSERT` and reads single-use off the unique
index's conflict, never a query. That reasoning held for the claim and missed
the purge: `purge_expired_nonces` deletes on `expires_at`
(`DELETE ... WHERE expires_at < now()`), and Postgres requires `SELECT` on
every column a `DELETE`'s `WHERE` clause reads, whether or not the statement's
own author ever calls it a read. The table has grown without a reclaimed tail
for as long as it has existed, and because `purge_launch_nonces` shares one
`SessionLocal` across both launch tables, `lti_launch_state`'s own expired
tail has never been reclaimed either — its half of the task never runs, since
the nonce half always raises first.

SPEC §9.1 requires replay-proof, single-use nonces and says nothing about how
their storage is queried; the withholding of `SELECT` in E1-08 was itself a
deliberate, spec-silent choice about what a connection able to read the
ledger would learn. Widening it — even by one column — is the same kind of
choice, made by a reasonable engineer differently than the original one, so it
is recorded here rather than folded silently into the fix.

## Decision

**Grant `pulse_app` `SELECT (expires_at)` on `public.lti_launch_nonce`, and
nothing wider.** `lti_launch_nonce_grants_v002.sql` adds exactly this column;
`lti_launch_nonce_grants_v001.sql`'s own `GRANT INSERT, DELETE` line is
untouched, per ADR 0041 — a file a shipped revision already executed stays
byte-identical, and the narrowing lives in the new file instead.

**Why `SELECT` was withheld entirely in E1-08, restated so this record does
not read as reversing that one without saying why it was right.** `nonce` is
a one-time credential: the whole property the ledger exists to provide is
that nothing but the row that first claimed a value ever reads it back. A
connection able to `SELECT` the column can enumerate every nonce this
deployment has ever spent, and from that, which launches happened and
roughly when — a fact the launch protocol itself keeps opaque to everyone but
the platform and the tool. Withholding `SELECT` outright cost nothing at the
time, because the only caller, `claim_nonce`, never needed it.

**What this widening concedes, exactly.** `pulse_app` can now read every
row's `expires_at` and, by extension, count how many nonces are outstanding
and roughly how the ledger's tail is shaped over time — a coarser signal than
enumerating the values themselves, and one that names no specific launch.
`pulse_app` still cannot read `nonce` itself: the negative half of
`RUNTIME_COLUMN_PRIVILEGES`'s proof
(`test_the_application_role_may_read_the_nonce_ledgers_expiry_and_not_its_nonce`)
measures exactly that, as a direct refused query beside the permitted one, in
the same transaction and the same role, so neither can be explained by a role
that holds nothing at all. `INSERT` and `DELETE` are unchanged from E1-08;
`UPDATE` stays withheld for the reason it always was — a spent nonce is never
rewritten, and a role that could rewrite `expires_at` could keep a replay
window open past its intended life.

## Alternatives rejected

- **Full-table `SELECT` on `lti_launch_nonce`.** Concedes the ledger's whole
  value column for a task that reads one other column. The purge's own
  `WHERE` never touches `nonce`, so the wider grant buys nothing the narrower
  one does not already provide, at the cost this decision exists to avoid.
- **A `SECURITY DEFINER` purge function**, owned the way the identity-reveal
  path is (SPEC §4.1, §8). That mechanism exists in this codebase for reads
  that cross an identity boundary a view or a grant cannot express safely —
  reading a student's name for an audited Care reveal, for instance. A
  column-scoped grant already says everything this case needs to say, at a
  fraction of the moving parts; reaching for a definer function here would be
  the same shape of over-build the identity-separation rule exists to
  prevent from spreading to cases that do not need it.
- **Deleting on a schedule with no `WHERE`** — the carried entry's own
  measured near miss: `DELETE FROM lti_launch_nonce` with no `WHERE` is
  permitted today, because `pulse_app` already holds table-wide `DELETE`.
  That would let the purge "succeed" without any new grant, and it would
  destroy every unexpired nonce along with the expired ones — defeating
  SPEC §9.1's single-use guarantee for any launch still in flight. Rejected
  outright; not a real candidate, but the shape this decision is written
  against.

## Consequences

- The daily beat entry completes both halves: `lti_launch_nonce`'s expired
  tail and `lti_launch_state`'s expired tail are both reclaimed, proven by
  driving the task as `pulse_app`
  (`tests/integration/test_the_launch_replay_purge_runs_as_pulse_app.py`)
  rather than by reading the grant or approximating its SQL by hand — the
  beat schedule itself is never exercised in CI, so this is the only proof
  that exists.
- `RUNTIME_COLUMN_PRIVILEGES` in `tests/integration/test_identity_grants.py`
  carries one new entry,
  `(APPLICATION_ROLE, "lti_launch_nonce", "expires_at", "SELECT")`, and the
  module's equality test over the live database's ACLs is what keeps a later
  widening — table-wide, or a grant on `nonce` itself — from landing silently.
- The launch path itself is unchanged: `claim_nonce`'s `INSERT` and its
  single-use guarantee do not depend on any `SELECT`, and its own tests pass
  unmodified.
- `lti_launch_nonce_grants_v001.sql` carries a dated note pointing here
  rather than a rewrite, per ADR 0041's rule that a file a shipped revision
  already executed stays exactly as it was applied.
