# E8 — Student loop closure: build order

Four tickets decompose SPEC §14.3's E8 entry. Each is sized for one focused
session and leaves the repository working: CI green, the Compose stack healthy,
nothing half-wired.

E7 built the hold and a results page that shows a week's state and its
response only. E8 fills that page with what students said, under the same hold:
the figures, the comments, the small-N state, the release batches and the
course's name. It also shows the student their own posted participation score,
which SPEC §3.3 assigned to this epic, and leads the landing with a section's
newest results. So the first ticket builds the student's read under the hold,
with the invariant tests that pin it, and the page is built on top of it.

Say **"build E8, ticket 2"** and it means E8-02.

Branch names follow `CONTRIBUTING.md`. Cut `e8/<slug>` from
`epic/e8-student-loop-closure`, which is cut from `main` at 22a81a41. One
ticket per branch, one pull request into the epic branch.

**Read before building anything here:** SPEC §3.3, §3.4, §4 and §4.1, §5.2,
§5.4, §7.6 and §13; §14.3's E8 entry; this README's rulings;
`carried-from-e7.md` in this folder, whole, and the entry "A note for E8: what
a student's comment read uses" in `../e7/carried-from-e6.md`; and
`docs/MISTAKES.md` whole. Ticket 01 also reads ADRs 0146, 0152, 0184, 0187,
0191 and 0193 (the release batch, the cut, the report's opening, the moderation
read, the name channel and the hold). Ticket 03 also reads ADRs 0124 and 0125
(the grade record and its ledger). UI tickets (02, 03) read
`docs/DESIGN_BRIEF.md`, `design/tokens.css` and §7.6 first.

**Lanes in this breakdown:** one of the four tickets is heavy: 01. It is heavy
by what it touches. It adds the §4.1 item 3 test for students and the other
invariant tests that pin the hold over the new figures and comments, it
extends two invariant-marked sweeps (the student-path import sweep and the
student payload-schema sweep), and it moves a surface in the invariant-marked
copy inventory. If its `EXPLAIN` asks for an index on `role_assignment`, that
migration touches an identity table, which is heavy too. SPEC marks no ⚠ on E8,
so no ticket carries ⚠ and no ticket has a verifier step. 02 is frontend only.
03 adds a student's read of their own grade record, which is no heavy path, and
a landing card. 04 is the exit. A light ticket whose change reaches a path in
`.claude/heavy-lane-paths.md`, or reds an invariant-marked test, stops and
re-lanes in its pull request.

## Rulings this breakdown builds on

Rulings 1 to 4 are the owner's, made on 2026-10-11 at the start of the epic.
Each took the recommended option. Rulings 5 to 7 were settled the same day as
breakdown decisions inside the epic's scope. No ticket reopens them. This
breakdown's pull request writes rulings 1 to 4 and 6 into SPEC §3.3, §3.4 and
§5.4.

1. **Release batches show on the latest week only, and only while nothing is
   held.** The from-earlier-weeks group shows on the page of the section's
   latest published week. It shows only while no published week of the section
   is `awaiting`, and only the batches cut before that week's report opened.
   So a held week's comment can never reach a student through a batch. The
   accepted cost: one required week that nobody answers hides every batch for
   the rest of the term.
2. **The page names the course in every state,** the closed door included,
   through `section_codes.course_label`. The survey page already prints that
   label, and a course label is not a figure about the week.
3. **Next-launch surfacing is a lead on the landing.** When no survey is open
   for a section, the student's landing card for it leads with "Week N results
   are in" and the link to the page. It reads the existing results route. There
   is no stored record of what a student has seen, so nothing says "new".
4. **The student sees their own posted participation score.** The results page
   shows, in every state, the student's latest accepted `grade_sync` score and
   its `ledger_text`, exactly as posted, with one fixed sentence: a comment
   counted at submission can be re-checked later, and a week's count can go
   down. It is the student's own record and not an aggregate, so a held week
   does not hide it.
