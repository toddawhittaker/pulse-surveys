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
trigger takes a transaction-scoped advisory lock keyed on the table's own oid,
**and refuses the write outright if the transaction is `REPEATABLE READ`**.

Errors are raised with `ERRCODE = 'check_violation'` and messages naming what the
writer did.

### The isolation level is part of the guarantee, so it is enforced rather than assumed

Both cross-row rules are read-then-write, so the guard is only as good as what
its read can see. The advisory lock serialises the writers; it does not give the
second one a fresh snapshot. Measured against the shipped migration on the pinned
Postgres, three attempts per cell, two shapes — `A → B` plus `B → A`, and a
three-row shape where `B → C` is already committed while one transaction writes
`C → A` and the other writes `A → B`:

| Trigger | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
|---|---|---|---|
| advisory lock alone | 0/3 stored | **3/3 stored, both shapes** | 0/3 stored |
| lock + parent `FOR KEY SHARE` | 0/3 | **3/3, both shapes** | 0/3 |
| lock + parent `FOR SHARE` or `FOR UPDATE` | 0/3 | 0/3 two-row, **3/3 three-row** | 0/3 |
| lock + refusing REPEATABLE READ (shipped) | 0/3 | 0/3 | 0/3 |

`READ COMMITTED` holds because each statement inside the trigger re-snapshots, so
after the lock is granted the walk sees the other writer's committed edge.
`SERIALIZABLE` holds by SSI, which aborts one side with a `40001`. `REPEATABLE
READ` fails because the snapshot was fixed at the transaction's first statement
and no amount of waiting changes it.

Refusing that level is the whole of the fix, and it is refused only for writes
that need the cross-row read — an assignment with no edge and a role other than
`CARE` is accepted at any isolation level, which is measured too. Nothing in this
codebase runs `REPEATABLE READ` today ([ADR
0013](0013-the-database-session-is-synchronous.md) leaves the level at the server
default), so the restriction costs nothing now and converts a silent wrong answer
into an error naming the level and the two that work.

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

**Locking the parent row instead of refusing `REPEATABLE READ`.** The repair
suggested by the privacy review, and the one to reach for first: after taking the
advisory lock, `SELECT … FOR KEY SHARE` the parent, so a writer whose snapshot is
stale gets a `40001` instead of a silent success. Rejected on measurement, in two
steps. `FOR KEY SHARE` does not close even the two-row case — it conflicts only
with `FOR UPDATE`, and writing an edge takes `FOR NO KEY UPDATE` because
`reports_to` is not a key column, so the lock is granted against the stale row
version and the cycle is stored 3/3. `FOR SHARE` and `FOR UPDATE` are strong
enough to raise, and they close the two-row case, but they still store the
three-row case 3/3: the edge the stale walk cannot see sits further up the path
than the parent being locked, so locking the parent asks the wrong row. Closing
it properly means locking **every row the walk visits**, which the recursive CTE
cannot do — Postgres forbids a locking clause in a recursive term — so it would
mean replacing the walk with a hand-rolled `LOOP` and taking a share lock on each
ancestor of every re-parenting write. That is a real option and it is the one to
weigh if `REPEATABLE READ` is ever wanted; it is not worth its complexity and its
lock footprint for a level nothing uses.

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
`ALTER TABLE ... DISABLE TRIGGER`" — stands, and **`ALTER TABLE` is not the
cheapest way to do it**. `SET session_replication_role = replica` turns off every
non-replica trigger in the session, with no `ALTER TABLE`, no ownership check and
nothing in the schema to notice: measured, two inserts and two updates in such a
session store a two-row cycle. The parameter is superuser-only, so this does not
widen what the application can do — measured from both ends, `pulse_app` is
refused `ALTER TABLE role_assignment DISABLE TRIGGER` with "must be owner of
table role_assignment", and refused the parameter itself with "permission denied
to set parameter `session_replication_role`".

**Where that matters is [E0-17](../tickets/e0/E0-17-seed-script.md), which runs
as the superuser identity**, and a bulk loader is exactly the place somebody
reaches for `session_replication_role` to make an import fast. A seed run that
does so is not writing test data past a slow constraint; it is writing a
supervision graph that no rule in this schema has looked at. The same applies to
any future data migration. If a loader ever needs it, the loader owes a check
afterwards that no cycle exists — the same recursive walk, run once over the
table.

**Re-parenting writes serialise.** Only writes that carry an edge or make a row
Care take the lock, so an ordinary assignment with no supervisor does not queue —
measured, an edgeless insert completes while a re-parenting transaction is open.
The writes that do serialise are administrator edits and CSV import rows, where
the contention is one person at a time. If a bulk import ever makes this hurt,
the fix is a coarser transaction rather than a weaker guard.

**The rules the trigger enforces that no test in this ticket asserts** are the
concurrency case and the `REPEATABLE READ` refusal. Both need two connections and
an isolation level, which no fixture here sets up. They stay because each closes a
path to the same stored state the tested rules refuse, and both are named in the
pull request. The measurements behind them are reproducible from the tables above.

A third was in that list and is now covered: an existing assignment flipped to
`CARE` while others report to it, mutated and survived, now
`test_an_assignment_others_report_to_cannot_be_turned_into_a_care_assignment` in
`tests/integration/test_role_assignment_graph.py`. It is the `UPDATE` path to the
state the two insert-side Care tests refuse — the row itself becomes Care while
the edges pointing at it do not move, so a guard that inspects the edge being
written never runs — and its control is the same update applied to an assignment
nothing reports to, which is what makes the refusal attributable to the inbound
edge rather than to the role, the scope or the doors all changing at once.

**The walk is over assignment ids, and a future edit must keep it that way.** A
guard written over `person_id` passes every cycle test in the suite and makes the
commonest two-hat arrangement in the institution — a chair who also leads a
course — unwritable. §2.1 calls that arrangement "legal and expected", and the
test that holds the line is `test_a_person_may_hold_two_assignments_where_one_
reports_to_the_other`.
