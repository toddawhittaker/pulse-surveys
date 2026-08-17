"""The mock provider's discovery document and code flow — ticket E0-16.

E0-16 builds the *provider* side of the second entry door (SPEC §2, §9.2):
metadata at the standard path, an authorization endpoint, a token endpoint, a
JWKS whose key verifies what it issued, and PKCE over the whole of it.
Everything below asserts what the provider produces.

**What is deliberately not here.** Tool-side login, session handling and the
unified session model that merges both doors are E1's, and E0-16's out-of-scope
list says so. So there is no test of what Pulse does when it receives one of
these sessions. The negative cases that *are* here are of two kinds and both are
labelled: the acceptance criteria that are themselves refusals — a code redeemed
twice, a mismatched verifier — and one control on this module's own verifier,
without which "the signature verifies" would be satisfied by a function that
answers yes to everything (`docs/MISTAKES.md` entry 3).

**Where the seeded client comes from.** An authorization request names a
`client_id` and a redirect URI, and E0-16 spells neither. `MockIdentityProvider.
registration()` in `tests/conftest.py` looks in the three places a reasonable
implementation would publish them — a JSON document, a form on the provider's own
page, the Compose environment — and fails by name if none of them does. That
failure is a real gap rather than a fixture problem: E1 and E0-18 have to learn
the same two values.

**"Validates against the OIDC discovery schema"** is asserted as the REQUIRED
members of OpenID Connect Discovery 1.0 §3, transcribed here with their types.
Nothing in this project's locked dependency set validates JSON Schema, and adding
a package to satisfy a test would be a lockfile decision this ticket does not
own — so the schema's requirements are written out instead, and the citation is
on each constant.

**The verifier is written out of `pow` and `hashlib`** in `tests/conftest.py`,
shared with the mock platform's launch tests, which is also where the tampered-
payload control on it lives. RS256 is required rather than merely accepted:
OIDC Core 1.0 §2 makes it the algorithm every implementation must support, and a
session signed with anything else is one E1 could not validate with a conformant
library.
"""

import time
from typing import Any
from urllib.parse import urlsplit

# `mock_idp`, `mock_idps` and `web_login` come from `tests/conftest.py`, and
# everything this module needs from the provider is reached through them rather
# than imported. That is deliberate: a test module that imports its sibling
# `conftest` by name depends on where pytest happened to put `tests/` on
# `sys.path`, and an import error is not a red — it is a broken suite that
# reports nothing about the ticket. The fixtures are annotated `Any` for the same
# reason `test_mock_lms_launch.py` annotates its own that way.

# The members OpenID Connect Discovery 1.0 §3 marks REQUIRED, with the type each
# must have. `token_endpoint` is REQUIRED "unless only the Implicit Flow is
# used", and E0-16's third criterion is an authorization *code* flow, so it is
# required here. Not this suite's preferences in any part.
REQUIRED_DISCOVERY_MEMBERS = {
    "issuer": str,
    "authorization_endpoint": str,
    "token_endpoint": str,
    "jwks_uri": str,
    "response_types_supported": list,
    "subject_types_supported": list,
    "id_token_signing_alg_values_supported": list,
}

# The values those lists must contain for the flow E0-16 builds. `code` because
# criterion 3 is the authorization code flow; `RS256` because OIDC Discovery 1.0
# §3 says the signing algorithm list "MUST include RS256"; `S256` because RFC
# 7636 §4.2 requires it of any server supporting PKCE and it is the only method
# a client should use.
REQUIRED_RESPONSE_TYPE = "code"
REQUIRED_SIGNATURE_ALGORITHM = "RS256"
REQUIRED_CODE_CHALLENGE_METHOD = "S256"

# The subject identifier types OIDC Discovery 1.0 §3 defines. Anything else in
# that list is a value no client knows how to read.
SUBJECT_TYPES = frozenset({"public", "pairwise"})

# Every metadata member that is a URL a client is expected to call, mapped to the
# words that name the same endpoint in a path. Both halves of criterion 2 read
# this: "lists every endpoint it actually serves" needs to know which served
# route is an endpoint at all, and the converse — an advertised URL that answers
# nothing — is the same defect from the other side. The member names are OIDC
# Discovery 1.0 §3 and RFC 8414 §2; the path words are how those endpoints are
# conventionally spelled.
ENDPOINT_MEMBERS = {
    "authorization_endpoint": ("authorize", "authorization"),
    "token_endpoint": ("token",),
    "userinfo_endpoint": ("userinfo",),
    "jwks_uri": ("jwks",),
    "registration_endpoint": ("register",),
    "end_session_endpoint": ("logout", "end-session", "end_session", "endsession"),
    "revocation_endpoint": ("revoke", "revocation"),
    "introspection_endpoint": ("introspect", "introspection"),
}

