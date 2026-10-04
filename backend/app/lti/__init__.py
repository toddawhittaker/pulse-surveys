"""The LTI 1.3 tool side (SPEC §13, §7.3).

§13 draws this package as the modules that are here: `registration.py`
(platform and deployment configuration and the tool's signing key, E1-05),
`launch.py` (beginning a launch and validating the one that returns, E0-18 and
E1-08), `fastapi_adapter.py` (the FastAPI adapter `pylti1p3` does not ship),
`in_flight.py` and `replay_guard.py` (a launch handshake's server-side memory and
its single-use nonces, ADR 0089), `ags.py` (the grade passback client, E3-04) and
`platforms/` (the `PlatformProfile` seam, E3-04, with the mock's profile as the
only one written).

**The roster client is not here; it is `app.services.roster_sync`, and §13 draws
it there.** E1-11 built it there and E3-04 looked at moving it; the ruling was to
leave it, on the ground that a working confidentiality-critical client is not
worth re-homing for symmetry alone. The two service clients therefore sit in two
places, which is a thing to know rather than a thing to discover — ADR 0132
records it and says what would change the answer.

§13 also draws four more platform profiles (Canvas, Moodle, D2L, Blackboard) and
marks each "not built yet": each waits for a platform that launches against this
tool, because a profile with no caller is a guess at an interface.

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
