# 0024 — The person-to-user link is carried by `person`, and is one to one

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-08, E0-09

## Context

[SPEC §2.1](../SPEC.md) keeps two structures apart: the LMS-owned side, where a
launch identifies someone by their LMS user ID, and the Pulse-owned people graph,
whose `person` rows carry a name and a category and are built top-down in the
admin console. Purview is computed from the people graph; responses are keyed to
the LMS user ID.

Something has to join the two, and E0-08 says only that "a `person` may or may
not correspond to a `user`; the link is nullable and explicit". It does not say
which table carries it, and the spec does not either. E0-09 resolves a launch to
a set of role assignments through this link, so it cannot be left implicit.

## Decision

`person.user_id` — nullable, unique, foreign key to `user.id`, `ON DELETE
RESTRICT`.

Nullable because the graph exists before anybody launches: a dean who has never
opened the tool still supervises chairs. Unique because two `person` rows
claiming one LMS user is a contradiction, not a state to resolve at read time.
On `person` because that keeps `user` to what E0-08's scope says it is — the key
and the platform reference — and because the link is a Pulse-owned fact, and
`person` is the Pulse-owned table.

## Alternatives rejected

**`user.person_id`.** The shape that models reality better: one person can hold
several `user` rows, one per registered platform, and a many-to-one link
expresses that without a second table. Rejected on two counts. It puts a third
column on the table ADR 0001 keeps deliberately minimal, and it is the table
whose contents every read path may see; and it moves the link onto the row that
a roster sync writes, so the people graph acquires an edge as a side effect of an
LMS sync rather than as an admin-console edit. Under the chosen shape the graph
is only ever edited where SPEC §2.1 says it is built.

**Matching a person to a user by name.** What "explicit" is written against. Two
people with the same name is not an exotic case, and the failure is a purview
computed for the wrong person — invisible, because it produces a plausible
answer.

**A join table.** The general answer, and it is what this becomes if the
one-to-one assumption breaks. Rejected now as unearned: it needs a uniqueness
rule per platform to be any better than the column, and nothing in E0 registers
two platforms.

## Consequences

**One person can be linked to one `user` row, and therefore to one platform.** A
deployment that registers two platforms carrying the same people — a pilot LMS
alongside production, which is the case E0-08's criterion 2 exists for — cannot
represent the person behind both. The fix is a migration: move the link to
`user`, or add the join table above. It is stated here rather than discovered,
and it is why the column is unique: the wrong row is unwritable rather than
merely discouraged.

**Deleting a `user` that a person is linked to is refused.** Unlinking is a
deliberate edit. This is the opposite choice from `user_identity`, which cascades
so that a name cannot outlive its user; the difference is that a `person` row is
Pulse's own record and losing it would lose the supervision edges hanging off it.

**E0-09 joins through this column** to resolve a launch to role assignments, and
E0-10's views join through it in the other direction. Both are single joins,
which is the property that made the direction look free — it is not, for the
reasons above, but neither direction costs a query.
