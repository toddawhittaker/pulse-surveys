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
  only by accident. → **E2-14 item 1, built in PR #154.**
- **HIGH, confirmed** — `leadership_grant_covers` (`authz.py:800`, ADR
  0108, the M9 fix and §4.1 item 2's live enforcement point) answering
  `True` unconditionally survives the entire isolated pass; its only
  behavioural cover is one integration module with no `invariant` mark.
  → **E2-14 item 2, built in PR #154.**
- **MEDIUM, confirmed and sharpened** — the item 1 route inventory is a
  filter over the `require_student` dependency; a handler calling
  `session_from_request` directly is invisible to it, and the route walk
  does not descend a `Mount` — which is live today (`main.py:324` mounts
  the single-page application). Today the direct call exists only in
  `api/deps.py`. → **E2-14 item 5, built in PR #154 — and its security review widened the sweep to the whole app package.**
- **MEDIUM, confirmed with character clarified** — two live §4.1 denial
  tests hold their `invariant` marker per test, the currency the
  denial-module sweep refuses, escaping only by filename. Both ARE
  collected into the pass today; this is currency inconsistency, not lost
  coverage. → **E2-14 item 3, built in PR #154.**
- **MEDIUM, confirmed** — `test_dev_clock_control_exposure.py`, the sole
  gate on the environment exposure of the clock-writing routes, carries no
  `invariant` marker while both sibling exposure modules do. → **E2-14
  item 4, built in PR #154.**
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
  itself pinned by no test. → **E2-15 item 1, built in PR #153.**

**From the exit review:**

- **MEDIUM, confirmed** — the shipped bounce sentence ends in a truncated
  infinitive ("are too brief to.") and nothing pins the string. → **E2-15
  item 2, built in PR #153.**
- **MEDIUM, confirmed** — `make ci` runs the paid eval runner
  unconditionally: red on a fresh clone, roughly a hundred paid calls on a
  configured one, against two README sentences claiming otherwise.
  → **E2-15 item 3, built in PR #153.**
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

## Second round — the four always-run agents, after the final batch merged

Run 2026-09-03 against the epic branch at c2a83f1 (E2-14 and E2-15 merged),
per the roster's always-run rule: a11y-copy, data-model, lti-oidc and
prompt-eval, each in a fresh context that had watched none of the epic's
builds. Every finding went through an adversarial verification pass — a
second, independent context tasked with refuting it, by execution where the
claim was about behaviour. Nothing was refuted outright; two findings came
back worse than reported, two came back smaller.

**From data-model** (all verified on a throwaway database; the dev database
untouched):

- **HIGH ×2, confirmed and sharpened** — both survey migrations destroyed or
  silently corrupted data on a downgrade/upgrade round trip: `3f6907349751`
  stranded the database re-adding `term_id` NOT NULL over 188 windows (and
  its downgrade dropped `response` and `answer` whole, unpreserved);
  `f1a3c7d02b64` backfilled every `is_valid` to true and left restored
  classifications' `answer_id` NULL — permanently invisible to the floored
  sweep. → **E2-16 items 1–2, built in PR #156.**
- **MEDIUM, confirmed** — a cross-term (section, week) response was
  representable while `survey_window` refused the same pairing. → **E2-16
  item 3, PR #156.**
- **MEDIUM, confirmed and raised** — the floored-comment sweep's `NOT IN`
  unhashes past `work_mem` at term volume: 72 seconds measured, index alone
  recovering ~35%; the remedy is the query's shape. → **E2-16 item 4,
  PR #156.**
- **MEDIUM, downgraded to LOW on verification** — the two week-axis indexes
  are unused today but spec-anchored for E3's week-close read; their comments
  claimed the present tense. → retensed, **E2-16 item 6, PR #156.**
- **LOW, confirmed and sharpened** — window derivation measured at 5N+1 round
  trips (the review counted 2N+1). → **E2-16 item 5, PR #156.**

**From a11y-copy** (all independently re-measured against the live stack):

- **HIGH, confirmed** — the disabled submit button left the tab order with
  nothing saying why; no form element, no required attributes.
  → **E2-17 item 1, built in PR #157.**
- **MEDIUM ×5, confirmed** — Likert polarity spatial only; the unchecked dot
  at 1.92:1 rendered (2.58:1 by token — worse than reported); the
  required-comment flip silent; headings bare section codes with no course on
  the wire; the confidentiality sentence rendered per section. The last was
  sharpened to an unadjudicated reading of §4.1 item 5's "once per surface",
  ruled 2026-09-03: once per screen. → **E2-17 items 2–6, PR #157.**
- **LOW ×2** — the idle live region removed from the accessibility tree by
  `:empty { display: none }` (confirmed via the accessibility protocol:
  ignored/notRendered); the slider track's 1.30:1 (downgraded — the thumb
  identifies the control at 12.45:1, so a design-fidelity fix, not a WCAG
  failure). → **E2-17 items 8 and 3, PR #157.**

**From lti-oidc:**

- **MEDIUM, confirmed** — the CSRF double-submit's client half was never
  built: the SPA never read `pulse_csrf`, so a cookie-borne student could
  read and never submit. → **E2-17 item 7, PR #157.**
- **MEDIUM, confirmed** — SPEC §7.3's roster-sync sentence still read
  unconditionally against E2-02's merged purview gate. Ruled 2026-09-03: the
  sentence is conditioned. → **the spec edit rides PR #156.**
- **LOW, confirmed (one characterization softened)** — a rewound dev clock
  can wedge one section's roster sync against the enrollment window
  constraints, contained by the per-section savepoint; development only.
  → **carried** (`../e3/carried-from-e2.md`).
- Clean, verified by execution: no protocol validation reads the mocked
  clock; the staff-launch gate changes no claim-limb outcome; the launch
  validation order, NRPS paging and both mocks hold as merged.

**From prompt-eval:**

- **MEDIUM, confirmed** — prompt-file immutability was convention only (the
  runner compares version stems; the mock guards one marker line).
  → **E2-18 item 1, built in PR #155.**
- **MEDIUM, verified as already tracked** — the workflow's model literal and
  `.env.example` untied by any test: the second of the three sites the
  existing carried entry "the model identifier lives in three places" already
  names. → **no new record; the carried entry stands.**
- **MEDIUM, confirmed, record-only** — the floors moved twice inside PR #149;
  verified: no floor existed on main, the moves rescued no red run, the
  ruling and the standing objection are recorded, and E10 holds the revisit.
  → **no change; this line is the second-round re-affirmation.**
- **LOW ×2, confirmed** — the E2-12-06 routing fix unpinned; the hard
  families' sizes unguarded. → **E2-18 items 2–3, PR #155**, where the
  security round then widened both fixes (the composition pinned whole, the
  hash pin recursive) — that round's record is PR #155's body.

**Explained rather than found:** classifications carrying `answer_id` NULL,
observed live during verification, are bounce verdicts — a bounced comment
stores no answer row by the 2026-09-03 ruling recorded in ADR 0114, so the
reclassify sweep correctly never sees them.

**Dispositions of this batch:** every code finding above landed in PR #155,
#156 or #157; the two spec sentences were ruled by the owner on 2026-09-03
and edited in PRs #156 (§7.3) and #157 (§4.1 item 5); the dev-clock/roster
interaction and the session-read sweep's disclosed limits are re-listed in
`../e3/carried-from-e2.md`.
