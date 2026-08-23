# 0078 — The login state cookie is signed with a per-process key and lives five minutes

**Status:** Accepted
**Date:** 2026-08-22
**Tickets:** [E0-18](../tickets/e0/E0-18-e0-exit-smoke.md) (PR #57), recorded by
[E0-42](../tickets/e0/E0-42-the-records-the-epic-falsified.md)

Written after the fact. The decision shipped in `backend/app/api/deps.py`'s module
docstring, which argues it well and is not where anybody looks for a decision;
this record is the index entry it never got, and the docstring stays as the
detail.

## Context

Both entry doors leave the tool and come back. `/lti/login` sends a browser to the
platform and `/lti/launch` receives what the platform signed; `/auth/oidc/login`
sends it to the provider and `/auth/oidc/callback` receives the code. `state` is
the cross-site request forgery defence, `nonce` is the replay defence, and on the
web door the PKCE verifier is the whole of what binds an authorization code to
this client, since it is a public client with no secret. All three are defences
only if the second request can be shown to have come from the same browser as the
first, so something has to hold them in between.

[SPEC](../SPEC.md) does not decide where. §13 names `api/deps.py` for "auth
context, role scoping, n-threshold guards" and E0 has no session model at all —
E1's breakdown owns the session, and platform-side state storage for cookieless
iframes with it. E0-18 needed the two doors working before any of that exists.

## Decision

**A short-lived signed cookie per door**, written and read in one module.

- **A JWT signed HS256**, carrying `state`, `nonce` and — on the web door — the
  PKCE verifier. The algorithm is passed explicitly on the way in *and* on the way
  out: a verifier that read `alg` out of the cookie would accept `none` from
  anyone who can write a cookie, which is everyone.
- **The key is `secrets.token_bytes(32)`, minted in `create_app` and held on
  `app.state.login_secret`.** Per process, never configured, never persisted.
- **300 seconds**, as both the JWT `exp` and the cookie `max-age`. Five minutes is
  what both mocks give their own pending requests and is generous for a redirect a
  browser follows immediately.
- **`HttpOnly`, `SameSite=Lax`, `path=/`, and `Secure` unless `ENVIRONMENT` is
  exactly `development`** — the same comparison and the same constant
  (`app.config.DEVELOPMENT_ENVIRONMENT`) that [ADR 0074](0074-the-openapi-schema-is-served-only-in-development.md)
  keys `/docs` on. The comparison is made once, in `deps.py`, rather than at each
  door.
- **One cookie name per door**, because the two flows can be in progress at once
  and a shared name would have the second overwrite the first.

## Alternatives rejected

**A row in a table.** Where E1 puts this, and the right answer once there is a
session model and an iframe with no cookies. Rejected for E0 only: it means
inventing that schema in a ticket whose subject is the doors.

**An unsigned cookie.** Rejected because it proves nothing: the point of `state`
is that the caller did not choose it, and comparing a caller-supplied `state`
against a caller-supplied cookie is a comparison of two values the same caller
wrote.

**A configured secret, in `.env.example`.** Rejected because an `.env.example`
entry is a promise that a value is worth setting, and this mechanism has a
two-ticket life. See the consequence below, which is the price of that.

**`SameSite=None; Secure`.** Correct for a real LTI launch, which is a
cross-*site* POST from the platform — and that is exactly the cookieless problem
E1's boundary section owns. Rejected here because widening it now ships the weaker
cookie for the length of E0 to buy a deployment nobody has; on the development
stack every service is `localhost` on another port, which is one site.

**`Secure` unconditionally.** Rejected because a `Secure` cookie is not sent to
`http://localhost`, so every development flow would fail on a `state` mismatch and
look like a broken door.

## Consequences

- **Two `api` replicas cannot serve one login.** The second process cannot read
  the first process's cookie, so a login that starts on one and returns to the
  other is refused. Compose runs one `api` container and E0 is a single-process
  system, so this is true today and costs nothing today. **Scaling past one
  replica requires a shared or configured signing key first** — it is not a
  load-balancer setting and not a sticky-session workaround, it is this decision
  being reversed.
- **Restarting the API invalidates every login in flight.** The browser gets a
  refusal rather than a session, which is the safe direction.
- A login takes at most five minutes. A person who leaves the provider's page open
  longer starts again.
- Every failure to read the cookie — absent, forged, expired — is the same `None`
  and the same refusal, so a refusal never tells an attacker whether their forgery
  was well formed.
- E1 replaces this outright with its session model. When it does, the module
  docstring and this record go together: the cookie names, the lifetime and the
  per-process key are all in `deps.py` and nowhere else.
