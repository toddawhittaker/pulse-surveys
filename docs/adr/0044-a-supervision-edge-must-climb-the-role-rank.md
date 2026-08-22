# 0044 — A supervision edge must climb the role rank, and the trigger is what refuses one that does not

**Status:** Accepted — **context amended 2026-08-22** (E0-42); the decision is
unchanged, and the half of it the spec was silent on is silent no longer
**Date:** 2026-08-17
**Tickets:** E0-11

Extends [ADR 0027](0027-supervision-edges-are-policed-by-one-row-level-trigger.md),
which built the trigger this rule lands in.

## Context

> **Amended 2026-08-22.** The paragraph ending "It says nothing about whether two
> assignments in the same role may report to one another, and nothing about where
> `ADMIN` sits" was true when it was written and was falsified the same week.
> `fd703bb` (2026-08-17) added a paragraph to **SPEC §2.1** stating the rule
> directly: an edge is legal only where the child's role sits below the parent's
> in the canonical chain, two assignments in the same role never report to one
> another, an edge never runs downward, Care and Admin sit outside the graph and
> hold no edges in either direction, and the graph is therefore at most six
> assignments deep. It also states that the rule reads the two assignments' roles
> and never the person.
>
> So the *rule* below is now spec, and what stays this record's own is **where it
> is enforced and how**: the trigger rather than the resolver, `array_position`
> over one array holding the chain, `NULL` treated as a refusal, the mirror
> enforced on an `UPDATE` that changes a parent's role, and the resolver's
> matching fail-closed shape in `_OWN_GRANT_ROOT`. The dispute ruling on
> [E0-11-01](../disputes/E0-11-01.md) is likewise superseded on its facts rather
> than reversed in its outcome: it found the equal-rank refusal correct while the
> spec was silent, and the spec now says the same thing.

[SPEC §2.1](../SPEC.md) defines purview as "**Purview(assignment) = own grant
union the purviews of all assignments transitively reporting to it**", and §4.1
invariant 2 as "a Lead Faculty assignment never grants sibling leads' courses, at
any point in the purview union computation".

E0-09 built the supervision graph and its privacy review found that **nothing in
the schema constrains an edge by role**. Two writes were measured accepted against
the shipped migration:

- `LEAD_FACULTY → LEAD_FACULTY`, which under §2.1's definition puts one lead's
  courses inside a sibling lead's purview — §4.1 invariant 2, written as a row;
- `CHAIR ← VP_ACADEMICS`, which puts the whole institution inside that chair's
  purview.

Neither row is wrong on its face, neither errors, and E0-09's sibling-isolation
test asserts the ancestors of the rows *it* wrote rather than that the joining
edge is unwritable, so it stayed green against both. E0-11's ticket states the
choice and refuses to leave it unmade: "Decide where the rule lives: a role-rank
check inside E0-09's trigger, or enforcement in the resolver. **Either is
legitimate; leaving it in neither is not.**"

What the spec does not supply is an *order*. §2.1 gives a canonical chain —
`INSTRUCTOR(section) → LEAD_FACULTY(course) → CHAIR(department) → DEAN(college) →
VP_ACADEMICS`, with the assistant dean inserted between chair and dean by the same
paragraph — and it gives that chain as an example of reporting lines rather than
as a lattice. It says nothing about whether two assignments in the same role may
report to one another, and nothing about where `ADMIN` sits.

## Decision

**An edge is accepted only where `rank(child) < rank(parent)`**, with rank being a
role's position in SPEC §2.1's canonical chain:

| role | rank |
|---|---|
| `INSTRUCTOR` | 1 |
| `LEAD_FACULTY` | 2 |
| `CHAIR` | 3 |
| `ASSISTANT_DEAN` | 4 |
| `DEAN` | 5 |
| `VP_ACADEMICS` | 6 |

**`ADMIN` holds no rank, and an edge touching an `ADMIN` assignment at either end
is refused.** So is an edge touching any role that a later ticket adds to
`AssignmentRole` without giving it a rank. `CARE` holds no rank either and is
already refused an edge in both directions by E0-09 — a `CHECK` for the child side
and the trigger for the parent side — so this rule does not restate it.

