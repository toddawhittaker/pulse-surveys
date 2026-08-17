"""The mock platform's launch, driven the way a tool drives one — ticket E0-14.

E0-14 builds the *platform* side of an LTI 1.3 launch: per-run issuer keys, a
JWKS endpoint, an authorization endpoint that answers with a signed `id_token`,
and a launch page a browser can click through. Everything below asserts what the
platform produces.

**What is deliberately not here.** Tool-side validation — refusing a replayed
nonce, a mismatched `state`, a token outside its clock-skew window, a signature
from an unregistered key — is E1's, and E0-14's out-of-scope list says so in
those words: "The mock produces launches; validating them is E1's work." So there
is no test below of what Pulse does when it receives one of these. The two
negative cases that *are* here are not tool-side validation wearing a disguise;
they are controls on this module's own verifier, and they are labelled as such.
Without them, `verify_rs256` returning `True` unconditionally would make the
signature criterion pass, which is `docs/MISTAKES.md` entry 3 exactly.

**What this suite gives E1.** `mock_platform.mint(...)` in `tests/conftest.py` is
the fixture E0-14's definition of done asks for. It mints by being the tool —
reading the platform's initiation request off the launch page and answering it
with an authorization request — so a launch obtained here and a launch a browser
produces are the same launch, and E1's validation tests can build on it without
inheriting a shortcut. What E1 will additionally need, and what E0-14 does not
ask for, is a way to mint a *deliberately wrong* launch: an expired token, a
foreign signature, a replayed nonce. That is E1's to specify, and inventing the
interface for it here would decide it.

**Where the registration values come from.** No endpoint publishes them, and
E0-14 names none. They do not need one: the OIDC third-party-initiated login
request the launch page carries *is* the platform announcing its issuer, its
client ID, its deployment ID and the target link URI, so every claim comparison
below reads its expected value out of that form. The one thing this cannot reach
is the value of a registration field the initiation request does not carry.

**The verifier is written out of `pow` and `hashlib`** in `tests/conftest.py`,
because nothing in this project's locked dependency set verifies a JSON Web
Signature and adding one to satisfy a test would decide, from the test side,
which JOSE library the mock signs with. RS256 is required rather than merely
accepted: the IMS security framework LTI 1.3 rests on specifies it, and SPEC §7.3
asks for strict LTI 1.3 core.
"""

import base64
import json
import re
import time
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.lti

# `mock_platform`, `mock_platforms` and `signed_launch` come from
# `tests/conftest.py`, and everything this module needs from the platform is
# reached through them rather than imported. That is deliberate: a test module
# that imports its sibling `conftest` by name depends on where pytest happened
# to put `tests/` on `sys.path`, and an import error is not a red — it is a
# broken suite that reports nothing about the ticket.
#
# The fixtures are annotated `Any` for the same reason. `MockPlatform`,
# `SignedLaunch` and `LaunchOffer` are documented on the class in
# `tests/conftest.py`; mypy checks `backend/app` only, so nothing is lost but
# the reading.

# The one signature algorithm this suite verifies. Not a preference: the IMS
# security framework LTI 1.3 rests on requires RS256 for message signing, and
# SPEC §7.3 asks for strict LTI 1.3 core. A launch signed with anything else is
# one E1 could not validate with a conformant library, so the right answer is a
# red rather than a wider verifier.
REQUIRED_SIGNATURE_ALGORITHM = "RS256"

# The members that make a JSON Web Key a *private* key, from RFC 7517 and
# RFC 7518: `d` for RSA and EC, `k` for a symmetric key, and RSA's CRT
# parameters. A published key set carrying any of them has served the signing
# key to whoever asked.
PRIVATE_JWK_MEMBERS = ("d", "p", "q", "dp", "dq", "qi", "k")

# The LTI 1.3 message claims, spelled as the specification spells them. Not this
# suite's choice in any part: a claim under a different name is a claim
# `pylti1p3` (SPEC §7.1) will not read.
LTI_CLAIM = "https://purl.imsglobal.org/spec/lti/claim/"
MESSAGE_TYPE_CLAIM = LTI_CLAIM + "message_type"
VERSION_CLAIM = LTI_CLAIM + "version"
DEPLOYMENT_ID_CLAIM = LTI_CLAIM + "deployment_id"
TARGET_LINK_URI_CLAIM = LTI_CLAIM + "target_link_uri"
RESOURCE_LINK_CLAIM = LTI_CLAIM + "resource_link"
CONTEXT_CLAIM = LTI_CLAIM + "context"
ROLES_CLAIM = LTI_CLAIM + "roles"

RESOURCE_LINK_MESSAGE_TYPE = "LtiResourceLinkRequest"
LTI_VERSION = "1.3.0"

