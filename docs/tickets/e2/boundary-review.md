# E2 epic-boundary review — the record

Run at the epic exit (ticket E2-13, branch `e2/e2-exit`, commit a3c810d, with
record corrections landing as 9e302c4 and the security round's fix as 70d87f2
on the same branch), per SPEC §14.2
item 6: an exit review against the running system, an invariant-coverage
audit, and a docs/ADR completeness check, each in a fresh context that had
watched none of the build. Every code finding below went through an
adversarial verification pass — a second, independent context tasked with
refuting it, by execution where the claim was about behaviour. One finding
was downgraded and three came back sharper than reported; none was refuted
outright, and one claim inside a finding ("no existing test catches it") was.

## Verdict

**All four §14.3 E2 exit clauses hold against the running system**, each
verified by execution rather than by reading:

1. *A student submits a valid response.* Proven in the enforcing Playwright
   gate (`tests/e2e/exit-weekly-survey.spec.ts`, green in CI run 33702092144
   and again at a3c810d) down to the stored rows: one `response`, a real
   audit pair on every comment's `classification`, revise-in-place under a
   resubmission. The exit review also drove a different seeded section
   end-to-end, off the specs' path, with the same result.
2. *"It was okay" is bounced with immediate feedback.* Proven by
   `tests/e2e/student-survey.spec.ts` (the coach-fix-resubmit test drives
   exactly that sentence) and re-driven by hand at the boundary: 422, the
   coaching body, zero rows stored, no comment text retained.
3. *The §4.1 invariant suite carries the item 1 test and it fails when a
   student-visible path returns another section's data.* The module ran
   inside CI's isolated pass on the exit commit (188 passed, none skipped),
   and E2-09's loosened-predicate mutation — deleting
   `Enrollment.user_id == user_id` from `_live_enrollments` — was re-run
   twice at the boundary, by the build's own battery and independently by
   the exit review in a detached worktree; four tests red both times, the
   headline test naming the leaked section.
4. *The copy-inventory test exists and reads the survey surface's shipped
   strings.* Collected and green in the same isolated pass; the collector,
   invoked live, returned 43 shipped strings including the survey screen's
   own keys — not a blind walk.

E2 is an unmarked epic, so no whole-epic threat model is owed. The
independent per-PR security review stood in every one of the epic's
thirteen ticket PRs (recorded in each PR body), which is stated here so the
absence of a boundary threat model reads as the rule applied, not as a step
skipped.

## The denial-module sweep re-affirmation

The carried decision (E2 breakdown, from `carried-from-e1.md`) was that this
review re-affirms the two disclosed limits of `DENIAL_NAME_SHAPES` in
writing, or reports they no longer hold. Both were **executed at the
boundary, in both directions, and both still hold exactly as disclosed**:

- *A shape named outside every pattern escapes the sweep.* A temporary
  denial-duty module named to match no shape
  (`test_a_planted_export_shows_no_other_person.py`) was planted on the live
  tree; the sweep ran green over it, and red-side behaviour is already
  proven by the sweep's own planted offenders.
- *A shape deleted together with its planted sample is green.* The
  `repeats_nothing` shape and its planted sample were deleted together in
  one edit; both of the sweep's tests stayed green while the real module
  that shape demands was demanded by nothing. The edit was reverted from a
  snapshot and the module re-run green.

E2-09 did add a denial module, and the sweep reaches it: the stem of
`test_the_student_read_path_names_nothing_outside_the_enrollment.py`
carries the `names_nothing` shape, the module holds its `invariant` marker
at module level in the list form, and CI's isolated pass ran it on the exit
commit. The convention's class limit stays what the sweep's own docstring
says it is; nothing here closes it.

## Findings and dispositions

Severity, claim, verification verdict, and where each went. "Fixed here"
means commit 9e302c4 on this branch; E2-14 and E2-15 are this epic's final
batch (`E2-14-invariant-pass-coverage.md`,
`E2-15-student-surface-and-local-gate-repairs.md`), built inside E2 per
§14.2 item 6 — never E3's inheritance.

**From the invariant-coverage audit:**

- **HIGH, downgraded to MEDIUM on verification** — the submit path's
  own-submission lookup (`submissions.py:385`) losing its `user_id`
  predicate would let one student's resubmission overwrite and return a
  classmate's row. Verified by mutation: the isolated invariant pass stays
  green (188 passed), and the reviewer's claim that *nothing* catches it
  was refuted — one integration test about the outage floor kills it,
  incidentally, because it happens to submit as a second student first. The
  real finding stands: the clobber is invisible to the §4.1 pass and caught
  only by accident. → **E2-14 item 1.**
