"""The mock platform's roster refuses a read that is not authorised — E1-11 fix round.

E1-06 built the client-credentials grant and ruled that the Advantage services
would not start requiring a token yet: "a service that started refusing before a
conformant client existed would be refusing this repository's own tests"
(`docs/tickets/e1/carried-from-e0.md`, "The client-credentials grant"). That
ruling named the ticket that would end it — "enforcement pairs with E1-11's
client" — and E1-11's client landed without it, so the route went on answering
200 to anybody who could reach it. E1-15's exit clause 5 needs the refusal, and
this module is it.

**The contract, in one sentence.** `GET` on the memberships URL a launch
advertises requires an `Authorization: Bearer <token>` whose token this
platform's own endpoint (`mock-lms/app/tokens.py`) issued carrying the NRPS
membership scope. Missing or malformed header → **401** with a
`WWW-Authenticate: Bearer` challenge. A token this endpoint never issued, or one
that has expired → **401**, `invalid_token`. A token issued without the
membership scope → **403**, `insufficient_scope`. A token issued with it → the
container, exactly as before.

**Where the status codes and the two error strings come from.** RFC 6750 — it is
the only document that defines `invalid_token` and `insufficient_scope`, §3.1
fixes which status answers each, and §3 puts them inside the
`WWW-Authenticate` challenge as an `error` parameter. So the challenge is where
this module reads them. Nothing here invents a vocabulary: the work order names
the two strings and the two statuses, and they are that RFC's, so its own
placement is the one they belong in.

**AGS is deliberately not here.** No grade-passback client exists yet — SPEC §14.3
gives AGS line-item creation and score posting to **E3**, "Grade passback" — so the
argument E1-06 made is still live for that half of the surface, and
`MockPlatform.refuse_an_unspecified_ags_token_flow` still reports an AGS 401 as a
gap in a ticket rather than as a defect. §3.4 states the rule the passback
implements; §14.3 is what says whose it is.

**Every refusal is one difference from a read that works, and carries it.** A
401 is a 401: a platform that refused every roster read would satisfy each refusal
below and serve nothing (`docs/MISTAKES.md` entry 3). So each test performs the
authorised read first, against the same URL on the same platform, and then changes
exactly one thing — the header, the signature, the clock, the scope.

**No §4.1 invariant lives here**, for the reason `test_mock_lms_nrps_roster.py`
gives: the mock is a platform, not a Pulse read path.
"""

import re
import time
from typing import Any

import pytest

pytestmark = pytest.mark.lti

# `mock_platform`, `tool_key_pair`, `key_the_tool_never_published`,
# `claims_for_an_assertion` and `wind_the_clock_back` come from `tests/fixtures/`
# and are reached as fixtures rather than imported, for the reason every module in
# this suite gives: an import of a fixtures module by name depends on where pytest
# put `tests/` on `sys.path`, and an import error is not a red.

# The media type an NRPS membership container is asked for, as NRPS 2.0 spells it.
# Sent on every request below, refused and accepted alike, so that the only thing
# differing between a pair is the credential.
NRPS_MEDIA_TYPE = "application/vnd.ims.lti-nrps.v2.membershipcontainer+json"

# The scope a token must carry to read a roster, as NRPS 2.0 spells it and as the
# platform's own discovery document advertises it. A specification constant.
NRPS_MEMBERSHIP_SCOPE = "https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly"

# The authentication scheme RFC 6750 §2.1 defines for presenting an access token,
# and the one a `WWW-Authenticate` challenge for that scheme names (§3).
BEARER_SCHEME = "Bearer"

# RFC 6750 §3.1's two error codes and the status each answers with. Specification
# constants: a client distinguishes "your credential is not good" from "your
# credential is good and does not reach this" by these strings and nothing else.
INVALID_TOKEN = "invalid_token"  # noqa: S105 - an error code, not a credential
INSUFFICIENT_SCOPE = "insufficient_scope"
UNAUTHORIZED = 401
FORBIDDEN = 403

# One `parameter="value"` of an RFC 6750 §3 challenge. RFC 6750's ABNF makes the
# `error` parameter a quoted string, so the quotes are the specification's rather
# than a convenience of this parser.
CHALLENGE_PARAMETER = re.compile(r'(?P<name>[A-Za-z_-]+)\s*=\s*"(?P<value>[^"]*)"')