# Every LTI role is a URI in one of the LIS v2 vocabularies — membership,
# institution/person, system/person — and all three share this stem. LTI 1.3
# permits the bare context-role names (`Learner`) only as a deprecated
# compatibility form, and SPEC §7.3 asks for strict core, so a mock that emits
# one would hand E1 a shape it should not learn to read.
LIS_VOCABULARY = "http://purl.imsglobal.org/vocab/lis/v2/"

# How far out of step the mock's clock and this test's may be before a freshly
# issued token looks like it was issued in the future. **This suite's choice**,
# and generous: both clocks are the same clock.
CLOCK_TOLERANCE_SECONDS = 60

# Where the launch form is pointed to prove it is pointed by configuration. The
# `.invalid` top-level domain is reserved by RFC 2606 and can never resolve, so
# this value cannot be mistaken for a real destination if it leaks into a
# fixture. **This suite's choice.**
MARKER_LAUNCH_TARGET = "http://tool.invalid/lti/login-marker"

# `${NAME}`, `${NAME:-default}`, `${NAME-default}`, `${NAME:?message}`.
COMPOSE_VARIABLE = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?P<rest>[^}]*)\}")


def resolve(value: str, documented: dict[str, str]) -> str:
    """Expand Compose's `${...}` forms out of `.env.example`.

    Twice, because `.env.example` builds some values out of others and Compose
    expands them transitively — `DATABASE_URL` is the standing example. Two
    passes is not a general fixed point and is not meant to be; it is what this
    repository's own file needs, and a value that is still unresolved after it
    simply fails to match, which is a red rather than a wrong answer.

    `${NAME:-default}` falls back to its default and `${NAME:?message}` falls
    back to nothing, because the second form's tail is an error message rather
    than a value and treating it as one would invent a URL.
    """

    def expand(match: re.Match[str]) -> str:
        documented_value = documented.get(match.group("name"))
        if documented_value:
            return documented_value
        tail = match.group("rest")
        if tail.startswith((":-", "-", ":+", "+")):
            return tail.lstrip(":-+")
        return ""

    for _ in range(2):
        value = COMPOSE_VARIABLE.sub(expand, value)
    return value


def configured_environment(
    documents: tuple[dict[str, Any], ...],
    service: str,
    documented: dict[str, str],
) -> dict[str, str]:
    """Everything the Compose files put into the `service` container's environment.

    Both the `environment:` block and, where the service pulls the whole
    configuration surface in with `env_file: .env`, the documented variables
    themselves — because `api` is written the second way and a mock written
    beside it may be too. Which of the two the implementer chooses is not
    something this test decides; what it needs is the set of values the container
    would hold.
    """
    values: dict[str, str] = {}
    for document in documents:
        declared = (document.get("services") or {}).get(service)
        if not isinstance(declared, dict):
            continue
        files = declared.get("env_file")
        if files and ".env" in str(files):
            values.update({name: resolve(value, documented) for name, value in documented.items()})
        block = declared.get("environment")
        if isinstance(block, dict):
            pairs = [(str(name), str(value)) for name, value in block.items() if value is not None]
        elif isinstance(block, list):
            pairs = [
                (entry.split("=", 1)[0], entry.split("=", 1)[1])
                for entry in block
                if isinstance(entry, str) and "=" in entry
            ]
        else:
            pairs = []
        values.update({name: resolve(value, documented) for name, value in pairs})
    return values


def claim(launch: Any, name: str) -> Any:
    """One claim, or a failure listing what the token does carry."""
    if name not in launch.claims:
        pytest.fail(
            f"The `id_token` carries no `{name}` claim. It carries {sorted(launch.claims)}. "
            "E0-14 criterion 4: an issued token contains every LTI 1.3 required claim."
        )
    return launch.claims[name]


def announced(offer: Any, name: str) -> str:
    """One parameter of the platform's own initiation request, or a failure.

    These are the values the launch page publishes about itself, and they are
    what the claims below are compared against. A missing one is worth a red
    naming it rather than a comparison quietly skipped: without `client_id`, for
    instance, nothing can say what the token's `aud` ought to be.
    """
    value = offer.parameters.get(name)
    if not value:
        pytest.fail(
            f"The launch form publishes no `{name}` (it publishes "
            f"{sorted(offer.parameters)}). The OIDC third-party-initiated login request is "
            "where a platform announces itself to a tool, and it is the only place E0-14 "
            "gives a test to learn the seeded registration values from."
        )
    return value


def launches_across_seeded_offers(platform: Any) -> list[Any]:
    """One minted launch per launch the platform's page offers."""
    return [platform.mint(offer) for offer in platform.require_offers()]


