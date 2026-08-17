# 0045 — The chokepoint refuses an LMS-owned write at table grain, plus one row

**Status:** Accepted
**Date:** 2026-08-17
**Tickets:** E0-11

Does **not** close the open half of
[ADR 0014](0014-lms-owned-columns-are-marked-by-a-name-prefix.md). See the
consequences.

## Context

[SPEC §2.1](../SPEC.md) splits ownership. LMS-owned: "courses, sections, section
codes, enrollments, teaching instructors", synced hourly and never hand-edited.
Pulse-owned: "person records (name, category) plus reports-to edges" — "the LMS
has no equivalent; purview is computed from this graph" — and the Lead Faculty
mapping, "maintained in the admin console with CSV import/export".
[§8](../SPEC.md) restates the first half as a constraint: "LMS-owned data is never
hand-edited in Pulse."

E0-05 marked LMS-owned columns with an `lms_` name prefix (ADR 0014) and E0-11's
criterion asks for a refusal at the chokepoint — with an instruction attached:
"**Choose the grain deliberately; do not inherit it from the marker.**" The ticket
records that two earlier drafts of that criterion each got this wrong, the more
dangerous one by claiming the prefix is the only possible signal, "because it
records an unprefixed LMS-owned column slipping through as expected behaviour".

The failure being prevented is quiet. An edit to LMS-owned data is not rejected by
the LMS and does not error; it is overwritten at the next hourly sync, so the
symptom is a value that changes back by itself, which reads as a sync bug rather
than as a write path that should not exist.

## Decision

`services/authz.py` exposes `guard_write(table=..., assignment_role=...)`, which
raises `LmsOwnedWriteRefused` in exactly two cases.

**Table grain.** `LMS_OWNED_TABLES` is `{course, section, enrollment, user}`, and
any write to one of them is refused.

`course`, `section` and `enrollment` carry four of §2.1's five owned items —
courses, sections, section codes, enrollments. `user` is in the set because
`user.lms_user_id` is the `sub` claim verbatim (ADR 0014: the platform supplies
the value and Pulse never edits it) and §4 keys every response to it. The launch
path that creates a `user` row is a sanctioned writer, in the same way E1's roster
sync must be for the other three.

**Plus one row.** A `role_assignment` row whose role is `INSTRUCTOR` is refused,
and every other role on that table is permitted.

That row is §2.1's fifth owned item, the teaching instructor. §2.1's chain is
`INSTRUCTOR(section) → LEAD_FACULTY(course) → …` over **role assignments**, and §8
puts those on `role_assignment` — so the one LMS-owned item that does not live on
the three tables is a row on a table the application otherwise writes freely. It
is not a stale attribute: §2.1 computes purview from exactly these rows, so an
application write path able to create one is a path that can grant somebody
oversight of a section, with the moderation view and the report that hang off it.

**`user_identity` is deliberately not in the set.** It is LMS-sourced and it is
identity-marked (ADR 0022), and what protects it is E0-10's grant model —
`pulse_app` holds no privilege of any kind on it, asserted out of
`has_table_privilege` for all seven privileges and provoked as a refusal
separately — not this chokepoint. Adding it here would put a second, weaker
statement of that guarantee in the application layer, where deleting it changes
nothing and reading it suggests the protection lives in Python.

## Alternatives rejected

**Column grain over the `lms_` prefix.** The grain the marker suggests, and the
one E0-11 explicitly warns against inheriting. It has the omission gap: a column
that is LMS-owned and unprefixed is invisible to it, and ADR 0014 itself records
that the prefix is a convention rather than something the schema enforces. Under
table grain an unprefixed LMS-owned column arriving on `course`, `section` or
`enrollment` is refused along with everything else on that table, which is the
failure direction worth having.

It is also the wrong shape for the fifth item. There is no `lms_` column on a
`role_assignment` row; what makes that row the LMS's is its `role` value, so a
name-based check cannot express the rule at all.

