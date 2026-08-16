# 0027 — Supervision edges are policed by one row-level trigger, holding an advisory lock

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-09

## Context

[SPEC §2.1](../SPEC.md) makes the supervision graph "a forest/DAG over
assignments" and says "assignment-level cycles are invalid, person-level cycles
are fine". [§8](../SPEC.md) repeats it: "assignment-level cycles are rejected at
write time." §2.1 also puts Care outside the graph entirely — it "supervises
nothing and escalates to nobody" — which E0-09 states as a rule in both
directions: a `CARE` assignment never carries a `reports_to` edge and is never
the target of one.

Purview is "own grant ∪ purviews of all assignments transitively reporting to
it". Over a loop that union has no fixed point, so a stored cycle is not a wrong
report — it is a report that never arrives. And an edge into a Care assignment
gives the one role that can re-identify a student a reporting purview, which
§6.2 spends a paragraph refusing.

Three of these four rules cannot be a `CHECK` constraint, because a `CHECK` may
not read a second row. Only "a Care assignment carries no edge" is a fact about
one row, and that one is a `CHECK`.

## Decision

One `AFTER INSERT OR UPDATE ... FOR EACH ROW` trigger on `role_assignment`,
enforcing the three cross-row rules: the parent is not a Care assignment, the row
does not become a Care assignment while others report to it, and the edge does
not close a cycle at any depth.

The cycle test is a recursive CTE walking `reports_to` upward from the new
parent, with the SQL `CYCLE` clause so the walk terminates even against a row set
that already contains a loop. It compares assignment ids and never `person_id`.

Before either cross-row check, and only where there is cross-row work to do, the
trigger takes a transaction-scoped advisory lock keyed on the table's own oid.

Errors are raised with `ERRCODE = 'check_violation'` and messages naming what the
writer did.

## Alternatives rejected

**A check in `app/services/`.** The obvious place, and it can produce the best
error message. Rejected because it is not the only writer: E0-17's seed script,
E9's CSV import and any future admin path all write these rows, and E0-09 asks
for the rule to be enforced "rather than trusting callers". A guarantee that
holds only for code that remembers to call it is a convention.

**A `BEFORE` trigger.** Rejected because it misses the shortest cycle in the
schema. Postgres checks a row's foreign keys after the row exists, so
`INSERT ... (id, reports_to) VALUES (x, x)` is a legal self-reference written in
one statement, with no second write for a `BEFORE UPDATE` guard to intercept.
Firing after the row is in place also means the walk starts from a graph that
already contains the edge under test, whichever statement put it there.

**A `CHECK (reports_to <> id)` alongside the trigger**, as cheap
defence-in-depth. Rejected because the trigger already refuses depth one, and two
rules that refuse the same row make a behavioural test unable to say which one
did — `docs/MISTAKES.md` entry 3, in its own words. A partial guard that survives
the trigger being dropped would also be worse than none: it would leave depth one
refused and every longer loop accepted, which reads like a working guard.

**A deferrable constraint trigger firing at commit.** Genuinely attractive: it
lets an administrator reorganise a subtree in one transaction through a
transient state that is briefly cyclic. The test suite deliberately accommodates
either design, issuing `SET CONSTRAINTS ALL IMMEDIATE` so both answer at the same
moment. Rejected because an error raised at `COMMIT` cannot be attributed to the
statement that caused it, and §6.3's People editor needs to tell an administrator
which edit made the loop. No target state becomes unreachable: any acyclic
arrangement can be reached by clearing the conflicting edge first, at the cost of
one extra statement.

**Living with the concurrency hole rather than taking a lock.** Rejected because
it was measured rather than reasoned about. Both rules are read-then-write, so
two concurrent transactions each see a graph without the other's edge; against
this schema on the pinned Postgres, `A → B` and `B → A` were written in
overlapping transactions, both committed, and both edges were stored. With the
advisory lock the second transaction blocks, then sees the first one's committed
edge and is refused — measured the same way, against the migration as it ships.

## Consequences

**`alembic check` cannot see this trigger, in either direction.** It reads
neither `pg_trigger` nor `pg_proc`, so dropping the trigger or the function
leaves the check green and leaves the supervision graph accepting loops. The
behavioural tests and the Hypothesis properties are the only thing that notices,
which is why those generate cycles of every length up to eight and close each
from every rotation. Any later change to this rule needs a test run, not a drift
check.

**[ADR 0015](0015-course-level-is-a-stored-generated-column.md) rejected a
trigger for `course.level` and this accepts one**, which is worth stating rather
than leaving as an apparent contradiction. That decision had a generated column
available, and this rule spans rows, so no declarative instrument exists. The
objection 0015 raised — "a trigger's guarantee is only as good as the next
`ALTER TABLE ... DISABLE TRIGGER`" — is narrower here than it looks: disabling a
trigger requires ownership of the table, migrations run as the superuser
identity ([ADR 0009](0009-a-superuser-identity-is-sanctioned-for-migrations-and-bootstrap.md))
and so own it, and the application role is `NOSUPERUSER` and not the owner.
Measured: as `pulse_app`, with `SELECT`/`INSERT`/`UPDATE` granted, `ALTER TABLE
role_assignment DISABLE TRIGGER` is refused with "must be owner of table
role_assignment".

**Re-parenting writes serialise.** Only writes that carry an edge or make a row
Care take the lock, so an ordinary assignment with no supervisor does not queue —
measured, an edgeless insert completes while a re-parenting transaction is open.
The writes that do serialise are administrator edits and CSV import rows, where
the contention is one person at a time. If a bulk import ever makes this hurt,
the fix is a coarser transaction rather than a weaker guard.

**Two rules the trigger enforces are asserted by no test**: an existing
assignment being flipped to `CARE` while others report to it, and the concurrency
case above. Both were mutated and both survived, which is how they are known to
be untested rather than assumed to be covered. They stay because each closes a
path to the same stored state the tested rules refuse, and both are named in the
pull request so the test author can decide whether to cover them.

**The walk is over assignment ids, and a future edit must keep it that way.** A
guard written over `person_id` passes every cycle test in the suite and makes the
commonest two-hat arrangement in the institution — a chair who also leads a
course — unwritable. §2.1 calls that arrangement "legal and expected", and the
test that holds the line is `test_a_person_may_hold_two_assignments_where_one_
reports_to_the_other`.
