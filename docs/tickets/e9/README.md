# E9 — Leadership hierarchy & roll-ups: build order

Thirteen tickets decompose SPEC §14.3's E9 entry. Each is sized for one focused
session and leaves the repository working: CI green, the Compose stack healthy,
nothing half-wired.

E0 to E8 gave leaders only their own grant: a lead's courses, and a chair's
unled courses (`authz.lead_review_courses`). E9 is the first epic that computes
a purview over the supervision graph at all. `resolve_scope` has no caller
today, and `transitive_purview` raises by design (ADR 0003). So the first wave
builds the four pieces of security code everything else stands on, in
parallel: the purview walk, the admin's writes to the people graph, the
staff-name channel for a set of sections, and the session switch with logout.
The roll-ups, the drill-down, the named-set figures and the editors are built
on top of them.

Say **"build E9, ticket 7"** and it means E9-07.

Branch names follow `CONTRIBUTING.md`. Cut `e9/<slug>` from
`epic/e9-leadership-rollups`, which is cut from `main` at 40d3e24b. One ticket
per branch, one pull request into the epic branch.

**Read before building anything here:** SPEC §2, §2.1, §2.2, §4, §4.1, §5.1,
§5.5, §5.6, §6.2, §6.3 and §13; §14.3's E9 entry; this README's rulings;
`carried-from-e8.md` in this folder, whole, and the older entries it names for
E9 (listed under "Where the carried work lands"); and `docs/MISTAKES.md` whole.
Every ticket names the ADRs it reads. UI tickets (10, 11) read
`docs/DESIGN_BRIEF.md`, `design/tokens.css`, §7.6 and the mockups they name
first.

**Lanes in this breakdown:** seven of the thirteen tickets are heavy, far
more than the usual one in five. That follows from what this epic is: the
purview (01), an identity definer (02), a staff-name definer (03), the
session (04), two tickets that add `invariant`-marked tests (05, 12), and one
that edits the `invariant`-marked student import sweep (08) are each heavy by
`.claude/heavy-lane-paths.md`. SPEC marks the purview computation ⚠,
so 01 carries ⚠ and gets the verifier's mutation battery. 12 carries ⚠ too:
its invariant tests are written after the code they test, so only a mutation
battery shows each can fail. The other six are light. 09, the drill-down, is
light by path but carries privacy weight: it must not add or change an
`invariant`-marked test (those are 12's), and it reads the reader-aware seal
05 builds rather than changing the seal itself. A light ticket whose change
reaches a path in `.claude/heavy-lane-paths.md`, or reds an invariant-marked
test, stops and re-lanes in its pull request.

## Rulings this breakdown builds on

Rulings 1 to 9 are the owner's, made on 2026-10-12 at the start of the epic.
Rulings 1 and 5 depart from the architect's recommendation; the other seven
took it. Decisions 10 to 16 were settled the same day as breakdown decisions
inside the epic's scope. No ticket reopens them. This breakdown's pull request
writes rulings 1, 2, 4, 5, 6, 7, 8 and 9 into SPEC §5.1, §5.4, §5.5, §6.2,
§6.3 and §14.3.

1. **The People editor grants every Pulse-owned role, Care and Admin
   included, to any person, the acting admin included.** A complete editor
   was chosen over one that refuses Care, Admin and self-targeted writes. So the
   separation between running the system and holding the Care queue rests on
   policy and audit on the assignment path, not on code. What code still
   enforces: an Admin session never reads a flagged comment's content or
   reveals an identity, a Care session has no reporting access, and every
   grant and revocation is written to the audit log. E10's Admin access log
   shows each Care grant beside the reveals for the outside review (§6.2).
   Teaching instructors stay LMS-owned, so the editor writes no `INSTRUCTOR`
   assignment (decision 11).
2. **No comments on roll-up pages.** Leaders read raw comments only inside a
   section drill-down, under that section's own per-stream threshold and
   release batches. Pooled comments at course or department nodes are
   declined: subtracting one node or week from another can re-attribute them
   (MISTAKES entry 51).
3. **The staff-name definer answers any live leadership holder, and the Python
   door passes only sections from the reader's resolved purview** (narrowed
   for leads by decision 16). There is no
   SQL copy of the walk, so ticket 03 does not wait on 01. The cost: a Python
   scoping bug would show staff names, never student data, outside the
   purview. Ticket 12 asserts the door passes purview sections only.
