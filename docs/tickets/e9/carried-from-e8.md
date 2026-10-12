# Carried from E8 into E9

Things E8 decided or deferred that later work has to know, per SPEC §14.1: one
entry per thing, each with an owner and what it looks like to be finished. This
is a hand-off note, not a ticket; the next breakdown schedules the work, and an
entry here is what that breakdown has to have read first. Created by E8-04.
Entries point at the record that owns the detail rather than restating it.

The completeness rule this file was written to: **every entry of
`../e8/carried-from-e7.md` not closed inside E8, every entry of
`../e7/carried-from-e6.md` that E8 carried as it stood, plus everything an E8
pull request deferred to a later epic or accepted as residue, plus everything
the E8 boundary reviews found and did not fix inside the epic, appears here.**
E8 kept no `deferred.md`; its tickets named their deferrals in their pull
request bodies, and those are the second source. The demonstration is the
ledger at the end of this file: every source entry is named with what happened
to it, in the source's own order.

The boundary reviews run after this file is written (`../e8/boundary-review.md`).
Whatever they find and do not fix is added here, under its own heading, by the
change that records the finding.

## How the sources were dispositioned

**Closed inside E8,** each closure recorded in its source file with the pull
request and the merge commit:

- E8-01 (#324, merged as 295cc9fd): the student results route's figures,
  comments and small-N state under the hold; release batches beside a held
  week (ruling 1, ADR 0197); the course on the page in every state (ruling 2);
  the confidentiality line's surface; the role-assignment `EXPLAIN`; the
  policy-of-record rule written once; and the note for E8 on what a student's
  comment read uses.
- E8-02 (#326, afc04110): the page for each of those; `design/StudentResults.dc.html`'s
  count attributes; `student-results.spec.ts` made re-runnable; the scan on the
  student results drive.
- Process pull request #322 (merged as 14bcb93d) and E8-04 (this pull request):
  the accessibility scan on every page the five named drives reach.
- E8-04: the two response paths no drive reached.

**Carried through unchanged**, under the owner and done-when of the source
entry, every entry the ledger below marks so. They are not restated here.

**Re-carried below with a new fact from E8:** the stored-summary rule, the
comments that tell ticket history, the pinned-date drives, the standing
questions, the simplifications (with the chair's department walk), the e2e
residue, and the leadership rollup mockup's count.

**New from E8:** the entries under "New from E8" below.

## No deployment reaches real students until E10's Care queue exists

The owner's ruling 5 (`../e6/README.md`), repeated as every epic since E6 was
asked to repeat it. E8 adds no reader of `threat_case`. **Owner:** E10.
**Done when:** the Care queue reads `threat_case`, and only then may a
deployment reach real students.

## A stored summary can carry a comment excluded after it was written

Not triggered in E8: SPEC §5.4 shows students no summary, so E8 built no reader
of a stored summary. **Owner:** the first ticket that shows a stored summary up
the chain (E9's roll-up and drill-down). **Done when:** each such reader leaves
out a summary not strictly later than the week's latest exclusion or undo of a
keep, through the on-behalf filter's own function rather than a copy, with a
test that excludes a summarized comment and reads the summary as that reader.

## The Lead Faculty name in the student page header

Ruling 5 of `../e8/README.md`: SPEC §2.1 names the Lead Faculty in the page
header, and neither the student results page nor the instructor report shows
it. **Owner:** E9, with its staff-name work. **Done when:** both headers name
the course's Lead Faculty through `response_loop.section_staff_names` (or the
read that replaces it), with a test that a course with no lead shows none.

## The leadership rollup mockup still passes a count to the small-N notice

From `../e7/carried-from-e6.md`, half closed by E8-02.
`design/LeadershipRollup.dc.html` still passes `responded` and `total` to
`SmallNNotice`. **Owner:** E9, which builds the rollup. **Done when:** the
mockup passes neither attribute.

## Comments that tell ticket history

E8-01 and E8-03 rewrote the comments in the files they edited. Left behind by
E8-01: `services/reporting.py` (58 lines matching the pattern below),
`services/report_comments.py` (39) and `frontend/src/api/instructor.ts` (8),
besides the older files the source entry names. **Owner:** the next ticket that
touches each file. **Done when:** `rg "E[0-9]+(\.[0-9]+)?-[0-9]{2}" backend/app
frontend/src` finds no comment naming a ticket, and each such comment cites an
ADR or a SPEC section for the why and says what the code does now.

## The exit drives read pinned dates in Fall 2026

Unchanged from the source entry, and now close: the report and moderation
drives move the clock to fixed dates, the latest reading 2026-11-23. E8's
drives read every instant from window rows. **Owner:** a `process/` pull
request, which must land before 2026-11-23. **Done when:** no spec under
`tests/e2e/` sets the clock to a literal date.

## Simplifications the E7 boundary proposed, and the chair's department walk

E8-01 wrote the policy-of-record rule once. Still open: the lead-and-chair rule
is written three times in SQL; the chair's walk to courses with a lead appears
twice in `services/authz.py` (`lead_review_courses`,
`chaired_courses_with_a_lead`); `record_policy` recomputes what its caller
already knows; and `publish_response` converts a course week to a week itself.
**Owner:** the next ticket that touches each file; `services/authz.py` is
heavy-lane. **Done when:** each rule is written once, or a record argues the
extra copy, and `publish_response` takes the week its caller already resolved.

## The e2e suite's shared-stack residue

E8-02 made `student-results.spec.ts` re-runnable, and E8-04's drive takes fresh
weeks on each run. Still open, each leaving rows a second run on one stack trips
over (CI builds a fresh stack, so none reds CI):

- `instructor-response.spec.ts` leaves `identity_name` set on the shared mock
  instructor.
- `leadership-response.spec.ts` leaves `BIOL 215`'s latest policy `REQUIRED`
  after a red run, because its serial block skips the reset.
- `exit-response-loop.spec.ts` publishes into course weeks 3 and 4 of
  `MATH-140-E1FF` every run, so a second run's publish is refused.
- The composer's hold banner is driven in component tests only.

**Owner:** a `process/` pull request on the e2e world, or the next ticket that
touches each spec. **Done when:** each spec runs green twice in a row on one
stack, and the hold banner is driven once.

## The standing questions, re-asked at the E8 exit

The answers are in `../e8/boundary-review.md`.

- **`PERSON_TABLES`**: E8 added no table; unchanged and correct. **Owner:** E13
  at the latest; every boundary re-asks it of the tables it adds.
- **The TypeScript 7 pair**: re-checked 2026-10-11, typescript-eslint 8.71.1,
  peer range still `>=4.8.4 <6.1.0`. **Owner / done when:** unchanged.
- **The session-read sweep's two disclosed limits**: re-affirmed by planting in
  the results route and in `services/response_loop.py`. **Owner:** each
  boundary; the structural close is E13's.
- **The denial-module inventory and the collection floor**: twelve new E8
  invariant-marked modules, every one collected. **Owner:** a candidate process
  ticket. **Done when:** unchanged.

## New from E8

### Shares at small n can still pin the rater count

From E8-01's privacy re-check (#324), accepted as LOW. With five raters the
shares are multiples of 20, so a student who subtracts their own rating learns
the other four ratings as a group, though not who gave which: the group size the
comment threshold already accepts. The E8 boundary's `privacy-authz` review adds
that whole-number shares alone can pin the rater count at small n (14, 43 and 43
percent can only be seven raters); E8-05 rounded the mean and the median, which
gave it away more directly. **Owner:** the owner's SPEC choice, with E9.
**Done when:** a record decides coarser buckets or a higher floor for shares, or
says why neither.

### Split the student read out of the response-loop service

From the E8 boundary's `code-reviewer` (simplification 4): `services/response_loop.py`
is over 1,200 lines and holds the student's read beside the response loop.
**Owner:** the next ticket that touches the student read. **Done when:** the
student read lives in `services/student_results.py`, SPEC §13 draws it, and the
import sweeps name the new module.

### The landing reads a full results payload for each section

From `spec-conformance`: the landing's results lead fetches each closed
section's whole results payload to learn its newest week. **Owner:** E13, or
earlier if load shows it. **Done when:** a slim route answers the newest
released week, or a measurement shows the full read is fine.

### Leadership staff-name reads are set-based

From `data-model`: the staff-name definer is called once per section. **Owner:**
E9, with its leadership pages. **Done when:** every leadership page that names
staff calls the definer once per set of sections, with a query-count test.

### ADR 0198 overstates a failed post with no response code

From `lti-oidc`: a `failed` row with no response code may still have landed, so
"a score the platform never took" in ADR 0198's rejected alternatives is too
strong. **Owner:** the next ticket that touches ADR 0198 or the passback.
**Done when:** the line says the score is the last one Pulse knows the platform
took.

### A release batch's `cut_at` is the database's clock, not the effective clock

`release_batch.cut_at` carries a `now()` server default, while every other
scheduling and visibility instant reads `clock.now` (ADR 0109). On a development
stack with a moved clock, every batch is stamped after any past week's report
opened, so the student's from-earlier-weeks group (shown only for batches cut
before the week's report opened, ADR 0197) never shows, and no drive and no
axe scan reaches it. In a deployment the two clocks agree. The docstring of
`tests/fixtures/student_week.py` says the cutter stamps `cut_at` from the moving
development clock, which is not so. **Owner:** the next ticket that touches the
release cut. **Done when:** `cut_due_release_batches` writes `cut_at` from the
effective clock with a test, or a record argues the wall clock; a drive reaches
the from-earlier-weeks group and scans it with axe; and the fixture docstring
says what the code does.

### The exit drive's posted score is planted

`tests/e2e/exit-student-loop.spec.ts` writes one `grade_sync` row for the
learner and deletes it on the way out, rather than running the passback,
because the passback would post into the mock gradebook that
`exit-grade-passback.spec.ts` later reads from a known-empty start. So the
drive shows the page prints a posted row as posted, not that a real post
reaches the page. **Owner:** a `process/` pull request on the e2e world.
**Done when:** the drive's score comes from a real passback without changing
what `exit-grade-passback.spec.ts` reads, or a record argues the plant.

### The student trend's axis ends at the latest published week

From E8-02 (#326), proposed and not done: the payload carries no section
length, so `PulseTrendChart`'s axis on the student page spans to the latest
published week rather than the section's whole length. **Owner:** the next
ticket that touches the student trend. **Done when:** the axis spans the
section's length, or a record argues the shorter axis.

## The ledger

Every source entry, in its source's order, with what happened to it.

### `../e8/carried-from-e7.md`

| Source entry | Disposition |
|---|---|
| How the sources were dispositioned: the pass-throughs | Carried through unchanged, under their source owners |
| No deployment reaches real students until E10's Care queue exists | Repeated (E10) |
| The accessibility scan is not run on any moderation or response page | Closed by #322, E8-02 (#326) and E8-04; the earlier-weeks group's gap is new below |
| Comments that tell ticket history | Re-carried, with E8's files |
| A stored summary can carry a comment excluded after it was written | Not triggered in E8; re-carried (E9) |
| The exit drives read pinned dates in Fall 2026 | Re-carried (a `process/` pull request before 2026-11-23) |
| The forged summary block boundaries, passed on unchanged | Not triggered in E8; carried through unchanged |
| The four standing questions | Re-asked; re-carried |
| For E8: the student results route answers the state and the response only | Closed by E8-01 (#324) and E8-02 (#326) |
| For E8: release batches carry no week | Closed by E8-01 (#324) and E8-02 (#326) |
| For E8: the results page names no course | Closed by E8-01 (#324) and E8-02 (#326) |
| For E8: the results page owes a confidentiality line | Closed by E8-01 (#324) and E8-02 (#326) |
| For E9: the attention list, staff names, and three leadership roles | Carried through unchanged (E9) |
| For E9: purview-wide reads of the response tables | Carried through unchanged (E9) |
| The on-behalf summary filter compares transaction-start times | Carried through unchanged (the next summary-walk ticket) |
| Two publishes at the same instant: a 500 and a second author's row | Carried through unchanged (the next publish-door ticket) |
| Two near-duplicates proposed by E7-03 | Half closed by E8-01 (#324); the chair's walk re-carried with the simplifications |
| The draft and check evals have no floor | Carried through unchanged (E10) |
| `record_teaching_instructor` accepts any person key | Carried through unchanged (the next teaching-definer ticket, or E13) |
| The staff-name definer judges "today" by the database's UTC date | Carried through unchanged (the next `section_staff_names` ticket) |
| The e2e suite's shared-stack residue | One spec closed by E8-02 (#326); the rest re-carried |
| Five simplifications the boundary review proposed | One closed by E8-01 (#324); four re-carried |
| The role-assignment table has no index on its section | Closed by E8-01 (#324) |
| The draft eval set bypasses the output contracts | Carried through unchanged (E10) |
| Two response paths no drive reaches | Closed by E8-04 |
| `response_gather` has a keyword that changes nothing | Carried through unchanged (the next ticket touching `response_gather`) |
| The E7-10 graders' closed word lists | Carried through unchanged (E10) |
| The composer's busy line is inserted with its text | Carried through unchanged (the next ticket touching `InstructorResponse.tsx`) |

### `../e7/carried-from-e6.md`, the entries E8 carried as they stood

| Source entry | Disposition |
|---|---|
| The Care sweep owes two kinds of held comment, and old summaries owe a look | Carried through unchanged (E10) |
| A note for E8: what a student's comment read uses | Closed by E8-01 (#324) |
| The bounced comment stays outside the moderation pass | Carried through unchanged (E10) |
| Deans, vice presidents and the assistant dean have no review queue | Carried through unchanged (E9) |
| Two behaviours no test covers: the unlock log line | Carried through unchanged (the next sweep ticket) |
| The import cycle between moderation and the report services | Carried through unchanged (the next ticket touching `services/moderation.py`) |
| `services/moderation.py` does two jobs | Carried through unchanged (the same) |
| Small redundancies in `services/moderation.py` | Carried through unchanged (the same) |
| The review queue has no index of its own | Carried through unchanged (E10) |
| No precision or recall floor for moderation | Carried through unchanged (E10) |
| Grading reads the close the other way | Carried through unchanged (the next grading ticket) |
| Two mockups still pass a count to the small-N notice | Half closed by E8-02 (#326); the rollup mockup re-carried (E9) |

### E8's pull requests, in merge order

| Deferral or residue | Disposition |
|---|---|
| #321 (the breakdown): ruling 5, the Lead Faculty name | Carried: "The Lead Faculty name in the student page header" (E9) |
| #320 (process: the active epic) | Nothing deferred |
| #323 (E8-03): `participation` defaults to null, so the invariant payload tests build the model without it | A fact of the schema; the score is the student's own record and not held, so nothing owed |
| #323: the comment sweep left to E8-01 | Done by E8-01 in the files it shares |
| #322 (process: `@axe-core/playwright`) | Nothing deferred; the scans landed in E8-02 and E8-04 |
| #325 (main into the epic) | Nothing deferred |
| #324 (E8-01): shares at the threshold can reveal bucket counts | Carried: "Shares at small n can still pin the rater count" |
| #324: ticket names left in three files | Re-carried with "Comments that tell ticket history" |
| #326 (E8-02): the trend axis ends at the latest published week | Carried: "The student trend's axis ends at the latest published week" |
| #326: the axe scan cannot reach the small-N notices or the earlier-weeks group | The small-N notices (ratings and comments): scanned by E8-04's drive. The earlier-weeks group: carried with "A release batch's `cut_at`" |
| #326: the mockup's small-N branch draws the held week's trend values | Fixed by E8-04: the branch's trend stops at the week before |
| E8-04: the posted score on the exit drive is planted | Carried: "The exit drive's posted score is planted" |
| E8-04: `cut_at` is the database's clock | Carried: "A release batch's `cut_at` is the database's clock" |

### The E8 README's "Left out, and why"

| Item | Disposition |
|---|---|
| AI summaries for students | Not in SPEC §5.4; the stored-summary rule is carried for E9's readers |
| Notifications (the Monday-after email) | E12, in SPEC §14.3 already |
| A per-student "seen" record, and a launch that lands on the results | Ruling 3 chose the landing card; nothing owed |
| A new view under `views_sql/` for the student's comment read | Ruling 7; nothing owed |
| The Lead Faculty name in the page header | Carried (E9) |
| A classmate count | Ruling 6; nothing owed |
| The workload mean | SPEC §5.4 lists the median only; nothing owed |
| The publish-door and summary-walk races, the definer's UTC date, `response_gather`'s keyword | Carried through unchanged, each under its owner |

### The E8 boundary (`../e8/boundary-review.md`)

Everything the boundary reviews found and E8-05 (#328) and E8-06 (#327) did not
fix. The other findings are recorded there with their fixes.

| Finding | Disposition |
|---|---|
| `privacy-authz` note: whole-number shares can pin the rater count at small n | Carried: "Shares at small n can still pin the rater count", merged with #324's LOW |
| `code-reviewer` simplification 4: `services/response_loop.py` is too long | Carried: "Split the student read out of the response-loop service" |
| `spec-conformance` LOW: the landing reads a full results payload per section | Carried: "The landing reads a full results payload for each section" |
| `data-model` note: leadership name reads must be set-based | Carried: "Leadership staff-name reads are set-based" |
| `lti-oidc` LOW: ADR 0198's line on a failed post | Carried: "ADR 0198 overstates a failed post with no response code" |
| Every other finding | Fixed in E8-05 (#328) or E8-06 (#327) |
