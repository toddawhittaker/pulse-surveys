"""The OAuth 2.0 client-credentials grant, as an LTI platform issues one — E1-06.

A tool cannot call NRPS or AGS unauthenticated on any real platform. It asks the
platform's token endpoint for an access token, authenticating with a **client
assertion** — a short-lived JWT the tool signs with its own key (RFC 7523 §2.2) —
and attaches the token it is given to every service call. `pylti1p3`'s
`ServiceConnector` issues no service request at all without that sequence, so a
mock platform with no token endpoint is one no conformant client can be built
against. That is the whole of why E1-06 exists.

**The platform fetches the tool's key set to verify the assertion**, from
`PlatformSettings.tool_jwks_url`, on every token request. That is what a real
platform does with a registered tool's JWKS URL, and it is what makes the tool's
own `/lti/jwks` route (part 4 of this ticket) load-bearing rather than
decorative: a platform that verified nothing would grant a service token to
anyone who knows the client id, which is a value the launch form publishes.

**Verified with `app.signing`, which is this service's own arithmetic.** ADR 0035
bounds that to `mock-lms/`: these are throwaway keys for a fake platform. The
tool verifies with PyJWT (ADR 0073) and nothing here is copied there.

**What is refused, and with which RFC 6749 §5.2 code.** The codes matter because
E1-11's client is only conformant if nonconformance is distinguishable — one code
for every refusal tells a client nothing about whether it has a clock problem, a
key problem or a scope it was never granted:

  - `invalid_request` — the request or the assertion is missing something it must
    carry: no `client_assertion`, the wrong `client_assertion_type`, no `scope`,
    an assertion stating no `exp`.
  - `invalid_client` — an assertion arrived and does not authenticate the client:
    signed by a key the tool never published, addressed to something other than
    this token endpoint, expired, or claiming a lifetime past the bound below.
  - `invalid_scope` — a scope this platform does not advertise.
  - `unsupported_grant_type` — anything but `client_credentials`.
  - `invalid_grant` — the assertion authenticates the client perfectly and the
    *grant* it presents is one this endpoint will not honour: a `jti` already
    spent, or an `exp` further ahead than this platform's own clock allows. The
    distinction from `invalid_client` is one E1-11's client needs, because one of
    them means "mint a fresh assertion" and the other means "your clock is wrong".

**400 for all of them, including `invalid_client`.** RFC 6749 §5.2 makes 400 the
status of a refused token request and carves out one exception: a client that
"attempted to authenticate via the `Authorization` request header field" MUST be
answered 401. A `client_assertion` in the form body is not that, so the exception
does not apply.
"""

import secrets
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.ags import ADVERTISED_SCOPES as AGS_SCOPES
from app.config import PlatformSettings
from app.nrps import MEMBERSHIP_SCOPE
from app.signing import CompactJws, IssuerKey, JwsError

# The grant and the assertion profile, spelled as RFC 6749 §4.4 and RFC 7523 §2.2
# spell them. Specification constants: a platform accepting some other spelling
# is one no conformant client reaches.
CLIENT_CREDENTIALS_GRANT = "client_credentials"
JWT_BEARER_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

# The scope OIDC defines, which the launch flow already asks for. Kept at the
# head of the advertised list rather than replaced by the service scopes: a
# platform that swapped it would break the door it already serves.
OPENID_SCOPE = "openid"

# Every scope a token may be requested for, in one tuple, because the discovery
# document's `scopes_supported` and the token endpoint's own answer have to be
# the same list. Advertising a scope no token can be had for, or granting one the
# document does not advertise, are two halves of the same defect and one list is
# what makes both impossible.
#
# The strings themselves come from the services that name them — `app.ags` and
# `app.nrps` — rather than being written again here. A tool asks its token
# endpoint for the exact string a service claim carries, so a second copy that
# drifted would be a scope nothing can ever ask for.
ADVERTISED_SCOPES: tuple[str, ...] = (OPENID_SCOPE, *AGS_SCOPES, MEMBERSHIP_SCOPE)

# How the client authenticates at this endpoint, as OIDC Discovery 1.0 §3 names
# it. Advertised because it is what the endpoint actually accepts.
TOKEN_ENDPOINT_AUTH_METHOD = "private_key_jwt"  # noqa: S105 - a method name, not a credential