4. **Leadership views use the union of leadership assignments only.** An
   instructor assignment is reached through the role switcher and never merged
   into a leadership tree. A lead who teaches a sibling lead's section never
   sees that course in the leadership tree, which matches
   `lead_review_courses` today.
5. **Named-set figures are shown on roll-ups,** in preference to retiring
   the named-set reads. A reader sees a named set's figures only over the set's
   sections inside their purview; the figures meet both benchmark minimums;
   the benchmark seal counts the reader, with their whole purview as what they
   already know (§5.1); and generated properties prove no figure reaches a
   reader from outside their purview. The carried entry on set names that
   differ only in case is resolved in this epic, not carried again (ticket 05).
   Only cohort views and reads that stay unread are retired (decision 10).
6. **Benchmark residues are accepted and recorded:** a set's membership read
   after a week was published, reports of one week read in two terms, and two
   readers pooling what each sees (§5.1). Freezing membership at publication
   would add a table and a writer for a rare admin act.
7. **No assignment end-dating.** Revoking an assignment deletes it, and the
   `RESTRICT` on `reports_to` forces its children to be re-pointed first. No
   spec reader needs assignment history; teaching history already lives in
   `ended_teaching_grant`. §14.3's sentence now says so, and keeps the
   four-copy condition for whoever adds dates later.
8. **Plain logout in E9; back-channel logout moves to E13.** Until then,
   ending the identity-provider session does not end a Pulse session before
   it expires.
9. **Shares at small n are accepted and recorded.** At or near the threshold,
   whole-number shares can tell a student how many classmates rated and, less
   their own rating, how the others rated as a group, never who gave which.
   That is the group size the comment threshold already accepts (§5.4).

Breakdown decisions:

10. **Where the named-set work goes.** Named-set figures are computed through
    the set functions `benchmark_set_week` and `benchmark_set_rating_week`
    over the set's member sections inside the reader's purview, per start
    cohort on the term axis, like a roll-up node's own series. Ticket 05 owns
    the read, the reader-aware seal, the properties and the set-name index,
    and serves the figures on its own route; ticket 11 draws them.
    `named_set_term_axis` is deleted, because it answers the declared length
    and level institution-wide and its view holds no course to narrow by
    (its own docstring says so). After that, the four cohort views
    (`benchmark_cohort_week`, `benchmark_cohort_rating_week`,
    `benchmark_cohort_term_axis` and `benchmark_cohort_rating_term_axis`) have
    no reader under `backend/app/`, and ticket 12 retires them with their
    grants. If a ticket finds it needs one of them, it says so in its pull
    request and 12 keeps that view.
11. **The editor does not write `INSTRUCTOR` assignments.** SPEC §2.1 and §6.3
    make teaching instructors LMS-owned, and nothing LMS-owned is editable in
    Pulse.
12. **The three wider roles.** The assistant dean, the dean and the vice
    president read the exclusion log and the response policy over their
    purview, read-only. The review queue and on-behalf publishing stay with
    the lead and, for an unled course, the chair (§5.2, §5.3). Ticket 09
    replaces ADR 0190's refusal.
13. **The aggregate-ordering gate** (§4.1 item 4) is a property in ticket 07
    (the order of every roll-up list is unchanged when every figure changes)
    and an invariant test in ticket 12.
14. **The cutoff of a named-set or roll-up figure** is the start cohort's own
    week-N window close in the term being viewed. Every section of one start
    cohort shares its window closes, so this is the earliest close in that
    population (ADR 0178) without a cross-term question. Ticket 05 records it.
15. **New copy surfaces are registered by heavy tickets.** The copy inventory
    (`tests/unit/test_the_shipped_copy_inventory_holds_to_items_four_and_five.py`)
    is `invariant`-marked. It requires every copy prefix to sit in
    `GOVERNED_SURFACES` or `SURFACES_WITH_NO_CONFIDENTIALITY_LINE`, and every
    governed prefix to collect at least one key, so placing a new surface is
    an invariant-test edit. Each of E9's three new surfaces is registered,
    with its first keys, by a ticket that is heavy anyway: `admin_people` by
    02, `landing` by 04 (which moves the landing views' sentences out of
    `frontend/src/lib/landings.ts`, the carried entry), and `leadership_rollup`
    by 05. None of the three owes a confidentiality line, because none shows a
    student's words or a single response. The drill-down reuses the
    instructor report's surface and its line. Light tickets file their strings
    under these prefixes; one that needs a new prefix stops and re-lanes.
