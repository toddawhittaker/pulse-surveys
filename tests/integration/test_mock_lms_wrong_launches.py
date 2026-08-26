"""The mock platform mints deliberately wrong launches, by name — ticket E1-07.

E0-25 item 5, carried out of E0 with E1 as owner: "the mock LMS cannot mint a
deliberately wrong launch — tool-side launch validation is E1's, and E0-14
defined no interface for a bad launch deliberately." `docs/MISTAKES.md` entry
28 is why that matters: a driver that can only speak correctly leaves the
invalid half of every guard E1-08 (heavy) writes untestable.

**What this module asserts, and what it does not.** Every test below decodes
the artifact a mint produces and checks the *specific* wrongness the ticket
names — a bad signature verifies false against the platform's own JWKS, `alg`
really is `none`, the two `reused_nonce` tokens really are the same bytes —
never a 200 alone (`docs/MISTAKES.md` entry 3). Each also carries a canary: a
claim or property known to survive that one defect, so a check that has gone
blind — a verifier that always answers `True`, a comparison against emptiness
— says so by failing the canary rather than by passing quietly. Tool-side
validation, and whether Pulse refuses any of these, is E1-08's; nothing here
asserts a refusal.

**Driven around `MockPlatform.mint`, not through it.** `mint()` in
`tests/fixtures/lti_services.py` has no `?defect=` parameter — E1-07's mints
live on the mock, not in that fixture (E1-08 is expected to extend it, or to
drive the query parameter directly the way this module does). So the requests
below are built the same way `mint()` builds one and posted straight at the
authorization endpoint with the selector appended, and the response is read
back with `MockPlatform.read_authorization_response`, the same method `mint()`
itself calls.

**Why the claims are decoded locally rather than through `SignedLaunch`.**
`SignedLaunch.header`/`.claims` are populated by `mint()` at the moment it
signs a request, and there is no such object for a request `mint()` never
made. `header_claims_and_signature` below is this module's own decoder, the
way `test_mock_lms_client_credentials_grant.py` keeps `rsa_public_key_from` —
not imported from `tests/fixtures/lti_platform.py`, for the reason
`test_mock_lms_launch.py` gives about every fixtures import: an import of a
fixtures module by name depends on where pytest put `tests/` on `sys.path`,
and an import error is not a red.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

import pytest

pytestmark = pytest.mark.lti

# `mock_platform` and `mock_platforms` come from `tests/fixtures/lti_services.py`
# and are reached as fixtures rather than imported — see the module docstring.

# The query parameter `mock-lms/app/wrong_launches.py` reads off the
# authorization request's URL. **This suite's own copy of the string**, not an
# import of `app.wrong_launches.DEFECT_QUERY_PARAM`: both mocks declare a
# package named `app` (SPEC §13), and importing either by name from a test
# module is the collision `docs/adr/0039-the-two-app-packages-are-typechecked-
# in-two-runs.md` describes for mypy and this suite avoids for the same reason.
DEFECT_QUERY_PARAM = "defect"

# The fifteen wrong-launch selectors and the three near-miss/edge selectors
# `app.wrong_launches.ALL_SELECTORS` declares, copied here as this suite's own
# vocabulary for the reason above. If a name below stops matching the mock's
# own constant, every test that selects it starts failing on the 400 refusal
# `WrongLaunchMinter.mint` gives an unrecognised name — loudly, not silently.
FOREIGN_SIGNATURE = "foreign_signature"
RIGHT_KEY_TAMPERED_CLAIMS = "right_key_tampered_claims"
ALG_NONE = "alg_none"
HS256_CONFUSION = "hs256_confusion"
WRONG_AUD = "wrong_aud"
WRONG_ISS = "wrong_iss"
MISSING_NONCE = "missing_nonce"
REUSED_NONCE = "reused_nonce"
UNREGISTERED_DEPLOYMENT = "unregistered_deployment"
UNKNOWN_MESSAGE_TYPE = "unknown_message_type"
WRONG_VERSION = "wrong_version"
TAMPERED_STATE = "tampered_state"
MISSING_STATE = "missing_state"
IAT_FUTURE = "iat_future"
EXP_PAST = "exp_past"
ONLY_TEACHING_ASSISTANT_ROLE = "only_teaching_assistant_role"
ONLY_MENTOR_ROLE = "only_mentor_role"
TITLELESS_CONTEXT = "titleless_context"

ALL_SELECTORS: tuple[str, ...] = (
    FOREIGN_SIGNATURE,
    RIGHT_KEY_TAMPERED_CLAIMS,
    ALG_NONE,
    HS256_CONFUSION,
    WRONG_AUD,
    WRONG_ISS,
    MISSING_NONCE,
    REUSED_NONCE,
    UNREGISTERED_DEPLOYMENT,
    UNKNOWN_MESSAGE_TYPE,
    WRONG_VERSION,
    TAMPERED_STATE,
    MISSING_STATE,
    IAT_FUTURE,
    EXP_PAST,
    ONLY_TEACHING_ASSISTANT_ROLE,
    ONLY_MENTOR_ROLE,
    TITLELESS_CONTEXT,
)

# The LTI 1.3 message claims, spelled as `test_mock_lms_launch.py` spells them
# and as the specification spells them — not this suite's choice.
LTI_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/"
MESSAGE_TYPE_CLAIM = LTI_CLAIM + "message_type"
VERSION_CLAIM = LTI_CLAIM + "version"
DEPLOYMENT_ID_CLAIM = LTI_CLAIM + "deployment_id"
CONTEXT_CLAIM = LTI_CLAIM + "context"
ROLES_CLAIM = LTI_CLAIM + "roles"

RESOURCE_LINK_MESSAGE_TYPE = "LtiResourceLinkRequest"
LTI_VERSION = "1.3.0"

# `app.launch.TOKEN_LIFETIME_SECONDS` — 300, five minutes — copied rather than
# imported for the same reason as everything else in this block. Used only as
# the canary in `iat_future`/`exp_past`: that shifting `iat` leaves the token's
# own lifetime untouched, so the one thing that moved is the one thing each
# selector names.
TOKEN_LIFETIME_SECONDS = 300

# Copied whole from the ticket rather than assembled from a base URN — it is
# not a member of the plain membership vocabulary's stem, it is IMS's
# sub-role form, and a concatenation here is the retype `docs/MISTAKES.md`
# entry 3 warns against.
TEACHING_ASSISTANT_SUB_ROLE_URN = (
    "http://purl.imsglobal.org/vocab/lis/v2/membership/Instructor#TeachingAssistant"
)

# Built the same way `tests/integration/test_lti_launch_door.py` builds
# `MENTOR_ROLE_URI` — off the plain membership vocabulary stem, because Mentor
# (unlike TeachingAssistant above) is a direct member of it.
MENTOR_ROLE_URN = "http://purl.imsglobal.org/vocab/lis/v2/membership#Mentor"

# How far past `TOKEN_LIFETIME_SECONDS` this suite requires `iat_future` and
# `exp_past` to land before calling them "implausible". Generous on purpose: a
# tight bound here would make this suite the thing that decides E1-08's clock-
# skew tolerance, which §9.1 leaves to that ticket.
IMPLAUSIBLE_MARGIN_SECONDS = 1800


# ---------------------------------------------------------------------------
# Driving the endpoint the way `MockPlatform.mint` does, plus one query
# parameter it does not yet know about.
# ---------------------------------------------------------------------------


def authorization_endpoint(platform: Any) -> str:
    """Where this platform answers a tool's authorization request."""
    return platform.endpoint(
        "authorization_endpoint",
        ("auth",),
        "receives the tool's authorization request and answers with a signed `id_token`",
    )


