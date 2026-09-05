# FIX-03 — attempts

Ticket: `docs/tickets/fixes/FIX-03-test-env-parity.md`. Branch
`fix/test-env-parity`. Heavy lane: the tests were committed first, at 3336a22,
and `tests/**` is not mine to edit.

## 2026-09-05 — the red set confirmed, controls first

`.venv/bin/pytest tests/unit/test_the_documented_environment_is_laid_down_for_every_test.py -p no:randomly -q`
→ **1 failed, 7 passed**. The seven green ones are the module's controls and its
canary pair, so the machinery the ticket rests on measures something before I
build anything: the session baseline is in place for a test that declares
nothing, the opt-out really clears the documented names, `app.db` imports under
the baseline and refuses under the opt-out. The single red is
`test_the_makefile_declares_a_target_that_runs_the_gate_scrubbed`, on its own
assertion — the Makefile declares no `test-as-ci` target. That is the whole of
my deliverable's red.

## 2026-09-05 — the trap and the scrub, proven in a scratch shell first

Before writing the recipe I built the same construct in
`scratchpad/traptest/run.sh` and ran it three ways, because a restore that only
fires on success is worse than none — it loses a developer's `.env` on the run
that fails.

- success: `.env` moved aside, the documented names absent inside the run,
  `PATH` still set, file back afterwards, no stash left.
- failure (`exit 7`): file back, **exit status 7 preserved** through the trap.
- interrupt (`kill -INT` on the running shell): file back, no stash left.

**Worked.** The recipe uses that construct unchanged: `trap` on `EXIT INT TERM`
guarded on the stash existing (so it is also right when there was no `.env`),
`sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' .env.example` for the names, and
`env -u NAME ... $(MAKE) test` so the sub-make never sees them.

**A mistake inside this step, worth recording.** My interrupt check ran
`cd <scratch> && bash run.sh &` — backgrounded, so the *parent* shell never
changed directory, and the follow-up `cat .env` printed the repository's own
`.env` into the session transcript, a live provider key included. Nothing was
committed and nothing left the machine, but the credential is in one
conversation transcript that did not need it. Cause: a `cd` inside a
backgrounded subshell does not move the shell that runs the next command, and
the next command used a relative path. Rule: absolute paths for every check that
touches a file, and never `cat` a path that can resolve to `.env` — read a file
you own by name, or test for its content with `grep -q`. Reported to the
orchestrator so the key can be rotated if Todd wants it rotated.

## 2026-09-05 — the target

`test-as-ci` added to the Makefile's test-gates section, in the file's own style
(banner macro, `##` help line, the reason in a comment above the recipe).
Committed as 3e8d782.

- `.venv/bin/pytest tests/unit/test_the_documented_environment_is_laid_down_for_every_test.py -q`
  → **8 passed**. The module is fully green.
- `make help` lists the target, so the `##` line parses the way the help grep
  expects.

## 2026-09-05 — the runs

All foreground, `.venv/bin` on PATH, on the committed tree.

- `make test-as-ci` (first run, before the records): **exit 0**, 2679 passed in
  4m34 under the scrub, whole target 6m00. `.env` back, no stash left, working
  tree clean.
- `.venv/bin/pytest tests/unit tests/integration -n 4 -q` (ambient, after the
  records): **2679 passed** in 4m13.
- `make test-as-ci` again on the final tree, whole log kept in the scratchpad:
  **exit 0**. It scrubs all 29 names `.env.example` documents (the log prints
  the list); the invariant half ran serially — **217 passed, none skipped**,
  `check_invariants.py` OK, `check_invariant_assertions.py` OK over 161 marked
  tests — and then 2679 passed. Nothing in the suite needed a variable the
  scrub removed, so criterion 1 is proven by a run rather than by argument, and
  criterion 3 holds with the autouse baseline in place.

No dispute filed: the one red was mine to fix and the seven controls were green
before I started.

## 2026-09-05 — the counter was not bumped, and why

The brief asked for `Caught: 1` → `Caught: 2` on entry 40, for the E3-06
recurrence. **Not done, deliberately.** `docs/MISTAKES.md` says a bump is earned
when the entry *stops* someone making the mistake, and explicitly not for
"recording something already found"; PR #172's own summary says the E3-06 case
was a CI-only failure found mid-build and then repaired. That is a detection.
The precedent is inside this very entry: the E1-11 instance is marked "Not
counted as a catch: CI caught it, the gate did not." Bumping here would make the
one number that decides an entry's rank measure something different from what
the file says it measures. The recurrence is recorded as an instance instead,
and the deviation is reported to the orchestrator rather than settled quietly.

Adding it took the detail file to four instances, so it was trimmed to the three
most recent, which is what `docs/MISTAKES.md` asks for. The trimmed one is the
founding E1-10 diagnosis; it is summarised in a sentence at the head of the file
with a pointer to PR #105, and the one place the rule section leaned on it
("Here the inference…") now names E1-10 so the sentence still stands on its own.
