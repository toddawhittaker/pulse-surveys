# Pulse Surveys — Data Model: Org Hierarchy, Roles, and Reporting

> Frozen design-session input (an earlier standalone copy of SPEC_ADDITIONS.md Part A), written before `docs/SPEC.md` existed; where they disagree, the spec governs (known case: §2.1 — students hold no role assignment; their access resolves from enrollment).

Spec input for the data model behind the Leadership Roll-up, Instructor Monday Report, Student Survey, and Student Results views. Written to be machine-readable; entity and field names are suggestions, not mandates.

## 1. Core principle

**People are not roles.** A person holds one or more *role assignments*, each scoped to a node in the org hierarchy. Deans and chairs can also be lead faculty; an assistant dean can hold a lead-faculty assignment while supervising a chair. Every view in the product is resolved from an assignment (or a union of them), never from a person "type."

Two separate structures, deliberately decoupled:

1. **Org containment hierarchy** — what contains what. Used for navigation, aggregation, and drill-down.
2. **Supervision graph (reports-to)** — who answers to whom. Used to compute purview (what a viewer may see) and escalation routing.

Containment alone cannot express the real reporting structure (see §5); do not derive one from the other.

## 2. Org containment hierarchy

```
Institution
└── College                 (e.g., College of Sciences)
    └── Department          (e.g., Biology — a grouping of prefixes)
        └── Prefix          (e.g., BIOL, MARS, MATH, STAT, MIS)
            └── Course      (e.g., BIOL 2150 — Principles of Ecology)
                └── Section (term instance, e.g., R3WW in Fall 2026)
```

- A department groups one or more prefixes (Math may hold MATH, STAT, MIS).
- Courses belong to exactly one prefix; sections belong to exactly one course and one term.

### Section (term instance)
| Field | Notes |
|---|---|
| code | `{startLetter}{ordinal}{modality}`, e.g. `Q1WW`, `F3WW`, `Q2FF` |
| startLetter | Encodes length + start date within the term (see §7) |
| ordinal | Nth section of that start within the course |
| modality | `WW` online, `FF` face-to-face |
| term | e.g. Fall 2026 (begins 8/17/2026) |
| startDate / endDate | Derived from startLetter + term calendar |
| lengthWeeks | 3, 6, 8, 10, 12, 15, 16, 18 |
| instructorAssignment | The teaching instructor (usually adjunct; see §3) |

## 3. Role assignments

```
RoleAssignment {
  id
  personId
  role        // VP_ACADEMICS | DEAN | ASSISTANT_DEAN | CHAIR | LEAD_FACULTY | INSTRUCTOR | CARE | ADMIN
  scopeNodeId // org node the assignment attaches to
  reportsTo   // RoleAssignment id (nullable only for the top of the graph) — see §4
}
```

Scope attachment by role:
- `VP_ACADEMICS` → institution
- `DEAN` → college
- `ASSISTANT_DEAN` → college (same node as the dean; authority comes from the supervision graph, not the scope)
- `CHAIR` → department
- `LEAD_FACULTY` → **course** (the natural grain: one lead per course). A lead's practical scope is the set of courses they lead, which may span prefixes and departments. Prefix-level things (policy, exclusion log) resolve to the lead(s) holding courses under that prefix.
- `INSTRUCTOR` → section (per term; ~95% adjuncts, distinct from the full-time faculty who hold the leadership roles)
- `CARE` → institution (Office of Community Standards; receives welfare escalations regardless of hierarchy)

A person may hold any combination (chair + lead faculty; assistant dean + lead faculty; dean + lead faculty). Each assignment is a separate row with its own `reportsTo`.

## 4. Supervision graph (reports-to)

`reportsTo` edges connect **role assignments, not people and not org nodes**. Canonical chain:

```
INSTRUCTOR(section) → LEAD_FACULTY(course) → CHAIR(department) → DEAN(college) → VP_ACADEMICS
```

But the graph must allow insertions and exceptions without schema change:

