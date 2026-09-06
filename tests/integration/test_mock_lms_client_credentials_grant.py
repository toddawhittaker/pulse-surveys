"""The mock platform's client-credentials grant, driven the way a tool drives one — E1-06.

E1-06 lands four things in one change, because a surface carrying some of them
"cannot be built against any better than one carrying none" — the carried entry
`docs/tickets/e1/carried-from-e0.md`, "The client-credentials grant, and the four
things that move with it". Three of the four are the platform's and are asserted
here: a `token_endpoint` in the OIDC discovery document, the AGS and NRPS scope
strings in `scopes_supported`, and `auth_token_url` in the `/registration`
document. The fourth is the tool's JWKS route and is next door, in
`tests/integration/test_the_tool_publishes_its_key_set.py`.

**Nothing here speaks `pylti1p3`, and that is criterion 2's own instruction.** The
library arrives with E1-08 and E1-11; this module builds the token request by hand
— form-encoded `grant_type`, `client_assertion_type`, `client_assertion`, `scope`
— so the platform's conformance is proven independently of the client that will
consume it. What shape a request takes is not this file's invention either: it is
the shape `ServiceConnector` posts, and every value in it is read off the platform
rather than transcribed. The token endpoint comes out of the discovery document,
the client id out of the launch form the platform publishes, and the audience out
of the token endpoint's own advertised URL.

**Every refusal is one difference from a request that works, and carries that
request with it.** A 400 is a 400: a case that got two things wrong at once is
satisfied by a platform that checks either, which is `docs/MISTAKES.md` entry 3 in
the shape this ticket is most exposed to. So each refusal test below posts a
request that must be *granted* first, in the same test against the same platform,
and then changes exactly one thing. The `jti` and `iat` differ between the two by
construction, because an assertion is single-use and a platform is entitled to say
so; nothing else does.

**Which error code means which refusal is settled** — RFC 6749 §5.2's vocabulary,
assigned in the E1-06 dispatch brief rather than in the ticket: `invalid_request`
where the request is missing something it must carry, `invalid_client` where the
assertion arrived and does not authenticate the client, `invalid_scope` where the
platform will not grant what was asked for. The ticket's reason for caring is in
its own scope section — "E1-11's client is only conformant if nonconformance is
distinguishable" — and a platform answering one code for all six is a platform
whose client cannot tell a clock problem from a key problem.

**The services did not begin requiring a token here**, which was E1-06's ruling and
not an omission: enforcement paired with the conformant client of each service.
**Both pairings have since landed.** E1-11's fix round put the roster behind the
membership scope; E3-04 built the first AGS client and put line items, scores and
results behind the four AGS scopes in the same ticket. Those refusals are asserted
in `test_mock_lms_nrps_requires_a_token.py` and
`test_mock_lms_ags_requires_a_token.py` rather than here — this module's subject is
the endpoint that grants a token, not the services that check one.
`MockPlatform.refuse_an_unspecified_ags_token_flow`, which reported a 401 from
either service as a gap in a ticket, is deleted: there is no service left whose
refusal is a gap.

What the conformance test at the foot of this module asserts is unchanged and is
the whole sequence completing — token requested with a tool-signed assertion, token
attached, container returned — which is the carried entry's own definition of done.

**Why this module still builds its own token request by hand.** Every other suite
that needs a credential now goes through one helper,
`tests/fixtures/client_credentials.py::access_token_granted_to`, reached as
`MockPlatform.service_token` (`docs/MISTAKES.md` entry 13). This module is the one
that does not, deliberately: the *shape* of the form and the code each malformed one
is refused with are its subject, so a conformance test driven through that helper
would be checking the helper against itself (`docs/MISTAKES.md` entry 19).

**How the platform is told what the tool's key is.** Through one seam, described
in `tests/fixtures/client_credentials.py`, which pins an interface the ticket
leaves open and says so. `test_the_platform_fetches_the_tools_key_set_when_it_
verifies_an_assertion` is what keeps that from being an assumption.
"""

import base64
import time
from typing import Any

import pytest

pytestmark = pytest.mark.lti

# `mock_platforms`, `tool_key_pair`, `serve_key_set` and `claims_for_an_assertion`
# come from `tests/fixtures/` and are reached as fixtures rather than imported, for
# the reason `test_mock_lms_nrps_roster.py` gives: an import of a fixtures module
# by name depends on where pytest put `tests/` on `sys.path`, and an import error
# is not a red.

# The OAuth 2.0 client-credentials grant, spelled as RFC 6749 §4.4 spells it, and
# the assertion profile RFC 7523 §2.2 defines for presenting a JWT as the client's
# own credential. Specification constants; a platform that accepts some other
# spelling is one no conformant client reaches.
CLIENT_CREDENTIALS_GRANT = "client_credentials"
JWT_BEARER_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

# RFC 6749 §5.2's error codes, the three this endpoint can answer with. The
# mapping from case to code is the dispatch brief's, recorded in this module's
# docstring; the *strings* are the RFC's.
INVALID_REQUEST = "invalid_request"
INVALID_CLIENT = "invalid_client"
INVALID_SCOPE = "invalid_scope"

# RFC 6749 §5.2's fourth code, and the one E1-11 adds two refusals under.
# **Settled by E1-11's work order (D12)** for both of the deferred E1-06 items it
# closes: a replayed `jti`, and an `exp` beyond the platform's own clock plus the
# stated allowance. `invalid_grant` rather than `invalid_client` because in each
# case the assertion authenticates the client perfectly and the *grant* it
# presents is one this endpoint will not honour — a distinction E1-11's client
# needs, since one of them means "mint a fresh assertion" and the other means
# "your clock is wrong".
INVALID_GRANT = "invalid_grant"

# The skew the platform allows beyond its own clock when it judges an `exp`.
# **Settled at 30 seconds by E1-11's work order (D12)**: "`exp` further than now +
# 300s + 30s skew → 400 `invalid_grant`; the 30s skew is the recorded allowance".
# It is the allowance the wall-clock clamp needs in order not to refuse an honest
# tool whose clock is a little fast, which ADR 0084's consequences already warn
# about ("a tool whose clock is more than five minutes fast is refused here").
ASSERTION_SKEW_ALLOWANCE_SECONDS = 30

# How long a `client_assertion` may live, in seconds. **Settled at 300 by the
# E1-06 dispatch brief**, which the ticket asks for in as many words: "an
# assertion with no `exp` or one longer-lived than the short bound the mock
# enforces (minutes, not hours; the exact bound is the builder's, asserted in a
# test)". Asserted as a boundary pair below — 300 accepted, 301 refused — because
# a bound tested from one side only is satisfied by a platform with no bound at
# all, or by one that refuses everything.
ASSERTION_LIFETIME_BOUND_SECONDS = 300

# How far past the wall-clock line the refused half of that clamp's pair is dated.
# **This suite's choice, and it is a repair to a flake rather than part of the
# contract**, so it is named here with what it buys and what it costs rather than
# left as a magic `+ 1`.
#
# The clamp compares the assertion's `exp` against **the platform's** clock at the
# moment it reads it, and this test computes `exp` from **its own** read some
# milliseconds earlier — signing an assertion, posting it, letting the platform
# fetch a key set and verify a signature all happen in between. `int(time.time())`
# truncates downward, which costs up to another second. So the two clocks differ by
# a small positive amount, and an `exp` exactly one second past the line lands back
# inside it whenever that amount reaches a second: measured as a real failure in a
# combined run, passing when the module ran alone.
#
# **What five seconds buys**: the refusal is attributable to the clamp under any
# drift a loaded run plausibly produces. **What it costs**: the line is pinned to
# five seconds rather than to one, so a platform whose clamp sat anywhere in
# [330, 335) would pass both halves. Against a line at 330 seconds built out of a
# 300-second bound and a 30-second allowance, that is a resolution the numbers do
# not depend on. The *accepted* half is deliberately not widened and still sits
# exactly on the line, because drift moves it the safe way — a later platform clock
# raises the ceiling — so that half stays as tight as it ever was.
WALL_CLOCK_DRIFT_MARGIN_SECONDS = 5

