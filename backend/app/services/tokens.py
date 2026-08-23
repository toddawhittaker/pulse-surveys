"""Verifying somebody else's signed token against the key set they publish.

Both entry doors do this and they do it identically: an LTI 1.3 launch arrives
as an `id_token` signed by the platform, and a web login's `id_token` arrives
from the provider's token endpoint. In both cases the tool holds no key — it
fetches the issuer's published JWK Set and checks the signature against it.

**This is not one of SPEC §8's identity-separated read paths, so it is one
function rather than two.** The duplication that section's separation requires is
between paths that reach a *name*; this reaches a signature. Two copies of a signature
check is two places for the `verify_signature=False` that somebody adds while
debugging, which is the failure worth designing against here.

Three rules the implementation holds, each of which is a real defect if dropped:

* **The algorithm comes from this module, never from the token.** `alg` is a
  header field an attacker writes, and a verifier that trusts it accepts `none`
  or accepts an HMAC computed with the public key as its secret. `algorithms=`
  is passed explicitly on every call.
* **`iss` and `aud` are checked, not read.** OIDC Core 1.0 §3.1.3.7 requires
  both. Without the issuer check, any provider this tool can reach mints
  sessions for it; without the audience check, a token issued for a different
  tool on the same platform opens this one.
* **Every fetch goes through the caller's HTTP client**, which is
  `app.state.http`. PyJWT ships `PyJWKClient`, which opens its own `urllib`
  connection with its own timeout and its own cache — a second, invisible way
  out of the process, unreachable from any test and unaffected by any timeout
  this application sets. E0-18's whole seam is that one client makes every
  outbound call.

**`state` and `nonce` are compared here too**, by `same_opaque_value`, and that
is a deliberate widening of what this module is about. Deciding whether a token
is one this tool asked for has two halves — the signature says who wrote it, and
the echoed opaque values say this tool started the flow it came back from — and
both doors do both. Four call sites compared them with `secrets.compare_digest`
on `str`, which **raises `TypeError` rather than answering `False`** as soon as
either side holds a character outside ASCII, and a caller can put one there. That
hazard living in four places, fixed in one of them, is `docs/MISTAKES.md` entry
13; so the comparison is a function, and it takes bytes.

**No refusal message names an address this tool fetched.** A key set URL is a
server-side address — a Compose service name in this stack — and the browser that
receives a refusal page is the one that provoked the fetch. Naming it there hands
whoever asked a piece of the network map behind the tool, so the messages below
say what failed and not where. Nothing logs it either: `backend/app` has no
logging yet, and inventing a logger in an authentication change is a bigger
decision than this one. The address is not lost — it is the `jwks_url` on the
platform's registration row and the `OIDC_JWKS_URL` setting, which is where
somebody debugging a failed fetch already has to look.

**No key set is cached.** A launch fetches the platform's JWKS every time, which
is one extra request per launch and no correctness question at all: a cache has
to decide what happens when a platform rotates a key, and E0-18 has no launch
volume to justify answering that. `lti_platform.jwks_fetched_at` is the column
that would record such a fetch, and nothing writes it — see `app.lti.launch`.
"""

import secrets
from collections.abc import Mapping, Sequence
from typing import Any

import httpx
import jwt

__all__ = ["TokenVerificationError", "same_opaque_value", "verified_claims"]

# The only signature algorithm either door accepts. RS256 is what the IMS
# security framework specifies for an LTI 1.3 launch and what E0-16's provider
# advertises, and an asymmetric algorithm is the only kind that makes sense for a
# token this tool verifies and does not issue.
SIGNATURE_ALGORITHMS = ("RS256",)

# Claims a token must carry before anything reads one. `exp` is the one that
# matters most — PyJWT only compares an expiry that is *present*, so a token
# with no `exp` at all is valid forever unless it is required here.
REQUIRED_CLAIMS = ("iss", "sub", "aud", "exp", "iat")

# How long the tool waits for an issuer's key set. Not a setting: there is one
# correct answer for a request made inside a browser redirect, and a knob for it
# would only ever be turned up.
KEY_SET_TIMEOUT_SECONDS = 10.0


class TokenVerificationError(Exception):
    """A token was not accepted, and why in words a person can act on.

    Carries no part of the token and no claim value. The reason reaches a
    refusal page and a log line, and a token is a credential: quoting one back
    is how a launch that failed for somebody else's session ends up in an access
    log (SPEC §10).
    """


def same_opaque_value(delivered: str, issued: str) -> bool:
    """Is the `state` or `nonce` that came back the one this tool sent?

    **Compared as bytes.** `secrets.compare_digest` accepts two `str` only while
    both are ASCII, and raises `TypeError` on anything else — so a caller who puts
    `é` in a `state` takes a door that compares text out through the error handler
    instead of through its refusal. That is fail-closed, and it is still a defect:
    the request gets no page, and everything the refusal path does on the way out
    does not happen. On both doors that includes clearing the single-use cookie,
    which leaves a browser holding a `state` an attacker may keep trying against.

    Encoding first is the whole fix. `str.encode` has an answer for every string,
    the comparison then has an answer for every pair, and the caller's refusal is
    reached the ordinary way.

    Still constant-time, which is the reason `compare_digest` is here at all: an
    equality that returns early tells a caller how much of a guessed `state` was
    right, one character at a time.
    """
    return secrets.compare_digest(delivered.encode("utf-8"), issued.encode("utf-8"))