# Paths that carry an endpoint word and are not that endpoint. `.well-known` is
# the metadata document itself, and a mock-only readback route is deliberately
# outside the protocol surface — the mock platform has one at `/mock/`
# (ADR 0047), and a provider written beside it may too.
UNADVERTISED_PATH_PREFIXES = ("/.well-known", "/mock", "/static", "/docs", "/openapi", "/redoc")

# The members that make a JSON Web Key a *private* key, from RFC 7517 and
# RFC 7518: `d` for RSA and EC, `k` for a symmetric key, and RSA's CRT
# parameters. A published key set carrying any of them has served the signing key
# to whoever asked.
PRIVATE_JWK_MEMBERS = ("d", "p", "q", "dp", "dq", "qi", "k")

# The token type OIDC Core 1.0 §3.1.3.3 fixes for this flow, lower-cased because
# RFC 6749 §5.1 makes the value case-insensitive.
BEARER_TOKEN_TYPE = "bearer"  # noqa: S105 — the token type's name, not a credential

# A redirect URI that is not the registered one and can never resolve: the
# `.invalid` top-level domain is reserved by RFC 2606. **This suite's choice** of
# value; that it must be refused is not — RFC 6749 §3.1.2.4 and §4.1.2.1 make an
# unregistered redirect URI an error the server must not redirect to.
UNREGISTERED_REDIRECT_URI = "http://attacker.invalid/collect"

# How far out of step the provider's clock and this test's may be. **This suite's
# choice**, and generous: both clocks are the same clock.
CLOCK_TOLERANCE_SECONDS = 60


def refusal(provider: Any, response: Any, subject: str) -> None:
    """Require `response` to be a refusal, and to be a refusal about `subject`.

    Three assertions rather than one, because "the exchange failed" is satisfied
    by several things that are not the rule under test:

      - A 2xx would be the defect itself, so the status is checked first.
      - A body carrying an `id_token` or an `access_token` is a session issued
        alongside an error status, which is the failure that matters and which a
        status check alone would miss.
      - `invalid_client` means the provider refused the *caller* rather than the
        code, and this suite sends no client secret — so a provider that required
        one would pass both refusal criteria while asserting nothing about either
        (`docs/MISTAKES.md` entry 3). It is named as a gap rather than counted as
        a pass.
    """
    provider.refuse_an_unspecified_client_credential(response)
    body = provider.body_of(response)
    assert not 200 <= response.status_code < 300, (
        f"The token endpoint accepted {subject}: it answered {response.status_code}. "
        f"Body begins {response.text[:200]!r}."
    )
    issued = sorted(name for name in ("id_token", "access_token") if body.get(name))
    assert not issued, (
        f"The token endpoint refused {subject} with status {response.status_code} and handed back "
        f"{issued} anyway. A client reads the body it was given; an error status with a session "
        "in it is a session."
    )
    assert body.get("error"), (
        f"The token endpoint refused {subject} with status {response.status_code} and no `error` "
        f"member (it carried {sorted(body)}). RFC 6749 §5.2 makes that member required, and it is "
        "what tells a client the difference between a rejected grant and a provider that fell "
        "over."
    )


# ---------------------------------------------------------------------------
# The discovery document. Criterion 2.
# ---------------------------------------------------------------------------


def test_the_discovery_document_is_served_at_the_standard_path(
    mock_idp: Any, discovery_path: str
) -> None:
    """Criterion 2's precondition: a client can find the provider at all.

    OIDC Discovery 1.0 §4 fixes `/.well-known/openid-configuration`, and E0-16's
    scope repeats it. A provider that serves the same JSON at a path of its own
    is one every conformant client has to be told about by hand, which is the
    thing discovery exists to remove.

    Fetched here directly rather than through the driver, so that the path this
    criterion is about appears in the test that is about it — every other test in
    this module reads the document through `MockIdentityProvider.discovery()`,
    which fetches the same path and would report the same failure less clearly.
    """
    response = mock_idp.client.get(discovery_path)

    assert response.status_code == 200, (
        f"`GET {discovery_path}` answered {response.status_code}. E0-16's scope: 'Discovery "
        f"document at `{discovery_path}`', which is where OIDC Discovery 1.0 §4 says every client "
        f"looks. Body begins {response.text[:200]!r}."
    )
    document = response.json()
    assert isinstance(document, dict) and document, (
        f"`GET {discovery_path}` served {document!r}. Provider metadata is a non-empty JSON "
        "object (OIDC Discovery 1.0 §3), and every other test in this module reads an endpoint "
        "out of it — a search of an empty mapping is the emptiness `docs/MISTAKES.md` entry 3 is "
        "about."
    )


