"""The mock platform's profile: it deviates in nothing, and that is the point.

`mock-lms/` is a conformant LTI Advantage platform built to be built against
(SPEC §9.2), so its profile restates none of `base.py`'s values and overrides
none of them. What it is here for is that the registry has a written entry to
resolve, so the seam is exercised by the stack a developer actually runs rather
than only by a test that substitutes one.

**It is the only profile that ships.** Canvas, Moodle, D2L and Blackboard are on
E3's deliberately-not-done list: a quirk file written from a vendor's
documentation, against a platform nobody here has posted a grade to, is a guess
recorded as a fact. ADR 0132 records the ruling.
"""

from typing import Final

from app.lti.platforms.base import PlatformProfile

# The issuer `mock-lms` runs under in `docker-compose.yml` and in its own default
# (`mock-lms/app/config.py::DEFAULT_ISSUER`). A registration is looked up by
# issuer, so this is the key the mock's own launches arrive under; an operator who
# moves the mock to another origin registers it under that one and gets the
# conformant profile, which is the same profile.
MOCK_ISSUER: Final[str] = "http://mock-lms:8000"

MOCK_PROFILE: Final[PlatformProfile] = PlatformProfile()