# ---------------------------------------------------------------------------
# The key set, and the signature over it. Criteria 2 and 3.
# ---------------------------------------------------------------------------


def test_the_jwks_endpoint_serves_at_least_one_key(mock_platform: Any) -> None:
    """Criterion 2's precondition, asserted before anything rests on it.

    Catches a JWKS endpoint that answers 200 with `{"keys": []}` — which is a
    valid JWK Set and a platform whose launches nothing can ever verify. Every
    test below searches that list, and a search of an empty list is the emptiness
    `docs/MISTAKES.md` entry 3 is about.
    """
    keys = mock_platform.published_keys()
    assert keys, (
        "The JWKS endpoint serves no keys. E0-14 criterion 2 is that it serves a key which "
        "verifies the signature on an issued `id_token`, and an empty key set verifies "
        "nothing while answering 200 like a working one."
    )


def test_the_published_key_set_carries_no_private_key_material(
    mock_platform: Any,
) -> None:
    """A JWKS publishes public halves. Catches a serializer that dumped the pair.

    The mistake is one line — serialising the generated key rather than its
    public half — and it breaks nothing: every launch still verifies, because the
    public members are all present alongside. E0-14's security review asks that
    the mock's keys are never reused as anything but test keys, and a signing key
    served over HTTP has stopped being anybody's key.
    """
    keys = mock_platform.published_keys()
    assert keys, "The JWKS endpoint serves no keys, so this test has nothing to inspect."
    leaked = [
        (key.get("kid"), sorted(set(key) & set(PRIVATE_JWK_MEMBERS)))
        for key in keys
        if set(key) & set(PRIVATE_JWK_MEMBERS)
    ]
    assert not leaked, (
        f"The published key set carries private key material: {leaked}. RFC 7517 makes `d`, "
        "`p`, `q`, `dp`, `dq`, `qi` and `k` the private members of a JWK; publishing any of "
        "them serves the signing key to anyone who asks. Serialise the public half."
    )


