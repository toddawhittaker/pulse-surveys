"""The tool's own JWKS route: the public half of `tool_signing_key`, and nothing else — E1-06.

This is part 4 of the four the carried entry moves together, and it is the ⚠ half
of the ticket: "the tool's first cryptographic production endpoint". A platform
cannot verify a `client_assertion` this tool signs without the tool's public key,
so the tool has to publish one — and the route that does it is public, ungated,
and one mistake away from publishing the private half instead.

**Four properties, one test each, because each fails differently.**

  - **It answers in every environment.** Criterion 4's own words. A key set served
    only in development is a tool that cannot be registered anywhere it matters,
    and the failure appears at the first service call rather than at deployment.
  - **It carries one RSA signing key, shaped as RFC 7517 shapes one.** ADR 0082
    stores exactly one key and forbids rotation, so a key set with two keys is a
    tool with two identities and a key set with none is a document that verifies
    nothing.
  - **Its `kid` is the key's RFC 7638 thumbprint.** A platform selects a
    verification key by `kid`, and the tool puts the same value in the header of
    every assertion it signs. Any stable string works right up until the two are
    computed in different places.
  - **It is the public half of the stored key, and it carries no private
    material.** Those are two assertions rather than one: a route can serve a
    correct public key *and* a `d` beside it, and it can serve a private-free
    document describing a key that signs nothing.

**Why the key is planted rather than seeded.** `tests/integration/
test_tool_signing_key_custody.py` owns what the seed writes. What is under test
here is the route's *reading*: given a row, does it publish that row's public half?
A test that seeded the key and then read it back would have the same value on both
sides by construction, and could not tell a route that derives the public key from
the stored one apart from a route that generates a fresh key per request
(`docs/MISTAKES.md` entry 30).

**The grant this route needs is pinned somewhere else, deliberately.** ADR 0082
left `tool_signing_key` with no `pulse_app` grant in E1-05 — "a runtime role
holding read access to a private key it never opens is a credential at rest with no
owner" — and E1-06 adds `SELECT` with the code that spends it. That widening is
recorded as an equality in
`tests/integration/test_identity_grants.py::RUNTIME_BASE_TABLE_PRIVILEGES`, which is
where a grant on this table has its loud conversation. Without it every test in
this module fails on a 500 rather than on its own assertion, so that is the first
thing to check if they all go red together.
"""

import base64
import json
from typing import Any

import pytest

pytestmark = pytest.mark.integration

# The route, settled by the E1-06 dispatch brief. Not discovered from a candidate
# list: this is a public URL a platform is registered with, so a spelling nobody
# fixed is a spelling that changes under whoever already stored it.
TOOL_JWKS_PATH = "/lti/jwks"

# `tool_signing_key` and its one column, spelled as E1-05's work order spells them
# and as `tests/integration/test_tool_signing_key_custody.py` does.
SIGNING_KEYS = "tool_signing_key"
PRIVATE_KEY_COLUMN = "private_key_pem"

# `ENVIRONMENT` and the two values that decide whether a gate fires, spelled as
# `tests/integration/test_lti_launch_door.py` spells them.
ENVIRONMENT_VARIABLE = "ENVIRONMENT"
DEVELOPMENT = "development"
PRODUCTION = "production"

# What PEM private-key armour looks like, assembled from pieces rather than
# written out: the repository-wide sweep in
# `tests/unit/test_mock_lms_service.py::test_no_private_key_material_is_committed_to_the_repository`
# reads every file including this one, and a module that is its own offender
# teaches everybody to add an exclusion.
PEM_PRIVATE_MARKER = "PRIVATE" + " KEY-----"

# RSA's key size, as E1-05 fixes it. Used only to generate the key this module
# plants, so that the row under test looks like the row the seed writes.
KEY_BITS = 2048