# How far past an access token's own stated lifetime the clock is wound to produce
# an expired one. **This suite's choice**, and a margin rather than a rule: the
# lifetime itself is read off the platform's `expires_in` so that no number here is
# a second copy of the mock's (`docs/MISTAKES.md` entry 19).
EXPIRY_MARGIN_SECONDS = 60

# A credential shape that is not an RFC 6750 bearer token. **This suite's own
# string**, and it is deliberately not JWT-shaped: it is the plainest form of "a
# value the endpoint never issued", and the JWT-shaped near miss has a test of its
# own below.
A_TOKEN_NOBODY_ISSUED = "not-a-token-this-platform-ever-issued"  # noqa: S105 - a fake, by design


# ---------------------------------------------------------------------------
# Reading the platform. Nothing below transcribes a URL or an identifier.
# ---------------------------------------------------------------------------


def roster_url(platform: Any) -> str:
    """The memberships URL of the first context this platform offers a launch into.

    Discovered through a launch's own NRPS claim, the way every other module here
    finds it: a test that named a path would be asserting against an interface
    E0-15 left open, and would keep passing against a platform that moved it.
    """
    contexts = platform.seeded_contexts()
    assert contexts, (
        "The launch page offers no launches, so no context advertises a memberships URL and there "
        "is nothing here to authorise a read of. E0-14 seeds the launches and E0-15 the roster "
        "behind them."
    )
    return contexts[0].memberships_url


def advertised_scopes(platform: Any) -> list[str]:
    """Every scope this platform says a token may be requested for."""
    document = platform.discovery() or {}
    scopes = document.get("scopes_supported")
    assert isinstance(scopes, list) and all(isinstance(scope, str) for scope in scopes), (
        f"The discovery document's `scopes_supported` is {scopes!r} rather than a list of strings "
        f"(the document carries {sorted(document)}). E1-06 puts the service scopes there, and "
        "without it this module cannot ask for a token carrying the wrong scope."
    )
    return list(scopes)


def read_roster(platform: Any, url: str, credential: str | None) -> Any:
    """One raw `GET` on the roster, carrying `credential` as its `Authorization` header.

    Deliberately **not** `MockPlatform.roster_get`: that helper attaches a valid
    token, which is the whole of what these tests vary. The `Accept` header is sent
    either way so that a refused read and an accepted one differ in one header and
    no other.
    """
    headers = {"accept": NRPS_MEDIA_TYPE}
    if credential is not None:
        headers["authorization"] = credential
    return platform.client.get(platform.local(url), headers=headers)


def challenge_parameters(challenge: str) -> dict[str, str]:
    """Every `name="value"` parameter an RFC 6750 §3 challenge carries.

    A parser rather than a substring search, for the reason
    `MockPlatform.link_relations` is a parser: `"invalid_token" in header` is a
    different question that happens to look the same, and it answers yes to a
    challenge carrying `error_description="… not an invalid_token …"`
    (`docs/MISTAKES.md` entry 3). `test_the_challenge_reader_finds_the_error_code_
    and_not_a_mention_of_it` runs it against both.
    """
    return {
        found.group("name").lower(): found.group("value")
        for found in CHALLENGE_PARAMETER.finditer(challenge)
    }


def bearer_challenge(response: Any, subject: str, control: str) -> str:
    """The `WWW-Authenticate` challenge on a refusal, required to name `Bearer`.

    The header is asserted rather than the status alone, and it is what makes this
    non-vacuous: a 401 with no challenge is indistinguishable, to a client, from a
    route that has gone wrong, and RFC 7235 §3.1 requires the header on a 401 at
    all. `Bearer` specifically is what tells a tool *which* credential to go and
    get, which is the whole reason a mock platform is worth building against.
    """
    challenge = response.headers.get("www-authenticate")
    assert isinstance(challenge, str) and challenge.strip(), (
        f"{subject} was answered {response.status_code} with no `WWW-Authenticate` header. "
        f"{control} RFC 7235 §3.1 requires the header on a 401 and RFC 6750 §3 makes it the "
        "challenge that names the scheme, which is how a client learns it needs a bearer token "
        "rather than that the roster has moved. A bare 401 is indistinguishable from a 404."
    )
    scheme = challenge.split(None, 1)[0]
    assert scheme.lower() == BEARER_SCHEME.lower(), (
        f"{subject} was challenged with {challenge!r}, whose scheme is {scheme!r} rather than "
        f"{BEARER_SCHEME!r}. {control} RFC 6750 §3 makes the challenge for a protected resource "
        "that takes an access token a `Bearer` challenge; any other scheme sends a conformant "
        "client looking for a credential this platform does not issue."
    )
    return challenge