# RFC 6749 §5.2's error codes, the five this endpoint answers with.
INVALID_REQUEST = "invalid_request"
INVALID_CLIENT = "invalid_client"
INVALID_GRANT = "invalid_grant"
INVALID_SCOPE = "invalid_scope"
UNSUPPORTED_GRANT_TYPE = "unsupported_grant_type"

# How long a `client_assertion` may claim to live, in seconds. **Five minutes,
# and the bound is the point rather than the number.** A tool-signed assertion is
# a bearer credential: whoever holds it can spend it at this endpoint until it
# expires, so an assertion with an unbounded `exp` is a credential that stays
# usable wherever it leaks. Five minutes covers any clock skew a real deployment
# has and leaves nothing worth stealing. The IMS security framework recommends
# the same order of magnitude.
ASSERTION_LIFETIME_BOUND_SECONDS = 300

# How far past this platform's own clock an `exp` may sit, on top of the lifetime
# bound above. **Thirty seconds, and the allowance is the point rather than the
# number**: a tool whose clock is a little fast is an honest tool, and a clamp with
# no allowance refuses it. ADR 0084's consequences already warn about the
# direction ("a tool whose clock is more than five minutes fast is refused here").
ASSERTION_SKEW_ALLOWANCE_SECONDS = 30

# How long an issued access token lives. An hour is what LTI platforms issue in
# practice and what `ServiceConnector` caches against.
ACCESS_TOKEN_LIFETIME_SECONDS = 3600

# What RFC 6749 §7.1 calls a token a client presents as `Authorization: Bearer`.
BEARER_TOKEN_TYPE = "Bearer"  # noqa: S105 - a token type, not a credential


class TokenRequestError(Exception):
    """A refused token request, carrying the RFC 6749 §5.2 code that says why.

    The code is part of the refusal rather than chosen by the route, for the
    reason `app.ags`'s `GradeServiceError` carries its own status: which code
    answers is a fact about the rule that was broken and belongs beside it.
    """

    def __init__(self, error: str, description: str) -> None:
        super().__init__(description)
        self.error = error
        self.description = description

    def response(self) -> dict[str, str]:
        """The error body, as RFC 6749 §5.2 shapes one."""
        return {"error": self.error, "error_description": self.description}


@dataclass(frozen=True)
class AccessToken:
    """One issued access token and what a client needs to use it (RFC 6749 §5.1)."""

    access_token: str
    expires_in: int
    scope: str

    def response(self) -> dict[str, Any]:
        """The token response, with `expires_in` as a number rather than a string.

        A client caches a token against `expires_in` and does arithmetic on it,
        so `"3600"` is a near miss every client that does none accepts.
        """
        return {
            "access_token": self.access_token,
            "token_type": BEARER_TOKEN_TYPE,
            "expires_in": self.expires_in,
            "scope": self.scope,
        }


def requested_scopes(form: Mapping[str, str]) -> list[str]:
    """The scopes this request asks for, refusing one this platform does not serve.

    RFC 6749 §3.3 makes `scope` a space-delimited list. Every element has to be
    advertised: a token endpoint that granted whatever it was asked for would make
    `scopes_supported` decoration, and the scope a token carries is what a service
    checks before it acts — so a platform granting `…/scope/score` to a tool never
    authorised for it has handed out the ability to write grades.
    """
    asked = str(form.get("scope", "")).split()
    if not asked:
        raise TokenRequestError(
            INVALID_REQUEST,
            "The token request states no `scope`. RFC 6749 §4.4.2 makes it OPTIONAL for the "
            "grant, and this platform requires it: an access token here is only ever presented "
            "to a service that checks the scope it carries.",
        )
    unadvertised = [scope for scope in asked if scope not in ADVERTISED_SCOPES]
    if unadvertised:
        raise TokenRequestError(
            INVALID_SCOPE,
            f"This platform does not serve the scope(s) {unadvertised}. It advertises "
            f"{list(ADVERTISED_SCOPES)} in its discovery document, and grants no token for "
            "anything outside that list.",
        )
    return asked