def generated_pem() -> tuple[str, Any]:
    """A fresh RSA private key, as PKCS#8 PEM and as an object, generated here.

    SPEC §9.1: keys are generated per test run rather than checked in. Both halves
    are handed back because the assertions below need the PEM to plant and the key
    object to compare the served public half against.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_BITS)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return pem, key


def decoded_base64url(value: str) -> int:
    """One RSA parameter out of a JWK: base64url, big-endian, unpadded (RFC 7518 §6.3)."""
    padded = value + "=" * (-len(value) % 4)
    return int.from_bytes(base64.urlsafe_b64decode(padded), "big")


def served_key_set(client: Any) -> dict[str, Any]:
    """`GET /lti/jwks` as a JWK Set, or a failure naming the missing deliverable."""
    response = client.get(TOOL_JWKS_PATH)
    assert response.status_code == 200, (
        f"`GET {TOOL_JWKS_PATH}` answered {response.status_code} rather than 200. E1-06 part 4 "
        "adds this route: the tool signs a `client_assertion` and the platform verifies it "
        "against the key set the tool publishes, so a key set nobody can fetch verifies nothing. "
        "A 500 here rather than a 404 is most likely the missing `SELECT` grant on "
        f"`{SIGNING_KEYS}` — see this module's docstring. Body begins {response.text[:300]!r}."
    )
    document = response.json()
    assert isinstance(document, dict), (
        f"`GET {TOOL_JWKS_PATH}` served {document!r}, which is not a JWK Set. RFC 7517 §5 makes a "
        "key set a JSON object with a `keys` member."
    )
    return document


def the_one_key(document: dict[str, Any]) -> dict[str, Any]:
    """The single key in a served key set, or a failure saying how many there were."""
    keys = document.get("keys")
    assert isinstance(keys, list), (
        f"The published key set carries `keys` {keys!r}. RFC 7517 §5 makes it a JSON array of "
        "JWK values; a bare key, or the key under another member, is a document no platform's "
        "key-set reader accepts."
    )
    assert len(keys) == 1, (
        f"The published key set carries {len(keys)} keys. ADR 0082 stores exactly one signing key "
        "and forbids rotation — 'two rows is not an untidy state to reconcile later, it is two "
        "identities for one tool' — so zero keys is a document that verifies nothing and two is a "
        "tool a platform can be made to accept two signatures from."
    )
    key = keys[0]
    assert isinstance(key, dict), f"The published key is {key!r} rather than a JWK object."
    return key


@pytest.fixture
def stored_signing_key(committed_rows: Any, metadata_tables: dict[str, Any]) -> tuple[str, Any]:
    """One `tool_signing_key` row, planted by this test, and the key it holds.

    Planted rather than seeded, for the reason this module's docstring gives: the
    route's job is to publish the public half of *the row that is there*, and a
    key this suite did not choose could not tell that apart from a key the route
    made up.
    """
    if SIGNING_KEYS not in metadata_tables:
        pytest.fail(
            f"There is no `{SIGNING_KEYS}` table (what is there: {sorted(metadata_tables)}). "
            "E1-05 adds it and E1-06 is the ticket that reads it; without the row there is no "
            "key for this route to publish and every test here would be about an absence."
        )
    pem, key = generated_pem()
    committed_rows.seed(SIGNING_KEYS, {}, **{PRIVATE_KEY_COLUMN: pem})
    committed_rows.commit()
    return pem, key


@pytest.fixture
def open_the_tool(tool_doors: Any, door_contract: Any) -> Any:
    """Build the application, optionally under an environment a test names."""

    def build(environment: str | None = None) -> Any:
        values = {door_contract.settings["public_base_url"]: door_contract.public_base_url}
        if environment is not None:
            values[ENVIRONMENT_VARIABLE] = environment
        return tool_doors(values, {})

    return build


@pytest.mark.parametrize(
    "environment",
    [pytest.param(DEVELOPMENT, id="development"), pytest.param(PRODUCTION, id="production")],
)
def test_the_tools_key_set_is_served_in_every_environment(
    stored_signing_key: tuple[str, Any], open_the_tool: Any, environment: str
) -> None:
    """Criterion 4: "the tool's JWKS route serves the public key in every environment".

    **Which parameter kills what.** `production` kills a route registered behind
    `settings.environment == "development"`, which is the shape this repository
    reaches for by habit — `/docs` (ADR 0074), `/dev` (ADR 0079) and the demo seed
    (ADR 0063) are all gated that way, so a new route written next to them
    inherits the gate without anybody deciding to. A tool whose key set answers
    404 in production cannot be registered at a real platform at all, and nothing
    else in the suite would notice, because every other test runs in development.
    `development` kills the opposite mistake — a route somehow available only to a
    deployment — and is what keeps the pair from being satisfied by a route that
    answers everywhere for the wrong reason.

    **The near miss it must survive**: `/dev`'s shape (ADR 0079), where the route
    is registered in every environment and only the *handler* is gated. That
    answers 200 in development and 404 in production, which this parametrization
    catches and a single-environment test would not.
    """
    document = served_key_set(open_the_tool(environment))

    assert the_one_key(document), (
        f"The key set served under `{ENVIRONMENT_VARIABLE}={environment}` carries no key. A "
        "route that answers 200 with an empty document is a platform fetching a key set and "
        "finding nothing to verify with, which fails at the first client assertion rather than "
        "here."
    )


def test_the_published_key_set_carries_exactly_one_rsa_signing_key(
    stored_signing_key: tuple[str, Any], open_the_tool: Any
) -> None:
    """RFC 7517's shape, and the four members a platform reads before it trusts anything.

    **The mutations this kills.** A key with no `kid`, which leaves a platform
    unable to select it and which is the member the next test is entirely about. A
    key with no `alg` or `use`, which some platform key readers require and which
    every one of them uses to decide whether this key may verify a signature at
    all. And `kty` anything but `RSA` — the tool signs RS256 with an RSA key, and
    a document that says otherwise describes a key it does not hold.

    `n` and `e` are asserted present and non-empty here and asserted *correct*
    two tests down; the split is deliberate, because "the document is shaped like
    a key set" and "the key in it is this tool's key" fail for different reasons
    and a reader is better off seeing which.
    """
    key = the_one_key(served_key_set(open_the_tool()))

    expected = {"kty": "RSA", "use": "sig", "alg": "RS256"}
    wrong = {name: key.get(name) for name, value in expected.items() if key.get(name) != value}
    needed = {name: expected[name] for name in wrong}
    assert not wrong, (
        f"The published key states {wrong} where RFC 7517 and this tool's own signing need "
        f"{needed}. `use` and `alg` are what tell a platform this key may verify a signature and "
        "which algorithm it verifies; a key set that omits them is one some platform key readers "
        "skip entirely, and the failure is a client assertion refused for a reason that names no "
        "key."
    )
    for member in ("kid", "n", "e"):
        assert isinstance(key.get(member), str) and key[member], (
            f"The published key carries `{member}` {key.get(member)!r}. RFC 7517 makes all three "
            "REQUIRED for an RSA signing key: `n` and `e` are the key, and `kid` is how a "
            "platform picks it out of a set."
        )


def test_the_published_key_identifier_is_the_thumbprint_of_the_key_it_names(
    stored_signing_key: tuple[str, Any], open_the_tool: Any, thumbprint_of: Any
) -> None:
    """ADR 0082: the `kid` is derived from the key, never stored beside it.

    "Only the private half is stored. The public key and the RFC 7638 `kid` are
    both derived from it on read. A stored copy of something derivable is a copy
    that can drift out of step with what it was derived from" — and here the drift
    would be a key set advertising a key that no longer signs anything.

    **The mutations this kills:** a `kid` that is a constant, a row id, or a
    timestamp. Every one of those is stable, plausible, and works perfectly until
    the tool and the platform compute it in two places — which is exactly what
    happens when a real LMS reads this document and the tool puts its own value in
    an assertion header.

    The expected value is computed from RFC 7638 in
    `tests/fixtures/client_credentials.py` rather than taken from anything the
    implementation produces (`docs/MISTAKES.md` entry 19), and the control below
    exercises that computation in both directions before this comparison is
    believed.
    """
    key = the_one_key(served_key_set(open_the_tool()))

    assert key.get("kid") == thumbprint_of(key), (
        f"The published key names itself {key.get('kid')!r} and its RFC 7638 thumbprint is "
        f"{thumbprint_of(key)!r}. A platform selects a verification key by `kid` and the tool "
        "writes one into every assertion header it signs; any stable string works until those two "
        "values are computed somewhere different, and then every assertion is refused with an "
        "error about a key rather than about a name."
    )


def test_the_published_key_is_the_public_half_of_the_stored_signing_key(
    stored_signing_key: tuple[str, Any], open_the_tool: Any
) -> None:
    """The document describes the key this tool actually signs with.

    **The mutations this kills:** a route that generates a key pair per request or
    per process — which serves a perfectly well-formed key set that verifies
    nothing this tool ever signed, and which is precisely the arrangement ADR 0082
    rejects ("two processes signing with two keys means half the assertions are
    rejected"); and a route that reads some *other* row, or a hardcoded key left
    over from development.

    **Both halves, because each catches what the other misses.** The public
    numbers are compared, which says the served key *is* this row's key and fails
    with two integers a reader can see. And a signature made with the stored
    private key is verified against the served `n` and `e`, which says the served
    encoding is one a verifier can actually use — a modulus written with padding,
    or big-endian the wrong way round, compares unequal in the first half and
    would be a puzzle without the second.

    **The near miss it must survive**, and the reason the second half is not on
    its own: a verifier that accepts everything. So the same signature is checked
    against a *different* key and required to be refused.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    _, stored = stored_signing_key
    key = the_one_key(served_key_set(open_the_tool()))

    served_numbers = (decoded_base64url(key["n"]), decoded_base64url(key["e"]))
    stored_numbers = stored.public_key().public_numbers()
    assert served_numbers == (stored_numbers.n, stored_numbers.e), (
        "The published key is not the public half of the stored signing key. Served modulus "
        f"{served_numbers[0]} exponent {served_numbers[1]}; stored modulus {stored_numbers.n} "
        f"exponent {stored_numbers.e}. A platform holding this document verifies nothing this "
        "tool signs, and the failure arrives at the platform as a rejected signature."
    )

    message = b"e1-06: an assertion this tool would sign"
    signature = stored.sign(message, padding.PKCS1v15(), hashes.SHA256())
    public_key = rsa.RSAPublicNumbers(served_numbers[1], served_numbers[0]).public_key()
    public_key.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())

    _, other = generated_pem()
    other_numbers = other.public_key().public_numbers()
    other_public = rsa.RSAPublicNumbers(other_numbers.e, other_numbers.n).public_key()
    with pytest.raises(InvalidSignature):
        other_public.verify(signature, message, padding.PKCS1v15(), hashes.SHA256())