def test_the_discovery_document_carries_every_member_the_standard_requires(
    mock_idp: Any,
) -> None:
    """Criterion 2: the document validates against the discovery schema.

    The REQUIRED members of OIDC Discovery 1.0 §3, with their types and with the
    values the standard fixes inside three of the lists. A missing member is not
    cosmetic: `jwks_uri` absent means nothing can verify a session, and
    `token_endpoint` absent means the code a client just received can never be
    redeemed — both while the provider works perfectly for anyone who read its
    source.
    """
    document = mock_idp.discovery()

    missing = sorted(name for name in REQUIRED_DISCOVERY_MEMBERS if name not in document)
    assert not missing, (
        f"The discovery document is missing {missing} (it carries {sorted(document)}). OIDC "
        "Discovery 1.0 §3 marks each of those REQUIRED — `token_endpoint` unless only the "
        "implicit flow is supported, and E0-16 criterion 3 is the authorization code flow."
    )

    wrong = sorted(
        f"{name}={document[name]!r}"
        for name, kind in REQUIRED_DISCOVERY_MEMBERS.items()
        if not isinstance(document[name], kind)
    )
    assert not wrong, (
        f"The discovery document carries {wrong} at the wrong type. OIDC Discovery 1.0 §3 makes "
        "the issuer and the three URLs strings, and the three `*_supported` members arrays; a "
        "client parsing this document reads them as declared or fails."
    )

    assert REQUIRED_RESPONSE_TYPE in document["response_types_supported"], (
        f"`response_types_supported` is {document['response_types_supported']!r} and does not "
        f"offer {REQUIRED_RESPONSE_TYPE!r}. E0-16 criterion 3 is an authorization code flow, and "
        "a client reads this list to decide whether it may start one."
    )
    assert REQUIRED_SIGNATURE_ALGORITHM in document["id_token_signing_alg_values_supported"], (
        f"`id_token_signing_alg_values_supported` is "
        f"{document['id_token_signing_alg_values_supported']!r}. OIDC Discovery 1.0 §3: this list "
        f"MUST include {REQUIRED_SIGNATURE_ALGORITHM!r}."
    )
    unknown = sorted(set(document["subject_types_supported"]) - SUBJECT_TYPES)
    assert document["subject_types_supported"] and not unknown, (
        f"`subject_types_supported` is {document['subject_types_supported']!r}. OIDC Core 1.0 §8 "
        f"defines exactly {sorted(SUBJECT_TYPES)}; an empty list offers a client nothing and an "
        "unknown value is one no client can interpret."
    )


def test_the_advertised_issuer_names_the_provider_the_document_was_fetched_from(
    mock_idp: Any, discovery_path: str
) -> None:
    """OIDC Discovery 1.0 §4.3: the `issuer` and the fetch location must agree.

    This is the check a client makes to know it is talking to the provider it
    thinks it is, and it is the one an ID token's `iss` is compared against
    afterwards. A provider whose metadata claims a different issuer hands every
    client a session it must reject — or, worse, teaches E1 to skip the
    comparison.

    The comparison is on the path rather than the host, because this suite drives
    the application in process: the host is whatever public base the provider is
    configured with, which is a deployment question and not a conformance one.
    What must hold is that the issuer is an absolute URL, and that a client
    building the well-known URL out of it the way §4 says — the issuer, then
    `/.well-known/openid-configuration` — arrives at this document rather than at
    a 404. An issuer carrying a path component is legal, and then the document has
    to be served under that path too; the assertion allows both and requires them
    to agree.
    """
    issuer = mock_idp.metadata("issuer", "which provider it is talking to")
    issuer_path = urlsplit(issuer).path.rstrip("/")

    assert issuer.startswith(("https://", "http://")), (
        f"The advertised issuer is {issuer!r}, which is not an absolute URL. OIDC Discovery 1.0 "
        "§3 makes the issuer a URL using the https scheme (http is tolerated for a development "
        "provider), and a client concatenates it with the well-known path to find this document."
    )
    assert not issuer.endswith("/"), (
        f"The advertised issuer is {issuer!r}, with a trailing slash. OIDC Discovery 1.0 §4.3 "
        "compares the issuer to the one in every `id_token` **exactly**, and §4 builds the "
        "well-known URL by concatenation — so the slash produces either a double slash or a "
        "mismatch, depending on which client reads it."
    )

    if issuer_path:
        under_the_issuer = mock_idp.client.get(f"{issuer_path}{discovery_path}")
        assert under_the_issuer.status_code == 200, (
            f"The advertised issuer is {issuer!r}, so OIDC Discovery 1.0 §4 says a client looks "
            f"for this document at `{issuer_path}{discovery_path}` — and that answered "
            f"{under_the_issuer.status_code}. The document is served at `{discovery_path}` "
            "instead, which only a client that already knew the provider would find."
        )


