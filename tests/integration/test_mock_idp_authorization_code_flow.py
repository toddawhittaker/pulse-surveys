"""The mock provider's discovery document and code flow — ticket E0-16.

E0-16 builds the *provider* side of the second entry door (SPEC §2, §9.2):
metadata at the standard path, an authorization endpoint, a token endpoint, a
JWKS whose key verifies what it issued, and PKCE over the whole of it.
Everything below asserts what the provider produces.

**What is deliberately not here.** Tool-side login, session handling and the
unified session model that merges both doors are E1's, and E0-16's out-of-scope
list says so. So there is no test of what Pulse does when it receives one of
these sessions. The negative cases that *are* here are of three kinds and each is
labelled: the acceptance criteria that are themselves refusals — a code redeemed
twice, a mismatched verifier — one control on this module's own verifier, without
which "the signature verifies" would be satisfied by a function that answers yes
to everything (`docs/MISTAKES.md` entry 3), and the two malformed-PKCE tests
added after the fact.

**Those two came from the implementer rather than from a criterion**, and they
are the reason `refusal` below now requires a 4xx. Two 500s, fixed one after the
other: a `code_verifier` outside ASCII raised when the token endpoint hashed it,
and a `code_challenge` outside ASCII — a value the *authorization* endpoint had
already accepted and stored — raised when the same redemption compared it. So the
two malformed values enter at different endpoints and **both crashes land at the
same one**, which is why the second test below walks the flow to its end rather
than judging the authorization response: a check that stopped where the value was
submitted would have watched the provider accept it and called that a pass.

Nothing in this suite could reach either. Every PKCE value it sends comes from
`secrets.token_urlsafe`, which cannot produce a byte those guards were breaking
on — a driver that only emits well-formed input makes the invalid half of every
guard unreachable, and the suite reads as covering a path no test can enter.

**A third group came from the security review, and it is the same sentence
again.** A parameter was trimmed *before* the check that judges it, so the check
never saw what made the value wrong — and for PKCE that meant a challenge
registered over a verifier `v` was satisfied by every string that trims to `v`.
The values this suite sends could not express that either, because a client that
builds a request and reads the answer with the same code trims on both sides and
cancels the defect out. The exactness tests below therefore pad **one** side on
purpose and say so where it would be tempting to simplify. Alongside them: what a
scope releases, what a repeated parameter must not buy, and — because presence is
judged on the trimmed value while the untrimmed one is what is handed on — that a
parameter which is nothing but whitespace is still absent.

**A fourth group came from the second review pass, and by then the shape had a
name.** [ADR 0062](../../docs/adr/0062-a-request-is-parsed-once-at-the-edge.md)
records it: a value transformed between the wire and the check that was supposed
to judge it, five times across three rounds. What is new here is the two ways that
transformation hid a *test*. `scope.split()` treats a tab, a newline and U+00A0 as
separators, so it turned a malformed scope into a well-formed one before the
unknown-scope refusal written the round before could fire — a guard tested through
a repair that runs first is a guard nothing tests. And the duplicate-parameter
rule ran over one collection at a time, so a name sent once in the query and once
in the body was two singletons; the test for it has to send a request no browser
sends. The grant-type pair and the token endpoint's own padded fields are the same
subject on the endpoint the earlier rounds did not reach.

**Where the seeded client comes from.** An authorization request names a
`client_id` and a redirect URI, and E0-16 spells neither. `MockIdentityProvider.
registration()` in `tests/fixtures/mock_idp.py` looks in the three places a reasonable
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

**The verifier is written out of `pow` and `hashlib`** in
`tests/fixtures/lti_platform.py`, shared with the mock platform's launch tests,
which is also where the tampered-
payload control on it lives. RS256 is required rather than merely accepted:
OIDC Core 1.0 §2 makes it the algorithm every implementation must support, and a
session signed with anything else is one E1 could not validate with a conformant
library.
"""

import time
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

import pytest

# `mock_idp`, `mock_idps` and `web_login` come from `tests/fixtures/mock_idp.py`,
# and everything this module needs from the provider is reached through them
# rather than imported. That is deliberate: a test module that imports a fixtures
# module by name depends on where pytest happened to put `tests/` on
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

# A PKCE value carrying one character outside ASCII, and **43 characters long**.
# The length is the whole reason this constant is written out rather than typed
# at the call site: 43 is the minimum RFC 7636 §4.1 allows a verifier and the
# exact length the base64url of a SHA-256 digest has, so a length check cannot be
# what refuses it. A shorter non-ASCII value would be turned away before anything
# looked at its characters, and the tests below would pass without reaching the
# handling they are named for — `docs/MISTAKES.md` entry 3, in the form where the
# test and the guard that answers it are one rule apart.
NON_ASCII_PKCE_VALUE = "é" + "a" * 42

# The two other shapes RFC 7636 §4.1 rules out by length: nothing at all, and one
# character past the 128 it permits. Neighbours of the measured case rather than
# measured cases themselves, and included because they are the shapes an
# unchecked slice or an unguarded index fails on, which is the same class of
# failure as the one that was found.
EMPTY_PKCE_VALUE = ""
OVERLONG_PKCE_VERIFIER = "a" * 129

# What is submitted to the *authorization* endpoint as `code_challenge`, with
# `code_challenge_method=S256` alongside it — so neither of these can be read as
# "this client is not using PKCE". The empty one is malformed rather than absent,
# and that difference is the whole of why it belongs here.
MALFORMED_CHALLENGES = {
    "a challenge carrying a character outside ASCII": NON_ASCII_PKCE_VALUE,
    "an empty challenge": EMPTY_PKCE_VALUE,
}

# What is submitted to the *token* endpoint as `code_verifier`. The same value
# appears in both mappings on purpose: it is legal at 43 characters for a
# verifier and legal at 43 characters for an S256 challenge, so one constant
# reaches both entry points without either being able to refuse it for its size.
MALFORMED_VERIFIERS = {
    "a verifier carrying a character outside ASCII": NON_ASCII_PKCE_VALUE,
    "an empty verifier": EMPTY_PKCE_VALUE,
    "a verifier past the 128-character maximum": OVERLONG_PKCE_VERIFIER,
}

# The status RFC 6749 §5.2 fixes for a rejected grant. Its only other status is
# the 401 for `invalid_client`, which this suite never provokes and which
# `refusal` below rules out by name before it gets here.
REJECTED_GRANT_STATUS = 400