**The rule lives in E0-09's trigger**, extended in place rather than joined by a
second one, and the rank comparison is expressed as `array_position` over one
array holding the chain. A role outside the array answers `NULL`, and every
comparison treats `NULL` as a refusal.

**The rank is a property of the two assignments an edge joins, never of the person
holding them.**

**The mirror of the rule is enforced too**, on the `UPDATE` that changes a
*parent's* role: an assignment may not change to a role that something already
reporting to it fails to be outranked by.

**The resolver applies the same fail-closed shape at its own site.**
`services/authz.py`'s `_OWN_GRANT_ROOT` is a mapping from role to the containment
level its own grant is rooted at, and a role absent from it raises
`NoReportingPurviewError` rather than answering. `ADMIN` is absent, because §2's
table gives it the observability console, LTI registration, org and people
management and configuration, and no reporting access.

### Why role rank

Because purview is computed from the edges, so an edge is a grant, and the grant a
non-climbing edge makes is one the spec forbids elsewhere in as many words. An
equal-rank edge hands each side the other's subtree at the same containment level:
between two leads that is §4.1 invariant 2 exactly, and between two chairs it is
the same disclosure one level up — each chair's department inside the other's
purview, with no sentence anywhere that permits it. An inverted edge is worse and
simpler: it hands the lower role everything above it.

Rank is also the only property available. The alternative discriminators are the
scope node — which ADR 0025 already constrains per role, so it adds nothing — and
the person, which is wrong for the reason below.

### Why the trigger rather than the resolver

Three reasons, and the first is the one that decides it.

**The resolver is not the only writer.** E0-17's seed script, E9's CSV import and
§6.3's People editor all write `role_assignment`, and a rule enforced by whoever
happens to read the graph is not enforced. This is the same argument ADR 0027
makes for its own three rules, and E0-09 asks for the rule to hold "rather than
trusting callers".

**A resolver that ignores an illegal edge stores it.** The row stays in the
database, `alembic check` cannot see it, and every later reader — E9's union, a
CSV export, a report query somebody writes by hand — has to remember to ignore it
too. Refusing the write means there is nothing to remember.

**The failure is visible at the moment somebody causes it.** An administrator
re-pointing a reporting line in the People editor gets an error naming the two
roles. A resolver-side rule produces a purview that is quietly smaller than the
graph says it should be, which reads as missing data.

### Why `ADMIN` is refused rather than ranked

Giving it a rank means deciding either who an administrator answers to or who
answers to an administrator, and the spec says neither. §2's table gives `ADMIN` a
console rather than a scope over other people's data, and §2.1's chain does not
contain it.

The direction of the failure is what makes this fail-closed rather than tidy. An
edge **into** an `ADMIN` assignment gives it a transitive purview — "own grant
union the purviews of all assignments transitively reporting to it" — which turns
the role that manages the org chart into the role that reads everybody's reports,
and it is one row in the People editor away. An edge **out of** one puts the
administrator's own grant, whatever a later ticket decides that is, inside
somebody else's.

Treating an unranked role as rank zero would accept every edge out of one,
silently. That is the same trap `SCOPE_GRAIN_RULE`'s `ELSE false` was written for
(ADR 0025): an unmatched `CASE` returns `NULL`, a `CHECK` that evaluates to `NULL`
passes, and a role nobody has thought about acquires a grain by default.

### Why the rank reads the assignments and not the person

SPEC §2.1 attaches the edge to the assignment — "`reportsTo` edges connect **role
assignments, not people or org nodes**" — and calls two-hat people ordinary: "a
chair's lead-faculty assignment may report to their own chair assignment — legal
and expected", and §2 adds "a chair can also lead courses; an assistant dean can
hold a lead-faculty assignment while supervising a chair".

