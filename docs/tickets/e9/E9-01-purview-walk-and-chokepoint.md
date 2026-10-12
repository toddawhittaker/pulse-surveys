# E9-01 — The purview walk and its chokepoint

**ID:** E9-01
**Branch:** `e9/purview-walk-and-chokepoint`
**Depends on:** none
**Lane:** heavy ⚠
**Why this lane:** it writes the purview computation in
`backend/app/services/authz.py` and a dependency in `backend/app/api/deps.py`,
both heavy paths, and SPEC §14.3 marks the purview computation ⚠. It adds
`invariant`-marked properties for §4.1 item 2.
**Size:** L
**Security-relevant:** the purview decides everything every leader reads in
E9. A defect here hands a lead a sibling lead's courses, a chair another
department, or anyone the institution; or lets a request name someone else's
scope.

## Context

SPEC §2.1: "Purview(assignment) = own grant ∪ purviews of all assignments
transitively reporting to it", with the own grant restricted by role grain,
and a Lead Faculty's grant only the courses they lead, "never sibling leads'
courses, at any point in the union". E0-11 shipped the own grant
(`_own_grant_of`) and left the union as a seam that raises
(`transitive_purview`, ADR 0003). `resolve_scope` exists and has no caller.
This ticket writes the walk and makes it the only way a leadership read gets
a scope.

**The walk.** Breadth-first over `assignment_scope.reports_to` (v002), from
the assignment down through every assignment that reports to it, at most six
levels (§2.1: the graph is at most six assignments deep). It batches the own
grant queries one level at a time rather than one per assignment. It walks by
assignment id, never by person.

**The lead clamp.** A `LEAD_FACULTY` assignment's purview is its own grant
only, whatever reports to it. An instructor assignment that reports to a lead
from a sibling lead's course therefore adds nothing to that lead, nor to
anyone above that lead through it. This is what "at any point in the union"
means.

**The leadership scope (ruling 4).** A leadership read's scope is the union
of the purviews of the person's leadership assignments only: `LEAD_FACULTY`,
`CHAIR`, `ASSISTANT_DEAN`, `DEAN` and `VP_ACADEMICS`. `INSTRUCTOR`, `CARE` and
`ADMIN` assignments contribute nothing. `ActorScope` gains `grants`: one
`(assignment id, role, purview)` per leadership assignment, which gives the
tree's roots and the by-lead gate in E9-07 without a second walk.

**The chokepoint.** A new dependency in `api/deps.py`, `leadership_scope`,
resolves the scope from the verified session's own `person_id` and nothing
else: no route takes a person, assignment or scope id from the request to
resolve a scope. A sweep checks that `resolve_scope` (or whatever replaces
it) has no caller outside that dependency and the services it hands the scope
to.

**Also here:** `course_leads(course_ids)` answers each course's mapped lead
person in one query, for E9-07's tree labels. `leadership_grant_covers` (ADR
0108) uses the full leadership purview, so an assistant dean's launch into a
supervised chair's department binds. The chair's walk to courses with a lead
is written once (it is written twice today, in `lead_review_courses` and
`chaired_courses_with_a_lead`).

Read first: SPEC §2, §2.1 and §4.1 item 2; ADRs 0003, 0044, 0046 and 0108;
`services/authz.py` whole; `api/deps.py`'s `require_leadership`;
`tests/integration/test_supervision_graph_properties.py` (its generators are
reused); `scripts/seed.py`'s worked example.

## Owns

- `backend/app/services/authz.py`: `transitive_purview` written; the
  leadership scope; `ActorScope.grants`; `course_leads`;
  `leadership_grant_covers` on the full purview; the chair walk once.
- `backend/app/api/deps.py`: `leadership_scope`.
- The Hypothesis properties, `invariant`-marked, beside the existing
  supervision-graph properties.
- The caller sweep.
- ADR **0199** (the walk, the clamp, the leadership-only union, the
  chokepoint). It supersedes ADR 0003 in part and amends 0046 and 0108, each
  with a line pointing at it.

## Reuse, do not rewrite

`Purview`, `ActorScope`, `CONTAINMENT_LEVELS`, `_own_grant_of`,
`_lead_faculty_grant`, `_nodes_beneath`, `_ASSIGNMENTS_OF_PERSON` and
`resolve_scope`'s skipping of Care and Admin in `services/authz.py`;
`verified_session` and `person_of`; the graph generators in
`tests/integration/test_supervision_graph_properties.py`.

## Done when

1. **The worked example resolves.** On the seeded graph, the assistant dean's
   leadership scope holds exactly PSYC 110 and its sections, plus the Math and
   Biology departments' whole subtrees, and nothing else of Psychology. The
   Psychology chair's scope holds the Psychology department and not the Math
   or Biology departments. Asserted against named nodes, with a present twin
   for each absent one.
