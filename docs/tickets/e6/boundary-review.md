# E6 boundary review

The SPEC §14.2 item 6 record for E6 (moderation and exclusions). It has four
parts: the reviews and where each finding went, the exit clause driven against
the running stack, the standing questions every epic boundary re-asks, and CI on
the exit commit.

The battery ran on the epic head c1b79714, after E6-01 to E6-08 merged.
**Stopping rule, declared in the reviewers' common brief before any finding
arrived:** confirmed HIGH and MEDIUM findings get tests-first fixes in one
ticket pull request into the epic branch; LOWs are fixed there or carried with
an owner and a done-when; one re-check pass over the fixes; no further round
unless something is red or a HIGH appears. The fixes became E6-09 (#302,
heavy) and E6-10 (#301, light). `epic-exit` ran last, on the epic head after
both merged.

## The reviews

The full battery CLAUDE.md names for an epic boundary, each with a fresh
context, over the epic's cumulative diff against `main`.

| Review | Head reviewed | Result |
|---|---|---|
| `invariant-coverage` | c1b79714 | 2 HIGH, 4 MED, 2 LOW |
| `adr-docs-completeness` | c1b79714 | 3 MED, 4 LOW |
| `spec-conformance` | c1b79714 | 2 MED, 4 LOW; every done-when of E6-01 to E6-08 met |
| `code-reviewer` | c1b79714 | 1 MED, stale comments, 8 simplifications |
| `app-security` | c1b79714 | Nothing found |
| `privacy-authz` | c1b79714 | 1 MED, 1 LOW |
| `data-model` | c1b79714 | 1 HIGH, 1 MED, 1 LOW |
| `prompt-eval` | c1b79714 | 1 MED, 5 LOW |
| `a11y-copy` | c1b79714 | 1 HIGH, 3 LOW |
| `lti-oidc` | c1b79714 | Nothing found |
| `threat-model` | not run | SPEC §14.3 does not mark E6 ⚠ |
| `epic-exit` | c8b7207a | Both halves of the exit clause met; 3 LOW |

## The findings, and where each went

**Fixed in E6-09 (#302), tests first:**

- HIGH (`data-model`): the two E6 migrations' downgrades destroyed decision
  and Care records and could not be re-applied. They now refuse while
  `threat_case`, `moderation_attempt` or `moderation_state` holds a row, or
  while a decision names its decider.
- HIGH (`invariant-coverage`): withholding an old ordinary summary on a stream
  now below the threshold had no §4.1 test. It now has one, through the
  served report, with a full stream as the control.
- HIGH (`invariant-coverage`): the exclusion log's excerpt rule had no §4.1
  test, and two of its three cases had no test at all. One marked test now
  covers a held stream, a week not yet moderated and a comment released by a
  batch, beside a shown row.
- MED (`code-reviewer`): a week waiting on a verdict told the instructor "No
  comments this week." It is now served as suppressed.
- MED (`privacy-authz`): ruling 7's filter read only current teaching grants,
  so a section came back into a reader's queue and log once the roster ended
  their grant. The queue, the leader door and the log now leave out sections
  the reader teaches or has taught. This needed `pulse_app` to read two
  columns of `ended_teaching_grant` (dispute E6-09-01, ruled; ADR 0183
  amended).
- MED (`invariant-coverage`): a lead who also chairs a department had no test
  against seeing a sibling lead's course. It has one now.
- MED (`invariant-coverage`): the ruling-1 queue test and the self-harm exit
  test ran outside the isolated pass. Both are marked now, and the
  denial-module guard knows the `leaves_no_trace` shape.
- MED (`invariant-coverage`): the student-path import sweep did not watch
  `app.services.moderation`. It does now, with a planted import.
- MED (`invariant-coverage`): the queue and log pages showed students' comment
  text with no confidentiality line, while the instructor report carries one.
  They carry it now, with canary keys for the collector.
- MED (`spec-conformance`): the log showed an undone exclusion as standing, and
  an undone keep as an exclusion with no reason. Undo rows now show as
  reversals (`is_undo`).
- MED (`data-model`): the log ran three queries per section, week and stream.
  It now costs a fixed number.
- MED (`prompt-eval`): the eval set had no case for the moderation prompt's
  own rules. It gains injection-shaped threat and self-harm cases, a threat
  that is also abusive, a harmful-and-private comment, and clear near-misses.
  No floor moved.
- MED (`adr-docs-completeness`, `spec-conformance`): ADRs 0187 and 0188, their
  index rows, SPEC §8 and the moderation module's docstring still described
  the attempt cap before ruling 8 and E6-08. All corrected.
- LOWs fixed there: the queue's exemption from §5.2's "appear together"
  sentence is written into §5.2, §5.5 and ADR 0190; ADR 0187's broken
  blockquote; ADR 0188's stale rejection; the repo README's empty beat
  schedule; `CommentFlag` typed as `HeldNoteType`; one definition of "closed";
  the small-N summary cases pinned to `summary.v3`; the refusal's HTTP status
  in the sweep's log line; stale comments; the participation note's leftovers
  in `design/`.
- The E6-09 review itself found two more MEDs (`data-model`): the routing
  downgrade did not count `moderation_attempt`, and the log's commenter count
  grouped over all history. Both were fixed in one round and re-checked clean.

**Fixed in E6-10 (#301):**

- HIGH (`a11y-copy`): every moderation control on the instructor report
  removed itself when pressed, dropping keyboard focus and announcing nothing.
  Focus now moves to the reason field, back to Exclude on Cancel, and to the
  card after a decision, with the outcome in a status region.
- LOWs: the reason refusal is tied to its field; each "Show the numbers"
  toggle names its stream; the log row says who decided in a sentence.

**Carried, each with an owner and a done-when in
`../e7/carried-from-e6.md`:** the import cycle between the moderation and
report services; splitting `services/moderation.py`; three small
redundancies; a test linking the reason length in the frontend and the
backend; comments that tell ticket history; a partial index for the review
queue; the moderation precision floor (E10); and `grading.py`'s opposite
boundary for "closed".

**Not ours:** `CLAUDE.md` still names E5.1 as the active epic. The open
process pull request #290 changes it, and it waits for the owner.

**For the owner:** `SummaryView.held_note` has no writer, and SPEC §5.1 still
allows "one comment is held for review". Whether that note survives ruling 6
is the owner's question (`code-reviewer`). An instructor can keep a comment a
Lead Faculty member excluded; SPEC §5.2 allows it and the log records it
(`app-security`, a design note).

## The exit clause, driven against the running stack

SPEC §14.3's E6 exit: "the anti-cherry-picking trail is visible up-chain, and a
welfare-flagged comment in a 3-response week provably reaches Care with no trace
in the instructor view."

Two pieces of E6-07 drive it:

- **`tests/e2e/exit-moderation.spec.ts`**, over the story
  `scripts/seed_moderation_exit_story.py` writes into `BIOL-215-R3WW`. The
  real moderation sweep asks the mock provider, and the real summary walk
  runs. The drive shows the instructor excluding an unflagged comment with a
  reason and keeping a flagged one. It reads the exclusion log as the Lead
  Faculty seat and the chair seat: both rows reach the lead while the course
  has a lead, and reach the chair once it has none, because a course with a
  lead is its lead's to review (SPEC §2.1, ADR 0190). An instructor-only seat
  reaches no log. The drive also reads the `threat_case` row for the comment
  carrying the self-harm marker. It compares the instructor's report for that
  three-response week with a week that has no comment, in every member that
  shows or counts comments, and checks a canary week in the same world whose
  comments do show.
- **`tests/integration/test_a_self_harm_comment_opens_a_threat_case_and_leaves_no_trace_in_the_report.py`**,
  the same claim in the pytest world: the sweep against the mock provider,
  the `threat_case` table read directly, the served report unchanged in its
  comment-bearing members, the summary equal to a no-comment week's, and a
  canary week.

The drive's first run is CI's: the shared Compose stack serves the main
checkout's build. Its result on the exit commit c8b7207a: all six tests in
`exit-moderation.spec.ts` passed in CI run 38100511357, with 97 Playwright
tests passed in all.

**`epic-exit`'s verdict on c8b7207a.** Both halves are met. The reviewer
confirmed the CI run by its id and head SHA, and ran 36 of the integration
tests behind the clause itself. Its three LOWs:

- In a three-response week, the small-N rule alone already empties the comment
  list, so the comment-list comparisons pass there whether moderation works or
  not. The proof rests on the summary comparison and the release-batch test
  (`test_a_care_class_comment_reaches_no_reader.py`), and both are present.
  Neither may be dropped without a replacement.
- "Reaches Care" means a `threat_case` row for now, because no Care reader
  exists until E10. That is what §14.3's E6 entry asks for, and ruling 5 keeps
  real students away until E10.
- An earlier count of the exit drive's tests was wrong. This record gives the
  right count.

## The standing questions

### `PERSON_TABLES`, asked of `threat_case` and `moderation_state.decided_by_person_id`

`PERSON_TABLES` is unchanged (`user`, `user_identity`, `person`), and the answer
is correct for both. `threat_case` names an `answer` and a `classification`,
which put it two hops from `response.user_id`, so the person walk in
`tests/integration/test_identity_column_marker.py` reaches it. It holds no
identity: its columns are the comment, the verdict that routed it, and when the
case opened. `pulse_app` holds no privilege on the table, which the routing
definer writes, and the only route from a case to a name is the audited Care
reveal (SPEC §4, §6.2).
`moderation_state.decided_by_person_id` is a `person` key, the actor convention
`audit_log.actor_person_id` and `comparison_set.created_by_person_id` already
use. The identity behind it sits on `user_identity`, which `pulse_app` holds no
`SELECT` on by any mechanism. Both tables sit in
`REACHED_TABLES_THAT_CARRY_NOTHING` with pinned column tuples, so either entry
expires the first time its table grows a column. The owner stays E13.

### The session-read sweep, shown by planting

A session read from the request (`from app.services.session import
session_from_request`) was planted in E6's two route-serving modules,
`backend/app/api/leadership.py` (the review queue, the lead's decision door and
the exclusion log) and `backend/app/api/instructor.py` (the instructor's
decision route), one at a time.
`tests/unit/test_only_the_dependency_module_reads_a_session_from_a_request.py`
went red on each, naming the planted module; restored, it is green and the tree
clean. E6 added no route-serving package outside `backend/app/`, so the sweep's
two disclosed limits stand as disclosed and are re-carried.

### The TypeScript 7 watch

Checked 2026-10-10: `typescript-eslint`'s latest is 8.71.1, and its peer range
is still `typescript >=4.8.4 <6.1.0`, so TypeScript 7 was not admitted during
E6. The root `package.json` pins TypeScript 6.0.3 and typescript-eslint 8.71.1.
Re-carried with the date.

### Every new E6 invariant-marked module is collected by the isolated pass

Twenty test modules added in E6 carry the `invariant` marker, and
`pytest -m invariant --collect-only` collects every one of them (732 tests in
all on c8b7207a, measured again after E6-08, E6-09 and E6-10 merged). Each
module and its collected count:

| Module | Collected |
|---|---|
| `test_a_moderation_verdict_is_routed_only_through_its_definer.py` | 15 |
| `test_a_verdict_is_routed_only_after_its_window_closes.py` | 4 |
| `test_the_lead_review_queue_and_log_never_cross_to_a_sibling_lead.py` | 4 |
| `test_the_lead_review_queue_leaves_out_every_section_the_reader_teaches.py` | 6 |
| `test_an_instructor_decides_only_on_a_comment_their_report_returns.py` | 3 |
| `test_the_lead_review_routes_refuse_everyone_without_a_leadership_grant.py` | 9 |
| `test_no_care_class_comment_reaches_the_lead_review_queue_or_log.py` | 5 |
| `test_a_care_class_comment_reaches_no_reader.py` | 17 |
| `test_the_application_role_inserts_only_a_decisions_columns.py` | 3 |
| `test_the_per_stream_gate_holds_over_generated_moderated_worlds.py` | 2 |
| `test_a_comment_with_no_moderation_verdict_reaches_no_reader.py` | 3 |
| `test_the_week_report_carries_no_held_count.py` | 7 |
| `test_a_decided_comment_card_names_nobody.py` | 1 |
| `test_a_moderation_state_row_with_no_decider_is_the_routers_alone.py` | 2 |
| `test_the_lead_review_queue_shows_what_ruling_one_allows.py` | 6 |
| `test_a_self_harm_comment_opens_a_threat_case_and_leaves_no_trace_in_the_report.py` | 1 |
| `test_a_lead_who_also_chairs_never_sees_a_sibling_leads_course.py` | 3 |
| `test_an_ended_teaching_grant_still_keeps_its_section_out_of_the_leaders_review.py` | 4 |
| `test_the_exclusion_log_withholds_every_excerpt_its_instructor_is_not_shown_under_a_week.py` | 1 |
| `test_the_report_serves_no_ordinary_summary_of_a_thin_stream.py` | 1 |

## CI on the exit commit

Green. CI run 38100511357, the push run on the epic branch, completed with
success on head SHA c8b7207a, the exit commit (`docs/MISTAKES.md` entry 42).
This record changes only documents, so its own pull request's run is checked
again before it merges.
