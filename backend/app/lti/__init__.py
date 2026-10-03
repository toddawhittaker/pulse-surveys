"""The LTI 1.3 tool side (SPEC §13, §7.3).

§13 gives this package five modules — `registration.py`, `launch.py`, `nrps.py`,
`ags.py` and a `platforms/` directory of adapters. Four of them are here:
`launch.py` (launch validation, E0-18), `registration.py` (platform and
deployment configuration and the tool's signing key, E1-05), `ags.py` (the grade
passback client, E3-04) and `platforms/` (the `PlatformProfile` seam, E3-04, with
the mock's profile as the only one written).

**`nrps.py` is not here, and the roster client is at
`app.services.roster_sync`.** E1-11 built it there and E3-04 looked at moving it;
the ruling was to leave it, on the ground that a working confidentiality-critical
client is not worth re-homing for symmetry alone. The two siblings therefore sit
in two places, which is a thing to know rather than a thing to discover — ADR 0132
records it and says what would change the answer.

A module with no caller is a guess at an interface, and §13 is a map of where
things go rather than a list of files that must exist.

**`pylti1p3` validates launches, and §13 names it.** E0-18 verified them with
PyJWT and docs/adr/0073 deferred the library to E1; E1-08 moved the launch door
onto it. `launch.py` runs `pylti1p3`'s `OIDCLogin` for the login leg, and its
`MessageLaunch` checks the token's format and its signature, against keys this
tool fetches itself; the steps the library would otherwise run in one call are
called one at a time so each refusal is classified by the check that failed.
The web door still verifies with PyJWT (`app.services.tokens`). The library is
also used outbound, by both service clients, for the client-credentials grant
that authorises every service call.
"""
