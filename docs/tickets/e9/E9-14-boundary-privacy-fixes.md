# E9-14 — Boundary privacy fixes

**ID:** E9-14
**Branch:** `e9/boundary-privacy-fixes`
**Depends on:** 01 to 12
**Lane:** heavy ⚠
**Why this lane:** it changes what the exclusion log serves to each reader, two
`SECURITY DEFINER` functions over the people graph, and the checks on
`audit_log`, and it adds `invariant`-marked tests. Each is a path in
`.claude/heavy-lane-paths.md`. It carries ⚠ because item 5's invariant tests
are written against code that already exists, so they pass on arrival; only
the verifier's mutation battery shows each one can fail.
**Size:** M
**Security-relevant:** item 1 closes a way to put a released comment back in
its week; item 2 closes a state in which a course's harmful comments reach no
review queue; item 3 makes the audit row that keeps a Care grant visible a
rule of the table rather than of its writers.

## Context

The E9 boundary review battery ran on the epic head `464f9773` against `main`
`40d3e24b`. This ticket carries its privacy, data-model and invariant-coverage
findings; E9-15 carries the interface findings and E9-16 the records.

- **Threat model (MED).** The assistant dean, the dean and the vice president
  read the exclusion log over their purview (ADR 0206) and also read the
  section's drill-down, which shows a release batch's comments. A log row whose
  excerpt is withheld still carried the decider's free-text reason and the
  decision date. A reason that paraphrases the comment, beside a date, puts the
  released comment back in its week, which is what SPEC §5.2's withheld
  excerpt and the release's missing week prevent (ADR 0153, ADR 0190).
- **Spec conformance (MED).** "Led" had two definitions: a
  `lead_faculty_mapping` row and a `LEAD_FACULTY` assignment. A course mapped
  to a person with no `LEAD_FACULTY` assignment does not fall to its chair
  (SPEC §2.1), yet ADR 0190's review queue reads only a lead holding the
  assignment, so that course's harmful comments reach no queue at all.
- **Data model (LOW).** Nothing in `audit_log` required an admin write's row to
  carry the role and the scope node ADR 0200 says it records.
- **Privacy and code review (LOW).** `response_loop.section_lead_name` let a
  caller omit the reader's scope; `is_owed`'s docstring named a caller it does
  not have.
- **Invariant coverage (HIGH ×2, MED ×2).** The wider roles' log, the admin
  read routes and definers, and the by-lead pivot were tested only in
  unmarked modules; the attention-card order property was unmarked.
- **Records (LOW).** `moderation.py`'s module docstring named one reach of the
  log; ADR 0174 and `models/audit.py` gave a stale count of actions and
  writers.

Read first: SPEC §2.1, §4, §4.1, §5.2, §6.3 and §8; ADRs 0153, 0174, 0190,
0200, 0204 and 0206; `docs/MISTAKES.md` entries 3, 16, 22, 43, 46, 47 and 53.

## Owns

- Migration **`e9b8c0d2e417`**, `down_revision = "e9e5b7d9f605"`: replaces
  `admin_map_lead_course` and `admin_revoke_role` from
  `views_sql/people_graph_v003.sql`, and adds the two `audit_log` checks; its
  downgrade restores v001's two definitions and drops the checks.
- `backend/app/views_sql/people_graph_v003.sql` (new).

## Done when

1. **A withheld log row names no week to anyone but its decider.** Wherever a
   row's excerpt is withheld and the reader did not make that decision, the
   row's `reason` and `decided_on` are `null`; the members stay on the row,
   nullable. The decider still reads their own reason and date, and a row
   whose excerpt is shown keeps every member. The schema change regenerates
   `openapi.json` and `wire.gen.ts`, and the log row in the frontend draws a
   row with no date. An invariant test drives the log beside the drill-down's
   release for the three wider roles, a lead reading an instructor's decision
   and a chair reading somebody else's, each with its present twin.
2. **A course is mapped only to a Lead Faculty holder.** `people_graph_v003.sql`
   replaces `admin_map_lead_course`, which refuses a person holding no
   `LEAD_FACULTY` assignment with `admin_people.lead_needs_the_lead_role`, and
   `admin_revoke_role`, which refuses to revoke a `LEAD_FACULTY` assignment
   while its person still has mappings with `admin_people.lead_still_leads_courses`,
   carrying the count in the detail as `assignment_has_reports` does. The
   revoke route answers 409 with the count in its sentence; an import line
   naming such a person answers 422 at its line, dry run and apply alike.
3. **`audit_log` holds an admin write's shape.**
   `ck_audit_log_an_admin_write_names_its_role_and_scope`: a `ROLE_GRANTED`,
   `ROLE_REVOKED`, `REPORTS_TO_SET` or `LEAD_MAPPING_CHANGED` row carries a role
   and a scope node, and no other row carries both.
   `ck_audit_log_a_linkage_names_no_scope`: a `WEB_LOGIN_LINKAGE_CHANGED` row
   carries no scope node. Each is tested both ways.
4. **`section_lead_name` takes `scope` as a required keyword**, and E9-12's
   sweep of the staff-name door's callers covers it. `is_owed`'s docstring
   says it is the one-section form of `owed_section_weeks`.
5. **The invariant pass covers what the battery found unmarked.** (a) The wider
   roles' exclusion log: no row or excerpt outside the purview, with an
   own-course twin; a held stream's excerpt withheld; no row from a taught
   section; the review queue answers the three roles 403. (b) Every admin read
   and export route answers a Lead Faculty session and an instructor session
   403 with no data (admin 200 control), and each admin read definer called
   with a non-admin key on `pulse_app` returns no rows. (c) The by-lead pivot
   is never answered to a lead: the tree has no by-lead group, and a lead's
   request for a sibling's by-lead or no-lead node answers as a missing node
   (chair 200 control). (d) The attention-card order property test is marked
   `invariant`.
   **Item (e) is dropped.** The battery asked for the drill-down's context bar
   as its own copy surface owing no confidentiality line. Its words already sit
   under the `leadership_rollup.` prefix, a surface that owes no line, and
   `DrillDown.test.tsx` already asserts the report's line once on the page.
6. **The records match.** `moderation.py`'s module docstring names both reaches
   of the log (ADR 0206); `models/audit.py` and ADR 0174 give the right count
   of actions and say which functions write rows.
7. **Every new test can fail.** The verifier plants each test's named mutation
   and sees it red, and the named near miss green.

## Not in this ticket

- The interface findings (E9-15) and the remaining records (E9-16).
- Auditing person create and edit, and showing who holds Care when a login
  was linked first: carried to E10's access log.
