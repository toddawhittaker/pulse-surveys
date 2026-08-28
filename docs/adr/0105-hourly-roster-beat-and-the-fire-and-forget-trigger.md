# 0105 — Hourly roster beat, and the trigger that must not hold a launch

**Status:** Accepted
**Date:** 2026-08-28 (recording decisions built in E1-11; written at the E1
boundary after `adr-docs-completeness` flagged the gap)

## Context

SPEC §7.3 orders the roster pulled "on schedule and on launch (debounced)"
and says nothing about the cadence, the schedule type, or what a launch
trigger does when the queue is down. E1-11 decided all three in code, with
the reasoning in comments (`backend/app/jobs/schedules.py`,
`backend/app/services/roster_sync.py`, the debounce docstring) — the one
construction decision of the epic reasoned only there. Each is contestable;
this record moves the reasoning where decisions live.

## Decision

- **Hourly, as `crontab(minute="0")`, not a `timedelta`.** "Hourly" and
  "every 3600 seconds" are different schedules: a `timedelta` entry drifts
  with every beat restart, so which minute an institution's rosters are
  pulled in would depend on when beat last came up.
- **The walk is scheduled, not the per-section task.** `sync_rosters` visits
  every section carrying a stored roster address — that visit *is* the
  scheduled half's discovery. `sync_section_roster` exists for the launch
  trigger's one section.
- **The launch trigger is fire-and-forget.** It runs after the person is
  authenticated and the launch committed, asking for a background job whose
  absence costs at most an hour. So: `retry=False` (a down Redis fails at
  once instead of holding the request through kombu's retry policy),
  `ignore_result=True` (nothing consults a result nobody reads), the publish
  wrapped in `try` (a person must never fail to enter the product because a
  queue was unavailable), the failure logged at error level (MISTAKES 26's
  visibility), the caller told `False`.

## Alternatives rejected

- **A `timedelta` schedule** — drifts, above.
- **Scheduling the per-section task per section** — moves discovery into the
  scheduler, which then needs the section list beat cannot cheaply hold.
- **Letting the trigger retry or block** — turns queue availability into a
  launch dependency, inverting §7.3's priority (entry first, freshness
  second).

## Consequences

- A roster is at most an hour stale when the queue is healthy, and at most
  an hour late when a trigger's publish fails — the same bound, which is why
  fire-and-forget is safe.
- Every addressed section is called every hour with no term filter; the
  boundary review recorded the missing filter as carried
  (`docs/tickets/e1/boundary-review.md`, LOW table).
- The cadence is code, not a §6.3 knob; making it configurable is a decision
  for whoever first needs a different one.
