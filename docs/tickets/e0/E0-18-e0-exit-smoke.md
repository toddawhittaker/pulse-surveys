# E0-18 — E0 exit: both doors, end to end

**ID:** E0-18
**Branch:** `e0/e0-exit-smoke` (two pull requests; see the work plan)
**Depends on:** E0-11, E0-13, E0-15, E0-16, E0-17, E0-26 item 1, E0-22

## Context

E0's exit condition is that `docker compose up` yields a launchable-into,
loggable-into, testable system that does nothing yet (§14.3). Nothing proves
that today, and most of it is not yet true: the backend serves exactly one
route, `/healthz` (`backend/app/api/` holds only `health.py`). Both mocks are
finished and tested, the mock platform is registered in `lti_platform` by the
seed (E0-31 item 1, ADR 0068), and the CI `e2e` job exists with the stack
bring-up already written — but there is no door on the tool for either mock to
open, no Playwright suite, and the `e2e` job skips itself when it finds no
specs.

So this ticket has two halves, in order: **build the smallest tool-side entry
for both doors**, then **prove it in a browser and make the proof a gate**. The
first half is new backend surface; the second is the first Playwright specs and
the removal of the e2e tolerance branch, so every later epic inherits a
pipeline that exercises both entry doors on every run (§9.2).

Read first: SPEC §14.3 (E0's and E1's exit criteria — the boundary between them
is most of what this ticket has to get right), §9.2, §2.1, §13 (module homes),
`docs/DESIGN_BRIEF.md` and `design/tokens.css` (the landing pages are UI),
and §6.2 before touching anything the Care landing page shows.

## The boundary with E1, drawn before any code

E1 is "Entering the app": launch validation depth (state/nonce storage for
cookieless iframes, replay, clock skew), provisioning, the hourly roster sync,
role resolution from claims *plus the app-owned assignment model*, the unified
session model, and — named in E1's own ticket breakdown — the **dual-door
identity merge**. None of that is built here. What E0 needs is thinner:

**E0 builds:** the four routes below, signature-verified tokens, a landing page
per role derived from the verified token's claims alone, and the e2e proof.

**E0 does not build:** any database identity resolution on either door, any
`user` row for a mock subject, any session that outlives the entry
flow, any purview computation. `transitive_purview` raises by design (ADR
0003), and its docstring already names this ticket: the leadership landing
views are empty *by design* and must not traverse it. If a spec here needs it,
the spec is asserting more than E0 delivers — fix the spec.

Two consequences, stated so they are decisions rather than drift:

1. **The landing role comes from the verified token, not from the database.**
   A launch carries the LIS roles claim; a web login's `id_token` carries
   `https://pulse.example/claims/roles` (`mock-idp/app/flow.py`, ADR 0058).
   Both tokens are signature-verified before anything reads them, so an empty
   view labelled by claim is honest. E1 replaces this with the app-owned
   assignment model; the seam to leave is one function that maps a verified
   token to a landing role, called from both doors, so E1 edits one place.
2. **The same-identity assertion moves to E1, and this ticket says so.** The
   old criterion here — both doors resolve to the same stored identity for the
   two-hat person — cannot be met without the identity merge E1's breakdown
   owns. What E0 *can* assert: the two-hat person exists on both doors and
   both doors open for her. The cross-mock reference that makes that a fact
   about one human rather than two fixtures is
   `mock-idp/app/seed.py::LMS_INSTRUCTOR_USER_ID`, which names the mock LMS's
   instructor user; a unit test here pins the two constants to each other so
   the reference cannot go stale silently. The DB-level merge assertion is
   written into E1's carried-forward notes (see E0-28 item 6 for the file).

## The four routes, and what each one does

Homes per §13: `backend/app/api/lti.py` (login initiation and launch — §13
names this module for exactly these endpoints) and a new
`backend/app/api/auth.py` (web login — §13 has no router for it; a new module
is justified because nothing fits, and the PR says so). Validation helpers go
in `backend/app/lti/launch.py` and a small OIDC client beside the auth router;
keep the routers thin per §13.

