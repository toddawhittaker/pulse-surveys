# E2-04 — One clock service, and a development-only time control on `/dev`

**ID:** E2-04
**Branch:** `e2/dev-clock`
**Depends on:** nothing
**Lane:** heavy
**Security-relevant:** the override must be unreachable outside development —
same guard discipline as the `/dev` console itself (ADR 0079) and the seed
(ADR 0063). And faked time must never reach protocol validation: a movable
clock on nonce, state, or token expiry checks would open the replay window E1
closed.

## Context

Survey windows are wall-clock behavior (§3.1: opens Friday 18:00, closes
Sunday 23:59:59, institution timezone), and E2 has to be testable — including
*interactively*: Todd drives the stack and wants to see what a student sees on
a Friday evening without waiting for one. Decided with Todd 2026-08-31: a
clock service that all scheduling reads go through, with a development-only
override set from the existing `/dev` console and stored in the database so
the backend and the worker agree.

Today there is no clock abstraction. The scheduling-relevant "now" reads are
scattered direct calls: `backend/app/services/provisioning.py` (a
`datetime.now(ZoneInfo(settings.institution_timezone)).date()`),
`backend/app/services/roster_sync.py` (`_today(settings)`), and
`backend/app/services/authz.py` (the live-assignment date check). The LTI
launch door (`backend/app/lti/launch.py`) and the session module also read
real time — those are protocol time and stay real, deliberately.

Read first: SPEC §3.1; `backend/app/api/dev.py` and its guard
(`is_development`, exact-match on `settings.environment`, 404 outside
development); ADR 0079, ADR 0063; the three call sites above; MISTAKES
entry 40 (tests that read the process environment state what they run under).

## Scope

- A clock service (one module under `backend/app/services/`, §13) exposing
  the two questions the codebase actually asks: the current instant (UTC) and
  today's date in the institution timezone. Everything the *scheduling and
  visibility* logic asks about time goes through it: the three sites above
  migrate, and E2-06's window logic is written against it from the start.
- The development override: a single-row table holding a pretend "now"
  anchor paired with the real instant it was set at, so time keeps flowing
  from the point you set (an offset, not a freeze). The service applies the
  override **only when `is_development(settings)`** — in any other
  environment the row is dead weight even if present.
- `/dev` grows the control: set the pretend now, see the effective now, clear
  it. Same in-handler guard and 404 shape as the existing console route.
  The console's section table already shows derived dates; show the effective
  clock beside it so an overridden stack is never mistaken for a live one.
- An ADR: database-row dev clock, offset semantics, and the explicit list of
  clocks it does **not** touch (launch validation, session expiry, audit
  timestamps, `func.now()` column defaults). One column is called out by
  name so two tickets cannot each leave it to the other: `response`'s
  submission timestamp is *application-written through this service* (E2-08
  does the writing) — a dev-clock submission whose stored timestamp sits
  outside the window that accepted it would hand E3's participation formula
  a row that contradicts itself. The spec is silent and the choice is
  contestable; that is the ADR test.
- Tests: the override moves the service's answers in development and moves
  nothing outside it (both directions); the migrated call sites read the
  service (the sweep question: a new direct `datetime.now` in scheduling code
  is the thing reviews now look for — state it in the ADR rather than
  building a sweep nobody asked for).

## Acceptance criteria

1. The service exists, the three call sites read it, and E2-06 can be written
   against it.
2. In development, setting the pretend now from `/dev` changes what the
   backend and the worker both answer; clearing it returns them to real time
   — proven against the running stack, not only in-process.
3. Outside development the override is inert and the `/dev` control answers
   404 — asserted, not assumed (MISTAKES entry 2).
4. Launch validation, session expiry, and audit timestamps still read real
   time — pinned by a test that sets the override and watches a token's
   clock-skew check not move.

## Out of scope

- Faking time in the browser or the frontend bundle — the backend decides
  what is open; the page renders what the API answers.
- freezegun/time-machine as a test dependency — explicit values through the
  service make it unnecessary; adding a dependency needs a reason and none
  exists once the service is injectable.
- Any change to Celery beat's own schedule (the hourly sync fires on real
  time; what it *computes* uses the service).
