"""The platform's issuer key: generated per run, published as a JWK, used to sign.

SPEC §9.1 asks for "issuer keys generated per test run rather than fixtures
checked into the repository", and E0-14's third acceptance criterion repeats it.
So there is no key file, no environment variable holding a key, and no constant
in an image layer: `IssuerKey.generate()` is called once per application and the
private half exists only in that process's memory.

**Why the arithmetic is here rather than a library call.** Nothing in this
project's locked dependency closure generates an RSA key or signs a JSON Web
Signature, and the mock is a second application with no lockfile of its own — so
adding one would mean either shipping it in the production backend image or
building a second locked closure for a development-only service. The whole of
what is needed is a prime search and one modular exponentiation, both of which
are in the standard library. The reasoning, and the bound on where this is
allowed to be used, are in
`docs/adr/0035-the-mock-platform-signs-with-standard-library-rsa.md`.

**Read that bound before copying anything out of this file.** These are throwaway
keys for a fake platform; nothing confidential rests on them. Pulse's own signing
key, when E1 introduces it, is a real credential and belongs to a real library.

The two specifications implemented below, so a reader can check the code against
them rather than against this docstring:

- **RFC 8017 §9.2** — EMSA-PKCS1-v1_5 encoding, which is what makes `RS256` a
  signature rather than an encryption of a digest.
- **RFC 7638** — the JWK thumbprint, used as the `kid`. A key ID derived from the
  key means the published `kid` and the signing key cannot drift apart.
"""

import base64
import hashlib
import hmac
import json
import math
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# The modulus size. 2048 bits is the floor every JOSE implementation accepts and
# is what a real platform would use; a smaller key would generate faster and
# would teach a reader that a mock key is a different kind of key.
MODULUS_BITS = 2048

# The public exponent every RSA JWK in practice carries. Fixed rather than
# chosen: F4 is what makes verification cheap, and a platform that used anything
# else would exercise a path no tool implements well.
PUBLIC_EXPONENT = 65537

# Rounds of Miller-Rabin for a candidate that has already survived trial
# division. FIPS 186-5 asks for 5 rounds at this size for a randomly generated
# candidate; 40 is the conventional belt-and-braces figure and costs
# milliseconds, which is worth more here than the milliseconds are.
PRIMALITY_ROUNDS = 40

# Small odd primes, for trial division before any modular exponentiation. About
# 88% of odd candidates are eliminated by this loop at a fraction of the cost of
# one Miller-Rabin round, and it is the whole reason key generation takes a
# fraction of a second rather than several.
SMALL_PRIMES: tuple[int, ...] = tuple(
    candidate
    for candidate in range(3, 1000, 2)
    if all(candidate % divisor for divisor in range(3, int(candidate**0.5) + 1, 2))
)

# The DigestInfo prefix PKCS#1 v1.5 puts in front of a SHA-256 digest, from
# RFC 8017 appendix B.1: the DER encoding of the SHA-256 algorithm identifier
# and the OCTET STRING header for the 32-byte digest that follows it.
SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")

# The JOSE algorithm this platform signs with. The IMS security framework LTI 1.3
# rests on specifies RS256 for message signing, and SPEC §7.3 asks for strict LTI
# 1.3 core, so this is the specification's choice and not a preference.
SIGNATURE_ALGORITHM = "RS256"