def authorization_request(platform: Any) -> dict[str, str]:
    """One well-formed authorization request, built off the platform's own launch form.

    The same construction `MockPlatform.mint` uses — read the offer, invent a
    `state` and a `nonce`, carry over everything the launch form named — kept
    here rather than reused from there because `mint` has no `?defect=`
    parameter to carry it through (see the module docstring).
    """
    offer = platform.require_offers()[0]
    request = {
        "scope": "openid",
        "response_type": "id_token",
        "response_mode": "form_post",
        "prompt": "none",
        "state": secrets.token_urlsafe(24),
        "nonce": secrets.token_urlsafe(24),
        "redirect_uri": offer.parameters.get("target_link_uri", ""),
    }
    for name in ("login_hint", "lti_message_hint", "client_id", "lti_deployment_id"):
        value = offer.parameters.get(name)
        if value:
            request[name] = value
    return request


def post_authorization(platform: Any, request: dict[str, str], defect: str | None) -> Any:
    """POST one authorization request, `?defect=` appended when `defect` is given."""
    path = authorization_endpoint(platform)
    params = {} if defect is None else {DEFECT_QUERY_PARAM: defect}
    return platform.client.post(path, data=request, params=params)


def mint(platform: Any, defect: str | None) -> tuple[dict[str, str], str, str]:
    """One authorization round trip: the request sent, the `id_token`, and the returned `state`.

    Fails loudly through `MockPlatform.read_authorization_response` if the
    platform answers with anything other than a launch — a 400 refusal among
    them — which is the right failure for every selector in `ALL_SELECTORS`:
    each of those is expected to be *producible*, whatever else is wrong with
    what it produces.
    """
    request = authorization_request(platform)
    response = post_authorization(platform, request, defect)
    id_token, returned_state, _ = platform.read_authorization_response(
        response, authorization_endpoint(platform)
    )
    return request, id_token, returned_state or ""


