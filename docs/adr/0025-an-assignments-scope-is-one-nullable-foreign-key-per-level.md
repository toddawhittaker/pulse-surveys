# 0025 — An assignment's scope is one nullable foreign key per containment level

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-09

## Context

[SPEC §8](../SPEC.md) says an assignment carries "`person_id`, `role`,
`scope_node_id`, and a nullable `reports_to`", and [§2.1](../SPEC.md) gives each
role the kind of node it attaches to — instructor to a section, lead faculty to a
course, chair to a department, assistant dean and dean to a college, VP of
Academics, Care and Admin to the institution. E0-09 requires that pairing to be
enforced: "an assignment's `scope_node_id` must reference a node of the right
kind for its role… Enforce it rather than trusting callers."

`scope_node_id` is singular and there is nothing singular for it to reference.
E0-05 built containment as six separate tables — `institution`, `college`,
`department`, `prefix`, `course`, `section` — with no unified `org_node`, so the
spec's column name describes a table that does not exist. E0-09's own scope was
amended to say so and to hand the choice to this ticket.

The stakes are the reason it is enforced rather than assumed. Every one of these
rows is a grant of access to somebody's data, and a wrong pairing widens a
purview quietly: a dean scoped to the institution hands one college's dean every
college in the university, and a lead faculty scoped to a prefix holds every
sibling lead's course, which is [§4.1](../SPEC.md) invariant 2 broken in the
schema before any query is written. Nobody reports seeing too much.

**On invariant 2 the grain rule is necessary and not sufficient**, and this
record should not be read as claiming otherwise. It stops a `LEAD_FACULTY`
assignment being scoped above a course; it does not decide *whose* course that
is. §2.1 puts "one lead per course" on `lead_faculty_mapping`, which is where a
lead's own grant is computed from, and the two are unconstrained against each
other — measured, two `LEAD_FACULTY` assignments on one course are accepted, and
so is one on a course whose mapping names somebody else. E0-11 owns which of the
two a resolver reads.

## Decision

`role_assignment` carries **five nullable foreign keys**, one per containment
level a role can be scoped to: `institution_id`, `college_id`, `department_id`,
`course_id`, `section_id`. There is no `scope_node_id` column and no
`prefix_id`.

One `CHECK` constraint holds §2.1's whole scope-attachment column:
`num_nonnulls(...) = 1` says an assignment is scoped to exactly one node, and a
`CASE` over `role` says which one it must be. The `CASE` ends in `ELSE false`, so
a role added to the enum without a grain cannot be written down at all.

`prefix_id` is absent because no role in §2.1's table is scoped to a prefix. A
scope that cannot be spelled is a stronger rule than one that is spelled and
rejected.

**Two spec lines put a Lead Faculty and a prefix in one sentence, and neither is
an assignment scope.** §5.2 makes the exclusion log "visible at the Lead Faculty
prefix scope and above", and §5.3 lets a Lead Faculty set response publishing to
"required" per prefix. Both are grain for a *view* and for a *policy*, and both
are computed from §2.1's rule that a lead's tree roots are "the prefixes of their
led courses" — the distinct prefixes of the courses in `lead_faculty_mapping`,
which is a query over rows that already exist. A `prefix_id` here would be a much
larger claim than either line makes: it would grant the lead every course under
that prefix, sibling leads' courses included, which is §4.1 invariant 2. When
§5.3's per-prefix policy is built, the prefix belongs on the policy row.

## Alternatives rejected

**A kind column beside an untyped id** — `scope_node_kind` plus `scope_node_id`,
which is what the singular name most directly suggests. It keeps one column pair
whatever the hierarchy grows to, and the grain rule is a plain `CHECK` comparing
the kind against the role. Rejected because the id can then carry no foreign key:
it points at six different tables, so nothing enforces that it names a row that
exists, or that it names a row of the kind the neighbouring column claims. A
department deleted out from under an assignment leaves a grant pointing at
nothing, and the purview computed from it is wrong in whichever direction the
join happens to fail. Trading referential integrity for column count is the wrong
trade on the table every authorization decision is computed from.

**A unified `org_node` table**, with the six containment tables hanging off it.
The cleanest answer to "what does a singular `scope_node_id` point at", and it
would make this column a single foreign key. Rejected for scope and for timing:
it is a redesign of E0-05's shipped containment schema, it needs a decision about
whether `org_node` owns identity for the six tables or merely mirrors them, and
E0-22 had an open spec question at the time about how many institutions a
deployment holds (answered on 2026-08-18: exactly one, SPEC §8, enforced since
2026-08-20 by [ADR 0072](0072-one-institution-is-a-unique-index-on-a-constant.md)).
This ticket could not settle that, and a half-built node table would be worse
than either shape. It stays available — collapsing five columns into one is
a later migration, and the grain rule survives it as a check over the node's
kind.

**An opaque id whose kind is implied by the role.** Ruled out by E0-09's own
scope, and the reason is the sentence above it: the grain rule must be enforced,
and an id with no kind beside it gives a constraint nothing to compare against.

## Consequences

**The grain rule is enforced by the server for everyone**, including a seed
script, a roster sync, E9's CSV import and a superuser session. Each arm is
independently verified: loosening any single `WHEN` — chair, lead faculty, Care —
turns the matching test red, measured by mutation.

**Five columns are mostly null.** That is the visible cost. Postgres stores a
null in the row's null bitmap rather than in a column, so five nulls cost bits,
not bytes; the real cost is that readers must know that exactly one is set, which
the constraint states and the model docstring repeats.

**A query that wants "the node this is scoped to" must coalesce five columns.**
E0-11 and E9 will write that expression, probably once, in the purview resolver.
This is the shape a unified node table would improve, and the reason the door is
left open above.

**`num_nonnulls(...) = 1` and `ELSE false` shipped as hardening that no test
asserted.** Both were mutated, both survived, and both were declared rather than
quietly kept: no test wrote two scope columns, and the `ELSE` is unreachable while
the enum holds exactly the labels the `CASE` names. They stayed because the
failure they prevent — a role scopeable to anything, or a grant naming two nodes —
is silent.

Both are asserted now, in `tests/integration/test_role_assignment_graph.py`. A row
carrying two scope columns and a row carrying none are each written and refused.
The first is what needed a test rather than a note: a chair carrying a second
scope column satisfies every other rule on the table, and the coalesce above then
resolves it to whichever level that expression reaches first, so the failure is a
widened purview and not an error. The `ELSE` is held closed from the other end —
every label `pg_enum` holds for the role type must appear in the constraint's
definition — because the failure that reaches it is a role added later without an
arm, and no row this suite can write provokes that.

**Adding a role means editing this constraint**, and forgetting to makes the role
unwritable rather than unrestricted. That is the intended direction of failure.
