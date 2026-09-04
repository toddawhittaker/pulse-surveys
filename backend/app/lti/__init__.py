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

**`pylti1p3` is not used for launch verification, and §13 names it.** E0-18
verifies launches with PyJWT instead; the decision, and what it costs, is in
docs/adr/0073. It *is* used outbound, by both service clients, for the
client-credentials grant that authorises every service call.
"""