def test_the_id_token_is_signed_with_rs256_and_names_a_published_key(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The header a tool selects a key with. Catches `alg: none` and a missing `kid`.

    Two failures, both of which leave a launch that still "works" against a
    permissive reader. An `alg` of `none` produces a token with an empty
    signature that a decoder happily parses; an HS256 token verifies against a
    shared secret and makes the whole JWKS decorative. A missing or unmatched
    `kid` leaves a tool guessing which published key to try, which is exactly the
    ambiguity a key set exists to remove — and it goes unnoticed for as long as
    the platform publishes only one key.
    """
    algorithm = signed_launch.header.get("alg")
    assert algorithm == REQUIRED_SIGNATURE_ALGORITHM, (
        f"The `id_token` is signed with `alg` {algorithm!r} rather than "
        f"{REQUIRED_SIGNATURE_ALGORITHM!r}. The IMS security framework LTI 1.3 rests on "
        "specifies RS256 for message signing, and SPEC §7.3 asks for strict LTI 1.3 core: a "
        "symmetric algorithm makes the published key set irrelevant, and `none` makes the "
        "signature itself irrelevant."
    )
    published = {key.get("kid") for key in mock_platform.published_keys()}
    assert signed_launch.header.get("kid") in published, (
        f"The `id_token` header names key {signed_launch.header.get('kid')!r}, which is not "
        f"among the published key IDs {sorted(k for k in published if k)}. A tool selects the "
        "verifying key by `kid`; with one key published this is invisible, and it becomes a "
        "launch nobody can validate the first time the platform rotates."
    )


def test_the_id_token_signature_verifies_against_the_published_key_set(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Criterion 2. Catches a platform that signs with one key and publishes another.

    The failure this exists for is not exotic — it is a second key pair created
    somewhere in the startup path, or a JWKS built from a freshly generated key
    rather than from the one the signer holds. Nothing else notices: the token
    parses, every claim is right, the key set is well formed, and only the
    arithmetic disagrees.
    """
    assert mock_platform.verifies(signed_launch.signature) is not None, (
        "No key in the published set verifies the signature on the issued `id_token`. E0-14 "
        "criterion 2 is exactly this agreement — the JWKS has to serve what the launch was "
        "signed with, or every tool that trusts this platform rejects every launch."
    )


def test_a_launch_from_another_platform_is_refused_by_this_platforms_key_set(
    mock_platform: Any,
    mock_platforms: Any,
) -> None:
    """The control on the test above, not a test of tool-side validation.

    A verifier that answered `True` for everything would satisfy every signature
    assertion in this module, and would do it silently — `docs/MISTAKES.md` entry
    3's "a test passed for a reason unrelated to what it asserted". So it is shown
    saying no, and the wrong key is a real one from a second platform rather than
    a corrupted blob, because a near miss is what a decode-only verifier accepts.

    That this is *also* the shape of an E1 requirement is a coincidence of the
    protocol. E1 owns refusing a foreign signature at the tool; this owns knowing
    that the verifier below it works.
    """
    stranger = mock_platforms().mint()
    assert mock_platform.verifies(stranger.signature) is None, (
        "A launch signed by a different platform instance verified against this platform's "
        "published key set. Either the two instances share a key — which is criterion 3's "
        "failure, keys not generated per run — or the verifier in tests/conftest.py is "
        "decoding rather than verifying, in which case every signature assertion in this "
        "module is vacuous."
    )


def test_a_tampered_payload_is_refused_by_the_published_key_set(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The second control: the signature covers the claims, and the verifier notices.

    A verifier that checked only that the signature decodes under the public
    exponent, or that compared only the trailing digest and not PKCS#1 padding,
    accepts a token whose payload has moved. So does a platform that signs one
    payload and serves another.

    The payload is re-encoded from altered claims rather than corrupted a
    character at a time, and the difference is the point: a random character
    change usually produces something that is no longer JSON, so the verifier
    would never be reached and the test would report a decode failure as a
    refusal. This tampered token is well formed in every respect except the
    arithmetic, which is the only thing being asked about.
    """
    encoded_header, _, encoded_signature = signed_launch.id_token.split(".")
    altered = dict(signed_launch.claims)
    altered["sub"] = f"{altered.get('sub', '')}-tampered"
    encoded_claims = (
        base64.urlsafe_b64encode(json.dumps(altered).encode("utf-8")).rstrip(b"=").decode("ascii")
    )
    tampered = f"{encoded_header}.{encoded_claims}.{encoded_signature}"

    assert mock_platform.verifies(tampered) is None, (
        "A token whose payload was altered after signing still verified against the "
        "published key set. The verifier in tests/conftest.py is not checking the signature "
        "over the payload, so every other signature assertion in this module means nothing."
    )


def test_two_platform_instances_publish_different_issuer_keys(mock_platforms: Any) -> None:
    """Criterion 3's first half: keys are generated per run, not loaded.

    Catches the implementation the criterion is written against — a key pair
    generated once and read from a file, an environment variable, or a constant
    in the image. Every other test in this module passes against it: the launches
    verify, the key set is well formed, nothing is published that should not be.
    The only observable difference is that a second start of the platform is the
    same platform, which is what makes the private half a durable credential
    rather than a value that exists for one run.

    `tests/unit/test_mock_lms_service.py` holds the other half — that no private
    key is committed — and neither implies the other. A key baked into a
    Dockerfile is absent from the tree and identical on every run; a key generated
    per run and also checked in is different every run and still committed.
    """
    first = {key["n"] for key in mock_platforms().published_keys() if key.get("n")}
    second = {key["n"] for key in mock_platforms().published_keys() if key.get("n")}
    assert first and second, (
        "A platform instance published no RSA key material, so the comparison below would be "
        "between two empty sets — which agree about nothing and would pass."
    )
    assert not (first & second), (
        "Two independently started platform instances published the same key material. E0-14 "
        "criterion 3 and SPEC §9.1: issuer keys are generated per test run rather than taken "
        "from a fixture. A key that survives a restart is a credential, and it is the same "
        "credential in every checkout of this repository."
    )


# ---------------------------------------------------------------------------
# The claims. Criterion 4, field by field.
# ---------------------------------------------------------------------------


def test_the_id_token_carries_the_registered_jwt_claims(signed_launch: Any) -> None:
    """The six the JWT and OIDC layers require, before any LTI claim.

    Catches a token built as a bag of LTI claims with the JWT envelope left to a
    library's defaults. `sub` in particular is not decoration: SPEC §4 keys every
    response to "the LMS user ID (`sub` from the launch)", so a launch without one
    identifies nobody and a launch with a non-string one identifies something
    that cannot be a key.
    """
    for name in ("iss", "sub", "aud", "nonce"):
        value = claim(signed_launch, name)
        assert value, f"The `id_token`'s `{name}` claim is empty ({value!r})."
    for name in ("iss", "sub", "nonce"):
        assert isinstance(claim(signed_launch, name), str), (
            f"The `id_token`'s `{name}` claim is {type(claim(signed_launch, name)).__name__} "
            "rather than a string."
        )
    for name in ("exp", "iat"):
        assert isinstance(claim(signed_launch, name), int), (
            f"The `id_token`'s `{name}` claim is {claim(signed_launch, name)!r} rather than "
            "the NumericDate integer RFC 7519 specifies."
        )


def test_the_audience_is_exactly_the_client_id_the_platform_announced(
    signed_launch: Any,
) -> None:
    """`aud` is the client ID, whole — not a string that contains it.

    Catches the two shapes that pass a careless tool-side check and fail a
    correct one: an `aud` holding several values with no `azp` to say which is
    the tool, and an `aud` that merely has the client ID somewhere inside it. A
    tool testing `client_id in aud` accepts both, so the mock has to be right or
    it teaches the tool to be wrong.
    """
    expected = announced(signed_launch.offer, "client_id")
    audience = claim(signed_launch, "aud")
    if isinstance(audience, list):
        assert audience == [expected], (
            f"The `id_token`'s `aud` is {audience!r} rather than the single announced client "
            f"ID {expected!r}. OpenID Connect requires an `azp` claim when the audience holds "
            "more than one value, and a launch for one tool has one audience."
        )
    else:
        assert audience == expected, (
            f"The `id_token`'s `aud` is {audience!r}, and the client ID the launch page "
            f"announced is {expected!r}. A tool that checked `client_id in aud` would accept "
            "the difference; a tool that compares the claim would not."
        )


def test_the_issuer_is_the_issuer_the_platform_announced(signed_launch: Any) -> None:
    """`iss` agrees with the `iss` the initiation request carried.

    Catches a platform whose launch page announces one issuer and whose signer
    uses another — a public base URL in one place and `http://localhost` in the
    other, which is the classic form. A tool looks the registration up by `iss`,
    so the two disagreeing means no registration is found at all.
    """
    expected = announced(signed_launch.offer, "iss")
    assert claim(signed_launch, "iss") == expected, (
        f"The `id_token`'s `iss` is {claim(signed_launch, 'iss')!r} and the launch page "
        f"announced {expected!r}. A tool resolves the platform registration by issuer, so "
        "these two disagreeing is a launch that matches no registration."
    )


def test_the_id_token_declares_a_resource_link_launch_at_lti_1_3(
    signed_launch: Any,
) -> None:
    """Message type and version, the two claims a tool dispatches on.

    Catches a Deep Linking message type — explicitly out of scope for E0-14, and
    SPEC §7.3 makes plain resource-link launch the default — and a `version` of
    `1.3` or `1.3.1`, neither of which is the string the specification fixes.
    """
    assert claim(signed_launch, MESSAGE_TYPE_CLAIM) == RESOURCE_LINK_MESSAGE_TYPE, (
        f"The message type claim is {claim(signed_launch, MESSAGE_TYPE_CLAIM)!r} rather than "
        f"{RESOURCE_LINK_MESSAGE_TYPE!r}. SPEC §7.3 makes plain resource-link launch the "
        "default and E0-14 puts Deep Linking out of scope."
    )
    assert claim(signed_launch, VERSION_CLAIM) == LTI_VERSION, (
        f"The version claim is {claim(signed_launch, VERSION_CLAIM)!r} rather than the exact "
        f"string {LTI_VERSION!r} LTI 1.3 fixes."
    )


def test_the_deployment_id_claim_is_the_one_the_platform_announced(
    signed_launch: Any,
) -> None:
    """The claim `lti_deployment` (E0-08) is the tool-side row for.

    Catches a deployment ID invented at signing time rather than taken from the
    seeded registration. A tool resolves the deployment from `iss` plus this
    value, so one that does not match anything the platform announces makes the
    launch unregisterable — and it fails in E1 rather than here unless something
    compares the two.
    """
    expected = announced(signed_launch.offer, "lti_deployment_id")
    assert claim(signed_launch, DEPLOYMENT_ID_CLAIM) == expected, (
        f"The deployment ID claim is {claim(signed_launch, DEPLOYMENT_ID_CLAIM)!r} and the "
        f"launch page announced {expected!r}. E0-08's `lti_deployment` rows are keyed on this "
        "pair agreeing."
    )


def test_the_target_link_uri_claim_is_the_one_the_platform_announced(
    signed_launch: Any,
) -> None:
    """The claim a tool checks the landing URL against.

    Catches a platform that announces one target in the initiation request and
    signs another. The tool is required to compare them, so a mock that lets them
    drift produces launches a conformant tool refuses — and it looks fine from
    every angle except this comparison.
    """
    expected = announced(signed_launch.offer, "target_link_uri")
    assert claim(signed_launch, TARGET_LINK_URI_CLAIM) == expected, (
        f"The target link URI claim is {claim(signed_launch, TARGET_LINK_URI_CLAIM)!r} and "
        f"the initiation request announced {expected!r}."
    )


def test_the_resource_link_claim_carries_an_id(signed_launch: Any) -> None:
    """`id` is the only required member of the resource link claim, and it is the key.

    Catches a resource link claim serialised as a bare string, and one carrying a
    title and description but no identifier. The identifier is what makes two
    launches from the same placement the same placement, so a launch without one
    cannot be attributed to anything.
    """
    resource_link = claim(signed_launch, RESOURCE_LINK_CLAIM)
    assert isinstance(resource_link, dict), (
        f"The resource link claim is {resource_link!r} rather than an object. LTI 1.3 makes it "
        "an object whose `id` is required."
    )
    assert resource_link.get("id"), (
        f"The resource link claim carries no `id` (it carries {sorted(resource_link)}). `id` "
        "is its one required member and the only stable identifier a placement has."
    )


def test_the_context_claim_carries_an_id(signed_launch: Any) -> None:
    """The course and section the launch came from, identified.

    Catches a context claim reduced to a label. `id` is the context claim's one
    required member, and E0-14's scope asks the launch to carry "context (course
    and section)" — which a title alone cannot resolve to a row.
    """
    context = claim(signed_launch, CONTEXT_CLAIM)
    assert isinstance(context, dict), (
        f"The context claim is {context!r} rather than an object. LTI 1.3 makes it an object "
        "whose `id` is required and whose `label`, `title` and `type` are optional."
    )
    assert context.get("id"), (
        f"The context claim carries no `id` (it carries {sorted(context)}). E0-14's scope has "
        "the launch carry the course and section, and `id` is the only member that identifies "
        "them."
    )


def test_the_roles_claim_is_a_list_of_lis_vocabulary_uris(signed_launch: Any) -> None:
    """Roles are URIs from the LIS vocabularies, not words.

    Catches `["student"]`, `["Instructor"]` and `"Learner"` — the three shapes a
    mock invents when nobody checks. Each is readable enough that E1's ingestion
    would be written against it, and none of them is what a real platform sends,
    so the bug ships in the tool rather than in the mock.

    An empty list is permitted: LTI 1.3 allows a launch with no roles, and
    refusing it here would be this suite adding a rule.
    """
    roles = claim(signed_launch, ROLES_CLAIM)
    assert isinstance(roles, list), (
        f"The roles claim is {roles!r} rather than an array. LTI 1.3 makes it an array even "
        "when the launching user holds one role."
    )
    invented = [role for role in roles if not (isinstance(role, str) and LIS_VOCABULARY in role)]
    assert not invented, (
        f"The roles claim carries {invented!r}, which are not LIS v2 vocabulary URIs "
        f"(they all contain {LIS_VOCABULARY!r}). LTI 1.3 permits the bare context-role names "
        "only as a deprecated compatibility form, and SPEC §7.3 asks for strict core — a mock "
        "that emits a short name teaches E1's ingestion to read a shape no platform sends."
    )


def test_the_token_is_valid_when_it_is_issued(signed_launch: Any) -> None:
    """`exp` is in the future and after `iat`. Catches an expiry with the sign flipped.

    A lifetime subtracted instead of added produces a token that is expired the
    moment it is minted. Every other assertion in this module passes against it —
    the claims are all there, the signature verifies — and the failure surfaces in
    E1 as "clock skew handling is broken", which is the wrong place to look and
    the wrong thing to fix. The token's own lifetime is not asserted, because
    E0-14 does not set one.
    """
    now = time.time()
    issued = claim(signed_launch, "iat")
    expires = claim(signed_launch, "exp")
    assert issued <= now + CLOCK_TOLERANCE_SECONDS, (
        f"The token says it was issued at {issued}, which is more than "
        f"{CLOCK_TOLERANCE_SECONDS}s after now ({now:.0f}). A token from the future is refused "
        "by a conformant tool for the same reason an expired one is."
    )
    assert expires > now, (
        f"The token expired at {expires}, and it is now {now:.0f} — it was issued already "
        "expired. The likely cause is a lifetime subtracted from `iat` rather than added, "
        "which nothing else in this suite can see."
    )
    assert expires > issued, f"`exp` ({expires}) is not after `iat` ({issued})."


# ---------------------------------------------------------------------------
# The authorization exchange. Criterion 5.
# ---------------------------------------------------------------------------


def test_the_authorization_endpoint_returns_the_state_it_was_given(
    mock_platform: Any,
) -> None:
    """Criterion 5, the `state` half. Catches a platform that mints its own.

    `state` is the tool's value and the platform's only job with it is to hand it
    back untouched. A platform that generates one, or that URL-encodes what it
    was given, breaks the tool's cross-site request forgery defence in a way that
    looks like a tool bug — and a mock that does it makes E1's `state` test
    unpassable against the only platform E0 has.

    A value with punctuation is used deliberately, because a `state` of plain
    letters and digits round-trips through every mistake this is looking for. It
    stops short of `&`, `#` and `+`: those three change meaning in a query string
    and a fragment, so a `state` carrying them would fail here against a platform
    that answered by redirect and encoded them correctly — a false red about the
    transport rather than a true one about the value.
    """
    given = "st4te=with:slash/tilde~dot.dash-underscore_"
    launch = mock_platform.mint(state=given)
    assert launch.state == given, (
        f"The platform returned `state` {launch.state!r} for a request carrying {given!r}. "
        "The tool owns this value; the platform's whole obligation is to return it unchanged."
    )


def test_the_id_token_carries_the_nonce_the_authorization_request_supplied(
    mock_platform: Any,
) -> None:
    """Criterion 5, the `nonce` half, and it lands in the token rather than the form.

    Catches a platform that generates its own nonce and ignores the tool's. That
    breaks replay detection at the tool — the tool remembers what it sent and
    compares — and it is invisible without this comparison, because a
    platform-generated nonce is a perfectly well-formed claim.
    """
    given = "nonce-0d0a6e2b-supplied-by-the-tool"
    launch = mock_platform.mint(nonce=given)
    assert claim(launch, "nonce") == given, (
        f"The `id_token` carries nonce {claim(launch, 'nonce')!r} for an authorization "
        f"request that supplied {given!r}. The nonce is the tool's value: it is what the tool "
        "compares against on the way back, and a platform-generated one can never match."
    )


def test_two_launches_carry_different_nonces(mock_platform: Any) -> None:
    """When the tool supplies none, the platform's own nonce is per launch.

    Catches a constant. A fixed nonce is not a defect anyone sees — every launch
    validates — right up to the moment E1 writes its replay test, which would then
    pass against a correct implementation and against a broken one alike, because
    every launch this platform issues is a replay of the last.
    """
    first = mock_platform.mint()
    second = mock_platform.mint()
    assert claim(first, "nonce") != claim(second, "nonce"), (
        f"Two launches carried the same nonce ({claim(first, 'nonce')!r}). A nonce is single "
        "use by definition; a constant one makes every launch a replay of the last and makes "
        "E1's replay test unable to fail."
    )


# ---------------------------------------------------------------------------
# The seeded launches. Criteria 6 and 7, and the context title.
# ---------------------------------------------------------------------------


def test_a_launch_can_be_minted_for_more_than_one_seeded_user(
    mock_platform: Any,
) -> None:
    """Criterion 7, the user half: `sub` follows the seeded user chosen.

    Catches a launch page that offers a choice of users and signs the same one
    regardless — the shape a hardcoded `sub` takes once a selector is added
    around it. SPEC §4 keys every response to `sub`, so a platform with one
    effective identity gives E1 and E3 a system in which every student is the
    same student, and nothing downstream can tell.
    """
    launches = launches_across_seeded_offers(mock_platform)
    subjects = {claim(launch, "sub") for launch in launches}
    assert len(subjects) > 1, (
        f"Every launch the platform offers signs the same subject ({sorted(subjects)}) across "
        f"{len(launches)} offered launches. E0-14 criterion 7 is a signed launch 'for an "
        "arbitrary seeded user', which needs more than one seeded user and needs the choice "
        "to reach `sub`."
    )


def test_the_seeded_launches_offer_more_than_one_role(mock_platform: Any) -> None:
    """Criterion 7, the role half: the roles claim follows the seeded role chosen.

    Catches a platform that seeds only learners, and one that offers an
    instructor and signs a learner's roles anyway. Either leaves "an arbitrary
    seeded user *and role*" with nothing behind it, and leaves E1 with no launch
    to build the instructor path against.
    """
    launches = launches_across_seeded_offers(mock_platform)
    role_sets = {tuple(sorted(claim(launch, ROLES_CLAIM))) for launch in launches}
    assert len(role_sets) > 1, (
        f"Every launch the platform offers carries the same roles ({sorted(role_sets)}). E0-14 "
        "criterion 7 asks for a launch for an arbitrary seeded user *and role*, which needs at "
        "least two roles seeded and the choice to reach the roles claim."
    )


def test_a_seeded_context_carries_a_title(mock_platform: Any) -> None:
    """A seeded context is nameable, which is what E0-05's `NOT NULL` needs.

    **This test had a pair, and the pair was the requirement.**
    `test_a_seeded_context_carries_no_title` asserted that at least one seeded
    context carried `id` alone, so that E1's ingestion met a titleless course in
    a test rather than in a deployment. Todd withdrew that on 2026-08-17 in
    favour of E0-15's "every seeded course needs a title" — the two cannot both
    hold in one seed — so the other half is deleted and this one stands alone.
    E0-14's scope carries the withdrawal and what it costs.

    What remains here is the weak form. The strong one — *every* seeded context
    rather than at least one — is E0-15's criterion, and it is asserted in
    `tests/integration/test_mock_lms_seed_data.py`, because the seed is that
    ticket's subject.
    """
    contexts = [
        claim(launch, CONTEXT_CLAIM) for launch in launches_across_seeded_offers(mock_platform)
    ]
    assert contexts, "The platform offers no launches, so there are no contexts to inspect."
    assert any(isinstance(context, dict) and context.get("title") for context in contexts), (
        f"No seeded context carries a `title` (contexts: {contexts!r}). E0-14's scope: 'Have "
        "this mock exercise both shapes: at least one seeded context with a title and one with "
        "`id` alone.'"
    )


def test_the_launch_page_submits_by_http_post(mock_platform: Any) -> None:
    """The launch page posts to the tool, and posting means POST.

    Catches a launch page whose form is a `GET`, which puts the initiation
    parameters in a query string. A browser-driven test would still "click
    through" it, so E0-18's Playwright path would pass, and the realism the ticket
    asks for — a launch that looks like a platform's — would be gone.
    """
    offer = mock_platform.require_offers()[0]
    assert offer.method == "post", (
        f"The launch form on `{offer.page}` submits by {offer.method.upper()} rather than "
        "POST. E0-14's scope: 'A launch page that posts the form to the tool, so a "
        "browser-driven test can click through a realistic launch.'"
    )


def test_the_launch_form_posts_where_configuration_points_it(
    base_compose: dict[str, Any],
    override_compose: dict[str, Any],
    documented_env: dict[str, str],
    mock_lms_service: str,
    mock_platforms: Any,
) -> None:
    """Criterion 6: the launch target is configuration, not a constant in the source.

    Two assertions, and the second is what makes the first mean anything. The
    first finds a configured value that matches where the form posts — which a
    hardcoded URL that happens to equal the configured one would also satisfy.
    The second moves that variable and requires the form to follow, which nothing
    hardcoded can do. `docs/MISTAKES.md` entry 2 is the reason for the pair: a
    property that holds today and is defended by nothing.

    The variable is discovered rather than named. E0-14 spells no configuration
    name, and the epic README's rule means it may not be able to: an
    `.env.example` entry earns its place only when an `app.config.Settings` field
    resolves to it or a Compose file interpolates it, and the mock's own settings
    are neither. So what is asserted is the property the criterion states — "so it
    can point at the tool once E1 exists" — over whatever the Compose file calls
    it.
    """
    configured = configured_environment(
        (base_compose, override_compose), mock_lms_service, documented_env
    )
    assert configured, (
        f"The `{mock_lms_service}` service is given no environment by either Compose file, so "
        "nothing points its launch form anywhere. Criterion 6 asks for a configurable target "
        "'so it can point at the tool once E1 exists', and E1's tool is another service on "
        "this network."
    )

    posts_to = mock_platforms(configured).require_offers()[0].posts_to
    candidates = sorted(name for name, value in configured.items() if value and value == posts_to)
    assert candidates, (
        f"The launch form posts to {posts_to!r}, which is not any value the Compose files give "
        f"the `{mock_lms_service}` service. Configured values: "
        f"{ {name: value for name, value in sorted(configured.items()) if value} }. A launch "
        "target that is not configuration cannot be pointed at the tool without editing the "
        "mock."
    )

    moved = mock_platforms({**configured, candidates[0]: MARKER_LAUNCH_TARGET})
    assert moved.require_offers()[0].posts_to == MARKER_LAUNCH_TARGET, (
        f"Setting `{candidates[0]}` to {MARKER_LAUNCH_TARGET!r} left the launch form posting "
        f"to {moved.require_offers()[0].posts_to!r}. The value agreeing with configuration by "
        "coincidence is not the same as being configured by it, and only this direction can "
        "tell them apart."
    )


def test_the_mock_lms_directory_holds_the_application_spec_13_places_there(
    mock_lms_dir: Path,
) -> None:
    """The deliverable exists where SPEC §13 says, before anything else looks for it.

    Kept separate from the tests that drive the platform so that "there is no
    mock LMS yet" reports as one failure naming the missing directory rather than
    as every test in this module failing inside a fixture — which is
    `docs/MISTAKES.md` entry 13's advice read forward.
    """
    assert (mock_lms_dir / "app").is_dir(), (
        f"{mock_lms_dir / 'app'} does not exist. SPEC §13 puts the in-repo LTI 1.3 platform at "
        "`mock-lms/`, with a `Dockerfile` and an `app/` holding the login and authorization "
        "endpoints, JWKS, and the seed data."
    )
