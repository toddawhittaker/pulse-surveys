"""Each platform's launch goes to its own authorization endpoint — E1-05, criterion 1.

The carried entry this closes is E0-18's security review, written up in
`docs/tickets/e1/carried-from-e0.md`: "`LTI_PLATFORM_AUTHORIZATION_ENDPOINT` is
process-wide and platforms are not". Platforms already resolve per issuer —
`app/lti/launch.py::registered_platform` looks up the one `lti_platform` row for
the `iss` in the login initiation and takes the client ID from that row — but the
address the browser was then sent to came from a single setting, the same string
for every platform in the process. With one registered platform the two agree.
With two they do not: a launch from platform B resolves B's registration and then
sends the browser to A's authorization endpoint, carrying B's client ID and this
tool's `state` and `nonce`.

The entry's done-when is exactly the first test below: **two platforms registered
at once, each launch round-tripping to its own authorization endpoint, proved by
a test that would fail if both went to one address.** One platform cannot pose
it. A tool that reads a setting, a constant in the source, or the first row in
the table passes every single-platform test ever written and fails here.

**The second test is the other half of the same decision.** The column is
nullable, because a registration written before it existed has no value for it
and a `NOT NULL` migration would need a fabricated backfill. NULL therefore means
"not stated", and the ticket refuses a launch from such a platform rather than
falling back to anything — the setting is deleted, not demoted to a default. A
fallback would be the carried entry re-opened under a different name: one address
standing in for every registration that does not carry its own.

**How the refusal is observed, and why it is not observed as an exception type.**
The work order names `LaunchRefusedError` as what `begin_a_launch` raises, and it
does not fix that function's signature — so a test calling it directly would be
inventing an interface (`docs/MISTAKES.md` entry 24's neighbourhood). What is
asserted instead is what a browser gets, which is the criterion anyway: a 4xx
with no `Location`, from a route that answered rather than raised. The
distinction between those two is real and is why `answered_by` exists here: a
`LaunchRefusedError` the door handles produces a refusal page, and any other
exception escapes the route entirely — fail-closed, still a defect, and
indistinguishable from a refusal to any test that only reads a status code.

**Nothing is mounted behind `app.state.http`.** A login initiation makes no
server-side fetch: it resolves a row and answers a redirect. So a door that
fetched anything here reaches no mock at all and says which address it wanted,
rather than being quietly served.
"""

from typing import Any
from urllib.parse import urlsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The mock platform's configuration surface, from `mock-lms/app/config.py`,
# spelled as `tests/integration/test_lti_launch_door.py` spells it.
MOCK_LMS_TOOL_LOGIN_URL_VARIABLE = "MOCK_LMS_TOOL_LOGIN_URL"
MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE = "MOCK_LMS_TOOL_LAUNCH_URL"
MOCK_LMS_ISSUER_VARIABLE = "MOCK_LMS_ISSUER"

# Two issuers, so that two platform instances are two registrations rather than
# one row written twice. `.invalid` is reserved by RFC 2606 and resolves nowhere,
# which is what these have to be: nothing in this module fetches either.
FIRST_ISSUER = "http://platform-one.invalid"
SECOND_ISSUER = "http://platform-two.invalid"

# The two browser-facing authorization endpoints, one per registration. **Chosen
# so that no implementation could arrive at either by accident**: neither is
# derivable from an issuer, from `PUBLIC_BASE_URL`, or from the other, so a
# redirect that lands on one of them can only have come from the row that carries
# it. They differ in host as well as in path, so a tool that got the origin from
# one registration and the path from another fails too.
FIRST_AUTHORIZATION_ENDPOINT = "http://authorize-one.invalid:9101/platform-one/authorize"
SECOND_AUTHORIZATION_ENDPOINT = "http://authorize-two.invalid:9202/platform-two/authorize"

# Where each platform publishes the key set a launch would be verified against.
# Registered because the column exists and a registration without one is not a
# registration; nothing here fetches it, because nothing here completes a launch.
FIRST_JWKS_URL = f"{FIRST_ISSUER}/.well-known/jwks.json"
SECOND_JWKS_URL = f"{SECOND_ISSUER}/.well-known/jwks.json"


