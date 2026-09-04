# E3-04 — The AGS client, and the mock's AGS routes start asking for a token

**ID:** E3-04
**Branch:** `e3/ags-client-and-mock-enforcement`
**Depends on:** E3-02
**Lane:** heavy
**Security-relevant:** yes, on both sides. The ticket writes a client that
signs assertions with the tool's key and posts grades to a platform, and it
turns on credential enforcement across the mock's AGS surface.
`backend/app/lti/`, `mock-lms/` and `tests/fixtures/` are all heavy-lane
rows.

## Context

This is the epic's pinch point: everything downstream of it waits, and it
carries two pieces of work that are one piece.

**The client.** No backend AGS code exists — `backend/app/lti/` holds
`launch.py`, `registration.py`, `replay_guard.py`, `in_flight.py` and
`fastapi_adapter.py`, and nothing else. The conformance shape it needs is
already solved next door in `backend/app/services/roster_sync.py`: the
service connector taking its transport as a constructor argument
(`roster_sync.py:389`), the no-redirect session (`roster_sync.py:427`), and
the pinned-host resolution adapter (`PinnedResolutionAdapter`, constructor at
`roster_sync.py:492`). The client copies that shape rather than inventing a
second one.

**The enforcement.** ADR 0099 records that the mock requires a
client-credentials token on NRPS and still does not on AGS, and it records
why: no AGS client existed to build the enforcement against. The carried
entry names the deadline as "paired with the first AGS client", and E1-06
made that promise once before about E1-11 and it was not kept. Putting both
halves in one ticket is what makes the pairing structural instead of stated.

The mock is ready for it. `mock-lms/app/ags.py` is a full AGS 2.0 platform —
line items, scores, and both readback routes — and its `ADVERTISED_SCOPES`
(`mock-lms/app/ags.py:92`) already lists the line-item scope, the line-item
read-only scope, the result read-only scope and the score scope.

Read first: ADR 0047 (the posted-score readback is a mock-only route),
ADR 0051 (a disagreeing `scoreMaximum` is refused rather than rescaled),
ADR 0052 (an equal score timestamp is accepted as a retry), ADR 0099 (the
enforcement boundary this ticket closes); SPEC §7.3, §9.1; `roster_sync.py`
whole; `mock-lms/app/ags.py`; `carried-from-e2.md`, both the AGS-token entry
and the superstring-scope entry.

## Scope

- The client: a connector on the roster sync's shape, a client-credentials
  token per scope, the registration resolved from the section's own
  deployment, the pinned-host adapter and the no-redirect session.
- Line item find-or-create for "Pulse Participation", a read-back after
  creation, and a paged read of the line-item container.
- Score posting against the line item's own maximum, with a 409 treated as
  stop-and-re-read and an equal timestamp treated as an accepted retry, per
  ADRs 0051 and 0052.
- An `ags_call` row per HTTP call, at E3-02's grain.
- Mock AGS enforcement: the AGS routes require a bearer token carrying the
  right scope per route, and the scope bounds that currently sit at the
  signature level move behind the credential, exactly as ADR 0099's
  consequences predict.
- The superstring-scope proof pair, discharging the carried entry.
- The `PlatformProfile` seam (§7.3) with exactly one profile written: the
  mock's.
- The worker log policy: no score, no ledger, no LMS user id in anything this
  code logs.

## Acceptance criteria

1. A score posts to the mock through the conformant flow — token requested
   for the score scope, assertion signed with the tool's key, posted to the
   line item's own scores address — and is readable back through the Result
   container.
2. The scores address is composed from the line item's id **as a URL**, not
   by string concatenation. Every id the mock mints carries a query string
   precisely so that `id + "/scores"` cannot be green-and-wrong, and a test
   drives an id with a query string and requires the composed address to be
   right.
3. A post whose `scoreMaximum` disagrees with the line item is refused rather
   than rescaled (ADR 0051), and a repeat of an identical post at an equal
   timestamp is accepted as a retry rather than doubled (ADR 0052) — both
   asserted against the mock.
