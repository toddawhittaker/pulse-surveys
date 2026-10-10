# E6 boundary review

The SPEC §14.2 item 6 record for E6 (moderation and exclusions). It has four
parts: the reviews and where each finding went, the exit clause driven against
the running stack, the standing questions every epic boundary re-asks, and CI on
the exit commit.

**This file is a skeleton until the boundary reviews run.** They run on the
epic pull request after E6-07 merges, so every result below that depends on
them says "pending". Nothing here claims a result that has not been produced.

## The reviews

The full battery CLAUDE.md names for an epic boundary, each with a fresh
context, over the epic's cumulative diff against `main`.

| Review | Head reviewed | Result |
|---|---|---|
| `epic-exit` | pending | pending |
| `invariant-coverage` | pending | pending |
| `adr-docs-completeness` | pending | pending |
| `spec-conformance` | pending | pending |
| `code-reviewer` | pending | pending |
| `app-security` | pending | pending |
| `privacy-authz` | pending | pending |
| `data-model` | pending | pending |
| `prompt-eval` | pending | pending |
| `a11y-copy` | pending | pending |
| `lti-oidc` | pending | pending |
| `threat-model` | pending | pending |

## The findings, and where each went

Pending. Each finding is fixed in a ticket pull request, or carried to
`../e7/carried-from-e6.md` with an owner and a done-when.

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
checkout's build. Its result on the exit commit: pending.

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

Fourteen test modules added in E6 carry the `invariant` marker, and
`pytest -m invariant --collect-only` collects every one of them (713 tests in
all on 72b062b0). Each module and its collected count:

| Module | Collected |
|---|---|
| `test_a_moderation_verdict_is_routed_only_through_its_definer.py` | 15 |
| `test_a_verdict_is_routed_only_after_its_window_closes.py` | 4 |
| `test_the_lead_review_queue_and_log_never_cross_to_a_sibling_lead.py` | 4 |
| `test_the_lead_review_queue_leaves_out_every_section_the_reader_teaches.py` | 5 |
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

## CI on the exit commit

Pending. The verdict is a completed run whose head SHA is the exit commit
(`docs/MISTAKES.md` entry 42).
