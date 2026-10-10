# E6-03 — The instructor excludes, keeps and undoes

**ID:** E6-03
**Branch:** `e6/instructor-decisions`
**Depends on:** E6-01
**Lane:** heavy (a grants file under `backend/app/views_sql/`, `api/deps.py`,
and the invariant-marked payload test)
**Size:** L
**Security-relevant:** the first write path a person drives on a comment, a
new handle on the instructor payload, and the participation note. A defect
here lets an instructor act on a comment they cannot see, or turns the note
into a category hint.

## Context

SPEC §5.2's lifecycle: `published` → `flagged-collapsed` → the instructor
excludes (with Undo) or keeps (with Undo). Excluding a comment the AI did not
flag needs a stated reason. Both directions are logged.

Ruling 3 puts the record on `moderation_state`: it gains the decider and the
reason, and E6-05's exclusion log is a read over it. Ruling 4 has the log show
the decider's role, not a name, so the row stores the role the decision was
made under. A role read off today's assignments would change when the
assignments do.

`CommentView` (`backend/app/schemas/report.py:232`) has no handle, so nothing
can name a comment to act on it. The handle is the answer id. That is safe
because of E6-01: v004 never returns a Care-class comment, and the reveal door
refuses any answer without a Care-class verdict, so an instructor never holds
the id of a comment the door would answer for. The card carries no dates
(ADRs 0153 and 0162 name that channel).

An instructor may decide only on a comment their report currently returns: a
shown stream, or a release batch. The looser rule, any comment in a section
they teach, would let them act on a comment they cannot see.

**The participation note (ruling 2).** This ticket builds it and writes its
rule into SPEC §5.2, replacing "no count" so the section no longer says both:

- Below the threshold, a flagged comment shows no chip and no flag-type hint,
  and the instructor sees no count except this note.
- At most one note per section-week. It names no stream and no category.
- It counts the comments in that week's held streams that carry a harmful or
  privacy verdict and that a decision has not kept.
- It never counts a threat or self-harm comment.

The held-note type is a free string today (`../e4/deferred.md`). It becomes a
closed set, harmful and privacy, that cannot express threat or self-harm, and
the note is computed at read time in `reporting._payload`, because states
change and a stored summary row does not.

Read first: SPEC §4, §4.1, §5.1, §5.2 and §8; ADRs 0145, 0153, 0162, 0178,
0179 and 0187; ADR 0185 (the generated wire types); the de-anonymization
entries in `../e5/carried-from-e4.md` and `carried-from-e5.md`; and
`api/leadership.py`'s write routes, which are the pattern.

## Owns

- **M2**, with `down_revision` set to M1's revision id as merged. It adds to
  `moderation_state`:
  - `decided_by_person_id`, nullable, a `person` foreign key with `RESTRICT`,
    as `audit_log.actor_person_id` is;
  - `decided_as`, the role the decision was made under, from a closed
    vocabulary that includes the instructor, the Lead Faculty and the
    department chair (the chair decides for a course with no lead), so E6-05
    needs no migration of its own;
  - `reason`, nullable, non-blank and bounded in length when present;
  - `CHECK`s: a decider names a role and a role names a decider; a row with no
    decider is the router's and is `FLAGGED_COLLAPSED`; a reason needs a
    decider.
- `backend/app/views_sql/moderation_decision_grants_v001.sql`: column-grain
  `INSERT` for `pulse_app` on exactly the columns a decision writes.
- `csrf_verified_instructor` in `backend/app/api/deps.py`, following
  `csrf_verified_leadership`.
- The decision service in `backend/app/services/moderation.py`: exclude, keep
  and undo. A reason is required to exclude a comment with no harmful or
  privacy verdict. The strict visibility rule above. Undo writes the state the
  comment held before the decision it undoes.
- The decision routes in `backend/app/api/instructor.py`, and their refusal
  sentences in `backend/app/copy/instructor_report.py`.
- `backend/app/services/report_comments.py` and `backend/app/schemas/report.py`:
  `CommentView` gains the handle, the flag class (harmful, privacy or none) and
  "decided by you". No date, no decider name, no time.
- `HeldNoteType` in `backend/app/ai/contracts.py`; `WeeklySummaryRecord.held_note_type`
  and `SummaryView.held_note` take it; the participation note's payload member;
  both computed in `reporting._payload`.
- `tests/integration/test_the_report_payload_repeats_nothing_beyond_the_comment_service.py`,
  amended for the new members, and only those.
- `tests/unit/test_the_moderation_state_ordering_has_one_home_under_backend_app.py`:
  it admits `services/moderation.py` as the one writer, and still holds the
  ordering to one home.
