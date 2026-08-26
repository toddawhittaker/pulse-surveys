"""Deliberately wrong launches, selected by name — E1-07.

E0-25 item 5, carried out of E0 with E1 as owner: "the mock LMS cannot mint a
deliberately wrong launch — tool-side launch validation is E1's, and E0-14
defined no interface for a bad launch deliberately." E1-08 (heavy) proves the
tool refuses bad launches; a driver that could only speak correctly would leave
the invalid half of every one of those guards untestable
(`docs/MISTAKES.md` entry 28, this module's reason to exist).

**Consumed by name, not by shape.** E1-08's Playwright specs, and any other
future driver, select a mint the way `?defect=foreign_signature` reads: one
string naming the defect. The strings in `WRONG_DEFECTS` and
`NEAR_MISS_FIXTURES` below are that vocabulary, and `main.py`'s authorization
route is the only place either tuple is read against a request.

**One defect per mint, always.** A launch wrong two ways is two tests that
cannot tell which guard fired — the ticket's own rule, and MISTAKES 28's
spirit read literally: a mint that combines `wrong_aud` and `alg_none` tells
E1-08 nothing about which check refused it.

**Everything here is additive.** `mint` is called only when a request names a
defect; the authorization route in `main.py` takes the exact code path it took
before this module existed when it does not, so a correct launch is unaffected
byte for byte. See ADR 0088 for the selector shape and the one-sentence-worthy
mechanism behind `reused_nonce`.

**Where the arithmetic lives.** `foreign_signature` and `right_key_tampered_
claims` both reuse `IssuerKey.compact_jws` and ordinary string surgery — no new
signing. `alg_none` and `hs256_confusion` are the two mints that build a compact
JWS this platform's own key never signs in the normal sense, and that
construction lives in `app.signing` (`unsigned_compact_jws`,
`hs256_compact_jws`) rather than here, on ADR 0035's rule: the standard-library
arithmetic belongs beside the arithmetic it sits next to, not scattered across
whichever module first needed a JWS with a different shape.
"""

import time
from dataclasses import dataclass
from typing import Any

from app.config import PlatformSettings
from app.launch import (
    CONTEXT_CLAIM,
    DEPLOYMENT_ID_CLAIM,
    MESSAGE_TYPE_CLAIM,
    ROLES_CLAIM,
    VERSION_CLAIM,
    AuthorizationRequestError,
    ResolvedLaunch,
    id_token_claims,
)
from app.seed import MEMBERSHIP_ROLE
from app.signing import (
    IssuerKey,
    compact_jws_header_and_claims,
    hs256_compact_jws,
    unsigned_compact_jws,
)

# The query parameter `main.py`'s authorization route reads. One name, so a
# request that omits it takes the untouched happy path and a request that sets
# it selects exactly one of the strings below.
DEFECT_QUERY_PARAM = "defect"

# -- The fifteen ways a launch is wrong --------------------------------------
#
# Spelled to read as the defect, because these are the names a Playwright spec
# — E1-08's, or any later one — selects by.
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

WRONG_DEFECTS: tuple[str, ...] = (
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
)

# -- The three near-miss and edge fixtures: valid launches, not wrong ones ---
#
# Same selector, same vocabulary, because E1-10 and E1-08 ask for these the
# same way they ask for a wrong one. What each mints is syntactically and
# semantically a launch this platform would sign unprompted for a real seeded
# enrollment — only the shape of one claim is chosen rather than resolved from
# the seed.
ONLY_TEACHING_ASSISTANT_ROLE = "only_teaching_assistant_role"
ONLY_MENTOR_ROLE = "only_mentor_role"
TITLELESS_CONTEXT = "titleless_context"

NEAR_MISS_FIXTURES: tuple[str, ...] = (
    ONLY_TEACHING_ASSISTANT_ROLE,
    ONLY_MENTOR_ROLE,
    TITLELESS_CONTEXT,
)

# Every name the selector answers to, wrong and near-miss together — the set
# `main.py` refuses outside of, and the set a completeness test in
# `tests/integration/test_mock_lms_wrong_launches.py` walks.
ALL_SELECTORS: tuple[str, ...] = WRONG_DEFECTS + NEAR_MISS_FIXTURES

# The TeachingAssistant sub-role URN, copied whole from the ticket rather than
# assembled from `MEMBERSHIP_ROLE` — it is not a member of that vocabulary's
# stem, it is IMS's own sub-role form, `<role>/<parent>#<sub-role>`, and a
# concatenation here would be the retype `docs/MISTAKES.md` entry 3 warns
# against. This is the string E1-10's exact-match guard is built to survive
# despite it containing "Instructor".
TEACHING_ASSISTANT_SUB_ROLE_URN = (
    "http://purl.imsglobal.org/vocab/lis/v2/membership/Instructor#TeachingAssistant"
)