- **Assistant dean insertion:** `CHAIR(dept) → ASSISTANT_DEAN(college) → DEAN(college)`. Some chairs report to the assistant dean, others directly to the dean, within the same college.
- A person wearing two hats has two assignments with two different `reportsTo` edges (e.g., a chair's `LEAD_FACULTY` assignment reports to their own `CHAIR` assignment — self-supervision across assignments is legal and expected).
- The graph is a forest/DAG over assignments. Cycles are invalid. Person-level cycles (A's assignment reports to B's, B's other assignment reports to A's) are legal.

## 5. Purview computation

**Purview(viewer assignment) = own grant ∪ purviews of all assignments that transitively report to it.**

- Own grant: the org subtree under the assignment's scope, restricted by role grain — `LEAD_FACULTY` grants only the courses they lead (never sibling leads' courses), `CHAIR` grants the whole department subtree, `DEAN` the college subtree.
- Union of subordinates: everything visible to any assignment reporting to this one, transitively.

Worked example — the assistant dean:
- Holds `LEAD_FACULTY` on some courses → those courses.
- Has `CHAIR(dept X)` reporting to them → all of department X's subtree.
- Result: **union** of their own led courses plus every supervised chair's department — even though no single org node contains that set. This is why purview must come from the supervision graph, not containment.

View behavior at each purview:
- Multi-role people get a **role/assignment switcher**, or the app renders the union purview with the hierarchy nav rooted at the top-level nodes of the union (multiple roots are fine; the roll-up already renders multi-root trees).
- Lead faculty see **hierarchy view only** — never a by-lead-faculty pivot (they must not see peers' courses). Chair-and-above additionally get the by-lead-faculty drill-down over their purview.
- Tree roots are the highest *useful* nodes: never show a single all-encompassing root row (no "Whole university" for the VP; VP starts at colleges, dean at departments, chair at prefixes, lead faculty at their prefixes-of-led-courses).

## 6. What each level displays (labels)

- College row: name + `N departments · N sections · Dean: {name}`
- Department row: `N prefixes · N sections · Chair: {name}`
- Course row: `N sections · Lead: {name}` (lead name omitted in a lead's own view — redundant)
- Section row: code (`R3WW`) + teaching instructor's name
- Course-level pages (instructor report, student results) carry the Lead Faculty name in the header.

## 7. Term calendar model

- Fall and Spring: 18 calendar weeks (incl. break). Summer: 12.
- Course lengths: 3, 6, 8, 10, 12, 15, 16 weeks (+18-week dissertation).
- Start letters map (length, start date) per term — Fall 2026: 12-week U (8/17), R (9/7), Q (9/28); 6-week E (8/17), F (9/28), H (11/9); 8-week X (start), Y/Z (late, 2-week gap in 18-week terms, overlap in summer, plus a week-5 start in 18-week terms); 10-week S/T; 15-week V/D; 16-week K; 3-week sections numbered 2–7.
- Course-level charts plot **course week** with a quiet term-week sub-label (offset from the section's start letter).
- Aggregate charts plot the **term axis**, one line per start cohort (letter), selectable.
- Comparable benchmarks are past-referencing and same-length: week N of a 12-week course compares to week N of 12-week courses in current and past terms, regardless of start date.

## 8. Routing and escalation (interacts with reports-to)

- Attention rules (trend down 2+ weeks per stream, response rate < 40%, response required + delinquent 48h) surface a section to the assignments whose purview contains it — never ranked, never worded as "underperforming."
- Respond-on-behalf at 96h falls to the section's course `LEAD_FACULTY` assignment (honest attribution as the lead).
- Flagged "harmful" comments split by type: abuse of instructor → the course's `LEAD_FACULTY` review queue; self-harm / student-welfare signals → `CARE`, immediately, regardless of N or anonymity. Severe safety escalations bypass the graph entirely.
- Exclusion log rows are visible at the lead-faculty prefix scope and above (accountability follows supervision).
- Response-required policy is set per prefix by the lead faculty holding courses there; read-only (with attribution) for chair and above.

## 9. Invariants

1. No view may ever widen a student's visibility (no comparables/benchmarks on student surfaces; small-N comment suppression by threshold).
2. A `LEAD_FACULTY` assignment never grants sibling leads' courses, at any point in the union computation.
3. Purview changes require only supervision-graph edits — never schema or UI changes.
4. Aggregate language counts sections, not instructors.
5. Every escalation path terminates at a named assignment, not a person, so personnel changes re-point cleanly.