# The scopes a token may be requested for. **Specification constants, not this
# suite's choice**, and the same strings `test_mock_lms_ags_line_items_and_scores.py`
# quotes for AGS: a tool asks its token endpoint for the exact strings the service
# claims name, so a platform advertising a scope of its own devising grants tokens
# for a scope no client will ever ask about.
AGS_LINE_ITEM_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
AGS_SCORE_SCOPE = "https://purl.imsglobal.org/spec/lti-ags/scope/score"
NRPS_MEMBERSHIP_SCOPE = "https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly"

# The scope OIDC itself defines, which the launch flow already uses and which
# `scopes_supported` carries today. Named separately from the three above because
# it is the one that must **survive**: a platform that replaced its scope list
# rather than extending it would pass every service-scope assertion below and
# break the launch it already serves.
OPENID_SCOPE = "openid"

# A scope no service on this platform serves. **This suite's own string**, from a
# domain RFC 2606 reserves, and it is deliberately not a real-but-unused IMS scope
# — `…/scope/result.readonly` would be a plausible thing for the mock to advertise,
# and a refusal test whose scope the platform legitimately grants is a test that
# reports a defect where there is none. Asserted absent from `scopes_supported`
# before it is used, so this cannot quietly become an advertised one.
UNADVERTISED_SCOPE = "http://pulse-tests.invalid/scope/no-service-here-serves-this"

# The registration document's key for the token endpoint. **The `lti_platform`
# column name E1-05 added**, not the protocol's `token_endpoint`, because ADR 0036
# keys that document by column name so that "paste it into the table in one step"
# stays literal.
AUTH_TOKEN_URL_KEY = "auth_token_url"  # noqa: S105 - a column name, not a credential

# The media type an NRPS membership container is asked for, as NRPS 2.0 spells it.
NRPS_MEDIA_TYPE = "application/vnd.ims.lti-nrps.v2.membershipcontainer+json"


# ---------------------------------------------------------------------------
# Reading the platform: nothing below transcribes a URL or an identifier.
# ---------------------------------------------------------------------------


def discovery_of(platform: Any) -> dict[str, Any]:
    """The platform's OIDC discovery document, or a failure saying it serves none."""
    document = platform.discovery()
    if not isinstance(document, dict) or not document:
        pytest.fail(
            "The mock platform serves no OIDC discovery document, so there is nothing here to "
            "read a token endpoint or a scope list out of. E0-14 serves one at "
            "`/.well-known/openid-configuration` and E1-06 adds `token_endpoint` and the service "
            "scopes to it — parts 1 and 2 of the four the carried entry moves together."
        )
    return document


def token_endpoint_of(platform: Any) -> str:
    """Where this platform issues access tokens, per its own discovery document.

    Read from the document rather than from a path this file knows, which is the
    rule the whole `MockPlatform` driver is built on: a tool learns a platform's
    endpoints from what it publishes, so a mock serving a perfectly good token
    endpoint at a fixed URL it advertises nowhere is a mock `pylti1p3` cannot use.
    """
    document = discovery_of(platform)
    advertised = document.get("token_endpoint")
    if not isinstance(advertised, str) or not advertised:
        pytest.fail(
            f"The discovery document advertises no `token_endpoint` (it carries "
            f"{sorted(document)}). That is part 1 of E1-06's four, and without it a tool has "
            "nowhere to ask for an access token — `ServiceConnector` issues no NRPS and no AGS "
            "request at all without one, whatever else the platform serves."
        )
    return advertised


def advertised_scopes(platform: Any) -> list[str]:
    """Every scope the platform says a token may be requested for."""
    document = discovery_of(platform)
    scopes = document.get("scopes_supported")
    if not isinstance(scopes, list) or not all(isinstance(scope, str) for scope in scopes):
        pytest.fail(
            f"The discovery document's `scopes_supported` is {scopes!r} rather than a list of "
            "strings (the document carries "
            f"{sorted(document)}). OpenID Connect Discovery 1.0 §3 makes it a JSON array of "
            "scope values, and a tool asks its token endpoint for the exact strings it finds "
            "there."
        )
    return list(scopes)


def client_id_of(platform: Any) -> str:
    """The client id this platform registered for the tool.

    Off the launch form, which is the OIDC third-party-initiated login request and
    the one place a platform announces itself — the same source
    `tests/fixtures/doors.py` builds a registration from. A `client_assertion` is
    the tool speaking about itself, so `iss` and `sub` are this value, and a
    platform resolves which registration the assertion belongs to from it.
    """
    offer = platform.require_offers()[0]
    value = offer.parameters.get("client_id")
    if not isinstance(value, str) or not value:
        pytest.fail(
            f"The mock platform's launch form publishes no `client_id` (it publishes "
            f"{sorted(offer.parameters)}). That is the value a `client_assertion`'s `iss` and "
            "`sub` carry, so without it there is no assertion to build."
        )
    return value


def token_request(assertion: str | None, scope: str) -> dict[str, str]:
    """The form body `ServiceConnector` posts to a platform's token endpoint.

    `assertion` may be `None`, which posts the body **without** a
    `client_assertion` member rather than with an empty one. A missing parameter
    and an empty one are two different requests, and the missing one is the case a
    fail-open check matches.
    """
    body = {
        "grant_type": CLIENT_CREDENTIALS_GRANT,
        "client_assertion_type": JWT_BEARER_ASSERTION_TYPE,
        "scope": scope,
    }
    if assertion is not None:
        body["client_assertion"] = assertion
    return body


def post_token_request(platform: Any, url: str, body: dict[str, str]) -> Any:
    """Post one form-encoded token request and hand back the response, asserting nothing."""
    return platform.client.post(platform.local(url), data=body)


def json_body(response: Any, subject: str) -> Any:
    """`response`'s body as JSON, or a failure quoting what arrived instead.

    A token endpoint that answers HTML — a stack trace, a 404 page, a redirect to
    a login form — makes `.json()` raise, and an exception raised inside a helper
    reads as a broken test rather than as the finding it is: this endpoint does
    not speak the protocol. RFC 6749 §5.1 and §5.2 both make the body JSON.
    """
    try:
        return response.json()
    except ValueError:
        pytest.fail(
            f"{subject} answered {response.status_code} with a body that is not JSON. RFC 6749 "
            "makes both the token response and the error response JSON objects, so a client has "
            f"nothing to read here at all. Body begins {response.text[:300]!r}."
        )


def rsa_public_key_from(jwk: dict[str, Any]) -> Any:
    """The `cryptography` public key a JWK's `n` and `e` describe.

    Used only by the two controls at the foot of this module, which verify what
    this suite signs. Written out of RFC 7518 §6.3 — base64url, big-endian, no
    padding — rather than through a library's JWK loader, because a loader that
    round-trips this suite's own encoding mistake would agree with it.
    """
    from cryptography.hazmat.primitives.asymmetric import rsa

    def decoded(value: str) -> int:
        padded = value + "=" * (-len(value) % 4)
        return int.from_bytes(base64.urlsafe_b64decode(padded), "big")

    return rsa.RSAPublicNumbers(decoded(jwk["e"]), decoded(jwk["n"])).public_key()


