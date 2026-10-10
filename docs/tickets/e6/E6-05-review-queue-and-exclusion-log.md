# E6-05 — The Lead Faculty review queue and the exclusion log

**ID:** E6-05
**Branch:** `e6/review-queue-and-exclusion-log`
**Depends on:** E6-03 (the decision service, the decision columns and the
stored role)
**Lane:** heavy (`backend/app/services/authz.py` and new sibling-isolation
invariant tests)
**Size:** L
**Security-relevant:** the first leadership read of raw comment text, and the
first leadership write on a comment. A defect here hands a Lead Faculty
member a sibling lead's comments, or shows a Care-class comment up-chain.

## Context

SPEC §5.2 routes abuse aimed at the instructor to the course's Lead Faculty
review queue, and keeps an exclusion log for leadership: the anti-cherry-picking
trail. Ruling 1 settles the clash with §5.5: the Lead Faculty sees a harmful
comment's text and its section at any threshold, with no week and no time
shown, and can exclude or keep it. §5.5 gains one exception sentence, written
here.

**The queue.** Comments with a harmful verdict that are still flagged-collapsed,
in the courses the reader leads, or, for a course with no lead, the courses of
the department the reader chairs (§8: an unmapped course resolves to its
chair). Only harmful goes to the queue; privacy stays with the instructor.
Each item shows the text and the section, in random order. No week, no time,
no count beside it.

**The queue reads view v004.** It finds its comments through
`public.report_comment` v004, the one place the Care-class exclusion lives. It
gets no grant on `answer` and does not rebuild the exclusion in Python, so
there is one copy of the rule and a Care-class comment cannot reach the queue
by a second road.

**Each door holds its own visibility check.** The Lead Faculty door is a
separate entry into E6-03's decision service, with its own check: the comment
is in the queue this reader may see. It is not a flag or a role argument on
the shared service, so adding this door cannot loosen E6-03's instructor rule.
Both checks run before the shared write.

**What the instructor sees of a Lead Faculty decision.** On a comment in a
shown stream, the instructor's card shows the decision. On a comment in a held
stream, the instructor sees nothing of the decision: there is no participation
note and no held count (ruling 6). There is no per-comment trace.

**The log.** Every `EXCLUDED` and `KEPT` row decided by a person, inside the
reader's own grant at their leadership roles. Each row shows the section
(course label and code), the decider's stored role (ruling 4), AI-flagged or
unflagged with its reason, the decision date, and an excerpt. The excerpt is
withheld when the comment is not visible to its own instructor, because a date
beside text from a held stream would place that text in a week. Both
directions are shown, which settles §5.2's open item and §11 question 5.

**The scope.** The log and the queue read the reader's own grant at
leadership roles only. `resolve_scope` includes instructor grants, so no
leadership-only union is public today; this ticket adds one function to
`authz.py`. The transitive purview is E9's, and the assistant dean fails
closed until then (ADR 0108). §5.2's "Lead Faculty prefix scope" is wrong in
the spec's own terms (a lead holds no prefix scope, §2.1, ADR 0025), so the
sentence is rewritten as the reader's own grant.

Read first: SPEC §2.1, §4, §4.1 items 2 and 3, §5.2, §5.5 and §6.2; ADRs 0025,
0108, 0153, 0162, 0178, 0179 and 0189; and `services/comparison_sets.py` with
`copy/leadership_sets.py`, the pattern for a leadership read and its refusals.

## Owns

- One public leadership-only own-grant function in
  `backend/app/services/authz.py`.
- The queue read (over view v004), the log read and the Lead Faculty door into
  E6-03's decision service, in `backend/app/services/moderation.py`. The door
  holds its own visibility check. A Lead Faculty or chair decision is written
  with that role.
- `backend/app/schemas/moderation.py` (new) and
  `backend/app/copy/leadership_moderation.py` (new).
- The queue, decision and log routes in `backend/app/api/leadership.py`,
  behind `require_leadership` and `csrf_verified_leadership`.
- Invariant-marked tests: sibling isolation over the queue and the log; no
  Care-class comment in either; an instructor-only person refused.
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated.
- **M3** only if a column is missing, with `down_revision` set to M2's id. E6-03
  stores the role so that none should be.
