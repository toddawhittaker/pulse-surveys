# E0-11 — Authorization skeleton

**ID:** E0-11
**Branch:** `e0/authz-skeleton`
**Depends on:** E0-09, E0-10

## Context

`backend/app/services/authz.py` is the single chokepoint every entry point
passes through — HTTP, Celery jobs, and the future MCP server (§13,
`CLAUDE.md`). E0 builds the shape of that chokepoint and the role-grain rules,
not the full transitive purview computation; the DAG union with
Hypothesis-generated supervision graphs is E9's work and is explicitly deferred.

Read first: SPEC §2.1 (purview definition and role grain), §13 (why routers stay
thin), §4.1, and the roles section of `CLAUDE.md`.

## Scope

- `backend/app/services/authz.py` with the interface every caller uses: resolve
  an actor's assignments, produce a scope, and apply it to a query. Callers pass
  through this module or they do not read data.
- Own-grant resolution by role grain: a lead's grant is only their led courses,
  a chair's the department subtree, a dean's the college, VPAA the institution.
  Sibling-lead isolation holds at this level even before transitive union
  exists.
- Care is not composable with any reporting role — encode that here, so no later
  ticket can accidentally union it into a purview.
- Care identification: an actor holds Care because they hold a live `CARE`
  role assignment (E0-09), never because of anything in an LTI or OIDC claim.
  The resolver reads the assignment table; it does not read claims for this.
- The resolver returns Care as a *separate* capability rather than as an element
  of the purview set, so that no union operation can ever pick it up. Ticket
  E0-10's Care service asks this module whether the actor holds Care; that is
  the only supported way to ask.
- A `ScopedSession`-style helper or query dependency that makes the
  E0-10 views the default read path and makes bypassing it visibly deliberate.
- The n-threshold guard *interface* — the parameter and the call site — with the
  threshold read from `Settings`. The suppression rules that use it are E4.
- mypy strict already applies to `app/services/`; keep it clean without
  `type: ignore`.

## Out of scope

- Transitive purview union over the assignment DAG, the assistant-dean worked
  example resolving end to end, and property tests over generated graphs — all
  E9. Leave a clearly named unimplemented seam rather than a partial union.
- The multi-role switcher and multi-root navigation (E9).
- Any HTTP router or dependency wiring to a real request (E1).

## Two rules E0-09 left for you, both measured

E0-09 built the supervision graph and its privacy review found two rules that
are **not** enforced by the schema. Neither widens anything today, because no
purview computation exists yet — this ticket is the one that writes it, so this
is where they stop being theoretical.

**1. Edge direction is unconstrained by role.** Nothing stops
`LEAD_FACULTY → LEAD_FACULTY`, which puts one lead's course inside a sibling
lead's purview, or `CHAIR ← VP_ACADEMICS`, which under §2.1's "own grant ∪ the
purviews of all assignments transitively reporting to it" puts the whole
institution inside that chair's purview. Both writes were accepted against the
shipped migration. E0-09's sibling-isolation test asserts the ancestors of the
rows *it* wrote, not that the joining edge is unwritable, so it stays green
against this.

Decide where the rule lives: a role-rank check inside E0-09's trigger, or
enforcement in the resolver. **Either is legitimate; leaving it in neither is
not.** If you choose the resolver, say so in an ADR and amend ADR 0027, because
it currently reads as though the trigger is the whole story.

**2. One lead per course is enforced on `lead_faculty_mapping` only** — a table
`role_assignment` does not reference. Two `LEAD_FACULTY` assignment rows on one
course are accepted, and so is an assignment on a course whose mapping names a
different person. `RoleAssignment`'s docstring names the mapping as
authoritative and ADR 0025 says the grain rule is necessary and **not
sufficient** for §4.1 invariant 2, so the reading is settled — the constraint
keeping the two tables in step is not.

## Acceptance criteria

