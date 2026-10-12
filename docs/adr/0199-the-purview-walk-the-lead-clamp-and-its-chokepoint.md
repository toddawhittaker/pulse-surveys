# 0199 — The purview walk, the lead clamp, the leadership-only union, and its chokepoint

**Status:** Accepted. Supersedes [ADR 0003](0003-deferred-authz-seams-fail-closed.md) in part (the transitive union no longer raises); amends [ADR 0046](0046-a-purview-is-a-materialised-node-set-per-containment-level.md) and [ADR 0108](0108-the-leadership-limb-is-scoped-by-the-launchers-own-grant.md).
**Date:** 2026-10-12
**Ticket:** [E9-01](../tickets/e9/E9-01-purview-walk-and-chokepoint.md)

## Context

[SPEC §2.1](../SPEC.md) defines a purview as an assignment's own grant together
with the purviews of everything transitively reporting to it, with a Lead
Faculty's grant "only the courses they lead (never sibling leads' courses, at any
point in the union)". [§5.5](../SPEC.md) makes a leadership view the union of
leadership assignments only. E0-11 shipped the own grant and
left the union a seam that raised (ADR 0003). The spec does not say how the walk
reads the graph, what "at any point in the union" does to an instructor
assignment that legally reports to a lead from a sibling lead's course, or where
a request's scope is resolved.

## Decision

- **The walk.** `authz.transitive_purview(session, assignment_id=…)` walks
  `reports_to` breadth-first from the assignment, by assignment id and never by
  person, one statement per level for the whole level, and unions the own grants
  of everything it reached. The own grants are read by `_own_grants_of`, which
  is now the one statement of the role grain and reads a fixed number of
  statements for any set of assignments. So the cost grows with depth, not width.
  A chain deeper than the rank rule allows (ADR 0044, six assignments) is refused
  rather than walked.
- **The lead clamp.** A `LEAD_FACULTY` assignment's purview is its own grant only.
  The walk reaches a lead and never passes through it, so nothing beneath a lead
  reaches the lead or anyone above it through the lead. A chair still reaches a
  section in their own department through the department grant.
- **The leadership-only union.** `authz.resolve_scope(session, person_id=…)`
  unions `transitive_purview` over the person's `LEAD_FACULTY`, `CHAIR`,
  `ASSISTANT_DEAN`, `DEAN` and `VP_ACADEMICS` assignments, and `ActorScope.grants`
  carries one `LeadershipGrant(assignment_id, role, purview)` for each. A person
  with no leadership assignment resolves to an empty scope. `leadership_grant_covers`
  answers on the same union, so an assistant dean's launch into a supervised
  chair's department binds.
- **Two lead assignments under two chairs.** The Lead Faculty mapping is per
  person, so each lead assignment's grant is every course mapped to that person,
  and both chairs receive all of them. This is the spec's literal meaning.
- **The chokepoint.** `app.api.deps.leadership_scope` is the only caller of
  `resolve_scope` under `backend/app/`. It depends on `require_leadership` and
  takes the person from the verified session, declaring no other request input.
  A unit sweep over the source tree holds the single caller.

## Alternatives rejected

- **The formula read literally, without the clamp.** An instructor on lead B's
  course reporting to lead A would hand A, and A's chair through A, a sibling
  lead's section — the case §4.1 item 2 forbids.
- **A clamp on the lead's own answer only.** Clamping the lead's result while
  passing the unclamped subtree up to the chair would still leak the section to
  the chair. The walk stops at the lead instead.
- **A walk by person.** It would merge a two-hat person's instructor edge into
  their lead hat.
- **One recursive SQL statement.** Allowed by the ticket and cheaper, but a
  second statement of the clamp in SQL would be a second place for it to be got
  wrong; the Python walk keeps the clamp in one readable loop.
- **A per-assignment own grant inside the walk.** Its cost grows with the width
  of each level.
- **A scope dependency that accepts a person id.** Any route could then name
  whose scope it reads.

## Consequences

- Every leadership read gets its scope from `leadership_scope`; a new caller of
  `resolve_scope` turns the sweep red.
- `lead_review_courses` and `chaired_courses_with_a_lead` still read own grants
  only; who reads the review queue and exclusion log over the full purview is
  E9-09's.
- The Lead Faculty mapping carries no assignment, so a person cannot lead a
  course under one chair and not under another.