def test_every_endpoint_the_discovery_document_advertises_is_served(mock_idp: Any) -> None:
    """Criterion 2: an advertised endpoint that answers nothing is a broken document.

    A client calls what discovery tells it to call. An endpoint advertised at a
    path nothing routes leaves that client with a 404 it cannot diagnose, and the
    provider works perfectly for anyone who guessed the real path — which is why
    this is asserted rather than assumed from the document parsing cleanly.

    A `405` counts as served: `GET` on a token endpoint is the wrong method for
    the right route, and what is being asked here is whether the route exists.
    """
    document = mock_idp.discovery()
    advertised = {
        name: document[name]
        for name in ENDPOINT_MEMBERS
        if isinstance(document.get(name), str) and document[name]
    }
    assert advertised, (
        f"The discovery document advertises none of {sorted(ENDPOINT_MEMBERS)} (it carries "
        f"{sorted(document)}), so this test would assert nothing about an empty set."
    )

    relative = sorted(f"{name}={url}" for name, url in advertised.items() if "://" not in url)
    assert not relative, (
        f"The discovery document advertises {relative} as relative URLs. OIDC Discovery 1.0 §3 "
        "makes every endpoint an absolute URL, and a client that fetched this document over the "
        "network has nothing to resolve a relative one against."
    )

    unserved = []
    for name, url in advertised.items():
        response = mock_idp.client.get(mock_idp.endpoint_path(name, "an advertised endpoint"))
        if response.status_code == 404:
            unserved.append(f"{name}={url}")
    assert not unserved, (
        f"The discovery document advertises {unserved}, and the provider serves nothing there — "
        f"it serves {sorted(set(mock_idp.paths('GET')) | set(mock_idp.paths('POST')))}. A client "
        "calls what discovery tells it to call."
    )


def test_every_oidc_endpoint_the_provider_serves_is_advertised_in_the_discovery_document(
    mock_idp: Any,
) -> None:
    """Criterion 2, in the ticket's own words: the document "lists every endpoint it serves".

    The direction the test above does not cover. A provider that serves a
    userinfo endpoint and advertises no `userinfo_endpoint` has built something a
    client can only reach by having been told about it out of band — which is
    exactly what an in-repo provider exists to make unnecessary, and exactly the
    habit E1 must not learn.

    Routes outside the protocol surface are excluded by prefix rather than by
    guesswork about their purpose: the metadata document itself, and the
    mock-only readback space the platform side already uses (ADR 0047).
    """
    document = mock_idp.discovery()
    served = sorted(set(mock_idp.paths("GET")) | set(mock_idp.paths("POST")))
    assert served, "The provider declares no routes at all, so this test would inspect nothing."

    advertised_members = {name for name in ENDPOINT_MEMBERS if isinstance(document.get(name), str)}
    advertised_urls = sorted(f"{name}={document[name]}" for name in advertised_members)

    unadvertised = []
    for path in served:
        if path.startswith(UNADVERTISED_PATH_PREFIXES):
            continue
        lowered = path.lower()
        for member, words in ENDPOINT_MEMBERS.items():
            if member in advertised_members:
                continue
            if any(word in lowered for word in words):
                unadvertised.append(f"{path} (would be `{member}`)")
    assert not unadvertised, "\n".join(
        [
            "The provider serves endpoints its discovery document does not list:",
            *(f"  {entry}" for entry in unadvertised),
            "",
            f"The document advertises {advertised_urls}. E0-16 criterion 2: the discovery "
            "document 'lists every endpoint it actually serves'. An endpoint a client can only "
            "find by reading the source is one E1 would have to hardcode.",
        ]
    )


def test_the_discovery_document_advertises_the_code_flow_with_s256_pkce(mock_idp: Any) -> None:
    """How a client learns it may — and must — use PKCE here.

    RFC 7636 §4.2 requires S256 of any server supporting PKCE, and RFC 8414 puts
    `code_challenge_methods_supported` in the metadata so a client can tell
    before it sends anything. E0-16's third criterion is a code flow *with* PKCE
    and its fifth is that a mismatched verifier is refused; a provider that
    enforces both and advertises neither leaves every client guessing, and the
    guess that costs is the one that omits the challenge.

    `plain` is not asserted absent. It is permitted by the specification, and
    what makes PKCE load-bearing here is the enforcement tested below rather than
    a list.
    """
    document = mock_idp.discovery()
    methods = document.get("code_challenge_methods_supported")

    assert isinstance(methods, list) and REQUIRED_CODE_CHALLENGE_METHOD in methods, (
        f"`code_challenge_methods_supported` is {methods!r}. RFC 8414 §2 is where a client learns "
        f"whether PKCE is available, and RFC 7636 §4.2 requires {REQUIRED_CODE_CHALLENGE_METHOD!r}"
        " of a server that supports it. E0-16 criteria 3 and 5 both rest on this provider "
        "enforcing PKCE, so a client has to be able to discover it."
    )


# ---------------------------------------------------------------------------
# The key set, and the signature over it. Criteria 3 and 9.
# ---------------------------------------------------------------------------


def test_the_jwks_endpoint_serves_at_least_one_key(mock_idp: Any) -> None:
    """Criterion 3's precondition, asserted before anything rests on it.

    Catches a JWKS endpoint that answers 200 with `{"keys": []}` — a valid JWK
    Set, and a provider whose sessions nothing can ever verify. Every test below
    searches that list, and a search of an empty list is emptiness passing for
    agreement.
    """
    keys = mock_idp.published_keys()

    assert keys, (
        "The JWKS endpoint serves no keys. E0-16 criterion 3 is an `id_token` that verifies "
        "against the served JWKS, and an empty key set verifies nothing while answering 200 like "
        "a working one."
    )


