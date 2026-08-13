# 0001 — Identity separation enforced by database role and grant

**Status:** Accepted — one consequence amended by
[ADR 0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
**Date:** 2026-08-12
**Tickets:** E0-08, E0-10, E0-11

> ADR 0009 sanctions a superuser identity for migrations and bootstrap, and
> supersedes the "roles are created in migrations" consequence below for the
> bootstrap and application roles. **The decision recorded here is unchanged,
> and so is the first consequence** — runtime roles must not own tables and must
> not be superuser. That is the rule ADR 0009 exists to protect, not to relax.

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
Putting the read and the audit write in one transaction means they cannot come
apart.

## Consequences

- **Runtime roles must not own tables and must not be superuser.** Both bypass
  grants entirely, which would make the whole scheme decorative. E0-10 tests
  this.
- **Deployment must provision three roles**, and migrations run as a different
  role than the application. This is new operational surface for whoever installs
  Pulse, and belongs in the operator documentation in E13.
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
  created by a migration. E0-10's read roles are still migrations.)*
- **If a deployment target cannot create roles** — some managed databases
  restrict it — the guarantee degrades to views that merely omit the columns.
  E0-10 requires documenting that fallback plainly rather than implying the
  stronger property.
