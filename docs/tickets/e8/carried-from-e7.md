# Carried from E7 into E8

Things E7 decided or deferred that later work has to know, per SPEC §14.1: one
entry per thing, each with an owner and what it looks like to be finished. This
is a hand-off note, not a ticket; the next breakdown schedules the work, and an
entry here is what that breakdown has to have read first. Created by E7-09.
Entries point at the record that owns the detail rather than restating it.

The completeness rule this file was written to: **every entry of
`../e7/carried-from-e6.md` and `../e7/carried-requirements.md` not closed inside
E7, plus everything an E7 pull request deferred to a later epic or accepted as
residue, plus everything the E7 boundary reviews found and did not fix inside
the epic, appears here.** E7 kept no `deferred.md`; its tickets named their
deferrals in their pull request bodies, and those are the second source. The
demonstration is the ledger at the end of this file: every source entry is
named with what happened to it, in the source's own order.

The boundary reviews run after this file is written (`../e7/boundary-review.md`).
Whatever they find and do not fix is added here, under its own heading, by the
change that records the finding.

## How the sources were dispositioned

**Closed inside E7,** each closure recorded in its source file with the pull
request and the merge commit:

- E7-01 (#308, merged as e26b5274), E7-06 (#311, merged as dee0cec8) and E7-05
  (#313, merged as b0a6794b): the professor's name reaches the student through
  one channel (`carried-requirements.md`).
- E7-05 (#313): released comments are no longer read-only on the instructor
  page, and the reason bound is checked once against the backend.
- E7-08 (#307, merged as 09c48a19): the two LOWs on the leadership moderation
  drive, and a signed-in reader without the role is no longer told their
  session ended.
- E7-03 (#312, merged as e7a928c7): a stored summary written before the week's
  latest exclusion is withheld from the on-behalf reader. The entry stays open
  for E8's and E9's readers, below.

**Carried through unchanged**, under the owner and done-when of the source
entry: every pass-through `../e7/carried-from-e6.md` names as "Carried through
unchanged" in its ledger, and the pass-throughs its "How the sources were
dispositioned" section lists (the landing views' sentences, the serial summary
walk, the aggregate-ordering gate, the summary eval floor, the quiet-week
summary, and the E2 and E3 list that file names). The forged summary block
boundaries entry is among them and is restated below because E7 touched it.

**Re-carried below with a new fact from E7:** ruling 5 for E10, the
accessibility scan, comments that tell ticket history, the stored summary rule
for later readers, the pinned-date drives, `PERSON_TABLES`, the TypeScript 7
pair, the session-read sweep's limits, and the denial-module inventory.

**Carried as they stood, from `../e7/carried-from-e6.md`:** the Care sweep's two
kinds of held comment (E10), the note for E8 on comment reads, the bounced
comment (E10), the review queue for deans, vice presidents and the assistant
dean (E9), the unlock log line, the three `services/moderation.py` entries, the
review queue's index (E10), the moderation floor (E10), grading's close
boundary, and the two mockups' notice attributes. Each keeps its owner and
done-when there; this file's ledger names each.

**New from E7:** the entries under "New from E7" below.

## No deployment reaches real students until E10's Care queue exists

The owner's ruling 5 (`../e6/README.md`), repeated as E6 and E7 were asked to
repeat it. E7 adds no reader of `threat_case`. **Owner:** E10. **Done when:**
the Care queue reads `threat_case`, and only then may a deployment reach real
students.

## The accessibility scan is not run on any moderation or response page

`@axe-core/playwright` is still not installed: no `process/` pull request added
it during E7, and adding it touches `package.json`, which the merger refuses on
a ticket pull request. So E7-05's composer, E7-06's results page and E7-07's
three leadership pages joined the moderation pages without a scan. **Owner:** a
`process/` pull request that adds the dependency, then the next UI epic (E8).
**Done when:** the instructor-report, leadership-moderation, student-results,
instructor-response and leadership-response drives each run an axe scan on
every page they reach and fail on a violation.

## Comments that tell ticket history

E6's entry asked each E7 ticket to clean the files it edited. They did not, and
added their own: thirty files under `backend/app/` and `frontend/src/` that E7
changed name an E7 ticket in a comment or docstring, among them
`services/response_loop.py`, `api/student.py`, `api/instructor.py`,
`api/leadership.py`, `api/deps.py`, `models/loop.py`, the four
`views_sql/response_loop_*` files and `section_staff_names_v001.sql`,
and `frontend/src/api/leadership.ts`. **Owner:** the next ticket that touches
each file. **Done when:** `rg "E[0-9]+(\.[0-9]+)?-[0-9]{2}" backend/app
frontend/src` finds no comment naming a ticket, and each such comment cites an
ADR or a SPEC section for the why and says what the code does now.

## A stored summary can carry a comment excluded after it was written

`../e7/carried-from-e6.md`'s entry, closed for the on-behalf reader only (ADR
0194). **Owner:** the first ticket that shows a stored summary to a student
(E8) or up-chain (E9). **Done when:** each such reader leaves out a summary not
strictly later than the week's latest exclusion or undo of a keep, through the
on-behalf filter's own function rather than a copy, with a test that excludes a
summarized comment and reads the summary as that reader.

## The exit drives read pinned dates in Fall 2026

Unchanged from the source entry: the report and moderation drives move the
clock to fixed dates (the latest reading 2026-11-23). E7's own drives read
every instant from the seeded calendar or the section's own window rows.
**Owner:** a `process/` pull request, which must land before 2026-11-23.
**Done when:** unchanged from the source entry.

## The forged summary block boundaries, passed on unchanged

E7-04's draft and check send the model no comment (ADR 0195), so the entry did
not trigger in E7. **Owner:** the next ticket that renders comments into a
prompt. **Done when:** unchanged from the source entry.

## The four standing questions, re-asked at the E7 exit

The answers are in `../e7/boundary-review.md`.

- **`PERSON_TABLES`**, asked of `instructor_response` and `response_policy`:
  unchanged, and correct for both. **Owner:** E13 at the latest; every boundary
  re-asks it of the tables it adds.
- **The TypeScript 7 pair**: re-checked 2026-10-11, typescript-eslint 8.71.1,
  peer range still `>=4.8.4 <6.1.0`. **Owner / done when:** unchanged.
- **The session-read sweep's two disclosed limits**: re-affirmed by planting in
  E7's three route-serving modules. **Owner:** each boundary; the structural
  close is E13's.
- **The denial-module inventory and the collection floor**: twenty new E7
  invariant-marked modules, every one collected. **Owner:** a candidate process
  ticket. **Done when:** unchanged.

## New from E7

### For E8: the student results route answers the state and the response only

E7's route (`GET /student/sections/{section_id}/weeks/{course_week}/results`,
ADR 0193) carries `state`, `response` and `published_weeks`. **Owner:** E8.
**Done when:** E8 adds the week's aggregates, comments and small-N state to
that page under the same hold, reading the hold through
`services/response_loop.py`'s `policy_of_record`, `first_response`,
`latest_response` and `week_state` (or the read that assembles them), never a
copy; and a test shows a required, unanswered week serves no aggregate and no
comment.

### For E8: release batches carry no week

`release_batch` holds a section, a term and a cut instant, and no week. A
batch's comments therefore have no week to be held with. **Owner:** E8.
**Done when:** a record decides how a release batch sits beside a held week on
the student page (shown, held until the week it was cut in is released, or
something else), and the page follows it with a test.

### For E8: the results page names no course

E7-06 (#311) left the course off the page, because a course label carries a
number and a held week may show none. **Owner:** E8. **Done when:** the page
names the course where it can do so without a figure in a held week, or a
record says why it does not.

### For E9: the attention list, staff names, and three leadership roles

- The attention list calls `response_loop.is_owed` (SPEC §5.6 rule 4, ruling
  10), never a copy of the 48-hour rule.
- Staff names on leadership pages: the owed list and the on-behalf page show
  no instructor name.
- The assistant dean's, the dean's and the vice president's policy and
  on-behalf views: refused until the supervision walk, as the review queue is.
- When E9's leadership drill-down renders the report up-chain, the
  `leadership_response` copy surface's answer on SPEC §4.1 item 5 is asked
  again. E7-07 answered that it owes no confidentiality line, because its pages
  show aggregate summaries, counts and ratings and never one student's comment.

**Owner:** E9. **Done when:** the attention list's test fails if
`response_loop.is_owed` is replaced; each leadership page that shows a member
of staff reads the name through `response_loop.section_staff_names`; the three
roles' views are decided through the purview walk; and the surface's item 5
answer is recorded beside the up-chain report.

### For E9: purview-wide reads of the response tables

From E7-02's data-model review (#310): the response loop's reads are one
section-week at a time. **Owner:** E9, with the first purview-wide reader.
**Done when:** that reader reads policies and responses set-based, and an index
on `instructor_response (section_id, week_id, sequence)` exists if `EXPLAIN`
over a term-sized seed wants it.

### The on-behalf summary filter compares transaction-start times

From E7-03's privacy review (#312), accepted as LOW. The filter compares
`moderation_state.decided_at` with `weekly_summary.generated_at`, both stamped
at transaction start, so an exclusion whose transaction starts before the
summary walk's and commits after the walk read the comments can leave a summary
that carries the excluded comment and still passes. **Owner:** the next ticket
that touches the summary walk. **Done when:** `weekly_summary` stores the
highest `moderation_state.sequence` the walk saw (a migration), the filter
compares sequences, and a test interleaves the two transactions.

### Two publishes at the same instant: a 500 and a second author's row

From E7-03 (#312). If an instructor and a lead publish the same week at the
same instant, the response guard's one-author refusal (42501) reaches the loser
as a 500 rather than the 409; nothing is written and the message names no one.
ADR 0194 also records that two publishes racing for an empty week can both pass
the door's check, and one author's second row then reads as an edit. **Owner:**
the next ticket that touches the publish doors. **Done when:** the guard's
refusal is answered with the same 409 as a second publish, with a test that
forces the race.

### Two near-duplicates proposed by E7-03

`policy_of_record` and the set-based clock read apply one policy-of-record rule
in two forms, and the chair's department walk appears twice in
`services/authz.py` (`lead_review_courses`, `chaired_courses_with_a_lead`).
**Owner:** the next ticket that touches either file. **Done when:** each rule is
written once, or a record argues the second copy.

### The draft and check evals have no floor

From E7-04's prompt-eval review (#309), accepted residue. The typed cases in
`tests/evals/response_draft/` and `tests/evals/draft_check/` are in no registry
slot and have no `floors.py`; the held-count grader shares the product's own
rule (`states_a_count_of_people`), so a loosened rule is caught by the phrasing
tests rather than the eval; and `addresses()` is keyword-based. **Owner:** E10's
floors pull request. **Done when:** both sets have a registry slot and a floor,
the grader's count rule is checked against cases the product rule does not
share, and `addresses()` is checked against the live endpoint before a floor is
set on it.

### `record_teaching_instructor` accepts any person key

From E7-01's review (#308), recorded in ADR 0191 as accepted residue: a caller
who can run SQL as `pulse_app` can grant teaching rights to any person, and so
pass the response guard's author check. **Owner:** the next ticket that touches
`views_sql/teaching_instructor_*` (heavy lane), or E13. **Done when:** the
definer refuses a person key that is not the roster's member for the section,
with a test.

### The staff-name definer judges "today" by the database's UTC date

From E7-01 (#308), recorded in ADRs 0191 and 0193. Near midnight in the
institution's zone, the definer and the survey read can disagree about whether
an enrollment is live for a few hours, and under a moved development clock the
definer reads the real date. **Owner:** the next ticket that touches
`section_staff_names`. **Done when:** the definer takes the reader's date as a
parameter from the application clock, or a record argues the edge.

### The e2e suite's shared-stack residue

Each of these leaves rows a second run on the same local stack trips over; CI
builds a fresh stack each time, so none reds CI today:

- `student-results.spec.ts` (#311) leaves an instructor name, a required policy
  row dated 1970 and a response on `MATH-140-E1FF`.
- `instructor-response.spec.ts` (#313) leaves `identity_name` set on the shared
  mock instructor.
- `leadership-response.spec.ts` (#314) leaves `BIOL 215`'s latest policy
  `REQUIRED` after a red run, because its serial block skips the reset.
- `exit-response-loop.spec.ts` (E7-09) leaves two required-then-encouraged
  policy rows and three response rows on `MATH-140-E1FF`, which the response
  table's append-only rule keeps; a second run's publish is refused.
- E7-05 (#313) covers the composer's hold banner in component tests only,
  because showing it on the stack needs a required policy row that other specs
  would read.

**Owner:** a `process/` pull request on the e2e world, or the next ticket that
touches each spec. **Done when:** each spec runs green twice in a row on one
stack, and the hold banner is driven once.

## The ledger

Every source entry, in its source's order, with what happened to it.

### `../e7/carried-from-e6.md`

| Source entry | Disposition |
|---|---|
| How the sources were dispositioned: the pass-throughs | Carried through unchanged, under their source owners |
| No deployment reaches real students until E10's Care queue exists | Repeated (E10) |
| The Care sweep owes two kinds of held comment, and old summaries owe a look | Carried as it stood (E10) |
| A note for E8: what a student's comment read uses | Carried as it stood (E8) |
| The bounced comment stays outside the moderation pass | Carried as it stood (E10) |
| The accessibility scan is not run on the moderation pages | Re-carried, widened to E7's pages (a `process/` pull request, then E8) |
| Two LOWs on the leadership moderation drive | Closed by E7-08 (#307) |
| Released comments are read-only on the instructor page | Closed by E7-05 (#313) |
| Deans, vice presidents and the assistant dean have no review queue | Carried as it stood (E9), with the policy and on-behalf views added under "For E9" |
| Two older copies of "closed" | Closed before E7, by E6-09 |
| Two behaviours no test covers: the unlock log line | Carried as it stood (the next sweep ticket) |
| The import cycle between moderation and the report services | Carried as it stood (the next ticket touching `services/moderation.py`) |
| `services/moderation.py` does two jobs | Carried as it stood (the same) |
| Small redundancies in `services/moderation.py` | Carried as it stood (the same) |
| The reason bound is written twice | Closed by E7-05 (#313) |
| Comments that tell ticket history | Re-carried, with E7's files |
| The review queue has no index of its own | Carried as it stood (E10) |
| No precision or recall floor for moderation | Carried as it stood (E10) |
| Grading reads the close the other way | Carried as it stood (the next grading ticket) |
| A stored summary can carry a comment excluded after it was written | Closed for the on-behalf reader by E7-03 (#312); re-carried for E8 and E9 |
| A signed-in reader without the role is told their session ended | Closed by E7-08 (#307) |
| Two mockups still pass a count to the small-N notice | Carried as it stood (E8 or E9) |
| The exit drives read pinned dates in Fall 2026 | Re-carried (a `process/` pull request before 2026-11-23) |
| The `PERSON_TABLES` standing question | Re-asked; re-carried |
| The TypeScript 7 pair | Re-checked 2026-10-11; re-carried |
| The session-read sweep's two disclosed limits | Re-affirmed by planting; re-carried |
| The denial-module inventory and the collection floor | Re-counted; re-carried |

### `../e7/carried-requirements.md`

| Source entry | Disposition |
|---|---|
| The professor's name reaches the student, through a sanctioned channel | Closed by E7-01 (#308), E7-06 (#311) and E7-05 (#313) |

### E7's pull requests, in merge order

| Deferral or residue | Disposition |
|---|---|
| #306: the accessibility scan needs a `process/` pull request | Re-carried with the scan entry |
| #306: the older drives' pinned dates | Re-carried with the pinned-date entry |
| #307: done-when 2 narrowed (a session has no server-side record, ADR 0089) | Closed as ruled in the ticket file; nothing owed |
| #307: no frontend unit test for the `not-your-role` outcome | Closed as ruled; the e2e cases cover the pages |
| #309: `response_gather(..., for_on_behalf=True)` raised `NotImplementedError` | Closed by E7-03 (#312) |
| #309: the draft route declares no request body | A fact of the interface; nothing owed |
| #309: fractions and plural quantity words were not count tokens | Closed by E7-03 (#312), ADR 0195 amended |
| #309: the eval sets' floor, registry, shared grader and keyword `addresses()` | Carried: "The draft and check evals have no floor" (E10) |
| #308: `record_teaching_instructor` accepts any person key | Carried (the next teaching-definer ticket, or E13) |
| #308: the definer's "today" is the database's UTC date | Carried (the next `section_staff_names` ticket) |
| #308: staff names on leadership pages | Carried under "For E9" |
| #310: set-based reads and an index for a purview-wide reader | Carried under "For E9" |
| #310: aggregates and comments on the student page | Carried: "For E8: the student results route" |
| #311: the results page names no course | Carried: "For E8: the results page names no course" |
| #311: the e2e spec leaves rows on `MATH-140-E1FF` | Carried with the shared-stack residue |
| #311: no axe scan | Re-carried with the scan entry |
| #312: the summary filter's transaction-start race | Carried (the next summary-walk ticket) |
| #312: two publishes at one instant (a 500), and the race ADR 0194 records | Carried (the next publish-door ticket) |
| #312: two near-duplicates proposed | Carried (the next ticket touching either file) |
| #313: the e2e spec leaves `identity_name` on the shared mock instructor | Carried with the shared-stack residue |
| #313: the hold banner is not driven end to end | Carried with the shared-stack residue |
| #314: a red run leaves `BIOL 215` required | Carried with the shared-stack residue |
| #314: whether the leadership response surface owes the item 5 line | Answered (it owes none today); re-asked in E9 |
| #314: instructor names and three leadership roles' views | Carried under "For E9" |
| E7-09: the exit drive cannot run twice on one stack | Carried with the shared-stack residue |

### The E7 README's "Left out, and why"

| Item | Disposition |
|---|---|
| Notifications | E12, in SPEC §14.3 already |
| Staff names on leadership pages | Carried under "For E9" |
| Aggregates, comments and the small-N state on the student page | Carried under "For E8" |
| Eval floors for the draft and the check | Carried (E10) |
| Unpublished drafts on the server, an "edited" marker, unpublishing | Nothing in SPEC §5.3 asks for them; nothing owed |
| The assistant dean's, dean's and vice president's policy views | Carried under "For E9" |
| A new scheduled job | None needed: the deadlines are computed on read |

### The E7 boundary (`../e7/boundary-review.md`)

Everything the boundary reviews found and E7-10 and E7-11 did not fix. The
other findings are recorded there with their fixes. The summary walk's
transaction-start race, the 500 on a publish race, the purview-wide reads, the
draft evals' floor and the shared-stack residue were already entries above, and
are not repeated.

| Finding | Disposition |
|---|---|
| `code-reviewer` simplifications 1 to 5 | Carried: "Five simplifications the boundary review proposed" |
| `data-model` LOW: `role_assignment.section_id` has no index | Carried: "The role-assignment table has no index on its section" |
| `prompt-eval` LOW: the draft eval set is not typed through its contracts | Carried: "The draft eval set bypasses the output contracts" |
| `spec-conformance` LOW: on-behalf and unanswered not driven on the stack | Carried: "Two response paths no drive reaches" |
| `response_gather`'s `for_on_behalf` keyword | Carried: "`response_gather` has a keyword that changes nothing" |
| Every other finding | Fixed in E7-10 (#318) or E7-11 (#316), or covered by process pull request #305 |

### Five simplifications the boundary review proposed

From `code-reviewer`, accepted as not worth the risk inside the epic: the
lead-and-chair rule is written three times in SQL; the chair's walk to courses
with a lead appears twice; the policy-of-record rule is written in two forms;
`record_policy` recomputes what its caller already knows; and `publish_response`
converts a course week to a week itself. **Owner:** the next ticket that touches
each file. **Done when:** each rule is written once, or a record argues the
extra copy, and `publish_response` takes the week its caller already resolved.

### The role-assignment table has no index on its section

From `data-model`. E7 adds reads keyed by section on the student path (the
staff-name definer and the teaching-instructor lookup). **Owner:** E8, which
adds more student-path reads. **Done when:** `EXPLAIN` at a realistic size
(about twenty thousand rows) is recorded in ADR 0191 and shows the reads are
fine, or a partial index on `section_id` where the role is instructor exists.

### The draft eval set bypasses the output contracts

From `prompt-eval`. The cases in `tests/evals/response_draft/` are not typed
through `ResponseDraftOutput` or the gathered stream, so a change to either
contract would not fail them. **Owner:** E10's floors pull request, with the
entry "The draft and check evals have no floor". **Done when:** every case
builds its input and checks its output through those types.

### Two response paths no drive reaches

From `spec-conformance`. The exit drive reads an on-behalf response, but no
drive on the running stack publishes on behalf of a course, and none reads an
unanswered week past the deadline as the lead sees it. **Owner:** E8's
end-to-end work, or the first ticket that touches the on-behalf page.
**Done when:** one drive publishes on behalf and one reads an unanswered week
as the lead, each on a fresh stack and leaving no rows a rerun trips over.

### `response_gather` has a keyword that changes nothing

E7-10 made every draft gather use the on-behalf summary filter, so the
`for_on_behalf` keyword no longer changes what is read. **Owner:** the next
ticket that touches `response_gather`. **Done when:** the keyword is removed
from the function and its callers.