def test_the_published_key_set_carries_no_private_key_material(mock_idp: Any) -> None:
    """A JWKS publishes public halves. Catches a serializer that dumped the pair.

    The mistake is one line — serialising the generated key rather than its
    public half — and it breaks nothing: every session still verifies, because
    the public members are all present alongside. E0-16's security review is
    about a provider that is lenient in the wrong place, and a signing key served
    over HTTP has stopped being anybody's key.
    """
    keys = mock_idp.published_keys()
    assert keys, "The JWKS endpoint serves no keys, so this test has nothing to inspect."

    leaked = [
        (key.get("kid"), sorted(set(key) & set(PRIVATE_JWK_MEMBERS)))
        for key in keys
        if set(key) & set(PRIVATE_JWK_MEMBERS)
    ]
    assert not leaked, (
        f"The published key set carries private key material: {leaked}. RFC 7517 makes `d`, `p`, "
        "`q`, `dp`, `dq`, `qi` and `k` the private members of a JWK; publishing any of them "
        "serves the signing key to anyone who asks. Serialise the public half."
    )


def test_two_provider_instances_publish_different_signing_keys(mock_idps: Any) -> None:
    """Criterion 9's first half: keys are generated at startup, not loaded.

    Catches the implementation the criterion is written against — a key pair
    generated once and read from a file, an environment variable, or a constant
    in the image. Every other test in this module passes against it: the sessions
    verify, the key set is well formed, nothing is published that should not be.
    The only observable difference is that a second start of the provider is the
    same provider, which is what makes the private half a durable credential
    rather than a value that exists for one run.

    `tests/unit/test_mock_lms_service.py` holds the other half — that no private
    key is committed anywhere in this repository — and neither implies the other.
    A key baked into a Dockerfile is absent from the tree and identical on every
    run; a key generated per run and also checked in is different every run and
    still committed.
    """
    first = {key["n"] for key in mock_idps().published_keys() if key.get("n")}
    second = {key["n"] for key in mock_idps().published_keys() if key.get("n")}

    assert first and second, (
        "A provider instance published no RSA key material, so the comparison below would be "
        "between two empty sets — which agree about nothing and would pass."
    )
    assert not (first & second), (
        "Two independently started providers published the same key material. E0-16 criterion 9 "
        "and SPEC §9.1: keys are generated at startup rather than taken from a fixture. A key "
        "that survives a restart is a credential, and it is the same credential in every image, "
        "every fork and every developer's checkout."
    )


# ---------------------------------------------------------------------------
# The authorization code flow with PKCE. Criterion 3.
# ---------------------------------------------------------------------------


def test_an_authorization_code_flow_with_pkce_returns_a_bearer_token_response(
    web_login: Any,
) -> None:
    """Criterion 3, the flow half: the exchange completes and returns a session.

    Reaching this assertion is most of what it asserts — `mock_idp.login()` sends
    a conformant authorization request, drives the login form, reads the code out
    of the redirect and redeems it with the verifier, failing by name at whichever
    step does not answer. What is left to check is the shape of what came back:
    RFC 6749 §5.1 makes `access_token` and `token_type` required members, and OIDC
    Core 1.0 §3.1.3.3 fixes the type as Bearer.
    """
    assert web_login.tokens.get("access_token"), (
        f"The token response carries no `access_token` (it carries {sorted(web_login.tokens)}). "
        "RFC 6749 §5.1 makes it a required member of a successful response."
    )
    assert str(web_login.tokens.get("token_type", "")).lower() == BEARER_TOKEN_TYPE, (
        f"The token response declares `token_type` {web_login.tokens.get('token_type')!r} rather "
        f"than {BEARER_TOKEN_TYPE!r}. OIDC Core 1.0 §3.1.3.3 fixes it for this flow, and a client "
        "reads it to decide how to present the token."
    )


def test_the_id_token_is_signed_with_rs256_and_names_a_published_key(
    mock_idp: Any, web_login: Any
) -> None:
    """The header a client selects a key with. Catches `alg: none` and a missing `kid`.

    Two failures, both of which leave a session that still "works" against a
    permissive reader. An `alg` of `none` produces a token with an empty
    signature that a decoder happily parses; an HS256 token verifies against a
    shared secret and makes the published key set decorative. A missing or
    unmatched `kid` leaves a client guessing which published key to try, which is
    the ambiguity a key set exists to remove — and it goes unnoticed for as long
    as the provider publishes only one key.
    """
    algorithm = web_login.header.get("alg")
    assert algorithm == REQUIRED_SIGNATURE_ALGORITHM, (
        f"The `id_token` is signed with `alg` {algorithm!r} rather than "
        f"{REQUIRED_SIGNATURE_ALGORITHM!r}. OIDC Core 1.0 §2 makes RS256 the algorithm every "
        "implementation must support: a symmetric algorithm makes the published key set "
        "irrelevant, and `none` makes the signature itself irrelevant."
    )

    published = {key.get("kid") for key in mock_idp.published_keys()}
    assert web_login.header.get("kid") in published, (
        f"The `id_token` header names key {web_login.header.get('kid')!r}, which is not among the "
        f"published key IDs {sorted(k for k in published if k)}. A client selects the verifying "
        "key by `kid`; with one key published this is invisible, and it becomes a session nobody "
        "can validate the first time the provider rotates."
    )