def granted(platform: Any, url: str, body: dict[str, str], subject: str) -> dict[str, Any]:
    """Post a token request that must succeed, and hand back what the platform answered.

    Every refusal test calls this first with a request that differs from its own in
    exactly one place. Without it a refusal below could be the platform refusing
    every request it is sent — a token endpoint that answers 400 unconditionally
    passes all six refusal tests and grants nothing (`docs/MISTAKES.md` entry 3).
    """
    response = post_token_request(platform, url, body)
    assert response.status_code == 200, (
        f"{subject} answered {response.status_code} rather than 200, so the request this test "
        "poses its refusal against does not itself work and the refusal would say nothing. Body "
        f"begins {response.text[:300]!r}."
    )
    answered = json_body(response, subject)
    assert isinstance(answered, dict), (
        f"{subject} answered {answered!r}, which is not an OAuth 2.0 access token response. "
        "RFC 6749 §5.1 makes it a JSON object carrying `access_token`, `token_type` and "
        "`expires_in`."
    )
    return answered


def refused(
    platform: Any, url: str, body: dict[str, str], code: str, subject: str, control: str
) -> None:
    """Post a token request that must be refused, with the RFC 6749 §5.2 code that says why.

    The code is asserted rather than the status alone. E1-06's scope makes the
    refusals distinguishable on purpose — "E1-11's client is only conformant if
    nonconformance is distinguishable" — and a platform answering one code for
    every refusal satisfies a bare `status_code == 400` on all six.

    **400 rather than 401, including for `invalid_client`.** RFC 6749 §5.2 makes
    400 the status for a refused token request and carves out exactly one
    exception: a client that "attempted to authenticate via the `Authorization`
    request header field" MUST be answered 401. Nothing here does — the client
    authenticates with a `client_assertion` in the form body, which is RFC 7523's
    profile — so the exception does not apply and 400 is what the RFC asks for.
    """
    response = post_token_request(platform, url, body)
    assert response.status_code == 400, (
        f"{subject} answered {response.status_code}, and RFC 6749 §5.2 answers a refused token "
        "request with 400 — its 401 clause is scoped to a client authenticating through the "
        "`Authorization` header, which a `client_assertion` in the body is not. "
        f"{control} Body begins {response.text[:300]!r}."
    )
    answered = json_body(response, subject)
    assert isinstance(answered, dict), (
        f"{subject} was refused with the body {answered!r}, which is not an OAuth 2.0 error "
        "response. RFC 6749 §5.2 makes it a JSON object whose `error` member names the reason."
    )
    assert answered.get("error") == code, (
        f"{subject} was refused with `error` {answered.get('error')!r} rather than {code!r} "
        f"(the whole body: {answered!r}). {control} The codes are what make a nonconformant "
        "client's failure diagnosable: E1-11 has to tell a clock problem from a key problem from "
        "a scope it was never granted, and one code for every refusal tells it none of the three."
    )


# ---------------------------------------------------------------------------
# The platform, told what the tool's key set is.
# ---------------------------------------------------------------------------


@pytest.fixture
def tool_key_set(tool_key_pair: Any, serve_key_set: Any) -> Any:
    """The tool's published key set, served to whatever address the platform fetches."""
    return serve_key_set(tool_key_pair.key_set())


@pytest.fixture
def platform(mock_platforms: Any, tool_key_set: Any) -> Any:
    """One mock platform that can reach the tool's key set.

    `tests/fixtures/client_credentials.py` says what that seam pins and what it
    leaves to the implementer.
    """
    return mock_platforms(None, tool_key_set)


@pytest.fixture
def token_url(platform: Any) -> str:
    """The token endpoint this platform advertises, absolute, as a tool would store it."""
    return token_endpoint_of(platform)


@pytest.fixture
def client_id(platform: Any) -> str:
    """The client id the platform registered for the tool."""
    return client_id_of(platform)


# ---------------------------------------------------------------------------
# Part 1 — the token endpoint is advertised, and it is served.
# ---------------------------------------------------------------------------


def test_the_discovery_document_advertises_a_token_endpoint_the_platform_serves(
    platform: Any,
) -> None:
    """Part 1 of the four, and ADR 0036's rule that nothing is advertised unless it is served.

    **The mutations this kills.** A discovery document with no `token_endpoint`,
    which is HEAD and which leaves `ServiceConnector` unable to make a single
    call. A relative URL, which is a URL no tool can resolve: the document is
    fetched from a platform and its members are addresses, so `"/token"` reaches
    whatever host the tool itself is on. And a `token_endpoint` advertised at a
    path the application declares no route for — ADR 0036's own words, "an
    advertised endpoint that answers nothing is worse than an absent one: it fails
    at the point of use, in a tool, with a 404 that reads as the tool's bug".

    The route is required to accept `POST`, because RFC 6749 §3.2 makes the token
    endpoint a `POST`, and a platform that declared it for `GET` alone would
    advertise an address every conformant client is refused at.
    """
    advertised = token_endpoint_of(platform)
    path = platform.local(advertised)

    assert advertised.startswith(("http://", "https://")), (
        f"The discovery document advertises `token_endpoint` as {advertised!r}, which is not an "
        "absolute URL. A discovery document is fetched from the platform and read by a tool "
        "somewhere else entirely, so a relative address names a path on the *tool*."
    )
    assert path in platform.paths("POST"), (
        f"The platform advertises a token endpoint at {advertised!r} — path {path!r} — and "
        f"declares no `POST` route there. It declares {platform.paths('POST')}. ADR 0036: no "
        "endpoint here is advertised unless it is served, because an advertised endpoint that "
        "answers nothing fails at the point of use, inside a tool, as a 404 that reads as the "
        "tool's bug. RFC 6749 §3.2 makes the token endpoint a `POST`."
    )


# ---------------------------------------------------------------------------
# Part 2 — the scopes a service token can be requested for.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scope",
    [
        pytest.param(OPENID_SCOPE, id="openid"),
        pytest.param(AGS_LINE_ITEM_SCOPE, id="ags-lineitem"),
        pytest.param(AGS_SCORE_SCOPE, id="ags-score"),
        pytest.param(NRPS_MEMBERSHIP_SCOPE, id="nrps-contextmembership-readonly"),
    ],
)
def test_the_discovery_document_advertises_the_scopes_a_service_token_is_asked_for(
    platform: Any, scope: str
) -> None:
    """Part 2 of the four: `scopes_supported` names every scope a service claim names.

    **Which parameter kills what.** `openid` kills a change that *replaced* the
    scope list rather than extending it — the launch flow already asks for that
    scope, so a platform that swapped it for the service scopes breaks the door it
    already serves and every other case here stays green. The two AGS strings kill
    a list that carries NRPS alone, and the NRPS string a list that carries AGS
    alone; the carried entry moves them together because a tool asks for the exact
    strings the service claims carry, so a platform advertising three of the four
    is one no token can be requested from for the fourth.

    The strings are the specifications' and are transcribed here the way
    `test_mock_lms_ags_line_items_and_scores.py` transcribes the AGS pair — a
    platform advertising a scope of its own devising advertises one nothing will
    ever ask for.
    """
    advertised = advertised_scopes(platform)
    assert scope in advertised, (
        f"The platform advertises {advertised!r} and not {scope!r}. A tool requests an access "
        "token for the exact scope string the service claim names, so a platform that does not "
        "advertise it is one that service's token cannot be requested from — which is the state "
        "at HEAD, where the list is `['openid']`, and the reason the carried entry refuses to let "
        "these parts land separately: 'a token endpoint with no scopes, or scopes with no "
        "`auth_token_url`, still leaves `ServiceConnector` unable to make a single call, and it "
        "looks finished from a discovery document'."
    )