- SPEC §5.5 (the exception sentence), §5.2 (the log's scope and its columns;
  the open item settled), §11 question 5 (settled), and §13 (the two new
  modules).
- ADR **0190**.

## Reuse, do not rewrite

`own_grant`, `_own_grant_of` and `holds_leadership` in `services/authz.py`.
`person_of`, `require_leadership`, `csrf_verified_leadership` and the CSRF
token helpers in `api/deps.py`. E6-03's decision service; never a second
writer of `moderation_state`. `section_codes.course_label` for the section.
`COMMENT_VIEW` and `visible_comments` for "visible to its instructor".
`services/clock.now`.

## Done when

1. **The queue shows what ruling 1 allows.** A Lead Faculty member sees a
   harmful, undecided comment from a course they lead, in a week below the
   threshold, with its text and section and no week, time or count. A privacy
   comment, a decided comment and a clear comment in the same course are not
   in the queue.
2. **The chair covers an unmapped course.** A comment in a course with no lead
   is in its department chair's queue and in no Lead Faculty member's.
3. **Sibling isolation.** A Lead Faculty member never sees a sibling lead's
   course in the queue or the log, and a decision on a sibling's comment is
   refused and writes no row. Invariant-marked, with the reader's own course in
   the same world as the canary.
4. **Care-class is absent.** A threat or self-harm comment appears in neither
   the queue nor the log, at any threshold. Invariant-marked.
5. **An instructor is refused.** A person holding only an instructor grant is
   refused by every route here, over HTTP against the built application, and a
   leadership person in the same world is answered (entry 47).
6. **Lead Faculty decisions.** A Lead Faculty member excludes and keeps a queued
   comment; each is a row with the decider and the stored role. In a shown
   stream, the instructor's card shows the decision. In a held stream, a test
   shows that the instructor's payload is the same before and after an
   exclusion and before and after a keep (ruling 6: there is no held count).
7. **The gate runs at dispatch.** A leadership decision POST with no CSRF
   token, or from another origin, is refused over HTTP against the built
   application, and the same POST with the token succeeds (entry 47).
8. **The doors do not share a check.** An instructor decision on a comment in a
   held stream of their own section is still refused after this ticket, and the
   same comment is accepted through the Lead Faculty door by its lead.
9. **One copy of the Care exclusion.** The queue read selects from
   `public.report_comment`, and this ticket adds no grant to `pulse_app`:
   `tests/integration/test_identity_grants.py` shows its grant set unchanged.
10. **The log, both directions.** The log shows `EXCLUDED` and `KEPT` rows inside
   the reader's own grant, with the section, the role, flagged or the reason,
   and the date. A row whose comment its instructor cannot see carries no
   excerpt.
11. **The assistant dean fails closed.** A person whose only leadership grant is
   `ASSISTANT_DEAN` gets the refusal, as ADR 0108 says, until E9.
12. **The records match.** §5.5's exception sentence, §5.2's log sentences and
   open item, and §11 question 5 are edited. ADR 0190 records who sees what,
   the residual that the queue's arrival time hints at the week, and the
   de-anonymization statement for leadership views, written after reading
   ADRs 0153, 0162, 0178 and 0179.

## Shares files with

- `services/moderation.py`: E6-03 before this.
- `frontend/src/api/openapi.json`, `wire.gen.ts`: E6-03 before this; regenerate
  on conflict, never hand-merge.
- `docs/SPEC.md`, `docs/adr/README.md`: E6-07 after this.
- E6-04 runs in parallel and shares no file with this ticket.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 35, 43, 46, 47, 50, 51 and 53.

## Known traps

- **Entry 35 and 53.** The own-grant function must find a Lead Faculty grant on
  a subject that certainly holds one, as a control, and must be attacked one
  level out: a person with both a lead grant and an instructor grant, and a
  chair whose department has one mapped and one unmapped course.
- **Entry 51.** The queue's contents change over time, and a reader who looks
  every hour learns when a comment arrived. Ruling 1 accepts showing the text;
  ADR 0190 states this residual, and the random order must hold on every read.
- **Entry 46.** Read the queue and the log through the connection production
  uses at least once.
- **Entry 43.** `copy/leadership_moderation.py` and schema descriptions will
  name sections and courses. Reword any phrase the SQL sweep reads.

## Out of scope

- The pages (06).
- Staff names in the log (E9).
- The transitive purview (E9).
