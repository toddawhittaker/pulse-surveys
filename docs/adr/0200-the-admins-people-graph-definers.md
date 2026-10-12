# 0200 — The admin writes the people graph through admin-checked definers, and the audit row is the control

**Status:** Accepted
**Date:** 2026-10-12
**Ticket:** [E9-02](../tickets/e9/E9-02-admin-gate-and-people-graph-writes.md)

## Context

SPEC §6.3 puts the People & reporting editor and the Lead Faculty mapping table
in the admin console. SPEC §6.2 (the E9 owner's ruling 1) makes every Pulse-owned
role grantable to anyone, Care and Admin included, the acting admin included,
with every grant and revocation audited. §6.3 says revoking an assignment
deletes it. Until now `pulse_app` held no write on `person`, `role_assignment`,
`lead_faculty_mapping` or `web_login_subject`; the seed wrote them, and a web
login was linked by hand ([ADR 0097](0097-the-identity-a-verified-subject-resolves-to.md)).
The spec does not say how the writes reach the database.

## Decision

**Twelve `SECURITY DEFINER` functions in `views_sql/people_graph_v001.sql`**,
owned by the NOLOGIN `pulse_people_graph_definer` (ADR 0043's one owner per door,
ADR 0191's definer pattern), with `EXECUTE` for `pulse_app` and nothing else on
the four tables. Nine write: create and edit a person, grant and revoke an
assignment, set or clear its `reports_to`, map and unmap a course's lead, link
and unlink a web login. Three read people, assignments and mappings, and answer
no `person.user_id`, no `idp_subject` and no `user_identity` column. Each takes
the acting admin's person key first and checks that it holds a live `ADMIN`
assignment. A refused read answers zero rows. A refused write raises SQLSTATE
P0001 whose message is a key in `app/copy/admin_people.py`.

**`pulse_app` passes the acting admin's key, so the database's admin check is
only as good as the route, and the route is the real check.** The database
cannot tell whether the key is the session's own. The definers stop a write that
bypasses them and a write naming a non-admin key, and nothing more. The real
check is `require_admin` in `api/deps.py`, with the key taken from the verified
session only (E9-06 done-when 13).

**No code refuses a Care, Admin or self-targeted grant.** `INSTRUCTOR` is refused
(teaching grants are the roster sync's), and so is an edge whose child is one.
**Every grant, revocation, edge change, mapping change and linkage change writes
one `audit_log` row in the same call, with no exception handler around the
insert**, so a write whose row cannot be written is rolled back. The row names
the action, the acting admin, the person written about (`subject_person_id`, new)
and, for an assignment or a mapping, the role and scope node (`role` and
`scope_node_id`, new). An edge row also names the new parent
(`parent_assignment_id`, new, no foreign key because the parent may be revoked
later; NULL for a clear and on every other action, by a check). A linkage row
carries, as `role`, the privilege the linked person holds when it is written:
`CARE`, else `ADMIN`, else NULL. So a login linked to a Care holder reads as
reaching Care. `subject_user_id` became nullable, and two two-way checks hold the
two shapes: a row names a student exactly when it is a reveal, and names a person
exactly when it is not. `subject_person_id` has a foreign key and no index; an
index arrives with the first read that needs one. Creating and editing a person
record is not audited.

**Revoking deletes.** The existing `RESTRICT` on `reports_to` refuses to delete an
assignment others report to, and the definer turns that refusal into a named one
carrying the children's count.

**Catching `check_violation` in the edge write also catches ADR 0044's
REPEATABLE READ refusal.** That refusal is reported as `edge_does_not_climb`.
The application sets no isolation level, so it runs at PostgreSQL's default,
READ COMMITTED, and this is accepted rather than told apart.

**An edge write that loses a race answers `no_such_assignment`.** If the child is
revoked while the update waits on its row lock, the update matches nothing and an
`IF NOT FOUND` refuses before any audit row. If the parent is revoked first, the
foreign key raises `foreign_key_violation`, which is mapped to the same key.
Today that fires before ADR 0044's trigger, because PostgreSQL fires a table's
AFTER ROW triggers in name order and `RI_ConstraintTrigger_...` sorts before
`role_assignment_supervision_edge_is_legal`. The answer does not rest on that
order: the `check_violation` handler first asks again, at a fresh READ COMMITTED
snapshot, whether the parent exists, and answers `no_such_assignment` when it does
not.

## Alternatives rejected

- **Table grants to `pulse_app`.** A grant cannot refuse an `INSTRUCTOR` row,
  cannot require an admin, and cannot make a write and its audit row one
  transaction.
- **Refusing Care, Admin and self-targeted grants in code.** The owner chose a
  complete editor (ruling 1); the audit row is the control.
- **An audit row written by the service, after the write.** A caller could commit
  the write without it.
- **Assignment end-dating.** Ruling 7: no reader needs assignment history.

## Consequences

- A `pulse_app` session holding any admin's person key can grant anybody Care or
  Admin. The audit row records it; nothing refuses it. The reveal definers are
  still `pulse_care`'s, not `pulse_app`'s.
- One action covers each pair (set and clear, map and unmap, link and unlink).
- A linkage row records no login subject. `idp_subject` is marked
  identity-bearing on its table and stays out of `audit_log`; the identity
  provider's own logs answer whose login was linked. The row's `role` records
  only the privilege the linked person held, not a later change to it.
- The admin cannot read a linked person's `idp_subject`, only whether one is
  linked and by which issuer.
- No refusal for a duplicate grant, revoking the last admin, a blank name or an
  over-long category; E9-06's request schema bounds the inputs.
- The downgrade refuses while any admin write is recorded, and the five enum
  values stay.
