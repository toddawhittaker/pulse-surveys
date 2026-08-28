# Batch C — addresses are judged as addresses — attempts

The composed fix of deferred E1-05 items 2 and 3 and E1-11 item 1, on
`e1/addresses-resolved-and-pinned`, cut from `epic/e1-entering-the-app`. The
tests are committed at 0033ff8 and red; nothing here may touch `tests/`.

## Attempt 1 — confirm the reds (2026-08-28)

Run in the main checkout at 0033ff8 with no code written, controls read first.

- `tests/unit/test_registration_address_constraints.py`: **77 failed, 122
  passed**, exit 1. Every one of the four controls at the foot of the module is
  green, so the reds are about the code rather than about the module.
- The three integration modules together: **11 failed, 18 passed**, exit 1, 24s.
  The failures are exactly the manifest's list — the two flush refusals, the
  unstated-environment session, the update refusal, the sync's resolution seam,
  the pin, the private-resolving hop, the second-host walk, and the three
  private-literal rows at the launch-time writer. Every named control (the wire's
  Host-header routing, the session stamp, the two ORM writes that must succeed,
  the development exemption) is green.

Worked: yes, as the starting measurement. 88 red cases, which is the number the
test commit's own message states.

## Attempt 2 — rule 5, the pin and the flush chokepoint

Written in the order the work order sets: the resolution and judgment in
`backend/app/models/lti.py`, then the pin in
`backend/app/services/roster_sync.py`, then the mapper events and the two
session stamps.

Decisions worth their own line, because a later reader will ask:

- **Rule 5 runs as a second pass over the registration's addresses**, after rules
  1 to 4 have judged all three. Per-address interleaving would also satisfy
  `docs/MISTAKES.md` entry 29 for each address on its own, but the second pass
  means a registration refused for a *spelling* costs no name lookup at all.
- **The refusal quotes neither the value nor the resolved addresses**, and does
  not name the host either. The house rule permits the host; a fetched address is
  chosen by the platform, so leaving it out costs nothing and keeps an
  attacker-supplied string out of a container log.
- **The exempt host is compared through `url_host` on both sides** — the address's
  host and `f"//{development_exempt_host}"` — so one normalisation answers for
  both ends rather than a second copy of the fold-and-strip (entry 13).
- **`PinnedResolutionAdapter` re-wraps rather than nests.** `sync_all_rosters`
  hands one session to every section in the institution, so a wrapper mounted per
  section would be a chain hundreds deep by the end of an hourly run. Mounting
  unwraps an adapter of its own type first.
- **TLS on a pinned request** is arranged with a per-hostname `HTTPAdapter` whose
  pool carries `server_hostname` and `assert_hostname` (urllib3 keys its pools on
  both, so nothing leaks between hosts). An inner adapter that is not a `requests`
  HTTP adapter opens no socket — that is the suite's in-process wire — and is
  delegated to unchanged.

Worked: `tests/unit/test_registration_address_constraints.py` **199 passed**,
and the three integration modules **29 passed**, both exit 0, first run after the
code was written. `ruff format --check`, `ruff check` clean on the four files.