16. **Ruling 3's broad answer applies to chair and above only.** A reader
    whose only leadership assignments are `LEAD_FACULTY` keeps v001's
    per-section check in the definer (sections of courses they lead), so the
    database still refuses a sibling lead's section to a lead even if the
    Python door passes one. Chair, assistant dean, dean and VP readers get
    ruling 3's answer for any section the door passes. This narrows ruling 3
    for leads only, inside its scope; it adds no SQL copy of the walk.

**Facts checked in the code at 40d3e24b, which the tickets build on:**

- The Alembic head is `7f679faf4b8d`, and it is the only head.
- The last ADR is 0198; the next free number is 0199.
- The next MISTAKES entry is 61.
- `authz.resolve_scope` has no caller under `backend/app/`, and
  `authz.transitive_purview` raises `NotImplementedError` (ADR 0003). Every
  leadership read goes through `lead_review_courses`.
- `resolve_scope` unions the own grants of every reporting assignment,
  `INSTRUCTOR` included, and skips Care and Admin. An assistant dean's own
  grant is empty (`_GRANT_ARRIVES_THROUGH_THE_GRAPH`).
- `assignment_scope` v002 already carries `reports_to`, so the walk needs no
  new view.
- ADR 0044's trigger refuses an edge whose child does not rank below its
  parent, and `INSTRUCTOR` is the lowest rank, so no edge can sit under a
  teaching grant today.
- `named_set_trend`, `named_set_workload` and `named_set_term_axis` in
  `services/benchmarks.py` have no caller. Of the four cohort views, only
  `benchmark_cohort_term_axis` is read, by `named_set_term_axis`.
- The seed holds the worked example (`scripts/seed.py`): the assistant dean
  supervises the Math and Biology chairs and leads PSYC 110 in Psychology,
  whose chair reports straight to the dean. The mock IdP already seeds an
  assistant dean (`mock-idp/app/seed.py`).
- `api/admin.py` does not exist; SPEC §13 lists it as not built yet.

## Build order