- [ ] **A `LEAD_FACULTY → LEAD_FACULTY` edge and a role-inverted edge such as
      `CHAIR ← VP_ACADEMICS` are refused**, or the resolver ignores them and an
      ADR says why that is the right place. A test covers whichever you choose.
- [ ] **A lead's own grant has one answer.** Either `role_assignment` cannot
      hold two `LEAD_FACULTY` rows for one course, or the resolver reads
      `lead_faculty_mapping` alone and a test asserts a conflicting assignment
      row changes nothing.
- [ ] Every read helper in the module goes through the E0-10 views; a test
      asserts no code path in `services/` opens a raw session against an
      identity table.
- [ ] A lead-faculty assignment resolves to exactly its own led courses. A
      second lead in the same prefix resolves to a disjoint set — an
      `invariant`-marked test, since it is §4.1 item 2.
- [ ] A chair's grant covers its department's prefixes and no sibling
      department.
- [ ] A Care assignment produces no reporting purview at all, and attempting to
      union it with a reporting assignment raises rather than silently widening.
- [ ] The deferred transitive union is a named, documented seam that raises
      `NotImplementedError` — not a silent empty set that would read as "no
      access" and look like it works. The module docstring explains why it
      raises, per [ADR 0003](../../adr/0003-deferred-authz-seams-fail-closed.md);
      without that, the next contributor "fixes" it.
- [ ] A write to an LMS-owned column is refused at the chokepoint, and the
      refusal is asserted per column rather than once. E0-05 marks those
      columns with an `lms_` prefix ([ADR
      0014](../../adr/0014-lms-owned-columns-are-marked-by-a-name-prefix.md)).
      **Choose the grain deliberately; do not inherit it from the marker.** Two
      earlier drafts of this criterion each got this wrong in a different
      direction — the first claimed the chokepoint closes ADR 0014's open half,
      the second claimed the prefix is the chokepoint's only possible signal.
      Neither is right, and the second is the more dangerous, because it records
      an unprefixed LMS-owned column slipping through as expected behaviour.

      SPEC §2.1's ownership list is *courses, sections, section codes,
      enrollments, teaching instructors*. Four of those five live on `course`,
      `section` or `enrollment`, so a **table-grained** refusal answers most of
      §2.1 without reading a column name, and would catch the unprefixed column
      a name-based check cannot.

      **Establish where the teaching-instructor link lands before choosing.**
      It is the item that may not live on those three tables: §2.1's chain is
      `INSTRUCTOR(section) → LEAD_FACULTY(course) → …` over **role assignments**,
      and §8 puts those on `role_assignment`. If the link is an assignment row,
      a table-grained refusal over `{course, section, enrollment}` leaves an
      application write path able to create or edit an LMS-sourced `INSTRUCTOR`
      assignment — and that is not a stale attribute, it is a **purview grant**,
      since §2.1 computes purview from exactly those rows. Table grain's other
      failure is the mirror of column grain's: it breaks the day a Pulse-owned
      writable column lands on one of those tables, and `course.level` is
      already a non-LMS column there, saved only by being unwritable. A
      **column-grained** refusal over the `lms_` prefix has the omission gap
      instead.

      Pick one, say which in the pull request, and say what the chosen grain
      does not catch. [E0-21](E0-21-review-debt.md) carries the residue of
      whichever is chosen.
- [ ] mypy strict passes on `app/services/authz.py`.

## Definition of done

**Tests apply.** Unit tests for each role grain. One `invariant`-marked test for
sibling-lead isolation (§4.1 item 2). A structural test that `services/` never
bypasses the views.

**Docs apply, briefly.** `CLAUDE.md` already states the chokepoint rule; add the
module docstring that tells a future reader why the union is deliberately absent
and which epic completes it.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies and matters here.** Review for a path that widens
scope, for Care composability leaking in, and — most importantly — for whether
the unimplemented union could be mistaken for a permissive default. A
fail-closed stub is correct; a fail-open one is a vulnerability.
