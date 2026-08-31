"""E1-06 — the tool's key set, and the assertions a client-credentials grant is asked with.

Two ticket parts meet here and neither can be driven without the other. The mock
platform verifies a `client_assertion` against **the tool's** published key set,
and the tool publishes that key set from the key E1-05 put in `tool_signing_key`.
So a test of the platform's token endpoint needs a key pair it can sign with and a
way to tell the platform what the tool's public half is, and a test of the tool's
JWKS route needs the same arithmetic — an RFC 7638 thumbprint, and the set of JWK
members that make a key a private one — asked of a document the tool served.

**The seam, and why it is named here rather than discovered.** The platform fetches
the tool's key set over HTTP, from an address it is configured with, and neither
address resolves in an in-process test. `tests/fixtures/doors.py` already answers
exactly this question for the *tool's* own server-side fetches — "every server-side
fetch a door makes goes through one client, so a test can route it and nothing else
has to be intercepted" — and this is that idiom pointed the other way:
`MockPlatform(..., tool_key_set=…)` puts a client on the mock application's
`state.http`, and every request it makes is answered with the key set.

**What that pins, and it is an interface E1-06's implementer has to satisfy.** The
ticket says the platform needs "somewhere to fetch the tool's key set" and does not
say how it reaches it, so this fixture decides two things a test cannot avoid
deciding: the fetch goes through `app.state.http`, an httpx-shaped client, and it
happens **while a token request is being verified** rather than once at startup —
the client is installed after the mock's lifespan has run, exactly as `tool_doors`
installs the tool's. `ToolKeySetServer.requested` records every URL asked for, so
"the platform actually fetched the key set" is an assertion in
`test_mock_lms_client_credentials_grant.py` rather than an assumption here.

**Nothing here is a secret and nothing is written down.** Both key pairs are
generated once per pytest run and live in memory, which is SPEC §9.1's rule and the
reason `tests/unit/test_mock_lms_service.py`'s repository-wide sweep can stay an
equality against zero.

**The one place a test obtains an access token.** `client_credentials_form` and
`access_token_granted_to` are the grant sequence — form, assertion, post, token —
extracted out of `tests/integration/test_mock_lms_client_credentials_grant.py`'s
machinery so that the suites that merely *need* a token have one helper rather than
a copy each (`docs/MISTAKES.md` entry 13). Every such asker reaches it through
`MockPlatform.service_token`, which supplies the post; nothing calls it twice over.

That grant module is deliberately the one caller that goes on building its own
request by hand, and the reason is not oversight: its subject **is** the shape of
the form and the codes each malformed one is refused with, so a conformance test
driven through this helper would be checking the helper against itself
(`docs/MISTAKES.md` entry 19). What keeps the two from drifting is
`test_mock_lms_nrps_requires_a_token.py`'s control on the form's members, which
fails if this helper stops posting what RFC 6749 §4.4 and RFC 7523 §2.2 require.
"""

import base64
import hashlib
import json
import time
from collections.abc import Callable, Iterator, Mapping
from typing import Any
from uuid import uuid4

import pytest

from fixtures.suite_keys import base64url_of

# ---------------------------------------------------------------------------
# E1-06 — the tool's key set, and the assertions it verifies.
# ---------------------------------------------------------------------------

# How long an assertion these tests sign lives, when the test is not about
# lifetime. **This suite's choice**, and deliberately well inside E1-06's bound:
# a default that sat on the boundary would make every accepted twin in the grant
# suite an assertion about the boundary as well as about its own subject.
DEFAULT_ASSERTION_LIFETIME_SECONDS = 60

# The members that make a JSON Web Key a private key (RFC 7517, RFC 7518): `d`
# for RSA and EC, `k` for a symmetric key, and RSA's four CRT parameters. The
# same set `tests/unit/test_mock_lms_service.py` sweeps the repository's *files*
# for; it is transcribed rather than shared because that module reads a tree and
# this one reads one HTTP response, and neither is a workaround the other could
# route through (`docs/MISTAKES.md` entry 13 is about a hazard, and this is a
# specification's own list).
PRIVATE_JWK_MEMBERS = frozenset({"d", "p", "q", "dp", "dq", "qi", "k"})