def key_set(http: httpx.Client, jwks_url: str) -> Mapping[str, Any]:
    """Fetch a published JWK Set, or refuse saying what about it failed.

    The URL is one this tool stored or was configured with, never one read out
    of the token being checked: a verifier that fetched the key set an unverified
    token named would verify every forgery against its forger's own key.

    **No refusal below names `jwks_url`.** These messages reach `refusal_page`,
    and the caller reading that page is the one who provoked the fetch — see the
    module docstring for where the address is instead.
    """
    try:
        response = http.get(jwks_url, timeout=KEY_SET_TIMEOUT_SECONDS)
    except httpx.HTTPError as failure:
        raise TokenVerificationError(
            f"The issuer's published key set could not be fetched ({type(failure).__name__}), "
            "so the signature could not be checked."
        ) from failure
    if response.status_code != 200:
        raise TokenVerificationError(
            f"The issuer's published key set answered {response.status_code}, so there is no "
            "key to check the signature against."
        )
    try:
        document = response.json()
    except ValueError as failure:
        raise TokenVerificationError(
            "The issuer's published key set is not JSON, so it is not a JWK Set (RFC 7517)."
        ) from failure
    if not isinstance(document, dict) or not isinstance(document.get("keys"), list):
        raise TokenVerificationError(
            "The document the issuer publishes as its key set carries no `keys` array, so it is "
            "not a JWK Set (RFC 7517)."
        )
    return document


def signing_key(document: Mapping[str, Any], token: str) -> Any:
    """The published key the token's `kid` names, as something PyJWT can verify with.

    A key set holds more than one key while an issuer is rotating, and the `kid`
    header is how a token says which one signed it. A verifier that tried every
    key would still be correct — any one of them verifying is a valid signature
    — so this is about failing clearly rather than about security: "no key in the
    set has that `kid`" is a rotation that has half happened, and it should say
    so rather than report a bad signature.

    A set with exactly one key and a token with no `kid` is the ordinary case for
    a small platform, and it is served rather than refused.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as failure:
        raise TokenVerificationError(
            "The token's header could not be read, so it is not a well-formed JWS."
        ) from failure

    try:
        published = jwt.PyJWKSet.from_dict(dict(document))
    except jwt.PyJWTError as failure:
        # `PyJWKSetError` and `PyJWKError` are siblings under `PyJWTError` rather
        # than one under the other, so the parent is what catches both.
        raise TokenVerificationError(
            "The issuer's key set could not be read as JWKs (RFC 7517)."
        ) from failure

    usable = [key for key in published.keys if key.public_key_use in ("sig", None)]
    if not usable:
        raise TokenVerificationError("The issuer's key set publishes no signing key.")

    kid = header.get("kid")
    if kid is None:
        if len(usable) == 1:
            return usable[0].key
        raise TokenVerificationError(
            "The token names no `kid` and the issuer publishes more than one signing key, so "
            "which key signed it is not stated anywhere."
        )
    for key in usable:
        if key.key_id == kid:
            return key.key
    raise TokenVerificationError(
        "The issuer's key set publishes no key with the `kid` this token names, so the key that "
        "signed it is not one this issuer currently publishes."
    )


def verified_claims(
    http: httpx.Client,
    token: str,
    *,
    jwks_url: str,
    issuer: str,
    audience: str,
    algorithms: Sequence[str] = SIGNATURE_ALGORITHMS,
) -> dict[str, Any]:
    """The claims of `token`, once its signature, issuer, audience and expiry hold.

    Everything a caller may read comes back from here and nowhere else: a door
    that decoded the token itself to find out who it was for, and then called
    this, would be making decisions on unverified claims while looking careful.
    """
    key = signing_key(key_set(http, jwks_url), token)
    try:
        return jwt.decode(
            token,
            key=key,
            algorithms=list(algorithms),
            issuer=issuer,
            audience=audience,
            options={"require": list(REQUIRED_CLAIMS)},
        )
    except jwt.ExpiredSignatureError as failure:
        raise TokenVerificationError("The token expired.") from failure
    except jwt.InvalidAudienceError as failure:
        raise TokenVerificationError("The token was issued for a different tool.") from failure
    except jwt.InvalidIssuerError as failure:
        raise TokenVerificationError(
            "The token states an issuer this tool does not trust."
        ) from failure
    except jwt.MissingRequiredClaimError as failure:
        raise TokenVerificationError(
            f"The token carries none of the claims {list(REQUIRED_CLAIMS)} under one of those "
            "names, so there is not enough in it to check."
        ) from failure
    except jwt.PyJWTError as failure:
        # The catch-all is last and is deliberately vague: the signature failing
        # and the token being malformed are the two cases that reach it, and
        # telling an unauthenticated caller which is an oracle.
        raise TokenVerificationError("The token's signature did not verify.") from failure
