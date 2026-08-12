# E0-18 — E0 exit: both doors, end to end

**ID:** E0-18
**Branch:** `e0/e0-exit-smoke`
**Depends on:** E0-11, E0-13, E0-15, E0-16, E0-17

## Context

E0's exit condition is that `docker compose up` yields a launchable-into,
loggable-into, testable system that does nothing yet (§14.3). This ticket proves
it with the first Playwright end-to-end paths and turns the e2e gate from
tolerant to enforcing, so every later epic inherits a pipeline that actually
exercises both entry doors on every run (§9.2).

Read first: SPEC §14.3 (E0's exit criterion), §9.2 (both doors exercised in
every run), §2.1 (dual-door entry resolving to the same identity and purview).

## Scope

- Playwright configuration and `tests/e2e/`, running against the Compose stack.
- A launch path: click through the mock LMS launch form, arrive at the tool, and
  land on a role-appropriate empty view.
- A web-login path: authenticate against the mock IdP as a leadership user and
  arrive at a role-appropriate empty view.
- A test asserting that both doors, for a person who could use either, resolve
  to the same identity — the §2.1 rule that the launch context resolves which
  section a link points at but never caps what a leadership user may see.
- Enable the CI `e2e` job: remove the tolerance branch, bring up the stack
  including `mock-lms` and `mock-idp`, and run the suite.
- A trace or screenshot artifact uploaded on failure, since an e2e failure in CI
  is otherwise close to undebuggable.

## Out of scope

- Any real view content — the survey form is E2, reports are E4, roll-ups are
  E9. "Role-appropriate empty view" means exactly that.
- Tool-side launch validation depth: replay, clock skew, cookieless session
  handling (E1). This ticket proves the wiring, not the hardening.
- Accessibility auditing of the landing views (E13, and in-slice as real views
  land).

## Acceptance criteria

- [ ] `docker compose up -d` brings every service healthy: `api`, `worker`,
      `beat`, `db`, `redis`, `mailpit`, `mock-lms`, `mock-idp`.
- [ ] A Playwright test completes an LTI launch from the mock LMS and asserts
      the landing view corresponds to the launching user's role.
- [ ] A Playwright test completes an OIDC login against the mock IdP for a dean
      and asserts the landing view.
- [ ] A test asserts both doors resolve to the same identity for a person who
      holds both an instructor and a leadership assignment.
- [ ] The CI `e2e` job runs the suite for real, with the tolerance notice
      removed, and passes on a clean runner.
- [ ] A failing e2e run uploads a Playwright report artifact — verify by
      deliberately breaking an assertion once, then reverting.
- [ ] `make ci` locally runs the same suite.

## Definition of done

**Tests apply — this ticket is tests.** Playwright end-to-end paths per §9.2,
covering both doors.

**Docs apply.** `README.md` gains "how to run the e2e suite locally," including
the Compose prerequisite and how to run headed for debugging.

**AI evals do not apply.** The eval job remains tolerant until E2 ships the
first eval set; say so explicitly in the pull request so the remaining tolerance
is a recorded decision rather than an oversight.

**Accessibility does not apply yet** in audit form, but the landing views must
be keyboard-reachable — if a view cannot be tabbed to, fix it here rather than
booking it for E13.

**Security review applies.** This is the first ticket where a real launch
reaches real authorization code. Review that the e2e path does not depend on any
authorization shortcut, and that no test fixture grants a role the launch itself
would not.

## E0 exit checklist

Confirm and record in the pull request:

- [ ] Every CI gate that has something to check is enforcing. The only tolerant
      job left is `evals`, and the pull request says why.
- [ ] `docker compose up` from a clean checkout reaches a working system.
- [ ] A student, an instructor, and a dean each land on the right empty view
      from whichever door applies to them.
- [ ] The §4.1 invariant suite runs and cannot be skipped.