# The error codes RFC 6749 §5.2 defines, and the three this suite distinguishes
# between. They are not interchangeable and the tests below are about *which* one
# came back: `invalid_grant` says the grant presented does not match what was
# registered, `invalid_request` says the request was malformed or repeated a
# parameter, and `unsupported_grant_type` is reserved for a grant type the server
# does not support. A provider answering `invalid_request` for a verifier one byte
# from correct would be calling a well-formed request malformed; one answering
# `invalid_request` for an unknown grant type would be saying nothing about the
# thing the client got wrong.
INVALID_GRANT = "invalid_grant"
INVALID_REQUEST = "invalid_request"
UNSUPPORTED_GRANT_TYPE = "unsupported_grant_type"

# The scopes a client may ask for, and what each is supposed to bring back. Not
# this suite's invention: `openid` is required of every OIDC request (Core §3.1.2.1)
# and `email` and `profile` are the standard claim sets Core §5.4 defines, with
# the claims each releases named there.
BASE_SCOPE = "openid"
FULL_SCOPE = "openid email profile"
UNKNOWN_SCOPE = "openid wibble"

# The claims §5.4 attaches to those two optional scopes and to nothing else, so a
# session issued for `openid` alone may not carry any of them.
SCOPED_CLAIMS = ("email", "email_verified", "preferred_username")

# Scopes that are two valid tokens to `str.split()` and one invalid token to the
# grammar. RFC 6749 Appendix A.4: `scope = scope-token *( SP scope-token )` with
# `scope-token = 1*NQCHAR` — separated by one space and by nothing else.
#
# **All four separate the fix from the defect, by two different routes**, and the
# routes are worth keeping apart because they fail for different reasons:
#
#   - A tab, a newline and U+00A0 are *separators* to a bare `split()`. Each of
#     those values is one unknown token to a conformant server and arrived as two
#     known ones, so it was granted — and the unknown-scope refusal added the
#     round before could not fire at all, because the value had been made
#     well-formed before anything judged it.
#   - A doubled space is the mirror image. A bare `split()` *drops* the empty
#     token, so the value reads as two valid tokens and is granted; under the
#     grammar the empty token is not `1*NQCHAR` and the request is refused. The
#     same outcome by the opposite mechanism.
#
# An earlier version of this comment said the doubled space could not detect a
# bare `split()`, and said it in that case's own parameter name — the worst place
# for a wrong claim, because a parameter name is what the next person reads when
# deciding whether the case is worth keeping. It was reasoned from `split()`
# dropping empty tokens and never measured. Restoring `scope.split()` reddens all
# four.
MALFORMED_SCOPES = {
    "a tab between the tokens": "openid\temail",
    "a newline between the tokens": "openid\nemail",
    # "a non-breaking space between the tokens" is assigned below, with `chr`.
    "an empty token between two valid ones": "openid  email",
}

# Built with `chr` rather than typed or written as an escape. An editor, a
# formatter or a paste can turn an escape into the character and the character
# into a plain space, and the plain space is the dangerous one: `openid email`
# with an ordinary space is a *valid* scope, so that case would be granted rather
# than refused and the failure would say nothing about why. `chr(0xA0)` cannot be
# rewritten into something that looks the same, and it is reviewable on the page.
MALFORMED_SCOPES["a non-breaking space between the tokens"] = f"openid{chr(0xA0)}email"

# Values this suite sends and then looks for coming back. **This suite's choice**,
# and chosen to say where they came from: one of these turning up in a log, a
# seed or a claim is traceable to this file.
MARKER_STATE = "e0-16-state-marker"
MARKER_NONCE = "e0-16-nonce-marker"

# The two `grant_type` refusals RFC 6749 §5.2 keeps apart, as (what to leave out,
# what to override, which error). Written as one mapping because the pair is the
# rule: asserted in two separate tests they can both pass against a provider that
# answers one code for both, since neither test ever sees the other's case.
GRANT_TYPE_REFUSALS = {
    "no grant type at all": (["grant_type"], {}, INVALID_REQUEST),
    "a grant type this provider does not support": (
        [],
        {"grant_type": "client_credentials"},
        UNSUPPORTED_GRANT_TYPE,
    ),
}

# The token request's own fields, and the refusal each must produce when the value
# arrives with whitespace around it. Three fields rather than one because the
# never-repair rule is about the endpoint rather than about a parameter, and three
# *different* expected errors because a provider answering one code for all of
# them has stopped distinguishing an unsupported grant type from a grant that does
# not match.
PADDED_TOKEN_FIELDS = {
    "grant_type": UNSUPPORTED_GRANT_TYPE,
    "code": INVALID_GRANT,
    "client_id": INVALID_GRANT,
}

# A `client_id` and a `code` no registration and no flow ever produced, submitted
# beside the real one under the same name. Both spell out what they are.
FORGED_CLIENT_ID = "e0-16-forged-client"
FORGED_CODE = "e0-16-forged-authorization-code"

# Where the forged value sits relative to the real one. **Both orders are the
# test**, not thoroughness: a server that reads the last value for a repeated
# name refuses one ordering and accepts the other, so a single-order test reports
# a pass for whichever half it happened to pick and says nothing about the other.
REPEAT_ORDERS = {"the forged value first": True, "the forged value last": False}


