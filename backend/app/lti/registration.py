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
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from pylti1p3.deployment import Deployment
from pylti1p3.registration import Registration
from pylti1p3.tool_config import ToolConfAbstract
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lti import LtiDeployment, LtiPlatform, ToolSigningKey

__all__ = [
    "JWKS_PATH",
    "MultipleRegistrationsError",
    "NoSigningKeyError",
    "OrmToolConf",
    "ToolRegistration",
    "launcher_origins",
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


class MultipleRegistrationsError(Exception):
    """One issuer resolves to more than one registration, and this tool refuses.

    LTI 1.3 allows it — one LMS registering this tool twice, a pilot beside
    production — which is why `lti_platform` is unique on `(issuer, client_id)`
    and not on the issuer. Telling two registrations for one issuer apart needs a
    rule for what a launch that names a client the issuer did not register does,
    and E1's multi-tenant work writes it; until then a second registration is a
    loud refusal rather than a silent choice between two. `app.lti.launch`'s
    `registered_platform` refuses the same way at the launch, and this preserves
    it inside the `pylti1p3` adapter's own lookup so a future caller through the
    library gets the refusal, not `pylti1p3`'s default "pick one".
    """


class ToolRegistration(Registration):
    """A `pylti1p3` registration whose `kid` is this module's own thumbprint.

    `Registration.get_kid` derives one from the *public* key with jwcrypto, and
    `ServiceConnector` reads it to put a `kid` in the header of every
    `client_assertion` the tool signs. Measured on the locked versions, that
    derivation agrees with `rfc7638_thumbprint` below — both are RFC 7638 §3.2 over
    `e`, `kty` and `n` — and "measured to agree today" is exactly the state
    `rfc7638_thumbprint`'s own docstring warns about: "Any stable string works
    right up until the two are computed in different places."

    So there is one derivation and this class is where the library reads it. The
    alternative is `set_tool_public_key`, which would work and would leave the
    identifier a platform selects a verification key by computed by a dependency
    rather than by the module that publishes the key set.

    Eight lines and one overridden method, deliberately: this is not a layer over
    `pylti1p3` — the library has no `set_kid` and expects its own classes to be
    subclassed, which is how `OrmToolConf` below reaches it too.
    """

    _kid: str | None = None

    def set_kid(self, kid: str) -> "ToolRegistration":
        self._kid = kid
        return self

    def get_kid(self) -> str | None:
        return self._kid


class OrmToolConf(ToolConfAbstract[Any]):
    """`pylti1p3`'s tool configuration, backed by `lti_platform`/`lti_deployment`.

    `pylti1p3` reaches a registration through this interface: the OIDC login step
    asks for a platform's client id and authorization endpoint, and the launch
    steps ask for the same registration and its deployments. `pylti1p3`'s own
    subclasses read a static dict or a JSON file; this one reads the two tables
    the admin console writes, on the session the request already holds.

    **The `>1`-row refusal is preserved.** `pylti1p3`'s stock config picks the
    first registration for an issuer; SPEC §2's model is that a second one is
    ambiguous, so `find_registration_by_issuer` raises `MultipleRegistrationsError`
    rather than choosing — the same guard `app.lti.launch.registered_platform`
    holds, kept here so a lookup through the library cannot lose it.

    **The platform's key set is left unfetched.** `Registration.get_key_set_url`
    carries the `jwks_url`, but the launch door fetches the key set through the
    repo's httpx client (`app.state.http`) the way `app.services.tokens` does, and
    hands it to the launch — never letting `pylti1p3` open its own `requests`
    connection for an inbound verification.

    **The tool's own key is filled in, and E1-11 is why.** A registration is used
    in both directions: inbound, to verify what a platform signed, and outbound, to
    sign the `client_assertion` a token request authenticates with —
    `pylti1p3.ServiceConnector` reads `get_tool_private_key()` and `get_kid()` off
    exactly this object and asserts the first is not None. One construction path
    for both is what keeps the `kid` this tool writes into an assertion header and
    the `kid` it publishes at `/lti/jwks` the same function of the same modulus; two
    would agree until somebody rotated one of them.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def _platforms_for(self, iss: str) -> list[LtiPlatform]:
        return list(
            self._session.execute(select(LtiPlatform).where(LtiPlatform.issuer == iss)).scalars()
        )

    def _registration(self, row: LtiPlatform) -> Registration:
        registration = ToolRegistration()
        registration.set_issuer(row.issuer)
        registration.set_client_id(row.client_id)
        registration.set_key_set_url(row.jwks_url)
        # Both are nullable — a registration written before E1-05 states neither.
        # Set them only when present; a NULL authorization endpoint is refused at
        # the login (`app.lti.launch.begin_a_launch`), not fabricated here.
        if row.authorization_endpoint is not None:
            registration.set_auth_login_url(row.authorization_endpoint)
        if row.auth_token_url is not None:
            registration.set_auth_token_url(row.auth_token_url)
        # **Absent rather than refused**, deliberately. Every inbound launch is
        # resolved through this method, and a deployment with no `tool_signing_key`
        # row can still verify one — so raising here would take the door down over
        # a key only the outbound client needs. The outbound caller
        # (`app.services.roster_sync`) checks for it and raises `NoSigningKeyError`
        # naming the table, which is a better message than the library's assert.
        stored = self._session.scalars(select(ToolSigningKey)).one_or_none()
        if stored is not None:
            registration.set_tool_private_key(stored.private_key_pem)
            registration.set_kid(public_jwk(stored.private_key_pem)["kid"])
        return registration

    def find_registration_by_issuer(self, iss: str, *args: Any, **kwargs: Any) -> Registration:
        rows = self._platforms_for(iss)
        if len(rows) > 1:
            raise MultipleRegistrationsError(
                "More than one registration exists for that platform, and this tool cannot yet "
                "tell which of them began the launch."
            )
        return self._registration(rows[0]) if rows else None  # type: ignore[return-value]

    def find_registration_by_params(
        self, iss: str, client_id: str, *args: Any, **kwargs: Any
    ) -> Registration:
        rows = [row for row in self._platforms_for(iss) if row.client_id == client_id]
        return self._registration(rows[0]) if rows else None  # type: ignore[return-value]

    def find_deployment(self, iss: str, deployment_id: str) -> Deployment | None:
        rows = self._platforms_for(iss)
        if len(rows) != 1:
            return None
        return self._deployment(rows[0], deployment_id)

    def find_deployment_by_params(
        self, iss: str, deployment_id: str, client_id: str, *args: Any, **kwargs: Any
    ) -> Deployment | None:
        rows = [row for row in self._platforms_for(iss) if row.client_id == client_id]
        if len(rows) != 1:
            return None
        return self._deployment(rows[0], deployment_id)

    def _deployment(self, platform: LtiPlatform, deployment_id: str) -> Deployment | None:
        found = self._session.execute(
            select(LtiDeployment.id).where(
                LtiDeployment.lti_platform_id == platform.id,
                LtiDeployment.deployment_id == deployment_id,
            )
        ).first()
        return Deployment().set_deployment_id(deployment_id) if found is not None else None


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


def launcher_origins(session: Session) -> list[str]:
    """The distinct browser-facing origins every registered platform launches from.

    The browser-facing address a registration exposes is its
    `authorization_endpoint`, and its origin — `scheme://host[:port]`, path
    stripped — is the thing two callers ask this table for. The developer console
    links to it so a developer reaches a platform's launcher page (E1-05); the
    security-headers middleware admits it as a `frame-ancestors` source, because a
    launch from that platform arrives inside its iframe (ADR 0102). It lives here,
    in the platform-config module SPEC §13 names, rather than in either caller, so
    the framing policy and the console read one derivation of one column
    (`docs/MISTAKES.md` entry 13).

    **Read from `lti_platform` and from nowhere else** (E1-05). This used to be
    the origin of one process-wide setting, which is one link whatever the
    database holds — the same address for every registration, and a link even
    when there is no registration at all. A registration with no authorization
    endpoint states none, so it offers no launcher; that is the same NULL the
    launch door refuses rather than defaults.

    Distinct, in the order the issuers sort, because two registrations of one
    platform — a pilot beside production, which is why `lti_platform` is unique
    on the pair — share one launcher page and two identical links would be a
    duplicate rather than a choice.
    """
    endpoints = session.execute(
        select(LtiPlatform.authorization_endpoint)
        .where(LtiPlatform.authorization_endpoint.is_not(None))
        .order_by(LtiPlatform.issuer)
    ).scalars()

    origins: list[str] = []
    for endpoint in endpoints:
        split = urlsplit(str(endpoint))
        origin = f"{split.scheme}://{split.netloc}"
        if origin not in origins:
            origins.append(origin)
    return origins
