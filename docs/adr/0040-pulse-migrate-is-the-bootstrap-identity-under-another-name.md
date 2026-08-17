# 0040 — `pulse_migrate` is the bootstrap identity under another name, and is not created

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-10
**Amends:** [ADR 0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md) —
one row of its provisioning table, not its decision. Migrations still run as the
bootstrap superuser, and runtime roles still own nothing and are not superusers.

## Context

[ADR 0001](0001-identity-separation-by-database-role.md) names three database
roles: `pulse_migrate` owns the schema and runs Alembic, `pulse_app` serves
ordinary requests, `pulse_care` serves the Care queue. E0-10's scope repeats it
and asks for all three "established as migrations".

[ADR 0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md)
was written two tickets later and settles a question ADR 0001 did not reach:
migrations run as `DB_SUPERUSER`, the role `initdb` creates, because the identity
a migration runs as has to exist before the first migration and so cannot be
created by one. E0-04 wired that up and
[ADR 0012](0012-the-migration-environment-builds-its-own-superuser-connection.md)
records how the connection is assembled.

That leaves two records naming two different migration identities, and E0-10's
own "Reconcile first" section refuses to let it stand:

> **`pulse_migrate` needs reconciling with ADR 0009.** The scope below gives it
> schema ownership and the Alembic connection, but ADR 0009 decides that
> migrations run as the bootstrap superuser identity (`DB_SUPERUSER`), which is
> what E0-04 wires up. Either `pulse_migrate` *is* that identity under a
> different name in `.env`, or this ticket is reintroducing a separate
> non-superuser owner and ADR 0009 has to be amended in the same pull request
> rather than contradicted quietly.

## Decision

**`pulse_migrate` is ADR 0001's name for the migration identity, and that
identity is `DB_SUPERUSER`. No role called `pulse_migrate` is created.** E0-10's
migration establishes two roles, `pulse_app` and `pulse_care`, and runs as the
third.

Concretely:

* `backend/app/views_sql/identity_roles_v001.sql` creates and corrects the two
  runtime roles and mentions no third;
* the schema, every table, every view and the `SECURITY DEFINER` reveal function
  are owned by whichever role ran the migration, which ADR 0009 fixes as
  `DB_SUPERUSER` in every environment;
* `.env` gains no `DB_MIGRATE_USER`. The migration identity is already named
  there, twice, as `DB_SUPERUSER` and `DB_SUPERUSER_PASSWORD`.

**ADR 0001's requirement is met by this, not waived by it.** What that record
needs from `pulse_migrate` is that the schema's owner is not a role that serves
requests — because an owner holds every privilege on what it owns regardless of
any grant, so a runtime role that owned `user_identity` would make the whole
scheme decorative. That property holds: `pulse_app` and `pulse_care` own nothing
and are members of nothing, and `tests/integration/test_identity_grants.py`
asserts all three of those facts, including the membership one that no criterion
asked for.

## Alternatives rejected

**Create a real `pulse_migrate` and give it the schema.** The literal reading of
ADR 0001, and rejected on the circularity ADR 0009 identified: something still
has to create `pulse_migrate` and grant it `CREATE`, and that something is the
bootstrap superuser, which therefore still exists and still runs at least one
statement. So this buys no reduction in the number of privileged identities — it
adds a third credential to provision, a third row in ADR 0009's environment
table, and a second answer to "who owns this table" that every later migration
has to get right. ADR 0009 rejected the same option under the name "a
non-superuser migration role, owning the schema but not the cluster", called it
"genuinely better on paper", and put it at E13 with the operator guide. Nothing
E0-10 learned changes that; this record only stops the two documents disagreeing
in the meantime.

**Create `pulse_migrate` as an empty role so the name exists.** Rejected as the
worst of both: a role that owns nothing and runs nothing, which `\du` shows
beside two roles that do, and which the next reader has to work out is
decoration. A name that means nothing is worse than a name that is absent,
because it invites somebody to start using it.

**Say nothing and let the tests decide.** The test module's own comment notes
that `pulse_migrate` is "deliberately absent from the assertions below" precisely
because the ticket left it open, so the suite would have been green either way.
That is exactly the condition under which a decision goes unrecorded and is
re-litigated a year later.

## Consequences

**ADR 0009's provisioning table has one row that needed correcting**, and it
carries a pointer to this record: "E0-10's read roles — created by migrations,
unchanged" was written before this ticket knew that the two runtime roles need a
login credential a migration cannot hold. What the migration establishes is the
role, its attributes and its grants; what a deployment establishes is whether it
can authenticate and with what password. Those are different halves and they now
have different owners in every environment.

**A migration can create a role and cannot finish provisioning one.** The
statements in `identity_roles_v001.sql` deliberately never mention `LOGIN` or a
password: on a Compose volume `scripts/db-init` has already created `pulse_app`
with both, and an `ALTER ROLE … NOLOGIN` would take the running application's
connection away as a side effect of a migration. So a role created by the
migration alone — CI's drift job, a fresh testcontainer, a managed Postgres — is
`NOLOGIN` until somebody gives it a credential, and connecting as it fails with
an authentication error rather than with a silent fallback to another role. That
is the right failure, and it is the reason `tests/conftest.py` reaches these
roles with `SET ROLE` rather than by logging in.

**The bootstrap superuser is now load-bearing for confidentiality, not only for
DDL.** It owns the reveal function, so `SECURITY DEFINER` means *its* privileges;
it owns the views, so a view reads its sources with them. ADR 0009 already
records that keeping the application out of that role is enforced by a test
rather than by there being no superuser to reach, and this widens what that test
protects.

**If a deployment cannot use a superuser for migrations**, the fallback is the
E13 option above rather than this record: a non-superuser owner with `CREATE` on
the schema and `CREATEROLE`, running the same scripts. Nothing in
`views_sql/` assumes superuser specifically — it assumes the runner can create
roles, create objects and grant on them.