def presented_assertion(form: Mapping[str, str]) -> CompactJws:
    """The `client_assertion` this request carries, parsed but not yet believed.

    A missing parameter is `invalid_request` rather than `invalid_client`: nothing
    arrived to authenticate the client with, so the request is malformed rather
    than the client unauthenticated, and that distinction is what tells a client
    it built the request wrongly rather than signed it wrongly.
    """
    assertion_type = form.get("client_assertion_type", "")
    if assertion_type != JWT_BEARER_ASSERTION_TYPE:
        raise TokenRequestError(
            INVALID_REQUEST,
            f"The token request states `client_assertion_type` {assertion_type!r}. This platform "
            f"authenticates a client by the RFC 7523 §2.2 profile, {JWT_BEARER_ASSERTION_TYPE!r}.",
        )
    assertion = form.get("client_assertion", "")
    if not assertion:
        raise TokenRequestError(
            INVALID_REQUEST,
            "The token request carries no `client_assertion`. A client authenticates at this "
            "endpoint with a JWT it signed itself; there is nothing here to authenticate it by.",
        )
    try:
        return CompactJws.parse(assertion)
    except JwsError as failure:
        raise TokenRequestError(
            INVALID_REQUEST, f"The `client_assertion` is not a compact JWS: {failure}"
        ) from None


def tool_key_set(settings: PlatformSettings, http: Any) -> list[Mapping[str, Any]]:
    """The tool's published key set, fetched now rather than held from startup.

    Fetched per request, deliberately. A cache is what a real platform has and it
    is also what makes a key rotation invisible for its lifetime; this platform
    exists to be verified against, and one HTTP call on a development machine buys
    nothing worth the extra state.

    A key set this platform cannot fetch is `invalid_client` rather than a 500:
    the platform is working and the client cannot be authenticated, which is
    exactly what that code says. The URL is named in the description because the
    likeliest cause is that it is configured wrongly, and a refusal that does not
    say which address it tried is an afternoon.
    """
    try:
        response = http.get(settings.tool_jwks_url)
        response.raise_for_status()
        document = response.json()
    # Any failure of that fetch is the same refusal: a connection refused, a
    # timeout, a 404 and a body that is not JSON all leave this platform with
    # nothing to verify against, and none of them is the caller's to diagnose.
    except Exception as failure:
        raise TokenRequestError(
            INVALID_CLIENT,
            f"This platform could not fetch the tool's key set from {settings.tool_jwks_url!r} "
            f"({type(failure).__name__}: {failure}), so the `client_assertion` cannot be "
            "verified against anything.",
        ) from None
    keys = document.get("keys") if isinstance(document, dict) else None
    if not isinstance(keys, list) or not keys:
        raise TokenRequestError(
            INVALID_CLIENT,
            f"The tool's key set at {settings.tool_jwks_url!r} carries no `keys`. RFC 7517 §5 "
            "makes a key set a JSON object with an array of JWK values, and there is nothing "
            "here to verify a signature with.",
        )
    return [key for key in keys if isinstance(key, Mapping)]


