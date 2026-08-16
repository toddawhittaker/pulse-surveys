# 0020 — Identity-bearing columns are marked by an `identity_` name prefix

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-08, E0-10

## Context

[SPEC §8](../SPEC.md) requires that instructor and leadership read paths go
through views that structurally cannot join to identity columns, and
[§4.1](../SPEC.md) makes the resulting rules automated assertions.
[ADR 0001](0001-identity-separation-by-database-role.md) settles the enforcement
— a table-level grant on `user_identity` — and leaves open how E0-10's views and
the CI invariant pass are supposed to *find* the columns in question.

E0-08's scope asks for exactly that and leaves the mechanism open: "column-level
comments or a marker convention identifying every identity column, so E0-10's
views and the CI invariant can both find them programmatically rather than by a
hand-maintained list."

Two properties decide it. The marker has to be visible to a reader that is not
Python — a view is a database object and CI's invariant pass asserts against a
database. And the model's set and the database's set have to be the same set,
because a marker that is declared and never applied leaves everything reading the
model seeing a complete convention and everything reading Postgres seeing a
partial one.

## Decision

Identity-bearing columns carry an `identity_` name prefix:
`user_identity.identity_name`, `user_identity.identity_email`,
`person.identity_name`. This follows the precedent
[ADR 0014](0014-lms-owned-columns-are-marked-by-a-name-prefix.md) set for
LMS-owned columns, for reasons that apply again here.

**The prefix says what the column holds. It does not say who may read it** —
that is E0-10's decision, made with grants and views, and a separate one. In
particular, marking `person.identity_name` does not by itself withhold it from
anybody.

**Where a column is both identity-bearing and LMS-sourced, the identity marker
takes the name.** A display name and an email address reach Pulse from the
platform, so ADR 0014 read alone would prefix them `lms_`, and a column cannot
lead with two prefixes. The identity marker wins because it is the one with a
mechanical reader: E0-10 builds views and grants from this enumeration and the
§4.1 invariant suite asserts against it, while ADR 0014's own amendment records
that its marker may turn out to be documentation if E0-11 picks table grain.
Nothing is lost on the ownership side either — `user_identity` is LMS-sourced
in its entirety, so ownership there is a fact about the table and needs no
column to carry it.

## Alternatives rejected

**A Postgres column comment**, which E0-08's scope names first. It is visible to
any client including a bare `psql` session. Rejected on drift: the comment is
written by the migration and the model carries its own copy, `alembic check` does
not compare comments, and the two come apart silently. Measured rather than
assumed — putting `comment="identity"` on a model column with no migration
behind it leaves `alembic check` clean, and
`tests/integration/test_identity_column_marker.py` catches it only because that
test compares the two sides directly. ADR 0014 rejected comments on the same
ground for the same reason.

**A comment on the whole table.** Coherent — ADR 0001 makes the protection a
table-level grant, so a table-grained marker matches the enforcement — and it is
the accurate statement for `user_identity`, where every column is identity.
Rejected because it is not accurate for `person`, whose `id`, `user_id` and
`category` are not identity. Marking them would put them into the enumeration
E0-10 builds its views from, and an enumeration that grows to cover the schema
stops being able to fail.

**`Column(..., info={"identity": True})`.** Idiomatic SQLAlchemy and readable
from `Base.metadata` without importing anything. Rejected because the database
never sees it: a view definition and a CI assertion against a live database are
both one indirection away from it, and it is the shape that can be declared and
never applied.

**A hand-maintained list in E0-10.** Rejected by the ticket's own wording —
"programmatically rather than by a hand-maintained list" — and by the failure it
invites, which is a later ticket adding an identity column and no list changing.

## Consequences

The prefix is noisy, and it is noisier than ADR 0014's because these columns are
read constantly: every serializer, every view definition and every Care-queue
query spells `identity_name` rather than `name`.

**The convention is a convention, not an enforcement, and the boundary is worth
stating exactly.** `tests/integration/test_identity_column_marker.py` sweeps the
tables that hold a person — `user`, `user_identity`, `person`, and anything with
a foreign key to one of them — for columns whose names contain "name" or "email",
and fails on one that carries no marker. That reaches E0-09's `role_assignment`
and E1's roster tables without being edited, which is the point. What it cannot
see is an identity column whose name contains neither word: a `sortable`, a
`sis_login`, a `phone`. No test that reads a database can distinguish one of
those from an ordinary string column, and this record does not claim otherwise.

**A column that stops being identity-bearing needs a migration to rename it**,
which is the intended cost: a change in what a column holds should be a visible
schema event.

**The two markers cannot both be prefixes on one column**, so a reader who wants
to know whether an identity column is LMS-sourced has to look at the table rather
than at the name. Today that question has one answer per table — `user_identity`
is LMS-sourced, `person` is Pulse-owned (SPEC §2.1) — and if a table ever mixes
the two, this record needs revisiting rather than reinterpreting.