| # | Ticket | Branch | Lane | Waits for | Summary | Merged |
|---|---|---|---|---|---|---|
| 01 | [The purview walk and its chokepoint](E9-01-purview-walk-and-chokepoint.md) | `e9/purview-walk-and-chokepoint` | heavy ⚠ | none | `transitive_purview` over `reports_to`, the lead clamp, the leadership scope resolved only from the verified session, `ActorScope.grants`, `course_leads`, the chair walk written once, Hypothesis properties over generated forests; ADR 0199. | |
| 02 | [The admin gate and the people-graph writes](E9-02-admin-gate-and-people-graph-writes.md) | `e9/admin-gate-and-people-graph-writes` | heavy | none | `require_admin`; admin-checked definers for person, assignment, edge, mapping and web-login linkage writes and the admin's name reads; every Pulse-owned role grantable (ruling 1); revoke deletes (ruling 7); every grant and revocation audited; ADR 0200; migration `e9a1d0c3f201`. | |
| 03 | [Staff names for a set of sections](E9-03-staff-names-for-a-set-of-sections.md) | `e9/staff-names-for-a-set-of-sections` | heavy | none | `section_staff_names` v002, set-based, answering instructors, response authors, lead, chair and dean; leadership readers per ruling 3 and decision 16; the reader's date from the app clock; ADR 0201; migration `e9b2c4d6a802`. | |
| 04 | [The role switcher and logout](E9-04-role-switcher-and-logout.md) | `e9/role-switcher-and-logout` | heavy | none | The landings at this door, a CSRF-protected switch that issues a new session and revokes the old one, logout that revokes, a revoked-session table that purges itself; the `landing` copy surface; ADR 0202; migration `e9c3f5a7b403`. | |
| 05 | [Named-set figures under the reader's purview](E9-05-named-set-figures-under-the-readers-purview.md) | `e9/named-set-figures-under-the-readers-purview` | heavy | 01 | The seal counts a leadership reader; named-set figures over the set's sections inside the purview, on their own route; `named_set_term_axis` deleted; generated isolation properties over named sets; the set-name index; ADR 0203; migration `e9a7c9e1b807`. | |
| 06 | [The people and mapping editor, backend](E9-06-people-and-mapping-editor-backend.md) | `e9/people-and-mapping-editor-backend` | light | 02 | `services/people.py`, `api/admin.py`, `schemas/admin.py`: sorting, paging, the reports-to selector, CSV export and import with a dry-run diff, the web-login linkage field; ADR 0204. | |
| 07 | [The roll-up backend](E9-07-roll-up-backend.md) | `e9/roll-up-backend` | light | 01, 03, 05 | `services/rollups.py`: the whole tree in one payload, hierarchy and by-lead modes, held-only counts and labels, term-axis series per start cohort, rates and workload, the §5.6 attention cards on a set-based owed read, the ordering property; ADR 0205; migration `e9f6c8e0a706` only if `EXPLAIN` asks. | |
| 08 | [The Lead Faculty name on course pages](E9-08-lead-faculty-name-on-course-pages.md) | `e9/lead-faculty-name-on-course-pages` | heavy | 03 | The student read moved to `services/student_results.py` first, as a pure move; the lead's name on the student results and instructor report headers. | |
| 09 | [The drill-down and the wider roles](E9-09-drill-down-and-the-wider-roles.md) | `e9/drill-down-and-the-wider-roles` | light | 01, 05 | The read-only section drill-down through the purview, sealed against the reader; the stored-summary filter on decision sequence; the exclusion log and policy for the assistant dean, dean and VP; ADR 0206; migration `e9d4a6c8e504`. | |
| 10 | [The admin editors, frontend](E9-10-admin-editors-frontend.md) | `e9/admin-editors-frontend` | light | 06 | The People & reporting table and the Lead Faculty mapping table in `routes/admin/`, with the import diff screen. | |
| 11 | [The leadership frontend](E9-11-leadership-frontend.md) | `e9/leadership-frontend` | light | 04, 05, 07, 09 | The tree, the roll-up page, the cohort and named-set selectors, the attention list, the read-only drill-down with its context bar, the switcher and logout, the leadership landing replaced; the carried frontend entries. | |
| 12 | [The §4.1 pass over E9's reads, and the view retirement](E9-12-invariant-pass-and-view-retirement.md) | `e9/invariant-pass-and-view-retirement` | heavy ⚠ | 05, 07, 09 | `invariant`-marked tests over every E9 read path through its route: items 2, 3, 4 and 7; the staff-name door; the four cohort views and their grants dropped; migration `e9e5b7d9f605`. | |
| 13 | [E9 exit](E9-13-e9-exit.md) | `e9/e9-exit` | light | all | The assistant dean from both doors on a fresh stack; the drive where only the university line is withheld; the exit verdict; `../e10/carried-from-e9.md`; SPEC §14.3. | |

## Waves

A dependent ticket may start from its prerequisite's pull request head rather
than wait for the merge.

| Wave | Tickets (in parallel within a wave) | Why it waits |
|---|---|---|
| 1 | 01, 02, 03, 04 | Nothing. Each is security code the rest stands on, and none needs another's code (ruling 3 frees 03 from 01). |
| 2 | 05, 06, 08 | 05 needs 01's purview; 06 needs 02's definers and copy surface; 08 needs 03's set-based names. |
| 3 | 07, 09, 10 | 07 needs 01's purview, 03's names and 05's `leadership_rollup` surface (decision 15); 09 needs 01's scope and 05's reader-aware seal; 10 needs 06's contract. |
| 4 | 11, 12 | 11 draws 04, 05, 07 and 09; 12 tests 05, 07 and 09 through their routes. |
| 5 | 13 | Waits for everything. |

## Counters, allotted now

Each was checked in the tree at 40d3e24b.

- **Alembic.** The single head is `7f679faf4b8d`
  (`20261011_7f679faf4b8d_a_policy_row_covers_one_course.py`). Revision ids
  are allotted now so no two tickets collide. The planned chain below follows
  the ticket order; each ticket builds against the epic head it sees, and the
  ticket that merges second re-points its `down_revision` to the head it finds
  when it merges the epic branch in. A ticket that finds it needs a migration
  not listed here stops and says so in its pull request.

  | Revision | Ticket | Planned `down_revision` | What it does | Heavy by migration? |
  |---|---|---|---|---|
  | `e9a1d0c3f201` | 02 | `7f679faf4b8d` | The people-graph definers, their NOLOGIN owner and grants (`views_sql/people_graph_v001.sql`). | Yes: identity tables and definers |
  | `e9b2c4d6a802` | 03 | `e9a1d0c3f201` | `section_staff_names` v002 and its grants. | Yes: a definer under `views_sql/` |
  | `e9c3f5a7b403` | 04 | `e9b2c4d6a802` | The revoked-session table. | Yes: session |
  | `e9a7c9e1b807` | 05 | `e9c3f5a7b403` | A unique index on a comparison set's normalized name. | No (`comparison_set` is none of the four kinds) |
  | `e9f6c8e0a706` | 07 | `e9a7c9e1b807` | An index on `instructor_response (section_id, week_id, sequence)`, only if `EXPLAIN` over a term-sized seed asks for it. | No |
  | `e9d4a6c8e504` | 09 | `e9f6c8e0a706` (or `e9a7c9e1b807` if 07 adds none) | `weekly_summary` stores the highest decision sequence it saw. | No |
  | `e9e5b7d9f605` | 12 | `e9d4a6c8e504` | Drops the four cohort views and their grants. | Yes: views |

- **ADRs.** **0199** is 01's (the walk, the clamp, the chokepoint; supersedes
  0003 in part, amends 0046 and 0108). **0200** is 02's (the admin's definers,
  every role grantable, revoke deletes, the audit, and the route as the real
  admin check because `pulse_app` asserts the admin's key). **0201** is 03's
  (the set-based name channel; ruling 3 for chair and above and decision 16
  for leads; supersedes 0191 in part). **0202** is 04's (the
  switch and logout). **0203** is 05's (named-set figures, the seal counting
  the reader, the cutoffs, the residues of ruling 6, the set-name index;
  amends 0173 and 0179). **0204** is 06's (CSV keys, and the dry run as an
  apply that is rolled back). **0205** is 07's (the one-payload tree, the set
  functions, the set-based owed read). **0206** is 09's (the drill-down, the
  three wider roles, the sequence filter; amends 0190 and 0194). A number left
  unused is recorded as a gap by 13 and never reused.