# ---------------------------------------------------------------------------
# Part 3 — the registration document, keyed by column name.
# ---------------------------------------------------------------------------


def test_the_registration_document_states_the_token_endpoint_under_its_column_name(
    platform: Any, token_url: str
) -> None:
    """Part 3 of the four: `auth_token_url` in `/registration`, spelled as the column is.

    ADR 0036 keys that document by `lti_platform`'s column names rather than by
    the protocol's terms — `jwks_url` and not `jwks_uri` — because its audience is
    somebody filling in a row and "one step" should not include translating
    between two vocabularies. E1-05 added the column; this is the half that makes
    pasting it literal.

    **The mutations this kills:** the key absent, which is HEAD; the key present
    under the protocol's spelling `token_endpoint`, which is the natural thing to
    write and which no column takes; and a value that disagrees with what the
    discovery document advertises, which registers an address the platform does
    not issue tokens at.

    The document is found by what its path is named after rather than transcribed,
    the way every other address in this suite is.
    """
    path = platform.path_named_after(
        ("registration",), "publishes the platform's registration values (ADR 0036)"
    )
    response = platform.client.get(path)
    assert response.status_code == 200, (
        f"`GET {path}` answered {response.status_code} rather than 200. ADR 0036 makes the "
        f"registration a JSON document a developer pastes into `lti_platform`. Body begins "
        f"{response.text[:200]!r}."
    )
    document = response.json()
    assert isinstance(document, dict), (
        f"`GET {path}` served {document!r}, which is not a registration document. ADR 0036 makes "
        "it a JSON object whose keys are the column names the values go into."
    )

    assert AUTH_TOKEN_URL_KEY in document, (
        f"The registration document carries {sorted(document)} and no `{AUTH_TOKEN_URL_KEY}`. "
        "That is E1-06's part 3, and its spelling is the point: ADR 0036 keys this document by "
        "`lti_platform`'s column names, so a `token_endpoint` member here would be the protocol's "
        "vocabulary in a document whose whole purpose is the table's."
    )
    assert document[AUTH_TOKEN_URL_KEY] == token_url, (
        f"The registration document states `{AUTH_TOKEN_URL_KEY}` as "
        f"{document[AUTH_TOKEN_URL_KEY]!r} and the discovery document advertises the token "
        f"endpoint at {token_url!r}. A developer registering this platform would store an address "
        "the platform does not issue tokens at, and the failure arrives much later as a token "
        "request that returns something other than a token."
    )


# ---------------------------------------------------------------------------
# The grant itself.
# ---------------------------------------------------------------------------


def test_a_client_credentials_grant_answers_a_bearer_access_token(
    platform: Any, token_url: str, client_id: str, tool_key_pair: Any, claims_for_an_assertion: Any
) -> None:
    """The happy path, and the shape RFC 6749 §5.1 requires of it.

    **The mutations this kills.** No token endpoint at all, which is HEAD. A
    response carrying an `access_token` and no `token_type`, which `pylti1p3`
    reads and then presents as a header it cannot build. `expires_in` as a string
    — every JSON-shaped near miss of an integer, `"3600"`, is accepted by a client
    that never does arithmetic on it and refused by one that does. And a
    `token_type` other than `Bearer`, which decides the `Authorization` header
    every subsequent service call carries.

    `expires_in` is asserted positive as well as integral, because a token that
    has already expired when it is issued is a token no client can use twice and
    the arithmetic that produces it — subtracting where it should add — is a
    one-character mistake.
    """
    claims = claims_for_an_assertion(client_id, token_url)
    answered = granted(
        platform,
        token_url,
        token_request(tool_key_pair.sign(claims), NRPS_MEMBERSHIP_SCOPE),
        "A well-formed client-credentials grant",
    )

    access_token = answered.get("access_token")
    assert isinstance(access_token, str) and access_token, (
        f"The token response carries `access_token` {access_token!r}. RFC 6749 §5.1 makes it "
        "REQUIRED and a string; an empty one is a credential a client will present and every "
        "service will refuse."
    )
    token_type = answered.get("token_type")
    assert isinstance(token_type, str) and token_type.lower() == "bearer", (
        f"The token response carries `token_type` {token_type!r} rather than `Bearer`. That value "
        "decides the `Authorization` header every service call afterwards carries, and a client "
        "reading anything else does not know how to present the token it was just given."
    )
    expires_in = answered.get("expires_in")
    assert isinstance(expires_in, int) and not isinstance(expires_in, bool) and expires_in > 0, (
        f"The token response carries `expires_in` {expires_in!r}. RFC 6749 §5.1 makes it the "
        "lifetime in seconds as a number, and a client caches a token against it — a string is a "
        "near miss every client that does no arithmetic accepts, and a value at or below zero is "
        "a token that is stale when it arrives."
    )
    assert NRPS_MEMBERSHIP_SCOPE in str(answered.get("scope", "")).split(), (
        f"A token was requested for {NRPS_MEMBERSHIP_SCOPE!r} and granted with `scope` "
        f"{answered.get('scope')!r}. RFC 6749 §5.1 requires the scope to be stated when it "
        "differs from what was asked for, and a client that asked for one thing and was silently "
        "granted another discovers it at the service rather than here."
    )


def test_the_platform_fetches_the_tools_key_set_when_it_verifies_an_assertion(
    platform: Any,
    token_url: str,
    client_id: str,
    tool_key_pair: Any,
    tool_key_set: Any,
    claims_for_an_assertion: Any,
) -> None:
    """Part 4's platform half: the assertion is checked against a key set that was fetched.

    The `client_assertion` is signed by the **tool** and the platform holds no
    copy of the tool's key, so verifying it means fetching the tool's published
    key set. A platform that granted tokens without fetching anything is one that
    trusts whatever arrives — and every accepted twin in this module would stay
    green, because they all sign with the key the platform was supposed to fetch.

    **The mutation this kills:** a token endpoint that decodes the assertion and
    does not verify it. That is the cheapest implementation, it grants tokens
    correctly for every well-formed request, and the only test that can see it is
    one that asks whether the key set was read.

    **This is also where the seam these tests pin is asserted rather than
    assumed.** `tests/fixtures/client_credentials.py` installs the key set on the
    mock's `app.state.http`, the way `tool_doors` installs the tool's; if the
    platform reaches the tool's key set some other way, this is the test that says
    so by name, and that fixture is the one place it changes.
    """
    claims = claims_for_an_assertion(client_id, token_url)
    granted(
        platform,
        token_url,
        token_request(tool_key_pair.sign(claims), NRPS_MEMBERSHIP_SCOPE),
        "A well-formed client-credentials grant",
    )

    assert tool_key_set.requested, (
        "The platform granted an access token without fetching the tool's key set. The "
        "`client_assertion` is signed by the tool and the platform holds no copy of that key, so "
        "a grant that fetched nothing verified nothing — it decoded a JWT and believed it, which "
        "makes the assertion a formality any caller can produce. E1-06's fourth part exists "
        "precisely because the platform has to go and get that key set.\n\n"
        "If the platform does fetch it and reaches it some other way than `app.state.http`, this "
        "is the fixture's seam rather than the mock's defect: "
        "`tests/fixtures/client_credentials.py` is the one place that changes, and the ticket "
        "leaves the fetch mechanics to the implementer."
    )


# ---------------------------------------------------------------------------
# The six refusals, each with the request it differs from by one thing.
# ---------------------------------------------------------------------------