def test_the_published_key_set_carries_no_private_key_material(
    stored_signing_key: tuple[str, Any], open_the_tool: Any, private_key_members_in: Any
) -> None:
    """Criterion 4's second half: "never the private half (asserted, not assumed)".

    **The mutation this kills:** serialising the key pair rather than its public
    half — one call apart in every JOSE library there is, and the result is a
    document that works perfectly. Every other test in this module passes against
    it: the key set has one RSA key, its `kid` is right, its `n` and `e` verify a
    signature. The only difference is a `d` beside them, and the tool's identity
    is then readable by anyone who can reach the route this ticket makes public in
    every environment.

    **Two detectors, because a private key can leave by two doors.** The JWK
    members RFC 7517 and RFC 7518 define — `d`, `p`, `q`, `dp`, `dq`, `qi`, `k` —
    found anywhere in the document rather than only inside `keys`, because a
    private half in a debug member is the same disclosure. And the raw response
    text, checked against the stored PEM and against PEM armour of any kind, which
    catches the other shape entirely: a route that helpfully includes the value it
    read from the column.

    The detector's own control is next door and must be green before this test's
    silence counts for anything.
    """
    pem, _ = stored_signing_key
    client = open_the_tool()
    document = served_key_set(client)
    response = client.get(TOOL_JWKS_PATH)

    found = private_key_members_in(document)
    assert not found, (
        f"The published key set carries the private JWK member(s) {found}: "
        f"{json.dumps(document)[:400]}. That is the tool's private signing key, served by a "
        "route this ticket makes public in every environment — the whole of the tool's LTI "
        "identity, to anyone who asks."
    )
    assert pem.strip() not in response.text, (
        "The published key set carries the stored PEM itself. The route reads "
        f"`{SIGNING_KEYS}.{PRIVATE_KEY_COLUMN}` and has evidently put it in the response."
    )
    assert PEM_PRIVATE_MARKER not in response.text, (
        "The published key set carries PEM private-key armour, which is either the key this row "
        f"holds or another one the route handled on the way past. Body begins "
        f"{response.text[:300]!r}."
    )


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the route.**
# ---------------------------------------------------------------------------