def container_read(platform: Any, url: str, credential: str, subject: str) -> dict[str, Any]:
    """The authorised read every refusal below is posed against, required to succeed.

    Without it a refusal here could be the platform refusing every roster read —
    which passes every test in this module and serves nothing (`docs/MISTAKES.md`
    entry 3) — and it is also the criterion's own accepted half: "a token the
    endpoint issued with the scope → the current 200 behaviour, unchanged".
    """
    response = read_roster(platform, url, credential)
    assert response.status_code == 200, (
        f"{subject} answered {response.status_code} rather than 200, so the read this test poses "
        "its refusal against does not itself work and the refusal would say nothing about what "
        f"was refused. Body begins {response.text[:300]!r}."
    )
    container = response.json()
    assert isinstance(container, dict) and isinstance(container.get("members"), list), (
        f"{subject} answered 200 with {container!r}, which is not an NRPS membership container. "
        "NRPS 2.0 makes it a JSON object with `id`, `context` and `members`, and enforcement that "
        "changed what an authorised read *returns* would be a regression this pair cannot see "
        "from a status code alone."
    )
    return container


def refused(
    platform: Any,
    url: str,
    credential: str | None,
    *,
    status: int,
    code: str | None,
    subject: str,
    control: str,
) -> None:
    """Assert one roster read is refused, with the status and the RFC 6750 code that say why.

    The code is asserted rather than the status alone wherever the contract states
    one. 401 and 403 are two different instructions to a client — go and get a
    credential, versus the credential you hold will never reach this — and a
    platform answering one code for every refusal tells a tool neither.

    `code=None` is the missing-or-malformed case, and it is `None` on purpose:
    RFC 6750 §3.1 says a request carrying no authentication SHOULD NOT be told
    which error it made, because there is no credential to have got wrong. So that
    case asserts the challenge and stops there.
    """
    response = read_roster(platform, url, credential)
    assert response.status_code == status, (
        f"{subject} answered {response.status_code} rather than {status}. {control} Body begins "
        f"{response.text[:300]!r}."
    )
    challenge = bearer_challenge(response, subject, control)
    if code is None:
        return
    parameters = challenge_parameters(challenge)
    assert parameters.get("error") == code, (
        f"{subject} was challenged with {challenge!r}, whose `error` is "
        f"{parameters.get('error')!r} rather than {code!r}. {control} RFC 6750 §3.1 is the only "
        "place these strings are defined and it is the parameter a client reads: "
        f"{INVALID_TOKEN!r} means 'get a new credential' and {INSUFFICIENT_SCOPE!r} means 'ask for "
        "a different scope', and a refusal that states neither leaves a tool retrying the thing "
        "that will not work."
    )


def claims_of(token: str, subject: str) -> dict[str, Any]:
    """`token`'s claims, read without verifying anything.

    Used only by this module's guards and controls, which ask what a token *says*
    rather than whether it is good — the platform is the only thing entitled to
    answer the second question, and a test that verified a token here would be
    checking the mock's arithmetic with a second copy of it.
    """
    import jwt

    try:
        return dict(
            jwt.decode(
                token,
                options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
            )
        )
    except Exception as failure:
        pytest.fail(
            f"{subject} is not a JWT this suite can read ({type(failure).__name__}: {failure}). "
            "E1-06 mints an access token as a signed JWS — 'a signed JWS rather than an opaque "
            "string', so that a service can check one without this process having remembered "
            "anything — and the guards in this module rest on being able to read what a token "
            "states. If the mock has moved to opaque tokens, the two tests that build a forged or "
            "an expired one need rebuilding, and that is a finding about this module rather than "
            "about the platform."
        )


# ---------------------------------------------------------------------------
# Controls on this module's own machinery. **A red in this section means these
# tests are broken, not the mock platform**, and every refusal below is then
# reporting nothing.
# ---------------------------------------------------------------------------