def test_a_token_request_with_no_client_assertion_is_refused(
    platform: Any, token_url: str, client_id: str, tool_key_pair: Any, claims_for_an_assertion: Any
) -> None:
    """Refusal 1 of six: the request carries no `client_assertion` at all.

    **The mutation this kills:** a token endpoint that issues a token for any
    well-formed `grant_type=client_credentials` request, which is the shape a
    first implementation reaches when the assertion is read as optional metadata.
    A platform doing that grants a service token to anything that can reach the
    container.

    `invalid_request` rather than `invalid_client`, per RFC 6749 §5.2: nothing
    arrived to authenticate the client with, so the request is malformed rather
    than the client unauthenticated. The distinction is what tells E1-11 that it
    built the request wrongly rather than signed it wrongly.

    The body is posted **without** the member rather than with an empty one; an
    empty `client_assertion` is a different request and would be caught by a
    length check that a missing member walks past.
    """
    control = claims_for_an_assertion(client_id, token_url)
    granted(
        platform,
        token_url,
        token_request(tool_key_pair.sign(control), NRPS_MEMBERSHIP_SCOPE),
        "The same request carrying an assertion",
    )

    refused(
        platform,
        token_url,
        token_request(None, NRPS_MEMBERSHIP_SCOPE),
        INVALID_REQUEST,
        "A token request carrying no `client_assertion`",
        "The identical request carrying a valid assertion was granted a moment ago,",
    )


def test_an_assertion_whose_audience_is_not_the_token_endpoint_is_refused(
    platform: Any, token_url: str, client_id: str, tool_key_pair: Any, claims_for_an_assertion: Any
) -> None:
    """Refusal 2 of six: `aud` names something other than this token endpoint.

    The audience is what stops an assertion being replayed somewhere else. A tool
    holds one signing key and talks to several platforms, so an assertion minted
    for platform A and accepted by platform B lets B authenticate as that tool
    wherever A would — the same credential, spent at the wrong door.

    **The mutation this kills:** a verifier that decodes the assertion and checks
    the signature and never compares `aud`, which is the default behaviour of
    every JOSE library that is not told an audience. `pylti1p3` sets `aud` to the
    `auth_token_url` it was configured with, which is why this test's accepted
    twin uses exactly the advertised URL and nothing derived from it.

    **The near miss it must survive**: the issuer. That value is the platform's
    own identity, it appears in every launch this platform signs, and it is the
    single most likely thing for a verifier to compare against by accident — so
    the refused assertion names it rather than naming a stranger, and a platform
    that accepts it is one where any assertion for any endpoint on this issuer
    works.
    """
    control = claims_for_an_assertion(client_id, token_url)
    granted(
        platform,
        token_url,
        token_request(tool_key_pair.sign(control), NRPS_MEMBERSHIP_SCOPE),
        "The same assertion with `aud` set to the token endpoint",
    )

    issuer = discovery_of(platform).get("issuer")
    assert isinstance(issuer, str) and issuer and issuer != token_url, (
        f"The discovery document's `issuer` is {issuer!r}, which is not a distinct string to put "
        "in `aud`. This test needs an audience that is wrong and plausible; if the issuer and the "
        "token endpoint are the same value, the refusal below could not be posed at all."
    )
    claims = claims_for_an_assertion(client_id, token_url)
    claims["aud"] = issuer

    refused(
        platform,
        token_url,
        token_request(tool_key_pair.sign(claims), NRPS_MEMBERSHIP_SCOPE),
        INVALID_CLIENT,
        f"An assertion whose `aud` is the platform's issuer {issuer!r} rather than its token "
        "endpoint",
        "The identical assertion with the right audience was granted a moment ago,",
    )


def test_a_token_request_for_an_unadvertised_scope_is_refused(
    platform: Any, token_url: str, client_id: str, tool_key_pair: Any, claims_for_an_assertion: Any
) -> None:
    """Refusal 3 of six: a scope the platform does not advertise.

    A token endpoint that grants whatever scope it is asked for makes
    `scopes_supported` decoration. That matters beyond tidiness: the scope a token
    carries is what a service checks before it acts, so a platform that grants
    `…/scope/score` to a tool that was never authorised for it has handed out the
    ability to write grades.

    **The mutation this kills:** an implementation that echoes the requested scope
    into the response and grants it. That passes the happy-path test above — which
    asks for an advertised scope — and is invisible to everything else.

    The scope asked for is asserted absent from `scopes_supported` first, so this
    cannot pass because the platform happens to advertise it (`docs/MISTAKES.md`
    entry 3), and the accepted twin uses one that *is* advertised, so the refusal
    is about the scope rather than about the platform's mood.
    """
    advertised = advertised_scopes(platform)
    assert UNADVERTISED_SCOPE not in advertised, (
        f"The platform advertises {UNADVERTISED_SCOPE!r} (its list is {advertised!r}), so the "
        "request below asks for something it may legitimately grant and the refusal this test "
        "asserts would be a defect report about a platform doing the right thing."
    )

    control = claims_for_an_assertion(client_id, token_url)
    granted(
        platform,
        token_url,
        token_request(tool_key_pair.sign(control), NRPS_MEMBERSHIP_SCOPE),
        f"The same request asking for the advertised scope {NRPS_MEMBERSHIP_SCOPE!r}",
    )

    claims = claims_for_an_assertion(client_id, token_url)
    refused(
        platform,
        token_url,
        token_request(tool_key_pair.sign(claims), UNADVERTISED_SCOPE),
        INVALID_SCOPE,
        f"A token request for the unadvertised scope {UNADVERTISED_SCOPE!r}",
        "The identical request for an advertised scope was granted a moment ago,",
    )


def test_an_assertion_signed_by_a_key_the_tool_never_published_is_refused(
    platform: Any,
    token_url: str,
    client_id: str,
    tool_key_pair: Any,
    key_the_tool_never_published: Any,
    claims_for_an_assertion: Any,
) -> None:
    """Refusal 4 of six: the signature is real, and it is somebody else's.

    This is the refusal the tool's whole JWKS route exists for. The assertion is a
    bearer credential in every respect except that it is signed, so the signature
    is the entire authentication: a platform that does not check it against the
    tool's published key set will authenticate anyone who knows a client id, which
    is a value published in a launch form.

    **The mutations this kills:** a verifier that decodes without verifying; one
    that verifies against a key set it was never given, so any well-formed
    signature passes; and one that selects a key by the header's `kid` and then
    trusts the token because a key was found. The last is why the refused
    assertion is signed by a **real** RSA key rather than being a corrupted
    signature — a mangled signature is refused by a verifier that does no key
    selection at all, and the test would read that as key selection working.

    The claims are otherwise identical to the accepted twin's, so nothing but the
    key differs.
    """
    control = claims_for_an_assertion(client_id, token_url)
    granted(
        platform,
        token_url,
        token_request(tool_key_pair.sign(control), NRPS_MEMBERSHIP_SCOPE),
        "The same assertion signed with the key the tool published",
    )

    claims = claims_for_an_assertion(client_id, token_url)
    refused(
        platform,
        token_url,
        token_request(key_the_tool_never_published.sign(claims), NRPS_MEMBERSHIP_SCOPE),
        INVALID_CLIENT,
        "An assertion signed by a key that is not in the tool's published key set",
        "The identical claims signed with the tool's own key were granted a moment ago,",
    )


