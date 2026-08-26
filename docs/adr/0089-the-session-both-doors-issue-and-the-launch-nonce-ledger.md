# 0089 — The session both doors issue, and the launch-nonce ledger in Postgres

**Status:** Accepted
**Date:** 2026-08-26
**Tickets:** [E1-08](../tickets/e1/E1-08-launch-door-pylti1p3.md)

## Context

E1-08 moves the launch door onto `pylti1p3` (the deferral
[0073](0073-the-tool-verifies-launches-with-pyjwt-rather-than-adopting-pylti1p3.md)
made) and adds the depth E0 skipped: single-use nonces, clock-skew windows,
state round-trip, and a launch that survives inside a cookie-blocked LMS iframe.
Two things that outlive the ticket have to be decided: what a *session* is — the
first one in this product, shared by both entry doors (E1-09's web door reuses
it, E1-12 gives it stored identity) — and where the *replay ledger* lives. SPEC
§7.3 asks for a short-lived launch-session JWT so no third-party cookie is ever
required; §9.1 asks for replay-proof nonces; §8 and §10 govern what a
browser-held credential may carry.

## Decision

**A signed session JWT, issued by `app.services.session`, carrying only who
arrived and in what role.** `SessionClaims` is `door`, `role`, `sub`, `iss`,
`jti`, `iat`, `exp` — the opaque `sub` the launch already carried, and no name,
email or `lms_user_id` (§8 keeps identity in one place; a copy in every browser is
the opposite).

- **HS256, one configured secret** (`SESSION_SECRET`, a `SecretStr` in
  `app.config`). Symmetric because the tool both issues and verifies this token —
  unlike the asymmetric platform key `app.services.tokens` verifies. Configured,
  not per-process, so the `api` container and any replica share it and a restart
  does not log a sitting person out. The algorithm is named on encode and decode
  alike; a verifier that read `alg` off the token would accept `none`.
- **Sixty minutes.** One class period or report-review sitting, no refresh flow in
  E1, and a bound on how long a `sessionStorage` token is worth stealing.
- **Cookie attributes:** `HttpOnly`, `Secure` unless `is_development`,
  **`SameSite=None`**, `path=/`, `max_age=3600`. `None` because the tool is inside
  a cross-site iframe for the whole visit, so `Lax` would drop the cookie on every
  in-iframe request — a gap only the real deployment shape shows.
- **CSRF, live because of `SameSite=None`:** a double-submit token bound to the
  session's `jti` by HMAC (`issue_csrf_token`/`verify_csrf_token`). A tossed cookie
  without the secret still fails, and a token minted for one session does not
  verify against another's `jti`. Its cookie is not `HttpOnly` — the SPA echoes it
  in `X-Pulse-CSRF`. E2's first mutating endpoint consumes the check; E1-15 carries
  the line so it cannot arrive unowned.
- **The cookieless delivery mechanism** is what makes the cookie's attributes
  sufficient for every credential the session uses in the iframe: on a valid
  launch the door sets the cookie *and* 302s to `/app/<role>#session=<jwt>`; the
  SPA captures the fragment into `sessionStorage`, strips it from the address bar,
  and sends it as `Authorization: Bearer` thereafter. `session_from_request` reads
  the Bearer header before the cookie, so the Bearer path carries the session with
  no cookie required.
- **The replay ledger is a Postgres table** (`lti_launch_nonce`), not Redis.
  `claim_nonce` spends a nonce with a plain `INSERT` whose unique-constraint
  violation is the replay, claimed only after every other check passes; the daily
  `purge_expired_nonces` beat task replaces the native TTL Redis would have had.

## Alternatives rejected

- **A per-process session key** — a restart silently logs everyone out
  mid-session, which was fine for the retired five-minute login cookie
  ([0078](0078-the-login-state-cookie-is-signed-per-process-and-short-lived.md))
  and wrong for a session meant to last a sitting. **A one-row DB key table** —
  a migration this ticket otherwise needs and a read per verify;
  [0082](0082-the-tools-signing-key-lives-in-the-database.md)'s reasons to keep a
  key out of settings do not reach this one, which is a single-line symmetric
  secret rather than an asymmetric PEM.
- **`SameSite=Lax`** — drops on every in-iframe request in the real deployment,
  passing every same-site localhost test and failing only where it matters.
- **Redis for the nonce ledger** — every other launch-validation input already
  lives in Postgres and the launch already opens one `Session` the claim rides
  inside; making the disposable task-queue broker the record of which credentials
  were spent pulls a disposability-assuming component into an auth boundary.

## Consequences

- **[0078](0078-the-login-state-cookie-is-signed-per-process-and-short-lived.md)
  is superseded in part** — for the launch door only. The ADR-0078
  `pulse_lti_login` cookie's state/nonce role is now `pylti1p3`'s in-flight cookies
  (`app.lti.fastapi_adapter`); `app.state.login_secret` and the web door's copy of
  that cookie stay until E1-09. The security property (a `Secure`-outside-
  development, single-use, burned-after-use in-flight carrier) does **not** fully
  transfer to those in-flight cookies: the launch handshake's second leg is a
  cross-site POST that must carry them, and a `Secure` cookie drops over `http`, so
  the in-flight cookies are non-`Secure` and the `Secure`-outside-development
  guarantee lives on the session cookie. `docs/disputes/E1-08-01.md` records the
  three ADR-0078 tests this reconciles and the tension with the criterion-5 cookie
  test.
- **The cookieless path covers the *session*, not yet the *handshake*.** The
  in-flight state and nonce are still on cookies, which survive the same-site
  development stack but would be blocked in a genuinely cross-site cookie-blocked
  iframe. `pylti1p3`'s platform-storage/postMessage path for a fully cookie-blocked
  handshake is deliberately not built here; it is follow-up work.
- **One new weak-copyleft dependency enters the runtime closure.** `pylti1p3`
  verifies a launch's JWS with **`jwcrypto`** (LGPLv3+), the first such library
  joining the two psycopg rows [0073](0073-the-tool-verifies-launches-with-pyjwt-rather-than-adopting-pylti1p3.md)
  noted "ask for a human look". LGPL via an unmodified dynamic import is compliant;
  the license gate classifies it "review — weak copyleft" (it prints, it does not
  fail, and CI passes no `--strict-unknown`). Recorded here so the fact is seen,
  not buried.
- **`pulse_app` gains `INSERT` and `DELETE` on `lti_launch_nonce`** — the first
  runtime grant that lets the application write a base table for its own sake
  rather than a moderation record. `SELECT` and `UPDATE` are withheld (the claim
  reads single-use off a constraint violation, never a `SELECT`, and a spent nonce
  is never rewritten). The entry belongs in `RUNTIME_BASE_TABLE_PRIVILEGES`;
  `docs/disputes/E1-08-02.md` records that it lives in a test file the implementer
  could not edit.
