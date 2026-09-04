"""Per-platform quirk isolation (SPEC §7.3, SPEC §13), and the one way to reach it.

SPEC §7.3 puts each platform's deviations in a file of its own so that "nothing
leaks into domain logic", and this package is the whole of what domain logic sees:
one function, taking a registration's issuer and answering the profile to use.

**Resolved by issuer, because that is the only thing a tool reliably knows about
which software it is talking to.** A launch states `iss` and a registration is
looked up by it, so by the time any service call is made the issuer is in hand.
A platform nothing is written for gets the conformant profile rather than an
error: an institution running an LMS nobody has met should still get its grades
posted, by the book, and find out that the book was wrong from a refused post
rather than from a tool that would not try.

**One profile is written and it is the mock's** (ADR 0132). Canvas, Moodle, D2L
and Blackboard are named in SPEC §7.3 and are on E3's deliberately-not-done list,
because a quirk file written from a vendor's documentation against a platform
nobody here has posted a grade to is a guess recorded as a fact.

`profile_for` is the only public callable here on purpose, and it is imported by
name into `app.lti.ags` and called through that module's own global — so a test
substituting the seam can replace it wherever the client looks it up.
"""

from app.lti.platforms.base import CONFORMANT_PROFILE, PlatformProfile
from app.lti.platforms.mock import MOCK_ISSUER, MOCK_PROFILE

# Every platform a profile is written for, keyed by the issuer its registration
# carries. A mapping rather than a chain of `if`s, so adding a platform is adding
# a file and a line here and touching nothing that posts a grade.
#
# The keys are matched exactly. An issuer is an origin (`mock-lms/app/config.py`
# strips a trailing slash for the same reason), and a prefix or substring match
# would hand `https://canvas.instructure.com.evil.example` the profile of the
# platform it is impersonating.
PROFILES: dict[str, PlatformProfile] = {MOCK_ISSUER: MOCK_PROFILE}


def profile_for(issuer: str) -> PlatformProfile:
    """The profile for the platform registered under `issuer`, conformant by default.

    The whole of the registry. A caller passes the issuer off the registration it
    is about to sign an assertion with, and never a hostname, a display name or a
    URL it composed — those are three ways to reach the wrong entry and the issuer
    is the value the protocol itself keys on.
    """
    return PROFILES.get(issuer, CONFORMANT_PROFILE)
