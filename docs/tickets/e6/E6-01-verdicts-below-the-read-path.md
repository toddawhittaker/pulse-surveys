# E6-01 — Moderation verdicts govern the read path

**ID:** E6-01
**Branch:** `e6/verdicts-below-the-read-path`
**Depends on:** none
**Lane:** heavy (a new view and definer under `backend/app/views_sql/`, a Care
table, and invariant-marked tests rewritten)
**Size:** L
**Security-relevant:** this ticket decides which comments any reader can
reach. A defect here shows a threat or self-harm comment to an instructor,
feeds it to the summary model, or shows a comment nobody has moderated.

## Context

Today a comment with no `moderation_state` row counts as published
(`reported_status_of`, `coalesce(latest, INITIAL_STATE)`), and nothing writes a
row. Three carried entries meet here:

- A comment whose moderation never ran is shown and summarized
  (`carried-from-e5.md`, "A comment with no moderation verdict counts as
  published").
- SPEC §6.2's threat and self-harm class is suppressed neither in the read path
  nor in the summary gather (`../e4/deferred.md`). Its tripwire is the test
  `test_no_harm_classification_task_exists_yet_for_this_filter_to_have_missed`,
  which reds the moment `ClassificationTask` gains a second member. This
  ticket adds that member, so it owns the repair. **Widening the tripwire's
  expected set is not the repair**; the test's own message says so.
- `moderation_state` has no ordering that breaks a same-transaction tie
  (`../e4/deferred.md`). It must be fixed before the first writer, and the
  first writer is this ticket's definer.

This ticket also narrows the reveal door to Care-class answers, which makes
E6-03's comment handle safe: an instructor never holds the id of a
Care-class comment, because v004 never returns one.

The summary gather (`reporting.py::_comments_reaching_the_model`) does not read
`public.report_comment`; it reads `answer` directly and carries its own copy of
the blank-comment class. After this ticket it reads the view, and that copy is
deleted.

**v004 hides every seeded and fixture comment until verdicts are planted.**
v004 shows a comment only when it holds a verdict. No fixture, seed or e2e
world plants one today, so the moment v004 lands, every comment in every test
world, seed script and Playwright drive disappears. This ticket plants verdicts
everywhere in the same change. It does not leave that to a later ticket
(entry 22).

**Ruling 5.** Nothing reads a `threat_case` row until E10's Care queue, which
is Phase 2. The owner ruled on 2026-10-09 that no deployment reaches real
students until that queue exists. This ticket writes the ruling into SPEC §12's
phase lines and into ADR 0187. The design here does not change.

Read first: SPEC §4, §4.1 item 3, §5.2, §6.2, §7.4, §8 and §12; ADRs 0043, 0144,
0145, 0153 and 0162; `../e4/deferred.md`'s three moderation entries whole; and
this folder's README rulings.

## Owns

- **M1**, `down_revision = "ad9da2d96664"`. It adds:
  - `ClassificationTask.MODERATION` in `backend/app/models/ai.py`, with a
    per-task verdict `CHECK` built from the enums, the way the validity `CHECK`
    is built (entry 13);
  - `moderation_state.sequence`, an identity column that orders rows;
  - `moderation_attempt` in `backend/app/models/ai.py` (`answer_id` with
    `RESTRICT`, `attempted_at`): one append-only row per failed moderation
    call, which E6-02's attempt cap counts. `pulse_app` gets `INSERT` and
    `SELECT` on it and nothing else. This ticket only creates it; E6-02 writes
    and reads it;
  - `backend/app/models/safety.py` with `threat_case` (`answer_id` unique,
    `classification_id`, `opened_at`), in the `models/report.py` style (text
    with `CHECK`, `RESTRICT` foreign keys, `UuidPrimaryKey`). The opening row
    only; E10 designs the lifecycle;
  - `backend/app/views_sql/moderation_routing_v001.sql`: a `SECURITY DEFINER`
    with its own `NOLOGIN` owner, following `teaching_grant_end_v001.sql` and
    ADR 0043. One call writes a moderation verdict and its route together: a
    `FLAGGED_COLLAPSED` row for harmful or privacy, a `threat_case` row for
    threat or self-harm, nothing more for clear or nonsense. `pulse_app` gets
    `EXECUTE` on it and no privilege on `threat_case`;
  - `backend/app/views_sql/report_comment_v004.sql`, the same five columns as
    v003. A comment appears only when it holds a moderation verdict, and never
    when any of its verdicts, ever, is threat or self-harm;
  - `backend/app/views_sql/reveal_subject_for_answer_v002.sql`, which refuses
    an answer with no threat or self-harm verdict.
- `backend/app/services/moderation.py` (new), holding only the one Python call
  to the routing definer (the `services/roster_sync.py` pattern for
  `end_teaching_instructor`). 02 and 03 add to this module.
- `backend/app/services/report_comments.py`: `reported_status_of` orders by
  `sequence`.
- `backend/app/services/reporting.py`: the gather reads the view; a
  section-week is not summarized until every comment in it holds a verdict.
- The tripwire test module above, rewritten as planted-verdict tests.
- `tests/fixtures/report_comments.py`, `tests/fixtures/summary_job.py`,
  `tests/fixtures/care_subject.py`, and every other fixture that builds a
  comment.
- `scripts/seed_demo_story.py`, `scripts/seed_exit_story.py`,
  `scripts/seed_benchmark_history.py`: each plants a verdict under a named seed
  provenance (a prompt version that says it is a seed, never a real one).
- `tests/integration/test_identity_grants.py` (the new owner and grants).
- SPEC §5.2 (the "harmful … can be a self-harm disclosure" sentence), §8 (a
  comment is shown only once moderated; `threat_case`; `moderation_attempt`;
  the ordering), §12 (ruling 5, below), and §13 (`models/safety.py` and
  `services/moderation.py` drawn as built).
- ADR **0187**; amendments to ADRs 0144 and 0145.

**Must not touch:** the moderation prompt and the sweep (02), the decision
columns and routes (03), `CommentView` (03).

## Reuse, do not rewrite

From `services/report_comments.py`: `reported_status_of`, `visible_comments`,
`released_comments`, `stream_is_suppressed`, `n_threshold`, `COMMENT_VIEW`,
`_in_no_release_batch`, `INITIAL_STATE`. From `models/report.py`:
`MODERATION_STATES` and `_in_the_vocabulary`. From `ai/`: `ModerationVerdict`,
`ModerationOutput`, `record_classification`. `services/clock.now` (ADR 0109).

## Done when

1. **No verdict, no comment.** A comment with no moderation verdict is absent
   from `visible_comments`, from `released_comments`, from every release batch,
   and from the gather's model-facing input. A test plants a failed moderation
   run and asserts all four. The same world holds a verdicted comment that does
   appear in each, so emptiness cannot pass the test (entry 3).
2. **Care-class never reaches a reader.** A comment with a threat or a
   self-harm verdict, in a section-week at the threshold, is absent from the
   service's return, from a release batch's members and from the gather's
   model-facing input. This holds when a later verdict on the same comment is
   clear. A test proves each of the three, one per verdict.
3. **The exit's 3-response week, at the service and the payload.** In a
   3-response week with one self-harm comment, the routing definer writes a
   `threat_case` row; the instructor's report payload carries no comment, no
   count and no summary text drawn from that comment.
4. **A same-transaction pair orders by sequence.** Two decisions about one
   comment written in one transaction resolve to the second. The test runs
   both ways round.
5. **Verdict and route land together.** A definer call that fails after the
   verdict is written leaves neither the verdict nor the route. `pulse_app`
   cannot insert into `moderation_state` or `threat_case` directly, and one
   test proves it through the connection production uses (entry 46).
6. **The verdict check is per task.** A `MODERATION` row with a validity verdict,
   and a validity row with a moderation verdict, are both refused by the
   database.
7. **The reveal door narrows.** `reveal_subject_for_answer` refuses an answer
   with no Care-class verdict and still answers for one with a threat verdict,
   proven with planted verdicts on both sides.
8. **The gather waits.** A section-week with one unverdicted comment is not
   summarized; once the verdict lands, the next walk summarizes it. A test
   asserts both.
9. **The gather's blank class is the view's.** The gather's own copy of the
   blank-comment class is deleted, and a whitespace-only comment is left out
   of the gather by the view.
10. **A generated property for the per-stream gate.** One Hypothesis property
    asserts, over random worlds that include unverdicted and Care-class
    comments, that no answer is both visible under its week and in a batch,
    that every shown stream has at least the threshold of unreleased
    commenters, and that every batch slice has the threshold of authors over two
    or more weeks. The generator draws the Care-class and unverdicted cases its
    docstring names (entry 15).
11. **Credit does not move.** A comment's moderation verdict, of every kind,
    leaves the response's participation credit unchanged.
12. **Every world still shows its comments.** Every fixture, every seed script
    and every e2e world plants verdicts, and the existing suites and drives are
    green with their comments visible.
13. **The records match.** SPEC §5.2, §8 and §13 are edited as listed above.
    ADR 0187 records the view rule, the definer, the gather's wait, the
    ordering, and that an identity column orders by insert, not by commit.
    ADRs 0144 and 0145 carry amendment lines pointing at it.
14. **Ruling 5 is in the spec.** SPEC §12's phase lines carry one sentence
    saying that no deployment reaches real students until E10's Care queue
    exists, because before it a `threat_case` row has no reader. ADR 0187
    states the same ruling with its date, 2026-10-09. A grep of §12 for
    "Care queue" finds the sentence.

## Shares files with

- `services/moderation.py`: 02 and 03 add to it after this merges.
- `services/reporting.py`, `services/report_comments.py`,
  `tests/fixtures/report_comments.py`, `tests/fixtures/summary_job.py`,
  `tests/integration/test_identity_grants.py`: 03 edits them after this merges.
- `scripts/seed_*_story.py`: 07 edits them later.
- `docs/adr/README.md`, `docs/SPEC.md`: 02, 03, 05 and 07 later.

## MISTAKES entries to heed

3, 1, 2, 13 and 9 (the top five), and 22, 15, 19, 35, 43, 44, 46, 50, 51 and 53.

## Known traps

- **Entry 22.** v004 empties every comment world at once. Plant verdicts in
  fixtures, seeds and e2e worlds in this ticket. When a test fails inside its
  own fixture, suspect the fixture first (entry 13).
- **The e2e drives.** `tests/e2e/support/stack.ts` calls the summary job
  directly after seeding. With the gather waiting for verdicts, a seeder that
  plants no verdict yields no summary. Check every drive that submits a comment
  through the page and then reads it back; such a drive needs a verdict too.
- **Entry 43.** v004 reads `classification`, which joins the org-views SQL
  sweep's inventory. Reword any non-docstring prose under `backend/app/` that
  names it after `from`, a comma or the other trigger words. Never widen the
  sweep.
- **Entries 50 and 51.** Leaving a Care-class comment out of the view also
  leaves its author out of the commenter count. That is the conservative side.
  But a report read before a verdict lands and read again after can differ.
  Decide what the comment read returns for a section-week whose verdicts have
  not all landed, record it in ADR 0187, and assert it over the sequence of
  reads, not over one.
- **The tie-break.** An identity column orders by insert, not by commit. Say so
  in ADR 0187; two concurrent writers are not a same-transaction pair.
- **Entry 46.** A suite driven through the migrating engine has not tested a
  grant. At least one test reaches the definer and the view as `pulse_app`.
- **Entry 44.** A schema guard goes in the test body, never in a fixture, so a
  red is a FAILED and not an ERROR.

## Out of scope

- The moderation prompt, the model call and the sweep (02).
- Who may decide, and the columns that record it (03).
- The Care queue, the case lifecycle and `pulse_care`'s grants (E10).
