# 0043 — The reveal function has an owner of its own, holding three grants

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-10, E10
**Relates to:** [ADR 0040](0040-pulse-migrate-is-the-bootstrap-identity-under-another-name.md),
which counts the roles this ticket creates, and
[ADR 0042](0042-the-care-pool-has-its-own-credential-and-opens-on-first-use.md),
which decides who may call this function.

## Context

`public.reveal_student_identity` is `SECURITY DEFINER`, which is the whole of how
[ADR 0001](0001-identity-separation-by-database-role.md)'s scheme works:
`pulse_care` holds no privilege on `public.user_identity`, so the only way it
obtains a name is through a function that runs with **its owner's** privileges
and writes an audit row in the same transaction.

Nothing in the first implementation set that owner. A function is owned by
whoever created it, and every object here is created by `alembic upgrade head`,
which [ADR 0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
fixes as `DB_SUPERUSER` — the cluster superuser. So the one deliberate hole in
the wall was executing its body as a superuser, where the body needs three
grants.

**Measured rather than argued**, on the pinned image, because "it runs as
superuser" and "that reaches something" are different claims. A probe function
created by the same migration and granted to `pulse_care` returned
`pulse_admin read pg_authid rows=18` — every role in the cluster and its password
verifier — to a caller that is refused `pg_catalog.pg_authid` directly one
statement later.

The body itself is static SQL with three typed parameters, no dynamic statement,
a fixed `search_path` and every relation schema-qualified, so there is no
reachable path from a caller to that privilege today. "No reachable path today"
is a property of the current text of one function, and this is the object in the
system where a future one-line edit costs the most.

## Decision

**A dedicated owner, `pulse_reveal_definer`, holding exactly what the body does
and nothing else.** Created by the same idempotent script as the two connection
roles, `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOLOGIN`,
granted:

* `SELECT` on `public.role_assignment` — the actor's live `CARE` assignment;
* `INSERT` on `public.audit_log` — the record;
* `SELECT` on `public.user_identity` — the name.

and then `ALTER FUNCTION public.reveal_student_identity(uuid, uuid, uuid) OWNER
TO pulse_reveal_definer`.

**It is not a connection role, and three things say so.** It is `NOLOGIN`; no
mechanism in this repository gives it a password — no `.env` entry, no
`scripts/db-init` step, nothing for an operator to do; and it is deliberately
absent from the `GRANT CONNECT` beside it, which would give it nothing it could
use. Nobody is a member of it.

**The views keep the migration identity as their owner**, and the asymmetry is
the decision rather than an oversight. A view is a stored `SELECT` and can only
ever read; a `plpgsql` body is code executed at request time, so the same
superuser ownership means "a Care request can, after one added line, do anything
a superuser can", which includes `COPY … FROM PROGRAM` — command execution in
the database container, the finding E0-02's security review made and ADR 0009
exists to confine to migrations. Giving the views scoped owners is a coherent
next step and is proposed rather than done; see the Consequences.

## Alternatives rejected

**Leave the owner as the migration identity and rely on the four controls in the
function's header.** Defensible, and it was the other half of a genuine choice:
ADR 0009 already sanctions the superuser for everything a migration makes, a
fourth role is another thing to explain, and the static body is what actually
bounds the privilege today. Rejected on what the two options do on the day
somebody adds a line. As the migration identity, an added `SELECT` against any
table in the cluster **succeeds**, silently, with the extra privilege spent at
request time on behalf of a Care staffer. Owned by this role it **fails**, at the
first call, with `permission denied` naming the table — measured both ways, with
the same probe. That converts a review-time risk into a run-time error, which is
this codebase's stated preference (`CLAUDE.md`: fail loudly and early), and it
costs one `CREATE ROLE` in a script that already creates two.

**Own the function with `pulse_care`.** No new role at all, and it is the first
thing anybody suggests. Rejected because it destroys the guarantee it is meant to
serve: the owner needs `SELECT` on `public.user_identity`, so `pulse_care` would
hold it directly, and "a name cannot be obtained without leaving a record" would
be false in one statement. E0-10 has a criterion whose whole subject is that
`pulse_care` cannot read that table.

**Drop `SECURITY DEFINER` and grant `pulse_care` the three privileges directly.**
Simplest of all, no owner question, and it is the design ADR 0001 rejected in as
many words: the audit trail becomes a convention that a future code path can
skip, because reading the table and writing the record are then two things a
caller does in whatever order it likes, or does not.

**Reuse `pulse_migrate`** — the name ADR 0040 declined to create — as a
non-superuser owner of the whole schema. That is ADR 0009's "non-superuser
migration role" option, still the right thing to revisit at E13 with the operator
guide, and still rejected here for the reason 0040 gives: it does not remove the
bootstrap role, so it buys a third credential and a third provisioning step. This
record's role is a different animal precisely because it needs neither — it
never connects.

**Set `ALTER DEFAULT PRIVILEGES` or an event trigger so that any future
`SECURITY DEFINER` function gets a scoped owner automatically.** Rejected as
action at a distance: it changes what every later migration means without that
migration saying anything, and the class is already policed by
`test_the_application_role_may_not_execute_the_reveal_function`, which fails on
any definer function the application role can call.

## Consequences

**What this does not protect against**, stated because a control whose limits are
unstated gets read as a wider one:

- **A migration that grants the role more.** The three grants are a budget, and
  the fail-closed property lasts exactly as long as nobody adds a grant beside
  the line that needed it. `alembic check` reads no grants, so nothing detects
  it; line-by-line review of `views_sql/` is what stands there, and it is the
  reason the ticket asks for that review by name.
- **A body change within the three grants.** The function could be edited to
  return every row of `user_identity` and would still write exactly one audit
  row: the record says an access happened, not what was read. E10 owns making the
  reveal case-shaped; today it takes a single subject key and that is the bound.
- **A compromised migration identity.** `DB_SUPERUSER` still exists, still owns
  the schema, and can grant itself anything. This narrows the privilege the
  *runtime* path spends, not the privilege the build path holds.
- **The views.** They are still owned by the migration identity, so a view added
  later reads its sources as a superuser and a mistake there is caught by the
  marker sweep and the §4.1 tests rather than by a grant. Giving each view a
  scoped owner is the same idea one step further and is worth doing when there
  are more of them; it costs a grant per base table per view, which is why it is
  not done for two.

**A fourth role exists in `\du` and in none of the configuration.** That is the
point, and it is also the thing an operator will ask about: it has no password
because nothing should ever authenticate as it, and E13's operator guide owes it
a line beside ADR 0001's degradation note. ADR 0040's sentence "E0-10's migration
establishes two roles" is amended by this record rather than left to disagree.

**The downgrade revokes what the drop cannot.** Privileges on the function vanish
with the function; the definer's grants on `user_identity` and `role_assignment`
outlive the revision, so the downgrade removes them by hand. A downgraded
database is left with an inert `NOLOGIN` role holding nothing, which is checked
rather than assumed.

**Nothing asserts the ownership yet.** The suite has no test that
`reveal_student_identity` is owned by a non-superuser holding exactly three
privileges, so this is behaviour shipped with nothing asserting it
(`docs/MISTAKES.md` entry 2) until one is written — the implementer does not
write tests in this loop, and it has been routed. The two properties worth
asserting are that the owner of every `SECURITY DEFINER` function in `public` is
not a superuser, and that its privilege set on the tables its body names is
exactly the three above; the first is the one that survives E10 replacing the
function.