2. **Transitive, not one level.** In a generated chain
   `LEAD → CHAIR → ASSISTANT_DEAN → DEAN → VP`, each assignment's purview
   contains every purview below it. A test with a chain of six assignments
   reaches the bottom. The number of queries grows with the depth and not
   with the number of assignments: a forest ten assignments wide and one a
   single assignment wide, both of the same depth, issue the same number of
   queries (counted).
3. **The lead clamp.** An `INSTRUCTOR` assignment in sibling lead B's course
   that reports to lead A adds nothing to A's purview and nothing to A's
   chair's purview through A. The same section reaches the chair when it lies
   in the chair's own department, through the department grant only.
4. **Sibling-lead disjointness, generated.** Over generated forests and
   mappings (assistant-dean insertions, two-hat people, cross-department led
   courses, instructor edges into leads), no `LEAD_FACULTY` assignment's
   purview contains a course mapped to another person. Marked `invariant`.
   The generator draws the instructor-edge-into-a-lead case, and a test
   asserts that it does (MISTAKES entry 15).
5. **Parent covers child, generated.** For every edge, the parent's purview
   contains the child's clamped purview. Marked `invariant`.
6. **The purview equals an independent computation, generated.** Over
   generated forests and mappings, for every assignment, its purview equals a
   set the test computes on its own: the assignment's own grant, together with
   the clamped purviews of its children (a child `LEAD_FACULTY` assignment
   contributing its own grant only). The person's leadership scope equals the
   union of those sets across their leadership assignments. The expected sets
   are computed by the test from the generated graph, never by calling the
   code under test (MISTAKES entry 19), and the generator's draw of an
   instructor edge into a lead is asserted as in done-when 4. This catches a
   walk that clamps a lead's own result but passes the unclamped set up to
   the chair. Marked `invariant`.
7. **Care and Admin never contribute, generated.** Adding a `CARE` or `ADMIN`
   assignment to any person in a generated forest changes no leadership scope.
   Marked `invariant`.
8. **Instructor hats stay out (ruling 4).** A chair who also teaches a section
   in another department has a leadership scope without that section, and the
   section is reached through the instructor session only.
9. **Two `LEAD_FACULTY` assignments under two chairs.** A person who holds two
   lead assignments, each reporting to a different chair, hands both chairs
   every course mapped to that person, because the mapping is per person. Test
   it as the spec's literal meaning, and say so in ADR 0199.
10. **The chokepoint refuses any other id.** No leadership route accepts a
   person, assignment or scope id that decides whose scope is resolved. A
   request carrying another person's id in a query string, a path segment or
   a body is answered from the session's own person. The caller sweep finds
   `resolve_scope` called only from `leadership_scope` and the services it
   passes the scope to, with a planted second caller going red and the
   allowed caller found as a control (MISTAKES entry 35).
11. **The launch binding follows the purview.** `leadership_grant_covers`
    admits the assistant dean's launch into a section of a supervised chair's
    department, and still refuses a lead's launch into a sibling lead's
    course (the existing test stays green unchanged).
12. **The chair walk is written once.** `lead_review_courses` and
    `chaired_courses_with_a_lead` share one statement of the walk to a
    department's courses with a lead. Their existing tests stay green
    unchanged.
13. **`transitive_purview` no longer raises,** and every test that asserted
    the seam raised is rewritten in its own commit, saying in the pull request
    why the old assertion is now wrong (MISTAKES entry 22).
14. **The records match.** ADR 0199 is written and indexed; ADR 0003, 0046 and
    0108 each gain a line pointing at it. Comments in `authz.py` that say
    "E9 lands it" or name a ticket are rewritten to say what the code does.

## Shares files with

- `api/deps.py`: 02 (`require_admin`) and 04 (the revoked-session check).
- `services/authz.py`: 04 (the landings at a door).
- `docs/adr/README.md`: every ADR owner.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 15, 35, 46 and 53.

## Known traps

- **Entry 15.** A generator that never draws an instructor edge into a lead
  never tests the clamp. Assert the generator's coverage.
- **Entry 1.** ADR 0003, 0046, 0108 and the `authz.py` docstrings all say the
  union is E9's and raises. Grep the fact ("raises", "E9 lands", "deferred"),
  not the function name.
- **Entry 46.** At least one test resolves the scope through the connection
  production uses, not the migrating engine.
- **Walk by assignment.** A walk by person would merge a two-hat person's
  instructor edge into their lead hat.

## Not in this ticket

- The tree, labels and roots (07).
- Staff names (03).
- The switcher (04).
- Who reads the review queue and the exclusion log (09).