So a lead faculty member who also teaches a section of somebody else's course
holds an `INSTRUCTOR` assignment whose edge to that course's lead is legal, and a
VP who teaches does the same. A rule that ranked the *person* would compute
`rank(LEAD_FACULTY) >= rank(LEAD_FACULTY)` for the first and
`rank(VP_ACADEMICS) > rank(LEAD_FACULTY)` for the second, refuse both, and pass
every refusal test in the suite — because each of those builds its assignments
with a person of its own. The symptom would be that the roster sync cannot write a
teaching assignment for any lead who also teaches, which is most of them (§2:
"~95% adjuncts").

This is the trap ADR 0027 already records for the cycle walk, arriving a second
time at a different guard in the same function.

### Why the mirror rule, and why it is narrow

An edge can be made illegal without anybody writing an edge. An administrator
editing a chair into a lead faculty member in §6.3's People editor leaves whatever
reported to that chair reporting to a lead, and a guard that inspects only the
edge being written never runs. E0-09 already closes exactly this shape for its
Care rule — a row "may not become a CARE assignment while other assignments report
to it" — and closing it for one rule and not the neighbouring one is
`docs/MISTAKES.md` entry 13 in a single function body.

It runs only on an `UPDATE` where `OLD.role IS DISTINCT FROM NEW.role`, because no
row can have children at the instant it is inserted. That keeps ADR 0027's lock
discipline: an ordinary insert still takes no advisory lock, and only a role change
joins the set of writes that do.

It sits *after* E0-09's Care-children rule, so a chair with children turned into a
`CARE` assignment is still refused by the rule named for it, with the message that
names it, rather than by the rank rule underneath.

### Why the rank check runs before the cycle walk, and why the cycle walk stays

The rank check is a property of one edge and two role values, so it is cheap and
its message is specific. Putting it first means an administrator who inverts a
reporting line is told about the inversion rather than about a cycle.

The consequence is that **E0-09's cycle guard is now reached only where the rank
rule has already passed**, and it is kept anyway. Two reasons. It is what still
holds if a later ticket changes the rank order, adds a ranked role, or replaces
this rule — and `docs/MISTAKES.md` entry 3 is explicit that where two rules can
refuse the same row, a behavioural test cannot say which one did, so the honest
position is to keep both and record which one answers first.

## Alternatives rejected

**Enforcement in the resolver, with an illegal edge ignored at read time.** The
option E0-11's criterion offers as equally legitimate, and rejected on the three
reasons above — chiefly that `role_assignment` has writers that are not the
resolver.

**A `CHECK` constraint.** Impossible: the rule reads the parent row's role, and a
`CHECK` may not look at a second row. This is why ADR 0027 exists at all.

**A rank column on `role_assignment`, or a rank lookup table.** A generated column
would work and is the instrument ADR 0015 and ADR 0026 both prefer, but the rule
compares *two* rows, so a column on each does not make the comparison declarative
— the trigger would still be needed to perform it, and there would then be two
statements of the order. A lookup table would put the order in data, where a
`DELETE` changes the rule with nothing going red.

**Ranking `ADMIN` at the top, beside `VP_ACADEMICS`.** Superficially reasonable —
an administrator is an authority — and it is the reading that hands them every
report in the institution the first time somebody points an edge at their
assignment. §2 gives `ADMIN` no reporting access at all, so the rank that would
express it correctly is not a number.

**Ranking `ADMIN` at the bottom, below `INSTRUCTOR`.** Refuses the dangerous
direction and permits the other: an administrator's assignment could then report
to anybody, putting their own grant inside somebody else's purview. A grant that
is currently empty is not a reason to leave the edge writable, because what
`ADMIN` holds is a later ticket's decision and this edge would already be in the
database when it is made.

**A partial order rather than a total one** — for instance, "an edge is legal if
the parent's role is above the child's in *some* chain", allowing parallel
branches. Rejected as machinery for a shape nobody has asked for: SPEC §2.1's
insertions (`CHAIR → ASSISTANT_DEAN → DEAN` beside `CHAIR → DEAN`) are already
expressible in a total order, because the insertion is a role *between* two
others rather than a branch beside them.

## Consequences

**The supervision graph is now at most six assignments deep.** Every edge strictly
increases rank and there are six ranks, so no chain can be longer than the chain.
That is a real restriction rather than a restatement of the rule, and it is
stronger than "refuse equal-rank and inverted edges" sounds.

