# E9-04 — The role switcher and logout

**ID:** E9-04
**Branch:** `e9/role-switcher-and-logout`
**Depends on:** none
**Lane:** heavy
**Why this lane:** it changes `backend/app/services/session.py`,
`backend/app/api/auth.py`, `backend/app/api/deps.py` and
`backend/app/services/authz.py`, all heavy paths, and adds a session table.
**Size:** M
**Security-relevant:** a switch issues a new session in a new role. A defect
here lets a person switch into a role they do not hold, merges two hats into
one session, keeps a logged-out session working, or lets another site force a
switch.

## Context

SPEC §2: "multi-role people get a role/assignment switcher", and "Care is
deliberately not composable with reporting roles". Sessions today are
short-lived signed tokens that expire rather than end; nothing revokes one.
The first landing follows `LANDING_PRECEDENCE` (`authz.chosen_landing`). This
ticket adds the switch and logout behind the routes; E9-11 draws the
controls.

- **The landings at this door.** A route lists the roles the session's person
  can land in at the door the session came through (`_ASSIGNED_ROLES_AT`), so
  a web-login session never offers the instructor or student role, and a
  launch session never offers Care or Admin (§2's door rules).
- **The switch.** A CSRF-protected route takes one landing role, re-reads the
  person's assignments at that moment, refuses a role they do not hold at this
  door, and otherwise issues a new session in that role and revokes the old
  session's id. A session holds one role; Care is never combined with a
  reporting role, and neither is Admin.
- **Logout (ruling 8).** A CSRF-protected route revokes the session id and
  clears the cookie. Back-channel logout from the identity provider is E13's.
- **Revocation.** A new table holds revoked session ids until their tokens'
  own expiry, and purges rows past it. `session_from_request` refuses a
  revoked id with the same 401 an expired token gets.

Read first: SPEC §2 (doors, composition) and §7.3; ADRs 0089, 0196 and the
session ADRs `services/session.py` cites; `services/session.py`,
`api/auth.py`, `api/deps.py` and `authz.py`'s landing functions.

## Owns

- `backend/app/services/session.py`: revocation and its check.
- `backend/app/api/auth.py`: the landings route, the switch route and the
  logout route.
- `backend/app/api/deps.py`: the revoked-id check where the session is read.
- `backend/app/services/authz.py`: the landings available at a door, from the
  existing door table.
- A model for the revoked-session table, and migration **`e9c3f5a7b403`**,
  planned `down_revision = "e9b2c4d6a802"` (re-pointed to the head it finds).
- `frontend/src/api/openapi.json` and `wire.gen.ts`, regenerated.
- ADR **0202** (the switch issues a new session and revokes the old; the
  revoked-id table instead of server sessions; why the switch never merges
  hats).

## Reuse, do not rewrite

`issue_session`, `verified_session`, `session_from_request`,
`clear_session_cookie`, `fragment_redirect`, `_double_submit_verified`,
`chosen_landing`, `LANDING_PRECEDENCE` and `_ASSIGNED_ROLES_AT`.

## Done when

1. **The landings follow the door.** For the seeded two-hat person, the
   landings route at the launch door lists their instructor and leadership
   roles and no Care or Admin; at the web door it lists leadership, and Care
   or Admin if held, and never instructor or student.
2. **A switch re-checks.** A switch to a role the person holds at this door
   answers a new session in that role. A switch to a role they do not hold,
   or held only at the other door, is refused and issues nothing. A switch
   after the assignment was revoked (between listing and switching) is
   refused.
3. **The old session ends.** After a switch, the old token is refused with
   the expired-token 401 on every gated route kind (student, instructor,
   leadership, admin).
4. **One role per session.** No session issued by the switch carries two
   roles; a Care session issued by a switch reaches no leadership or
   instructor route, and a leadership session reaches no Care route.
5. **Logout ends the session.** After logout the token is refused, the cookie
   is cleared, and a second logout with the same token answers the same as
   the first without error.
6. **CSRF.** The switch and logout routes refuse a request without the
   double-submit token, over HTTP (MISTAKES entry 47).
7. **The first landing is unchanged.** A launch or web login with no switch
   lands where `LANDING_PRECEDENCE` sends it today (existing tests green,
   unchanged).
8. **Revocations purge.** A revoked id past its token's expiry is deleted by
   the purge; one before it is kept.
9. **The records match.** ADR 0202 is written and indexed. `PERSON_TABLES` is
   checked against the new table and the answer recorded in the pull request.
   The carried logout entry is named closed in the pull request, with
   back-channel logout pointed at E13.

## Shares files with

- `api/deps.py`: 01 and 02.
- `services/authz.py`: 01.
- `openapi.json`, `wire.gen.ts`: 05 to 09.

## MISTAKES entries to heed

3, 1, 2, 13 and 9, and 7, 38 and 47.

## Known traps

- **Entry 47.** A route's gate must live in its endpoint; drive each over HTTP.
- **Clock.** Expiry and purge read `services/clock.now`, so a moved
  development clock does not purge live revocations.

## Not in this ticket

- The switcher and logout controls in the app shell (11).
- Back-channel logout (E13, ruling 8).