# The grant and the assertion profile, spelled as RFC 6749 §4.4 and RFC 7523 §2.2
# spell them. Specification constants: a platform accepting some other spelling is
# one no conformant client reaches, which is why the grant suite transcribes the
# same two strings independently rather than importing these.
CLIENT_CREDENTIALS_GRANT = "client_credentials"
JWT_BEARER_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

# One RSA key pair per label, for the length of a pytest run. Generating a
# 2048-bit key is the slow part and nothing here is a credential: it exists in
# memory, is never written down, and signs nothing but assertions this suite
# hands to a mock platform. `tests/fixtures/suite_keys.py` caches its own key for
# the same reason.
_KEY_PAIRS: dict[str, Any] = {}


def rsa_key(label: str) -> Any:
    """The RSA private key this suite uses under `label`, generated once."""
    if label not in _KEY_PAIRS:
        from cryptography.hazmat.primitives.asymmetric import rsa

        _KEY_PAIRS[label] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return _KEY_PAIRS[label]


def rfc7638_thumbprint(members: Mapping[str, Any]) -> str:
    """The RFC 7638 JWK thumbprint of an RSA key, as its `kid`.

    Written out of the RFC rather than taken from a library, because it is the
    value E1-06's JWKS route is asserted against and a test that computed it with
    whatever the implementation computed it with would be checking a value against
    itself (`docs/MISTAKES.md` entry 19).

    RFC 7638 §3.2 fixes both halves of what makes this reproducible: for an RSA
    key the required members are exactly `e`, `kty` and `n` — `use`, `alg` and
    `kid` itself are excluded — and they are serialised as JSON with the members
    in lexicographic order and no whitespace anywhere. Getting either half wrong
    produces a stable, plausible, wrong identifier, so
    `test_the_tool_publishes_its_key_set.py` exercises both directions before it
    believes this.
    """
    if "n" not in members or "e" not in members:
        pytest.fail(
            f"A thumbprint was asked for a key carrying {sorted(members)}, which has no `n` or no "
            "`e`. RFC 7638 computes an RSA thumbprint over exactly `e`, `kty` and `n`, so there is "
            "nothing to hash — and a helper that answered anyway would hand back the same digest "
            "for every malformed key it was given."
        )
    canonical = json.dumps(
        {"e": members["e"], "kty": members.get("kty", "RSA"), "n": members["n"]},
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def private_jwk_members(node: Any) -> list[str]:
    """Every private JWK member anywhere in `node`, by name, deepest last.

    A *list* rather than a boolean, unlike the repository sweep's copy, because
    the failure this serves has to name what it found: "the tool's key set carries
    `d`" is a finding somebody can act on and "the tool's key set carries private
    material" is a puzzle. It walks the whole document rather than the `keys`
    array, so a private half tucked beside the key set — in a debug member, in an
    error body — is found where a targeted read would walk past it.
    """
    found: list[str] = []
    if isinstance(node, Mapping):
        found.extend(sorted(PRIVATE_JWK_MEMBERS & set(node)))
        for value in node.values():
            found.extend(private_jwk_members(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(private_jwk_members(item))
    return found


class ToolKeyPair:
    """One RSA key pair, its public JWK, and `sign`.

    Two of these exist in the grant suite and the difference between them is the
    whole of one refusal: one is the key the platform is told belongs to the tool,
    and the other is a key nothing published. They are otherwise identical, which
    is what makes a refusal attributable to the key rather than to anything about
    how the assertion was built.
    """

    def __init__(self, label: str, private_key: Any | None = None) -> None:
        self.label = label
        # `private_key` is for the one caller that cannot generate its own: the
        # roster-sync fixture, where the key the platform will verify against is
        # the *tool's* stored `tool_signing_key` row rather than anything this
        # module made up. A pair built from that PEM signs assertions the real
        # tool's published key set verifies, which is what lets the shared token
        # helper work against a platform pointed at the real tool's JWKS route.
        self.private_key = rsa_key(label) if private_key is None else private_key

    def jwk(self) -> dict[str, Any]:
        """The public half, as RFC 7517 spells a signing key.

        `kid` is the thumbprint rather than a name, because that is what E1-06's
        JWKS route publishes and a test key that identified itself some other way
        would let a platform work against these tests and fail against the tool.
        """
        numbers = self.private_key.public_key().public_numbers()
        members = {"kty": "RSA", "n": base64url_of(numbers.n), "e": base64url_of(numbers.e)}
        return {**members, "use": "sig", "alg": "RS256", "kid": rfc7638_thumbprint(members)}

    @property
    def kid(self) -> str:
        return str(self.jwk()["kid"])

    def key_set(self) -> dict[str, Any]:
        """This key alone, as a JWK Set — the shape a JWKS endpoint serves."""
        return {"keys": [self.jwk()]}

    def sign(self, claims: Mapping[str, Any], *, kid: str | None = None) -> str:
        """`claims` as an RS256 JWT, signed with this key.

        `kid` is overridable so that a test can present a token whose header names
        a key the platform holds and whose signature is somebody else's — the near
        miss for a platform that selects a key by `kid` and never verifies with it.
        """
        import jwt

        return jwt.encode(
            dict(claims), self.private_key, algorithm="RS256", headers={"kid": kid or self.kid}
        )


class ToolKeySetServer:
    """The tool's key set, served to a mock platform through one seam.

    **It answers every request, whatever the address**, and that is deliberate.
    The platform is configured with the tool's JWKS URL, and which variable
    carries it and what its value is are the implementer's — so a server that
    matched on host would be this fixture deciding a name the ticket leaves open,
    and would fail as "no key set" rather than as "configured elsewhere".

    `requested` is what keeps that permissiveness honest: a platform that fetches
    nothing is a platform verifying against something else, and the assertion that
    it fetched is in the grant suite rather than implied here.
    """

    def __init__(self, key_set: Mapping[str, Any]) -> None:
        import httpx

        self.key_set = dict(key_set)
        self.requested: list[str] = []
        self.client = httpx.Client(transport=httpx.MockTransport(self.answer))

    def answer(self, request: Any) -> Any:
        import httpx

        self.requested.append(str(request.url))
        return httpx.Response(200, json=self.key_set, request=request)

    def close(self) -> None:
        self.client.close()


def assertion_claims(
    client_id: str,
    audience: str,
    *,
    issued_at: float | None = None,
    lifetime: int = DEFAULT_ASSERTION_LIFETIME_SECONDS,
) -> dict[str, Any]:
    """The claims `pylti1p3`'s `ServiceConnector` puts in a `client_assertion`.

    Handed back as a plain mutable dict rather than built through keyword
    arguments for every case, because every refusal in the grant suite is *one*
    difference from a request that works — `claims["aud"] = something_else`, or
    `claims.pop("exp")` — and a builder with a switch per case hides how many
    things a call changed. A 4xx is a 4xx, so a case that got two things wrong is
    satisfied by a platform that checks either (`docs/MISTAKES.md` entry 3).

    `iss` and `sub` are both the tool's client id: the assertion is the tool
    speaking about itself, which is what makes it a *client* assertion, and a
    platform resolves the registration from it.
    """
    issued = int(time.time() if issued_at is None else issued_at)
    return {
        "iss": client_id,
        "sub": client_id,
        "aud": audience,
        "jti": uuid4().hex,
        "iat": issued,
        "exp": issued + lifetime,
    }


def key_pair_from_pem(label: str, private_key_pem: str) -> ToolKeyPair:
    """A `ToolKeyPair` over a private key that already exists, given as a PEM.

    For the caller whose key is not this module's to invent: the roster-sync
    fixture points its platform at the real tool's `/lti/jwks`, so an assertion
    that platform will accept has to be signed by the `tool_signing_key` row the
    tool publishes. Loading the row's PEM is the only way to hold both halves.
    """
    from cryptography.hazmat.primitives import serialization

    loaded = serialization.load_pem_private_key(private_key_pem.encode("ascii"), password=None)
    return ToolKeyPair(label, private_key=loaded)


# ---------------------------------------------------------------------------
# The grant, as the one sequence every suite that merely needs a token uses.
# ---------------------------------------------------------------------------


def client_credentials_form(assertion: str | None, scope: str) -> dict[str, str]:
    """The form body `ServiceConnector` posts to a platform's token endpoint.

    `assertion` may be `None`, which posts the body **without** a
    `client_assertion` member rather than with an empty one: a missing parameter
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


def access_token_granted_to(
    post: Callable[[str, dict[str, str]], Any],
    *,
    token_url: str,
    client_id: str,
    key_pair: ToolKeyPair,
    scope: str,
) -> dict[str, Any]:
    """One client-credentials grant, from a signed assertion to the token response.

    The whole sequence in one place, because every suite below the grant module
    asks the same question — "give me a token I can present to a service" — and a
    copy per suite is `docs/MISTAKES.md` entry 13 in the shape this fix round is
    most exposed to: enforcement lands, six modules need a token, and five of them
    grow their own minting code that drifts from the sixth.

    `post` is supplied by the caller rather than a client being built here, so the
    request travels over whatever seam that caller's platform is reachable through.

    **A failure here is the machinery, not the platform.** Everything this asserts
    — that the endpoint answered 200 with an `access_token` — is already the
    subject of `test_mock_lms_client_credentials_grant.py`, so a red raised from
    inside this helper means a test that only wanted a credential could not get
    one, and the grant suite is where the reason is diagnosed.
    """
    claims = assertion_claims(client_id, token_url)
    response = post(token_url, client_credentials_form(key_pair.sign(claims), scope))
    if response.status_code != 200:
        pytest.fail(
            f"Asking `{token_url}` for an access token carrying {scope!r} answered "
            f"{response.status_code} rather than 200, so a test that needed a credential to "
            "present to a service has none. That is this suite's machinery failing rather than "
            "the thing under test: `test_mock_lms_client_credentials_grant.py` is where a refused "
            f"grant is diagnosed. Body begins {response.text[:300]!r}."
        )
    try:
        granted = response.json()
    except ValueError:
        pytest.fail(
            f"`{token_url}` answered 200 with a body that is not JSON, so there is no "
            f"`access_token` to read. Body begins {response.text[:300]!r}."
        )
    if not isinstance(granted, dict) or not str(granted.get("access_token") or ""):
        pytest.fail(
            f"`{token_url}` answered 200 with {granted!r}, which carries no `access_token`. RFC "
            "6749 §5.1 makes that member REQUIRED, and an empty one is a credential every service "
            "refuses — which would read as the service being wrong."
        )
    return granted


@pytest.fixture
def tool_key_pair() -> ToolKeyPair:
    """The key the platform is told belongs to the tool."""
    return ToolKeyPair("e1-06-tool")


@pytest.fixture
def key_the_tool_never_published() -> ToolKeyPair:
    """A second key pair, absent from every key set these tests serve.

    Its whole job is one refusal — an assertion signed by a key not in the tool's
    set — and it is a real 2048-bit RSA key rather than a corrupted signature so
    that the platform refuses it for the reason the test names. A signature
    mangled byte by byte is refused by a verifier that does no key selection at
    all, and the test would read that as key selection working.
    """
    return ToolKeyPair("e1-06-stranger")


@pytest.fixture
def serve_key_set() -> Iterator[Callable[[Mapping[str, Any]], ToolKeySetServer]]:
    """Serve a key set to a mock platform, and close the client afterwards."""
    served: list[ToolKeySetServer] = []

    def serve(key_set: Mapping[str, Any]) -> ToolKeySetServer:
        server = ToolKeySetServer(key_set)
        served.append(server)
        return server

    try:
        yield serve
    finally:
        for server in reversed(served):
            server.close()


@pytest.fixture
def claims_for_an_assertion() -> Callable[..., dict[str, Any]]:
    """Hand `assertion_claims` to a test. See it for why it answers a plain dict."""
    return assertion_claims


@pytest.fixture
def thumbprint_of() -> Callable[[Mapping[str, Any]], str]:
    """Hand `rfc7638_thumbprint` to the JWKS suite and to its own control.

    The control and the thing it controls are one function, which is the whole
    value of a control (`docs/MISTAKES.md` entry 3): a suite that checked the
    tool's `kid` with one implementation and demonstrated the rule with another
    could have both wrong and agree.
    """
    return rfc7638_thumbprint


@pytest.fixture
def private_key_members_in() -> Callable[[Any], list[str]]:
    """Hand `private_jwk_members` to the test that asserts a key set has none.

    Handed out for the same reason as above: the assertion that the served
    document carries no private member and the canary that proves the detector can
    *find* one have to be the same detector, or the canary certifies nothing
    (`docs/MISTAKES.md` entry 35 — a control that only ever reports absence cannot
    say which mechanisms it can see).
    """
    return private_jwk_members