def test_the_challenge_reader_finds_the_error_code_and_not_a_mention_of_it() -> None:
    """The parser the refusals are read through, run against both texts.

    `docs/MISTAKES.md` entry 3: a pattern searched against text is "a test that
    passed for a reason unrelated to what it asserted" wearing a disguise, so it is
    run against the text it is claimed to catch *and* the text it is claimed to
    allow. Both halves are here and neither is ceremony — a reader that answered
    `{}` for everything would make every code assertion in this module fail for a
    reason that is this file's, and a reader that matched a substring would pass a
    challenge whose `error` says one thing and whose prose mentions another.
    """
    found = challenge_parameters(
        'Bearer realm="pulse-mock-lms", error="invalid_token", '
        'error_description="the token expired at 1"'
    )
    assert found.get("error") == INVALID_TOKEN
    assert found.get("realm") == "pulse-mock-lms"
    assert found.get("error_description") == "the token expired at 1"

    described = challenge_parameters(
        f'Bearer error="{INSUFFICIENT_SCOPE}", '
        f'error_description="this is not an {INVALID_TOKEN}, the scope is wrong"'
    )
    assert described.get("error") == INSUFFICIENT_SCOPE, (
        "The reader took an error code out of the human-readable description rather than out of "
        "the `error` parameter, so a platform answering the right status with the wrong code "
        "would be read as correct."
    )

    assert challenge_parameters("Bearer") == {}
    assert challenge_parameters("") == {}


def test_the_token_helper_obtains_a_credential_the_platform_itself_granted(
    mock_platform: Any,
) -> None:
    """The machinery every accepted half of every pair below rests on.

    `MockPlatform.service_token` is new: if it handed back a string it made up, or
    one obtained some way the platform does not sanction, every accepted read in
    this module would fail and every refusal would pass — a module reporting a
    conformant platform having proved nothing.

    Two things say it is a real grant, and the second is the one that cannot be
    faked from this side: the response carries RFC 6749 §5.1's `token_type` and the
    scope that was asked for, **and** the platform fetched the tool's key set while
    it was verifying the assertion. A helper that minted a token locally would fetch
    nothing.

    **A red here means these tests are broken, not the mock platform.**
    """
    before = len(mock_platform.tool_key_set.requested)
    granted = mock_platform.service_token_grant(NRPS_MEMBERSHIP_SCOPE)

    token = granted.get("access_token")
    assert isinstance(token, str) and token, (
        f"The grant answered {granted!r}, which carries no `access_token` — so the helper handed "
        "back nothing to present and every accepted read below is about an empty credential."
    )
    assert str(granted.get("token_type", "")).lower() == BEARER_SCHEME.lower(), (
        f"The grant states `token_type` {granted.get('token_type')!r} rather than "
        f"{BEARER_SCHEME!r}, so this suite is presenting the token under a scheme the platform did "
        "not issue it for."
    )
    assert NRPS_MEMBERSHIP_SCOPE in str(granted.get("scope", "")).split(), (
        f"A token was asked for {NRPS_MEMBERSHIP_SCOPE!r} and granted with `scope` "
        f"{granted.get('scope')!r}, so the credential the accepted halves below present is not the "
        "one they say it is."
    )
    assert len(mock_platform.tool_key_set.requested) > before, (
        "The platform granted a token without fetching the tool's key set, so either it verified "
        "nothing — which `test_mock_lms_client_credentials_grant.py` diagnoses — or this helper "
        "did not go through the platform's endpoint at all and the credential it returns is its "
        "own invention."
    )