- **MISTAKES.** The next entry is **61**.

## Shared files

The ticket that merges second merges the epic branch in first, and resolves by
keeping both sides.

| File | Tickets | How it is shared |
|---|---|---|
| `backend/app/api/deps.py` | 01, 02, 04 | 01 `leadership_scope`; 02 `require_admin`; 04 the revoked-session check in the session read. Different functions. |
| `backend/app/services/authz.py` | 01, 04 | 01 the walk and the scope; 04 the landings at a door for the switch. |
| `backend/app/services/response_loop.py` | 03, 07, 08, 09 | 03 the set-based name door; 07 the set-based owed read; 08 moves the student read out (expect the largest conflict; whoever merges second re-applies its change on the moved code); 09 the summary filter. |
| `backend/app/services/reporting.py` | 08, 09 | 08 the lead's name on the report header; 09 `leadership_report`. |
| `backend/app/services/benchmarks.py` | 05, 07, 09 | 05 the reader-aware seal and the named-set reads; 07 the node series through the set functions; 09 calls 05's seal and changes nothing in it. |
| `backend/app/api/leadership.py` | 05, 07, 09 | One route family each. |
| `backend/app/schemas/report.py`, `schemas/student.py` | 08, 09 | 08 the lead's name; 09 only if the drill-down needs a member. |
| `tests/integration/test_identity_grants.py` | 02, 03, 12 | Each adds its grants' rows. |
| `frontend/src/api/openapi.json`, `wire.gen.ts` | 04, 05, 06, 07, 08, 09 | On conflict, regenerate with `scripts/export_openapi.py` and `npm run gen:wire`; never hand-merge. |
| `frontend/src/router.tsx` | 10, 11 | Different route trees. |
| `docs/SPEC.md` §13 tree | 02, 03, 05, 06, 07, 08, 12 | Each draws the files it adds or removes. |
| `docs/adr/README.md` | every ADR owner | Merge in ADR order; keep both rows. |
| `scripts/seed.py` | 07 or 11 (roll-up data), 13 | Additions only. |

