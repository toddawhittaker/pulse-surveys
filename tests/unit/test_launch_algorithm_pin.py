"""The launch door's algorithm pin, exercised in isolation — ADR 0073, ticket E1-08.

ADR 0073's closing condition, applied to the pylti1p3 adapter: "the algorithm
list stays a constant in code... The moment it is read from a token or from
configuration, the library's protection is gone." The implementer extracted
that pin into its own function, `app.lti.launch._refuse_unpinned_algorithm`,
which takes a decoded JWT header and raises `SignatureRefused` unless
`header["alg"]` is one of `LAUNCH_SIGNATURE_ALGORITHMS` (`("RS256",)`).

**Why this needs a unit test at all**, when `tests/integration/test_lti_launch_door.py`
already drives `alg_none` and `hs256_confusion` through the whole door: pylti1p3's
own key-matching refuses both *before* this pin is ever reached — an unknown `kid`
for `alg: none` (no signature to match a key against) and a JWK looked up under
`RS256` failing to verify an `HS256`-keyed token, both for reasons upstream of
the pin. Those integration tests prove the *door* refuses both shapes; neither
proves this specific function is what would refuse them if pylti1p3's own
checks were ever loosened or reordered. This module calls the pin directly, so
a mutation here is caught here rather than staying invisible behind a library
that happens to refuse the same input for an unrelated reason.
"""

from collections.abc import Mapping
from typing import Any

import pytest


def imported_launch_module() -> Any:
    """`app.lti.launch`, or a failure naming what this ticket says should be there."""
    try:
        import app.lti.launch as launch_module
    except ModuleNotFoundError as missing:
        pytest.fail(
            f"`app.lti.launch` does not import ({missing}). E1-08 rewrites this module onto "
            "pylti1p3, and the coordinator's brief puts `_refuse_unpinned_algorithm` and "
            "`SignatureRefused` there."
        )
    return launch_module


def pin(header: Mapping[str, Any]) -> None:
    """Call `_refuse_unpinned_algorithm` off a freshly imported `app.lti.launch`.

    Imported inside every call rather than once at module scope, matching this
    suite's own convention (`tests/unit/test_registration_address_constraints.py`
    and others) for a module that a collection-time import failure would
    otherwise take every test in this file down with it.
    """
    module = imported_launch_module()
    refuse = getattr(module, "_refuse_unpinned_algorithm", None)
    assert callable(refuse), (
        "`app.lti.launch` exposes no callable `_refuse_unpinned_algorithm` (it exposes "
        f"{sorted(name for name in vars(module) if not name.startswith('__'))}). The coordinator's "
        "brief names this exact function, extracted from the ADR-0073 algorithm pin."
    )
    return refuse(header)


def signature_refused_type() -> type[Exception]:
    """`app.lti.launch.SignatureRefused`, or a failure naming its absence."""
    module = imported_launch_module()
    found = getattr(module, "SignatureRefused", None)
    assert isinstance(found, type) and issubclass(found, Exception), (
        f"`app.lti.launch.SignatureRefused` is {found!r}, not an exception type. E1-08's plan "
        "names it as one of the `LaunchRefusedError` subclasses classifying a refusal."
    )
    return found


# ---------------------------------------------------------------------------
# The three refused shapes. Each is a boundary pair with the accepted case
# below: without that pair, a pin that raised unconditionally on *every*
# header — never reading `alg` at all — would pass all three of these.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header",
    [
        pytest.param({"alg": "none"}, id="alg-none-rfc7519-unsecured-jwt"),
        pytest.param({"alg": "HS256"}, id="alg-hs256-rs256-confusion-attack"),
        pytest.param({}, id="no-alg-member-at-all"),
    ],
)
def test_refuse_unpinned_algorithm_raises_for_an_unpinned_header(header: dict[str, Any]) -> None:
    """**Dies if the pin is a no-op**, and dies if it reads `alg` from anywhere
    other than the header it was handed — the three headers here disagree with
    the pin in three different ways (a forged value, a confused value, and an
    absent one), so a pin that checks the wrong thing or checks nothing fails
    at least one of them.
    """
    refused_type = signature_refused_type()

    with pytest.raises(refused_type):
        pin(header)


def test_refuse_unpinned_algorithm_accepts_the_pinned_rs256_header() -> None:
    """The near miss for the three cases above, and the control every one of them needs.

    Without this, a pin that raised `SignatureRefused` unconditionally — never
    actually reading `alg`, never actually comparing against
    `LAUNCH_SIGNATURE_ALGORITHMS` — would pass every test above while
    refusing every real launch this door is supposed to accept. A real
    launch's header carries more than `alg` (`kid`, `typ`); the extra members
    are included here so this also proves the pin looks at `alg` specifically
    rather than, say, the header's size or shape.
    """
    result = pin({"alg": "RS256", "kid": "e1-08-algorithm-pin-unit-test-key", "typ": "JWT"})

    assert result is None, (
        f"`_refuse_unpinned_algorithm` returned {result!r} for a header carrying the pinned "
        "`RS256`, rather than returning `None` (or raising, which this call would already have "
        "reported). A launch this door is supposed to accept must not be refused by its own "
        "algorithm pin."
    )
