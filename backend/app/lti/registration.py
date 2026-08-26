"""The tool's own LTI identity: the key it signs with, and the key set it publishes.

SPEC §13 names this module "platform/deployment config, key management", and this
is the key-management half. LTI 1.3 is asymmetric in both directions: `app.lti.
launch` verifies what a *platform* signed against keys fetched from that
platform's JWKS URL, and this is the mirror — the public half of **this tool's**
key, published so a platform can verify the `client_assertion` the tool signs a
client-credentials grant with (E1-06 part 4, E1-11's service calls).

**One key, read from the database on every request** (ADR 0082). The `api`
container and the celery worker are two processes and one tool, and a platform
holds the public half of exactly one key — so the key lives in a one-row
`tool_signing_key` table rather than in a process, a file or a setting. Only the
private PEM is stored; the public JWK and its `kid` are both derived here, on
read, because a stored copy of something derivable is a copy that can drift out
of step with what it was derived from (`docs/MISTAKES.md` entry 19). The drift
would be a key set advertising a key that no longer signs anything.

**The public JWK is assembled member by member, never filtered.** `cryptography`
will serialise a *private* key to a JWK-shaped mapping one call away from the
public one, and the result differs only by a `d` beside the modulus — a document
that passes every other check and hands the tool's whole LTI identity to whoever
fetches it. Nothing here ever holds a private member to leave out:
`public_numbers()` yields `n` and `e` and there is nothing else to drop.
`mock-lms/app/signing.py::public_jwk` states the same rule for the platform's own
key set.

**PyJWT and `cryptography`, not the mocks' arithmetic.** ADR 0035 bounds the
hand-written RSA in `mock-lms/` and `mock-idp/` to those services; ADR 0073 is
why this side of the wall uses the locked library. This module reads a PEM and
publishes two integers, which is the smallest thing that library does.
"""

import base64
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lti import ToolSigningKey

__all__ = [
    "JWKS_PATH",
    "NoSigningKeyError",
    "public_jwk",
    "published_key_set",
    "rfc7638_thumbprint",
]

# Where this tool publishes its key set. Beside `LOGIN_PATH` and `LAUNCH_PATH` in
# this package, and a constant for the same reason they are: it is a public
# address a platform is registered with, so a second copy of it is a spelling
# that can be changed in one place and not the other.
JWKS_PATH = "/lti/jwks"

# The JOSE algorithm this tool signs with and the key type it signs with. LTI
# 1.3's security framework specifies RS256 for message signing, so both are the
# specification's choice rather than a preference, and a key set that said
# otherwise would describe a key this tool does not hold.
SIGNATURE_ALGORITHM = "RS256"
KEY_TYPE = "RSA"

# What the published key may be used for, as RFC 7517 §4.2 spells it. A platform
# reads `use` and `alg` to decide whether this key may verify a signature at all,
# and some key-set readers skip a key that states neither.
SIGNATURE_USE = "sig"


class NoSigningKeyError(RuntimeError):
    """This deployment holds no `tool_signing_key` row, so the tool has no identity.

    A deliberate state rather than an impossible one (ADR 0082): the key is
    written by the demo seed, which runs only in development, and the supply
    route for a real deployment is `docs/tickets/e1/deferred.md`'s with a
    done-when. Raised loudly here rather than answered with an empty key set,
    because an empty set is a document a platform accepts and stores — and the
    failure then arrives hours later, at that platform, as an assertion refused
    for a reason that names no key.
    """


def base64url_uint(value: int) -> str:
    """A non-negative integer as a JWK numeric member (RFC 7518 §2).

    The minimum number of octets that represents the value, big-endian, with no
    leading zero and no padding. A longer encoding is a different *string* for
    the same number, and a platform comparing key material — or computing a
    thumbprint over it — would see two keys where there is one.
    """
    width = max(1, (value.bit_length() + 7) // 8)
    return base64.urlsafe_b64encode(value.to_bytes(width, "big")).rstrip(b"=").decode("ascii")


def rfc7638_thumbprint(members: dict[str, str]) -> str:
    """The RFC 7638 thumbprint of an RSA public key, used as its `kid`.

    §3.2 fixes both halves of what makes this reproducible, and getting either
    wrong produces a stable, plausible, wrong identifier: for an RSA key the
    required members are exactly `e`, `kty` and `n` — `use`, `alg` and `kid`
    itself are excluded — and they are serialised as JSON with the members in
    lexicographic order and no whitespace anywhere.

    Derived rather than assigned, so the `kid` a platform selects a verification
    key by and the `kid` this tool writes into an assertion header are the same
    function of the same modulus. Any stable string works right up until the two
    are computed in different places.
    """
    canonical = json.dumps(
        {"e": members["e"], "kty": members["kty"], "n": members["n"]},
        separators=(",", ":"),
        sort_keys=True,
    )
    return (
        base64.urlsafe_b64encode(hashlib.sha256(canonical.encode("utf-8")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


def public_jwk(private_key_pem: str) -> dict[str, str]:
    """The public half of a stored PEM, as RFC 7517 spells a signing key.

    The three thumbprint members are built first and the thumbprint is taken over
    exactly those, which is what keeps this agreeing with a platform that
    computes the same value from the document it fetched.
    """
    key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    if not isinstance(key, RSAPrivateKey):
        raise NoSigningKeyError(
            f"`tool_signing_key` holds a {type(key).__name__}. This tool signs RS256 with an RSA "
            "key (ADR 0082), and a key set describing anything else describes a key it does not "
            "hold."
        )
    numbers = key.public_key().public_numbers()
    members = {
        "kty": KEY_TYPE,
        "n": base64url_uint(numbers.n),
        "e": base64url_uint(numbers.e),
    }
    return {
        **members,
        "use": SIGNATURE_USE,
        "alg": SIGNATURE_ALGORITHM,
        "kid": rfc7638_thumbprint(members),
    }


def published_key_set(session: Session) -> dict[str, Any]:
    """This tool's key set, as RFC 7517 §5 shapes one: `{"keys": [...]}`.

    Exactly one key, because ADR 0082 stores exactly one and forbids rotation:
    "two rows is not an untidy state to reconcile later, it is two identities for
    one tool, and whichever row a process reads first decides whether its
    assertions verify". `one_or_none` is what makes a second row a loud failure
    here as well as at the unique index, rather than this quietly publishing
    whichever came back first.
    """
    stored = session.scalars(select(ToolSigningKey)).one_or_none()
    if stored is None:
        raise NoSigningKeyError(
            "This deployment holds no `tool_signing_key` row, so the tool has no key to publish "
            "and nothing it signs can be verified. `make seed` writes one in development; ADR "
            "0082 records that a real deployment needs a supply route before it needs anything "
            "else."
        )
    return {"keys": [public_jwk(stored.private_key_pem)]}