**Acyclicity is now implied.** Every cycle contains at least one edge that does not
increase in rank, so no cycle this schema can express survives the rank rule, and
E0-09's cycle guard has become defence in depth rather than the only guard. The
cost is recorded above; the benefit is that the invariant §8 asks for at write time
now holds for two independent reasons.

**Three of E0-09's tests had to be rewritten for this rule**, and were:
`test_a_six_assignment_cycle_is_refused` and both properties in
`test_supervision_graph_properties.py`. Each built its graph out of
`graph.node("CHAIR", reports_to=<another CHAIR>)` and required those writes to
succeed, while E0-11's `[chair-chair]` case writes the identical row and requires
it to be refused. That was not a defect in either module and not something an
implementation could resolve, so it was raised as
[`docs/disputes/E0-11-01.md`](../disputes/E0-11-01.md) rather than worked around.

The ruling was that the E0-09 controls move, because no spec line requires a
same-role edge to be storable and those modules' own docstrings say the
single-role generator was fixture convenience. On the one same-role pair the spec
does answer — `LEAD_FACULTY → LEAD_FACULTY` — §4.1 invariant 2, §2.1's grain
sentence and §2.1's hierarchy-view-only rule agree that it is forbidden. Every
other same-role pair is spec-silent, and silence is not permission. The generators
now draw a strictly increasing role sequence; the dispute file carries the whole
argument, which is worth reading before anyone proposes relaxing this rule.

**A future role that does not fit one order is the cost this record is most
exposed on.** A total order is the right shape for the chain §2.1 draws, and it
answers badly for a role that is genuinely beside an existing one rather than above
or below it — a programme director who supervises leads across two departments
without being a chair, say, or a second kind of dean. The order would then need a
number inserted into it, which means renumbering nothing (the ranks are positions in
an array, so an insertion is one line) but does mean deciding the new role's place
relative to every existing one, which is a policy decision disguised as a
migration. If the answer is genuinely "beside", this record is the one to supersede,
and the replacement is the partial order rejected above. The fail-closed default is
what buys the time to make that decision: an unranked role cannot be given an edge
at all, so the schema refuses to store a graph nobody has reasoned about, rather
than inventing one.

**`alembic check` cannot see any of this**, exactly as ADR 0027 records for the
rules it added: the check reads neither `pg_trigger` nor `pg_proc`, so replacing
the function or dropping the trigger leaves it green.
`tests/integration/test_supervision_edges_run_up_the_role_ranks.py` is the only
reader: the legal pairs, the refused pairs, the two-hat shapes, the `ADMIN` pair,
the `UPDATE` path and the mirror rule below. No count is given here on purpose — a
number that has to be re-measured on every edit to that file is a record that will
be wrong again (`docs/MISTAKES.md` entry 1).

**The mirror rule on the parent's role shipped unasserted and no longer is.** When
this record was written no test wrote an `UPDATE` that changes a role in a way that
invalidates a child's edge, and the implementer of this ticket is walled out of
`tests/`, so the gap was declared here rather than left to be discovered
(`docs/MISTAKES.md` entry 2). The test named in that declaration now exists: a
`CHAIR` with a `LEAD_FACULTY` reporting to it, updated to `LEAD_FACULTY`, refused,
controlled by the same update applied to a chair nothing reports to, which must
succeed. A second test edits that chair to `DEAN` — a role that still outranks its
reporters — and asserts the reporter still reports to it afterwards, which is what
distinguishes this rule from one implemented by clearing the children's edges.

The scope node moves with the role in those updates, and has to: E0-09's grain rule
ties the populated scope column to the role, so a role-only update is refused by
the grain rule and that refusal says nothing about rank.

**The `REPEATABLE READ` refusal widened**, and the message with it. E0-09 refused
that isolation level for writes carrying an edge or the `CARE` role; a write that
changes a role now joins them, because the mirror rule is read-then-write like its
neighbours. Nothing in this codebase runs `REPEATABLE READ` (ADR 0013 leaves the
level at the server default), so the restriction costs nothing today.