def test_the_id_token_verifies_against_the_served_jwks(mock_idp: Any, web_login: Any) -> None:
    """Criterion 3, the signature half, in the criterion's own words.

    The failure this exists for is not exotic — it is a second key pair created
    somewhere in the startup path, or a JWKS built from a freshly generated key
    rather than from the one the signer holds. Nothing else notices: the token
    parses, every claim is right, the key set is well formed, and only the
    arithmetic disagrees.
    """
    assert mock_idp.verifies(web_login.signature) is not None, (
        "No key in the served JWKS verifies the signature on the issued `id_token`. E0-16 "
        "criterion 3 is exactly this agreement — the JWKS has to serve what the session was "
        "signed with, or every client that trusts this provider rejects every login."
    )


def test_a_session_from_another_provider_instance_does_not_verify_here(
    mock_idp: Any, mock_idps: Any
) -> None:
    """The control on the test above, not a test of client-side validation.

    A verifier that answered `True` for everything would satisfy the signature
    assertion above, and would do it silently — `docs/MISTAKES.md` entry 3's "a
    test passed for a reason unrelated to what it asserted". So it is shown
    saying no, and the wrong key is a real one from a second provider rather than
    a corrupted blob, because a near miss is what a decode-only verifier accepts.

    The tampered-payload half of the same control lives in
    `tests/integration/test_mock_lms_launch.py`, over the same `verify_rs256`.
    """
    stranger = mock_idps().login()

    assert mock_idp.verifies(stranger.signature) is None, (
        "A session signed by a different provider instance verified against this provider's key "
        "set. Either the two instances share a key — which is criterion 9's failure, keys not "
        "generated at startup — or the verifier in tests/conftest.py is decoding rather than "
        "verifying, in which case every signature assertion in this module is vacuous."
    )


def test_the_id_token_carries_the_nonce_the_authorization_request_supplied(
    web_login: Any,
) -> None:
    """OIDC Core 1.0 §3.1.3.7 step 11: the nonce binds the session to the request.

    Without it a client cannot tell its own login from a session replayed at it,
    and the check E1 has to make has nothing to compare against. It lands in the
    token rather than in the redirect, which is the part a provider gets wrong by
    echoing it in the query string and leaving the claim out.
    """
    assert web_login.claims.get("nonce") == web_login.request["nonce"], (
        f"The `id_token` carries nonce {web_login.claims.get('nonce')!r}; the authorization "
        f"request sent {web_login.request['nonce']!r}. OIDC Core 1.0 §3.1.3.7 makes the client "
        "compare exactly these two, so a provider that mints its own leaves the client with "
        "nothing to check."
    )


def test_the_authorization_response_returns_the_state_it_was_given(mock_idp: Any) -> None:
    """RFC 6749 §4.1.2: `state` comes back unchanged, and it is the client's CSRF check.

    Catches a provider that mints its own — which looks identical from a browser
    and defeats the one defence a client has against a login it did not start.
    """
    attempt = mock_idp.begin()
    identity = mock_idp.offered_identities(attempt)[0]
    submitted = mock_idp.submit_login(attempt, identity)

    assert submitted.code, (
        f"Signing in as {identity} produced no authorization code (status "
        f"{submitted.response.status_code}), so there is no authorization response to read a "
        "`state` out of."
    )
    assert submitted.state == attempt.request["state"], (
        f"The authorization response returned state {submitted.state!r}; the request sent "
        f"{attempt.request['state']!r}. RFC 6749 §4.1.2 requires the value back exactly, and a "
        "client that cannot match it cannot tell its own login from someone else's."
    )


def test_the_id_token_is_addressed_to_the_client_that_asked_for_it(
    mock_idp: Any, web_login: Any
) -> None:
    """`aud` is the client ID, whole — not a string that happens to contain it.

    A client validating a session compares this exactly (OIDC Core 1.0 §3.1.3.7
    step 3). A provider that puts something else there hands every client a
    session it must reject, or teaches it to compare loosely.
    """
    client_id = mock_idp.registration()["client_id"]
    audience = web_login.claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]

    assert client_id in audiences, (
        f"The `id_token` is addressed to {audience!r}; the request was made by client "
        f"{client_id!r}. OIDC Core 1.0 §3.1.3.7 makes the client require its own client ID among "
        "the audiences, so anything else is a session it has to refuse."
    )


