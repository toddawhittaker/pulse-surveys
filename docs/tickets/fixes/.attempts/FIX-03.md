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