def base64url(raw: bytes) -> str:
    """Encode `raw` as base64url with the padding JOSE omits (RFC 7515 §2)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def base64url_uint(value: int) -> str:
    """Encode a non-negative integer as a JWK numeric member (RFC 7518 §2).

    The octet sequence is the minimum number of octets that represents the
    value, big-endian, with no leading zero — a longer encoding is a different
    string for the same number, and a verifier comparing key material would then
    see two keys where there is one.
    """
    width = max(1, (value.bit_length() + 7) // 8)
    return base64url(value.to_bytes(width, "big"))


def base64url_decoded(value: str) -> bytes:
    """Decode a base64url member, restoring the padding JOSE omits (RFC 7515 §2).

    Raises `ValueError` on anything that is not base64url, which is what makes a
    mangled token a refusal rather than a 500: `binascii.Error` is a subclass of
    `ValueError`. `validate=True` is what makes that true — without it the
    decoder discards every character outside the alphabet, so a corrupted segment
    decodes to something shorter and plausible instead of failing.
    """
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def base64url_uint_decoded(value: str) -> int:
    """One RSA parameter out of a JWK: base64url, big-endian, unpadded (RFC 7518 §6.3)."""
    return int.from_bytes(base64url_decoded(value), "big")


def pkcs1_v15_encoded(signing_input: bytes, width: int) -> bytes:
    """The EMSA-PKCS1-v1_5 encoding of `signing_input`, `width` octets wide.

    `0x00 0x01`, then `0xFF` padding, then `0x00`, then the DigestInfo (RFC 8017
    §9.2). The padding is what makes RS256 a signature scheme rather than a raw
    exponentiation of a digest, and a verifier that skips it accepts a forgery.

    One function because signing and verifying are the same encoding read in two
    directions: signing raises this to the private exponent, and verifying raises
    a signature to the public one and compares the result against it. Two copies
    of this arithmetic would be two chances to get the padding wrong, and only
    one of them would be caught by a test that signs and verifies with this file.
    """
    digest_info = SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(signing_input).digest()
    padding_length = width - len(digest_info) - 3
    if padding_length < 8:
        # RFC 8017's own bound: fewer than eight padding octets means the key is
        # too small for the digest. Unreachable at 2048 bits, and loud rather
        # than silent if MODULUS_BITS is ever lowered.
        raise ValueError(
            f"A {width * 8}-bit modulus is too small to sign a SHA-256 digest under PKCS#1 v1.5."
        )
    return b"\x00\x01" + b"\xff" * padding_length + b"\x00" + digest_info


def is_probable_prime(candidate: int) -> bool:
    """Miller-Rabin with random bases, after trial division by the small primes.

    Composite in, `False` out, always: Miller-Rabin has no false negatives, so
    the only error this can make is calling a composite prime, and it does that
    with probability below 4**-40. A composite modulus would not fail quietly
    either — the signature would simply not verify, and the suite checks exactly
    that against an independent verifier.
    """
    if candidate < 2:
        return False
    for prime in SMALL_PRIMES:
        if candidate % prime == 0:
            return candidate == prime
    if candidate % 2 == 0:
        return False

    remainder = candidate - 1
    exponent_of_two = 0
    while remainder % 2 == 0:
        remainder //= 2
        exponent_of_two += 1

    for _ in range(PRIMALITY_ROUNDS):
        base = secrets.randbelow(candidate - 3) + 2
        witness = pow(base, remainder, candidate)
        if witness in (1, candidate - 1):
            continue
        for _ in range(exponent_of_two - 1):
            witness = witness * witness % candidate
            if witness == candidate - 1:
                break
        else:
            return False
    return True


def random_prime(bits: int) -> int:
    """A random prime of exactly `bits` bits.

    The top bit is forced so that two primes of this size always multiply to a
    modulus of exactly `2 * bits` bits, which is what keeps the signature the
    fixed width a verifier expects. The bottom bit is forced because no even
    number above two is prime and testing one is wasted work.

    `secrets` rather than `random`: this is a key, and the fact that it is a
    throwaway key is not a reason to draw it from a predictable stream.
    """
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(candidate):
            return candidate


@dataclass(frozen=True)
class IssuerKey:
    """One RSA key pair, alive for as long as the process that generated it.

    `private_exponent` never leaves this object: `public_jwk()` builds the key
    set entry from the modulus and the public exponent alone, which is the
    difference between publishing a key set and publishing a signing key.
    """

    modulus: int
    public_exponent: int
    private_exponent: int

    @classmethod
    def generate(cls) -> "IssuerKey":
        """A fresh key pair. Called once per application, never cached to disk."""
        half = MODULUS_BITS // 2
        while True:
            first = random_prime(half)
            second = random_prime(half)
            if first == second:
                continue
            modulus = first * second
            if modulus.bit_length() != MODULUS_BITS:
                continue
            # The Carmichael function rather than Euler's totient: RFC 8017 and
            # every current implementation use it, and it yields the smaller
            # private exponent of the two.
            carmichael = (first - 1) * (second - 1) // math.gcd(first - 1, second - 1)
            if carmichael % PUBLIC_EXPONENT == 0:
                # `pow(e, -1, lambda)` would raise; the odds are negligible and
                # the answer is another candidate rather than a special case.
                continue
            return cls(
                modulus=modulus,
                public_exponent=PUBLIC_EXPONENT,
                private_exponent=pow(PUBLIC_EXPONENT, -1, carmichael),
            )

    @property
    def modulus_width(self) -> int:
        """The signature's length in octets, which is the modulus's own width."""
        return (self.modulus.bit_length() + 7) // 8

    @property
    def key_id(self) -> str:
        """The RFC 7638 thumbprint of the public key, used as the JWK `kid`.

        Derived from the key rather than assigned, so the `kid` in a token
        header and the `kid` in the published key set cannot disagree: they are
        the same function of the same modulus.
        """
        return base64url(hashlib.sha256(self.public_key_material()).digest())

    def public_key_material(self) -> bytes:
        """The canonical bytes this key's public half is described by.

        RFC 7638's canonical JWK — `e`, `kty`, `n`, sorted and compact — which
        `key_id` hashes for the thumbprint above. **Also, deliberately, what
        `app.wrong_launches`'s `hs256_confusion` mint uses as an HMAC secret.**
        That mint is the classic RS256-to-HS256 algorithm-confusion bypass: a
        verifier that reads `alg` off the token it is checking, rather than
        fixing the algorithm itself, and is handed "the public key" as generic
        key material, is fooled by a token whose HMAC was computed with that
        exact material. ADR 0035 bars a PEM library on this side of the wall, so
        this canonical encoding — already served, byte for byte, as three
        members of every JWKS response — is what "the public key, as bytes"
        means on this mock. See
        `docs/adr/0088-a-query-parameter-selects-one-wrong-launch-per-mint.md`.
        """
        canonical = json.dumps(
            {
                "e": base64url_uint(self.public_exponent),
                "kty": "RSA",
                "n": base64url_uint(self.modulus),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return canonical.encode("utf-8")

    def public_jwk(self) -> dict[str, Any]:
        """The public half, as one entry of a JWK Set (RFC 7517).

        `d` and the CRT parameters are absent because they are never assembled,
        not because they are filtered out afterwards. A published key set that
        carries any of them has served the signing key to whoever asked.
        """
        return {
            "kty": "RSA",
            "use": "sig",
            "alg": SIGNATURE_ALGORITHM,
            "kid": self.key_id,
            "n": base64url_uint(self.modulus),
            "e": base64url_uint(self.public_exponent),
        }

    def sign(self, signing_input: bytes) -> bytes:
        """An RS256 signature over `signing_input` (RFC 8017 §8.2.1, §9.2).

        The encoding is `pkcs1_v15_encoded` above, raised to the private
        exponent; verification is the same encoding compared against a signature
        raised to a public one.
        """
        width = self.modulus_width
        encoded = pkcs1_v15_encoded(signing_input, width)
        signature = pow(int.from_bytes(encoded, "big"), self.private_exponent, self.modulus)
        return signature.to_bytes(width, "big")

    def compact_jws(self, claims: dict[str, Any]) -> str:
        """`claims` as a signed compact JWS, with the header a tool selects on.

        `kid` is in the header because that is how a tool picks the verifying key
        out of a set, and `typ` because RFC 7519 recommends it for a JWT. The
        signature covers the encoded header and the encoded payload, which is why
        the same encoding is used to build the signing input and to build the
        token rather than the payload being serialised twice.
        """
        header = {"alg": SIGNATURE_ALGORITHM, "typ": "JWT", "kid": self.key_id}
        encoded_header = base64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        encoded_claims = base64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
        return f"{signing_input.decode('ascii')}.{base64url(self.sign(signing_input))}"


def compact_jws_header_and_claims(
    header: dict[str, Any], claims: dict[str, Any]
) -> tuple[str, bytes]:
    """The encoded `header.claims` half of a compact JWS, and the signing input.

    Factored out of `IssuerKey.compact_jws` so that `unsigned_compact_jws` and
    `hs256_compact_jws` below build the identical two segments a real RS256
    token would carry — the encoding is the header a JWT decoder reads
    regardless of whether anything about to follow it is a real signature.
    """
    encoded_header = base64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_claims = base64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    return (
        f"{encoded_header}.{encoded_claims}",
        f"{encoded_header}.{encoded_claims}".encode("ascii"),
    )


def unsigned_compact_jws(claims: dict[str, Any]) -> str:
    """`claims` as a compact JWS carrying `alg: none` and no signature at all.

    E1-07's `alg_none` mint. RFC 7519 permits an unsecured JWT — `alg: none`,
    an empty third segment — and it is the one case this module does not sign,
    on purpose: the defect is that there is nothing here to verify, so building
    one out of `hashlib`/`hmac`/`pow` would be arithmetic in search of a point.
    The trailing dot keeps the compact-JWS shape at three segments, the way a
    real unsecured JWT is written, so a reader splitting on `.` finds an empty
    signature rather than a token that looks truncated.
    """
    joined, _ = compact_jws_header_and_claims({"alg": "none", "typ": "JWT"}, claims)
    return f"{joined}."


def hs256_compact_jws(claims: dict[str, Any], secret: bytes, kid: str) -> str:
    """`claims` as a compact JWS, HMAC-SHA256'd under `secret` rather than signed.

    E1-07's `hs256_confusion` mint — the classic RS256-to-HS256 algorithm
    confusion bypass. `hmac`, stdlib, over `pow`: an HMAC is not RSA arithmetic
    and does not belong beside `sign`'s modular exponentiation, but it is the
    same bound ADR 0035 draws — standard library only, mock-only. `kid` is a
    parameter rather than always this file's own key, so a caller can carry the
    real platform key's id into the header, which is what makes the confusion
    attack the attack it is: a token whose header points at a real RS256 key but
    whose signature is an HMAC.
    """
    joined, signing_input = compact_jws_header_and_claims(
        {"alg": "HS256", "typ": "JWT", "kid": kid}, claims
    )
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    return f"{joined}.{base64url(signature)}"


# ---------------------------------------------------------------------------
# The other direction (E1-06): reading a JWS somebody else signed.
# ---------------------------------------------------------------------------
#
# The platform verifies a `client_assertion` the **tool** signed, against a key
# set it fetches from the tool. That is the same arithmetic as above read
# backwards — the signature raised to a public exponent, compared against the
# encoding `pkcs1_v15_encoded` produces — and it stays in this file for the
# reason ADR 0035 gives about the signing half: nothing in the mock's dependency
# closure does it, the mock has no lockfile of its own, and the bound is that
# none of this is copied into the tool, which uses PyJWT (ADR 0073).


class JwsError(ValueError):
    """A compact JWS could not be read at all: wrong shape, or an unreadable segment.

    Raised by `parse` and by nothing else. Whether a token that *is* a JWS
    verifies is a question with a boolean answer, which `verifies_with` gives, so
    "this is not a token" and "this token is signed by somebody else" stay
    distinguishable here — even though the caller in `app.tokens` deliberately
    answers a refused token request the same way for both.
    """


@dataclass(frozen=True)
class CompactJws:
    """One compact JWS, read but not yet believed.

    Parsing and verifying are two steps and this type is what sits between them,
    so that nothing can read the claims of a token whose signature has not been
    checked without saying so in as many words: `parse` hands back the claims,
    and `verifies_with` is a separate call the caller has to make.
    """

    header: dict[str, Any]
    claims: dict[str, Any]
    signing_input: bytes
    signature: bytes

    @classmethod
    def parse(cls, token: str) -> "CompactJws":
        """Read a `header.claims.signature` token, refusing anything else.

        Both segments must decode to a JSON **object**: a token whose payload is
        an array or a bare string is not a JWT, and a caller reading claims off
        it would be reading attributes of a list.
        """
        parts = token.split(".")
        if len(parts) != 3:
            raise JwsError(
                f"A compact JWS has three dot-separated segments and this has {len(parts)}."
            )
        encoded_header, encoded_claims, encoded_signature = parts
        try:
            header = json.loads(base64url_decoded(encoded_header))
            claims = json.loads(base64url_decoded(encoded_claims))
            signature = base64url_decoded(encoded_signature)
        except ValueError as failure:
            raise JwsError(f"A segment of this compact JWS could not be read: {failure}") from None
        if not isinstance(header, dict) or not isinstance(claims, dict):
            raise JwsError(
                "A compact JWS carries a JSON object in each of its first two segments; this "
                f"carries a {type(header).__name__} and a {type(claims).__name__}."
            )
        return cls(
            header=header,
            claims=claims,
            signing_input=f"{encoded_header}.{encoded_claims}".encode("ascii"),
            signature=signature,
        )

    def verifies_with(self, jwk: Mapping[str, Any]) -> bool:
        """Whether this token's signature is one `jwk` could have produced.

        **`alg` is taken from this file, never from the token.** A JWS header
        names its own algorithm, and a verifier that obeys it accepts `none` and
        accepts an HMAC keyed with the public key it was about to verify against.
        RS256 is what LTI 1.3 specifies and it is the only thing this platform
        signs or checks, so a header naming anything else is refused rather than
        honoured.

        A signature wider than the modulus, or numerically at or above it, is
        refused before `pow` is asked anything: RFC 8017 §8.2.2 makes that a
        malformed signature rather than one to reduce.
        """
        if self.header.get("alg") != SIGNATURE_ALGORITHM:
            return False
        if str(jwk.get("kty")) != "RSA":
            return False
        try:
            modulus = base64url_uint_decoded(str(jwk["n"]))
            public_exponent = base64url_uint_decoded(str(jwk["e"]))
        except (KeyError, ValueError):
            return False

        width = (modulus.bit_length() + 7) // 8
        if len(self.signature) != width:
            return False
        raised = int.from_bytes(self.signature, "big")
        if raised >= modulus:
            return False
        try:
            expected = pkcs1_v15_encoded(self.signing_input, width)
        except ValueError:
            # A modulus too small to carry a SHA-256 DigestInfo. No signature
            # over it can be valid, so this is a refusal rather than a failure.
            return False
        recovered = pow(raised, public_exponent, modulus).to_bytes(width, "big")
        # Constant time is not required — every value here is public — but it
        # costs nothing and keeps the comparison honest for anyone reading the
        # file for a pattern to copy.
        return secrets.compare_digest(recovered, expected)