5. **The Lead Faculty name in the page header (§2.1) is carried to E9,** with
   E9's staff-name work. The instructor report lacks it too.
6. **No classmate count.** The mockup's "18 of 24 classmates responded" line is
   left out. §5.4 does not list it, and in a small week it tells a student how
   many classmates answered.
7. **The architect's placement stands.** The student read stays a filter over
   `report_comments.visible_cards` and `released_cards` (which read
   `report_comment` v004), with no new view under `views_sql/`. The figures
   come from a new `reporting.student_streams`, following the pattern of
   `reporting.on_behalf_streams`: `response_loop` decides who may read, and
   `reporting` assembles the figures. Ticket 01 is heavy and 02 to 04 are light.
   01 takes only the policy-of-record simplification; 04 re-carries the other
   simplifications.

8. **Ratings as shares, hidden when small** (the owner's, 2026-10-11, on
   E8-01's privacy review). Students see each stream's distribution as
   whole-number percentages summing to 100, never counts. Below the n-threshold
   of distinct raters in a stream-week, the student gets no distribution and no
   trend mean for that stream-week, only the small-N notice; the workload
   median follows the same rule on workload answers. SPEC §5.4 says so. E8-01
   builds it in its fix round; E8-02 renders it.

**Facts checked in the code at 22a81a41, which the tickets build on:**

- The Alembic head is `7f679faf4b8d`, and it is the only head.
- The last ADR is 0196; the next free number is 0197.
- The next MISTAKES entry is 61.
- `StudentWeekResults` in `backend/app/schemas/response_loop.py` carries
  `state`, `response` and `published_weeks`, and nothing else.
- The invariant-marked import sweep
  (`tests/unit/test_the_report_comment_service_names_nothing_a_student_path_can_reach.py`)
  forbids four student-facing modules (`api/student.py`,
  `services/survey_read.py`, `services/submissions.py`, `schemas/student.py`)
  from importing `services/report_comments.py` or `services/moderation.py`.
  `services/response_loop.py` imports neither today, and the sweep does not
  list it.
- The invariant-marked payload-schema sweep
  (`tests/unit/test_the_student_payload_schema_carries_nothing_of_a_benchmark.py`)
  reads only `app.schemas.student`, so it does not reach `StudentWeekResults`.
- `pulse_app` holds `SELECT` on `grade_sync`, and the table has an index on
  `(section_id, user_id, created_at)`.
- `SmallNNotice` has only its instructor audience. `TrendDuo` does not exist.
- `@axe-core/playwright` is not installed.

## Build order

| # | Ticket | Branch | Lane | Depends on | Summary | Merged |
|---|---|---|---|---|---|---|
| 01 | [The student's week under the hold](E8-01-the-students-week-under-the-hold.md) | `e8/students-week-under-the-hold` | heavy | none | The figures, the comments, the small-N state, the release group and the course label on the results payload, all under the hold; the invariant tests; both student sweeps extended; the confidentiality line's surface; the `role_assignment` `EXPLAIN`; ADR 0197. | #324 as 295cc9fd, 2026-10-11 |
| 02 | [The results page](E8-02-the-results-page.md) | `e8/results-page` | light | 01 | The course heading, the response first, TrendDuo, the histograms, the workload median, the two comment groups, the student small-N notice, the from-earlier-weeks group and the confidentiality line; two mockups fixed; `student-results.spec.ts` made re-runnable. | #326 as MERGE_326, 2026-10-11 |
| 03 | [Participation and next launch](E8-03-participation-and-next-launch.md) | `e8/participation-and-next-launch` | light | none | The student's own posted score and ledger with the fixed sentence (ruling 4); the landing card that leads with the newest results (ruling 3); ADR 0198. | #323 as 7d3cbe17, 2026-10-11 |
| 04 | [E8 exit](E8-04-e8-exit.md) | `e8/e8-exit` | light | all | The full loop driven from one student's seat on a fresh stack; one drive that publishes on behalf and one that reads an unanswered week as the lead; axe scans if the package has landed; `../e9/carried-from-e8.md`; SPEC §14.3. | |

## Waves

| Wave | Tickets (in parallel within a wave) | Why it waits |
|---|---|---|
| 1 | 01, 03 | 01 builds the read and its tests. 03 adds one member to the same payload and a landing card, and needs nothing of 01's. They share the response-loop schema and service, the wire types and `docs/adr/README.md`. |
| 2 | 02 | Renders 01's payload, through the regenerated wire types. |
| 3 | 04 | Waits for everything. |

## Counters, allotted now

Each was checked in the tree at 22a81a41.

- **Alembic.** The single head is `7f679faf4b8d`
  (`20261011_7f679faf4b8d_a_policy_row_covers_one_course.py`). No migration is
  planned. E8-01 owns **M1**, with `down_revision = "7f679faf4b8d"`, only if its
  `EXPLAIN` calls for a partial index on `role_assignment (section_id)` for
  instructors. No other ticket adds a migration. A ticket that finds it needs
  one stops and says so in its pull request; its `down_revision` is the latest
  E8 revision as merged.
- **ADRs.** **0197** is 01's (the student's read under the hold). **0198** is
  03's (the posted score shown as posted). A number left unused is recorded as
  a gap by 04 and never reused.
- **MISTAKES.** The next entry is **61**.

## Shared files

The ticket that merges second merges the epic branch in first, and resolves by
keeping both sides.

| File | Tickets | How it is shared |
|---|---|---|
| `backend/app/services/response_loop.py`, `backend/app/schemas/response_loop.py` | 01, 03 | 01 the figures, comments, batches and course label; 03 the participation member. Different members. |
| `frontend/src/api/openapi.json`, `frontend/src/api/wire.gen.ts` | 01, 03 | On conflict, regenerate with `scripts/export_openapi.py` and `npm run gen:wire`; never hand-merge. |
| `frontend/src/copy/studentResults.ts` | 01, 03, then 02 | 01 adds the confidentiality line's key; 03 the participation sentence and the landing lead; 02 the rest of the page's words. |
| `frontend/src/routes/student/StudentResults.tsx` and its test, `frontend/src/api/student.ts` | 03, then 02 | 03 renders the participation block; 02 builds the rest of the page around it and keeps it. |
| `docs/adr/README.md` | 01, 03, 04 | Merge in ADR order; keep both rows. |
| `docs/SPEC.md` | 01, 03 (only if a built fact differs from what this breakdown wrote), 04 (§14.3) | Keep both sides. |

`tests/unit/test_spec_section_13_draws_the_tree.py` reads the filesystem, so a
ticket that adds a backend module draws it in SPEC §13 and edits no test. No
ticket here plans a new backend module.

## Process pull requests this epic needs

- **The accessibility scan.** Adding `@axe-core/playwright` touches
  `frontend/package.json` and the lockfile, which no ticket may change. If a
  `process/` pull request adds it before 02 is built, 02 adds the scan to the
  student-results drive and 04 adds it to the other drives the carried entry
  names. If not, 04 passes the entry on to E9 unchanged.
- **The pinned-date drives.** The older report and moderation drives read
  dates in Fall 2026, the latest 2026-11-23. A `process/` pull request must
  rework them before that date. No E8 ticket adds a pinned date.

## Exit criterion and the tickets that prove it

SPEC §14.3: "the full weekly loop demos end-to-end from one student's seat."

| Piece of the exit | Rests on |
|---|---|
| The student answers the week's survey, and the week closes and is moderated. | Built in E2 and E6; 04 (the drive) |
| On the next launch the landing leads with "Week N results are in". | 03 (the card), 04 (the drive) |
| In a required week the page is a closed door that names the course and shows no figure, comment or batch. | 01 (the hold over the new read), 02 (the page), 04 (the drive) |
| After a named human publishes, the page leads with the response, then the trend, distributions, workload median and the published comments, with the confidentiality line. | 01, 02, 04 |
| A small stream shows the student small-N notice in place of its comments. | 01, 02, 04 |
| The student sees their own posted score and ledger with the fixed sentence. | 03, 04 |

## Where the carried work lands

Only E8-04 edits the carried files' closures. Every other ticket names the
entries it closes in its pull request body, and 04 marks them closed with the
pull request and the merge commit. This breakdown's pull request writes which
ticket each entry lands in beside the entry.

### `carried-from-e7.md`

| Entry | Owner |
|---|---|
| For E8: the student results route answers the state and the response only | **E8-01** (the read under the hold, and the test that a held week serves nothing); **E8-02** (the page) |
| For E8: release batches carry no week | **E8-01**, by ruling 1, with ADR 0197; **E8-02** renders the group |
| For E8: the results page names no course | **E8-01** (on the payload in every state, ruling 2); **E8-02** (the heading) |
| For E8: the results page owes a confidentiality line | **E8-01** (the surface map and the key); **E8-02** (the line on the page) |
| A stored summary can carry a comment excluded after it was written | Not triggered: E8 shows students no summary (§5.4). **E8-04** re-carries it to E9 |
| The accessibility scan is not run on any moderation or response page | The `process/` pull request above, then **E8-02** and **E8-04** |
| Comments that tell ticket history | Each E8 ticket, in the files it edits; 04 lists any it saw and left |
| The exit drives read pinned dates in Fall 2026 | The `process/` pull request above; 04 repeats it if still open |
| The forged summary block boundaries, passed on unchanged | Not triggered: no E8 ticket renders comments into a prompt. 04 passes it on |
| The four standing questions | **E8-04** re-asks them |
| The role-assignment table has no index on its section | **E8-01** (the `EXPLAIN`, and M1 if it asks) |
| Two near-duplicates proposed by E7-03 | **E8-01** takes the policy-of-record pair. The chair's department walk is in `services/authz.py`, which no E8 ticket touches; 04 re-carries it |
| Five simplifications the boundary review proposed | **E8-01** takes the policy-of-record rule. 04 re-carries the other four |
| Two response paths no drive reaches | **E8-04** |
| The e2e suite's shared-stack residue | **E8-02** for `student-results.spec.ts`; 04 re-carries the rest unless it touches those specs |
| `response_gather` has a keyword that changes nothing | Not touched in E8; 04 re-carries it |
| Every other entry (for E9, E10, E13, the summary walk, the publish doors, the definers, the evals, the composer's busy line) | Carried through unchanged under its owner; 04 names each in the ledger |

### `../e7/carried-from-e6.md`, carried as it stood

| Entry | Owner |
|---|---|
| A note for E8: what a student's comment read uses | **E8-01**: the read goes through v004, with a flagged, an excluded and a Care-class comment absent and a kept one present |
| Two mockups still pass a count to the small-N notice | **E8-02** fixes `design/StudentResults.dc.html`; `design/LeadershipRollup.dc.html` stays with E9, and 04 re-carries it |

## Left out, and why

- **AI summaries for students.** §5.4 and the mockup show none, so the
  stored-summary rule has no student reader in E8 and stays with E9.
- **Notifications** (the Monday-after email). E12.
- **A per-student "seen" record**, and a launch that lands on the launched
  section's results. Ruling 3 chose the landing card, which needs no stored
  state and no change to the launch path.
- **A new view under `views_sql/`** for the student's comment read (ruling 7).
  A view later would be an additive migration, so this is easy to undo.
- **The Lead Faculty name in the page header.** E9 (ruling 5).
- **A classmate count** on the page (ruling 6).
- **The workload mean.** §5.4 lists the median only.
- **The publish-door and summary-walk races, the staff-name definer's UTC date,
  and `response_gather`'s keyword.** No E8 ticket touches the files they live
  in; each stays carried under its owner.