def test_the_forged_token_these_tests_build_is_a_twin_of_a_granted_one(
    mock_platform: Any,
    key_the_tool_never_published: Any,
) -> None:
    """The forged credential, checked against a real one before a refusal rests on it.

    `test_a_token_signed_by_a_key_the_platform_does_not_use_is_refused` claims the
    platform refuses a token *because of who signed it*. That claim is only worth
    something if the forgery is otherwise indistinguishable: a token that also
    named the wrong issuer, or carried no scope, or had already expired, would be
    refused by a platform checking any one of those and the test would read that as
    a signature check (`docs/MISTAKES.md` entry 3).

    So both are decoded here and compared claim by claim. The one thing that must
    differ is the signature.

    **A red here means these tests are broken, not the mock platform.**
    """
    granted = str(mock_platform.service_token_grant(NRPS_MEMBERSHIP_SCOPE)["access_token"])
    forged = forged_access_token(mock_platform, key_the_tool_never_published)

    real_claims = claims_of(granted, "The token the platform granted")
    forged_claims = claims_of(forged, "The token these tests forged")

    assert set(forged_claims) >= set(real_claims) - {"jti"}, (
        f"The forged token states {sorted(forged_claims)} and a granted one states "
        f"{sorted(real_claims)}. A claim the platform puts in and this forgery leaves out is a "
        "second thing the refusal could be about, so the test that rests on this would not be "
        "about the signature."
    )
    for claim in ("iss", "aud", "sub", "scope"):
        assert forged_claims.get(claim) == real_claims.get(claim), (
            f"The forged token states `{claim}` {forged_claims.get(claim)!r} and a granted one "
            f"states {real_claims.get(claim)!r}. The forgery has to agree with a real token about "
            "everything except who signed it."
        )
    assert float(forged_claims.get("exp", 0)) > time.time(), (
        f"The forged token expired at {forged_claims.get('exp')!r} and it is now "
        f"{int(time.time())}, so a platform refusing it would be refusing an expired token and "
        "the signature would never be reached."
    )
    assert granted.rsplit(".", 1)[-1] != forged.rsplit(".", 1)[-1], (
        "The forged token and the granted one carry the same signature, so the two keys these "
        "tests use are one key and the refusal that rests on them is about nothing."
    )


def forged_access_token(platform: Any, stranger: Any) -> str:
    """An access token that says everything a granted one says, signed by nobody's key.

    Every value is read off the platform rather than transcribed: the issuer and
    the audience out of its discovery document, the subject out of the client id
    its launch form publishes, the `kid` out of the key set it serves. The `kid` in
    particular is the platform's own, which is the near miss for an implementation
    that selects a key by the header's `kid` and then trusts the token because a key
    was found — a mangled signature would be refused by a verifier that does no key
    selection at all, and the test would read that as key selection working.
    """
    import uuid

    document = platform.discovery() or {}
    issuer = document.get("issuer")
    assert isinstance(issuer, str) and issuer, (
        f"The discovery document states no `issuer` (it carries {sorted(document)}), so a forged "
        "token cannot claim to have come from this platform and its refusal would be about a "
        "token that is wrong in two ways."
    )
    client_id = platform.require_offers()[0].parameters.get("client_id")
    assert isinstance(client_id, str) and client_id, (
        "The launch form publishes no `client_id`, so a forged token cannot name the subject a "
        "granted one names."
    )
    published = platform.published_keys()
    assert published, "The platform publishes no keys, so there is no `kid` to forge a header with."

    issued = int(time.time())
    return stranger.sign(
        {
            "iss": issuer,
            "sub": client_id,
            "aud": issuer,
            "jti": uuid.uuid4().hex,
            "iat": issued,
            "exp": issued + 3600,
            "scope": NRPS_MEMBERSHIP_SCOPE,
        },
        kid=str(published[0].get("kid") or ""),
    )


# ---------------------------------------------------------------------------
# Missing and malformed credentials — 401 with a `Bearer` challenge.
# ---------------------------------------------------------------------------


def test_a_roster_read_carrying_no_authorization_header_is_refused_with_a_bearer_challenge(
    mock_platform: Any,
) -> None:
    """The contract's first line, and the state of this route at HEAD.

    **The mutation this kills:** no enforcement at all, which is what the mock does
    today — `mock-lms/app/main.py`'s Advantage comment says so in as many words, and
    E1-06's carried entry records that "the Advantage services still answer without
    a token". Anything that can reach the container reads the class list.

    **The near misses it is written around.** A 404 would also stop the read and
    would tell a tool the roster is not there, sending its author looking for the
    URL rather than for a credential; a 403 would tell it the credential it does not
    have would not have helped. Both are excluded by asserting the status and the
    `WWW-Authenticate` challenge together — the header is what distinguishes
    "refused for authentication" from "gone", and it is why an assertion on the
    absence of members would be the wrong test entirely.

    The authorised read comes first and is the criterion's own accepted half: the
    container still answers exactly as it did.
    """
    url = roster_url(mock_platform)
    container_read(
        mock_platform,
        url,
        f"{BEARER_SCHEME} {mock_platform.service_token(NRPS_MEMBERSHIP_SCOPE)}",
        "A roster read presenting a token this platform granted for the membership scope",
    )

    refused(
        mock_platform,
        url,
        None,
        status=UNAUTHORIZED,
        code=None,
        subject="A roster read carrying no `Authorization` header at all",
        control="The identical read presenting a granted token was answered 200 a moment ago,",
    )


