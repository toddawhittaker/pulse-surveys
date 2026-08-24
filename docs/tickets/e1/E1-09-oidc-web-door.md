# E1-09 — The web door: OIDC login and the branch the user cancels

**ID:** E1-09
**Branch:** `e1/oidc-web-door`
**Depends on:** E1-08
**Security-relevant (⚠ line-by-line):** the authorization-code flow — state
binding, token exchange, `id_token` verification, cookie attributes, and the
error branch's refusal to trust anything it is handed.

## Context

E0-18 built a minimal web door: authlib-shaped flow against the mock IdP,
PyJWT verification (ADR 0073 — the web door *keeps* this verifier), landing
by claims. Batch F (E0-30 item 1) taught the mock IdP RFC 6749 §4.1.2.1 error
redirects precisely so this ticket's error branch would be testable: "the case
it handles, the user cancelling, is the one that actually occurs." ADR 0077
made the five `OIDC_*` settings required with mock-address refusals outside
development; ADR 0078 bounds the login state cookie (signed per process,
short-lived). This ticket brings the web door to the same depth E1-08 brings
the launch door, on the shared session module E1-08 built.

Read first: ADR 0077 (all four refusal routes must keep holding), ADR 0078,
ADR 0073 (why PyJWT stays here), Batch F's ticket
(`../e0/E0-30-review-debt-from-e0-16.md`) for the error-redirect shape;
`backend/app/api/auth.py` and `app/services/tokens.py` as they stand; SPEC §2
(which roles enter this door).

## Scope

- The full authorization-code flow hardened: `state` generated, bound to the
  in-flight login, and verified on return; `nonce` in the `id_token` checked;
  token exchange over the tool-facing endpoint; `id_token` verified by
  `app/services/tokens.py` exactly as today (issuer, audience, algorithm list
  constant — ADR 0073's closing condition).
- **The error branch ships tested:** a refusal arriving as a redirect carrying
  `error` and the sent `state` (the user cancelled; the IdP refused) lands the
  person on a calm, non-blaming page, verifies the `state` before trusting
  anything else in the redirect, echoes nothing attacker-supplied
  (`error_description` is untrusted text), and logs no more than the error
  code. A mismatched or absent `state` on an error redirect is itself a
  refusal, tested separately from the happy cancel.
- Session issuance through E1-08's shared module — same type, same custody,
  cookie attributes per ADR 0078 (and `Secure` outside development, per the
  environment rules ADR 0078/0079 record).
- Landing continues through the unchanged claims mapping (E1-13 replaces it).

## Acceptance criteria

1. A seeded leadership, Care, and admin identity each logs in and lands on
   their E1-04 route with a session.
2. The cancel path: Playwright drives an IdP refusal; the tool shows the calm
   page; no session exists afterwards; the assertion covers the *absence* of
   the session (the forbidden state, per MISTAKES entry 2's preference).
3. A forged error redirect (wrong `state`) is refused distinctly from a
   genuine cancel.
4. ADR 0077's refusal tests and the §4.1 pass stay green; no new setting is
   introduced without its `.env.example` name.

## Out of scope

- Identity resolution (E1-12) and role resolution (E1-13).
- Any IdP beyond the mock; local-account fallback (§7.1 names it as pilot
  fallback — nothing in E1..E13 schedules it; raised in the breakdown PR as a
  scheduling question rather than silently dropped).
- Logout/back-channel logout — not in §14.3 E1; deferred to the epic that
  first needs it, noted in `carried-from-e1.md` by E1-15 if still unowned then.