`tests/unit/test_spec_section_13_draws_the_tree.py` reads the filesystem, so a
ticket that adds or removes a backend module draws it in SPEC §13 and edits no
test.

## Process pull requests this epic needs

- **The pinned-date drives.** The older report and moderation drives read
  dates in Fall 2026, the latest 2026-11-23. A `process/` pull request must
  rework them before that date, and E9 is running across it. No E9 ticket
  adds a pinned date.
- **The e2e suite's shared-stack residue** (carried) belongs to the same kind
  of pull request, unless a ticket touches the spec concerned.

## Exit criterion and the tickets that prove it

SPEC §14.3: "the assistant-dean worked example (§2.1) resolves correctly from
either door, and generated-graph properties prove sibling isolation and
transitive unions."

| Piece of the exit | Rests on |
|---|---|
| The assistant dean's purview is their led course plus each supervised chair's department, and nothing of the Psychology chair's department beyond PSYC 110. | 01 (the walk), 07 (the tree), 13 (the drive) |
| The same purview from an LTI launch and from web login, as one stored identity. | 01 (scope from the verified session), 04 (the switch), 13 (both doors) |
| The roll-up shows the term axis with per-cohort lines and a cohort selector, hierarchy mode, and by-lead mode for chair and above only. | 07, 11, 13 |
| A drill-down shows the section's Monday report read-only, with no action, sealed against the reader. | 05, 09, 11, 12 |
| Generated forests prove sibling-lead disjointness, parent covers child, Care contributes nothing, and the assistant-dean union. | 01 |
| Generated named sets prove no figure reaches a reader from outside their purview. | 05 |
| No comment on any roll-up page; comments in a drill-down under the section's own hold. | 07, 09, 12 |

## Where the carried work lands

Only E9-13 edits the carried files' closures. Every other ticket names the
entries it closes in its pull request body, and 13 marks them closed with the
pull request and the merge commit. This breakdown's pull request writes which
ticket each entry lands in beside the entry in `carried-from-e8.md`.

### `carried-from-e8.md`

| Entry | Owner |
|---|---|
| No deployment reaches real students until E10's Care queue exists | Repeated by **13** (E10) |
| A stored summary can carry a comment excluded after it was written | **09**, through the sequence filter (the on-behalf race widens to every leader, so it closes here too) |
| The Lead Faculty name in the student page header | **08** |
| The leadership rollup mockup still passes a count to the small-N notice | **11** |
| Comments that tell ticket history | Each ticket in the files it edits: 08 and 09 (`reporting.py`, `response_loop.py`, `report_comments.py`), 11 (`instructor.ts`); 13 lists what is left |
| The exit drives read pinned dates in Fall 2026 | The `process/` pull request above, before 2026-11-23 |
| Simplifications the E7 boundary proposed, and the chair's department walk | **01** (the chair walk, written once); the other three stay with the next ticket that touches their function, and 13 re-carries what is left |
| The e2e suite's shared-stack residue | The `process/` pull request above, or the ticket that touches each spec; 13 re-carries what is left |
| The standing questions, re-asked at the E8 exit | **13** re-asks them; `PERSON_TABLES` covers 04's revoked-session table and 02's tables, if any |
| Shares at small n can still pin the rater count | Closed by ruling 9, written into SPEC §5.4 by this breakdown; **08** adds the line to ADR 0197 |
| Split the student read out of the response-loop service | **08** |
| The landing reads a full results payload for each section | E13, unchanged; 13 re-carries it |
| Leadership staff-name reads are set-based | **03** (the definer), with **07**, **09** and **11** (every leadership page calls it once per set) |
| ADR 0198 overstates a failed post with no response code | Not touched in E9; 13 re-carries it |
| A release batch's `cut_at` is the database's clock | Not touched in E9; 13 re-carries it |
| The exit drive's posted score is planted | Not touched in E9; 13 re-carries it |
| The student trend's axis ends at the latest published week | Not touched in E9; 13 re-carries it |

### Older entries this epic owns, carried as they stood

