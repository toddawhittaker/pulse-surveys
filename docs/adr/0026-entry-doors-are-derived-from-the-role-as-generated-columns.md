# 0026 — Entry doors are derived from the role, as stored generated columns

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-09

## Context

[SPEC §2.1](../SPEC.md) gives every role an entry point, and states the rule
twice — once as a table column and once as prose:

> Every *reporting* role — instructor, lead faculty, chair, assistant dean, dean,
> VP of Academics — can enter through an LTI launch, including leadership. Every
> role except instructor and student can *also* enter by web login; Care and
> Admin are web login only (their work has no launch context), and students enter
> by launch only.

It also says whose property a door is: "Entry doors are a property of the
assignment, not the person. A person holding two assignments uses whichever door
fits the one they are acting under."

E0-09's criterion 10 asks that "assignments record which entry doors they
permit" and, as amended, asks this ticket to decide what *record* means. The two
readings are not equivalent, and the ticket says why: the rule as written is
stated purely in terms of role, so a value derived from the role cannot disagree
with it, while a value stored per row can — a row may claim a door its role does
not permit and nothing would notice.

## Decision

Two **stored generated columns** on `role_assignment`, `permits_launch` and
`permits_web_login`, each derived from `role`.

Derived, so no write path can contradict the role; stored as columns, so the fact
is on the row where a view, a seed script or a psql session can read it, rather
than in a Python function only the application can call.

Each door **enumerates the roles that hold it** rather than excluding the ones
that do not. `permits_web_login` is not written as `role <> 'INSTRUCTOR'`, though
that is shorter and equivalent today.

## Alternatives rejected

**Two writable boolean columns, set by whoever writes the row.** The reading
criterion 10's wording most obviously suggests, and the one that lets a
deployment vary a door per assignment. Rejected because §2.1's rule is about
roles, so any per-row value is a second, weaker statement of a rule that already
has an authority — and the failure is silent in the dangerous direction. A Care
assignment with `permits_launch` set is a row that contradicts its own role, and
nothing notices until a launch honours it. Keeping a writable column honest needs
a check constraint restating the role rule beside it, at which point the column
is derived and merely says so less clearly.

**A `role_entry_door` lookup table, joined at read time.** Normalised, editable
without a migration, and the shape most reviewers expect. Rejected on both
halves: the join buys nothing for a fact with eight rows fixed by the spec, and
"editable without a migration" is the defect rather than the feature. It makes
the door a configuration knob for something with one correct answer, and the
answer is a security boundary — Care and Admin have no launch context because
there is nothing for a launch to mean to them, and a row in a table is a much
quieter way to change that than a migration is.

**Derived in Python, with no column at all.** Cheapest, and genuinely correct as
far as the application is concerned. Rejected because it puts the rule somewhere
only one reader can see it: E0-10's identity-separated views are SQL, the seed
script writes SQL, and an operator answering "why can this person not log in"
reads rows. A property of an assignment that cannot be read off the assignment is
not a property of the assignment.

## Consequences

**A row cannot contradict its own role**, which is the question the ticket asked
to be answered. There is no write path to either column for anyone — application
role, seed script, superuser session or future admin console alike.

**The rule now lives in two places that must agree**: the two expressions here
and `AssignmentRole`. Adding a role to the enum without adding it to a door list
gives that role no door at all, which fails closed and reports itself the first
time somebody tries to enter. That is the reason each list is positive: the
negative spelling would hand a new role web login by default, from a line nobody
revisited.

**Changing a door is a migration.** Alembic cannot alter a generated column, so
its entire response to a changed expression is one normalised string comparison
and a `UserWarning` — no error, and a zero exit. Both expressions are therefore
written in Postgres's own deparsed shape, so that warning fires on real drift
rather than on every run; this is the practice [ADR
0015](0015-course-level-is-a-stored-generated-column.md) established for
`course.level`, and the same caveat applies — the warning is a signal, not a
gate. Verified by running `alembic check` against the applied migration and
seeing it silent.

**Two extra booleans per row.** Trivial in space, and they earn it by being
readable from SQL. Both were verified by mutation: adding `CARE` to the launch
list, or `INSTRUCTOR` to the web-login list, turns the door test red.
