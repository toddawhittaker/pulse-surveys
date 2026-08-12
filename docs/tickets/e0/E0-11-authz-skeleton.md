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

## Acceptance criteria

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
      access" and look like it works.
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
