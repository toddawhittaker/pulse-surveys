# E0-09 — Role assignments and the supervision graph

**ID:** E0-09
**Branch:** `e0/role-assignment-graph`
**Depends on:** E0-05, E0-06, E0-08

## Context

People are not roles. A person holds one or more role assignments, each scoped
to an org node, and `reportsTo` edges connect **assignments** — never people,
never org nodes. This is the schema that makes the assistant-dean case
expressible and sibling-lead isolation enforceable. Getting the edge endpoints
wrong here would quietly break purview for the whole product.

Read first: SPEC §2.1 in full — especially the purview definition and the
assistant-dean worked example — plus §8 and the roles section of `CLAUDE.md`.

## Scope

- `backend/app/models/identity.py` (or a sibling module): `role_assignment` and
  `lead_faculty_mapping`.
- `role_assignment` carries `person_id`, `role`, `scope_node_id`, and a nullable
  `reports_to` **referencing another role_assignment**. Enforce the foreign key
  target at the database level; a schema where it could point at a person or an
  org node is a defect.
- Reject assignment-level cycles at write time. Person-level cycles are legal
  and expected — a chair's lead-faculty assignment reporting to their own chair
  assignment must be accepted.
- `lead_faculty_mapping` maps a person to courses they lead, one lead per
  course, enforced by constraint. A course with no mapping resolves to its
  department chair; that resolution is a query concern, not a stored row.
- Role grain constraint: an assignment's `scope_node_id` must reference a node
  of the right kind for its role — a chair scoped to a department, a dean to a
  college, a lead to a course, **Care and Admin to the institution**. Enforce it
  rather than trusting callers.
- **Care is Pulse-owned and assigned only here.** No LTI claim, no OIDC claim,
  and no LMS role may ever produce a `CARE` assignment. The launch or login
  establishes who someone is; this table establishes what they may do, and for
  Care the two must stay strictly separate — a claim-to-Care mapping would let
  an LMS administrator grant themselves identity access, walking past every
  guarantee in §4. Add a test asserting no claim-mapping code path can write a
  `CARE` assignment.
- A `CARE` assignment never carries a `reports_to` edge and is never the target
  of one. It sits outside the supervision graph entirely, because it supervises
  nothing and escalates to nobody (§2.1).
- **A person may hold both a `CARE` assignment and a reporting assignment.** A
  Care staffer who also teaches a section is unlikely but legitimate, and this
  is a deliberate decision: do not add a constraint forbidding it. Non-
  composability is about capabilities, not about people — Care grants no
  reporting purview and no reporting role grants Care. The residual risk is
  accepted, governed by the ethical obligations of the Office of Community
  Standards and by the identity-access audit log.

## Out of scope

- Purview computation over the graph (E0-11 builds the skeleton; the full
  transitive union with Hypothesis-generated graphs is E9).
- The People and reporting admin editor, and CSV import with dry-run diffs
  (E9 / E11).
- The role switcher and multi-root navigation (E9).

## Acceptance criteria

- [ ] `reports_to` is a foreign key to `role_assignment`; a migration attempting
      to point it at `person` or an org table would fail review, and the model
      makes that impossible to do accidentally.
- [ ] Creating a two-assignment cycle is rejected at write time with a clear
      error.
- [ ] Creating a three-assignment cycle is also rejected — test the transitive
      case, not just the direct one.
- [ ] A person holding two assignments where one reports to the other is
      accepted, and a test asserts this explicitly as legal.
- [ ] A second lead-faculty mapping for an already-mapped course is rejected.
- [ ] An assignment whose role and scope-node kind disagree is rejected.
- [ ] A `CARE` assignment scoped to anything other than the institution is
      rejected.
- [ ] A `CARE` assignment with a `reports_to` edge is rejected, and so is an
      attempt to point another assignment's `reports_to` at one.
- [ ] No code path that maps LTI or OIDC claims to roles can produce a `CARE`
      assignment — asserted by test, since this is the escalation that would
      bypass §4 entirely.
- [ ] A person holding both a `CARE` assignment and an instructor assignment is
      **accepted**, with a test asserting it, so nobody later "tightens" this
      into a constraint. The fixture is reused by E0-10 and E0-18.
- [ ] Assignments record which entry doors they permit: launch for every
      reporting role, web login for every role except instructor and student.
- [ ] The assistant-dean shape from §2.1 — lead courses plus supervised chairs —
      can be constructed in a fixture, even though computing its purview is E9.

## Definition of done

**Tests apply, heavily.** Unit tests for cycle rejection at depth 2 and 3, for
the legal person-level cycle, for role-and-scope agreement, and for the one-lead
-per-course constraint. A fixture builder for the assistant-dean shape that E9
will reuse.

**Docs do not apply** beyond model docstrings. The admin editor documentation
comes with the editor.

**AI evals do not apply.**

**Accessibility does not apply.**

**Security review applies and matters here.** This schema is the foundation of
every authorization decision in the product. Review specifically for a path that
would let an assignment's scope widen implicitly, and for whether cycle
rejection can be bypassed by writing rows in a particular order or inside a
single transaction.
