# E1-08 — The launch door on `pylti1p3`

**ID:** E1-08
**Branch:** `e1/launch-door-pylti1p3`
**Depends on:** E1-05, E1-07
**Security-relevant (⚠ line-by-line):** the whole validation path — token
verification, state/nonce/replay/clock-skew handling, the cookieless storage,
and session issuance. This is the ticket the epic's ⚠ exists for.

## Context

ADR 0073 deferred `pylti1p3` to "the ticket that restructures this code
anyway" — this one. E0-18 verifies both doors' tokens with PyJWT in
`app/services/tokens.py`; per that ADR's consequences, the web door keeps that
verifier and the launch door moves to the library, and the two are expected to
diverge rather than be kept artificially alike. §14.3 E1 names the depth E0
deliberately skipped: state, nonce, replay, clock skew (§9.1's launch fixture
list), platform-storage patterns for cookieless iframes, and §7.3's short-lived
launch-session JWT so no third-party cookie is ever required.

This ticket also builds the **session module both doors share**: the launch
door issues the session here; E1-09 issues the same session type from the web
door; E1-12 gives sessions their stored identity. Scope discipline: this
ticket validates and issues — it does **not** write course, section, or user
rows (E1-10's, so the line-by-line review of validation is not diluted by ORM
writes).

Read first: ADR 0073 in full (including what the adoption was expected to
cost); ADR 0078 (the login state cookie's bounds); SPEC §7.3, §9.1, §2.1
(claims the launch carries); `app/lti/launch.py` and `app/services/tokens.py`
as they stand; E1-07's mint catalog (the refusal fixtures); §13 (the `lti/`
package homes: `registration.py`, `launch.py` — add only modules with callers,
per ADR 0073's note).

## Scope

- `pylti1p3` pinned (exact, per ADR 0005) with its framework adapter written
  against the session model this ticket defines; launch validation moves onto
  it: signature against the registration's `jwks_url`, `iss`/`aud`/
  `deployment_id` against the registration row, message type and version,
  `nonce` single-use with a bounded store, `state` round-trip integrity,
  clock-skew windows for `iat`/`exp`.
- Cookieless survival per §7.3: the library's platform-storage/postMessage
  patterns plus the launch-session JWT — short-lived, signed, carrying no more
  than the session needs. What the session JWT carries, where the signing key
  lives, and its lifetime are decisions: ADR them if they outlast this ticket
  (they will).
- Every E1-07 mint is met by a refusal test: wrong key, tampered claims, wrong
  `aud`, wrong `iss`, missing nonce, **replayed nonce**, tampered/missing
  state, stale/future timestamps. Each refusal is specific enough that the
  test can tell which guard fired, and none leaks claim contents into the
  error page or log (no student PII in logs — §10).
- The happy path lands on E1-04's landing routes carrying the session; the
  claims-derived landing mapping (`landing_role_for`) keeps working unchanged
  — replacing it is E1-13's, and this ticket must not half-replace it.
- `app/services/tokens.py` is untouched except where the launch door stops
  calling it; the web door's use stands (ADR 0073). If the adapter forces a
  change there, that is a dispute to raise, not a drive-by edit.

## Acceptance criteria

1. All §9.1 launch cases pass: valid launch lands; each E1-07 mint is refused
   with its specific guard asserted.
2. A launch in a cookie-blocked context (Playwright with third-party cookies
   disabled) completes via the cookieless path.
3. The nonce store refuses a second presentation of the same token, across
   process restart if the store outlives the process (say which in the ADR).
4. A session survives navigation between landing routes and expires on
   schedule; expiry is tested at the boundary, not just "eventually."
5. `ruff`, `mypy` strict on the touched packages, and the full §4.1 pass stay
   green; the new dependency's license is clean in the gate.

## Out of scope

- Provisioning of any row (E1-10). Role resolution changes (E1-13). Identity
  (E1-12). NRPS/AGS service calls (E1-11). Deep Linking (deferred, README).
- Web-door changes beyond consuming the shared session module (E1-09).