def verified_assertion(
    assertion: CompactJws, settings: PlatformSettings, http: Any
) -> Mapping[str, Any]:
    """Check the assertion against the tool's key set and this platform's rules.

    In this order, and the order is what makes each refusal say what it means:
    the signature first, because claims read off an unverified token are claims
    anybody wrote; then who it says it is, then who it is addressed to, then how
    long it lives.

    **Every key in the set is tried rather than the one the header names.** A
    platform that selects by `kid` and then trusts the token because a key was
    found has authenticated nobody, and selecting by `kid` buys nothing here: the
    tool publishes one key (ADR 0082), and a wrong `kid` beside a valid signature
    is a tool that has rotated, not an impostor.
    """
    keys = tool_key_set(settings, http)
    if not any(assertion.verifies_with(key) for key in keys):
        raise TokenRequestError(
            INVALID_CLIENT,
            "The `client_assertion` is not signed by any key in the set the tool publishes at "
            f"{settings.tool_jwks_url!r}. The signature is the whole of the authentication here — "
            "a client id is a value this platform's own launch form publishes.",
        )

    claims = assertion.claims
    if claims.get("iss") != settings.client_id or claims.get("sub") != settings.client_id:
        raise TokenRequestError(
            INVALID_CLIENT,
            f"The `client_assertion` states `iss` {claims.get('iss')!r} and `sub` "
            f"{claims.get('sub')!r}. RFC 7523 §3 makes both the client's own identifier, and this "
            f"platform has registered exactly one tool, {settings.client_id!r}.",
        )

    audience = claims.get("aud")
    addressed = audience if isinstance(audience, list) else [audience]
    if settings.token_url not in addressed:
        raise TokenRequestError(
            INVALID_CLIENT,
            f"The `client_assertion` is addressed to {audience!r} rather than to this token "
            f"endpoint, {settings.token_url!r}. The audience is what stops an assertion being "
            "replayed: a tool holds one key and talks to several platforms, so one accepted "
            "here that was minted for another lets this platform spend it there.",
        )

    expires_at = claims.get("exp")
    if not isinstance(expires_at, int | float) or isinstance(expires_at, bool):
        raise TokenRequestError(
            INVALID_REQUEST,
            f"The `client_assertion` states `exp` {expires_at!r}. RFC 7523 §3 makes it REQUIRED "
            "and a number of seconds; an assertion with no expiry is a credential with no end, "
            "usable by whoever holds it for as long as this platform runs.",
        )
    now = time.time()
    if expires_at <= now:
        raise TokenRequestError(
            INVALID_CLIENT,
            f"The `client_assertion` expired at {int(expires_at)} and it is now {int(now)}.",
        )

    # **The wall-clock clamp**, and it is a separate rule from the lifetime bound
    # below rather than a restatement of it. `exp` and `iat` are *both* the
    # signer's own statements, so a signer who dates both claims into the future
    # mints an assertion that passes the expiry check above and measures a lifetime
    # of zero — a credential with a five-minute stated life and an unbounded real
    # one. ADR 0084 measured that hole; this is the platform comparing `exp`
    # against its own clock instead of against the assertion's arithmetic.
    ceiling = now + ASSERTION_LIFETIME_BOUND_SECONDS + ASSERTION_SKEW_ALLOWANCE_SECONDS
    if expires_at > ceiling:
        raise TokenRequestError(
            INVALID_GRANT,
            f"The `client_assertion` expires at {int(expires_at)}, which is further ahead than "
            f"this platform's own clock allows: at most {ASSERTION_LIFETIME_BOUND_SECONDS} "
            f"seconds of lifetime plus {ASSERTION_SKEW_ALLOWANCE_SECONDS} seconds of clock skew, "
            f"so no later than {int(ceiling)}. An assertion whose `iat` and `exp` are both dated "
            "forward states a short lifetime and is usable for as long as it says it is.",
        )

    issued_at = claims.get("iat")
    started = (
        issued_at if isinstance(issued_at, int | float) and not isinstance(issued_at, bool) else now
    )
    lifetime = expires_at - started
    if lifetime > ASSERTION_LIFETIME_BOUND_SECONDS:
        raise TokenRequestError(
            INVALID_CLIENT,
            f"The `client_assertion` claims a lifetime of {int(lifetime)} seconds and this "
            f"platform accepts at most {ASSERTION_LIFETIME_BOUND_SECONDS}. A tool-signed bearer "
            "assertion with a long life is a credential that stays usable wherever it leaks; "
            "mint one per request instead.",
        )

    # **The replay check comes last**, after the assertion has been proved to be
    # this client's, addressed here, and inside both time bounds. A store that
    # recorded every `jti` it was shown would let anybody fill it by posting
    # unsigned junk, and would refuse the tool's own next request if a passing
    # attacker guessed a value it was about to use.
    identifier = claims.get("jti")
    if not isinstance(identifier, str) or not identifier:
        raise TokenRequestError(
            INVALID_REQUEST,
            f"The `client_assertion` states `jti` {identifier!r}. RFC 7523 §3 makes it REQUIRED "
            "and it is what lets this platform refuse a replay; an assertion without one cannot "
            "be told from a second presentation of itself.",
        )
    if not SEEN_ASSERTIONS.claim(identifier, now=now):
        raise TokenRequestError(
            INVALID_GRANT,
            f"The `client_assertion` with `jti` {identifier!r} has already been granted a token. "
            "RFC 7523 §3 makes that identifier one-use, and an endpoint that honoured a replay "
            "would make a captured assertion worth a token to whoever holds it, for as long as "
            "it lives. Mint a fresh assertion per request.",
        )
    return claims


