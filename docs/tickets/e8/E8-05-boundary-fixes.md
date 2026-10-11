# E8-05 — The boundary review's fixes

**ID:** E8-05
**Branch:** `e8/boundary-fixes`
**Depends on:** E8-01, E8-02, E8-03
**Lane:** heavy
**Why this lane:** it changes what the student read serves under §4.1 and adds invariant-marked tests.
**Size:** S
**Security-relevant:** yes. It closes a path from an unrounded mean to the number of classmates who rated.

## Context

The E8 boundary battery ran on 1ecd5b55 (`boundary-review.md`). This ticket fixes its backend, test and record findings. E8-06 fixes the page's.

## Done when

1. **No figure carries more precision than the page shows** (privacy-authz MED). The student trend's `mean` and the `workload_median` are rounded on the server to one decimal before they enter the payload. Read beside whole-number shares, an unrounded mean such as 30/7 named the rater count (ruling 8, ruling 6). An invariant-marked test pins it with a seven-rater week: the served mean has at most one decimal and is not the exact quotient. Instructor figures are unchanged.
2. **A student's score names nothing but the reader's own row** (invariant-coverage MED). The participation isolation test (a classmate's row, the same student's row in another section, a later failed row) moves into an `invariant`-marked module named for the denial, asserting in its body.
3. **Student copy is swept for comparison words in the isolated pass** (invariant-coverage MED). An `invariant`-marked test runs the item 1 word check (`comparisons_offending`) over every `student_*` key of the frontend copy inventory, with a planted offender as its control.
4. **The score's records say what it is** (lti-oidc MED and LOW). The score shown is the canonical percentage before AGS scales it to the column's maximum, not the characters the gradebook shows. ADR 0198 and the `StudentParticipation` field descriptions say so, and ADR 0198 says "the last one Pulse knows the platform took". E8-06 changes the words on the page.
5. **The records match** (adr-docs, data-model and code-reviewer LOWs). ADR 0197's last consequence states dispute E8-01-02's ruling and names the two statements that read `answer`. ADR 0198 is cut to its one construction choice (the shared `latest_grade_sync` helper and its `outcome` argument) and links SPEC §3.3 and §5.4 for the rest. `models/identity.py`'s comment on the `role_assignment` index points at ADR 0191. `StudentParticipation` is in the schema module's `__all__`. `student_workload_median` reuses the workload count the stream read already made.

## Not in this ticket

The page (E8-06). Splitting `services/response_loop.py`, a slim landing route, and whether shares alone may pin the rater count in a small week are carried in `../e9/carried-from-e8.md`.
