# E8 boundary review

The SPEC §14.2 item 6 record for E8 (student loop closure). It has four parts:
the reviews and where each finding went, the exit clause driven against the
running stack, the standing questions every epic boundary re-asks, and CI on
the exit commit.

The battery ran on 1ecd5b55, the head of E8-02 (carrying E8-01 and E8-03),
against `main` at 14bcb93d. Its findings became two fix tickets: E8-05 (#328)
and E8-06 (#327). The standing questions were answered by E8-04, below.

## The reviews

The full battery CLAUDE.md names for an epic boundary, each with a fresh
context, over the epic's cumulative diff against `main`.

| Review | Head reviewed | Result |
|---|---|---|
| `invariant-coverage` | 1ecd5b55 | 2 MED, 1 LOW |
| `adr-docs-completeness` | 1ecd5b55 | 2 LOW |
| `spec-conformance` | 1ecd5b55 | 2 LOW; every done-when of E8-01 to E8-03 met |
| `code-reviewer` | 1ecd5b55 | 3 LOW, 4 simplifications |
| `app-security` | 1ecd5b55 | Nothing found |
| `privacy-authz` | 1ecd5b55 | 1 MED, and a note for the owner |
| `data-model` | 1ecd5b55 | 2 LOW, and a note for E9 |
| `prompt-eval` | 1ecd5b55 | Nothing found |
| `a11y-copy` | 1ecd5b55 | 5 MED, 2 LOW |
| `lti-oidc` | 1ecd5b55 | 1 MED, 1 LOW |
| `threat-model` |  | not run: SPEC §14.3 does not mark E8 ⚠ |
| `epic-exit` | | |

## The findings, and where each went

**Fixed in E8-05 (#328):**

- MED (`privacy-authz`): the student trend's mean was an unrounded number, so
  with the shares it gave back the rater count and the bucket counts. The mean
  and the workload median are now rounded to one decimal on the server, with a
  test that a seven-rater week's mean does not identify seven.
- MED (`invariant-coverage`): the test that the participation score is the
  reader's own row was not invariant-marked. It now sits in an invariant module.
- MED (`invariant-coverage`): the student copy keys were not swept for SPEC
  §4.1 item 1's comparison words in the invariant pass. They are now.
- LOWs (`adr-docs-completeness`): ADR 0197 named a ruled dispute as open, and
  ADR 0198 restated the spec. Both corrected.
- LOW (`data-model`): a comment in `services/identity.py` pointed at the
  carried file for the index measurement; it now points at ADR 0191.
- LOW (`data-model`): the workload median re-ran the answerer count; it reuses
  the first.
- LOW (`code-reviewer`): `StudentParticipation` was missing from `__all__`.

**Fixed in E8-06 (#327):**

- MED (`lti-oidc`) and MED (`a11y-copy`): the page printed the score with no
  unit under words saying it was what the gradebook shows, while the platform
  scales the score to its column. The page now labels it as a percentage, and
  ADR 0198 and the schema's descriptions are corrected.
- The other four `a11y-copy` MEDs and both LOWs: the ledger's lines are a list;
  the trend draws once; the percent histogram has a data table; the held
  ratings notice names ratings in its visible title; the reply link is not
  repeated beside the results lead; and hours are spelled out.
- LOW (`code-reviewer`): the small-N notice no longer gives a cause, since a
  week can be held while moderation is pending.
- LOW (`code-reviewer`): the landing lead tests now render a second section
  before asserting an absence.
- LOW (`invariant-coverage`): a component test plants comparison and
  university data and finds it absent from the text and the labels.
- Simplifications 1 to 3 (`code-reviewer`).
- A HIGH found by E8-06's own re-check, the histogram's table inside an element
  marked `role=img` (so screen readers never reached it), fixed in the same
  pull request.

**Recorded, nothing owed:** `spec-conformance`'s LOW that
`models.grades.latest_grade_sync` and the grading change were outside E8-03's
Owns list; the pull request body says so.

**Carried to E9, each with an owner and a done-when in
`../e9/carried-from-e8.md`:** whole-number shares can still pin the rater count
at small n (`privacy-authz`'s note for the owner); simplification 4, splitting
the student read out of `services/response_loop.py`; the landing's full results
read per section (`spec-conformance`); set-based staff-name reads for E9's
leadership pages (`data-model`); and the ADR 0198 rejected-alternative line that
overstates a failed post with no response code (`lti-oidc` LOW, left after E8-05).

## The exit clause, driven against the running stack

SPEC §14.3's E8 exit: "the full weekly loop demos end-to-end from one student's
seat."

Two pieces of E8-04 drive it:

- **`tests/e2e/exit-student-loop.spec.ts`**, its first block, over
  `MATH-140-E1FF`. Classmates' answers for the exit week and the week before
  it are written by `scripts/seed_student_loop_exit_story.py`; the learner
  answers the exit week's survey through the page. The Lead Faculty member sets
  the course to required the day before the report opens, the window closes,
  and the moderation sweep gives every comment its verdict. On the next launch
  the landing shows no results lead, and the results page is the closed door:
  the course's name, the learner's own posted score and ledger, and no
  response, figure, comment, notice or confidentiality line. The instructor
  publishes; the landing now leads with "Week N results are in", and its link
  opens the page, which reads the response first (checked by document order),
  then the trend, two distributions, the workload median, the six instructor
  comments, the course stream's small-N notice in place of its one comment, and
  the confidentiality line once. One week back, both streams' ratings are held.
  Every page is scanned with axe. The lead sets the course back to encouraged
  before the next week's report opens.
- **`tests/integration/test_the_student_loop_exit_story_reads_as_the_drive_expects.py`**,
  which plants a launched `MATH-140-E1FF`, runs the seeder as its runbook does,
  routes the verdicts through the product's writer, and reads both weeks
  through `response_loop.student_week_results`, never the seeder's own count
  (`docs/MISTAKES.md` entry 58).

**The landing's lead over a held week.** The ticket's story has the landing
lead with "Week N results are in" before the closed door. E8-03 built, and
SPEC §5.4 and §14.3 now say, that a held week gives no lead, because "results
are in" over a closed door teases what the hold keeps back. The drive asserts
what was built: no lead while held, the lead once released.

**The two carried response paths** are the drive's second block, over
`NURS-8100-Q2FF`: past 48 hours the lead reads the required, unanswered week as
owed with no on-behalf door; past 96 hours the student reads the closed door,
and the lead opens the week on the on-behalf page and reads it unanswered (an
empty composer and no response card), then publishes on behalf; the student
reads the lead's name and role.

**Green twice on one stack, shown by structure.** No stack built from this
branch was available locally: the commands that rebuild one wipe the shared
development database. So the drive's first run is CI's, and the claim that a
second run on one stack stays green rests on how the drive is built. The
response and policy tables are append-only and are never cleaned. Each run takes
fresh section-weeks: the seeder takes the first of `MATH-140-E1FF`'s course
weeks 5 and 6 with no response, and the response-path block takes the first
week of `NURS-8100-Q2FF` with no response. Each run's required row is set the
day before its own week's report opens, which is after the previous run's
encouraged row, and its encouraged row is set before the next week's report
opens. The posted score and the lead mappings are deleted on the way out. A
third run of the student's week on one stack is refused by the seeder, with a
sentence saying the stack needs to be fresh.

**What the drive does not reach.** The from-earlier-weeks group: a release
batch's `cut_at` is the database's wall clock, so on a stack with a moved clock
every batch is cut after any past week's report opened, and the group never
shows. **The posted score is planted**, not posted, because a passback would
write into the gradebook `exit-grade-passback.spec.ts` reads later. Both are
carried in `../e9/carried-from-e8.md`.

## The standing questions

### `PERSON_TABLES`

E8 adds no table and no migration (`git diff 22a81a41 -- backend/migrations` is
empty). `PERSON_TABLES` is unchanged (`user`, `user_identity`, `person`) and
correct. E8's new student-path reads are of `grade_sync` (the student's own
posted score, ADR 0198), whose class docstring records why it is not a person
table, and of the comment and figure reads behind `report_comment` v004, which
join no identity column. `tests/integration/test_identity_column_marker.py`
passed (32 tests) on the E8-04 branch. The owner stays E13.

### The session-read sweep, shown by planting

A session read from the request (`from app.services.session import
session_from_request`) was planted in the results route's module,
`backend/app/api/student.py`, and then in `backend/app/services/response_loop.py`,
which E8 grew most, one at a time.
`tests/unit/test_only_the_dependency_module_reads_a_session_from_a_request.py`
went red on each (1 failed, 3 passed), naming the planted module; restored, it
is green (4 passed) and the tree clean. E8 added no route-serving module, so the
sweep's two disclosed limits stand as disclosed and are re-carried.

### The TypeScript 7 watch

Checked 2026-10-11: `typescript-eslint`'s latest is 8.71.1, and its peer range
is still `typescript >=4.8.4 <6.1.0`, so TypeScript 7 was not admitted during
E8. The root `package.json` pins TypeScript 6.0.3 and typescript-eslint 8.71.1.
Re-carried with the date.

### Every new E8 invariant-marked module is collected by the isolated pass

Nine test modules added in E8 carry the `invariant` marker, all from E8-01, and
`pytest -m invariant --collect-only` collects every one of them (971 tests in
all on the E8-04 branch). E8-01 also extended four existing invariant-marked
modules: the student-path import sweep, the copy inventory's items 4 and 5, and
the two student payload sweeps. Each new module and its collected count:

| Module | Collected |
|---|---|
| `test_a_held_week_serves_nothing_about_the_week_and_reaches_no_other_page.py` | 2 |
| `test_a_students_comment_model_carries_nothing_but_its_text_and_stream.py` | 24 |
| `test_a_students_figures_are_shares_and_are_withheld_below_the_threshold.py` | 7 |
| `test_a_students_stream_below_the_threshold_carries_its_small_n_state_and_no_comment_text.py` | 2 |
| `test_a_students_week_names_nothing_outside_her_section_and_no_count.py` | 3 |
| `test_no_comment_a_student_reads_carries_its_id_status_time_or_week.py` | 3 |
| `test_only_published_and_kept_comments_reach_a_student.py` | 2 |
| `test_the_release_group_shows_on_the_latest_week_only_and_only_what_was_cut_before_it_opened.py` | 4 |
| `test_the_students_comment_reads_go_through_the_comment_view_and_never_the_answer_table.py` | 3 |

## CI on the exit commit

Recorded with the reviews, by the run's id on the final epic head
(`docs/MISTAKES.md` entry 42).