def test_a_roster_read_whose_credential_is_not_a_bearer_token_is_refused(
    mock_platform: Any,
) -> None:
    """The malformed half of the same line, over the shapes a fail-open check accepts.

    **The mutations these kill, one per shape.**

      - `Basic …` with junk: an enforcement written as `"authorization" in
        request.headers`, which is the cheapest thing that passes the test above
        and authorises anybody who sends any header at all.
      - `Basic <a genuine token>`: the near miss, and the reason this shape is
        here. An enforcement that takes the last whitespace-separated word of the
        header — `header.split()[-1]` — reads a perfectly good token out of a
        scheme this platform does not accept, and every other case in this module
        stays green. RFC 6750 §2.1 makes the credential `Bearer` and nothing else.
      - `Bearer` with an empty credential: a check that splits on a space and does
        not ask whether anything followed it, which then looks a token up by the
        empty string.
      - the bare token with no scheme: a check that treats the whole header value
        as the credential, which accepts a client that forgot the scheme and would
        accept the same value in `Basic` clothing.

    Each shape gets the challenge asserted, not just the status, for the reason the
    test above gives: a client that is told nothing goes looking for the URL.
    """
    url = roster_url(mock_platform)
    token = mock_platform.service_token(NRPS_MEMBERSHIP_SCOPE)
    container_read(
        mock_platform,
        url,
        f"{BEARER_SCHEME} {token}",
        "A roster read presenting that same token under the `Bearer` scheme",
    )

    for credential, description in (
        ("Basic cHVsc2U6bm90LWEtdG9rZW4=", "a `Basic` credential"),
        (f"Basic {token}", "a granted token presented under the `Basic` scheme"),
        (f"{BEARER_SCHEME} ", "a `Bearer` scheme with no credential after it"),
        (token, "a granted token with no scheme in front of it"),
    ):
        refused(
            mock_platform,
            url,
            credential,
            status=UNAUTHORIZED,
            code=None,
            subject=f"A roster read carrying {description}",
            control=(
                "The identical read presenting the same token as `Bearer <token>` was answered "
                "200 a moment ago,"
            ),
        )


# ---------------------------------------------------------------------------
# Credentials this endpoint never issued, or issued and outlived — 401,
# `invalid_token`.
# ---------------------------------------------------------------------------


def test_a_credential_the_token_endpoint_never_issued_is_refused_as_an_invalid_token(
    mock_platform: Any,
) -> None:
    """The contract's second line, in its plainest form.

    **The mutation this kills:** an enforcement that checks the header is present
    and well formed and never asks whether the token is one this platform issued.
    That passes both tests above completely — the header is there, it names
    `Bearer`, it carries something — and hands the roster to anyone who types the
    word.

    The credential here is deliberately not JWT-shaped, so the refusal is about the
    token being unknown rather than about it being unreadable; the JWT-shaped near
    miss is the test below, and the two fail for different reasons.
    """
    url = roster_url(mock_platform)
    container_read(
        mock_platform,
        url,
        f"{BEARER_SCHEME} {mock_platform.service_token(NRPS_MEMBERSHIP_SCOPE)}",
        "A roster read presenting a token this platform granted",
    )

    refused(
        mock_platform,
        url,
        f"{BEARER_SCHEME} {A_TOKEN_NOBODY_ISSUED}",
        status=UNAUTHORIZED,
        code=INVALID_TOKEN,
        subject=f"A roster read presenting the string {A_TOKEN_NOBODY_ISSUED!r} as a bearer token",
        control="A read presenting a token this platform granted was answered 200 a moment ago,",
    )