def start_platform(mock_platforms: Any, door_contract: Any, issuer: str) -> Any:
    """One mock platform under `issuer`, posting its launch form at this tool."""
    return mock_platforms(
        {
            MOCK_LMS_ISSUER_VARIABLE: issuer,
            MOCK_LMS_TOOL_LOGIN_URL_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.lti_login}"
            ),
            MOCK_LMS_TOOL_LAUNCH_URL_VARIABLE: (
                f"{door_contract.public_base_url}{door_contract.lti_launch}"
            ),
        }
    )


def answered_by(deliver: Any, what: str) -> Any:
    """What the tool answered, or a failure saying it raised instead of answering.

    `tool_doors` builds its `TestClient` with `raise_server_exceptions` at the
    default, so an exception escaping a route arrives here rather than as a 500.
    That is a different outcome from a refusal and this module has to tell them
    apart: a refusal renders a page and clears what it set, while an escape gets
    the browser nothing and skips whatever the refusal path does on its way out.
    """
    try:
        return deliver()
    except Exception as failure:
        pytest.fail(
            f"The tool raised {type(failure).__name__}: {failure} rather than answering {what}. "
            "E1-05 refuses this launch with `LaunchRefusedError` inside `begin_a_launch`, which "
            "the login route turns into a refusal page; an exception that escapes the route is "
            "fail-closed and is still a defect, and it is not the refusal the ticket asks for."
        )


def without_query(url: str) -> str:
    """A redirect target with its query dropped: scheme, authority and path."""
    split = urlsplit(url)
    return f"{split.scheme}://{split.netloc}{split.path}"


def redirected_to(response: Any, purpose: str) -> str:
    """The `Location` of a redirect, or a failure saying what came back instead."""
    assert response.status_code in (302, 303, 307), (
        f"The tool answered {response.status_code} rather than a redirect when {purpose}. Body "
        f"begins {response.text[:300]!r}."
    )
    location = response.headers.get("location")
    assert location, (
        f"The tool answered {response.status_code} with no `Location` when {purpose}, so there is "
        "nowhere for a browser to go and no endpoint for this test to read."
    )
    return location


def test_each_registered_platform_is_sent_to_its_own_authorization_endpoint(
    mock_platforms: Any, door_contract: Any, register_platform: Any, tool_doors: Any
) -> None:
    """The carried entry's done-when, and it cannot be posed with one platform.

    Two platforms are registered at the same time and each one's own launch form
    is posted at `/lti/login`. Each redirect has to land on the endpoint that
    platform's *row* carries.

    **The mutation this kills, which is the whole ticket:** the endpoint read
    from anywhere that is not this registration — a setting, a constant, the
    first row in the table, or the row for some other issuer. Every one of those
    sends both launches to one address, and every one of them passes a suite that
    registers a single platform, which is what E0 had.

    **The near miss inside that mutation** is the reason both directions are
    asserted rather than only the positive. A door that resolved the right row
    and then took the endpoint off the wrong one satisfies "the first launch went
    to the first endpoint" half the time; requiring each redirect to be *not* the
    other platform's endpoint is what closes it.

    The two endpoints are asserted different first. Two rows that happened to
    carry one address would make every assertion below true of a tool that
    ignored the column entirely (`docs/MISTAKES.md` entry 3).

    **The registrations are written here rather than in a fixture**, so that a
    schema with no such column fails inside this test naming the column, rather
    than erroring in somebody's setup — a red and a broken test are read by
    different people. Nothing is mounted behind `app.state.http`: a login
    initiation resolves a row and answers a redirect, so a door that fetched
    anything reaches no mock and says which address it wanted.
    """
    first = start_platform(mock_platforms, door_contract, FIRST_ISSUER)
    second = start_platform(mock_platforms, door_contract, SECOND_ISSUER)
    register_platform(first.require_offers()[0], FIRST_JWKS_URL, FIRST_AUTHORIZATION_ENDPOINT)
    register_platform(second.require_offers()[0], SECOND_JWKS_URL, SECOND_AUTHORIZATION_ENDPOINT)
    tool = tool_doors({door_contract.settings["public_base_url"]: door_contract.public_base_url})

    assert FIRST_AUTHORIZATION_ENDPOINT != SECOND_AUTHORIZATION_ENDPOINT, (
        "The two registrations carry one authorization endpoint, so a tool that sent every launch "
        "to a single address would pass this test. They are constants at the head of this module."
    )

    first_location = redirected_to(
        tool.post(door_contract.lti_login, data=first.require_offers()[0].parameters),
        f"the platform at {FIRST_ISSUER} began a launch",
    )
    second_location = redirected_to(
        tool.post(door_contract.lti_login, data=second.require_offers()[0].parameters),
        f"the platform at {SECOND_ISSUER} began a launch",
    )

    assert without_query(first_location) == FIRST_AUTHORIZATION_ENDPOINT, (
        f"A launch from {FIRST_ISSUER} was redirected to {without_query(first_location)!r} and "
        f"that platform's registration carries {FIRST_AUTHORIZATION_ENDPOINT!r}. The other "
        f"registered platform carries {SECOND_AUTHORIZATION_ENDPOINT!r}. E1-05 makes the "
        "authorization endpoint a property of the registration precisely so that the row the "
        "issuer resolved to is the row the browser is sent by."
    )
    assert without_query(second_location) == SECOND_AUTHORIZATION_ENDPOINT, (
        f"A launch from {SECOND_ISSUER} was redirected to {without_query(second_location)!r} and "
        f"that platform's registration carries {SECOND_AUTHORIZATION_ENDPOINT!r}. If this is the "
        "*other* platform's endpoint, this is the carried entry's finding exactly: B's launch "
        "resolved B's registration and then went to A's address carrying B's client ID and this "
        "tool's `state` and `nonce`."
    )
    assert without_query(first_location) != without_query(second_location), (
        "Both launches were redirected to one address. Two platforms are registered here and each "
        "carries its own endpoint, so one address means the endpoint came from somewhere other "
        "than the registration — which is the process-wide setting this ticket deletes."
    )