def test_an_expired_assertion_is_refused(
    platform: Any, token_url: str, client_id: str, tool_key_pair: Any, claims_for_an_assertion: Any
) -> None:
    """Refusal 5 of six: `exp` is in the past.

    **The mutation this kills:** a verifier that reads `exp` and never compares it
    to a clock — the state of every JOSE library asked to decode without
    verification options. An assertion that never stops being valid is a
    credential that stays usable wherever it leaks, which is the ticket's own
    argument for the bound in the next test.

    The expiry is produced by moving `iat` and `exp` **back together**, so the
    assertion is a well-formed one that was minted an hour ago rather than a
    malformed one whose `exp` precedes its `iat`. A verifier can legitimately
    refuse the second for a different reason, and this test would then pass
    against a platform that checks no clock at all (`docs/MISTAKES.md` entry 3).
    """
    control = claims_for_an_assertion(client_id, token_url)
    granted(
        platform,
        token_url,
        token_request(tool_key_pair.sign(control), NRPS_MEMBERSHIP_SCOPE),
        "The same assertion, live",
    )

    claims = claims_for_an_assertion(client_id, token_url, issued_at=time.time() - 3600)
    assert claims["exp"] < time.time(), (
        f"The assertion this test means to be expired expires at {claims['exp']} and it is now "
        f"{int(time.time())}, so it is still live and the refusal below would be about something "
        "else."
    )

    refused(
        platform,
        token_url,
        token_request(tool_key_pair.sign(claims), NRPS_MEMBERSHIP_SCOPE),
        INVALID_CLIENT,
        "An assertion that expired an hour ago",
        "The identical assertion inside its own lifetime was granted a moment ago,",
    )


def test_an_assertion_with_no_expiry_is_refused(
    platform: Any, token_url: str, client_id: str, tool_key_pair: Any, claims_for_an_assertion: Any
) -> None:
    """Refusal 6a of six: the assertion states no `exp`.

    A missing claim and a bad one are different cases and a verifier is entitled
    to treat them differently — which is exactly the risk. The natural
    implementation reads `exp` and compares it, and a claim that is absent
    compares as "no expiry stated", which is the fail-open branch: an assertion
    with no `exp` is a credential with no end.

    **The mutation this kills:** an expiry check written as "if `exp` is present
    and in the past, refuse". That passes the expired test above and grants a
    token to an assertion that never expires.

    `invalid_request` rather than `invalid_client`, per the brief's mapping: the
    assertion is missing something it must carry.
    """
    control = claims_for_an_assertion(client_id, token_url)
    granted(
        platform,
        token_url,
        token_request(tool_key_pair.sign(control), NRPS_MEMBERSHIP_SCOPE),
        "The same assertion carrying an `exp`",
    )

    claims = claims_for_an_assertion(client_id, token_url)
    claims.pop("exp")
    assert "exp" not in claims, "The claims this test signs still carry an `exp`."

    refused(
        platform,
        token_url,
        token_request(tool_key_pair.sign(claims), NRPS_MEMBERSHIP_SCOPE),
        INVALID_REQUEST,
        "An assertion stating no `exp`",
        "The identical assertion carrying one was granted a moment ago,",
    )


def test_an_assertion_living_past_the_bound_is_refused_and_one_at_the_bound_is_granted(
    platform: Any, token_url: str, client_id: str, tool_key_pair: Any, claims_for_an_assertion: Any
) -> None:
    """Refusal 6b of six: the lifetime bound, asserted from both sides of the line.

    The ticket asks for this in as many words — "an assertion with no `exp` or one
    longer-lived than the short bound the mock enforces (minutes, not hours; the
    exact bound is the builder's, asserted in a test)" — and gives the reason: "a
    tool-signed bearer assertion with unbounded `exp` is a credential that stays
    usable wherever it leaks". **The bound is 300 seconds**, settled in the E1-06
    dispatch brief so that the test and the implementation could be written from
    one number rather than one discovering the other's.

    **Both directions in one test, because a bound has two failure modes and each
    is invisible to the other half.** A platform with no bound at all passes the
    accepted case and fails the refused one; a platform that refuses everything —
    or whose bound is a minute — passes the refused case and fails the accepted
    one. A test written from one side is satisfied by one of the two.

    301 rather than an hour, and 300 rather than a minute, because the pair either
    side of the line is what says the line is where the ticket put it. A refusal at
    3600 and an acceptance at 60 is equally satisfied by a bound anywhere between
    them.

    **The near miss this is written around:** the assertion is aged by moving
    `exp` forward from a live `iat`, so the only thing that differs between the two
    halves is one second of stated lifetime. Neither is expired, neither is
    malformed, and both are signed by the same key.
    """
    at_the_bound = claims_for_an_assertion(
        client_id, token_url, lifetime=ASSERTION_LIFETIME_BOUND_SECONDS
    )
    assert at_the_bound["exp"] - at_the_bound["iat"] == ASSERTION_LIFETIME_BOUND_SECONDS, (
        "The claims builder did not produce the lifetime this test asked for, so neither half "
        "below is about the bound."
    )
    granted(
        platform,
        token_url,
        token_request(tool_key_pair.sign(at_the_bound), NRPS_MEMBERSHIP_SCOPE),
        f"An assertion living exactly {ASSERTION_LIFETIME_BOUND_SECONDS} seconds",
    )

    past_the_bound = claims_for_an_assertion(
        client_id, token_url, lifetime=ASSERTION_LIFETIME_BOUND_SECONDS + 1
    )
    refused(
        platform,
        token_url,
        token_request(tool_key_pair.sign(past_the_bound), NRPS_MEMBERSHIP_SCOPE),
        INVALID_CLIENT,
        f"An assertion living {ASSERTION_LIFETIME_BOUND_SECONDS + 1} seconds, one past the bound",
        f"An assertion living exactly {ASSERTION_LIFETIME_BOUND_SECONDS} seconds was granted a "
        "moment ago, so the bound is where this ticket put it,",
    )


# ---------------------------------------------------------------------------
# The two refusals E1-11 closes, from `docs/tickets/e1/deferred.md` (E1-06 items
# 1 and 2). Both are about what this endpoint remembers or refuses **beyond the
# signature**, which is why ADR 0084's own measured-boundary paragraph puts them
# in the same future change.
# ---------------------------------------------------------------------------


def test_an_assertion_presented_twice_is_refused_the_second_time(
    platform: Any, token_url: str, client_id: str, tool_key_pair: Any, claims_for_an_assertion: Any
) -> None:
    """Deferred E1-06 item 1: the endpoint refuses a replayed `jti`.

    "**Done when** the endpoint refuses a second request presenting an
    already-seen `jti` within the lifetime bound, proven by a pair (fresh `jti`
    granted, replayed `jti` refused) — at latest with E1-11, whose client's
    conformance claims otherwise rest on an endpoint that cannot notice a replay."

    A `client_assertion` is a bearer credential for the five minutes it lives, so
    an endpoint that cannot notice a replay is one where a captured assertion is
    worth a token to anybody holding it, however often — which is the property ADR
    0084's lifetime bound was supposed to cap and, as its own security-review
    paragraph records, does not: "with `jti` untracked — [it] stays spendable until
    its far-future `exp`".

    **The pair, and it is three requests rather than two.** The same assertion is
    granted once and refused once, which is the finding; and a *fresh* assertion is
    granted afterwards, which is what tells a `jti` store from an endpoint that
    grants exactly one token and refuses everything after it. Without the third
    request, a platform that shut its own door would pass.

    **The near miss it must not fire on** is in that third request: it differs from
    the first only in `jti` and `iat`, which is what `claims_for_an_assertion`
    produces on every call — so the refusal in the middle is attributable to the
    identifier and not to anything else about the request.

    **What this deliberately does not assert** is the store's eviction: D12 keeps
    entries "≥ the 300s assertion bound", and a test of that would have to wait out
    the bound. What matters for conformance is that a replay inside the lifetime is
    refused.
    """
    claims = claims_for_an_assertion(client_id, token_url)
    assertion = tool_key_pair.sign(claims)

    granted(
        platform,
        token_url,
        token_request(assertion, NRPS_MEMBERSHIP_SCOPE),
        "The first presentation of a freshly minted assertion",
    )

    refused(
        platform,
        token_url,
        token_request(assertion, NRPS_MEMBERSHIP_SCOPE),
        INVALID_GRANT,
        f"The same assertion, `jti` {claims['jti']!r}, presented a second time",
        "The very same assertion was granted a moment ago,",
    )

    granted(
        platform,
        token_url,
        token_request(
            tool_key_pair.sign(claims_for_an_assertion(client_id, token_url)), NRPS_MEMBERSHIP_SCOPE
        ),
        "A second, freshly minted assertion after the replay was refused",
    )