- E6-01's test that `pulse_app` cannot insert into `moderation_state`, amended
  to the column grant.
- `tests/integration/test_identity_grants.py`, `tests/fixtures/report_comments.py`,
  `tests/fixtures/summary_job.py`.
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated with
  `scripts/export_openapi.py` and `npm run gen:wire`. `frontend/src/api/instructor.ts`
  only as far as the type check needs; E6-04 owns it after.
- SPEC §5.2 (the participation-note rule above), §8 (no `exclusion_log`; the
  decision columns; `audit_log` holds no exclusion or keep), and §13 (the
  `loop.py` line loses `exclusion_log`).
- ADR **0189**.

## Reuse, do not rewrite

`person_of`, the CSRF token helpers and `csrf_verified_leadership` in
`api/deps.py`. `teaching_instructor_assigned` and `taught_section_ids` in
`services/authz.py`. `visible_comments`, `released_comments`,
`reported_status_of`, `stream_is_suppressed` and `n_threshold` in
`services/report_comments.py`, for the visibility rule, rather than a new
query. `models/report._in_the_vocabulary` for the role `CHECK`.
`services/clock.now`. `ModerationVerdict` as the source of the flag classes.

## Done when

1. **Exclude, keep, undo.** An instructor excludes a flagged comment, keeps
   it, and undoes each. After each undo the comment reports the state it held
   before. Each step is one appended row naming the instructor and their role.
2. **A reason for an unflagged exclusion.** Excluding a comment with no harmful
   or privacy verdict without a reason is refused with a governed sentence. A
   blank reason, or one over the bound, is refused by the route and by the
   database. The reason is checked as sent, before any trimming (entry 29).
3. **Only what the report returns.** A decision on a comment in a held stream,
   on a comment of a section the instructor does not teach, or on an answer id
   that is not a comment, is refused, and writes no row. The same world holds
   a decision that succeeds (entry 3).
4. **The gate runs at dispatch.** A decision POST with no CSRF token, or from
   another origin, is refused over HTTP against the built application, and the
   same POST with the token succeeds (entry 47).
5. **The handle carries nothing else.** `CommentView` carries the answer id,
   the flag class and "decided by you", and no date, time, week, author or
   decider. The invariant payload test asserts the exact member set.
6. **The held-note type is closed.** `HeldNoteType` cannot be built with a
   threat or self-harm value; the type check refuses it, and a test proves the
   runtime refuses it too.
7. **The participation note.** In a held stream with one harmful comment, the
   week carries one note with the count 1 and no category or stream. In the
   same world with one self-harm comment instead, the week carries no note.
   Keeping the harmful comment removes it from the count. Above the threshold,
   no note is carried, and the flagged comment shows its chip.
8. **The grants hold as production runs them.** `pulse_app` can insert only the
   decision columns, proven through the production connection (entry 46), and
   still holds nothing on `threat_case`.
9. **The records match.** SPEC §5.2, §8 and §13 are edited as listed above.
   ADR 0189 records the handle and why it is safe, the visibility rule, the
   no-dates rule, the stored role, the participation note and the cost ruling 2
   accepted, the gradebook limit stated in the README, and the
   de-anonymization statement for instructor views. That statement reads ADRs
   0153, 0162, 0178 and 0179 first.

## Shares files with

- `services/moderation.py`, `services/reporting.py`, `ai/contracts.py`,
  `docs/SPEC.md`, `docs/adr/README.md`: E6-02 in parallel. Keep both sides.
- `services/moderation.py`: E6-05 adds the Lead Faculty door after this
  merges.
- `frontend/src/api/openapi.json`, `wire.gen.ts`: E6-05 after this merges.
- `frontend/src/api/instructor.ts`: E6-04 after this merges.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 22, 29, 35, 46, 47, 50, 51 and 53.

## Known traps

- **Entry 22.** The new `CommentView` members and the decision columns reach
  every fixture and the invariant payload test. Change the fixtures in this
  ticket; amend the invariant test only by the new members.
- **Entry 51.** The note's count changes when a verdict lands or a decision is
  made. Assert what two consecutive reads of the same week reveal, not one
  read.
- **Entry 50.** The note counts comments, and the threshold counts people.
  The note is not a threshold and must never feed one.
- **Entry 35 and 53.** The visibility rule must find the comment the way the
  report does. Do not rebuild it from the decision's own inputs; call the
  report's functions, and test one level out (a released comment, a comment in
  the other stream).
- **Entry 43.** A `Field(description=...)` or refusal sentence that names
  `section` or `course` after a comma or `from` trips the SQL sweep. Reword it.

## Out of scope

- The page that renders all this (04).
- The Lead Faculty's decisions and the exclusion log (05).
- Staff names (E9).