def test_a_launch_from_a_platform_with_no_authorization_endpoint_is_refused(
    mock_platforms: Any, door_contract: Any, register_platform: Any, tool_doors: Any
) -> None:
    """A registration that states no endpoint is refused, not defaulted.

    The column is nullable because a row written before it existed carries no
    value for it, and NULL means "not stated". The decision is that such a launch
    is refused with `LaunchRefusedError` — an administrator completes the
    registration — rather than falling back to a process-wide address, because a
    fallback is the carried entry re-opened: one string standing in for every
    registration that does not carry its own.

    **The mutation this kills:** `platform.authorization_endpoint or
    settings.something`, and its cousin `or DEFAULT_AUTHORIZATION_ENDPOINT`. Both
    redirect here, and both leave the deleted setting alive under another name.

    **Both halves of the answer are asserted**, because a 4xx alone is satisfied
    by a tool that redirects *and* returns an error status: the absence of a
    `Location` is what says no browser was sent anywhere. Its pair is the test
    above, where the same door with the same platform and an endpoint in the row
    does redirect — without that, this would pass against a door that refuses
    every launch.
    """
    platform = start_platform(mock_platforms, door_contract, FIRST_ISSUER)
    register_platform(platform.require_offers()[0], FIRST_JWKS_URL, None)
    tool = tool_doors({door_contract.settings["public_base_url"]: door_contract.public_base_url})

    response = answered_by(
        lambda: tool.post(door_contract.lti_login, data=platform.require_offers()[0].parameters),
        "a login initiation from a platform whose registration states no authorization endpoint",
    )

    assert 400 <= response.status_code < 500, (
        f"The tool answered {response.status_code} to a login initiation from a platform whose "
        "registration carries no authorization endpoint. Body begins "
        f"{response.text[:300]!r}. E1-05: NULL means 'not stated', and a launch from such a "
        "registration is refused rather than sent to a default."
    )
    assert not response.headers.get("location"), (
        f"The tool sent the browser to {response.headers.get('location')!r} for a registration "
        "that states no authorization endpoint. Wherever that address came from, it is a "
        "process-wide fallback — which is the thing this ticket deletes rather than relocates."
    )