**`POST /lti/login`** — LTI 1.3 third-party-initiated login. Receives `iss`,
`login_hint`, `target_link_uri`, `lti_message_hint` from the mock's launch
form. Looks up the platform by `iss` in `lti_platform` (seeded by E0-31 item
1); unknown issuer is a 4xx page, not a silent 302. Answers a 302 to the
platform's authorization endpoint carrying `client_id`, `redirect_uri` (the
tool's own launch URL), `state`, `nonce`, `login_hint`, `lti_message_hint` —
the mock validates all six (`mock-lms/app/launch.py::resolve_launch`), and
`redirect_uri` is compared exactly against the mock's configured
`MOCK_LMS_TOOL_LAUNCH_URL`, so the tool must build it from its own public base
URL setting (below). `state` and `nonce` go into a short-lived signed cookie;
E1's platform-storage/cookieless work replaces that mechanism and is out of
scope here.

**`POST /lti/launch`** — receives `id_token` + `state`. Checks `state` against
the cookie, then verifies the token: RS256 signature against the JWKS fetched
from `lti_platform.jwks_url` (server-side URL, seeded), `iss` matches the
registered issuer, `aud` the registered `client_id`, `deployment_id` a row in
`lti_deployment`, `nonce` the cookie's, `exp` current. Then renders the
landing page for the LIS roles claim: Learner → student empty view, Instructor
→ instructor empty view. Render directly in the response — no session, no
redirect; there is nowhere else to go in a system that does nothing yet.
Depth (replay windows, clock-skew tolerance, cookieless) is E1's; absence of
*basic* state/nonce/signature checks is not tolerable even briefly, because
this is auth code and the first thing E1 reads.

**`GET /auth/oidc/login`** — starts the code flow against the mock IdP: 302 to
its authorization endpoint with `client_id`, `redirect_uri`, `response_type=
code`, `scope=openid email`, `state`, `nonce`, and PKCE (`code_challenge`,
`S256` — the mock refuses anything else). Verifier and state ride the same
short-lived signed cookie mechanism as the launch door.

**`GET /auth/oidc/callback`** — validates `state`, exchanges the code at the
token endpoint (server-side, `httpx`, PKCE verifier; the client is public, no
secret exists), verifies the `id_token` (signature via the IdP JWKS, `iss`,
`aud`, `nonce`, `exp`), reads the roles claim, renders the landing page for
the highest-standing role in it: leadership roles → leadership empty view,
`CARE` → Care empty view, `ADMIN` → admin empty view. The Care page shows a
heading and nothing else — read §6.2 before writing even that. Rendering at
the callback URL leaves `code` in browser history; acceptable for a
development-only flow and named in the PR, gone when E1's session lands.

**Landing pages** are server-rendered HTML from the API (no frontend exists
until E1). Follow `docs/DESIGN_BRIEF.md` and `design/tokens.css`; keep them
spare — a heading naming the role's view, an empty-state line, nothing
interactive. Every page keyboard-reachable. Give each a `data-testid` the
specs address, mirroring the mock IdP's convention
(`mock-idp/app/pages.py::IDENTITY_CONTROL_TESTID`); add testids to the mock
LMS launch form in the same PR if it has none.

## Configuration: one public base URL, two horizons

A host browser reaches the services at `localhost:8000/8080/8081`
(`docker-compose.override.yml`); containers reach each other as
`api/mock-lms/mock-idp:8000`. Every URL below is one or the other — decide per
value, not per service:

