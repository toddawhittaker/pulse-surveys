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

## Attempt 3 — the whole suite, and the one regression it found

`pytest tests/unit tests/integration`: **1 failed, 1965 passed** in 12:00. The
failure is the reason the whole suite is run rather than the ticket's own
(`docs/MISTAKES.md` entry 41's corollary):
`test_demo_seed_script.py::test_the_seed_refuses_to_register_the_mock_outside_a_development_environment`.

Its *control* — the half that proves the refusal above it means something —
calls `seed_mock_platform` under a development configuration through a session
that `demo_session` in that module builds itself, and that session states no
environment. The flush chokepoint judged it as a deployment, exactly as designed,
and refused the mock's own loopback `authorization_endpoint`. `docs/MISTAKES.md`
entry 22's shape: a new rule making an earlier ticket's test unrunnable. Not
bumped — the entry did not stop this, the suite caught it.

The repair is not behind the test wall, which is why no dispute was written. The
seed's two registration writers already read the environment out of the
`configuration` mapping they are handed, and already call the address rules with
it; they now also state it on the session, through `state_the_environment`, with
`setdefault` so a caller that has already said where it is keeps saying it. That
is the same argument those writers already make for calling the address rules
again after `main` has checked: `main` is not the only way in.

The session-info key became a constant in `app.models.lti`
(`ENVIRONMENT_SESSION_KEY`), imported by `app.db` and `scripts/seed.py`, because
three spellings of one string with nothing comparing them is entry 13.

Worked: the seed module plus the four batch modules, **283 passed**, exit 0.
`mypy` clean after the adapter's `send` was given `BaseAdapter`'s own signature —
`(self, request, **kwargs)` is an incompatible override and mypy said so.

## Attempt 4 — the records, and the verification they were written against

Records last, after the code stopped moving. ADR 0101; a superseded-in-part
pointer at the top of ADR 0081's decision section naming the two paragraphs it
falsifies; the "four rules" claims in ADR 0091, `docs/adr/README.md`'s rows for
0081 and 0091, `org.py`'s roster-address comment and `provisioning.py`'s writer;
the three deferred entries; the two E2 hand-off entries. `.env.example` was read
rather than assumed: the change adds no configuration variable, so it needs no
line.

One claim in the ADR draft was wrong and was corrected before it was committed:
the sync's token request does *not* travel over a transport of `pylti1p3`'s own —
it goes through the same session the pinned adapter is mounted on, and is
unpinned because nothing ever judged its host at fetch time. The residue is the
same; the reason is not.

Verified, on the tree at the records commit:

- `pytest tests/unit tests/integration`: **1966 passed**, exit 0, 12:24.
- `pytest -m invariant`: **112 passed, 1854 deselected**, exit 0;
  `check_invariants.py` "112 invariant test(s) ran, none skipped, none failed";
  `check_invariant_assertions.py` "78 invariant-marked test(s) each assert
  something".
- `ruff check .`, `ruff format --check .` (220 files), `mypy`, `mypy
  mock-lms/app`, `mypy mock-idp/app`: all exit 0.
- No migration: a mapper event is not DDL, and no column, constraint or index
  moved.

## Attempt 5 — the battery's survivor, and the tree it was left in

The verifier's mutation battery ran against the four behaviour commits and one
mutation survived: `development_exempt_host=exempt_host` at the walk's per-URL
judgment, mutated to `None`. Every test stayed green, because the wire tests that
drive a hostile hop run under `deployment_settings`, where that argument is
ignored — and the one development test asserted only that something was *not*
resolved, which is even more true when nothing is judged at all. The test author
closed the pair in `ec0292e` with two tests on the development side: a hop that
resolves privately is refused **and the resolver is proved to have been asked
about the hostile host**, which is the fingerprint of rule 5 running; and a hop
that resolves publicly is walked, so the refusal cannot be satisfied by a stack
that refuses every second host.

**The battery left the mutation in the working tree.** `roster_sync.py` still
carried `development_exempt_host=None`, uncommitted, over the top of the correct
committed code — the hazard the memory note about mutating a shared checkout
describes. Restored with `git restore` (the correct version is committed at
`abb845e`, so nothing of mine was at risk in that restore), and verified: the
module is **14 passed**, exit 0, with no code change needed.

Then the kill was measured rather than assumed (`docs/MISTAKES.md` entries 9 and
16): the mutation re-applied by hand, the module run again — **2 failed, 12
passed**, and the two failures are exactly the two new tests — and the file
restored again. `git status` clean on `backend/`, `scripts/` and `docs/`
afterwards.

No code change was owed by this round; the tests were always about a case the
implementation already handled and nothing asserted.

## Attempt 6 — the fix round: two more embedded-IPv4 forms (2026-08-28)

A follow-up security finding: `_is_an_acceptable_resolved_address` unwrapped only
the IPv4-mapped form (`::ffff:0:0/96`, via `.ipv4_mapped`) before the `is_global`
test, so `64:ff9b::a9fe:a9fe` (NAT64 well-known, RFC 6052) and `::a9fe:a9fe`
(IPv4-compatible, RFC 4291) were judged at the wrapper — which `ipaddress` reports
`is_global` true — and accepted while reaching `169.254.169.254`.

Fix: a `_embedded_ipv4` helper returns the IPv4 an IPv6 address carries in its low
32 bits for all three forms, and the judgment unwraps through it. Both entries
(registration write and fetched address) share
`_is_an_acceptable_resolved_address`, so one change fixes both.

The boundary that took the care: the IPv4-compatible `::/96` contains `::`
(unspecified) and `::1` (loopback). Unwrapping `::1` to `0.0.0.1` would lose the
loopback identity ADR 0096's sidecar split turns on, so both are excluded by
`is_loopback`/`is_unspecified` guards — while `::7f00:1` (`::127.0.0.1`) is a
genuine embedded address and IS unwrapped to 127.0.0.1 (refused on the
browser-facing column). Not a blanket reject: `64:ff9b::8.8.8.8` unwraps to a
global v4 and stays accepted, which the boundary-acceptance test guards.

Verified with `ipaddress` first (all vectors classify as the tests claim), then:

- new tests + control (`-k "embedded or sit_where_this_module"`): 23 passed.
- the full unit address-rules module: 222 passed (199 before + 23 new), exit 0.
- the integration roster-sync refusal module: 24 passed (23 before + the nat64
  metadata hop), exit 0, 22s.
- `ruff format --check`, `ruff check`, `mypy`, `mypy mock-lms/app`, `mypy
  mock-idp/app`: all clean.

No `::1`/loopback or ADR 0096 case reddened — the exclusion held. No dispute.
Records: ADR 0101 consequences (two more forms + the custom-NAT64-prefix residual)
and the E1-11 deferred entry's Batch C paragraph.

Worked: yes.