4. A 409 stops the retry loop and triggers a re-read, and the test plants the
   409 rather than reasoning about it.
5. Every AGS route on the mock refuses an absent token, refuses a token
   carrying the wrong scope, and accepts a token carrying the right one —
   all three, per route.
6. **The superstring pair**: a token granted only the line-item read-only
   scope is refused by a route requiring the line-item scope, even though the
   granted string contains the required one as a substring. This is the
   carried entry's proof that the check is membership and not substring, and
   it becomes available for the first time in this ticket.
7. `ags_call` rows are written for successes and for failures, and carry no
   score value.
8. A `PlatformProfile` exists as a seam with one profile behind it, and a
   test proves the seam is actually consulted rather than being a file the
   code never reads (`docs/MISTAKES.md` entry 9).
9. No log line emitted by this code contains a score, a ledger line, or an
   LMS user id, asserted by a test over what the code logs rather than by
   reading it.

## Decisions this ticket settles

- **Where the client module lives.** SPEC §13 says `backend/app/lti/ags.py`,
  and the repository put the roster client at
  `backend/app/services/roster_sync.py` rather than at §13's `lti/nrps.py`.
  Two siblings in two places is the thing to avoid; whichever home wins, the
  reason is recorded, and if it departs from §13 the spec moves with it
  rather than being left to disagree.
- **Line-item identity and reconciliation.** Matching by label is the fragile
  choice. The rule to write down: match by the id Pulse stored, fall back to
  a container read, and decide explicitly what happens when both fail — the
  requirement being that a renamed or deleted line item never produces a
  second "Pulse Participation" column on the next run.
- **The retry and backoff policy**, and what an operator can see about a
  failing post.
- **How the mock's per-route scopes map to AGS routes**, recorded so E11's
  observability work and any later platform read the same table.
- **Which `PlatformProfile` adapters ship.** Ruled at breakdown, 2026-09-04:
  the mechanism plus the mock's profile only. Canvas, Moodle, D2L and
  Blackboard are in the README's deliberately-not-done list.

## Known traps

- **Turning on the mock's AGS token breaks existing suites by design.** Every
  AGS test that calls without a credential goes red at once, the page-bound
  signatures move behind the credential, and
  `refuse_an_unspecified_ags_token_flow`
  (`tests/fixtures/lti_services.py:633`) is the fixture hook that flips.
  Budget that churn inside this ticket rather than meeting it as a surprise,
  and remember that a ticket's new rule making an earlier ticket's tests
  unrunnable is `docs/MISTAKES.md` entry 22 — the repair is on the other side
  of the test wall, so the lane's test author and implementer split has to be
  planned for it before the build starts.
- **Query-string line-item ids.** The whole reason the mock mints them that
  way is that naive concatenation produces an address that looks right and is
  not. Assert the composed address against an id that has a query string; an
  id without one proves nothing.
- **The scope check's proof pair is only honest in one direction each way.**
  A test showing the right scope accepted proves the route can pass; a test
  showing an absent token refused proves the route can fail. Neither proves
  membership. The superstring pair is the one that does, and it needs both
  halves: the read-only token refused where the line-item scope is required,
  and the line-item token accepted there.
- **A guard that only ever reports absence cannot say which mechanisms it can
  see** (`docs/MISTAKES.md` entry 35). Give the enforcement tests a control
  that finds the credential on a request that certainly carries one.
- **`read_line_item` on the mock** (`mock-lms/app/main.py:735`) and
  `GET /mock/posted-scores` (`mock-lms/app/main.py:858`) exist for the test
  to read back through. Per ADR 0047 the posted-score route is a mock-only
  route and the backend never calls it; only a test does.

## Out of scope

- Creating the line item from a launch — E3-05.
- The job that decides when to post — E3-06.
- Any adapter for a real platform — the README's deliberately-not-done list.
- Views over `ags_call` — E11.