# The Mentor role, built the same way `tests/integration/test_lti_launch_door.py`
# builds `MENTOR_ROLE_URI` — off the same base every ordinary membership role
# in this mock uses, `app.seed.MEMBERSHIP_ROLE` — because Mentor, unlike the
# TeachingAssistant sub-role above, *is* a plain member of that vocabulary.
MENTOR_ROLE_URN = f"{MEMBERSHIP_ROLE}Mentor"

# Values a real registration would never carry, all at a domain RFC 2606
# reserves so nothing here can be mistaken for a live address.
WRONG_AUD_VALUE = "https://wrong-client.mock-lms.invalid"
WRONG_ISS_VALUE = "https://wrong-issuer.mock-lms.invalid"
UNREGISTERED_DEPLOYMENT_ID = "mock-lms-deployment-unregistered"

# A real LTI 1.3 message type this platform does not implement (Deep Linking is
# out of scope — the epic README's not-do list), rather than an invented
# string: the defect is "a message type the registration does not accept", and
# a conformant tool has to be able to recognise this one as LTI and still
# refuse it.
UNKNOWN_MESSAGE_TYPE_VALUE = "LtiDeepLinkingRequest"

# A real, superseded LTI version string. `app.launch.LTI_VERSION` is `"1.3.0"`;
# this is the version LTI 1.3 replaced, not a made-up one.
WRONG_VERSION_VALUE = "1.1.0"

# How far outside any plausible clock-skew window `iat_future` and `exp_past`
# push a timestamp. **This module's choice.** §9.1 names clock skew as one of
# the cases E1's launch validation covers, but the tolerance itself is E1-08's
# to set; an hour is past any tolerance a five-minute-lifetime token would
# plausibly carry, so the fixture stays a clear miss whatever E1-08 lands on.
CLOCK_SKEW_MARGIN_SECONDS = 3600

# The suffix `tampered_state` appends to a genuine `state`, rather than
# replacing it outright — a test can then assert the returned value both
# differs from the request's `state` and still carries it, which is what shows
# the mock actually read the request rather than emitting a fixed string blind
# to it.
TAMPERED_STATE_SUFFIX = "-tampered-by-mock-lms"


@dataclass(frozen=True)
class MintedResponse:
    """What `main.py` needs to answer a defect-selected authorization request.

    Both halves of the `authorization_response_page` form: the `id_token` and
    the `state` it echoes. Most defects change one and leave the other exactly
    what a correct launch would have carried, and this type is what lets
    `mint` say which without the route having to know each defect's shape.
    """

    id_token: str
    state: str