def header_claims_and_signature(token: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    """One minted `id_token`'s header and claims, decoded independently.

    Returns the raw (still base64url-encoded) third segment rather than
    decoded bytes, because `alg_none`'s whole assertion is that segment being
    the empty string.
    """
    parts = token.split(".")
    if len(parts) != 3:
        pytest.fail(
            f"A mint produced {token[:64]!r}, which has {len(parts)} dot-separated segments "
            "rather than the three a compact JWS has."
        )
    encoded_header, encoded_claims, encoded_signature = parts

    def decoded(segment: str) -> Any:
        padding = "=" * (-len(segment) % 4)
        return json.loads(base64.urlsafe_b64decode(segment + padding))

    return decoded(encoded_header), decoded(encoded_claims), encoded_signature


# ---------------------------------------------------------------------------
# Criterion 2: the happy path is unaffected when no selector is named.
# ---------------------------------------------------------------------------


def test_a_launch_minted_with_no_defect_selector_still_verifies_and_carries_the_right_claims(
    mock_platform: Any,
) -> None:
    """The request this whole ticket is not allowed to change.

    Driven through `authorization_request`/`post_authorization` rather than
    `mock_platform.mint()`, deliberately: this is the same route `?defect=`
    reaches, minus the parameter, so a regression in the `if defect is None`
    branch of `mock-lms/app/main.py` shows up here rather than only in
    `test_mock_lms_launch.py`, which drives the endpoint through `mint()`
    instead.
    """
    request, id_token, returned_state = mint(mock_platform, defect=None)

    assert mock_platform.verifies(id_token) is not None, (
        "A launch minted with no `defect` selector does not verify against the platform's own "
        "published key set. E1-07 is additive; this path must be byte-identical to what it was "
        "before this ticket."
    )
    _, claims, signature = header_claims_and_signature(id_token)
    assert signature, "The id_token carries no signature segment at all."
    assert claims.get("nonce") == request["nonce"], (
        f"The id_token's `nonce` is {claims.get('nonce')!r}, not the request's own "
        f"{request['nonce']!r}."
    )
    assert (
        returned_state == request["state"]
    ), f"The returned `state` is {returned_state!r}, not the request's own {request['state']!r}."
    assert claims.get(MESSAGE_TYPE_CLAIM) == RESOURCE_LINK_MESSAGE_TYPE
    assert claims.get(VERSION_CLAIM) == LTI_VERSION


@pytest.mark.parametrize("name", ALL_SELECTORS)
def test_every_declared_selector_is_producible(mock_platform: Any, name: str) -> None:
    """Acceptance criterion 1's precondition: every mint answers, none 400s.

    Not a substitute for the defect-specific tests below — a mint that
    answers 200 with the wrong artifact still passes this — but without it a
    selector that always 400s (a typo between `main.py` and
    `app.wrong_launches`, say) could pass every specific test below by that
    test never being reached for the right reason.
    """
    _, id_token, _ = mint(mock_platform, defect=name)
    assert id_token, f"Selector {name!r} produced an empty id_token."


def test_an_unrecognised_defect_name_is_refused_with_a_400(mock_platform: Any) -> None:
    """The dispatcher's own guard: a typo in `?defect=` is a refusal, not a launch."""
    request = authorization_request(mock_platform)
    response = post_authorization(mock_platform, request, defect="not-a-real-defect")
    assert response.status_code == 400, (
        f"`?defect=not-a-real-defect` answered {response.status_code}, not 400. A selector this "
        "platform does not recognise should be refused the way every other malformed "
        "authorization request is, per `app.launch.AuthorizationRequestError`."
    )
    assert "not-a-real-defect" in response.text, (
        "The 400 for an unrecognised `defect` does not name the value that was rejected, which "
        "is an afternoon for whoever mistypes a selector next."
    )


# ---------------------------------------------------------------------------
# The signature-shaped defects.
# ---------------------------------------------------------------------------


def test_foreign_signature_does_not_verify_against_the_platforms_own_key_set(
    mock_platform: Any,
) -> None:
    """`kid` present, key absent from this platform's JWKS."""
    request, id_token, _ = mint(mock_platform, defect=FOREIGN_SIGNATURE)
    header, claims, signature = header_claims_and_signature(id_token)
    assert signature, "The foreign-signature mint carries no signature segment at all."
    published = {key.get("kid") for key in mock_platform.published_keys()}
    assert header.get("kid") not in published, (
        f"`foreign_signature`'s header names `kid` {header.get('kid')!r}, which the platform's "
        f"own JWKS does publish ({sorted(k for k in published if k)}). The defect is a `kid` "
        "present but unknown to this platform, not a missing one."
    )
    assert (
        mock_platform.verifies(id_token) is None
    ), "A `foreign_signature` launch verified against the platform's own published key set."
    assert claims.get("nonce") == request["nonce"], "Canary: every other claim should be intact."


def test_right_key_tampered_claims_breaks_the_signature(mock_platform: Any) -> None:
    """The real `kid`, a claim rewritten after signing: the signature no longer matches."""
    request, id_token, _ = mint(mock_platform, defect=RIGHT_KEY_TAMPERED_CLAIMS)
    header, claims, _ = header_claims_and_signature(id_token)
    published = {key.get("kid") for key in mock_platform.published_keys()}
    assert header.get("kid") in published, (
        "Canary: `right_key_tampered_claims` is supposed to carry the platform's real `kid` — "
        "the defect is the payload, not the header."
    )
    assert str(claims.get("sub", "")).endswith("-tampered"), (
        f"`right_key_tampered_claims`'s `sub` is {claims.get('sub')!r}, which does not carry the "
        "tamper this mint is named for."
    )
    assert claims.get("nonce") == request["nonce"], "Canary: the rest of the payload is genuine."
    assert mock_platform.verifies(id_token) is None, (
        "A `right_key_tampered_claims` launch still verified. The signature covers the payload; "
        "a payload rewritten after signing must break it."
    )


def test_alg_none_carries_no_signature(mock_platform: Any) -> None:
    """`alg: none`, and an empty third segment — RFC 7519's unsecured JWT."""
    request, id_token, _ = mint(mock_platform, defect=ALG_NONE)
    header, claims, signature = header_claims_and_signature(id_token)
    assert header.get("alg") == "none", f"`alg_none`'s header carries `alg` {header.get('alg')!r}."
    assert signature == "", f"`alg_none`'s signature segment is {signature!r}, not empty."
    assert claims.get("nonce") == request["nonce"], "Canary: the claims are otherwise genuine."
    assert mock_platform.verifies(id_token) is None, (
        "An `alg_none` launch verified against the platform's key set — the verifier is not "
        "checking that a signature exists at all."
    )


def test_hs256_confusion_is_an_hmac_keyed_with_the_platforms_own_public_key(
    mock_platform: Any,
) -> None:
    """The classic RS256-to-HS256 bypass: HMAC'd with the key a JWKS actually serves.

    Recomputed independently — RFC 7518 §6.3's canonical `e`/`kty`/`n` member
    encoding, `hmac`/`hashlib` from the standard library — rather than by
    calling anything `app.signing` exports, for the same reason
    `test_mock_lms_launch.py`'s own RS256 verifier is a second implementation:
    a check that reuses the code it is checking agrees with itself by
    construction.
    """
    request, id_token, _ = mint(mock_platform, defect=HS256_CONFUSION)
    header, claims, encoded_signature = header_claims_and_signature(id_token)
    assert (
        header.get("alg") == "HS256"
    ), f"`hs256_confusion`'s header carries {header.get('alg')!r}."
    published = {key.get("kid"): key for key in mock_platform.published_keys()}
    assert header.get("kid") in published, (
        "Canary: `hs256_confusion`'s header should name a `kid` this platform's JWKS actually "
        "publishes — the whole attack is a token that points at a real RS256 key."
    )
    jwk = published[header["kid"]]
    secret = json.dumps(
        {"e": jwk["e"], "kty": "RSA", "n": jwk["n"]}, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    encoded_header = id_token.split(".")[0]
    encoded_claims = id_token.split(".")[1]
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    expected = hmac.new(secret, signing_input, hashlib.sha256).digest()
    padding = "=" * (-len(encoded_signature) % 4)
    actual = base64.urlsafe_b64decode(encoded_signature + padding)
    assert hmac.compare_digest(actual, expected), (
        "`hs256_confusion`'s signature is not an HMAC-SHA256 over the header and claims keyed "
        "with the canonical `e`/`kty`/`n` encoding of the platform's own published public key."
    )
    assert claims.get("nonce") == request["nonce"], "Canary: the claims are otherwise genuine."
    assert mock_platform.verifies(id_token) is None, (
        "An `hs256_confusion` launch verified as RS256 — the verifier is reading `alg` off the "
        "token rather than fixing the algorithm it checks."
    )


# ---------------------------------------------------------------------------
# The claim-value defects: a valid RS256 signature, one claim wrong.
# ---------------------------------------------------------------------------


def test_wrong_aud_names_an_unregistered_client_and_still_verifies(mock_platform: Any) -> None:
    request, id_token, _ = mint(mock_platform, defect=WRONG_AUD)
    _, claims, _ = header_claims_and_signature(id_token)
    registered = request.get("client_id")
    assert claims.get("aud") != registered, (
        f"`wrong_aud`'s `aud` is {claims.get('aud')!r}, the same client id the request itself "
        f"named ({registered!r})."
    )
    assert claims.get("aud") == "https://wrong-client.mock-lms.invalid"
    assert (
        mock_platform.verifies(id_token) is not None
    ), "Canary: `wrong_aud` is a signature-level valid launch — only `aud` is wrong."


def test_wrong_iss_names_an_unregistered_issuer_and_still_verifies(mock_platform: Any) -> None:
    _, id_token, _ = mint(mock_platform, defect=WRONG_ISS)
    _, claims, _ = header_claims_and_signature(id_token)
    # `iss` belongs to the *login-initiation* request the launch page posts to
    # the tool, not to the authorization request `mint` builds — so the real
    # issuer is read off the launch form's own hidden field, the same place
    # `MockPlatform.mint` would read it were this a happy-path launch.
    real_issuer = mock_platform.require_offers()[0].parameters.get("iss")
    assert real_issuer, "The launch form publishes no `iss` for this test to compare against."
    assert (
        claims.get("iss") != real_issuer
    ), f"`wrong_iss`'s `iss` is {claims.get('iss')!r}, the platform's own real issuer."
    assert claims.get("iss") == "https://wrong-issuer.mock-lms.invalid"
    assert (
        mock_platform.verifies(id_token) is not None
    ), "Canary: `wrong_iss` is a signature-level valid launch — only `iss` is wrong."


def test_missing_nonce_has_no_nonce_claim_and_still_verifies(mock_platform: Any) -> None:
    _, id_token, _ = mint(mock_platform, defect=MISSING_NONCE)
    _, claims, _ = header_claims_and_signature(id_token)
    assert "nonce" not in claims, f"`missing_nonce` carries `nonce` {claims.get('nonce')!r}."
    assert claims.get("sub"), "Canary: the rest of the payload is present."
    assert (
        mock_platform.verifies(id_token) is not None
    ), "Canary: `missing_nonce` is a signature-level valid launch — only `nonce` is absent."


def test_reused_nonce_hands_back_the_identical_signed_token(mock_platform: Any) -> None:
    """A real replay: the same bytes, not merely a matching `nonce` value.

    The second call arrives measurably later, so a cache that is doing real
    work is the only way the two `id_token`s — `iat` and all — can agree.
    """
    request = authorization_request(mock_platform)
    first_response = post_authorization(mock_platform, request, defect=REUSED_NONCE)
    first_id_token, _, _ = mock_platform.read_authorization_response(
        first_response, authorization_endpoint(mock_platform)
    )
    time.sleep(1.1)
    second_response = post_authorization(mock_platform, request, defect=REUSED_NONCE)
    second_id_token, _, _ = mock_platform.read_authorization_response(
        second_response, authorization_endpoint(mock_platform)
    )
    assert second_id_token == first_id_token, (
        "Two `reused_nonce` mints for the same `nonce`, over a second apart, produced different "
        "`id_token`s. `reused_nonce` is supposed to hand back the first mint's exact bytes — a "
        "fresh mint each time would be a duplicate nonce *value*, not a replayed token."
    )
    _, claims, _ = header_claims_and_signature(first_id_token)
    assert claims.get("nonce") == request["nonce"], "Canary: the cached token is the real one."
    assert mock_platform.verifies(first_id_token) is not None, "Canary: it is validly signed."


def test_unregistered_deployment_names_a_deployment_id_not_this_registration(
    mock_platform: Any,
) -> None:
    request, id_token, _ = mint(mock_platform, defect=UNREGISTERED_DEPLOYMENT)
    _, claims, _ = header_claims_and_signature(id_token)
    registered = request.get("lti_deployment_id")
    assert claims.get(DEPLOYMENT_ID_CLAIM) != registered, (
        f"`unregistered_deployment`'s deployment id claim is {claims.get(DEPLOYMENT_ID_CLAIM)!r}, "
        f"the same one the registration names ({registered!r})."
    )
    assert claims.get(DEPLOYMENT_ID_CLAIM) == "mock-lms-deployment-unregistered"
    assert mock_platform.verifies(id_token) is not None, "Canary: this is a validly signed token."


def test_unknown_message_type_names_a_type_this_platform_does_not_send_unprompted(
    mock_platform: Any,
) -> None:
    _, id_token, _ = mint(mock_platform, defect=UNKNOWN_MESSAGE_TYPE)
    _, claims, _ = header_claims_and_signature(id_token)
    assert claims.get(MESSAGE_TYPE_CLAIM) != RESOURCE_LINK_MESSAGE_TYPE
    assert claims.get(MESSAGE_TYPE_CLAIM) == "LtiDeepLinkingRequest"
    assert mock_platform.verifies(id_token) is not None, "Canary: this is a validly signed token."


def test_wrong_version_names_a_superseded_lti_version(mock_platform: Any) -> None:
    _, id_token, _ = mint(mock_platform, defect=WRONG_VERSION)
    _, claims, _ = header_claims_and_signature(id_token)
    assert claims.get(VERSION_CLAIM) != LTI_VERSION
    assert claims.get(VERSION_CLAIM) == "1.1.0"
    assert mock_platform.verifies(id_token) is not None, "Canary: this is a validly signed token."


# ---------------------------------------------------------------------------
# The return-leg defects: the `state` the response echoes, not the token.
# ---------------------------------------------------------------------------


def test_tampered_state_differs_from_the_requests_state_but_is_derived_from_it(
    mock_platform: Any,
) -> None:
    request, id_token, returned_state = mint(mock_platform, defect=TAMPERED_STATE)
    assert (
        returned_state != request["state"]
    ), f"`tampered_state` returned the request's own `state` unchanged ({returned_state!r})."
    assert request["state"] in returned_state, (
        "Canary: the returned `state` should still carry the request's real value somewhere in "
        "it, which is what shows this mock read the request rather than answering with a fixed "
        "string blind to it."
    )
    assert (
        mock_platform.verifies(id_token) is not None
    ), "Canary: `tampered_state` is a return-leg defect only — the id_token itself is untouched."


def test_missing_state_returns_no_state_on_the_return_leg(mock_platform: Any) -> None:
    request, id_token, returned_state = mint(mock_platform, defect=MISSING_STATE)
    assert returned_state == "", f"`missing_state` returned `state` {returned_state!r}, not empty."
    assert request["state"], "Canary: the request itself carried a real, non-empty `state`."
    assert (
        mock_platform.verifies(id_token) is not None
    ), "Canary: `missing_state` is a return-leg defect only — the id_token itself is untouched."


# ---------------------------------------------------------------------------
# The timestamp defects.
# ---------------------------------------------------------------------------


def test_iat_future_is_implausibly_ahead_of_now(mock_platform: Any) -> None:
    before = int(time.time())
    _, id_token, _ = mint(mock_platform, defect=IAT_FUTURE)
    _, claims, _ = header_claims_and_signature(id_token)
    iat = claims.get("iat")
    assert isinstance(iat, int), f"`iat_future`'s `iat` is {iat!r}, not an integer."
    assert (
        iat > before + IMPLAUSIBLE_MARGIN_SECONDS
    ), f"`iat_future`'s `iat` ({iat}) is not implausibly ahead of now ({before})."
    assert (
        claims.get("exp") - iat == TOKEN_LIFETIME_SECONDS
    ), "Canary: only `iat` should have moved — the token's own lifetime should be untouched."
    assert mock_platform.verifies(id_token) is not None, "Canary: this is a validly signed token."


def test_exp_past_is_implausibly_behind_now(mock_platform: Any) -> None:
    before = int(time.time())
    _, id_token, _ = mint(mock_platform, defect=EXP_PAST)
    _, claims, _ = header_claims_and_signature(id_token)
    exp = claims.get("exp")
    assert isinstance(exp, int), f"`exp_past`'s `exp` is {exp!r}, not an integer."
    assert (
        exp < before - IMPLAUSIBLE_MARGIN_SECONDS
    ), f"`exp_past`'s `exp` ({exp}) is not implausibly behind now ({before})."
    assert (
        exp - claims.get("iat") == TOKEN_LIFETIME_SECONDS
    ), "Canary: the token's own lifetime should be untouched — only where it sits in time moved."
    assert mock_platform.verifies(id_token) is not None, "Canary: this is a validly signed token."


# ---------------------------------------------------------------------------
# The near-miss and edge fixtures: valid launches, not wrong ones.
# ---------------------------------------------------------------------------


def test_only_teaching_assistant_role_carries_exactly_the_sub_role_urn(mock_platform: Any) -> None:
    """E1-10's near-miss: a URN containing "Instructor" that is not the Instructor role."""
    _, id_token, _ = mint(mock_platform, defect=ONLY_TEACHING_ASSISTANT_ROLE)
    _, claims, _ = header_claims_and_signature(id_token)
    assert claims.get(ROLES_CLAIM) == [
        TEACHING_ASSISTANT_SUB_ROLE_URN
    ], f"`only_teaching_assistant_role`'s roles claim is {claims.get(ROLES_CLAIM)!r}."
    assert "Instructor" in TEACHING_ASSISTANT_SUB_ROLE_URN, (
        "Sanity on this suite's own fixture: the whole point of this near-miss is that the URN "
        "contains the substring 'Instructor' while not being the Instructor role."
    )
    assert claims.get(CONTEXT_CLAIM, {}).get(
        "title"
    ), "Canary: this is otherwise a normal, fully-formed launch."
    assert (
        mock_platform.verifies(id_token) is not None
    ), "A near-miss fixture is a valid launch — it must still verify."


def test_only_mentor_role_carries_exactly_the_mentor_urn(mock_platform: Any) -> None:
    """E1-10's second near-miss: a real LIS role this system has no view for."""
    _, id_token, _ = mint(mock_platform, defect=ONLY_MENTOR_ROLE)
    _, claims, _ = header_claims_and_signature(id_token)
    assert claims.get(ROLES_CLAIM) == [
        MENTOR_ROLE_URN
    ], f"`only_mentor_role`'s roles claim is {claims.get(ROLES_CLAIM)!r}."
    assert claims.get(CONTEXT_CLAIM, {}).get(
        "title"
    ), "Canary: this is otherwise a normal, fully-formed launch."
    assert (
        mock_platform.verifies(id_token) is not None
    ), "A near-miss fixture is a valid launch — it must still verify."


def test_titleless_context_carries_id_alone(mock_platform: Any) -> None:
    """The E0-14 case Todd withdrew from the seed: `id` with no `title`, no `label`."""
    _, id_token, _ = mint(mock_platform, defect=TITLELESS_CONTEXT)
    _, claims, _ = header_claims_and_signature(id_token)
    context = claims.get(CONTEXT_CLAIM)
    assert isinstance(context, dict), f"`titleless_context`'s context claim is {context!r}."
    assert "title" not in context, "`titleless_context`'s context claim still carries `title`."
    assert "label" not in context, "`titleless_context`'s context claim still carries `label`."
    assert context.get("id"), "Canary: `id` — the one claim LTI 1.3 requires — is still present."
    assert (
        mock_platform.verifies(id_token) is not None
    ), "An edge fixture is a valid launch — it must still verify."