def test_a_jti_is_remembered_for_as_long_as_an_assertion_carrying_it_could_be_accepted(
    platform: Any,
    token_url: str,
    client_id: str,
    tool_key_pair: Any,
    claims_for_an_assertion: Any,
    wind_the_clock_back: Any,
) -> None:
    """The security round's F4: the prune horizon has to be the acceptance ceiling.

    Two numbers in the same endpoint, one apart. A `jti` is forgotten after
    `ASSERTION_LIFETIME_BOUND_SECONDS`; an assertion is accepted while
    `exp <= now + lifetime + skew`. So an assertion whose `iat` sits inside the skew
    allowance — an honest tool whose clock is a little fast, which is the case the
    allowance exists for — is still live after its `jti` has been forgotten, and a
    spent one replayed in that window is granted a **second** token off one
    signature.

    **How the window is reached without waiting five minutes.** The clock is wound
    back for the first grant only, so the platform records the `jti` at `T` while
    the assertion is dated `iat = T + skew`, `exp = T + lifetime + skew` — accepted,
    because that is exactly the boundary the test below pins. Real time is then
    `T + 310`: past the prune horizon as it stands, inside the one the fix gives it,
    with the assertion still live for twenty seconds. Only the `jti` can refuse it.

    **The mutation this kills**: the prune horizon left at
    `ASSERTION_LIFETIME_BOUND_SECONDS`. Every other replay assertion in this module
    presents its `jti` a second or two after recording it, so all of them stay
    green — which is how this survived to the security review.

    **What this pair cannot pose, said rather than hidden** (`docs/MISTAKES.md`
    entry 14). The other half — "a `jti` past the horizon is forgotten" — is not
    observable through this endpoint, and that is the *reason* the horizon is
    `lifetime + skew` rather than something larger: past that point no assertion
    carrying the `jti` can still be accepted, so a forgotten one and a remembered
    one are both refused and both for the expiry. What is observable, and is
    asserted, is that the store has not become a wall: a fresh `jti` after the
    wound-back grant is still granted.
    """
    horizon = ASSERTION_LIFETIME_BOUND_SECONDS + ASSERTION_SKEW_ALLOWANCE_SECONDS
    replayed_at = ASSERTION_LIFETIME_BOUND_SECONDS + 10
    assert ASSERTION_LIFETIME_BOUND_SECONDS < replayed_at < horizon, (
        f"This test replays a `jti` {replayed_at} seconds after it was recorded, and the window it "
        f"means to land in is ({ASSERTION_LIFETIME_BOUND_SECONDS}, {horizon}) — past the prune "
        "horizon as it stands and inside the one the fix gives it. Outside that window the "
        "assertion is either still inside the old horizon, and refused for the `jti` whatever the "
        "fix does, or expired, and refused for that instead."
    )

    with wind_the_clock_back(replayed_at):
        aged = claims_for_an_assertion(
            client_id,
            token_url,
            issued_at=time.time() + ASSERTION_SKEW_ALLOWANCE_SECONDS,
            lifetime=ASSERTION_LIFETIME_BOUND_SECONDS,
        )
        assertion = tool_key_pair.sign(aged)
        granted(
            platform,
            token_url,
            token_request(assertion, NRPS_MEMBERSHIP_SCOPE),
            f"An assertion dated {ASSERTION_SKEW_ALLOWANCE_SECONDS} seconds ahead of the "
            "platform's clock, inside the stated skew allowance",
        )

    assert aged["exp"] > time.time(), (
        f"The assertion this test replays expired at {aged['exp']} and it is now "
        f"{int(time.time())}, so the endpoint would refuse it for its expiry and the refusal below "
        "would say nothing about whether the `jti` was remembered."
    )

    refused(
        platform,
        token_url,
        token_request(assertion, NRPS_MEMBERSHIP_SCOPE),
        INVALID_GRANT,
        f"The same assertion, `jti` {aged['jti']!r}, replayed {replayed_at} seconds after it was "
        "first spent and still twenty seconds from expiry",
        "The identical assertion was granted when it was first presented, and it is still live,",
    )

    granted(
        platform,
        token_url,
        token_request(
            tool_key_pair.sign(claims_for_an_assertion(client_id, token_url)),
            NRPS_MEMBERSHIP_SCOPE,
        ),
        "A freshly minted assertion after the replayed one was refused",
    )


def test_an_assertion_dated_beyond_the_platforms_clock_and_the_stated_skew_is_refused(
    platform: Any, token_url: str, client_id: str, tool_key_pair: Any, claims_for_an_assertion: Any
) -> None:
    """Deferred E1-06 item 2: the wall-clock clamp, from both sides of its line.

    "**Done when** the endpoint also refuses an assertion whose `exp` lies further
    than the bound plus a stated skew allowance beyond the platform's clock, proven
    by a pair on both sides of that line."

    ADR 0084 measures the hole this closes: `exp - iat` are *both* the signer's own
    statements, "so a signer who dates both claims in the future mints an assertion
    that passes the expiry check and measures a lifetime of zero" — a credential
    with a five-minute stated life and an unbounded real one. The clamp is the
    platform comparing `exp` against its own clock rather than against the
    assertion's arithmetic.

    **Why both halves move `iat` forward too, which is the whole shape of the
    test.** Decision 1's bound is still in force, so an assertion with `iat` now and
    `exp` at now + 330 is refused for its 330-second *lifetime* and says nothing
    about the clamp. Dating both claims forward keeps the stated lifetime at exactly
    the permitted 300 and leaves `exp` as the only thing that moves — which is
    precisely the forged-dating case, and which makes the accepted half a real
    requirement rather than a formality: a tool whose clock is 30 seconds fast is an
    honest tool, and the allowance exists so that this endpoint does not refuse it.

    **Close either side of the line**, for the reason the lifetime bound's own pair
    gives: a refusal at an hour and an acceptance at a minute is satisfied by a clamp
    anywhere between them. The accepted half sits *exactly* on the line. The refused
    half sits `WALL_CLOCK_DRIFT_MARGIN_SECONDS` past it rather than one second past
    it, and that constant carries the whole reason — this test reads one clock and
    the platform reads another a moment later, so a one-second margin is a race
    rather than a measurement. Each half reads the clock immediately before its own
    request, so neither pays for the other's round trip.
    """
    bound = ASSERTION_LIFETIME_BOUND_SECONDS
    allowance = ASSERTION_SKEW_ALLOWANCE_SECONDS

    now = int(time.time())
    at_the_line = claims_for_an_assertion(client_id, token_url, issued_at=now + allowance)
    at_the_line["exp"] = now + bound + allowance
    at_the_line["iat"] = at_the_line["exp"] - bound
    assert at_the_line["exp"] - at_the_line["iat"] == bound, (
        "The claims this test means to sit at the wall-clock line do not state the permitted "
        "lifetime, so this half would be refused for its stated lifetime instead and would say "
        "nothing about the clamp."
    )
    granted(
        platform,
        token_url,
        token_request(tool_key_pair.sign(at_the_line), NRPS_MEMBERSHIP_SCOPE),
        f"An assertion expiring exactly {bound + allowance} seconds from now, with a stated "
        f"lifetime of {bound}",
    )

    # Read again here rather than reusing the read above: the grant that just
    # happened signed an assertion, posted it, and had a key set fetched and a
    # signature verified, and every millisecond of that would otherwise come out of
    # this half's margin.
    now = int(time.time())
    past = bound + allowance + WALL_CLOCK_DRIFT_MARGIN_SECONDS
    past_the_line = claims_for_an_assertion(client_id, token_url)
    past_the_line["exp"] = now + past
    past_the_line["iat"] = past_the_line["exp"] - bound
    assert past_the_line["exp"] - past_the_line["iat"] == bound, (
        "The assertion this test means to be refused by the clamp states a lifetime other than "
        f"{bound}, so it would be refused for that instead and the refusal would be about the "
        "bound rather than about the platform's own clock."
    )
    refused(
        platform,
        token_url,
        token_request(tool_key_pair.sign(past_the_line), NRPS_MEMBERSHIP_SCOPE),
        INVALID_GRANT,
        f"An assertion expiring {past} seconds from now — "
        f"{WALL_CLOCK_DRIFT_MARGIN_SECONDS} past the bound plus the stated skew — whose own "
        f"arithmetic still claims a {bound}-second lifetime",
        f"An assertion expiring exactly {bound + allowance} seconds from now, dated the same way, "
        "was granted a moment ago,",
    )