**Table grain over `{course, section, enrollment}` alone.** What the ownership
sentence looks like at a glance, and it leaves an application write path able to
create or edit an LMS-sourced `INSTRUCTOR` assignment. That is the more dangerous
of the two omissions this grain could have had, for the reason above: the row is a
purview grant.

**Refusing `role_assignment` outright.** Satisfies every denial test and makes
§6.3's People editor unable to write anything — §2.1 builds the people graph
"top-down in the admin console (a new person's reports-to selector lists only
people already in the graph)", and every leadership assignment in it is a row on
that table.

**Both grains at once — table grain plus a prefix sweep.** Tempting as
defence-in-depth, and rejected because the prefix sweep would add nothing on
today's schema and would cost the thing that matters. Every `lms_`-marked column
already sits on `course`, `section` or `user`, so the sweep refuses no write the
table rule does not. What it would add is a second statement of the rule that
*looks* like it closes ADR 0014's open half, which is exactly the false record
E0-11's criterion warns about, and `docs/MISTAKES.md` entry 3 is about two rules
refusing the same row leaving a behavioural test unable to say which one did.

**Enforcing it in the database, with a grant.** The right answer eventually, and
not available yet. Refusing the *application role* `INSERT`/`UPDATE` on these
tables would be structural rather than a convention — the ADR 0001 shape — but the
launch path and E1's roster sync are the same connection, so the grant would have
to distinguish a sanctioned writer from an unsanctioned one, and no such
separation exists in E0. E1 is where the roster sync arrives and where that
becomes a real option.

## Consequences

**What this grain does not catch, stated so nobody cites it as more than it is.**

A **Pulse-owned writable column landing on `course`, `section` or `enrollment`** is
refused along with everything else on that table, which is table grain's mirror of
column grain's omission gap. `course.level` is already a non-LMS column on one of
them and is saved only by being a stored generated column that nothing can write
(ADR 0015); `enrollment.started_on` and `enrollment.ended_on` are the live case —
`app/models/identity.py` records that they are most likely Pulse's record of when a
student was first and last seen, which is why they carry no `lms_` prefix, and this
guard refuses a write to them. If E1's roster sync turns out to own them, they are
already inside the refusal for the right reason; if Pulse owns them, the guard is
wrong about that column and the fix is a narrower rule for that table, not an
exemption.

**ADR 0014's open half stays open.** That record's own status line says
"a convention, with the enforcing check deferred to E0-11", and this is E0-11
declining to close it. The prefix is still unenforced: nothing stops a later ticket
adding an LMS-owned column without the marker, and nothing here can see one. What
this decision does is make the *table* the unit, so that on the three tables §2.1
names the marker's accuracy stops mattering. Off those tables it matters as much as
it did. [E0-21](../tickets/e0/E0-21-review-debt.md) carries the residue.

**A caller can bypass it by not calling it.** `guard_write` is a function, not a
grant, so it holds for the write paths that go through the chokepoint and for no
others — which is the same objection ADR 0027 raises against putting the
supervision rules in `app/services/`, and it is answered differently here only
because the database instrument that would close it does not exist yet. E0 ships no
HTTP write path at all, so today the set of callers is empty and the guard is
scaffolding with tests on it. E1 is the first ticket that has to route a real write
through it.

**A typo in the set refuses nothing.** `LMS_OWNED_TABLES` holds table *names*, so
`"courses"` would refuse writes to a table that does not exist while leaving the
real one writable, and it would read as correct in review.
`test_the_refusal_set_names_the_tables_the_spec_puts_on_the_lms_side` asserts every
name in it is a table on `Base.metadata` for that reason, and
`test_every_column_marked_lms_owned_sits_on_a_table_the_chokepoint_refuses` asserts
the other direction per marked column, so a marked column arriving on a table
nobody added to the set fails rather than becoming an edit path with nothing going
red.

**`LmsOwnedWriteRefused` keeps a name that ruff's `N818` objects to.** The rule
asks for an `Error` suffix; the name is part of the interface E0-11 settled before
any of it was written, and renaming it to quiet a linter would be a change to the
contract. Suppressed at the class with the reason on it. The base class,
`AuthzError`, carries the suffix, and that is the name an entry point catches.
