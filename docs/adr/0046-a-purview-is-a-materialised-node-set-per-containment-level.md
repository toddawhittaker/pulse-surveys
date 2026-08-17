# 0046 — A purview is a materialised, downward-closed node set per containment level

**Status:** Accepted
**Date:** 2026-08-17
**Tickets:** E0-11

## Context

[SPEC §2.1](../SPEC.md) says what a purview *is*: "**Purview(assignment) = own
grant union the purviews of all assignments transitively reporting to it**, with
the own grant restricted by role grain: a Lead Faculty's grant is only the courses
they lead (never sibling leads' courses, at any point in the union); a chair's is
the department subtree; a dean's the college." It draws the containment hierarchy
as "Institution → College → Department → Prefix → Course → Section", and it is
explicit that purview comes from the supervision graph rather than from containment
— the assistant dean's purview is "own led courses union every supervised chair's
department, a set no single containment node holds".

It says nothing about how that value is represented in code, and the plausible
answers behave differently at the two places it matters: when two purviews are
unioned, and when a read is checked against one.

The other constraint is a grant. E0-10 left `pulse_app` holding `SELECT` on
`public.section_roster` and `public.section_enrollment_count` and on nothing else
— measured, and `identity_grants_v001.sql` says in as many words that "what
`pulse_app` may read is E0-11's decision". So whatever representation is chosen has
to be computable over views this ticket also has to design, under
[ADR 0041](0041-a-read-view-ships-as-an-immutable-versioned-sql-file.md).

## Decision

**A `Purview` is six `frozenset`s of ids, one per containment level**, on a frozen
dataclass, with `union` joining them level by level and returning a new value.

**It carries no capability.** `ActorScope` is what a caller receives —
`person_id`, `purview`, `holds_care`, `n_threshold` — and Care lives there, beside
the purview rather than in it.

**The own grant is materialised**: `own_grant` resolves an assignment to the actual
ids of every node it reaches, at the moment it is asked, rather than returning a
predicate or a query fragment to be composed into a later `WHERE` clause.

**It is downward-closed by construction.** An own grant holds the node an
assignment is scoped to and every node beneath it in the containment hierarchy, and
never a node above it. A lead's grant is the exception that proves the rule: it
holds the courses the Lead Faculty mapping gives them and those courses' sections,
and **no `prefix_ids`**.

**Three views make it computable on the application connection**, each a versioned
`.sql` file executed by one revision:

| view | answers |
|---|---|
| `public.assignment_scope` | one assignment, its scope node, its edge |
| `public.lead_faculty_course` | which courses a person leads |
| `public.containment_path` | every org node with the chain of ancestors above it |

`containment_path` emits **one row per node at every level**, with the levels at
and below it `NULL`, rather than one row per section carrying five ancestors.

### Why a set of nodes rather than a predicate

A predicate — "this actor may see anything under department X" — is smaller, cheaper
to build, and composes into SQL. It fails at the union.

§2.1's purview is a union of subtrees rooted at unrelated nodes, and the worked
example says so: the assistant dean's purview is "a set no single containment node
holds". As a predicate that is a disjunction that grows a term per supervised
assignment, and E9's transitive walk grows it per assignment at every depth. Every
read then carries that disjunction into the database, where it is a correctness
surface: a term dropped, an `OR` mis-parenthesised, or one predicate composed into
a query that already had a `WHERE` is a widening, in a string, at a call site.

A materialised set makes the check `in`. `section_id not in scope.purview.section_ids`
is one expression that cannot be mis-parenthesised, it is the same expression at
every call site, and it is checked by mypy. The confidentiality decision moves out
of composed SQL and into one comparison.

The second reason is that a predicate cannot be *inspected*. §4.1's invariants are
statements about what an actor can reach, and a test can compare two purviews for
disjointness — which is what
`test_two_leads_with_courses_under_one_prefix_resolve_to_disjoint_purviews` does —
where two predicates can only be compared by running them.

### Why one set per level rather than one set of nodes

Because a node id alone does not say what it is, and every consumer needs to know.
§2.1's navigation trees have different roots per role — "VP starts at colleges, dean
at departments, chair at prefixes" — and its display labels are level-specific:
"department rows `N prefixes · N sections`", "course rows `N sections · Lead:
{name}`". A single opaque set would have every consumer re-deriving the level of
each id, which means every consumer re-joining containment.

Six sets also make a wrong answer legible. A chair whose purview carries
`college_ids` is holding every sibling department in that college, and that is a
one-line failure in a whole-value comparison rather than something you find by
expanding a tree. The tests compare all six at once for exactly that reason.

### Why the own grant is materialised rather than lazy

The alternative is to resolve on demand — hold the assignment and answer
`contains(node)` by querying. It is attractive because it does no work for a read
that never happens, and it is rejected on two counts.

**It puts a query behind every check**, including inside loops a screen writes
without knowing. A roll-up rendering 200 sections would issue 200 containment
queries.

**It makes the scope a live object rather than a value.** A purview resolved once
and frozen is the same answer for the whole request; one that queries per check can
answer differently at the start and end of a request if the graph changes under it,
and nothing records which answer a given row was admitted by. §4.1 item 6 — "no view
may ever widen a student's visibility relative to these rules" — is easier to hold
when the scope is a value computed once at a known point.

The cost is real and is stated: a VP of Academics' own grant is every node in the
institution, materialised. On the seed data that is trivial; at a few thousand
sections it is a few thousand UUIDs in memory per request, which is fine; at a scale
where it is not, the fix is a per-level cap or a lazy variant for
institution-scoped roles, and it is a change to this record rather than to any
caller, because the surface is `in`.

### Why frozen

`Purview` and `ActorScope` are both frozen, and mutation raises. This module is the
single chokepoint SPEC §13 puts every entry point through; a mutable purview means a
router, a Celery task or E9's MCP server can add a node to the scope it was given
and then read with it, with nothing in the chokepoint involved in the decision.
`union` returning a new value rather than widening in place is the same rule at the
one operation that could break it.

### Why Care is not a field on `Purview`

§2 makes the rule and gives the reason: "**Care is deliberately not composable**
with reporting roles — its sole power is the threat queue, kept isolated so safety
re-identification never rides alongside routine oversight access."

A union is the operation that would carry it. If `Purview` had a `holds_care`
field, `union` would have to decide what to do with it, and every answer is wrong:
`or` composes the capability, `and` silently drops it, and carrying the left
operand's makes the result depend on argument order. Keeping it off the value means
the question never arises — six sets of ids union to six sets of ids, and there is
nothing else in there. The field the tests check for is absent, and so is anything
that would smuggle it in under another name.

`own_grant` on a `CARE` assignment therefore raises rather than answering, because
the only way a union could widen is if something handed it a Care-derived purview,
and that is where such a value would have come from. `resolve_scope` skips a `CARE`
row instead — a person holding a Care hat and a teaching hat is ordinary and §2.1
calls it legal, and it is capabilities that do not compose, not people.

### Why `containment_path` is one row per node

The obvious view is one row per section with its five ancestors, and it is wrong in
a way that is invisible until it matters: a prefix with no courses, or a course
with no sections, contributes no section row and drops out of a chair's grant
entirely. §2.1's display labels count prefixes separately from sections, so a
prefix that exists and is not in the purview is a row a screen cannot render and
nobody can explain.

One row per node at every level means a childless node answers for itself, and the
read is uniform: the descendants of a node are the rows whose column at that level
holds its key, and the grant is the non-`NULL` ids at the levels *below* the one
the assignment is scoped to.

### Why a lead's grant has no `prefix_ids`

ADR 0025 refuses a `LEAD_FACULTY` assignment a prefix-shaped scope precisely
because "it would grant the lead every course under that prefix, sibling leads'
courses included, which is §4.1 invariant 2". A purview that listed the prefix
invites exactly the reading the scope column was denied — whatever expands that
node holds the other lead's courses, and a tree renderer, a benchmark comparison
set or E9's union is entitled to expand it.

§2.1's "tree roots are the prefixes of their led courses" is a statement about where
a *navigation tree starts*, computed from the courses, not about what the lead
holds. The two are different questions and this value answers the second.

### Why the courses come from the mapping and not from the assignment

§2.1 puts "one lead per course" on the Lead Faculty mapping, and
`RoleAssignment`'s own docstring settles it from the other end: "a purview resolver
reads the mapping to decide which courses a lead holds, and reads this table only
for the edges."

That is not a preference between two equivalent sources. E0-09 measured that
`role_assignment` accepts two `LEAD_FACULTY` rows on one course, and accepts a
`LEAD_FACULTY` row on a course whose mapping names somebody else;
`lead_faculty_mapping` carries `UNIQUE (course_id)`, so it has exactly one answer
per course. ADR 0025 says the assignment table's grain rule is "necessary and
**not** sufficient" for §4.1 invariant 2 — it stops a lead being scoped above a
course and it does not make the course theirs.

## Alternatives rejected

**A SQLAlchemy query filter or a `ScopedSession` that rewrites every statement.**
The idiomatic answer, and it would make bypassing harder than a function call does.
Rejected because the read paths are `text()` statements against views (ADR 0041,
and `views_sql/queries.py` returns frozen rows rather than ORM entities), so there
is no ORM query for a filter to attach to — and adding one would mean mapping the
views, which E0-10's criterion excludes in as many words.

**A single set of `(level, id)` pairs.** One field instead of six, same
information. Rejected because every consumer then filters by level on every access,
the type says nothing about which levels exist, and a whole-value comparison in a
test prints one large set rather than naming the level that moved.

**Storing the resolved purview**, in a table or a cache keyed by person. Rejected
as premature and as a second copy of a derived fact: purview changes whenever an
assignment, an edge or a mapping changes, so a stored copy needs invalidation on
five tables, and a stale purview is a widening that nothing reports. Worth
revisiting only with a measurement behind it.

**Letting `own_grant` answer for a `CARE` assignment with an empty purview.** True
in a sense — Care supervises nothing — and rejected because it is
indistinguishable from a lead with no mapped courses, so a caller would union it,
get its own grant back, and the rule §2 states would be enforced by nothing. This
is ADR 0003's argument about the deferred union, arriving at a different function
for the same reason.

## Consequences

**The scope is a value, so it can be logged, compared and passed.** `ActorScope` is
serialisable in principle and carries no credential and no name — six sets of node
ids, a person key, a boolean and an integer — so a future request log or an audit
record can hold what an actor's scope was without holding anything §4 protects.

**A purview for an institution-scoped role is large.** Stated above with the
threshold at which it stops being fine and what the fix would be. Nothing measures
it today, and this record is where the number goes when somebody does.

**Three more views are now immutable under ADR 0041.** A column added to any of
them costs a `_v002.sql` file and a revision, which is the price of that record and
is why `assignment_scope` already carries `reports_to` — E9 walks that edge, and
paying for the column now is cheaper than the first migration E9 would otherwise
have to write.

**`alembic check` vouches for none of it.** It reads neither `pg_class` for views
nor ACLs, so a missing view or a missing grant leaves the drift gate clean. The
integration tests running as `pulse_app` are the only reader — which is why
`test_own_grant_follows_the_role_grain.py` and
`test_a_scoped_reader_refuses_what_is_outside_the_purview.py` use the
`application_session` fixture rather than `db_session`, and why a "permission
denied" there is a real half of the criterion rather than an obstacle to it.

**`prefix` is a level in the value and the root of no role's grant.** No role in
§2.1's scope table is scoped to a prefix (ADR 0025 removed the column for that
reason), so `prefix_ids` is only ever populated by a chair's or a wider role's
descent. The level exists in `Purview` because §2.1's hierarchy has six levels and
a chair's grant genuinely holds prefixes; `_DESCENDANTS` carries a statement for it
for uniformity and nothing calls it.