| Entry (source file) | Owner |
|---|---|
| For E9: the attention list, staff names, and three leadership roles (`../e8/carried-from-e7.md`) | **07** (`is_owed`), **03** with **07** and **11** (names), **09** (the three roles and the §4.1 item 5 answer) |
| For E9: purview-wide reads of the response tables (`../e8/carried-from-e7.md`) | **07** (set-based reads; the conditional index) |
| The on-behalf summary filter compares transaction-start times (`../e8/carried-from-e7.md`) | **09** |
| The staff-name definer judges "today" by the database's UTC date (`../e8/carried-from-e7.md`) | **03** |
| Deans, vice presidents and the assistant dean have no review queue (`../e7/carried-from-e6.md`) | **09**, by decision 12 |
| `services/moderation.py`: the import cycle, two jobs, small redundancies (`../e7/carried-from-e6.md`) | **09** fixes the small redundancies in the functions it edits; the split and the cycle go to E10, whose Care sweep restructures the module, and 13 writes that reason down |
| A named set's figures are read with no reader and no purview (`../e6/carried-from-e5.md`) | **05**, by ruling 5 |
| Generative sibling isolation does not cover named sets (`../e6/carried-from-e5.md`) | **05** |
| The rating term-axis read and three cohort views are unread (`../e6/carried-from-e5.md`) | **05** deletes the last reader; **12** retires the four views (decision 10) |
| Set names that differ only in case are two sets (`../e6/carried-from-e5.md`) | **05** |
| A teaching grant with a child edge would stop its section's roster sync (`../e6/carried-from-e5.md`) | **06** (one test that the edge is refused) |
| Six server-required members stay optional in the frontend, and one figure has three names (`../e6/carried-from-e5.md`) | **11** |
| The landing views' sentences sit outside the inventory (`../e5/carried-from-e4.md`) | **04** moves them into `frontend/src/copy/` under the `landing` surface (decision 15); **11** replaces the leadership landing on those keys |
| Aggregate ordering has no code-level gate (`../e5/carried-from-e4.md`) | **07** (the property) and **12** (the invariant), by decision 13 |
| The E1 generative purview coverage note (`../e3/carried-from-e2.md`) | **01** |
| A web-login linkage can only be provisioned by the demo seed or by hand (`../e3/carried-from-e2.md`) | **02** (the definer), **06** and **10** (the editor) |
| Logout and back-channel logout (`../e3/carried-from-e2.md`) | **04** (logout); back-channel logout to E13 by ruling 8, written into SPEC §14.3 |
| The exit drive does not show a week where only the university line is withheld (`../e6/carried-from-e5.md`) | **13** |
| Earlier pass-throughs (forged summary boundaries, the serial summary walk, the summary floor, the quiet week, and the rest) | Carried through unchanged; 13 names each in the ledger |

## Left out, and why

- **Back-channel logout** (ruling 8): E13.
- **Assignment end-dating and assignment history** (ruling 7). Whoever adds
  dates later changes the four live-Care predicate copies together.
- **Pooled comments on roll-up pages** (ruling 2).
- **A code refusal of Care, Admin or self-targeted grants** (ruling 1). The
  audit row is the control, and E10's access log shows it.
- **Freezing set membership at publication** (ruling 6).
- **Coarser share buckets or a higher floor for shares** (ruling 9).
- **A SQL copy of the purview walk** for the staff-name definer (ruling 3).
- **Loading the tree lazily, node by node.** One payload is enough at E13's
  500-section target. Changing later is a contract change, so revisit it at
  E13's load test.
- **Escalation along the supervision graph.** No E9 surface escalates
  anything.
- **The Care case count on a leadership surface** (§6.2's optional aperture).
  It is an institutional governance decision, for E10 or E11.
- **Policy writes by the assistant dean, dean or VP.** §5.3 makes chair and
  above read-only there.
- **A response composer or AI panels inside the drill-down.** §5.5 makes the
  drill-down read-only.
- **Conflict-of-interest marking across a Care revealer's whole purview.** It
  is E10's (§6.2); 01's purview now makes it possible, and 13 writes that into
  E10's carried file.
- **The `moderation.py` split and its import cycle.** E10, whose Care sweep
  restructures that module.
- **Per-level questions and the MCP server.** Phase 3.
