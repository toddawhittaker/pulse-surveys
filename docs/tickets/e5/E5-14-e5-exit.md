# E5-14 — E5 exit

**ID:** E5-14
**Branch:** `e5/e5-exit`
**Depends on:** all
**Lane:** heavy
**Security-relevant:** the boundary reviews run here; the exit drive
exercises every guarantee the epic added.

## Context

§14.3's exit clause, driven against the running stack: **an instructor
sees three lines per panel benchmarked against prior terms; a student
provably sees two lines and no benchmarks.** Plus the epic's one
spec-named obligation: **the min-N starting values are still §11 question
1 and are settled before this epic exits** (breakdown decision 10).

E4-15 is the template: the exit drive, the boundary-review roster, the
deferred-file cleanup pass, and the hand-off file, under the completeness
rule E3 and E4 both used.

Read first: E4-15's ticket and `docs/tickets/e4/boundary-review.md` (the
record shape this reproduces); `carried-from-e4.md` whole (the pass-through
ledger this ticket writes forward); `deferred.md` as E5 left it; SPEC §11
question 1 and §14.2.

## Scope

- **The exit drive**, against the seeded stack (E5-12's world): an LTI
  launch lands the instructor on a report with three lines per panel whose
  comparison reaches prior-term sections; the same world's student sees
  two lines; the thin cohort's report shows every suppression treatment.
  Recorded with the evidence conventions E4-15 set.
- **§11 question 1 settled**: present the seeded worlds' real cohort
  sizes and the suppression behavior at the defaults (3 sections, 15
  respondents), obtain the owner's ruling, record it — SPEC §11 and §5.1
  updated in this PR, and the configuration defaults confirmed or moved in
  the same change. Until the ruling lands this PR is not ready; the values
  are the owner's call, not this ticket's.
- **Boundary reviews**: the always-run roster (a11y-copy over the new
  chart treatments and leadership surface, adr-docs-completeness,
  data-model over E5-01/03's migrations, epic-exit, invariant-coverage
  over the epic's new read paths, lti-oidc, prompt-eval, spec-conformance;
  threat-model does not run — E5 is unmarked), reconciled in
  `boundary-review.md` as E4 did, fix rounds included.
- **The re-checks the carried file assigns to every boundary**: the
  session-read sweep planted in `services/benchmarks.py` and
  `api/leadership.py`; `PERSON_TABLES` asked of `comparison_set` and its
  membership relation.
- **The hand-off**: `../e6/carried-from-e5.md` under the completeness
  rule — every open `carried-from-e4.md` entry dispositioned, every
  `deferred.md` entry still open re-listed, everything the boundary found
  and did not fix included.

## Acceptance criteria

1. The exit clause demonstrated end-to-end and recorded: three lines,
   prior-term reach (shown by a comparison figure that changes when the
   prior term is excluded — the drive proves the reach, not the legend),
   and the student half per breakdown decision 9: the E5-11 suite green
   against the same world plus a student-seat walk of every surface that
   exists; the literal two-line TrendDuo walk if E8's view has merged,
   otherwise the structural proof recorded and the walk named as the
   first E8 obligation in the hand-off.
2. §11 question 1 closed: the ruling recorded in SPEC §11's answered set,
   §5.1 consistent, config matching, and no record left claiming the
   values are unsettled (entry 1's grep).
3. The boundary-review record complete, every finding resolved or carried
   with an owner and done-when.
4. `deferred.md` cleanup pass run; `../e6/carried-from-e5.md` written to
   the completeness rule, with the ledger demonstrating it.
5. CI green on the exact exit commit, verified by run id, status,
   conclusion and head SHA (entry 42's full discipline).

## Known traps

- **The exit story freeze** — E4's exit e2e asserts exact numbers;
  nothing here may lean on or alter that world (E5-12 criterion 5's
  other half).
- **Boundary fix rounds go stale** — a review pass is void the moment a
  fix lands on it; re-run over the fixes or state the stop, per the
  standing review rules.
- **The sequence channel** (entry 51) — the drive walks consecutive
  weeks on both seats, not one Monday.

## Out of scope

- Anything a boundary review finds that belongs to a later epic — carried
  with an owner, not fixed here under exit pressure.
- Rendering the term axis — E9 (decision 7); the boundary verifies the
  reads exist and are proven, nothing more.