- **HIGH, confirmed** — `leadership_grant_covers` (`authz.py:800`, ADR
  0108, the M9 fix and §4.1 item 2's live enforcement point) answering
  `True` unconditionally survives the entire isolated pass; its only
  behavioural cover is one integration module with no `invariant` mark.
  → **E2-14 item 2.**
- **MEDIUM, confirmed and sharpened** — the item 1 route inventory is a
  filter over the `require_student` dependency; a handler calling
  `session_from_request` directly is invisible to it, and the route walk
  does not descend a `Mount` — which is live today (`main.py:324` mounts
  the single-page application). Today the direct call exists only in
  `api/deps.py`. → **E2-14 item 5.**
- **MEDIUM, confirmed with character clarified** — two live §4.1 denial
  tests hold their `invariant` marker per test, the currency the
  denial-module sweep refuses, escaping only by filename. Both ARE
  collected into the pass today; this is currency inconsistency, not lost
  coverage. → **E2-14 item 3.**
- **MEDIUM, confirmed** — `test_dev_clock_control_exposure.py`, the sole
  gate on the environment exposure of the clock-writing routes, carries no
  `invariant` marker while both sibling exposure modules do. → **E2-14
  item 4.**
- **MEDIUM, recorded as plausible** — the rendered student surface's
  aria/label strings rest on a convention (everything resolves through the
  copy registry) that holds today — the reviewer walked every component and
  found no violation — but that nothing sweeps. Not adversarially re-run.
  This one is deliberately **carried to E4 rather than batched**: there is
  no live violation, and the sweep it asks for belongs with the copy
  inventory E4 grows anyway. → `docs/tickets/e3/carried-from-e2.md`.

**From the docs/ADR completeness check:**

- **MEDIUM, confirmed** — `ai/tasks.py` attributed the fail-open rule to
  CLAUDE.md, which never carried it (the rule is SPEC §3.3/§6.2's).
  → **Fixed here.**
- **MEDIUM, resolved by sequencing** — `carried-from-e2.md` cited this file
  before it existed. It exists now, in the same PR. → **Fixed here.**
- **MEDIUM, confirmed and sharpened** — CONTRIBUTING.md's gate table was
  stale on three facts (eval floors enforcing since E2-12, frontend gates
  enforcing since E1-04, `mock-ai` in the Compose health list). → **Fixed
  here.**
- **MEDIUM, confirmed with a new sub-finding** — `GET /student/survey` sets
  no `Cache-Control: no-store` while returning the student's own prior
  free text; the POST sets it, and verification found the POST's header is
  itself pinned by no test. → **E2-15 item 1.**

**From the exit review:**

- **MEDIUM, confirmed** — the shipped bounce sentence ends in a truncated
  infinitive ("are too brief to.") and nothing pins the string. → **E2-15
  item 2.**
- **MEDIUM, confirmed** — `make ci` runs the paid eval runner
  unconditionally: red on a fresh clone, roughly a hundred paid calls on a
  configured one, against two README sentences claiming otherwise.
  → **E2-15 item 3.**
- **LOW, confirmed** — ADR 0002 claimed no tolerance survives while the
  `node` probe still gates the Node-side audit and licence steps, and
  ci.yml's header comment was three removals out of date. → **Fixed here.**
- **LOW, confirmed** — the epic index's Merged column was empty for all
  thirteen rows and PR #149 appeared nowhere in it. → **Fixed here.**

**From the exit PR's own security review, after the round above:**

- **HIGH ×2, confirmed, resolved on the owner's word (2026-09-03)** — the
  ADR 0114 ruling paragraph this PR wrote recorded two of its accepted
  grounds as present facts when both mature later (no moderation pass
  screens any comment for harm until E6/E10, and the threat recall floor is
  a deferred empty declaration until E10), and the closure removed the
  revisit mechanism while its reopen trigger — a missed rate — cannot fire
  on a rate nobody measures. The ruling stands; the record was corrected:
  the grounds are restated in their honest tense with today's state plain,
  and the revisit is scheduled rather than assumed — `carried-from-e2.md`
  hands E10 a named check (its floor-setting takes the
  bounce-before-screening path into the floor's scope or reopens the
  ruling). → **Fixed here**, with a security re-pass over the fix.

## What was executed and came back clean

The full e2e suite against the live stack (36 passed); an independent drive
of a seeded section the specs never touch, including the refusal pair
answering byte-identical 404s for a forbidden and a nonexistent section; the
isolated invariant pass (188 passed, none skipped, 138 asserting — the gate
scripts' own verdicts); the copy collector invoked live; the four E2 grants
files' two-directional privilege equality; every E2 logger and the AI
gateway read for comment text (none carried any); all seventeen
`deferred.md` entries traced to a closure in place or an entry in
`carried-from-e2.md`; all twenty-three `carried-from-e1.md` headings traced
to a closure or a re-listing; CLAUDE.md checked against its own
process-only rule.