- **Tool settings (new, in `Settings` + `.env.example`, same PR):**
  `PUBLIC_BASE_URL` (browser-facing base of the tool itself, default
  `http://localhost:8000`; `/lti/launch` and `/auth/oidc/callback` derive from
  it), the platform's browser-facing authorization endpoint (default
  `http://localhost:8080/authorize` — `lti_platform` has no column for it, and
  E0-23 decided service-address columns are E1's, built with the code that
  reads them; a settings field is the E0 stand-in and the ADR says so), and an
  OIDC block for the IdP: issuer (`http://mock-idp:8000`, must equal the
  token's `iss`), browser-facing authorize URL (`http://localhost:8081/...`),
  server-facing token and JWKS URLs, client id.
- **Mock repointing, in the override file (dev wiring, absent from
  deployments):** `MOCK_LMS_TOOL_LOGIN_URL` / `MOCK_LMS_TOOL_LAUNCH_URL` →
  `http://localhost:8000/lti/login` / `/lti/launch`, and
  `MOCK_IDP_TOOL_REDIRECT_URI` → `http://localhost:8000/auth/oidc/callback`.
  This settles E0-30 item 3; record the answer there when it lands.
- Server-side fetches (`jwks_url`, token endpoint) keep container names.

## Decide and record: `/docs` and `/openapi.json`

`create_app()` builds `FastAPI(...)` without `docs_url`/`openapi_url`
(`backend/app/main.py`), so the schema is public to any caller. Harmless while
it described `/healthz`; this ticket adds the first real routes, so decide now.
**Recommendation: serve them only when `ENVIRONMENT` is exactly
`"development"`** — the same value `backend/app/db.py` and `scripts/seed.py`
already key on (E0-37 item 2 centralizes the constant; whichever ticket lands
second imports it). Cheap, keeps `/docs` for developers, and hides route
enumeration (§6.2's reveal surface, §5.5's roll-ups) from launched browsers in
any real deployment. Leaving it public is defensible single-tenant; gating on
the authenticated actor is most consistent and the most work — rejected here
as E1-shaped. The schema stays *producible* either way (§7.1 keeps it for the
future MCP server; the §13 client generator calls `app.openapi()` in-process —
note the script does not exist yet, so there is nothing to update). ADR
required: spec-silent, contestable.

## One new dependency, named out loud

Nothing in the locked closure verifies an RS256 JWT (the mocks *sign* with
stdlib arithmetic under ADR 0035's mock-only bound — do not copy it into the
tool). **Recommendation: pin `PyJWT` + `cryptography`**, used by both doors.
The alternative — adopting `pylti1p3` now, since §13 assigns it `lti/` — buys
nothing for E0 (it needs a framework adapter, does not cover the web door, and
E1 restructures this code anyway) and is rejected for cost, in a short ADR so
E1 finds a decision. Lockfiles updated per `CLAUDE.md`.

## Work plan — two pull requests on this ticket

**PR 1 — the doors.** Routes, validation, landing pages, settings +
`.env.example`, override repointing, `/docs` gating, the two ADRs, and
integration tests: a signed launch minted the way
`tests/integration/test_mock_lms_launch.py` mints them lands on the right
view; a tampered signature, wrong `aud`, unknown `iss`, stale `exp`, and a
mismatched `state`/`nonce` are each refused; the full code flow against the
in-process mock IdP lands the dean on the leadership view; the wrong-door
person is refused by the IdP itself (already tested there — do not re-prove
it, drive through it); the cross-mock constant test pinning
`LMS_INSTRUCTOR_USER_ID` to the mock LMS instructor's `user_id`.

**PR 2 — the proof.** Playwright as a **pinned devDependency**: root
`package.json` + `package-lock.json` (the repo's first — new files, named in
the PR), `playwright.config.ts` with `baseURL` from the published ports, specs
under `tests/e2e/`. The CI `e2e` job currently runs `npx --yes playwright
install`, resolving latest at run time against the `CLAUDE.md` pin rule — it
becomes `npm ci` + local-binary `npx playwright install --with-deps chromium`
+ `npx playwright test`. Fold the license scanner into the same
`package.json` as a pinned devDependency (it currently pins a version but
fetches from the registry). The job gains migrate-and-seed steps before the
specs run — host-side Python mirroring the `test` job's setup, `alembic
upgrade head` and `python scripts/seed.py` with `DATABASE_URL` rewritten to
`localhost:5432` (the override publishes the port; the runtime image does not
carry `scripts/` or the migrations, so exec-in-container is not an option).
Remove the tolerance branch: the `detect.outputs.e2e` find-and-skip gating and
the "No e2e specs yet" notice go, in `ci.yml` and the `Makefile` both — an
empty suite fails loudly from here on. E0-38's inert-diff skip is unchanged.
The failure-artifact upload already exists; verify it by breaking one
assertion once, then reverting.

Specs: a student launch lands on the student empty view; an instructor launch
on the instructor view; the dean's web login on the leadership view; the
two-hat person through both doors in one spec. Address forms by the published
testids; learn subjects and placements from the mocks' published documents
(`/mock/registration` on both — `tests/conftest.py` already models this
pattern) rather than hardcoding them.

## Out of scope

- Everything the E1 boundary section defers: provisioning, sessions beyond the
  entry flow, cookieless handling, replay and clock skew, role resolution from
  the assignment model, the dual-door identity merge, `pylti1p3`.
- Any real view content (survey is E2, reports E4, roll-ups E9) and any `user`
  row for a mock subject — that is a second registration decision and ADR
  0068's reasoning applies to it.
- Accessibility *audit* (E13); keyboard reachability is in scope.

## Acceptance criteria

- [ ] `docker compose up -d` brings every service healthy: `api`, `worker`,
      `beat`, `db`, `redis`, `mailpit`, `mock-lms`, `mock-idp`.
- [ ] A Playwright spec completes an LTI launch from the mock LMS as a student
      and as an instructor; each lands on the view its verified roles claim
      names.
- [ ] A Playwright spec completes the mock IdP code flow as the dean and lands
      on the leadership view.
- [ ] One spec drives the two-hat person through both doors; a unit test pins
      `mock_idp` and `mock_lms` seed constants to each other; the DB-level
      same-identity assertion is recorded as E1's, in E1's carried-forward
      notes, in this ticket's PR.
- [ ] Integration tests refuse: bad signature, wrong `aud`, unknown `iss`,
      unknown `deployment_id`, stale `exp`, mismatched `state`, mismatched
      `nonce` — each as its own case, launch door and web door alike where the
      check exists on both.
- [ ] The CI `e2e` job runs the suite unconditionally on non-inert diffs, with
      Playwright resolved from the committed lockfile; the find-and-skip
      branches are gone from `ci.yml` and the `Makefile`; `make ci` runs the
      same suite.
- [ ] A deliberately broken assertion uploads the Playwright report artifact;
      the break is reverted in the same PR's history.
- [ ] The `/docs` exposure decision is made, recorded in an ADR, and enforced
      by a test (development serves them; any other `ENVIRONMENT` value does
      not; `app.openapi()` still produces the schema either way).
- [ ] The JWT dependency ADR exists and the lockfiles carry the pins.

## Definition of done

**Tests apply — this ticket is tests**, both integration and the first §9.2
Playwright paths. **Docs apply:** `README.md` gains "how to run the e2e suite
locally" (Compose prerequisite, seeding, headed mode for debugging). **AI
evals do not apply** — the eval gate stays tolerant until E2's first eval set;
say so in the PR so it is a recorded decision. **Accessibility:** no audit,
but every landing page must be tab-reachable; fix here, not in E13.
**Security review applies and is not light:** this is the first ticket where a
real token reaches real tool code. Review that no spec depends on an
authorization shortcut, that no fixture grants a role the token would not, and
the state/nonce/PKCE handling on both doors. Run it in a separate session per
§14.2 item 3, and rescope it to the PR's base (the review defaults to the
wrong diff on ticket branches).

## E0 exit checklist

Confirm and record in PR 2's body:

- [ ] Every CI gate with something to check is enforcing; the PR names each
      one still tolerant and why. Expected: `evals` (waits on E2) and the four
      frontend gates (wait on E1 — no frontend exists). Anything else tolerant
      is a finding.
- [ ] `docker compose up` from a clean checkout reaches a working system.
- [ ] A student, an instructor, and a dean each land on the right empty view
      from whichever door applies to them.
- [ ] The §4.1 invariant suite runs and cannot be skipped.