def test_a_token_signed_by_a_key_the_platform_does_not_use_is_refused(
    mock_platform: Any,
    key_the_tool_never_published: Any,
) -> None:
    """The near miss for the same line: a credential that is wrong in exactly one way.

    **The mutation this kills:** an enforcement that decodes the token and reads
    its `scope` claim without establishing that this platform issued it. That is
    the cheapest implementation that passes every other test in this module — the
    header is well formed, the token is a readable JWT, the scope is right — and it
    authorises anybody who can write a JSON object, which is what E1-06's own
    argument for a *signed* access token was about: "when a service on this platform
    starts requiring a token, it can check one without this process having
    remembered anything".

    It also kills the narrower version that selects a key by the header's `kid` and
    trusts the token because a key was found: the forgery carries the platform's own
    published `kid`.

    The forged token is a real RS256 signature by a real 2048-bit key rather than a
    corrupted one — a mangled signature is refused by a verifier that does no key
    selection at all, and this test would read that as verification working.
    `test_the_forged_token_these_tests_build_is_a_twin_of_a_granted_one` is what
    says the two differ in nothing else.
    """
    url = roster_url(mock_platform)
    container_read(
        mock_platform,
        url,
        f"{BEARER_SCHEME} {mock_platform.service_token(NRPS_MEMBERSHIP_SCOPE)}",
        "A roster read presenting a token this platform signed",
    )

    refused(
        mock_platform,
        url,
        f"{BEARER_SCHEME} {forged_access_token(mock_platform, key_the_tool_never_published)}",
        status=UNAUTHORIZED,
        code=INVALID_TOKEN,
        subject=(
            "A roster read presenting a token that states everything a granted one states, "
            "carries the platform's own `kid`, and is signed by a key the platform does not have"
        ),
        control=(
            "The identical read presenting a token this platform actually signed was answered 200 "
            "a moment ago,"
        ),
    )


def test_an_expired_access_token_is_refused_and_a_fresh_one_is_accepted(
    mock_platform: Any,
    wind_the_clock_back: Any,
) -> None:
    """The other half of the second line, asserted from both sides of the expiry.

    **The mutations this kills, and each is invisible to the other half.** An
    enforcement that recognises a token this platform issued and never compares its
    `exp` to a clock — the state of every JOSE library asked to decode without
    verification options, and a credential that never stops working wherever it
    leaks. And, from the accepted side, an enforcement whose clock arithmetic runs
    the wrong way and refuses everything, which would pass the refused half alone.

    **Where the number comes from.** The wind is `expires_in` — the platform's own
    answer, read off the fresh grant — plus a margin, so nothing here is a second
    copy of the mock's token lifetime (`docs/MISTAKES.md` entry 19). A test holding
    `3600` would go quietly wrong the day that value changed and would report the
    change as a defect in the enforcement.

    The expired token is produced by winding the clock back for the grant alone, so
    it is a well-formed token that was issued an hour ago rather than a malformed
    one whose `exp` precedes its `iat` — a platform is entitled to refuse the second
    for a different reason, and the test would then pass against one that checks no
    clock at all (`docs/MISTAKES.md` entry 3).
    """
    url = roster_url(mock_platform)
    fresh = mock_platform.service_token_grant(NRPS_MEMBERSHIP_SCOPE)
    container_read(
        mock_platform,
        url,
        f"{BEARER_SCHEME} {fresh['access_token']}",
        "A roster read presenting a token granted moments ago",
    )

    lifetime = fresh.get("expires_in")
    assert isinstance(lifetime, int) and not isinstance(lifetime, bool) and lifetime > 0, (
        f"The grant states `expires_in` {lifetime!r}, so this test cannot work out how far to wind "
        "the clock back to obtain a token that has already expired, and the pair below would be "
        "about something else."
    )

    with wind_the_clock_back(lifetime + EXPIRY_MARGIN_SECONDS):
        stale = str(mock_platform.service_token_grant(NRPS_MEMBERSHIP_SCOPE)["access_token"])

    expires_at = claims_of(stale, "The token this test means to be expired").get("exp")
    assert isinstance(expires_at, int | float) and expires_at < time.time(), (
        f"The token this test means to be expired states `exp` {expires_at!r} and it is now "
        f"{int(time.time())}, so it is still live and the refusal below would be about something "
        "else entirely."
    )

    refused(
        mock_platform,
        url,
        f"{BEARER_SCHEME} {stale}",
        status=UNAUTHORIZED,
        code=INVALID_TOKEN,
        subject=(
            f"A roster read presenting a token this platform issued {lifetime}s of stated lifetime "
            "ago, which has since expired"
        ),
        control=(
            "The identical read presenting a token from the same endpoint, inside its own "
            "lifetime, was answered 200 a moment ago,"
        ),
    )


# ---------------------------------------------------------------------------
# A credential this endpoint issued for something else — 403,
# `insufficient_scope`.
# ---------------------------------------------------------------------------


