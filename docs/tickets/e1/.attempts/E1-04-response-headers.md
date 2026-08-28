# E1-04 item 2 — the security response headers (Batch D)

Worktree `/home/todd/projects/pulse-surveys-batch-d`, branch `e1/response-headers`.
Heavy lane. Tests: `tests/integration/test_the_security_response_headers.py` (red).

## Attempt 1 — refactor: move `launcher_origins` to the platform-config module

`launcher_origins` lived in `backend/app/api/dev.py` (the dev-console router). The
framing middleware needs the same derivation, and MISTAKES 13 forbids a second
copy. A security control in `main.py` importing a helper from the dev-console
router is a layering smell, and SPEC §13 puts domain logic in a config module,
not a router. Moved it to `backend/app/lti/registration.py` — the module SPEC §13
names "platform/deployment config, key management", which already reads
`lti_platform`. Left `dev.py` importing the moved function; dropped its now-unused
`urlsplit` and `LtiPlatform` imports.

Result: ruff format/check clean, mypy clean, `dev.launcher_origins is
registration.launcher_origins` True. Committed as a refactor, separate from the
behavior change.

## Attempt 2 — behavior: the security-headers middleware (in progress)

Design (ADR 0102): static headers (nosniff, Referrer-Policy
`strict-origin-when-cross-origin`, base CSP `default-src 'self'; script-src
'self'`) on every response with no DB access; `frame-ancestors 'self' <origins>`
added only to `text/html` document responses, reading `launcher_origins` per
request through a fresh `SessionLocal()` in a threadpool. Keeps `/healthz` and
JSON off the database (design goal + `test_frame_ancestors` reads only documents).

Verification step 1 (npm build): `npm run build` emits an external module script
(`/app/assets/index-*.js`) and an external stylesheet (`/app/assets/index-*.css`)
— NO inline script, NO inline `<style>`. So the CSP needs no `'unsafe-inline'`
anywhere; the same-origin stylesheet is covered by `default-src 'self'`, so no
`style-src` directive is required either. CSP stays minimal.

Result: all 11 header tests green. But the first run of the full unit suite found
a regression I caused: 3 unit tests (`test_the_spa_is_served_from_the_app_factory`
x2, `test_docs_exposure` x1) build `create_app()` with NO reachable database and
serve `text/html` (the SPA mount and `/docs`). My content-type gate made those
responses do a per-request registration read, which failed with
`OperationalError: failed to resolve host 'db'`. This is my regression, not a
stale-`.env` issue — serving a document must not require a reachable database.

Fix: `framing_ancestors` catches `SQLAlchemyError` and degrades to
`['self']` — fail-closed (stricter, never wider), so a document still serves and
the LMS iframe just does not load until the DB is back. Recorded in ADR 0102.
After the fix: 846 unit + 11 header + 149 door/landing integration tests green;
ruff and mypy clean.

## Commits
- `8cda9cf` refactor: move `launcher_origins` to `app.lti.registration`
- `1ec9ff2` behavior: the security-headers middleware in `create_app()`
- (docs) ADR 0102 + README row + this attempt file

## Fix-round — malformed `authorization_endpoint` injects into `frame-ancestors`

The finding: `launcher_origins` built each origin as `f"{scheme}://{netloc}"`
from a stored `authorization_endpoint`. `urlsplit` strips neither a space nor a
`;` from the host, and the SSRF chokepoint (ADR 0081) does not reject those
characters on `authorization_endpoint` (browser-facing, not resolve-judged). So a
stored `https://lms.edu *` emitted `frame-ancestors 'self' https://lms.edu *` —
the bare `*` lets any origin frame the app; a `;`-bearing value appended a whole
CSP directive.

Fix, in `launcher_origins` itself (the root of the derivation, so both the CSP
header and the dev-console links benefit): a module-level compiled regex
`_VALID_ORIGIN` — `^https?://(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]+)?$` —
anchored end to end. Each candidate origin is matched and skipped if it does not
match. A hostname/IPv4 or bracketed IPv6 host with an optional numeric port is
admitted; anything with whitespace, `;`, `,`, `*`, a quote or other
CSP-breaking character is dropped. Fail-safe: a malformed endpoint contributes no
framing source at all rather than corrupting the header.

Chose `launcher_origins` over the middleware: it is the root of the bug, MISTAKES
13 forbids a second copy, and a malformed endpoint has no valid console link
either. Did NOT use `.hostname` — `urlsplit("https://lms.edu *").hostname` keeps
the space; the characters must be validated explicitly.

Result: `test_the_security_response_headers.py` 16 passed (all three target tests
green, including `..._admits_a_valid_ipv6_origin_with_a_port` which must stay
green — the regex admits `[` `]` `:`); `test_dev_console.py` 5 passed. ruff
format/check clean, mypy clean. Records: ADR 0102 gained an emitter-validation
paragraph and an E11-owed residual consequence; the residue is recorded in
`deferred.md` (E1-04 item 2) and `e2/carried-from-e1.md`.

## For the orchestrator
- The e2e/Docker gate serialises through you. `tests/e2e/cookieless-launch.spec.ts`
  is the canary that must run before the PR — it proves the LMS iframe actually
  loads under the enforced `frame-ancestors`, and it is the check for any *runtime*
  inline style the built stylesheet does not cover (the build itself emits none).
- The fresh-context security review over this diff is yours to run; it goes stale
  the moment a fix lands (MISTAKES 19).
