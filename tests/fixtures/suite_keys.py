"""E0-18 PR 1, round 3 — a key set this suite signs with.

`suite_key_set` is a signing key and a served JWK Set of this suite's own, so
that a test can deliver a launch or a session **whose claims it chose** and still
have the door verify a real RS256 signature against the key set its own
registration names. Neither mock can be told what to put in a token, and the
vocabulary rule E0-18 has to hold — each door reads one roles claim and ignores
the other — cannot be posed with any token either mock will mint.

**This module is the one home of the session's signing key.** A second copy of
the memo below would be a second key set, and a door verifying against one while
a test signed with the other would fail for a reason no test names.
"""

import base64
from collections.abc import Iterator, Mapping
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# E0-18 PR 1, round 3 — a key set this suite signs with.
# ---------------------------------------------------------------------------

# Where this suite publishes the key set it signs with. `.invalid` is reserved by
# RFC 2606, and the host is what routes the door's fetch here: a door that
# verified against a key set it was not configured with reaches no mock at all
# and says so, rather than quietly verifying against the platform's real keys.
SUITE_JWKS_HOST = "key-set-this-suite-signs-with.invalid"
SUITE_JWKS_PATH = "/.well-known/jwks.json"
SUITE_JWKS_URL = f"http://{SUITE_JWKS_HOST}{SUITE_JWKS_PATH}"

# The key identifier the header of every token signed here carries, and the one
# member of the served JWK that ties the two together.
SUITE_SIGNING_KID = "e0-18-suite-signing-key"

# One key for the whole session. Generating an RSA key is the slow part and
# nothing here is a secret: it exists for the length of a pytest run, is never
# written down, and signs nothing but tokens this suite hands to itself.
_SUITE_SIGNING_KEY: dict[str, Any] = {}


def suite_signing_key() -> Any:
    """The RSA private key this suite signs its own tokens with, generated once."""
    if "key" not in _SUITE_SIGNING_KEY:
        from cryptography.hazmat.primitives.asymmetric import rsa

        _SUITE_SIGNING_KEY["key"] = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return _SUITE_SIGNING_KEY["key"]


def base64url_of(number: int) -> str:
    """One RSA parameter as RFC 7518 §6.3 spells it in a JWK: big-endian, unpadded."""
    width = (number.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(number.to_bytes(width, "big")).rstrip(b"=").decode("ascii")


class SuiteSignedKeySet:
    """A signing key, a JWK Set served at `SUITE_JWKS_URL`, and `sign()`.

    **Why this exists.** Both mocks mint tokens for the people they seed, and
    neither takes instruction about what claims to put in one — which is correct
    for a mock and leaves E0-18's round-3 vocabulary rule unposable. That rule is
    about a token stating *both* vocabularies, or the wrong one, and no seeded
    person produces such a token. So the claims are taken from a real minted token,
    changed in exactly the one place the test is about, and signed again.

    **What it is not.** It is not a way around signature verification. The door
    verifies RS256 against the key set its own registration names, and these tests
    point that registration here — so a door that skipped the signature, fetched
    the wrong key set, or ignored the `kid` fails against this exactly as it would
    against the platform's own keys. Each module that uses it carries a control
    test in which the claims are re-signed **unchanged** and the launch is required
    to succeed; without that control, every refusal below could be the signature
    rather than the vocabulary (`docs/MISTAKES.md` entry 3).

    Mounted like a mock — it exposes `.client` — so `routed_through` serves it with
    no special case, and any request to a path other than the key set's gets a 404
    rather than a key set, so a door fetching something else here says so.
    """

    def __init__(self) -> None:
        import httpx

        self.kid = SUITE_SIGNING_KID
        self.host = SUITE_JWKS_HOST
        self.jwks_url = SUITE_JWKS_URL
        self.private_key = suite_signing_key()
        self.client = httpx.Client(transport=httpx.MockTransport(self.answer))

    def document(self) -> dict[str, Any]:
        """The JWK Set a door fetches to verify anything `sign` produced."""
        numbers = self.private_key.public_key().public_numbers()
        return {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "alg": "RS256",
                    "kid": self.kid,
                    "n": base64url_of(numbers.n),
                    "e": base64url_of(numbers.e),
                }
            ]
        }

    def serve(self, request: Any) -> Any:
        """This key set for a request addressed to it, and `None` for anything else.

        Handed out as well as used internally, because the web door's key set URL
        is a *setting* pointed here while its token endpoint stays at the running
        provider — so that suite answers this one request inside its `around` hook
        and delivers the rest to the mock.
        """
        import httpx

        if request.url.host != self.host or request.url.path != SUITE_JWKS_PATH:
            return None
        return httpx.Response(200, json=self.document(), request=request)

    def answer(self, request: Any) -> Any:
        """Serve the key set, or 404 anything else addressed to this host."""
        import httpx

        served = self.serve(request)
        if served is not None:
            return served
        return httpx.Response(
            404,
            json={"error": f"this suite serves only {SUITE_JWKS_PATH} on {self.host}"},
            request=request,
        )

    def sign(self, claims: Mapping[str, Any]) -> str:
        """`claims` as an RS256 `id_token` this key set verifies."""
        import jwt

        return jwt.encode(
            dict(claims), self.private_key, algorithm="RS256", headers={"kid": self.kid}
        )


@pytest.fixture
def suite_key_set() -> Iterator[SuiteSignedKeySet]:
    """A key set this suite signs with. See `SuiteSignedKeySet` for why it exists."""
    keys = SuiteSignedKeySet()
    try:
        yield keys
    finally:
        keys.client.close()