def test_a_token_granted_without_the_membership_scope_is_refused_as_insufficient_scope(
    mock_platform: Any,
) -> None:
    """The contract's third line, over every other scope this platform advertises.

    **The mutations this kills.** An enforcement that establishes the token is one
    this platform issued and never reads what it was issued *for*: E1-06's token
    endpoint grants `…/scope/score` to the same client on request, so a roster
    behind a scope-blind check is a roster any AGS token opens. And, narrower, an
    enforcement that requires the token to carry *some* scope, which the AGS
    parameters below satisfy.

    **Every advertised scope but the membership one is asked, rather than a chosen
    couple** (`docs/MISTAKES.md` entry 15): the platform's own `scopes_supported` is
    the set, so a scope added to that list later is covered here the day it is added
    rather than being the one case a hand-written parametrisation missed.

    403 rather than 401, per RFC 6750 §3.1, and the difference is the whole point of
    stating a code: the credential is good and will never reach this, so a client
    that retried with a fresh token of the same scope would loop forever.
    """
    url = roster_url(mock_platform)
    advertised = advertised_scopes(mock_platform)
    assert NRPS_MEMBERSHIP_SCOPE in advertised, (
        f"The platform advertises {advertised!r} and not {NRPS_MEMBERSHIP_SCOPE!r}, so no token "
        "can be requested for the roster at all and the accepted half below is unreachable. E1-06 "
        "adds it; `test_mock_lms_client_credentials_grant.py` diagnoses its absence."
    )
    others = [scope for scope in advertised if scope != NRPS_MEMBERSHIP_SCOPE]
    assert others, (
        f"The platform advertises only {advertised!r}, so there is no scope a token can be granted "
        "for that does not open the roster, and this test cannot pose its question at all."
    )

    container_read(
        mock_platform,
        url,
        f"{BEARER_SCHEME} {mock_platform.service_token(NRPS_MEMBERSHIP_SCOPE)}",
        f"A roster read presenting a token granted for {NRPS_MEMBERSHIP_SCOPE!r}",
    )

    for scope in others:
        refused(
            mock_platform,
            url,
            f"{BEARER_SCHEME} {mock_platform.service_token(scope)}",
            status=FORBIDDEN,
            code=INSUFFICIENT_SCOPE,
            subject=f"A roster read presenting a token this platform granted for {scope!r}",
            control=(
                "The identical read presenting a token granted for the membership scope was "
                "answered 200 a moment ago, so the platform does serve this roster,"
            ),
        )


def test_a_token_carrying_the_membership_scope_beside_another_is_accepted(
    mock_platform: Any,
) -> None:
    """The accepted half the wrong-scope test cannot pose, and the mutation it kills.

    **The mutation:** a scope check written as equality — `granted == MEMBERSHIP_
    SCOPE` — rather than membership of the space-delimited list RFC 6749 §3.3
    defines. It passes every other test in this module: a single-scope token is
    accepted and every wrong-scope token is refused. What it breaks is a real
    client, because `pylti1p3` asks its token endpoint for whichever scopes the
    launch's service claims advertise, and a tool that will also post grades asks
    for the AGS scopes in the same breath.

    The grant is asserted to have carried both scopes before the read is believed:
    a platform that quietly dropped one would make this test an assertion about a
    membership-only token, which the test above already makes.
    """
    url = roster_url(mock_platform)
    advertised = advertised_scopes(mock_platform)
    others = [scope for scope in advertised if scope != NRPS_MEMBERSHIP_SCOPE]
    assert others, (
        f"The platform advertises only {advertised!r}, so no token can carry the membership scope "
        "*beside* another one and the equality mutation this test exists for is not expressible."
    )
    beside = others[0]

    granted = mock_platform.service_token_grant(f"{beside} {NRPS_MEMBERSHIP_SCOPE}")
    carried = str(granted.get("scope", "")).split()
    assert {beside, NRPS_MEMBERSHIP_SCOPE} <= set(carried), (
        f"A token was asked for {beside!r} and {NRPS_MEMBERSHIP_SCOPE!r} together and granted with "
        f"`scope` {granted.get('scope')!r}. A platform that dropped one of them leaves this test "
        "presenting a single-scope token, which says nothing about how the roster reads a list."
    )

    container_read(
        mock_platform,
        url,
        f"{BEARER_SCHEME} {granted['access_token']}",
        f"A roster read presenting a token granted for {beside!r} and the membership scope together",
    )