class WrongLaunchMinter:
    """Mints one wrong (or near-miss) launch per call, selected by name.

    **One instance per running platform**, created in `main.py` beside the
    issuer key it signs most of its defects with, for the same reason
    `app.ags.GradeBook` is one-per-app (ADR 0049): `reused_nonce` remembers a
    previously minted token for as long as this process runs and no longer,
    and `foreign_signature`'s key is generated once, lazily, and reused rather
    than paid for on every call.
    """

    def __init__(self, key: IssuerKey) -> None:
        self._key = key
        self._foreign_key: IssuerKey | None = None
        self._replayed: dict[str, str] = {}

    def foreign_key(self) -> IssuerKey:
        """A key never published in this platform's own JWKS, generated once.

        Lazy, so a platform started for a test that never asks for
        `foreign_signature` never pays `IssuerKey.generate()`'s ~0.3 second
        cost (ADR 0035's consequences) for a key nothing will use. Cached
        after that, so a suite that asks for this mint more than once pays it
        once per platform rather than once per request.
        """
        if self._foreign_key is None:
            self._foreign_key = IssuerKey.generate()
        return self._foreign_key

    def mint(
        self, name: str, resolved: ResolvedLaunch, settings: PlatformSettings
    ) -> MintedResponse:
        """The one mint `name` selects, or a refusal naming the valid selectors.

        Dispatches on the constants above; every branch returns a
        `MintedResponse` built from `resolved` and `settings`, the same two
        values a correct launch is built from, so nothing about the defect
        depends on anything a caller supplies beyond the name itself.
        """
        if name not in ALL_SELECTORS:
            raise AuthorizationRequestError(
                f"`{DEFECT_QUERY_PARAM}` names {name!r}, which is not one of this platform's "
                f"selectors. The wrong launches are {list(WRONG_DEFECTS)}; the near-miss and edge "
                f"fixtures are {list(NEAR_MISS_FIXTURES)}."
            )

        claims = id_token_claims(resolved, settings)
        state = resolved.state

        if name == FOREIGN_SIGNATURE:
            id_token = self.foreign_key().compact_jws(claims)
        elif name == RIGHT_KEY_TAMPERED_CLAIMS:
            id_token = self._right_key_tampered_claims(claims)
        elif name == ALG_NONE:
            id_token = unsigned_compact_jws(claims)
        elif name == HS256_CONFUSION:
            id_token = hs256_compact_jws(claims, self._key.public_key_material(), self._key.key_id)
        elif name == WRONG_AUD:
            id_token = self._signed({**claims, "aud": WRONG_AUD_VALUE})
        elif name == WRONG_ISS:
            id_token = self._signed({**claims, "iss": WRONG_ISS_VALUE})
        elif name == MISSING_NONCE:
            without_nonce = dict(claims)
            del without_nonce["nonce"]
            id_token = self._signed(without_nonce)
        elif name == REUSED_NONCE:
            id_token = self._reused_nonce(claims, resolved.nonce)
        elif name == UNREGISTERED_DEPLOYMENT:
            id_token = self._signed({**claims, DEPLOYMENT_ID_CLAIM: UNREGISTERED_DEPLOYMENT_ID})
        elif name == UNKNOWN_MESSAGE_TYPE:
            id_token = self._signed({**claims, MESSAGE_TYPE_CLAIM: UNKNOWN_MESSAGE_TYPE_VALUE})
        elif name == WRONG_VERSION:
            id_token = self._signed({**claims, VERSION_CLAIM: WRONG_VERSION_VALUE})
        elif name == TAMPERED_STATE:
            id_token = self._signed(claims)
            state = f"{resolved.state}{TAMPERED_STATE_SUFFIX}"
        elif name == MISSING_STATE:
            id_token = self._signed(claims)
            state = ""
        elif name == IAT_FUTURE:
            future = int(time.time()) + CLOCK_SKEW_MARGIN_SECONDS
            id_token = self._signed(id_token_claims(resolved, settings, issued_at=future))
        elif name == EXP_PAST:
            past = int(time.time()) - CLOCK_SKEW_MARGIN_SECONDS - _token_lifetime(claims)
            id_token = self._signed(id_token_claims(resolved, settings, issued_at=past))
        elif name == ONLY_TEACHING_ASSISTANT_ROLE:
            id_token = self._signed({**claims, ROLES_CLAIM: [TEACHING_ASSISTANT_SUB_ROLE_URN]})
        elif name == ONLY_MENTOR_ROLE:
            id_token = self._signed({**claims, ROLES_CLAIM: [MENTOR_ROLE_URN]})
        else:  # name == TITLELESS_CONTEXT — the only selector left, per the guard above
            context_claim = dict(claims[CONTEXT_CLAIM])
            del context_claim["title"]
            del context_claim["label"]
            id_token = self._signed({**claims, CONTEXT_CLAIM: context_claim})

        return MintedResponse(id_token=id_token, state=state)

    def _signed(self, claims: dict[str, Any]) -> str:
        """Every defect that is still a validly-signed, RS256 launch."""
        return self._key.compact_jws(claims)

    def _right_key_tampered_claims(self, claims: dict[str, Any]) -> str:
        """Sign for real, then swap the payload for one the signature never covered.

        The header and the signature both come out of a genuine
        `compact_jws` call — the `kid` really is this platform's, and the
        bytes really are a valid RS256 signature, just not over the payload
        the token now carries. `sub` is the claim that changes: a launch
        whose subject was rewritten after signing is the shape a forged
        impersonation takes, which is the sharpest version of "the signature
        no longer matches" to assert against.
        """
        correct = self._key.compact_jws(claims)
        encoded_header, _, encoded_signature = correct.split(".")
        tampered = {**claims, "sub": f"{claims['sub']}-tampered"}
        joined, _ = compact_jws_header_and_claims(
            {"alg": "RS256", "typ": "JWT", "kid": self._key.key_id}, tampered
        )
        _, tampered_encoded_claims = joined.split(".")
        return f"{encoded_header}.{tampered_encoded_claims}.{encoded_signature}"

    def _reused_nonce(self, claims: dict[str, Any], nonce: str) -> str:
        """The same signed bytes as the previous mint for this `nonce`, if any.

        First call for a given `nonce` mints and remembers a correct token;
        every later call with that same `nonce` — however much later, whatever
        else about the request — is handed back the identical bytes rather
        than a fresh mint. That is the difference between "a duplicate nonce
        value" and "the same signed artifact, replayed", and it is why the
        second answer's `iat`/`exp` are the *first* call's, not `time.time()`
        run again. Mock-process-local: `self._replayed` lives as long as this
        platform's application object, per ADR 0088.
        """
        cached = self._replayed.get(nonce)
        if cached is not None:
            return cached
        minted = self._signed(claims)
        self._replayed[nonce] = minted
        return minted


def _token_lifetime(claims: dict[str, Any]) -> int:
    """`exp - iat` off an already-built claims dict, so `exp_past` stays exact.

    Read off the claims rather than importing `app.launch.TOKEN_LIFETIME_
    SECONDS` a second time: the two are already the same value by
    construction, and computing it this way means a future change to the
    lifetime constant cannot make `exp_past` mint an `exp` that is not, in
    fact, past.
    """
    return int(claims["exp"]) - int(claims["iat"])