def refusal(provider: Any, response: Any, subject: str) -> None:
    """Require `response` to be a refusal, and to be a refusal about `subject`.

    Four assertions rather than one, because "the exchange failed" is satisfied
    by several things that are not the rule under test:

      - A 2xx would be the defect itself, so the status is checked first.
      - **The status is 400, which RFC 6749 §5.2 fixes for a rejected grant.** Two
        earlier versions of this line were weaker, and each was weaker in a way
        worth recording. "Not 2xx" admits a 5xx, and a 5xx is not a refusal — it
        is input the provider failed to parse rather than a decision it made,
        which is a different defect with a different fix, and two malformed PKCE
        values produced exactly that here. "Any 4xx" replaced it, leaving the
        400-against-401 question to the pull request; the answer came back that
        §5.2's only other status is the 401 for `invalid_client`, which the
        assertion below already rules out by name, and that every refusal this
        provider raises carries the default 400. The loose range was therefore
        looser than both the specification and the code, and asserting the number
        is what would make a 401, a 403 or a 422 arriving later visible.
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
    assert response.status_code == REJECTED_GRANT_STATUS, (
        f"The token endpoint answered {response.status_code} for {subject} rather than "
        f"{REJECTED_GRANT_STATUS}. RFC 6749 §5.2 makes a rejected grant a 400 carrying an "
        "`error`, and its one other status — 401 for `invalid_client` — is ruled out above. A 5xx "
        "here would not be a refusal at all: it is the provider failing to handle the request, "
        f"which is what a malformed PKCE value did before it was fixed. Body begins "
        f"{response.text[:300]!r}."
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


def outcome_of(provider: Any, attempt: Any) -> tuple[str, Any]:
    """Drive `attempt` as far as the provider will take it, and say where it stopped.

    A request the provider should not honour may be turned away at any of three
    points, and **which one is not something E0-16 settles**: at the
    authorization endpoint, at the login form, or at the token endpoint when the
    code it issued is redeemed. All three are legal places to enforce PKCE — RFC
    7636 §4.4 recommends the first and requires the last — so a test that
    insisted on one would fail a provider for choosing another.

    So the walk goes as far as it can and hands back the stage it reached with
    the response that ended it, and the assertions are made about *that*: no
    crash anywhere along it, and no session at the end of it. The redemption uses
    the attempt's own verifier, which is the strongest case for the provider —
    if a session comes back for a verifier that genuinely matches nothing the
    provider could have stored, PKCE has been skipped rather than enforced.
    """
    if attempt.form is None:
        return "authorization endpoint", attempt.response
    submitted = provider.submit_login(attempt, provider.offered_identities(attempt)[0])
    if submitted.code is None:
        return "login form", submitted.response
    return "token endpoint", provider.redeem(submitted.code, attempt.verifier)


def with_repeated(
    parameters: Sequence[tuple[str, str]], name: str, value: str, *, first: bool
) -> list[tuple[str, str]]:
    """`parameters` with `value` added under `name`, beside the value already there.

    `first` puts the added value before the real one and otherwise after it. The
    rest of the request is untouched and stays in order, so the only difference
    between the two calls — and between either of them and a conformant request —
    is the duplicate and where it sits.
    """
    built: list[tuple[str, str]] = []
    for key, existing in parameters:
        if key != name:
            built.append((key, existing))
        elif first:
            built.extend([(name, value), (name, existing)])
        else:
            built.extend([(name, existing), (name, value)])
    return built


def scoped_claims_released(
    provider: Any, stage: str, response: Any, claims_in_token: Any
) -> list[str]:
    """The scope-bound claims a session carried, or nothing when none was issued.

    Read into the failure message of the assertion below rather than asserted
    separately, because a session that exists at all has already failed that
    assertion — a second `assert` for it would be a line that can never run. What
    it buys is the message: "it granted a session" and "it granted a session
    carrying this person's email address" are the same defect described at two
    different distances from the consequence.
    """
    if stage != "token endpoint":
        return []
    token = provider.body_of(response).get("id_token")
    if not isinstance(token, str) or not token:
        return []
    claims = claims_in_token(token)
    return sorted(claim for claim in SCOPED_CLAIMS if claim in claims)


def session_issued(provider: Any, stage: str, response: Any) -> bool:
    """Whether `response` handed back something a client could sign in with.

    An `id_token` at the token endpoint, or an authorization code anywhere
    earlier — a code is a session one exchange later, so treating only the token
    as "issued" would report the flow as refused at the moment it stopped being
    refused.
    """
    if stage == "token endpoint":
        return bool(provider.body_of(response).get("id_token"))
    return provider.read_authorization_response(response)[1] is not None


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
        "generated at startup — or the verifier in tests/fixtures/lti_platform.py is decoding "
        "rather than verifying, in which case every signature assertion in this module is "
        "vacuous."
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
        "not one. `pkce_pair` in tests/fixtures/mock_idp.py draws it from `secrets`."
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


@pytest.mark.parametrize("case", sorted(MALFORMED_VERIFIERS))
def test_a_code_redemption_carrying_a_malformed_pkce_verifier_is_refused_rather_than_crashing(
    mock_idp: Any, case: str
) -> None:
    """The token endpoint's half of a measured defect: malformed input, not a wrong answer.

    A `code_verifier` carrying a character outside ASCII raised inside the
    provider and produced a 500. That is a different failure from the mismatch
    two tests above, and no test in this module could reach it: `pkce_pair` in
    `tests/fixtures/mock_idp.py` builds every verifier this suite sends out of
    `secrets.token_urlsafe`, which cannot emit a byte outside the unreserved set
    — so the suite was structurally incapable of producing the input that broke
    it. The values are written out at the top of this file for that reason.

    **Why a 500 matters when the client sees no token either way.** A crash is
    reached by input the provider failed to parse rather than by a decision it
    made, so nothing about the request has been judged: an endpoint that raises
    on one malformed shape usually raises on others, it says so in a stack trace
    rather than in an `error` member, and E1 would be writing a client against a
    provider that answers a 500 where every real IdP answers a 400. `refusal`
    above requires the 4xx; the assertion here names the crash directly, so the
    failure reads as what it is.

    The non-ASCII case is the measured one. The empty and over-long verifiers are
    its neighbours: both are refused by the digest comparison in any
    implementation, so neither depends on an alphabet or length check existing,
    and both are the shapes an unguarded slice fails on.

    The control is a whole flow redeemed with its matching verifier, on the same
    provider, in the same test — without it a token endpoint that refused
    everything would pass.
    """
    control = mock_idp.login()
    assert control.tokens.get("id_token"), (
        "A flow redeemed with its matching verifier produced no `id_token`, so the refusal below "
        "would be indistinguishable from a token endpoint that refuses every exchange."
    )

    attempt = mock_idp.begin()
    identity = mock_idp.offered_identities(attempt)[0]
    submitted = mock_idp.submit_login(attempt, identity)
    assert submitted.code, (
        f"Signing in as {identity} produced no authorization code (status "
        f"{submitted.response.status_code}), so there is nothing to redeem."
    )

    response = mock_idp.redeem(submitted.code, MALFORMED_VERIFIERS[case])

    assert response.status_code < 500, (
        f"Redeeming a code with {case} answered {response.status_code}. The provider raised on "
        "the value rather than deciding about it — the request never got as far as being "
        f"rejected. Body begins {response.text[:300]!r}."
    )
    refusal(mock_idp, response, f"a code exchange carrying {case}")


@pytest.mark.parametrize("case", sorted(MALFORMED_CHALLENGES))
def test_an_authorization_request_with_a_malformed_pkce_challenge_does_not_crash_or_grant(
    mock_idp: Any, case: str
) -> None:
    """The other entry point for the same defect, and it is a separate half.

    A `code_challenge` outside ASCII was **accepted** by the authorization
    endpoint and raised later, when the redemption compared it. The two were
    fixed one after the other and the first fix did not close the second, which
    is `docs/MISTAKES.md` entry 13 exactly: one hazard faced at two entry points,
    worked around at one. So this is its own test rather than a second assertion
    in the one above, and either half can regress without the other going red.

    **This is why the flow is walked to its end.** The malformed value enters
    here and the crash lands at the token endpoint, so a test that judged the
    authorization response and stopped would have watched the provider accept the
    value and reported a pass — the defect intact, one step further on.
    `outcome_of` above therefore goes as far as the provider allows and reports
    the stage it stopped at, which also means neither assertion below decides
    *where* PKCE is enforced.

    **Two assertions, and neither can substitute for the other.** The provider
    must not raise, and no session may come out of the flow. The second is not
    implied by the first — a provider that accepted the malformed challenge,
    showed the form and issued a spendable code has crashed nowhere — and the
    first is not implied by the second, because a 500 also produces no session
    and would read as a refusal.

    **What is deliberately not asserted here: the shape of the refusal.** E0-16
    did not say what a malformed authorization request should answer, and this
    test was written while error redirects were deferred. **E0-30 settled it** —
    a refusal raised after `client_id` and `redirect_uri` have validated arrives
    as RFC 6749 §4.1.2.1's redirect carrying `error`, `error_description` and the
    echoed `state`, and `tests/integration/test_mock_idp_error_redirects.py`
    holds a test per code. This test keeps asserting the *verdict* — no crash,
    no session — because E0-30 changed only where a refusal is delivered, and
    because that is what makes the two modules fail for different reasons: this
    one goes red if a malformed challenge is honoured, and that one goes red if a
    refusal comes back as a page.
    """
    control = mock_idp.login()
    assert control.tokens.get("id_token"), (
        "A well-formed flow produced no session on this provider, so 'a malformed challenge "
        "produces none' would be a fact about the provider being broken for everyone."
    )

    attempt = mock_idp.begin(code_challenge=MALFORMED_CHALLENGES[case])
    stage, response = outcome_of(mock_idp, attempt)

    assert response.status_code < 500, (
        f"An authorization request carrying {case} reached the {stage} and answered "
        f"{response.status_code}. The provider raised on the value rather than deciding about "
        f"it. Body begins {response.text[:300]!r}."
    )
    assert not session_issued(mock_idp, stage, response), (
        f"An authorization request carrying {case} was honoured: the {stage} handed back a "
        "session. RFC 7636 §4.4 has the server reject a challenge it cannot use, and a challenge "
        "no verifier can ever match is PKCE removed rather than PKCE applied — the code becomes "
        "spendable by whoever holds it, which is the whole of what the challenge exists to "
        "prevent."
    )


# ---------------------------------------------------------------------------
# The value the provider judges is the value it was sent, byte for byte.
# ---------------------------------------------------------------------------


def test_a_code_verifier_that_only_trims_to_the_right_value_is_refused(
    mock_idp: Any, padded: Any
) -> None:
    """The review's HIGH: a parameter trimmed before the check that judges it.

    `.strip()` ran before the shape check, so for a challenge registered over a
    verifier `v` **every string that trims to `v`** satisfied the proof — PKCE was
    binding an unbounded set of values rather than the one the client held. A
    stolen code plus any padding of the verifier is the same session.

    **The pairing is the whole test, and the obvious way to write it passes
    against the defect.** The first reproduction of this used a self-consistent
    client — the same padded value used to compute the challenge *and* sent as the
    verifier — and got a refusal before the fix, because trimming both sides
    cancels out and the comparison is between two clean values. It looks like a
    test and it closes a real HIGH as "cannot reproduce". So the challenge here is
    bound over the **clean** verifier, by an ordinary conformant `begin()`, and
    only the redemption is padded. Do not simplify this into one padded value.

    The control is the same construction with the padding left off, on the same
    provider, in the same test: without it a token endpoint that refused every
    exchange would pass.
    """
    control = mock_idp.login()
    assert control.tokens.get("id_token"), (
        "A flow redeemed with its own unpadded verifier produced no `id_token`, so the refusal "
        "below would say nothing about padding."
    )

    attempt = mock_idp.begin()
    identity = mock_idp.offered_identities(attempt)[0]
    submitted = mock_idp.submit_login(attempt, identity)
    assert submitted.code, (
        f"Signing in as {identity} produced no authorization code (status "
        f"{submitted.response.status_code}), so there is nothing to redeem."
    )

    response = mock_idp.redeem(submitted.code, padded(attempt.verifier))

    refusal(mock_idp, response, "a code exchange whose verifier only trims to the right value")
    assert mock_idp.body_of(response).get("error") == INVALID_GRANT, (
        f"The exchange was refused as {mock_idp.body_of(response).get('error')!r}. RFC 6749 §5.2 "
        f"makes {INVALID_GRANT!r} the code for a grant whose proof does not match — which is what "
        "a verifier one whitespace character away from correct is. `invalid_request` would say "
        "the request was malformed, and it is not: it is a well-formed request carrying the "
        "wrong value."
    )


def test_the_state_comes_back_exactly_as_it_was_sent(mock_idp: Any, padded: Any) -> None:
    """The same defect reaching `state`, where the cost is a client that cannot match it.

    RFC 6749 §4.1.2 returns `state` unchanged, and a client compares it to what it
    stored. A provider that trims it hands back a value the client never sent, so
    the comparison fails for a login that was perfectly legitimate — or, on a
    client that trims its own copy before comparing, silently succeeds for one
    that was not.

    Clean control first, padded value second, both on values that say where they
    came from.
    """
    clean = mock_idp.begin(state=MARKER_STATE)
    clean_submitted = mock_idp.submit_login(clean, mock_idp.offered_identities(clean)[0])
    assert clean_submitted.state == MARKER_STATE, (
        f"An unpadded `state` came back as {clean_submitted.state!r} rather than "
        f"{MARKER_STATE!r}, so the assertion below would be about a provider that does not echo "
        "`state` at all."
    )

    padded_state = padded(MARKER_STATE)
    attempt = mock_idp.begin(state=padded_state)
    submitted = mock_idp.submit_login(attempt, mock_idp.offered_identities(attempt)[0])

    assert submitted.state == padded_state, (
        f"The authorization response returned state {submitted.state!r}; the request sent "
        f"{padded_state!r}. RFC 6749 §4.1.2 requires the value back exactly — a provider that "
        "trims it is answering about a value the client never sent, and the client's own "
        "comparison then fails on a login it started itself."
    )


def test_the_nonce_is_issued_exactly_as_it_was_sent(mock_idp: Any, padded: Any) -> None:
    """The same defect reaching `nonce`, where the cost is the replay check itself.

    OIDC Core 1.0 §3.1.3.7 step 11 has the client compare the `nonce` claim to the
    value it sent. A provider that trims it breaks that comparison for a
    legitimate login and — the direction that matters — makes two different
    requests indistinguishable in the session they produce, which is the property
    the nonce exists to give.
    """
    clean = mock_idp.login(nonce=MARKER_NONCE)
    assert clean.claims.get("nonce") == MARKER_NONCE, (
        f"An unpadded `nonce` was issued as {clean.claims.get('nonce')!r} rather than "
        f"{MARKER_NONCE!r}, so the assertion below would be about a provider that does not carry "
        "the nonce at all."
    )

    padded_nonce = padded(MARKER_NONCE)
    login = mock_idp.login(nonce=padded_nonce)

    assert login.claims.get("nonce") == padded_nonce, (
        f"The `id_token` carries nonce {login.claims.get('nonce')!r}; the authorization request "
        f"sent {padded_nonce!r}. The client compares exactly these two (OIDC Core §3.1.3.7), so a "
        "provider that trims one of them has removed the check rather than performed it."
    )


def test_a_state_that_is_only_whitespace_is_refused_as_absent(mock_idp: Any, padded: Any) -> None:
    """The other half of the fix, and the half that could silently invert later.

    Presence is judged on the *trimmed* value and the *untrimmed* one is what gets
    handed on — two rules about one parameter, and the three tests above pin only
    the second. A parameter that is nothing but whitespace is therefore absent,
    and a required parameter that is absent is a request the provider may not
    honour.

    Written with `padded("")` rather than a whitespace literal so that it is
    visibly the same padding as the tests above with nothing inside it: together
    they say that the whitespace is stripped for the question "is it there" and
    kept for the question "what is it". If someone later judges presence on the
    untrimmed value, `"   "` becomes a present state, this flow succeeds, and this
    test is the only thing that notices.
    """
    control = mock_idp.login()
    assert control.tokens.get("id_token"), (
        "A well-formed flow produced no session on this provider, so 'a whitespace state produces "
        "none' would be a fact about the provider being broken for everyone."
    )

    attempt = mock_idp.begin(state=padded(""))
    stage, response = outcome_of(mock_idp, attempt)

    assert response.status_code < 500, (
        f"An authorization request whose `state` is only whitespace reached the {stage} and "
        f"answered {response.status_code} — the provider raised on it rather than deciding about "
        f"it. Body begins {response.text[:300]!r}."
    )
    assert not session_issued(mock_idp, stage, response), (
        f"An authorization request whose `state` is only whitespace was honoured by the {stage}. "
        "A value that trims to nothing is an absent parameter, and `state` is what a client "
        "matches its own login against; a provider that accepts one has issued a session no "
        "client can attribute to a request it made."
    )


# ---------------------------------------------------------------------------
# One name, two values. What a repeated parameter must not buy.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(REPEAT_ORDERS))
def test_an_authorization_request_repeating_the_client_id_is_refused(
    mock_idp: Any, case: str
) -> None:
    """`client_id=forged&client_id=real`, and the same pair the other way round.

    RFC 6749 says nothing about a parameter that appears twice, so what a server
    does with one is decided by the web framework underneath it — and every
    framework picks an end. A provider that reads the last value refuses the
    forged-first ordering and accepts the forged-last one, which means **a test
    written in one order reports a pass for the half it happened to pick**. Both
    orders are therefore the test rather than a pair of similar tests, and
    `begin_from` in `tests/fixtures/mock_idp.py` exists because a mapping cannot express
    the question at all.

    What it buys an attacker if it is accepted: the request one endpoint validates
    and the request another reads are two different requests, which is how a code
    ends up issued for one client and redeemable by another.

    The control is a conformant flow on the same provider.
    """
    control = mock_idp.login()
    assert control.tokens.get("id_token"), (
        "A conformant flow produced no session on this provider, so the refusal below would be a "
        "fact about a provider that is broken for everyone."
    )

    request, verifier = mock_idp.authorization_request()
    repeated = with_repeated(
        list(request.items()), "client_id", FORGED_CLIENT_ID, first=REPEAT_ORDERS[case]
    )
    attempt = mock_idp.begin_from(repeated, verifier)
    stage, response = outcome_of(mock_idp, attempt)

    assert response.status_code < 500, (
        f"An authorization request carrying two `client_id` values, with {case}, reached the "
        f"{stage} and answered {response.status_code} — the provider raised rather than deciding. "
        f"Body begins {response.text[:300]!r}."
    )
    assert not session_issued(mock_idp, stage, response), (
        f"An authorization request carrying two `client_id` values, with {case}, was honoured by "
        f"the {stage}: it handed back a session for a request naming two different clients. Which "
        "of the two a reader takes is a framework's choice rather than the specification's, so "
        "one of these two orderings will always be the attacker's — the request has to be refused "
        "rather than resolved."
    )


@pytest.mark.parametrize("case", sorted(REPEAT_ORDERS))
def test_a_token_request_repeating_the_code_is_refused(mock_idp: Any, case: str) -> None:
    """The same question at the token endpoint, where the duplicate is the grant itself.

    `code` rather than `client_id` here, for two reasons. It is the field where
    last-wins is worth the most — a forged value beside a real one, in whichever
    order the reader does not take, redeems a grant the request did not present —
    and it keeps the refusal readable: a duplicated `client_id` may legitimately
    come back as `invalid_client`, which `refusal` treats as a gap in this suite's
    own client authentication rather than as an answer about the duplicate.

    The control is the *same* body, single-valued, redeemed on its own flow and
    required to succeed.
    """
    control_attempt = mock_idp.begin()
    control_submitted = mock_idp.submit_login(
        control_attempt, mock_idp.offered_identities(control_attempt)[0]
    )
    assert control_submitted.code, "Signing in produced no authorization code for the control."
    control = mock_idp.redeem_from(
        list(mock_idp.token_body(control_submitted.code, control_submitted.verifier).items())
    )
    assert mock_idp.tokens(control).get("id_token"), (
        "A single-valued token request built the same way produced no `id_token`, so the refusal "
        "below would be about `redeem_from` rather than about the duplicate."
    )

    attempt = mock_idp.begin()
    submitted = mock_idp.submit_login(attempt, mock_idp.offered_identities(attempt)[0])
    assert submitted.code, "Signing in produced no authorization code, so there is nothing to send."

    body = mock_idp.token_body(submitted.code, submitted.verifier)
    repeated = with_repeated(list(body.items()), "code", FORGED_CODE, first=REPEAT_ORDERS[case])
    response = mock_idp.redeem_from(repeated)

    assert response.status_code < 500, (
        f"A token request carrying two `code` values, with {case}, answered "
        f"{response.status_code} — the provider raised rather than deciding. Body begins "
        f"{response.text[:300]!r}."
    )
    refusal(mock_idp, response, f"a token request carrying two `code` values, with {case}")


def test_a_login_naming_one_person_in_the_query_and_another_in_the_body_is_refused(
    mock_idp: Any,
) -> None:
    """The same rule across two *sources*, which is where the first fix did not reach.

    The duplicate check ran over one collection at a time, so a name sent once in
    the query string and once in the body was two singletons rather than one
    duplicate — and RFC 6749 §3.1 is a statement about the request, not about one
    encoding of it (ADR 0062, rule 3: whole-request questions are asked before a
    mapping exists, because `dict()` is where a repetition stops being visible).

    Two *different people* rather than the same value twice, because that is what
    makes the answer matter: whichever source the provider reads is the person it
    signs in, and the other one is what a reviewer reading the other half of the
    request would think happened.

    The control is the same submission with no query string on it.
    """
    control_attempt = mock_idp.begin()
    control = mock_idp.submit_login(
        control_attempt, mock_idp.offered_identities(control_attempt)[0]
    )
    assert control.code, (
        f"A login with nothing added to its URL produced no code (status "
        f"{control.response.status_code}), so the refusal below would be a fact about a login "
        "form that never works."
    )

    attempt = mock_idp.begin()
    form = mock_idp.require_login_form(attempt)
    field = mock_idp.identity_field(form)
    offered = mock_idp.offered_identities(attempt)
    people = sorted({submission[field] for submission in offered if submission.get(field)})
    assert len(people) >= 2, (
        f"The login form offers {people} under `{field}`, so there is no second person to name in "
        "the query. This test needs two."
    )
    signing_in = offered[0][field]
    other = next(person for person in people if person != signing_in)

    submitted = mock_idp.submit_login(attempt, offered[0], query={field: other})

    assert submitted.response.status_code < 500, (
        f"A login naming one person in the body and another in the query answered "
        f"{submitted.response.status_code} — the provider raised rather than deciding. Body "
        f"begins {submitted.response.text[:300]!r}."
    )
    assert submitted.refused, (
        f"A login naming `{field}`={signing_in!r} in the body and "
        f"`{field}`={other!r} in the query issued a code ({submitted.code!r}). One request "
        "named two people and the provider picked one: whichever source it reads, the other is "
        "what the request also says, and a session was issued for a request that does not say who "
        "it is for."
    )


def test_a_token_request_repeating_a_field_across_the_query_and_the_body_is_refused(
    mock_idp: Any,
) -> None:
    """The same rule at the token endpoint, and the probe that would have understated it.

    The body here is **valid** — a real code, its own verifier, the registered
    client — and the query carries `code` and `grant_type` again with values that
    are not. That pairing is the test: the first probe of this used a bogus code
    in the body and got a 400 either way, which reads as "already refused" and
    would have closed the finding. Only a request the provider would otherwise
    accept can show that the duplicate is what stopped it.

    The control is that same valid body posted with no query string, which must
    succeed. It runs on its own flow, because an authorization code is single-use
    and reusing one would make the second exchange a replay test.
    """
    control_attempt = mock_idp.begin()
    control_submitted = mock_idp.submit_login(
        control_attempt, mock_idp.offered_identities(control_attempt)[0]
    )
    assert control_submitted.code, "Signing in produced no authorization code for the control."
    control = mock_idp.redeem_from(
        list(mock_idp.token_body(control_submitted.code, control_submitted.verifier).items())
    )
    assert mock_idp.tokens(control).get("id_token"), (
        "The same body with no query string produced no `id_token`, so the refusal below would "
        "not be about the query string."
    )

    attempt = mock_idp.begin()
    submitted = mock_idp.submit_login(attempt, mock_idp.offered_identities(attempt)[0])
    assert submitted.code, "Signing in produced no authorization code, so there is nothing to send."

    response = mock_idp.redeem_from(
        list(mock_idp.token_body(submitted.code, submitted.verifier).items()),
        query={"code": FORGED_CODE, "grant_type": "bogus"},
    )

    assert response.status_code < 500, (
        f"A token request repeating `code` and `grant_type` in the query answered "
        f"{response.status_code} — the provider raised rather than deciding. Body begins "
        f"{response.text[:300]!r}."
    )
    refusal(mock_idp, response, "a token request repeating fields across the query and the body")
    assert mock_idp.body_of(response).get("error") == INVALID_REQUEST, (
        f"The exchange was refused as {mock_idp.body_of(response).get('error')!r}. RFC 6749 §5.2 "
        f"makes {INVALID_REQUEST!r} the code for a request that 'includes a parameter more than "
        "once' — the grant itself was valid, and saying `invalid_grant` here would send a client "
        "looking at its code rather than at its request."
    )


# ---------------------------------------------------------------------------
# Scope: what a client asked for is what it gets, and no more.
# ---------------------------------------------------------------------------


def test_the_openid_scope_alone_releases_no_email_or_username_claim(mock_idp: Any) -> None:
    """OIDC Core 1.0 §5.4: `email` and `profile` claims come with `email` and `profile`.

    A provider that releases them for `openid` alone teaches every client that
    scope is decorative, and the client E1 writes against it will ask for `openid`
    and read a `preferred_username` that a real IdP would not have sent — which
    fails at the institution rather than here.

    **The roles claim is asserted present in the same test**, and that is not a
    stray extra assertion. It is the live control: a session carrying no claims at
    all satisfies "none of these three is here", and the absence would then be a
    fact about a session with nothing in it. It is also the rule itself — the
    roles claim stays bound to `openid` deliberately, because a client that had to
    know to ask for it would discover the omission at role resolution, with an
    empty purview looking like a person who supervises nothing.
    """
    login = mock_idp.login(scope=BASE_SCOPE)
    roles_claim = mock_idp.roles_claim_name()

    assert roles_claim in login.claims, (
        f"A session issued for {BASE_SCOPE!r} carries no `{roles_claim}` claim (it carries "
        f"{sorted(login.claims)}). The registration document names that claim as where a client "
        "reads its roles, and it is not gated on a scope — so its absence here is both a missing "
        "rule and the reason the assertion below would otherwise be vacuous."
    )

    released = sorted(claim for claim in SCOPED_CLAIMS if claim in login.claims)
    assert not released, (
        f"A session issued for {BASE_SCOPE!r} alone carries {released}. OIDC Core 1.0 §5.4 "
        f"attaches those to the `email` and `profile` scopes; releasing them unasked means this "
        "provider grants more than it was asked for, and a client built against it will ask for "
        "less than it needs from a real one."
    )


def test_the_email_and_profile_scopes_release_their_claims(mock_idp: Any) -> None:
    """The other direction, without which the test above passes on a provider that releases nothing.

    A provider that never emits `email` satisfies "no email for `openid` alone"
    perfectly, and E0-18's browser path would then have no identity to show. So
    the same three claims are required when the scopes that carry them are asked
    for.
    """
    login = mock_idp.login(scope=FULL_SCOPE)

    missing = sorted(claim for claim in SCOPED_CLAIMS if claim not in login.claims)
    assert not missing, (
        f"A session issued for {FULL_SCOPE!r} is missing {missing} (it carries "
        f"{sorted(login.claims)}). OIDC Core 1.0 §5.4 attaches `email` and `email_verified` to the "
        "`email` scope and `preferred_username` to `profile`, and a scope that releases nothing is "
        "a scope a client cannot use."
    )
    assert mock_idp.roles_claim_name() in login.claims, (
        f"A session issued for {FULL_SCOPE!r} carries no roles claim. The claim is bound to "
        "`openid` rather than to an optional scope, so asking for more must not take it away — a "
        "widening request that quietly drops the one claim authorization depends on is worse than "
        "one that fails."
    )


@pytest.mark.parametrize("requested", [BASE_SCOPE, FULL_SCOPE])
def test_the_token_response_says_which_scope_it_granted(mock_idp: Any, requested: str) -> None:
    """RFC 6749 §5.1: the response tells the client what it actually got.

    Both scopes, because an echo asserted for one value is satisfied by a
    provider that answers a constant — and the constant it would answer is
    `openid`, which is the case that looks correct.
    """
    login = mock_idp.login(scope=requested)

    assert login.tokens.get("scope") == requested, (
        f"Asking for {requested!r} produced a token response declaring scope "
        f"{login.tokens.get('scope')!r}. RFC 6749 §5.1 has the response state the granted scope, "
        "and a client reads it to find out whether what it asked for is what it may rely on."
    )


@pytest.mark.parametrize("case", sorted(MALFORMED_SCOPES))
def test_a_scope_separated_by_anything_but_a_space_yields_no_session(
    mock_idp: Any, claims_in_token: Any, case: str
) -> None:
    """RFC 6749 Appendix A.4's grammar, and the defect that made the last round's test unable to fire.

    `scope.split()` treats a tab, a newline and U+00A0 as separators, so
    `openid<TAB>email` reached the provider as two tokens it knew and was granted
    — one unknown token to any conformant server, and a session carrying claims
    the client never asked for. Okta answers `invalid_scope` for it; Azure AD
    answers `AADSTS70011`.

    **It also made the unknown-scope refusal written the round before unable to
    fire at all**, which is the part worth keeping in mind while reading this
    module: that test sends `openid wibble`, and a repair upstream of it turned
    every malformed value into a well-formed one before the check it was aimed at
    could see it. A guard cannot be tested through a repair that runs first.

    **The doubled space is here for the opposite reason from the other three**,
    and it took a measurement to say which. A bare `split()` *drops* the empty
    token, so `openid  email` reads as two valid tokens and is granted; the
    grammar refuses it, because an empty token is not `1*NQCHAR`. The two
    implementations therefore disagree about the outcome, which is what makes the
    case detect the defect — by outcome rather than by what either does with a
    separator. The strictness is deliberate: some servers tolerate a doubled space,
    and refusing it is the right direction for a mock, because a client that
    satisfies this provider satisfies a lenient one and the reverse is what E0-28
    exists to catalogue.

    An earlier version of this paragraph said that case could not detect the
    defect at all, and its parameter name said so too. It was reasoned from
    `split()` dropping empty tokens and never run; restoring `scope.split()`
    reddens all four cases. A prediction about which mutations a test kills is a
    claim like any other, and this one had been written where it reads as
    documentation.

    The control is `openid email profile` on the same provider in the same test.
    The fix's own risk is over-refusal — a grammar check that rejects every
    multi-token scope would satisfy every assertion below and break every real
    client — and nothing else in this test would notice.
    """
    control = mock_idp.login(scope=FULL_SCOPE)
    assert control.tokens.get("id_token"), (
        f"A conformant multi-token scope ({FULL_SCOPE!r}) produced no session, so the refusals "
        "below would be a fact about a provider that refuses every scope with more than one token "
        "in it — which is this fix's own failure mode rather than the defect it closes."
    )

    scope = MALFORMED_SCOPES[case]
    attempt = mock_idp.begin(scope=scope)
    stage, response = outcome_of(mock_idp, attempt)

    assert response.status_code < 500, (
        f"An authorization request with {case} ({scope!r}) reached the {stage} and answered "
        f"{response.status_code} — the provider raised rather than deciding. Body begins "
        f"{response.text[:300]!r}."
    )

    released = scoped_claims_released(mock_idp, stage, response, claims_in_token)
    assert not session_issued(mock_idp, stage, response), "\n".join(
        [
            f"An authorization request with {case} ({scope!r}) was granted by the {stage}"
            + (f", releasing {released}" if released else "")
            + ".",
            "",
            "RFC 6749 Appendix A.4: `scope = scope-token *( SP scope-token )`, one space and "
            "nothing else. A separator the grammar does not have, treated as one, turns a value "
            "the client got wrong into two tokens the provider knows — so the client is granted "
            "what it did not ask for and told it asked for it.",
        ]
    )


def test_an_unknown_scope_yields_no_session(mock_idp: Any) -> None:
    """A request for something this provider does not offer is refused, not quietly narrowed.

    The failure this exists for is the silent one: a provider that drops the part
    of the scope it does not recognise issues a session that looks like the one
    the client asked for and is missing what it asked for, and the client finds
    out downstream — at role resolution, or in a claim that is absent for a reason
    nothing recorded.
    """
    control = mock_idp.login()
    assert control.tokens.get("id_token"), (
        "A conformant flow produced no session on this provider, so the refusal below would be a "
        "fact about a provider that is broken for everyone."
    )

    attempt = mock_idp.begin(scope=UNKNOWN_SCOPE)
    stage, response = outcome_of(mock_idp, attempt)

    assert response.status_code < 500, (
        f"An authorization request for {UNKNOWN_SCOPE!r} reached the {stage} and answered "
        f"{response.status_code} — the provider raised rather than deciding. Body begins "
        f"{response.text[:300]!r}."
    )
    assert not session_issued(mock_idp, stage, response), (
        f"An authorization request for {UNKNOWN_SCOPE!r} was honoured by the {stage}. RFC 6749 "
        "§3.3 lets a server refuse or narrow, and narrowing silently is what leaves a client "
        "holding a session that is missing something it asked for with nothing saying so — "
        "`invalid_scope` exists for this."
    )


# ---------------------------------------------------------------------------
# The token endpoint's own parameters: which refusal, and on which value.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(GRANT_TYPE_REFUSALS))
def test_the_token_endpoint_distinguishes_a_missing_grant_type_from_an_unsupported_one(
    mock_idp: Any, case: str
) -> None:
    """RFC 6749 §5.2 gives these two different codes, and the module gave them one.

    `invalid_request` is for a request "missing a required parameter";
    `unsupported_grant_type` is reserved for a grant type "not supported by the
    authorization server". A client reading the first goes looking at what it
    failed to send and a client reading the second goes looking at what it
    supports, and they are different afternoons.

    **The two are one parametrized test on purpose.** Asserted separately they can
    both pass against a provider that answers one code for both, because each
    assertion would only ever see its own case — the pair is the rule, and a
    single test with two parameters is what makes the pair fail as a pair. The
    same module already answered this correctly one check later, for a missing
    `code`, so the two refusals disagreed with each other about the same rule.

    Each case gets its own flow: a code is single-use, and a control login proves
    the endpoint answers at all before either refusal is believed.
    """
    omitting, overrides, expected = GRANT_TYPE_REFUSALS[case]

    control = mock_idp.login()
    assert control.tokens.get("id_token"), (
        "A conformant exchange produced no session, so the refusal below would be a fact about a "
        "token endpoint that refuses everything."
    )

    attempt = mock_idp.begin()
    submitted = mock_idp.submit_login(attempt, mock_idp.offered_identities(attempt)[0])
    assert submitted.code, "Signing in produced no authorization code, so there is nothing to send."

    response = mock_idp.redeem(submitted.code, submitted.verifier, omitting=omitting, **overrides)

    refusal(mock_idp, response, f"a token request with {case}")
    assert mock_idp.body_of(response).get("error") == expected, (
        f"A token request with {case} was refused as "
        f"{mock_idp.body_of(response).get('error')!r} rather than {expected!r}. RFC 6749 §5.2 "
        "assigns `invalid_request` to a missing required parameter and reserves "
        "`unsupported_grant_type` for a grant type the server does not support; a provider that "
        "answers the same code for both has told the client nothing it can act on."
    )


@pytest.mark.parametrize("field", sorted(PADDED_TOKEN_FIELDS))
def test_a_padded_token_request_field_is_refused_rather_than_repaired(
    mock_idp: Any, padded: Any, field: str
) -> None:
    """The never-repair rule on the endpoint the earlier round did not reach.

    The authorization endpoint's exactness is asserted three tests above — a
    padded verifier, `state` and `nonce` returned byte for byte — and this is the
    same property on the token endpoint's own parameters, which nothing covered:
    a `grant_type`, a `code` or a `client_id` arriving with whitespace around it
    must be the value that arrived, not the value it trims to.

    What repairing them costs is not symmetry. A trimmed `code` means two
    different strings redeem one grant, which is the PKCE defect again in the
    field the grant is named by; a trimmed `client_id` means a client identifier
    is matched loosely, which is how one client's code becomes another's; a
    trimmed `grant_type` is the mildest and is still a request the provider
    answered as though it said something it did not say.

    Which refusal each produces is asserted, not just that one did: they are
    different rules — an unsupported grant type against a grant that does not
    match — and a provider answering one code for all three would be treating a
    request it could not parse as a request it could.
    """
    expected = PADDED_TOKEN_FIELDS[field]

    control = mock_idp.login()
    assert control.tokens.get("id_token"), (
        "A conformant exchange produced no session, so the refusal below would be a fact about a "
        "token endpoint that refuses everything."
    )

    attempt = mock_idp.begin()
    submitted = mock_idp.submit_login(attempt, mock_idp.offered_identities(attempt)[0])
    assert submitted.code, "Signing in produced no authorization code, so there is nothing to send."

    body = mock_idp.token_body(submitted.code, submitted.verifier)
    assert field in body, (
        f"A conformant token request carries no `{field}` (it carries {sorted(body)}), so there is "
        "nothing to pad. `token_body` in tests/fixtures/mock_idp.py builds RFC 6749 §4.1.3's "
        "request."
    )
    body[field] = padded(body[field])
    response = mock_idp.redeem_from(list(body.items()))

    assert response.status_code < 500, (
        f"A token request whose `{field}` carried surrounding whitespace answered "
        f"{response.status_code} — the provider raised rather than deciding. Body begins "
        f"{response.text[:300]!r}."
    )
    refusal(mock_idp, response, f"a token request whose `{field}` was padded with whitespace")
    assert mock_idp.body_of(response).get("error") == expected, (
        f"A padded `{field}` was refused as {mock_idp.body_of(response).get('error')!r} rather "
        f"than {expected!r}. The value that arrived is the value the provider must judge — a "
        f"`{field}` that only trims to the right one is a different `{field}`."
    )


def test_an_authorization_request_naming_an_unregistered_redirect_uri_is_refused(
    mock_idp: Any,
) -> None:
    """The security review's redirect-URI item: a code may only go where it was registered.

    This is the oldest hole in OAuth, and a mock that leaves it open teaches the
    tool-side code the habit E0-16's definition of done exists to prevent: RFC
    6749 §4.1.2.1 says a server that finds the redirect URI invalid "MUST NOT
    automatically redirect the user-agent to the invalid redirect URI", because
    doing so hands the code to whoever named it.

    Asserted as *where the code went*, not as a status. Several shapes are
    conformant here — a refusal page, a 400, or a redirect back to the
    *registered* URI carrying an error — and what none of them may do is send an
    authorization code to the URI it was handed. **E0-30 chose among them for
    this provider**: an unregistered redirect URI is refused before there is any
    address to redirect to, so it stays a page, and
    `tests/integration/test_mock_idp_error_redirects.py` asserts that choice
    along with the near miss that makes it load-bearing — an unregistered URI
    sent together with a second defect, which must still not redirect. This
    assertion is unchanged by that ticket and is deliberately the weaker,
    longer-lived one: no code reaches the address, whatever the transport.
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
        "tests/fixtures/mock_idp.py found the wrong thing and every other test here fails for "
        "that reason, or the provider refuses a conformant authorization request."
    )