class SeenAssertions:
    """The `jti` values this platform has already granted a token for.

    **An assertion is a bearer credential for as long as it lives**, so an endpoint
    that cannot notice a replay is one where a captured assertion is worth a token
    to whoever holds it, however often. ADR 0084's own security-review paragraph
    records exactly that gap — "with `jti` untracked — [it] stays spendable until
    its far-future `exp`" — and E1-11 closes it, because a client's conformance
    claims otherwise rest on an endpoint that cannot tell a replay from a request.

    **In process, deliberately.** A store that survived a restart would need a
    database, and a mock with one behaves differently after a restart, which is the
    thing this platform exists not to do. What it costs is stated rather than
    hidden: restarting the platform forgets every `jti`, so a captured assertion is
    spendable once more across a restart. On a development stack that is a
    reasonable trade; a real platform keeps the store where its tokens are.

    **Entries live at least as long as an assertion may**, which is what makes
    forgetting safe: a `jti` older than the lifetime bound belongs to an assertion
    this endpoint already refuses for being expired, so remembering it buys nothing.
    Pruning happens on the way in rather than on a timer, because a mock with a
    background task is a mock with a shutdown problem.
    """

    def __init__(self, lifetime: int = ASSERTION_LIFETIME_BOUND_SECONDS) -> None:
        self._lifetime = lifetime
        self._seen: dict[str, float] = {}

    def claim(self, jti: str, *, now: float) -> bool:
        """Record `jti` as spent, and answer whether it was fresh."""
        self._seen = {seen: at for seen, at in self._seen.items() if at > now - self._lifetime}
        if jti in self._seen:
            return False
        self._seen[jti] = now
        return True


# The one store, at module scope, because `granted_token` is called from a route
# that holds no state of its own and a store threaded through four signatures would
# be four places to forget it. Two platform instances in one process share it,
# which is a difference from a real deployment and not one a `jti` can notice: RFC
# 7523 makes the value unique per assertion, and every client that mints one uses a
# UUID or equivalent.
SEEN_ASSERTIONS = SeenAssertions()


def issued_token(settings: PlatformSettings, key: IssuerKey, scopes: list[str]) -> AccessToken:
    """Mint an access token for `scopes`, signed by this platform's issuer key.

    **A signed JWS rather than an opaque string**, and the difference matters
    exactly once: when a service on this platform starts requiring a token
    (E1-11), it can check one without this process having remembered anything.
    An opaque random string would need a store, and a mock with a store is a mock
    that behaves differently after a restart.

    The scope granted is the scope asked for, always: `requested_scopes` has
    already refused anything this platform does not serve, so there is no case
    where a client asks for one thing and is quietly given another.
    """
    issued = int(time.time())
    return AccessToken(
        access_token=key.compact_jws(
            {
                "iss": settings.issuer,
                "sub": settings.client_id,
                "aud": settings.issuer,
                "jti": secrets.token_urlsafe(16),
                "iat": issued,
                "exp": issued + ACCESS_TOKEN_LIFETIME_SECONDS,
                "scope": " ".join(scopes),
            }
        ),
        expires_in=ACCESS_TOKEN_LIFETIME_SECONDS,
        scope=" ".join(scopes),
    )


def granted_token(
    form: Mapping[str, str], settings: PlatformSettings, key: IssuerKey, http: Any
) -> AccessToken:
    """One client-credentials grant, from a posted form to an issued token.

    Raises `TokenRequestError` for every refusal, which the route turns into the
    400 and the JSON body RFC 6749 §5.2 describes.
    """
    grant_type = form.get("grant_type", "")
    if grant_type != CLIENT_CREDENTIALS_GRANT:
        raise TokenRequestError(
            UNSUPPORTED_GRANT_TYPE,
            f"This platform issues tokens for the {CLIENT_CREDENTIALS_GRANT!r} grant and the "
            f"request asks for {grant_type!r}. LTI Advantage services are reached with that grant "
            "and no other.",
        )
    scopes = requested_scopes(form)
    verified_assertion(presented_assertion(form), settings, http)
    return issued_token(settings, key, scopes)
