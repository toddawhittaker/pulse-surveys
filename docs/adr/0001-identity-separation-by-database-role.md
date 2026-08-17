# 0001 — Identity separation enforced by database role and grant

**Status:** Accepted — one consequence amended by
[ADR 0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md),
`pulse_migrate` resolved by
[ADR 0040](0040-pulse-migrate-is-the-bootstrap-identity-under-another-name.md),
and **one claim withdrawn as measured false** during E0-10's review — the read
and the audit write were said to be inseparable, and a caller that rolls back
separates them.
**Date:** 2026-08-12
**Tickets:** E0-08, E0-10, E0-11

> ADR 0009 sanctions a superuser identity for migrations and bootstrap, and
> supersedes the "roles are created in migrations" consequence below for the
> bootstrap and application roles. **The decision recorded here is unchanged,
> and so is the first consequence** — runtime roles must not own tables and must
> not be superuser. That is the rule ADR 0009 exists to protect, not to relax.
>
> ADR 0040 settles the third name in the decision below: `pulse_migrate` **is**
> that bootstrap identity, and E0-10 creates no role by that name. What this
> record needs from it is that the schema's owner is not a role that serves
> requests, and that holds — `pulse_app` and `pulse_care` own nothing, are
> members of nothing, and E0-10 asserts all three.
>
> ADR 0043 adds one role this record does not name: `pulse_reveal_definer`, which
> owns the `SECURITY DEFINER` function in point 4 below and holds the three
> grants its body needs. It is not a fourth connection — it is `NOLOGIN` and has
> no credential — and it exists so that "runs with its owner's privileges" names
> a short list rather than a superuser.

## Context

[SPEC §8](../SPEC.md) requires that instructor and leadership read paths go
through views that *structurally cannot* join to identity columns, "enforced in
the database, not just the application," and that only the Care role can reach
identity, through an audited reveal. [§4.1](../SPEC.md) makes the resulting
visibility rules automated assertions rather than conventions.

The spec says what must be true. It does not say by what mechanism, and the
available mechanisms differ enough in cost and in failure mode that the choice
is not obvious. E0-08 and E0-10 cannot be built without settling it.

## Decision

Four things together:

1. **Identity lives in its own table.** `user` holds the key and platform
   reference; `user_identity` holds name and email.
2. **Three database roles.** `pulse_migrate` owns the schema and runs Alembic.
   `pulse_app` serves student, instructor, leadership, and admin requests with
   **no grant of any kind** on `user_identity`. `pulse_care` serves the Care
   queue.
3. **The connection pool is bound to the service module, not to the actor.**
   Only the Care service can obtain a `pulse_care` session, and it separately
   verifies a live `CARE` assignment.
4. **Care's only access is one `SECURITY DEFINER` function** that returns
   identity and writes the audit row in the same transaction. `pulse_care` has
   no direct `SELECT` on `user_identity`.

## Alternatives rejected

**Column-level grants on a single `user` table.** Keeps the schema simpler and
matches the table list in §8 literally. Rejected because a column grant
disappears silently when a table is recreated — a routine migration can void the
protection with nothing failing loudly. Table-level grants are coarser and
survive that.

**Application-layer enforcement only** — ORM guards, query helpers, a review
convention. Rejected because §8 names it insufficient in as many words, and
because it fails exactly the case the spec is worried about: a future careless
query written by someone who never read this file.

**Postgres row-level security.** Rejected as the wrong instrument. RLS filters
which *rows* a role sees; the requirement here is that identity *columns* be
unreachable. RLS would not stop `SELECT email FROM user_identity`.

**A separate identity service behind a network boundary.** The strongest
isolation available, and rejected on proportionality: this is a single-tenant,
self-hosted product (§1), and a second deployment unit adds an operational
burden and a new failure mode to every read path in exchange for a guarantee the
grant model already provides.

**Selecting the pool from the actor's role** rather than from the service.
Rejected because §2.1 permits one person to hold both a Care assignment and a
reporting assignment, which makes "the actor's role" ambiguous precisely where
being wrong is most expensive.

**Logging the reveal as a separate step** after reading identity. Rejected
because it makes the audit trail a convention that a future code path can skip.
Putting the read and the audit write in one transaction means the function
cannot return a name without having written the record first, and cannot keep a
record of a reveal that failed.

> **This paragraph used to end "means they cannot come apart", and that property
> was measured false.** The consequence below headed "one transaction does not
> make the reveal atomic against its caller" says what was measured. The
> alternative is still rejected, for the reason above — a separate step is a
> convention — but the transaction buys less than this record claimed, and the
> difference is the whole of E0-26 item 1.

## Consequences

- **Runtime roles must not own tables and must not be superuser.** Both bypass
  grants entirely, which would make the whole scheme decorative. E0-10 tests
  this.
- **Deployment must provision three roles**, and migrations run as a different
  role than the application. This is new operational surface for whoever installs
  Pulse, and belongs in the operator documentation in E13.
- **One transaction does not make the reveal atomic against its caller, and this
  record claimed it did.** What one transaction gives is real and is worth
  keeping: the audit row is written before the identity is read and in the same
  transaction, so an actor whose `INSERT` is refused never reaches the `SELECT`,
  and a failure inside the function discards both. What it does not give is
  atomicity against the caller. The rows have already been streamed to the client
  by the time the caller decides, so a session that deliberately rolls back keeps
  the name and discards the record. This was reproduced during E0-10's review on
  the pinned image, using the function's own SQL: `BEGIN; SELECT * FROM
  public.reveal_student_identity(<a real CARE person id>, <any user id>, NULL);
  ROLLBACK;` returns the real name and email address and leaves `audit_log` at
  zero rows, while the identical call without the `ROLLBACK` does write the row
  and a non-CARE actor is refused either way — so the rollback alone is the
  difference. plpgsql has no autonomous transaction, so closing this means
  writing the audit row over a second connection (dblink or a loopback foreign
  data wrapper), which is **E0-26 item 1**. Until then the record holds against
  everything except a caller that rolls back on purpose, and the credential that
  permits that is narrowed to the `api` process alone by the same pull request
  that corrects this record.
- **The audit table is on the write path of a safety-critical read.** If it is
  unwritable, the reveal fails. That is the correct trade — an unauditable reveal
  should not happen — but it makes the audit table's availability a Care-queue
  dependency.
- **Tests need a real Postgres**, not SQLite. Already true under §9.1, so no new
  cost.
- **Local development gets more setup**: roles are created in migrations so a
  fresh `docker compose up` still works in one command. *(Amended by ADR 0009:
  the bootstrap role comes from `initdb` and the application role from
  `scripts/db-init`, because the identity a migration runs as cannot itself be
  created by a migration. Amended again by ADR 0040, which found the same split
  inside E0-10's own roles: the migration creates each role and writes every
  grant, idempotently and in every environment, and `scripts/db-init` or the
  operator gives it a login, because a migration cannot hold a password without
  holding it in the repository.)*
- **If a deployment target cannot create roles** — some managed databases
  restrict it — the guarantee degrades to views that merely omit the columns.
  E0-10 requires documenting that fallback plainly rather than implying the
  stronger property.
