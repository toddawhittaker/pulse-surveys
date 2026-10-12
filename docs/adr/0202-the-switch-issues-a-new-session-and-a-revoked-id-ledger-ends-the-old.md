# 0202 — The switch issues a new session, and a revoked-id ledger ends the old one

**Status:** Accepted
**Date:** 2026-10-12
**Ticket:** [E9-04](../tickets/e9/E9-04-role-switcher-and-logout.md)

## Context

SPEC §2 gives a person with several hats a role switcher and keeps Care apart
from the reporting roles; SPEC §14.3 has logout end a Pulse session at once. A
session is a signed token that verifies until its `exp`, sixty minutes after it
was issued, with no server-side record ([0089](0089-the-session-both-doors-issue-and-the-launch-nonce-ledger.md)).
Nothing could end one sooner. The spec does not say how a switch changes a
session's role, how a session ends before its token expires, or where that
check is made.

## Decision

**A switch issues a new session and revokes the old one; it never changes a
session's role.** `services/session.switch_session` re-reads the person's views
at the session's own door (`authz.resolve_landings`, over the assignments'
door columns, [0026](0026-entry-doors-are-derived-from-the-role-as-generated-columns.md)'s rule) and
refuses a view not in that list. Otherwise it issues a session that copies the
door, subject, issuer and row keys and names only the asked role, and revokes
the old `jti`. A session holds one role, so a Care session is never also a
leadership one, and a gate reads the role off the session, never off the
person ([0196](0196-the-leadership-gate-answers-another-role-403-marked-insufficient-scope.md)).

**A switch is not a refresh** (fix round, ruling G1). The switched token keeps
the old token's `exp` exactly (`issue_session(..., expires_at=claims.exp)`;
`iat` is the time of the switch), and a switch to the session's own role is
refused like any role not held. So no sequence of switches keeps a session,
or a stolen token, alive past the hour it was first issued for.

**A token switches once** (ruling G2). The switch revokes the old `jti` before
it issues, in one transaction, with `ON CONFLICT DO NOTHING RETURNING jti`. A
second switch with the same token waits on the first one's row, gets no row
back once the first commits, and answers the expired-token 401 with nothing
issued.

**Ending a session is a row in `revoked_session`**: the `jti` (primary key)
until the token's own `exp`. Logout and the switch write it with an insert that
does nothing on conflict, and the same transaction deletes rows past their
expiry, so the table purges itself and holds at most an hour of revocations.
The purge reads the real clock, not `services/clock.now`: the signature check
judges `exp` by the real clock ([0109](0109-the-dev-clock-is-a-database-offset-not-a-freeze.md)),
and a purge on a moved development clock would bring ended sessions back.

**The check is made by the gates, not by `session_from_request`.** That
function stays a pure read of the request and the secret. Every role gate in
`api/deps.py` reads through one helper, `_unrevoked_session`, which asks
`session_from_request` and then `is_revoked` on the request's own database
session. A revoked token joins the absent, malformed, expired and forged ones
in the one `None` each gate already refuses, so its answer is the expired
token's answer on every route kind. Logout reads with `ending_session`, which
checks the signature and expiry but not revocation, so a second logout answers
as the first did; it applies the double-submit check when the session rides
the cookie.

## Alternatives rejected

- **Server-side sessions** (a row per live session, looked up on every
  request). It would end sessions too, but it replaces 0089's design for every
  request to serve the rare early end; the ledger holds only the exceptions.
- **One session carrying several roles, with the active one chosen per
  request.** It merges hats in one credential, which SPEC §2 forbids for Care,
  and every gate would have to trust a choice made after the door.
- **The check inside `session_from_request`, with the database passed in.** The
  unit suite calls it with a request and a secret only, and an optional
  database parameter would let a caller skip the check by leaving it out. The
  sweep that only `api/deps.py` reads a session keeps every gate on the helper.
- **A purge job on Celery beat.** A second moving part for a table that a
  write can trim as it goes.

## Consequences

- Every gated request makes one more query, on the connection the route
  already holds. `pulse_app` holds SELECT, INSERT and DELETE on the table.
- The first landing is unchanged: `LANDING_PRECEDENCE` still decides it, and
  the switcher offers the other views in the same order, the student view
  last and only at the launch door.
- **Accepted residue (ruling G3): a switch racing a logout.** If the switch's
  revocation lands first, logout still answers 204 while the switched session
  lives. The person asked for both, and the switched session holds one role
  they really have and keeps the old `exp`, so it ends no later than the
  session they signed out of would have.
- A session ended at the identity provider still lives until its token
  expires; back-channel logout is E13's.
