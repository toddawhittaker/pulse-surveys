# 0093 — The web door keeps the cookie-carried login handshake

**Status:** Accepted
**Date:** 2026-08-26
**Tickets:** [E1-09](../tickets/e1/E1-09-oidc-web-door.md)

## Context

A login that leaves the tool and comes back has to be recognised when it
returns. The web door mints a `state`, a `nonce` and a PKCE verifier at
`/auth/oidc/login` and checks all three at `/auth/oidc/callback`, and something
has to hold them in between.

[0078](0078-the-login-state-cookie-is-signed-per-process-and-short-lived.md)
made that a short-lived signed cookie for both doors.
[0089](0089-the-session-both-doors-issue-and-the-launch-nonce-ledger.md)
superseded it for the launch door, moving that handshake into a server-side
store (`lti_launch_state`, `app.lti.in_flight`) — because a browser blocks a
cookie inside the LMS's cross-site iframe *whatever its attributes say*, so a
cookie handshake cannot complete there at all, and SPEC §7.3 requires that no
third-party cookie ever be needed. 0089 recorded the web door as keeping the
cookie "until E1-09", which reads as a deferral rather than a decision, and
0078's own consequences say E1 "replaces this outright". E1-09 is the ticket
that has to settle it, and the spec does not: §7.3's requirement is about the
iframe, and no iframe is involved in a web login.

## Decision

**The web door keeps the ADR 0078 handshake exactly as it is** — the
`pulse_oidc_login` cookie, signed HS256 with the per-process
`app.state.login_secret`, `HttpOnly`, `SameSite=Lax`, `path=/`, `Secure` unless
`ENVIRONMENT` is `development`, five minutes as both the JWT `exp` and the
cookie `max-age`, carrying `state`, `nonce` and the PKCE verifier.
**0089's supersession of 0078 is launch-door-only**, and 0078 stands unqualified
for this door.

The reason the launch handshake had to move does not reach here.
`/auth/oidc/callback` is a **top-level navigation** the browser makes to this
tool's own address — the provider redirects the whole tab, not a subframe — and
`SameSite=Lax` is written precisely to allow a cookie on a top-level GET
navigation, cross-site or not. There is no iframe, no third-party cookie, and
nothing for a browser's third-party-cookie policy to block.

What E1-09 does change is what happens on the way out. The cookie is now cleared
on **all three** exits from the callback — the session that was issued, the
refusal, and the cancel branch this ticket adds — so a login buys exactly one
attempt whichever way it ends. That was 0078's burn-after-use property; E1-09
only widened the set of exits it has to cover.

## Alternatives rejected

**A server-side handshake store for the web door, like 0089's.** Consistency
with the launch door is the argument, and it is the only one: the store would
be a table, a migration, two `pulse_app` grants, a purge beat, and a second
place a login in flight can be, bought to solve a problem — the cookie-blocking
iframe — that this door does not have. A mechanism copied for symmetry, whose
motivating fact is absent, is a mechanism nobody can later tell the reason for.

**A configured secret for the login cookie**, so two `api` replicas could serve
one login. Rejected on 0078's own reasoning, which has not changed: an
`.env.example` entry is a promise that a value is worth setting, and this one
carries a five-minute in-flight value where dying on a restart is the safe
direction. The session itself is the thing a restart must not invalidate, and
0089 already gave *that* a configured secret. The replica limit is the price,
and it is in the consequences below rather than discovered under load.

**`SameSite=None` on the login cookie.** Rejected: the cross-site POST that
needed `None` was the launch door's, and it no longer sets a cookie at all.
`None` would widen this cookie to every cross-site subrequest and buy this door
nothing that `Lax` does not already give it.

**Rendering the cancel branch's answer from what the provider sent.** Rejected
outright, and it is why `cancelled_page()` takes no argument: RFC 6749 §4.1.2.1
puts no grammar on `error_description` or `error_uri`, so both are text an
attacker chooses, and a page repeating them is a page whose words they wrote
under this tool's name and styling. The log line gets the error code alone, and
only when it is exactly one of four registry members; anything else logs
`unrecognized`, because `error` is as attacker-chosen as the description is.

## Consequences

- **Two `api` replicas still cannot serve one web login.** The second process
  cannot read the first's cookie, and a login that starts on one and returns to
  the other is refused. Scaling past one replica requires a shared or configured
  login secret first — it is this decision being reversed, not a load-balancer
  setting. The session survives it (0089's configured `SESSION_SECRET`); only
  the five-minute in-flight value does not.
- **Restarting the API still invalidates every web login in flight**, and the
  browser gets a refusal rather than a session.
- **Two handshake mechanisms exist, one per door, and that is now on purpose.**
  Anyone reading `app/api/deps.py` beside `app/lti/in_flight.py` sees a
  difference that looks like drift; the module docstring and this record say
  which fact makes it a difference. The day the web door is reached inside an
  iframe — nothing in E1..E13 puts it there — this decision is the one to
  revisit.
- **A sentence in `app/services/session.py` is now false, and this ticket could
  not fix it.** `SessionClaims` says `iss` is "the platform's issuer URL, or
  `None` for the web door where a session is not platform-issued". `iss=None` is
  a value `issue_session` cannot actually produce: it writes `payload["iss"]`
  unconditionally and PyJWT raises `TypeError: Issuer (iss) must be a string`.
  So both doors pass the issuer of the token the session was minted from — the
  platform at one door, the identity provider at the other. That module was
  read-only for E1-09. **Done when** `SessionClaims`' docstring says what `iss`
  carries at each door, and either `issue_session` omits a `None` `iss` from the
  payload or the type stops offering one.
- **Logout inherits nothing from this cookie.** Whenever a logout is built — it
  is not in E1-09's scope, and the ticket leaves it to whichever epic first needs
  it — `pulse_oidc_login` has already been cleared at the callback, on every one
  of the three exits. There is no in-flight login left for a logout to end, only
  the session.
