# E7-10 — The boundary review's fixes

**ID:** E7-10
**Branch:** `e7/boundary-fixes`
**Depends on:** E7-01 to E7-08 (merged)
**Lane:** heavy
**Why this lane:** it changes the draft gather and the on-behalf doors behind invariant-marked tests, adds invariant tests, and edits the copy inventory's surface map.
**Size:** M
**Security-relevant:** yes. It closes a paraphrase path from an excluded comment into published text, a connection-pool exhaustion, and an untested on-behalf refusal.

## Context

The E7 boundary battery ran on the epic head 7b5f0c94 (`boundary-review.md`).
Its confirmed HIGH and MEDIUM findings outside accessibility (which E7-11
fixes) are fixed here, tests first, with the cheap LOWs. The rest is carried in
`../e8/carried-from-e7.md` with an owner.

## Done when

1. **The on-behalf draft refuses what the instructor's does** (invariant-coverage
   HIGH). Invariant-marked tests drive the on-behalf draft past +96h with a
   scripted draft lifting a run of an excluded, a still-flagged and a
   held-stream comment: each refused, no row written, beside an accepted
   control lifting a published comment. The same pair for a count stated beside
   a held stream. The on-behalf gather and prompt carry no comment and no count
   on a held theme.
2. **No summary written before the week's latest exclusion feeds any draft or
   check** (privacy-authz MED). The instructor's gather applies the same filter
   as the on-behalf gather; the `for_on_behalf` branch for summaries goes. A
   test excludes a comment after its summary was written: neither the
   instructor's draft nor check prompt carries that summary or its themes; a
   summary written after the decision is still fed. ADR 0195 is corrected.
3. **A model call holds no database connection, and one person runs one at a
   time** (app-security MED). Every draft and check path (instructor and
   on-behalf) does all its reads before the model call and ends its transaction
   first; a test's gateway stub asserts the pool has no checked-out connection
   at call time. A second draft or check from the same person while one is in
   flight is refused 429 with one fixed sentence before any model call; a test
   asserts the stub is never called for it.
4. **An on-behalf draft is written in the lead's voice** (prompt-eval MED).
   `response_draft.v3.md` takes the author's role and frames the draft as a
   named leadership role writing to the class; for on-behalf it never promises
   an action in the instructor's voice. The instructor path uses v3 too, with
   the instructor role. v1 and v2 are removed with their pin rows (no draft is
   ever stored). The eval set gains an on-behalf family, a stream with a null
   summary, and a week with no themes; `draft_check` gains a no-themes and a
   null-summary case; each new case has a breach that fails its grader. Each
   eval set's `PROMPT_VERSION` equals its task's version, and a test fails when
   they differ.
5. **The first publisher can come back to edit an on-behalf response**
   (code-reviewer MED). Once a week is answered, its on-behalf read answers the
   first publisher with the response; every other reader still gets the one
   404. The on-behalf page seeds its composer from that answer. A test covers
   publish, a fresh read, and an edit.
6. **Edit is offered only to the first publisher** (code-reviewer LOW).
   `WeekResponseView` carries `can_edit`; the composer shows Edit only when it
   is true; a two-instructor test pins it.
7. **The untested reads are tested and marked** (invariant-coverage MEDs and
   LOW). The instructor's `GET …/response` has a marked test: own week served,
   and the sibling section, a nonexistent section and an unpublished week each
   get the report's own 404, byte for byte, naming nothing. The draft routes'
   not-taught, nonexistent and unpublished refusals, the sibling publish
   refusal, and the two policy-route isolation tests carry `invariant`. The
   student benchmark-exclusion drive also opens the results page.
8. **The results page is its own copy surface** (invariant-coverage and
   privacy-authz LOW). Its strings move to a `student_results.` prefix, placed
   in the surfaces that owe no confidentiality line, with the reason: it shows
   only staff-written text today; `../e8/carried-from-e7.md` reopens it when E8
   adds anything derived from students.
9. **The records match** (adr-docs and spec-conformance MEDs and LOWs). SPEC §8's
   `response_policy` line says a row covers one course, fixed when written, and
   the policy in force for a course is its latest row whoever wrote it; SPEC
   §5.3 says a course's setting carries over when its lead changes, with a test
   and an ADR 0193 line; ADR 0193 says why `prefix_id` stays. SPEC §13's api,
   copy, services and views_sql lines match the files. ADR 0195's "two
   refusals" reads three, and its stale `RESPONSE_TEXT_MAX` line goes;
   `schemas/report.py` imports the constant from `models/loop.py`. The five E7
   attempt files under `docs/tickets/e0/.attempts/` move to
   `docs/tickets/e7/.attempts/`. Comments that cite fix rounds are reworded
   to cite the SPEC or ADR; stale comments in `WeekEyebrow.tsx` and
   `models/identity.py` are corrected. The 502 sentence and status are defined
   once; `STREAM_ON_THE_WIRE` becomes a plain lower-casing.

## Not in this ticket

Accessibility (E7-11). The remaining simplifications, the `role_assignment`
section index, the summary-walk watermark, the 409 on a publish race, and the
on-stack `unanswered` drive are carried in `../e8/carried-from-e7.md`.
