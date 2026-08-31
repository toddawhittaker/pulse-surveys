# E2-09 — The student read path, and §4.1 item 1 gets its assertion

**ID:** E2-09
**Branch:** `e2/student-read-path`
**Depends on:** E2-01, E2-05, E2-06
**Lane:** heavy
**Security-relevant:** the first student-visible read path — the reason §4.1
item 1 has been waiting since E0. The invariant test this ticket adds is the
epic's namesake deliverable.

## Context

E2-10's form needs one question answered: *for me, right now, what is there?*
— the student's enrolled section(s), the open window if any, the v1 questions,
and their own current submission for the resubmit case. That read path is the
first place "another section" means something a student could ever be shown,
so §4.1 item 1's assertion lands here, in the invariant suite, marked and
unskippable like the rest of the §4.1 pass.

The student path reads the student's *own* rows — identity separation
(ADR 0001) constrains instructor and leadership reads, not a person reading
themself — but it goes behind the same discipline: E2-01's corrected sweep
and import guard are a hard dependency by Todd's deadline (before E2's first
read path behind the sweep), and any new relation read follows the sweep's
sanctioned locations.

Read first: SPEC §4.1 (items 1 and 6), §3.1 (exactly one open survey), §5.4
only to know what is *not* built yet; the carried block's note on the
denial-module naming shapes (`DENIAL_NAME_SHAPES` — a new §4.1 denial module
must sit inside the invariant pass, and its name must match a shape the sweep
sees); `scripts/ci/check_invariants.py`; the E1-01/Batch-A sweep machinery;
the memory that a guard's inventory must come from somewhere the guarded
structure cannot shrink.

## Scope

- The read route(s) (student session): current survey state for the
  student's enrollment(s) — section, week, window open/close instants,
  question set version and text, own submission if any. Nothing else: no
  aggregates, no other sections, no benchmarks, no counts of classmates.
- **The §4.1 item 1 invariant test**: a student-visible path returning data
  from a section the student is not enrolled in is a failure. Built so its
  inventory of student-visible paths has a source the code cannot quietly
  shrink — derived from the route table (every route a student session can
  reach), not from a hand-kept list, with a planted-offender control proving
  the sweep sees a new student route (MISTAKES entries 2, 35). The two-section
  fixture pair: same student enrolled in A, not B; everything B-shaped is
  absent from every answer — body, and error shape too (a 404-vs-403
  distinction that confirms B exists is a leak; refusals are
  indistinguishable from nonexistence).
- The invariant suite still runs in the isolated CI pass, still cannot be
  empty, and the new test is proven red by mutation (loosen the enrollment
  predicate; watch it fail — MISTAKES entry 3, and check the mutation landed).
- Whatever refusal copy this path serves is externalized for E2-11.

## Acceptance criteria

1. The form's question is answerable in one round trip against the seeded
   stack, with the dev clock deciding open/closed.
2. The item 1 test exists, is collected in the invariant pass, fails under
   the loosened-predicate mutation, and its path inventory flags a planted
   unlisted student route.
3. §4.1's statement of item 1 ("asserted from E2") is now true; the SPEC
   footnote's tense needs no edit (it already states E2) — verified by
   reading it, not assumed (MISTAKES entry 1).
4. No new module under `backend/app/views_sql/` — or if one proves
   necessary, E2-01's corrected guard names it deliberately in the same PR.

## Out of scope

- The results/closing-the-loop view (§5.4) — E8's.
- Instructor or leadership reads of responses — E4's, behind the identity
  separation that epic will exercise.
- Any benchmark or comparison figure — E5's, and forbidden here by item 1.