# ---------------------------------------------------------------------------
# Criterion 2 — the whole sequence, in raw HTTP.
# ---------------------------------------------------------------------------


def test_a_roster_is_read_with_a_token_obtained_the_way_a_service_connector_obtains_one(
    platform: Any, token_url: str, client_id: str, tool_key_pair: Any, claims_for_an_assertion: Any
) -> None:
    """Criterion 2, and the carried entry's own definition of done.

    "The test that says it is done is a roster read performed the way `pylti1p3`
    performs one — token requested with a tool-signed assertion, token attached,
    container returned — rather than an unauthenticated `GET` that happens to
    answer." Every step here is that sequence in raw HTTP: the token endpoint out
    of the discovery document, the assertion signed with the tool's key, the scope
    the NRPS claim names, and the token presented as a `Bearer` credential on the
    memberships URL the launch advertised.

    **The mutation this kills:** any of the four parts landing without the others.
    A platform with a token endpoint and no NRPS scope refuses the request at the
    scope; one with scopes and no endpoint has nowhere to send it; one that
    advertises an endpoint it does not serve answers HTML. Each of those is a
    separate test above, and this is the one that says they compose.

    **What it could not say when it was written, and what now says it.** Under
    E1-06's ruling NRPS did not require a token, so a roster that answered the same
    way with no header at all would have satisfied the last step; the substance
    here was the grant, and the roster read only proved the granted token was
    presentable. E1-11's fix round closed that half: a tokenless read is refused,
    asserted in `test_mock_lms_nrps_requires_a_token.py`. This test is unchanged and
    still asserts what it always did — that the four parts compose into a sequence
    a conformant client can complete.
    """
    contexts = platform.seeded_contexts()
    assert contexts, (
        "The launch page offers no launches, so there is no context whose roster this could read "
        "with the token it just obtained. E0-14 seeds the launches and E0-15 the roster behind "
        "them."
    )

    claims = claims_for_an_assertion(client_id, token_url)
    answered = granted(
        platform,
        token_url,
        token_request(tool_key_pair.sign(claims), NRPS_MEMBERSHIP_SCOPE),
        "The roster-shaped token request",
    )
    access_token = str(answered.get("access_token") or "")
    assert access_token, "The platform granted a token response with no `access_token` in it."

    memberships_url = contexts[0].memberships_url
    response = platform.client.get(
        platform.local(memberships_url),
        headers={"accept": NRPS_MEDIA_TYPE, "authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200, (
        f"The membership service answered {response.status_code} for `{memberships_url}` when the "
        "token this platform had just issued was presented as a `Bearer` credential. A token a "
        "service will not accept is one E1-11's client cannot use, whatever the token endpoint "
        f"answered. Body begins {response.text[:300]!r}."
    )
    container = response.json()
    assert isinstance(container, dict) and isinstance(container.get("members"), list), (
        f"The membership service answered {container!r} for an authenticated read. NRPS 2.0 makes "
        "the container a JSON object with `id`, `context` and `members`; this is the document the "
        "whole grant exists to reach."
    )


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the mock platform.**
# ---------------------------------------------------------------------------


def test_the_assertions_these_tests_sign_verify_against_the_key_set_they_serve(
    tool_key_pair: Any, claims_for_an_assertion: Any
) -> None:
    """The machinery, checked before any refusal above is believed.

    Every accepted twin in this module rests on one claim: an assertion signed by
    `tool_key_pair` verifies against the key set `tool_key_set` serves. If that
    were false — a `kid` that names no served key, a JWK whose `n` was encoded
    with padding, a signing call that produced something a verifier cannot read —
    then every request in this module would be refused, all six refusal tests
    would pass, and the module would report a conformant platform having proved
    nothing.

    So the signature is verified here with the same arithmetic a platform would
    use: the served JWK, decoded, and RS256 checked against it.

    **A red here means these tests are broken, not the code.**
    """
    import jwt

    served = tool_key_pair.key_set()["keys"][0]
    assertion = tool_key_pair.sign(claims_for_an_assertion("a-client", "https://platform.invalid"))

    header = jwt.get_unverified_header(assertion)
    assert header.get("alg") == "RS256", (
        f"The assertions these tests sign carry `alg` {header.get('alg')!r}. E1-06's assertion is "
        "RS256, which is what the tool's published key set declares."
    )
    assert header.get("kid") == served["kid"], (
        f"The assertion's header names `kid` {header.get('kid')!r} and the served key set carries "
        f"{served['kid']!r}. A platform that selects a key by `kid` would find none, and every "
        "accepted twin in this module would be refused for a reason no test names."
    )

    claims = jwt.decode(
        assertion,
        rsa_public_key_from(served),
        algorithms=["RS256"],
        audience="https://platform.invalid",
    )
    assert claims["iss"] == "a-client" and claims["sub"] == "a-client", (
        f"An assertion signed and verified through this suite's own machinery came back as "
        f"{claims!r}, which does not carry the client id in `iss` and `sub`."
    )


def test_the_key_set_these_tests_serve_refuses_a_signature_by_the_other_key(
    tool_key_pair: Any, key_the_tool_never_published: Any, claims_for_an_assertion: Any
) -> None:
    """The other half of the control, and the one the fourth refusal rests on.

    The test above says the served key set accepts what the tool signs. This says
    it *refuses* what the stranger signs — "run it against the text you claim it
    catches and against the text you claim it allows" (`docs/MISTAKES.md` entry
    3). Without it, `key_the_tool_never_published` could be the same key under
    another name, or the two could share a modulus, and
    `test_an_assertion_signed_by_a_key_the_tool_never_published_is_refused` would
    be posing no question at all.

    **A red here means these tests are broken, not the code.**
    """
    import jwt

    served = tool_key_pair.key_set()["keys"][0]
    stranger = key_the_tool_never_published.key_set()["keys"][0]
    assert served["kid"] != stranger["kid"] and served["n"] != stranger["n"], (
        "The two key pairs these tests use are the same key: they share a modulus or a key "
        "identifier. The refusal that rests on them would then be about nothing."
    )

    assertion = key_the_tool_never_published.sign(
        claims_for_an_assertion("a-client", "https://platform.invalid")
    )

    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(
            assertion,
            rsa_public_key_from(served),
            algorithms=["RS256"],
            audience="https://platform.invalid",
        )