def test_the_private_member_detector_finds_a_private_key_and_ignores_a_public_one(
    private_key_members_in: Any,
) -> None:
    """The canary on the test above, run before its silence is believed.

    `docs/MISTAKES.md` entry 3: run the detector against the document you claim it
    catches *and* against the one you claim it allows. Both halves matter and the
    second is the one people leave out — a detector that answered "private" for
    everything would make the test above fail loudly and get "corrected" without
    anyone learning it was wrong in both directions.

    The nested case is not padding. It is the whole reason the detector walks the
    document rather than the `keys` array: a private half beside the key set, in a
    diagnostic member, is the same key in the same response.

    **A red here means these tests are broken, not the code.**
    """
    public_key = {"kty": "RSA", "use": "sig", "alg": "RS256", "kid": "k", "n": "AQ", "e": "AQAB"}
    public_only = {"keys": [public_key]}
    assert private_key_members_in(public_only) == []

    with_private_half = {"keys": [{**public_key, "d": "AQ", "p": "AQ"}]}
    assert private_key_members_in(with_private_half) == ["d", "p"]

    tucked_away = {"keys": [public_key], "debug": {"loaded": {"kty": "RSA", "d": "AQ"}}}
    assert private_key_members_in(tucked_away) == ["d"]


def test_the_thumbprint_these_tests_compute_ignores_every_member_rfc_7638_excludes(
    thumbprint_of: Any,
) -> None:
    """The control on the `kid` test: the two ways to compute a thumbprint wrongly.

    RFC 7638 §3.2 hashes exactly `e`, `kty` and `n`, in lexicographic order, with
    no whitespace. There are two ways to get that wrong and both produce a stable,
    plausible value that would agree with an implementation making the same
    mistake.

    **Hashing the whole JWK.** Then adding `use`, `alg` or `kid` changes the
    answer — so a tool whose document carries an `alg` and a platform's library
    that does not would compute two different identifiers for one key. The first
    assertion is that adding them changes nothing.

    **Not hashing the key at all** — a constant, or the `kid` echoed back. The
    second assertion is that a different modulus gives a different thumbprint,
    which is what makes the identifier identify anything.

    **A red here means these tests are broken, not the code.**
    """
    bare = {"kty": "RSA", "n": "0vx7ago", "e": "AQAB"}
    decorated = {**bare, "use": "sig", "alg": "RS256", "kid": "something-else"}
    assert thumbprint_of(bare) == thumbprint_of(decorated), (
        "The thumbprint changed when `use`, `alg` and `kid` were added. RFC 7638 §3.2 hashes only "
        "`e`, `kty` and `n` for an RSA key, so a computation that reads the whole JWK gives two "
        "answers for one key depending on how it was decorated."
    )
    assert thumbprint_of(bare) != thumbprint_of({**bare, "n": "0vx7agp"}), (
        "Two different keys have the same thumbprint, so the value identifies nothing and the "
        "`kid` assertion above would pass against a route that answers a constant."
    )
    assert len(thumbprint_of(bare)) == 43, (
        f"The thumbprint is {len(thumbprint_of(bare))} characters. A SHA-256 digest in unpadded "
        "base64url is 43, and a different length means the encoding — padding, or standard "
        "base64 rather than the URL alphabet — is not what RFC 7638 asks for."
    )
