# 0021 — Overlapping enrollment windows are refused, by a GiST exclusion constraint

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-08

## Context

[SPEC §2.1](../SPEC.md) makes enrollments LMS-owned and synced, and E3's
participation formula is enrollment-windowed — it asks whether a student was
enrolled in week N. E0-08 gives `enrollment` a start and an end for that reason
and then leaves the hard part open: "Overlapping enrollments for the same user
and section are either rejected or explicitly permitted with a documented reason
— decide and test it."

The spec says nothing about what two overlapping rows would mean. That is the
whole difficulty: a rule for choosing between them would have to be invented
here, and it would be invisible to everyone who later reads the two rows.

Mid-term adds and drops are ordinary — E0-15 seeds them deliberately — so
whatever is chosen has to keep accepting a student who drops in week 3 and
re-adds in week 8.

## Decision

**Overlapping windows for one user and one section are refused**, and the refusal
is a Postgres exclusion constraint on `enrollment`:

```
EXCLUDE USING gist (
    user_id WITH =, section_id WITH =,
    daterange(started_on, ended_on, '[]') WITH &&
)
```

`btree_gist` is created by the same migration, because GiST has no operator class
for `uuid` equality without it. `ended_on` is nullable and means still enrolled,
which makes the range unbounded above; two open-ended windows for one pair
therefore overlap and the second is refused, which is the right answer.

An ordinary `CheckConstraint` beside it states criterion 4's rule —
`ended_on IS NULL OR ended_on >= started_on` — separately from this one. See the
consequences: the two overlap, and that is deliberate.

## Alternatives rejected

**Permitting overlap.** The other branch the criterion offers, and it needs a
tie-break rule written down first: "was this student enrolled in week N" would
have two answers, and a student counted twice moves the denominator of a
participation figure that goes on an instructor's report. No ticket has such a
rule, and inventing one in a schema ticket puts it where nobody computing
participation will look.

**`UNIQUE (user_id, section_id)`.** The constraint that suggests itself, and it
is a different rule: "a user may be enrolled in this section once, ever". It
refuses the drop-and-re-add above, which the LMS sends, and E3 then cannot know
the student was away for two weeks.

**A trigger, or a `BEFORE INSERT` check that queries the table.** Expresses the
same rule and is subject to the race the constraint is not: two concurrent
transactions each see no conflicting row and both commit. A roster sync running
on a schedule and on launch (SPEC §7.3) is exactly the workload that produces
concurrent writers for one section.

**Enforcing it in `app/services/`.** Refused by SPEC §8 for this class of rule,
and it would be unenforceable against the seed script and the Celery tasks that
also write, which is why every other rule in this schema is a constraint.

**Storing the section's end date instead of a null `ended_on`.** Would let the
range be closed always and avoid reasoning about unbounded ranges. Rejected
because it stores a prediction as a fact: it has to be corrected on every drop,
and a section whose dates change makes every enrollment row silently wrong.

## Consequences

**`alembic check` does not compare this constraint in either direction, and that
was measured, not assumed.** Autogenerate rendered it into the creating migration
because it sits on the model's `Table` and the table was new. Afterwards:
removing it from the model leaves `alembic check` clean, because Alembic's own
Postgres implementation drops the backing GiST index from the reflected set
(`correct_for_autogen_constraints`) and nothing compares `pg_constraint` rows of
type `x`. Editing the model's rule without writing a migration is therefore
silent drift. `tests/integration/test_identity_schema.py` asserts the behaviour
against a real server, which is the only thing that can. E0-07 found the same
hole for `CheckConstraint` expressions; on the pinned Alembic 1.19 a check
constraint's *name* is now compared and its *expression* still is not, which was
measured the same way.

**The check constraint and the exclusion constraint overlap, and neither is
redundant in the way it looks.** A backwards window is refused by either one
alone: with the check removed, `daterange(started_on, ended_on, '[]')` raises
"range lower bound must be less than or equal to range upper bound", and with the
exclusion constraint removed the check refuses it. Both were measured by
deletion. The check is kept because it is the rule stated in the schema rather
than implied by an implementation of a different rule, and because it produces an
error a reader can act on. The cost is honest and is recorded in the pull
request: the check constraint can be deleted with the whole suite green, which is
`docs/MISTAKES.md` entry 2's shape.

**A deployment target that cannot create extensions cannot apply this
migration.** `btree_gist` ships with Postgres as a contrib module and the pinned
image has it; a managed database that restricts `CREATE EXTENSION` would need
the rule moved to a trigger, with the race above.

**Two enrollments that touch at a boundary are an overlap**, because the range is
inclusive at both ends: a student who drops on day 30 cannot be re-added on day
30. That is the correct reading of a window as a set of days the student was
enrolled on, and it is what makes a same-day add-and-drop a non-empty range.