def test_the_id_token_is_issued_by_the_provider_the_discovery_document_names(
    mock_idp: Any, web_login: Any
) -> None:
    """`iss` and the advertised issuer agree, which is what makes discovery worth doing.

    OIDC Core 1.0 §3.1.3.7 step 1 compares them, and a mismatch is how a session
    from one provider is passed off as another's. Both values are read from the
    provider itself rather than pinned here, so this asserts they agree rather
    than what they are — which is the ticket's business, not this file's.
    """
    issuer = mock_idp.metadata("issuer", "which provider it is talking to")

    assert web_login.claims.get("iss") == issuer, (
        f"The `id_token` names issuer {web_login.claims.get('iss')!r}; the discovery document "
        f"advertises {issuer!r}. OIDC Core 1.0 §3.1.3.7 makes a client compare exactly these two "
        "strings, and Discovery §4.3 makes the same comparison the point of fetching the "
        "document at all."
    )


def test_the_id_token_is_valid_when_it_is_issued(web_login: Any) -> None:
    """`exp` is in the future and after `iat`. Catches an expiry with the sign flipped.

    E0-16's security review names token expiry, and this is the direction that
    fails closed in the worst way: a session already expired when it is issued
    breaks every login, but one whose `exp` was written as `iat` minus the
    lifetime — or omitted entirely — is a session that never stops being valid.
    """
    issued = web_login.claims.get("iat")
    expires = web_login.claims.get("exp")
    now = time.time()

    assert isinstance(issued, int | float) and isinstance(expires, int | float), (
        f"The `id_token` carries `iat` {issued!r} and `exp` {expires!r}. OIDC Core 1.0 §2 makes "
        "both required and both a number of seconds since the epoch."
    )
    assert issued <= now + CLOCK_TOLERANCE_SECONDS, (
        f"The `id_token` says it was issued at {issued}, which is more than "
        f"{CLOCK_TOLERANCE_SECONDS}s ahead of this clock ({now}). A client checking `iat` refuses "
        "a token from the future."
    )
    assert expires > now, (
        f"The `id_token` expired at {expires}, and it is now {now} — it was issued already "
        "expired, so no client can ever use it."
    )
    assert expires > issued, (
        f"The `id_token`'s `exp` ({expires}) is not after its `iat` ({issued}). That is an expiry "
        "computed with the sign the wrong way round, which is invisible for as long as nothing "
        "checks it."
    )


# ---------------------------------------------------------------------------
# What the provider must refuse. Criteria 4 and 5, and the security review.
# ---------------------------------------------------------------------------


def test_an_authorization_code_cannot_be_redeemed_twice(mock_idp: Any) -> None:
    """Criterion 4, with the first redemption as its own control.

    The control is not ceremony. "The second exchange failed" is satisfied by a
    token endpoint that fails every exchange, by a client credential this suite
    does not send, and by a code that was never valid — so the *same* code is
    redeemed successfully first, in the same test, and only then again. RFC 6749
    §4.1.2 requires exactly this: the authorization code must be single-use, and
    a provider that leaks one into a log or a referrer header has leaked a
    session if it can still be spent.
    """
    attempt = mock_idp.begin()
    identity = mock_idp.offered_identities(attempt)[0]
    submitted = mock_idp.submit_login(attempt, identity)
    assert submitted.code, (
        f"Signing in as {identity} produced no authorization code (status "
        f"{submitted.response.status_code}), so there is no code to redeem twice."
    )

    first = mock_idp.redeem(submitted.code, submitted.verifier)
    assert mock_idp.tokens(first).get("id_token"), (
        "The first redemption of a fresh code did not produce an `id_token`, so the second one "
        "below would be refusing a code that never worked — which says nothing about replay."
    )

    second = mock_idp.redeem(submitted.code, submitted.verifier)
    refusal(mock_idp, second, "an authorization code that had already been redeemed")


def test_a_code_redemption_with_a_mismatched_pkce_verifier_is_rejected(mock_idp: Any) -> None:
    """Criterion 5, with a matching verifier on an identical flow as the control.

    Two flows rather than one, because a code is single-use and the control has
    to be the same request in every respect except the verifier. Flow A is
    redeemed with a verifier that is well formed and belongs to a different
    challenge — a near miss rather than a corrupted string, because a provider
    that merely checks the parameter is present accepts anything non-empty. Flow
    B is redeemed with its own verifier and must succeed, which is what says the
    refusal was about the verifier rather than about the endpoint.
    """
    control = mock_idp.login()
    assert control.tokens.get("id_token"), (
        "A flow redeemed with its matching verifier produced no `id_token`, so the refusal below "
        "would be indistinguishable from a token endpoint that refuses everything."
    )

    attempt = mock_idp.begin()
    identity = mock_idp.offered_identities(attempt)[0]
    submitted = mock_idp.submit_login(attempt, identity)
    assert (
        submitted.code
    ), "Signing in produced no authorization code, so there is nothing to redeem."

    _, another_verifier = mock_idp.authorization_request()
    assert another_verifier != submitted.verifier, (
        "Two authorization requests produced the same PKCE verifier, so the 'mismatch' below is "
        "not one. `pkce_pair` in tests/conftest.py draws it from `secrets`."
    )
    mismatched = mock_idp.redeem(submitted.code, another_verifier)
    refusal(mock_idp, mismatched, "a code exchange carrying a PKCE verifier from another flow")


