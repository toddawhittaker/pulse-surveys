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

## The mock's registration exists now, and stops one step short

E0-31 item 1 landed on 2026-08-19: `scripts/seed.py` registers the mock platform
in `seed_mock_platform`, behind the guard that refuses to run outside a
development environment. So a launch from `mock-lms` is no longer rejected for
want of a row naming its issuer, which was the thing blocking this ticket.
[ADR 0068](../../adr/0068-the-demo-seed-registers-the-mock-platform-behind-its-guard.md)
records the decision and what it costs, and
[ADR 0038](../../adr/0038-the-mock-platform-ships-in-the-base-compose-file.md) is
amended to name the guard as what keeps the row out of a deployment.

**What it deliberately did not settle is this ticket's.** That registration
carries no `user` rows. A launch from the mock arrives as one of *its* two
invented subjects (`mock-lms/app/seed.py`), not as one of the eighteen demo
people, so it reaches the code and resolves to nobody. Provisioning the person a
launch names is E1's by SPEC §14.3 — so "the landing view corresponds to the
launching user's role" needs an answer here about where that role comes from
before E1 builds provisioning. Do not close it by seeding a `user` row for a
mock subject without saying so: that is a second registration decision, and ADR
0068's reasoning applies to it too.

## Decide first: whether `/docs` and `/openapi.json` stay public

`create_app()` builds `FastAPI(...)` without `docs_url` or `openapi_url`
(`backend/app/main.py`), so `/docs`, `/redoc`, and `/openapi.json` are served to
any unauthenticated caller. That has been harmless through all of E0 — the
schema holds `/healthz` and a version string — and **this is the ticket where it
stops being harmless**, because this is the first one to put a route behind
authorization. The E0-02 independent security review raised it as a timing
question rather than a defect, for exactly this reason.

What a public schema gives away once real routes exist is not data but design:
every path, every parameter name, and every request and response shape,
including the ones the caller is not allowed to invoke. For this system that
enumerates the Care re-identification surface (§6.2) and the leadership roll-up
surface (§5.5) to anyone who can reach the tool — which, after an LTI launch,
is every enrolled student's browser.

**The obvious fix is wrong**, so do not take it without reading this. Setting
`openapi_url=None` unconditionally breaks two things the spec depends on:
`scripts/generate_client.sh` generates the frontend client from the backend
OpenAPI (§13), and §7.1 keeps the schema specifically because the future MCP
server (§7.5) is meant to reuse it. The schema has to remain *producible*; the
decision is only about who can fetch it over HTTP.

Options, in rough order of cost:

- **Leave it public.** Defensible: the deployment is single-tenant, self-hosted,
  and behind a TLS-terminating proxy (§7.2), and hiding a schema is not a
  security control on its own. If this wins, say so in the pull request so the
  next reviewer finds a decision rather than an oversight.
- **Serve it only outside production**, keyed on the `ENVIRONMENT` setting
  (§6.3) that `/healthz` already reports. Cheap, and it keeps `/docs` where
  developers want it. Note that `ENVIRONMENT` is free-form, so this needs an
  explicit rule about which values count.
- **Serve it only to an authenticated actor**, through the E0-11 chokepoint.
  Most consistent with the rest of the system, and the most work.

Generation is unaffected either way: `scripts/generate_client.sh` can call
`app.openapi()` in-process rather than fetching the route.

Whichever wins, it is a construction decision the spec does not settle and a
reasonable engineer might make differently, so it wants an ADR — and the
decision belongs in E0's exit checklist below, since after this ticket the
question stops being hypothetical for every epic that follows.

## Scope

- Playwright configuration and `tests/e2e/`, running against the Compose stack.
- Install Playwright as a **pinned devDependency** and invoke the local binary.
  The `e2e` job currently runs `npx --yes playwright install` and
  `npx playwright test` (the "Run Playwright" step in
  `.github/workflows/ci.yml`, mirrored in the `e2e` target of the `Makefile`),
  which resolves whatever version is latest at run time and so breaks the
  `CLAUDE.md` rule against unpinned tool versions in CI. Fix it in this ticket,
  since this is where those lines stop being dead code. The license scanner —
  `license-checker-rseidelsohn` in the `supply-chain` job and in the Makefile's
  `licenses` target — pins its version but still fetches from the registry
  rather than a lockfile; fold it in if the frontend has landed by then. Raised
  by the E0-01 security review. (Line numbers were cited here originally and had
  drifted by four tickets; the steps are named instead.)
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
- [ ] The `/docs` and `/openapi.json` exposure question above is answered, the
      answer is recorded in an ADR, and the schema is still generatable for
      `scripts/generate_client.sh` whatever the answer is.

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

- [ ] Every CI gate that has something to check is enforcing, and the pull
      request names each one still tolerant with the reason. At this point that
      should be `evals`, which waits for E2's first eval set, and the four
      frontend gates (`tsc`, `eslint`, production build, bundle budget), which
      wait for E1 — no frontend exists in E0. Anything else still tolerant is a
      finding, not a footnote.
- [ ] `docker compose up` from a clean checkout reaches a working system.
- [ ] A student, an instructor, and a dean each land on the right empty view
      from whichever door applies to them.
- [ ] The §4.1 invariant suite runs and cannot be skipped.