def test_a_code_redemption_with_no_pkce_verifier_is_rejected(mock_idp: Any) -> None:
    """Criterion 5's other half, and the one that makes PKCE load-bearing.

    A provider that compares the verifier when one is sent and issues a session
    when none is passes the mismatch test above and offers no protection at all:
    an attacker holding a stolen code simply omits the parameter. RFC 7636 §4.6
    requires the request to be refused when a challenge was registered and no
    verifier arrives, and E0-16's security review names PKCE enforcement.

    A missing parameter and a wrong one are different requests, which is why this
    is a test of its own rather than a second assertion above.
    """
    attempt = mock_idp.begin()
    identity = mock_idp.offered_identities(attempt)[0]
    submitted = mock_idp.submit_login(attempt, identity)
    assert (
        submitted.code
    ), "Signing in produced no authorization code, so there is nothing to redeem."

    without = mock_idp.redeem(submitted.code, None)
    refusal(mock_idp, without, "a code exchange carrying no PKCE verifier at all")


def test_an_authorization_request_naming_an_unregistered_redirect_uri_is_refused(
    mock_idp: Any,
) -> None:
    """The security review's redirect-URI item: a code may only go where it was registered.

    This is the oldest hole in OAuth, and a mock that leaves it open teaches the
    tool-side code the habit E0-16's definition of done exists to prevent: RFC
    6749 §4.1.2.1 says a server that finds the redirect URI invalid "MUST NOT
    automatically redirect the user-agent to the invalid redirect URI", because
    doing so hands the code to whoever named it.

    Asserted as *where the code went*, not as a status. A provider may refuse
    with an error page, a 400 or a redirect back to the registered URI carrying
    an error, and all three are conformant; what none of them may do is send an
    authorization code to the URI it was handed.
    """
    attempt = mock_idp.begin(redirect_uri=UNREGISTERED_REDIRECT_URI)

    if attempt.form is not None:
        identity = mock_idp.offered_identities(attempt)[0]
        submitted = mock_idp.submit_login(attempt, identity)
        landed, code = submitted.location or "", submitted.code
    else:
        location, code, _ = mock_idp.read_authorization_response(attempt.response)
        landed = location or ""

    assert not (code and landed.startswith(UNREGISTERED_REDIRECT_URI)), (
        f"An authorization request naming the unregistered redirect URI "
        f"{UNREGISTERED_REDIRECT_URI!r} was answered with a code sent to it ({landed!r}). RFC "
        "6749 §4.1.2.1: a server that finds the redirect URI invalid MUST NOT redirect to it. "
        "Anyone who can get a user to open a link then collects that user's session."
    )
    assert not landed.startswith(UNREGISTERED_REDIRECT_URI), (
        f"The provider redirected the user agent to the unregistered redirect URI {landed!r}. "
        "Even carrying an error, that is the redirect RFC 6749 §4.1.2.1 forbids — the registered "
        "URI is the only place this flow may send a browser."
    )


def test_the_registration_this_suite_drives_the_provider_with_is_the_one_it_registered(
    mock_idp: Any,
) -> None:
    """The control on every flow above: the client they name is a real registration.

    `registration()` finds the seeded client by looking, because E0-16 spells
    neither the client ID nor the redirect URI. If it found something that is not
    a registration — a placeholder in a page, a variable nothing reads — every
    flow in this module would fail identically and the reason would be invisible
    in the failures. So the values are asserted to be a client the provider will
    actually start a flow for, once, here.
    """
    registration = mock_idp.registration()

    assert (
        registration["client_id"] and registration["redirect_uri"]
    ), f"The registration found is {registration!r}, which carries an empty member."
    assert "://" in registration["redirect_uri"], (
        f"The registered redirect URI is {registration['redirect_uri']!r}, which is not an "
        "absolute URL. RFC 6749 §3.1.2 requires one, and a browser has nothing to resolve a "
        "relative redirect against."
    )

    attempt = mock_idp.begin()
    assert attempt.form is not None, (
        f"An authorization request naming client {registration['client_id']!r} did not reach a "
        f"login form — the provider answered {attempt.response.status_code}. Either that client "
        "is not the seeded one, in which case `MockIdentityProvider.registration()` in "
        "tests/conftest.py found the wrong thing and every other test here fails for that reason, "
        "or the provider refuses a conformant authorization request."
    )
